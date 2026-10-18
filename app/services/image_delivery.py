"""Private, bounded WebP derivatives. Authorization always happens before cache access."""

import hashlib
import io
import threading
import time
from collections import OrderedDict
from pathlib import Path

from fastapi import HTTPException, Response
from google.api_core.exceptions import NotFound, PreconditionFailed
from PIL import Image, ImageOps, UnidentifiedImageError

from ..config import settings
from ..store import store
from . import media

WIDTHS = (384, 768)
VERSION = "webp-v1"
MAX_CACHE_BYTES = 32 * 1024 * 1024
MAX_CACHE_ENTRIES = 256
CACHE_SECONDS = 300
_cache = OrderedDict()
_cache_bytes = 0
_lock = threading.RLock()
_generation_locks = [threading.Lock() for _ in range(16)]


def variant_key(record, width):
    return record["key"].rsplit(".", 1)[0] + f".{VERSION}-{width}.webp"


def cache_key(owner, record, width):
    cfg = settings()
    return (
        cfg.media_bucket or str(Path(cfg.data_dir).resolve()),
        owner,
        record["id"],
        record["sha256"],
        width,
    )


def cached(key):
    global _cache_bytes
    with _lock:
        entry = _cache.get(key)
        if entry and entry[0] > time.monotonic():
            _cache.move_to_end(key)
            return entry[1]
        if entry:
            _cache_bytes -= len(_cache.pop(key)[1])
    return None


def remember(key, raw):
    global _cache_bytes
    with _lock:
        old = _cache.pop(key, None)
        if old:
            _cache_bytes -= len(old[1])
        if len(raw) > MAX_CACHE_BYTES:
            return
        _cache[key] = (time.monotonic() + CACHE_SECONDS, raw)
        _cache_bytes += len(raw)
        while _cache and (_cache_bytes > MAX_CACHE_BYTES or len(_cache) > MAX_CACHE_ENTRIES):
            _, removed = _cache.popitem(last=False)
            _cache_bytes -= len(removed[1])


def encode(raw, width):
    try:
        with Image.open(io.BytesIO(raw)) as source:
            image = ImageOps.exif_transpose(source)
            image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
            image.thumbnail((width, width))
            output = io.BytesIO()
            image.save(output, "WEBP", quality=78, method=4)
            return output.getvalue()
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise HTTPException(422, "This image could not be resized") from exc


def present(owner, key):
    row = store().get("media", owner, key)
    return row and not row.get("deleting")


def thumbnail(owner, record, width):
    if width not in WIDTHS or not record["mime"].startswith("image/"):
        raise HTTPException(422, "Choose a supported image width")
    key = cache_key(owner, record, width)
    hit = cached(key)
    if hit is not None:
        return hit
    # Bound simultaneous transforms and avoid repeated work for the same image.
    with _generation_locks[hash(key) % len(_generation_locks)]:
        hit = cached(key)
        if hit is not None:
            return hit
        cfg = settings()
        object_key = variant_key(record, width)
        blob = None
        if cfg.media_bucket:
            blob = media.storage_client(cfg.google_cloud_project).bucket(cfg.media_bucket).blob(object_key)
            try:
                raw = blob.download_as_bytes()
            except NotFound:
                raw = None
        else:
            path = Path(cfg.data_dir) / "media" / object_key
            raw = path.read_bytes() if path.exists() else None
        if raw is None:
            source, _ = media.read(owner, record["id"], record=record)
            raw = encode(source, width)
            # A deleted source must never be resurrected by a transform finishing late.
            if not present(owner, record["id"]):
                raise HTTPException(404, "Photo or preview not found")
            if blob:
                try:
                    blob.upload_from_string(raw, content_type="image/webp", if_generation_match=0)
                except PreconditionFailed:
                    pass  # Another Cloud Run instance already wrote this immutable derivative.
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
            if not present(owner, record["id"]):
                delete_variants(owner, record)
                raise HTTPException(404, "Photo or preview not found")
        remember(key, raw)
        return raw


def response(owner, key, width=None, if_none_match=None, *, catalog=False, record=None):
    record = record or store().get("media", owner, key)
    if not record or record.get("deleting"):
        raise HTTPException(404, "Photo or preview not found")
    if width is not None and width not in WIDTHS:
        raise HTTPException(422, "Supported image widths are 384 and 768")
    etag = '"' + hashlib.sha256(f"{record['sha256']}:{width}:{VERSION}".encode()).hexdigest() + '"'
    headers = {
        "Cache-Control": "private, max-age=300, must-revalidate" if catalog else "private, no-store",
        "Vary": "Authorization",
        "ETag": etag,
        "X-Content-Type-Options": "nosniff",
    }
    if if_none_match and etag in [value.strip().removeprefix("W/") for value in if_none_match.split(",")]:
        return Response(status_code=304, headers=headers)
    raw, mime = (
        (thumbnail(owner, record, width), "image/webp") if width else media.read(owner, key, record=record)
    )
    return Response(raw, media_type=mime, headers=headers)


def delete_variants(owner, record):
    global _cache_bytes
    cfg = settings()
    for width in WIDTHS:
        key = cache_key(owner, record, width)
        with _lock:
            old = _cache.pop(key, None)
            if old:
                _cache_bytes -= len(old[1])
        object_key = variant_key(record, width)
        if cfg.media_bucket:
            try:
                media.storage_client(cfg.google_cloud_project).bucket(cfg.media_bucket).blob(
                    object_key
                ).delete()
            except NotFound:
                pass
        else:
            (Path(cfg.data_dir) / "media" / object_key).unlink(missing_ok=True)


def warm_product(owner, product):
    """Prepare new listings during indexing; an image failure never hides valid inventory."""
    import logging

    record = store().get("media", owner, product["image"][6:])
    if record and not record.get("deleting"):
        try:
            thumbnail(owner, record, 384)
        except Exception as exc:  # noqa: BLE001 - optional derivative, original remains available
            logging.getLogger(__name__).warning("Thumbnail preparation failed: %s", type(exc).__name__)
