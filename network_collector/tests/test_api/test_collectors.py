"""Тесты collector endpoints."""

import pytest
from unittest.mock import patch, MagicMock


class TestDevicesEndpoint:
    """Тесты /api/devices."""

    def test_collect_devices_empty_list(self, client_with_credentials):
        """Запрос с пустым списком устройств."""
        response = client_with_credentials.post(
            "/api/devices/collect",
            json={"devices": []},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "No devices" in data["errors"][0]

    @patch("network_collector.api.services.collector_service.DeviceCollector")
    def test_collect_devices_success(self, mock_collector_class, client_with_credentials):
        """Успешный сбор devices."""
        mock_collector = MagicMock()
        mock_collector.collect_dicts.return_value = [
            {
                "hostname": "switch1",
                "device_ip": "10.0.0.1",
                "platform": "cisco_ios",
                "model": "WS-C2960",
                "serial": "FOC12345",
                "version": "15.0(2)SE",
                "uptime": "10 days",
            }
        ]
        mock_collector_class.return_value = mock_collector

        response = client_with_credentials.post(
            "/api/devices/collect",
            json={"devices": ["10.0.0.1"]},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["devices"]) == 1
        assert data["devices"][0]["hostname"] == "switch1"
        assert data["devices"][0]["platform"] == "cisco_ios"

    @patch("network_collector.api.services.collector_service.DeviceCollector")
    def test_collect_devices_error(self, mock_collector_class, client_with_credentials):
        """Ошибка при сборе devices."""
        mock_collector = MagicMock()
        mock_collector.collect_dicts.side_effect = Exception("Connection timeout")
        mock_collector_class.return_value = mock_collector

        response = client_with_credentials.post(
            "/api/devices/collect",
            json={"devices": ["10.0.0.1"]},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "Connection timeout" in data["errors"][0]


class TestMACEndpoint:
    """Тесты /api/mac."""

    @patch("network_collector.api.services.collector_service.MACCollector")
    def test_collect_mac_success(self, mock_collector_class, client_with_credentials):
        """Успешный сбор MAC."""
        mock_collector = MagicMock()
        mock_collector.collect_dicts.return_value = [
            {
                "mac": "00:11:22:33:44:55",
                "interface": "Gi0/1",
                "vlan": 100,
                "hostname": "switch1",
                "device_ip": "10.0.0.1",
                "type": "dynamic",
            },
            {
                "mac": "AA:BB:CC:DD:EE:FF",
                "interface": "Gi0/2",
                "vlan": 200,
                "hostname": "switch1",
                "device_ip": "10.0.0.1",
                "type": "static",
            },
        ]
        mock_collector_class.return_value = mock_collector

        response = client_with_credentials.post(
            "/api/mac/collect",
            json={"devices": ["10.0.0.1"]},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["total"] == 2
        assert len(data["entries"]) == 2
        assert data["entries"][0]["mac"] == "00:11:22:33:44:55"


class TestLLDPEndpoint:
    """Тесты /api/lldp."""

    @patch("network_collector.api.services.collector_service.LLDPCollector")
    def test_collect_lldp_success(self, mock_collector_class, client_with_credentials):
        """Успешный сбор LLDP."""
        mock_collector = MagicMock()
        mock_collector.collect_dicts.return_value = [
            {
                "hostname": "switch1",
                "device_ip": "10.0.0.1",
                "local_interface": "Gi0/1",
                "remote_hostname": "switch2",
                "remote_port": "Gi0/24",
                "remote_ip": "10.0.0.2",
                "protocol": "lldp",
            }
        ]
        mock_collector_class.return_value = mock_collector

        response = client_with_credentials.post(
            "/api/lldp/collect",
            json={"devices": ["10.0.0.1"], "protocol": "lldp"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["total"] == 1
        assert data["neighbors"][0]["remote_hostname"] == "switch2"
        assert data["neighbors"][0]["local_interface"] == "Gi0/1"

    @patch("network_collector.api.services.collector_service.LLDPCollector")
    def test_collect_lldp_both_protocol(self, mock_collector_class, client_with_credentials):
        """Сбор LLDP с protocol=both."""
        mock_collector = MagicMock()
        mock_collector.collect_dicts.return_value = [
            {
                "hostname": "switch1",
                "device_ip": "10.0.0.1",
                "local_interface": "Gi0/1",
                "remote_hostname": "switch2",
                "remote_port": "GigabitEthernet0/24",
                "protocol": "cdp",
            }
        ]
        mock_collector_class.return_value = mock_collector

        response = client_with_credentials.post(
            "/api/lldp/collect",
            json={"devices": ["10.0.0.1"], "protocol": "both"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        # CDP возвращает полные имена интерфейсов
        assert data["neighbors"][0]["remote_port"] == "GigabitEthernet0/24"

    def test_collect_lldp_invalid_protocol(self, client_with_credentials):
        """Неверный protocol."""
        response = client_with_credentials.post(
            "/api/lldp/collect",
            json={"devices": ["10.0.0.1"], "protocol": "invalid"},
        )
        assert response.status_code == 422


class TestInterfacesEndpoint:
    """Тесты /api/interfaces."""

    @patch("network_collector.api.services.collector_service.InterfaceCollector")
    def test_collect_interfaces_success(self, mock_collector_class, client_with_credentials):
        """Успешный сбор interfaces."""
        mock_collector = MagicMock()
        mock_collector.collect_dicts.return_value = [
            {
                "name": "GigabitEthernet0/1",
                "description": "Uplink to core",
                "status": "up",
                "ip_address": "10.0.0.1/24",
                "mac": "00:11:22:33:44:55",
                "speed": "1000",
                "duplex": "full",
                "hostname": "switch1",
                "device_ip": "10.0.0.1",
            }
        ]
        mock_collector_class.return_value = mock_collector

        response = client_with_credentials.post(
            "/api/interfaces/collect",
            json={"devices": ["10.0.0.1"]},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["total"] == 1
        assert data["interfaces"][0]["name"] == "GigabitEthernet0/1"
        assert data["interfaces"][0]["status"] == "up"


class TestInventoryEndpoint:
    """Тесты /api/inventory."""

    @patch("network_collector.api.services.collector_service.InventoryCollector")
    def test_collect_inventory_success(self, mock_collector_class, client_with_credentials):
        """Успешный сбор inventory."""
        mock_collector = MagicMock()
        mock_collector.collect_dicts.return_value = [
            {
                "name": "Chassis",
                "description": "Catalyst 2960 Switch",
                "pid": "WS-C2960-24TT-L",
                "serial": "FOC12345678",
                "hostname": "switch1",
                "device_ip": "10.0.0.1",
            },
            {
                "name": "Power Supply 1",
                "description": "AC Power Supply",
                "pid": "PWR-AC",
                "serial": "FOC87654321",
                "hostname": "switch1",
                "device_ip": "10.0.0.1",
            },
        ]
        mock_collector_class.return_value = mock_collector

        response = client_with_credentials.post(
            "/api/inventory/collect",
            json={"devices": ["10.0.0.1"]},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["total"] == 2
        assert data["items"][0]["pid"] == "WS-C2960-24TT-L"


class TestBackupEndpoint:
    """Тесты /api/backup."""

    @patch("network_collector.api.services.collector_service.ConfigBackupCollector")
    def test_run_backup_success(self, mock_collector_class, client_with_credentials):
        """Успешный backup."""
        mock_collector = MagicMock()
        mock_collector.collect_dicts.return_value = [
            {
                "hostname": "switch1",
                "device_ip": "10.0.0.1",
                "success": True,
                "file_path": "/backups/switch1_2024-01-01.cfg",
            }
        ]
        mock_collector_class.return_value = mock_collector

        response = client_with_credentials.post(
            "/api/backup/run",
            json={"devices": ["10.0.0.1"], "output_dir": "/backups"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["total_success"] == 1
        assert data["total_failed"] == 0
        assert data["results"][0]["file_path"] == "/backups/switch1_2024-01-01.cfg"

    @patch("network_collector.api.services.collector_service.ConfigBackupCollector")
    def test_run_backup_partial_failure(self, mock_collector_class, client_with_credentials):
        """Частичная ошибка backup."""
        mock_collector = MagicMock()
        mock_collector.collect_dicts.return_value = [
            {
                "hostname": "switch1",
                "device_ip": "10.0.0.1",
                "success": True,
                "file_path": "/backups/switch1.cfg",
            },
            {
                "hostname": "switch2",
                "device_ip": "10.0.0.2",
                "success": False,
                "error": "Connection refused",
            },
        ]
        mock_collector_class.return_value = mock_collector

        response = client_with_credentials.post(
            "/api/backup/run",
            json={"devices": ["10.0.0.1", "10.0.0.2"]},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["total_success"] == 1
        assert data["total_failed"] == 1
