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
    OUTPUT_PATH,
    PANES_FROM_EVAL_CASES,
    STANDALONE_PANES,
    build_panes,
)


@pytest.fixture(scope="module")
def committed() -> dict:
    return json.loads(OUTPUT_PATH.read_text())


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
    overlap = set(PANES_FROM_EVAL_CASES) & set(STANDALONE_PANES)
    assert not overlap, f"panes declared twice: {sorted(overlap)}"
    assert set(committed) == set(PANES_FROM_EVAL_CASES) | set(STANDALONE_PANES)


def test_eval_backed_panes_quote_their_case_verbatim(committed):
    """The ask card's question must be the case's question, character for
    character.

    This is the property that makes a screenshot evidence rather than
    illustration: the caption is the input the eval suite actually runs, so
    the image cannot claim a case it does not depict.
    """
    import yaml

    cases = {
        case["id"]: case
        for case in yaml.safe_load((REPO_ROOT / "evals" / "demo_scripts.yaml").read_text())["cases"]
    }
    for pane_id, case_id in PANES_FROM_EVAL_CASES.items():
        pane = committed[pane_id]
        assert pane["case_id"] == case_id
        assert pane["question"] == cases[case_id]["question"], pane_id
        assert pane["member_id"] == cases[case_id]["member_id"], pane_id


def test_standalone_panes_carry_no_borrowed_case_id(committed):
    """A pane with no eval case must say so.

    The UI renders a null case_id as an explicit "no eval case" stamp. If one
    of these ever acquired an id it would be a borrowed one, and the
    screenshot would point at a case that asserts nothing about it.
    """
    for pane_id in STANDALONE_PANES:
        assert committed[pane_id]["case_id"] is None, pane_id


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
        pane_id: pane for pane_id, pane in committed.items() if pane["priced"] is not None
    }
    assert priced_panes, "no priced panes -- the guard would pass vacuously"

    for pane_id, pane in priced_panes.items():
        priced = pane["priced"]
        expected = priced["cpt_code"] in plans[priced["plan_id"]]["prior_auth_required_codes"]
        assert priced["breakdown"]["prior_auth_required"] is expected, pane_id
