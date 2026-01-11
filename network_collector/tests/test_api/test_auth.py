"""Тесты auth endpoints.

Credentials передаются через HTTP headers:
- X-SSH-Username
- X-SSH-Password
- X-NetBox-URL
- X-NetBox-Token
"""

import pytest


class TestCredentialsStatus:
    """Тесты статуса credentials (из headers)."""

    def test_credentials_status_no_headers(self, client):
        """Статус когда headers не переданы."""
        response = client.get("/api/auth/credentials/status")
        assert response.status_code == 200
        data = response.json()
        assert data["credentials_set"] is False
        assert data["username"] is None

    def test_credentials_status_with_headers(self, client, auth_headers):
        """Статус когда credentials в headers."""
        response = client.get("/api/auth/credentials/status", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["credentials_set"] is True
        assert data["username"] == "testuser"


class TestNetBoxStatus:
    """Тесты статуса NetBox config (из headers)."""

    def test_netbox_status_no_headers(self, client):
        """Статус когда headers не переданы."""
        response = client.get("/api/auth/netbox/status")
        assert response.status_code == 200
        data = response.json()
        assert data["netbox_configured"] is False
        assert data["url"] is None

    def test_netbox_status_with_headers(self, client, full_auth_headers):
        """Статус когда NetBox в headers."""
        response = client.get("/api/auth/netbox/status", headers=full_auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["netbox_configured"] is True
        assert data["url"] == "http://netbox.example.com"


class TestAuthRequired:
    """Тесты требования авторизации через headers."""

    def test_lldp_requires_credentials(self, client):
        """LLDP endpoint требует credentials в headers."""
        response = client.post("/api/lldp/collect", json={"devices": ["10.0.0.1"]})
        assert response.status_code == 401
        assert "X-SSH-Username" in response.json()["detail"]

    def test_devices_requires_credentials(self, client):
        """Devices endpoint требует credentials в headers."""
        response = client.post("/api/devices/collect", json={})
        assert response.status_code == 401

    def test_mac_requires_credentials(self, client):
        """MAC endpoint требует credentials в headers."""
        response = client.post("/api/mac/collect", json={})
        assert response.status_code == 401

    def test_interfaces_requires_credentials(self, client):
        """Interfaces endpoint требует credentials в headers."""
        response = client.post("/api/interfaces/collect", json={})
        assert response.status_code == 401

    def test_inventory_requires_credentials(self, client):
        """Inventory endpoint требует credentials в headers."""
        response = client.post("/api/inventory/collect", json={})
        assert response.status_code == 401

    def test_backup_requires_credentials(self, client):
        """Backup endpoint требует credentials в headers."""
        response = client.post("/api/backup/run", json={})
        assert response.status_code == 401

    def test_devices_with_credentials_headers(self, client, auth_headers):
        """Devices endpoint работает с credentials в headers."""
        response = client.post(
            "/api/devices/collect",
            json={"devices": []},
            headers=auth_headers,
        )
        # Не 401 - credentials приняты (может быть другая ошибка)
        assert response.status_code != 401
