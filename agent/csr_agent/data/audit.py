"""Synchronous, same-transaction audit log writer -- the concrete
implementation of the spec's non-negotiable requirement that a supervisor
must be able to trace any quote back to its source data (plan §2.4/§4.6).

Deliberately decoupled from the CostEstimateResult union: this module only
knows how to persist a row, not how to build one -- pipeline/estimate.py is
responsible for assembling request_snapshot/result_snapshot/
source_data_snapshot from its own intermediate values before calling this.
"""
from __future__ import annotations

import json
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text

from csr_agent.data.db import get_engine


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, UUID):
        return str(value)
    if hasattr(value, "isoformat"):  # date/datetime
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def write_audit_log(
    *,
    audit_id: UUID,
    csr_user_id: str,
    session_id: str,
    invocation_id: str,
    trace_id: str,
    member_id: str,
    cpt_code: str | None,
    response_type: str,
    request_snapshot: dict,
    result_snapshot: dict,
    source_data_snapshot: dict,
) -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO quote_audit_log "
                "(audit_id, csr_user_id, session_id, invocation_id, trace_id, member_id, "
                " cpt_code, response_type, request_snapshot, result_snapshot, source_data_snapshot) "
                "VALUES "
                "(:audit_id, :csr_user_id, :session_id, :invocation_id, :trace_id, :member_id, "
                " :cpt_code, :response_type, "
                " CAST(:request_snapshot AS jsonb), CAST(:result_snapshot AS jsonb), "
                " CAST(:source_data_snapshot AS jsonb))"
            ),
            {
                "audit_id": str(audit_id),
                "csr_user_id": csr_user_id,
                "session_id": session_id,
                "invocation_id": invocation_id,
                "trace_id": trace_id,
                "member_id": member_id,
                "cpt_code": cpt_code,
                "response_type": response_type,
                "request_snapshot": json.dumps(request_snapshot, default=_json_default),
                "result_snapshot": json.dumps(result_snapshot, default=_json_default),
                "source_data_snapshot": json.dumps(source_data_snapshot, default=_json_default),
            },
        )
