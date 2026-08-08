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

variable "vpc_connector_id" {
  description = "Direct VPC egress / Serverless VPC Access connector for reaching Cloud SQL over private IP."
  type        = string
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

output "service_name" {
  value = google_cloud_run_v2_service.service.name
}

output "uri" {
  value = google_cloud_run_v2_service.service.uri
}
