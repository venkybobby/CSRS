# Future Integration Path (Not Built in MVP1)

This is a documented stub, per plan §3.3/§9 -- it records the intended
migration path so a later phase doesn't have to rediscover it, and so
implementers don't accidentally hard-code assumptions that only the
synthetic MVP1 sample data will ever exist. **Nothing in this document is
built.** MVP1 ships against `db/seed/*.json` only.

## What stays the same

The tool-layer and calculator-layer contracts are the interface a future
phase integrates against, unchanged:

- `agent/csr_agent/tools/models.py`'s Pydantic types (`EligibilityResult`,
  `ProcedureMatchResult`, `CostBreakdown`, the `CostEstimateResult` union)
- `agent/csr_agent/calculator/{individual,family}.py`'s pure
  `(PlanTerms, RateInfo, MemberAccumulators) -> CostBreakdown` signatures
- `agent/csr_agent/pipeline/estimate.py`'s eligibility -> exclusion ->
  preventive -> prior-auth -> calculator ordering

None of this needs to change when the data source behind it changes. That's
deliberate -- it's what makes the migration a data-source swap, not a
rewrite.

## What would change

Only `agent/csr_agent/data/eligibility.py` and
`agent/csr_agent/data/rate_matcher.py`'s query functions
(`get_eligibility`, `get_plan`, `get_member_accumulators`, `get_rate`) would
be re-pointed from direct Postgres queries to:

1. Calling Meridian's real eligibility/claims/rate systems (whatever those
   turn out to be -- likely a claims platform or a FHIR-adjacent API,
   per Dana's scoping call), and
2. Caching the results into the *same* `members` / `plans` / `rate_sheet` /
   `member_accumulators` tables as a TTL'd materialized read layer, so the
   rest of the system (pipeline, calculator, audit log, frontend) doesn't
   need to know or care that the data source changed underneath it.

This is why Cloud SQL/Postgres was chosen over Firestore in the first place
(plan §3): a relational schema is a much closer shape-match to what a real
claims/eligibility API is likely to expose than a document store would be.

## Explicitly out of scope for this future phase too

Restating plan §9's non-goals, because "future integration" should not be
read as "eventually build these":

- CRM integration (a separate system entirely, not a data-source swap)
- Prior-auth *submission* (the system only ever flags a requirement, never
  submits or tracks an actual authorization)
- Any member/patient-facing interface (CSRSupport is confirmed CSR-internal;
  a patient-facing surface would be a different product with a different
  threat model, auth model, and liability framing -- not an extension of
  this one)
- Multi-procedure bundles, grievance/escalation tracking, and a
  finance-facing rate-sheet update workflow

## Open question, not resolved here

`quote_audit_log` retention policy (plan §4.4) is flagged for Dana --
commonly 6-7 years for health-plan records, not decided at MVP1 build time.
The schema partitions by `created_at` month from day one specifically so
that whatever the real answer turns out to be, applying it later is a
partition-drop, not a schema migration.
