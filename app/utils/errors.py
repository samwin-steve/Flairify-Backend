"""Safe customer messages; provider payloads can contain private input."""

from fastapi import HTTPException


def chat_failure(exc: Exception) -> str:
    if isinstance(exc, HTTPException):
        return str(exc.detail)
    current = exc
    seen = set()
    for _ in range(8):
        if current is None or id(current) in seen:
            break
        seen.add(id(current))
        # ADK wraps Google SDK errors; inspect their typed cause, never echo it.
        if getattr(current, "code", None) == 429:
            return "Google's AI service is busy right now. Your message is kept here; please try again shortly."
        if isinstance(current, TimeoutError):
            return "The stylist took too long to respond. Your message is kept here; please try again."
        current = current.__cause__ or current.__context__
    return "The stylist was interrupted. Retry your message or reopen the conversation to check for a completed answer."
