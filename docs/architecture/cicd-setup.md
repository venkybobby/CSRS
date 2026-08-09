# CI/CD Setup — Prerequisites and One-Time Manual Steps

`cloudbuild/pr-checks.yaml` and `cloudbuild/deploy.yaml` are the pipeline definitions.
`infra/modules/cicd/` is what wires them to GitHub as actual Cloud Build triggers. This
document is the ordered runbook for standing that up — split clearly into what Terraform
automates and what requires a human clicking through a browser once, because pretending the
whole thing is `terraform apply` would be dishonest. Do this once per environment
(dev/staging/prod are separate GCP projects, plan §6.1).

**Live demo on `csrs-504922`:** this project is a standalone GCP project under a personal
Google account — there is no GCP Organization. That changes two things everywhere below:
VPC Service Controls / Access Context Manager (`infra/modules/vpc_sc`) is an org-level-only
feature and stays **disabled** (`enable_vpc_sc = false`, the default); and the OAuth consent
screen IAP depends on can only run in **Testing** publishing status (see §6.5), which is fine
for a small named set of CSR test accounts and is what this runbook assumes. There's only one
real project, so point `infra/envs/dev` at it (`project_id = "csrs-504922"` in
`terraform.tfvars`) rather than standing up separate dev/staging/prod projects — staging/prod
configs stay unapplied until additional GCP projects exist. §0 through §6.5 provision that one
project end-to-end; §7 runs the 5 demo-script scenarios against it live.

## Why some of this can't be Terraform

Two things in this pipeline are inherently one-time, human, browser-based actions that no
tool — Terraform included — can safely script:

1. **Authorizing the Cloud Build GitHub App on the repo.** Connecting Cloud Build to GitHub
   requires GitHub OAuth consent, which only a human with admin rights on `venkybobby/CSRS`
   can grant, in a browser.
2. **Creating a GitHub PAT.** Cloud Build's 2nd-gen GitHub connection needs a personal access
   token stored in Secret Manager. Generating that token is a GitHub UI action.

Everything else below **is** Terraform-managed (`infra/modules/{cicd,artifact_registry,
cloud_run_job,cloud_sql}` etc.) — this doc just orders the manual steps around it correctly.

## 0. Enable required APIs

```bash
gcloud services enable \
    cloudbuild.googleapis.com \
    aiplatform.googleapis.com \
    sqladmin.googleapis.com \
    run.googleapis.com \
    iap.googleapis.com \
    artifactregistry.googleapis.com \
    vpcaccess.googleapis.com \
    secretmanager.googleapis.com \
    servicenetworking.googleapis.com \
    --project=csrsupport-dev
```
Repeat per environment project.

### 0.5. Grant the build execution identity storage access

Projects created after Google's Cloud Build default-service-account change run builds as the
**Compute Engine default service account** (`PROJECT_NUMBER-compute@developer.gserviceaccount.com`),
not the legacy dedicated Cloud Build SA — and that account doesn't automatically have access to
the auto-created `PROJECT_ID_cloudbuild` GCS bucket builds stage their source in. Skipping this
doesn't fail at `gcloud services enable` time; it fails the first time you actually submit a
build, with a `storage.objects.get` 403 on the `_cloudbuild` bucket. Grant it up front:

```bash
PROJECT_NUMBER=$(gcloud projects describe csrsupport-dev --format='value(projectNumber)')
gcloud projects add-iam-policy-binding csrsupport-dev \
    --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
    --role="roles/cloudbuild.builds.builder"
```
`roles/cloudbuild.builds.builder` is the role Google now recommends for whichever SA executes
builds — it covers source-bucket read/write, log writing, and the other baseline build
operations in one grant, rather than discovering each missing permission one 403 at a time.
Repeat per environment project. (If §3's Terraform later creates a dedicated `sa-cicd-build`
and you configure triggers to run *as* that SA instead of the default compute SA, this specific
grant becomes moot for triggered builds — but ad hoc `gcloud builds submit` runs still use the
default compute SA unless you pass `--service-account` explicitly, so keep it either way.)

## 1. One-time manual: connect GitHub to Cloud Build

In the GCP Console: **Cloud Build → Repositories → Connect Repository → GitHub**, and follow
the OAuth flow to install the **Google Cloud Build** GitHub App on `venkybobby/CSRS` (org- or
repo-scoped, your call — repo-scoped is tighter). Note the **installation ID** shown at the
end of the flow; `infra/envs/<env>/terraform.tfvars`'s `github_app_installation_id` needs it.

(The CLI equivalent, `gcloud builds connections create github`, still opens an interactive
browser OAuth prompt — there's no non-interactive path.)

## 2. One-time manual: create a GitHub PAT and store it in Secret Manager

**Must be a classic PAT** — confirmed against Cloud Build's own docs: "Cloud Build doesn't
support the use of GitHub fine-grained access tokens." A fine-grained token here fails silently
at `terraform apply` time with a misleading `google_cloudbuildv2_connection` error ("the user
token does not have access to installations"), not at token-creation time, so this is easy to
get wrong without ever seeing an obvious cause.

At **[github.com/settings/tokens](https://github.com/settings/tokens)**, use the
**"Tokens (classic)"** tab (not "Fine-grained tokens") → **Generate new token (classic)**, on
the same GitHub account that installs the Cloud Build GitHub App in §1. Scopes: `repo`
(full control of private repos), `read:user`, and `read:org` (needed even for a personal-account
repo — the GitHub App installation is checked via an org-shaped API regardless), then:

```bash
echo -n "<the PAT>" | gcloud secrets create csrsupport-github-pat \
    --project=csrsupport-dev --data-file=- --replication-policy=automatic
```

Grant the Cloud Build service agent (not `sa-cicd-build` — the *platform* service agent that
establishes the connection) read access:

```bash
PROJECT_NUMBER=$(gcloud projects describe csrsupport-dev --format='value(projectNumber)')
gcloud secrets add-iam-policy-binding csrsupport-github-pat \
    --project=csrsupport-dev \
    --member="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-cloudbuild.iam.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"
```
`infra/envs/<env>/terraform.tfvars`'s `github_pat_secret_id` = `csrsupport-github-pat`.

## 2.5. One-time manual: create the Terraform state bucket

`backend "gcs" { bucket = "csrsupport-dev-tfstate" }` in `infra/envs/dev/main.tf` tells
Terraform *where* to store state — it does not create that bucket. `terraform init` fails
outright against a bucket that doesn't exist yet. Create it once, before `init`:

```bash
gcloud storage buckets create gs://csrsupport-dev-tfstate \
    --project=csrs-504922 --location=us-central1 --uniform-bucket-level-access
gcloud storage buckets update gs://csrsupport-dev-tfstate --versioning
```
Versioning isn't optional polish here — it's the only rollback path if a bad `apply` corrupts
state. Repeat for staging/prod's own `*-tfstate` bucket names only once those environments'
projects actually exist.

## 2.6. One-time manual: create the Supabase project and bootstrap DB roles

Dev's database is Supabase Postgres, not Cloud SQL — a deliberate cost swap (Cloud SQL's
`db-custom-2-8192` tier runs ~$100+/mo continuously billed, plus ~$8-13/mo for a VPC connector
it also requires; a Supabase project on this org's Pro plan is $25/mo flat, shared across every
project in the org). Staging/prod are unaffected and still use Cloud SQL (`infra/envs/{staging,prod}`,
unchanged) — they aren't provisioned yet, so this asymmetry is fine for now.

None of this is Terraform-managed — Supabase project creation and role grants happen directly
against Supabase (dashboard or MCP), then the resulting connection strings get stored in GCP
Secret Manager for Cloud Run/Cloud Build to read, the same manual pattern already used for
`github_pat_secret_id` above. **This must run before §3's `terraform apply`** — unlike the old
Cloud SQL IAM bootstrap (which ran after `apply`, since Cloud SQL and its IAM users didn't
exist until Terraform created them), `main.tf` now has `google_secret_manager_secret_iam_member`
resources that reference these two secrets by name, so `apply` fails outright ("secret not
found") if they don't already exist.

1. **Create the project.** Org `SARO` on Supabase already has 2 free-tier projects
   (`SARO`, `cms-coverage-rag`) — creating a third requires either pausing one of those or
   upgrading the org to the Pro plan ($25/mo flat, covers all projects in the org). Name it
   `csrsupport-dev`, region `us-west-1` (matches the org's other projects).

2. **Bootstrap two least-privilege Postgres roles**, mirroring the same split Cloud SQL used
   (`db/bootstrap_iam_grants.sql`'s model, now password-based instead of GCP-IAM-based) — run
   [`db/bootstrap_supabase_roles.sql`](../../db/bootstrap_supabase_roles.sql) once against the
   new project (Supabase SQL Editor, or the `execute_sql` MCP tool) after filling in two
   generated passwords:
   - `csrsupport_migrate` — DDL rights, used only by the migration Cloud Run Job.
   - `csrsupport_agent_engine` — SELECT/INSERT-only, used by the running agent. Never used for
     schema changes, matching the same reasoning `bootstrap_iam_grants.sql` documents.

3. **Store both as full `postgresql+pg8000://` connection strings** in Secret Manager, using
   Supavisor's **session-mode** pooler (port `5432`, not the transaction-mode `6543`) — Cloud
   Run's scale-to-zero means many container instances can open connections near-simultaneously,
   which is what pooling is for, but transaction mode drops session-level state (e.g.
   `csr_agent.data.db.get_engine()`'s `isolation_level="REPEATABLE READ"`) between transactions,
   which session mode preserves. The pooler username is **not** just the role name — Supavisor
   multiplexes every project through one shared host, so it must be `<role>.<project-ref>`
   (e.g. `csrsupport_migrate.tmhuklbjpbblnwoiyjjo`), confirmed against Supabase's own docs
   rather than assumed:

   ```bash
   echo -n "postgresql+pg8000://csrsupport_migrate.<project-ref>:<password>@aws-0-us-west-1.pooler.supabase.com:5432/postgres" | \
       gcloud secrets create csrsupport-migrate-dev-db-url --project=csrs-504922 --data-file=-
   echo -n "postgresql+pg8000://csrsupport_agent_engine.<project-ref>:<password>@aws-0-us-west-1.pooler.supabase.com:5432/postgres" | \
       gcloud secrets create csrsupport-agent-engine-dev-db-url --project=csrs-504922 --data-file=-
   ```

   Set `migrate_db_url_secret_id = "csrsupport-migrate-dev-db-url"` and
   `agent_engine_db_url_secret_id = "csrsupport-agent-engine-dev-db-url"` in `terraform.tfvars`
   — `terraform apply` (§3) grants `sa-migrate-dev` and `sa-cicd-build-dev` (which reads the
   agent-engine secret at deploy time to inject `DATABASE_URL` into `deploy_agent_engine.py` —
   see `cloudbuild/deploy.yaml`'s `availableSecrets`) accessor IAM on the matching secret.

## 3. Terraform apply

```bash
cd infra/envs/dev
cp terraform.tfvars.example terraform.tfvars
# fill in every value, including steps 1-2's outputs, AND override project_id/region for the
# standalone project:
#   project_id = "csrs-504922"
terraform init
terraform plan     # review — creates real, billed resources including two service accounts
                    # holding elevated IAM (sa-cicd-build, sa-migrate)
terraform apply
```

This provisions (see `infra/modules/cicd/main.tf` for the exact resources): the
`sa-cicd-build` service account and its least-privilege grants, the `google_cloudbuildv2_connection`
/ `google_cloudbuildv2_repository` linking to GitHub, and three triggers —
`csrsupport-pr-checks-dev` (on pull_request), `csrsupport-deploy-dev` (on push to `master`, no
approval gate), and (in the staging/prod environments) `csrsupport-deploy-staging` /
`csrsupport-deploy-prod` (also on push to `master`, but **approval-gated** — see below). It also
creates the Artifact Registry repo, the Agent Engine staging bucket, and the migration Cloud
Run Job (with a placeholder image).

`bff_image`/`frontend_image` also carry a placeholder default
(`us-docker.pkg.dev/cloudrun/container/hello`) so this first `apply` doesn't fail on a Cloud
Run requirement that an image already exist — `cloudbuild/deploy.yaml` overwrites both with
real images on the first CI/CD deploy run.

VPC-SC stays off (`enable_vpc_sc` defaults `false`) — leave `terraform.tfvars` alone on that
var unless `csrs-504922` later joins a GCP Organization.

**No VPC/networking module for dev.** `infra/modules/networking` (VPC, subnet, private-services
peering, Serverless VPC Access connector) and `infra/modules/cloud_sql` existed solely to give
Cloud Run private-IP access to a GCP Cloud SQL instance. Dev's database is Supabase Postgres
instead (see §2.6, which must run *before* this section — the secret IAM bindings below
require both secrets to already exist) — reached over the public internet with TLS, like any
external SaaS Postgres — so neither module is used in `infra/envs/dev`. This was a deliberate
cost swap: Cloud SQL's `db-custom-2-8192` tier runs ~$100+/mo continuously billed, plus
~$8-13/mo for the VPC connector's `min_instances = 2`; a Supabase project on this org's Pro
plan is $25/mo flat, shared across every project in the org rather than per-database.
Staging/prod still use Cloud SQL (`infra/envs/{staging,prod}`, unchanged) — they aren't
provisioned yet, so this asymmetry is fine for now; revisit if/when they're stood up for real.

## 5. Grant build-approval permissions (staging/prod only)

The staging/prod triggers use Cloud Build's native `approval_config.approval_required` (plan
§6.3's "manual approval (Dana/eng lead)") — a build queues on push to `master` but sits in
`PENDING_APPROVAL` until someone approves it. Grant that specifically:

```bash
gcloud projects add-iam-policy-binding csrsupport-staging \
    --member="group:csrsupport-approvers@meridianhealthplans.com" \
    --role="roles/cloudbuild.builds.approver"
```
Repeat for `csrsupport-prod` (can be the same or a stricter group — e.g. prod's approvers
could be a subset of staging's). This is independent from `roles/cloudbuild.builds.editor`
(who can invoke/view triggers at all) — grant that separately, more broadly, to your eng team.

## 6. First deploy — breaking the circular dependencies

Two pairs of values are circular on a from-scratch environment: the BFF's
`IAP_EXPECTED_AUDIENCE` needs the IAP backend service Terraform just created, and its
`AGENT_ENGINE_RESOURCE_NAME` needs an Agent Engine resource that only exists after the first
successful `csrsupport-deploy-dev` run. Break the cycle in this order:

1. Push to `master` (or `gcloud builds triggers run csrsupport-deploy-dev-... --branch=master`) —
   the first run's `deploy-bff` step will set `AGENT_ENGINE_RESOURCE_NAME` correctly (it reads
   `/workspace/agent_engine_resource_name.txt`, written earlier in the same build by
   `deploy_agent_engine.py`), so this part self-resolves on the very first CI/CD run.
2. `IAP_EXPECTED_AUDIENCE` doesn't self-resolve — after step 1, run
   `terraform output` (or check the Console) for the IAP backend service's numeric ID, format
   it as `/projects/<PROJECT_NUMBER>/global/backendServices/<BACKEND_SERVICE_ID>`, set it as
   `iap_expected_audience` in `terraform.tfvars`, and `terraform apply` again (or
   `gcloud run services update csrsupport-bff-dev --update-env-vars=...` directly, which is
   faster for a one-off fix — Terraform will just reconcile to the same value next apply).

## 6.5. One-time manual: configure the IAP OAuth consent screen (standalone project)

`infra/modules/iap` creates the IAP-enabling resources, but the underlying OAuth consent
screen it depends on has to be configured once per project through the Console (it isn't a
Terraform-manageable resource) — **APIs & Services → OAuth consent screen**:

1. **User type: Internal** is normally the easy path, but Internal requires a Google
   Workspace organization — a standalone personal-account project doesn't have one, so this
   project must use **External**.
2. Publishing status: leave it in **Testing**, not Production. Production triggers Google's
   verification review (a multi-week process meant for public-facing apps requesting broad
   scopes); Testing skips that entirely and is the correct, honest choice for a CSR-internal
   tool with a handful of named users.
3. Under **Test users**, add the exact CSR test accounts (Google accounts) that will click
   through IAP during the demo — Testing mode's consent screen only lets listed test users
   past it, everyone else gets blocked at Google's login step before even reaching IAP.
4. Grant `roles/iap.httpsResourceAccessor` on the BFF/frontend Cloud Run services to the same
   accounts (or to a Google Group containing them, matching plan §4) — the OAuth consent
   screen controls who can *authenticate*, IAP's IAM binding controls who's *authorized* after
   that; both gates have to pass.

Skipping this doesn't fail at `terraform apply` — it fails the first time a CSR opens the
frontend URL, with Google's consent screen rejecting them as an untested user.

## 7. Run the 5 demo-script scenarios live

Once §6's circular-dependency fixups land and a real `deploy` build has gone green, verify the
whole thing works by walking through `evals/demo_scripts.yaml`'s cases in the browser (open the
frontend Cloud Run URL — IAP will bounce you through Google login, use one of §6.5's test
accounts) exactly as a CSR would type them:

| # | Type this | Expect |
|---|---|---|
| 1 | `M1002 wants an MRI on his knee, what does he owe?` | `STANDARD_COST` — $470.00 member cost (partial deductible + coinsurance) |
| 2 | `What's James Whitaker M1004 looking at for knee surgery?` | `STANDARD_COST` — $150.00 member cost, OOP max triggered |
| 3 | `Same question for M1007 and M1006 — knee surgery` (ask once for M1006, once for M1007) | Both `STANDARD_COST`, both $1,860.00 member cost, but `triggering_threshold` differs (`INDIVIDUAL` vs `FAMILY`) and `oop_remaining` differs ($3,100.00 vs $6,100.00) — this is the embedded-family divergence check, see the note in `evals/demo_scripts.yaml` |
| 4 | `M1005 — anything, what do they owe?` | `TERMED_BLOCK` — mentions Priya Raman and a 2026-05-31 coverage end, no dollar figure at all |
| 5 | `Cardiac CT for M1003` | `RATE_NOT_FOUND` — an honest "don't have a negotiated rate for that" miss, not a guess |

For each case, also open the `audit_id` reference the UI shows and confirm
`SELECT * FROM quote_audit_log WHERE audit_id = '<id>'` (via `gcloud sql connect`) returns a
row with the exact same figures — that round-trip from UI back to the audit table is the actual
thing being demoed, not just "the agent answered correctly." If any case instead shows the
guardrail's "transfer to supervisor" fallback message, check Cloud Logging for a
`GUARDRAIL_VIOLATION` entry before assuming the demo data is wrong — that's the numeric-
provenance layer doing its job, and it means a real mismatch between what the model said and
what the tool actually returned.

## Summary: automated vs. manual

| Step | Mechanism |
|---|---|
| Enable APIs | manual (`gcloud services enable`, once) |
| Grant build execution identity storage access | manual (`gcloud`, once, §0.5) |
| GitHub App install | manual, browser OAuth (§1) |
| GitHub PAT + Secret Manager | manual (§2) |
| Terraform state bucket | manual (`gcloud storage buckets create`, once, §2.5) |
| Supabase project + DB role bootstrap + Secret Manager secrets | manual, once, dashboard/SQL/`gcloud` (§2.6, before §3) |
| Cloud Run, Artifact Registry, IAM, Cloud Build triggers | `terraform apply` (§3) |
| Build-approver IAM | manual (`gcloud`, §5) |
| First-deploy circular-dependency fixups | manual, once, `terraform apply` or `gcloud run services update` (§6) |
| IAP OAuth consent screen (Testing mode, test users) | manual, browser, once (§6.5) |
| Everything after that — build, test, deploy, migrate, eval | fully automated, `cloudbuild/{pr-checks,deploy}.yaml` |
| The 5 demo-script scenarios | manual walkthrough, once deployed (§7) |
