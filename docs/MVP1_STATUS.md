# CSRSupport MVP1 — Status

**Meridian Health Plans · CSR-internal Cost Estimator**
Prepared for: Dana Whitfield (Meridian) · Status as of 2026-08-14

This is a build-status summary, not a sign-off. Everything below separates
**what has been executed and observed** from **what is written but not yet
run**, because the difference matters more than a percentage would.

---

## Headline

All eight user stories are implemented, and the behaviour they specify is
verified by tests that run against a real PostgreSQL database. What is *not*
yet done is anything requiring live cloud infrastructure: no GCP resources
have been provisioned, so the agent has never run against a real model, and
nobody has logged into a deployed frontend.

MVP1 is **code-complete and locally verified. It is not deployed.**

---

## What is verified, with evidence

| Check | Result |
|---|---|
| Unit suite (`pytest tests/unit`) | **89 passed** |
| Integration suite (`pytest tests/integration`) | **17 passed**, against real Postgres 16 |
| Deterministic eval suite (`evals/run_eval.py`) | **16/16 cases passed**, against real Postgres 16 |
| Frontend typecheck · lint · production build | clean |
| Python lint (`ruff`) | clean |

The integration and eval suites were run against a disposable PostgreSQL 16
instance with the real migrations and `db/seed` data applied — not mocks, and
not a developer's own database.

The 16 eval cases cover the five demo-script scenarios plus regressions for
the clarify gate, the exclusion-vs-no-rate distinction, and every
date-of-service outcome.

### The numbers a supervisor would want to trace

The eval suite pins these to the source spec's own worked examples, and they
are reproduced in the screenshots:

- **Demo 1** — M1002, MRI knee: `$300` to deductible, `$850` balance, 20%
  coinsurance = `$170`, member owes **`$470`**
- **Demo 2** — M1004, knee surgery: `$1,860` of coinsurance owed on paper,
  but only `$150` of out-of-pocket room left, so member owes **`$150`**
- **Demo 3** — M1006 and M1007, same family, same procedure: both owe
  **`$1,860`**, but their out-of-pocket positions differ (`$3,100` vs
  `$6,100`) and they exit the deductible phase by *different* thresholds
  (individual vs family). The spec warns that identical outputs would
  indicate a broken per-member lookup; the differing rows are what show it
  is not broken.

---

## Story 6 — the exclusion vs. no-rate distinction

This was called out as an explicit requirement: *"not a covered benefit"* and
*"we have no rate on file"* are different regulatory facts requiring
different CSR scripts, and must never look the same on screen.

It is now demonstrable rather than asserted. The same procedure code
(**S8092, acupuncture**) is asked of two members on different plans:

| Plan | Screen | CSR is told |
|---|---|---|
| Bronze (excludes S8092) | **Not a Covered Benefit** | Escalate to Member Services — a member-rights disclosure applies |
| Silver (no rate on file) | **No Rate On File** | Transfer to a supervisor, or call back with a confirmed cost |

Different component, different colour, different icon, different instruction
— from the same input. The two screens are captured side by side in
`docs/screenshots/exclusion-bronze.png` and
`docs/screenshots/rate-not-found-silver.png`.

This is structural, not cosmetic: the two outcomes are different types in the
API response, so they *cannot* render as the same component.

---

## Screenshots

`docs/screenshots/` holds 16 images covering every screen a CSR can currently
reach: the five demo-script cases, the Story 6 pair, preventive-at-100%, the
four date-of-service outcomes, and the prior-authorisation warning.

Each shows **the question the CSR typed above the answer it produced**, and
is stamped with the id of the automated test case that pins its figures. They
are regenerated from the engine rather than hand-assembled, so they cannot
quietly drift from what the system actually does.

---

## What is NOT done

Stated plainly, because these are the items that decide whether a demo can be
scheduled:

1. **No infrastructure exists.** No Cloud SQL, Agent Engine, Cloud Run, or
   IAP resources have been created, and no Terraform has been applied. The
   configuration is written and reviewed but never executed against a real
   project.
2. **The agent has never run against a live model.** Its tools and their
   schemas were verified statically. Tool-call *ordering* under a real model
   — the property that guarantees eligibility is always checked before a cost
   is quoted — is checked by the live eval mode, which cannot run until a
   deployment exists.
3. **No adversarial test against a live model.** The guardrail that blocks a
   fabricated dollar figure is unit-tested, but no prompt injection has been
   attempted end-to-end.
4. **No CSR has used it.** No IAP login, no audit-log entry resolved from the
   UI.

Items 2–4 are all blocked by item 1 and cannot be closed by further coding.

---

## Open question needing a Meridian decision

**How long must `quote_audit_log` records be retained?**

This has been flagged as an open question since the architecture plan and is
still unanswered. Health-plan records are commonly kept 6–7 years, but we
should not guess on Meridian's behalf.

It is **not blocking the build**: the audit table is partitioned by month
from day one specifically so that whatever the answer turns out to be,
applying it later is a partition drop rather than a schema migration and data
backfill. But it should be settled before production data accumulates.

---

## Deliberate scope boundaries

Restated so there is no ambiguity about what MVP1 does *not* attempt: no CRM
integration, no connection to real eligibility/claims/rate systems (synthetic
sample data only), no prior-authorisation *submission* — the system only ever
flags that authorisation is required — no member- or patient-facing
interface, no multi-procedure bundles, and no rate-sheet update workflow.

The system also never lets the language model produce a dollar figure. Every
amount shown comes verbatim from a deterministic calculation, and a guardrail
blocks any figure in a response that cannot be traced to one.

---

## Suggested next step

Provisioning the `dev` environment is the single change that unblocks
everything in the "not done" list. That is a cost and access decision rather
than an engineering one, and it needs Meridian's go-ahead before anything is
created.
