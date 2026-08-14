// Fixture-driven preview of every date-of-service outcome plus the
// prior-auth banner, reachable at /?preview. Exists because these screens
// are otherwise hard to see: they need a live agent AND a member whose
// coverage ends within the quotable window.
//
// Companion page: DemoScriptPreview (/?preview=demo) covers demo-script
// cases 1-5.
//
// Each pane is a faithful rendering of a case in evals/demo_scripts.yaml --
// same member, same question wording, same pinned `today`, same date of
// service -- and every dollar figure was produced by running
// csr_agent.calculator.individual against db/seed rather than written by
// hand. Both properties matter more than they look:
//
//   * The pane states the member id next to the numbers. A fixture carrying
//     one member's accumulators under another member's name is a visible
//     contradiction the moment the ask is shown alongside the answer.
//   * Dates are pinned to each case's `today` rather than tracking the real
//     clock, for the reason demo_scripts.yaml gives: these outcomes are
//     positions on a calendar (M1010's coverage ends 2026-08-31, the plan
//     year ends 2026-12-31), so a floating today would silently change what
//     the screenshot demonstrates.
import { PreviewPane, ROW } from "../components/PreviewPane";
import type { CostEstimateResult, EligibilityResult } from "../types";

// M1010: the only seeded member whose coverage ends inside the quotable
// window, which is what makes the dated-yes/dated-no pair possible at all.
const ellery: EligibilityResult = {
  member_id: "M1010",
  found: true,
  name: "George Ellery",
  plan_id: "MER-SLV-2026",
  tier: "INDIVIDUAL",
  status: "ACTIVE",
  coverage_start: "2026-01-01",
  coverage_end: "2026-08-31",
  warning: null,
  evaluated_as_of: null,
};

// M1002: used by the plan-year and past-date cases in demo_scripts.yaml, and
// by the prior-auth pane below. Open-ended coverage, so no warning banner.
const chen: EligibilityResult = {
  member_id: "M1002",
  found: true,
  name: "Robert Chen",
  plan_id: "MER-SLV-2026",
  tier: "INDIVIDUAL",
  status: "ACTIVE",
  coverage_start: "2026-01-01",
  coverage_end: null,
  warning: null,
  evaluated_as_of: null,
};

// dos_dated_yes_inside_coverage. $1,150, not the $470 this fixture used to
// claim: M1010's seeded accumulators are all $0.00, so the whole $1,150 rate
// lands on the unmet deductible and no coinsurance applies. The old figures
// were M1002's accumulator profile ($1,200 met) printed under George
// Ellery's name.
const datedYes: CostEstimateResult = {
  response_type: "STANDARD_COST",
  eligibility: {
    ...ellery,
    warning:
      "Coverage ends 2026-08-31 -- date of service 2026-08-20 falls within the coverage period",
    evaluated_as_of: "2026-08-20",
  },
  plan_display_name: "Meridian Silver 2026",
  procedure: {
    query: "MRI on his knee",
    status: "MATCHED",
    cpt_code: "73721",
    common_name: "MRI Knee",
    negotiated_rate: "1150.00",
  },
  breakdown: {
    negotiated_rate: "1150.00",
    deductible_individual: "1500.00",
    deductible_met_ytd: "0.00",
    deductible_remaining: "1500.00",
    applied_to_deductible: "1150.00",
    balance_after_deductible: "0.00",
    coinsurance_pct: "0.20",
    coinsurance_amount: "0.00",
    member_cost_before_cap: "1150.00",
    oop_remaining: "4000.00",
    oop_cap_triggered: false,
    triggering_threshold: "N/A",
    member_cost: "1150.00",
    prior_auth_required: false,
  },
  date_of_service: "2026-08-20",
  message: "",
  audit_id: "a3f1c8e2-5d94-4b17-9e30-7c2a1f6b8d45",
};

// dos_dated_no_after_coverage_ends -- same member, same question, same day.
// Only the date of service differs.
const datedNo: CostEstimateResult = {
  response_type: "NOT_ELIGIBLE_ON_DOS",
  eligibility: { ...ellery, status: "NOT_COVERED_ON_DOS", evaluated_as_of: "2026-09-15" },
  date_of_service: "2026-09-15",
  reason: "COVERAGE_ENDED",
  message:
    "George Ellery's coverage ends 2026-08-31, so they are not eligible on the requested " +
    "date of service 2026-09-15. Do not quote a cost.",
  audit_id: "b7e2d4a9-1c68-4f35-8a02-9d5e3b1c7f28",
};

// dos_plan_year_boundary_is_a_refusal -- M1002 asked on 2026-11-15, per the
// eval case. The member is eligible on the date; we simply cannot price it.
const planYear: CostEstimateResult = {
  response_type: "PLAN_YEAR_BOUNDARY",
  eligibility: { ...chen, evaluated_as_of: "2027-01-20" },
  date_of_service: "2027-01-20",
  plan_year_end: "2026-12-31",
  message:
    "Date of service 2027-01-20 falls in the next plan year (the current plan year ends " +
    "2026-12-31). Robert Chen's deductible and out-of-pocket balances reset January 1, and " +
    "the plan on file (MER-SLV-2026) covers the current year only -- next year's terms are " +
    "not on file. Do not quote a cost for this date; advise the member we can estimate once " +
    "the new plan year begins.",
  audit_id: "c9a4f2b1-7e35-4d68-b120-4f8c2e9a1d63",
};

// dos_in_past_is_a_claims_question -- refused on the shape of the request,
// before the member is even looked up, which is why this variant carries a
// member_id rather than an EligibilityResult.
const pastDate: CostEstimateResult = {
  response_type: "DATE_OF_SERVICE_INVALID",
  member_id: "M1002",
  date_of_service: "2026-07-20",
  reason: "IN_PAST",
  message:
    "Date of service 2026-07-20 is in the past (today is 2026-08-13). This tool estimates " +
    "upcoming procedures only -- a past date of service is a claims question, not an " +
    "estimate. Route to Claims; do not estimate.",
  audit_id: "d1b8e5c3-2f74-4a96-8e51-3c7d9b2a6e04",
};

// No eval case -- this pane exists to show Story 4's prior-auth wording,
// which no demo-script or date-of-service case happens to trigger.
//
// M1002 with MRI Brain rather than the MRI Knee above, for two independent
// reasons: 73721 is not prior-auth under Meridian Silver (db/seed/plans.json
// lists only 70551 and 72148), and M1002's real accumulators ($1,200 of
// $1,500 met) are what make this a partial-deductible breakdown worth
// looking at instead of a single deductible row.
const priorAuth: CostEstimateResult = {
  response_type: "STANDARD_COST",
  eligibility: { ...chen, evaluated_as_of: "2026-08-20" },
  plan_display_name: "Meridian Silver 2026",
  procedure: {
    query: "MRI brain",
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
        Date-of-service outcomes &mdash; fixtures from db/seed, cases from evals/demo_scripts.yaml
      </p>

      <div style={ROW}>
        <PreviewPane
          id="dated-yes"
          title="Dated yes — date inside the coverage period"
          ask={{
            caseId: "dos_dated_yes_inside_coverage",
            memberId: "M1010",
            question: "MRI on his knee for M1010",
            dateOfService: "2026-08-20",
            askedOn: "2026-08-13",
          }}
          result={datedYes}
        />
        <PreviewPane
          id="dated-no"
          title="Dated no — date after coverage ends"
          ask={{
            caseId: "dos_dated_no_after_coverage_ends",
            memberId: "M1010",
            question: "MRI on his knee for M1010",
            dateOfService: "2026-09-15",
            askedOn: "2026-08-13",
          }}
          result={datedNo}
        />
      </div>

      <div style={ROW}>
        <PreviewPane
          id="plan-year-boundary"
          title="Plan-year hard stop — eligible but unpriceable"
          ask={{
            caseId: "dos_plan_year_boundary_is_a_refusal",
            memberId: "M1002",
            question: "MRI on his knee for M1002",
            dateOfService: "2027-01-20",
            askedOn: "2026-11-15",
          }}
          result={planYear}
        />
        <PreviewPane
          id="past-date"
          title="Past date — routed to Claims"
          ask={{
            caseId: "dos_in_past_is_a_claims_question",
            memberId: "M1002",
            question: "MRI on his knee for M1002",
            dateOfService: "2026-07-20",
            askedOn: "2026-08-13",
          }}
          result={pastDate}
        />
      </div>

      <div style={ROW}>
        <PreviewPane
          id="prior-auth"
          title="Prior authorization required — Story 4 wording"
          ask={{
            memberId: "M1002",
            question: "MRI brain for M1002",
            dateOfService: "2026-08-20",
            askedOn: "2026-08-13",
          }}
          result={priorAuth}
        />
      </div>
    </div>
  );
}
