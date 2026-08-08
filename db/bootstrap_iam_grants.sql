-- One-time, manually-run bootstrap for a fresh Cloud SQL instance. This is
-- NOT applied by Terraform or by db/migrations/run_migrations.py -- it has
-- to run before either of them, using a privileged connection (Cloud SQL
-- Studio in the console, or `gcloud sql connect <instance> --user=postgres`),
-- because IAM database users start with no privileges at all and something
-- has to grant the first ones. This is the one unavoidable manual step in
-- an otherwise password-free (IAM-auth-only) design -- see
-- docs/architecture/cicd-setup.md.
--
-- Run this ONCE per environment, immediately after `terraform apply`
-- creates the Cloud SQL instance and its two IAM database users
-- (sa-migrate-<env>, sa-agent-engine-<env>), and BEFORE the first
-- migration/deploy runs.
--
-- Replace the two placeholder identities with the real IAM user names
-- Terraform created (terraform output migrate_service_account_email /
-- agent_engine_service_account_email) -- Cloud SQL IAM usernames drop the
-- ".gserviceaccount.com" suffix.

-- sa-migrate: owns schema evolution. Needs to CREATE/ALTER tables, run DDL.
GRANT CREATE ON SCHEMA public TO "sa-migrate-ENV@PROJECT_ID.iam";
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO "sa-migrate-ENV@PROJECT_ID.iam";
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT ALL PRIVILEGES ON TABLES TO "sa-migrate-ENV@PROJECT_ID.iam";

-- sa-agent-engine: the running application's identity. Read-mostly by
-- design (plan §4: "SELECT/INSERT-only IAM DB role -- no DDL/DELETE").
-- Re-run the two ALTER DEFAULT PRIVILEGES lines below (only those two --
-- not the whole file) after any migration that adds a new table, so the
-- new table is covered without a manual grant every time.
GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA public TO "sa-agent-engine-ENV@PROJECT_ID.iam";
-- UPDATE is intentionally included only on quote_audit_log's source columns
-- is unnecessary -- the app never updates existing rows, only inserts new
-- ones (see agent/csr_agent/data/audit.py, pipeline/estimate.py). If a
-- future migration needs UPDATE somewhere, grant it explicitly on that one
-- table, not broadly.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT ON TABLES TO "sa-agent-engine-ENV@PROJECT_ID.iam";
