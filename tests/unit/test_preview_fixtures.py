"""The committed preview fixtures must still be what the engine produces.

frontend/src/fixtures/previewPanes.json feeds the /?preview and
/?preview=demo pages, which are what docs/screenshots/ is captured from. The
figures in it are generated from db/seed through the real calculator, and the
questions from evals/demo_scripts.yaml -- but a generated file that nobody
checks is just a hand-maintained file with extra steps, because the moment a
rate, an accumulator, or the calculator changes, the committed copy is stale
and the screenshots quietly start showing arithmetic the engine no longer
does.

This is not hypothetical. The dated-yes pane shipped showing M1010 owing
$470 with $1,200 of deductible met; M1010's seeded accumulators are all
$0.00, so the engine produces $1,150 with no coinsurance. The wrong figures
were M1002's accumulator profile printed under George Ellery's name, and
they survived review because a result panel with no visible question looks
equally correct whatever it says.
"""

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from generate_preview_fixtures import (  # noqa: E402
    CLARIFICATION_ANSWER_PANES,
    OUTPUT_PATH,
    PANES_FROM_EVAL_CASES,
    STANDALONE_PANES,
    build_panes,
)

# Every pane must come from exactly one of the three declaration sites.
ALL_DECLARED = set(PANES_FROM_EVAL_CASES) | set(STANDALONE_PANES) | set(CLARIFICATION_ANSWER_PANES)


@pytest.fixture(scope="module")
def committed() -> dict:
    return json.loads(OUTPUT_PATH.read_text())


def _eval_cases() -> list[dict]:
    """The eval cases, as the generator itself reads them. Imported lazily
    for the same reason the callers used to inline it -- pyyaml is a dev
    dependency and this module is imported by tooling that does not need it."""
    import yaml

    return yaml.safe_load((REPO_ROOT / "evals" / "demo_scripts.yaml").read_text())["cases"]


def test_committed_fixtures_match_a_fresh_generation(committed):
    """The whole guard, in one comparison.

    Covers every way the fixtures can rot at once: a changed negotiated
    rate, an edited accumulator, a calculator fix, a reworded question in
    demo_scripts.yaml, or a pane added to the generator and never
    regenerated.
    """
    assert committed == build_panes(), (
        "frontend/src/fixtures/previewPanes.json is stale -- the preview pages "
        "(and every screenshot in docs/screenshots/) would show figures the "
        "engine no longer produces. Regenerate with:\n"
        "    python scripts/generate_preview_fixtures.py\n"
        "then re-capture with:\n"
        "    python scripts/capture_demo_screenshots.py"
    )


def test_every_pane_is_declared_exactly_once(committed):
    """No pane may come from both an eval case and a standalone declaration.

    A pane declared in both places would silently take whichever branch runs
    last in build_panes(), so an eval-case-backed pane could end up rendering
    a hand-written question while still displaying that case's id.
    """
    sites = (PANES_FROM_EVAL_CASES, STANDALONE_PANES, CLARIFICATION_ANSWER_PANES)
    seen: set[str] = set()
    for site in sites:
        overlap = seen & set(site)
        assert not overlap, f"panes declared twice: {sorted(overlap)}"
        seen |= set(site)
    assert set(committed) == ALL_DECLARED


def test_eval_backed_panes_quote_their_case_verbatim(committed):
    """The ask card's question must be the case's question, character for
    character.

    This is the property that makes a screenshot evidence rather than
    illustration: the caption is the input the eval suite actually runs, so
    the image cannot claim a case it does not depict.
    """
    cases = {case["id"]: case for case in _eval_cases()}
    for pane_id, case_id in PANES_FROM_EVAL_CASES.items():
        pane = committed[pane_id]
        assert pane["case_id"] == case_id
        assert pane["question"] == cases[case_id]["question"], pane_id
        assert pane["member_id"] == cases[case_id]["member_id"], pane_id


def test_standalone_panes_carry_no_borrowed_case_id(committed):
    """A standalone pane's stamp must be earned, or absent.

    This began as "standalone panes must have a null case_id", which was the
    right rule while no eval case existed for the prior-auth banner: the UI
    renders null as an explicit "no eval case" stamp, and any id would have
    been borrowed from a case asserting nothing about that screen.

    prior_auth_required_on_silver now asserts exactly what the prior-auth
    pane shows, so the blanket rule would forbid a true statement. What the
    original was really protecting is kept and made checkable: a stamp must
    name a case that exists AND that is about this pane's member and
    procedure. An id whose case has been renamed, deleted, or repointed at a
    different member fails here -- which is strictly worse than "no eval
    case", because that label was at least honest about having no coverage.
    """
    cases = {case["id"]: case for case in _eval_cases()}

    for pane_id in STANDALONE_PANES:
        pane = committed[pane_id]
        case_id = pane["case_id"]
        if case_id is None:
            continue

        assert case_id in cases, f"{pane_id}: stamp names {case_id!r}, which no longer exists"
        case = cases[case_id]
        assert case["member_id"] == pane["member_id"], (
            f"{pane_id}: stamped {case_id!r}, but that case is about member "
            f"{case['member_id']} and this pane shows {pane['member_id']}"
        )
        assert case.get("expected_cpt_code") == pane["procedure"]["cpt_code"], (
            f"{pane_id}: stamped {case_id!r}, but that case is about CPT "
            f"{case.get('expected_cpt_code')} and this pane shows {pane['procedure']['cpt_code']}"
        )


def test_clarification_answer_pane_really_answers_its_turn_one(committed):
    """Turn 2 must resolve to a code turn 1 actually offered.

    The pane exists to show the exchange without a live agent, and the whole
    value of that is that it depicts a real resolution. A turn 2 naming a CPT
    that was never on the CSR's screen would be a staged conversation --
    exactly the kind of illustration these fixtures exist not to be.
    """
    for pane_id, spec in CLARIFICATION_ANSWER_PANES.items():
        turn_one = committed[spec["answers"]]
        turn_two = committed[pane_id]

        assert turn_one["clarification"] is not None, f"{spec['answers']} is not a turn 1"
        offered = {c["cpt_code"] for c in turn_one["clarification"]["candidates"]}

        assert turn_two["procedure"] is not None, f"{pane_id} resolved to nothing"
        assert turn_two["procedure"]["cpt_code"] in offered, (
            f"{pane_id} resolved to {turn_two['procedure']['cpt_code']}, which was not among the "
            f"candidates turn 1 offered ({sorted(offered)})"
        )
        assert turn_two["member_id"] == turn_one["member_id"], (
            f"{pane_id} prices a different member than the question it answers"
        )
        assert turn_two["question"] == spec["answer"]


def test_priced_panes_price_only_what_the_plan_covers(committed):
    """prior_auth_required must match the plan's own list.

    The calculator deliberately leaves this field False and
    pipeline/estimate.py sets it from the plan afterwards, so it is the one
    figure the generator reproduces rather than reads. Asserting it here
    against db/seed keeps that reproduction honest -- a prior-auth banner on
    a procedure the plan does not gate would be a false instruction to a CSR.
    """
    plans = {
        plan["plan_id"]: plan
        for plan in json.loads((REPO_ROOT / "db" / "seed" / "plans.json").read_text())
    }
    priced_panes = {
        pane_id: pane for pane_id, pane in committed.items() if pane["breakdown"] is not None
    }
    assert priced_panes, "no priced panes -- the guard would pass vacuously"

    for pane_id, pane in priced_panes.items():
        plan = plans[pane["member"]["plan_id"]]
        expected = pane["procedure"]["cpt_code"] in plan["prior_auth_required_codes"]
        assert pane["breakdown"]["prior_auth_required"] is expected, pane_id


def test_only_standard_cost_cases_carry_a_breakdown(committed):
    """Every other outcome is a refusal or a flat $0.

    This is the invariant that keeps Story 6's pair honest: S8092 has no
    negotiated rate at all, so a breakdown appearing on either the exclusion
    or the rate-not-found pane would mean the generator had priced something
    the plan cannot price.
    """
    cases = {case["id"]: case for case in _eval_cases()}
    for pane_id, case_id in PANES_FROM_EVAL_CASES.items():
        expected_standard = cases[case_id].get("expected_response_type") == "STANDARD_COST"
        has_breakdown = committed[pane_id]["breakdown"] is not None
        assert has_breakdown is expected_standard, pane_id


def test_story_6_pair_is_the_same_code_on_different_plans(committed):
    """The pair only demonstrates anything if the code really is identical.

    Story 6 is Dana's requirement that "not a covered benefit" and "no rate
    on file" never look the same. The evidence is weak unless both panes ask
    about the same CPT -- otherwise the screens could differ for the trivial
    reason that the procedures differ.
    """
    excluded = committed["exclusion-bronze"]
    unpriced = committed["rate-not-found-silver"]
    assert excluded["procedure"]["cpt_code"] == unpriced["procedure"]["cpt_code"] == "S8092"
    assert excluded["member"]["plan_id"] != unpriced["member"]["plan_id"]
    # The condition the whole distinction turns on: no rate on either plan,
    # so only the exclusion list separates them.
    assert excluded["procedure"]["negotiated_rate"] is None
    assert unpriced["procedure"]["negotiated_rate"] is None
