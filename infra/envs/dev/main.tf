# csrsupport-dev environment. Structurally identical to staging/prod (plan
# §6.1: "three fully separate GCP projects... no shared Cloud SQL instances
# or Agent Engine deployments across environments") -- only var values
# differ between envs/dev, envs/staging, envs/prod.

terraform {
  required_version = ">= 1.7"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
  backend "gcs" {
    bucket = "csrsupport-dev-tfstate"
    prefix = "csrsupport"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

variable "project_id" {
  type    = string
  default = "csrsupport-dev"
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "support_email" {
  type = string
}

variable "csr_group_email" {
  type    = string
  default = "csr-agents@meridianhealthplans.com"
}

variable "enable_vpc_sc" {
  description = "VPC Service Controls / Access Context Manager is an org-level feature -- unavailable on a standalone project with no GCP Organization (see docs/architecture/cicd-setup.md). Leave false for csrsupport-dev on a personal-account project; set true (and supply access_policy_id) once/if this project is part of an org."
  type        = bool
  default     = false
}

variable "access_policy_id" {
  description = "Org-level Access Context Manager policy ID. Only required when enable_vpc_sc = true."
  type        = string
  default     = null
}

variable "bff_image" {
  type = string
  # Placeholder for first apply, same pattern as migrate_image below --
  # Cloud Run requires a valid, already-existing image at apply time, and
  # nothing has ever been pushed to Artifact Registry yet on a fresh
  # environment (pr-checks.yaml only builds, never pushes). deploy.yaml
  # overwrites this with a real image via `gcloud run deploy` on first
  # real deploy.
  default = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "frontend_image" {
  type    = string
  default = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "migrate_image" {
  type    = string
  default = "us-docker.pkg.dev/cloudrun/container/job:latest" # placeholder; CI overwrites via `gcloud run jobs update` on first deploy
}

variable "github_app_installation_id" {
  description = "From the manual 'Install Cloud Build GitHub App' step -- see docs/architecture/cicd-setup.md."
  type        = string
}

variable "github_pat_secret_id" {
  description = "Secret Manager secret name holding a GitHub PAT, created manually -- see docs/architecture/cicd-setup.md."
  type        = string
}

# Database is Supabase Postgres (see docs/architecture/cicd-setup.md's
# Supabase section), not Cloud SQL -- these hold Secret Manager secret
# names for the two least-privilege DATABASE_URL connection strings,
# created manually (same pattern as github_pat_secret_id above), never
# Terraform-managed values, so no password ever lands in state.
variable "migrate_db_url_secret_id" {
  description = "Secret Manager secret name holding sa-migrate's Supabase DATABASE_URL (DDL rights), created manually -- see docs/architecture/cicd-setup.md."
  type        = string
}

variable "agent_engine_db_url_secret_id" {
  description = "Secret Manager secret name holding the running agent's Supabase DATABASE_URL (SELECT/INSERT-only), created manually -- see docs/architecture/cicd-setup.md."
  type        = string
}

resource "google_secret_manager_secret_iam_member" "agent_engine_db_url_accessor" {
  project   = var.project_id
  secret_id = var.agent_engine_db_url_secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${module.cicd.cicd_service_account_email}"
}

module "vpc_sc" {
  count            = var.enable_vpc_sc ? 1 : 0
  source           = "../../modules/vpc_sc"
  project_id       = var.project_id
  access_policy_id = var.access_policy_id
}

module "agent_engine_sa" {
  source      = "../../modules/agent_engine"
  project_id  = var.project_id
  environment = "dev"
}

resource "google_service_account" "migrate" {
  project      = var.project_id
  account_id   = "sa-migrate-dev"
  display_name = "CSRSupport DB migration runner (dev)"
}

# Database is Supabase Postgres, not Cloud SQL -- no GCP IAM DB role needed
# here. sa-migrate's DB identity/privileges live in Supabase itself (see
# db/bootstrap_supabase_roles.sql); this service account exists only to run
# the Cloud Run Job and read its DATABASE_URL secret (see
# csrsupport_migrate_db_url_accessor below).
resource "google_secret_manager_secret_iam_member" "migrate_db_url_accessor" {
  project   = var.project_id
  secret_id = var.migrate_db_url_secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.migrate.email}"
}

module "artifact_registry" {
  source      = "../../modules/artifact_registry"
  project_id  = var.project_id
  region      = var.region
  environment = "dev"
}

module "migrate_job" {
  source                 = "../../modules/cloud_run_job"
  project_id             = var.project_id
  region                 = var.region
  job_name               = "csrsupport-migrate-dev"
  image                  = var.migrate_image
  service_account_email  = google_service_account.migrate.email
  secret_env_vars = {
    DATABASE_URL = var.migrate_db_url_secret_id
  }
}

resource "google_service_account" "bff" {
  project      = var.project_id
  account_id   = "sa-bff-run-dev"
  display_name = "CSRSupport BFF Cloud Run (dev)"
}

# Deliberately NOT granted any Cloud SQL role (plan §4 least-privilege
# table) -- the BFF never talks to Postgres directly, see
# bff/app/audit_readback.py's docstring.
resource "google_project_iam_member" "bff_aiplatform_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.bff.email}"
}

resource "google_project_iam_member" "bff_trace_agent" {
  project = var.project_id
  role    = "roles/cloudtrace.agent"
  member  = "serviceAccount:${google_service_account.bff.email}"
}

resource "google_project_iam_member" "bff_logging_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.bff.email}"
}

resource "google_service_account" "frontend" {
  project      = var.project_id
  account_id   = "sa-frontend-run-dev"
  display_name = "CSRSupport frontend Cloud Run (dev)"
}
# No grants beyond default logging -- serves static assets only (plan §4).

module "bff_cloud_run" {
  source                 = "../../modules/cloud_run"
  project_id             = var.project_id
  region                 = var.region
  service_name           = "csrsupport-bff-dev"
  image                  = var.bff_image
  service_account_email  = google_service_account.bff.email
  min_instances          = 0
  max_instances          = 10
  env_vars = {
    IAP_EXPECTED_AUDIENCE          = var.iap_expected_audience
    AGENT_ENGINE_RESOURCE_NAME     = var.agent_engine_resource_name
    GOOGLE_CLOUD_PROJECT           = var.project_id
    GOOGLE_CLOUD_LOCATION          = var.region
  }
}

variable "iap_expected_audience" {
  type    = string
  default = "" # set post-deploy once the IAP backend service exists -- see README
}

variable "agent_engine_resource_name" {
  type    = string
  default = "" # set post-deploy by deploy_agent_engine.py's output
}

module "frontend_cloud_run" {
  source                 = "../../modules/cloud_run"
  project_id             = var.project_id
  region                 = var.region
  service_name           = "csrsupport-frontend-dev"
  image                  = var.frontend_image
  service_account_email  = google_service_account.frontend.email
  min_instances          = 0
  max_instances          = 5
}

module "iap" {
  source                 = "../../modules/iap"
  project_id             = var.project_id
  region                 = var.region
  support_email          = var.support_email
  cloud_run_service_name = module.bff_cloud_run.service_name
  csr_group_email        = var.csr_group_email
}

module "cicd" {
  source                     = "../../modules/cicd"
  project_id                 = var.project_id
  region                     = var.region
  environment                = "dev"
  github_app_installation_id = var.github_app_installation_id
  github_pat_secret_id       = var.github_pat_secret_id
  staging_bucket_name        = replace(module.artifact_registry.staging_bucket, "gs://", "")
  runtime_service_account_ids = [
    "projects/${var.project_id}/serviceAccounts/${google_service_account.bff.email}",
    "projects/${var.project_id}/serviceAccounts/${google_service_account.frontend.email}",
    "projects/${var.project_id}/serviceAccounts/${module.agent_engine_sa.service_account_email}",
    "projects/${var.project_id}/serviceAccounts/${google_service_account.migrate.email}",
  ]
}

output "bff_service_account_email" {
  value = google_service_account.bff.email
}

output "agent_engine_service_account_email" {
  value = module.agent_engine_sa.service_account_email
}

output "migrate_service_account_email" {
  value = google_service_account.migrate.email
}

output "artifact_registry_url" {
  value = module.artifact_registry.repository_url
}

output "agent_engine_staging_bucket" {
  value = module.artifact_registry.staging_bucket
}

output "cicd_service_account_email" {
  value = module.cicd.cicd_service_account_email
}

# The runbook (§6 step 2) says `terraform output` gives the IAP backend
# service ID to derive iap_expected_audience from -- true only once this
# is re-exported at the env level, since infra/modules/iap's own output
# only exists at the module scope.
output "iap_backend_service_id" {
  value = module.iap.backend_service_id
}

# Ready to paste straight into terraform.tfvars's iap_expected_audience --
# no manual gcloud lookup or /projects/<NUM>/global/backendServices/<NUM>
# formatting needed.
output "iap_expected_audience" {
  value = module.iap.iap_expected_audience
}
