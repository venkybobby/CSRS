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
from pathlib import Path

import csr_agent.data.db as db_module
import pytest
from sqlalchemy import create_engine, text

from db.seed.seed import seed

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_SQL = REPO_ROOT / "db" / "migrations" / "0001_init_schema.sql"

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
        conn.execute(text(MIGRATION_SQL.read_text(encoding="utf-8")))
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
