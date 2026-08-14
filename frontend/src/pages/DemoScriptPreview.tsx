// Fixture-driven preview of the five demo-script cases from
// evals/demo_scripts.yaml, reachable at /?preview=demo. Companion to
// DateOfServicePreview (/?preview), which covers the date-of-service
// outcomes and the prior-auth banner.
//
// Nothing factual is typed in this file. Questions, member ids and dates come
// from evals/demo_scripts.yaml; names, plans, rates and every dollar figure
// come from db/seed through the real calculator. Both arrive via the
// generated src/fixtures/previewPanes.json, which
// tests/unit/test_preview_fixtures.py re-derives and compares on every CI
// run -- so these panes cannot quietly disagree with either the engine or
// the cases they claim to depict.
//
// What IS written here: refusal message text (owned by shared/messages.py,
// mirrored by hand for MVP1 like types.ts) and audit ids, which are opaque.
import { PreviewPane, ROW } from "../components/PreviewPane";
import { pane, priced } from "../fixtures/panes";
import type { CostEstimateResult, EligibilityResult } from "../types";

function eligibility(id: string): EligibilityResult {
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
  };
}

// Every priced demo case renders the same way -- only the member, the code
// and the arithmetic differ, and all three are generated.
function standardCost(id: string, auditId: string): CostEstimateResult {
  const { priced: p } = priced(id);
  return {
    response_type: "STANDARD_COST",
    eligibility: eligibility(id),
    plan_display_name: p.plan_display_name,
    procedure: {
      query: p.common_name,
      status: "MATCHED",
      cpt_code: p.cpt_code,
      common_name: p.common_name,
      negotiated_rate: p.negotiated_rate,
    },
    breakdown: p.breakdown,
    date_of_service: null,
    message: "",
    audit_id: auditId,
  };
}

// demo_4 -- check_eligibility blocks before any procedure lookup runs, so
// there is no CPT and no breakdown. Wording from
// shared/messages.py::termed_member_message.
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

// demo_5 -- Cardiac CT is not on the rate sheet at all, so resolve_procedure
// returns NOT_ON_FILE and the pipeline never runs: hence eligibility null and
// audit_id null, per the note in types.ts. Wording from
// shared/messages.py::rate_not_found_message.
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
        Demo script cases 1&ndash;5 &mdash; questions from evals/demo_scripts.yaml, figures from
        the real calculator over db/seed
      </p>

      <div style={ROW}>
        <PreviewPane
          id="demo-1-partial-deductible"
          title="Demo 1 — partial deductible + coinsurance"
          ask={pane("demo-1-partial-deductible")}
          result={standardCost(
            "demo-1-partial-deductible",
            "1f0a7c94-6d21-4e38-b5a9-2c8e04f7b613",
          )}
        />
        <PreviewPane
          id="demo-2-oop-cap"
          title="Demo 2 — out-of-pocket cap binds"
          ask={pane("demo-2-oop-cap")}
          result={standardCost("demo-2-oop-cap", "2b6d38e1-90fc-4a75-8e42-7d1c5b3f0a29")}
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
          ask={pane("demo-3a-family-individual-threshold")}
          result={standardCost(
            "demo-3a-family-individual-threshold",
            "3c9e51f7-4a08-4b62-9d17-6e2f8a0c4d51",
          )}
        />
        <PreviewPane
          id="demo-3b-family-family-threshold"
          title="Demo 3b — same $1,860, family threshold"
          ask={pane("demo-3b-family-family-threshold")}
          result={standardCost(
            "demo-3b-family-family-threshold",
            "4d176208-b3ec-4f95-a8d0-1b5c7e9f2a64",
          )}
        />
      </div>

      <div style={ROW}>
        <PreviewPane
          id="demo-4-termed-block"
          title="Demo 4 — termed member, blocked"
          ask={pane("demo-4-termed-block")}
          result={demo4}
        />
        <PreviewPane
          id="demo-5-honest-miss"
          title="Demo 5 — no negotiated rate on file"
          ask={pane("demo-5-honest-miss")}
          result={demo5}
        />
      </div>
    </div>
  );
}
