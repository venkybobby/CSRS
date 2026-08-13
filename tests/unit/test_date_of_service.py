"""Unit tests for the date-of-service rules -- pure date arithmetic and the
as-of-date eligibility derivation, no DB.

_derive_status is exercised directly rather than through get_eligibility()
so these run on every PR without TEST_DATABASE_URL; the DB-backed path is
covered by tests/integration/test_pipeline.py.
"""
from datetime import date, timedelta

import pytest
from csr_agent.data.eligibility import _derive_status
from csr_agent.pipeline.date_of_service import (
    MAX_DAYS_OUT,
    check_window,
    crosses_plan_year,
    max_quotable_date,
    not_eligible_reason_and_message,
    parse_date_of_service,
    plan_year_end,
)

TODAY = date(2026, 8, 13)

# George Ellery, M1010: ACTIVE, coverage 2026-01-01 .. 2026-08-31. The
# future-term member the whole dated yes/no demo is built on.
ELLERY_START = date(2026, 1, 1)
ELLERY_END = date(2026, 8, 31)


# --- window rules --------------------------------------------------------


def test_past_date_of_service_is_rejected():
    """A past date is a claims question -- there is no historical
    accumulator or rate-sheet state to answer it from."""
    assert check_window(date(2026, 7, 20), TODAY) == "IN_PAST"


def test_today_is_quotable():
    assert check_window(TODAY, TODAY) is None


def test_last_day_of_window_is_quotable():
    assert check_window(max_quotable_date(TODAY), TODAY) is None


def test_one_day_past_window_is_rejected():
    just_past = max_quotable_date(TODAY) + timedelta(days=1)
    assert check_window(just_past, TODAY) == "BEYOND_MAX_HORIZON"


def test_window_is_ninety_days():
    assert MAX_DAYS_OUT == 90
    assert max_quotable_date(TODAY) == date(2026, 11, 11)


# --- plan-year rules -----------------------------------------------------


def test_plan_year_end_is_calendar_year_end():
    assert plan_year_end(TODAY) == date(2026, 12, 31)


def test_december_31_does_not_cross():
    assert crosses_plan_year(date(2026, 12, 31), TODAY) is False


def test_january_1_crosses():
    assert crosses_plan_year(date(2027, 1, 1), TODAY) is True


def test_ninety_day_window_cannot_cross_plan_year_from_august():
    """The two bounds are independent, not redundant: from August the window
    caps out in November and the plan-year rule can never fire."""
    assert crosses_plan_year(max_quotable_date(TODAY), TODAY) is False


def test_ninety_day_window_does_cross_plan_year_from_november():
    """...but from mid-November it lands in February, which is exactly why
    both checks have to exist."""
    november = date(2026, 11, 15)
    assert check_window(date(2027, 1, 20), november) is None
    assert crosses_plan_year(date(2027, 1, 20), november) is True


# --- date parsing --------------------------------------------------------


@pytest.mark.parametrize("raw", ["2026-09-15", " 2026-09-15 "])
def test_parses_iso_dates(raw):
    assert parse_date_of_service(raw) == date(2026, 9, 15)


@pytest.mark.parametrize("raw", ["next month", "09/15/2026", "", "2026-13-45", "soon"])
def test_unparseable_dates_return_none_rather_than_guessing(raw):
    """Never silently fall back to today -- a wrong period looks exactly
    like a normal quote."""
    assert parse_date_of_service(raw) is None


# --- eligibility as of a date -------------------------------------------


def test_ellery_dated_yes_inside_coverage():
    """Demo screen, left half: date of service before coverage ends."""
    status, note = _derive_status(
        "ACTIVE", ELLERY_START, ELLERY_END, TODAY, date(2026, 8, 20)
    )
    assert status == "ACTIVE"
    assert "2026-08-20" in note
    assert "falls within the coverage period" in note
    assert "⚠️" not in note  # a settled yes, not a warning


def test_ellery_dated_no_after_coverage_ends():
    """Demo screen, right half: same member, date of service after coverage
    ends -- a definite no, not a warning to resolve."""
    status, note = _derive_status(
        "ACTIVE", ELLERY_START, ELLERY_END, TODAY, date(2026, 9, 15)
    )
    assert status == "NOT_COVERED_ON_DOS"
    assert note is None


def test_ellery_last_covered_day_is_still_a_yes():
    status, _ = _derive_status("ACTIVE", ELLERY_START, ELLERY_END, TODAY, ELLERY_END)
    assert status == "ACTIVE"


def test_ellery_day_after_coverage_is_a_no():
    status, _ = _derive_status(
        "ACTIVE", ELLERY_START, ELLERY_END, TODAY, date(2026, 9, 1)
    )
    assert status == "NOT_COVERED_ON_DOS"


def test_date_before_coverage_start_is_not_yet_effective():
    """coverage_start was never consulted before dates existed -- a new hire
    enrolled effective the 1st of next month has no other guard."""
    status, _ = _derive_status(
        "ACTIVE", date(2026, 10, 1), None, TODAY, date(2026, 9, 20)
    )
    assert status == "NOT_COVERED_ON_DOS"


def test_termed_stays_termed_regardless_of_date():
    """A termed member is blocked on the DB status alone -- the date of
    service never rescues them."""
    status, _ = _derive_status(
        "TERMED", ELLERY_START, date(2026, 5, 31), TODAY, date(2026, 8, 20)
    )
    assert status == "TERMED"


def test_no_date_of_service_preserves_the_original_warning():
    """Every new branch is gated on a date being supplied: without one the
    pre-existing ACTIVE_FUTURE_TERM behavior must be bit-for-bit unchanged,
    glyph included."""
    status, warning = _derive_status("ACTIVE", ELLERY_START, ELLERY_END, TODAY, None)
    assert status == "ACTIVE_FUTURE_TERM"
    assert warning == (
        "⚠️ Coverage ends 2026-08-31 -- "
        "confirm date of service falls within coverage period"
    )


def test_no_date_of_service_open_ended_member_is_plain_active():
    status, warning = _derive_status("ACTIVE", ELLERY_START, None, TODAY, None)
    assert status == "ACTIVE"
    assert warning is None


# --- refusal reason selection -------------------------------------------


def test_reason_is_coverage_ended_when_past_the_end():
    reason, message = not_eligible_reason_and_message(
        "George Ellery", ELLERY_START, ELLERY_END, date(2026, 9, 15)
    )
    assert reason == "COVERAGE_ENDED"
    assert "George Ellery" in message
    assert "2026-08-31" in message
    assert "2026-09-15" in message
    assert "Do not quote a cost." in message


def test_reason_is_not_yet_effective_when_before_the_start():
    reason, message = not_eligible_reason_and_message(
        "New Hire", date(2026, 10, 1), None, date(2026, 9, 20)
    )
    assert reason == "NOT_YET_EFFECTIVE"
    assert "does not begin until 2026-10-01" in message
    assert "Do not quote a cost." in message
