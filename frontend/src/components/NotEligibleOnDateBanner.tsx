import type { NotEligibleOnDateResult } from "../types";

// Deliberately a different banner from TermedBlock even though both are
// "not eligible": a termed member is not eligible at all, while this member
// is very likely eligible TODAY and simply is not on the date being asked
// about. Showing the coverage window makes that difference visible on the
// screen rather than leaving the CSR to infer it from the sentence.
export function NotEligibleOnDateBanner({ result }: { result: NotEligibleOnDateResult }) {
  const { eligibility: e } = result;
  return (
    <div className="banner banner-block" role="alert">
      <div className="banner-icon">⛔</div>
      <div>
        <div className="banner-title">
          Not Eligible on {result.date_of_service}
        </div>
        <p className="banner-message">{result.message}</p>
        <dl className="banner-detail">
          <div>
            <dt>Date of service</dt>
            <dd>{result.date_of_service}</dd>
          </div>
          <div>
            <dt>Coverage period</dt>
            <dd>
              {e.coverage_start ?? "—"} to {e.coverage_end ?? "open-ended"}
            </dd>
          </div>
        </dl>
        <p className="banner-hint">
          {result.reason === "NOT_YET_EFFECTIVE"
            ? "Coverage has not started as of this date. Do not quote a cost."
            : "Coverage has ended as of this date. Do not quote a cost."}
        </p>
        {result.audit_id && <p className="audit-ref">Audit ref: {result.audit_id}</p>}
      </div>
    </div>
  );
}
