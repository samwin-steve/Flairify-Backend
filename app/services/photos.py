"""Google Photos Picker: separate, user-initiated OAuth, selected media only."""

from urllib.parse import urlparse
import httpx
from fastapi import HTTPException
from ..store import store
from ..models import PhotoSource
from . import media

BASE = "https://photospicker.googleapis.com/v1"


def call(method, path, token, **kwargs):
    if not token or len(token) > 4096:
        raise HTTPException(401, "Authorize Google Photos separately to select photos")
    response = httpx.request(
        method, BASE + path, headers={"Authorization": f"Bearer {token}"}, timeout=30, **kwargs
    )
    if response.status_code >= 400:
        raise HTTPException(
            401 if response.status_code == 401 else 502,
            "Google Photos could not complete this request. Reconnect Photos or upload directly.",
        )
    return response.json() if response.content else {}


def create(owner, token):
    result = call("POST", "/sessions", token, json={"pickingConfig": {"maxItemCount": "12"}})
    store().put("picker", owner, result["id"], {"id": result["id"], "created": True})
    return result


def check_owner(owner, key):
    if not store().get("picker", owner, key):
        raise HTTPException(404, "Picker session not found")


def poll(owner, key, token):
    check_owner(owner, key)
    return call("GET", "/sessions/" + key, token)


def delete(owner, key, token):
    check_owner(owner, key)
    call("DELETE", "/sessions/" + key, token)
    store().delete("picker", owner, key)


def import_selected(owner, key, token):
    session = poll(owner, key, token)
    if not session.get("mediaItemsSet"):
        raise HTTPException(409, "Finish choosing your photos first")
    photo_ids = []
    page = None
    while True:
        params = {"sessionId": key, "pageSize": 100}
        if page:
            params["pageToken"] = page
        result = call("GET", "/mediaItems", token, params=params)
        for item in result.get("mediaItems", []):
            if len(photo_ids) >= 12:
                break
            if item.get("type") != "PHOTO":
                continue
            existing = store().get("picked", owner, item["id"])
            if existing and store().get("photos", owner, existing["photo_id"]):
                photo_ids.append(existing["photo_id"])
                continue
            url = item["mediaFile"]["baseUrl"]
            parsed = urlparse(url)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or not (
                    parsed.hostname.endswith(".googleusercontent.com")
                    or parsed.hostname == "googleusercontent.com"
                )
                or parsed.port not in (None, 443)
            ):
                raise HTTPException(502, "Unexpected Google Photos image host")
            # Fresh base URLs are obtained on every import/retry, never stored as durable media.
            with httpx.stream(
                "GET",
                url + "=w1600-h1600",
                headers={"Authorization": f"Bearer {token}"},
                timeout=45,
                follow_redirects=False,
            ) as response:
                if response.status_code != 200:
                    raise HTTPException(
                        502, "A selected photo expired or is unavailable. Retry to refresh its URL."
                    )
                chunks = []
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > 10 * 1024 * 1024:
                        raise HTTPException(413, "A selected photo exceeds the upload limit")
                    chunks.append(chunk)
            downloaded = b"".join(chunks)
            raw, captured = media.normalize(downloaded)
            photo = PhotoSource(
                media_id=media.save(owner, raw),
                original_media_id=media.save_original(owner, downloaded),
                source="google_photos",
                captured_at=item.get("createTime") or captured,
            )
            store().put("photos", owner, photo.id, photo.model_dump())
            store().put("picked", owner, item["id"], {"photo_id": photo.id})
            photo_ids.append(photo.id)
        page = result.get("nextPageToken")
        if not page or len(photo_ids) >= 12:
            break
    delete(owner, key, token)
    return {"photo_ids": photo_ids, "next_step": "Review the selected person before starting extraction"}
