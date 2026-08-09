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
from csr_agent.agent import root_agent
from vertexai import agent_engines
from vertexai.agent_engines import AdkApp

REPO_ROOT = Path(__file__).resolve().parents[3]
REQUIREMENTS_FILE = REPO_ROOT / "agent" / "requirements.txt"


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"Required environment variable {name} is not set")
    return value


def _env_or_default(name: str, default: str) -> str:
    # Return type is always `str` (never None) since `default` is -- unlike
    # the single required-vs-optional `_env()` helper this replaced, whose
    # `str | None` return type didn't actually narrow to `str` for the
    # optional-with-a-string-default call sites, and mypy correctly flagged
    # every downstream int()/dict-value use of those as a str|None mismatch.
    return os.environ.get(name) or default


def main() -> None:
    project = _required_env("GOOGLE_CLOUD_PROJECT")
    location = _required_env("GOOGLE_CLOUD_LOCATION")
    staging_bucket = _required_env("STAGING_BUCKET")
    service_account = _required_env("AGENT_ENGINE_SERVICE_ACCOUNT")
    cloud_sql_instance = _required_env("CLOUD_SQL_INSTANCE_CONNECTION_NAME")
    cloud_sql_iam_user = _required_env("CLOUD_SQL_IAM_USER")
    display_name = _env_or_default("AGENT_ENGINE_DISPLAY_NAME", "csr-cost-agent")
    min_instances = int(_env_or_default("AGENT_ENGINE_MIN_INSTANCES", "0"))
    max_instances = int(_env_or_default("AGENT_ENGINE_MAX_INSTANCES", "10"))

    vertexai.init(project=project, location=location, staging_bucket=staging_bucket)

    requirements = [
        line.strip()
        for line in REQUIREMENTS_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]

    app = AdkApp(agent=root_agent, enable_tracing=True)

    remote_app = agent_engines.create(
        # AdkApp is Google's own documented wrapper for exactly this call
        # (has stream_query/async_stream_query at runtime -- verified via
        # `dir(AdkApp)`), but isn't included in agent_engines.create()'s
        # declared agent_engine Union type -- a stub gap in
        # google-cloud-aiplatform, not a bug here.
        agent_engine=app,  # type: ignore[arg-type]
        display_name=display_name,
        requirements=requirements,
        # csr_agent.pipeline.estimate imports from shared.messages (and
        # transitively nothing else from shared/ today, but keep the whole
        # package together rather than risk this drifting out of sync again
        # the way it did once already when shared/ was split out of
        # agent/csr_agent/ -- see docs/architecture/plan.md's
        # "Implementation note"). Without this, the deployed agent fails at
        # runtime with ModuleNotFoundError the first time estimate_member_cost
        # is called, not at deploy time -- there's no import-time check here.
        extra_packages=[str(REPO_ROOT / "agent" / "csr_agent"), str(REPO_ROOT / "shared")],
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

    output_file = os.environ.get("AGENT_ENGINE_OUTPUT_FILE")
    if output_file:
        # Written for cloudbuild/deploy.yaml to pick up in later steps
        # (Cloud Build substitution variables are fixed at trigger time and
        # can't be set mid-build from a step's output -- /workspace is the
        # documented way steps hand values to each other).
        Path(output_file).write_text(remote_app.resource_name, encoding="utf-8")


if __name__ == "__main__":
    main()
