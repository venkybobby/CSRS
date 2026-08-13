import type { PlanYearBoundaryResult } from "../types";

// The member IS eligible here -- this is a refusal to PRICE, not a refusal
// of coverage, and the banner says so explicitly. Getting that distinction
// wrong on screen would have the CSR tell a member they are not covered
// when they are.
export function PlanYearBoundaryBanner({ result }: { result: PlanYearBoundaryResult }) {
  return (
    <div className="banner banner-cannot-price" role="alert">
      <div className="banner-icon">📅</div>
      <div>
        <div className="banner-title">Cannot Estimate — Next Plan Year</div>
        <p className="banner-message">{result.message}</p>
        <dl className="banner-detail">
          <div>
            <dt>Date of service</dt>
            <dd>{result.date_of_service}</dd>
          </div>
          <div>
            <dt>Current plan year ends</dt>
            <dd>{result.plan_year_end}</dd>
          </div>
          <div>
            <dt>Plan on file</dt>
            <dd>{result.eligibility.plan_id ?? "—"}</dd>
          </div>
        </dl>
        <p className="banner-hint">
          The member is eligible on this date — we cannot price it. Deductible and
          out-of-pocket balances reset January 1, and next year's plan terms are not
          on file.
        </p>
        {result.audit_id && <p className="audit-ref">Audit ref: {result.audit_id}</p>}
      </div>
    </div>
  );
}
