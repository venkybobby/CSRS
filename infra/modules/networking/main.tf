# VPC network, Cloud SQL private-services peering, and a Serverless VPC
# Access connector. All three were previously just assumed to already
# exist, taken as blind input variables (vpc_network_id, vpc_connector_id)
# by infra/modules/{cloud_sql,cloud_run,cloud_run_job} -- a real gap on a
# fresh project where none of this is provisioned yet. This module is the
# thing that actually creates it.
#
# Deliberately NOT using the project's auto-created "default" network:
# custom-mode gives explicit control over the subnet range and keeps this
# environment's networking self-contained and reviewable in one place.

variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "environment" {
  type = string
}

variable "subnet_cidr" {
  type    = string
  default = "10.10.0.0/20"
}

# Serverless VPC Access connectors require their own dedicated /28,
# distinct from the subnet range above.
variable "connector_cidr" {
  type    = string
  default = "10.8.0.0/28"
}

# Cloud SQL's private-services peering reserves its own range too --
# distinct from both of the above.
variable "private_service_range_cidr_prefix" {
  description = "Prefix length for the reserved private-service-access range (a /20 comfortably covers Cloud SQL + any future peered services)."
  type        = number
  default     = 20
}

resource "google_compute_network" "vpc" {
  project                 = var.project_id
  name                     = "csrsupport-${var.environment}-vpc"
  auto_create_subnetworks  = false
}

resource "google_compute_subnetwork" "subnet" {
  project       = var.project_id
  name          = "csrsupport-${var.environment}-subnet"
  region        = var.region
  network       = google_compute_network.vpc.id
  ip_cidr_range = var.subnet_cidr
}

# Reserved IP range + peering connection so Cloud SQL can hand out a
# private IP on this VPC (plan §3.2: "no public IP").
resource "google_compute_global_address" "private_service_range" {
  project       = var.project_id
  name          = "csrsupport-${var.environment}-private-service-range"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = var.private_service_range_cidr_prefix
  network       = google_compute_network.vpc.id
}

resource "google_service_networking_connection" "private_vpc_connection" {
  network                 = google_compute_network.vpc.id
  service                  = "servicenetworking.googleapis.com"
  reserved_peering_ranges  = [google_compute_global_address.private_service_range.name]
}

# Lets Cloud Run services/jobs reach the VPC (and therefore Cloud SQL's
# private IP) -- plan §3 hardening, referenced by infra/modules/cloud_run
# and infra/modules/cloud_run_job.
resource "google_vpc_access_connector" "connector" {
  project       = var.project_id
  name          = "csrsupport-${var.environment}-conn"
  region        = var.region
  network       = google_compute_network.vpc.name
  ip_cidr_range = var.connector_cidr
  machine_type  = "e2-micro"
  min_instances = 2
  max_instances = 3

  depends_on = [google_service_networking_connection.private_vpc_connection]
}

output "vpc_network_id" {
  value = google_compute_network.vpc.id
}

output "vpc_connector_id" {
  value = google_vpc_access_connector.connector.id
}
