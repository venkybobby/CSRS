"""Diffs db/seed/rate_sheet.json against Meridian's own rate sheet,
db/seed/source/rate_sheet_2026.xlsx.

This is the only test in the suite that checks a fact the system cannot
check about itself. Everything else -- the calculator tests, the eval
suite, the numeric-provenance guardrail in the BFF -- verifies that a
displayed figure traces back to a tool payload, and every one of them
passed while 8 of the 11 shared rates were wrong, 4 of Meridian's
procedures were missing from the seed, and 3 procedures were seeded that
Meridian never negotiated. That is not a gap in those tests; it is their
boundary. The provenance chain runs model -> tool -> seed, and a chain
that terminates at the seed can only ever prove the seed was used
faithfully, never that the seed was right.

So this test crosses the boundary: it reads the client artifact and
asserts the seed is a faithful mirror of it. J. Morrow (Finance) reissues
that sheet monthly on the first business day from September, and a
rate-sheet update is exactly a reseed -- so this is also the check that
makes the update cadence safe to operate rather than something to hold
one's breath through.

What is and is not diffed:
  * negotiated_rate and the set of CPT codes ARE diffed. They are
    Meridian's facts and we do not get a vote.
  * common_name and search_aliases are NOT diffed. Those are the app's
    display and search vocabulary -- ours to choose, and deliberately
    divergent in places (see the _note row in rate_sheet.json for the
    'cardiac' omission and why Story 8 depends on it).
"""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import openpyxl
import pytest

# Imported hard, not via pytest.importorskip. A missing openpyxl must break
# the build, not quietly skip the one check that crosses the trust boundary
# -- the live eval gate already taught this repo what a self-skipping gate
# is worth. openpyxl is pinned in requirements-dev.txt for exactly this.

REPO_ROOT = Path(__file__).resolve().parents[2]
SEED_PATH = REPO_ROOT / "db" / "seed" / "rate_sheet.json"
SOURCE_XLSX = REPO_ROOT / "db" / "seed" / "source" / "rate_sheet_2026.xlsx"

# The one seeded CPT that is legitimately absent from Meridian's sheet.
# S8092 (acupuncture) exists so Story 6's Bronze exclusion has something to
# fire on and so Silver/Gold produce a real "no rate on file" outcome; it
# carries a NULL rate precisely because Meridian has not negotiated one.
# Anything else off-sheet is an invented rate, which is the failure this
# test exists to catch -- so this allowlist must stay tiny and each entry
# must justify itself in the seed's _source field.
OFF_SHEET_BY_DESIGN = {"S8092"}

_HEADER_CPT_CELL = "CPT Code"


def _load_source_sheet() -> dict[str, Decimal]:
    """{cpt_code: negotiated_rate} straight out of the client's workbook.

    The header is not on row 1 -- the sheet opens with a title line and a
    provenance line ("Last updated: ... (J. Morrow)"), so the header row is
    located by value rather than by index. If Finance reshapes the workbook
    this raises rather than silently reading zero rows and passing.
    """
    workbook = openpyxl.load_workbook(SOURCE_XLSX, data_only=True)
    sheet = workbook.worksheets[0]
    rows = list(sheet.iter_rows(values_only=True))

    header_index = next(
        (i for i, row in enumerate(rows) if row and row[0] == _HEADER_CPT_CELL),
        None,
    )
    assert header_index is not None, (
        f"No {_HEADER_CPT_CELL!r} header found in {SOURCE_XLSX.name} -- the workbook layout "
        "changed and this test needs updating before its result means anything."
    )

    rates: dict[str, Decimal] = {}
    for row in rows[header_index + 1 :]:
        if not row or row[0] is None:
            continue
        cpt_code, _description, _common_name, rate = row[:4]
        rates[str(cpt_code).strip()] = Decimal(str(rate))

    assert rates, f"{SOURCE_XLSX.name} parsed to zero rate rows."
    return rates


def _load_seed() -> dict[str, Decimal | None]:
    with open(SEED_PATH, encoding="utf-8") as f:
        rows = json.load(f)
    return {
        r["cpt_code"]: (Decimal(r["negotiated_rate"]) if r["negotiated_rate"] is not None else None)
        for r in rows
    }


@pytest.fixture(scope="module")
def source_rates() -> dict[str, Decimal]:
    return _load_source_sheet()


@pytest.fixture(scope="module")
def seeded_rates() -> dict[str, Decimal | None]:
    return _load_seed()


def test_every_seeded_rate_matches_the_source_sheet(source_rates, seeded_rates):
    """The drift check. A $50 error here is not a typo -- the product's
    entire claim is that a quoted figure is Meridian's figure."""
    drift = {
        cpt: (seeded_rates[cpt], expected)
        for cpt, expected in source_rates.items()
        if cpt in seeded_rates and seeded_rates[cpt] != expected
    }
    assert not drift, "Seeded rates disagree with rate_sheet_2026.xlsx: " + ", ".join(
        f"{cpt}: seeded {seeded} != sheet {expected}" for cpt, (seeded, expected) in sorted(drift.items())
    )


def test_every_procedure_on_the_sheet_is_seeded(source_rates, seeded_rates):
    """The omission check. A procedure on Meridian's sheet that is missing
    from the seed makes the system answer 'we have no rate on file' about a
    rate Meridian holds -- the same false-statement class as the dilution
    defect in the matcher, reached through the data instead of the code."""
    missing = sorted(set(source_rates) - set(seeded_rates))
    assert not missing, (
        "On rate_sheet_2026.xlsx but absent from the seed, so the system will deny having a rate "
        f"for them: {missing}"
    )


def test_no_seeded_procedure_is_absent_from_the_sheet(source_rates, seeded_rates):
    """The invention check, and the sharpest of the three.

    A seeded procedure that Meridian never negotiated gets quoted with a
    real-looking rate and a full provenance stamp, because the guardrail's
    question is 'did this number come from a tool?' and the answer is yes.
    This is the only check that asks the other question.
    """
    invented = sorted(set(seeded_rates) - set(source_rates) - OFF_SHEET_BY_DESIGN)
    assert not invented, (
        "Seeded but not on rate_sheet_2026.xlsx -- these would be quoted as negotiated rates "
        f"Meridian never agreed to: {invented}"
    )


@pytest.mark.parametrize("cpt_code", sorted(OFF_SHEET_BY_DESIGN))
def test_off_sheet_allowlist_entries_carry_no_rate(seeded_rates, cpt_code):
    """The allowlist is an escape hatch for rows that must be *matchable*
    without being *priceable* (S8092 -- Story 6). Letting one carry a
    non-NULL rate would reopen the invention hole through the exemption."""
    assert cpt_code in seeded_rates, f"{cpt_code} is allowlisted as off-sheet but is not seeded at all."
    assert seeded_rates[cpt_code] is None, (
        f"{cpt_code} is allowlisted as absent from Meridian's sheet, so it must carry a NULL rate -- "
        f"found {seeded_rates[cpt_code]}. A priced off-sheet row is an invented rate with a waiver."
    )
