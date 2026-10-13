import asyncio

import pytest

from app.agents.live_stylist import BlockingTool, LiveStylist
from app.models import Conversation
from app.services.voice_navigation import destination
from app.store import store


@pytest.mark.parametrize(
    ("spoken", "target"),
    [
        ("styles", "stylist"),
        ("chat", "stylist"),
        ("My Closet", "wardrobe"),
        ("closet", "wardrobe"),
        ("  SAVED   LOOKS ", "saved"),
        ("shop", "inventory"),
        ("fitting room", "fitting"),
        ("my orders", "orders"),
        ("settings", "profile"),
        ("seller studio", "admin"),
        ("previous page", "back"),
        ("original page", "origin"),
    ],
)
def test_navigation_resolves_only_known_screens(spoken, target):
    assert destination(spoken) == target


def test_navigation_deduplicates_a_turn_and_preserves_chat_without_generation(onboarded):
    events = []
    uid = onboarded[0]["user_id"]

    async def emit(kind, data):
        events.append((kind, data))

    async def noop(*args):
        pass

    async def check():
        conversation = Conversation(voice_selection=[{"kind": "product", "id": "selected"}])
        state = LiveStylist(
            {"uid": uid, "request": {"reference_outfit_id": "focus"}}, conversation, {}, emit, noop
        )
        assert BlockingTool(state.navigate)._get_declaration().name == "navigate"
        state.input_text = "Take me back"
        first = await state.navigate("back")
        assert first == await state.navigate("back")
        assert len(events) == 1 and events[0][0] == "navigation"
        for invalid in [
            "https://example.com",
            "javascript:alert(1)",
            "/admin/delete",
            "purchase",
            "__proto__",
        ]:
            assert "error" in await state.navigate(invalid)
        assert len(events) == 1
        assert not state.closed and state.bound is None
        assert not store().list("jobs", uid)
        state.output_text = "Taking you back."
        await state.finish()
        saved = store().get("conversations", uid, conversation.id)
        assert saved["voice_selection"] == conversation.voice_selection
        assert state.options["reference_outfit_id"] == "focus"
        state.input_text = "Back once more"
        second = await state.navigate("back")
        assert first["request_id"] != second["request_id"]
        assert sum(kind == "navigation" for kind, _ in events) == 2
        await state.close()

    asyncio.run(check())
