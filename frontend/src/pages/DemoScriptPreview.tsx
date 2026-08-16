// Fixture-driven preview of the demo-script cases and the Story 6 / Story 7
// regression cases from evals/demo_scripts.yaml, reachable at /?preview=demo.
// Companion to DateOfServicePreview (/?preview), which covers the
// date-of-service outcomes and the prior-auth banner.
//
// Nothing factual is typed in this file. Questions, member ids and dates come
// from evals/demo_scripts.yaml; names, plans, rates and every dollar figure
// come from db/seed through the real calculator. Both arrive via the
// generated src/fixtures/previewPanes.json, which
// tests/unit/test_preview_fixtures.py re-derives and compares on every CI
// run -- so these panes cannot quietly disagree with either the engine or
// the cases they claim to depict.
//
// What IS written here: response message text, which pipeline/estimate.py
// and shared/messages.py own and this file mirrors by hand for MVP1 (the
// same arrangement types.ts documents), and audit ids, which are opaque.
import { PreviewPane, ROW } from "../components/PreviewPane";
import { clarifying, eligibilityOf, pane, priced } from "../fixtures/panes";
import type { CostEstimateResult } from "../types";

// Every priced demo case renders the same way -- only the member, the code
// and the arithmetic differ, and all three are generated.
function standardCost(id: string, auditId: string): CostEstimateResult {
  const { member, procedure, breakdown } = priced(id);
  return {
    response_type: "STANDARD_COST",
    eligibility: eligibilityOf(id),
    plan_display_name: member.plan_display_name,
    procedure: {
      query: procedure.common_name,
      status: "MATCHED",
      cpt_code: procedure.cpt_code,
      common_name: procedure.common_name,
      negotiated_rate: procedure.negotiated_rate,
    },
    breakdown,
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
  eligibility: eligibilityOf("demo-4-termed-block"),
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

// --- Story 6: two different regulatory facts, two different screens -------
//
// Same CPT (S8092, which has a NULL negotiated_rate AND is excluded on
// Bronze) asked of two members on different plans. Bronze must say "not a
// covered benefit"; Silver must say "no rate on file". Dana's requirement is
// that these never look the same, so they are shown adjacently -- the only
// arrangement in which "visually distinct" is actually checkable.

// Wording from pipeline/estimate.py's ExclusionResult branch.
const exclusion: CostEstimateResult = {
  response_type: "EXCLUSION",
  eligibility: eligibilityOf("exclusion-bronze"),
  cpt_code: "S8092",
  common_name: "Acupuncture",
  plan_id: pane("exclusion-bronze").member.plan_id,
  message:
    "This procedure (S8092 -- Acupuncture) is excluded from Meridian Bronze 2026. It is " +
    "not a covered benefit. Do not quote a cost.",
  audit_id: "6a3f92d4-8c17-4e05-b6a8-2f9d41c73b8e",
};

// Same code, different plan. Caught inside estimate_member_cost rather than
// by resolve_procedure, so unlike demo_5 this one DOES carry an eligibility
// block and an audit id. Wording from
// shared/messages.py::rate_not_found_message.
const rateNotFound: CostEstimateResult = {
  response_type: "RATE_NOT_FOUND",
  eligibility: eligibilityOf("rate-not-found-silver"),
  procedure_query: "acupuncture",
  message:
    "We don't have a negotiated rate on file for acupuncture. Do not estimate. Please " +
    "transfer to Member Services supervisor or advise the member we'll call back with a " +
    "confirmed cost.",
  audit_id: "7b4a03e5-9d28-4f16-a719-3e0c52d84c9f",
};

// Preventive short-circuits before accumulators are read at all, which is
// why it carries a flat $0 and no breakdown. Wording from
// pipeline/estimate.py's preventive branch.
const preventive: CostEstimateResult = {
  response_type: "PREVENTIVE_ZERO_COST",
  eligibility: eligibilityOf("preventive-zero-cost"),
  cpt_code: "45380",
  common_name: "Colonoscopy, Preventive (Screening)",
  date_of_service: null,
  member_cost: "0.00",
  message:
    "Member owes $0. Colonoscopy, Preventive (Screening) (45380) is covered at 100% as a " +
    "preventive benefit under Meridian Silver 2026. No deductible or coinsurance applies.",
  audit_id: "8c5b14f6-0e39-4a27-b82a-4f1d63e95da0",
};

// The only pane whose result is a question rather than an answer. Nothing is
// priced and no procedure is resolved, so there is no eligibility block and no
// audit id -- the pipeline never ran. Both the question text and the candidate
// list are generated, because rate_matcher interpolates the CSR's own words
// into the question and the candidates are whatever the seeded rate sheet
// actually ties on.
const clarifyAmbiguousMri: CostEstimateResult = {
  response_type: "NEEDS_CLARIFICATION",
  clarifying_question: clarifying("clarify-ambiguous-mri").clarification.clarifying_question,
  candidates: clarifying("clarify-ambiguous-mri").clarification.candidates,
  message: "",
  audit_id: null,
};

export function DemoScriptPreview() {
  return (
    <div className="query-page" style={{ maxWidth: 1100 }}>
      <h1>CSRSupport</h1>
      <p className="subtitle">
        Demo script cases 1&ndash;5 and the Story 6 regression pair &mdash; questions from
        evals/demo_scripts.yaml, figures from the real calculator over db/seed
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
          title="Demo 5 — procedure never on the rate sheet"
          ask={pane("demo-5-honest-miss")}
          result={demo5}
        />
      </div>

      <div style={ROW}>
        <PreviewPane
          id="exclusion-bronze"
          title="Story 6 — S8092 on Bronze: excluded"
          ask={pane("exclusion-bronze")}
          result={exclusion}
        />
        <PreviewPane
          id="rate-not-found-silver"
          title="Story 6 — same S8092 on Silver: no rate"
          ask={pane("rate-not-found-silver")}
          result={rateNotFound}
        />
      </div>

      <div style={ROW}>
        <PreviewPane
          id="preventive-zero-cost"
          title="Preventive — covered at 100%, no accumulators read"
          ask={pane("preventive-zero-cost")}
          result={preventive}
        />
        <PreviewPane
          id="clarify-ambiguous-mri"
          title="Ambiguous procedure — asks instead of choosing"
          ask={pane("clarify-ambiguous-mri")}
          result={clarifyAmbiguousMri}
        />
      </div>
    </div>
  );
}
