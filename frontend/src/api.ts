import type { QueryResponse } from "./types";

export async function submitQuery(
  memberId: string,
  question: string,
  currentSession: QueryResponse["session_state"] | null,
): Promise<QueryResponse> {
  const res = await fetch("/api/v1/query", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include", // IAP identity travels via cookie/header set by the load balancer
    body: JSON.stringify({
      member_id: memberId,
      question,
      current_session: currentSession,
    }),
  });

  if (!res.ok) {
    throw new Error(`Query failed: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as QueryResponse;
}
