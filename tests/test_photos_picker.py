from app.services import photos
from app.store import store
import pytest
from fastapi import HTTPException


def test_picker_separate_authorization_and_ownership(client, session, monkeypatch):
    data, h = session
    calls = []

    def mock(method, path, token, **kwargs):
        calls.append((method, path, token))
        return {
            "id": "pick-1",
            "pickerUri": "https://photos.google.com/picker/test",
            "mediaItemsSet": False,
            "pollingConfig": {"pollInterval": "2s", "timeoutIn": "60s"},
        }

    monkeypatch.setattr(photos, "call", mock)
    r = client.post("/api/photos-picker", headers={**h, "X-Photos-Token": "separate-oauth-token"})
    assert r.json()["pollingConfig"]["pollInterval"] == "2s"
    assert calls[0][2] == "separate-oauth-token"
    other = client.post("/api/auth/demo").json()
    assert (
        client.get(
            "/api/photos-picker/pick-1",
            headers={"Authorization": "Bearer " + other["token"], "X-Photos-Token": "token"},
        ).status_code
        == 404
    )
    assert (
        client.delete("/api/photos-picker/pick-1", headers={**h, "X-Photos-Token": "token"}).status_code
        == 200
    )
    assert not store().get("picker", data["user_id"], "pick-1")


def test_picker_pagination_and_cleanup(client, session, monkeypatch):
    data, h = session
    store().put("picker", data["user_id"], "s", {"id": "s"})
    visited = []

    def mock(method, path, token, **kw):
        visited.append((method, path, kw))
        if method == "DELETE":
            return {}
        if path == "/sessions/s":
            return {"mediaItemsSet": True}
        if kw["params"].get("pageToken") == "p2":
            return {"mediaItems": []}
        return {"mediaItems": [], "nextPageToken": "p2"}

    monkeypatch.setattr(photos, "call", mock)
    result = photos.import_selected(data["user_id"], "s", "oauth-token")
    assert result["photo_ids"] == []
    assert any(c[2].get("params", {}).get("pageToken") == "p2" for c in visited)
    assert visited[-1][0] == "DELETE"


def test_picker_rejects_non_google_url(client, session, monkeypatch):
    data, _ = session
    store().put("picker", data["user_id"], "s", {"id": "s"})

    def mock(method, path, token, **kw):
        return (
            {"mediaItemsSet": True}
            if path.startswith("/sessions")
            else {
                "mediaItems": [
                    {"id": "bad", "type": "PHOTO", "mediaFile": {"baseUrl": "http://127.0.0.1/private"}}
                ]
            }
        )

    monkeypatch.setattr(photos, "call", mock)
    with pytest.raises(HTTPException, match="Unexpected"):
        photos.import_selected(data["user_id"], "s", "token")
