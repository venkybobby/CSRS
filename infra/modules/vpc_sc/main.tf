# VPC Service Controls perimeter around the project's PHI-adjacent
# resources (plan §4: "VPC-SC perimeter around Cloud SQL/Storage/Vertex AI
# restricts data exfiltration paths").
#
# Access levels / perimeter bridges are intentionally left minimal here --
# widen access_level membership only for identities that genuinely need to
# reach into the perimeter (e.g. a CI/CD service account), never broadly.

variable "project_id" {
  type = string
}

variable "access_policy_id" {
  description = "Org-level Access Context Manager policy ID (created once per org, not per environment)."
  type        = string
}

variable "perimeter_name" {
  type    = string
  default = "csrsupport_perimeter"
}

variable "restricted_services" {
  type = list(string)
  default = [
    "sqladmin.googleapis.com",
    "aiplatform.googleapis.com",
    "storage.googleapis.com",
  ]
}

resource "google_access_context_manager_service_perimeter" "csrsupport" {
  parent = "accessPolicies/${var.access_policy_id}"
  name   = "accessPolicies/${var.access_policy_id}/servicePerimeters/${var.perimeter_name}"
  title  = var.perimeter_name

  status {
    restricted_services = var.restricted_services

    resources = [
      "projects/${var.project_id}",
    ]

    vpc_accessible_services {
      enable_restriction = true
      allowed_services   = var.restricted_services
    }
  }
}
