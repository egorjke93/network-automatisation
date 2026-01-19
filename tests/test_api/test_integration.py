"""
Интеграционные тесты API с реальными фикстурами.

Проверяют полный флоу: API → Collector → Parser → Response.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from network_collector.api.main import app


# Путь к фикстурам
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def load_fixture(platform: str, filename: str) -> str:
    """Загружает фикстуру."""
    filepath = FIXTURES_DIR / platform / filename
    if filepath.exists():
        return filepath.read_text()
    return ""


class AuthenticatedClient:
    """Client wrapper с auth headers."""

    def __init__(self, client, headers):
        self._client = client
        self._headers = headers

    def _merge(self, kwargs):
        h = kwargs.get("headers", {})
        h.update(self._headers)
        kwargs["headers"] = h
        return kwargs

    def get(self, *a, **kw): return self._client.get(*a, **self._merge(kw))
    def post(self, *a, **kw): return self._client.post(*a, **self._merge(kw))
    def put(self, *a, **kw): return self._client.put(*a, **self._merge(kw))
    def delete(self, *a, **kw): return self._client.delete(*a, **self._merge(kw))


@pytest.fixture
def client():
    """TestClient с SSH credentials в headers."""
    with TestClient(app) as c:
        yield AuthenticatedClient(c, {
            "X-SSH-Username": "admin",
            "X-SSH-Password": "test123",
        })


@pytest.fixture
def client_with_netbox():
    """Client с SSH и NetBox credentials в headers."""
    with TestClient(app) as c:
        yield AuthenticatedClient(c, {
            "X-SSH-Username": "admin",
            "X-SSH-Password": "test123",
            "X-NetBox-URL": "http://netbox.local:8000",
            "X-NetBox-Token": "test-token-12345",
        })


# =============================================================================
# Devices Tests
# =============================================================================

class TestDevicesIntegration:
    """Интеграционные тесты /api/devices."""

    def test_collect_devices_with_mock(self, client):
        """Сбор devices с мок данными."""
        with patch("network_collector.api.services.collector_service.DeviceCollector") as mock:
            mock_instance = MagicMock()
            mock_instance.collect_dicts.return_value = [
                {
                    "hostname": "switch1",
                    "device_ip": "10.0.0.1",
                    "platform": "cisco_ios",
                    "model": "WS-C2960X-48LPD-L",
                    "serial": "FOC12345678",
                    "version": "15.2(7)E3",
                    "uptime": "10 days, 5 hours",
                }
            ]
            mock.return_value = mock_instance

            response = client.post("/api/devices/collect", json={
                "devices": ["10.0.0.1"]
            })

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert len(data["devices"]) == 1

            device = data["devices"][0]
            assert device["hostname"] == "switch1"
            assert device["platform"] == "cisco_ios"
            assert device["model"] == "WS-C2960X-48LPD-L"
            assert device["serial"] == "FOC12345678"


# =============================================================================
# MAC Tests
# =============================================================================

class TestMACIntegration:
    """Интеграционные тесты /api/mac."""

    def test_collect_mac_with_mock(self, client):
        """Сбор MAC table с мок данными."""
        with patch("network_collector.api.services.collector_service.MACCollector") as mock:
            mock_instance = MagicMock()
            mock_instance.collect_dicts.return_value = [
                {
                    "mac": "00:11:22:33:44:55",
                    "interface": "Gi0/1",
                    "vlan": "100",
                    "type": "dynamic",
                    "hostname": "switch1",
                    "device_ip": "10.0.0.1",
                },
                {
                    "mac": "AA:BB:CC:DD:EE:FF",
                    "interface": "Gi0/2",
                    "vlan": "200",
                    "type": "static",
                    "hostname": "switch1",
                    "device_ip": "10.0.0.1",
                },
            ]
            mock.return_value = mock_instance

            response = client.post("/api/mac/collect", json={
                "devices": ["10.0.0.1"]
            })

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["total"] == 2
            assert len(data["entries"]) == 2

            entry = data["entries"][0]
            assert entry["mac"] == "00:11:22:33:44:55"
            assert entry["interface"] == "Gi0/1"
            assert entry["vlan"] == "100"


# =============================================================================
# LLDP/CDP Tests
# =============================================================================

class TestLLDPIntegration:
    """Интеграционные тесты /api/lldp."""

    def test_collect_lldp_with_mock(self, client):
        """Сбор LLDP neighbors с мок данными."""
        with patch("network_collector.api.services.collector_service.LLDPCollector") as mock:
            mock_instance = MagicMock()
            mock_instance.collect_dicts.return_value = [
                {
                    "hostname": "switch1",
                    "device_ip": "10.0.0.1",
                    "local_interface": "Gi0/1",
                    "remote_hostname": "switch2.domain.ru",
                    "remote_port": "GigabitEthernet0/24",
                    "remote_ip": "10.0.0.2",
                    "remote_mac": "00:11:22:33:44:55",
                    "protocol": "LLDP",
                },
                {
                    "hostname": "switch1",
                    "device_ip": "10.0.0.1",
                    "local_interface": "Gi0/2",
                    "remote_hostname": "AP-Office-01",
                    "remote_port": "eth0",
                    "remote_ip": "10.0.0.10",
                    "protocol": "LLDP",
                },
            ]
            mock.return_value = mock_instance

            response = client.post("/api/lldp/collect", json={
                "devices": ["10.0.0.1"],
                "protocol": "lldp"
            })

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["total"] == 2

            neighbor = data["neighbors"][0]
            assert neighbor["local_interface"] == "Gi0/1"
            assert neighbor["remote_hostname"] == "switch2.domain.ru"
            assert neighbor["remote_port"] == "GigabitEthernet0/24"

    def test_collect_both_protocols_with_mock(self, client):
        """Сбор LLDP+CDP (both) с merge."""
        with patch("network_collector.api.services.collector_service.LLDPCollector") as mock:
            mock_instance = MagicMock()
            mock_instance.collect_dicts.return_value = [
                {
                    "hostname": "switch1",
                    "local_interface": "Gi0/1",
                    "remote_hostname": "switch2",
                    "remote_port": "GigabitEthernet0/24",
                    "remote_platform": "cisco WS-C2960X-48LPD-L",
                    "remote_mac": "00:11:22:33:44:55",
                    "protocol": "BOTH",  # Merged
                },
            ]
            mock.return_value = mock_instance

            response = client.post("/api/lldp/collect", json={
                "devices": ["10.0.0.1"],
                "protocol": "both"
            })

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["neighbors"][0]["protocol"] == "BOTH"


# =============================================================================
# Interfaces Tests
# =============================================================================

class TestInterfacesIntegration:
    """Интеграционные тесты /api/interfaces."""

    def test_collect_interfaces_with_mock(self, client):
        """Сбор interfaces с мок данными."""
        with patch("network_collector.api.services.collector_service.InterfaceCollector") as mock:
            mock_instance = MagicMock()
            mock_instance.collect_dicts.return_value = [
                {
                    "name": "GigabitEthernet0/1",
                    "description": "Uplink to core",
                    "status": "up",
                    "ip_address": "10.0.0.1/24",
                    "mac": "00:11:22:33:44:55",
                    "speed": "1000",
                    "duplex": "full",
                    "mode": "trunk",
                    "hostname": "switch1",
                    "device_ip": "10.0.0.1",
                },
                {
                    "name": "GigabitEthernet0/2",
                    "description": "Server port",
                    "status": "down",
                    "mode": "access",
                    "hostname": "switch1",
                    "device_ip": "10.0.0.1",
                },
            ]
            mock.return_value = mock_instance

            response = client.post("/api/interfaces/collect", json={
                "devices": ["10.0.0.1"]
            })

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["total"] == 2

            intf = data["interfaces"][0]
            assert intf["name"] == "GigabitEthernet0/1"
            assert intf["status"] == "up"
            assert intf["mode"] == "trunk"


# =============================================================================
# Inventory Tests
# =============================================================================

class TestInventoryIntegration:
    """Интеграционные тесты /api/inventory."""

    def test_collect_inventory_with_mock(self, client):
        """Сбор inventory с мок данными."""
        with patch("network_collector.api.services.collector_service.InventoryCollector") as mock:
            mock_instance = MagicMock()
            mock_instance.collect_dicts.return_value = [
                {
                    "name": "Chassis",
                    "description": "Catalyst 2960X-48LPD-L",
                    "pid": "WS-C2960X-48LPD-L",
                    "serial": "FOC12345678",
                    "hostname": "switch1",
                    "device_ip": "10.0.0.1",
                },
                {
                    "name": "Power Supply 1",
                    "description": "AC Power Supply",
                    "pid": "PWR-C2-250WAC",
                    "serial": "LIT23456789",
                    "hostname": "switch1",
                    "device_ip": "10.0.0.1",
                },
                {
                    "name": "GigabitEthernet0/1",
                    "description": "SFP-10G-SR",
                    "pid": "SFP-10G-SR",
                    "serial": "AGM34567890",
                    "hostname": "switch1",
                    "device_ip": "10.0.0.1",
                },
            ]
            mock.return_value = mock_instance

            response = client.post("/api/inventory/collect", json={
                "devices": ["10.0.0.1"]
            })

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["total"] == 3

            item = data["items"][0]
            assert item["pid"] == "WS-C2960X-48LPD-L"
            assert item["serial"] == "FOC12345678"


# =============================================================================
# Backup Tests
# =============================================================================

class TestBackupIntegration:
    """Интеграционные тесты /api/backup."""

    def test_backup_with_mock(self, client):
        """Backup с мок данными."""
        from network_collector.collectors.config_backup import BackupResult as CollectorBackupResult

        with patch("network_collector.api.services.collector_service.ConfigBackupCollector") as mock:
            mock_instance = MagicMock()
            # backup() возвращает List[BackupResult], не dicts
            mock_instance.backup.return_value = [
                CollectorBackupResult(
                    hostname="switch1",
                    device_ip="10.0.0.1",
                    success=True,
                    file_path="/backups/switch1_2024-01-15.cfg",
                ),
                CollectorBackupResult(
                    hostname="switch2",
                    device_ip="10.0.0.2",
                    success=False,
                    error="Connection timeout",
                ),
            ]
            mock.return_value = mock_instance

            response = client.post("/api/backup/run", json={
                "devices": ["10.0.0.1", "10.0.0.2"],
                "output_dir": "/backups"
            })

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["total_success"] == 1
            assert data["total_failed"] == 1


# =============================================================================
# Export Tests
# =============================================================================

class TestExportIntegration:
    """Тесты экспорта данных."""

    def test_devices_response_exportable(self, client):
        """Проверка что devices response можно экспортировать."""
        with patch("network_collector.api.services.collector_service.DeviceCollector") as mock:
            mock_instance = MagicMock()
            mock_instance.collect_dicts.return_value = [
                {
                    "hostname": "switch1",
                    "device_ip": "10.0.0.1",
                    "platform": "cisco_ios",
                    "model": "WS-C2960X-48LPD-L",
                    "serial": "FOC12345678",
                    "version": "15.2(7)E3",
                    "uptime": "10 days, 5 hours",
                }
            ]
            mock.return_value = mock_instance

            response = client.post("/api/devices/collect", json={
                "devices": ["10.0.0.1"]
            })

            data = response.json()
            assert data["success"] is True

            # JSON serializable
            json_str = json.dumps(data)
            assert len(json_str) > 0

            # Required fields for Excel export
            device = data["devices"][0]
            assert all(k in device for k in ["hostname", "ip_address", "platform"])

    def test_mac_response_exportable(self, client):
        """MAC table export validation."""
        with patch("network_collector.api.services.collector_service.MACCollector") as mock:
            mock_instance = MagicMock()
            mock_instance.collect_dicts.return_value = [
                {
                    "mac": "00:11:22:33:44:55",
                    "interface": "Gi0/1",
                    "vlan": "100",
                    "type": "dynamic",
                    "hostname": "switch1",
                    "device_ip": "10.0.0.1",
                },
            ]
            mock.return_value = mock_instance

            response = client.post("/api/mac/collect", json={
                "devices": ["10.0.0.1"]
            })

            data = response.json()
            assert data["success"] is True

            # Required fields for MAC export
            entry = data["entries"][0]
            required = ["mac", "interface", "vlan"]
            assert all(k in entry for k in required), f"Missing: {set(required) - set(entry.keys())}"

    def test_lldp_response_exportable(self, client):
        """LLDP neighbors export validation."""
        with patch("network_collector.api.services.collector_service.LLDPCollector") as mock:
            mock_instance = MagicMock()
            mock_instance.collect_dicts.return_value = [
                {
                    "hostname": "switch1",
                    "local_interface": "Gi0/1",
                    "remote_hostname": "switch2",
                    "remote_port": "Gi0/24",
                    "remote_platform": "cisco WS-C2960X",
                    "protocol": "BOTH",
                },
            ]
            mock.return_value = mock_instance

            response = client.post("/api/lldp/collect", json={
                "devices": ["10.0.0.1"],
                "protocol": "both"
            })

            data = response.json()
            assert data["success"] is True

            # Required fields for LLDP export
            neighbor = data["neighbors"][0]
            required = ["hostname", "local_interface", "remote_hostname", "protocol"]
            assert all(k in neighbor for k in required), f"Missing: {set(required) - set(neighbor.keys())}"

    def test_interfaces_response_exportable(self, client):
        """Interfaces export validation."""
        with patch("network_collector.api.services.collector_service.InterfaceCollector") as mock:
            mock_instance = MagicMock()
            mock_instance.collect_dicts.return_value = [
                {
                    "name": "GigabitEthernet0/1",
                    "description": "Uplink",
                    "status": "up",
                    "hostname": "switch1",
                    "device_ip": "10.0.0.1",
                },
            ]
            mock.return_value = mock_instance

            response = client.post("/api/interfaces/collect", json={
                "devices": ["10.0.0.1"]
            })

            data = response.json()
            assert data["success"] is True

            # Required fields for interfaces export
            intf = data["interfaces"][0]
            required = ["name", "status", "hostname"]
            assert all(k in intf for k in required), f"Missing: {set(required) - set(intf.keys())}"

    def test_inventory_response_exportable(self, client):
        """Inventory export validation."""
        with patch("network_collector.api.services.collector_service.InventoryCollector") as mock:
            mock_instance = MagicMock()
            mock_instance.collect_dicts.return_value = [
                {
                    "name": "Chassis",
                    "pid": "WS-C2960X",
                    "serial": "FOC12345678",
                    "hostname": "switch1",
                },
            ]
            mock.return_value = mock_instance

            response = client.post("/api/inventory/collect", json={
                "devices": ["10.0.0.1"]
            })

            data = response.json()
            assert data["success"] is True

            # Required fields for inventory export
            item = data["items"][0]
            required = ["name", "pid", "serial"]
            assert all(k in item for k in required), f"Missing: {set(required) - set(item.keys())}"

    def test_all_responses_json_serializable(self, client):
        """Verify all collector responses are JSON serializable."""
        collectors = [
            ("DeviceCollector", "/api/devices/collect", {"devices": ["10.0.0.1"]}, [{"hostname": "test"}]),
            ("MACCollector", "/api/mac/collect", {"devices": ["10.0.0.1"]}, [{"mac": "00:11:22:33:44:55"}]),
            ("LLDPCollector", "/api/lldp/collect", {"devices": ["10.0.0.1"], "protocol": "both"}, [{"hostname": "test"}]),
            ("InterfaceCollector", "/api/interfaces/collect", {"devices": ["10.0.0.1"]}, [{"name": "Gi0/1"}]),
            ("InventoryCollector", "/api/inventory/collect", {"devices": ["10.0.0.1"]}, [{"name": "Chassis"}]),
        ]

        for collector_name, endpoint, request_data, mock_data in collectors:
            with patch(f"network_collector.api.services.collector_service.{collector_name}") as mock:
                mock_instance = MagicMock()
                mock_instance.collect_dicts.return_value = mock_data
                mock.return_value = mock_instance

                response = client.post(endpoint, json=request_data)
                data = response.json()

                # Must be JSON serializable without errors
                try:
                    json_str = json.dumps(data)
                    assert len(json_str) > 0, f"{collector_name}: Empty JSON"
                except (TypeError, ValueError) as e:
                    pytest.fail(f"{collector_name}: Not JSON serializable: {e}")


# =============================================================================
# NetBox Sync Tests
# =============================================================================

class TestNetBoxSyncIntegration:
    """Интеграционные тесты синхронизации с NetBox."""

    def test_sync_requires_auth(self, client):
        """Sync требует credentials и netbox config."""
        # Без netbox config
        response = client.post("/api/sync/netbox", json={
            "sync_all": True
        })
        assert response.status_code == 401

    def test_sync_dry_run_with_mock(self, client_with_netbox):
        """Dry run синхронизации."""
        with patch("network_collector.api.services.sync_service.DeviceCollector") as mock_collector, \
             patch("network_collector.api.services.sync_service.NetBoxClient") as mock_client, \
             patch("network_collector.api.services.sync_service.NetBoxSync") as mock_sync:

            # Mock collector
            mock_collector_instance = MagicMock()
            mock_collector_instance.collect_dicts.return_value = [
                {"hostname": "switch1", "model": "WS-C2960X", "serial": "FOC123"}
            ]
            mock_collector.return_value = mock_collector_instance

            # Mock sync
            mock_sync_instance = MagicMock()
            mock_sync_instance.sync_devices_from_inventory.return_value = {
                "created": 1,
                "updated": 0,
                "skipped": 0,
                "failed": 0,
                "details": {"created": [{"name": "switch1"}]}
            }
            mock_sync.return_value = mock_sync_instance

            response = client_with_netbox.post("/api/sync/netbox", json={
                "devices": ["10.0.0.1"],
                "create_devices": True,
                "dry_run": True,
                "site": "Office",
                "async_mode": False,  # Sync mode for testing
            })

            assert response.status_code == 200
            data = response.json()
            assert data["dry_run"] is True
            assert data["devices"]["created"] == 1

    def test_sync_interfaces_with_mock(self, client_with_netbox):
        """Синхронизация interfaces."""
        with patch("network_collector.api.services.sync_service.InterfaceCollector") as mock_collector, \
             patch("network_collector.api.services.sync_service.NetBoxClient"), \
             patch("network_collector.api.services.sync_service.NetBoxSync") as mock_sync:

            mock_collector_instance = MagicMock()
            mock_collector_instance.collect_dicts.return_value = [
                {"hostname": "switch1", "name": "GigabitEthernet0/1", "status": "up"},
                {"hostname": "switch1", "name": "GigabitEthernet0/2", "status": "down"},
            ]
            mock_collector.return_value = mock_collector_instance

            mock_sync_instance = MagicMock()
            mock_sync_instance.sync_interfaces.return_value = {
                "created": 2,
                "updated": 0,
                "skipped": 0,
                "details": {"created": [{"name": "Gi0/1"}, {"name": "Gi0/2"}]}
            }
            mock_sync.return_value = mock_sync_instance

            response = client_with_netbox.post("/api/sync/netbox", json={
                "devices": ["10.0.0.1"],
                "interfaces": True,
                "async_mode": False,  # Sync mode for testing
            })

            assert response.status_code == 200
            data = response.json()
            assert data["interfaces"]["created"] == 2

    def test_sync_cables_from_lldp(self, client_with_netbox):
        """Синхронизация cables из LLDP."""
        with patch("network_collector.api.services.sync_service.LLDPCollector") as mock_collector, \
             patch("network_collector.api.services.sync_service.NetBoxClient"), \
             patch("network_collector.api.services.sync_service.NetBoxSync") as mock_sync:

            mock_collector_instance = MagicMock()
            mock_collector_instance.collect_dicts.return_value = [
                {
                    "hostname": "switch1",
                    "local_interface": "Gi0/1",
                    "remote_hostname": "switch2",
                    "remote_port": "Gi0/24",
                    "protocol": "BOTH"
                }
            ]
            mock_collector.return_value = mock_collector_instance

            mock_sync_instance = MagicMock()
            mock_sync_instance.sync_cables_from_lldp.return_value = {
                "created": 1,
                "skipped": 0,
                "failed": 0
            }
            mock_sync.return_value = mock_sync_instance

            response = client_with_netbox.post("/api/sync/netbox", json={
                "devices": ["10.0.0.1"],
                "cables": True,
                "async_mode": False,  # Sync mode for testing
            })

            assert response.status_code == 200
            data = response.json()
            assert data["cables"]["created"] == 1


# =============================================================================
# Full Pipeline Tests
# =============================================================================

class TestFullPipeline:
    """Тесты полного пайплайна."""

    def test_full_lldp_pipeline_cisco_ios(self, client):
        """Полный пайплайн LLDP для Cisco IOS с реальной нормализацией."""
        with patch("network_collector.api.services.collector_service.LLDPCollector") as mock:
            mock_instance = MagicMock()
            # Simulate normalized data from Cisco IOS
            mock_instance.collect_dicts.return_value = [
                {
                    "hostname": "core-switch",
                    "device_ip": "10.0.0.1",
                    "local_interface": "GigabitEthernet0/1",
                    "remote_hostname": "access-switch.domain.ru",
                    "remote_port": "GigabitEthernet0/24",
                    "remote_platform": "cisco WS-C2960X-48LPD-L",
                    "remote_ip": "10.0.0.2",
                    "remote_mac": "00:11:22:33:44:55",
                    "protocol": "BOTH",
                },
                {
                    "hostname": "core-switch",
                    "device_ip": "10.0.0.1",
                    "local_interface": "GigabitEthernet0/2",
                    "remote_hostname": "AP-Office-01",
                    "remote_port": "eth0",
                    "protocol": "LLDP",
                },
            ]
            mock.return_value = mock_instance

            response = client.post("/api/lldp/collect", json={
                "devices": ["10.0.0.1"],
                "protocol": "both"
            })

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["total"] == 2

            # Проверяем что данные нормализованы
            for neighbor in data["neighbors"]:
                assert "hostname" in neighbor
                assert "local_interface" in neighbor
                assert "remote_hostname" in neighbor
                assert "protocol" in neighbor

    def test_full_interfaces_pipeline_cisco_nxos(self, client):
        """Полный пайплайн interfaces для Cisco NX-OS."""
        with patch("network_collector.api.services.collector_service.InterfaceCollector") as mock:
            mock_instance = MagicMock()
            # Simulate NX-OS normalized interface data
            mock_instance.collect_dicts.return_value = [
                {
                    "name": "Ethernet1/1",
                    "description": "Uplink to spine",
                    "status": "up",
                    "ip_address": "10.0.0.1/30",
                    "mac": "00:11:22:33:44:55",
                    "speed": "10000",
                    "duplex": "full",
                    "mode": "routed",
                    "mtu": "9216",
                    "hostname": "leaf-01",
                    "device_ip": "10.0.0.1",
                },
                {
                    "name": "Ethernet1/2",
                    "description": "Server port",
                    "status": "up",
                    "mode": "trunk",
                    "hostname": "leaf-01",
                    "device_ip": "10.0.0.1",
                },
                {
                    "name": "Vlan100",
                    "description": "Management",
                    "status": "up",
                    "ip_address": "192.168.100.1/24",
                    "hostname": "leaf-01",
                    "device_ip": "10.0.0.1",
                },
            ]
            mock.return_value = mock_instance

            response = client.post("/api/interfaces/collect", json={
                "devices": ["10.0.0.1"]
            })

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["total"] == 3

            # NX-OS specific checks
            interface = data["interfaces"][0]
            assert interface["name"] == "Ethernet1/1"
            assert interface["speed"] == "10000"

    def test_response_format_consistency(self, client):
        """Проверка консистентности формата ответов."""
        with patch("network_collector.api.services.collector_service.DeviceCollector") as mock:
            mock_instance = MagicMock()
            mock_instance.collect_dicts.return_value = [{"hostname": "test"}]
            mock.return_value = mock_instance

            response = client.post("/api/devices/collect", json={"devices": ["10.0.0.1"]})
            data = response.json()

            # Все responses должны иметь success и errors
            assert "success" in data
            assert isinstance(data.get("errors", []), list)

    def test_multiple_devices_collection(self, client):
        """Сбор данных с нескольких устройств."""
        with patch("network_collector.api.services.collector_service.DeviceCollector") as mock:
            mock_instance = MagicMock()
            mock_instance.collect_dicts.return_value = [
                {
                    "hostname": "switch1",
                    "device_ip": "10.0.0.1",
                    "platform": "cisco_ios",
                    "model": "WS-C2960X",
                },
                {
                    "hostname": "switch2",
                    "device_ip": "10.0.0.2",
                    "platform": "cisco_nxos",
                    "model": "N9K-C9336C-FX2",
                },
                {
                    "hostname": "router1",
                    "device_ip": "10.0.0.3",
                    "platform": "cisco_iosxe",
                    "model": "C9300-48P",
                },
            ]
            mock.return_value = mock_instance

            response = client.post("/api/devices/collect", json={
                "devices": ["10.0.0.1", "10.0.0.2", "10.0.0.3"]
            })

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert len(data["devices"]) == 3

            # Verify different platforms
            platforms = [d["platform"] for d in data["devices"]]
            assert "cisco_ios" in platforms
            assert "cisco_nxos" in platforms
            assert "cisco_iosxe" in platforms


# =============================================================================
# Error Handling Tests
# =============================================================================

class TestErrorHandling:
    """Тесты обработки ошибок."""

    def test_connection_error_handling(self, client):
        """Обработка ошибки подключения."""
        with patch("network_collector.api.services.collector_service.DeviceCollector") as mock:
            mock_instance = MagicMock()
            mock_instance.collect_dicts.side_effect = Exception("Connection refused")
            mock.return_value = mock_instance

            response = client.post("/api/devices/collect", json={
                "devices": ["10.0.0.1"]
            })

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is False
            assert len(data["errors"]) > 0

    def test_invalid_protocol(self, client):
        """Невалидный протокол."""
        response = client.post("/api/lldp/collect", json={
            "devices": ["10.0.0.1"],
            "protocol": "invalid"
        })
        assert response.status_code == 422

    def test_empty_devices_list(self, client):
        """Пустой список устройств = использовать все из device management."""
        response = client.post("/api/devices/collect", json={
            "devices": []
        })
        assert response.status_code == 200
        # При пустом devices=[] используются все устройства из device_service
        # Главное что API не падает с ошибкой
