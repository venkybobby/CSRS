import type { NeedsClarificationResult } from "../types";

export function ClarificationPrompt({ result }: { result: NeedsClarificationResult }) {
  return (
    <div className="banner banner-clarify" role="status">
      <div className="banner-icon">💬</div>
      <div>
        <div className="banner-title">Ask the Caller</div>
        <p className="banner-message">{result.clarifying_question}</p>
        {result.candidates.length > 0 && (
          <ul className="candidate-list">
            {result.candidates.map((c) => (
              <li key={c.cpt_code}>
                {c.common_name} ({c.cpt_code})
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
