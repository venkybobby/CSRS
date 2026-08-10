"""CSRSupport BFF (backend-for-frontend). Cloud Run service sitting between
the internal frontend SPA and the Agent Engine deployment (plan §1).

Responsibilities (and nothing else -- deliberately thin):
  - verify the CSR's IAP identity cryptographically (auth.py)
  - decide session reuse/rotation per plan §2.5 (agent_client.py)
  - call the deployed agent (agent_client.py)
  - run the numeric-provenance guardrail on the agent's final text
    (guardrails.py) before it ever reaches the CSR
  - surface a per-session audit transcript for supervisor review
    (audit_readback.py)

Session state is kept client-side (round-tripped in the request/response
body) rather than server-side, so this service stays stateless across Cloud
Run instances/restarts for MVP1 -- see QueryResponse.session_state. A
shared cache (e.g. Redis) is the natural upgrade path if that round-trip
proves awkward for the frontend; not needed for this scope.
"""
from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

from app.agent_client import AgentEngineClient, SessionState, next_session
from app.audit_readback import get_session_transcript
from app.auth import get_current_csr
from app.guardrails import enforce_numeric_provenance
from shared.messages import rate_not_found_message

app = FastAPI(title="CSRSupport BFF")


@app.get("/health")
def health() -> dict:
    return {"app": "csrsupport-bff", "status": "ok"}


class ClientSessionState(BaseModel):
    session_id: str
    member_id: str | None = None
    last_activity: float


class QueryRequest(BaseModel):
    member_id: str
    question: str
    current_session: ClientSessionState | None = None


class QueryResponse(BaseModel):
    message: str
    # The structured tool payload itself (a CostEstimateResult or
    # ProcedureMatchResult dict, keyed by response_type/status) -- the
    # frontend renders its distinct-per-outcome components (plan §1: "never
    # raw LLM markdown") from THIS, not from parsing `message`. Every dollar
    # figure the UI displays therefore comes straight from the tool's own
    # JSON, untouched by the model -- `message` is CSR-readable prose only.
    result: dict | None = None
    audit_id: str | None = None
    guardrail_triggered: bool
    session_state: ClientSessionState


def _agent_client() -> AgentEngineClient:
    return AgentEngineClient()


@app.post("/api/v1/query", response_model=QueryResponse)
def query(
    body: QueryRequest,
    csr_user_id: str = Depends(get_current_csr),
    client: AgentEngineClient = Depends(_agent_client),
) -> QueryResponse:
    current = (
        SessionState(
            session_id=body.current_session.session_id,
            member_id=body.current_session.member_id,
            last_activity=body.current_session.last_activity,
        )
        if body.current_session
        else None
    )
    new_state, is_new = next_session(current, body.member_id)
    if is_new:
        client.create_session(user_id=csr_user_id, session_id=new_state.session_id)

    raw = client.query(user_id=csr_user_id, session_id=new_state.session_id, message=body.question)
    events = raw.get("events", [])

    agent_message, structured_result, audit_id, tool_payloads = _extract_agent_turn(events)

    final_message, guardrail_result = enforce_numeric_provenance(
        agent_message, tool_payloads, audit_id=audit_id
    )

    return QueryResponse(
        message=final_message,
        result=structured_result,
        audit_id=audit_id,
        guardrail_triggered=not guardrail_result.passed,
        session_state=ClientSessionState(
            session_id=new_state.session_id,
            member_id=new_state.member_id,
            last_activity=new_state.last_activity,
        ),
    )


# response_type values that identify a tool payload as a CostEstimateResult
# (estimate_member_cost's return shape) vs. some other tool's output -- see
# agent/csr_agent/tools/models.py's CostEstimateResult union.
_COST_ESTIMATE_RESPONSE_TYPES = {
    "MEMBER_NOT_FOUND",
    "TERMED_BLOCK",
    "EXCLUSION",
    "RATE_NOT_FOUND",
    "PREVENTIVE_ZERO_COST",
    "STANDARD_COST",
}


def _extract_agent_turn(
    events: list[dict],
) -> tuple[str, dict | None, str | None, list[dict]]:
    """Pulls the final model text, the last CostEstimateResult-shaped tool
    payload (what the frontend renders its distinct-per-outcome components
    from), the audit_id to attribute the turn to, and every tool-result
    payload from this turn's ADK event stream (used by the numeric-
    provenance guardrail, not just the structured result).

    Exact event shape depends on the ADK version's Event schema -- this
    walks the documented function_response/content.parts structure
    defensively so a minor field-naming change degrades to "no tool
    payloads found" (which the guardrail then correctly treats as zero
    verified values, causing ANY dollar figure to fail closed) rather than
    raising.
    """
    tool_payloads: list[dict] = []
    structured_result: dict | None = None
    final_text = ""
    audit_id: str | None = None

    for event in events:
        for part in (event.get("content") or {}).get("parts", []) or []:
            function_response = part.get("function_response")
            if function_response and isinstance(function_response.get("response"), dict):
                payload = function_response["response"]
                tool_payloads.append(payload)
                if "audit_id" in payload:
                    audit_id = payload["audit_id"]
                if payload.get("response_type") in _COST_ESTIMATE_RESPONSE_TYPES:
                    structured_result = payload
            text = part.get("text")
            if text:
                final_text = text

    # Two resolve_procedure-only outcomes never reach estimate_member_cost,
    # so there's no CostEstimateResult from the pipeline -- synthesize one
    # so the frontend still renders its normal distinct component instead
    # of falling back to plain text:
    #   - NEEDS_CLARIFICATION: surface the ProcedureMatchResult as-is.
    #   - NOT_ON_FILE: a code never on the rate sheet at all (e.g. Cardiac
    #     CT) must look identical in the UI to a matched-but-unpriced code
    #     caught later inside the pipeline (e.g. S8092 on Silver/Gold) --
    #     same RateNotFoundBanner either way, same canonical wording
    #     (shared/messages.py), even though this path never ran eligibility
    #     and therefore has no audit_id to attribute it to.
    if structured_result is None:
        for payload in reversed(tool_payloads):
            if payload.get("status") == "NEEDS_CLARIFICATION":
                structured_result = {**payload, "response_type": "NEEDS_CLARIFICATION"}
                break
            if payload.get("status") == "NOT_ON_FILE":
                query = payload.get("query", "")
                structured_result = {
                    "response_type": "RATE_NOT_FOUND",
                    "eligibility": None,
                    "procedure_query": query,
                    "message": rate_not_found_message(query),
                    "audit_id": None,
                }
                break

    return final_text, structured_result, audit_id, tool_payloads


@app.get("/api/v1/audit/{session_id}")
async def audit_transcript(
    session_id: str, csr_user_id: str = Depends(get_current_csr)
) -> dict:
    events = await get_session_transcript(user_id=csr_user_id, session_id=session_id)
    if not events:
        raise HTTPException(status_code=404, detail="No session transcript found")
    return {"session_id": session_id, "events": events}
