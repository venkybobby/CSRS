# Artifact Registry repo for bff/frontend/migrate images, and the GCS
# staging bucket Agent Engine's deploy SDK needs to stage its build
# artifacts. Both are referenced throughout cloudbuild/*.yaml and
# deploy_agent_engine.py but weren't actually provisioned anywhere until
# this module -- a real gap in the original infra scaffold.

variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "environment" {
  type = string
}

resource "google_artifact_registry_repository" "csrsupport" {
  project       = var.project_id
  location      = var.region
  repository_id = "csrsupport"
  format        = "DOCKER"
  description   = "CSRSupport bff/frontend/migrate images (${var.environment})"

  # Prod keeps a longer tail for rollback; dev/staging can prune more
  # aggressively to control storage cost.
  cleanup_policies {
    id     = "keep-recent"
    action = "KEEP"
    most_recent_versions {
      keep_count = var.environment == "prod" ? 20 : 5
    }
  }
}

resource "google_storage_bucket" "agent_engine_staging" {
  project                     = var.project_id
  name                        = "csrsupport-${var.environment}-agent-engine-staging"
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = var.environment != "prod"

  lifecycle_rule {
    condition {
      age = 30
    }
    action {
      type = "Delete"
    }
  }
}

output "repository_url" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.csrsupport.repository_id}"
}

output "staging_bucket" {
  value = "gs://${google_storage_bucket.agent_engine_staging.name}"
}
