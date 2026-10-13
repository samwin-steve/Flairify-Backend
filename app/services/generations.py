"""Shared, authorized job submission for buttons and explicit voice requests."""

import hashlib

from fastapi import HTTPException

from ..auth import quota, require_record
from ..config import settings
from ..store import store
from . import jobs, try_on


def submit(kind, data, p):
    if kind not in ("try_on", "video", "avatar"):
        raise HTTPException(404, "Unknown generation type")
    # Check idempotency before charging the quota.
    key = hashlib.sha256(f"{kind}:{data.request_key}".encode()).hexdigest()[:32]
    existing = store().get("jobs", p.uid, key)
    if existing:
        return jobs.public(existing)
    payload = {**data.model_dump(), "catalog_owner": p.catalog_owner}
    if kind == "try_on" and not p.demo:
        try:
            payload, _, _ = try_on.prepare(p.uid, payload)
        except (try_on.CapabilityUnavailable, ValueError) as exc:
            raise HTTPException(409, str(exc))
    quota(p.uid, "generation", settings().max_daily_generations)
    if kind == "video":
        source = require_record("jobs", p.uid, data.source_job_id)
        if (
            source["kind"] != "try_on"
            or source["status"] != "succeeded"
            or not source.get("result", {}).get("accepted")
        ):
            raise HTTPException(409, "Accept a successful try-on preview first")
    return jobs.create(p.uid, kind, payload, data.request_key)
