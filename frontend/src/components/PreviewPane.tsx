import type { CSSProperties } from "react";
import type { PreviewPaneData } from "../fixtures/panes";
import type { CostEstimateResult } from "../types";
import { ResultPanel } from "./ResultPanel";

// A row of preview panes. alignItems flex-start matters for the screenshots
// specifically: stretch (the flex default) makes every pane as tall as the
// tallest one in its row, so a per-pane capture of a short card comes out
// padded with dead space below it.
export const ROW: CSSProperties = {
  display: "flex",
  gap: "1.5rem",
  flexWrap: "wrap",
  alignItems: "flex-start",
  marginTop: "1.5rem",
};

// Scaffolding for the fixture preview pages only -- never rendered in the
// real CSR flow, which reaches ResultPanel straight from QueryPage.
//
// `id` becomes a data-capture attribute so scripts/capture_demo_screenshots.py
// can shoot each pane deterministically. Selecting on the rendered heading
// instead would re-break on every copy change, which is exactly the kind of
// change the screenshots exist to record.
//
// `ask` is the generated pane record itself rather than a hand-built prop
// object: retyping those fields at each call site is how the question shown
// above a result drifts from the case the pane claims to depict.
export function PreviewPane({
  id,
  title,
  ask,
  result,
}: {
  id: string;
  title: string;
  ask: PreviewPaneData;
  result: CostEstimateResult;
}) {
  return (
    <div data-capture={id} style={{ flex: "1 1 420px", minWidth: 380 }}>
      <h2
        style={{
          fontSize: "0.9rem",
          textTransform: "uppercase",
          letterSpacing: "0.05em",
          color: "#6b7280",
        }}
      >
        {title}
      </h2>

      <div className="preview-ask">
        <div className="preview-ask-head">
          <span className="preview-ask-label">CSR asked</span>
          {/* Rendered as an explicit "no eval case" rather than left blank:
              an empty slot would read as an id someone forgot to fill in,
              when in fact the pane depicts behavior no eval case covers. */}
          <span className="preview-ask-case">{ask.case_id ?? "no eval case"}</span>
        </div>
        <p className="preview-ask-question">&ldquo;{ask.question}&rdquo;</p>
        <dl className="preview-ask-fields">
          <div>
            <dt>Member ID</dt>
            <dd>{ask.member_id}</dd>
          </div>
          {/* Shown only when the CSR stated one -- the field is optional in
              the real form and must not appear filled in when it wasn't. */}
          {ask.date_of_service && (
            <div>
              <dt>Date of service</dt>
              <dd>{ask.date_of_service}</dd>
            </div>
          )}
          {/* Only the cases whose outcome depends on the calendar pin a
              `today`, so only those show one. */}
          {ask.asked_on && (
            <div>
              <dt>Asked on</dt>
              <dd>{ask.asked_on}</dd>
            </div>
          )}
        </dl>
      </div>

      <span className="preview-ask-arrow" aria-hidden="true">
        ▼
      </span>

      <ResultPanel result={result} />
    </div>
  );
}
