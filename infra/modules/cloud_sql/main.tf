# Cloud SQL for PostgreSQL, regional HA, private-IP-only, IAM database
# authentication (plan §3/§4: no DB password ever exists). This module
# creates the instance/database/IAM bindings; schema (db/migrations/
# 0001_init_schema.sql) and seed data (db/seed/) are applied out-of-band by
# the CI/CD deploy pipeline (cloudbuild/deploy.yaml), not by Terraform --
# keeping schema evolution in normal migration tooling rather than HCL.

variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "environment" {
  type = string # dev | staging | prod
}

variable "vpc_network_id" {
  description = "Self link of the VPC the instance's private IP attaches to."
  type        = string
}

variable "agent_engine_iam_member" {
  description = "IAM DB user identity for the Agent Engine service account, e.g. sa-agent-engine@PROJECT.iam"
  type        = string
}

variable "tier" {
  type    = string
  default = "db-custom-2-8192" # 2 vCPU / 8GB -- MVP1 scale, not a sizing claim for real production load
}

resource "google_sql_database_instance" "csrsupport" {
  project          = var.project_id
  name             = "csrsupport-${var.environment}"
  region           = var.region
  database_version = "POSTGRES_16"

  settings {
    tier              = var.tier
    availability_type = var.environment == "prod" ? "REGIONAL" : "ZONAL"

    ip_configuration {
      ipv4_enabled    = false # no public IP -- plan §3.2
      private_network = var.vpc_network_id
    }

    database_flags {
      name  = "cloudsql.iam_authentication"
      value = "on"
    }

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
    }

    disk_autoresize = true
  }

  deletion_protection = var.environment == "prod"
}

resource "google_sql_database" "csrsupport" {
  project  = var.project_id
  instance = google_sql_database_instance.csrsupport.name
  name     = "csrsupport"
}

# IAM DB user for the Agent Engine service account -- the ONLY principal
# with database access (plan §4: sa-bff-run intentionally has no Cloud SQL
# role at all).
resource "google_sql_user" "agent_engine" {
  project  = var.project_id
  instance = google_sql_database_instance.csrsupport.name
  name     = var.agent_engine_iam_member
  type     = "CLOUD_IAM_SERVICE_ACCOUNT"
}

output "instance_connection_name" {
  value = google_sql_database_instance.csrsupport.connection_name
}
