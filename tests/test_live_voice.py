import asyncio
import hashlib
import time

import pytest
from fastapi import HTTPException

from app.auth import Principal, principal
from app.config import settings
from app.main import app
from app.models import Conversation
from app.services.live_voice import VoiceRequest, consume_ticket, create_ticket
from app.store import store


@pytest.fixture
def voice_user(onboarded, monkeypatch):
    uid = onboarded[0]["user_id"]
    p = Principal(uid)
    cfg = settings()
    monkeypatch.setattr(cfg, "enable_paid_ai", True)
    monkeypatch.setattr(cfg, "gemini_model", "configured-test-model")
    monkeypatch.setattr(cfg, "live_model", "configured-test-live-model")
    app.dependency_overrides[principal] = lambda: p
    yield p
    app.dependency_overrides.pop(principal, None)


def test_voice_requires_real_account_and_configuration(client, onboarded):
    assert client.post("/api/voice/sessions", json={}).status_code == 401
    assert client.post("/api/voice/sessions", headers=onboarded[1], json={}).status_code == 403
    assert not client.get("/api/config", headers=onboarded[1]).json()["voice"]


def test_voice_ticket_is_single_use_and_blocks_overlapping_chat(client, voice_user):
    result = client.post("/api/voice/sessions", json={})
    assert result.status_code == 200
    data = result.json()
    assert "ticket" not in data["url"] and data["expires_in"] == 45
    assert client.post("/api/voice/sessions", json={}).status_code == 409
    key, record = consume_ticket(data["ticket"])
    assert record["uid"] == voice_user.uid
    assert store().get("chat_locks", voice_user.uid, "active")["key"] == key
    with pytest.raises(HTTPException) as e:
        consume_ticket(data["ticket"])
    assert e.value.status_code == 401
    assert client.post("/api/chat", json={"message": "Find an office look"}).status_code == 409


def test_voice_ticket_expiry_and_cancel_are_owner_scoped(client, voice_user):
    ticket = create_ticket(voice_user, VoiceRequest())["ticket"]
    key = hashlib.sha256(ticket.encode()).hexdigest()
    app.dependency_overrides[principal] = lambda: Principal("another-user")
    client.post("/api/voice/sessions/cancel", json={"ticket": ticket})
    assert store().get("voice_tickets", "system", key)
    app.dependency_overrides[principal] = lambda: voice_user
    client.post("/api/voice/sessions/cancel", json={"ticket": ticket})
    assert not store().get("voice_tickets", "system", key)
    assert store().get("chat_locks", voice_user.uid, "active")["until"] == 0
    ticket = create_ticket(voice_user, VoiceRequest())["ticket"]
    key = hashlib.sha256(ticket.encode()).hexdigest()
    store().mutate("voice_tickets", "system", key, lambda r: {**r, "expires": time.time() - 1})
    with pytest.raises(HTTPException) as e:
        consume_ticket(ticket)
    assert e.value.status_code == 401


def test_voice_rejects_foreign_chat_and_unknown_reference(client, voice_user):
    other = Conversation()
    store().put("conversations", "other-owner", other.id, other.model_dump())
    assert client.post("/api/voice/sessions", json={"conversation_id": other.id}).status_code == 404
    assert client.post("/api/voice/sessions", json={"reference_outfit_id": "foreign-look"}).status_code == 422


def test_voice_has_no_daily_session_cap_even_with_old_exhausted_counters(client, voice_user):
    from app.services.chat import release

    key = "voice-session:" + time.strftime("%Y-%m-%d", time.gmtime())
    for owner in (voice_user.uid, "live-ai"):
        store().put("quotas", owner, key, {"count": 10000})
    # New calls and recovery use the same ticket flow. Neither reads nor charges
    # the retired session counter; exclusive leases and single-use tickets remain.
    for _ in range(14):
        response = client.post("/api/voice/sessions", json={})
        assert response.status_code == 200
        ticket_key, record = consume_ticket(response.json()["ticket"])
        release(record["uid"], ticket_key)
        store().delete("voice_tickets", "system", ticket_key)
    for owner in (voice_user.uid, "live-ai"):
        assert store().get("quotas", owner, key) == {"count": 10000}


def test_websocket_rejects_origin_and_invalid_ticket(client):
    from starlette.websockets import WebSocketDisconnect

    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect("/api/voice/ws", headers={"origin": "https://untrusted.example"}),
    ):
        pass
    with client.websocket_connect("/api/voice/ws", headers={"origin": "http://localhost:3000"}) as ws:
        ws.send_json({"ticket": "invalid"})
        assert ws.receive_json()["type"] == "error"


def test_transport_releases_microphone_session_lease(client, voice_user, monkeypatch):
    from app.agents.live_stylist import LiveStylist

    async def fake_run(self):
        await self.emit("ready", {"conversation_id": self.conversation.id})
        await asyncio.Future()

    monkeypatch.setattr(LiveStylist, "run", fake_run)
    data = client.post("/api/voice/sessions", json={}).json()
    with client.websocket_connect("/api/voice/ws", headers={"origin": "http://localhost:3000"}) as ws:
        ws.send_json({"ticket": data["ticket"]})
        assert ws.receive_json()["type"] == "ready"
        ws.send_bytes(b"\x00")  # malformed PCM cannot reach a model
        assert ws.receive_json()["type"] == "error"
        assert ws.receive()["type"] == "websocket.close"
    assert store().get("chat_locks", voice_user.uid, "active")["until"] == 0
    assert not store().get("voice_tickets", "system", hashlib.sha256(data["ticket"].encode()).hexdigest())


def test_voice_keeps_actual_look_context_and_persists_interruptions(client, onboarded):
    from app.agents.live_stylist import LiveStylist

    uid = onboarded[0]["user_id"]
    conversation = Conversation()
    events = []

    async def emit(kind, data):
        events.append((kind, data))

    async def audio(raw):
        pass

    async def journey():
        state = LiveStylist(
            {"uid": uid, "request": {"include_wardrobe": False}},
            conversation,
            store().get("profiles", uid, "me"),
            emit,
            audio,
        )
        state.principal = Principal(uid, demo=True)  # deterministic catalogue fixture; never a live model
        await state.text("An office outfit under ₹5,000")
        result = await state.suggest_outfits("ignored paraphrase", "smart office outfit", "Office")
        assert result["outfits"]
        first = state.bound.result["outfits"][1]
        state.output_text = "Ooh, I would try the second look for this."
        await state.finish()
        await state.text("Keep the second look's shirt and trousers, but swap the shoes")
        result = await state.suggest_outfits(
            "ignored",
            "different office shoes",
            "Office",
            refine=True,
            reference_outfit_id=first["id"],
            change_categories=["shoes"],
        )
        kept = {p["id"] for p in first["products"] if p["category"] != "shoes"}
        for outfit in state.bound.result["outfits"]:
            assert kept <= {p["id"] for p in outfit["products"]}
            assert outfit["total"] <= 5000
        state.output_text = "I kept your preferred pieces and changed the shoes."
        await state.finish(interrupted=True)
        saved = store().get("conversations", uid, conversation.id)
        assert len(saved["messages"]) == 4
        assert all(m["source"] == "voice" for m in saved["messages"])
        assert saved["messages"][-1]["interrupted"]
        assert not store().get("conversations", "other-user", conversation.id)
        await state.text("Why does this version work?")
        explanation = await state.discuss_looks("Why?")
        assert explanation["looks"] and state.bound.result["outfits"] == []
        state.output_text = "The colours work together."
        await state.close()
        assert len(store().get("conversations", uid, conversation.id)["messages"]) == 6

    asyncio.run(journey())


def test_voice_greeting_does_not_clear_selected_look(client, onboarded):
    from app.agents.live_stylist import LiveStylist

    async def noop(*args):
        pass

    async def check():
        state = LiveStylist(
            {"uid": onboarded[0]["user_id"], "request": {"reference_outfit_id": "chosen"}},
            Conversation(),
            {},
            noop,
            noop,
        )
        state.output_text = "Hi Asha, shall we keep working on your look?"
        await state.finish()
        assert state.options["reference_outfit_id"] == "chosen"
        assert [m.role for m in state.conversation.messages] == ["assistant"]

    asyncio.run(check())


def test_native_transcript_spacing_preserves_words_initials_and_prices(client, onboarded):
    from google.adk.events import Event
    from google.genai import types

    from app.agents.live_stylist import LiveStylist

    async def noop(*args):
        pass

    async def check():
        state = LiveStylist(
            {"uid": onboarded[0]["user_id"], "request": {}}, Conversation(), {}, noop, noop
        )
        transcript = "Let me look.I've found it.The U.S. Polo shirt is ₹999.50."
        for finished in (False, True):
            await state.receive_event(
                Event(
                    author="flairify_voice_stylist",
                    output_transcription=types.Transcription(text=transcript, finished=finished),
                )
            )
            assert state.output_text == "Let me look. I've found it. The U.S. Polo shirt is ₹999.50."
        await state.finish()
        assert (
            state.conversation.messages[-1].content
            == "Let me look. I've found it. The U.S. Polo shirt is ₹999.50."
        )

    asyncio.run(check())


def test_live_events_keep_tool_acknowledgement_and_recommendation_in_one_turn(client, onboarded):
    from google.adk.events import Event
    from google.genai import types

    from app.agents.live_stylist import BlockingTool, LiveStylist

    emitted, audio = [], []

    async def emit(kind, data):
        emitted.append((kind, data))

    async def output(raw):
        audio.append(raw)

    async def check():
        state = LiveStylist({"uid": onboarded[0]["user_id"], "request": {}}, Conversation(), {}, emit, output)
        assert BlockingTool(state.suggest_outfits)._get_declaration().behavior == types.Behavior.BLOCKING
        state.input_text = "Suggest an office outfit"
        state.output_prefix = state.output_text = "Let me find something."
        await state.receive_event(
            Event(
                author="flairify_voice_stylist",
                content=types.Content(
                    parts=[
                        types.Part(
                            function_response=types.FunctionResponse(
                                name="suggest_outfits", response={"outfits": []}
                            )
                        )
                    ]
                ),
            )
        )
        await state.receive_event(Event(author="flairify_voice_stylist", turn_complete=True))
        assert not any(k == "turn" for k, _ in emitted)
        # Live audio content can omit role; ADK author is the authoritative speaker.
        await state.receive_event(
            Event(
                author="flairify_voice_stylist",
                content=types.Content(
                    parts=[
                        types.Part(inline_data=types.Blob(data=b"\x00\x00", mime_type="audio/pcm;rate=24000"))
                    ]
                ),
            )
        )
        await state.receive_event(
            Event(
                author="flairify_voice_stylist",
                output_transcription=types.Transcription(text="Ooh, this green shirt works.", finished=False),
            )
        )
        await state.receive_event(
            Event(
                author="flairify_voice_stylist",
                output_transcription=types.Transcription(text="Ooh, this green shirt works.", finished=True),
            )
        )
        await state.receive_event(Event(author="flairify_voice_stylist", turn_complete=True))
        assert audio == [b"\x00\x00"]
        assert (
            state.conversation.messages[-1].content == "Let me find something. Ooh, this green shirt works."
        )
        assert len(state.conversation.messages) == 2
        assert sum(k == "turn" for k, _ in emitted) == 1

    asyncio.run(check())
