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

variable "vpc_network_id" {
  type = string
}

variable "vpc_connector_id" {
  type = string
}

variable "bff_image" {
  type = string
}

variable "frontend_image" {
  type = string
}

module "vpc_sc" {
  source            = "../../modules/vpc_sc"
  project_id        = var.project_id
  access_policy_id  = var.access_policy_id
}

variable "access_policy_id" {
  type = string
}

module "agent_engine_sa" {
  source      = "../../modules/agent_engine"
  project_id  = var.project_id
  environment = "dev"
}

module "cloud_sql" {
  source                  = "../../modules/cloud_sql"
  project_id              = var.project_id
  region                  = var.region
  environment             = "dev"
  vpc_network_id          = var.vpc_network_id
  agent_engine_iam_member = module.agent_engine_sa.service_account_email
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
  vpc_connector_id       = var.vpc_connector_id
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
  vpc_connector_id       = var.vpc_connector_id
}

module "iap" {
  source                 = "../../modules/iap"
  project_id             = var.project_id
  region                 = var.region
  support_email          = var.support_email
  cloud_run_service_name = module.bff_cloud_run.service_name
  csr_group_email        = var.csr_group_email
}

output "cloud_sql_instance_connection_name" {
  value = module.cloud_sql.instance_connection_name
}

output "bff_service_account_email" {
  value = google_service_account.bff.email
}

output "agent_engine_service_account_email" {
  value = module.agent_engine_sa.service_account_email
}
