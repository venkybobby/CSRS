# Generic Cloud Run Job module -- used for the DB migration runner
# (db/migrations/Dockerfile), invoked synchronously from the deploy
# pipeline via `gcloud run jobs execute --wait`, not left running.
#
# Unlike infra/modules/cloud_run (the always-on BFF/frontend services),
# a Job has no ingress concept and no min/max instance scaling -- it runs
# to completion once per invocation.

variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "job_name" {
  type = string
}

variable "image" {
  type = string
}

variable "service_account_email" {
  type = string
}

variable "vpc_connector_id" {
  description = "Needed to reach the private-IP-only Cloud SQL instance -- this is the whole reason this runs as a Cloud Run Job instead of a Cloud Build step."
  type        = string
}

variable "env_vars" {
  type    = map(string)
  default = {}
}

resource "google_cloud_run_v2_job" "job" {
  project  = var.project_id
  name     = var.job_name
  location = var.region

  template {
    template {
      service_account = var.service_account_email
      max_retries      = 0 # a failed migration should surface immediately, not silently retry

      vpc_access {
        network_interfaces {
          network = var.vpc_connector_id
        }
        egress = "PRIVATE_RANGES_ONLY"
      }

      containers {
        image = var.image

        dynamic "env" {
          for_each = var.env_vars
          content {
            name  = env.key
            value = env.value
          }
        }
      }
    }
  }
}

output "job_name" {
  value = google_cloud_run_v2_job.job.name
}
