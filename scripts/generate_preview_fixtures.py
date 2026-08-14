"""Generate the preview pages' fixture data from db/seed and the real calculator.

    python scripts/generate_preview_fixtures.py

Writes frontend/src/fixtures/previewPanes.json, which
frontend/src/pages/DateOfServicePreview.tsx and DemoScriptPreview.tsx import.
tests/unit/test_preview_fixtures.py regenerates this in memory and fails if
the committed file differs, so CI catches a stale copy.

Why this exists rather than hand-written fixtures:

The preview fixtures were hand-maintained copies of engine output, and one
had silently drifted -- the dated-yes pane showed M1010 owing $470 with
$1,200 of deductible met, while M1010's seeded accumulators are all $0.00
and the engine produces $1,150 with no coinsurance. Those were M1002's
accumulators printed under George Ellery's name. Fixing that one instance
left every other fixture free to drift the same way the next time the
calculator, the rate sheet, or a member's accumulators change.

So nothing here is typed by hand twice. Questions, member ids, and dates come
from evals/demo_scripts.yaml -- the same file the eval suite asserts against,
so a screenshot's caption cannot disagree with the case it claims to depict.
Names, plans, rates, and every dollar figure come from db/seed through the
real calculator. Only prose the engine does not own (refusal message text,
audit ids) stays in the TSX.
"""

from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "agent"))

from csr_agent.calculator.family import family_tier_cost  # noqa: E402
from csr_agent.calculator.individual import individual_tier_cost  # noqa: E402
from csr_agent.calculator.types import (  # noqa: E402
    MemberAccumulators,
    PlanTerms,
    RateInfo,
)

SEED_DIR = REPO_ROOT / "db" / "seed"
DEMO_SCRIPTS = REPO_ROOT / "evals" / "demo_scripts.yaml"
OUTPUT_PATH = REPO_ROOT / "frontend" / "src" / "fixtures" / "previewPanes.json"

# pane id (the data-capture slug) -> the case in evals/demo_scripts.yaml it
# depicts. The pane's question, member, date of service and pinned `today`
# are read from that case, so the ask card shown above a result is the same
# text the eval suite runs.
PANES_FROM_EVAL_CASES = {
    "demo-1-partial-deductible": "demo_1_partial_deductible_and_coinsurance",
    "demo-2-oop-cap": "demo_2_oop_max_binding",
    "demo-3a-family-individual-threshold": "demo_3a_embedded_family_m1006",
    "demo-3b-family-family-threshold": "demo_3b_embedded_family_m1007",
    "demo-4-termed-block": "demo_4_termed_member_block",
    "demo-5-honest-miss": "demo_5_honest_miss",
    "dated-yes": "dos_dated_yes_inside_coverage",
    "dated-no": "dos_dated_no_after_coverage_ends",
    "plan-year-boundary": "dos_plan_year_boundary_is_a_refusal",
    "past-date": "dos_in_past_is_a_claims_question",
}

# The one pane with no eval case behind it. Story 4's prior-auth banner is
# not triggered by any demo-script or date-of-service case, so its ask is
# declared here instead of read from demo_scripts.yaml -- and it is rendered
# with an explicit "no eval case" stamp rather than a borrowed id.
#
# M1002 + MRI Brain, for two independent reasons: 73721 is not prior-auth
# under Meridian Silver (only 70551 and 72148 are), and M1002's real
# accumulators are what make this a partial-deductible breakdown rather than
# a single deductible row.
STANDALONE_PANES = {
    "prior-auth": {
        "case_id": None,
        "question": "MRI brain for M1002",
        "member_id": "M1002",
        "cpt_code": "70551",
        "date_of_service": "2026-08-20",
        "asked_on": "2026-08-13",
    },
}


def _load(name: str) -> Any:
    return json.loads((SEED_DIR / name).read_text())


def _by_id(rows: list[dict], key: str) -> dict[str, dict]:
    return {row[key]: row for row in rows}


def build_panes() -> dict[str, Any]:
    import yaml

    plans = _by_id(_load("plans.json"), "plan_id")
    rates = _by_id(_load("rate_sheet.json"), "cpt_code")
    members = _by_id(_load("members.json"), "member_id")
    accumulators = _by_id(_load("member_accumulators.json"), "member_id")
    cases = _by_id(yaml.safe_load(DEMO_SCRIPTS.read_text())["cases"], "id")

    def priced(member_id: str, cpt_code: str) -> dict[str, Any]:
        """The engine's own answer for this member and code.

        Runs the same calculator the agent runs, then applies the one field
        the calculator deliberately leaves unset -- pipeline/estimate.py sets
        prior_auth_required from the plan after the call, so reproducing that
        here is what keeps the prior-auth banner honest.
        """
        member = members[member_id]
        plan = plans[member["plan_id"]]
        rate = rates[cpt_code]
        acc = accumulators[member_id]

        terms = PlanTerms(
            deductible_individual=Decimal(plan["deductible_individual"]),
            deductible_family=Decimal(plan["deductible_family"]),
            coinsurance_pct=Decimal(plan["coinsurance_pct"]),
            oop_max_individual=Decimal(plan["oop_max_individual"]),
            oop_max_family=Decimal(plan["oop_max_family"]),
        )
        calculate = family_tier_cost if member["tier"] == "FAMILY" else individual_tier_cost
        breakdown = calculate(
            terms,
            RateInfo(cpt_code=cpt_code, negotiated_rate=Decimal(rate["negotiated_rate"])),
            MemberAccumulators(
                ind_ded_met=Decimal(acc["ind_ded_met"]),
                ind_oop_met=Decimal(acc["ind_oop_met"]),
                fam_ded_met=Decimal(acc["fam_ded_met"]),
                fam_oop_met=Decimal(acc["fam_oop_met"]),
            ),
        )
        breakdown.prior_auth_required = cpt_code in plan["prior_auth_required_codes"]

        return {
            "member_name": f"{member['first_name']} {member['last_name']}",
            "plan_id": plan["plan_id"],
            "plan_display_name": plan["display_name"],
            "tier": member["tier"],
            "coverage_start": member["coverage_start"],
            "coverage_end": member["coverage_end"],
            "cpt_code": cpt_code,
            "common_name": rate["common_name"],
            "negotiated_rate": rate["negotiated_rate"],
            "breakdown": {
                field: str(value) if isinstance(value, Decimal) else value
                for field, value in vars(breakdown).items()
            },
        }

    panes: dict[str, Any] = {}

    for pane_id, case_id in PANES_FROM_EVAL_CASES.items():
        case = cases[case_id]
        cpt_code = case.get("expected_cpt_code")
        panes[pane_id] = {
            "case_id": case_id,
            "question": case["question"],
            "member_id": case["member_id"],
            "date_of_service": case.get("date_of_service"),
            "asked_on": case.get("today"),
            # Refusal cases resolve no CPT at all (the eligibility check or
            # the rate lookup blocks first), so there is nothing to price and
            # nothing that can drift numerically.
            "priced": priced(case["member_id"], cpt_code) if cpt_code else None,
        }

    for pane_id, spec in STANDALONE_PANES.items():
        panes[pane_id] = {
            "case_id": spec["case_id"],
            "question": spec["question"],
            "member_id": spec["member_id"],
            "date_of_service": spec["date_of_service"],
            "asked_on": spec["asked_on"],
            "priced": priced(spec["member_id"], spec["cpt_code"]),
        }

    return panes


def main() -> int:
    panes = build_panes()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(panes, indent=2) + "\n")
    priced_count = sum(1 for pane in panes.values() if pane["priced"])
    print(
        f"Wrote {len(panes)} panes ({priced_count} priced) to "
        f"{OUTPUT_PATH.relative_to(REPO_ROOT).as_posix()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
