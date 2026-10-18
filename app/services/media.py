import hashlib
import io
from functools import lru_cache
from pathlib import Path
from PIL import Image, ImageOps, UnidentifiedImageError
from fastapi import HTTPException
from ..config import settings
from ..models import uid, now
from ..store import store

Image.MAX_IMAGE_PIXELS = 30_000_000


@lru_cache(maxsize=4)
def storage_client(project):
    # Reuse HTTP connections across image requests on a warm Cloud Run instance.
    from google.cloud import storage

    return storage.Client(project=project)


def normalize(raw: bytes):
    if len(raw) > settings().max_upload_mb * 1024 * 1024:
        raise HTTPException(413, "Each photo must be 10 MB or smaller")
    try:
        with Image.open(io.BytesIO(raw)) as source:
            if source.format not in ("JPEG", "PNG", "WEBP"):
                raise ValueError("format")
            if source.width * source.height > 30_000_000:
                raise ValueError("pixel limit")
            source.load()
            captured = source.getexif().get(36867)
            img = ImageOps.exif_transpose(source).convert("RGB")
            img.thumbnail((1600, 1600))
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=88)
            return buf.getvalue(), captured
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        raise HTTPException(422, "Use a valid JPEG, PNG or WebP photo with at most 30 megapixels")


def save(owner, raw, mime="image/jpeg", source_id=None):
    media_id = uid()
    ext = {"video/mp4": "mp4", "image/png": "png", "image/webp": "webp"}.get(mime, "jpg")
    key = f"{owner}/{media_id}.{ext}"
    cfg = settings()
    if cfg.media_bucket:
        storage_client(cfg.google_cloud_project).bucket(cfg.media_bucket).blob(key).upload_from_string(
            raw, content_type=mime
        )
    else:
        path = Path(cfg.data_dir) / "media" / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    record = {
        "id": media_id,
        "key": key,
        "mime": mime,
        "size": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "source_id": source_id,
        "created_at": now(),
    }
    store().put("media", owner, media_id, record)
    return media_id


def read(owner, media_id, *, record=None):
    record = record or store().get("media", owner, media_id)
    if not record or record.get("deleting"):
        raise HTTPException(404, "Photo or preview not found")
    cfg = settings()
    if cfg.media_bucket:
        data = (
            storage_client(cfg.google_cloud_project)
            .bucket(cfg.media_bucket)
            .blob(record["key"])
            .download_as_bytes()
        )
    else:
        data = (Path(cfg.data_dir) / "media" / record["key"]).read_bytes()
    return data, record["mime"]


def delete(owner, media_id):
    record = store().get("media", owner, media_id)
    if not record:
        return
    # A concurrent thumbnail transform can see this marker before writing a derivative.
    store().put("media", owner, media_id, {**record, "deleting": True})
    from .image_delivery import delete_variants

    delete_variants(owner, record)
    cfg = settings()
    if cfg.media_bucket:
        blob = storage_client(cfg.google_cloud_project).bucket(cfg.media_bucket).blob(record["key"])
        blob.delete() if blob.exists() else None
    else:
        (Path(cfg.data_dir) / "media" / record["key"]).unlink(missing_ok=True)
    store().delete("media", owner, media_id)


def crop(raw, box, max_size=600):
    img = Image.open(io.BytesIO(raw))
    x, y, w, h = box["x"], box["y"], box["width"], box["height"]
    cropped = img.crop(
        (
            int(x * img.width),
            int(y * img.height),
            max(int((x + w) * img.width), int(x * img.width) + 1),
            max(int((y + h) * img.height), int(y * img.height) + 1),
        )
    )
    cropped.thumbnail((max_size, max_size))
    out = io.BytesIO()
    cropped.save(out, "JPEG", quality=90)
    return out.getvalue()


def save_original(owner, raw):
    # Called only after normalize() validates byte size, decoder and pixel count.
    with Image.open(io.BytesIO(raw)) as source:
        mime = Image.MIME[source.format]
    return save(owner, raw, mime)
