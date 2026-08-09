"""End-to-end integration tests for estimate_member_cost() against a real
(throwaway) Postgres database seeded from db/seed/*.json. Covers all 7
CostEstimateResult branches (MEMBER_NOT_FOUND, TERMED_BLOCK, EXCLUSION,
RATE_NOT_FOUND x2, PREVENTIVE_ZERO_COST, STANDARD_COST) and asserts the
audit log is written correctly for each.

Requires TEST_DATABASE_URL -- see conftest.py. Skipped entirely if unset.
"""
from datetime import date
from decimal import Decimal
from unittest.mock import patch
from uuid import UUID

import pytest
from csr_agent.pipeline.estimate import estimate_member_cost
from sqlalchemy import create_engine, text

AUDIT_CTX = {
    "csr_user_id": "csr.jordan@meridianhealthplans.com",
    "session_id": "test-session-1",
    "invocation_id": "test-invocation-1",
    "trace_id": "test-trace-1",
}


def _audit_row(db_url: str, audit_id: UUID) -> dict:
    engine = create_engine(db_url)
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT * FROM quote_audit_log WHERE audit_id = :id"), {"id": str(audit_id)}
        ).mappings().first()
    engine.dispose()
    assert row is not None, f"no audit_log row for audit_id={audit_id}"
    return dict(row)


def test_member_not_found(seeded_db):
    result = estimate_member_cost("M9999", "73721", **AUDIT_CTX)
    assert result.response_type == "MEMBER_NOT_FOUND"
    row = _audit_row(seeded_db, result.audit_id)
    assert row["response_type"] == "MEMBER_NOT_FOUND"


def test_termed_member_blocks_before_calculator(seeded_db):
    """Story 1 / Demo Script #4, exact: Priya Raman (M1005), termed
    2026-05-31 -> refusal, no dollar figure, calculator never runs."""
    with patch("csr_agent.pipeline.estimate.individual_tier_cost") as calc, \
         patch("csr_agent.pipeline.estimate.family_tier_cost") as calc_fam:
        result = estimate_member_cost("M1005", "73721", **AUDIT_CTX)

    assert result.response_type == "TERMED_BLOCK"
    assert "2026-05-31" in result.message
    assert "Priya Raman" in result.message
    calc.assert_not_called()
    calc_fam.assert_not_called()
    row = _audit_row(seeded_db, result.audit_id)
    assert row["response_type"] == "TERMED_BLOCK"


def test_exclusion_before_rate_lookup(seeded_db):
    """Story 6: Bronze (M1004) excludes S8092 -- must return EXCLUSION, not
    RATE_NOT_FOUND, even though S8092 also has no negotiated_rate."""
    with patch("csr_agent.pipeline.estimate.individual_tier_cost") as calc:
        result = estimate_member_cost("M1004", "S8092", **AUDIT_CTX)

    assert result.response_type == "EXCLUSION"
    assert "not a covered benefit" in result.message
    calc.assert_not_called()
    row = _audit_row(seeded_db, result.audit_id)
    assert row["response_type"] == "EXCLUSION"


def test_rate_not_found_for_non_excluded_plan_on_unpriced_code(seeded_db):
    """Story 6: Silver (M1002) does NOT exclude S8092, so it falls through
    to a genuine rate-not-found -- a different fact, different CSR script,
    from Bronze's exclusion above."""
    result = estimate_member_cost("M1002", "S8092", **AUDIT_CTX)
    assert result.response_type == "RATE_NOT_FOUND"
    row = _audit_row(seeded_db, result.audit_id)
    assert row["response_type"] == "RATE_NOT_FOUND"


def test_rate_not_found_for_code_absent_entirely(seeded_db):
    """Story 8: a CPT code not on the sheet at all."""
    result = estimate_member_cost("M1001", "00000", **AUDIT_CTX)
    assert result.response_type == "RATE_NOT_FOUND"
    assert "00000" in result.message


def test_preventive_zero_cost_never_touches_accumulators(seeded_db):
    """Story 7: preventive colonoscopy (45380) short-circuits to $0 without
    reading member_accumulators at all."""
    with patch("csr_agent.pipeline.estimate.get_member_accumulators") as get_accum:
        result = estimate_member_cost("M1001", "45380", **AUDIT_CTX)

    assert result.response_type == "PREVENTIVE_ZERO_COST"
    assert result.member_cost == Decimal("0.00")
    get_accum.assert_not_called()
    row = _audit_row(seeded_db, result.audit_id)
    assert row["response_type"] == "PREVENTIVE_ZERO_COST"


def test_standard_cost_m1002_matches_demo_script(seeded_db):
    result = estimate_member_cost("M1002", "73721", **AUDIT_CTX)
    assert result.response_type == "STANDARD_COST"
    assert result.breakdown.member_cost == Decimal("470.00")
    row = _audit_row(seeded_db, result.audit_id)
    assert row["response_type"] == "STANDARD_COST"
    assert row["source_data_snapshot"]["rate"]["negotiated_rate"] == "1150.00"


def test_family_members_diverge_in_explanation_same_dollar_total(seeded_db):
    """The real regression this system must survive: M1006 and M1007, same
    plan, same procedure, correctly produce the SAME member_cost ($1,860,
    per Demo Script #3) but DIFFERENT oop_remaining/triggering_threshold --
    proving the accumulator lookup is per-member, not shared/mis-joined."""
    r6 = estimate_member_cost("M1006", "29881", **AUDIT_CTX)
    r7 = estimate_member_cost("M1007", "29881", **AUDIT_CTX)

    assert r6.breakdown.member_cost == r7.breakdown.member_cost == Decimal("1860.00")
    assert r6.breakdown.oop_remaining != r7.breakdown.oop_remaining
    assert r6.breakdown.triggering_threshold == "INDIVIDUAL"
    assert r7.breakdown.triggering_threshold == "FAMILY"


def test_prior_auth_flag_set_when_required(seeded_db):
    """Story 4: MRI Brain (70551) requires prior auth on Silver."""
    result = estimate_member_cost("M1001", "70551", **AUDIT_CTX)
    assert result.response_type == "STANDARD_COST"
    assert result.breakdown.prior_auth_required is True
    assert "Prior authorization required" in result.message


def test_prior_auth_flag_not_set_when_not_required(seeded_db):
    """Story 4: MRI Knee (73721) does NOT require prior auth on Silver."""
    result = estimate_member_cost("M1001", "73721", **AUDIT_CTX)
    assert result.breakdown.prior_auth_required is False
    assert "Prior authorization required" not in result.message


def test_future_term_warning_shown_alongside_cost_estimate(seeded_db):
    """Story 1: M1010, active but terming 2026-08-31 -- cost is still shown,
    plus a visible coverage-end warning."""
    result = estimate_member_cost(
        "M1010", "73721", today=date(2026, 8, 8), **AUDIT_CTX
    )
    assert result.response_type == "STANDARD_COST"
    assert result.eligibility.status == "ACTIVE_FUTURE_TERM"
    assert "2026-08-31" in result.message


@pytest.mark.parametrize(
    "member_id,cpt_code,expected_type",
    [
        ("M9999", "73721", "MEMBER_NOT_FOUND"),
        ("M1005", "73721", "TERMED_BLOCK"),
        ("M1004", "S8092", "EXCLUSION"),
        ("M1002", "S8092", "RATE_NOT_FOUND"),
        ("M1001", "45380", "PREVENTIVE_ZERO_COST"),
        ("M1002", "73721", "STANDARD_COST"),
    ],
)
def test_audit_log_written_for_every_response_type(seeded_db, member_id, cpt_code, expected_type):
    result = estimate_member_cost(member_id, cpt_code, **AUDIT_CTX)
    assert result.response_type == expected_type
    row = _audit_row(seeded_db, result.audit_id)
    assert row["member_id"] == member_id
    assert row["csr_user_id"] == AUDIT_CTX["csr_user_id"]
    assert row["response_type"] == expected_type
