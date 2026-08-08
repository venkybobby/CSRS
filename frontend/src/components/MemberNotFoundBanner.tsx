import type { MemberNotFoundResult } from "../types";

export function MemberNotFoundBanner({ result }: { result: MemberNotFoundResult }) {
  return (
    <div className="banner banner-not-found" role="alert">
      <div className="banner-icon">❓</div>
      <div>
        <div className="banner-title">Member Not Found</div>
        <p className="banner-message">{result.message}</p>
        <p className="banner-hint">Double-check the member ID with the caller.</p>
      </div>
    </div>
  );
}
