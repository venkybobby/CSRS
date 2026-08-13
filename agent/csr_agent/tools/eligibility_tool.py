"""ADK tool wrapper around data/eligibility.py::get_eligibility().

Mostly thin, with one deliberate exception: a TERMED result is upgraded to
a full TermedMemberResult (response_type TERMED_BLOCK, minted audit_id,
audit log row) before it goes back to the model. agent.py's instruction
tells the model to STOP right after this call for a termed member -- it
never reaches estimate_member_cost's pipeline, which is the only other
place a TERMED_BLOCK would otherwise get built. Without this, a termed-
member refusal had no response_type for the BFF to key its structured
result off of (frontend fell back to dumping the model's raw AgentResponse
JSON as plain text) and, more importantly, was never written to
quote_audit_log at all -- an unaudited refusal, for a compliance tool where
every quote/block is supposed to be traceable.
"""
from __future__ import annotations

from uuid import uuid4

from google.adk.tools.tool_context import ToolContext

from csr_agent.data.audit import write_audit_log
from csr_agent.data.eligibility import get_eligibility
from csr_agent.pipeline.date_of_service import (
    not_eligible_reason_and_message,
    parse_date_of_service,
)
from csr_agent.tools.models import NotEligibleOnDateResult, TermedMemberResult
from shared.messages import termed_member_message


def check_eligibility(
    member_id: str, tool_context: ToolContext, date_of_service: str | None = None
) -> dict:
    """Look up a Meridian member's eligibility status by member ID.

    Always call this before discussing any cost for a member -- a member who
    is not eligible must never receive a cost estimate. Returns the member's
    name, plan, coverage tier, coverage dates, and status (ACTIVE, TERMED,
    ACTIVE_FUTURE_TERM, or NOT_COVERED_ON_DOS).

    If status is TERMED, or if the response_type is TERMED_BLOCK or
    NOT_ELIGIBLE_ON_DOS, relay the message verbatim and do not proceed to a
    cost estimate under any phrasing of the request.

    Args:
      member_id: The member ID as given by the CSR, e.g. "M1002".
      date_of_service: Optional ISO date (YYYY-MM-DD) when the procedure is
        scheduled, if and only if the CSR stated one. Eligibility is then
        evaluated as of that date instead of today. Pass it through exactly
        as given -- never infer a date, never substitute today, and never
        turn a vague phrase like "next month" into a specific date yourself;
        ask the CSR for the actual date. Omit it when none was stated.

    Returns:
      If not eligible: a dict discriminated by response_type "TERMED_BLOCK"
      or "NOT_ELIGIBLE_ON_DOS", with an audit_id and a ready-to-relay
      message -- relay `message` verbatim and stop, per instruction step 1.
      Otherwise: a dict with keys member_id, found, name, plan_id, tier,
      status, coverage_start, coverage_end, warning, evaluated_as_of.
    """
    parsed_dos = None
    if date_of_service is not None:
        parsed_dos = parse_date_of_service(date_of_service)
        if parsed_dos is None:
            return {
                "error": "DATE_OF_SERVICE_UNPARSEABLE",
                "message": (
                    f"'{date_of_service}' is not a valid date. Ask the CSR for the "
                    "date of service as a calendar date and pass it as YYYY-MM-DD, "
                    "or omit it if they did not state one."
                ),
            }

    elig = get_eligibility(member_id, date_of_service=parsed_dos)

    if elig.status not in ("TERMED", "NOT_COVERED_ON_DOS"):
        return elig.model_dump(mode="json")

    # Reaching here means status was populated, and get_eligibility only
    # populates status on a found member row (both not-found paths return a
    # bare found=False result whose status is None) -- so name is set too.
    # That invariant lives in EligibilityResult's optional typing rather than
    # anywhere mypy can follow from the status check.
    assert elig.name is not None

    result: TermedMemberResult | NotEligibleOnDateResult
    if elig.status == "TERMED":
        result = TermedMemberResult(
            eligibility=elig,
            message=termed_member_message(
                elig.name, elig.coverage_end.isoformat() if elig.coverage_end else "unknown date"
            ),
            audit_id=uuid4(),
        )
    else:
        # NOT_COVERED_ON_DOS is only reachable when a date was supplied and
        # parsed, so parsed_dos is set here.
        assert parsed_dos is not None
        reason, message = not_eligible_reason_and_message(
            elig.name, elig.coverage_start, elig.coverage_end, parsed_dos
        )
        result = NotEligibleOnDateResult(
            eligibility=elig,
            date_of_service=parsed_dos,
            reason=reason,
            message=message,
            audit_id=uuid4(),
        )

    request_snapshot: dict = {"member_id": member_id}
    if parsed_dos is not None:
        request_snapshot["date_of_service"] = parsed_dos.isoformat()

    invocation_context = tool_context.get_invocation_context()
    trace_id = getattr(invocation_context, "trace_id", None) or tool_context.invocation_id
    write_audit_log(
        audit_id=result.audit_id,
        csr_user_id=tool_context.user_id,
        session_id=tool_context.session.id,
        invocation_id=tool_context.invocation_id,
        trace_id=trace_id,
        member_id=member_id,
        cpt_code=None,
        response_type=result.response_type,
        request_snapshot=request_snapshot,
        result_snapshot=result.model_dump(mode="json"),
        source_data_snapshot={"eligibility": elig.model_dump(mode="json")},
    )
    return result.model_dump(mode="json")
