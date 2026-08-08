"""Deterministic family-tier (embedded model) cost calculation (Story 5 /
spec section "Deterministic calculation (family tier)"). Pure function, same
constraints as individual.py.

Embedded model, confirmed with Plan Ops (Marcus): a member exits the
deductible phase when EITHER their individual deductible is met OR the
family deductible is met, whichever happens first. The OOP cap mirrors this:
capped at whichever is lower, individual OOP remaining or family OOP
remaining.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Literal

from csr_agent.calculator._money import to_cents
from csr_agent.calculator.types import MemberAccumulators, PlanTerms, RateInfo
from csr_agent.tools.models import CostBreakdown

ZERO = Decimal("0.00")


def family_tier_cost(
    plan: PlanTerms, rate: RateInfo, accumulators: MemberAccumulators
) -> CostBreakdown:
    ind_deductible_met = accumulators.ind_ded_met >= plan.deductible_individual
    fam_deductible_met = accumulators.fam_ded_met >= plan.deductible_family
    in_coinsurance = ind_deductible_met or fam_deductible_met

    triggering_threshold: Literal["INDIVIDUAL", "FAMILY", "N/A"]

    if in_coinsurance:
        # A point-in-time snapshot can't observe which one crossed first if
        # both happen to be true simultaneously; report INDIVIDUAL in that
        # tie, consistent with evaluating the individual clause first in the
        # `or` -- deterministic and stable, not arbitrary per-call.
        triggering_threshold = "INDIVIDUAL" if ind_deductible_met else "FAMILY"
        deductible_remaining = ZERO
        applied_to_deductible = ZERO
        balance_after_deductible = rate.negotiated_rate
    else:
        remaining_ind_ded = plan.deductible_individual - accumulators.ind_ded_met
        remaining_fam_ded = plan.deductible_family - accumulators.fam_ded_met
        deductible_remaining = min(remaining_ind_ded, remaining_fam_ded)
        applied_to_deductible = min(rate.negotiated_rate, deductible_remaining)
        balance_after_deductible = rate.negotiated_rate - applied_to_deductible
        triggering_threshold = "N/A"

    # Step 3 -- coinsurance
    coinsurance_amount = to_cents(balance_after_deductible * plan.coinsurance_pct)
    member_cost_before_cap = applied_to_deductible + coinsurance_amount

    # Step 4 -- OOP cap, embedded: lower of individual or family remaining
    remaining_ind_oop = max(plan.oop_max_individual - accumulators.ind_oop_met, ZERO)
    remaining_fam_oop = max(plan.oop_max_family - accumulators.fam_oop_met, ZERO)
    oop_remaining = min(remaining_ind_oop, remaining_fam_oop)
    member_cost = min(member_cost_before_cap, oop_remaining)
    oop_cap_triggered = member_cost_before_cap > oop_remaining

    return CostBreakdown(
        negotiated_rate=rate.negotiated_rate,
        deductible_individual=plan.deductible_individual,
        deductible_met_ytd=accumulators.ind_ded_met,
        deductible_remaining=deductible_remaining,
        applied_to_deductible=applied_to_deductible,
        balance_after_deductible=balance_after_deductible,
        coinsurance_pct=plan.coinsurance_pct,
        coinsurance_amount=coinsurance_amount,
        member_cost_before_cap=member_cost_before_cap,
        oop_remaining=oop_remaining,
        oop_cap_triggered=oop_cap_triggered,
        triggering_threshold=triggering_threshold,
        member_cost=member_cost,
        prior_auth_required=False,  # set by pipeline/estimate.py after this call
    )
