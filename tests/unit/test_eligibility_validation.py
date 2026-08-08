"""Unit test for the member_id format guard in get_eligibility() (plan §4).
Only the malformed-input short-circuit is unit-testable without a DB -- it
returns before ever calling get_engine(); the found/not-found DB path is
covered by tests/integration/test_pipeline.py.
"""
from csr_agent.data.eligibility import get_eligibility


def test_malformed_member_id_short_circuits_before_any_query():
    for bad_id in ["'; DROP TABLE members; --", "../../etc/passwd", "M1", "12345", ""]:
        result = get_eligibility(bad_id)
        assert result.found is False
        assert result.member_id == bad_id
