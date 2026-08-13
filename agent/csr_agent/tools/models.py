"""Pydantic I/O contracts for CSRSupport tools.

These types are the structural enforcement mechanism for the non-negotiable
constraint that the LLM never generates a dollar figure: only StandardCostResult
and PreventiveZeroCostResult carry money fields, and PreventiveZeroCostResult's
member_cost is a computed property (not a constructor field), so it is pinned to
0.00 and cannot be set by any caller. Every other outcome (termed, excluded,
not-on-file, needs-clarification) has no dollar field on its type at all -- it is
not just "expected to be empty," it does not exist as an attribute a caller could
set. All models forbid extra fields so a typo'd or adversarial payload key raises
immediately instead of being silently dropped.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EligibilityResult(StrictModel):
    member_id: str
    found: bool
    name: str | None = None
    plan_id: str | None = None
    tier: Literal["INDIVIDUAL", "FAMILY"] | None = None
    # NOT_COVERED_ON_DOS is reachable only when a date of service was
    # supplied: without one the question is "covered today?", which the
    # ACTIVE/ACTIVE_FUTURE_TERM pair already answers. The two reasons it can
    # fire (coverage ended before the date, coverage not yet effective on it)
    # are distinguished by NotEligibleOnDateResult.reason rather than by two
    # statuses, so the frontend keeps a single not-covered branch to render.
    status: Literal[
        "ACTIVE", "TERMED", "ACTIVE_FUTURE_TERM", "NOT_COVERED_ON_DOS"
    ] | None = None
    coverage_start: date | None = None
    coverage_end: date | None = None
    warning: str | None = None  # e.g. "coverage ends 2026-08-31" -- code-populated only
    # The date this determination was made FOR -- today when the CSR gave no
    # date of service, otherwise the date they gave. Carried so the audit row
    # records what question was actually answered, not just its answer.
    evaluated_as_of: date | None = None


class ProcedureCandidate(StrictModel):
    cpt_code: str
    common_name: str
    score: float


class ProcedureMatchResult(StrictModel):
    query: str
    status: Literal["MATCHED", "NEEDS_CLARIFICATION", "NOT_ON_FILE"]
    cpt_code: str | None = None
    common_name: str | None = None
    negotiated_rate: Decimal | None = None
    candidates: list[ProcedureCandidate] = Field(default_factory=list)
    clarifying_question: str | None = None  # exact text, code-owned, never LLM-authored


class CostBreakdown(StrictModel):
    negotiated_rate: Decimal
    deductible_individual: Decimal
    deductible_met_ytd: Decimal
    deductible_remaining: Decimal
    applied_to_deductible: Decimal
    balance_after_deductible: Decimal
    coinsurance_pct: Decimal
    coinsurance_amount: Decimal
    member_cost_before_cap: Decimal
    oop_remaining: Decimal
    oop_cap_triggered: bool
    triggering_threshold: Literal["INDIVIDUAL", "FAMILY", "N/A"]
    member_cost: Decimal
    prior_auth_required: bool


class MemberNotFoundResult(StrictModel):
    response_type: Literal["MEMBER_NOT_FOUND"] = "MEMBER_NOT_FOUND"
    member_id: str
    message: str
    audit_id: UUID
    source_tool_calls: list[str] = Field(default_factory=list)


class TermedMemberResult(StrictModel):
    response_type: Literal["TERMED_BLOCK"] = "TERMED_BLOCK"
    eligibility: EligibilityResult
    message: str
    audit_id: UUID
    source_tool_calls: list[str] = Field(default_factory=list)


class DateOfServiceInvalidResult(StrictModel):
    """The requested date cannot be quoted at all -- a request-level refusal
    that fires before the member is even looked up, so it carries a
    member_id rather than an EligibilityResult."""

    response_type: Literal["DATE_OF_SERVICE_INVALID"] = "DATE_OF_SERVICE_INVALID"
    member_id: str
    date_of_service: date
    reason: Literal["IN_PAST", "BEYOND_MAX_HORIZON"]
    message: str
    audit_id: UUID
    source_tool_calls: list[str] = Field(default_factory=list)


class NotEligibleOnDateResult(StrictModel):
    """Member exists and is not termed, but is outside their coverage window
    on the requested date. Distinct from TERMED_BLOCK: this member may be
    perfectly eligible today, just not on the date being asked about."""

    response_type: Literal["NOT_ELIGIBLE_ON_DOS"] = "NOT_ELIGIBLE_ON_DOS"
    eligibility: EligibilityResult
    date_of_service: date
    reason: Literal["COVERAGE_ENDED", "NOT_YET_EFFECTIVE"]
    message: str
    audit_id: UUID
    source_tool_calls: list[str] = Field(default_factory=list)


class PlanYearBoundaryResult(StrictModel):
    """Member IS eligible on the date -- we simply cannot price it. Both the
    accumulators and the plan record are current-year-scoped, so there is no
    honest number to give. Carries no dollar field, like every other refusal
    in this module."""

    response_type: Literal["PLAN_YEAR_BOUNDARY"] = "PLAN_YEAR_BOUNDARY"
    eligibility: EligibilityResult
    date_of_service: date
    plan_year_end: date
    message: str
    audit_id: UUID
    source_tool_calls: list[str] = Field(default_factory=list)


class ExclusionResult(StrictModel):
    response_type: Literal["EXCLUSION"] = "EXCLUSION"
    eligibility: EligibilityResult
    cpt_code: str
    common_name: str | None = None
    plan_id: str
    message: str
    audit_id: UUID
    source_tool_calls: list[str] = Field(default_factory=list)


class RateNotFoundResult(StrictModel):
    response_type: Literal["RATE_NOT_FOUND"] = "RATE_NOT_FOUND"
    eligibility: EligibilityResult
    procedure_query: str
    message: str
    audit_id: UUID
    source_tool_calls: list[str] = Field(default_factory=list)


class PreventiveZeroCostResult(StrictModel):
    response_type: Literal["PREVENTIVE_ZERO_COST"] = "PREVENTIVE_ZERO_COST"
    eligibility: EligibilityResult
    cpt_code: str
    common_name: str
    # None when the CSR named no date -- deliberately not defaulted to today,
    # so a quote never prints a date of service the CSR did not actually give.
    date_of_service: date | None = None
    message: str
    audit_id: UUID
    source_tool_calls: list[str] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def member_cost(self) -> Decimal:
        """Always $0 -- a computed property, not a constructor field. Combined
        with StrictModel's extra="forbid", passing member_cost=... to the
        constructor raises a ValidationError rather than being silently
        accepted or dropped."""
        return Decimal("0.00")


class StandardCostResult(StrictModel):
    response_type: Literal["STANDARD_COST"] = "STANDARD_COST"
    eligibility: EligibilityResult
    procedure: ProcedureMatchResult
    breakdown: CostBreakdown
    # See PreventiveZeroCostResult.date_of_service -- None when unstated.
    date_of_service: date | None = None
    message: str
    audit_id: UUID
    source_tool_calls: list[str] = Field(default_factory=list)


class NeedsClarificationResult(StrictModel):
    response_type: Literal["NEEDS_CLARIFICATION"] = "NEEDS_CLARIFICATION"
    clarifying_question: str
    candidates: list[ProcedureCandidate] = Field(default_factory=list)
    message: str


class ToolCallRef(StrictModel):
    tool_name: str
    invocation_id: str


class AgentResponse(StrictModel):
    """The agent's structured final-turn output (plan §2.2 layer 2). Forces
    the model to point at a tool result rather than free-compose an answer:
    tool_result_ref should be the audit_id of the CostEstimateResult (or
    ProcedureMatchResult, for a clarification turn) the message is based on,
    and evidence lists every tool invocation that contributed."""

    message: str
    tool_result_ref: str
    evidence: list[ToolCallRef] = Field(default_factory=list)


CostEstimateResult = Annotated[
    MemberNotFoundResult
    | DateOfServiceInvalidResult
    | TermedMemberResult
    | NotEligibleOnDateResult
    | PlanYearBoundaryResult
    | ExclusionResult
    | RateNotFoundResult
    | PreventiveZeroCostResult
    | StandardCostResult
    | NeedsClarificationResult,
    Field(discriminator="response_type"),
]
