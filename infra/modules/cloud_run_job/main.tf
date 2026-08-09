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

variable "env_vars" {
  type    = map(string)
  default = {}
}

variable "secret_env_vars" {
  description = "Map of env var name -> Secret Manager secret name (latest version). Resolved by Cloud Run at container start using this job's own service_account_email -- the secret value never passes through Terraform state (plan §3.2's no-plaintext-password intent, now serving Supabase DATABASE_URL secrets instead of Cloud SQL IAM auth)."
  type        = map(string)
  default     = {}
}

resource "google_cloud_run_v2_job" "job" {
  project  = var.project_id
  name     = var.job_name
  location = var.region

  template {
    template {
      service_account = var.service_account_email
      max_retries      = 0 # a failed migration should surface immediately, not silently retry

      containers {
        image = var.image

        dynamic "env" {
          for_each = var.env_vars
          content {
            name  = env.key
            value = env.value
          }
        }

        dynamic "env" {
          for_each = var.secret_env_vars
          content {
            name = env.key
            value_source {
              secret_key_ref {
                secret  = env.value
                version = "latest"
              }
            }
          }
        }
      }
    }
  }
}

output "job_name" {
  value = google_cloud_run_v2_job.job.name
}
