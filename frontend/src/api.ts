import type { QueryResponse } from "./types";

export async function submitQuery(
  memberId: string,
  question: string,
  currentSession: QueryResponse["session_state"] | null,
  // Omitted from the body entirely when empty rather than sent as null: the
  // backend treats "no date stated" as its pre-existing as-of-today
  // behavior, and an explicit null would be a value the CSR never entered.
  dateOfService?: string,
): Promise<QueryResponse> {
  const res = await fetch("/api/v1/query", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include", // IAP identity travels via cookie/header set by the load balancer
    body: JSON.stringify({
      member_id: memberId,
      question,
      current_session: currentSession,
      ...(dateOfService ? { date_of_service: dateOfService } : {}),
    }),
  });

  if (!res.ok) {
    throw new Error(`Query failed: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as QueryResponse;
}
