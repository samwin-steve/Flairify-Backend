from app.config import settings


def test_firebase_verification_and_anonymous_exclusion(client, monkeypatch):
    import firebase_admin
    from firebase_admin import auth

    monkeypatch.setenv("ALLOW_FIREBASE_IN_DEMO", "true")
    settings.cache_clear()
    monkeypatch.setattr(firebase_admin, "_apps", {"test": object()})
    seen = []

    def verify(token, check_revoked):
        seen.append(check_revoked)
        return {"uid": "signed-in-user", "firebase": {"sign_in_provider": "password"}}

    monkeypatch.setattr(auth, "verify_id_token", verify)
    headers = {"Authorization": "Bearer signed-in-test-token"}
    response = client.get("/api/profile", headers=headers)
    assert response.status_code == 200 and not response.json()["demo"]
    assert seen == [True]
    monkeypatch.setattr(
        auth,
        "verify_id_token",
        lambda *a, **k: {"uid": "anonymous-user", "firebase": {"sign_in_provider": "anonymous"}},
    )
    assert client.get("/api/profile", headers=headers).status_code == 401


def test_anonymous_demo_never_calls_live_analysis(client, session, monkeypatch):
    from tests.test_journey import image_bytes
    from app.services import ai

    _, headers = session
    monkeypatch.setenv("ENABLE_PAID_AI", "true")
    monkeypatch.setenv("GEMINI_MODEL", "configured-test-model")
    settings.cache_clear()

    def forbidden(*args, **kwargs):
        raise AssertionError("An anonymous demo must not call the paid model")

    monkeypatch.setattr(ai, "detect", forbidden)
    photo = client.post(
        "/api/photos", headers=headers, files={"file": ("photo.jpg", image_bytes(), "image/jpeg")}
    ).json()
    job = client.post("/api/wardrobe/import", headers=headers, json={"photo_ids": [photo["id"]]})
    assert job.status_code == 200
    item = client.get("/api/wardrobe", headers=headers).json()["items"][0]
    assert item["category"] == "unknown"
    assert client.get("/api/config", headers=headers).json()["analysis"] == "manual"
