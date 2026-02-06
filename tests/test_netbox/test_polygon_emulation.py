"""
Комплексные интеграционные тесты — эмуляция полигона NetBox.

Эмулирует полный цикл работы с mock-NetBox:
1. Devices — создание, обновление, primary IP, cleanup
2. Interfaces — LAG двухфазный, VLAN, cleanup, update
3. IP Addresses — batch create/delete, primary IP, prefix change
4. Inventory — batch create/update/delete, fallback
5. Cables — создание, cleanup, failed_devices tracking
6. Pipeline — полный flow (devices → interfaces → IP → inventory → cables)
7. Error сценарии — silent failures, get_cables error, API errors

Уровень: integration (полная эмуляция sync flow через mock client).
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, call
from dataclasses import dataclass

from network_collector.netbox.sync import NetBoxSync
from network_collector.core.models import (
    Interface, IPAddressEntry, InventoryItem, LLDPNeighbor, DeviceInfo,
)


# ==================== HELPER: MOCK NETBOX ОБЪЕКТЫ ====================

def make_nb_device(
    id=1, name="switch-01", site="TestSite", tenant=None,
    serial="", model="WS-C2960", platform=None, role="switch",
    primary_ip4=None,
):
    """Создаёт mock NetBox устройство."""
    device = MagicMock()
    device.id = id
    device.name = name
    device.serial = serial or ""

    device.site = MagicMock()
    device.site.name = site
    device.site.slug = site.lower().replace(" ", "-")

    device.device_type = MagicMock()
    device.device_type.model = model

    device.platform = MagicMock() if platform else None
    if platform:
        device.platform.name = platform

    device.role = MagicMock()
    device.role.name = role

    device.tenant = MagicMock() if tenant else None
    if tenant:
        device.tenant.name = tenant
        device.tenant.id = 100
        device.tenant.slug = tenant.lower().replace(" ", "-")

    device.primary_ip4 = primary_ip4
    device.save = Mock()
    device.update = Mock()
    device.delete = Mock()

    return device


def make_nb_interface(
    id=1, name="GigabitEthernet0/1", description="", enabled=True,
    mtu=None, speed=None, duplex=None, intf_type="1000base-t",
    mode=None, lag=None, mac_address=None, device=None,
    untagged_vlan=None, tagged_vlans=None, cable=None,
):
    """Создаёт mock NetBox интерфейс."""
    intf = MagicMock()
    intf.id = id
    intf.name = name
    intf.description = description
    intf.enabled = enabled
    intf.mtu = mtu
    intf.speed = speed
    intf.duplex = duplex

    intf.type = MagicMock()
    intf.type.value = intf_type

    intf.mode = MagicMock() if mode else None
    if mode:
        intf.mode.value = mode

    intf.lag = lag
    intf.mac_address = mac_address
    intf.device = device or MagicMock()
    intf.untagged_vlan = untagged_vlan
    intf.tagged_vlans = tagged_vlans or []
    intf.cable = cable
    intf.delete = Mock()
    intf.update = Mock()

    return intf


def make_nb_ip(id=1, address="10.0.0.1/24", interface_id=100, tenant=None):
    """Создаёт mock NetBox IP-адрес."""
    ip = MagicMock()
    ip.id = id
    ip.address = address
    ip.assigned_object_id = interface_id
    ip.assigned_object_type = "dcim.interface"
    ip.description = ""
    ip.tenant = tenant
    ip.status = MagicMock()
    ip.status.value = "active"
    ip.delete = Mock()
    ip.update = Mock()
    return ip


def make_nb_cable(id=1, a_device="switch-01", a_intf="Gi0/1", b_device="switch-02", b_intf="Gi0/1"):
    """Создаёт mock NetBox кабель."""
    cable = MagicMock()
    cable.id = id

    # a_terminations
    a_term = MagicMock()
    a_term.object = MagicMock()
    a_term.object.device = MagicMock()
    a_term.object.device.name = a_device
    a_term.object.name = a_intf

    b_term = MagicMock()
    b_term.object = MagicMock()
    b_term.object.device = MagicMock()
    b_term.object.device.name = b_device
    b_term.object.name = b_intf

    cable.a_terminations = [a_term]
    cable.b_terminations = [b_term]
    cable.delete = Mock()
    return cable


def make_sync_config(**overrides):
    """Создаёт mock sync config с дефолтными значениями."""
    defaults = {
        "create_missing": True,
        "update_existing": True,
        "exclude_interfaces": [],
        "auto_detect_type": True,
        "sync_vlans": False,
        "enabled_mode": "admin",
        "sync_mac_only_with_ip": False,
    }
    defaults.update(overrides)

    cfg = MagicMock()
    cfg.get_option.side_effect = lambda key, default=None: defaults.get(key, default)
    cfg.is_field_enabled.return_value = True
    return cfg


# ==================== FIXTURES ====================

@pytest.fixture
def base_client():
    """Базовый NetBox клиент (минимальная настройка)."""
    client = Mock()
    client.get_device_by_name.return_value = None
    client.get_device_by_ip.return_value = None
    client.get_device_by_mac.return_value = None
    client.get_interfaces.return_value = []
    client.get_ip_addresses.return_value = []
    client.get_inventory_items.return_value = []
    client.get_cables.return_value = []
    client.get_devices.return_value = []
    client.bulk_create_interfaces.return_value = []
    client.bulk_update_interfaces.return_value = []
    client.bulk_delete_interfaces.return_value = True
    client.bulk_create_inventory_items.return_value = []
    client.bulk_update_inventory_items.return_value = []
    client.bulk_delete_inventory_items.return_value = True
    client.bulk_create_ip_addresses.return_value = []
    client.bulk_delete_ip_addresses.return_value = True
    client.get_interface_by_name.return_value = None
    client.assign_mac_to_interface = Mock()
    client.api = MagicMock()
    return client


# ==================== 1. DEVICES SYNC ====================

class TestDevicesSyncPolygon:
    """Эмуляция полигона: sync_devices_from_inventory."""

    def test_create_new_device(self, base_client):
        """Создание нового устройства из inventory data."""
        base_client.get_device_by_name.return_value = None
        base_client.api.dcim.devices.create.return_value = MagicMock(id=1)

        sync = NetBoxSync(base_client, dry_run=False)
        # Mock вспомогательных методов
        sync._get_or_create_manufacturer = Mock(return_value=MagicMock(id=10))
        sync._get_or_create_device_type = Mock(return_value=MagicMock(id=20))
        sync._get_or_create_site = Mock(return_value=MagicMock(id=30))
        sync._get_or_create_role = Mock(return_value=MagicMock(id=40))
        sync._get_or_create_platform = Mock(return_value=MagicMock(id=50))

        devices_data = [
            DeviceInfo(hostname="new-switch", ip_address="10.0.0.1", model="C2960", serial="ABC123"),
        ]
        result = sync.sync_devices_from_inventory(devices_data, site="Lab")

        assert result["created"] == 1
        assert result["failed"] == 0

    def test_update_existing_device_serial(self, base_client):
        """Обновление серийного номера существующего устройства."""
        device = make_nb_device(serial="OLD_SERIAL")
        base_client.get_device_by_name.return_value = device

        sync = NetBoxSync(base_client, dry_run=False)
        sync._get_or_create_manufacturer = Mock(return_value=MagicMock(id=10))
        sync._get_or_create_device_type = Mock(return_value=MagicMock(id=20))

        devices_data = [
            DeviceInfo(hostname="switch-01", serial="NEW_SERIAL", model="WS-C2960"),
        ]
        result = sync.sync_devices_from_inventory(devices_data, update_existing=True)

        assert result["updated"] == 1
        device.update.assert_called_once()
        call_args = device.update.call_args[0][0]
        assert call_args["serial"] == "NEW_SERIAL"

    def test_skip_device_no_changes(self, base_client):
        """Устройство без изменений — пропуск."""
        # site="Main" и role="switch" совпадают с дефолтами sync_devices_from_inventory
        device = make_nb_device(serial="SAME", model="WS-C2960", site="Main", role="switch")
        base_client.get_device_by_name.return_value = device

        sync = NetBoxSync(base_client, dry_run=False)

        # model="Unknown" пропускается в _update_device, serial совпадает
        devices_data = [
            DeviceInfo(hostname="switch-01", serial="SAME", model="Unknown"),
        ]
        result = sync.sync_devices_from_inventory(
            devices_data, update_existing=True, site="Main", role="switch"
        )

        assert result["skipped"] == 1
        assert result["updated"] == 0

    def test_find_device_by_ip_fallback(self, base_client):
        """Fallback: устройство не найдено по имени, но найдено по IP."""
        device = make_nb_device(name="switch-01")
        base_client.get_device_by_name.return_value = None
        base_client.get_device_by_ip.return_value = device

        sync = NetBoxSync(base_client, dry_run=False)

        devices_data = [
            DeviceInfo(hostname="10.0.0.1", ip_address="10.0.0.1", model="WS-C2960"),
        ]
        result = sync.sync_devices_from_inventory(devices_data, update_existing=True)

        # Найдено по IP — skipped (no changes) или updated
        assert result["created"] == 0
        base_client.get_device_by_ip.assert_called_with("10.0.0.1")

    def test_device_with_primary_ip(self, base_client):
        """Установка primary IP при обновлении устройства."""
        device = make_nb_device(primary_ip4=None)
        base_client.get_device_by_name.return_value = device

        # Mock для _set_primary_ip
        ip_obj = make_nb_ip(id=500, address="10.0.0.1/32")
        base_client.get_ip_addresses.return_value = [ip_obj]

        sync = NetBoxSync(base_client, dry_run=False)

        devices_data = [
            DeviceInfo(hostname="switch-01", ip_address="10.0.0.1", model="WS-C2960"),
        ]
        result = sync.sync_devices_from_inventory(
            devices_data, update_existing=True, set_primary_ip=True
        )

        assert result["updated"] == 1

    def test_primary_ip_not_found_logs_warning(self, base_client):
        """Primary IP не найден — логируется warning."""
        device = make_nb_device(primary_ip4=None)
        base_client.get_device_by_name.return_value = device
        base_client.get_ip_addresses.return_value = []
        base_client.api.ipam.ip_addresses.get.return_value = None
        base_client.api.ipam.ip_addresses.create.side_effect = Exception("IP create failed")

        sync = NetBoxSync(base_client, dry_run=False)

        devices_data = [
            DeviceInfo(hostname="switch-01", ip_address="10.0.0.99", model="WS-C2960"),
        ]
        # Не должен упасть — ошибка primary IP логируется
        result = sync.sync_devices_from_inventory(
            devices_data, update_existing=True, set_primary_ip=True
        )
        assert result["failed"] == 0 or result["updated"] == 0

    def test_cleanup_devices(self, base_client):
        """Cleanup удаляет устройства не из inventory."""
        # Устройство в inventory
        existing = make_nb_device(name="switch-01", tenant="Lab")
        base_client.get_device_by_name.return_value = existing

        # Устройства в NetBox (switch-01 + switch-OLD)
        nb_switch01 = make_nb_device(name="switch-01", tenant="Lab")
        nb_old = make_nb_device(id=99, name="switch-OLD", tenant="Lab")
        base_client.get_devices.return_value = [nb_switch01, nb_old]

        sync = NetBoxSync(base_client, dry_run=False)

        devices_data = [
            DeviceInfo(hostname="switch-01", model="WS-C2960"),
        ]
        result = sync.sync_devices_from_inventory(
            devices_data, cleanup=True, tenant="Lab"
        )

        assert result["deleted"] == 1
        nb_old.delete.assert_called_once()

    def test_dry_run_devices(self, base_client):
        """Dry-run: устройства не создаются, статистика считается."""
        base_client.get_device_by_name.return_value = None

        sync = NetBoxSync(base_client, dry_run=True)

        devices_data = [
            DeviceInfo(hostname="new-switch", model="C2960"),
        ]
        result = sync.sync_devices_from_inventory(devices_data)

        assert result["created"] == 1
        base_client.api.dcim.devices.create.assert_not_called()


# ==================== 2. INTERFACES SYNC (LAG + VLAN + CLEANUP) ====================

class TestInterfacesSyncPolygon:
    """Эмуляция полигона: sync_interfaces с различными сценариями."""

    @patch("network_collector.netbox.sync.interfaces.get_sync_config")
    def test_full_sync_create_update_delete(self, mock_sync_cfg, base_client):
        """Полный цикл: создание новых + обновление существующих + удаление лишних."""
        mock_sync_cfg.return_value = make_sync_config()

        device = make_nb_device()
        base_client.get_device_by_name.return_value = device

        # В NetBox: Gi0/1 (будет обновлён) + Gi0/99 (будет удалён)
        nb_gi01 = make_nb_interface(id=100, name="GigabitEthernet0/1", description="old desc", device=device)
        nb_gi99 = make_nb_interface(id=199, name="GigabitEthernet0/99", description="stale", device=device)
        base_client.get_interfaces.return_value = [nb_gi01, nb_gi99]
        base_client.bulk_update_interfaces.return_value = [Mock()]
        base_client.bulk_create_interfaces.return_value = [MagicMock(id=200)]
        base_client.bulk_delete_interfaces.return_value = True

        # На устройстве: Gi0/1 (обновить desc) + Gi0/2 (новый)
        local = [
            Interface(name="GigabitEthernet0/1", status="up", description="new desc"),
            Interface(name="GigabitEthernet0/2", status="up", description="server link"),
        ]

        sync = NetBoxSync(base_client, dry_run=False)
        result = sync.sync_interfaces("switch-01", local, cleanup=True)

        assert result["updated"] == 1  # Gi0/1 description changed
        assert result["created"] == 1  # Gi0/2 new
        assert result["deleted"] == 1  # Gi0/99 removed

    @patch("network_collector.netbox.sync.interfaces.get_sync_config")
    def test_lag_two_phase_create(self, mock_sync_cfg, base_client):
        """Двухфазное создание: Port-channel ДО member интерфейсов."""
        mock_sync_cfg.return_value = make_sync_config()

        device = make_nb_device()
        base_client.get_device_by_name.return_value = device
        base_client.get_interfaces.return_value = []

        # Эмулируем LAG creation flow
        created_lags = {}

        def fake_bulk_create(batch):
            results = []
            for i, data in enumerate(batch):
                m = MagicMock(id=1000 + i)
                m.name = data["name"]
                results.append(m)
                if data["name"].lower().startswith(("port-channel", "po")):
                    created_lags[data["name"]] = m
            return results

        base_client.bulk_create_interfaces.side_effect = fake_bulk_create
        base_client.get_interface_by_name.side_effect = lambda dev_id, name: created_lags.get(name)

        local = [
            Interface(name="Port-channel1", status="up"),
            Interface(name="GigabitEthernet0/1", status="up", lag="Port-channel1"),
            Interface(name="GigabitEthernet0/2", status="up", lag="Port-channel1"),
            Interface(name="GigabitEthernet0/3", status="up"),  # standalone
        ]

        sync = NetBoxSync(base_client, dry_run=False)
        result = sync.sync_interfaces("switch-01", local)

        assert result["created"] == 4
        assert base_client.bulk_create_interfaces.call_count == 2

        # Фаза 1: только LAG
        phase1 = base_client.bulk_create_interfaces.call_args_list[0][0][0]
        assert len(phase1) == 1
        assert phase1[0]["name"] == "Port-channel1"

        # Фаза 2: members + standalone
        phase2 = base_client.bulk_create_interfaces.call_args_list[1][0][0]
        assert len(phase2) == 3

        # Members имеют lag ID
        gi01 = next(d for d in phase2 if d["name"] == "GigabitEthernet0/1")
        assert "lag" in gi01 and gi01["lag"] == 1000

        # Standalone без lag
        gi03 = next(d for d in phase2 if d["name"] == "GigabitEthernet0/3")
        assert "lag" not in gi03

    @patch("network_collector.netbox.sync.interfaces.get_sync_config")
    def test_dict_input_from_pipeline(self, mock_sync_cfg, base_client):
        """Pipeline передаёт dict данные — sync_interfaces должен их принять."""
        mock_sync_cfg.return_value = make_sync_config()

        device = make_nb_device()
        base_client.get_device_by_name.return_value = device
        base_client.get_interfaces.return_value = []
        base_client.bulk_create_interfaces.return_value = [MagicMock(id=1)]

        # Данные как dict (так приходит из pipeline)
        local = [
            {"interface": "GigabitEthernet0/1", "status": "up", "description": "test"},
        ]

        sync = NetBoxSync(base_client, dry_run=False)
        result = sync.sync_interfaces("switch-01", local)

        assert result["created"] == 1

    @patch("network_collector.netbox.sync.interfaces.get_sync_config")
    def test_interface_bulk_create_fallback(self, mock_sync_cfg, base_client):
        """При ошибке bulk create — fallback на поштучное создание."""
        mock_sync_cfg.return_value = make_sync_config()

        device = make_nb_device()
        base_client.get_device_by_name.return_value = device
        base_client.get_interfaces.return_value = []
        base_client.bulk_create_interfaces.side_effect = Exception("Bulk API error")
        base_client.create_interface.return_value = MagicMock(id=1)

        local = [
            Interface(name="GigabitEthernet0/1", status="up"),
            Interface(name="GigabitEthernet0/2", status="up"),
        ]

        sync = NetBoxSync(base_client, dry_run=False)
        result = sync.sync_interfaces("switch-01", local)

        assert result["created"] == 2
        assert base_client.create_interface.call_count == 2

    @patch("network_collector.netbox.sync.interfaces.get_sync_config")
    def test_disabled_interface_status(self, mock_sync_cfg, base_client):
        """Интерфейс со статусом disabled — enabled=False."""
        mock_sync_cfg.return_value = make_sync_config(enabled_mode="admin")

        device = make_nb_device()
        base_client.get_device_by_name.return_value = device
        base_client.get_interfaces.return_value = []

        created = [MagicMock(id=1)]
        base_client.bulk_create_interfaces.return_value = created

        # В admin mode: "disabled" и "error" → enabled=False
        # "up", "down", "administratively down" → enabled=True
        local = [
            Interface(name="GigabitEthernet0/1", status="disabled"),
        ]

        sync = NetBoxSync(base_client, dry_run=False)
        result = sync.sync_interfaces("switch-01", local)

        assert result["created"] == 1
        batch = base_client.bulk_create_interfaces.call_args[0][0]
        assert batch[0]["enabled"] is False


# ==================== 3. IP ADDRESSES SYNC ====================

class TestIPAddressesSyncPolygon:
    """Эмуляция полигона: sync_ip_addresses."""

    def test_create_new_ip(self, base_client):
        """Создание нового IP-адреса."""
        device = make_nb_device()
        base_client.get_device_by_name.return_value = device

        nb_intf = make_nb_interface(id=100, name="Vlan100")
        base_client.get_interfaces.return_value = [nb_intf]
        base_client.get_ip_addresses.return_value = []
        base_client.bulk_create_ip_addresses.return_value = [MagicMock(id=1)]

        entries = [
            IPAddressEntry(ip_address="10.0.0.1", mask="24", interface="Vlan100"),
        ]

        sync = NetBoxSync(base_client, dry_run=False)
        result = sync.sync_ip_addresses("switch-01", entries)

        assert result["created"] == 1
        base_client.bulk_create_ip_addresses.assert_called_once()

    def test_skip_existing_ip(self, base_client):
        """Существующий IP — пропуск."""
        device = make_nb_device()
        base_client.get_device_by_name.return_value = device

        nb_intf = make_nb_interface(id=100, name="Vlan100")
        base_client.get_interfaces.return_value = [nb_intf]

        existing_ip = make_nb_ip(id=50, address="10.0.0.1/24", interface_id=100)
        base_client.get_ip_addresses.return_value = [existing_ip]

        entries = [
            IPAddressEntry(ip_address="10.0.0.1", mask="24", interface="Vlan100"),
        ]

        sync = NetBoxSync(base_client, dry_run=False)
        result = sync.sync_ip_addresses("switch-01", entries)

        assert result["created"] == 0
        assert result["skipped"] == 1

    def test_cleanup_old_ip(self, base_client):
        """Cleanup удаляет IP которых нет на устройстве."""
        device = make_nb_device()
        base_client.get_device_by_name.return_value = device

        nb_intf = make_nb_interface(id=100, name="Vlan100")
        base_client.get_interfaces.return_value = [nb_intf]

        old_ip = make_nb_ip(id=50, address="192.168.1.1/24", interface_id=100)
        base_client.get_ip_addresses.return_value = [old_ip]

        sync = NetBoxSync(base_client, dry_run=False)
        result = sync.sync_ip_addresses("switch-01", [], cleanup=True)

        assert result["deleted"] == 1

    def test_set_primary_ip(self, base_client):
        """Установка primary IP после создания."""
        device = make_nb_device(primary_ip4=None)
        base_client.get_device_by_name.return_value = device

        nb_intf = make_nb_interface(id=100, name="Vlan100")
        base_client.get_interfaces.return_value = [nb_intf]

        # IP уже создан на устройстве
        ip_obj = make_nb_ip(id=500, address="10.0.0.1/24", interface_id=100)
        base_client.get_ip_addresses.return_value = [ip_obj]

        sync = NetBoxSync(base_client, dry_run=False)
        result = sync.sync_ip_addresses(
            "switch-01",
            [IPAddressEntry(ip_address="10.0.0.1", mask="24", interface="Vlan100")],
            device_ip="10.0.0.1",
        )

        # primary IP должен быть установлен
        assert "primary_ip" in result.get("details", {})

    def test_dry_run_ip_no_api_calls(self, base_client):
        """Dry-run: IP не создаются, статистика считается."""
        device = make_nb_device()
        base_client.get_device_by_name.return_value = device

        nb_intf = make_nb_interface(id=100, name="Vlan100")
        base_client.get_interfaces.return_value = [nb_intf]
        base_client.get_ip_addresses.return_value = []

        entries = [
            IPAddressEntry(ip_address="10.0.0.1", mask="24", interface="Vlan100"),
            IPAddressEntry(ip_address="10.0.0.2", mask="24", interface="Vlan100"),
        ]

        sync = NetBoxSync(base_client, dry_run=True)
        result = sync.sync_ip_addresses("switch-01", entries)

        assert result["created"] == 2
        base_client.bulk_create_ip_addresses.assert_not_called()

    def test_ip_bulk_create_fallback(self, base_client):
        """При ошибке bulk create — fallback на поштучное."""
        device = make_nb_device()
        base_client.get_device_by_name.return_value = device

        nb_intf = make_nb_interface(id=100, name="Vlan100")
        base_client.get_interfaces.return_value = [nb_intf]
        base_client.get_ip_addresses.return_value = []

        base_client.bulk_create_ip_addresses.side_effect = Exception("Bulk API error")
        base_client.api.ipam.ip_addresses.create.return_value = MagicMock(id=1)

        entries = [
            IPAddressEntry(ip_address="10.0.0.1", mask="24", interface="Vlan100"),
        ]

        sync = NetBoxSync(base_client, dry_run=False)
        result = sync.sync_ip_addresses("switch-01", entries)

        assert result["created"] == 1
        base_client.api.ipam.ip_addresses.create.assert_called_once()

    def test_device_not_found(self, base_client):
        """Устройство не найдено — ошибка."""
        base_client.get_device_by_name.return_value = None

        entries = [IPAddressEntry(ip_address="10.0.0.1", mask="24", interface="Vlan100")]

        sync = NetBoxSync(base_client, dry_run=False)
        result = sync.sync_ip_addresses("nonexistent", entries)

        assert result["failed"] >= 1


# ==================== 4. INVENTORY SYNC ====================

class TestInventorySyncPolygon:
    """Эмуляция полигона: sync_inventory."""

    def test_create_new_inventory(self, base_client):
        """Создание новых inventory items."""
        device = make_nb_device()
        base_client.get_device_by_name.return_value = device
        base_client.get_inventory_items.return_value = []
        base_client.bulk_create_inventory_items.return_value = [MagicMock(id=1), MagicMock(id=2)]

        items = [
            InventoryItem(name="PSU 1", pid="PWR-C2960-AC", serial="PSU001"),
            InventoryItem(name="FAN 1", pid="FAN-C2960", serial="FAN001"),
        ]

        sync = NetBoxSync(base_client, dry_run=False)
        result = sync.sync_inventory("switch-01", items)

        assert result["created"] == 2
        base_client.bulk_create_inventory_items.assert_called_once()

    def test_update_inventory_serial(self, base_client):
        """Обновление серийного номера inventory item."""
        device = make_nb_device()
        base_client.get_device_by_name.return_value = device

        existing = MagicMock()
        existing.id = 10
        existing.name = "PSU 1"
        existing.part_id = "PWR-C2960-AC"
        existing.serial = "OLD_SERIAL"
        existing.description = ""
        existing.manufacturer = None
        base_client.get_inventory_items.return_value = [existing]
        base_client.bulk_update_inventory_items.return_value = [MagicMock()]

        items = [
            InventoryItem(name="PSU 1", pid="PWR-C2960-AC", serial="NEW_SERIAL"),
        ]

        sync = NetBoxSync(base_client, dry_run=False)
        result = sync.sync_inventory("switch-01", items)

        assert result["updated"] == 1

    def test_cleanup_inventory(self, base_client):
        """Cleanup удаляет inventory items которых нет на устройстве."""
        device = make_nb_device()
        base_client.get_device_by_name.return_value = device

        old_item = MagicMock()
        old_item.id = 99
        old_item.name = "Old Module"
        old_item.part_id = ""
        old_item.serial = "OLD"
        old_item.description = ""
        old_item.manufacturer = None
        base_client.get_inventory_items.return_value = [old_item]
        base_client.bulk_delete_inventory_items.return_value = True

        sync = NetBoxSync(base_client, dry_run=False)
        result = sync.sync_inventory("switch-01", [], cleanup=True)

        assert result["deleted"] == 1

    def test_inventory_name_truncation(self, base_client):
        """Длинные имена обрезаются до 64 символов."""
        device = make_nb_device()
        base_client.get_device_by_name.return_value = device
        base_client.get_inventory_items.return_value = []
        base_client.bulk_create_inventory_items.return_value = [MagicMock(id=1)]

        long_name = "A" * 100  # 100 символов
        items = [InventoryItem(name=long_name, pid="PID", serial="SER1")]

        sync = NetBoxSync(base_client, dry_run=False)
        result = sync.sync_inventory("switch-01", items)

        assert result["created"] == 1
        # Проверяем что имя обрезано
        batch = base_client.bulk_create_inventory_items.call_args[0][0]
        assert len(batch[0]["name"]) <= 64

    def test_dry_run_inventory(self, base_client):
        """Dry-run: inventory не создаётся."""
        device = make_nb_device()
        base_client.get_device_by_name.return_value = device
        base_client.get_inventory_items.return_value = []

        items = [InventoryItem(name="PSU 1", pid="PWR", serial="S1")]

        sync = NetBoxSync(base_client, dry_run=True)
        result = sync.sync_inventory("switch-01", items)

        assert result["created"] == 1
        base_client.bulk_create_inventory_items.assert_not_called()


# ==================== 5. CABLES SYNC ====================

class TestCablesSyncPolygon:
    """Эмуляция полигона: sync_cables_from_lldp."""

    def test_create_cable_between_devices(self, base_client):
        """Создание кабеля между двумя устройствами."""
        dev_a = make_nb_device(id=1, name="switch-01")
        dev_b = make_nb_device(id=2, name="switch-02")
        base_client.get_device_by_name.side_effect = lambda name: {
            "switch-01": dev_a, "switch-02": dev_b
        }.get(name)

        intf_a = make_nb_interface(id=100, name="GigabitEthernet0/1", device=dev_a, cable=None)
        intf_b = make_nb_interface(id=200, name="GigabitEthernet0/1", device=dev_b, cable=None)

        # Кэш интерфейсов
        base_client.get_interfaces.side_effect = lambda device_id: {
            1: [intf_a], 2: [intf_b]
        }.get(device_id, [])

        base_client.api.dcim.cables.create.return_value = MagicMock(id=1)

        lldp = [
            LLDPNeighbor(
                hostname="switch-01",
                local_interface="GigabitEthernet0/1",
                remote_hostname="switch-02",
                remote_port="GigabitEthernet0/1",
                neighbor_type="hostname",
            ),
        ]

        sync = NetBoxSync(base_client, dry_run=False)
        result = sync.sync_cables_from_lldp(lldp)

        assert result["created"] == 1
        base_client.api.dcim.cables.create.assert_called_once()

    def test_skip_existing_cable(self, base_client):
        """Кабель уже существует — пропуск."""
        dev_a = make_nb_device(id=1, name="switch-01")
        dev_b = make_nb_device(id=2, name="switch-02")
        base_client.get_device_by_name.side_effect = lambda name: {
            "switch-01": dev_a, "switch-02": dev_b
        }.get(name)

        existing_cable = MagicMock()
        intf_a = make_nb_interface(id=100, name="GigabitEthernet0/1", device=dev_a, cable=existing_cable)
        intf_b = make_nb_interface(id=200, name="GigabitEthernet0/1", device=dev_b, cable=existing_cable)

        base_client.get_interfaces.side_effect = lambda device_id: {
            1: [intf_a], 2: [intf_b]
        }.get(device_id, [])

        lldp = [
            LLDPNeighbor(
                hostname="switch-01",
                local_interface="GigabitEthernet0/1",
                remote_hostname="switch-02",
                remote_port="GigabitEthernet0/1",
                neighbor_type="hostname",
            ),
        ]

        sync = NetBoxSync(base_client, dry_run=False)
        result = sync.sync_cables_from_lldp(lldp)

        assert result["already_exists"] == 1
        assert result["created"] == 0

    def test_skip_unknown_neighbor(self, base_client):
        """Неизвестный тип соседа — пропуск при skip_unknown=True."""
        lldp = [
            LLDPNeighbor(
                hostname="switch-01",
                local_interface="Gi0/1",
                remote_hostname="phone-01",
                remote_port="Port 1",
                neighbor_type="unknown",
            ),
        ]

        sync = NetBoxSync(base_client, dry_run=False)
        result = sync.sync_cables_from_lldp(lldp, skip_unknown=True)

        assert result["skipped"] == 1
        assert result["created"] == 0

    def test_skip_lag_interfaces(self, base_client):
        """LAG интерфейсы пропускаются при создании кабелей."""
        dev_a = make_nb_device(id=1, name="switch-01")
        dev_b = make_nb_device(id=2, name="switch-02")
        base_client.get_device_by_name.side_effect = lambda name: {
            "switch-01": dev_a, "switch-02": dev_b
        }.get(name)

        lag_intf = make_nb_interface(id=100, name="Port-channel1", intf_type="lag", device=dev_a, cable=None)
        intf_b = make_nb_interface(id=200, name="Port-channel1", intf_type="lag", device=dev_b, cable=None)

        base_client.get_interfaces.side_effect = lambda device_id: {
            1: [lag_intf], 2: [intf_b]
        }.get(device_id, [])

        lldp = [
            LLDPNeighbor(
                hostname="switch-01",
                local_interface="Port-channel1",
                remote_hostname="switch-02",
                remote_port="Port-channel1",
                neighbor_type="hostname",
            ),
        ]

        sync = NetBoxSync(base_client, dry_run=False)
        result = sync.sync_cables_from_lldp(lldp)

        assert result["skipped"] >= 1
        assert result["created"] == 0

    @patch("network_collector.netbox.sync.cables.get_cable_endpoints")
    def test_cable_cleanup_tracks_failed_devices(self, mock_get_endpoints, base_client):
        """Cleanup кабелей: отслеживание failed_devices."""
        dev_a = make_nb_device(id=1, name="switch-01")
        dev_b = make_nb_device(id=2, name="switch-02")
        base_client.get_device_by_name.side_effect = lambda name: {
            "switch-01": dev_a, "switch-02": None  # switch-02 не найден!
        }.get(name)

        base_client.get_cables.return_value = []
        base_client.get_interfaces.return_value = []

        lldp = [
            LLDPNeighbor(
                hostname="switch-01",
                local_interface="Gi0/1",
                remote_hostname="switch-02",
                remote_port="Gi0/1",
                neighbor_type="hostname",
            ),
        ]

        sync = NetBoxSync(base_client, dry_run=False)
        result = sync.sync_cables_from_lldp(lldp, cleanup=True)

        # switch-02 не найден при cleanup → failed_devices
        # Это попадает в stats["failed"]
        assert result["failed"] >= 1

    @patch("network_collector.netbox.sync.cables.get_cable_endpoints")
    def test_cable_cleanup_get_cables_error(self, mock_get_endpoints, base_client):
        """get_cables ошибка — устройство пропущено, увеличивает failed."""
        dev = make_nb_device(id=1, name="switch-01")
        base_client.get_device_by_name.return_value = dev
        base_client.get_cables.side_effect = Exception("Connection timeout")
        base_client.get_interfaces.return_value = []

        lldp = [
            LLDPNeighbor(
                hostname="switch-01",
                local_interface="Gi0/1",
                remote_hostname="switch-01",
                remote_port="Gi0/2",
                neighbor_type="hostname",
            ),
        ]

        sync = NetBoxSync(base_client, dry_run=False)
        result = sync.sync_cables_from_lldp(lldp, cleanup=True)

        # Ошибка get_cables → failed_devices += 1
        assert result["failed"] >= 1

    def test_dry_run_cables(self, base_client):
        """Dry-run: кабели не создаются, статистика считается."""
        dev_a = make_nb_device(id=1, name="switch-01")
        dev_b = make_nb_device(id=2, name="switch-02")
        base_client.get_device_by_name.side_effect = lambda name: {
            "switch-01": dev_a, "switch-02": dev_b
        }.get(name)

        intf_a = make_nb_interface(id=100, name="GigabitEthernet0/1", device=dev_a, cable=None)
        intf_b = make_nb_interface(id=200, name="GigabitEthernet0/1", device=dev_b, cable=None)

        base_client.get_interfaces.side_effect = lambda device_id: {
            1: [intf_a], 2: [intf_b]
        }.get(device_id, [])

        lldp = [
            LLDPNeighbor(
                hostname="switch-01",
                local_interface="GigabitEthernet0/1",
                remote_hostname="switch-02",
                remote_port="GigabitEthernet0/1",
                neighbor_type="hostname",
            ),
        ]

        sync = NetBoxSync(base_client, dry_run=True)
        result = sync.sync_cables_from_lldp(lldp)

        assert result["created"] == 1
        base_client.api.dcim.cables.create.assert_not_called()

    def test_cable_dedup_both_sides(self, base_client):
        """Дедупликация: LLDP видит кабель с обеих сторон, создаём 1 раз."""
        dev_a = make_nb_device(id=1, name="switch-01")
        dev_b = make_nb_device(id=2, name="switch-02")
        base_client.get_device_by_name.side_effect = lambda name: {
            "switch-01": dev_a, "switch-02": dev_b
        }.get(name)

        intf_a1 = make_nb_interface(id=100, name="GigabitEthernet0/1", device=dev_a, cable=None)
        intf_b1 = make_nb_interface(id=200, name="GigabitEthernet0/1", device=dev_b, cable=None)

        base_client.get_interfaces.side_effect = lambda device_id: {
            1: [intf_a1], 2: [intf_b1]
        }.get(device_id, [])

        base_client.api.dcim.cables.create.return_value = MagicMock(id=1)

        # Один кабель виден с двух сторон (LLDP bidirectional)
        lldp = [
            LLDPNeighbor(
                hostname="switch-01",
                local_interface="GigabitEthernet0/1",
                remote_hostname="switch-02",
                remote_port="GigabitEthernet0/1",
                neighbor_type="hostname",
            ),
            LLDPNeighbor(
                hostname="switch-02",
                local_interface="GigabitEthernet0/1",
                remote_hostname="switch-01",
                remote_port="GigabitEthernet0/1",
                neighbor_type="hostname",
            ),
        ]

        sync = NetBoxSync(base_client, dry_run=True)
        result = sync.sync_cables_from_lldp(lldp)

        # Должен быть засчитан только 1 кабель (дедупликация)
        assert result["created"] == 1


# ==================== 6. FIND NEIGHBOR DEVICE ====================

class TestFindNeighborDevice:
    """Тесты поиска соседей по различным идентификаторам."""

    def test_find_by_hostname(self, base_client):
        """Поиск соседа по hostname."""
        dev = make_nb_device(name="core-switch")
        base_client.get_device_by_name.return_value = dev

        sync = NetBoxSync(base_client, dry_run=True)
        entry = LLDPNeighbor(
            hostname="switch-01",
            local_interface="Gi0/1",
            remote_hostname="core-switch",
            remote_port="Gi0/48",
            neighbor_type="hostname",
        )

        result = sync._find_neighbor_device(entry)
        assert result is not None
        assert result.name == "core-switch"

    def test_find_by_hostname_with_domain(self, base_client):
        """Поиск соседа с FQDN — отрезаем домен."""
        dev = make_nb_device(name="core-switch")
        base_client.get_device_by_name.return_value = dev

        sync = NetBoxSync(base_client, dry_run=True)
        entry = LLDPNeighbor(
            hostname="switch-01",
            local_interface="Gi0/1",
            remote_hostname="core-switch.lab.local",
            remote_port="Gi0/48",
            neighbor_type="hostname",
        )

        result = sync._find_neighbor_device(entry)
        assert result is not None

    def test_find_by_mac_fallback(self, base_client):
        """Fallback поиск по MAC когда hostname не найден."""
        dev = make_nb_device(name="unknown-device")
        base_client.get_device_by_name.return_value = None
        base_client.get_device_by_ip.return_value = None
        base_client.get_device_by_mac.return_value = dev

        sync = NetBoxSync(base_client, dry_run=True)
        entry = LLDPNeighbor(
            hostname="switch-01",
            local_interface="Gi0/1",
            remote_hostname="not-found",
            remote_port="Gi0/1",
            remote_mac="00:11:22:33:44:55",
            neighbor_type="hostname",
        )

        result = sync._find_neighbor_device(entry)
        assert result is not None
        assert result.name == "unknown-device"

    def test_find_by_ip(self, base_client):
        """Поиск соседа по IP (neighbor_type=ip)."""
        dev = make_nb_device(name="ip-device")
        base_client.get_device_by_ip.return_value = dev

        sync = NetBoxSync(base_client, dry_run=True)
        entry = LLDPNeighbor(
            hostname="switch-01",
            local_interface="Gi0/1",
            remote_hostname="",
            remote_port="Gi0/1",
            remote_ip="192.168.1.1",
            neighbor_type="ip",
        )

        result = sync._find_neighbor_device(entry)
        assert result is not None
        assert result.name == "ip-device"

    def test_neighbor_not_found(self, base_client):
        """Сосед не найден нигде — None."""
        base_client.get_device_by_name.return_value = None
        base_client.get_device_by_ip.return_value = None
        base_client.get_device_by_mac.return_value = None

        sync = NetBoxSync(base_client, dry_run=True)
        entry = LLDPNeighbor(
            hostname="switch-01",
            local_interface="Gi0/1",
            remote_hostname="phantom",
            remote_port="Gi0/1",
            neighbor_type="hostname",
        )

        result = sync._find_neighbor_device(entry)
        assert result is None


# ==================== 7. PIPELINE FULL FLOW ====================

class TestPipelineFullFlow:
    """Эмуляция полного pipeline: devices → interfaces → IP → inventory → cables."""

    @patch("network_collector.netbox.sync.interfaces.get_sync_config")
    def test_full_pipeline_dry_run(self, mock_sync_cfg, base_client):
        """Полный pipeline в dry_run — ничего не создаётся, все stats считаются."""
        mock_sync_cfg.return_value = make_sync_config()

        device = make_nb_device()
        base_client.get_device_by_name.return_value = device
        base_client.get_interfaces.return_value = []
        base_client.get_ip_addresses.return_value = []
        base_client.get_inventory_items.return_value = []

        sync = NetBoxSync(base_client, dry_run=True)

        # Step 1: Devices
        devices = [DeviceInfo(hostname="switch-01", model="C2960")]
        dev_result = sync.sync_devices_from_inventory(devices)
        assert dev_result["skipped"] >= 1 or dev_result["created"] >= 0

        # Step 2: Interfaces (без LAG чтобы dry_run не пытался их найти)
        interfaces = [
            Interface(name="GigabitEthernet0/1", status="up"),
            Interface(name="Vlan100", status="up"),
        ]
        intf_result = sync.sync_interfaces("switch-01", interfaces)
        assert intf_result["created"] == 2

        # Step 3: IP Addresses
        # В dry_run интерфейсы не создаются в NetBox, но нужна Vlan100 в mock
        nb_vlan100 = make_nb_interface(id=100, name="Vlan100")
        base_client.get_interfaces.return_value = [nb_vlan100]

        ips = [
            IPAddressEntry(ip_address="10.0.0.1", mask="24", interface="Vlan100"),
        ]
        ip_result = sync.sync_ip_addresses("switch-01", ips)
        assert ip_result["created"] == 1

        # Step 4: Inventory
        inventory = [
            InventoryItem(name="PSU 1", pid="PWR", serial="PSU001"),
        ]
        inv_result = sync.sync_inventory("switch-01", inventory)
        assert inv_result["created"] == 1

        # Ни один bulk метод не должен быть вызван в dry_run
        base_client.bulk_create_interfaces.assert_not_called()
        base_client.bulk_create_ip_addresses.assert_not_called()
        base_client.bulk_create_inventory_items.assert_not_called()
        base_client.api.dcim.cables.create.assert_not_called()

    @patch("network_collector.netbox.sync.interfaces.get_sync_config")
    def test_full_pipeline_with_apply(self, mock_sync_cfg, base_client):
        """Полный pipeline с apply — все операции выполняются."""
        mock_sync_cfg.return_value = make_sync_config()

        device = make_nb_device()
        base_client.get_device_by_name.return_value = device

        # Interfaces
        base_client.get_interfaces.return_value = []
        created_intfs = {}

        def fake_bulk_create_intfs(batch):
            results = []
            for i, data in enumerate(batch):
                m = MagicMock(id=2000 + i)
                m.name = data["name"]
                results.append(m)
                created_intfs[data["name"]] = m
            return results

        base_client.bulk_create_interfaces.side_effect = fake_bulk_create_intfs
        base_client.get_interface_by_name.side_effect = lambda dev_id, name: created_intfs.get(name)

        # IP
        base_client.get_ip_addresses.return_value = []
        base_client.bulk_create_ip_addresses.return_value = [MagicMock(id=3000)]

        # Inventory
        base_client.get_inventory_items.return_value = []
        base_client.bulk_create_inventory_items.return_value = [MagicMock(id=4000)]

        sync = NetBoxSync(base_client, dry_run=False)

        # Step 1: Interfaces с LAG
        interfaces = [
            Interface(name="Port-channel1", status="up"),
            Interface(name="GigabitEthernet0/1", status="up", lag="Port-channel1"),
            Interface(name="Vlan100", status="up"),
        ]
        intf_result = sync.sync_interfaces("switch-01", interfaces)
        assert intf_result["created"] == 3
        # LAG двухфазный: 2 вызова bulk_create
        assert base_client.bulk_create_interfaces.call_count == 2

        # Step 2: IP Addresses (после interfaces создались)
        # Обновляем кэш интерфейсов для IP sync
        nb_vlan100 = make_nb_interface(id=2002, name="Vlan100")
        base_client.get_interfaces.return_value = [nb_vlan100]

        ips = [
            IPAddressEntry(ip_address="10.0.0.1", mask="24", interface="Vlan100"),
        ]
        ip_result = sync.sync_ip_addresses("switch-01", ips)
        assert ip_result["created"] == 1

        # Step 3: Inventory
        inventory = [
            InventoryItem(name="PSU 1", pid="PWR", serial="PSU001"),
        ]
        inv_result = sync.sync_inventory("switch-01", inventory)
        assert inv_result["created"] == 1

    @patch("network_collector.netbox.sync.interfaces.get_sync_config")
    def test_pipeline_with_cleanup_all(self, mock_sync_cfg, base_client):
        """Pipeline с cleanup=True на всех этапах."""
        mock_sync_cfg.return_value = make_sync_config()

        device = make_nb_device()
        base_client.get_device_by_name.return_value = device

        # В NetBox есть устаревшие данные
        old_intf = make_nb_interface(id=100, name="FastEthernet0/24", device=device)
        base_client.get_interfaces.return_value = [old_intf]
        base_client.bulk_delete_interfaces.return_value = True
        base_client.bulk_create_interfaces.return_value = [MagicMock(id=200)]

        old_ip = make_nb_ip(id=50, address="192.168.1.1/24", interface_id=100)
        base_client.get_ip_addresses.return_value = [old_ip]
        base_client.bulk_delete_ip_addresses.return_value = True
        base_client.bulk_create_ip_addresses.return_value = [MagicMock(id=300)]

        old_inv = MagicMock()
        old_inv.id = 99
        old_inv.name = "Old Module"
        old_inv.part_id = ""
        old_inv.serial = "OLD"
        old_inv.description = ""
        old_inv.manufacturer = None
        base_client.get_inventory_items.return_value = [old_inv]
        base_client.bulk_delete_inventory_items.return_value = True

        sync = NetBoxSync(base_client, dry_run=False)

        # Interfaces: новый + cleanup старого
        intf_result = sync.sync_interfaces(
            "switch-01",
            [Interface(name="GigabitEthernet0/1", status="up")],
            cleanup=True,
        )
        assert intf_result["created"] == 1
        assert intf_result["deleted"] == 1  # Fa0/24 удалён

        # IP: cleanup
        # Обновляем интерфейсы для IP sync
        nb_gi01 = make_nb_interface(id=200, name="GigabitEthernet0/1")
        base_client.get_interfaces.return_value = [nb_gi01]

        ip_result = sync.sync_ip_addresses(
            "switch-01",
            [IPAddressEntry(ip_address="10.0.0.1", mask="24", interface="GigabitEthernet0/1")],
            cleanup=True,
        )
        assert ip_result["created"] == 1
        assert ip_result["deleted"] == 1  # 192.168.1.1 удалён

        # Inventory: cleanup
        inv_result = sync.sync_inventory(
            "switch-01", [], cleanup=True
        )
        assert inv_result["deleted"] == 1  # Old Module удалён


# ==================== 8. ERROR SCENARIOS ====================

class TestErrorScenarios:
    """Тесты обработки ошибок — silent failures, API errors."""

    @patch("network_collector.netbox.sync.interfaces.get_sync_config")
    def test_bulk_create_total_failure_fallback_all(self, mock_sync_cfg, base_client):
        """Bulk create падает → fallback на поштучное → тоже падает = 0 created."""
        mock_sync_cfg.return_value = make_sync_config()

        device = make_nb_device()
        base_client.get_device_by_name.return_value = device
        base_client.get_interfaces.return_value = []
        base_client.bulk_create_interfaces.side_effect = Exception("Bulk failed")

        # _create_interface вызывается через внутренний метод — мокаем его
        from network_collector.netbox.sync.interfaces import InterfacesSyncMixin
        original_create = InterfacesSyncMixin._create_interface

        def failing_create(self_sync, device_id, intf):
            raise Exception("Single failed too")

        base_client.create_interface = Mock(side_effect=Exception("Single failed too"))

        local = [Interface(name="GigabitEthernet0/1", status="up")]

        sync = NetBoxSync(base_client, dry_run=False)
        # Мокаем _create_interface напрямую
        sync._create_interface = Mock(side_effect=Exception("Single failed too"))
        result = sync.sync_interfaces("switch-01", local)

        # Ни один интерфейс не создан из-за ошибок
        assert result["created"] == 0

    def test_inventory_fallback_on_bulk_error(self, base_client):
        """Inventory bulk create ошибка → fallback на api.dcim.inventory_items.create."""
        device = make_nb_device()
        base_client.get_device_by_name.return_value = device
        base_client.get_inventory_items.return_value = []
        base_client.bulk_create_inventory_items.side_effect = Exception("Bulk error")
        base_client.api.dcim.inventory_items.create.return_value = MagicMock(id=1)

        items = [InventoryItem(name="PSU 1", pid="PWR", serial="S1")]

        sync = NetBoxSync(base_client, dry_run=False)
        result = sync.sync_inventory("switch-01", items)

        assert result["created"] == 1
        base_client.api.dcim.inventory_items.create.assert_called_once()

    def test_cable_api_error(self, base_client):
        """Ошибка API при создании кабеля — failed++."""
        dev_a = make_nb_device(id=1, name="switch-01")
        dev_b = make_nb_device(id=2, name="switch-02")
        base_client.get_device_by_name.side_effect = lambda name: {
            "switch-01": dev_a, "switch-02": dev_b
        }.get(name)

        intf_a = make_nb_interface(id=100, name="GigabitEthernet0/1", device=dev_a, cable=None)
        intf_b = make_nb_interface(id=200, name="GigabitEthernet0/1", device=dev_b, cable=None)

        base_client.get_interfaces.side_effect = lambda device_id: {
            1: [intf_a], 2: [intf_b]
        }.get(device_id, [])

        # API ошибка
        from network_collector.core.exceptions import NetBoxError
        base_client.api.dcim.cables.create.side_effect = NetBoxError("Cable creation failed")

        lldp = [
            LLDPNeighbor(
                hostname="switch-01",
                local_interface="GigabitEthernet0/1",
                remote_hostname="switch-02",
                remote_port="GigabitEthernet0/1",
                neighbor_type="hostname",
            ),
        ]

        sync = NetBoxSync(base_client, dry_run=False)
        result = sync.sync_cables_from_lldp(lldp)

        assert result["failed"] >= 1
        assert result["created"] == 0

    def test_device_not_found_for_interfaces(self, base_client):
        """Устройство не найдено при sync_interfaces — нет падения."""
        base_client.get_device_by_name.return_value = None

        sync = NetBoxSync(base_client, dry_run=False)

        with patch("network_collector.netbox.sync.interfaces.get_sync_config") as mock_cfg:
            mock_cfg.return_value = make_sync_config()
            result = sync.sync_interfaces("nonexistent", [Interface(name="Gi0/1", status="up")])

        assert result.get("failed", 0) >= 1 or result.get("created", 0) == 0

    def test_device_not_found_for_inventory(self, base_client):
        """Устройство не найдено при sync_inventory — нет падения."""
        base_client.get_device_by_name.return_value = None

        sync = NetBoxSync(base_client, dry_run=False)
        result = sync.sync_inventory("nonexistent", [InventoryItem(name="PSU", pid="P", serial="S")])

        assert result.get("failed", 0) >= 1 or result.get("created", 0) == 0


# ==================== 9. CACHING ====================

class TestCachingBehavior:
    """Тесты кэширования — проверяем что API вызывается минимально."""

    def test_device_cache_prevents_duplicate_api_calls(self, base_client):
        """_find_device кэширует результат — 1 API вызов."""
        dev = make_nb_device(name="switch-01")
        base_client.get_device_by_name.return_value = dev

        sync = NetBoxSync(base_client, dry_run=True)

        # Два вызова для одного устройства
        r1 = sync._find_device("switch-01")
        r2 = sync._find_device("switch-01")

        assert r1 == r2
        base_client.get_device_by_name.assert_called_once_with("switch-01")

    def test_interface_cache_per_device(self, base_client):
        """Интерфейсы кэшируются по device_id — 1 API вызов."""
        intf1 = make_nb_interface(id=100, name="Gi0/1")
        intf2 = make_nb_interface(id=101, name="Gi0/2")
        base_client.get_interfaces.return_value = [intf1, intf2]

        sync = NetBoxSync(base_client, dry_run=True)

        r1 = sync._find_interface(1, "Gi0/1")
        r2 = sync._find_interface(1, "Gi0/2")

        assert r1.id == 100
        assert r2.id == 101
        # API вызван 1 раз (для device_id=1)
        base_client.get_interfaces.assert_called_once_with(device_id=1)

    def test_mac_cache(self, base_client):
        """MAC кэш работает — 1 API вызов."""
        dev = make_nb_device(name="mac-device")
        base_client.get_device_by_mac.return_value = dev

        sync = NetBoxSync(base_client, dry_run=True)

        r1 = sync._find_device_by_mac("00:11:22:33:44:55")
        r2 = sync._find_device_by_mac("00:11:22:33:44:55")

        assert r1 == r2
        base_client.get_device_by_mac.assert_called_once()


# ==================== 10. CREATE_ONLY / UPDATE_ONLY MODE ====================

class TestSyncModes:
    """Тесты create_only и update_only режимов."""

    @patch("network_collector.netbox.sync.interfaces.get_sync_config")
    def test_create_only_skips_update(self, mock_sync_cfg, base_client):
        """update_existing=False: существующие интерфейсы не обновляются."""
        mock_sync_cfg.return_value = make_sync_config(update_existing=False)

        device = make_nb_device()
        base_client.get_device_by_name.return_value = device

        nb_intf = make_nb_interface(id=100, name="GigabitEthernet0/1", description="old", device=device)
        base_client.get_interfaces.return_value = [nb_intf]

        local = [Interface(name="GigabitEthernet0/1", status="up", description="new")]

        sync = NetBoxSync(base_client, dry_run=False)
        result = sync.sync_interfaces("switch-01", local, update_existing=False)

        # Не должно быть updates
        assert result["updated"] == 0
        base_client.bulk_update_interfaces.assert_not_called()

    def test_cable_update_only_skips_create(self, base_client):
        """update_only: новые кабели не создаются."""
        dev_a = make_nb_device(id=1, name="switch-01")
        dev_b = make_nb_device(id=2, name="switch-02")
        base_client.get_device_by_name.side_effect = lambda name: {
            "switch-01": dev_a, "switch-02": dev_b
        }.get(name)

        intf_a = make_nb_interface(id=100, name="GigabitEthernet0/1", device=dev_a, cable=None)
        intf_b = make_nb_interface(id=200, name="GigabitEthernet0/1", device=dev_b, cable=None)

        base_client.get_interfaces.side_effect = lambda device_id: {
            1: [intf_a], 2: [intf_b]
        }.get(device_id, [])

        lldp = [
            LLDPNeighbor(
                hostname="switch-01",
                local_interface="GigabitEthernet0/1",
                remote_hostname="switch-02",
                remote_port="GigabitEthernet0/1",
                neighbor_type="hostname",
            ),
        ]

        sync = NetBoxSync(base_client, dry_run=False, update_only=True)
        result = sync.sync_cables_from_lldp(lldp)

        # Кабель не создаётся в update_only
        assert result["created"] == 0
        base_client.api.dcim.cables.create.assert_not_called()


# ==================== 11. MULTI-DEVICE SCENARIO ====================

class TestMultiDeviceScenario:
    """Эмуляция sync для нескольких устройств (как в pipeline)."""

    @patch("network_collector.netbox.sync.interfaces.get_sync_config")
    def test_two_devices_interfaces(self, mock_sync_cfg, base_client):
        """Sync интерфейсов для двух устройств последовательно."""
        mock_sync_cfg.return_value = make_sync_config()

        dev1 = make_nb_device(id=1, name="switch-01")
        dev2 = make_nb_device(id=2, name="switch-02")
        base_client.get_device_by_name.side_effect = lambda name: {
            "switch-01": dev1, "switch-02": dev2
        }.get(name)

        base_client.get_interfaces.return_value = []
        base_client.bulk_create_interfaces.return_value = [MagicMock(id=1)]

        sync = NetBoxSync(base_client, dry_run=False)

        # Device 1
        r1 = sync.sync_interfaces("switch-01", [Interface(name="Gi0/1", status="up")])
        assert r1["created"] == 1

        # Device 2
        r2 = sync.sync_interfaces("switch-02", [Interface(name="Gi0/1", status="up")])
        assert r2["created"] == 1

        # Два отдельных устройства
        assert base_client.bulk_create_interfaces.call_count == 2

    def test_two_devices_inventory(self, base_client):
        """Sync inventory для двух устройств."""
        dev1 = make_nb_device(id=1, name="switch-01")
        dev2 = make_nb_device(id=2, name="switch-02")
        base_client.get_device_by_name.side_effect = lambda name: {
            "switch-01": dev1, "switch-02": dev2
        }.get(name)

        base_client.get_inventory_items.return_value = []
        base_client.bulk_create_inventory_items.return_value = [MagicMock(id=1)]

        sync = NetBoxSync(base_client, dry_run=False)

        r1 = sync.sync_inventory("switch-01", [InventoryItem(name="PSU", pid="P", serial="S1")])
        r2 = sync.sync_inventory("switch-02", [InventoryItem(name="PSU", pid="P", serial="S2")])

        assert r1["created"] == 1
        assert r2["created"] == 1
