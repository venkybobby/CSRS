"""Deploys csr_agent.agent.root_agent to Vertex AI Agent Engine.

Per plan §6.2: each run creates a NEW Reasoning Engine resource version
rather than mutating one in place -- the BFF pins to a specific resource
name/version and rolls back by repointing, rather than this script updating
a live agent mid-call. Config is entirely environment-variable driven (plan
§6.3: no hardcoded per-environment values) so the same script runs
unchanged across csrsupport-dev / -staging / -prod, driven by whatever
Cloud Build substitution variables set these for that pipeline stage.

Usage:
    GOOGLE_CLOUD_PROJECT=csrsupport-dev \\
    GOOGLE_CLOUD_LOCATION=us-central1 \\
    STAGING_BUCKET=gs://csrsupport-dev-agent-engine-staging \\
    AGENT_ENGINE_SERVICE_ACCOUNT=sa-agent-engine@csrsupport-dev.iam.gserviceaccount.com \\
    CLOUD_SQL_INSTANCE_CONNECTION_NAME=csrsupport-dev:us-central1:csrsupport-db \\
    CLOUD_SQL_IAM_USER=sa-agent-engine@csrsupport-dev.iam \\
        python agent/csr_agent/deploy/deploy_agent_engine.py
"""
from __future__ import annotations

import os
from pathlib import Path

import vertexai
from vertexai import agent_engines
from vertexai.agent_engines import AdkApp

from csr_agent.agent import root_agent

REPO_ROOT = Path(__file__).resolve().parents[3]
REQUIREMENTS_FILE = REPO_ROOT / "agent" / "requirements.txt"


def _env(name: str, required: bool = True, default: str | None = None) -> str | None:
    value = os.environ.get(name, default)
    if required and not value:
        raise SystemExit(f"Required environment variable {name} is not set")
    return value


def main() -> None:
    project = _env("GOOGLE_CLOUD_PROJECT")
    location = _env("GOOGLE_CLOUD_LOCATION")
    staging_bucket = _env("STAGING_BUCKET")
    service_account = _env("AGENT_ENGINE_SERVICE_ACCOUNT")
    cloud_sql_instance = _env("CLOUD_SQL_INSTANCE_CONNECTION_NAME")
    cloud_sql_iam_user = _env("CLOUD_SQL_IAM_USER")
    display_name = _env("AGENT_ENGINE_DISPLAY_NAME", required=False, default="csr-cost-agent")
    min_instances = int(_env("AGENT_ENGINE_MIN_INSTANCES", required=False, default="0"))
    max_instances = int(_env("AGENT_ENGINE_MAX_INSTANCES", required=False, default="10"))

    vertexai.init(project=project, location=location, staging_bucket=staging_bucket)

    requirements = [
        line.strip()
        for line in REQUIREMENTS_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]

    app = AdkApp(agent=root_agent, enable_tracing=True)

    remote_app = agent_engines.create(
        agent_engine=app,
        display_name=display_name,
        requirements=requirements,
        extra_packages=[str(REPO_ROOT / "agent" / "csr_agent")],
        service_account=service_account,
        env_vars={
            "CLOUD_SQL_INSTANCE_CONNECTION_NAME": cloud_sql_instance,
            "CLOUD_SQL_IAM_USER": cloud_sql_iam_user,
        },
        min_instances=min_instances,
        max_instances=max_instances,
    )

    print(f"Deployed Agent Engine resource: {remote_app.resource_name}")
    print("Point the BFF's AGENT_ENGINE_RESOURCE_NAME at this value for this environment.")


if __name__ == "__main__":
    main()
