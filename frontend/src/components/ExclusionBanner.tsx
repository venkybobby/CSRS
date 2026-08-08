import type { ExclusionResult } from "../types";

// Deliberately a distinct component (not shared with RateNotFoundBanner)
// with its own class/icon/label -- Story 6, Dana's explicit requirement:
// "not a covered benefit" and "rate not on file" are different regulatory
// facts that require different CSR scripts, and must never look the same
// in the UI.
export function ExclusionBanner({ result }: { result: ExclusionResult }) {
  return (
    <div className="banner banner-exclusion" role="alert">
      <div className="banner-icon">🚫</div>
      <div>
        <div className="banner-title">Not a Covered Benefit</div>
        <p className="banner-message">{result.message}</p>
        <p className="banner-hint">
          Escalate to Member Services -- a specific member-rights disclosure applies to
          exclusions.
        </p>
      </div>
    </div>
  );
}
