import type { TermedMemberResult } from "../types";

export function TermedBlock({ result }: { result: TermedMemberResult }) {
  return (
    <div className="banner banner-block" role="alert">
      <div className="banner-icon">⛔</div>
      <div>
        <div className="banner-title">Not Eligible</div>
        <p className="banner-message">{result.message}</p>
        <p className="banner-hint">
          Do not quote a cost. Verify coverage manually before taking further action.
        </p>
      </div>
    </div>
  );
}
