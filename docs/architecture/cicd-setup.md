# CI/CD Setup — Prerequisites and One-Time Manual Steps

`cloudbuild/pr-checks.yaml` and `cloudbuild/deploy.yaml` are the pipeline definitions.
`infra/modules/cicd/` is what wires them to GitHub as actual Cloud Build triggers. This
document is the ordered runbook for standing that up — split clearly into what Terraform
automates and what requires a human clicking through a browser once, because pretending the
whole thing is `terraform apply` would be dishonest. Do this once per environment
(dev/staging/prod are separate GCP projects, plan §6.1).

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

Create a **fine-grained PAT** on `venkybobby/CSRS` with `Contents: Read-only` and
`Metadata: Read-only` (that's all Cloud Build needs to read the repo — resist the urge to grant
more), then:

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

## 3. Terraform apply

```bash
cd infra/envs/dev
cp terraform.tfvars.example terraform.tfvars   # fill in every value, including steps 1-2's outputs
terraform init
terraform plan     # review — creates real, billed resources including two service accounts
                    # holding elevated IAM (sa-cicd-build, sa-migrate)
terraform apply
```

This provisions (see `infra/modules/cicd/main.tf` for the exact resources): the
`sa-cicd-build` service account and its least-privilege grants, the `google_cloudbuildv2_connection`
/ `google_cloudbuildv2_repository` linking to GitHub, and three triggers —
`csrsupport-pr-checks-dev` (on pull_request), `csrsupport-deploy-dev` (on push to `main`, no
approval gate), and (in the staging/prod environments) `csrsupport-deploy-staging` /
`csrsupport-deploy-prod` (also on push to `main`, but **approval-gated** — see below). It also
creates the Artifact Registry repo, the Agent Engine staging bucket, the migration Cloud Run
Job (with a placeholder image), and `sa-migrate`'s Cloud SQL IAM database user.

## 4. One-time manual: bootstrap the IAM database grants

A fresh Cloud SQL instance's IAM database users start with **zero privileges** — something has
to grant the first ones, and that something can't be `sa-migrate` itself (chicken-and-egg) or
Terraform (Cloud SQL Postgres table/schema grants aren't part of `google_sql_user`'s Terraform
resource). Connect once with a privileged identity and run
[`db/bootstrap_iam_grants.sql`](../../db/bootstrap_iam_grants.sql) (fill in the two placeholder
identities from `terraform output migrate_service_account_email` /
`terraform output agent_engine_service_account_email` first — and remember Cloud SQL IAM
usernames drop the `.gserviceaccount.com` suffix, e.g.
`sa-migrate-dev@csrsupport-dev.iam`, not `...iam.gserviceaccount.com`):

```bash
gcloud sql connect csrsupport-dev --project=csrsupport-dev --user=postgres
# paste the filled-in contents of db/bootstrap_iam_grants.sql
```

Skipping this step doesn't fail loudly at `terraform apply` time — it fails later, the first
time `csrsupport-migrate-dev` actually runs, with a Postgres permission-denied error. Do it
now.

## 5. Grant build-approval permissions (staging/prod only)

The staging/prod triggers use Cloud Build's native `approval_config.approval_required` (plan
§6.3's "manual approval (Dana/eng lead)") — a build queues on push to `main` but sits in
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

1. Push to `main` (or `gcloud builds triggers run csrsupport-deploy-dev-... --branch=main`) —
   the first run's `deploy-bff` step will set `AGENT_ENGINE_RESOURCE_NAME` correctly (it reads
   `/workspace/agent_engine_resource_name.txt`, written earlier in the same build by
   `deploy_agent_engine.py`), so this part self-resolves on the very first CI/CD run.
2. `IAP_EXPECTED_AUDIENCE` doesn't self-resolve — after step 1, run
   `terraform output` (or check the Console) for the IAP backend service's numeric ID, format
   it as `/projects/<PROJECT_NUMBER>/global/backendServices/<BACKEND_SERVICE_ID>`, set it as
   `iap_expected_audience` in `terraform.tfvars`, and `terraform apply` again (or
   `gcloud run services update csrsupport-bff-dev --update-env-vars=...` directly, which is
   faster for a one-off fix — Terraform will just reconcile to the same value next apply).

## Summary: automated vs. manual

| Step | Mechanism |
|---|---|
| Enable APIs | manual (`gcloud services enable`, once) |
| Grant build execution identity storage access | manual (`gcloud`, once, §0.5) |
| GitHub App install | manual, browser OAuth (§1) |
| GitHub PAT + Secret Manager | manual (§2) |
| Cloud SQL, Cloud Run, Artifact Registry, IAM, Cloud Build triggers | `terraform apply` (§3) |
| IAM database bootstrap grants | manual, once, SQL (§4) |
| Build-approver IAM | manual (`gcloud`, §5) |
| Everything after that — build, test, deploy, migrate, eval | fully automated, `cloudbuild/{pr-checks,deploy}.yaml` |
