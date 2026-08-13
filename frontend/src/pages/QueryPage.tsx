import { useState } from "react";
import { submitQuery } from "../api";
import { ResultPanel } from "../components/ResultPanel";
import type { QueryResponse } from "../types";

export function QueryPage() {
  const [memberId, setMemberId] = useState("");
  const [question, setQuestion] = useState("");
  const [dateOfService, setDateOfService] = useState("");
  const [response, setResponse] = useState<QueryResponse | null>(null);
  const [session, setSession] = useState<QueryResponse["session_state"] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const result = await submitQuery(
        memberId.trim(),
        question.trim(),
        session,
        dateOfService || undefined,
      );
      setResponse(result);
      setSession(result.session_state);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="query-page">
      <h1>CSRSupport</h1>
      <p className="subtitle">Meridian member eligibility &amp; cost estimator</p>

      <form onSubmit={handleSubmit} className="query-form">
        <label>
          Member ID
          <input
            value={memberId}
            onChange={(e) => setMemberId(e.target.value)}
            placeholder="M1002"
            required
          />
        </label>
        <label>
          Question
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="MRI on his knee, what does he owe?"
            required
          />
        </label>
        <label>
          Date of service <span className="label-optional">(optional)</span>
          <input
            type="date"
            value={dateOfService}
            onChange={(e) => setDateOfService(e.target.value)}
          />
          <span className="field-hint">
            Leave blank to check eligibility as of today.
          </span>
        </label>
        <button type="submit" disabled={loading}>
          {loading ? "Asking..." : "Ask"}
        </button>
      </form>

      {error && (
        <div className="banner banner-block" role="alert">
          <p className="banner-message">{error}</p>
        </div>
      )}

      {response && (
        <div className="response-area">
          {response.guardrail_triggered && (
            <div className="banner banner-guardrail" role="alert">
              <div className="banner-icon">🛑</div>
              <p className="banner-message">{response.message}</p>
            </div>
          )}
          {!response.guardrail_triggered && response.result && (
            <ResultPanel result={response.result} />
          )}
          {!response.guardrail_triggered && !response.result && (
            <p className="banner-message">{response.message}</p>
          )}
        </div>
      )}
    </div>
  );
}
