import os

# must be set BEFORE app modules are imported (settings are read at import time)
os.environ.update({
    "MONGO_URI": "mongodb://unused",
    "JWT_SECRET_KEY": "test-secret-key-that-is-at-least-32-chars-long",
    "ADMIN_EMAIL": "admin@bookstore-demo.com",
    "ADMIN_PASSWORD": "Admin@12345",
    "ENVIRONMENT": "development",
})

import pytest
from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient

from app.core.db import MongoDB, create_indexes
from app.core.middleware import limiter
from app.main import app
from app.services.userService import UserService

limiter.enabled = False  # rate limits have their own dedicated test


@pytest.fixture
async def client():
    MongoDB.db = AsyncMongoMockClient()["bookstore_test"]
    await create_indexes(MongoDB.db)
    await UserService(MongoDB.db).seed_admin()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


async def login(client, email, password) -> dict:
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['accessToken']}"}


@pytest.fixture
async def admin(client):
    return await login(client, "admin@bookstore-demo.com", "Admin@12345")


@pytest.fixture
async def viewer(client):
    r = await client.post("/api/v1/auth/register", json={"name": "Viewer One", "email": "v1@x.com", "password": "Viewer@1234"})
    assert r.status_code == 201, r.text
    return await login(client, "v1@x.com", "Viewer@1234")


@pytest.fixture(autouse=True)
def _clean_uploads():
    """Tests upload real files into app/static/uploads - remove them afterwards."""
    yield
    from app.core.config import settings
    for f in settings.UPLOAD_ROOT.glob("*/*"):
        if f.name != ".gitkeep":
            f.unlink(missing_ok=True)
