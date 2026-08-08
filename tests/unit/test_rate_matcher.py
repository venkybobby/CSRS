"""Unit tests for match_procedure() -- pure, no DB, using an in-memory
catalog built directly from db/seed/rate_sheet.json so the test data can
never silently drift from what's actually seeded.
"""
import json
from decimal import Decimal
from pathlib import Path

import pytest

from csr_agent.data.rate_matcher import RateSheetRow, match_procedure

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


def test_qualified_colonoscopy_still_forces_clarification(catalog):
    """Even a query that already contains 'preventive' still routes through
    clarification -- the CSR confirms explicitly rather than the system
    silently trusting a keyword match. (Matches the spec's framing: the
    system ASKS, it does not infer from phrasing.)"""
    result = match_procedure("preventive colonoscopy", catalog=catalog)
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
