"""
Тесты batch/bulk операций для оптимизации производительности.

Покрывает:
- Bulk методы в client (interfaces, inventory, ip_addresses)
- Batch операции в sync (interfaces, inventory, ip_addresses)
- Fallback на поштучные операции при ошибке batch
- Dry-run режим с batch
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, call
from dataclasses import dataclass
from typing import Optional

from network_collector.netbox.sync import NetBoxSync
from network_collector.core.models import Interface, InventoryItem, IPAddressEntry


# ==================== MOCK ОБЪЕКТЫ ====================

@dataclass
class MockInterface:
    """Мок модели Interface."""
    name: str = "Gi0/1"
    description: str = ""
    status: str = "up"
    mode: str = ""
    access_vlan: str = ""
    native_vlan: str = ""
    mac: str = ""
    mtu: int = 0
    speed: str = ""
    duplex: str = ""
    ip_address: str = ""
    lag: str = ""
    tagged_vlans: str = ""

    def to_dict(self):
        return {k: v for k, v in self.__dict__.items() if v}

    @classmethod
    def ensure_list(cls, items):
        if items and isinstance(items[0], dict):
            return [cls(**d) for d in items]
        return items


class MockNBInterface:
    """Мок NetBox интерфейса."""
    def __init__(self, id=1, name="Gi0/1", description="", enabled=True):
        self.id = id
        self.name = name
        self.description = description
        self.enabled = enabled
        self.mtu = None
        self.speed = None
        self.duplex = None
        self.type = None
        self.lag = None
        self.mode = None
        self.untagged_vlan = None
        self.tagged_vlans = []
        self.device = None

    def delete(self):
        pass


# ==================== ТЕСТЫ BULK CLIENT ====================

class TestBulkClientInterfaces:
    """Тесты bulk методов в client/interfaces.py."""

    def test_bulk_create_empty_list(self):
        """Пустой список — нет API вызовов."""
        client = Mock()
        # Симулируем InterfacesMixin
        from network_collector.netbox.client.interfaces import InterfacesMixin
        mixin = InterfacesMixin()
        mixin.api = Mock()

        result = mixin.bulk_create_interfaces([])
        assert result == []
        mixin.api.dcim.interfaces.create.assert_not_called()

    def test_bulk_update_empty_list(self):
        """Пустой список update — нет API вызовов."""
        from network_collector.netbox.client.interfaces import InterfacesMixin
        mixin = InterfacesMixin()
        mixin.api = Mock()

        result = mixin.bulk_update_interfaces([])
        assert result == []
        mixin.api.dcim.interfaces.update.assert_not_called()

    def test_bulk_delete_empty_list(self):
        """Пустой список delete — нет API вызовов, возвращает True."""
        from network_collector.netbox.client.interfaces import InterfacesMixin
        mixin = InterfacesMixin()
        mixin.api = Mock()

        result = mixin.bulk_delete_interfaces([])
        assert result is True
        mixin.api.dcim.interfaces.delete.assert_not_called()

    def test_bulk_create_returns_list(self):
        """bulk_create возвращает список созданных объектов."""
        from network_collector.netbox.client.interfaces import InterfacesMixin
        mixin = InterfacesMixin()
        mixin.api = Mock()

        mock_results = [Mock(id=1), Mock(id=2)]
        mixin.api.dcim.interfaces.create.return_value = mock_results

        data = [{"device": 1, "name": "Gi0/1"}, {"device": 1, "name": "Gi0/2"}]
        result = mixin.bulk_create_interfaces(data)

        assert len(result) == 2
        mixin.api.dcim.interfaces.create.assert_called_once_with(data)

    def test_bulk_create_single_result_wrapped_in_list(self):
        """Если API вернул один объект — оборачиваем в список."""
        from network_collector.netbox.client.interfaces import InterfacesMixin
        mixin = InterfacesMixin()
        mixin.api = Mock()

        mock_result = Mock(id=1)
        mixin.api.dcim.interfaces.create.return_value = mock_result

        result = mixin.bulk_create_interfaces([{"device": 1, "name": "Gi0/1"}])
        assert len(result) == 1
        assert result[0].id == 1

    def test_bulk_update_sends_list_with_ids(self):
        """bulk_update отправляет список словарей с id."""
        from network_collector.netbox.client.interfaces import InterfacesMixin
        mixin = InterfacesMixin()
        mixin.api = Mock()

        mock_results = [Mock(id=1), Mock(id=2)]
        mixin.api.dcim.interfaces.update.return_value = mock_results

        updates = [
            {"id": 1, "description": "upd1"},
            {"id": 2, "description": "upd2"},
        ]
        result = mixin.bulk_update_interfaces(updates)

        assert len(result) == 2
        mixin.api.dcim.interfaces.update.assert_called_once_with(updates)

    def test_bulk_delete_sends_id_list(self):
        """bulk_delete передаёт список int ID в pynetbox."""
        from network_collector.netbox.client.interfaces import InterfacesMixin
        mixin = InterfacesMixin()
        mixin.api = Mock()

        result = mixin.bulk_delete_interfaces([10, 20, 30])

        assert result is True
        mixin.api.dcim.interfaces.delete.assert_called_once_with(
            [10, 20, 30]
        )


class TestBulkClientInventory:
    """Тесты bulk методов в client/inventory.py."""

    def test_bulk_create_empty(self):
        """Пустой список — нет API вызовов."""
        from network_collector.netbox.client.inventory import InventoryMixin
        mixin = InventoryMixin()
        mixin.api = Mock()

        assert mixin.bulk_create_inventory_items([]) == []

    def test_bulk_create_returns_list(self):
        """Bulk create возвращает список."""
        from network_collector.netbox.client.inventory import InventoryMixin
        mixin = InventoryMixin()
        mixin.api = Mock()

        mock_results = [Mock(id=1)]
        mixin.api.dcim.inventory_items.create.return_value = mock_results

        result = mixin.bulk_create_inventory_items([{"device": 1, "name": "PSU"}])
        assert len(result) == 1

    def test_bulk_delete_empty(self):
        """Пустой список delete — True."""
        from network_collector.netbox.client.inventory import InventoryMixin
        mixin = InventoryMixin()
        mixin.api = Mock()

        assert mixin.bulk_delete_inventory_items([]) is True


class TestBulkClientIPAddresses:
    """Тесты bulk методов в client/ip_addresses.py."""

    def test_bulk_create_empty(self):
        """Пустой список — нет API вызовов."""
        from network_collector.netbox.client.ip_addresses import IPAddressesMixin
        mixin = IPAddressesMixin()
        mixin.api = Mock()

        assert mixin.bulk_create_ip_addresses([]) == []

    def test_bulk_create_returns_list(self):
        """Bulk create возвращает список."""
        from network_collector.netbox.client.ip_addresses import IPAddressesMixin
        mixin = IPAddressesMixin()
        mixin.api = Mock()

        mock_results = [Mock(id=1)]
        mixin.api.ipam.ip_addresses.create.return_value = mock_results

        result = mixin.bulk_create_ip_addresses([{"address": "10.0.0.1/24"}])
        assert len(result) == 1

    def test_bulk_delete_empty(self):
        """Пустой список delete — True."""
        from network_collector.netbox.client.ip_addresses import IPAddressesMixin
        mixin = IPAddressesMixin()
        mixin.api = Mock()

        assert mixin.bulk_delete_ip_addresses([]) is True


# ==================== ТЕСТЫ BATCH SYNC INTERFACES ====================

class TestBatchSyncInterfaces:
    """Тесты batch операций в sync_interfaces."""

    @pytest.fixture
    def mock_client(self):
        """Мокированный NetBox клиент."""
        client = Mock()
        mock_device = Mock()
        mock_device.id = 1
        mock_device.name = "switch-01"
        client.get_device_by_name.return_value = mock_device
        client.get_interfaces.return_value = []
        client.bulk_create_interfaces.return_value = []
        client.bulk_update_interfaces.return_value = []
        client.bulk_delete_interfaces.return_value = True
        return client

    @pytest.fixture
    def sample_interfaces(self):
        """Тестовые интерфейсы."""
        return [
            Interface(name="GigabitEthernet0/1", description="Server 1", status="up"),
            Interface(name="GigabitEthernet0/2", description="Server 2", status="up"),
            Interface(name="GigabitEthernet0/3", description="Server 3", status="down"),
        ]

    @patch("network_collector.netbox.sync.interfaces.get_sync_config")
    def test_batch_create_uses_bulk_api(self, mock_sync_cfg, mock_client, sample_interfaces):
        """При создании интерфейсов используется bulk_create_interfaces."""
        # Настраиваем мок sync config
        cfg = MagicMock()
        cfg.get_option.side_effect = lambda key, default=None: {
            "create_missing": True,
            "update_existing": True,
            "exclude_interfaces": [],
            "auto_detect_type": True,
            "enabled_mode": "admin",
            "sync_vlans": False,
        }.get(key, default)
        cfg.is_field_enabled.return_value = True
        mock_sync_cfg.return_value = cfg

        # Мок bulk_create возвращает созданные объекты
        created = [Mock(id=i + 1) for i in range(3)]
        mock_client.bulk_create_interfaces.return_value = created

        sync = NetBoxSync(mock_client)
        result = sync.sync_interfaces("switch-01", sample_interfaces)

        # Проверяем что bulk_create был вызван
        mock_client.bulk_create_interfaces.assert_called_once()
        assert result["created"] == 3

    @patch("network_collector.netbox.sync.interfaces.get_sync_config")
    def test_batch_create_dry_run(self, mock_sync_cfg, mock_client, sample_interfaces):
        """В dry_run bulk_create НЕ вызывается."""
        cfg = MagicMock()
        cfg.get_option.side_effect = lambda key, default=None: {
            "create_missing": True,
            "update_existing": True,
            "exclude_interfaces": [],
            "auto_detect_type": True,
            "enabled_mode": "admin",
            "sync_vlans": False,
        }.get(key, default)
        cfg.is_field_enabled.return_value = True
        mock_sync_cfg.return_value = cfg

        sync = NetBoxSync(mock_client, dry_run=True)
        result = sync.sync_interfaces("switch-01", sample_interfaces)

        # Bulk create НЕ должен вызываться в dry_run
        mock_client.bulk_create_interfaces.assert_not_called()
        assert result["created"] == 3

    @patch("network_collector.netbox.sync.interfaces.get_sync_config")
    def test_batch_create_fallback_on_error(self, mock_sync_cfg, mock_client, sample_interfaces):
        """При ошибке bulk_create — fallback на поштучное создание."""
        cfg = MagicMock()
        cfg.get_option.side_effect = lambda key, default=None: {
            "create_missing": True,
            "update_existing": True,
            "exclude_interfaces": [],
            "auto_detect_type": True,
            "enabled_mode": "admin",
            "sync_vlans": False,
        }.get(key, default)
        cfg.is_field_enabled.return_value = True
        mock_sync_cfg.return_value = cfg

        # bulk_create падает
        mock_client.bulk_create_interfaces.side_effect = Exception("API error")
        # Поштучный create работает
        mock_client.create_interface.return_value = Mock(id=1)

        sync = NetBoxSync(mock_client)
        result = sync.sync_interfaces("switch-01", sample_interfaces)

        # Должен был попытаться bulk, потом fallback
        mock_client.bulk_create_interfaces.assert_called_once()
        # Поштучные вызовы create_interface
        assert mock_client.create_interface.call_count == 3
        assert result["created"] == 3

    @patch("network_collector.netbox.sync.interfaces.get_sync_config")
    def test_batch_delete_uses_bulk_api(self, mock_sync_cfg, mock_client):
        """При удалении интерфейсов используется bulk_delete_interfaces."""
        cfg = MagicMock()
        cfg.get_option.side_effect = lambda key, default=None: {
            "create_missing": True,
            "update_existing": True,
            "exclude_interfaces": [],
            "auto_detect_type": True,
            "enabled_mode": "admin",
            "sync_vlans": False,
        }.get(key, default)
        cfg.is_field_enabled.return_value = True
        mock_sync_cfg.return_value = cfg

        # В NetBox есть интерфейсы которых нет локально
        nb_intf1 = MockNBInterface(id=10, name="Gi0/10")
        nb_intf2 = MockNBInterface(id=11, name="Gi0/11")
        mock_client.get_interfaces.return_value = [nb_intf1, nb_intf2]

        sync = NetBoxSync(mock_client)
        # Пустой список = все в NetBox лишние при cleanup=True
        result = sync.sync_interfaces("switch-01", [], cleanup=True)

        # Проверяем что bulk_delete был вызван
        mock_client.bulk_delete_interfaces.assert_called_once_with([10, 11])
        assert result["deleted"] == 2

    @patch("network_collector.netbox.sync.interfaces.get_sync_config")
    def test_batch_delete_fallback_on_error(self, mock_sync_cfg, mock_client):
        """При ошибке bulk_delete — fallback на поштучное удаление."""
        cfg = MagicMock()
        cfg.get_option.side_effect = lambda key, default=None: {
            "create_missing": True,
            "update_existing": True,
            "exclude_interfaces": [],
            "auto_detect_type": True,
            "enabled_mode": "admin",
            "sync_vlans": False,
        }.get(key, default)
        cfg.is_field_enabled.return_value = True
        mock_sync_cfg.return_value = cfg

        nb_intf = MockNBInterface(id=10, name="Gi0/10")
        mock_client.get_interfaces.return_value = [nb_intf]
        mock_client.bulk_delete_interfaces.side_effect = Exception("API error")

        sync = NetBoxSync(mock_client)
        result = sync.sync_interfaces("switch-01", [], cleanup=True)

        # bulk_delete вызван, потом fallback поштучно
        mock_client.bulk_delete_interfaces.assert_called_once()
        assert result["deleted"] == 1

    @patch("network_collector.netbox.sync.interfaces.get_sync_config")
    def test_batch_update_uses_bulk_api(self, mock_sync_cfg, mock_client):
        """При обновлении интерфейсов используется bulk_update_interfaces."""
        cfg = MagicMock()
        cfg.get_option.side_effect = lambda key, default=None: {
            "create_missing": True,
            "update_existing": True,
            "exclude_interfaces": [],
            "auto_detect_type": False,
            "enabled_mode": "admin",
            "sync_vlans": False,
        }.get(key, default)
        cfg.is_field_enabled.side_effect = lambda field: field in ["description", "enabled"]
        mock_sync_cfg.return_value = cfg

        # Интерфейс в NetBox с другим description
        nb_intf = MockNBInterface(id=10, name="GigabitEthernet0/1", description="old")
        mock_client.get_interfaces.return_value = [nb_intf]

        # Локальный с новым description
        interfaces = [Interface(name="GigabitEthernet0/1", description="new", status="up")]

        mock_client.bulk_update_interfaces.return_value = [Mock()]

        sync = NetBoxSync(mock_client)
        result = sync.sync_interfaces("switch-01", interfaces)

        # Проверяем что bulk_update был вызван
        mock_client.bulk_update_interfaces.assert_called_once()
        call_args = mock_client.bulk_update_interfaces.call_args[0][0]
        assert len(call_args) == 1
        assert call_args[0]["id"] == 10
        assert call_args[0]["description"] == "new"
        assert result["updated"] == 1


# ==================== ТЕСТЫ BATCH SYNC INVENTORY ====================

class TestBatchSyncInventory:
    """Тесты batch операций в sync_inventory."""

    @pytest.fixture
    def mock_client(self):
        """Мокированный NetBox клиент."""
        client = Mock()
        mock_device = Mock()
        mock_device.id = 1
        mock_device.name = "switch-01"
        client.get_device_by_name.return_value = mock_device
        client.get_inventory_items.return_value = []
        client.get_inventory_item.return_value = None
        client.bulk_create_inventory_items.return_value = []
        client.bulk_update_inventory_items.return_value = []
        client.bulk_delete_inventory_items.return_value = True
        return client

    def test_batch_create_inventory(self, mock_client):
        """Создание inventory использует bulk API."""
        items = [
            InventoryItem(name="PSU 1", pid="PWR-123", serial="S001"),
            InventoryItem(name="PSU 2", pid="PWR-456", serial="S002"),
        ]

        sync = NetBoxSync(mock_client)
        result = sync.sync_inventory("switch-01", items)

        mock_client.bulk_create_inventory_items.assert_called_once()
        assert result["created"] == 2

    def test_batch_create_inventory_dry_run(self, mock_client):
        """В dry_run bulk create НЕ вызывается."""
        items = [
            InventoryItem(name="PSU 1", pid="PWR-123", serial="S001"),
        ]

        sync = NetBoxSync(mock_client, dry_run=True)
        result = sync.sync_inventory("switch-01", items)

        mock_client.bulk_create_inventory_items.assert_not_called()
        assert result["created"] == 1

    def test_batch_create_inventory_fallback(self, mock_client):
        """При ошибке bulk create — fallback на поштучное создание."""
        items = [
            InventoryItem(name="PSU 1", pid="PWR-123", serial="S001"),
        ]

        mock_client.bulk_create_inventory_items.side_effect = Exception("API error")

        sync = NetBoxSync(mock_client)
        result = sync.sync_inventory("switch-01", items)

        # Fallback использует api.dcim.inventory_items.create напрямую
        mock_client.api.dcim.inventory_items.create.assert_called_once()
        assert result["created"] == 1

    def test_batch_update_inventory(self, mock_client):
        """Обновление inventory использует bulk API."""
        # Существующий item с другим serial
        existing = Mock()
        existing.id = 10
        existing.name = "PSU 1"
        existing.part_id = "PWR-123"
        existing.serial = "OLD"
        existing.description = ""
        existing.manufacturer = None
        # Pre-fetch: get_inventory_items возвращает все items устройства
        mock_client.get_inventory_items.return_value = [existing]

        items = [
            InventoryItem(name="PSU 1", pid="PWR-123", serial="NEW"),
        ]

        sync = NetBoxSync(mock_client)
        result = sync.sync_inventory("switch-01", items)

        mock_client.bulk_update_inventory_items.assert_called_once()
        call_args = mock_client.bulk_update_inventory_items.call_args[0][0]
        assert call_args[0]["id"] == 10
        assert call_args[0]["serial"] == "NEW"
        assert result["updated"] == 1

    def test_batch_delete_inventory_cleanup(self, mock_client):
        """Cleanup использует bulk delete."""
        old_item = Mock()
        old_item.name = "Old Module"
        old_item.id = 99
        mock_client.get_inventory_items.return_value = [old_item]

        sync = NetBoxSync(mock_client)
        result = sync.sync_inventory("switch-01", [], cleanup=True)

        mock_client.bulk_delete_inventory_items.assert_called_once_with([99])
        assert result["deleted"] == 1


# ==================== ТЕСТЫ BATCH SYNC IP ====================

class TestBatchSyncIPAddresses:
    """Тесты batch операций в sync_ip_addresses."""

    @pytest.fixture
    def mock_client(self):
        """Мокированный NetBox клиент."""
        client = Mock()
        mock_device = Mock()
        mock_device.id = 1
        mock_device.name = "switch-01"
        mock_device.tenant = None
        mock_device.primary_ip4 = None
        client.get_device_by_name.return_value = mock_device

        # Интерфейсы
        mock_intf = Mock()
        mock_intf.name = "Vlan100"
        mock_intf.id = 100
        mock_intf.description = ""
        client.get_interfaces.return_value = [mock_intf]

        client.get_ip_addresses.return_value = []
        client.bulk_create_ip_addresses.return_value = []
        client.bulk_delete_ip_addresses.return_value = True
        return client

    def test_batch_create_ip(self, mock_client):
        """Создание IP использует bulk API."""
        entries = [
            IPAddressEntry(
                ip_address="10.0.0.1",
                mask="24",
                interface="Vlan100",
            ),
        ]

        sync = NetBoxSync(mock_client)
        result = sync.sync_ip_addresses("switch-01", entries)

        mock_client.bulk_create_ip_addresses.assert_called_once()
        assert result["created"] == 1

    def test_batch_create_ip_dry_run(self, mock_client):
        """В dry_run bulk create IP НЕ вызывается."""
        entries = [
            IPAddressEntry(
                ip_address="10.0.0.1",
                mask="24",
                interface="Vlan100",
            ),
        ]

        sync = NetBoxSync(mock_client, dry_run=True)
        result = sync.sync_ip_addresses("switch-01", entries)

        mock_client.bulk_create_ip_addresses.assert_not_called()
        assert result["created"] == 1

    def test_batch_create_ip_fallback(self, mock_client):
        """При ошибке bulk create IP — fallback."""
        entries = [
            IPAddressEntry(
                ip_address="10.0.0.1",
                mask="24",
                interface="Vlan100",
            ),
        ]

        mock_client.bulk_create_ip_addresses.side_effect = Exception("API error")

        sync = NetBoxSync(mock_client)
        result = sync.sync_ip_addresses("switch-01", entries)

        mock_client.api.ipam.ip_addresses.create.assert_called_once()
        assert result["created"] == 1

    def test_batch_delete_ip(self, mock_client):
        """Удаление IP использует bulk API."""
        # IP в NetBox которого нет локально
        old_ip = Mock()
        old_ip.id = 50
        old_ip.address = "192.168.1.1/24"
        old_ip.assigned_object = Mock()
        old_ip.assigned_object_id = 100
        old_ip.assigned_object_type = "dcim.interface"
        mock_client.get_ip_addresses.return_value = [old_ip]

        sync = NetBoxSync(mock_client)
        result = sync.sync_ip_addresses("switch-01", [], cleanup=True)

        mock_client.bulk_delete_ip_addresses.assert_called_once_with([50])
        assert result["deleted"] == 1


# ==================== ТЕСТЫ BUILD DATA ====================

class TestBuildCreateData:
    """Тесты _build_create_data для интерфейсов."""

    @patch("network_collector.netbox.sync.interfaces.get_sync_config")
    @patch("network_collector.netbox.sync.interfaces.get_netbox_interface_type")
    def test_build_create_data_basic(self, mock_get_type, mock_sync_cfg):
        """Базовый тест подготовки данных для создания."""
        mock_get_type.return_value = "1000base-t"
        cfg = MagicMock()
        cfg.is_field_enabled.return_value = True
        cfg.get_option.return_value = False
        mock_sync_cfg.return_value = cfg

        client = Mock()
        sync = NetBoxSync(client)

        intf = Interface(name="Gi0/1", description="Server", status="up")
        data, mac = sync._build_create_data(1, intf)

        assert data["device"] == 1
        assert data["name"] == "Gi0/1"
        assert data["type"] == "1000base-t"
        assert data["description"] == "Server"
        assert data["enabled"] is True
        assert mac is None

    @patch("network_collector.netbox.sync.interfaces.get_sync_config")
    @patch("network_collector.netbox.sync.interfaces.get_netbox_interface_type")
    def test_build_create_data_with_mac(self, mock_get_type, mock_sync_cfg):
        """Если MAC указан — возвращается отдельно."""
        mock_get_type.return_value = "1000base-t"
        cfg = MagicMock()
        cfg.is_field_enabled.return_value = True
        cfg.get_option.return_value = False
        mock_sync_cfg.return_value = cfg

        client = Mock()
        sync = NetBoxSync(client)

        intf = Interface(name="Gi0/1", description="", status="up", mac="00:11:22:33:44:55")
        data, mac = sync._build_create_data(1, intf)

        assert mac is not None
        # MAC не в data, а отдельно для post-create
        assert "mac_address" not in data


class TestBuildUpdateData:
    """Тесты _build_update_data для интерфейсов."""

    @patch("network_collector.netbox.sync.interfaces.get_sync_config")
    @patch("network_collector.netbox.sync.interfaces.get_netbox_interface_type")
    def test_build_update_data_no_changes(self, mock_get_type, mock_sync_cfg):
        """Если нет изменений — пустой dict."""
        mock_get_type.return_value = "1000base-t"
        cfg = MagicMock()
        cfg.is_field_enabled.side_effect = lambda f: f in ["description", "enabled"]
        cfg.get_option.side_effect = lambda key, default=None: {
            "auto_detect_type": False,
            "enabled_mode": "admin",
            "sync_vlans": False,
        }.get(key, default)
        mock_sync_cfg.return_value = cfg

        client = Mock()
        sync = NetBoxSync(client, dry_run=True)

        nb_intf = MockNBInterface(name="Gi0/1", description="same")
        intf = Interface(name="Gi0/1", description="same", status="up")

        updates, changes, mac = sync._build_update_data(nb_intf, intf)

        assert updates == {}
        assert changes == []
        assert mac is None

    @patch("network_collector.netbox.sync.interfaces.get_sync_config")
    @patch("network_collector.netbox.sync.interfaces.get_netbox_interface_type")
    def test_build_update_data_description_changed(self, mock_get_type, mock_sync_cfg):
        """При изменении description — возвращает updates."""
        mock_get_type.return_value = "1000base-t"
        cfg = MagicMock()
        cfg.is_field_enabled.side_effect = lambda f: f in ["description", "enabled"]
        cfg.get_option.side_effect = lambda key, default=None: {
            "auto_detect_type": False,
            "enabled_mode": "admin",
            "sync_vlans": False,
        }.get(key, default)
        mock_sync_cfg.return_value = cfg

        client = Mock()
        sync = NetBoxSync(client, dry_run=True)

        nb_intf = MockNBInterface(name="Gi0/1", description="old")
        intf = Interface(name="Gi0/1", description="new", status="up")

        updates, changes, mac = sync._build_update_data(nb_intf, intf)

        assert "description" in updates
        assert updates["description"] == "new"
        assert len(changes) > 0


# ==================== ТЕСТЫ КЭШИРОВАНИЯ ИНТЕРФЕЙСОВ ====================

class TestInterfaceCache:
    """Тесты кэширования _find_interface."""

    def test_find_interface_caches_by_device_id(self):
        """get_interfaces вызывается только 1 раз для одного device_id."""
        client = Mock()
        nb_intf1 = Mock()
        nb_intf1.name = "GigabitEthernet0/1"
        nb_intf2 = Mock()
        nb_intf2.name = "GigabitEthernet0/2"
        client.get_interfaces.return_value = [nb_intf1, nb_intf2]

        sync = NetBoxSync(client, dry_run=True)

        # Первый вызов — загружает из API
        result1 = sync._find_interface(100, "GigabitEthernet0/1")
        assert result1 == nb_intf1

        # Второй вызов с тем же device_id — из кэша
        result2 = sync._find_interface(100, "GigabitEthernet0/2")
        assert result2 == nb_intf2

        # API вызван только 1 раз
        client.get_interfaces.assert_called_once_with(device_id=100)

    def test_find_interface_different_devices(self):
        """Разные device_id — отдельные API-вызовы."""
        client = Mock()

        intf_a = Mock()
        intf_a.name = "Gi0/1"
        intf_b = Mock()
        intf_b.name = "Gi0/1"

        client.get_interfaces.side_effect = [
            [intf_a],  # device 100
            [intf_b],  # device 200
        ]

        sync = NetBoxSync(client, dry_run=True)

        result1 = sync._find_interface(100, "Gi0/1")
        result2 = sync._find_interface(200, "Gi0/1")

        assert result1 == intf_a
        assert result2 == intf_b
        assert client.get_interfaces.call_count == 2

    def test_find_interface_normalized_name(self):
        """Нормализация имён работает из кэша."""
        client = Mock()
        nb_intf = Mock()
        nb_intf.name = "GigabitEthernet0/1"
        client.get_interfaces.return_value = [nb_intf]

        sync = NetBoxSync(client, dry_run=True)

        # Ищем по короткому имени — должен найти через нормализацию
        result = sync._find_interface(100, "Gi0/1")
        assert result == nb_intf
        client.get_interfaces.assert_called_once()

    def test_find_interface_not_found(self):
        """Если интерфейс не найден — возвращает None."""
        client = Mock()
        nb_intf = Mock()
        nb_intf.name = "GigabitEthernet0/1"
        client.get_interfaces.return_value = [nb_intf]

        sync = NetBoxSync(client, dry_run=True)

        result = sync._find_interface(100, "TenGigabitEthernet1/0/1")
        assert result is None
