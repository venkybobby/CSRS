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
from csr_agent.tools.models import TermedMemberResult
from shared.messages import termed_member_message


def check_eligibility(member_id: str, tool_context: ToolContext) -> dict:
    """Look up a Meridian member's eligibility status by member ID.

    Always call this before discussing any cost for a member -- a termed
    member must never receive a cost estimate. Returns the member's name,
    plan, coverage tier, coverage dates, and status (ACTIVE, TERMED, or
    ACTIVE_FUTURE_TERM). If status is TERMED, relay that the member is not
    eligible and do not proceed to a cost estimate under any phrasing of the
    request.

    Args:
      member_id: The member ID as given by the CSR, e.g. "M1002".

    Returns:
      If TERMED: a dict discriminated by response_type "TERMED_BLOCK" with
      an audit_id and a ready-to-relay message -- relay `message` verbatim
      and stop, per instruction step 1.
      Otherwise: a dict with keys member_id, found, name, plan_id, tier,
      status, coverage_start, coverage_end, warning.
    """
    elig = get_eligibility(member_id)

    if elig.status != "TERMED":
        return elig.model_dump(mode="json")

    result = TermedMemberResult(
        eligibility=elig,
        message=termed_member_message(
            elig.name, elig.coverage_end.isoformat() if elig.coverage_end else "unknown date"
        ),
        audit_id=uuid4(),
    )

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
        request_snapshot={"member_id": member_id},
        result_snapshot=result.model_dump(mode="json"),
        source_data_snapshot={"eligibility": elig.model_dump(mode="json")},
    )
    return result.model_dump(mode="json")
