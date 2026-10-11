#!/usr/bin/env bash
set -euo pipefail
PROJECT="${PROJECT:-data-workshops}"
REGION="${REGION:-us-central1}"
# Isolated resources only; never alters pre-existing application resources.
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com firestore.googleapis.com cloudtasks.googleapis.com storage.googleapis.com secretmanager.googleapis.com aiplatform.googleapis.com bigquery.googleapis.com --project="$PROJECT" --quiet
if ! gcloud artifacts repositories describe flairify --location="$REGION" --project="$PROJECT" >/dev/null 2>&1; then
 gcloud artifacts repositories create flairify --repository-format=docker --location="$REGION" --project="$PROJECT" --quiet
fi
if ! gcloud firestore databases describe --database=flairify --project="$PROJECT" >/dev/null 2>&1; then
 gcloud firestore databases create --database=flairify --location="$REGION" --type=firestore-native --project="$PROJECT" --quiet
fi
if ! gcloud storage buckets describe "gs://$PROJECT-flairify-media" >/dev/null 2>&1; then
 gcloud storage buckets create "gs://$PROJECT-flairify-media" --project="$PROJECT" --location="$REGION" --uniform-bucket-level-access --public-access-prevention --quiet
fi
for name in flairify-api flairify-worker flairify-build flairify-tasks flairify-frontend; do
 if ! gcloud iam service-accounts describe "$name@$PROJECT.iam.gserviceaccount.com" --project="$PROJECT" >/dev/null 2>&1; then
  gcloud iam service-accounts create "$name" --display-name="$name" --project="$PROJECT" --quiet
 fi
done
for name in flairify-api flairify-worker; do
 gcloud projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:$name@$PROJECT.iam.gserviceaccount.com" --role=roles/datastore.user --condition=None --quiet >/dev/null
 gcloud storage buckets add-iam-policy-binding "gs://$PROJECT-flairify-media" --member="serviceAccount:$name@$PROJECT.iam.gserviceaccount.com" --role=roles/storage.objectUser --quiet >/dev/null
done
gcloud projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:flairify-api@$PROJECT.iam.gserviceaccount.com" --role=roles/cloudtasks.enqueuer --condition=None --quiet >/dev/null
gcloud projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:flairify-worker@$PROJECT.iam.gserviceaccount.com" --role=roles/cloudtasks.enqueuer --condition=None --quiet >/dev/null
for name in flairify-api flairify-worker; do
 gcloud iam service-accounts add-iam-policy-binding "flairify-tasks@$PROJECT.iam.gserviceaccount.com" --member="serviceAccount:$name@$PROJECT.iam.gserviceaccount.com" --role=roles/iam.serviceAccountUser --project="$PROJECT" --quiet >/dev/null
done
for role in roles/run.admin roles/logging.logWriter; do
 gcloud projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:flairify-build@$PROJECT.iam.gserviceaccount.com" --role="$role" --condition=None --quiet >/dev/null
done
gcloud artifacts repositories add-iam-policy-binding flairify --location="$REGION" --project="$PROJECT" --member="serviceAccount:flairify-build@$PROJECT.iam.gserviceaccount.com" --role=roles/artifactregistry.writer --quiet >/dev/null
for name in flairify-api flairify-worker flairify-frontend; do
 gcloud iam service-accounts add-iam-policy-binding "$name@$PROJECT.iam.gserviceaccount.com" --member="serviceAccount:flairify-build@$PROJECT.iam.gserviceaccount.com" --role=roles/iam.serviceAccountUser --project="$PROJECT" --quiet >/dev/null
done
if ! gcloud tasks queues describe flairify-jobs --location="$REGION" --project="$PROJECT" >/dev/null 2>&1; then
 gcloud tasks queues create flairify-jobs --location="$REGION" --project="$PROJECT" --max-concurrent-dispatches=2 --max-dispatches-per-second=1 --max-attempts=3 --min-backoff=10s --max-backoff=120s --quiet
fi
printf 'Flairify infrastructure ready in %s / %s\n' "$PROJECT" "$REGION"
# Optional BigQuery Graph query jobs; dataset-level reader/writer grants are applied
# by python -m scripts.configure_graph after provisioning the graph schema.
if [[ "${ENABLE_BIGQUERY:-false}" == "true" ]]; then
 for name in flairify-api flairify-worker; do
  gcloud projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:$name@$PROJECT.iam.gserviceaccount.com" --role=roles/bigquery.jobUser --condition=None --quiet >/dev/null
 done
fi
