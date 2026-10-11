# Google Cloud deployment

Project `data-workshops`; region `us-central1`. Use resource prefixes `flairify` to avoid unrelated workloads in the shared project. The existing project default Firestore database is Datastore mode, so Flairify uses the dedicated native database **flairify**.

## Resources

- Artifact Registry Docker repository `flairify`.
- Firestore database `flairify` (native mode).
- Private buckets `data-workshops-flairify-media` and `data-workshops-flairify-build` (source archives).
- Cloud Run `flairify-api`, `flairify-worker`, `flairify-web`.
- Cloud Tasks queue `flairify-jobs`: two simultaneous dispatches, one/second, three transport attempts.
- Runtime identities `flairify-api`, `flairify-worker`, `flairify-frontend`, task identity `flairify-tasks`, build identity `flairify-build`.
- Repositories linked under the existing `tal-chatbot-github` Cloud Build connection; separate `flairify-frontend-main` and `flairify-backend-main` push triggers.

`bootstrap_gcp.sh` provisions dedicated resources and roles. The API/worker can read/write application state and their private media bucket; only the task identity invokes the private worker. Build identity deploys services, writes the image repository and acts as the three Flairify runtime identities. It has source-object read access on the dedicated build bucket for manual submissions. No downloaded service-account keys.

To provision the source bucket in a new environment:

```sh
gcloud storage buckets create gs://data-workshops-flairify-build --project=data-workshops --location=us-central1 --uniform-bucket-level-access --public-access-prevention
gcloud storage buckets add-iam-policy-binding gs://data-workshops-flairify-build --member=serviceAccount:flairify-build@data-workshops.iam.gserviceaccount.com --role=roles/storage.objectViewer
```

## CI/CD

Each repository has a root `cloudbuild.yaml`. Backend runs Pytest, builds one image, deploys the private worker, grants the task invoker, then deploys the API. Frontend's Docker build runs type checks, Vitest and a production build before deploy. First deployment must deploy backend before frontend; future independent pushes redeploy the appropriate service. Cloud Run retains previous revisions for rollback.

Model IDs, consent/OAuth configuration and Secret Manager references should be added as runtime variables or Cloud Build substitutions. Backend builds explicitly set `_APP_MODE` and `_ENABLE_PAID_AI`, defaulting to safe demo configuration. Update the trigger substitutions when promoting to production; don't expect an ad hoc console mode change to survive a later demo build.

Cloud build commands in README use the dedicated source bucket. Builds triggered from GitHub don't need local archives. Never include `.env`, `.data`, credentials, local media, service-account keys or dependency folders in build contexts; `.gcloudignore`, `.dockerignore` and `.gitignore` are supplied.

## Security and operations

Firestore/Storage client rules deny all direct browser access. Server IAM and identity-scoped API checks perform authorization. Deploy the included rules to the named database using a Firebase CLI project configuration; do not overwrite other applications' default database rules. Cloud Logging captures platform health/errors while API access logs and raw content logging are disabled.

Production sign-in setup, API access and provider model validation are documented in INTEGRATIONS.md. Public anonymous sessions are excluded from paid AI; configured Firebase accounts can use limited live Gemini calls. Set a Secret Manager-backed demo admin key only for controlled demos; the default cloud build disables demo admin unlocking. The deployed backend trigger explicitly enables Firebase and Gemini text/analysis; source defaults remain credential-free.

`infra/main.tf` defines repeatable core resources and an optional budget alert. Import existing resources before Terraform applies; the bootstrap script and Terraform are alternative ownership workflows. Cloud Run revisions/CI triggers are managed by the provided build and trigger scripts. Budget alerts are not spending caps and require an explicit account/amount.

Public API/web services use Google’s documented `--no-invoker-iam-check` public-service setting, compatible with the project’s domain-restricted IAM sharing. The worker retains IAM enforcement. No organization policy is changed. See [Cloud Run public access](https://docs.cloud.google.com/run/docs/authenticating/public). The dedicated Firestore deny-all client rules and BigQuery schema were deployed on 11 October 2026.
