-- CSRSupport MVP1 schema. See plan §3 for the rationale (Postgres over
-- Firestore) and docs/architecture/future-integration.md for the migration
-- path to real eligibility/claims systems.

CREATE TABLE plans (
    plan_id                         text PRIMARY KEY,
    display_name                    text NOT NULL,
    deductible_individual           numeric(10,2) NOT NULL,
    deductible_family               numeric(10,2) NOT NULL,
    coinsurance_pct                 numeric(4,3) NOT NULL,
    oop_max_individual              numeric(10,2) NOT NULL,
    oop_max_family                  numeric(10,2) NOT NULL,
    preventive_covered_100pct_codes text[] NOT NULL DEFAULT '{}',
    prior_auth_required_codes       text[] NOT NULL DEFAULT '{}',
    excluded_codes                  text[] NOT NULL DEFAULT '{}'
);

CREATE TABLE rate_sheet (
    cpt_code        text PRIMARY KEY,
    common_name     text NOT NULL,
    search_aliases  text[] NOT NULL DEFAULT '{}',
    -- Nullable by design: a code can be identifiable/matchable (so
    -- resolve_procedure can route to it and a plan's excluded_codes check
    -- can fire) without Meridian having negotiated a payable rate for it.
    -- This is how CPT S8092 (Story 6) resolves correctly: Bronze excludes
    -- it (exclusion check runs, and fires, before any rate is needed), while
    -- Silver/Gold are not excluded and fall through to a real rate lookup
    -- that legitimately finds none -- "rate not on file", a different fact
    -- from "excluded", per Dana's explicit requirement that these produce
    -- distinct CSR scripts.
    negotiated_rate numeric(10,2) NULL
);

CREATE TABLE members (
    member_id       text PRIMARY KEY,
    first_name      text NOT NULL,
    last_name       text NOT NULL,
    plan_id         text NOT NULL REFERENCES plans(plan_id),
    tier            text NOT NULL CHECK (tier IN ('INDIVIDUAL', 'FAMILY')),
    family_id       text NULL,
    status          text NOT NULL CHECK (status IN ('ACTIVE', 'TERMED')),
    coverage_start  date NOT NULL,
    coverage_end    date NULL  -- NULL = open-ended; set = past or future term date
);

CREATE INDEX idx_members_family_id ON members(family_id) WHERE family_id IS NOT NULL;

CREATE TABLE member_accumulators (
    member_id    text PRIMARY KEY REFERENCES members(member_id),
    ind_ded_met  numeric(10,2) NOT NULL DEFAULT 0,
    ind_oop_met  numeric(10,2) NOT NULL DEFAULT 0,
    fam_ded_met  numeric(10,2) NOT NULL DEFAULT 0,
    fam_oop_met  numeric(10,2) NOT NULL DEFAULT 0
);

CREATE TABLE quote_audit_log (
    -- Postgres requires a partitioned table's PRIMARY KEY (or any unique
    -- constraint) to include every column in the partition key -- audit_id
    -- alone as PK was rejected outright at CREATE TABLE time with
    -- "unique constraint on partitioned table must include all
    -- partitioning columns" the first time this schema ran against a real
    -- Postgres. Composite (audit_id, created_at) satisfies that;
    -- audit_id is still generated fresh via gen_random_uuid() on every
    -- insert and never reused, so this doesn't meaningfully weaken
    -- uniqueness in practice. One operational tradeoff worth knowing: a
    -- partitioned table's PK index is local to each partition, so
    -- `WHERE audit_id = ...` without a created_at filter (the audit-lookup
    -- pattern in plan §4.6) checks each partition's local index rather
    -- than routing to one partition directly -- fine at MVP1's partition
    -- count (monthly), worth revisiting only if retention grows to
    -- hundreds of partitions.
    audit_id              uuid NOT NULL DEFAULT gen_random_uuid(),
    created_at            timestamptz NOT NULL DEFAULT now(),
    csr_user_id           text NOT NULL,
    session_id            text NOT NULL,
    invocation_id         text NOT NULL,
    trace_id              text NOT NULL,
    member_id             text NOT NULL,
    cpt_code              text NULL,
    response_type         text NOT NULL,
    request_snapshot      jsonb NOT NULL,
    result_snapshot       jsonb NOT NULL,
    source_data_snapshot  jsonb NOT NULL,
    PRIMARY KEY (audit_id, created_at)
) PARTITION BY RANGE (created_at);

-- Partition-per-month from day one (plan §4: retention/deletion later is a
-- partition-drop, not a scan-and-delete). Seed script creates the first
-- partition; a scheduled job (not built in MVP1) creates future ones.
CREATE TABLE quote_audit_log_2026_08 PARTITION OF quote_audit_log
    FOR VALUES FROM ('2026-08-01') TO ('2026-09-01');

CREATE INDEX idx_audit_member_id ON quote_audit_log(member_id);
CREATE INDEX idx_audit_csr_user_id ON quote_audit_log(csr_user_id);
CREATE INDEX idx_audit_response_type ON quote_audit_log(response_type);
