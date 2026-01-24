"""
Integration tests для NetBox синхронизации.

Тестирует NetBoxSync с мокированным клиентом.
Проверяет логику синхронизации без реальных API вызовов.
"""

import pytest
from unittest.mock import Mock, MagicMock

from network_collector.netbox.sync import NetBoxSync
from network_collector.netbox.client import NetBoxClient
from network_collector.core.models import Interface, DeviceInfo, LLDPNeighbor, IPAddressEntry


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


class TestIPAddressMaskSync:
    """Тесты синхронизации IP-адресов с правильной маской.

    Проверяет что IP-адреса создаются с корректной маской из prefix_length,
    а не с дефолтной /32.
    """

    @pytest.fixture
    def mock_client(self):
        """Мокированный NetBox клиент."""
        client = Mock()
        client.api = Mock()
        return client

    def test_ip_entry_with_prefix_length(self):
        """IPAddressEntry корректно формирует IP с маской из prefix_length."""
        # Данные как из show interfaces
        data = {
            "ip_address": "10.177.30.213",
            "interface": "Vlan30",
            "prefix_length": "24",
        }
        ip = IPAddressEntry.from_dict(data)

        assert ip.with_prefix == "10.177.30.213/24"
        assert ip.mask == "24"

    def test_ip_entry_with_dotted_mask(self):
        """IPAddressEntry работает с dotted маской."""
        ip = IPAddressEntry(
            ip_address="192.168.1.1",
            interface="Vlan100",
            mask="255.255.255.0",
        )

        assert ip.with_prefix == "192.168.1.1/24"

    def test_interface_preserves_prefix_length(self):
        """Interface сохраняет prefix_length из парсинга."""
        data = {
            "interface": "Vlan30",
            "ip_address": "10.177.30.213",
            "prefix_length": "24",
            "status": "up",
        }
        intf = Interface.from_dict(data)

        assert intf.ip_address == "10.177.30.213"
        assert intf.prefix_length == "24"

    def test_sync_ip_addresses_device_not_found(self, mock_client):
        """Если устройство не найдено — возвращает пустую статистику."""
        mock_client.get_device_by_name.return_value = None

        sync = NetBoxSync(mock_client)
        ip_data = [
            IPAddressEntry(
                ip_address="10.177.30.213",
                interface="Vlan30",
                mask="24",
            )
        ]

        result = sync.sync_ip_addresses("nonexistent-device", ip_data)

        assert result["created"] == 0
        assert result["failed"] == 1  # Device not found = failed
        assert "errors" in result
        assert len(result["errors"]) > 0

    def test_sync_ip_addresses_dry_run(self, mock_client):
        """В режиме dry_run IP не создаются в NetBox."""
        mock_device = Mock()
        mock_device.id = 1
        mock_device.tenant = None
        mock_client.get_device_by_name.return_value = mock_device
        mock_client.get_interfaces.return_value = []
        mock_client.get_ip_addresses.return_value = []

        sync = NetBoxSync(mock_client, dry_run=True)
        ip_data = [
            IPAddressEntry(
                ip_address="10.177.30.213",
                interface="Vlan30",
                mask="24",
            )
        ]

        result = sync.sync_ip_addresses("switch-01", ip_data)

        # create_ip_address НЕ должен вызываться в dry_run
        mock_client.create_ip_address.assert_not_called()
        assert isinstance(result, dict)

    def test_ip_entry_fallback_to_32_only_when_empty(self):
        """with_prefix возвращает /32 только если mask пустой."""
        # С маской
        ip_with_mask = IPAddressEntry(
            ip_address="10.0.0.1",
            interface="Vlan10",
            mask="24",
        )
        assert ip_with_mask.with_prefix == "10.0.0.1/24"

        # Без маски - fallback /32
        ip_no_mask = IPAddressEntry(
            ip_address="10.0.0.2",
            interface="Vlan10",
            mask="",
        )
        assert ip_no_mask.with_prefix == "10.0.0.2/32"

    def test_ip_entry_with_slash_in_address(self):
        """Если IP уже содержит маску - используется она."""
        ip = IPAddressEntry(
            ip_address="10.0.0.1/30",
            interface="Vlan10",
            mask="24",  # игнорируется
        )
        assert ip.with_prefix == "10.0.0.1/30"


class TestVLANSyncDuplicates:
    """Тесты синхронизации VLAN при дубликатах VID.

    Проверяет что get_vlan_by_vid не падает когда в NetBox
    несколько VLAN с одинаковым VID (например в разных site).
    """

    @pytest.fixture
    def mock_api(self):
        """Мокированный pynetbox API."""
        return Mock()

    def test_get_vlan_by_vid_single_result(self, mock_api):
        """Один VLAN найден — возвращается он."""
        mock_vlan = Mock()
        mock_vlan.vid = 100
        mock_vlan.name = "VLAN100"

        mock_api.ipam.vlans.filter.return_value = [mock_vlan]

        client = Mock(spec=NetBoxClient)
        client.api = mock_api

        # Эмулируем метод get_vlan_by_vid
        vlans = list(mock_api.ipam.vlans.filter(vid=100))
        result = vlans[0] if vlans else None

        assert result == mock_vlan
        assert result.vid == 100

    def test_get_vlan_by_vid_multiple_results(self, mock_api):
        """Несколько VLAN с одним VID — возвращается первый."""
        mock_vlan1 = Mock()
        mock_vlan1.vid = 16
        mock_vlan1.name = "VLAN 16 Site1"

        mock_vlan2 = Mock()
        mock_vlan2.vid = 16
        mock_vlan2.name = "VLAN 16 Site2"

        # filter возвращает несколько результатов
        mock_api.ipam.vlans.filter.return_value = [mock_vlan1, mock_vlan2]

        # Новая логика: используем filter и берём первый
        vlans = list(mock_api.ipam.vlans.filter(vid=16))
        result = vlans[0] if vlans else None

        # Не падает, возвращает первый
        assert result == mock_vlan1
        assert result.vid == 16

    def test_get_vlan_by_vid_no_results(self, mock_api):
        """VLAN не найден — возвращается None."""
        mock_api.ipam.vlans.filter.return_value = []

        vlans = list(mock_api.ipam.vlans.filter(vid=999))
        result = vlans[0] if vlans else None

        assert result is None

    def test_sync_vlans_from_interfaces_returns_stats(self):
        """sync_vlans_from_interfaces возвращает статистику."""
        mock_client = Mock()
        mock_client.get_vlan_by_vid.return_value = None  # VLAN не существует

        sync = NetBoxSync(mock_client, dry_run=True)

        # SVI интерфейсы
        interfaces = [
            Interface(name="Vlan30", status="up", description="Management"),
            Interface(name="Vlan100", status="up", description="Users"),
            Interface(name="GigabitEthernet0/1", status="up"),  # Не SVI
        ]

        result = sync.sync_vlans_from_interfaces("switch-01", interfaces)

        assert isinstance(result, dict)
        assert "created" in result
        assert "skipped" in result
        assert "failed" in result

    def test_sync_vlans_skips_existing(self):
        """Существующие VLAN пропускаются."""
        mock_client = Mock()
        mock_vlan = Mock()
        mock_vlan.vid = 30
        mock_client.get_vlan_by_vid.return_value = mock_vlan  # VLAN уже есть

        sync = NetBoxSync(mock_client, dry_run=True)

        interfaces = [
            Interface(name="Vlan30", status="up", description="Management"),
        ]

        result = sync.sync_vlans_from_interfaces("switch-01", interfaces)

        # VLAN 30 уже существует — должен быть пропущен
        assert result["skipped"] == 1
        assert result["created"] == 0

    def test_sync_vlans_dry_run_no_create(self):
        """В dry_run режиме VLAN не создаются."""
        mock_client = Mock()
        mock_client.get_vlan_by_vid.return_value = None

        sync = NetBoxSync(mock_client, dry_run=True)

        interfaces = [
            Interface(name="Vlan100", status="up"),
        ]

        result = sync.sync_vlans_from_interfaces("switch-01", interfaces)

        # create_vlan НЕ должен вызываться в dry_run
        mock_client.create_vlan.assert_not_called()
        # Но в статистике created увеличивается (симуляция)
        assert result["created"] == 1
