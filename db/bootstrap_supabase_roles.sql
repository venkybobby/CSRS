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
-- see docs/architecture/cicd-setup.md §2.6. Do not commit real passwords.

-- csrsupport_migrate: owns schema evolution. Needs to CREATE/ALTER tables,
-- run DDL. Used only by the migration Cloud Run Job, never the running
-- agent.
CREATE ROLE csrsupport_migrate WITH LOGIN PASSWORD '<MIGRATE_PASSWORD>';
GRANT CREATE ON SCHEMA public TO csrsupport_migrate;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO csrsupport_migrate;

-- csrsupport_agent_engine: the running application's identity. Read-mostly
-- by design (plan §4: "SELECT/INSERT-only DB role -- no DDL/DELETE").
CREATE ROLE csrsupport_agent_engine WITH LOGIN PASSWORD '<AGENT_ENGINE_PASSWORD>';
-- No-op the first time this runs against a brand-new project (no tables
-- exist yet -- migrations haven't run). Re-run this one line (only this
-- line) after the first migration, and after any later migration that
-- adds a new table, so the new table is covered without waiting on the
-- default-privileges rule below to catch it (belt-and-suspenders: the
-- rule below should already cover it, but this makes the grant explicit
-- and immediate rather than relying on remembering step 2 ran correctly).
GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA public TO csrsupport_agent_engine;
-- UPDATE is intentionally omitted -- the app never updates existing rows,
-- only inserts new ones (see agent/csr_agent/data/audit.py,
-- pipeline/estimate.py). If a future migration needs UPDATE somewhere,
-- grant it explicitly on that one table, not broadly.

-- ============================================================================
-- STEP 2 -- run separately, connected AS csrsupport_migrate itself, not as
-- the privileged/admin connection used above.
--
-- `ALTER DEFAULT PRIVILEGES [FOR ROLE x] ...` sets the default grant for
-- objects a role creates in the future -- but it only takes effect for
-- objects created by whichever role actually RAN the ALTER statement
-- (or the role named in FOR ROLE, if you have permission to name one you
-- aren't -- ordinary roles don't). Running this as the admin/privileged
-- connection sets defaults for objects THAT ADMIN ROLE creates, not for
-- tables csrsupport_migrate creates via db/migrations/*.sql -- a real bug
-- found live: every query failed with "permission denied for table
-- members" because this exact mistake meant the migration-created tables
-- never picked up csrsupport_agent_engine's SELECT/INSERT grant at all.
--
--   DATABASE_URL="postgresql+pg8000://csrsupport_migrate.<project-ref>:<password>@<pooler-host>:5432/postgres" \
--       python -c "
--   from sqlalchemy import create_engine, text
--   import os
--   engine = create_engine(os.environ['DATABASE_URL'])
--   with engine.begin() as conn:
--       conn.execute(text('ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT ON TABLES TO csrsupport_agent_engine'))
--   "
--
-- After this runs once, every future table csrsupport_migrate creates via
-- a normal migration automatically carries csrsupport_agent_engine's
-- SELECT/INSERT grant -- no more manual re-granting per migration.
-- ============================================================================
