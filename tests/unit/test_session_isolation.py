"""Unit tests for next_session() (plan §2.5). Pure function, no I/O -- placed
under tests/unit/ rather than tests/integration/ (the plan's illustrative
path) since it needs no database or deployed Agent Engine resource.
"""
from app.agent_client import SESSION_IDLE_TIMEOUT_SECONDS, next_session


def test_first_query_in_a_tab_always_mints_a_new_session():
    state, is_new = next_session(None, "M1006", now=1000.0)
    assert is_new is True
    assert state.member_id == "M1006"


def test_same_member_reuses_session():
    first, _ = next_session(None, "M1006", now=1000.0)
    second, is_new = next_session(first, "M1006", now=1010.0)
    assert is_new is False
    assert second.session_id == first.session_id
    assert second.last_activity == 1010.0  # activity timestamp refreshed


def test_different_member_mints_a_new_session_even_mid_tab():
    """The core plan §2.5 guarantee: Member A's resolved context must not
    bleed into Member B's turn, even in the same browser tab."""
    first, _ = next_session(None, "M1006", now=1000.0)
    second, is_new = next_session(first, "M1007", now=1001.0)
    assert is_new is True
    assert second.session_id != first.session_id
    assert second.member_id == "M1007"


def test_idle_session_is_replaced_even_for_the_same_member():
    first, _ = next_session(None, "M1006", now=1000.0)
    later = 1000.0 + SESSION_IDLE_TIMEOUT_SECONDS + 1
    second, is_new = next_session(first, "M1006", now=later)
    assert is_new is True
    assert second.session_id != first.session_id


def test_session_just_under_idle_timeout_is_reused():
    first, _ = next_session(None, "M1006", now=1000.0)
    just_under = 1000.0 + SESSION_IDLE_TIMEOUT_SECONDS - 1
    second, is_new = next_session(first, "M1006", now=just_under)
    assert is_new is False
    assert second.session_id == first.session_id
