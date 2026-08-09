# Vertex AI Agent Engine does not (as of this writing) have a mature
# first-party Terraform resource for the Reasoning Engine deployment itself
# -- that's created by agent/csr_agent/deploy/deploy_agent_engine.py via the
# Vertex AI SDK, run as a CI/CD pipeline step (plan §6.2/§6.3), not by
# `terraform apply`. This module manages everything Terraform legitimately
# owns around that: the least-privilege service account the deployed agent
# runs as (plan §4's service-account table).

variable "project_id" {
  type = string
}

variable "environment" {
  type = string
}

resource "google_service_account" "agent_engine" {
  project      = var.project_id
  account_id   = "sa-agent-engine-${var.environment}"
  display_name = "CSRSupport Agent Engine runtime (${var.environment})"
}

resource "google_project_iam_member" "cloud_trace_agent" {
  project = var.project_id
  role    = "roles/cloudtrace.agent"
  member  = "serviceAccount:${google_service_account.agent_engine.email}"
}

resource "google_project_iam_member" "logging_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.agent_engine.email}"
}

output "service_account_email" {
  value = google_service_account.agent_engine.email
}
