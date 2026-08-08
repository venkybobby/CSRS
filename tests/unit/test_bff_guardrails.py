"""Unit tests for the BFF's guardrail policy layer (replace-on-violation,
never show a fabricated figure to the CSR)."""
from app.guardrails import SUPERVISOR_TRANSFER_MESSAGE, enforce_numeric_provenance

PAYLOAD = [{"breakdown": {"member_cost": "470.00"}}]


def test_legit_message_passes_through_unchanged():
    text = "Member owes $470.00 after coinsurance."
    message, result = enforce_numeric_provenance(text, PAYLOAD)
    assert message == text
    assert result.passed is True


def test_fabricated_message_is_fully_replaced_not_partially_redacted():
    """The original text must never reach the CSR, even in part -- a
    partial redaction could still leak the fabricated number."""
    text = "Member owes $9,999.00 after coinsurance."
    message, result = enforce_numeric_provenance(text, PAYLOAD)
    assert message == SUPERVISOR_TRANSFER_MESSAGE
    assert "9,999" not in message
    assert result.passed is False


def test_violation_is_logged_at_error_level(caplog):
    import logging

    with caplog.at_level(logging.ERROR, logger="csrsupport.guardrails"):
        enforce_numeric_provenance("Owes $9,999.00.", PAYLOAD, audit_id="abc-123")
    assert any("GUARDRAIL_VIOLATION" in r.message for r in caplog.records)
    assert any("abc-123" in r.message for r in caplog.records)
