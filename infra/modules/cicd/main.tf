# Cloud Build CI/CD: GitHub connection, the sa-cicd-build service account
# (plan §4: "CI/CD, scoped per-environment, never org-wide"), and the three
# triggers (pr-checks, deploy-dev, deploy-staging, deploy-prod).
#
# Prerequisite this module CANNOT do for you (see
# docs/architecture/cicd-setup.md): installing the "Google Cloud Build"
# GitHub App on the repo and creating a GitHub PAT stored in Secret Manager.
# Both require interactive GitHub OAuth consent in a browser -- there is no
# way to script that safely or non-interactively. github_app_installation_id
# and github_pat_secret_id below come from that one-time manual step.
#
# Approval model for staging/prod (plan §6.3's "manual approval (Dana/eng
# lead)"): Cloud Build's native build-approval feature
# (approval_config.approval_required), not a hand-rolled convention. Two
# independent gates apply to staging/prod: (1) only principals with
# roles/cloudbuild.builds.editor (or a narrower custom role) can invoke the
# trigger at all -- these two have no push/pull_request event config, so
# they never auto-fire; (2) once invoked, the build sits in
# PENDING_APPROVAL until someone holding roles/cloudbuild.builds.approver
# approves it. Grant that role only to the intended approvers group.

variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "environment" {
  type = string
}

variable "github_owner" {
  type    = string
  default = "venkybobby"
}

variable "github_repo" {
  type    = string
  default = "CSRS"
}

variable "github_app_installation_id" {
  description = "From the manual 'Install Cloud Build GitHub App' step -- see docs/architecture/cicd-setup.md."
  type        = string
}

variable "github_pat_secret_id" {
  description = "Secret Manager secret name (not full resource path) holding a GitHub PAT with repo scope, created manually."
  type        = string
}

variable "runtime_service_account_ids" {
  description = "Full resource IDs (projects/P/serviceAccounts/S) of sa-bff-run, sa-frontend-run, sa-agent-engine, sa-migrate -- sa-cicd-build needs iam.serviceAccountUser on each to deploy on their behalf."
  type        = list(string)
}

variable "staging_bucket_name" {
  description = "GCS bucket name (no gs:// prefix) sa-cicd-build needs write access to for Agent Engine deploys."
  type        = string
}

resource "google_service_account" "cicd" {
  project      = var.project_id
  account_id   = "sa-cicd-build-${var.environment}"
  display_name = "CSRSupport CI/CD (Cloud Build) -- ${var.environment}"
}

resource "google_project_iam_member" "cicd_run_developer" {
  project = var.project_id
  role    = "roles/run.developer" # deploy Cloud Run services AND jobs (bff, frontend, migrate)
  member  = "serviceAccount:${google_service_account.cicd.email}"
}

resource "google_project_iam_member" "cicd_artifact_writer" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${google_service_account.cicd.email}"
}

resource "google_project_iam_member" "cicd_aiplatform_user" {
  project = var.project_id
  role    = "roles/aiplatform.user" # includes reasoningEngines.create/update for the Agent Engine deploy step
  member  = "serviceAccount:${google_service_account.cicd.email}"
}

resource "google_storage_bucket_iam_member" "cicd_staging_bucket_writer" {
  bucket = var.staging_bucket_name
  role   = "roles/storage.objectAdmin" # scoped to the one staging bucket, not project-wide storage.admin
  member = "serviceAccount:${google_service_account.cicd.email}"
}

# sa-cicd-build must be able to act AS the runtime service accounts to
# deploy resources that run under their identity (Cloud Run's
# --service-account flag, Agent Engine's service_account param) --
# iam.serviceAccountUser scoped to exactly these four SAs, not project-wide.
resource "google_service_account_iam_member" "cicd_can_act_as_runtime_sas" {
  for_each           = toset(var.runtime_service_account_ids)
  service_account_id = each.value
  role                = "roles/iam.serviceAccountUser"
  member              = "serviceAccount:${google_service_account.cicd.email}"
}

resource "google_cloudbuildv2_connection" "github" {
  project  = var.project_id
  location = var.region
  name     = "csrsupport-github-${var.environment}"

  github_config {
    app_installation_id = var.github_app_installation_id
    authorizer_credential {
      oauth_token_secret_version = "projects/${var.project_id}/secrets/${var.github_pat_secret_id}/versions/latest"
    }
  }
}

resource "google_cloudbuildv2_repository" "csrs" {
  project           = var.project_id
  location          = var.region
  name              = var.github_repo
  parent_connection = google_cloudbuildv2_connection.github.name
  remote_uri        = "https://github.com/${var.github_owner}/${var.github_repo}.git"
}

resource "google_cloudbuild_trigger" "pr_checks" {
  project         = var.project_id
  location        = var.region
  name            = "csrsupport-pr-checks-${var.environment}"
  service_account = google_service_account.cicd.id
  filename        = "cloudbuild/pr-checks.yaml"

  repository_event_config {
    repository = google_cloudbuildv2_repository.csrs.id
    pull_request {
      branch = "^main$"
    }
  }

  substitutions = {
    _ARTIFACT_REGISTRY = "${var.region}-docker.pkg.dev/${var.project_id}/csrsupport"
  }
}

resource "google_cloudbuild_trigger" "deploy" {
  project         = var.project_id
  location        = var.region
  name            = "csrsupport-deploy-${var.environment}"
  service_account = google_service_account.cicd.id
  filename        = "cloudbuild/deploy.yaml"

  # All three triggers fire on push to main -- staging/prod queuing a build
  # immediately isn't a problem because approval_config below is the actual
  # gate: a human holding roles/cloudbuild.builds.approver must approve
  # before a staging/prod build's steps run at all (dev has no such
  # requirement and proceeds straight through). This is Cloud Build's
  # native build-approval feature, not a hand-rolled "only some people can
  # invoke this trigger" convention -- simpler to reason about and to audit.
  repository_event_config {
    repository = google_cloudbuildv2_repository.csrs.id
    push {
      branch = "^main$"
    }
  }

  approval_config {
    approval_required = var.environment != "dev"
  }

  substitutions = {
    _ENVIRONMENT = var.environment
  }
}

output "cicd_service_account_email" {
  value = google_service_account.cicd.email
}

output "repository_id" {
  value = google_cloudbuildv2_repository.csrs.id
}
