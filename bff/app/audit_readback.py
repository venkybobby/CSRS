"""Pulls a session's tool-call/event transcript from Agent Engine's session
service, for supervisor review in the UI (plan §2.4, audit path (a):
"replaying the ADK session transcript").

Deliberately does NOT query quote_audit_log directly. Per the plan's
least-privilege service-account table (§4), sa-bff-run is intentionally NOT
granted any Cloud SQL role -- only sa-agent-engine is. Direct Postgres audit
queries (path (b): "querying quote_audit_log directly") are a separate,
DB-access-controlled workflow for supervisors/compliance tooling (e.g. a BI
tool or psql access granted independently), not something this CSR-facing
API surface exposes. Keeping the BFF off the database entirely means a BFF
compromise can't read member PHI/PII directly from Postgres -- it would
still need the Agent Engine's own credentials to do that.
"""
from __future__ import annotations

import os
from typing import Any


async def get_session_transcript(*, user_id: str, session_id: str) -> list[dict[str, Any]]:
    """Returns the ordered list of events (user message, each tool call and
    its result, model text) for one ADK session. Used to render "what did
    the agent actually do to arrive at this quote" in the UI."""
    from google.adk.sessions import VertexAiSessionService

    agent_engine_id = os.environ["AGENT_ENGINE_RESOURCE_ID"]
    session_service = VertexAiSessionService(
        project=os.environ["GOOGLE_CLOUD_PROJECT"],
        location=os.environ["GOOGLE_CLOUD_LOCATION"],
        agent_engine_id=agent_engine_id,
    )
    session = await session_service.get_session(
        app_name=agent_engine_id, user_id=user_id, session_id=session_id
    )
    if session is None:
        return []
    return [event.model_dump(mode="json") for event in session.events]
