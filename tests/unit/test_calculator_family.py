"""Unit tests for family_tier_cost() -- the embedded deductible/OOP model
confirmed with Plan Ops (Marcus). These reproduce Story 5's exact worked
examples (M1006, M1007, Bronze plan) plus the Demo Script #3 acceptance case,
and separately construct a scenario where the OOP cap genuinely binds
differently per member (the spec's own knee-surgery numbers happen to
produce equal totals for M1006/M1007 -- see the note on
test_m1006_and_m1007_knee_surgery_demo_script_case below).
"""
from decimal import Decimal

from csr_agent.calculator.family import family_tier_cost
from csr_agent.calculator.types import MemberAccumulators, PlanTerms, RateInfo

from .conftest import accumulators

# M1006 (Miguel Santos), Story 5 worked example: ind_ded_met=$3,000 (fully met
# -- individual trigger), ind_oop_met=$3,400, fam_oop_met=$4,500.
# fam_ded_met is not stated in the spec for M1006 -- it doesn't affect the
# outcome, since the individual clause alone already makes in_coinsurance
# True. Set to $0 (clearly not met) so the fixture is unambiguous about which
# clause is doing the triggering.
M1006 = MemberAccumulators(
    ind_ded_met=Decimal("3000.00"),
    ind_oop_met=Decimal("3400.00"),
    fam_ded_met=Decimal("0.00"),
    fam_oop_met=Decimal("4500.00"),
)

# M1007 (Hannah Santos, same family/plan as M1006), Story 5 worked example:
# ind_ded_met=$400 (NOT met), fam_ded_met=$6,000 (fully met -- family
# trigger), ind_oop_met=$400, fam_oop_met=$6,200.
M1007 = MemberAccumulators(
    ind_ded_met=Decimal("400.00"),
    ind_oop_met=Decimal("400.00"),
    fam_ded_met=Decimal("6000.00"),
    fam_oop_met=Decimal("6200.00"),
)


def test_m1006_individual_deductible_met_triggers_individual(bronze_plan, rate_knee_surgery):
    result = family_tier_cost(plan=bronze_plan, rate=rate_knee_surgery, accumulators=M1006)
    assert result.triggering_threshold == "INDIVIDUAL"
    assert result.applied_to_deductible == Decimal("0.00")
    assert result.balance_after_deductible == Decimal("6200.00")
    assert result.coinsurance_amount == Decimal("1860.00")
    assert result.oop_remaining == Decimal("3100.00")
    assert result.member_cost == Decimal("1860.00")
    assert result.oop_cap_triggered is False


def test_m1007_family_deductible_met_skips_individual_phase(bronze_plan, rate_knee_surgery):
    result = family_tier_cost(plan=bronze_plan, rate=rate_knee_surgery, accumulators=M1007)
    assert result.triggering_threshold == "FAMILY"
    assert result.applied_to_deductible == Decimal("0.00")
    assert result.balance_after_deductible == Decimal("6200.00")
    assert result.coinsurance_amount == Decimal("1860.00")
    assert result.oop_remaining == Decimal("6100.00")
    assert result.member_cost == Decimal("1860.00")
    assert result.oop_cap_triggered is False


def test_m1006_and_m1007_knee_surgery_demo_script_case(bronze_plan, rate_knee_surgery):
    """Demo Script #3 (spec, exact): both M1006 and M1007 owe $1,860 for the
    same knee-surgery query -- the source doc is explicit that the totals
    match here ('Outputs differ in explanation (different triggers,
    different OOP positions)'), NOT that member_cost itself must differ.
    The $1,860 coinsurance simply doesn't exceed either member's OOP
    headroom ($3,100 vs $6,100), so the cap never binds for either of them
    at this rate. What must differ -- and does -- is oop_remaining and
    triggering_threshold, proving the per-member accumulator lookup is
    genuinely using each member's own row, not a shared/mis-joined one.
    See test_family_members_diverge_when_oop_cap_binds_differently for the
    case where the dollar totals do split apart.
    """
    r6 = family_tier_cost(plan=bronze_plan, rate=rate_knee_surgery, accumulators=M1006)
    r7 = family_tier_cost(plan=bronze_plan, rate=rate_knee_surgery, accumulators=M1007)

    assert r6.member_cost == r7.member_cost == Decimal("1860.00")
    assert r6.oop_remaining != r7.oop_remaining, "OOP positions must differ even when totals match"
    assert r6.triggering_threshold != r7.triggering_threshold


def test_family_members_diverge_when_oop_cap_binds_differently(bronze_plan):
    """Constructed scenario (not from the 15-procedure rate sheet -- a
    hypothetical $15,000 major-procedure rate) chosen specifically to push
    the pre-cap coinsurance amount ($4,500) above M1006's OOP headroom
    ($3,100) while staying under M1007's ($6,100). This is what the spec's
    'if it returns identical numbers, the per-member accumulator lookup is
    wrong' warning is actually guarding against: a join-key bug (e.g.
    keyed by plan_id/family_id instead of member_id) would make both
    members' accumulators collapse to the same row and therefore always
    produce the same OOP cap and the same member_cost, including here --
    where the correct calculation must NOT match.
    """
    big_rate = RateInfo(cpt_code="99999-TEST-ONLY", negotiated_rate=Decimal("15000.00"))
    r6 = family_tier_cost(plan=bronze_plan, rate=big_rate, accumulators=M1006)
    r7 = family_tier_cost(plan=bronze_plan, rate=big_rate, accumulators=M1007)

    assert r6.member_cost == Decimal("3100.00")
    assert r6.oop_cap_triggered is True
    assert r7.member_cost == Decimal("4500.00")
    assert r7.oop_cap_triggered is False
    assert r6.member_cost != r7.member_cost, (
        "M1006/M1007 identical at a rate where the cap should bind "
        "differently -- check member_accumulators join key (likely joined "
        "on plan_id/family_id instead of member_id)"
    )


def test_family_deductible_can_truncate_individual_remaining(bronze_plan, rate_knee_surgery):
    """Rule 2: 'Family aggregate can truncate an individual's remaining
    deductible.' Neither threshold is fully met yet, but the family
    remaining ($200) is smaller than the individual remaining ($3,000), so
    the smaller (family-truncated) figure binds deductible_remaining."""
    accum = accumulators("0.00", "0.00", fam_ded_met="5800.00", fam_oop_met="0.00")
    result = family_tier_cost(plan=bronze_plan, rate=rate_knee_surgery, accumulators=accum)

    assert result.triggering_threshold == "N/A"  # not yet in coinsurance phase
    assert result.deductible_remaining == Decimal("200.00")  # min(3000, 200), family binds
    assert result.applied_to_deductible == Decimal("200.00")
    assert result.balance_after_deductible == Decimal("6000.00")
    assert result.coinsurance_amount == Decimal("1800.00")
    assert result.member_cost == Decimal("2000.00")


def test_both_thresholds_met_simultaneously_ties_to_individual(bronze_plan, rate_knee_surgery):
    """Not spec-stated (the worked examples never have both met at once) --
    documents the deterministic tie-break: when both individual and family
    deductibles are independently met in the same snapshot, INDIVIDUAL is
    reported, matching the order the `or` condition is evaluated."""
    accum = MemberAccumulators(
        ind_ded_met=Decimal("3000.00"),
        ind_oop_met=Decimal("0.00"),
        fam_ded_met=Decimal("6000.00"),
        fam_oop_met=Decimal("0.00"),
    )
    result = family_tier_cost(plan=bronze_plan, rate=rate_knee_surgery, accumulators=accum)
    assert result.triggering_threshold == "INDIVIDUAL"
