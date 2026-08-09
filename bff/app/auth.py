"""Cryptographic IAP identity verification (plan §4).

The raw X-Goog-IAP-JWT-Assertion header must never be trusted as-is: this
verifies its signature against Google's published public keys and checks
the audience against this exact deployment's configured resource, closing
the internal-network-pivot risk the architecture review flagged (a request
that reaches this service via a path other than the IAP-fronted load
balancer must not be able to forge or replay a CSR identity).

Cloud Run ingress lock-down (`internal-and-cloud-load-balancing`, set in
infra/modules/cloud_run) is the second, independent half of this control --
this module alone is not sufficient, and is not meant to be.
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from fastapi import HTTPException, Request
from google.auth.transport import requests as google_auth_requests
from google.oauth2 import id_token

IAP_JWT_HEADER = "X-Goog-IAP-JWT-Assertion"
IAP_PUBLIC_KEY_CERTS_URL = "https://www.gstatic.com/iap/verify/public_key"

# Reused across requests so google-auth can cache Google's public keys
# instead of re-fetching them on every call.
_google_auth_request = google_auth_requests.Request()


class IAPVerificationError(Exception):
    pass


def verify_iap_jwt(jwt_value: str, expected_audience: str) -> Mapping[str, Any]:
    """Verifies signature + audience/issuer of an IAP-issued JWT. Returns
    the decoded claims (including 'email') on success; raises
    IAPVerificationError on any failure -- expired, wrong audience, bad
    signature, or malformed token are all treated identically (no
    distinguishing detail is returned to the caller, avoiding an oracle for
    forging attempts)."""
    try:
        return id_token.verify_token(
            jwt_value,
            _google_auth_request,
            audience=expected_audience,
            certs_url=IAP_PUBLIC_KEY_CERTS_URL,
        )
    except Exception as exc:
        raise IAPVerificationError(str(exc)) from exc


def get_current_csr(request: Request) -> str:
    """FastAPI dependency. Returns the IAP-verified CSR email or raises
    401/403 -- never falls through to treating an unverified header as
    trusted identity."""
    jwt_value = request.headers.get(IAP_JWT_HEADER)
    if not jwt_value:
        raise HTTPException(status_code=401, detail="Missing IAP identity header")

    expected_audience = os.environ.get("IAP_EXPECTED_AUDIENCE")
    if not expected_audience:
        raise HTTPException(
            status_code=500, detail="Server misconfigured: IAP_EXPECTED_AUDIENCE unset"
        )

    try:
        decoded = verify_iap_jwt(jwt_value, expected_audience)
    except IAPVerificationError:
        raise HTTPException(status_code=403, detail="Invalid IAP identity token") from None

    email = decoded.get("email")
    if not email:
        raise HTTPException(status_code=403, detail="IAP token missing email claim")
    return email
