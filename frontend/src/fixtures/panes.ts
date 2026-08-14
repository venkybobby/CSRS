import raw from "./previewPanes.json";
import type { CostBreakdown } from "../types";

// Typed view over previewPanes.json, which is GENERATED -- do not hand-edit
// either file. scripts/generate_preview_fixtures.py builds the JSON from
// db/seed through the real calculator and from evals/demo_scripts.yaml, and
// tests/unit/test_preview_fixtures.py fails the build if the committed copy
// drifts from a fresh generation.
//
// The cast below is unchecked by TypeScript, which cannot see inside a .json
// import -- but it is not unchecked overall: that test asserts the exact
// shape and contents this interface describes, against the engine itself.

export interface PricedPane {
  member_name: string;
  plan_id: string;
  plan_display_name: string;
  tier: "INDIVIDUAL" | "FAMILY";
  coverage_start: string;
  coverage_end: string | null;
  cpt_code: string;
  common_name: string;
  negotiated_rate: string;
  breakdown: CostBreakdown;
}

export interface PreviewPaneData {
  // null for a pane no eval case covers; rendered as an explicit
  // "no eval case" stamp rather than an empty slot.
  case_id: string | null;
  question: string;
  member_id: string;
  date_of_service: string | null;
  asked_on: string | null;
  // null for refusals -- the eligibility check or the rate lookup blocks
  // before anything is priced, so there is no breakdown to show.
  priced: PricedPane | null;
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

// Same, for the panes that must carry a breakdown.
export function priced(id: string): PreviewPaneData & { priced: PricedPane } {
  const found = pane(id);
  if (!found.priced) {
    throw new Error(`pane "${id}" has no priced breakdown; it is a refusal case`);
  }
  return { ...found, priced: found.priced };
}
