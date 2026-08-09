# Generic Cloud Run service module, used for both the BFF and the frontend
# (plan §1). Ingress is locked to internal-and-cloud-load-balancing (plan
# §4.1 hardening): the only path in is through the IAP-fronted HTTPS load
# balancer -- a direct Cloud Run URL request never reaches the container,
# which is the second, independent half of the IAP-header-trust control
# (the first half is bff/app/auth.py's cryptographic JWT verification).

variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "service_name" {
  type = string
}

variable "image" {
  description = "Fully-qualified Artifact Registry image reference."
  type        = string
}

variable "service_account_email" {
  type = string
}

variable "min_instances" {
  type    = number
  default = 0
}

variable "max_instances" {
  type    = number
  default = 10
}

variable "env_vars" {
  type    = map(string)
  default = {}
}

resource "google_cloud_run_v2_service" "service" {
  project  = var.project_id
  name     = var.service_name
  location = var.region

  # plan §4.1: the ONLY path in is the IAP-fronted external HTTPS load
  # balancer -- never "all" (which would accept direct Cloud Run URL hits).
  ingress = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"

  template {
    service_account = var.service_account_email
    scaling {
      min_instance_count = var.min_instances
      max_instance_count = var.max_instances
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

  # cloudbuild/deploy.yaml's `gcloud run deploy --image=...` owns the image
  # after the placeholder-image bootstrap apply -- without this, any later
  # `terraform apply` (for an unrelated change elsewhere in this env) would
  # revert a live, CI/CD-deployed image back to var.image's placeholder
  # default, since terraform.tfvars was never meant to track every deploy's
  # image tag. Found live: a plan for IAP/LB changes also proposed reverting
  # both bff and frontend back to us-docker.pkg.dev/cloudrun/container/hello.
  lifecycle {
    ignore_changes = [template[0].containers[0].image]
  }
}

output "service_name" {
  value = google_cloud_run_v2_service.service.name
}

output "uri" {
  value = google_cloud_run_v2_service.service.uri
}
