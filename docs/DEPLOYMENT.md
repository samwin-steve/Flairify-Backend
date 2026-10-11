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

Each repository has a root `cloudbuild.yaml`. Backend runs Pytest, builds one image, deploys the private worker, grants the task invoker, then deploys the API. Frontend's Docker build runs type checks, Vitest and a production build before deploy. First deployment must deploy backend before frontend; future independent pushes redeploy the appropriate service. Cloud Run retains previous revisions for rollback. The installed triggers skip documentation-only changes (`docs/**`, `README.md`, `LICENSE`, `THIRD_PARTY.md` for backend; the last three files for frontend). Wait for a deployment to finish before starting another release, and verify that the serving image matches the latest successful build.

Model IDs, consent/OAuth configuration and Secret Manager references should be added as runtime variables or Cloud Build substitutions. Backend builds explicitly set `_APP_MODE` and `_ENABLE_PAID_AI`, defaulting to safe demo configuration. Update the trigger substitutions when promoting to production; don't expect an ad hoc console mode change to survive a later demo build.

Cloud build commands in README use the dedicated source bucket. Builds triggered from GitHub don't need local archives. Never include `.env`, `.data`, credentials, local media, service-account keys or dependency folders in build contexts; `.gcloudignore`, `.dockerignore` and `.gitignore` are supplied.

## Security and operations

Firestore/Storage client rules deny all direct browser access. Server IAM and identity-scoped API checks perform authorization. Deploy the included rules to the named database using a Firebase CLI project configuration; do not overwrite other applications' default database rules. Cloud Logging captures platform health/errors while API access logs and raw content logging are disabled.

Production sign-in setup, API access and provider model validation are documented in INTEGRATIONS.md. Public anonymous sessions are excluded from paid AI; configured Firebase accounts can use limited live Gemini calls. Token revocation checks also require `roles/firebaseauth.viewer` on the API runtime identity; this role is granted in the deployed project. Grant `roles/aiplatform.user` to API/worker when enabling Gemini. Set a Secret Manager-backed demo admin key only for controlled demos; the default cloud build disables demo admin unlocking. The deployed backend trigger explicitly enables Firebase, Gemini text/analysis and 2D image editing. It sets `_IMAGE_EDIT_MODEL=gemini-3.1-flash-image`, `_IMAGE_EDIT_LOCATION=global`, and `_ALLOW_SAMPLE_TRY_ON=true` for the clearly labeled sample catalogue. Source defaults remain credential-free; paid generation requires a verified account and photo consent.

`infra/main.tf` defines repeatable core resources and an optional budget alert. Import existing resources before Terraform applies; the bootstrap script and Terraform are alternative ownership workflows. Cloud Run revisions/CI triggers are managed by the provided build and trigger scripts. Budget alerts are not spending caps and require an explicit account/amount.

Public API/web services use Google’s documented `--no-invoker-iam-check` public-service setting, compatible with the project’s domain-restricted IAM sharing. The worker retains IAM enforcement. No organization policy is changed. See [Cloud Run public access](https://docs.cloud.google.com/run/docs/authenticating/public). The dedicated Firestore deny-all client rules and BigQuery schema were deployed on 11 October 2026.

## Owner and seller access

After the intended owner signs in to Flairify, a trusted operator can run `scripts/grant_seller_access.py --project data-workshops --email OWNER_EMAIL --role owner` with the backend virtual environment. The script uses the operator's current gcloud login, supplies the quota-project header for Identity Platform lookup, verifies an existing account with the exact email, and writes only Flairify's server-side role record. It does not change project IAM or Firebase claims. The owner can then approve seller requests in Seller Studio. The bootstrap was exercised with a temporary Firebase QA account and that account/role were removed afterward.

New seller/order records use the same Firestore database and existing owner-filtered queries. No new cloud service, GPU, payment service, identity-admin runtime permission or composite query index is required. Existing deny-all browser rules cover the new collections.
