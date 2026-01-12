"""Тесты sync endpoints."""

import pytest
from unittest.mock import patch, MagicMock


class TestSyncEndpoint:
    """Тесты /api/sync."""

    def test_sync_requires_credentials(self, client):
        """Sync требует credentials."""
        response = client.post("/api/sync/netbox", json={"sync_all": True})
        assert response.status_code == 401

    def test_sync_requires_netbox(self, client_with_credentials):
        """Sync требует NetBox config в headers."""
        response = client_with_credentials.post(
            "/api/sync/netbox",
            json={"sync_all": True},
        )
        assert response.status_code == 401
        assert "X-NetBox-URL" in response.json()["detail"]

    @patch("network_collector.api.services.sync_service.NetBoxClient")
    @patch("network_collector.api.services.sync_service.NetBoxSync")
    @patch("network_collector.api.services.sync_service.DeviceCollector")
    def test_sync_devices_dry_run(
        self,
        mock_device_collector_class,
        mock_sync_class,
        mock_client_class,
        client_with_netbox,
    ):
        """Dry run sync devices."""
        # Mock DeviceCollector
        mock_device_collector = MagicMock()
        mock_device_collector.collect_dicts.return_value = [
            {"hostname": "switch1", "model": "WS-C2960"}
        ]
        mock_device_collector_class.return_value = mock_device_collector

        # Mock NetBoxSync
        mock_sync = MagicMock()
        mock_sync.sync_devices_from_inventory.return_value = {
            "created": 1,
            "updated": 0,
            "skipped": 0,
            "failed": 0,
            "details": {
                "created": [{"name": "switch1"}],
            },
        }
        mock_sync_class.return_value = mock_sync

        response = client_with_netbox.post(
            "/api/sync/netbox",
            json={
                "devices": ["10.0.0.1"],
                "create_devices": True,
                "dry_run": True,
                "site": "Office",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["dry_run"] is True
        assert data["devices"]["created"] == 1

    @patch("network_collector.api.services.sync_service.NetBoxClient")
    @patch("network_collector.api.services.sync_service.NetBoxSync")
    @patch("network_collector.api.services.sync_service.InterfaceCollector")
    def test_sync_interfaces(
        self,
        mock_interface_collector_class,
        mock_sync_class,
        mock_client_class,
        client_with_netbox,
    ):
        """Sync interfaces."""
        # Mock InterfaceCollector
        mock_interface_collector = MagicMock()
        mock_interface_collector.collect_dicts.return_value = [
            {"hostname": "switch1", "name": "Gi0/1", "status": "up"},
            {"hostname": "switch1", "name": "Gi0/2", "status": "down"},
        ]
        mock_interface_collector_class.return_value = mock_interface_collector

        # Mock NetBoxSync
        mock_sync = MagicMock()
        mock_sync.sync_interfaces.return_value = {
            "created": 2,
            "updated": 0,
            "skipped": 0,
            "details": {
                "created": [{"name": "Gi0/1"}, {"name": "Gi0/2"}],
            },
        }
        mock_sync_class.return_value = mock_sync

        response = client_with_netbox.post(
            "/api/sync/netbox",
            json={
                "devices": ["10.0.0.1"],
                "interfaces": True,
                "dry_run": False,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["interfaces"]["created"] == 2

    @patch("network_collector.api.services.sync_service.NetBoxClient")
    @patch("network_collector.api.services.sync_service.NetBoxSync")
    @patch("network_collector.api.services.sync_service.LLDPCollector")
    def test_sync_cables(
        self,
        mock_lldp_collector_class,
        mock_sync_class,
        mock_client_class,
        client_with_netbox,
    ):
        """Sync cables from LLDP."""
        # Mock LLDPCollector
        mock_lldp_collector = MagicMock()
        mock_lldp_collector.collect_dicts.return_value = [
            {
                "hostname": "switch1",
                "local_interface": "Gi0/1",
                "remote_hostname": "switch2",
                "remote_port": "Gi0/24",
            }
        ]
        mock_lldp_collector_class.return_value = mock_lldp_collector

        # Mock NetBoxSync
        mock_sync = MagicMock()
        mock_sync.sync_cables_from_lldp.return_value = {
            "created": 1,
            "skipped": 0,
            "failed": 0,
        }
        mock_sync_class.return_value = mock_sync

        response = client_with_netbox.post(
            "/api/sync/netbox",
            json={
                "devices": ["10.0.0.1"],
                "cables": True,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["cables"]["created"] == 1

    def test_sync_no_devices(self, client_with_netbox):
        """Sync без устройств."""
        with patch(
            "network_collector.api.services.sync_service.SyncService._get_devices"
        ) as mock_get:
            mock_get.return_value = []

            response = client_with_netbox.post(
                "/api/sync/netbox",
                json={"sync_all": True},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is False
            assert "No devices to sync" in data["errors"]


class TestSyncDiff:
    """Тесты diff output."""

    @patch("network_collector.api.services.sync_service.NetBoxClient")
    @patch("network_collector.api.services.sync_service.NetBoxSync")
    @patch("network_collector.api.services.sync_service.DeviceCollector")
    def test_sync_returns_diff(
        self,
        mock_device_collector_class,
        mock_sync_class,
        mock_client_class,
        client_with_netbox,
    ):
        """Sync возвращает diff entries."""
        mock_device_collector = MagicMock()
        mock_device_collector.collect_dicts.return_value = [
            {"hostname": "switch1"},
            {"hostname": "switch2"},
        ]
        mock_device_collector_class.return_value = mock_device_collector

        mock_sync = MagicMock()
        mock_sync.sync_devices_from_inventory.return_value = {
            "created": 1,
            "updated": 1,
            "skipped": 0,
            "failed": 0,
            "details": {
                "created": [{"name": "switch1"}],
                "updated": [{"name": "switch2"}],
            },
        }
        mock_sync_class.return_value = mock_sync

        response = client_with_netbox.post(
            "/api/sync/netbox",
            json={
                "devices": ["10.0.0.1", "10.0.0.2"],
                "create_devices": True,
                "update_devices": True,
            },
        )
        assert response.status_code == 200
        data = response.json()

        # Проверяем что есть diff
        assert "diff" in data
        diff = data["diff"]
        assert len(diff) == 2

        # Проверяем структуру diff entry
        created_entries = [d for d in diff if d["action"] == "created"]
        updated_entries = [d for d in diff if d["action"] == "updated"]
        assert len(created_entries) == 1
        assert len(updated_entries) == 1
        assert created_entries[0]["entity_type"] == "device"
        assert created_entries[0]["entity_name"] == "switch1"


class TestMatchEndpoint:
    """Тесты /api/match."""

    def test_match_stub_response(self, client_with_credentials):
        """Match возвращает stub ответ (TODO)."""
        response = client_with_credentials.post(
            "/api/match/run",
            json={
                "mac_file": "/tmp/mac_table.xlsx",
                "source": "glpi",
            },
        )
        assert response.status_code == 200
        data = response.json()
        # Пока stub
        assert data["success"] is False

    def test_match_requires_mac_file(self, client_with_credentials):
        """Match требует mac_file."""
        response = client_with_credentials.post(
            "/api/match/run",
            json={"source": "glpi"},
        )
        assert response.status_code == 422


class TestPushEndpoint:
    """Тесты /api/push."""

    def test_push_stub_response(self, client_with_credentials):
        """Push возвращает stub ответ (TODO)."""
        response = client_with_credentials.post(
            "/api/push/descriptions",
            json={
                "source_file": "/tmp/descriptions.xlsx",
                "dry_run": True,
            },
        )
        assert response.status_code == 200
        data = response.json()
        # Пока stub
        assert data["success"] is False

    def test_push_requires_source_file(self, client_with_credentials):
        """Push требует source_file."""
        response = client_with_credentials.post(
            "/api/push/descriptions",
            json={"dry_run": True},
        )
        assert response.status_code == 422
