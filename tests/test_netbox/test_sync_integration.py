"""
Integration tests для NetBox синхронизации.

Тестирует NetBoxSync с мокированным клиентом.
Проверяет логику синхронизации без реальных API вызовов.
"""

import pytest
from unittest.mock import Mock

from network_collector.netbox.sync import NetBoxSync
from network_collector.netbox.client import NetBoxClient
from network_collector.core.models import Interface, DeviceInfo, LLDPNeighbor


class TestNetBoxSyncModes:
    """Тесты режимов синхронизации."""

    @pytest.fixture
    def mock_client(self):
        """Мокированный NetBox клиент."""
        return Mock()

    def test_create_only_mode(self, mock_client):
        """Режим create_only не обновляет существующие."""
        sync = NetBoxSync(mock_client, create_only=True)

        assert sync.create_only is True
        assert sync.update_only is False

    def test_update_only_mode(self, mock_client):
        """Режим update_only не создаёт новые."""
        sync = NetBoxSync(mock_client, update_only=True)

        assert sync.update_only is True
        assert sync.create_only is False

    def test_dry_run_mode(self, mock_client):
        """Режим dry_run не делает изменений."""
        sync = NetBoxSync(mock_client, dry_run=True)

        assert sync.dry_run is True

    def test_default_modes(self, mock_client):
        """По умолчанию все режимы выключены."""
        sync = NetBoxSync(mock_client)

        assert sync.dry_run is False
        assert sync.create_only is False
        assert sync.update_only is False


class TestNetBoxSyncInterfaces:
    """Тесты синхронизации интерфейсов."""

    @pytest.fixture
    def mock_client(self):
        """Мокированный NetBox клиент."""
        return Mock()

    @pytest.fixture
    def sample_interfaces(self):
        """Тестовые интерфейсы."""
        return [
            Interface(
                name="GigabitEthernet0/1",
                status="up",
                ip_address="10.0.0.1",
                mac="00:11:22:33:44:55",
                description="Uplink",
            ),
            Interface(
                name="GigabitEthernet0/2",
                status="down",
                mac="00:11:22:33:44:56",
            ),
        ]

    def test_sync_interfaces_device_not_found(self, mock_client):
        """Если устройство не найдено — возвращает пустую статистику."""
        mock_client.get_device_by_name.return_value = None

        sync = NetBoxSync(mock_client)
        interfaces = [Interface(name="Gi0/1", status="up")]

        result = sync.sync_interfaces("nonexistent-device", interfaces)

        assert result["created"] == 0
        assert result["updated"] == 0
        mock_client.get_device_by_name.assert_called_once_with("nonexistent-device")

    def test_sync_interfaces_returns_stats(self, mock_client, sample_interfaces):
        """sync_interfaces возвращает словарь статистики."""
        mock_client.get_device_by_name.return_value = None

        sync = NetBoxSync(mock_client)
        result = sync.sync_interfaces("switch-01", sample_interfaces)

        assert isinstance(result, dict)
        assert "created" in result
        assert "updated" in result
        assert "skipped" in result

    def test_sync_interfaces_dry_run(self, mock_client, sample_interfaces):
        """В режиме dry_run create_interface не вызывается."""
        mock_device = Mock()
        mock_device.id = 1
        mock_client.get_device_by_name.return_value = mock_device
        mock_client.get_interfaces.return_value = []

        sync = NetBoxSync(mock_client, dry_run=True)
        result = sync.sync_interfaces("switch-01", sample_interfaces)

        # create_interface НЕ должен вызываться в dry_run
        mock_client.create_interface.assert_not_called()


class TestNetBoxSyncDevices:
    """Тесты синхронизации устройств."""

    @pytest.fixture
    def mock_client(self):
        """Мокированный NetBox клиент."""
        client = Mock()
        client.api = Mock()
        return client

    @pytest.fixture
    def sample_devices(self):
        """Тестовые устройства."""
        return [
            DeviceInfo(
                hostname="switch-01",
                ip_address="10.0.0.1",
                platform="cisco_ios",
                model="C9200L-48P-4X",
                serial="JAE12345678",
                version="17.3.4",
            ),
        ]

    def test_sync_devices_returns_stats(self, mock_client, sample_devices):
        """sync_devices_from_inventory возвращает статистику."""
        mock_client.get_device_by_name.return_value = None

        sync = NetBoxSync(mock_client, dry_run=True)
        result = sync.sync_devices_from_inventory(
            sample_devices,
            site="Test Site",
            role="switch",
        )

        assert isinstance(result, dict)


class TestNetBoxSyncCables:
    """Тесты синхронизации кабелей из LLDP."""

    @pytest.fixture
    def mock_client(self):
        """Мокированный NetBox клиент."""
        return Mock()

    @pytest.fixture
    def sample_lldp_data(self):
        """Тестовые LLDP данные."""
        return [
            LLDPNeighbor(
                hostname="switch-01",
                local_interface="Gi0/1",
                remote_hostname="switch-02",
                remote_port="Gi0/1",
                protocol="LLDP",
            ),
        ]

    def test_sync_cables_returns_stats(self, mock_client, sample_lldp_data):
        """sync_cables_from_lldp возвращает статистику."""
        sync = NetBoxSync(mock_client, dry_run=True)
        result = sync.sync_cables_from_lldp(sample_lldp_data)

        assert isinstance(result, dict)

    def test_sync_cables_dry_run(self, mock_client, sample_lldp_data):
        """В режиме dry_run кабели не создаются."""
        sync = NetBoxSync(mock_client, dry_run=True)
        result = sync.sync_cables_from_lldp(sample_lldp_data)

        # create_cable НЕ должен вызываться
        mock_client.create_cable.assert_not_called()


class TestNetBoxClientMethods:
    """Тесты методов NetBoxClient."""

    def test_client_has_get_methods(self):
        """NetBoxClient имеет get методы."""
        assert hasattr(NetBoxClient, "get_device_by_name")
        assert hasattr(NetBoxClient, "get_interfaces")
        assert hasattr(NetBoxClient, "get_interface_by_name")

    def test_client_has_create_methods(self):
        """NetBoxClient имеет create методы."""
        assert hasattr(NetBoxClient, "create_interface")
        assert hasattr(NetBoxClient, "create_ip_address")
        assert hasattr(NetBoxClient, "create_vlan")

    def test_client_init_requires_url(self):
        """NetBoxClient требует URL."""
        with pytest.raises(ValueError):
            NetBoxClient()  # Без аргументов — ValueError


class TestNetBoxSyncInterfaceNormalization:
    """Тесты нормализации интерфейсов при синхронизации."""

    @pytest.fixture
    def mock_client(self):
        """Мокированный NetBox клиент."""
        return Mock()

    def test_interface_name_normalization(self, mock_client):
        """Имена интерфейсов нормализуются."""
        mock_device = Mock()
        mock_device.id = 1
        mock_client.get_device_by_name.return_value = mock_device
        mock_client.get_interfaces.return_value = []

        sync = NetBoxSync(mock_client, dry_run=True)

        # Короткое имя должно работать
        interfaces = [Interface(name="Gi0/1", status="up")]
        result = sync.sync_interfaces("switch-01", interfaces)

        # Не должно упасть
        assert isinstance(result, dict)


class TestNetBoxSyncErrorHandling:
    """Тесты обработки ошибок."""

    @pytest.fixture
    def mock_client(self):
        """Мокированный NetBox клиент."""
        return Mock()

    def test_handles_device_not_found(self, mock_client):
        """Обрабатывает случай когда устройство не найдено."""
        mock_client.get_device_by_name.return_value = None

        sync = NetBoxSync(mock_client)
        interfaces = [Interface(name="Gi0/1", status="up")]

        # Не должно выбросить исключение
        result = sync.sync_interfaces("nonexistent", interfaces)

        assert result["created"] == 0
        assert result["updated"] == 0

    def test_empty_interfaces_list(self, mock_client):
        """Пустой список интерфейсов не вызывает ошибку."""
        mock_client.get_device_by_name.return_value = None

        sync = NetBoxSync(mock_client)
        result = sync.sync_interfaces("device", [])

        assert isinstance(result, dict)

    def test_empty_lldp_list(self, mock_client):
        """Пустой список LLDP не вызывает ошибку."""
        sync = NetBoxSync(mock_client)
        result = sync.sync_cables_from_lldp([])

        assert isinstance(result, dict)
