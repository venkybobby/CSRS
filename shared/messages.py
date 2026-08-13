"""Canonical, code-owned response text (Story 8 / plan §2.2: the model
relays these, it does not author them). Lives in shared/ because both the
agent's pipeline (agent/csr_agent/pipeline/estimate.py, when a rate is
absent after a code has already been matched) and the BFF (bff/app/main.py,
when resolve_procedure itself never finds a match at all) need the exact
same wording -- a CSR should see an identical message regardless of which
tool caught the "honest miss".
"""
from __future__ import annotations


def rate_not_found_message(procedure_as_typed: str) -> str:
    return (
        f"We don't have a negotiated rate on file for {procedure_as_typed}. Do not estimate. "
        "Please transfer to Member Services supervisor or advise the member "
        "we'll call back with a confirmed cost."
    )


def termed_member_message(name: str, coverage_end: str) -> str:
    return f"{name} is not eligible as of {coverage_end}. Do not quote a cost."


# --- Date-of-service refusals -------------------------------------------
#
# All four are worded as instructions to a CSR, matching every other message
# in this module: they name what the CSR should DO (route to Claims, call
# back closer to the date, do not quote) rather than merely stating a fact.
# That is deliberate and is the reason these are not member-safe strings --
# see the phase-2 note on CSR-initiated send.


def coverage_ended_before_dos_message(
    name: str, coverage_end: str, date_of_service: str
) -> str:
    return (
        f"{name}'s coverage ends {coverage_end}, so they are not eligible on the "
        f"requested date of service {date_of_service}. Do not quote a cost."
    )


def not_yet_effective_message(
    name: str, coverage_start: str, date_of_service: str
) -> str:
    return (
        f"{name}'s coverage does not begin until {coverage_start}, so they are not "
        f"eligible on the requested date of service {date_of_service}. "
        "Do not quote a cost."
    )


def date_of_service_in_past_message(date_of_service: str, today: str) -> str:
    return (
        f"Date of service {date_of_service} is in the past (today is {today}). "
        "This tool estimates upcoming procedures only -- a past date of service is "
        "a claims question, not an estimate. Route to Claims; do not estimate."
    )


def date_of_service_too_far_out_message(
    date_of_service: str, max_date: str, max_days: int
) -> str:
    return (
        f"Date of service {date_of_service} is more than {max_days} days out; "
        f"estimates are supported through {max_date}. Benefit balances change too "
        "much over a longer horizon to estimate reliably. Do not quote -- advise "
        "the member to call back closer to the date."
    )


def plan_year_boundary_message(
    name: str, date_of_service: str, plan_year_end: str, plan_id: str
) -> str:
    """The guardrail Meridian is quoting to Compliance: a refusal, not a
    caveated guess, for any date of service in the next plan year."""
    return (
        f"Date of service {date_of_service} falls in the next plan year (the "
        f"current plan year ends {plan_year_end}). {name}'s deductible and "
        "out-of-pocket balances reset January 1, and the plan on file "
        f"({plan_id}) covers the current year only -- next year's terms are not "
        "on file. Do not quote a cost for this date; advise the member we can "
        "estimate once the new plan year begins."
    )


def accumulator_assumption_note(today: str, date_of_service: str) -> str:
    """Printed on every quote carrying a future date of service.

    Eligibility is evaluated exactly as of the date of service, but the
    dollar figure is not: member_accumulators holds one current-balance row
    with no history and no projection. This sentence is what keeps a
    future-dated quote from reading as a promise.
    """
    return (
        f"Estimate uses deductible and out-of-pocket balances as of {today}; these "
        f"may change before {date_of_service} if the member has other services in "
        "the meantime."
    )
