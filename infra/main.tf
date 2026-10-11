terraform {
  required_version = ">= 1.6.0"
  required_providers {
    google = { source = "hashicorp/google", version = "~> 7.0" }
  }
}
provider "google" { project = var.project_id
  region = var.region
}
variable "project_id" { type = string
  default = "data-workshops"
}
variable "region" { type = string
  default = "us-central1"
}
# Import resources created by scripts/bootstrap_gcp.sh before applying to the same project.
resource "google_artifact_registry_repository" "images" {
  location = var.region
  repository_id = "flairify"
  format = "DOCKER"
}
resource "google_firestore_database" "flairify" {
  name = "flairify"
  location_id = var.region
  type = "FIRESTORE_NATIVE"
  delete_protection_state = "DELETE_PROTECTION_ENABLED"
}
resource "google_storage_bucket" "media" {
  name = "${var.project_id}-flairify-media"
  location = var.region
  uniform_bucket_level_access = true
  public_access_prevention = "enforced"
  force_destroy = false
}
resource "google_cloud_tasks_queue" "jobs" {
  name = "flairify-jobs"
  location = var.region
  rate_limits { max_concurrent_dispatches = 2
    max_dispatches_per_second = 1
  }
  retry_config { max_attempts = 3
    min_backoff = "10s"
    max_backoff = "120s"
  }
}
resource "google_bigquery_dataset" "graph" {
  dataset_id = "flairify"
  location = var.region
  delete_contents_on_destroy = false
}
variable "billing_account" { type = string
  default = ""
}
variable "monthly_budget_usd" { type = number
  default = 0
}
# Optional alert: explicitly set account and budget. Alerts do not cap spending.
resource "google_billing_budget" "flairify" {
  count = var.billing_account != "" && var.monthly_budget_usd > 0 ? 1 : 0
  billing_account = var.billing_account
  display_name = "Flairify project cost alert (not a cap)"
  budget_filter { projects = ["projects/${data.google_project.project.number}"] }
  amount { specified_amount { currency_code = "USD"
    units = tostring(var.monthly_budget_usd)
  } }
  threshold_rules { threshold_percent = 0.5 }
  threshold_rules { threshold_percent = 0.9 }
  threshold_rules { threshold_percent = 1.0 }
}
data "google_project" "project" { project_id = var.project_id }

# 768 dimensions are explicitly requested from Gemini Embedding 2 (Firestore max 2048).
resource "google_firestore_index" "catalog_vector" {
  database = google_firestore_database.flairify.name
  collection = "flairify_vectors"
  query_scope = "COLLECTION"
  fields { field_path = "owner"
    order = "ASCENDING"
  }
  fields { field_path = "space"
    order = "ASCENDING"
  }
  fields { field_path = "active"
    order = "ASCENDING"
  }
  fields { field_path = "facets"
    array_config = "CONTAINS"
  }
  fields { field_path = "price"
    order = "ASCENDING"
  }
  fields { field_path = "embedding"
    vector_config { dimension = 768
      flat {}
    }
  }
}
resource "google_firestore_index" "catalog_affordable" {
  database = google_firestore_database.flairify.name
  collection = "flairify_vectors"
  query_scope = "COLLECTION"
  fields { field_path = "owner"
    order = "ASCENDING"
  }
  fields { field_path = "space"
    order = "ASCENDING"
  }
  fields { field_path = "active"
    order = "ASCENDING"
  }
  fields { field_path = "facets"
    array_config = "CONTAINS"
  }
  fields { field_path = "price"
    order = "ASCENDING"
  }
}
