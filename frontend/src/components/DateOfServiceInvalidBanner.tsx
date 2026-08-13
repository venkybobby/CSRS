import type { DateOfServiceInvalidResult } from "../types";

// A request-shape refusal: nothing was looked up, so there is no member or
// coverage detail to show -- just the date, why it cannot be quoted, and
// where the CSR should go instead.
export function DateOfServiceInvalidBanner({
  result,
}: {
  result: DateOfServiceInvalidResult;
}) {
  const inPast = result.reason === "IN_PAST";
  return (
    <div className="banner banner-cannot-price" role="alert">
      <div className="banner-icon">📅</div>
      <div>
        <div className="banner-title">
          {inPast ? "Past Date — Claims Question" : "Date Too Far Out"}
        </div>
        <p className="banner-message">{result.message}</p>
        <p className="banner-hint">
          {inPast
            ? "Route to Claims. This tool estimates upcoming procedures only."
            : "Advise the member to call back closer to the date."}
        </p>
        {result.audit_id && <p className="audit-ref">Audit ref: {result.audit_id}</p>}
      </div>
    </div>
  );
}
