import json

from app.services import recommendations
from app.store import store


def events(response):
    return [
        (block.splitlines()[0].split(": ", 1)[1], json.loads(block.splitlines()[1][6:]))
        for block in response.text.strip().split("\n\n")
        if block.startswith("event:")
    ]


def test_stream_persists_once_and_replays_same_request(client, onboarded):
    data, headers = onboarded
    payload = {"message": "Mumbai work under ₹5,000", "request_id": "stream-request-1"}
    response = client.post("/api/chat/stream", headers=headers, json=payload)
    assert response.status_code == 200 and "text/event-stream" in response.headers["content-type"]
    emitted = events(response)
    names = [name for name, _ in emitted]
    assert names[0] == "start" and names[-1] == "done"
    assert "outfits" in names and "text" in names
    result = emitted[-1][1]
    assert len(result["conversation"]["messages"]) == 2
    replay = events(client.post("/api/chat/stream", headers=headers, json=payload))
    assert replay == [("done", result)]
    assert len(store().list("conversations", data["user_id"])) == 1
    conflict = client.post("/api/chat/stream", headers=headers, json={**payload, "message": "different"})
    assert conflict.status_code == 409


def test_stream_error_is_not_saved_as_success_and_releases_lock(client, onboarded, monkeypatch):
    data, headers = onboarded
    original = recommendations.recommend
    monkeypatch.setattr(
        recommendations,
        "recommend",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("private provider error")),
    )
    payload = {"message": "work", "request_id": "stream-retry-1"}
    emitted = events(client.post("/api/chat/stream", headers=headers, json=payload))
    assert emitted[-1][0] == "error" and "private provider error" not in str(emitted)
    assert store().list("conversations", data["user_id"]) == []
    monkeypatch.setattr(recommendations, "recommend", original)
    assert events(client.post("/api/chat/stream", headers=headers, json=payload))[-1][0] == "done"


def test_stream_cannot_read_other_users_conversation(client, onboarded):
    _, headers = onboarded
    result = client.post("/api/chat", headers=headers, json={"message": "work"}).json()
    second = client.post("/api/auth/demo").json()
    profile = store().get("profiles", second["user_id"], "me")
    profile["onboarding_complete"] = True
    store().put("profiles", second["user_id"], "me", profile)
    response = client.post(
        "/api/chat/stream",
        headers={"Authorization": "Bearer " + second["token"]},
        json={"message": "read it", "conversation_id": result["conversation"]["id"]},
    )
    assert response.status_code == 404
