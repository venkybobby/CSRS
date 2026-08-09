"""Eligibility, plan, and accumulator reads. Plain DB reads plus the
status/date comparison for termed / future-term detection (Story 1) -- no
LLM involvement, no calculator math.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

from sqlalchemy import text

from csr_agent.calculator.types import MemberAccumulators, PlanTerms
from csr_agent.data.db import get_engine
from csr_agent.tools.models import EligibilityResult

# Plan §4 prompt-injection defense: member_id is validated against a strict
# format before it ever reaches a query, regardless of what free text the
# CSR/caller typed -- an injected instruction has no SQL- or path-shaped
# value it could smuggle through this parameter.
MEMBER_ID_RE = re.compile(r"^M\d{4}$")


@dataclass(frozen=True)
class PlanRow:
    plan_id: str
    display_name: str
    terms: PlanTerms
    preventive_covered_100pct_codes: frozenset[str]
    prior_auth_required_codes: frozenset[str]
    excluded_codes: frozenset[str]


def _derive_status(
    db_status: str, coverage_end: date | None, today: date
) -> tuple[Literal["ACTIVE", "TERMED", "ACTIVE_FUTURE_TERM"], str | None]:
    """Story 1: termed members are always blocked, regardless of phrasing.
    Active members whose coverage is scheduled to end (but hasn't yet) get a
    visible warning alongside their estimate, not a block."""
    if db_status == "TERMED":
        return "TERMED", None
    if coverage_end is not None and coverage_end >= today:
        warning = (
            f"⚠️ Coverage ends {coverage_end.isoformat()} -- "
            "confirm date of service falls within coverage period"
        )
        return "ACTIVE_FUTURE_TERM", warning
    return "ACTIVE", None


def get_eligibility(member_id: str, *, today: date | None = None) -> EligibilityResult:
    if not MEMBER_ID_RE.match(member_id):
        return EligibilityResult(member_id=member_id, found=False)

    today = today or date.today()
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT member_id, first_name, last_name, plan_id, tier, status, "
                "coverage_start, coverage_end FROM members WHERE member_id = :member_id"
            ),
            {"member_id": member_id},
        ).mappings().first()

    if row is None:
        return EligibilityResult(member_id=member_id, found=False)

    status, warning = _derive_status(row["status"], row["coverage_end"], today)
    return EligibilityResult(
        member_id=row["member_id"],
        found=True,
        name=f"{row['first_name']} {row['last_name']}",
        plan_id=row["plan_id"],
        tier=row["tier"],
        status=status,
        coverage_start=row["coverage_start"],
        coverage_end=row["coverage_end"],
        warning=warning,
    )


def get_plan(plan_id: str) -> PlanRow | None:
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT plan_id, display_name, deductible_individual, deductible_family, "
                "coinsurance_pct, oop_max_individual, oop_max_family, "
                "preventive_covered_100pct_codes, prior_auth_required_codes, excluded_codes "
                "FROM plans WHERE plan_id = :plan_id"
            ),
            {"plan_id": plan_id},
        ).mappings().first()

    if row is None:
        return None

    return PlanRow(
        plan_id=row["plan_id"],
        display_name=row["display_name"],
        terms=PlanTerms(
            deductible_individual=Decimal(row["deductible_individual"]),
            deductible_family=Decimal(row["deductible_family"]),
            coinsurance_pct=Decimal(row["coinsurance_pct"]),
            oop_max_individual=Decimal(row["oop_max_individual"]),
            oop_max_family=Decimal(row["oop_max_family"]),
        ),
        preventive_covered_100pct_codes=frozenset(row["preventive_covered_100pct_codes"]),
        prior_auth_required_codes=frozenset(row["prior_auth_required_codes"]),
        excluded_codes=frozenset(row["excluded_codes"]),
    )


def get_member_accumulators(member_id: str) -> MemberAccumulators | None:
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT ind_ded_met, ind_oop_met, fam_ded_met, fam_oop_met "
                "FROM member_accumulators WHERE member_id = :member_id"
            ),
            {"member_id": member_id},
        ).mappings().first()

    if row is None:
        return None

    return MemberAccumulators(
        ind_ded_met=Decimal(row["ind_ded_met"]),
        ind_oop_met=Decimal(row["ind_oop_met"]),
        fam_ded_met=Decimal(row["fam_ded_met"]),
        fam_oop_met=Decimal(row["fam_oop_met"]),
    )
