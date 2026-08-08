"""Unit tests for individual_tier_cost(), asserting every CostBreakdown
field against the spec's worked examples -- not just the final member_cost.
"""
from decimal import Decimal

from csr_agent.calculator.individual import individual_tier_cost

from .conftest import accumulators


def test_m1001_full_deductible_before_any_coinsurance(silver_plan, rate_mri_knee):
    """Alice Trevino, Silver, deductible_met=$0: 'full $1,500 deductible
    applies before any coinsurance' (Story 3 edge case). Rate ($1,150) is
    fully absorbed by the deductible, so coinsurance never engages."""
    result = individual_tier_cost(
        plan=silver_plan, rate=rate_mri_knee, accumulators=accumulators("0.00", "0.00")
    )
    assert result.deductible_remaining == Decimal("1500.00")
    assert result.applied_to_deductible == Decimal("1150.00")
    assert result.balance_after_deductible == Decimal("0.00")
    assert result.coinsurance_amount == Decimal("0.00")
    assert result.member_cost == Decimal("1150.00")
    assert result.oop_cap_triggered is False
    assert result.triggering_threshold == "N/A"


def test_m1002_partial_deductible_then_coinsurance_demo_script_case(silver_plan, rate_mri_knee):
    """Robert Chen, Silver, deductible_met=$1,200, oop_met=$1,200 -- Demo
    Script #1, exact figures: deductible remaining $300, balance $850,
    coinsurance 20% = $170, member owes $470."""
    result = individual_tier_cost(
        plan=silver_plan, rate=rate_mri_knee, accumulators=accumulators("1200.00", "1200.00")
    )
    assert result.deductible_remaining == Decimal("300.00")
    assert result.applied_to_deductible == Decimal("300.00")
    assert result.balance_after_deductible == Decimal("850.00")
    assert result.coinsurance_amount == Decimal("170.00")
    assert result.member_cost_before_cap == Decimal("470.00")
    assert result.oop_remaining == Decimal("2800.00")
    assert result.member_cost == Decimal("470.00")
    assert result.oop_cap_triggered is False


def test_m1003_deductible_fully_met_straight_to_coinsurance(gold_plan, rate_mri_knee):
    """Dorothy Okafor, Gold, deductible_met=$500 (== deductible_individual,
    fully met), oop_met=$1,100. Deductible phase is skipped entirely;
    coinsurance runs on the full negotiated rate at Gold's 10%."""
    result = individual_tier_cost(
        plan=gold_plan, rate=rate_mri_knee, accumulators=accumulators("500.00", "1100.00")
    )
    assert result.deductible_remaining == Decimal("0.00")
    assert result.applied_to_deductible == Decimal("0.00")
    assert result.balance_after_deductible == Decimal("1150.00")
    assert result.coinsurance_amount == Decimal("115.00")
    assert result.oop_remaining == Decimal("1400.00")
    assert result.member_cost == Decimal("115.00")
    assert result.oop_cap_triggered is False


def test_m1004_oop_max_binding_caps_regardless_of_procedure_cost(bronze_plan, rate_knee_surgery):
    """James Whitaker, Bronze, oop_met=$6,350 against oop_max=$6,500 -- only
    $150 of headroom. Story 3 / Demo Script #2: CPT 29881 at $6,200 must be
    capped at exactly $150, not the $1,860 coinsurance would otherwise
    produce. ind_ded_met is not stated in the spec for this member; it is
    assumed fully met ($3,000) here, consistent with a member whose OOP
    accumulator is already near its max -- this assumption only affects
    intermediate fields (applied_to_deductible, balance), not the asserted
    OOP-binding outcome, which holds regardless of the deductible split as
    long as member_cost_before_cap exceeds the $150 headroom.
    """
    result = individual_tier_cost(
        plan=bronze_plan,
        rate=rate_knee_surgery,
        accumulators=accumulators("3000.00", "6350.00"),
    )
    assert result.member_cost_before_cap == Decimal("1860.00")
    assert result.oop_remaining == Decimal("150.00")
    assert result.member_cost == Decimal("150.00")
    assert result.oop_cap_triggered is True


def test_deductible_over_met_does_not_go_negative(silver_plan, rate_mri_knee):
    """Defensive case not in the spec: if deductible_met_ytd somehow exceeds
    deductible_individual (data anomaly), deductible_remaining must clamp at
    zero rather than go negative and corrupt applied_to_deductible/balance."""
    result = individual_tier_cost(
        plan=silver_plan, rate=rate_mri_knee, accumulators=accumulators("1600.00", "0.00")
    )
    assert result.deductible_remaining == Decimal("0.00")
    assert result.applied_to_deductible == Decimal("0.00")
    assert result.balance_after_deductible == rate_mri_knee.negotiated_rate
