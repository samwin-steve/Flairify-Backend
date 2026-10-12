"""ADK Runner with actual Gemini streaming; no external model endpoints or agents."""

import json
import uuid

from google.adk.agents import LlmAgent
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.events import Event
from google.adk.models.google_llm import Gemini
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from ..config import settings
from ..prompts.stylist import STYLIST
from ..services import ai, conversation_context
from ..store import store
from .tools import StylistTools


async def run(principal, request, conversation, emit):
    cfg = settings()
    bound = StylistTools(principal, request, conversation.intent, emit, conversation)
    # One isolated ADK execution per turn. Firestore conversation/intent is the
    # durable source of history; no singleton in-memory state shared across users.
    sessions = InMemorySessionService()
    session = await sessions.create_session(
        app_name="flairify", user_id=principal.uid, session_id=uuid.uuid4().hex
    )
    for message in conversation.messages[-12:]:
        await sessions.append_event(
            session=session,
            event=Event(
                author="user" if message.role == "user" else "flairify_stylist",
                invocation_id="history-" + message.id,
                content=types.Content(
                    role="user" if message.role == "user" else "model",
                    parts=[types.Part.from_text(text=message.content[:3000])],
                ),
            ),
        )
    provider = ai.client(gemini=True, timeout=40000)
    agent = LlmAgent(
        name="flairify_stylist",
        model=Gemini(model=cfg.gemini_model, client=provider),
        instruction=STYLIST,
        tools=[
            bound.discuss_current_looks,
            bound.get_confirmed_wardrobe,
            bound.find_outfit_candidates,
            bound.get_product_details,
            bound.check_variant_availability,
        ],
        generate_content_config=types.GenerateContentConfig(
            temperature=1,
            thinking_config=ai.thinking(),
            max_output_tokens=2048,
        ),
    )
    runner = Runner(app_name="flairify", agent=agent, session_service=sessions)
    text = ""
    # Model input is data, never concatenated into system/tool instructions.
    context = json.dumps(
        {
            "shopping_preferences": {
                k: v
                for k, v in (store().get("profiles", principal.uid, "me") or {}).items()
                if k
                in (
                    "department",
                    "clothing_size",
                    "shoe_size",
                    "preferred_store_id",
                    "budget",
                    "fit",
                    "styles",
                    "colours",
                    "include_wardrobe",
                )
            },
            "wardrobe_override": request.include_wardrobe,
            "conversation": conversation_context.context(conversation, request),
            "message": request.message,
        },
        ensure_ascii=False,
    )
    try:
        async for event in runner.run_async(
            user_id=principal.uid,
            session_id=session.id,
            new_message=types.Content(role="user", parts=[types.Part.from_text(text=context)]),
            run_config=RunConfig(streaming_mode=StreamingMode.SSE, max_llm_calls=5),
        ):
            if not bound.result or not event.content or event.content.role != "model":
                continue
            chunk = "".join(p.text for p in event.content.parts or [] if p.text and not p.thought)
            if event.partial and chunk:
                text += chunk
                await emit("text", {"delta": chunk})
            elif event.is_final_response() and chunk and not text:
                text = chunk
                await emit("text", {"delta": chunk})
        if bound.result is None:
            # Never trust unsupported free-form claims when the model skipped retrieval.
            if conversation_context.DISCUSS.search(request.message):
                await bound.discuss_current_looks()
            else:
                await bound.find_outfit_candidates(
                    request.message, conversation.intent.get("occasion", "Everyday")
                )
        if not text:
            text = bound.result["text"]
            await emit("text", {"delta": text})
        return {**bound.result, "text": text, "method": "Google ADK / Gemini + validated outfits"}
    finally:
        await runner.close()
        await provider.aio.aclose()
        provider.close()
