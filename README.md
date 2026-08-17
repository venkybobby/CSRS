# CSRSupport

An internal AI agent for Meridian Health Plans Customer Service Reps: type a plain-English
question plus a member ID, get back eligibility status and an auditable, deterministically
calculated out-of-pocket cost estimate. **CSR-internal only — not a patient/member-facing
product.** Full architecture: [docs/architecture/plan.md](docs/architecture/plan.md). Source
requirements: [docs/meridian_csr_estimator_MVP1_stories.md](docs/meridian_csr_estimator_MVP1_stories.md)
(v1.4, 8 user stories).

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

- **Seed corrected against Meridian's own rate sheet, and gated (2026-08-16)**: the workbook
  named as a source input in the spec had never been in the repo. Diffing against it found 8 of
  11 shared rates drifted, 4 of Meridian's procedures missing, and 3 seeded that Meridian never
  negotiated. The only correct rates were the three back-derived from worked examples. Nothing
  in the suite could have caught this — the numeric-provenance guardrail asks whether a figure
  came from a tool, and all of them had; the 18 deterministic cases passed identically before
  and after. `tests/unit/test_rate_sheet_source.py` is the only check that reads an artifact
  from outside the system. The post-deploy gate then passed **22/22** against Agent Engine
  `reasoningEngines/2985492378028081152` (build `4439a4d5`), the first deploy carrying the
  corrected seed.
- **Live verification against the deployed dev agent (2026-08-15)**: `run_eval.py --mode live`
  passed **20/20** against Agent Engine `reasoningEngines/2344521079499784192` in `csrs-504922`
  (`us-central1`) -- the 16 demo/regression cases plus all 4 adversarial cases, under a real
  model. This is the first run that establishes tool-call ORDER (eligibility before pricing) from
  the agent's own ADK session trace, which no offline test can show. The adversarial passes cover
  a direct override instruction, a fabricated-rate injection, an impersonated-supervisor request
  to skip the eligibility check (still returned TERMED_BLOCK), and a system-prompt disclosure
  request. Closes Verification Plan item 3; item 5 is now covered at the agent level but not
  through the UI.
- **Local verification against real Postgres (2026-08-14)**: the integration suite (17 passed) and
  the deterministic eval suite (16/16 cases) were executed against a disposable PostgreSQL 16
  container with the real migrations and `db/seed` applied, alongside 89 passing unit tests. This
  closes items 1-3 of [plan.md](docs/architecture/plan.md)'s Verification Plan, which previously
  read "written, not executed". At the time of this run live mode had not yet been executed (see
  the 2026-08-15 entry above, which closes it); its preflight was verified instead -- with
  `AGENT_ENGINE_RESOURCE_NAME` unset it fails hard (exit 1) rather than the old
  skip-and-report-success behaviour that let the post-deploy gate pass against any deployment at
  all. Client-facing summary: [docs/MVP1_STATUS.md](docs/MVP1_STATUS.md).
- **`cloudbuild/pr-checks.yaml` is fully green end-to-end against a real GCP project**
  (`csrs-504922`, build `1ae41168`, 9m35s): lint, typecheck, all 48 unit tests (including every
  worked numeric example from the source spec M1001–M1010, the numeric-provenance guardrail's
  formatting-divergence and fabrication-detection cases, and IAP JWT verification), all 17
  integration tests against real Postgres, the deterministic eval suite (all 6 demo-script
  cases), and all three container builds (bff/frontend/migrate). This development sandbox still
  can't bind a local Postgres to test against directly (a disposable instance failed with
  `could not bind... Permission denied`), so every DB-dependent piece was verified entirely
  through that real run, not here. Getting to green surfaced three genuine bugs no design or
  static-review pass had caught:
  1. `quote_audit_log`'s `PRIMARY KEY (audit_id)` on a table partitioned by `created_at` is
     rejected outright by Postgres (`FeatureNotSupported: unique constraint on partitioned table
     must include all partitioning columns`) -- fixed to a composite
     `PRIMARY KEY (audit_id, created_at)`.
  2. The integration-test fixture and `db/migrations/run_migrations.py` applied the schema
     through two different, silently-drifting code paths (one tracked in `schema_migrations`, one
     not), which broke the moment both ran against the same shared CI Postgres container --
     unified into one `apply_pending_migrations()` function both now call.
  3. `match_procedure()`'s fuzzy matching only worked on short isolated phrases ("MRI on his
     knee") -- every unit test used that shape of input, but the real demo-script questions are
     full CSR sentences ("M1002 wants an MRI on his knee, what does he owe?"), which scored far
     below the match threshold under the original scorer. The first fix attempt
     (`partial_token_set_ratio`) solved that but introduced a worse bug -- it scored "MRI on his
     back" as a 100% match against "MRI brain," a wrong-body-part cross-match that would produce
     the wrong CPT, rate, and prior-auth determination, not just bad UX. Landed on
     `token_set_ratio` plus stripping member-ID tokens before scoring, verified against both
     failure modes with new regression tests.
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
- **Verified in a real browser**: the frontend was built (`npm run build`, clean) and run against
  a mocked BFF response in an actual browser session, confirming the `demo_1` (partial deductible)
  and `demo_4` (termed member) cases render pixel-for-content-correct against the source spec's
  own Demo Script wording, with zero console errors. Those screens are captured in
  [docs/screenshots/](docs/screenshots/) and regenerated by
  `python scripts/capture_demo_screenshots.py`, which shoots two fixture routes — `/?preview`
  (date-of-service outcomes plus the prior-auth banner) and `/?preview=demo` (demo-script cases
  1–5). Both need only a vite dev server: no BFF, no agent, no database. Every pane shows the
  CSR's input — the question verbatim from the eval case, the member ID, and the date of service
  where one was stated — above the result it produced, and is stamped with the id of the case in
  `evals/demo_scripts.yaml` it depicts. Every pane now carries a real id: the prior-auth banner
  was the one exception, stamped "no eval case" because none triggered it, and
  `prior_auth_required_on_silver` closed that. A stamp naming a case that does not exist, or one
  about a different member or CPT, fails `tests/unit/test_preview_fixtures.py` — the label was
  honest about having no coverage, so anything replacing it has to be honest about having some.
  Every dollar figure was produced by running the real
  calculator against `db/seed`, and the figures that a case pins match its `expected_fields`.
  Re-run the script after any change to the result components — a stale screenshot is worse than
  none, because it reads as current.
- **Steering review deck**: [docs/demo/steering-cut.html](docs/demo/steering-cut.html) is a
  15-slide decision review for the client's steering committee, generated by
  `python scripts/build_demo_deck.py` from those same screenshots — inlined as data URIs, so the
  file is self-contained and opens from anywhere with no server. It is structured as a decision
  meeting rather than a demo: `ask → stakes → the one architectural decision → evidence →
  demonstrations → loops closed → what we do not claim → decisions → what the hour buys`. Three
  slides are refusals, the scoreboard's last row is the number of CSRs who have used it (zero),
  and the "what we are not claiming" slide volunteers six gaps rather than waiting to be asked.
  <kbd>N</kbd> toggles speaker notes (hidden by default so they stay out of a screen recording),
  <kbd>S</kbd> puts the whole narration on one page for a second monitor, <kbd>A</kbd> opens an
  objection appendix. Generated for the same reason the screenshots and fixtures are — so it
  cannot quietly disagree with what the components render. Re-run `capture_demo_screenshots.py`
  first, then this. Edit the narration in `SLIDES` in the script, never the generated HTML.
- **Client summary**: [docs/demo/client-summary.html](docs/demo/client-summary.html), generated by
  `python scripts/build_client_summary.py`. Same palette as the deck deliberately — same people,
  same system, same week — but a different posture: the deck is *presented* and opens with three
  asks, while this is *read alone and forwarded onward*, so it leads with what was decided and
  holds each screenshot inline beside the claim it supports. Regenerate after the screenshots.

  Pairing the ask with the answer is what makes these images checkable rather than decorative,
  and it immediately caught a fixture bug: the dated-yes pane claimed M1010 owed $470 with
  $1,200 of deductible met, but M1010's seeded accumulators are all $0.00, so the engine
  produces $1,150 with no coinsurance. The old figures were M1002's accumulator profile printed
  under George Ellery's name — invisible while only the output was shown.

  That bug is now structurally impossible rather than merely fixed. The fixtures are
  **generated**, not written: `python scripts/generate_preview_fixtures.py` builds
  `frontend/src/fixtures/previewPanes.json` from `db/seed` through the real calculator and from
  `evals/demo_scripts.yaml`, and `tests/unit/test_preview_fixtures.py` re-derives it on every CI
  run and fails if the committed copy differs. A changed rate, an edited accumulator, a
  calculator fix, or a reworded question in the eval file all break the build instead of quietly
  making the screenshots wrong. Only prose the engine does not own (refusal message text, audit
  ids) is still hand-written in the TSX.
- **Not done at all**: no GCP resources were created (no live Cloud SQL, Agent Engine, Cloud Run,
  or IAP resources) and no Terraform was applied — this stays code-only until you're ready to
  provision real infrastructure and review the cost/scope of doing so.

## Deliberate decisions the spec asked to see recorded here

**No deductible proration for mid-year coverage starts.** A member whose coverage begins
part-way through the plan year (M1008, `coverage_start` 2026-07-01) is subject to the *full*
plan-year deductible, not a prorated share of it. This matches standard plan design and is a
stated demo-scope assumption in the source spec, which asks specifically that it be recorded in
this README "as an explicit decision, not an oversight" — so: it is a decision. Nothing in the
calculator prorates, and nothing is missing. M1008 exists in `db/seed/members.json` to exercise
this path, not a particular cost scenario.

## A note on the spec's own internal inconsistency

The source spec ([docs/meridian_csr_estimator_MVP1_stories.md](docs/meridian_csr_estimator_MVP1_stories.md))
states in one place that M1006 and
M1007 "must produce different outputs" and that identical numbers would indicate a bug — but its
own worked Demo Script #3 shows both members owing exactly $1,860 for the same knee-surgery
query. Both are correct simultaneously once you separate "dollar total" (legitimately equal here,
since neither member's OOP cap binds at this rate) from "OOP position" (`oop_remaining` and
`triggering_threshold`, which do differ and are asserted as differing).
[tests/unit/test_calculator_family.py](tests/unit/test_calculator_family.py) encodes both: the
literal Demo Script #3 case, and a separate constructed higher-rate case where the totals *do*
diverge, which is what the spec's warning is actually guarding against (a wrong accumulator
join-key silently collapsing two members onto the same values).
