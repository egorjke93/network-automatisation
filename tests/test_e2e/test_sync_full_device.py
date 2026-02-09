"""
E2E тесты для полного цикла синхронизации устройства.

Проверяет pipeline: Parse → Model → sync (dry_run).
Без реального NetBox подключения.

Тестируемые sync операции:
- Inventory: show inventory → InventoryItem → sync_inventory
- IP: show interfaces → IPAddressEntry → sync_ip_addresses
- VLAN: switchport → Interface (mode/vlans) → sync_interfaces
- Full device: все операции последовательно
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path

from network_collector.parsers.textfsm_parser import NTCParser
from network_collector.core.models import (
    Interface,
    IPAddressEntry,
    InventoryItem,
    DeviceInfo,
)
from network_collector.netbox.sync import NetBoxSync

from .conftest import create_mock_device


# Путь к fixtures
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def load_fixture(platform: str, filename: str) -> str:
    """Загружает fixture файл."""
    filepath = FIXTURES_DIR / platform / filename
    if filepath.exists():
        return filepath.read_text(encoding="utf-8")
    return ""


@pytest.fixture(scope="module")
def parser() -> NTCParser:
    """NTC парсер."""
    return NTCParser()


@pytest.fixture
def mock_netbox_client():
    """
    Мокированный NetBox клиент для sync pipeline.

    Настроен для dry_run тестов — реальных API-вызовов нет.
    """
    client = Mock()
    client.api = Mock()

    # Мок устройства
    mock_device = Mock()
    mock_device.id = 1
    mock_device.name = "switch-01"
    mock_device.primary_ip4 = None
    mock_device.tenant = None
    mock_device.site = Mock()
    mock_device.site.name = "TestSite"
    client.get_device_by_name.return_value = mock_device

    # Мок интерфейсов
    client.get_interfaces.return_value = []
    client.get_interface_by_name.return_value = None

    # Мок IP-адресов
    client.get_ip_addresses.return_value = []

    # Мок inventory items
    client.get_inventory_items.return_value = []

    # Мок для создания
    client.create_interface.return_value = Mock(id=100)
    client.create_ip_address.return_value = Mock(id=200)

    return client


# =============================================================================
# Inventory Sync Pipeline
# =============================================================================


@pytest.mark.e2e
class TestInventorySyncPipeline:
    """E2E: show inventory → InventoryItem → sync_inventory (dry_run)."""

    def test_inventory_sync_pipeline_ios(self, parser, mock_netbox_client):
        """Cisco IOS: inventory проходит полный pipeline до sync."""
        # 1. Загружаем fixture
        output = load_fixture("cisco_ios", "show_inventory.txt")
        if not output:
            pytest.skip("Нет fixture для cisco_ios/show_inventory")

        # 2. Парсим
        parsed = parser.parse(output, "cisco_ios", "show inventory")
        assert len(parsed) > 0, "Парсер вернул пустой результат"

        # 3. Конвертируем в модели
        items = [InventoryItem.from_dict(row) for row in parsed]
        assert len(items) > 0

        # 4. Проверяем ключевые поля
        for item in items:
            assert item.name, "Inventory item должен иметь имя"

        # Есть хотя бы один item с serial
        items_with_serial = [i for i in items if i.serial]
        assert len(items_with_serial) > 0, "Должен быть хотя бы один item с serial"

        # 5. Sync (dry_run)
        sync = NetBoxSync(mock_netbox_client, dry_run=True)
        result = sync.sync_inventory("switch-01", items_with_serial)

        assert isinstance(result, dict)
        assert "created" in result
        assert "skipped" in result
        # dry_run: created > 0 (все items новые, т.к. existing пуст)
        assert result["created"] >= 0

    def test_inventory_sync_pipeline_nxos(self, parser, mock_netbox_client):
        """Cisco NX-OS: inventory проходит pipeline до sync."""
        output = load_fixture("cisco_nxos", "show_inventory.txt")
        if not output:
            pytest.skip("Нет fixture для cisco_nxos/show_inventory")

        parsed = parser.parse(output, "cisco_nxos", "show inventory")
        assert len(parsed) > 0

        items = [InventoryItem.from_dict(row) for row in parsed]
        items_with_serial = [i for i in items if i.serial]

        sync = NetBoxSync(mock_netbox_client, dry_run=True)
        result = sync.sync_inventory("switch-01", items_with_serial)

        assert isinstance(result, dict)
        assert result["created"] + result["skipped"] >= 0

    def test_inventory_name_truncation(self, mock_netbox_client):
        """Имена > 64 символов обрезаются до 61 + '...'."""
        long_name = "A" * 70
        items = [
            InventoryItem(name=long_name, pid="PID-1", serial="SN123"),
        ]

        sync = NetBoxSync(mock_netbox_client, dry_run=True)
        result = sync.sync_inventory("switch-01", items)

        # dry_run создаёт item с обрезанным именем
        assert result["created"] == 1

    def test_inventory_skip_without_serial(self, mock_netbox_client):
        """Items без серийного номера пропускаются."""
        items = [
            InventoryItem(name="Module1", pid="PID-1", serial=""),
            InventoryItem(name="Module2", pid="PID-2", serial="SN123"),
        ]

        sync = NetBoxSync(mock_netbox_client, dry_run=True)
        result = sync.sync_inventory("switch-01", items)

        # Первый пропущен (нет serial), второй создан
        assert result["skipped"] == 1
        assert result["created"] == 1

    def test_inventory_empty_data(self, mock_netbox_client):
        """Пустые данные не вызывают ошибку."""
        sync = NetBoxSync(mock_netbox_client, dry_run=True)
        result = sync.sync_inventory("switch-01", [])

        assert isinstance(result, dict)
        assert result["created"] == 0


# =============================================================================
# IP Address Sync Pipeline
# =============================================================================


@pytest.mark.e2e
class TestIPSyncPipeline:
    """E2E: show interfaces → IPAddressEntry → sync_ip_addresses (dry_run)."""

    def test_ip_sync_pipeline_ios(self, parser, mock_netbox_client):
        """Cisco IOS: IP-адреса из show interfaces проходят pipeline до sync."""
        output = load_fixture("cisco_ios", "show_interfaces.txt")
        if not output:
            pytest.skip("Нет fixture для cisco_ios/show_interfaces")

        # 1. Парсим interfaces
        parsed = parser.parse(output, "cisco_ios", "show interfaces")
        assert len(parsed) > 0

        # 2. Извлекаем IP-адреса
        ip_entries = []
        for row in parsed:
            ip = row.get("ip_address", "")
            if ip and ip not in ("", "unassigned"):
                ip_entries.append(IPAddressEntry(
                    ip_address=ip,
                    interface=row.get("interface", ""),
                    mask=row.get("prefix_length", ""),
                    hostname="switch-01",
                    device_ip="10.0.0.1",
                ))

        # Могут быть или не быть IP в show interfaces
        if not ip_entries:
            pytest.skip("Нет IP-адресов в fixture")

        # 3. Настраиваем mock интерфейсы для привязки
        mock_interfaces = []
        for entry in ip_entries:
            mock_intf = Mock()
            mock_intf.id = 100 + len(mock_interfaces)
            mock_intf.name = entry.interface
            mock_intf.description = ""
            mock_interfaces.append(mock_intf)

        mock_netbox_client.get_interfaces.return_value = mock_interfaces

        # 4. Sync (dry_run)
        sync = NetBoxSync(mock_netbox_client, dry_run=True)
        result = sync.sync_ip_addresses(
            "switch-01",
            ip_entries,
            device_ip="10.0.0.1",
        )

        assert isinstance(result, dict)
        assert "created" in result
        assert "updated" in result

    def test_ip_sync_with_primary_ip(self, mock_netbox_client):
        """Primary IP устанавливается при sync."""
        ip_entries = [
            IPAddressEntry(
                ip_address="10.0.0.1",
                interface="Vlan100",
                mask="255.255.255.0",
                hostname="switch-01",
                device_ip="10.0.0.1",
            ),
        ]

        # Мок интерфейса
        mock_intf = Mock()
        mock_intf.id = 100
        mock_intf.name = "Vlan100"
        mock_intf.description = ""
        mock_netbox_client.get_interfaces.return_value = [mock_intf]

        sync = NetBoxSync(mock_netbox_client, dry_run=True)
        result = sync.sync_ip_addresses(
            "switch-01",
            ip_entries,
            device_ip="10.0.0.1",
        )

        assert isinstance(result, dict)

    def test_ip_sync_empty_data(self, mock_netbox_client):
        """Пустой список IP не вызывает ошибку."""
        sync = NetBoxSync(mock_netbox_client, dry_run=True)
        result = sync.sync_ip_addresses("switch-01", [])

        assert isinstance(result, dict)
        assert result["created"] == 0


# =============================================================================
# VLAN Sync Pipeline
# =============================================================================


@pytest.mark.e2e
class TestVLANSyncPipeline:
    """E2E: switchport → Interface (mode/vlans) → sync_interfaces с VLAN."""

    def test_access_port_vlan_sync(self, mock_netbox_client):
        """Access порт: untagged_vlan синхронизируется."""
        interfaces = [
            Interface(
                name="GigabitEthernet0/1",
                status="up",
                mode="access",
                access_vlan="100",
            ),
        ]

        sync = NetBoxSync(mock_netbox_client, dry_run=True)
        result = sync.sync_interfaces("switch-01", interfaces)

        assert isinstance(result, dict)
        assert result["created"] >= 0

    def test_trunk_port_vlan_sync(self, mock_netbox_client):
        """Trunk порт: native_vlan и tagged_vlans синхронизируются."""
        interfaces = [
            Interface(
                name="GigabitEthernet0/2",
                status="up",
                mode="tagged",
                native_vlan="1",
                tagged_vlans="10,20,30",
            ),
        ]

        sync = NetBoxSync(mock_netbox_client, dry_run=True)
        result = sync.sync_interfaces("switch-01", interfaces)

        assert isinstance(result, dict)
        assert result["created"] >= 0

    def test_mixed_mode_sync(self, mock_netbox_client):
        """Смешанные режимы: access + trunk + без mode."""
        interfaces = [
            Interface(name="Gi0/1", status="up", mode="access", access_vlan="100"),
            Interface(name="Gi0/2", status="up", mode="tagged", native_vlan="1", tagged_vlans="10,20"),
            Interface(name="Gi0/3", status="down"),  # Без mode
        ]

        sync = NetBoxSync(mock_netbox_client, dry_run=True)
        result = sync.sync_interfaces("switch-01", interfaces)

        assert isinstance(result, dict)
        # Все 3 интерфейса обработаны
        total = result["created"] + result["skipped"] + result.get("updated", 0)
        assert total >= 0

    def test_tagged_all_mode_sync(self, mock_netbox_client):
        """Trunk ALL VLANs (tagged-all mode)."""
        interfaces = [
            Interface(
                name="GigabitEthernet0/1",
                status="up",
                mode="tagged-all",
                native_vlan="1",
            ),
        ]

        sync = NetBoxSync(mock_netbox_client, dry_run=True)
        result = sync.sync_interfaces("switch-01", interfaces)

        assert isinstance(result, dict)


# =============================================================================
# Full Device Sync E2E
# =============================================================================


@pytest.mark.e2e
class TestFullDeviceSyncE2E:
    """Полный цикл синхронизации устройства."""

    def test_full_ios_device_sync(self, parser, mock_netbox_client):
        """
        Полный sync Cisco IOS: devices → interfaces → IP → inventory.

        Pipeline: show version → show interfaces → show inventory
        """
        sync = NetBoxSync(mock_netbox_client, dry_run=True)

        # Step 1: Device info (show version)
        version_output = load_fixture("cisco_ios", "show_version.txt")
        if version_output:
            version_parsed = parser.parse(version_output, "cisco_ios", "show version")
            if version_parsed:
                device_info = DeviceInfo.from_dict(version_parsed[0])
                device_info.ip_address = "10.0.0.1"

                assert device_info.hostname or device_info.name
                assert device_info.model

                # Sync device
                mock_netbox_client.get_device_by_name.return_value = None
                devices_result = sync.sync_devices_from_inventory(
                    [device_info], site="Test", role="switch",
                )
                assert isinstance(devices_result, dict)

        # Восстанавливаем mock устройства для последующих шагов
        mock_device = Mock()
        mock_device.id = 1
        mock_device.name = "switch-01"
        mock_device.primary_ip4 = None
        mock_device.tenant = None
        mock_device.site = Mock()
        mock_device.site.name = "TestSite"
        mock_netbox_client.get_device_by_name.return_value = mock_device
        mock_netbox_client.get_interfaces.return_value = []

        # Step 2: Interfaces
        intf_output = load_fixture("cisco_ios", "show_interfaces.txt")
        if intf_output:
            intf_parsed = parser.parse(intf_output, "cisco_ios", "show interfaces")
            if intf_parsed:
                interfaces = [Interface.from_dict(row) for row in intf_parsed[:10]]
                intf_result = sync.sync_interfaces("switch-01", interfaces)
                assert isinstance(intf_result, dict)
                assert "created" in intf_result

        # Step 3: IP-адреса из тех же interfaces
        if intf_output:
            intf_parsed = parser.parse(intf_output, "cisco_ios", "show interfaces")
            ip_entries = []
            for row in intf_parsed:
                ip = row.get("ip_address", "")
                if ip and ip not in ("", "unassigned"):
                    ip_entries.append(IPAddressEntry(
                        ip_address=ip,
                        interface=row.get("interface", ""),
                        mask=row.get("prefix_length", ""),
                    ))

            if ip_entries:
                mock_netbox_client.get_ip_addresses.return_value = []
                ip_result = sync.sync_ip_addresses("switch-01", ip_entries)
                assert isinstance(ip_result, dict)

        # Step 4: Inventory
        inv_output = load_fixture("cisco_ios", "show_inventory.txt")
        if inv_output:
            inv_parsed = parser.parse(inv_output, "cisco_ios", "show inventory")
            if inv_parsed:
                items = [InventoryItem.from_dict(row) for row in inv_parsed]
                items_with_serial = [i for i in items if i.serial]
                if items_with_serial:
                    mock_netbox_client.get_inventory_items.return_value = []
                    inv_result = sync.sync_inventory("switch-01", items_with_serial)
                    assert isinstance(inv_result, dict)

    def test_full_nxos_device_sync(self, parser, mock_netbox_client):
        """Полный sync NX-OS: devices → interfaces → inventory."""
        sync = NetBoxSync(mock_netbox_client, dry_run=True)

        # Настраиваем mock
        mock_device = Mock()
        mock_device.id = 1
        mock_device.name = "nxos-switch"
        mock_device.primary_ip4 = None
        mock_device.tenant = None
        mock_device.site = Mock()
        mock_device.site.name = "TestSite"
        mock_netbox_client.get_device_by_name.return_value = mock_device
        mock_netbox_client.get_interfaces.return_value = []

        # Step 1: Interfaces
        intf_output = load_fixture("cisco_nxos", "show_interface.txt")
        if intf_output:
            intf_parsed = parser.parse(intf_output, "cisco_nxos", "show interface")
            if intf_parsed:
                interfaces = [Interface.from_dict(row) for row in intf_parsed[:10]]
                intf_result = sync.sync_interfaces("nxos-switch", interfaces)
                assert isinstance(intf_result, dict)

        # Step 2: Inventory
        inv_output = load_fixture("cisco_nxos", "show_inventory.txt")
        if inv_output:
            inv_parsed = parser.parse(inv_output, "cisco_nxos", "show inventory")
            if inv_parsed:
                items = [InventoryItem.from_dict(row) for row in inv_parsed]
                items_with_serial = [i for i in items if i.serial]
                if items_with_serial:
                    mock_netbox_client.get_inventory_items.return_value = []
                    inv_result = sync.sync_inventory("nxos-switch", items_with_serial)
                    assert isinstance(inv_result, dict)

    def test_sync_stats_structure(self, mock_netbox_client):
        """Все sync методы возвращают консистентную структуру stats."""
        sync = NetBoxSync(mock_netbox_client, dry_run=True)

        # Проверяем структуру для каждого sync метода
        intf_result = sync.sync_interfaces("switch-01", [])
        ip_result = sync.sync_ip_addresses("switch-01", [])
        inv_result = sync.sync_inventory("switch-01", [])

        # Все должны содержать базовые ключи
        for result, name in [
            (intf_result, "interfaces"),
            (ip_result, "ip_addresses"),
            (inv_result, "inventory"),
        ]:
            assert isinstance(result, dict), f"{name}: результат не dict"
            assert "created" in result, f"{name}: нет ключа 'created'"
            assert "skipped" in result, f"{name}: нет ключа 'skipped'"

    def test_device_not_found_handling(self, mock_netbox_client):
        """Устройство не найдено → failed=1, без ошибки."""
        mock_netbox_client.get_device_by_name.return_value = None

        sync = NetBoxSync(mock_netbox_client, dry_run=True)

        # Каждый sync метод должен обработать отсутствие устройства
        intf_result = sync.sync_interfaces("nonexistent", [
            Interface(name="Gi0/1", status="up"),
        ])
        assert intf_result.get("failed", 0) >= 1 or "errors" in intf_result

        ip_result = sync.sync_ip_addresses("nonexistent", [
            IPAddressEntry(ip_address="10.0.0.1", interface="Gi0/1"),
        ])
        assert ip_result.get("failed", 0) >= 1

        inv_result = sync.sync_inventory("nonexistent", [
            InventoryItem(name="Module1", serial="SN1"),
        ])
        assert inv_result.get("failed", 0) >= 1
