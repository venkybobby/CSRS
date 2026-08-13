"""BFF-side enforcement of the numeric-provenance guardrail (plan §2.2
layer 4). The actual Decimal-normalization logic lives in
shared/guardrails/numeric_provenance.py -- this module is just the policy
of what to do with the result at the BFF boundary: replace the response
entirely on violation, and make that violation loud (paging-worthy log
event), never silently degrade.
"""
from __future__ import annotations

import logging
from datetime import date

from shared.guardrails.numeric_provenance import GuardrailResult, verify_numeric_provenance

logger = logging.getLogger("csrsupport.guardrails")

SUPERVISOR_TRANSFER_MESSAGE = (
    "Unable to produce a verified cost estimate for this request. "
    "Please transfer to a Member Services supervisor."
)

DATE_OF_SERVICE_MISMATCH_MESSAGE = (
    "This result could not be confirmed as being for the date of service you "
    "entered. Do not quote it. Re-run the query with the date, or transfer to a "
    "Member Services supervisor."
)

# response_types that carry a date_of_service and therefore can be checked
# against what the CSR asked for. The omissions are deliberate, not gaps:
# TERMED_BLOCK, MEMBER_NOT_FOUND, EXCLUSION and RATE_NOT_FOUND are answers
# that do not depend on the date at all (a termed member is termed on every
# date; an excluded code is excluded on every date), so requiring a date on
# them would fail closed on correct results.
_DATE_BEARING_RESPONSE_TYPES = {
    "DATE_OF_SERVICE_INVALID",
    "NOT_ELIGIBLE_ON_DOS",
    "PLAN_YEAR_BOUNDARY",
    "PREVENTIVE_ZERO_COST",
    "STANDARD_COST",
}


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


def enforce_date_of_service_provenance(
    requested: date | None, structured_result: dict | None, *, audit_id: str | None = None
) -> bool:
    """True when the result can be trusted to be FOR the date the CSR entered.

    The date reaches the agent's tools by being restated in the message text,
    which means a model that drops or rewrites it produces a quote for the
    wrong period that is otherwise indistinguishable from a correct one --
    the exact confidently-wrong output the date-of-service work exists to
    prevent. Same posture as the numeric-provenance check: verify after the
    model rather than trusting it, and replace the response on a mismatch
    instead of degrading quietly.

    Returns True when no date was requested (nothing to verify), and when the
    result is one whose answer does not depend on a date.
    """
    if requested is None:
        return True
    if structured_result is None:
        return True

    response_type = structured_result.get("response_type")
    if response_type not in _DATE_BEARING_RESPONSE_TYPES:
        return True

    returned = structured_result.get("date_of_service")
    if returned == requested.isoformat():
        return True

    logger.error(
        "GUARDRAIL_VIOLATION: date-of-service provenance check failed "
        "audit_id=%s response_type=%s requested=%s returned=%r",
        audit_id,
        response_type,
        requested.isoformat(),
        returned,
    )
    return False
