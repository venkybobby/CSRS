// Mirrors agent/csr_agent/tools/models.py's CostEstimateResult discriminated
// union. Keep these two definitions in sync by hand for MVP1 -- see
// docs/architecture/future-integration.md for the note on generating this
// from the backend schema in a later phase instead of hand-mirroring.

export interface EligibilityResult {
  member_id: string;
  found: boolean;
  name: string | null;
  plan_id: string | null;
  tier: "INDIVIDUAL" | "FAMILY" | null;
  status: "ACTIVE" | "TERMED" | "ACTIVE_FUTURE_TERM" | null;
  coverage_start: string | null;
  coverage_end: string | null;
  warning: string | null;
}

export interface CostBreakdown {
  negotiated_rate: string;
  deductible_individual: string;
  deductible_met_ytd: string;
  deductible_remaining: string;
  applied_to_deductible: string;
  balance_after_deductible: string;
  coinsurance_pct: string;
  coinsurance_amount: string;
  member_cost_before_cap: string;
  oop_remaining: string;
  oop_cap_triggered: boolean;
  triggering_threshold: "INDIVIDUAL" | "FAMILY" | "N/A";
  member_cost: string;
  prior_auth_required: boolean;
}

interface BaseResult {
  message: string;
  // Present for every variant except a resolve_procedure-only "not on file"
  // (no pipeline run, so nothing minted an audit_id) -- see the note on
  // RateNotFoundResult.
  audit_id: string | null;
}

export interface MemberNotFoundResult extends BaseResult {
  response_type: "MEMBER_NOT_FOUND";
  member_id: string;
}

export interface TermedMemberResult extends BaseResult {
  response_type: "TERMED_BLOCK";
  eligibility: EligibilityResult;
}

export interface ExclusionResult extends BaseResult {
  response_type: "EXCLUSION";
  eligibility: EligibilityResult;
  cpt_code: string;
  common_name: string | null;
  plan_id: string;
}

export interface RateNotFoundResult extends BaseResult {
  response_type: "RATE_NOT_FOUND";
  // eligibility/audit_id are present when caught inside estimate_member_cost
  // (a matched-but-unpriced code, e.g. S8092 on Silver/Gold) but absent when
  // caught earlier by resolve_procedure alone (a code never on the sheet at
  // all, e.g. Cardiac CT) -- the pipeline never ran, so there's no
  // eligibility lookup or audit_id from that stage. Both cases render the
  // same banner regardless (see ResultPanel / RateNotFoundBanner).
  eligibility: EligibilityResult | null;
  procedure_query: string;
}

export interface PreventiveZeroCostResult extends BaseResult {
  response_type: "PREVENTIVE_ZERO_COST";
  eligibility: EligibilityResult;
  cpt_code: string;
  common_name: string;
  member_cost: "0.00";
}

export interface StandardCostResult extends BaseResult {
  response_type: "STANDARD_COST";
  eligibility: EligibilityResult;
  procedure: {
    query: string;
    status: "MATCHED" | "NEEDS_CLARIFICATION" | "NOT_ON_FILE";
    cpt_code: string | null;
    common_name: string | null;
    negotiated_rate: string | null;
  };
  breakdown: CostBreakdown;
}

export interface NeedsClarificationResult extends BaseResult {
  response_type: "NEEDS_CLARIFICATION";
  clarifying_question: string;
  candidates: { cpt_code: string; common_name: string; score: number }[];
}

export type CostEstimateResult =
  | MemberNotFoundResult
  | TermedMemberResult
  | ExclusionResult
  | RateNotFoundResult
  | PreventiveZeroCostResult
  | StandardCostResult
  | NeedsClarificationResult;

export interface QueryResponse {
  message: string;
  result: CostEstimateResult | null;
  audit_id: string | null;
  guardrail_triggered: boolean;
  session_state: {
    session_id: string;
    member_id: string | null;
    last_activity: number;
  };
}
