import type { PreventiveZeroCostResult } from "../types";

export function PreventiveBanner({ result }: { result: PreventiveZeroCostResult }) {
  return (
    <div className="banner banner-preventive" role="status">
      <div className="banner-icon">✅</div>
      <div>
        <div className="banner-title">Covered at 100% -- Member Owes $0</div>
        <p className="banner-message">{result.message}</p>
      </div>
    </div>
  );
}
