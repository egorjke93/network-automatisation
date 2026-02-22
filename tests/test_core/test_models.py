"""
Тесты для Data Models.

Проверяет:
- Создание из словарей (from_dict)
- Сериализация в словари (to_dict)
- Обработка альтернативных имён полей
- Значения по умолчанию
"""

import pytest

from network_collector.core.models import (
    Interface,
    MACEntry,
    LLDPNeighbor,
    InventoryItem,
    IPAddressEntry,
    DeviceInfo,
    InterfaceStatus,
    SwitchportMode,
    NeighborType,
    interfaces_from_dicts,
    interfaces_to_dicts,
    mac_entries_from_dicts,
    neighbors_from_dicts,
    inventory_from_dicts,
)


class TestInterface:
    """Тесты модели Interface."""

    def test_from_dict_basic(self):
        """Базовое создание из словаря."""
        data = {
            "interface": "GigabitEthernet0/1",
            "description": "Uplink",
            "status": "up",
            "ip_address": "10.0.0.1",
        }
        intf = Interface.from_dict(data)

        assert intf.name == "GigabitEthernet0/1"
        assert intf.description == "Uplink"
        assert intf.status == "up"
        assert intf.ip_address == "10.0.0.1"

    def test_from_dict_alternative_keys(self):
        """Создание с альтернативными ключами."""
        data = {
            "name": "Eth1/1",  # альтернатива "interface"
            "link_status": "down",  # альтернатива "status"
            "mac_address": "AA:BB:CC:DD:EE:FF",  # альтернатива "mac"
            "speed": "10 Gbit",
        }
        intf = Interface.from_dict(data)

        assert intf.name == "Eth1/1"
        assert intf.status == "down"
        assert intf.mac == "AA:BB:CC:DD:EE:FF"
        assert intf.speed == "10 Gbit"

    def test_from_dict_with_all_fields(self):
        """Создание со всеми полями."""
        data = {
            "interface": "TenGigabitEthernet1/0/1",
            "description": "Server",
            "status": "up",
            "ip_address": "192.168.1.1",
            "mac": "00:11:22:33:44:55",
            "speed": "10 Gbit",
            "duplex": "full",
            "mtu": "9000",
            "vlan": "100",
            "mode": "access",
            "port_type": "10g-sfp+",
            "media_type": "SFP-10GBase-SR",
            "hardware_type": "Ten Gigabit Ethernet",
            "lag": "Port-channel1",
            "hostname": "switch-01",
            "device_ip": "10.0.0.1",
        }
        intf = Interface.from_dict(data)

        assert intf.name == "TenGigabitEthernet1/0/1"
        assert intf.mtu == 9000
        assert intf.port_type == "10g-sfp+"
        assert intf.lag == "Port-channel1"

    def test_to_dict_excludes_empty(self):
        """to_dict исключает пустые значения."""
        intf = Interface(name="Gi0/1", description="Test")
        result = intf.to_dict()

        assert "name" in result
        assert "description" in result
        # Пустые поля не включаются
        assert "ip_address" not in result
        assert "mac" not in result

    def test_defaults(self):
        """Проверка значений по умолчанию."""
        intf = Interface(name="Gi0/1")

        assert intf.description == ""
        assert intf.status == "unknown"
        assert intf.mtu is None
        assert intf.mode == ""


class TestMACEntry:
    """Тесты модели MACEntry."""

    def test_from_dict_basic(self):
        """Базовое создание."""
        data = {
            "mac": "AA:BB:CC:DD:EE:FF",
            "interface": "Gi0/1",
            "vlan": "100",
        }
        entry = MACEntry.from_dict(data)

        assert entry.mac == "AA:BB:CC:DD:EE:FF"
        assert entry.interface == "Gi0/1"
        assert entry.vlan == "100"

    def test_from_dict_alternative_keys(self):
        """Альтернативные ключи (NTC формат)."""
        data = {
            "destination_address": "00:11:22:33:44:55",
            "destination_port": "Eth1/1",
            "vlan": "200",
            "type": "static",
        }
        entry = MACEntry.from_dict(data)

        assert entry.mac == "00:11:22:33:44:55"
        assert entry.interface == "Eth1/1"
        assert entry.mac_type == "static"

    def test_to_dict(self):
        """Сериализация в словарь."""
        entry = MACEntry(
            mac="AA:BB:CC:DD:EE:FF",
            interface="Gi0/1",
            vlan="100",
            hostname="switch-01",
        )
        result = entry.to_dict()

        assert result["mac"] == "AA:BB:CC:DD:EE:FF"
        assert result["hostname"] == "switch-01"


class TestLLDPNeighbor:
    """Тесты модели LLDPNeighbor."""

    def test_from_dict_basic(self):
        """Базовое создание."""
        data = {
            "local_interface": "Gi0/1",
            "remote_hostname": "switch-02",
            "remote_port": "Gi0/2",
            "protocol": "lldp",
        }
        neighbor = LLDPNeighbor.from_dict(data)

        assert neighbor.local_interface == "Gi0/1"
        assert neighbor.remote_hostname == "switch-02"
        assert neighbor.remote_port == "Gi0/2"
        assert neighbor.protocol == "lldp"

    def test_from_dict_alternative_keys(self):
        """Альтернативные ключи."""
        data = {
            "local_port": "Eth1/1",
            "neighbor": "router-01",
            "neighbor_port": "Eth1/2",
            "chassis_id": "AA:BB:CC:DD:EE:FF",
            "management_ip": "10.0.0.2",
        }
        neighbor = LLDPNeighbor.from_dict(data)

        assert neighbor.local_interface == "Eth1/1"
        assert neighbor.remote_hostname == "router-01"
        assert neighbor.remote_mac == "AA:BB:CC:DD:EE:FF"
        assert neighbor.remote_ip == "10.0.0.2"

    def test_neighbor_type_default(self):
        """Тип соседа по умолчанию."""
        neighbor = LLDPNeighbor(local_interface="Gi0/1")
        assert neighbor.neighbor_type == "unknown"


class TestInventoryItem:
    """Тесты модели InventoryItem."""

    def test_from_dict_basic(self):
        """Базовое создание."""
        data = {
            "name": "Chassis",
            "pid": "WS-C3750X-48P-S",
            "serial": "FDO1234X5YZ",
            "description": "48-Port PoE Switch",
        }
        item = InventoryItem.from_dict(data)

        assert item.name == "Chassis"
        assert item.pid == "WS-C3750X-48P-S"
        assert item.serial == "FDO1234X5YZ"

    def test_from_dict_alternative_keys(self):
        """Альтернативные ключи."""
        data = {
            "name": "SFP-1",
            "part_id": "SFP-10G-SR",
            "sn": "ABC123",
            "descr": "10G SR Transceiver",
        }
        item = InventoryItem.from_dict(data)

        assert item.pid == "SFP-10G-SR"
        assert item.serial == "ABC123"
        assert item.description == "10G SR Transceiver"

    def test_to_dict_excludes_empty(self):
        """to_dict исключает пустые поля."""
        item = InventoryItem(name="Module", serial="ABC")
        result = item.to_dict()

        assert "name" in result
        assert "serial" in result
        assert "pid" not in result  # пустой


class TestIPAddressEntry:
    """Тесты модели IPAddressEntry."""

    def test_from_dict_basic(self):
        """Базовое создание."""
        data = {
            "ip_address": "10.0.0.1",
            "interface": "Vlan100",
            "mask": "255.255.255.0",
        }
        ip = IPAddressEntry.from_dict(data)

        assert ip.ip_address == "10.0.0.1"
        assert ip.interface == "Vlan100"
        assert ip.mask == "255.255.255.0"

    def test_with_prefix_from_mask(self):
        """Вычисление префикса из маски."""
        ip = IPAddressEntry(
            ip_address="192.168.1.1",
            interface="Gi0/1",
            mask="255.255.255.0",
        )
        assert ip.with_prefix == "192.168.1.1/24"

    def test_with_prefix_from_cidr(self):
        """Префикс уже в IP."""
        ip = IPAddressEntry(
            ip_address="10.0.0.1/30",
            interface="Gi0/1",
        )
        assert ip.with_prefix == "10.0.0.1/30"

    def test_with_prefix_numeric_mask(self):
        """Числовая маска."""
        ip = IPAddressEntry(
            ip_address="172.16.0.1",
            interface="Lo0",
            mask="32",
        )
        assert ip.with_prefix == "172.16.0.1/32"

    def test_with_prefix_default(self):
        """Маска по умолчанию /32."""
        ip = IPAddressEntry(
            ip_address="8.8.8.8",
            interface="Null0",
        )
        assert ip.with_prefix == "8.8.8.8/32"


class TestDeviceInfo:
    """Тесты модели DeviceInfo."""

    def test_from_dict_basic(self):
        """Базовое создание."""
        data = {
            "hostname": "switch-01",
            "ip_address": "10.0.0.1",
            "platform": "cisco_ios",
            "model": "C2960-24TT-L",
        }
        device = DeviceInfo.from_dict(data)

        assert device.hostname == "switch-01"
        assert device.ip_address == "10.0.0.1"
        assert device.platform == "cisco_ios"
        assert device.model == "C2960-24TT-L"

    def test_from_dict_alternative_keys(self):
        """Альтернативные ключи."""
        data = {
            "name": "router-01",
            "host": "192.168.1.1",
            "hardware": "ISR4431",
            "serial_number": "FTX1234",
            "software_version": "16.9.4",
            "vendor": "Cisco",
        }
        device = DeviceInfo.from_dict(data)

        assert device.hostname == "router-01"
        assert device.ip_address == "192.168.1.1"
        assert device.model == "ISR4431"
        assert device.serial == "FTX1234"
        assert device.version == "16.9.4"
        assert device.manufacturer == "Cisco"


class TestEnums:
    """Тесты Enum классов."""

    def test_interface_status_values(self):
        """Значения InterfaceStatus."""
        assert InterfaceStatus.UP.value == "up"
        assert InterfaceStatus.DOWN.value == "down"
        assert InterfaceStatus.ADMIN_DOWN.value == "administratively down"

    def test_switchport_mode_values(self):
        """Значения SwitchportMode."""
        assert SwitchportMode.ACCESS.value == "access"
        assert SwitchportMode.TAGGED.value == "tagged"
        assert SwitchportMode.TAGGED_ALL.value == "tagged-all"

    def test_neighbor_type_values(self):
        """Значения NeighborType."""
        assert NeighborType.HOSTNAME.value == "hostname"
        assert NeighborType.MAC.value == "mac"
        assert NeighborType.IP.value == "ip"
        assert NeighborType.UNKNOWN.value == "unknown"


class TestBatchConversions:
    """Тесты batch конвертации."""

    def test_interfaces_from_dicts(self):
        """Конвертация списка словарей в список Interface."""
        data = [
            {"interface": "Gi0/1", "status": "up"},
            {"interface": "Gi0/2", "status": "down"},
        ]
        interfaces = interfaces_from_dicts(data)

        assert len(interfaces) == 2
        assert interfaces[0].name == "Gi0/1"
        assert interfaces[1].status == "down"

    def test_interfaces_to_dicts(self):
        """Конвертация списка Interface в список словарей."""
        interfaces = [
            Interface(name="Gi0/1", status="up"),
            Interface(name="Gi0/2", description="Server"),
        ]
        data = interfaces_to_dicts(interfaces)

        assert len(data) == 2
        assert data[0]["name"] == "Gi0/1"
        assert data[1]["description"] == "Server"

    def test_mac_entries_from_dicts(self):
        """Конвертация списка MAC."""
        data = [
            {"mac": "AA:BB:CC:DD:EE:FF", "interface": "Gi0/1"},
            {"mac": "11:22:33:44:55:66", "interface": "Gi0/2"},
        ]
        entries = mac_entries_from_dicts(data)

        assert len(entries) == 2
        assert entries[0].mac == "AA:BB:CC:DD:EE:FF"

    def test_neighbors_from_dicts(self):
        """Конвертация списка соседей."""
        data = [
            {"local_interface": "Gi0/1", "remote_hostname": "switch-02"},
        ]
        neighbors = neighbors_from_dicts(data)

        assert len(neighbors) == 1
        assert neighbors[0].remote_hostname == "switch-02"

    def test_inventory_from_dicts(self):
        """Конвертация списка inventory."""
        data = [
            {"name": "Chassis", "serial": "ABC"},
            {"name": "SFP-1", "pid": "SFP-10G-SR"},
        ]
        items = inventory_from_dicts(data)

        assert len(items) == 2
        assert items[0].serial == "ABC"
        assert items[1].pid == "SFP-10G-SR"


class TestInterfacePrefixLength:
    """Тесты поля prefix_length в Interface."""

    def test_from_dict_with_prefix_length(self):
        """Создание Interface с prefix_length."""
        data = {
            "interface": "Vlan30",
            "ip_address": "10.177.30.213",
            "prefix_length": "24",
            "status": "up",
        }
        intf = Interface.from_dict(data)

        assert intf.ip_address == "10.177.30.213"
        assert intf.prefix_length == "24"

    def test_from_dict_with_mask_alternative(self):
        """Создание Interface с mask (альтернативное имя)."""
        data = {
            "interface": "Vlan100",
            "ip_address": "192.168.1.1",
            "mask": "255.255.255.0",
        }
        intf = Interface.from_dict(data)

        assert intf.prefix_length == "255.255.255.0"

    def test_prefix_length_in_to_dict(self):
        """prefix_length включается в to_dict."""
        intf = Interface(name="Vlan30", ip_address="10.0.0.1", prefix_length="24")
        result = intf.to_dict()

        assert result.get("prefix_length") == "24"

    def test_prefix_length_empty_by_default(self):
        """prefix_length пустой по умолчанию."""
        intf = Interface(name="Gi0/1")
        assert intf.prefix_length == ""


class TestIPAddressEntryPrefixLength:
    """Тесты IPAddressEntry с prefix_length."""

    def test_from_dict_with_prefix_length(self):
        """Создание IPAddressEntry с prefix_length."""
        data = {
            "ip_address": "10.177.30.213",
            "interface": "Vlan30",
            "prefix_length": "24",
        }
        ip = IPAddressEntry.from_dict(data)

        assert ip.ip_address == "10.177.30.213"
        assert ip.mask == "24"  # prefix_length -> mask
        assert ip.with_prefix == "10.177.30.213/24"

    def test_with_prefix_uses_mask_correctly(self):
        """with_prefix корректно использует mask."""
        # Числовая маска
        ip1 = IPAddressEntry(ip_address="10.0.0.1", interface="Vlan10", mask="24")
        assert ip1.with_prefix == "10.0.0.1/24"

        # Dotted маска
        ip2 = IPAddressEntry(ip_address="192.168.1.1", interface="Vlan20", mask="255.255.255.0")
        assert ip2.with_prefix == "192.168.1.1/24"

        # Маска /16
        ip3 = IPAddressEntry(ip_address="172.16.0.1", interface="Vlan30", mask="16")
        assert ip3.with_prefix == "172.16.0.1/16"

    def test_with_prefix_fallback_to_32(self):
        """with_prefix возвращает /32 только если mask пустой."""
        ip = IPAddressEntry(ip_address="8.8.8.8", interface="Lo0", mask="")
        assert ip.with_prefix == "8.8.8.8/32"


class TestEdgeCases:
    """Тесты граничных случаев."""

    def test_empty_dict(self):
        """Создание из пустого словаря."""
        intf = Interface.from_dict({})
        assert intf.name == ""
        assert intf.status == "unknown"

    def test_none_values(self):
        """Обработка None значений."""
        data = {
            "interface": "Gi0/1",
            "description": None,
            "mtu": None,
        }
        intf = Interface.from_dict(data)
        assert intf.description == ""
        assert intf.mtu is None

    def test_mtu_string_to_int(self):
        """Конвертация MTU из строки."""
        data = {"interface": "Gi0/1", "mtu": "1500"}
        intf = Interface.from_dict(data)
        assert intf.mtu == 1500
        assert isinstance(intf.mtu, int)

    def test_vlan_int_to_string(self):
        """Конвертация VLAN из int."""
        data = {"interface": "Gi0/1", "vlan": 100}
        intf = Interface.from_dict(data)
        assert intf.vlan == "100"
        assert isinstance(intf.vlan, str)
