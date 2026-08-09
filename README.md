# CSRSupport

An internal AI agent for Meridian Health Plans Customer Service Reps: type a plain-English
question plus a member ID, get back eligibility status and an auditable, deterministically
calculated out-of-pocket cost estimate. **CSR-internal only — not a patient/member-facing
product.** Full architecture: [docs/architecture/plan.md](docs/architecture/plan.md).

The non-negotiable constraint driving every design choice here: **the LLM only routes natural
language to tools — it never generates, computes, or restates a dollar figure.** Every number a
CSR sees came from a pure Python calculator function, and every quote is traceable back to its
source data. See `docs/architecture/plan.md` §2.2 for the four independent layers that enforce
this.

## Repo layout

```
agent/       ADK agent + tools + deterministic pipeline + calculator, deployed to Agent Engine
bff/         FastAPI backend-for-frontend (Cloud Run) -- IAP auth, guardrail enforcement
shared/      Pure logic both agent/ and bff/ depend on (numeric-provenance guardrail, messages)
frontend/    Vite + React SPA
db/          Postgres schema + seed data (from the source spec's worked examples)
tests/       pytest -- unit/ (pure, no I/O) and integration/ (needs a throwaway Postgres)
evals/       Demo-script + adversarial regression cases, the CI/CD deploy gate
infra/       Terraform (dev/staging/prod, each its own GCP project)
cloudbuild/  CI (PR checks) and CD (deploy) pipeline definitions
```

## Local setup

```bash
python -m pip install -r requirements-dev.txt
cd frontend && npm install && cd ..
```

## Running tests

```bash
# Unit tests -- pure logic, zero I/O, no external services needed
pytest tests/unit -v

# Integration tests -- need a throwaway Postgres (never point this at a real
# dev/staging/prod database; the fixture DROPs and recreates the public schema)
TEST_DATABASE_URL=postgresql+psycopg2://user:pass@localhost:5432/csrsupport_test \
    pytest tests/integration -v

# Frontend build/typecheck
cd frontend && npm run build
```

## Local dev servers

```bash
# Frontend (proxies /api to the BFF -- see frontend/vite.config.ts)
npm --prefix frontend run dev

# BFF (needs a running Postgres + AGENT_ENGINE_RESOURCE_NAME for full
# functionality; the app imports cleanly and serves /health without either)
DATABASE_URL=postgresql+psycopg2://... \
AGENT_ENGINE_RESOURCE_NAME=projects/.../reasoningEngines/... \
IAP_EXPECTED_AUDIENCE=/projects/.../apps/... \
    uvicorn app.main:app --app-dir bff --reload --port 8080
```

## Seeding a local database

```bash
DATABASE_URL=postgresql+psycopg2://user:pass@localhost:5432/csrsupport \
    python db/seed/seed.py
```

## Deploying

CI/CD is the intended path once set up (see below) -- push to `main` and `cloudbuild/deploy.yaml`
builds, migrates, deploys, and evals automatically. For a one-off manual deploy or the very
first bootstrap of an environment:

1. `terraform apply` in `infra/envs/<env>/` (copy `terraform.tfvars.example` first).
2. Deploy the agent: `python agent/csr_agent/deploy/deploy_agent_engine.py` (reads config from
   env vars -- see the script's docstring).
3. Point the BFF's `AGENT_ENGINE_RESOURCE_NAME` at the resource it prints, then deploy the BFF
   and frontend containers.

## CI/CD

`cloudbuild/pr-checks.yaml` (lint, typecheck, unit + integration tests, deterministic eval mode,
container builds) gates every PR. `cloudbuild/deploy.yaml` (build → migrate → deploy agent →
deploy BFF/frontend → live eval mode) runs on push to `main`, auto-deploying to dev and
queuing staging/prod behind Cloud Build's native build-approval feature. `infra/modules/cicd/`
is what actually wires these to GitHub as triggers.

**Setting this up requires two manual, one-time, browser-based steps that can't be scripted**
(authorizing the Cloud Build GitHub App, creating a GitHub PAT) plus a couple of
Terraform-adjacent manual steps (bootstrapping IAM database grants, since a fresh Cloud SQL
instance's IAM users start with zero privileges and something has to grant the first ones).
Full ordered runbook: [docs/architecture/cicd-setup.md](docs/architecture/cicd-setup.md).

## What's verified vs. not in this build

Being direct about this rather than claiming untested code works:

- **Fully executed and passing**: all 45 unit tests (`pytest tests/unit -v`), including every
  worked numeric example from the source spec (M1001–M1010), the rate-matcher's honest-miss and
  forced-clarification behavior, the numeric-provenance guardrail's formatting-divergence and
  fabrication-detection cases, IAP JWT verification (mocked), session-minting logic, and the
  Cloud SQL IAM-username-stripping fix (caught while wiring the CI/CD Terraform -- see below).
- **Terraform/CI-CD config: written, structurally checked, not applied.** `infra/modules/cicd`,
  `artifact_registry`, and `cloud_run_job` (the DB-migration runner) were added after the initial
  build, along with fixes to real gaps caught along the way: `deploy_agent_engine.py` was missing
  `shared/` from its `extra_packages` (would have failed at runtime, not deploy time), the DB
  migration step in `cloudbuild/deploy.yaml` assumed direct reachability to a private-IP-only
  Cloud SQL instance that Cloud Build's default pool can't actually reach (fixed by running it as
  a VPC-connected Cloud Run Job instead), and Cloud SQL IAM database usernames need their
  `.gserviceaccount.com` suffix stripped (fixed once, centrally, in `db.py`, rather than in every
  caller). None of this Terraform has been applied and no `terraform validate`/`plan` was run --
  this sandbox has no `terraform` binary. Review `terraform plan` output carefully before
  `apply`, especially `infra/modules/cicd`'s Cloud Build GitHub-connection resources, which have
  had schema changes across provider versions.
- **Built and statically verified, not executed**: the ADK agent (`agent/csr_agent/agent.py`) and
  its three tools were constructed and their real function-declaration schemas inspected against
  the actual installed `google-adk` package (confirming `tool_context` is correctly excluded from
  the model-visible schema) — but never run against a live model or deployed Agent Engine
  resource. The BFF's FastAPI app imports and registers routes correctly but wasn't exercised
  end-to-end against a real Agent Engine or Postgres instance.
- **Now actually verified against real Postgres, via the user's own Cloud Build run** (this
  development sandbox still can't bind a local Postgres to test against directly -- a disposable
  instance failed with `could not bind... Permission denied`, so `tests/integration/`'s case
  assertions remain unexecuted *here*). That real run caught a genuine schema bug the design
  review pass hadn't: `quote_audit_log`'s `PRIMARY KEY (audit_id)` on a table partitioned by
  `created_at` is rejected outright by Postgres (`FeatureNotSupported: unique constraint on
  partitioned table must include all partitioning columns`) -- fixed to a composite
  `PRIMARY KEY (audit_id, created_at)` in `db/migrations/0001_init_schema.sql`. `evals/run_eval.py`'s
  YAML parsing, argument handling, and per-case dispatch logic were separately verified here (it
  runs and fails gracefully with a clear "no DATABASE_URL" message rather than crashing) but its
  case assertions are likewise unexecuted in this sandbox.
- **Verified in a real browser**: the frontend was built (`npm run build`, clean) and run against
  a mocked BFF response in an actual browser session, confirming the `demo_1` (partial deductible)
  and `demo_4` (termed member) cases render pixel-for-content-correct against the source spec's
  own Demo Script wording, with zero console errors.
- **Not done at all**: no GCP resources were created (no live Cloud SQL, Agent Engine, Cloud Run,
  or IAP resources) and no Terraform was applied — this stays code-only until you're ready to
  provision real infrastructure and review the cost/scope of doing so.

## A note on the spec's own internal inconsistency

The source spec (`meridian_csr_estimator_MVP1_stories.md`) states in one place that M1006 and
M1007 "must produce different outputs" and that identical numbers would indicate a bug — but its
own worked Demo Script #3 shows both members owing exactly $1,860 for the same knee-surgery
query. Both are correct simultaneously once you separate "dollar total" (legitimately equal here,
since neither member's OOP cap binds at this rate) from "OOP position" (`oop_remaining` and
`triggering_threshold`, which do differ and are asserted as differing).
[tests/unit/test_calculator_family.py](tests/unit/test_calculator_family.py) encodes both: the
literal Demo Script #3 case, and a separate constructed higher-rate case where the totals *do*
diverge, which is what the spec's warning is actually guarding against (a wrong accumulator
join-key silently collapsing two members onto the same values).
