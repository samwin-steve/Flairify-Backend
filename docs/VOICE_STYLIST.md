# Talk with your stylist

Signed-in customers can tap **Talk** in Stylist, allow microphone access and have a spoken conversation. Gemini answers with native generated audio and live transcripts. The voice agent uses saved shopping settings, recent conversation history and the same authoritative outfit tools as text chat. It can suggest looks, refer to the second look, replace a particular garment and explain a previous choice. Warm language is an opinion about retrieved clothes and preferences, never a promise of fit or invented personal knowledge.

## Google integration

The implementation uses Google ADK `Runner.run_live`, `LiveRequestQueue` and the Google Gen AI SDK configured for Vertex AI. The verified configuration on 13 October 2026 is `LIVE_MODEL=gemini-3.8-live`, `LIVE_LOCATION=us-central1`, `LIVE_VOICE=Aoede`. Model IDs and availability are deployment configuration. The default model is empty, which disables voice until explicitly configured. Google API credentials stay in the Cloud Run runtime identity; no paid external speech provider or browser speech-recognition service is used.

Official references: [Live API](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/live-api), [ADK integration](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/live-api/get-started-adk), [Gemini Live model](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-live). The model has native audio output; transcript events provide the written copy.

## Data flow and security

1. The browser asks for microphone permission only after Talk is selected. An AudioWorklet downsamples mono audio to PCM16 at 16 kHz. Incoming model audio is played at 24 kHz using Web Audio.
2. Authenticated `POST /api/voice/sessions` verifies Firebase identity, onboarding and ownership of the selected conversation/look. A single chat lease prevents simultaneous text/voice mutations.
3. The server returns a random, single-use ticket expiring after 45 seconds. Only its hash is stored. The browser connects directly to the backend's WSS endpoint and sends the ticket in its first frame, never in the URL. WebSocket Origin must exactly match the configured frontend origin. HTTP CORS alone is insufficient for WebSockets.
4. The backend consumes the ticket atomically, connects to Vertex AI and supplies bounded recent history, profile settings and allowed tools. Untrusted product descriptions and customer content cannot authorize extra tools. Live tools can retrieve/discuss outfits; purchases and generation still require the existing explicit UI actions.
5. Outfit tools use Gemini Embedding 2 / Firestore retrieval, current serving inventory, whole-outfit ranking and existing compatibility evidence. Product IDs, selected sizes, stock, total budget and retained garments are checked by backend services. Structured cards and spoken transcripts flow over the same WebSocket.
6. Finished or interrupted turns are saved to the customer's existing Firestore conversation. Raw microphone audio and generated spoken audio are not persisted by Flairify. ADK audio/blob saving is disabled. Transcripts appear in ordinary chat history, including after refresh; the UI states that transcripts are saved.

The ticket cancellation endpoint deletes an unused owned ticket. Closing the socket saves pending transcript content and releases the lease. Used tickets are removed at disconnect; abandoned unused records are unusable after expiry and leases self-expire. Automatic deletion of abandoned ticket records is not yet scheduled. Their stored payload contains the UID and chat options, not the bearer secret or audio.

## Conversation and playback

The session begins with a short greeting. Function calls are declared blocking so the model waits for grounded results. Live acknowledgement, tool and spoken-answer events can be separate provider subturns; the adapter combines them into one application turn. Input and output transcripts are accumulated without repeating final segments. Interruptions stop queued playback and preserve the interrupted reply. Saved transcript messages use `source=voice` and stable IDs.

Mute stops audio forwarding and ends the current input stream; unmute resumes. End stops microphone tracks and playback immediately, then briefly allows transcript persistence. Leaving the page, signing out or hiding the tab stops microphone capture. Tap Talk again to open a new connection with saved context. Transport-level seamless session resumption is not implemented.

The frontend allows microphone access only for itself with `Permissions-Policy: microphone=(self)`. The voice feature never requests the camera. The speaking orb respects reduced-motion preferences. Permission denial, unsupported audio APIs and connection failures leave text chat available. A network error never produces a fabricated spoken success or substitute outfit.

## Configuration and cost bounds

Set `ENABLE_PAID_AI=true`, `GOOGLE_CLOUD_PROJECT`, `LIVE_MODEL`, `LIVE_LOCATION` and `LIVE_API_URL` (the public API HTTPS origin). Set `CORS_ORIGINS` to the exact web origin, without a trailing slash. Cloud Build derives the existing Cloud Run frontend/API URLs and sets the API request timeout to 360 seconds. The backend trigger explicitly enables the verified live model. Anonymous demo accounts cannot initiate paid voice; Firebase accounts can when `ALLOW_FIREBASE_IN_DEMO=true` is intentionally configured.

Defaults: `MAX_LIVE_SECONDS=300`, `MAX_DAILY_VOICE_SESSIONS=6` per user and `MAX_GLOBAL_DAILY_VOICE_SESSIONS=12`. Catalogue searches share the existing 50-per-user / 50-global daily chat tool limit. Sessions also bound messages, audio-frame size, input rate, output playback queue and concurrent generation through existing services. Cloud Run remains scale-to-zero with at most two API instances. These application quotas are safeguards, not a monetary spending cap. No cost-per-minute estimate has been measured for this release.

Local demo runs without credentials and reports voice unavailable. For live local development, configure Vertex ADC plus Firebase, allow the exact local frontend origin and set `LIVE_API_URL=http://localhost:8000`; localhost WS is permitted. Deployed connections require WSS. HTTP still uses the existing Next.js proxy; WebSocket audio goes directly to the configured backend.

## Verification and limits

Automated backend tests cover authorization, cross-user access, ticket reuse/expiry, session limits, chat leases, origin checks, malformed PCM, interrupted-turn persistence and multi-part Live event assembly. Frontend logic tests cover PCM conversion/resampling and playback interruption. Browser tests exercise the actual capture worklet with an explicitly simulated provider stream, mute/end, microphone denial, restored transcripts, reduced motion and tested accessibility/layout rules. Simulated audio is not evidence of a live provider call.

A separate real Vertex/ADK probe produced 2,209,934 audio bytes across 293 chunks while recommending an Independence Day office look, changing shoes in the second look and discussing why it worked. That probe used text inputs and real native-audio outputs. Its temporary owner records were removed. A deployed three-turn browser check also passed with synthesized spoken inputs through the real capture/transport path and real Google spoken output; see [collected results](live-voice-deployed-results.json) and [verification](VERIFICATION.md).

Physical iOS/Android microphone behavior, noisy environments, accent/language accuracy and broad recommendation-quality evaluation remain unmeasured. This release adds audio conversation, not camera streaming. Spoken recommendations can still be imperfect; retrieved cards and checkout validation remain the authoritative product facts.

## Voice availability during sign-in

The frontend waits until Firebase authentication has initialized before requesting service capabilities and caches guest/account capabilities separately. Abandoned capability requests are cancelled. For a signed-in customer, Talk asks the authenticated ticket endpoint for current availability; an absent or stale guest capability flag cannot reject the request locally. The backend still enforces sign-in, model configuration, ownership, quotas and the active-chat lease. Fitting Room shares the account capability cache. Demo Talk opens account sign-in without microphone capture or paid requests.

A deployed reproduction with a temporary Firebase account and deliberately delayed real capability responses reproduced “Voice is unavailable right now” even though the same authenticated server reported voice enabled. No voice session was started during the failing reproduction. This establishes a frontend initialization problem rather than a disabled Google Live deployment. The local correction passes 25 logic tests and 38 desktop/mobile browser journeys, including delayed initialization, a stale false voice flag, an honest server refusal, microphone denial and demo sign-in. Production compilation and TypeScript checks pass.

Cloud Build `cf8c8570-9b56-4276-b8e0-9451e83c6852` deployed source `8f90a2e` as `flairify-web-00019-d4x`. Repeating the delayed-capability check after refresh made one authenticated voice request, connected to real Gemini Live and received 34,562 native audio bytes plus a transcript and saved turn. End closed the call. Before the fix, the same account received the reported unavailable message and made zero voice requests. The browser used a simulated microphone; real human speech and physical-device acoustics were not retested. No model or quota settings changed. See [collected reproduction and deployment evidence](live-voice-config-results.json).

The temporary Firebase identity and five owner-scoped records were deleted; no QA owner records or media remained.
