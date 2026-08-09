-- One-time bootstrap for a fresh csrsupport-dev Supabase project. Run this
-- ONCE, right after the project is created and BEFORE the first
-- migration/deploy runs -- via the Supabase SQL Editor or the
-- `execute_sql` MCP tool, using the project's privileged connection.
--
-- Mirrors db/bootstrap_iam_grants.sql's least-privilege split (see that
-- file's comments for the full rationale) -- the only difference is the
-- auth mechanism: Cloud SQL used GCP IAM database users with no password
-- anywhere; Supabase is a standalone Postgres instance, so these are
-- ordinary password-based roles instead. Same two-principal design:
-- schema migrations and the running agent must never share a DB identity.
--
-- Replace <MIGRATE_PASSWORD> / <AGENT_ENGINE_PASSWORD> with generated
-- passwords before running (e.g. `openssl rand -base64 24`), then store
-- the resulting full connection strings in Secret Manager as
-- csrsupport-migrate-dev-db-url / csrsupport-agent-engine-dev-db-url --
-- see docs/architecture/cicd-setup.md §4. Do not commit real passwords.

-- csrsupport_migrate: owns schema evolution. Needs to CREATE/ALTER tables,
-- run DDL. Used only by the migration Cloud Run Job, never the running
-- agent.
CREATE ROLE csrsupport_migrate WITH LOGIN PASSWORD '<MIGRATE_PASSWORD>';
GRANT CREATE ON SCHEMA public TO csrsupport_migrate;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO csrsupport_migrate;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT ALL PRIVILEGES ON TABLES TO csrsupport_migrate;

-- csrsupport_agent_engine: the running application's identity. Read-mostly
-- by design (plan §4: "SELECT/INSERT-only DB role -- no DDL/DELETE").
-- Re-run the two ALTER DEFAULT PRIVILEGES lines below (only those two --
-- not the whole file) after any migration that adds a new table, so the
-- new table is covered without a manual grant every time.
CREATE ROLE csrsupport_agent_engine WITH LOGIN PASSWORD '<AGENT_ENGINE_PASSWORD>';
GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA public TO csrsupport_agent_engine;
-- UPDATE is intentionally omitted -- the app never updates existing rows,
-- only inserts new ones (see agent/csr_agent/data/audit.py,
-- pipeline/estimate.py). If a future migration needs UPDATE somewhere,
-- grant it explicitly on that one table, not broadly.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT ON TABLES TO csrsupport_agent_engine;
