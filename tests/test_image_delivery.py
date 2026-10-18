import io
from pathlib import Path
from unittest.mock import Mock

from PIL import Image

from app.config import settings
from app.services import image_delivery, inventory, media
from app.store import store


def photo():
    image = Image.effect_noise((1600, 2000), 55).convert("RGB")
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=95)
    return buffer.getvalue()


def test_small_webp_original_preserved_and_persistent_reuse(client, session, monkeypatch):
    account, headers = session
    original = photo()
    key = media.save(account["user_id"], original)
    url = "/api/media/" + key
    assert client.get(url, headers=headers).content == original
    result = client.get(url + "?width=384", headers=headers)
    assert result.status_code == 200 and result.headers["content-type"] == "image/webp"
    image = Image.open(io.BytesIO(result.content))
    assert max(image.size) == 384 and len(result.content) < len(original) / 4
    assert result.headers["cache-control"] == "private, no-store"
    record = store().get("media", account["user_id"], key)
    path = Path(settings().data_dir) / "media" / image_delivery.variant_key(record, 384)
    assert path.read_bytes() == result.content
    # Reuse the persisted derivative after losing a Cloud Run instance's RAM cache.
    monkeypatch.setattr(image_delivery, "cached", lambda key: None)
    monkeypatch.setattr(media, "read", Mock(side_effect=AssertionError("Original redownloaded")))
    assert client.get(url + "?width=384", headers=headers).content == result.content


def test_authorization_deletion_and_revalidation_precede_cached_bytes(client, session):
    account, headers = session
    owner = account["user_id"]
    key = media.save(owner, photo())
    url = "/api/media/" + key + "?width=384"
    result = client.get(url, headers=headers)
    etag = result.headers["etag"]
    assert client.get(url, headers={**headers, "If-None-Match": etag}).status_code == 304
    other = client.post("/api/auth/demo").json()
    assert (
        client.get(
            url, headers={"Authorization": "Bearer " + other["token"], "If-None-Match": etag}
        ).status_code
        == 404
    )
    assert client.get(url).status_code == 401
    record = store().get("media", owner, key)
    media.delete(owner, key)
    assert not (Path(settings().data_dir) / "media" / image_delivery.variant_key(record, 384)).exists()
    assert image_delivery.cached(image_delivery.cache_key(owner, record, 384)) is None
    assert client.get(url, headers={**headers, "If-None-Match": etag}).status_code == 404


def test_catalogue_private_browser_cache_and_archive_recheck(client, session, monkeypatch):
    account, headers = session
    owner = account["user_id"]
    key = media.save(owner, photo())
    product = next(iter(inventory.fixture_products().values())).copy()
    product.update(image="media:" + key, active=True)
    store().put("products", owner, product["id"], product)
    url = "/api/catalog/media/" + key + "?width=384"
    result = client.get(url, headers=headers)
    assert result.status_code == 200
    assert result.headers["cache-control"] == "private, max-age=300, must-revalidate"
    assert "Authorization" in [v.strip() for v in result.headers["vary"].split(",")]
    conditional = {**headers, "If-None-Match": result.headers["etag"]}
    monkeypatch.setattr(image_delivery, "thumbnail", Mock(side_effect=AssertionError("304 downloaded bytes")))
    assert client.get(url, headers=conditional).status_code == 304
    product["active"] = False
    store().put("products", owner, product["id"], product)
    assert client.get(url, headers=conditional).status_code == 404


def test_variants_are_bounded_distinct_and_original_is_not_transformed(client, session):
    account, headers = session
    key = media.save(account["user_id"], photo())
    url = "/api/media/" + key
    thumb = client.get(url + "?width=384", headers=headers)
    detail = client.get(url + "?width=768", headers=headers)
    assert thumb.headers["etag"] != detail.headers["etag"]
    assert max(Image.open(io.BytesIO(detail.content)).size) == 768
    for width in (0, -1, 99999):
        assert client.get(url + f"?width={width}", headers=headers).status_code == 422
    assert client.get(url, headers=headers).headers["content-type"] == "image/jpeg"
    video = media.save(account["user_id"], b"video", "video/mp4")
    assert client.get("/api/media/" + video + "?width=384", headers=headers).status_code == 422


def test_memory_cache_is_bounded_and_owner_scoped(client, monkeypatch):
    monkeypatch.setattr(image_delivery, "_cache", image_delivery.OrderedDict())
    monkeypatch.setattr(image_delivery, "_cache_bytes", 0)
    monkeypatch.setattr(image_delivery, "MAX_CACHE_BYTES", 8)
    monkeypatch.setattr(image_delivery, "MAX_CACHE_ENTRIES", 2)
    image_delivery.remember(("a",), b"123456")
    image_delivery.remember(("b",), b"123456")
    assert image_delivery.cached(("a",)) is None
    assert image_delivery.cached(("b",)) == b"123456"
    assert image_delivery._cache_bytes <= 8
    record = {"id": "same", "sha256": "same"}
    assert image_delivery.cache_key("alice", record, 384) != image_delivery.cache_key("bob", record, 384)


def test_deleting_during_transform_cannot_leave_a_derivative(client, session, monkeypatch):
    account, _ = session
    owner = account["user_id"]
    key = media.save(owner, photo())
    record = store().get("media", owner, key)
    encode = image_delivery.encode

    def deleting(raw, width):
        result = encode(raw, width)
        media.delete(owner, key)
        return result

    monkeypatch.setattr(image_delivery, "encode", deleting)
    import pytest
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as error:
        image_delivery.thumbnail(owner, record, 384)
    assert error.value.status_code == 404
    assert not (Path(settings().data_dir) / "media" / image_delivery.variant_key(record, 384)).exists()
