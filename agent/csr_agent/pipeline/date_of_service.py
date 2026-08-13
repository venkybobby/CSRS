"""Date-of-service window and plan-year rules.

Pure date arithmetic -- no DB, no LLM, no member context. These rules decide
whether a requested date of service can be quoted AT ALL, which is a
separate question from whether a given member is eligible on it (that lives
in data/eligibility.py::_derive_status).

Why the two hard bounds are both needed, since they look redundant:

  * MAX_DAYS_OUT caps how far ahead benefit balances stay meaningful.
  * The plan-year stop catches a date of service in the NEXT plan year.

From August, 90 days out is mid-November -- it can never cross January 1, so
the window check alone would never fire the plan-year rule. From mid-
November, 90 days lands in February and crosses it. Neither bound subsumes
the other at any point in the year.

The plan-year rule is the stricter of the two and is deliberately a refusal
rather than a caveated estimate. Deductible and out-of-pocket accumulators
reset January 1, so a January quote priced off today's balances is wrong by
up to a full deductible -- and wrong in the direction the member notices.
The plan record itself is also year-scoped (plan_ids are literally
"MER-SLV-2026"), so next year's coinsurance, exclusion list, and preventive
list are not on file either. That is why the check sits ahead of the
exclusion and preventive branches in the pipeline and not merely ahead of
the calculator: none of those answers are year-independent.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

from shared.messages import (
    coverage_ended_before_dos_message,
    not_yet_effective_message,
)

# Meridian's scheduling horizon, per Dana (Meridian CSR ops): matches how
# long a prior authorization stays valid, so a date beyond it would need
# re-auth anyway before the service happened.
MAX_DAYS_OUT = 90

DateOfServiceProblem = Literal["IN_PAST", "BEYOND_MAX_HORIZON"]


def plan_year_end(reference: date) -> date:
    """Last day of the plan year containing `reference`.

    All three Meridian plans are calendar-year (confirmed with Marcus), so
    this is derivable rather than a stored field. It is a function -- not a
    hardcoded December 31 comparison at the call site -- specifically so
    that a future non-calendar plan year becomes a change to this one place
    plus a plan lookup, rather than a hunt through comparison operators.
    """
    return date(reference.year, 12, 31)


def crosses_plan_year(date_of_service: date, today: date) -> bool:
    """True when the date of service falls in a later plan year than today.

    Compared against the plan year END rather than by comparing years so it
    stays correct if plan_year_end() ever stops being December 31.
    """
    return date_of_service > plan_year_end(today)


def check_window(date_of_service: date, today: date) -> DateOfServiceProblem | None:
    """The reason this date of service cannot be quoted, or None if it can.

    Past dates are rejected rather than evaluated: a date of service that has
    already happened is a claims question (what was actually billed, what the
    accumulators were at the time, which rate sheet applied), and this tool
    has no historical accumulator or rate-sheet history to answer it from.
    Quoting one would produce a confident number that has nothing to do with
    the member's actual liability.
    """
    if date_of_service < today:
        return "IN_PAST"
    if date_of_service > today + timedelta(days=MAX_DAYS_OUT):
        return "BEYOND_MAX_HORIZON"
    return None


def max_quotable_date(today: date) -> date:
    return today + timedelta(days=MAX_DAYS_OUT)


NotEligibleReason = Literal["COVERAGE_ENDED", "NOT_YET_EFFECTIVE"]


def not_eligible_reason_and_message(
    name: str,
    coverage_start: date | None,
    coverage_end: date | None,
    date_of_service: date,
) -> tuple[NotEligibleReason, str]:
    """Which side of the coverage window the date fell outside, and the
    CSR-facing sentence for it.

    Shared by the pipeline and by check_eligibility, which both have to
    produce this refusal: check_eligibility because the agent is instructed
    to stop there for an ineligible member, and the pipeline because a
    direct estimate call must never depend on the model having done so.
    Taking primitives rather than an EligibilityResult keeps this module
    free of a models import and makes it trivially unit-testable.
    """
    if coverage_start is not None and date_of_service < coverage_start:
        return "NOT_YET_EFFECTIVE", not_yet_effective_message(
            name, coverage_start.isoformat(), date_of_service.isoformat()
        )
    if coverage_end is None:
        raise ValueError(
            f"{name} is NOT_COVERED_ON_DOS on {date_of_service.isoformat()} but has "
            "neither a coverage_start after it nor a coverage_end before it"
        )
    return "COVERAGE_ENDED", coverage_ended_before_dos_message(
        name, coverage_end.isoformat(), date_of_service.isoformat()
    )


def parse_date_of_service(raw: str) -> date | None:
    """Parse an ISO date supplied by the model, or None if it is not one.

    Returns None rather than raising or guessing: a malformed date must
    become an explicit refusal the CSR can see, never a silently-defaulted
    "today" that would quote the wrong period.
    """
    try:
        return date.fromisoformat(raw.strip())
    except (ValueError, AttributeError):
        return None
