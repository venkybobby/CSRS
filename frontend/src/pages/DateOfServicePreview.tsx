// Fixture-driven preview of every date-of-service outcome plus the
// prior-auth banner, reachable at /?preview. Exists because these screens
// are otherwise hard to see: they need a live agent AND a member whose
// coverage ends within the quotable window.
//
// Companion page: DemoScriptPreview (/?preview=demo) covers demo-script
// cases 1-5.
//
// Nothing factual is typed in this file -- see DemoScriptPreview's header
// for why. Questions, members and dates come from evals/demo_scripts.yaml
// and the figures from db/seed through the real calculator, both via the
// generated src/fixtures/previewPanes.json.
//
// Dates are each case's pinned `today` rather than the real clock, for the
// reason demo_scripts.yaml gives: these outcomes are positions on a calendar
// (M1010's coverage ends 2026-08-31, the plan year ends 2026-12-31), so a
// floating today would silently change what the screenshot demonstrates.
import { PreviewPane, ROW } from "../components/PreviewPane";
import { pane, priced } from "../fixtures/panes";
import type { CostEstimateResult, EligibilityResult } from "../types";

function eligibility(id: string, overrides: Partial<EligibilityResult> = {}): EligibilityResult {
  const { member_id, priced: p } = priced(id);
  return {
    member_id,
    found: true,
    name: p.member_name,
    plan_id: p.plan_id,
    tier: p.tier,
    status: "ACTIVE",
    coverage_start: p.coverage_start,
    coverage_end: p.coverage_end,
    warning: null,
    evaluated_as_of: null,
    ...overrides,
  };
}

// dos_dated_yes_inside_coverage. M1010's seeded accumulators are all $0.00,
// so the whole $1,150 rate lands on an untouched deductible and no
// coinsurance applies -- the figure comes from the calculator, not from here.
const datedYes: CostEstimateResult = {
  response_type: "STANDARD_COST",
  eligibility: eligibility("dated-yes", {
    warning:
      "Coverage ends 2026-08-31 -- date of service 2026-08-20 falls within the coverage period",
    evaluated_as_of: "2026-08-20",
  }),
  plan_display_name: priced("dated-yes").priced.plan_display_name,
  procedure: {
    query: "MRI on his knee",
    status: "MATCHED",
    cpt_code: priced("dated-yes").priced.cpt_code,
    common_name: priced("dated-yes").priced.common_name,
    negotiated_rate: priced("dated-yes").priced.negotiated_rate,
  },
  breakdown: priced("dated-yes").priced.breakdown,
  date_of_service: "2026-08-20",
  message: "",
  audit_id: "a3f1c8e2-5d94-4b17-9e30-7c2a1f6b8d45",
};

// dos_dated_no_after_coverage_ends -- same member, same question, same day.
// Only the date of service differs. Wording from
// shared/messages.py::coverage_ended_before_dos_message.
const datedNo: CostEstimateResult = {
  response_type: "NOT_ELIGIBLE_ON_DOS",
  eligibility: eligibility("dated-yes", {
    status: "NOT_COVERED_ON_DOS",
    evaluated_as_of: "2026-09-15",
  }),
  date_of_service: "2026-09-15",
  reason: "COVERAGE_ENDED",
  message:
    "George Ellery's coverage ends 2026-08-31, so they are not eligible on the requested " +
    "date of service 2026-09-15. Do not quote a cost.",
  audit_id: "b7e2d4a9-1c68-4f35-8a02-9d5e3b1c7f28",
};

// dos_plan_year_boundary_is_a_refusal -- M1002 asked on 2026-11-15. The
// member is eligible on the date; we simply cannot price it, so this variant
// carries no dollar field and needs no generated breakdown. Wording from
// shared/messages.py::plan_year_boundary_message.
const planYear: CostEstimateResult = {
  response_type: "PLAN_YEAR_BOUNDARY",
  eligibility: eligibility("prior-auth", { evaluated_as_of: "2027-01-20" }),
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
// member_id rather than an EligibilityResult. Wording from
// shared/messages.py::date_of_service_in_past_message.
const pastDate: CostEstimateResult = {
  response_type: "DATE_OF_SERVICE_INVALID",
  member_id: pane("past-date").member_id,
  date_of_service: "2026-07-20",
  reason: "IN_PAST",
  message:
    "Date of service 2026-07-20 is in the past (today is 2026-08-13). This tool estimates " +
    "upcoming procedures only -- a past date of service is a claims question, not an " +
    "estimate. Route to Claims; do not estimate.",
  audit_id: "d1b8e5c3-2f74-4a96-8e51-3c7d9b2a6e04",
};

// No eval case -- this pane exists to show Story 4's prior-auth wording,
// which no demo-script or date-of-service case happens to trigger. See
// STANDALONE_PANES in scripts/generate_preview_fixtures.py for why it is
// M1002 and MRI Brain.
const priorAuth: CostEstimateResult = {
  response_type: "STANDARD_COST",
  eligibility: eligibility("prior-auth", { evaluated_as_of: "2026-08-20" }),
  plan_display_name: priced("prior-auth").priced.plan_display_name,
  procedure: {
    query: "MRI brain",
    status: "MATCHED",
    cpt_code: priced("prior-auth").priced.cpt_code,
    common_name: priced("prior-auth").priced.common_name,
    negotiated_rate: priced("prior-auth").priced.negotiated_rate,
  },
  breakdown: priced("prior-auth").priced.breakdown,
  date_of_service: "2026-08-20",
  message: "",
  audit_id: "e5c71a08-3b26-4f89-a743-1d6b90c2e857",
};

export function DateOfServicePreview() {
  return (
    <div className="query-page" style={{ maxWidth: 1100 }}>
      <h1>CSRSupport</h1>
      <p className="subtitle">
        Date-of-service outcomes &mdash; questions from evals/demo_scripts.yaml, figures from the
        real calculator over db/seed
      </p>

      <div style={ROW}>
        <PreviewPane
          id="dated-yes"
          title="Dated yes — date inside the coverage period"
          ask={pane("dated-yes")}
          result={datedYes}
        />
        <PreviewPane
          id="dated-no"
          title="Dated no — date after coverage ends"
          ask={pane("dated-no")}
          result={datedNo}
        />
      </div>

      <div style={ROW}>
        <PreviewPane
          id="plan-year-boundary"
          title="Plan-year hard stop — eligible but unpriceable"
          ask={pane("plan-year-boundary")}
          result={planYear}
        />
        <PreviewPane
          id="past-date"
          title="Past date — routed to Claims"
          ask={pane("past-date")}
          result={pastDate}
        />
      </div>

      <div style={ROW}>
        <PreviewPane
          id="prior-auth"
          title="Prior authorization required — Story 4 wording"
          ask={pane("prior-auth")}
          result={priorAuth}
        />
      </div>
    </div>
  );
}
