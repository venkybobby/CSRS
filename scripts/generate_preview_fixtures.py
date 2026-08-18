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
from csr_agent.data.rate_matcher import (  # noqa: E402
    RateSheetRow,
    match_procedure,
    resolve_clarification,
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
    # Story 6 -- Dana's explicit requirement that "not a covered benefit" and
    # "no rate on file" never look the same. These two cases are the same CPT
    # (S8092, which has a NULL negotiated_rate AND is excluded on Bronze) on
    # two different plans, so they are the sharpest available evidence that
    # the distinction is structural rather than cosmetic. Captured side by
    # side for exactly that reason.
    "exclusion-bronze": "exclusion_beats_missing_rate_on_bronze",
    "rate-not-found-silver": "same_code_is_rate_not_found_on_silver",
    "preventive-zero-cost": "preventive_colonoscopy_resolves_without_asking",
    "dated-yes": "dos_dated_yes_inside_coverage",
    "dated-no": "dos_dated_no_after_coverage_ends",
    "plan-year-boundary": "dos_plan_year_boundary_is_a_refusal",
    "past-date": "dos_in_past_is_a_claims_question",
    # The only pane whose result is a QUESTION rather than an answer. A bare
    # procedure family ties across three codes, so nothing is priced until the
    # CSR says which one. This is the outcome the client's steering committee
    # asked about -- "the model picks the procedure, what if it picks wrong?"
    # -- and the one screen docs/screenshots/ carried no image of.
    "clarify-ambiguous-mri": "bare_procedure_family_asks_which_one",
}

# Panes whose ask is declared here rather than read from demo_scripts.yaml,
# because the pane needs an input the eval case deliberately does not carry.
#
# The prior-auth banner used to sit here with case_id=None and rendered an
# explicit "no eval case" stamp -- honest, and the visible counterpart of the
# gap MVP1_STATUS.md disclosed. That gap is now closed by
# prior_auth_required_on_silver, so the pane carries the real id.
#
# It stays standalone rather than moving to PANES_FROM_EVAL_CASES because of
# one deliberate difference: this pane adds a date of service, so the screen
# also demonstrates the assumption line ("Balances are as of today and may
# change before..."), while the eval case omits any date on purpose -- a case
# that pins `today` has its outcome assertions SKIPPED in live mode, which
# would have gated the prior-auth flag offline only. The stamp is therefore a
# claim about the prior-auth behaviour this screen exists to show, which is
# genuinely gated, and not a claim that the date row is.
#
# M1002 + MRI Brain, for two independent reasons: 73721 is not prior-auth
# under Meridian Silver (only 70551 and 72148 are), and M1002's real
# accumulators are what make this a partial-deductible breakdown rather than
# a single deductible row.
STANDALONE_PANES = {
    "prior-auth": {
        "case_id": "prior_auth_required_on_silver",
        "question": "MRI brain for M1002",
        "member_id": "M1002",
        "cpt_code": "70551",
        "date_of_service": "2026-08-20",
        "asked_on": "2026-08-13",
    },
}


# Turn 2 of the clarification exchange.
#
# VIDEO_PLAN.md §5 calls shots 3 and 4 "the point of the video", and §3
# recorded that a fixture can show the question but not the exchange, so only
# a live recording against the deployed agent could show turn-taking. That was
# true of ONE pane. It is not true of two. With turn 2 here, the exchange is
# demonstrable with no agent, no deployed environment and no Reasoning Engine
# quota -- which is what makes the client walkthrough reproducible for free.
#
# The resolved CPT is deliberately NOT written here. It comes from
# resolve_clarification(), the real turn-2 API, restricted to the codes turn 1
# actually offered -- so this pane cannot claim an outcome the engine would
# not produce. If "knee" ever stops separating MRI Knee from MRI Brain and MRI
# Low Back by the required margin, the build fails instead of shipping a pane
# that says it resolved.
#
# `case` names the eval case in evals/demo_scripts.yaml's `multi_turn_cases:`
# block that this pane depicts -- evals/run_eval.py::run_multi_turn() runs
# exactly this exchange (same question, same answer, same member) and gates
# it against a cold twin (knee_without_pending_clarification_refuses: "knee" asked
# with no pending turn 1 must NOT resolve). The pane used to carry
# case_id=None and render an honest "no eval case" stamp, because
# demo_scripts.yaml's `cases:` are single-question and none of them covered a
# second turn; that gap is what run_multi_turn closes, so the stamp now names
# a case that is genuinely gated rather than only unit-tested. See also
# tests/unit/test_rate_matcher.py::test_clarification_answer_resolves_to_knee,
# which predates the eval case and still stands behind the same exchange.
CLARIFICATION_ANSWER_PANES = {
    "clarify-answered-knee": {
        "answers": "clarify-ambiguous-mri",
        "answer": "knee",
        "case": "clarify_mri_then_knee_resolves_to_mri_knee",
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
    demo_scripts_doc = yaml.safe_load(DEMO_SCRIPTS.read_text())
    cases = _by_id(demo_scripts_doc["cases"], "id")
    multi_turn_cases = _by_id(demo_scripts_doc.get("multi_turn_cases", []), "id")

    def member_context(member_id: str) -> dict[str, Any]:
        """Who the member is, straight from db/seed.

        Emitted for every pane, priced or not: a refusal banner still names
        the member and their plan, and those are the fields that made the
        drifted dated-yes fixture wrong in the first place.
        """
        member = members[member_id]
        plan = plans[member["plan_id"]]
        return {
            "name": f"{member['first_name']} {member['last_name']}",
            "plan_id": plan["plan_id"],
            "plan_display_name": plan["display_name"],
            "tier": member["tier"],
            "status": member["status"],
            "coverage_start": member["coverage_start"],
            "coverage_end": member["coverage_end"],
        }

    def procedure_context(cpt_code: str) -> dict[str, Any]:
        """The rate-sheet row. negotiated_rate is None for S8092, which is on
        the sheet by name but carries no price -- the exact condition Story
        6's rate-not-found case turns on."""
        rate = rates[cpt_code]
        return {
            "cpt_code": cpt_code,
            "common_name": rate["common_name"],
            "negotiated_rate": rate["negotiated_rate"],
        }

    def breakdown_for(member_id: str, cpt_code: str) -> dict[str, Any]:
        """The engine's own arithmetic for this member and code.

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
            field: str(value) if isinstance(value, Decimal) else value
            for field, value in vars(breakdown).items()
        }

    # Assembled from db/seed rather than the database, matching how
    # tests/unit/test_rate_matcher.py does it: this script must stay runnable
    # with no Postgres, like every other part of the fixture pipeline. Built
    # once at this level because BOTH turns of the clarification exchange
    # resolve against it, and two independently-built catalogs could disagree.
    catalog = [
        RateSheetRow(
            cpt_code=row["cpt_code"],
            common_name=row["common_name"],
            search_aliases=tuple(row["search_aliases"]),
            negotiated_rate=(
                Decimal(row["negotiated_rate"]) if row["negotiated_rate"] is not None else None
            ),
        )
        for row in _load("rate_sheet.json")
    ]

    def clarification_for(question: str) -> dict[str, Any]:
        """The question the CSR is asked and the candidates they are offered.

        The clarifying question is emitted rather than mirrored by hand in the
        TSX like the other response text, because unlike those it is not fixed
        prose -- rate_matcher interpolates the CSR's own words into it, and
        which of its two phrasings fires depends on whether the query tied
        above the match threshold or fell below it. Retyping that is how the
        pane would end up showing a sentence the engine never produced.
        """
        result = match_procedure(question, catalog=catalog)
        if result.status != "NEEDS_CLARIFICATION":
            raise SystemExit(
                f"pane question {question!r} was expected to need clarification but the "
                f"matcher returned {result.status!r} -- the pane and the case disagree"
            )
        return {
            "clarifying_question": result.clarifying_question,
            # score is emitted although nothing renders it, because the API
            # type carries it and the alternative is typing a number into the
            # TSX that the engine never produced. If a scorer change moves
            # these, test_preview_fixtures.py should say so.
            "candidates": [
                {"cpt_code": c.cpt_code, "common_name": c.common_name, "score": c.score}
                for c in result.candidates
            ],
        }

    def build(
        *,
        case_id: str | None,
        question: str,
        member_id: str,
        cpt_code: str | None,
        response_type: str | None,
        date_of_service: str | None,
        asked_on: str | None,
    ) -> dict[str, Any]:
        return {
            "case_id": case_id,
            "question": question,
            "member_id": member_id,
            "date_of_service": date_of_service,
            "asked_on": asked_on,
            "member": member_context(member_id),
            # None where no code is resolved at all -- demo_5's cardiac CT is
            # never on the rate sheet, so the pipeline stops before there is
            # a procedure to describe.
            "procedure": procedure_context(cpt_code) if cpt_code else None,
            # Only NEEDS_CLARIFICATION carries this, and it is produced by
            # running the real matcher against the real seeded rate sheet
            # rather than listed here. Hand-writing the candidate set would
            # let the pane keep showing three MRIs after someone added a
            # fourth to the sheet -- the precise class of drift this whole
            # file exists to prevent.
            "clarification": (
                clarification_for(question) if response_type == "NEEDS_CLARIFICATION" else None
            ),
            # Only STANDARD_COST reaches the calculator. Every other outcome
            # is a refusal or a flat $0, so there is no arithmetic that could
            # drift -- and asking for one would mean pricing S8092, which has
            # no negotiated rate by design.
            "breakdown": (
                breakdown_for(member_id, cpt_code)
                if cpt_code and response_type == "STANDARD_COST"
                else None
            ),
        }

    panes: dict[str, Any] = {}

    for pane_id, case_id in PANES_FROM_EVAL_CASES.items():
        case = cases[case_id]
        panes[pane_id] = build(
            case_id=case_id,
            question=case["question"],
            member_id=case["member_id"],
            cpt_code=case.get("expected_cpt_code"),
            response_type=case.get("expected_response_type"),
            date_of_service=case.get("date_of_service"),
            asked_on=case.get("today"),
        )

    for pane_id, spec in STANDALONE_PANES.items():
        # A stamp naming a case that no longer exists is worse than the "no
        # eval case" label it replaced: the label was honest about having no
        # coverage, whereas a dangling id asserts coverage that has gone.
        # Renaming or dropping the case must break the build here.
        declared = spec["case_id"]
        if declared is not None and declared not in cases:
            raise SystemExit(
                f"pane {pane_id!r} claims eval case {declared!r}, which is not in "
                "demo_scripts.yaml -- set case_id to None or fix the id"
            )
        panes[pane_id] = build(
            case_id=declared,
            question=spec["question"],
            member_id=spec["member_id"],
            cpt_code=spec["cpt_code"],
            response_type="STANDARD_COST",
            date_of_service=spec["date_of_service"],
            asked_on=spec["asked_on"],
        )

    # Built last: each of these reads the turn-1 pane it answers, so the
    # candidate list it resolves against is the one actually rendered on
    # screen rather than a second, independently-derived copy that could
    # disagree with it.
    for pane_id, spec in CLARIFICATION_ANSWER_PANES.items():
        turn_one = panes[spec["answers"]]
        asked = turn_one["clarification"]
        if asked is None:
            raise SystemExit(
                f"pane {pane_id!r} answers {spec['answers']!r}, but that pane carries no "
                "clarifying question -- it is not a turn 1"
            )

        # A stamp naming a case that no longer exists is worse than the "no
        # eval case" label it replaced -- see STANDALONE_PANES' identical
        # check above for why.
        declared_case = spec["case"]
        if declared_case not in multi_turn_cases:
            raise SystemExit(
                f"pane {pane_id!r} claims eval case {declared_case!r}, which is not in "
                "demo_scripts.yaml's multi_turn_cases -- set case to None or fix the id"
            )

        offered = [candidate["cpt_code"] for candidate in asked["candidates"]]
        resolved = resolve_clarification(
            spec["answer"], offered, asked["clarifying_question"], catalog=catalog
        )
        if resolved.status != "MATCHED":
            raise SystemExit(
                f"pane {pane_id!r}: answering {spec['answer']!r} to {spec['answers']!r} returned "
                f"{resolved.status}, not MATCHED. The exchange this pane depicts no longer "
                "resolves, so the pane would be claiming an outcome the engine does not produce."
            )

        panes[pane_id] = build(
            case_id=declared_case,
            question=spec["answer"],
            member_id=turn_one["member_id"],
            cpt_code=resolved.cpt_code,
            response_type="STANDARD_COST",
            date_of_service=None,
            asked_on=None,
        )

    return panes


def main() -> int:
    panes = build_panes()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(panes, indent=2) + "\n")
    priced_count = sum(1 for pane in panes.values() if pane["breakdown"])
    print(
        f"Wrote {len(panes)} panes ({priced_count} priced) to "
        f"{OUTPUT_PATH.relative_to(REPO_ROOT).as_posix()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
