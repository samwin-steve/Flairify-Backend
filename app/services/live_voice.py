"""Short-lived voice tickets, exclusive chat leases and bounded native-audio transport."""

import asyncio
import hashlib
import json
import logging
import secrets
import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from ..auth import Principal, principal, quota, require_record
from ..config import settings
from ..models import ChatRequest, Conversation
from ..store import store
from ..utils.errors import chat_failure
from . import conversation_context
from .chat import release

router = APIRouter()


class VoiceRequest(BaseModel):
    conversation_id: str | None = Field(default=None, max_length=100)
    reference_outfit_id: str | None = Field(default=None, max_length=100)
    include_wardrobe: bool | None = None
    store_id: str | None = Field(default=None, max_length=100)


class CancelVoiceRequest(BaseModel):
    ticket: str = Field(min_length=20, max_length=100)


def create_ticket(p, request):
    cfg = settings()
    if p.demo:
        raise HTTPException(403, "Sign in to talk with your stylist. Voice uses Google AI.")
    if not cfg.voice_ready:
        raise HTTPException(503, "Voice is unavailable right now. You can still type to your stylist.")
    profile = store().get("profiles", p.uid, "me") or {}
    if not profile.get("onboarding_complete"):
        raise HTTPException(409, "Save your shopping preferences before starting voice")
    conversation = (
        Conversation.model_validate(require_record("conversations", p.uid, request.conversation_id))
        if request.conversation_id
        else Conversation(title="A chat with your stylist")
    )
    if len(conversation.messages) >= 90 or len(conversation.model_dump_json().encode()) > 700_000:
        raise HTTPException(409, "Start a new conversation to continue")
    if request.reference_outfit_id:
        conversation_context.focus(
            conversation, ChatRequest(message="Continue", reference_outfit_id=request.reference_outfit_id)
        )
    ticket = secrets.token_urlsafe(32)
    key = hashlib.sha256(ticket.encode()).hexdigest()

    def acquire(old):
        if old and old.get("until", 0) > time.time():
            raise HTTPException(409, "Finish your current reply or voice conversation first")
        return {"key": key, "until": time.time() + 45}

    store().mutate("chat_locks", p.uid, "active", acquire)
    try:
        quota(p.uid, "voice-session", cfg.max_daily_voice_sessions, consume=False)
        quota("live-ai", "voice-session", cfg.max_global_daily_voice_sessions, consume=False)
        store().put(
            "voice_tickets",
            "system",
            key,
            {
                "uid": p.uid,
                "expires": time.time() + 45,
                "used": False,
                "request": request.model_dump(),
                "conversation_id": conversation.id,
            },
        )
        # Establish the canonical ID before the model connects, including brand-new chats.
        if not request.conversation_id:
            store().put("conversations", p.uid, conversation.id, conversation.model_dump(mode="json"))
        return {
            "ticket": ticket,
            "conversation_id": conversation.id,
            "expires_in": 45,
            "max_seconds": cfg.max_live_seconds,
        }
    except Exception:
        release(p.uid, key)
        store().delete("voice_tickets", "system", key)
        raise


def consume_ticket(ticket):
    if not isinstance(ticket, str) or len(ticket) > 100:
        raise HTTPException(401, "Start voice again to reconnect")
    key = hashlib.sha256(ticket.encode()).hexdigest()

    def consume(old):
        if not old or old["expires"] < time.time() or old["used"]:
            raise HTTPException(401, "Your voice connection expired. Start voice again.")
        return {**old, "used": True}

    record = store().mutate("voice_tickets", "system", key, consume)
    uid = record["uid"]

    def extend(old):
        if not old or old.get("key") != key or old.get("until", 0) < time.time():
            raise HTTPException(409, "Your voice connection expired. Start voice again.")
        return {"key": key, "until": time.time() + settings().max_live_seconds + 30}

    try:
        store().mutate("chat_locks", uid, "active", extend)
        quota(uid, "voice-session", settings().max_daily_voice_sessions)
        quota("live-ai", "voice-session", settings().max_global_daily_voice_sessions)
    except Exception:
        release(uid, key)
        store().delete("voice_tickets", "system", key)
        raise
    return key, record


@router.post("/api/voice/sessions")
def start_voice(data: VoiceRequest, request: Request, p: Annotated[Principal, Depends(principal)]):
    result = create_ticket(p, data)
    base = settings().live_api_url or str(request.base_url).rstrip("/")
    result["url"] = base.replace("https://", "wss://").replace("http://", "ws://") + "/api/voice/ws"
    return result


@router.post("/api/voice/sessions/cancel")
def cancel_voice(data: CancelVoiceRequest, p: Annotated[Principal, Depends(principal)]):
    key = hashlib.sha256(data.ticket.encode()).hexdigest()
    record = store().get("voice_tickets", "system", key)
    if record and record["uid"] == p.uid and not record["used"]:
        release(p.uid, key)
        store().delete("voice_tickets", "system", key)
    return {"cancelled": True}


@router.websocket("/api/voice/ws")
async def voice_socket(ws: WebSocket):
    # CORS middleware does not protect WebSocket upgrades.
    if ws.headers.get("origin") not in {s.strip() for s in settings().cors_origins.split(",")}:
        await ws.close(code=1008)
        return
    await ws.accept()
    key = record = state = None
    sender_lock = asyncio.Lock()

    async def emit(kind, data):
        async with sender_lock:
            await ws.send_json({"type": kind, **data})

    async def audio(data):
        async with sender_lock:
            await ws.send_bytes(data)

    try:
        raw = await asyncio.wait_for(ws.receive_text(), 10)
        if len(raw) > 512:
            raise HTTPException(400, "Invalid voice connection")
        hello = json.loads(raw)
        key, record = await asyncio.to_thread(consume_ticket, hello.get("ticket"))
        from ..agents.live_stylist import LiveStylist

        state = await LiveStylist.create(record, emit, audio)
        received = 0
        started = time.monotonic()

        async def receive():
            nonlocal received
            while True:
                message = await ws.receive()
                if message["type"] == "websocket.disconnect":
                    return
                raw_audio = message.get("bytes")
                if raw_audio is not None:
                    # 16kHz mono PCM16; reject oversized, odd or faster-than-live streams.
                    received += len(raw_audio)
                    allowance = (time.monotonic() - started + 5) * 32000 * 1.15
                    if not raw_audio or len(raw_audio) > 16384 or len(raw_audio) % 2 or received > allowance:
                        raise HTTPException(413, "Voice audio exceeded its streaming limit")
                    state.audio(raw_audio)
                elif message.get("text"):
                    if len(message["text"]) > 4096:
                        raise HTTPException(413, "Voice message is too large")
                    control = json.loads(message["text"])
                    if control.get("type") == "end":
                        return
                    if control.get("type") == "mute":
                        state.mute()
                    elif control.get("type") == "text":
                        await state.text(control.get("text", ""))
                    elif control.get("type") == "ping":
                        await emit("pong", {})

        async with asyncio.timeout(settings().max_live_seconds):
            tasks = [asyncio.create_task(state.run()), asyncio.create_task(receive())]
            try:
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    task.result()
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
    except TimeoutError:
        await emit(
            "ended", {"message": "This voice session has ended. Your chat is saved; tap Talk to continue."}
        )
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001 - only a safe customer message leaves the transport
        logging.getLogger(__name__).warning("Voice session ended (%s)", type(exc).__name__)
        try:
            await emit("error", {"message": chat_failure(exc)})
        except (RuntimeError, WebSocketDisconnect):
            pass
    finally:
        try:
            if state:
                try:
                    await state.close()
                except Exception as exc:  # noqa: BLE001 - cleanup must still release the chat lease
                    logging.getLogger(__name__).warning("Voice cleanup failed (%s)", type(exc).__name__)
        finally:
            try:
                if record:
                    try:
                        await asyncio.to_thread(release, record["uid"], key)
                    finally:
                        await asyncio.to_thread(store().delete, "voice_tickets", "system", key)
            finally:
                try:
                    await ws.close()
                except (RuntimeError, WebSocketDisconnect):
                    pass
