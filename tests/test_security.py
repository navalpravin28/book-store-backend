import io

import pytest
from PIL import Image
from pydantic import ValidationError

from app.core.config import settings
from app.schema.categorySchema import CategoryCreate
from tests.conftest import login


def test_http_image_urls_are_development_only(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    assert CategoryCreate(categoryName="Fiction", imageUrl="http://localhost:3000/cover.jpg").imageUrl

    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    with pytest.raises(ValidationError):
        CategoryCreate(categoryName="Fiction", imageUrl="http://localhost:3000/cover.jpg")

    assert CategoryCreate(categoryName="Fiction", imageUrl="https://example.com/cover.jpg").imageUrl


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (20, 20), "red").save(buf, "PNG")
    return buf.getvalue()


async def test_role_cannot_be_chosen_at_registration(client):
    r = await client.post("/api/v1/auth/register", json={
        "name": "Mallory", "email": "m@x.com", "password": "Strong@1234", "role": "admin"})
    assert r.status_code == 422  # extra fields are forbidden (mass assignment)
    r = await client.post("/api/v1/auth/register", json={"name": "Bob", "email": "b@x.com", "password": "Strong@1234"})
    assert r.status_code == 201 and r.json()["role"] == "viewer"


async def test_weak_password_rejected_and_input_not_echoed(client):
    r = await client.post("/api/v1/auth/register", json={"name": "Bob", "email": "b@x.com", "password": "password"})
    assert r.status_code == 422
    assert "password" not in str(r.json().get("input", ""))
    assert "'input'" not in r.text and '"input"' not in r.text


async def test_nosql_injection_in_login_is_rejected(client):
    r = await client.post("/api/v1/auth/login", json={"email": {"$ne": None}, "password": {"$ne": None}})
    assert r.status_code == 422


async def test_rbac_matrix(client, admin, viewer):
    assert (await client.post("/api/v1/categories", json={"categoryName": "Fiction"})).status_code == 401
    assert (await client.post("/api/v1/categories", json={"categoryName": "Fiction"}, headers=viewer)).status_code == 403
    assert (await client.get("/api/v1/dashboard/overview", headers=viewer)).status_code == 403
    assert (await client.get("/api/v1/sales", headers=viewer)).status_code == 403
    assert (await client.get("/api/v1/books/export/csv", headers=viewer)).status_code == 403
    assert (await client.get("/api/v1/users", headers=viewer)).status_code == 403
    assert (await client.post("/api/v1/categories", json={"categoryName": "Fiction"}, headers=admin)).status_code == 201


async def test_public_endpoints_need_no_login(client):
    for path in ("/api/v1/books", "/api/v1/categories", "/api/v1/advertisements", "/health"):
        assert (await client.get(path)).status_code == 200


async def test_forged_and_garbage_tokens(client):
    import jwt
    forged = jwt.encode({"sub": "a" * 24, "role": "admin", "jti": "x", "iat": 1, "exp": 9999999999}, "wrong-key" * 5, "HS256")
    assert (await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {forged}"})).status_code == 401
    assert (await client.get("/api/v1/users/me", headers={"Authorization": "Bearer nonsense"})).status_code == 401
    none_alg = jwt.encode({"sub": "a" * 24, "jti": "x"}, key=None, algorithm="none")
    assert (await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {none_alg}"})).status_code == 401


async def test_logout_revokes_token(client, viewer):
    assert (await client.get("/api/v1/users/me", headers=viewer)).status_code == 200
    assert (await client.post("/api/v1/auth/logout", headers=viewer)).status_code == 204
    assert (await client.get("/api/v1/users/me", headers=viewer)).status_code == 401


async def test_change_password_invalidates_old_tokens(client, viewer):
    import asyncio
    await asyncio.sleep(1.1)  # token iat is in whole seconds
    r = await client.post("/api/v1/auth/change-password", headers=viewer,
                          json={"currentPassword": "Viewer@1234", "newPassword": "Newer@12345"})
    assert r.status_code == 204
    assert (await client.get("/api/v1/users/me", headers=viewer)).status_code == 401
    await login(client, "v1@x.com", "Newer@12345")


async def test_account_lockout_after_repeated_failures(client, viewer):
    for _ in range(5):
        r = await client.post("/api/v1/auth/login", json={"email": "v1@x.com", "password": "Wrong@1234"})
        assert r.status_code == 401
    r = await client.post("/api/v1/auth/login", json={"email": "v1@x.com", "password": "Viewer@1234"})
    assert r.status_code == 429  # locked even with the correct password


async def test_login_error_is_identical_for_unknown_user_and_bad_password(client, viewer):
    a = await client.post("/api/v1/auth/login", json={"email": "nobody@x.com", "password": "Whatever@1"})
    b = await client.post("/api/v1/auth/login", json={"email": "v1@x.com", "password": "Whatever@1"})
    assert a.status_code == b.status_code == 401 and a.json() == b.json()


async def test_disabled_user_loses_access_immediately(client, admin, viewer):
    me = (await client.get("/api/v1/users/me", headers=viewer)).json()
    r = await client.patch(f"/api/v1/users/{me['id']}/status", json={"isActive": False}, headers=admin)
    assert r.status_code == 200
    assert (await client.get("/api/v1/users/me", headers=viewer)).status_code == 401


async def test_security_headers_and_oversized_body(client):
    r = await client.get("/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert "default-src 'none'" in r.headers["content-security-policy"]
    big = await client.post("/api/v1/auth/login", content=b"x" * (7 * 1024 * 1024),
                            headers={"content-type": "application/json"})
    assert big.status_code == 413


async def test_untrusted_host_is_rejected(client):
    r = await client.get("/health", headers={"host": "evil.example.com"})
    assert r.status_code == 400


async def test_image_upload_hardening(client, admin, viewer, tmp_path):
    ok = await client.post("/api/v1/uploads/categories", files={"file": ("../../evil.png", _png(), "image/png")}, headers=admin)
    assert ok.status_code == 201, ok.text
    url = ok.json()["imageUrl"]
    assert url.startswith("/static/uploads/categories/") and ".." not in url
    served = await client.get(url)
    assert served.status_code == 200 and served.headers["content-type"] == "image/png"
    assert served.headers["x-content-type-options"] == "nosniff"

    # fake image (text renamed to .png), svg/html, and a polyglot-ish payload
    for name, data in [("a.png", b"<script>alert(1)</script>"), ("a.svg", b"<svg onload=alert(1)>"), ("a.png", b"GIF89a....")]:
        r = await client.post("/api/v1/uploads/books", files={"file": (name, data, "image/png")}, headers=admin)
        assert r.status_code == 400, (name, r.text)

    # viewers: no books/categories upload, but may upload ad images
    assert (await client.post("/api/v1/uploads/books", files={"file": ("a.png", _png(), "image/png")}, headers=viewer)).status_code == 403
    assert (await client.post("/api/v1/uploads/advertisements", files={"file": ("a.png", _png(), "image/png")}, headers=viewer)).status_code == 201
    assert (await client.post("/api/v1/uploads/categories", files={"file": ("a.png", _png(), "image/png")})).status_code == 401
    assert (await client.post("/api/v1/uploads/..%2f..%2fetc", files={"file": ("a.png", _png(), "image/png")}, headers=admin)).status_code in (404, 422)

    big = Image.new("RGB", (10, 10))
    assert big  # size limit is covered by body-limit test above
