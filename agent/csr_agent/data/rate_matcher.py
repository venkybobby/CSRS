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

# How close a runner-up has to score before a win stops counting as an
# identification and starts counting as a tie.
#
# The defect this closes: clearing MATCH_THRESHOLD used to return MATCHED
# immediately, and the ambiguity check only ran BELOW it -- so the more
# confidently a query tied, the less likely it was to be questioned. A bare
# "MRI" scores 100 by token subset against "mri brain", "mri knee" and "mri
# low back" alike, and the winner was whichever alias happened to sort first:
# MRI Brain, silently, for a caller who may have meant either of the others.
# Meanwhile "an MRI" fell below the threshold and correctly asked -- exactly
# the wrong way round.
#
# This is the same shape as the colonoscopy clarify-gate defect, which was
# closed by adding the term to AMBIGUOUS_ALWAYS below: a fix for one known
# word rather than for the general case. This is the general case, and it is
# why that list does not have to grow every time the rate sheet does.
AMBIGUITY_MARGIN = 5

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

# ...but only when the CSR has not ALREADY said which one. The gate above
# short-circuits before any scoring, so without this it fired even on
# "preventive colonoscopy" -- which is an exact search_aliases entry on
# 45380 and scores 100. Asking a question the CSR just answered, with a
# caller on hold, is the single fastest way to get a tool abandoned.
#
# Keyed by the ambiguous term (not global) so a second AMBIGUOUS_ALWAYS
# entry cannot silently inherit colonoscopy's vocabulary -- "routine" means
# preventive for a colonoscopy but would mean nothing for, say, an MRI
# with/without contrast.
DISAMBIGUATORS: dict[str, dict[str, tuple[str, ...]]] = {
    "colonoscopy": {
        "45380": ("preventive", "screening", "screen", "routine", "wellness"),
        "45378": ("diagnostic", "symptom", "follow up", "followup", "problem"),
    },
}


def _disambiguated_cpt(term: str, normalized: str) -> str | None:
    """The CPT an already-qualified ambiguous query resolves to, or None to
    fall through to the clarifying question.

    Deliberately requires exactly ONE side to match: a query naming both
    (e.g. "diagnostic colonoscopy after her screening") is genuinely
    ambiguous and must still be asked about rather than resolved by
    whichever qualifier happened to be listed first.
    """
    hits = {
        cpt_code
        for cpt_code, qualifiers in DISAMBIGUATORS.get(term, {}).items()
        if any(qualifier in normalized for qualifier in qualifiers)
    }
    return hits.pop() if len(hits) == 1 else None


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


def _ambiguous_family_candidates(
    normalized: str, catalog: list[RateSheetRow]
) -> list[ProcedureCandidate]:
    """Procedures sharing a word the query used, when nothing scored at all.

    The second half of the ambiguity defect, and the more damaging half.
    token_set_ratio is diluted by filler, so a short family name inside a
    natural sentence -- "M1001 wants an MRI" -- scores BELOW even
    CLARIFY_THRESHOLD and fell through to NOT_ON_FILE. That tells the CSR we
    have no negotiated rate on file for an MRI, which is not a hedge or a
    near-miss but a false statement about the rate sheet, and Story 8's
    honest-miss wording is exactly the wrong script for it.

    So before declaring a miss, check whether the CSR used a word that
    several DIFFERENT procedures share. If they did, they named a family and
    not a procedure, and the answer is a question rather than a denial. A
    word belonging to one procedure proves nothing here -- that query would
    have scored above threshold already -- and a word belonging to none, as
    in "cardiac CT", still correctly falls through to the honest miss.
    """
    by_token: dict[str, set[str]] = {}
    rows_by_cpt: dict[str, RateSheetRow] = {}
    for row in catalog:
        rows_by_cpt[row.cpt_code] = row
        for haystack in (row.common_name, *row.search_aliases):
            for token in _normalize_query(haystack).split():
                by_token.setdefault(token, set()).add(row.cpt_code)

    for token in normalized.split():
        cpts = by_token.get(token, set())
        if len(cpts) > 1:
            return [
                ProcedureCandidate(
                    cpt_code=c, common_name=rows_by_cpt[c].common_name, score=100.0
                )
                for c in sorted(cpts)
            ][:MAX_CLARIFY_CANDIDATES]
    return []


def _tied_candidates(
    normalized: str, choices: dict[str, RateSheetRow], top_score: float
) -> list[ProcedureCandidate]:
    """Distinct procedures scoring within AMBIGUITY_MARGIN of the winner.

    Deduplicated by CPT code, because one procedure is reachable through
    several aliases and two aliases of the SAME code tying is not ambiguity --
    that is just "mri knee" and "mri on his knee" both being right. Only a
    second *code* within the margin means the query failed to pick one.
    """
    ranked = process.extract(
        normalized, choices.keys(), scorer=fuzz.token_set_ratio, limit=len(choices)
    )
    floor = top_score - AMBIGUITY_MARGIN
    seen: set[str] = set()
    tied: list[ProcedureCandidate] = []
    for text_, s, _ in ranked:
        if s < floor:
            break
        r = choices[text_]
        if r.cpt_code in seen:
            continue
        seen.add(r.cpt_code)
        tied.append(ProcedureCandidate(cpt_code=r.cpt_code, common_name=r.common_name, score=s))
        if len(tied) >= MAX_CLARIFY_CANDIDATES:
            break
    return tied


def match_procedure(query: str, catalog: list[RateSheetRow] | None = None) -> ProcedureMatchResult:
    if catalog is None:
        catalog = _load_catalog_from_db()

    normalized = _normalize_query(query)

    forced = next((term for term in AMBIGUOUS_ALWAYS if term in normalized), None)
    if forced is not None:
        already_qualified = _disambiguated_cpt(forced, normalized)
        if already_qualified is not None:
            row = next((r for r in catalog if r.cpt_code == already_qualified), None)
            # A qualifier pointing at a code the rate sheet doesn't carry is
            # a seed/config mismatch, not a CSR error -- fall through to the
            # question rather than reporting a confident NOT_ON_FILE.
            if row is not None:
                return ProcedureMatchResult(
                    query=query,
                    status="MATCHED",
                    cpt_code=row.cpt_code,
                    common_name=row.common_name,
                    negotiated_rate=row.negotiated_rate,
                )

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
        # An exact hit on a procedure's own name or one of its aliases is
        # decisive. The CSR typed the thing itself, so there is nothing to
        # ask about -- and asking anyway is the failure the DISAMBIGUATORS
        # note above already warns about: a question the CSR just answered,
        # with a caller on hold.
        if normalized != matched_text:
            tied = _tied_candidates(normalized, choices, score)
            if len(tied) > 1:
                return ProcedureMatchResult(
                    query=query,
                    status="NEEDS_CLARIFICATION",
                    candidates=tied,
                    clarifying_question=(
                        f"'{query}' matches more than one procedure equally well -- "
                        "which one is this?"
                    ),
                )

        return ProcedureMatchResult(
            query=query,
            status="MATCHED",
            cpt_code=row.cpt_code,
            common_name=row.common_name,
            negotiated_rate=row.negotiated_rate,
        )

    if score >= CLARIFY_THRESHOLD:
        # A named family beats a fuzzy ranking, even here. If the CSR used a
        # word that several DIFFERENT procedures share, they named a family,
        # and the family IS the candidate list -- a shared token is real
        # vocabulary, while a score in this band is often noise. "can we get
        # an MRI for her" scrapes 63.6 against the alias "mri on her knee"
        # on the strength of the word "her", and letting that drive the
        # answer offers MRI Knee first and pads the list with whatever ranks
        # next (Knee X-Ray, which shares nothing with the question).
        #
        # This is the third appearance of one shape: the wrong branch
        # winning on an accident of score. A tie above MATCH_THRESHOLD used
        # to resolve silently; dilution below CLARIFY_THRESHOLD used to fall
        # through to NOT_ON_FILE; and consulting the family check only below
        # this line meant a query that accidentally cleared it got the worse
        # answer. Same fix each time -- ask the semantic question before the
        # numeric one.
        named_family = _ambiguous_family_candidates(normalized, catalog)
        if len(named_family) > 1:
            return ProcedureMatchResult(
                query=query,
                status="NEEDS_CLARIFICATION",
                candidates=named_family,
                clarifying_question=(
                    f"'{query}' could be more than one procedure -- which one is this?"
                ),
            )

        # Rank everything and cap AFTER deduplicating by CPT, not before.
        # Capping the raw ranking at MAX_CLARIFY_CANDIDATES first caps
        # *aliases*, and one procedure owns several: "can we get an MRI for
        # her" filled all four slots with two codes (mri on her knee, mri of
        # the brain, head mri, mri knee) and dropped MRI Low Back entirely,
        # offering the CSR a two-way choice between three real options. The
        # constant means "at most four procedures to choose between", which
        # is what _tied_candidates() already implements -- this branch simply
        # never got the same treatment, and equal scores break by dict
        # insertion order, so which procedure vanished depended on the row
        # order in rate_sheet.json.
        top = process.extract(
            normalized, choices.keys(), scorer=fuzz.token_set_ratio, limit=len(choices)
        )
        seen_cpt: set[str] = set()
        candidates = []
        for text_, s, _ in top:
            r = choices[text_]
            if r.cpt_code in seen_cpt:
                continue
            seen_cpt.add(r.cpt_code)
            candidates.append(ProcedureCandidate(cpt_code=r.cpt_code, common_name=r.common_name, score=s))
            if len(candidates) >= MAX_CLARIFY_CANDIDATES:
                break
        return ProcedureMatchResult(
            query=query,
            status="NEEDS_CLARIFICATION",
            candidates=candidates,
            clarifying_question=(
                f"I found a few possible matches for '{query}' -- "
                "could you confirm which procedure this is?"
            ),
        )

    family = _ambiguous_family_candidates(normalized, catalog)
    if len(family) > 1:
        return ProcedureMatchResult(
            query=query,
            status="NEEDS_CLARIFICATION",
            candidates=family,
            clarifying_question=(
                f"'{query}' could be more than one procedure -- which one is this?"
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
