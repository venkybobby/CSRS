"""ADK tool wrapper around data/eligibility.py::get_eligibility(). Thin --
all it does is call the deterministic data-layer function and return a
JSON-serializable dict; ADK's FunctionTool builds the model-visible function
declaration from this function's signature and docstring.
"""
from __future__ import annotations

from google.adk.tools.tool_context import ToolContext

from csr_agent.data.eligibility import get_eligibility


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
      A dict with keys: member_id, found, name, plan_id, tier, status,
      coverage_start, coverage_end, warning.
    """
    result = get_eligibility(member_id)
    return result.model_dump(mode="json")
