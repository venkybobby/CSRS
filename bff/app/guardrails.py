"""BFF-side enforcement of the numeric-provenance guardrail (plan §2.2
layer 4). The actual Decimal-normalization logic lives in
shared/guardrails/numeric_provenance.py -- this module is just the policy
of what to do with the result at the BFF boundary: replace the response
entirely on violation, and make that violation loud (paging-worthy log
event), never silently degrade.
"""
from __future__ import annotations

import logging

from shared.guardrails.numeric_provenance import GuardrailResult, verify_numeric_provenance

logger = logging.getLogger("csrsupport.guardrails")

SUPERVISOR_TRANSFER_MESSAGE = (
    "Unable to produce a verified cost estimate for this request. "
    "Please transfer to a Member Services supervisor."
)


def enforce_numeric_provenance(
    agent_message: str, tool_payloads: list[dict], *, audit_id: str | None = None
) -> tuple[str, GuardrailResult]:
    """Returns (message_to_show_the_csr, guardrail_result).

    On violation, the CSR-facing message is replaced entirely -- the
    original (potentially fabricated) text is never shown to the CSR, only
    logged internally at ERROR level for incident review. This is the
    prompt-injection backstop: even a fully manipulated model cannot get a
    fabricated dollar figure in front of a CSR, because this check runs
    after the model, not as part of it.
    """
    result = verify_numeric_provenance(agent_message, tool_payloads)
    if result.passed:
        return agent_message, result

    logger.error(
        "GUARDRAIL_VIOLATION: numeric provenance check failed audit_id=%s "
        "violating_tokens=%s original_message=%r",
        audit_id,
        result.violating_tokens,
        agent_message,
    )
    return SUPERVISOR_TRANSFER_MESSAGE, result
