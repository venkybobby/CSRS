"""ADK tool wrapper around data/rate_matcher.py::match_procedure().

Also the write side of the plan §4 prompt-injection defense for
estimate_member_cost: when this tool MATCHES a cpt_code, it records that
cpt_code in session state (LAST_MATCHED_STATE_KEY). estimate_tool.py checks
that state -- not the LLM's restated text -- before it will call the
pipeline with a given cpt_code. This closes the "model was talked into
inventing/reusing a CPT code" gap even if the model itself is manipulated.
"""
from __future__ import annotations

from google.adk.tools.tool_context import ToolContext

from csr_agent.data.rate_matcher import match_procedure

LAST_MATCHED_STATE_KEY = "csr_agent:last_matched_cpt_code"


def resolve_procedure(procedure_query: str, tool_context: ToolContext) -> dict:
    """Resolve a plain-English procedure description to a CPT code and
    negotiated rate.

    Never invent, guess, or substitute a CPT code yourself -- only use a
    cpt_code that this tool returns with status "MATCHED". If status is
    "NEEDS_CLARIFICATION", ask the CSR the exact clarifying_question
    returned and wait for their answer before calling this tool again or
    calling estimate_member_cost. If status is "NOT_ON_FILE", tell the CSR
    there is no rate on file for this procedure and to transfer to a
    supervisor -- do not estimate a cost using a similar or nearby
    procedure's rate.

    Args:
      procedure_query: The procedure as the CSR described it, e.g.
        "MRI on his knee" or "knee surgery".

    Returns:
      A dict with keys: query, status (MATCHED|NEEDS_CLARIFICATION|
      NOT_ON_FILE), cpt_code, common_name, negotiated_rate, candidates,
      clarifying_question.
    """
    result = match_procedure(procedure_query)
    if result.status == "MATCHED":
        tool_context.state[LAST_MATCHED_STATE_KEY] = result.cpt_code
    return result.model_dump(mode="json")
