"""Agent Engine client + per-member session-minting policy (plan §2.5).

Two independent concerns kept in one small module because they're tightly
coupled in practice: `next_session()` is the pure decision of when to reuse
vs. mint a new ADK session (unit-testable with zero I/O -- see
tests/unit/test_session_isolation.py), and `AgentEngineClient` is the thin
I/O wrapper that actually calls the deployed Agent Engine resource using
whatever session id next_session() decided on.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, replace
from typing import Any
from uuid import uuid4

SESSION_IDLE_TIMEOUT_SECONDS = 30 * 60  # plan §2.5: cap so an abandoned tab doesn't accumulate context


@dataclass(frozen=True)
class SessionState:
    session_id: str
    member_id: str | None
    last_activity: float  # epoch seconds


def next_session(
    current: SessionState | None,
    requested_member_id: str,
    *,
    now: float | None = None,
) -> tuple[SessionState, bool]:
    """Decide whether to reuse `current`'s ADK session or mint a new one.

    A new session is minted whenever:
      - there is no current session for this browser tab,
      - the requested member_id differs from the session's member_id (plan
        §2.5: resolved CPT/accumulator context must never carry across a
        member-id boundary -- Member A's turn must not bleed into Member
        B's), or
      - the session has been idle past SESSION_IDLE_TIMEOUT_SECONDS.

    Returns (new_state, is_new_session). Pure function -- the caller (the
    BFF's request handler) is responsible for persisting the returned state
    (e.g. in a signed cookie or short-lived server-side cache) and for
    actually creating the ADK session via the client on a new session_id.
    """
    now = now if now is not None else time.time()

    if current is None:
        return (
            SessionState(session_id=str(uuid4()), member_id=requested_member_id, last_activity=now),
            True,
        )

    idle_for = now - current.last_activity
    member_changed = current.member_id != requested_member_id
    idle_expired = idle_for > SESSION_IDLE_TIMEOUT_SECONDS

    if member_changed or idle_expired:
        return (
            SessionState(session_id=str(uuid4()), member_id=requested_member_id, last_activity=now),
            True,
        )

    return replace(current, last_activity=now), False


class AgentEngineClient:
    """Thin wrapper around a deployed Vertex AI Agent Engine resource.

    Lazily resolves the resource on first use (not at import time) so unit
    tests and local tooling can import this module without GCP credentials.
    The exact query call surface (stream_query vs. async_stream_query) is
    dynamically registered by Agent Engine per the deployed app's declared
    operations -- verify against the actual deployed resource's
    operation_schemas() at integration/deploy time; this wrapper uses the
    standard documented ADK-on-Agent-Engine query pattern.
    """

    def __init__(self, resource_name: str | None = None):
        self._resource_name = resource_name or os.environ["AGENT_ENGINE_RESOURCE_NAME"]
        self._remote_app: Any = None

    def _get_remote_app(self) -> Any:
        if self._remote_app is None:
            from vertexai import agent_engines

            self._remote_app = agent_engines.get(self._resource_name)
        return self._remote_app

    def create_session(self, *, user_id: str, session_id: str) -> None:
        """Registers session_id with Vertex AI's session service before it's
        ever passed to query() -- stream_query() does NOT implicitly create
        a session on first use, it looks one up and raises
        google.adk.errors.session_not_found_error.SessionNotFoundError if
        it doesn't already exist. next_session() mints a fresh UUID and
        signals is_new_session precisely so the caller can call this first;
        that signal previously went unused (main.py discarded it into
        `_is_new`), so every single query failed with a silently-swallowed
        SessionNotFoundError -- caught deep in the ADK runner's background
        thread, never surfaced to the BFF's own request handler, producing
        a clean 200 with an empty message/result instead of an error.
        AdkApp.create_session (what remote_app proxies to) honors a
        caller-supplied session_id rather than minting its own."""
        remote_app = self._get_remote_app()
        remote_app.create_session(user_id=user_id, session_id=session_id)

    def query(self, *, user_id: str, session_id: str, message: str) -> dict:
        """Sends one turn to the agent and returns the final structured
        AgentResponse dict (plan §2.2 layer 2 -- {message, tool_result_ref,
        evidence}) plus the raw list of tool-call events for this turn, so
        the caller can build source_data_snapshot / run the numeric-
        provenance guardrail against real tool payloads, not just the
        agent's final text."""
        remote_app = self._get_remote_app()
        events = list(
            remote_app.stream_query(user_id=user_id, session_id=session_id, message=message)
        )
        return {"events": events}
