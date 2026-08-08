"""Cent-precision rounding shared by individual.py and family.py.

Not exported outside calculator/ -- this is an internal helper, not part of
the calculator's public (plan, rate, accumulators) -> CostBreakdown contract.
"""
from decimal import ROUND_HALF_UP, Decimal

CENTS = Decimal("0.01")


def to_cents(amount: Decimal) -> Decimal:
    return amount.quantize(CENTS, rounding=ROUND_HALF_UP)
