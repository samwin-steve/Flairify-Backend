import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.services import jobs
from app.store import store


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("APP_MODE", "demo")
    monkeypatch.setenv("STORE_BACKEND", "sqlite")
    monkeypatch.setenv("ENABLE_PAID_AI", "false")
    monkeypatch.setenv("ENABLE_MODEL_ARMOR", "false")
    monkeypatch.setenv("DEMO_ADMIN_KEY", "test-admin-key")
    monkeypatch.setenv("MEDIA_BUCKET", "")
    monkeypatch.setenv("WORKER_URL", "")
    settings.cache_clear()
    store.cache_clear()
    monkeypatch.setattr(jobs, "enqueue", lambda owner, key, delay=0: jobs.process(owner, key))
    with TestClient(app) as c:
        yield c
    store().db.close()
    store.cache_clear()
    settings.cache_clear()


@pytest.fixture
def session(client):
    data = client.post("/api/auth/demo").json()
    return data, {"Authorization": "Bearer " + data["token"]}


@pytest.fixture
def onboarded(client, session):
    data, headers = session
    profile = client.get("/api/profile", headers=headers).json()
    profile.pop("admin")
    profile.pop("demo")
    profile.pop("seller")
    profile.update(
        name="Asha",
        include_wardrobe=True,
        clothing_size="M",
        shoe_size="39",
        consent={"remember_preferences": True, "ai_photo_processing": False},
    )
    assert client.put("/api/profile", headers=headers, json=profile).status_code == 200
    items = client.post("/api/wardrobe/sample", headers=headers).json()["items"]
    for item in items:
        item["confirmed"] = True
        assert client.put("/api/wardrobe/" + item["id"], headers=headers, json=item).status_code == 200
    assert client.post("/api/onboarding/complete", headers=headers).status_code == 200
    return data, headers
