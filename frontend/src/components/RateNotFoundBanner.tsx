import type { RateNotFoundResult } from "../types";

export function RateNotFoundBanner({ result }: { result: RateNotFoundResult }) {
  return (
    <div className="banner banner-not-found" role="alert">
      <div className="banner-icon">❓</div>
      <div>
        <div className="banner-title">No Rate On File</div>
        <p className="banner-message">{result.message}</p>
        <p className="banner-hint">
          Do not estimate. Transfer to Member Services supervisor or advise the member of a
          callback with a confirmed cost.
        </p>
      </div>
    </div>
  );
}
