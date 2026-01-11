"""Тесты health endpoints."""

import pytest


class TestHealthEndpoints:
    """Тесты health check."""

    def test_root(self, client):
        """GET / возвращает информацию об API."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Network Collector API"
        assert "version" in data
        assert data["docs"] == "/docs"

    def test_health(self, client):
        """GET /health возвращает статус."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data
        assert "uptime" in data
        assert isinstance(data["uptime"], float)
        assert data["uptime"] >= 0

    def test_docs_available(self, client):
        """Swagger docs доступны."""
        response = client.get("/docs")
        assert response.status_code == 200

    def test_redoc_available(self, client):
        """ReDoc доступен."""
        response = client.get("/redoc")
        assert response.status_code == 200
