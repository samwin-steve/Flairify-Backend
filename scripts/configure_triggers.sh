#!/usr/bin/env bash
set -euo pipefail
PROJECT="${PROJECT:-data-workshops}"
REGION="${REGION:-us-central1}"
CONNECTION="${CONNECTION:-tal-chatbot-github}"
for part in frontend backend; do
 gcloud builds triggers create github --name="flairify-$part-main" --project="$PROJECT" --region="$REGION" --repository="projects/$PROJECT/locations/$REGION/connections/$CONNECTION/repositories/flairify-$part" --branch-pattern='^main$' --build-config=cloudbuild.yaml --service-account="projects/$PROJECT/serviceAccounts/flairify-build@$PROJECT.iam.gserviceaccount.com" --substitutions="_REGION=$REGION" --include-logs-with-status
 done
