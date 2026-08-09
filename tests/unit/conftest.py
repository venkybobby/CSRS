"""Shared plan/rate fixtures for calculator unit tests.

Every constant here is either stated explicitly in
meridian_csr_estimator_MVP1_stories.md, or derived arithmetically from
numbers stated there (derivation shown in the comment). Where the source doc
never states a value (e.g. Silver/Gold family-tier deductible/OOP), the field
is a documented placeholder that individual-tier tests never read.
"""
from decimal import Decimal

import pytest
from csr_agent.calculator.types import MemberAccumulators, PlanTerms, RateInfo

UNUSED_FAMILY_PLACEHOLDER = Decimal("999999.00")


@pytest.fixture
def silver_plan() -> PlanTerms:
    # Story 3 / Demo Script #1: M1002 deductible_met=$1,200, "$300 deductible
    # remaining" => deductible_individual = 1200 + 300 = $1,500.
    # Demo Script #1: coinsurance 20%. M1002 oop_met=$1,200, "OOP headroom =
    # $2,800" => oop_max_individual = 1200 + 2800 = $4,000.
    return PlanTerms(
        deductible_individual=Decimal("1500.00"),
        deductible_family=UNUSED_FAMILY_PLACEHOLDER,
        coinsurance_pct=Decimal("0.20"),
        oop_max_individual=Decimal("4000.00"),
        oop_max_family=UNUSED_FAMILY_PLACEHOLDER,
    )


@pytest.fixture
def gold_plan() -> PlanTerms:
    # Story 3: M1003 "deductible fully met ($500/$500)" => deductible_individual
    # = $500. "coinsurance = 10%". oop_met=$1,100, "OOP headroom = $1,400"
    # => oop_max_individual = 1100 + 1400 = $2,500.
    return PlanTerms(
        deductible_individual=Decimal("500.00"),
        deductible_family=UNUSED_FAMILY_PLACEHOLDER,
        coinsurance_pct=Decimal("0.10"),
        oop_max_individual=Decimal("2500.00"),
        oop_max_family=UNUSED_FAMILY_PLACEHOLDER,
    )


@pytest.fixture
def bronze_plan() -> PlanTerms:
    # Story 5 worked examples, stated explicitly: "Bronze plan: ind_ded=$3,000
    # / fam_ded=$6,000 / coinsurance=30% / ind_oop_max=$6,500 / fam_oop_max=$13,000"
    return PlanTerms(
        deductible_individual=Decimal("3000.00"),
        deductible_family=Decimal("6000.00"),
        coinsurance_pct=Decimal("0.30"),
        oop_max_individual=Decimal("6500.00"),
        oop_max_family=Decimal("13000.00"),
    )


@pytest.fixture
def rate_mri_knee() -> RateInfo:
    # CPT 73721, Demo Script #1: deductible remaining $300 fully absorbed
    # ("applied to deductible"), balance $850 => rate = 300 + 850 = $1,150.
    return RateInfo(cpt_code="73721", negotiated_rate=Decimal("1150.00"))


@pytest.fixture
def rate_knee_surgery() -> RateInfo:
    # CPT 29881, Story 3 / Demo Script #2 & #3: "rate $6,200" stated explicitly.
    return RateInfo(cpt_code="29881", negotiated_rate=Decimal("6200.00"))


def accumulators(
    ind_ded_met: str, ind_oop_met: str, fam_ded_met: str = "0.00", fam_oop_met: str = "0.00"
) -> MemberAccumulators:
    return MemberAccumulators(
        ind_ded_met=Decimal(ind_ded_met),
        ind_oop_met=Decimal(ind_oop_met),
        fam_ded_met=Decimal(fam_ded_met),
        fam_oop_met=Decimal(fam_oop_met),
    )
