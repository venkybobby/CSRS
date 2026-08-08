# Identity-Aware Proxy in front of a Cloud Run service (plan §4.1): CSR auth
# is IAP + Google Identity Platform/Workspace SSO, no app-level login.
#
# This module covers the IAP-specific resources (brand, backend service
# with the iap{} block enabled, and the IAM binding restricting access to
# the CSR group). It assumes the surrounding external HTTPS load balancer
# scaffolding (URL map, target proxy, forwarding rule, managed SSL cert) is
# provisioned alongside it in the environment's root module -- reproduced
# here would be standard GCP LB boilerplate that isn't the security-relevant
# part of this module.

variable "project_id" {
  type = string
}

variable "support_email" {
  description = "OAuth consent screen support email (must be a Workspace user in this org)."
  type        = string
}

variable "application_title" {
  type    = string
  default = "CSRSupport"
}

variable "cloud_run_service_name" {
  type = string
}

variable "region" {
  type = string
}

variable "csr_group_email" {
  description = "Google Group whose members are authorized CSRs, e.g. csr-agents@meridianhealthplans.com"
  type        = string
}

resource "google_iap_brand" "csrsupport" {
  project           = var.project_id
  support_email     = var.support_email
  application_title = var.application_title
}

resource "google_iap_client" "csrsupport" {
  display_name = "csrsupport-iap-client"
  brand        = google_iap_brand.csrsupport.name
}

resource "google_compute_region_network_endpoint_group" "cloud_run_neg" {
  project               = var.project_id
  name                  = "${var.cloud_run_service_name}-neg"
  region                = var.region
  network_endpoint_type = "SERVERLESS"
  cloud_run {
    service = var.cloud_run_service_name
  }
}

resource "google_compute_backend_service" "cloud_run_backend" {
  project     = var.project_id
  name        = "${var.cloud_run_service_name}-backend"
  protocol    = "HTTPS"
  timeout_sec = 30

  backend {
    group = google_compute_region_network_endpoint_group.cloud_run_neg.id
  }

  iap {
    enabled              = true
    oauth2_client_id     = google_iap_client.csrsupport.client_id
    oauth2_client_secret = google_iap_client.csrsupport.secret
  }
}

# Only this group can reach the IAP-protected backend -- onboarding/
# offboarding a CSR is a Google Group membership change (plan §4.1),
# auditable via Cloud Identity admin logs, not an app-level user table.
resource "google_iap_web_backend_service_iam_member" "csr_access" {
  project             = var.project_id
  web_backend_service  = google_compute_backend_service.cloud_run_backend.name
  role                 = "roles/iap.httpsResourceAccessor"
  member               = "group:${var.csr_group_email}"
}

output "backend_service_id" {
  value = google_compute_backend_service.cloud_run_backend.id
}
