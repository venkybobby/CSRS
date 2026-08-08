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
from shared.messages import rate_not_found_message
from csr_agent.tools.models import (
    CostEstimateResult,
    ExclusionResult,
    MemberNotFoundResult,
    PreventiveZeroCostResult,
    ProcedureMatchResult,
    RateNotFoundResult,
    StandardCostResult,
    TermedMemberResult,
)


def _log(
    *,
    audit_id,
    member_id: str,
    cpt_code: str | None,
    response_type: str,
    result: "CostEstimateResult",
    source_data_snapshot: dict,
    csr_user_id: str,
    session_id: str,
    invocation_id: str,
    trace_id: str,
) -> None:
    write_audit_log(
        audit_id=audit_id,
        csr_user_id=csr_user_id,
        session_id=session_id,
        invocation_id=invocation_id,
        trace_id=trace_id,
        member_id=member_id,
        cpt_code=cpt_code,
        response_type=response_type,
        request_snapshot={"member_id": member_id, "cpt_code": cpt_code},
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
) -> CostEstimateResult:
    elig = get_eligibility(member_id, today=today)

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
        )
        return result

    if elig.status == "TERMED":
        result = TermedMemberResult(
            eligibility=elig,
            message=(
                f"{elig.name} is not eligible as of "
                f"{elig.coverage_end.isoformat() if elig.coverage_end else 'unknown date'}. "
                "Do not quote a cost."
            ),
            audit_id=uuid4(),
        )
        _log(
            audit_id=result.audit_id, member_id=member_id, cpt_code=cpt_code,
            response_type=result.response_type, result=result,
            source_data_snapshot={"eligibility": elig.model_dump(mode="json")},
            csr_user_id=csr_user_id, session_id=session_id,
            invocation_id=invocation_id, trace_id=trace_id,
        )
        return result

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
        )
        return result

    if cpt_code in plan.preventive_covered_100pct_codes:
        result = PreventiveZeroCostResult(
            eligibility=elig,
            cpt_code=cpt_code,
            common_name=cpt_code,
            message=(
                f"Member owes $0. {cpt_code} is covered at 100% as a preventive benefit "
                f"under {plan.display_name}. No deductible or coinsurance applies."
            ),
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

    result = StandardCostResult(
        eligibility=elig,
        procedure=ProcedureMatchResult(
            query=cpt_code, status="MATCHED", cpt_code=cpt_code, negotiated_rate=rate.negotiated_rate
        ),
        breakdown=breakdown,
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
    )
    return result
