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
    DATABASE_URL=postgresql+pg8000://csrsupport_agent_engine:...@db.xxxx.supabase.co:5432/postgres \\
        python agent/csr_agent/deploy/deploy_agent_engine.py
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
# csr_agent isn't importable as-is when this script is invoked as
# `python agent/csr_agent/deploy/deploy_agent_engine.py` from the repo root
# (Cloud Build's run-db-migrations pattern) -- Python only puts the script's
# own directory on sys.path, not agent/. Same fix db/migrations/
# run_migrations.py already applies for the identical reason. Also need
# REPO_ROOT itself on sys.path: importing csr_agent.agent (to get
# root_agent) transitively pulls in csr_agent.pipeline.estimate, which
# imports shared.messages -- shared/ lives at the repo root, not under
# agent/, matching extra_packages below which bundles both directories
# for the *deployed* Agent Engine runtime; this covers the *local* import
# needed just to construct the AdkApp before deploying it.
sys.path.insert(0, str(REPO_ROOT / "agent"))
sys.path.insert(0, str(REPO_ROOT))

import vertexai  # noqa: E402
from csr_agent.agent import root_agent  # noqa: E402
from vertexai import agent_engines  # noqa: E402
from vertexai.agent_engines import AdkApp  # noqa: E402

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


def _db_env_vars() -> dict[str, str]:
    """Mirrors csr_agent.data.db.get_engine()'s own DATABASE_URL vs.
    CLOUD_SQL_INSTANCE_CONNECTION_NAME branch -- dev runs on Supabase
    (DATABASE_URL, a plain password-based connection string), staging/prod
    still run on Cloud SQL with IAM auth (the CLOUD_SQL_* pair) until/unless
    they're migrated too. Exactly one of the two must be set."""
    database_url = os.environ.get("DATABASE_URL")
    cloud_sql_instance = os.environ.get("CLOUD_SQL_INSTANCE_CONNECTION_NAME")
    if database_url and cloud_sql_instance:
        raise SystemExit("Set only one of DATABASE_URL or CLOUD_SQL_INSTANCE_CONNECTION_NAME, not both")
    if database_url:
        return {"DATABASE_URL": database_url}
    if cloud_sql_instance:
        return {
            "CLOUD_SQL_INSTANCE_CONNECTION_NAME": cloud_sql_instance,
            "CLOUD_SQL_IAM_USER": _required_env("CLOUD_SQL_IAM_USER"),
        }
    raise SystemExit("Set DATABASE_URL (Supabase) or CLOUD_SQL_INSTANCE_CONNECTION_NAME (Cloud SQL)")


def main() -> None:
    project = _required_env("GOOGLE_CLOUD_PROJECT")
    location = _required_env("GOOGLE_CLOUD_LOCATION")
    staging_bucket = _required_env("STAGING_BUCKET")
    service_account = _required_env("AGENT_ENGINE_SERVICE_ACCOUNT")
    db_env_vars = _db_env_vars()
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

    # vertexai.agent_engines._agent_engines._upload_extra_packages does
    # `tarfile.add(file)` with no arcname override, so whatever path string
    # we pass becomes the archive's literal directory structure verbatim
    # (absolute paths just get their leading "/" stripped -- tarfile's own
    # normalization, not path-relative-to-cwd or basename-only). csr_agent/
    # (at agent/csr_agent/) and shared/ (at the repo root) aren't siblings
    # in this repo, so passing their real absolute paths archives them
    # nested as workspace/agent/csr_agent/ and workspace/shared/ -- not the
    # flat csr_agent/ and shared/ the remote unpickler needs to `import
    # csr_agent` (matching how root_agent was imported locally above).
    # Confirmed against a live deploy: this nesting mismatch produced
    # "ModuleNotFoundError: No module named 'csr_agent'" when the deployed
    # Reasoning Engine unpickled the uploaded agent. tarfile also doesn't
    # dereference symlinks by default (would archive a dangling link, not
    # contents), so stage real copies as flat siblings and chdir there --
    # relative names ("csr_agent", "shared") then archive flat.
    with tempfile.TemporaryDirectory(prefix="agent_engine_extra_packages_") as staging_dir:
        shutil.copytree(REPO_ROOT / "agent" / "csr_agent", Path(staging_dir) / "csr_agent")
        # csr_agent.pipeline.estimate imports from shared.messages (and
        # transitively nothing else from shared/ today, but keep the whole
        # package together rather than risk this drifting out of sync again
        # the way it did once already when shared/ was split out of
        # agent/csr_agent/ -- see docs/architecture/plan.md's
        # "Implementation note").
        shutil.copytree(REPO_ROOT / "shared", Path(staging_dir) / "shared")
        original_cwd = os.getcwd()
        os.chdir(staging_dir)
        try:
            remote_app = agent_engines.create(
                # AdkApp is Google's own documented wrapper for exactly this
                # call (has stream_query/async_stream_query at runtime --
                # verified via `dir(AdkApp)`), but isn't included in
                # agent_engines.create()'s declared agent_engine Union type
                # -- a stub gap in google-cloud-aiplatform, not a bug here.
                agent_engine=app,  # type: ignore[arg-type]
                display_name=display_name,
                requirements=requirements,
                extra_packages=["csr_agent", "shared"],
                service_account=service_account,
                env_vars=db_env_vars,
                min_instances=min_instances,
                max_instances=max_instances,
            )
        finally:
            os.chdir(original_cwd)

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
