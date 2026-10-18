"""Server-side Model Armor input gate. Never log prompts or provider payloads."""

import logging
import re
import threading

import google.auth
from fastapi import HTTPException
from google.auth.transport.requests import AuthorizedSession

from ..config import settings

BLOCKED = "I can help with clothes and styling, but I can't help with that request. Try asking for a look or styling advice."
UNAVAILABLE = "I couldn't check that request safely. Please try again in a moment."
_local = threading.local()
_RESOURCE = re.compile(
    r"projects/[a-z][a-z0-9-]{4,62}/locations/([a-z]+-[a-z]+[0-9])/templates/[a-zA-Z0-9_-]{1,100}"
)


def _session():
    if not getattr(_local, "session", None):
        credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        _local.session = AuthorizedSession(credentials, refresh_timeout=8, max_refresh_attempts=1)
    return _local.session


def check(text: str):
    """Screen only the latest untrusted input, before AI/tools or turn persistence.

    Disabled only by explicit deployment configuration (credential-free local default).
    Missing configuration, partial inspection and provider errors fail closed.
    """
    cfg = settings()
    if not cfg.enable_model_armor:
        return
    match = _RESOURCE.fullmatch(cfg.model_armor_template)
    if not match or not isinstance(text, str) or not text.strip():
        raise HTTPException(503, UNAVAILABLE)
    url = f"https://modelarmor.{match[1]}.rep.googleapis.com/v1/{cfg.model_armor_template}:sanitizeUserPrompt"
    try:
        # One bounded retry for transient server/capacity failures; no keyword heuristics.
        for attempt in range(2):
            response = _session().post(url, json={"userPromptData": {"text": text}}, timeout=(3, 8))
            if attempt == 0 and response.status_code in (429, 500, 502, 503, 504):
                response.close()
                continue
            response.raise_for_status()
            result = response.json()["sanitizationResult"]
            break
    except Exception as exc:  # noqa: BLE001 - provider bodies can contain private content
        logging.getLogger(__name__).warning("Request safety check unavailable (%s)", type(exc).__name__)
        raise HTTPException(503, UNAVAILABLE) from None
    if not isinstance(result, dict):
        raise HTTPException(503, UNAVAILABLE)
    # A detected match remains blocked even if another detector failed.
    if result.get("filterMatchState") == "MATCH_FOUND":
        raise HTTPException(422, BLOCKED)
    filters = result.get("filterResults", {})
    required = {"rai": "raiFilterResult", "pi_and_jailbreak": "piAndJailbreakFilterResult"}
    if (
        result.get("invocationResult") != "SUCCESS"
        or result.get("filterMatchState") != "NO_MATCH_FOUND"
        or not isinstance(filters, dict)
    ):
        raise HTTPException(503, UNAVAILABLE)
    for name, key in required.items():
        value = filters.get(name, {})
        item = value.get(key, {}) if isinstance(value, dict) else {}
        if not isinstance(item, dict) or item.get("executionState") != "EXECUTION_SUCCESS":
            raise HTTPException(503, UNAVAILABLE)
        if item.get("matchState") == "MATCH_FOUND":
            raise HTTPException(422, BLOCKED)
        if item.get("matchState") != "NO_MATCH_FOUND":
            raise HTTPException(503, UNAVAILABLE)
