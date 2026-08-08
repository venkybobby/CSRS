"""Unit tests for the BFF's IAP JWT verification (plan §4 hardening / §7).
Placed under tests/unit/, not tests/integration/, despite the plan's
illustrative path listing -- this needs no database and no network (Google's
verify_token is mocked), so it shouldn't be gated behind TEST_DATABASE_URL
like the real integration suite is.
"""
import os
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.auth import IAP_JWT_HEADER, IAPVerificationError, get_current_csr


class _FakeRequest:
    def __init__(self, headers: dict[str, str]):
        self.headers = headers


@pytest.fixture(autouse=True)
def iap_audience_env():
    with patch.dict(os.environ, {"IAP_EXPECTED_AUDIENCE": "/projects/123/apps/csrsupport-prod"}):
        yield


def test_missing_header_rejected_401():
    request = _FakeRequest(headers={})
    with pytest.raises(HTTPException) as exc_info:
        get_current_csr(request)
    assert exc_info.value.status_code == 401


def test_valid_jwt_returns_email():
    request = _FakeRequest(headers={IAP_JWT_HEADER: "fake.jwt.token"})
    with patch("app.auth.id_token.verify_token", return_value={"email": "csr.jordan@meridianhealthplans.com"}):
        email = get_current_csr(request)
    assert email == "csr.jordan@meridianhealthplans.com"


def test_signature_or_audience_failure_rejected_403_not_trusted():
    """A forged/expired/wrong-audience token must be rejected outright --
    never falls through to trusting the raw header."""
    request = _FakeRequest(headers={IAP_JWT_HEADER: "forged.jwt.token"})
    with patch("app.auth.id_token.verify_token", side_effect=ValueError("Token has expired")):
        with pytest.raises(HTTPException) as exc_info:
            get_current_csr(request)
    assert exc_info.value.status_code == 403


def test_token_missing_email_claim_rejected_403():
    request = _FakeRequest(headers={IAP_JWT_HEADER: "fake.jwt.token"})
    with patch("app.auth.id_token.verify_token", return_value={"sub": "12345"}):
        with pytest.raises(HTTPException) as exc_info:
            get_current_csr(request)
    assert exc_info.value.status_code == 403


def test_missing_audience_config_is_a_server_error_not_a_silent_bypass():
    request = _FakeRequest(headers={IAP_JWT_HEADER: "fake.jwt.token"})
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(HTTPException) as exc_info:
            get_current_csr(request)
    assert exc_info.value.status_code == 500


def test_verify_iap_jwt_wraps_any_failure_uniformly():
    """No distinguishing detail leaks between 'expired' vs 'bad signature'
    vs 'wrong audience' -- all raise the same IAPVerificationError type,
    avoiding an oracle for someone probing forged tokens."""
    from app.auth import verify_iap_jwt

    with patch("app.auth.id_token.verify_token", side_effect=ValueError("boom")):
        with pytest.raises(IAPVerificationError):
            verify_iap_jwt("x", "aud")
