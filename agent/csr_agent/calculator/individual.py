"""Deterministic individual-tier cost calculation (Story 3 / spec section
"Deterministic calculation (individual tier)"). Pure function: no I/O, no
LLM, no imports outside the standard library, calculator/types.py, and
tools/models.py. Every value in CostBreakdown traces directly to this
formula -- nothing here is estimated or interpolated.
"""
from __future__ import annotations

from decimal import Decimal

from csr_agent.calculator._money import to_cents
from csr_agent.calculator.types import MemberAccumulators, PlanTerms, RateInfo
from csr_agent.tools.models import CostBreakdown

ZERO = Decimal("0.00")


def individual_tier_cost(
    plan: PlanTerms, rate: RateInfo, accumulators: MemberAccumulators
) -> CostBreakdown:
    # Step 1 -- deductible. Clamp at zero: if deductible_met_ytd already meets
    # or exceeds deductible_individual (fully met, or a data anomaly where
    # it's over-met), no further amount is applied -- the literal spec formula
    # (deductible_individual - deductible_met_ytd) would otherwise go negative
    # and corrupt every downstream figure.
    deductible_remaining = max(plan.deductible_individual - accumulators.ind_ded_met, ZERO)
    applied_to_deductible = min(rate.negotiated_rate, deductible_remaining)
    balance_after_deductible = rate.negotiated_rate - applied_to_deductible

    # Step 2 -- coinsurance
    coinsurance_amount = to_cents(balance_after_deductible * plan.coinsurance_pct)
    member_cost_before_cap = applied_to_deductible + coinsurance_amount

    # Step 3 -- OOP cap
    oop_remaining = max(plan.oop_max_individual - accumulators.ind_oop_met, ZERO)
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
        triggering_threshold="N/A",  # individual tier has no family/individual choice
        member_cost=member_cost,
        prior_auth_required=False,  # set by pipeline/estimate.py after this call
    )
