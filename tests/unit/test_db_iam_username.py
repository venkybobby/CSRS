"""Regression test for the Cloud SQL IAM DB username quirk: the DB username
for a service account IAM user must have .gserviceaccount.com stripped.
Caught while wiring the CI/CD Terraform -- every caller (Terraform's
google_sql_user, deploy_agent_engine.py, cloudbuild/*.yaml) had been passing
the raw full email instead."""
from csr_agent.data.db import _iam_db_username


def test_strips_gserviceaccount_suffix():
    assert (
        _iam_db_username("sa-agent-engine-dev@csrsupport-dev.iam.gserviceaccount.com")
        == "sa-agent-engine-dev@csrsupport-dev.iam"
    )


def test_leaves_already_stripped_username_unchanged():
    assert _iam_db_username("sa-agent-engine-dev@csrsupport-dev.iam") == "sa-agent-engine-dev@csrsupport-dev.iam"


def test_leaves_non_service_account_username_unchanged():
    assert _iam_db_username("someone@meridianhealthplans.com") == "someone@meridianhealthplans.com"
