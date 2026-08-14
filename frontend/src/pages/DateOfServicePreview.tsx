// Fixture-driven preview of every date-of-service outcome plus the
// prior-auth banner, reachable at /?preview. Exists because these screens
// are otherwise hard to see: they need a live agent AND a member whose
// coverage ends within the quotable window. Fixtures are taken from db/seed
// (M1010, Meridian Silver 2026).
//
// Companion page: DemoScriptPreview (/?preview=demo) covers demo-script
// cases 1-5.
import { PreviewPane, ROW } from "../components/PreviewPane";
import type { CostEstimateResult, EligibilityResult } from "../types";

// The day these fixtures are asked on. Every date below is positioned
// relative to it -- 2026-08-20 must stay inside both the coverage period and
// the 90-day quoting horizon, and 2026-07-20 must stay in the past -- so
// moving this is a deliberate edit, not a find-and-replace. Kept as one
// constant because the same date is otherwise restated inside the fixture
// message text, where a stale copy is invisible until it reaches a
// screenshot.
const ASKED_ON = "2026-08-14";

const ellery: EligibilityResult = {
  member_id: "M1010",
  found: true,
  name: "George Ellery",
  plan_id: "MER-SLV-2026",
  tier: "INDIVIDUAL",
  status: "ACTIVE",
  coverage_start: "2026-01-01",
  coverage_end: "2026-08-31",
  warning:
    "Coverage ends 2026-08-31 -- date of service 2026-08-20 falls within the coverage period",
  evaluated_as_of: "2026-08-20",
};

const datedYes: CostEstimateResult = {
  response_type: "STANDARD_COST",
  eligibility: ellery,
  plan_display_name: "Meridian Silver 2026",
  procedure: {
    query: "73721",
    status: "MATCHED",
    cpt_code: "73721",
    common_name: "MRI Knee",
    negotiated_rate: "1150.00",
  },
  breakdown: {
    negotiated_rate: "1150.00",
    deductible_individual: "1500.00",
    deductible_met_ytd: "1200.00",
    deductible_remaining: "300.00",
    applied_to_deductible: "300.00",
    balance_after_deductible: "850.00",
    coinsurance_pct: "0.20",
    coinsurance_amount: "170.00",
    member_cost_before_cap: "470.00",
    oop_remaining: "2800.00",
    oop_cap_triggered: false,
    triggering_threshold: "N/A",
    member_cost: "470.00",
    prior_auth_required: false,
  },
  date_of_service: "2026-08-20",
  message: "",
  audit_id: "a3f1c8e2-5d94-4b17-9e30-7c2a1f6b8d45",
};

const datedNo: CostEstimateResult = {
  response_type: "NOT_ELIGIBLE_ON_DOS",
  eligibility: { ...ellery, status: "NOT_COVERED_ON_DOS", warning: null, evaluated_as_of: "2026-09-15" },
  date_of_service: "2026-09-15",
  reason: "COVERAGE_ENDED",
  message:
    "George Ellery's coverage ends 2026-08-31, so they are not eligible on the requested date of service 2026-09-15. Do not quote a cost.",
  audit_id: "b7e2d4a9-1c68-4f35-8a02-9d5e3b1c7f28",
};

const planYear: CostEstimateResult = {
  response_type: "PLAN_YEAR_BOUNDARY",
  eligibility: { ...ellery, coverage_end: null, warning: null, evaluated_as_of: "2027-01-20" },
  date_of_service: "2027-01-20",
  plan_year_end: "2026-12-31",
  message:
    "Date of service 2027-01-20 falls in the next plan year (the current plan year ends 2026-12-31). George Ellery's deductible and out-of-pocket balances reset January 1, and the plan on file (MER-SLV-2026) covers the current year only -- next year's terms are not on file. Do not quote a cost for this date; advise the member we can estimate once the new plan year begins.",
  audit_id: "c9a4f2b1-7e35-4d68-b120-4f8c2e9a1d63",
};

const pastDate: CostEstimateResult = {
  response_type: "DATE_OF_SERVICE_INVALID",
  member_id: "M1010",
  date_of_service: "2026-07-20",
  reason: "IN_PAST",
  message:
    `Date of service 2026-07-20 is in the past (today is ${ASKED_ON}). This tool estimates upcoming procedures only -- a past date of service is a claims question, not an estimate. Route to Claims; do not estimate.`,
  audit_id: "d1b8e5c3-2f74-4a96-8e51-3c7d9b2a6e04",
};

// MRI Brain, not the MRI Knee above: 73721 is genuinely NOT prior-auth under
// Meridian Silver -- db/seed/plans.json lists only 70551 and 72148 -- so
// flipping prior_auth_required on datedYes would have produced a screenshot
// of a determination the engine would never make. Arithmetic follows the
// same accumulator premise as datedYes ($1,200 of $1,500 deductible met):
// $300 to deductible, $1,100 balance, 20% coinsurance = $220, total $520,
// under the $2,800 OOP remaining so no cap.
const priorAuth: CostEstimateResult = {
  response_type: "STANDARD_COST",
  eligibility: ellery,
  plan_display_name: "Meridian Silver 2026",
  procedure: {
    query: "70551",
    status: "MATCHED",
    cpt_code: "70551",
    common_name: "MRI Brain",
    negotiated_rate: "1400.00",
  },
  breakdown: {
    negotiated_rate: "1400.00",
    deductible_individual: "1500.00",
    deductible_met_ytd: "1200.00",
    deductible_remaining: "300.00",
    applied_to_deductible: "300.00",
    balance_after_deductible: "1100.00",
    coinsurance_pct: "0.20",
    coinsurance_amount: "220.00",
    member_cost_before_cap: "520.00",
    oop_remaining: "2800.00",
    oop_cap_triggered: false,
    triggering_threshold: "N/A",
    member_cost: "520.00",
    prior_auth_required: true,
  },
  date_of_service: "2026-08-20",
  message: "",
  audit_id: "e5c71a08-3b26-4f89-a743-1d6b90c2e857",
};

export function DateOfServicePreview() {
  return (
    <div className="query-page" style={{ maxWidth: 1100 }}>
      <h1>CSRSupport</h1>
      <p className="subtitle">
        M1010 George Ellery — coverage 2026-01-01 to 2026-08-31 — asked on {ASKED_ON}
      </p>
      <div style={ROW}>
        <PreviewPane id="dated-yes" title="Date of service 2026-08-20 — dated yes" result={datedYes} />
        <PreviewPane id="dated-no" title="Date of service 2026-09-15 — dated no" result={datedNo} />
      </div>
      <div style={ROW}>
        <PreviewPane id="plan-year-boundary" title="Date of service 2027-01-20 — plan-year hard stop" result={planYear} />
        <PreviewPane id="past-date" title="Date of service 2026-07-20 — past date" result={pastDate} />
      </div>
      <div style={ROW}>
        <PreviewPane id="prior-auth" title="Date of service 2026-08-20 — prior auth required" result={priorAuth} />
      </div>
    </div>
  );
}
