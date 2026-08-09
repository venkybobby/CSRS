# Identity-Aware Proxy in front of Cloud Run services (plan §4.1): CSR auth
# is IAP + Google Identity Platform/Workspace SSO, no app-level login.
#
# This module covers the IAP-specific resources (one shared brand/client,
# and per-service backend service + NEG + IAM binding). It assumes the
# surrounding external HTTPS load balancer scaffolding (URL map, target
# proxy, forwarding rule, managed SSL cert) is provisioned alongside it in
# the environment's root module -- reproduced here would be standard GCP LB
# boilerplate that isn't the security-relevant part of this module.
#
# Every service in cloud_run_service_names gets IAP-protected, not just the
# BFF: frontend/src/api.ts calls /api/v1/query with credentials: "include"
# as a same-origin relative path, meaning the frontend and BFF share one
# LB origin. If only the BFF's backend service were IAP-protected, the
# browser would never get challenged for login on the frontend's initial
# page load, and the first /api/v1/query fetch() would hit IAP's redirect-
# to-login response instead of JSON -- fetch() can't complete an
# interactive OAuth flow. Found by actually walking §7's live demo steps.

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

variable "cloud_run_service_names" {
  description = "Cloud Run service names to put behind IAP, sharing one OAuth brand/client. Each gets its own NEG + backend service + IAM binding."
  type        = set(string)
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
  for_each              = var.cloud_run_service_names
  project               = var.project_id
  name                  = "${each.value}-neg"
  region                = var.region
  network_endpoint_type = "SERVERLESS"
  cloud_run {
    service = each.value
  }
}

resource "google_compute_backend_service" "cloud_run_backend" {
  for_each    = var.cloud_run_service_names
  project     = var.project_id
  name        = "${each.value}-backend"
  protocol    = "HTTPS"
  timeout_sec = 30

  backend {
    group = google_compute_region_network_endpoint_group.cloud_run_neg[each.key].id
  }

  iap {
    enabled              = true
    oauth2_client_id     = google_iap_client.csrsupport.client_id
    oauth2_client_secret = google_iap_client.csrsupport.secret
  }
}

# Only this group can reach the IAP-protected backends -- onboarding/
# offboarding a CSR is a Google Group membership change (plan §4.1),
# auditable via Cloud Identity admin logs, not an app-level user table.
resource "google_iap_web_backend_service_iam_member" "csr_access" {
  for_each            = var.cloud_run_service_names
  project             = var.project_id
  web_backend_service = google_compute_backend_service.cloud_run_backend[each.key].name
  role                = "roles/iap.httpsResourceAccessor"
  member              = "group:${var.csr_group_email}"
}

data "google_project" "current" {
  project_id = var.project_id
}

# Separate from csr_access above: that grants END USERS access through
# IAP; this grants IAP's OWN Google-managed service agent permission to
# actually invoke the Cloud Run service once it's let a user through.
# Without it, IAP returns "The IAP service account is not provisioned" --
# found live trying to open the frontend URL. The service agent itself
# still has to be provisioned once via `gcloud beta services identity
# create --service=iap.googleapis.com` (not Terraform-manageable, a
# Google-managed service identity, not a resource this project creates)
# before this IAM binding has anything valid to reference.
resource "google_cloud_run_v2_service_iam_member" "iap_invoker" {
  for_each = var.cloud_run_service_names
  project  = var.project_id
  location = var.region
  name     = each.value
  role     = "roles/run.invoker"
  member   = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-iap.iam.gserviceaccount.com"
}

# .id (Terraform's name-based resource path, projects/<PROJECT_ID>/global/
# backendServices/<NAME>) is what a URL map's default_service/path_rule
# service fields need -- a valid resource reference.
output "backend_service_ids" {
  description = "Map of Cloud Run service name -> backend service resource ID, for wiring a URL map."
  value       = { for k, v in google_compute_backend_service.cloud_run_backend : k => v.id }
}

# IAP's JWT audience claim uses NUMERIC project number + NUMERIC backend
# service ID (.generated_id) -- .id above looks plausible for this too but
# silently doesn't match what IAP actually issues. Found via a live
# iap_backend_service_id output that returned the wrong format.
output "iap_expected_audiences" {
  description = "Map of Cloud Run service name -> ready-to-use IAP JWT audience string."
  value = {
    for k, v in google_compute_backend_service.cloud_run_backend :
    k => "/projects/${data.google_project.current.number}/global/backendServices/${v.generated_id}"
  }
}
