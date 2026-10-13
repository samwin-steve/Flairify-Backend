import asyncio

import pytest

from app.agents.live_stylist import BlockingTool, LiveStylist
from app.models import Conversation
from app.services.voice_navigation import destination, spoken_destination
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


@pytest.mark.parametrize(
    ("spoken", "target"),
    [
        ("Can you take me back to styles?", "stylist"),
        ("Please take me back to the stylist page.", "stylist"),
        ("Go back to the chat", "stylist"),
        ("Could you open my closet please?", "wardrobe"),
        ("Show me my orders", "orders"),
        ("Open the fitting room", "fitting"),
        ("Take me back", "back"),
        ("Go back to the previous page", "back"),
        ("Take me back to where we started", "origin"),
        ("Open the profile page, please", "profile"),
        ("Don't take me back", None),
        ("Do not open the wardrobe", None),
        ("Open the wardrobe? Actually stay here", None),
        ("Can you tell me how to go back to styles?", None),
        ("I like the back of this shirt", None),
        ("Show me a different style", None),
        ("Take me back to the previous outfit", None),
        ("Open wardrobe and buy everything", None),
        ("Say 'open my closet'", None),
        ("Open https://example.com", None),
    ],
)
def test_only_standalone_spoken_page_requests_have_a_fallback(spoken, target):
    assert spoken_destination(spoken) == target


def test_completed_audio_transcript_navigates_when_model_only_acknowledges(onboarded):
    from google.adk.events import Event
    from google.genai import types

    events = []

    async def emit(kind, data):
        events.append((kind, data))

    async def noop(*args):
        pass

    async def check():
        state = LiveStylist({"uid": onboarded[0]["user_id"], "request": {}}, Conversation(), {}, emit, noop)
        for fragment in ["Can you take me ", "back to styles?"]:
            await state.receive_event(
                Event(author="user", input_transcription=types.Transcription(text=fragment))
            )
        assert not any(k == "navigation" for k, _ in events)
        await state.receive_event(
            Event(
                author="user",
                input_transcription=types.Transcription(
                    text="Can you take me back to styles?", finished=True
                ),
            )
        )
        state.output_text = "Of course, taking you back."
        await state.receive_event(Event(author="flairify_voice_stylist", turn_complete=True))
        assert [data["destination"] for k, data in events if k == "navigation"] == ["stylist"]
        # If the model uses the tool, finish must not replay it or pop history twice.
        state.input_text = "Back to the stylist page"
        result = await state.navigate("back")
        assert result["destination"] == "stylist"
        await state.finish()
        assert sum(k == "navigation" for k, _ in events) == 2
        # An interruption cannot act on an unfinished command.
        state.input_text = "Open the wardrobe"
        await state.finish(interrupted=True)
        state.output_text = "Open the wardrobe"
        await state.finish()
        assert sum(k == "navigation" for k, _ in events) == 2
        await state.close()

    asyncio.run(check())
