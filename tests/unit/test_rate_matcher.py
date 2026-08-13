"""Unit tests for match_procedure() -- pure, no DB, using an in-memory
catalog built directly from db/seed/rate_sheet.json so the test data can
never silently drift from what's actually seeded.
"""
import json
from decimal import Decimal
from pathlib import Path

import pytest
from csr_agent.data.rate_matcher import RateSheetRow, match_procedure, resolve_clarification

SEED_PATH = Path(__file__).resolve().parents[2] / "db" / "seed" / "rate_sheet.json"


@pytest.fixture(scope="module")
def catalog() -> list[RateSheetRow]:
    with open(SEED_PATH, encoding="utf-8") as f:
        rows = json.load(f)
    return [
        RateSheetRow(
            cpt_code=r["cpt_code"],
            common_name=r["common_name"],
            search_aliases=tuple(r["search_aliases"]),
            negotiated_rate=Decimal(r["negotiated_rate"]) if r["negotiated_rate"] is not None else None,
        )
        for r in rows
    ]


def test_cardiac_ct_is_honest_miss(catalog):
    """Story 8 / Demo Script #5: Cardiac CT is deliberately absent from the
    15-procedure sheet -- must never fuzzy-match to something else."""
    result = match_procedure("Cardiac CT", catalog=catalog)
    assert result.status == "NOT_ON_FILE"
    assert result.cpt_code is None


def test_cardiac_ct_angiography_is_also_honest_miss(catalog):
    result = match_procedure("cardiac CT angiography", catalog=catalog)
    assert result.status == "NOT_ON_FILE"


def test_unqualified_colonoscopy_forces_clarification(catalog):
    """Story 2: colonoscopy without a preventive/diagnostic qualifier must
    always ask, regardless of fuzzy score -- never silently pick one."""
    result = match_procedure("colonoscopy", catalog=catalog)
    assert result.status == "NEEDS_CLARIFICATION"
    assert result.clarifying_question is not None
    assert "preventive" in result.clarifying_question.lower()
    assert "diagnostic" in result.clarifying_question.lower()
    candidate_codes = {c.cpt_code for c in result.candidates}
    assert candidate_codes == {"45380", "45378"}


@pytest.mark.parametrize(
    "query, expected_cpt",
    [
        ("wants a preventive colonoscopy", "45380"),
        ("screening colonoscopy", "45380"),
        ("M1001 is due for a routine colonoscopy", "45380"),
        ("diagnostic colonoscopy", "45378"),
        ("colonoscopy because of symptoms", "45378"),
    ],
)
def test_qualified_colonoscopy_resolves_without_asking(catalog, query, expected_cpt):
    """A query that ALREADY names preventive/diagnostic must not be sent
    back through the clarifying question.

    This reverses a previous expectation ("the system ASKS, it does not
    infer from phrasing"). That reading made the tool ask the CSR a
    question they had just answered -- with a member on hold -- which is
    the failure mode most likely to get the tool abandoned on the floor.
    The safety property it was protecting is unchanged and still tested
    below: the system never *silently picks* when the query is genuinely
    ambiguous, only when the CSR has already been explicit.

    Note "preventive colonoscopy" is an exact search_aliases entry on
    45380 -- the old gate returned before scoring ever ran, so a perfect
    100 match was discarded to ask about it.
    """
    result = match_procedure(query, catalog=catalog)
    assert result.status == "MATCHED"
    assert result.cpt_code == expected_cpt


def test_conflicting_qualifiers_still_force_clarification(catalog):
    """The narrow case the old always-ask rule was really protecting: a
    query naming BOTH sides is genuinely ambiguous and must still ask
    rather than resolve to whichever qualifier is listed first."""
    result = match_procedure("diagnostic colonoscopy after her screening", catalog=catalog)
    assert result.status == "NEEDS_CLARIFICATION"


def test_mri_on_his_knee_matches_cpt_73721(catalog):
    """Story 2 example phrase, verbatim."""
    result = match_procedure("MRI on his knee", catalog=catalog)
    assert result.status == "MATCHED"
    assert result.cpt_code == "73721"
    assert result.negotiated_rate == Decimal("1150.00")


def test_knee_surgery_matches_cpt_29881(catalog):
    result = match_procedure("knee surgery", catalog=catalog)
    assert result.status == "MATCHED"
    assert result.cpt_code == "29881"


def test_acupuncture_matches_but_has_no_rate(catalog):
    """Story 6: S8092 must be MATCHED (so the plan-level exclusion check can
    run) but carries no negotiated_rate -- Bronze excludes it before the
    rate is ever needed; Silver/Gold fall through to a genuine
    rate-not-found outcome. See rate_matcher.get_rate()."""
    result = match_procedure("acupuncture", catalog=catalog)
    assert result.status == "MATCHED"
    assert result.cpt_code == "S8092"
    assert result.negotiated_rate is None


def test_gibberish_query_is_not_on_file(catalog):
    result = match_procedure("xyzzy plugh nonsense procedure", catalog=catalog)
    assert result.status == "NOT_ON_FILE"


def test_empty_catalog_never_crashes():
    result = match_procedure("anything", catalog=[])
    assert result.status == "NOT_ON_FILE"


# The next two regression classes were caught by the eval harness running
# for real against Cloud Build, not by any test written before that --
# short isolated phrases ("MRI on his knee") all passed while the actual
# demo-script sentences and a cross-procedure discrimination check both
# failed. See rate_matcher.py's MATCH_THRESHOLD/scorer comment for the full
# story of what didn't work (token_sort_ratio, partial_token_set_ratio)
# before landing on token_set_ratio + query normalization.


def test_full_sentence_demo_script_questions_still_match(catalog):
    """The eval harness's actual question text -- a full CSR sentence with
    a member ID and filler phrasing, not an isolated phrase -- must match
    the same way the isolated phrase does. token_sort_ratio (the original
    scorer) scored these around 35-47 against the right alias, since it
    penalizes surrounding filler words as if they were edit-distance
    errors; below MATCH_THRESHOLD, so a real CSR question would have
    incorrectly returned NOT_ON_FILE for procedures genuinely on file."""
    cases = [
        ("M1002 wants an MRI on his knee, what does he owe?", "73721"),
        ("What's James Whitaker M1004 looking at for knee surgery?", "29881"),
        ("Same question for M1007 and M1006 -- knee surgery", "29881"),
    ]
    for question, expected_cpt in cases:
        result = match_procedure(question, catalog=catalog)
        assert result.status == "MATCHED", f"{question!r} -> {result.status} (expected MATCHED)"
        assert result.cpt_code == expected_cpt, f"{question!r} -> cpt={result.cpt_code}"


def test_does_not_cross_match_similar_body_part_procedures(catalog):
    """A real safety issue, not just a UX nit: partial_token_set_ratio (an
    earlier candidate fix for the sentence-matching problem above) scored
    'MRI on his back, low back pain' as a 100.0 match against 'mri brain'
    -- wrong body part -- purely because both share the token 'mri'.
    Confusing brain/back/knee MRIs would mean the wrong CPT, the wrong
    negotiated rate, and the wrong prior-auth determination. The
    distinguishing word (back/brain/knee) must actually drive the match,
    not just presence of the shared 'mri' token."""
    back = match_procedure("MRI on his back, low back pain", catalog=catalog)
    assert back.status == "MATCHED"
    assert back.cpt_code == "72148"  # MRI Low Back, not brain (70551) or knee (73721)

    brain = match_procedure("MRI on his brain please", catalog=catalog)
    assert brain.status == "MATCHED"
    assert brain.cpt_code == "70551"


# Turn 2 of the clarification exchange (Story 7). Regression class for a
# real defect: AMBIGUOUS_ALWAYS substring-matches "colonoscopy" on the query
# TEXT, so the CSR's own ANSWER was routed straight back to the same
# question whenever it contained that word -- including the candidate
# common_names the UI had just displayed to them. Only an answer that
# happened to omit the word ("screening") resolved, which is why the
# preventive $0 outcome was never demonstrable end-to-end.


def test_clarification_answer_resolves_to_preventive(catalog):
    """Story 7: the CSR answers "screening" and the system resolves to CPT
    45380 rather than re-asking.

    Turn 1 is a BARE "colonoscopy" rather than the qualified phrasing this
    originally used. A query that already names which kind it is now resolves
    outright and never reaches turn 2, so opening with one would test the
    clarify gate instead of resolve_clarification -- which is what this test
    is actually for. Bare "colonoscopy" is still genuinely ambiguous and
    still asks, so it is the honest way in.
    """
    turn1 = match_procedure("colonoscopy, what does she owe?", catalog=catalog)
    assert turn1.status == "NEEDS_CLARIFICATION"
    candidates = [c.cpt_code for c in turn1.candidates]

    turn2 = resolve_clarification(
        "screening", candidates, turn1.clarifying_question, catalog=catalog
    )
    assert turn2.status == "MATCHED"
    assert turn2.cpt_code == "45380"
    assert turn2.common_name == "Colonoscopy, Preventive (Screening)"


def test_clarification_answer_resolves_however_the_csr_phrases_it(catalog):
    """Every one of these previously looped back to the clarifying question
    because it contains the word "colonoscopy" -- including the candidate
    name the CSR is reading off their own screen."""
    turn1 = match_procedure("colonoscopy", catalog=catalog)
    candidates = [c.cpt_code for c in turn1.candidates]
    question = turn1.clarifying_question

    for answer, expected_cpt in [
        ("screening", "45380"),
        ("preventive", "45380"),
        ("screening colonoscopy", "45380"),
        ("Colonoscopy, Preventive (Screening)", "45380"),
        ("the screening one", "45380"),
        ("diagnostic", "45378"),
        ("diagnostic colonoscopy", "45378"),
    ]:
        result = resolve_clarification(answer, candidates, question, catalog=catalog)
        assert result.status == "MATCHED", f"{answer!r} -> {result.status}"
        assert result.cpt_code == expected_cpt, f"{answer!r} -> {result.cpt_code}"


def test_non_answer_re_asks_rather_than_guessing(catalog):
    """The margin rule, not the absolute score, is what protects this: a
    bare "colonoscopy" scores 100 against BOTH candidates, so it must not
    resolve to whichever one happens to sort first."""
    turn1 = match_procedure("colonoscopy", catalog=catalog)
    candidates = [c.cpt_code for c in turn1.candidates]
    question = turn1.clarifying_question

    for answer in ["colonoscopy", "yes", "not sure", "the one the doctor mentioned"]:
        result = resolve_clarification(answer, candidates, question, catalog=catalog)
        assert result.status == "NEEDS_CLARIFICATION", f"{answer!r} -> {result.cpt_code}"
        assert result.clarifying_question == question


def test_clarification_can_only_return_a_candidate_that_was_offered(catalog):
    """Restricting the pool is a safety property, not an optimization: an
    answer naming an entirely different procedure must not resolve here.
    (procedure_tool.py handles that pivot by falling through to normal
    free-text matching -- but this function must never do it silently.)"""
    turn1 = match_procedure("colonoscopy", catalog=catalog)
    candidates = [c.cpt_code for c in turn1.candidates]

    result = resolve_clarification(
        "knee surgery", candidates, turn1.clarifying_question, catalog=catalog
    )
    assert result.status == "NEEDS_CLARIFICATION"
    assert result.cpt_code != "29881"


def test_no_procedure_in_query_does_not_accidentally_match(catalog):
    """A termed-member-style question with no procedure mentioned at all
    must not accidentally fuzzy-match some unrelated catalog entry."""
    result = match_procedure("M1005 -- anything, what do they owe?", catalog=catalog)
    assert result.status == "NOT_ON_FILE"
