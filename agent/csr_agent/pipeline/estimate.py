"""The composite deterministic pipeline behind the estimate_member_cost
tool. This is the ONE place the eligibility -> exclusion -> preventive ->
prior-auth -> calculator ordering is enforced (plan §2.1): the LLM never
re-derives this sequence itself, it just calls this function once with a
member_id and an already-resolved cpt_code.

Every branch returns before the calculator runs except the final one, and
every branch writes an audit log entry -- termed-blocks and exclusions are
compliance-relevant events too, not just priced quotes.
"""
from __future__ import annotations

from datetime import date
from uuid import uuid4

from csr_agent.calculator.family import family_tier_cost
from csr_agent.calculator.individual import individual_tier_cost
from csr_agent.data.audit import write_audit_log
from csr_agent.data.eligibility import get_eligibility, get_member_accumulators, get_plan
from csr_agent.data.rate_matcher import get_rate
from csr_agent.pipeline.date_of_service import (
    MAX_DAYS_OUT,
    check_window,
    crosses_plan_year,
    max_quotable_date,
    not_eligible_reason_and_message,
    plan_year_end,
)
from csr_agent.tools.models import (
    CostEstimateResult,
    DateOfServiceInvalidResult,
    ExclusionResult,
    MemberNotFoundResult,
    NotEligibleOnDateResult,
    PlanYearBoundaryResult,
    PreventiveZeroCostResult,
    ProcedureMatchResult,
    RateNotFoundResult,
    StandardCostResult,
    TermedMemberResult,
)
from shared.messages import (
    accumulator_assumption_note,
    date_of_service_in_past_message,
    date_of_service_too_far_out_message,
    plan_year_boundary_message,
    rate_not_found_message,
    termed_member_message,
)

# Narrower than the public CostEstimateResult union: this pipeline never
# produces NeedsClarificationResult (that variant only exists at the BFF
# layer, synthesized from resolve_procedure's own output -- see
# bff/app/main.py::_extract_agent_turn). Every branch below has an
# audit_id; NeedsClarificationResult doesn't, which is exactly what mypy
# caught when `result` was typed against the full public union instead of
# this one.
PipelineResult = (
    MemberNotFoundResult
    | DateOfServiceInvalidResult
    | TermedMemberResult
    | NotEligibleOnDateResult
    | PlanYearBoundaryResult
    | ExclusionResult
    | RateNotFoundResult
    | PreventiveZeroCostResult
    | StandardCostResult
)


def _log(
    *,
    audit_id,
    member_id: str,
    cpt_code: str | None,
    response_type: str,
    result: PipelineResult,
    source_data_snapshot: dict,
    csr_user_id: str,
    session_id: str,
    invocation_id: str,
    trace_id: str,
    date_of_service: date | None = None,
) -> None:
    # date_of_service belongs in request_snapshot, not source_data_snapshot:
    # it is part of what the CSR ASKED, and a dispute three weeks later turns
    # on which date the quote was for. Omitted entirely rather than defaulted
    # to today when unstated, so the audit row never implies the CSR named a
    # date they did not.
    request_snapshot: dict = {"member_id": member_id, "cpt_code": cpt_code}
    if date_of_service is not None:
        request_snapshot["date_of_service"] = date_of_service.isoformat()

    write_audit_log(
        audit_id=audit_id,
        csr_user_id=csr_user_id,
        session_id=session_id,
        invocation_id=invocation_id,
        trace_id=trace_id,
        member_id=member_id,
        cpt_code=cpt_code,
        response_type=response_type,
        request_snapshot=request_snapshot,
        result_snapshot=result.model_dump(mode="json"),
        source_data_snapshot=source_data_snapshot,
    )


def estimate_member_cost(
    member_id: str,
    cpt_code: str,
    *,
    csr_user_id: str,
    session_id: str,
    invocation_id: str,
    trace_id: str,
    today: date | None = None,
    date_of_service: date | None = None,
) -> CostEstimateResult:
    today = today or date.today()

    # Request-level validation, before the member is even looked up: an
    # unquotable date is a property of the request, not of the member, and
    # answering it needs no DB read.
    if date_of_service is not None:
        problem = check_window(date_of_service, today)
        if problem is not None:
            message = (
                date_of_service_in_past_message(
                    date_of_service.isoformat(), today.isoformat()
                )
                if problem == "IN_PAST"
                else date_of_service_too_far_out_message(
                    date_of_service.isoformat(),
                    max_quotable_date(today).isoformat(),
                    MAX_DAYS_OUT,
                )
            )
            result: PipelineResult = DateOfServiceInvalidResult(
                member_id=member_id,
                date_of_service=date_of_service,
                reason=problem,
                message=message,
                audit_id=uuid4(),
            )
            _log(
                audit_id=result.audit_id, member_id=member_id, cpt_code=cpt_code,
                response_type=result.response_type, result=result,
                source_data_snapshot={
                    "date_of_service": date_of_service.isoformat(),
                    "quoted_on": today.isoformat(),
                    "window_problem": problem,
                },
                csr_user_id=csr_user_id, session_id=session_id,
                invocation_id=invocation_id, trace_id=trace_id,
                date_of_service=date_of_service,
            )
            return result

    elig = get_eligibility(member_id, today=today, date_of_service=date_of_service)

    if not elig.found:
        result = MemberNotFoundResult(
            member_id=member_id,
            message=f"No member found for ID '{member_id}'. Do not estimate a cost.",
            audit_id=uuid4(),
        )
        _log(
            audit_id=result.audit_id, member_id=member_id, cpt_code=cpt_code,
            response_type=result.response_type, result=result,
            source_data_snapshot={"member_found": False},
            csr_user_id=csr_user_id, session_id=session_id,
            invocation_id=invocation_id, trace_id=trace_id,
            date_of_service=date_of_service,
        )
        return result

    if elig.status == "TERMED":
        # Same model-optionality gap as the plan_id assert below: found is
        # True here, and a found member row always carries a name.
        assert elig.name is not None
        result = TermedMemberResult(
            eligibility=elig,
            message=termed_member_message(
                elig.name, elig.coverage_end.isoformat() if elig.coverage_end else "unknown date"
            ),
            audit_id=uuid4(),
        )
        _log(
            audit_id=result.audit_id, member_id=member_id, cpt_code=cpt_code,
            response_type=result.response_type, result=result,
            source_data_snapshot={"eligibility": elig.model_dump(mode="json")},
            csr_user_id=csr_user_id, session_id=session_id,
            invocation_id=invocation_id, trace_id=trace_id,
            date_of_service=date_of_service,
        )
        return result

    # Not termed, but outside the coverage window on the requested date.
    # Distinct from TERMED_BLOCK on purpose: this member is very likely
    # eligible TODAY, which is exactly why quoting them would be wrong.
    if elig.status == "NOT_COVERED_ON_DOS":
        assert elig.name is not None
        assert date_of_service is not None  # the only way this status is reachable

        reason, message = not_eligible_reason_and_message(
            elig.name, elig.coverage_start, elig.coverage_end, date_of_service
        )
        result = NotEligibleOnDateResult(
            eligibility=elig,
            date_of_service=date_of_service,
            reason=reason,
            message=message,
            audit_id=uuid4(),
        )
        _log(
            audit_id=result.audit_id, member_id=member_id, cpt_code=cpt_code,
            response_type=result.response_type, result=result,
            source_data_snapshot={"eligibility": elig.model_dump(mode="json")},
            csr_user_id=csr_user_id, session_id=session_id,
            invocation_id=invocation_id, trace_id=trace_id,
            date_of_service=date_of_service,
        )
        return result

    # The member IS eligible on this date -- we simply cannot price it.
    #
    # Positioned ahead of the exclusion and preventive branches rather than
    # just ahead of the calculator, because the plan record is year-scoped
    # too (plan_ids are literally "MER-SLV-2026"). Next year's exclusion list
    # and preventive list are no more on file than next year's accumulators,
    # so "acupuncture is excluded" and "screening colonoscopy is $0" are not
    # year-independent answers either.
    if date_of_service is not None and crosses_plan_year(date_of_service, today):
        assert elig.name is not None
        assert elig.plan_id is not None
        result = PlanYearBoundaryResult(
            eligibility=elig,
            date_of_service=date_of_service,
            plan_year_end=plan_year_end(today),
            message=plan_year_boundary_message(
                elig.name,
                date_of_service.isoformat(),
                plan_year_end(today).isoformat(),
                elig.plan_id,
            ),
            audit_id=uuid4(),
        )
        _log(
            audit_id=result.audit_id, member_id=member_id, cpt_code=cpt_code,
            response_type=result.response_type, result=result,
            source_data_snapshot={
                "eligibility": elig.model_dump(mode="json"),
                "plan_year_end": plan_year_end(today).isoformat(),
                "note": "accumulators and plan terms are current-year-scoped",
            },
            csr_user_id=csr_user_id, session_id=session_id,
            invocation_id=invocation_id, trace_id=trace_id,
            date_of_service=date_of_service,
        )
        return result

    # elig.found is True here (the not-found branch above already returned),
    # so plan_id is guaranteed non-None on a found member row -- but that
    # invariant lives in the EligibilityResult model's optional typing, not
    # something mypy can see through the .found check alone.
    assert elig.plan_id is not None
    plan = get_plan(elig.plan_id)
    if plan is None:
        raise RuntimeError(f"Member {member_id} references unknown plan_id {elig.plan_id!r}")

    if cpt_code in plan.excluded_codes:
        result = ExclusionResult(
            eligibility=elig,
            cpt_code=cpt_code,
            plan_id=plan.plan_id,
            message=(
                f"This procedure ({cpt_code}) is excluded from {plan.display_name}. "
                "It is not a covered benefit. Do not quote a cost."
            ),
            audit_id=uuid4(),
        )
        _log(
            audit_id=result.audit_id, member_id=member_id, cpt_code=cpt_code,
            response_type=result.response_type, result=result,
            source_data_snapshot={
                "eligibility": elig.model_dump(mode="json"),
                "plan_excluded_codes": sorted(plan.excluded_codes),
            },
            csr_user_id=csr_user_id, session_id=session_id,
            invocation_id=invocation_id, trace_id=trace_id,
            date_of_service=date_of_service,
        )
        return result

    rate = get_rate(cpt_code)
    if rate is None:
        result = RateNotFoundResult(
            eligibility=elig,
            procedure_query=cpt_code,
            message=rate_not_found_message(cpt_code),
            audit_id=uuid4(),
        )
        _log(
            audit_id=result.audit_id, member_id=member_id, cpt_code=cpt_code,
            response_type=result.response_type, result=result,
            source_data_snapshot={"eligibility": elig.model_dump(mode="json"), "rate_found": False},
            csr_user_id=csr_user_id, session_id=session_id,
            invocation_id=invocation_id, trace_id=trace_id,
            date_of_service=date_of_service,
        )
        return result

    if cpt_code in plan.preventive_covered_100pct_codes:
        preventive_message = (
            f"Member owes $0. {cpt_code} is covered at 100% as a preventive benefit "
            f"under {plan.display_name}. No deductible or coinsurance applies."
        )
        # No accumulator assumption note here, unlike STANDARD_COST: the
        # preventive path short-circuits before accumulators are read at all,
        # so its $0 does not depend on balances that could drift before the
        # date of service. Adding the caveat anyway would imply a fragility
        # this answer does not have.
        if date_of_service is not None:
            preventive_message += f" Date of service: {date_of_service.isoformat()}."
        result = PreventiveZeroCostResult(
            eligibility=elig,
            cpt_code=cpt_code,
            common_name=cpt_code,
            date_of_service=date_of_service,
            message=preventive_message,
            audit_id=uuid4(),
        )
        _log(
            audit_id=result.audit_id, member_id=member_id, cpt_code=cpt_code,
            response_type=result.response_type, result=result,
            source_data_snapshot={
                "eligibility": elig.model_dump(mode="json"),
                "note": "preventive short-circuit -- accumulators never read",
            },
            csr_user_id=csr_user_id, session_id=session_id,
            invocation_id=invocation_id, trace_id=trace_id,
            date_of_service=date_of_service,
        )
        return result

    accumulators = get_member_accumulators(member_id)
    if accumulators is None:
        raise RuntimeError(f"Member {member_id} has no member_accumulators row")

    if elig.tier == "FAMILY":
        breakdown = family_tier_cost(plan=plan.terms, rate=rate, accumulators=accumulators)
    else:
        breakdown = individual_tier_cost(plan=plan.terms, rate=rate, accumulators=accumulators)

    breakdown.prior_auth_required = cpt_code in plan.prior_auth_required_codes

    message = (
        f"Estimated member cost: ${breakdown.member_cost}. "
        f"Deductible applied: ${breakdown.applied_to_deductible}, "
        f"coinsurance ({breakdown.coinsurance_pct * 100}%): ${breakdown.coinsurance_amount}."
    )
    if breakdown.oop_cap_triggered:
        message += " Out-of-pocket maximum reached -- cost capped."
    if breakdown.prior_auth_required:
        message += (
            f" ⚠️ Prior authorization required for {cpt_code} under {plan.display_name}. "
            "Advise member to obtain auth before service. Cost estimate shown assumes "
            "auth is approved."
        )
    if elig.warning:
        message += f" {elig.warning}"

    # The line Meridian is quoting to Compliance: eligibility is exact as of
    # the date of service, but this dollar figure is not. member_accumulators
    # holds one current-balance row -- no history, no projection -- so a
    # future-dated quote is only as good as today's balances. Stated on the
    # quote rather than assumed, so it survives into the audit snapshot and
    # onto anything the CSR later sends the member.
    if date_of_service is not None:
        message += (
            f" Date of service: {date_of_service.isoformat()}. "
            + accumulator_assumption_note(today.isoformat(), date_of_service.isoformat())
        )

    result = StandardCostResult(
        eligibility=elig,
        procedure=ProcedureMatchResult(
            query=cpt_code, status="MATCHED", cpt_code=cpt_code, negotiated_rate=rate.negotiated_rate
        ),
        breakdown=breakdown,
        date_of_service=date_of_service,
        message=message,
        audit_id=uuid4(),
    )
    _log(
        audit_id=result.audit_id, member_id=member_id, cpt_code=cpt_code,
        response_type=result.response_type, result=result,
        source_data_snapshot={
            "eligibility": elig.model_dump(mode="json"),
            "plan_terms": {
                "deductible_individual": str(plan.terms.deductible_individual),
                "deductible_family": str(plan.terms.deductible_family),
                "coinsurance_pct": str(plan.terms.coinsurance_pct),
                "oop_max_individual": str(plan.terms.oop_max_individual),
                "oop_max_family": str(plan.terms.oop_max_family),
            },
            "rate": {"cpt_code": rate.cpt_code, "negotiated_rate": str(rate.negotiated_rate)},
            "accumulators": {
                "ind_ded_met": str(accumulators.ind_ded_met),
                "ind_oop_met": str(accumulators.ind_oop_met),
                "fam_ded_met": str(accumulators.fam_ded_met),
                "fam_oop_met": str(accumulators.fam_oop_met),
            },
        },
        csr_user_id=csr_user_id, session_id=session_id,
        invocation_id=invocation_id, trace_id=trace_id,
        date_of_service=date_of_service,
    )
    return result
