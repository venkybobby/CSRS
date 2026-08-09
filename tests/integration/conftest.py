"""Integration test fixtures. Requires TEST_DATABASE_URL (a throwaway
Postgres database -- these tests DROP/CREATE the public schema, so never
point this at a real dev/staging/prod database). Skips the whole
integration suite if it isn't set, rather than trying to guess credentials
for whatever Postgres happens to be running locally.

    TEST_DATABASE_URL=postgresql+psycopg2://user:pass@localhost:5432/csrsupport_test \
        pytest tests/integration -v
"""
from __future__ import annotations

import os

import csr_agent.data.db as db_module
import pytest
from sqlalchemy import create_engine, text

from db.migrations.run_migrations import apply_pending_migrations
from db.seed.seed import seed

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


@pytest.fixture()
def seeded_db():
    # A conftest-level `pytestmark` does NOT propagate to skip tests in
    # sibling modules the way a same-module `pytestmark` does -- that was
    # tried here and silently no-op'd, letting every test through to
    # create_engine(None). Skipping inside the fixture itself is the
    # reliable mechanism: every integration test depends on this fixture,
    # so this is a single, guaranteed choke point.
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL not set -- see tests/integration/conftest.py")

    engine = create_engine(TEST_DATABASE_URL)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    # Single source of truth for "how do I apply the schema" -- see
    # apply_pending_migrations' docstring. The DROP SCHEMA above also drops
    # schema_migrations itself, so this always sees zero recorded
    # migrations and applies 0001_init_schema.sql fresh, tracked, every
    # test -- and a later, separate process (e.g. db/migrations/
    # run_migrations.py run against this same database afterward) correctly
    # sees it as already applied instead of retrying CREATE TABLE.
    apply_pending_migrations(engine)
    engine.dispose()

    seed(TEST_DATABASE_URL)

    # csr_agent.data.db.get_engine() is lru_cache'd and reads DATABASE_URL /
    # CLOUD_SQL_INSTANCE_CONNECTION_NAME from the environment -- point it at
    # the test database and make sure no stray Cloud SQL env var wins.
    db_module.get_engine.cache_clear()
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    os.environ.pop("CLOUD_SQL_INSTANCE_CONNECTION_NAME", None)

    yield TEST_DATABASE_URL

    db_module.get_engine.cache_clear()
