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
  result,
}: {
  id: string;
  title: string;
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
      <ResultPanel result={result} />
    </div>
  );
}
