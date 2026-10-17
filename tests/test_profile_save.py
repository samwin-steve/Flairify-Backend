import pytest

from app.services import graph, recommendations
from app.store import store


def test_save_and_complete_returns_persisted_profile_in_one_write(client, session, monkeypatch):
    identity, headers = session
    writes = []
    original = store().put

    def record_put(kind, owner, key, data):
        if kind == "profiles":
            writes.append(data)
        return original(kind, owner, key, data)

    def unexpected(*args, **kwargs):
        raise AssertionError("Initial preferences must not load the wardrobe or clear an outfit graph")

    monkeypatch.setattr(store(), "put", record_put)
    monkeypatch.setattr(graph, "clear", unexpected)
    monkeypatch.setattr(recommendations, "get_confirmed_wardrobe", unexpected)
    response = client.put(
        "/api/profile?complete_onboarding=true",
        headers=headers,
        json={
            "name": "Sanch",
            "clothing_size": "XL",
            "shoe_size": "40",
            "styles": ["Classic"],
            "colours": ["Pink"],
            "keep_background": True,
            "consent": {"remember_preferences": False, "ai_photo_processing": True},
        },
    )
    assert response.status_code == 200
    saved = response.json()
    assert saved["onboarding_complete"] is True
    assert saved["clothing_size"] == "XL" and saved["shoe_size"] == "40"
    assert saved["keep_background"] is True and saved["consent"]["ai_photo_processing"] is True
    assert saved["styles"] == [] and saved["colours"] == []
    assert writes == [saved]
    assert store().get("profiles", identity["user_id"], "me") == saved


@pytest.mark.parametrize(
    "sizes",
    [
        {},
        {"clothing_size": "M"},
        {"shoe_size": "39"},
        {"clothing_size": " ", "shoe_size": "39"},
        {"clothing_size": "M", "shoe_size": " "},
    ],
)
def test_invalid_completion_leaves_saved_profile_unchanged(client, session, sizes):
    identity, headers = session
    before = store().get("profiles", identity["user_id"], "me")
    response = client.put("/api/profile?complete_onboarding=true", headers=headers, json=sizes)
    assert response.status_code == 409
    assert store().get("profiles", identity["user_id"], "me") == before


def test_invalid_store_does_not_complete_setup(client, session):
    identity, headers = session
    before = store().get("profiles", identity["user_id"], "me")
    response = client.put(
        "/api/profile?complete_onboarding=true",
        headers=headers,
        json={"clothing_size": "M", "shoe_size": "39", "preferred_store_id": "unavailable"},
    )
    assert response.status_code == 422
    assert store().get("profiles", identity["user_id"], "me") == before


def test_legacy_save_and_completion_remain_supported(client, session):
    _, headers = session
    response = client.put(
        "/api/profile",
        headers=headers,
        json={"clothing_size": "M", "shoe_size": "39", "onboarding_complete": True},
    )
    assert response.status_code == 200
    assert response.json()["onboarding_complete"] is False
    assert client.post("/api/onboarding/complete", headers=headers).json()["ready"] is True


def test_existing_profile_still_clears_graph_when_memory_consent_changes(client, onboarded):
    identity, headers = onboarded
    owner = identity["user_id"]
    graph.node(owner, "style:Classic", "Style", "Classic")
    graph.edge(owner, owner, "style:Classic", "PREFERS_STYLE")
    response = client.put(
        "/api/profile",
        headers=headers,
        json={"clothing_size": "XL", "shoe_size": "40", "consent": {"remember_preferences": False}},
    )
    assert response.status_code == 200 and response.json()["onboarding_complete"] is True
    assert store().list("nodes", owner) == [] and store().list("relationships", owner) == []
