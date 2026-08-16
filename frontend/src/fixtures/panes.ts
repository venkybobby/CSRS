import raw from "./previewPanes.json";
import type { CostBreakdown, EligibilityResult } from "../types";

// Typed view over previewPanes.json, which is GENERATED -- do not hand-edit
// either file. scripts/generate_preview_fixtures.py builds the JSON from
// db/seed through the real calculator and from evals/demo_scripts.yaml, and
// tests/unit/test_preview_fixtures.py fails the build if the committed copy
// drifts from a fresh generation.
//
// The cast below is unchecked by TypeScript, which cannot see inside a .json
// import -- but it is not unchecked overall: that test asserts the exact
// shape and contents this interface describes, against the engine itself.

export interface PaneMember {
  name: string;
  plan_id: string;
  plan_display_name: string;
  tier: "INDIVIDUAL" | "FAMILY";
  status: "ACTIVE" | "TERMED";
  coverage_start: string;
  coverage_end: string | null;
}

export interface PaneProcedure {
  cpt_code: string;
  common_name: string;
  // null for S8092, which is on the rate sheet by name but carries no price
  // -- the condition Story 6's rate-not-found case turns on.
  negotiated_rate: string | null;
}

export interface PaneCandidate {
  cpt_code: string;
  common_name: string;
  // Carried because the API type does, though nothing renders it.
  score: number;
}

// Present only on a NEEDS_CLARIFICATION pane. The question text is generated
// rather than mirrored by hand like the other response prose: rate_matcher
// interpolates the CSR's own words into it, and which of its two phrasings
// fires depends on whether the query tied above the match threshold or fell
// below it entirely.
export interface PaneClarification {
  clarifying_question: string;
  candidates: PaneCandidate[];
}

export interface PreviewPaneData {
  // null for a pane no eval case covers; rendered as an explicit
  // "no eval case" stamp rather than an empty slot.
  case_id: string | null;
  question: string;
  member_id: string;
  date_of_service: string | null;
  asked_on: string | null;
  member: PaneMember;
  // null where no code is resolved at all (demo_5's cardiac CT).
  procedure: PaneProcedure | null;
  // Only STANDARD_COST reaches the calculator; every other outcome is a
  // refusal or a flat $0.
  breakdown: CostBreakdown | null;
  // Null on every pane whose result is an answer. Non-null only where the
  // result is a question back to the CSR.
  clarification: PaneClarification | null;
}

const panes = raw as Record<string, PreviewPaneData>;

// Throws rather than returning undefined: a missing pane is a generator/page
// mismatch, and silently rendering an empty card would produce a screenshot
// that looks merely sparse instead of broken.
export function pane(id: string): PreviewPaneData {
  const found = panes[id];
  if (!found) {
    throw new Error(
      `no generated fixture for pane "${id}" -- add it to scripts/generate_preview_fixtures.py ` +
        "and re-run it",
    );
  }
  return found;
}

// Same, for the panes that must carry a breakdown and a resolved procedure.
export function priced(
  id: string,
): PreviewPaneData & { breakdown: CostBreakdown; procedure: PaneProcedure } {
  const found = pane(id);
  if (!found.breakdown || !found.procedure) {
    throw new Error(`pane "${id}" has no priced breakdown; it is a refusal or $0 case`);
  }
  return { ...found, breakdown: found.breakdown, procedure: found.procedure };
}

// Same, for the one pane whose result is a question rather than an answer.
export function clarifying(
  id: string,
): PreviewPaneData & { clarification: PaneClarification } {
  const found = pane(id);
  if (!found.clarification) {
    throw new Error(
      `pane "${id}" has no clarification; it resolved to a procedure instead of asking`,
    );
  }
  return { ...found, clarification: found.clarification };
}

// The eligibility block every result variant carries, built from seed rather
// than restated per pane -- the member's name and plan appearing next to the
// figures is what makes a mismatched fixture visible.
export function eligibilityOf(
  id: string,
  overrides: Partial<EligibilityResult> = {},
): EligibilityResult {
  const { member_id, member } = pane(id);
  return {
    member_id,
    found: true,
    name: member.name,
    plan_id: member.plan_id,
    tier: member.tier,
    status: member.status,
    coverage_start: member.coverage_start,
    coverage_end: member.coverage_end,
    warning: null,
    evaluated_as_of: null,
    ...overrides,
  };
}
