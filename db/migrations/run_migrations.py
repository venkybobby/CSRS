"""Idempotent migration runner. Applies any .sql file in db/migrations/ that
hasn't been recorded in schema_migrations yet, in filename order, each in
its own transaction.

Reuses csr_agent.data.db.get_engine() rather than opening its own
connection -- this is deliberate, not laziness: get_engine() already
branches on CLOUD_SQL_INSTANCE_CONNECTION_NAME vs. DATABASE_URL (plan §3.2),
so this script gets the same IAM-auth Cloud SQL Connector path the running
application uses, without duplicating that logic. In production this is
invoked from a Cloud Run Job (infra/modules/cloud_run_job), not directly
from a Cloud Build step -- Cloud Build's default worker pool has no VPC
route to the private-IP-only Cloud SQL instance, but a Cloud Run Job with a
VPC connector does (see cloudbuild/deploy.yaml's run-db-migrations step).

Usage:
    CLOUD_SQL_INSTANCE_CONNECTION_NAME=... CLOUD_SQL_IAM_USER=... \
        python db/migrations/run_migrations.py
    # or locally:
    DATABASE_URL=postgresql+psycopg2://... python db/migrations/run_migrations.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine

MIGRATIONS_DIR = Path(__file__).parent
REPO_ROOT = MIGRATIONS_DIR.parents[1]
sys.path.insert(0, str(REPO_ROOT / "agent"))

from csr_agent.data.db import get_engine  # noqa: E402

TRACKING_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    id          text PRIMARY KEY,
    applied_at  timestamptz NOT NULL DEFAULT now()
)
"""


def pending_migrations(applied: set[str]) -> list[Path]:
    all_migrations = sorted(MIGRATIONS_DIR.glob("[0-9]*.sql"))
    return [f for f in all_migrations if f.stem not in applied]


def apply_pending_migrations(engine: Engine) -> int:
    """The one place schema application happens -- imported directly by
    tests/integration/conftest.py's seeded_db fixture, not just invoked as
    a standalone script. Two independent code paths applying
    0001_init_schema.sql (the test fixture re-running the raw .sql file
    on every test vs. this script's schema_migrations-tracked apply) is
    exactly what caused a DuplicateTable error the first time both ran
    against the same shared Postgres container in one CI pipeline: the
    fixture's raw apply left tables in place without ever recording them
    in schema_migrations, so this script's tracking-table check didn't
    know they existed and tried to re-run CREATE TABLE. Single source of
    truth now -- returns the number of migrations actually applied.
    """
    with engine.begin() as conn:
        conn.execute(text(TRACKING_TABLE_DDL))
        applied = {row[0] for row in conn.execute(text("SELECT id FROM schema_migrations"))}

    pending = pending_migrations(applied)
    for migration_file in pending:
        print(f"Applying {migration_file.name} ...")
        sql = migration_file.read_text(encoding="utf-8")
        with engine.begin() as conn:
            conn.execute(text(sql))
            conn.execute(
                text("INSERT INTO schema_migrations (id) VALUES (:id)"),
                {"id": migration_file.stem},
            )
        print(f"  applied {migration_file.name}")

    return len(pending)


def main() -> int:
    count = apply_pending_migrations(get_engine())
    if count == 0:
        print("No pending migrations.")
    else:
        print(f"Applied {count} migration(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
