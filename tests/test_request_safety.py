import asyncio
from copy import deepcopy
from unittest.mock import Mock

import pytest
import requests
from fastapi import HTTPException

from app.config import settings
from app.models import Conversation
from app.services import request_safety
from app.store import store

SAFE = {
    "sanitizationResult": {
        "filterMatchState": "NO_MATCH_FOUND",
        "invocationResult": "SUCCESS",
        "filterResults": {
            "rai": {
                "raiFilterResult": {"executionState": "EXECUTION_SUCCESS", "matchState": "NO_MATCH_FOUND"}
            },
            "pi_and_jailbreak": {
                "piAndJailbreakFilterResult": {
                    "executionState": "EXECUTION_SUCCESS",
                    "matchState": "NO_MATCH_FOUND",
                }
            },
        },
    }
}


@pytest.fixture
def armor(client, monkeypatch):
    cfg = settings()
    monkeypatch.setattr(cfg, "enable_model_armor", True)
    monkeypatch.setattr(
        cfg,
        "model_armor_template",
        "projects/data-workshops/locations/us-central1/templates/flairify-input-guard",
    )
    response = Mock(status_code=200)
    response.json.return_value = deepcopy(SAFE)
    session = Mock()
    session.post.return_value = response
    monkeypatch.setattr(request_safety, "_session", lambda: session)
    return session, response


def test_local_default_never_calls_google(client, monkeypatch):
    monkeypatch.setattr(
        request_safety, "_session", lambda: pytest.fail("Local mode must not require credentials")
    )
    request_safety.check("Find a shirt")


def test_regional_api_receives_only_latest_text(armor):
    session, _ = armor
    request_safety.check("A nude-colour top for a beach holiday")
    session.post.assert_called_once_with(
        "https://modelarmor.us-central1.rep.googleapis.com/v1/projects/data-workshops/locations/us-central1/templates/flairify-input-guard:sanitizeUserPrompt",
        json={"userPromptData": {"text": "A nude-colour top for a beach holiday"}},
        timeout=(3, 8),
    )


@pytest.mark.parametrize("endpoint", ["/api/chat", "/api/chat/stream"])
def test_block_before_search_persistence_or_quota(client, onboarded, armor, monkeypatch, endpoint):
    from app.services import recommendations

    session, response = armor
    response.json.return_value["sanitizationResult"]["filterMatchState"] = "MATCH_FOUND"
    monkeypatch.setattr(
        recommendations, "recommend", lambda *a, **k: pytest.fail("Blocked request reached retrieval")
    )
    uid, headers = onboarded[0]["user_id"], onboarded[1]
    before = store().list("quotas", uid)
    result = client.post(
        endpoint, headers=headers, json={"message": "blocked fixture", "request_id": "blocked-turn"}
    )
    assert result.status_code == 422 and result.json()["detail"] == request_safety.BLOCKED
    for kind in ("conversations", "chat_turns", "chat_locks", "outfits", "jobs"):
        assert store().list(kind, uid) == []
    assert store().list("quotas", uid) == before
    assert session.post.call_count == 1


@pytest.mark.parametrize("change", ["partial", "missing", "skipped", "unknown", "malformed", "nested_match"])
def test_incomplete_or_inconsistent_result_never_allows_request(armor, change):
    _, response = armor
    result = response.json.return_value["sanitizationResult"]
    if change == "partial":
        result["invocationResult"] = "PARTIAL"
    elif change == "missing":
        result["filterResults"].pop("rai")
    elif change == "skipped":
        result["filterResults"]["rai"]["raiFilterResult"]["executionState"] = "EXECUTION_SKIPPED"
    elif change == "unknown":
        result["filterMatchState"] = "FILTER_MATCH_STATE_UNSPECIFIED"
    elif change == "malformed":
        result["filterResults"]["rai"] = []
    else:
        result["filterResults"]["rai"]["raiFilterResult"]["matchState"] = "MATCH_FOUND"
    with pytest.raises(HTTPException) as caught:
        request_safety.check("a request")
    assert caught.value.status_code == (422 if change == "nested_match" else 503)


def test_provider_error_is_private_and_fail_closed(client, onboarded, armor, caplog):
    session, _ = armor
    session.post.side_effect = requests.Timeout("private customer prompt and provider payload")
    result = client.post("/api/chat/stream", headers=onboarded[1], json={"message": "Find office clothes"})
    assert result.status_code == 503 and result.json()["detail"] == request_safety.UNAVAILABLE
    assert "private customer" not in caplog.text + result.text


def test_transient_response_retries_once(armor):
    session, response = armor
    busy = Mock(status_code=429)
    session.post.side_effect = [busy, response]
    request_safety.check("A travel outfit")
    assert session.post.call_count == 2
    busy.close.assert_called_once()


@pytest.mark.parametrize(
    "resource",
    [
        "",
        "https://evil.example/a",
        "projects/data-workshops/locations/global/templates/test",
        "projects/data-workshops/locations/us-central1/templates/test?redirect=evil",
    ],
)
def test_invalid_configuration_cannot_change_request_destination(armor, monkeypatch, resource):
    session, _ = armor
    monkeypatch.setattr(settings(), "model_armor_template", resource)
    with pytest.raises(HTTPException) as caught:
        request_safety.check("a request")
    assert caught.value.status_code == 503
    session.post.assert_not_called()


def test_allowed_stream_and_followup_keep_history(client, onboarded, armor):
    first = client.post(
        "/api/chat", headers=onboarded[1], json={"message": "Office clothes under 5000"}
    ).json()
    cid = first["conversation"]["id"]
    followup = "Keep the shirt but suggest different shoes"
    second = client.post(
        "/api/chat/stream", headers=onboarded[1], json={"message": followup, "conversation_id": cid}
    )
    assert second.status_code == 200 and "event: done" in second.text
    assert len(store().get("conversations", onboarded[0]["user_id"], cid)["messages"]) == 4
    assert armor[0].post.call_args.kwargs["json"] == {"userPromptData": {"text": followup}}


def test_voice_typed_input_and_native_tool_guard(armor, onboarded):
    from app.agents.live_stylist import LiveStylist

    events = []

    async def emit(kind, data):
        events.append((kind, data))

    async def audio(raw):
        pass

    async def check():
        state = LiveStylist({"uid": onboarded[0]["user_id"], "request": {}}, Conversation(), {}, emit, audio)
        armor[1].json.return_value["sanitizationResult"]["filterMatchState"] = "MATCH_FOUND"
        with pytest.raises(HTTPException):
            await state.text("blocked fixture")
        assert state.input_text == "" and not events
        state.input_text = "blocked native transcript"
        result = await state.before_tool(None, {"query": "sanitized model paraphrase"}, None)
        assert result["error"] == request_safety.BLOCKED
        assert armor[0].post.call_args.kwargs["json"]["userPromptData"]["text"] == state.input_text
        assert (await state.before_tool(None, {}, None))["error"]
        state.input_text = ""
        # Tools without any usable user transcript fail closed, never silently bypass.
        assert (await state.before_tool(None, {}, None))["error"] == request_safety.UNAVAILABLE
        armor[1].json.return_value = deepcopy(SAFE)
        state.input_text = "Show the selected kurta on me"
        assert await state.before_tool(None, {}, None) is None
        count = armor[0].post.call_count
        assert await state.before_tool(None, {}, None) is None
        assert armor[0].post.call_count == count

    asyncio.run(check())
