"""ADK tool wrapper around pipeline/estimate.py::estimate_member_cost().

Enforces the plan §4 prompt-injection defense (read side -- see
procedure_tool.py for the write side): this tool refuses to price a
cpt_code unless resolve_procedure just matched that exact code in the same
session, per server-side state -- never the LLM's own restated text. Even a
fully manipulated model cannot get an invented CPT code priced.
"""
from __future__ import annotations

from google.adk.tools.tool_context import ToolContext

from csr_agent.pipeline.date_of_service import parse_date_of_service
from csr_agent.pipeline.estimate import estimate_member_cost as _estimate_member_cost
from csr_agent.tools.procedure_tool import LAST_MATCHED_STATE_KEY


def estimate_member_cost(
    member_id: str,
    cpt_code: str,
    tool_context: ToolContext,
    date_of_service: str | None = None,
) -> dict:
    """Calculate a member's estimated out-of-pocket cost for a procedure,
    with a full deductible/coinsurance/OOP-max breakdown.

    Only call this after check_eligibility has confirmed the member is not
    TERMED, and only with a cpt_code that resolve_procedure just returned
    with status "MATCHED" -- never a code you infer, remember, or guess
    yourself. Relay every dollar figure in the response verbatim; never
    restate, round, or recompute a number that isn't literally present in
    this tool's output.

    Args:
      member_id: The member ID, e.g. "M1002".
      cpt_code: A CPT code that resolve_procedure just matched in this
        conversation.
      date_of_service: Optional ISO date (YYYY-MM-DD) when the procedure is
        scheduled, if and only if the CSR stated one. Pass it through
        exactly as given -- never infer a date, never substitute today, and
        never convert a vague phrase like "next month" into a specific date
        yourself; ask the CSR for the actual date instead. Omit this
        argument entirely when no date was stated.

    Returns:
      A dict discriminated by response_type: MEMBER_NOT_FOUND,
      DATE_OF_SERVICE_INVALID, TERMED_BLOCK, NOT_ELIGIBLE_ON_DOS,
      PLAN_YEAR_BOUNDARY, EXCLUSION, RATE_NOT_FOUND, PREVENTIVE_ZERO_COST,
      or STANDARD_COST (which includes the full breakdown).
    """
    # Plan §4: never trust an LLM-restated cpt_code -- it must match what
    # resolve_procedure itself just wrote to session state. This is a tool
    # contract violation, not a domain outcome, so it deliberately does NOT
    # return a CostEstimateResult variant (that union is reserved for
    # legitimate business results the frontend renders); an error dict tells
    # the model to correct its own tool-call sequence.
    last_matched = tool_context.state.get(LAST_MATCHED_STATE_KEY)
    if cpt_code != last_matched:
        return {
            "error": "CPT_NOT_CONFIRMED",
            "message": (
                "This CPT code was not confirmed by resolve_procedure in this "
                "conversation. Call resolve_procedure first and use the exact "
                "cpt_code it returns before calling estimate_member_cost."
            ),
        }

    # A date the model garbled is a tool contract violation for the same
    # reason an unconfirmed CPT code is: silently falling back to today would
    # price the wrong period and look exactly like a normal quote. Refuse and
    # make the model re-ask rather than guess.
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

    invocation_context = tool_context.get_invocation_context()
    trace_id = getattr(invocation_context, "trace_id", None) or tool_context.invocation_id

    result = _estimate_member_cost(
        member_id,
        cpt_code,
        csr_user_id=tool_context.user_id,
        session_id=tool_context.session.id,
        invocation_id=tool_context.invocation_id,
        trace_id=trace_id,
        date_of_service=parsed_dos,
    )
    return result.model_dump(mode="json")
