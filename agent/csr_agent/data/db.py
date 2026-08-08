"""Database connectivity.

Production (GCP): Cloud SQL Python Connector with IAM database
authentication -- no DB password ever exists (plan §3.2/§4). Selected
whenever CLOUD_SQL_INSTANCE_CONNECTION_NAME is set.

Local/CI: a plain DATABASE_URL (e.g. local Postgres or a Cloud Build
Postgres service container for the eval/integration test suite).

Pool size is intentionally tiny per instance (plan §3 hardening): Cloud
Run's scale-to-zero means many container instances can open connection pools
near-simultaneously under a traffic spike, and each instance's footprint
must stay small relative to Postgres's max_connections. If concurrency ever
outgrows this, add pgBouncer in front of Cloud SQL rather than widening
per-instance pools further.
"""
from __future__ import annotations

import os
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

POOL_SIZE = 2
MAX_OVERFLOW = 1


_GSA_SUFFIX = ".gserviceaccount.com"


def _iam_db_username(raw: str) -> str:
    """Cloud SQL IAM auth requires the DB username to be the service
    account email with the .gserviceaccount.com suffix stripped -- doing
    that here, once, means every caller (Terraform's google_sql_user,
    deploy_agent_engine.py, cloudbuild/*.yaml, Terraform env_vars blocks)
    can just pass the natural full service account email and not need to
    remember this Cloud-SQL-specific quirk."""
    return raw[: -len(_GSA_SUFFIX)] if raw.endswith(_GSA_SUFFIX) else raw


def _cloud_sql_creator():
    from google.cloud.sql.connector import Connector, IPTypes

    connector = Connector()

    def getconn():
        return connector.connect(
            os.environ["CLOUD_SQL_INSTANCE_CONNECTION_NAME"],
            "pg8000",
            user=_iam_db_username(os.environ["CLOUD_SQL_IAM_USER"]),
            db=os.environ.get("CLOUD_SQL_DATABASE", "csrsupport"),
            enable_iam_auth=True,
            ip_type=IPTypes.PRIVATE,
        )

    return getconn


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    instance_conn_name = os.environ.get("CLOUD_SQL_INSTANCE_CONNECTION_NAME")
    if instance_conn_name:
        return create_engine(
            "postgresql+pg8000://",
            creator=_cloud_sql_creator(),
            pool_size=POOL_SIZE,
            max_overflow=MAX_OVERFLOW,
            pool_timeout=10,
            isolation_level="REPEATABLE READ",
        )

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "Set CLOUD_SQL_INSTANCE_CONNECTION_NAME (production/staging/dev on "
            "GCP) or DATABASE_URL (local/test) to configure the database "
            "connection."
        )
    return create_engine(
        database_url,
        pool_size=POOL_SIZE,
        max_overflow=MAX_OVERFLOW,
        isolation_level="REPEATABLE READ",
    )
