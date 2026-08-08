"""Pure input types for the calculator module. Deliberately not the DB row
models -- the calculator must never import anything from data/, so it stays
testable with zero I/O and has no way to accidentally issue a query."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class PlanTerms:
    deductible_individual: Decimal
    deductible_family: Decimal
    coinsurance_pct: Decimal
    oop_max_individual: Decimal
    oop_max_family: Decimal


@dataclass(frozen=True)
class RateInfo:
    cpt_code: str
    negotiated_rate: Decimal


@dataclass(frozen=True)
class MemberAccumulators:
    ind_ded_met: Decimal
    ind_oop_met: Decimal
    fam_ded_met: Decimal
    fam_oop_met: Decimal
