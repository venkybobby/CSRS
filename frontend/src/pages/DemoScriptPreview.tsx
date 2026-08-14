// Fixture-driven preview of the five demo-script cases from
// evals/demo_scripts.yaml, reachable at /?preview=demo. Companion to
// DateOfServicePreview (/?preview), which covers the date-of-service
// outcomes and the prior-auth banner.
//
// Every dollar figure below was produced by running the real calculator
// (csr_agent.calculator.individual / .family) against db/seed, not computed
// by hand, and each one matches the expected_fields already pinned in
// evals/demo_scripts.yaml. Message strings come from shared/messages.py's
// builders. Fixtures that merely LOOK right are worse than no fixtures --
// they turn a screenshot into a plausible-looking claim about behavior the
// engine may not have.
import { PreviewPane, ROW } from "../components/PreviewPane";
import type { CostEstimateResult, EligibilityResult } from "../types";

function member(
  memberId: string,
  name: string,
  planId: string,
  tier: "INDIVIDUAL" | "FAMILY",
): EligibilityResult {
  return {
    member_id: memberId,
    found: true,
    name,
    plan_id: planId,
    tier,
    status: "ACTIVE",
    coverage_start: "2026-01-01",
    coverage_end: null,
    warning: null,
    evaluated_as_of: null,
  };
}

// demo_1 -- partial deductible then coinsurance. The everyday case: the
// deductible absorbs part of the rate and coinsurance applies to the rest.
const demo1: CostEstimateResult = {
  response_type: "STANDARD_COST",
  eligibility: member("M1002", "Robert Chen", "MER-SLV-2026", "INDIVIDUAL"),
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
  date_of_service: null,
  message: "",
  audit_id: "1f0a7c94-6d21-4e38-b5a9-2c8e04f7b613",
};

// demo_2 -- the OOP cap binds. $1,860 of coinsurance is owed on paper but
// only $150 of out-of-pocket room remains, so the member owes $150. The
// capped row is the whole point of the screenshot.
const demo2: CostEstimateResult = {
  response_type: "STANDARD_COST",
  eligibility: member("M1004", "James Whitaker", "MER-BRZ-2026", "INDIVIDUAL"),
  plan_display_name: "Meridian Bronze 2026",
  procedure: {
    query: "knee surgery",
    status: "MATCHED",
    cpt_code: "29881",
    common_name: "Knee Arthroscopy/Surgery",
    negotiated_rate: "6200.00",
  },
  breakdown: {
    negotiated_rate: "6200.00",
    deductible_individual: "3000.00",
    deductible_met_ytd: "3000.00",
    deductible_remaining: "0.00",
    applied_to_deductible: "0.00",
    balance_after_deductible: "6200.00",
    coinsurance_pct: "0.30",
    coinsurance_amount: "1860.00",
    member_cost_before_cap: "1860.00",
    oop_remaining: "150.00",
    oop_cap_triggered: true,
    triggering_threshold: "N/A",
    member_cost: "150.00",
    prior_auth_required: false,
  },
  date_of_service: null,
  message: "",
  audit_id: "2b6d38e1-90fc-4a75-8e42-7d1c5b3f0a29",
};

// demo_3a / demo_3b -- same family, same plan, same procedure, same $1,860
// total. The spec warns that identical outputs would indicate a broken
// per-member accumulator lookup; what must differ is the OOP position, not
// the dollar total (see the note in evals/demo_scripts.yaml and
// tests/unit/test_calculator_family.py). Shot side by side precisely so the
// differing rows are visible next to the matching one.
const demo3a: CostEstimateResult = {
  response_type: "STANDARD_COST",
  eligibility: member("M1006", "Miguel Santos", "MER-BRZ-2026", "FAMILY"),
  plan_display_name: "Meridian Bronze 2026",
  procedure: {
    query: "knee surgery",
    status: "MATCHED",
    cpt_code: "29881",
    common_name: "Knee Arthroscopy/Surgery",
    negotiated_rate: "6200.00",
  },
  breakdown: {
    negotiated_rate: "6200.00",
    deductible_individual: "3000.00",
    deductible_met_ytd: "3000.00",
    deductible_remaining: "0.00",
    applied_to_deductible: "0.00",
    balance_after_deductible: "6200.00",
    coinsurance_pct: "0.30",
    coinsurance_amount: "1860.00",
    member_cost_before_cap: "1860.00",
    oop_remaining: "3100.00",
    oop_cap_triggered: false,
    triggering_threshold: "INDIVIDUAL",
    member_cost: "1860.00",
    prior_auth_required: false,
  },
  date_of_service: null,
  message: "",
  audit_id: "3c9e51f7-4a08-4b62-9d17-6e2f8a0c4d51",
};

const demo3b: CostEstimateResult = {
  response_type: "STANDARD_COST",
  eligibility: member("M1007", "Hannah Santos", "MER-BRZ-2026", "FAMILY"),
  plan_display_name: "Meridian Bronze 2026",
  procedure: {
    query: "knee surgery",
    status: "MATCHED",
    cpt_code: "29881",
    common_name: "Knee Arthroscopy/Surgery",
    negotiated_rate: "6200.00",
  },
  breakdown: {
    negotiated_rate: "6200.00",
    deductible_individual: "3000.00",
    // $400, not $3,000: this member never met their individual deductible.
    // The family threshold is what moved them into coinsurance.
    deductible_met_ytd: "400.00",
    deductible_remaining: "0.00",
    applied_to_deductible: "0.00",
    balance_after_deductible: "6200.00",
    coinsurance_pct: "0.30",
    coinsurance_amount: "1860.00",
    member_cost_before_cap: "1860.00",
    oop_remaining: "6100.00",
    oop_cap_triggered: false,
    triggering_threshold: "FAMILY",
    member_cost: "1860.00",
    prior_auth_required: false,
  },
  date_of_service: null,
  message: "",
  audit_id: "4d176208-b3ec-4f95-a8d0-1b5c7e9f2a64",
};

// demo_4 -- termed member. check_eligibility blocks before any procedure
// lookup runs, so there is no CPT and no breakdown to show.
const demo4: CostEstimateResult = {
  response_type: "TERMED_BLOCK",
  eligibility: {
    member_id: "M1005",
    found: true,
    name: "Priya Raman",
    plan_id: "MER-SLV-2026",
    tier: "INDIVIDUAL",
    status: "TERMED",
    coverage_start: "2026-01-01",
    coverage_end: "2026-05-31",
    warning: null,
    evaluated_as_of: null,
  },
  message: "Priya Raman is not eligible as of 2026-05-31. Do not quote a cost.",
  audit_id: "5e28734f-c1a9-4d06-b73e-8f4a2c6d1b95",
};

// demo_5 -- the honest miss. Cardiac CT is not on the rate sheet at all, so
// resolve_procedure returns NOT_ON_FILE and the pipeline never runs: hence
// eligibility null and audit_id null, per the note in types.ts.
const demo5: CostEstimateResult = {
  response_type: "RATE_NOT_FOUND",
  eligibility: null,
  procedure_query: "cardiac CT",
  message:
    "We don't have a negotiated rate on file for cardiac CT. Do not estimate. Please " +
    "transfer to Member Services supervisor or advise the member we'll call back with a " +
    "confirmed cost.",
  audit_id: null,
};

export function DemoScriptPreview() {
  return (
    <div className="query-page" style={{ maxWidth: 1100 }}>
      <h1>CSRSupport</h1>
      <p className="subtitle">
        Demo script cases 1&ndash;5 &mdash; fixtures from db/seed, figures from the real calculator
      </p>

      <div style={ROW}>
        <PreviewPane
          id="demo-1-partial-deductible"
          title="Demo 1 — partial deductible + coinsurance"
          ask={{
            caseId: "demo_1_partial_deductible_and_coinsurance",
            memberId: "M1002",
            question: "M1002 wants an MRI on his knee, what does he owe?",
          }}
          result={demo1}
        />
        <PreviewPane
          id="demo-2-oop-cap"
          title="Demo 2 — out-of-pocket cap binds"
          ask={{
            caseId: "demo_2_oop_max_binding",
            memberId: "M1004",
            question: "What's James Whitaker M1004 looking at for knee surgery?",
          }}
          result={demo2}
        />
      </div>

      {/* One question, two members, two different answers -- the ask card is
          identical on both panes on purpose, because that is exactly what
          the spec's warning is about: same wording in, and anything that
          collapsed these onto one accumulator row would produce a matching
          OOP position rather than the differing one shown here. */}
      <div style={ROW}>
        <PreviewPane
          id="demo-3a-family-individual-threshold"
          title="Demo 3a — same $1,860, individual threshold"
          ask={{
            caseId: "demo_3a_embedded_family_m1006",
            memberId: "M1006",
            question: "Same question for M1007 and M1006 -- knee surgery",
          }}
          result={demo3a}
        />
        <PreviewPane
          id="demo-3b-family-family-threshold"
          title="Demo 3b — same $1,860, family threshold"
          ask={{
            caseId: "demo_3b_embedded_family_m1007",
            memberId: "M1007",
            question: "Same question for M1007 and M1006 -- knee surgery",
          }}
          result={demo3b}
        />
      </div>

      <div style={ROW}>
        <PreviewPane
          id="demo-4-termed-block"
          title="Demo 4 — termed member, blocked"
          ask={{
            caseId: "demo_4_termed_member_block",
            memberId: "M1005",
            question: "M1005 -- anything, what do they owe?",
          }}
          result={demo4}
        />
        <PreviewPane
          id="demo-5-honest-miss"
          title="Demo 5 — no negotiated rate on file"
          ask={{
            caseId: "demo_5_honest_miss",
            memberId: "M1003",
            question: "Cardiac CT for M1003",
          }}
          result={demo5}
        />
      </div>
    </div>
  );
}
