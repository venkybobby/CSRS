"""Canonical, code-owned response text (Story 8 / plan §2.2: the model
relays these, it does not author them). Lives in shared/ because both the
agent's pipeline (agent/csr_agent/pipeline/estimate.py, when a rate is
absent after a code has already been matched) and the BFF (bff/app/main.py,
when resolve_procedure itself never finds a match at all) need the exact
same wording -- a CSR should see an identical message regardless of which
tool caught the "honest miss".
"""
from __future__ import annotations


def rate_not_found_message(procedure_as_typed: str) -> str:
    return (
        f"We don't have a negotiated rate on file for {procedure_as_typed}. Do not estimate. "
        "Please transfer to Member Services supervisor or advise the member "
        "we'll call back with a confirmed cost."
    )


def termed_member_message(name: str, coverage_end: str) -> str:
    return f"{name} is not eligible as of {coverage_end}. Do not quote a cost."
