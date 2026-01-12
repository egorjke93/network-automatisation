"""Fixtures для API тестов.

Credentials передаются через HTTP headers:
- X-SSH-Username
- X-SSH-Password
- X-NetBox-URL
- X-NetBox-Token

Требует: pip install fastapi uvicorn httpx
"""

import pytest

# Skip all API tests if fastapi not installed
pytest.importorskip("fastapi", reason="fastapi not installed, skipping API tests")

from fastapi.testclient import TestClient

from network_collector.api.main import app


class AuthenticatedTestClient:
    """TestClient wrapper с автоматическими auth headers."""

    def __init__(self, client: TestClient, headers: dict):
        self._client = client
        self._headers = headers

    def _merge_headers(self, kwargs):
        """Объединяет auth headers с пользовательскими."""
        headers = kwargs.get("headers", {})
        headers.update(self._headers)
        kwargs["headers"] = headers
        return kwargs

    def get(self, *args, **kwargs):
        return self._client.get(*args, **self._merge_headers(kwargs))

    def post(self, *args, **kwargs):
        return self._client.post(*args, **self._merge_headers(kwargs))

    def put(self, *args, **kwargs):
        return self._client.put(*args, **self._merge_headers(kwargs))

    def delete(self, *args, **kwargs):
        return self._client.delete(*args, **self._merge_headers(kwargs))

    def patch(self, *args, **kwargs):
        return self._client.patch(*args, **self._merge_headers(kwargs))


@pytest.fixture
def client():
    """TestClient для API."""
    with TestClient(app) as client:
        yield client


@pytest.fixture
def credentials_data():
    """Тестовые credentials."""
    return {
        "username": "testuser",
        "password": "testpass",
    }


@pytest.fixture
def netbox_config_data():
    """Тестовый NetBox config."""
    return {
        "url": "http://netbox.example.com",
        "token": "test-token-12345",
    }


@pytest.fixture
def auth_headers(credentials_data):
    """Headers с SSH credentials."""
    return {
        "X-SSH-Username": credentials_data["username"],
        "X-SSH-Password": credentials_data["password"],
    }


@pytest.fixture
def full_auth_headers(credentials_data, netbox_config_data):
    """Headers с SSH и NetBox credentials."""
    return {
        "X-SSH-Username": credentials_data["username"],
        "X-SSH-Password": credentials_data["password"],
        "X-NetBox-URL": netbox_config_data["url"],
        "X-NetBox-Token": netbox_config_data["token"],
    }


@pytest.fixture
def client_with_credentials(client, auth_headers):
    """Client с SSH credentials в каждом запросе."""
    return AuthenticatedTestClient(client, auth_headers)


@pytest.fixture
def client_with_netbox(client, full_auth_headers):
    """Client с SSH и NetBox credentials в каждом запросе."""
    return AuthenticatedTestClient(client, full_auth_headers)
