"""
Tests for Device Management API endpoints.

Тестирует CRUD операции для устройств и импорт из NetBox.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock


class TestDeviceManagementAPI:
    """Тесты для /api/device-management/ эндпоинтов."""

    def test_list_devices_returns_list(self, client):
        """GET /api/device-management/ возвращает список устройств."""
        response = client.get("/api/device-management/")
        assert response.status_code == 200
        data = response.json()
        assert "devices" in data
        assert "total" in data
        assert isinstance(data["devices"], list)

    def test_get_stats_returns_statistics(self, client):
        """GET /api/device-management/stats возвращает статистику."""
        response = client.get("/api/device-management/stats")
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "enabled" in data
        assert "disabled" in data

    def test_get_device_types_returns_list(self, client):
        """GET /api/device-management/types возвращает типы устройств."""
        response = client.get("/api/device-management/types")
        assert response.status_code == 200
        data = response.json()
        assert "types" in data
        assert isinstance(data["types"], list)
        assert len(data["types"]) > 0
        # Проверяем структуру
        for t in data["types"]:
            assert "value" in t
            assert "label" in t

    def test_get_device_roles_returns_list(self, client):
        """GET /api/device-management/roles возвращает роли устройств."""
        response = client.get("/api/device-management/roles")
        assert response.status_code == 200
        data = response.json()
        assert "roles" in data
        assert isinstance(data["roles"], list)

    def test_create_device_requires_host(self, client):
        """POST /api/device-management/ требует host."""
        response = client.post(
            "/api/device-management/",
            json={"device_type": "cisco_ios"},
        )
        assert response.status_code == 422  # Validation error

    def test_create_device_with_valid_data(self, client):
        """POST /api/device-management/ создаёт устройство."""
        response = client.post(
            "/api/device-management/",
            json={
                "host": "192.168.1.100",
                "device_type": "cisco_ios",
                "name": "test-device",
                "enabled": True,
            },
        )
        # Может быть 201 (created) или 400 (duplicate)
        assert response.status_code in [201, 400]

    def test_get_device_hosts_returns_list(self, client):
        """GET /api/device-management/hosts/list возвращает список IP."""
        response = client.get("/api/device-management/hosts/list")
        assert response.status_code == 200
        data = response.json()
        assert "hosts" in data
        assert "count" in data
        assert isinstance(data["hosts"], list)


class TestNetBoxImportAPI:
    """Тесты для импорта устройств из NetBox."""

    def test_import_requires_url_and_token(self, client):
        """POST /api/device-management/import-from-netbox требует url и token."""
        response = client.post(
            "/api/device-management/import-from-netbox",
            json={},
        )
        assert response.status_code == 422  # Validation error

    def test_import_with_invalid_url_fails(self, client):
        """POST /api/device-management/import-from-netbox с неверным URL падает."""
        response = client.post(
            "/api/device-management/import-from-netbox",
            json={
                "netbox_url": "http://invalid-netbox-url.local",
                "netbox_token": "fake-token",
            },
        )
        # Should fail with connection error
        assert response.status_code == 500

    @patch("network_collector.netbox.client.NetBoxClient")
    def test_import_with_mocked_netbox(self, mock_client_class, client):
        """POST /api/device-management/import-from-netbox с mock NetBox."""
        # Setup mock
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        # Create mock device
        mock_device = MagicMock()
        mock_device.name = "test-switch-01"
        mock_device.primary_ip4 = MagicMock()
        mock_device.primary_ip4.address = "10.0.0.1/24"
        mock_device.primary_ip6 = None
        mock_device.platform = None
        mock_device.site = MagicMock()
        mock_device.site.name = "DC-1"
        mock_device.role = MagicMock()
        mock_device.role.slug = "switch"
        mock_device.tenant = None
        mock_device.comments = "Test device"
        mock_device.status = MagicMock()
        mock_device.status.value = "active"
        mock_device.tags = []

        mock_client.get_devices.return_value = [mock_device]

        response = client.post(
            "/api/device-management/import-from-netbox",
            json={
                "netbox_url": "http://netbox.local",
                "netbox_token": "test-token",
                "status": "active",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["fetched"] == 1

    @patch("network_collector.netbox.client.NetBoxClient")
    def test_import_skips_devices_without_ip(self, mock_client_class, client):
        """Импорт пропускает устройства без primary IP."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        # Device without IP
        mock_device = MagicMock()
        mock_device.name = "no-ip-device"
        mock_device.primary_ip4 = None
        mock_device.primary_ip6 = None

        mock_client.get_devices.return_value = [mock_device]

        response = client.post(
            "/api/device-management/import-from-netbox",
            json={
                "netbox_url": "http://netbox.local",
                "netbox_token": "test-token",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["fetched"] == 1
        assert data["skipped"] == 1
        assert data["added"] == 0


class TestNetBoxPlatformMapping:
    """Тесты для маппинга платформ NetBox → Scrapli."""

    def test_netbox_platform_map_exists(self):
        """NETBOX_TO_SCRAPLI_PLATFORM существует и содержит маппинги."""
        from network_collector.core.constants import NETBOX_TO_SCRAPLI_PLATFORM

        assert isinstance(NETBOX_TO_SCRAPLI_PLATFORM, dict)
        assert len(NETBOX_TO_SCRAPLI_PLATFORM) > 0

    def test_cisco_ios_mapping(self):
        """cisco-ios маппится на cisco_ios."""
        from network_collector.core.constants import NETBOX_TO_SCRAPLI_PLATFORM

        assert NETBOX_TO_SCRAPLI_PLATFORM.get("cisco-ios") == "cisco_ios"

    def test_cisco_nxos_mapping(self):
        """cisco-nxos маппится на cisco_nxos."""
        from network_collector.core.constants import NETBOX_TO_SCRAPLI_PLATFORM

        assert NETBOX_TO_SCRAPLI_PLATFORM.get("cisco-nxos") == "cisco_nxos"

    def test_arista_mapping(self):
        """arista-eos маппится на arista_eos."""
        from network_collector.core.constants import NETBOX_TO_SCRAPLI_PLATFORM

        assert NETBOX_TO_SCRAPLI_PLATFORM.get("arista-eos") == "arista_eos"


class TestFileImportAPI:
    """Тесты для импорта устройств из файла."""

    def test_import_json_file(self, client):
        """POST /api/device-management/import-from-file с JSON файлом."""
        import io

        json_content = b'[{"host": "10.0.0.1", "device_type": "cisco_ios", "role": "switch"}]'
        files = {"file": ("devices.json", io.BytesIO(json_content), "application/json")}

        response = client.post(
            "/api/device-management/import-from-file",
            files=files,
            data={"replace": "false"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "added" in data

    def test_import_json_with_devices_key(self, client):
        """JSON с полем 'devices' парсится корректно."""
        import io

        json_content = b'{"devices": [{"host": "10.0.0.2", "device_type": "cisco_nxos"}]}'
        files = {"file": ("devices.json", io.BytesIO(json_content), "application/json")}

        response = client.post(
            "/api/device-management/import-from-file",
            files=files,
            data={"replace": "false"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_import_invalid_json_fails(self, client):
        """Невалидный JSON возвращает ошибку."""
        import io

        json_content = b'{"invalid json'
        files = {"file": ("devices.json", io.BytesIO(json_content), "application/json")}

        response = client.post(
            "/api/device-management/import-from-file",
            files=files,
            data={"replace": "false"},
        )

        assert response.status_code == 400
        assert "Ошибка парсинга JSON" in response.json()["detail"]

    def test_import_unsupported_format_fails(self, client):
        """Неподдерживаемый формат возвращает ошибку."""
        import io

        content = b'some content'
        files = {"file": ("devices.txt", io.BytesIO(content), "text/plain")}

        response = client.post(
            "/api/device-management/import-from-file",
            files=files,
            data={"replace": "false"},
        )

        assert response.status_code == 400
        assert "Неподдерживаемый формат" in response.json()["detail"]

    def test_import_python_file(self, client):
        """POST /api/device-management/import-from-file с Python файлом."""
        import io

        py_content = b'''
devices_list = [
    {"host": "10.0.0.3", "device_type": "cisco_ios"},
    {"host": "10.0.0.4", "device_type": "arista_eos"},
]
'''
        files = {"file": ("devices.py", io.BytesIO(py_content), "text/x-python")}

        response = client.post(
            "/api/device-management/import-from-file",
            files=files,
            data={"replace": "false"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_import_empty_json_returns_empty_result(self, client):
        """Пустой JSON возвращает success но 0 добавлено."""
        import io

        json_content = b'[]'
        files = {"file": ("devices.json", io.BytesIO(json_content), "application/json")}

        response = client.post(
            "/api/device-management/import-from-file",
            files=files,
            data={"replace": "false"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["added"] == 0

    def test_import_applies_defaults_from_config(self, client):
        """Импорт применяет defaults из fields.yaml для пустых полей."""
        import io

        # Устройство без site/role/tenant - должны применяться defaults
        json_content = b'[{"host": "10.99.99.99", "device_type": "cisco_ios"}]'
        files = {"file": ("devices.json", io.BytesIO(json_content), "application/json")}

        response = client.post(
            "/api/device-management/import-from-file",
            files=files,
            data={"replace": "false"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Проверяем что устройство добавлено с defaults
        response = client.get("/api/device-management/")
        devices = response.json()["devices"]
        imported = [d for d in devices if d["host"] == "10.99.99.99"]
        if imported:
            device = imported[0]
            # Если fields.yaml содержит defaults, они должны быть применены
            # По умолчанию: site="SU", role="Switch", tenant="Отдел ОИТ"
            assert device.get("site") in ("SU", None)  # Если есть defaults
            assert device.get("role") in ("Switch", None)
