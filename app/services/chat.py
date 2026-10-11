"""Durable conversation orchestration shared by JSON and SSE transports."""

import asyncio
import hashlib
import json
import logging
import secrets
import time

from fastapi import HTTPException

from ..auth import quota, require_record
from ..config import settings
from ..models import Conversation, Message, now
from ..store import store
from ..utils.errors import chat_failure
from ..utils.events import sse
from . import recommendations


def prepare(principal, request):
    owner = principal.uid
    profile = store().get("profiles", owner, "me") or {}
    if not profile.get("onboarding_complete"):
        raise HTTPException(409, "Complete your wardrobe review before your first chat")
    key = request.request_id or secrets.token_hex(16)
    digest = hashlib.sha256(
        json.dumps(request.model_dump(exclude={"request_id"}), sort_keys=True).encode()
    ).hexdigest()
    previous_turn = store().get("chat_turns", owner, key)
    if previous_turn and previous_turn["hash"] != digest:
        raise HTTPException(409, "This request ID was already used for a different message")
    if previous_turn and previous_turn.get("result"):
        result = previous_turn["result"]
        current = store().get("conversations", owner, previous_turn["conversation_id"])
        if current:
            result = {**result, "conversation": current}
        return {"cached": result}
    conversation_id = request.conversation_id or (previous_turn or {}).get("conversation_id")
    conversation = (
        Conversation.model_validate(require_record("conversations", owner, conversation_id))
        if conversation_id and store().get("conversations", owner, conversation_id)
        else Conversation(id=conversation_id, title=request.message[:60])
        if conversation_id and previous_turn
        else Conversation(title=request.message[:60])
    )
    if request.conversation_id and not store().get("conversations", owner, request.conversation_id):
        raise HTTPException(404, "Conversation not found")
    prior_reply = next((m for m in conversation.messages if m.id == key + "-assistant"), None)
    if prior_reply:
        return {
            "cached": {
                "text": prior_reply.content,
                "outfits": prior_reply.outfits,
                "intent": conversation.intent,
                "conversation": conversation.model_dump(mode="json"),
            }
        }
    if len(conversation.messages) >= 100 or len(conversation.model_dump_json().encode()) > 750_000:
        raise HTTPException(409, "Start a new conversation to continue")

    def acquire(old):
        if old and old.get("until", 0) > time.time():
            raise HTTPException(409, "Your previous message is still being answered. Please wait a moment.")
        return {"key": key, "until": time.time() + 150}

    store().mutate("chat_locks", owner, "active", acquire)
    try:
        quota(owner, "chat", 50)
        if not principal.demo and settings().ai_ready:
            quota("live-ai", "chat", 50)
        store().put(
            "chat_turns",
            owner,
            key,
            {"id": key, "hash": digest, "conversation_id": conversation.id, "status": "running"},
        )
        return {"conversation": conversation, "key": key, "hash": digest}
    except Exception:
        release(owner, key)
        raise


def release(owner, key):
    store().mutate(
        "chat_locks", owner, "active", lambda old: {"until": 0} if old and old.get("key") == key else old
    )


async def execute(principal, request, turn, emit):
    if "cached" in turn:
        await emit("done", turn["cached"])
        return turn["cached"]
    conversation, key = turn["conversation"], turn["key"]
    try:
        await emit("start", {"conversation_id": conversation.id, "request_id": key})
        await emit("status", {"message": "Checking your wardrobe and preferences…"})
        if settings().ai_ready and not principal.demo:
            from ..agents.stylist import run

            result = await run(principal, request, conversation, emit)
        else:
            result = await asyncio.to_thread(
                recommendations.recommend, principal, request, conversation.intent
            )
            await emit(
                "outfits",
                {
                    "outfits": result["outfits"],
                    "retrieval": result.get("retrieval"),
                    "method": "Rule-based demo",
                },
            )
            # The deterministic demo emits one honest block, not simulated model typing.
            await emit("text", {"delta": result["text"]})
        conversation.messages += [
            Message(id=key + "-user", role="user", content=request.message),
            Message(
                id=key + "-assistant", role="assistant", content=result["text"], outfits=result["outfits"]
            ),
        ]
        conversation.intent = result["intent"]
        conversation.updated_at = now()
        if len(conversation.model_dump_json().encode()) > 900_000:
            raise HTTPException(409, "This conversation is full. Start a new conversation to continue.")
        data = {**result, "conversation": conversation.model_dump(mode="json")}
        await asyncio.to_thread(
            store().put, "conversations", principal.uid, conversation.id, data["conversation"]
        )
        await asyncio.to_thread(
            store().put,
            "chat_turns",
            principal.uid,
            key,
            {
                "id": key,
                "hash": turn["hash"],
                "conversation_id": conversation.id,
                "status": "succeeded",
                "result": result,
            },
        )
        await emit("done", data)
        return data
    finally:
        await asyncio.to_thread(release, principal.uid, key)


async def stream(principal, request, turn):
    queue = asyncio.Queue(maxsize=40)

    async def emit(event, data):
        await queue.put((event, data))

    async def produce():
        try:
            async with asyncio.timeout(105):
                await execute(principal, request, turn, emit)
        except Exception as exc:  # noqa: BLE001 - SSE must emit an honest terminal error
            # Type only: raw provider exceptions may include user/model content.
            logging.getLogger(__name__).warning("Stylist stream failed (%s)", type(exc).__name__)
            await emit("error", {"message": chat_failure(exc)})
        finally:
            await queue.put(None)

    task = asyncio.create_task(produce())
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), 10)
            except TimeoutError:
                yield ": keepalive\n\n"
                continue
            if event is None:
                break
            yield sse(*event)
    finally:
        # A disconnected browser must not leave unbounded model calls running.
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
