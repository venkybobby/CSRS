import type { CSSProperties } from "react";
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

// What the CSR typed, mirroring QueryPage's three form fields.
export interface PreviewAsk {
  // The id of the case in evals/demo_scripts.yaml this pane depicts. Printed
  // on the card so a screenshot can be traced back to the machine-checked
  // case that pins its figures -- otherwise the image is an unfalsifiable
  // claim, and the whole point of these fixtures is that they are not.
  //
  // Optional, and rendered as an explicit "no eval case" when absent rather
  // than left blank: a pane with nothing in this slot would read as one
  // whose id someone forgot to fill in, when in fact it is depicting
  // behavior the eval suite does not cover.
  caseId?: string;
  memberId: string;
  // Verbatim from the eval case's `question`. Paraphrasing here would show a
  // demo of a question no one actually runs.
  question: string;
  // Omitted when the CSR stated no date -- the field is optional in the real
  // form and must not be shown filled in when it wasn't.
  dateOfService?: string;
  // The case's pinned `today`. Only worth showing where the outcome depends
  // on it (a past date, the 90-day horizon, a plan-year boundary).
  askedOn?: string;
}

// Scaffolding for the fixture preview pages only -- never rendered in the
// real CSR flow, which reaches ResultPanel straight from QueryPage.
//
// `id` becomes a data-capture attribute so scripts/capture_demo_screenshots.py
// can shoot each pane deterministically. Selecting on the rendered heading
// instead would re-break on every copy change, which is exactly the kind of
// change the screenshots exist to record.
export function PreviewPane({
  id,
  title,
  ask,
  result,
}: {
  id: string;
  title: string;
  ask: PreviewAsk;
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
          <span className="preview-ask-case">{ask.caseId ?? "no eval case"}</span>
        </div>
        <p className="preview-ask-question">&ldquo;{ask.question}&rdquo;</p>
        <dl className="preview-ask-fields">
          <div>
            <dt>Member ID</dt>
            <dd>{ask.memberId}</dd>
          </div>
          {ask.dateOfService && (
            <div>
              <dt>Date of service</dt>
              <dd>{ask.dateOfService}</dd>
            </div>
          )}
          {ask.askedOn && (
            <div>
              <dt>Asked on</dt>
              <dd>{ask.askedOn}</dd>
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
