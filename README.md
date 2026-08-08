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

1. `terraform apply` in `infra/envs/<env>/` (copy `terraform.tfvars.example` first).
2. Deploy the agent: `python agent/csr_agent/deploy/deploy_agent_engine.py` (reads config from
   env vars -- see the script's docstring).
3. Point the BFF's `AGENT_ENGINE_RESOURCE_NAME` at the resource it prints, then deploy the BFF
   and frontend containers (`cloudbuild/deploy.yaml` does all of this in CI).

## What's verified vs. not in this build

Being direct about this rather than claiming untested code works:

- **Fully executed and passing**: all 42 unit tests (`pytest tests/unit -v`), including every
  worked numeric example from the source spec (M1001–M1010), the rate-matcher's honest-miss and
  forced-clarification behavior, the numeric-provenance guardrail's formatting-divergence and
  fabrication-detection cases, IAP JWT verification (mocked), and session-minting logic.
- **Built and statically verified, not executed**: the ADK agent (`agent/csr_agent/agent.py`) and
  its three tools were constructed and their real function-declaration schemas inspected against
  the actual installed `google-adk` package (confirming `tool_context` is correctly excluded from
  the model-visible schema) — but never run against a live model or deployed Agent Engine
  resource. The BFF's FastAPI app imports and registers routes correctly but wasn't exercised
  end-to-end against a real Agent Engine or Postgres instance.
- **Written, not executed**: `tests/integration/` and `evals/run_eval.py`'s case assertions both
  need a reachable Postgres. This development sandbox blocks binding new listening sockets (even
  a disposable local Postgres instance failed with `could not bind... Permission denied`), so
  neither could be run here. `evals/run_eval.py`'s YAML parsing, argument handling, and per-case
  dispatch logic *were* verified (it runs and fails gracefully with a clear "no DATABASE_URL"
  message rather than crashing). **Run both in a normal CI environment or local machine before
  trusting them as a merge/deploy gate.**
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
