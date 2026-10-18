# Request safety

Flairify uses Google Cloud Model Armor's regional `sanitizeUserPrompt` REST API with runtime Application Default Credentials. No API key or browser credential is required. The dedicated `flairify-input-guard` template in `data-workshops/us-central1` enables dangerous content, hate speech, harassment, sexually explicit content, prompt injection/jailbreak and malicious URI detection. RAI and injection thresholds are `MEDIUM_AND_ABOVE`; tune the template after reviewing false positives. This is probabilistic screening, not a guarantee of detecting every harmful request.

## Enforcement

- Both JSON chat and SSE chat screen the latest user message before acquiring a turn lock, charging chat quota, retrieving products, invoking ADK or persisting a new turn. Existing successful idempotent replays do not re-run processing.
- A match returns HTTP 422 with a safe, friendly refusal. The existing web client displays this message and leaves the composer usable. An unavailable, incomplete or misconfigured check returns HTTP 503 with a retry message. Neither condition silently falls back to an unprotected model.
- Only the latest message is submitted, never conversation history, system instructions, reference photos or profile data. Existing SSE response streaming remains intact; output tokens are not buffered for Model Armor output screening.
- Typed messages within voice sessions are screened before forwarding to Gemini Live. An ADK `before_tool_callback` screens the latest available voice transcript (or the tool's customer request/question if transcription has not arrived) before recommendations, selection, preview or navigation actions. Actions with no inspectable request fail closed. Safe results are cached only within the current voice turn; failures are never cached. Automatic spoken navigation uses the same gate.
- **Native live audio still reaches Gemini Live directly.** This text sanitization API does not inspect the raw audio stream and cannot retract speech already emitted. Tool protection is not a claim of pre-model audio filtering; Gemini's own provider safety remains in place. Uploaded images, product enrichment and generated output are outside this incoming-text gate. There is no user-provided freeform prompt on direct fitting-room generation endpoints; their item IDs and selections are validated separately.
- Sanitization payload logging is disabled in the dedicated template. Application logs contain only generic failure type, never request/provider bodies. This change does not alter other templates or project/organization floor settings. Sensitive Data Protection is not enabled, so ordinary account and clothing preference data is not blanket-blocked as PII.

## Configuration and deployment

Local credential-free runs default to `ENABLE_MODEL_ARMOR=false`. To enable real checks set:

```dotenv
ENABLE_MODEL_ARMOR=true
MODEL_ARMOR_TEMPLATE=projects/data-workshops/locations/us-central1/templates/flairify-input-guard
```

Create or update the policy and grant the API runtime `roles/modelarmor.user` (not template administration):

```sh
.venv/bin/python scripts/configure_model_armor.py --project data-workshops --region us-central1 --gcloud-login
gcloud builds triggers update github flairify-backend-main --project=data-workshops --region=us-central1 --update-substitutions='_ENABLE_MODEL_ARMOR=true,_MODEL_ARMOR_TEMPLATE=projects/data-workshops/locations/us-central1/templates/flairify-input-guard'
```

Omit `--gcloud-login` to use operator ADC instead. Run setup with an authorized operator identity, never by granting admin rights to the application. `cloudbuild.yaml` persists these settings on subsequent API deploys. Frontend and worker do not require Model Armor IAM permissions. No new dependencies were needed; the pinned Google Auth and HTTP transport are already in the lockfile. Model Armor calls incur GCP usage and add a check before response streaming; one retry is allowed for HTTP 429/5xx, with bounded connect/read timeouts.

Official references: [Sanitize prompts](https://docs.cloud.google.com/model-armor/sanitize-prompts-responses), [result semantics](https://docs.cloud.google.com/model-armor/reference/rest/v1/SanitizationResult), [template fields](https://docs.cloud.google.com/model-armor/reference/rest/v1/projects.locations.templates), [IAM](https://docs.cloud.google.com/model-armor/access-control/roles-permissions).

## Collected validation, 18 October 2026

Seven direct calls to the real configured template: five ordinary fashion requests passed (Mumbai office trip, follow-up jacket variation, nude-colour beach clothing, body-confidence styling, named kurta/sandals preview). One dangerous-instructions request and one system-prompt/key-exfiltration injection were blocked. Observed check latency was 0.301–0.880 seconds from the developer machine. This small smoke check does not establish detection accuracy, language coverage or production latency.

Automated tests cover JSON/SSE refusal before side effects, history continuity for allowed turns, private provider errors, malformed/partial/skipped detector results, transient retry, configuration validation, and typed/native-tool voice checks. Tests stub the provider; they do not claim raw-audio filtering.
