"""Real fixture records, with a stubbed image provider; no paid calls."""

import asyncio
import io
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from PIL import Image

from app.agents.live_stylist import LiveStylist
from app.auth import Principal
from app.config import settings
from app.models import Conversation, Message, UserProfile
from app.services import ai, inventory, media, voice_actions
from app.store import store

NAMES = ["Vishudh Women Brown Kurta", "Cobblerz Women Brown Sandals"]


@pytest.fixture
def actions(client, monkeypatch):
    cfg = settings()
    monkeypatch.setattr(cfg, "enable_paid_ai", True)
    monkeypatch.setattr(cfg, "image_edit_model", "configured-test-google-image")
    monkeypatch.setattr(cfg, "allow_sample_try_on", True)
    principal = Principal("voice-actions-test")
    profile = UserProfile(
        name="Asha",
        clothing_size="M",
        shoe_size="39",
        preferred_store_id="bandra",
        consent={"remember_preferences": False, "ai_photo_processing": True},
    ).model_dump()
    store().put("profiles", principal.uid, "me", profile)
    inventory.seed_catalog("retailer")
    products = [next(p for p in inventory.fixture_products().values() if p["name"] == n) for n in NAMES]
    look = {
        "id": "retrieved",
        "title": "Brown office look",
        "products": products,
        "owned": [],
        "occasion": "office",
        "total": sum(p["price"] for p in products),
        "complete": True,
        "sample": True,
        "explanation": "Test look",
    }
    conversation = Conversation(messages=[Message(role="assistant", content="Try this look", outfits=[look])])
    voice_actions.persist(principal, conversation)
    raw = io.BytesIO()
    Image.new("RGB", (100, 160), "white").save(raw, "JPEG")
    mid = media.save(principal.uid, raw.getvalue(), "image/jpeg")
    store().put("references", principal.uid, "full_body", {"id": "full_body", "media_id": mid})
    calls = []

    class Provider:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        @property
        def models(self):
            return self

        def generate_content(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                parts=[
                    SimpleNamespace(inline_data=SimpleNamespace(data=raw.getvalue(), mime_type="image/jpeg"))
                ]
            )

    monkeypatch.setattr(ai, "client", lambda **kwargs: Provider())
    yield principal, profile, conversation, calls


def test_named_garments_generate_together_once_and_survive_reconnection(actions):
    principal, profile, conversation, calls = actions
    result = voice_actions.choose(principal, conversation, profile, NAMES)
    assert [p["name"] for p in result["pieces"]] == NAMES
    assert not calls and not store().list("jobs", principal.uid)
    first = voice_actions.preview(principal, conversation, profile)
    reloaded = Conversation.model_validate(store().get("conversations", principal.uid, conversation.id))
    again = voice_actions.preview(principal, reloaded, profile)
    assert first["id"] == again["id"] and len(calls) == 1
    job = store().get("jobs", principal.uid, first["id"])
    assert job["status"] == "succeeded"
    assert [p["name"] for p in job["result"]["pieces"]] == NAMES
    assert job["result"]["provider"] == "google-gemini-image-edit"
    assert store().get("media", principal.uid, job["result"]["media_id"])
    assert not store().get("jobs", "someone-else", first["id"])
    assert reloaded.voice_preview_job_id == first["id"]


def test_ambiguous_unknown_and_foreign_items_do_not_change_selection(actions):
    principal, profile, conversation, _ = actions
    voice_actions.choose(principal, conversation, profile, [NAMES[0]])
    for name in ["Brown", "an imaginary hat", "product:not-retrieved"]:
        with pytest.raises(HTTPException):
            voice_actions.choose(principal, conversation, profile, [name], replace=True)
        assert [p["name"] for p in conversation.voice_selection] == [NAMES[0]]
    with pytest.raises(HTTPException):
        voice_actions.choose(Principal("other"), Conversation(), profile, NAMES)


def test_conflicts_are_explicit_and_remove_and_clear_work(actions):
    principal, profile, conversation, _ = actions
    original = conversation.messages[0].outfits[0]["products"][1]
    other = {**original, "id": "other-shoes", "name": "Alternative brown sandals", "image": "media:test"}
    store().put("products", "retailer", other["id"], other)
    conversation.messages[0].outfits[0]["products"].append(other)
    chosen = voice_actions.choose(principal, conversation, profile, [*NAMES, other["name"]])
    assert len(chosen["pieces"]) == 2 and len(chosen["adjustments"]) == 1
    assert chosen["pieces"][-1]["id"] == "other-shoes"
    voice_actions.choose(principal, conversation, profile, [other["name"]], remove=True)
    assert len(conversation.voice_selection) == 1
    voice_actions.choose(principal, conversation, profile, [], replace=True)
    with pytest.raises(HTTPException):
        voice_actions.preview(principal, conversation, profile)


def test_stock_photo_and_consent_rechecked_before_generation(actions):
    principal, profile, conversation, calls = actions
    voice_actions.choose(principal, conversation, profile, NAMES)
    store().delete("references", principal.uid, "full_body")
    with pytest.raises(HTTPException, match="Upload a clear photo"):
        voice_actions.preview(principal, conversation, profile)
    product = store().get("products", "retailer", conversation.voice_selection[0]["id"])
    product["active"] = False
    store().put("products", "retailer", product["id"], product)
    with pytest.raises(HTTPException, match="unavailable"):
        voice_actions.preview(principal, conversation, profile)
    assert not calls


def test_selection_error_blocks_generation_but_does_not_end_voice(actions):
    principal, profile, conversation, calls = actions
    events = []

    async def emit(kind, data):
        events.append((kind, data))

    async def audio(data):
        pass

    async def journey():
        state = LiveStylist({"uid": principal.uid, "request": {}}, conversation, profile, emit, audio)
        await state.select_garments(NAMES)
        assert (await state.select_garments(["unknown hat"]))["error"]
        assert (await state.see_it_on_me())["error"] and not calls
        await state.select_garments(NAMES)
        result = await state.see_it_on_me()
        assert result["job_id"] and not state.closed
        state.output_text = "Your preview is being created in Fitting Room."
        await state.finish()
        assert conversation.messages[-1].preview_job_id == result["job_id"]
        assert {k for k, _ in events} >= {"selection", "preview", "turn"}
        await state.close()

    asyncio.run(journey())


def test_retrieval_timeout_is_recoverable_in_same_call(actions, monkeypatch):
    principal, profile, conversation, _ = actions

    async def noop(*args):
        pass

    async def broken(**kwargs):
        raise TimeoutError("private provider text")

    async def journey():
        state = LiveStylist({"uid": principal.uid, "request": {}}, conversation, profile, noop, noop)
        bound = await state.tools("Another look")
        monkeypatch.setattr(bound, "find_outfit_candidates", broken)
        result = await state.suggest_outfits("another look", "office", "office")
        assert "too long" in result["error"] and "private" not in result["error"]
        assert not state.closed
        assert (await state.select_garments(NAMES))["pieces"]
        await state.close()

    asyncio.run(journey())
