"""Procedure resolution: plain-English text -> CPT code, via RapidFuzz
matching against the rate sheet. This is the deterministic engine behind the
resolve_procedure tool (Story 2) -- match thresholds are fixed, code-owned
constants, never an LLM judgment call.

match_procedure() takes an optional `catalog` argument specifically so it is
unit-testable with an in-memory fixture and never needs a live database in
tests -- the DB-backed default (_load_catalog_from_db) is only exercised by
integration tests and the running agent.
"""
from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from rapidfuzz import fuzz, process
from sqlalchemy import text

from csr_agent.calculator.types import RateInfo
from csr_agent.data.db import get_engine
from csr_agent.tools.models import ProcedureCandidate, ProcedureMatchResult

# Fixed thresholds (RapidFuzz token_set_ratio, 0-100). Code-owned, not model
# judgment -- see plan §2.1.
#
# Scorer choice matters a lot here and was wrong on the first pass:
# token_sort_ratio (edit-distance over the *whole* string) scores a real CSR
# question like "M1002 wants an MRI on his knee, what does he owe?" against
# the short alias "mri on his knee" way too low (~47) to ever match, because
# it penalizes the surrounding filler words as if they were errors.
# partial_token_set_ratio "fixes" that but overcorrects dangerously: it
# scored "MRI on his back, low back pain" as a 100.0 match against "mri
# brain" (wrong body part) just because both share the token "mri" --
# unacceptable here, a wrong CPT code is a wrong rate and a wrong prior-auth
# determination, not just a bad UX. Plain token_set_ratio on a
# member-ID-and-punctuation-stripped query (see _normalize_query) is the one
# that got every case right in manual verification: it tolerates arbitrary
# extra words (names, "what does he owe") because it compares token *sets*,
# but still requires the actual distinguishing word (knee/back/brain/...) to
# be present, so it doesn't confuse similar procedures the way the partial_
# variant does.
MATCH_THRESHOLD = 90
CLARIFY_THRESHOLD = 60
MAX_CLARIFY_CANDIDATES = 4

# Turn-2 thresholds, used ONLY by resolve_clarification() when scoring the
# CSR's answer against the candidates they were just shown. Deliberately not
# MATCH_THRESHOLD: that 90 governs open-ended free text against the whole
# rate sheet, where a near-miss means a different procedure entirely. Here
# the pool is restricted to the two codes already on the CSR's screen and
# they are answering a direct either/or question, so the reliable signal is
# SEPARATION between those candidates rather than absolute similarity -- a
# natural answer like "the screening one" scores only ~69 against the
# preventive row's aliases but beats the diagnostic row's by ~33. An answer
# that does not separate them (e.g. a bare "colonoscopy", which scores 100
# against both) falls below the margin and is re-asked rather than guessed.
CLARIFY_ANSWER_MIN_SCORE = 60
CLARIFY_ANSWER_MIN_MARGIN = 25

# Matches "M1002", "m1234", etc. so a member ID embedded in a free-text
# question doesn't get treated as a token to fuzzy-match against procedure
# names.
_MEMBER_ID_TOKEN_RE = re.compile(r"\bm\d{3,}\b")
_NON_ALPHANUMERIC_RE = re.compile(r"[^a-z0-9\s]")


def _normalize_query(query: str) -> str:
    q = query.strip().lower()
    q = _MEMBER_ID_TOKEN_RE.sub(" ", q)
    q = _NON_ALPHANUMERIC_RE.sub(" ", q)
    return " ".join(q.split())

# Procedures that are ALWAYS routed to clarification regardless of fuzzy
# score, because a single common-language term maps to genuinely different
# billing codes with different costs (Story 2: preventive CPT 45380 vs
# diagnostic CPT 45378 colonoscopy). Matched as a substring of the
# lowercased, stripped query.
AMBIGUOUS_ALWAYS = ("colonoscopy",)


@dataclass(frozen=True)
class RateSheetRow:
    cpt_code: str
    common_name: str
    search_aliases: tuple[str, ...]
    negotiated_rate: Decimal | None


def _load_catalog_from_db() -> list[RateSheetRow]:
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT cpt_code, common_name, search_aliases, negotiated_rate FROM rate_sheet")
        ).mappings().all()
    return [
        RateSheetRow(
            cpt_code=r["cpt_code"],
            common_name=r["common_name"],
            search_aliases=tuple(r["search_aliases"]),
            negotiated_rate=Decimal(r["negotiated_rate"]) if r["negotiated_rate"] is not None else None,
        )
        for r in rows
    ]


def _candidates_for_query(catalog: list[RateSheetRow], terms: tuple[str, ...]) -> list[ProcedureCandidate]:
    out = []
    for row in catalog:
        haystacks = (row.common_name.lower(), *[a.lower() for a in row.search_aliases])
        if any(any(term in h for term in terms) for h in haystacks):
            out.append(ProcedureCandidate(cpt_code=row.cpt_code, common_name=row.common_name, score=100.0))
    return out


def match_procedure(query: str, catalog: list[RateSheetRow] | None = None) -> ProcedureMatchResult:
    if catalog is None:
        catalog = _load_catalog_from_db()

    normalized = _normalize_query(query)

    forced = next((term for term in AMBIGUOUS_ALWAYS if term in normalized), None)
    if forced is not None:
        candidates = _candidates_for_query(catalog, (forced,))
        return ProcedureMatchResult(
            query=query,
            status="NEEDS_CLARIFICATION",
            candidates=candidates,
            clarifying_question="Is this a preventive (screening) or diagnostic colonoscopy?",
        )

    # Flatten (row, searchable text) pairs -- one row can be reached by
    # several aliases, so we track the best-scoring row rather than the
    # best-scoring string.
    choices: dict[str, RateSheetRow] = {}
    for row in catalog:
        for text_ in (row.common_name, *row.search_aliases):
            choices[text_.lower()] = row

    if not choices:
        return ProcedureMatchResult(query=query, status="NOT_ON_FILE")

    match = process.extractOne(normalized, choices.keys(), scorer=fuzz.token_set_ratio)
    if match is None:
        return ProcedureMatchResult(query=query, status="NOT_ON_FILE")

    matched_text, score, _ = match
    row = choices[matched_text]

    if score >= MATCH_THRESHOLD:
        return ProcedureMatchResult(
            query=query,
            status="MATCHED",
            cpt_code=row.cpt_code,
            common_name=row.common_name,
            negotiated_rate=row.negotiated_rate,
        )

    if score >= CLARIFY_THRESHOLD:
        top = process.extract(
            normalized, choices.keys(), scorer=fuzz.token_set_ratio, limit=MAX_CLARIFY_CANDIDATES
        )
        seen_cpt: set[str] = set()
        candidates = []
        for text_, s, _ in top:
            r = choices[text_]
            if r.cpt_code in seen_cpt:
                continue
            seen_cpt.add(r.cpt_code)
            candidates.append(ProcedureCandidate(cpt_code=r.cpt_code, common_name=r.common_name, score=s))
        return ProcedureMatchResult(
            query=query,
            status="NEEDS_CLARIFICATION",
            candidates=candidates,
            clarifying_question=(
                f"I found a few possible matches for '{query}' -- "
                "could you confirm which procedure this is?"
            ),
        )

    return ProcedureMatchResult(query=query, status="NOT_ON_FILE")


def resolve_clarification(
    answer: str,
    candidate_cpt_codes: Sequence[str],
    clarifying_question: str,
    catalog: list[RateSheetRow] | None = None,
) -> ProcedureMatchResult:
    """Turn 2 of a clarification: interpret the CSR's answer as a choice
    among the candidates that were offered on turn 1 (Story 2/7).

    This exists because AMBIGUOUS_ALWAYS is a property of the query TEXT,
    not of the conversation: it substring-matches "colonoscopy", so every
    query containing that word -- including the CSR's own answer, and
    including the candidate common_names the UI just displayed to them --
    was routed straight back to the same clarifying question. Only an
    answer that happened to omit the word (a bare "screening") could ever
    resolve, which made Story 7's preventive $0 path unreachable in
    practice.

    Restricting the pool to the offered codes is also strictly safer than
    re-running open free-text matching: the outcome can only ever be one of
    the codes the CSR was actually shown, never some third procedure.
    """
    if catalog is None:
        catalog = _load_catalog_from_db()

    normalized = _normalize_query(answer)
    offered = [row for row in catalog if row.cpt_code in set(candidate_cpt_codes)]

    scored: list[tuple[float, RateSheetRow]] = []
    for row in offered:
        haystacks = (row.common_name, *row.search_aliases)
        best_for_row = max(
            (fuzz.token_set_ratio(normalized, h.lower()) for h in haystacks), default=0.0
        )
        scored.append((best_for_row, row))
    scored.sort(key=lambda pair: pair[0], reverse=True)

    if scored:
        best_score, best_row = scored[0]
        runner_up_score = scored[1][0] if len(scored) > 1 else 0.0
        if (
            best_score >= CLARIFY_ANSWER_MIN_SCORE
            and best_score - runner_up_score >= CLARIFY_ANSWER_MIN_MARGIN
        ):
            return ProcedureMatchResult(
                query=answer,
                status="MATCHED",
                cpt_code=best_row.cpt_code,
                common_name=best_row.common_name,
                negotiated_rate=best_row.negotiated_rate,
            )

    # Not decisive -- re-ask the SAME question verbatim rather than picking
    # the higher of two indistinguishable scores.
    return ProcedureMatchResult(
        query=answer,
        status="NEEDS_CLARIFICATION",
        candidates=[
            ProcedureCandidate(cpt_code=row.cpt_code, common_name=row.common_name, score=score)
            for score, row in scored
        ],
        clarifying_question=clarifying_question,
    )


def get_procedure_name(cpt_code: str) -> str | None:
    """The rate sheet's friendly common_name for an already-resolved CPT
    code. Deliberately separate from get_rate(): every CSR-visible message
    that names a procedure needs this, including the two branches where
    get_rate() returns None and therefore can't supply it -- an excluded
    code (S8092 on Bronze, exclusion fires before any rate is needed) and a
    matched-but-unpriced code (S8092 on Silver/Gold, NULL negotiated_rate).
    Returns None only for a code with no rate_sheet row at all, which the
    pipeline renders as the bare code rather than inventing a name."""
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT common_name FROM rate_sheet WHERE cpt_code = :cpt_code"),
            {"cpt_code": cpt_code},
        ).mappings().first()

    return row["common_name"] if row is not None else None


def get_rate(cpt_code: str) -> RateInfo | None:
    """Direct lookup by an already-resolved CPT code (used by the pipeline
    after resolve_procedure has matched, never by free-text). Returns None
    both when no row exists AND when the row exists but negotiated_rate is
    NULL (see 0001_init_schema.sql -- e.g. CPT S8092, which must be
    matchable/nameable for the exclusion check to fire, but has no payable
    rate)."""
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT negotiated_rate FROM rate_sheet WHERE cpt_code = :cpt_code"),
            {"cpt_code": cpt_code},
        ).mappings().first()

    if row is None or row["negotiated_rate"] is None:
        return None
    return RateInfo(cpt_code=cpt_code, negotiated_rate=Decimal(row["negotiated_rate"]))
