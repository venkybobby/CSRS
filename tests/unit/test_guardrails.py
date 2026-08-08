"""Unit tests for the numeric-provenance guardrail (plan §2.2 layer 4 /
§7 hardening tests). The two cases the Google architecture review flagged
explicitly: formatting divergence must NOT false-positive, and genuine
fabrication must still be caught.
"""
from decimal import Decimal

from shared.guardrails.numeric_provenance import (
    normalize_currency,
    verify_numeric_provenance,
)

PAYLOAD = [{"breakdown": {"member_cost": "1250.00", "coinsurance_amount": "170.00"}}]


def test_formatting_variants_all_normalize_equal():
    assert normalize_currency("$1,250.00") == Decimal("1250.00")
    assert normalize_currency("$1250") == Decimal("1250.00")
    assert normalize_currency("$1,250") == Decimal("1250.00")
    assert normalize_currency("$ 1250.00") == Decimal("1250.00")


def test_formatting_divergence_does_not_false_positive():
    """Tool payload has '1250.00'; the model is free to render $1,250.00,
    $1250, or $1,250 -- none of these should trip the guardrail."""
    for rendering in ("$1,250.00", "$1250", "$1,250"):
        text = f"Member owes {rendering} after coinsurance."
        result = verify_numeric_provenance(text, PAYLOAD)
        assert result.passed, f"false positive for rendering {rendering!r}: {result.violating_tokens}"


def test_genuinely_fabricated_figure_is_caught():
    """$99.99 appears nowhere in the payload -- must be flagged even though
    it's a plausible-looking dollar amount."""
    text = "Member owes $99.99 after coinsurance."
    result = verify_numeric_provenance(text, PAYLOAD)
    assert result.passed is False
    assert "$99.99" in result.violating_tokens


def test_mixed_legit_and_fabricated_flags_only_the_fabricated_one():
    text = "Deductible applied $170.00, but member owes $99.99 total."
    # $170.00 isn't in PAYLOAD's exact keys either -- use a payload that has both.
    payload = [{"applied": "170.00", "member_cost": "1250.00"}]
    result = verify_numeric_provenance(text, payload)
    assert result.passed is False
    assert result.violating_tokens == ["$99.99"]


def test_numbers_without_dollar_sign_are_not_checked():
    """A CPT code or plain number in the message is not a currency claim --
    only $-prefixed tokens are extracted and checked at all."""
    text = "CPT 73721 was matched with score 92."
    result = verify_numeric_provenance(text, PAYLOAD)
    assert result.checked_tokens == []
    assert result.passed


def test_no_dollar_tokens_in_text_trivially_passes():
    result = verify_numeric_provenance("Member is not eligible. Do not quote a cost.", [])
    assert result.passed
    assert result.checked_tokens == []


def test_multiple_tool_payloads_are_all_considered():
    payloads = [{"a": "10.00"}, {"b": {"c": "20.00"}}]
    result = verify_numeric_provenance("That's $10.00 plus $20.00.", payloads)
    assert result.passed
