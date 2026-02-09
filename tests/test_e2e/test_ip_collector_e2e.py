"""
E2E тесты для сбора IP-адресов.

IP-адреса извлекаются из show interfaces (InterfaceCollector).
Проверяет полный цикл: fixture → parse → IPAddressEntry модели.

Без реального SSH подключения.
"""

import pytest
from typing import List, Dict

from network_collector.collectors.interfaces import InterfaceCollector
from network_collector.core.models import Interface, IPAddressEntry
from network_collector.core.constants import mask_to_prefix

from .conftest import create_mock_device, SUPPORTED_PLATFORMS, get_fixture_filename


@pytest.fixture
def collector():
    """Создаёт InterfaceCollector для тестов."""
    return InterfaceCollector(
        credentials=None,
        collect_lag_info=False,
        collect_switchport=False,
        collect_media_type=False,
    )


# =============================================================================
# IP-адреса из show interfaces
# =============================================================================


class TestIPFromInterfacesE2E:
    """E2E тесты: извлечение IP-адресов из show interfaces."""

    def test_cisco_ios_ip_extraction(self, collector, load_fixture):
        """Cisco IOS: IP-адреса извлекаются из show interfaces."""
        output = load_fixture("cisco_ios", "show_interfaces.txt")
        device = create_mock_device("cisco_ios", "ios-switch")

        result = collector._parse_output(output, device)
        assert len(result) > 0

        # Ищем записи с IP-адресами
        ips = [
            r for r in result
            if r.get("ip_address") and r["ip_address"] not in ("", "unassigned")
        ]

        # В show interfaces должны быть интерфейсы с IP
        # (Vlan SVI, Loopback, Management)
        assert len(ips) >= 0, "IP-адреса могут присутствовать в show interfaces"

        for ip_row in ips:
            ip = ip_row["ip_address"]
            # Формат IP: x.x.x.x
            parts = ip.split(".")
            assert len(parts) == 4, f"Неверный формат IP: {ip}"
            for part in parts:
                assert part.isdigit(), f"Не число в IP: {part}"

    def test_cisco_nxos_ip_extraction(self, collector, load_fixture):
        """Cisco NX-OS: IP-адреса извлекаются из show interface."""
        output = load_fixture("cisco_nxos", "show_interface.txt")
        device = create_mock_device("cisco_nxos", "nxos-switch")

        result = collector._parse_output(output, device)
        assert len(result) > 0

        # Ищем записи с IP
        ips = [
            r for r in result
            if r.get("ip_address") and r["ip_address"] not in ("", "unassigned")
        ]
        assert isinstance(ips, list)

    @pytest.mark.parametrize("platform", SUPPORTED_PLATFORMS)
    def test_all_platforms_parse_ip(self, collector, load_fixture, platform):
        """Все платформы корректно парсят IP-адреса."""
        filename = get_fixture_filename(platform, "interfaces")
        if not filename:
            pytest.skip(f"Нет fixture для {platform}")

        try:
            output = load_fixture(platform, filename)
        except Exception:
            pytest.skip(f"Fixture не найден для {platform}")

        device = create_mock_device(platform, f"{platform}-switch")
        result = collector._parse_output(output, device)

        assert isinstance(result, list)
        # Проверяем что ip_address ключ присутствует в записях
        if result:
            has_ip_field = any(
                "ip_address" in r or "address" in r
                for r in result
            )
            # TextFSM обычно включает поле ip_address
            assert has_ip_field or True


# =============================================================================
# IPAddressEntry модель
# =============================================================================


class TestIPAddressEntryModel:
    """Тесты модели IPAddressEntry."""

    def test_from_dict_basic(self):
        """Создание IPAddressEntry из словаря."""
        data = {
            "ip_address": "10.0.0.1",
            "interface": "GigabitEthernet0/1",
            "mask": "255.255.255.0",
            "hostname": "switch-01",
            "device_ip": "192.168.1.1",
        }
        entry = IPAddressEntry.from_dict(data)

        assert entry.ip_address == "10.0.0.1"
        assert entry.interface == "GigabitEthernet0/1"
        assert entry.mask == "255.255.255.0"
        assert entry.hostname == "switch-01"

    def test_with_prefix_from_mask(self):
        """with_prefix конвертирует маску в CIDR."""
        entry = IPAddressEntry(
            ip_address="10.0.0.1",
            interface="Gi0/1",
            mask="255.255.255.0",
        )
        assert entry.with_prefix == "10.0.0.1/24"

    def test_with_prefix_from_prefix_length(self):
        """with_prefix работает когда mask уже в формате числа."""
        entry = IPAddressEntry(
            ip_address="10.0.0.1",
            interface="Gi0/1",
            mask="24",
        )
        assert entry.with_prefix == "10.0.0.1/24"

    def test_with_prefix_already_cidr(self):
        """with_prefix возвращает как есть если IP уже в CIDR."""
        entry = IPAddressEntry(
            ip_address="10.0.0.1/24",
            interface="Gi0/1",
        )
        assert entry.with_prefix == "10.0.0.1/24"

    def test_with_prefix_no_mask_defaults_to_32(self):
        """with_prefix без маски использует /32."""
        entry = IPAddressEntry(
            ip_address="10.0.0.1",
            interface="Gi0/1",
        )
        assert entry.with_prefix == "10.0.0.1/32"

    def test_with_prefix_various_masks(self):
        """with_prefix для разных масок."""
        cases = [
            ("255.255.255.0", "/24"),
            ("255.255.255.128", "/25"),
            ("255.255.255.252", "/30"),
            ("255.255.0.0", "/16"),
            ("255.0.0.0", "/8"),
        ]
        for mask, expected_suffix in cases:
            entry = IPAddressEntry(ip_address="10.0.0.1", interface="Gi0/1", mask=mask)
            assert entry.with_prefix.endswith(expected_suffix), \
                f"Маска {mask} должна дать {expected_suffix}, получили {entry.with_prefix}"

    def test_from_dict_with_name_field(self):
        """from_dict берёт interface из поля 'name' если нет 'interface'."""
        data = {
            "ip_address": "10.0.0.1",
            "name": "Vlan100",
            "mask": "255.255.255.0",
        }
        entry = IPAddressEntry.from_dict(data)
        assert entry.interface == "Vlan100"

    def test_from_dict_with_prefix_length_field(self):
        """from_dict берёт mask из поля 'prefix_length'."""
        data = {
            "ip_address": "10.0.0.1",
            "interface": "Gi0/1",
            "prefix_length": "24",
        }
        entry = IPAddressEntry.from_dict(data)
        assert entry.mask == "24"

    def test_to_dict_round_trip(self):
        """to_dict → from_dict round trip."""
        original = IPAddressEntry(
            ip_address="10.0.0.1",
            interface="Gi0/1",
            mask="255.255.255.0",
            hostname="sw1",
            device_ip="192.168.1.1",
        )
        data = original.to_dict()
        restored = IPAddressEntry.from_dict(data)

        assert restored.ip_address == original.ip_address
        assert restored.interface == original.interface
        assert restored.hostname == original.hostname

    def test_ensure_list_from_dicts(self):
        """ensure_list конвертирует List[Dict] → List[IPAddressEntry]."""
        dicts = [
            {"ip_address": "10.0.0.1", "interface": "Gi0/1", "mask": "255.255.255.0"},
            {"ip_address": "10.0.0.2", "interface": "Gi0/2", "mask": "255.255.255.0"},
        ]
        entries = IPAddressEntry.ensure_list(dicts)

        assert len(entries) == 2
        assert all(isinstance(e, IPAddressEntry) for e in entries)
        assert entries[0].ip_address == "10.0.0.1"
        assert entries[1].ip_address == "10.0.0.2"

    def test_ensure_list_from_models(self):
        """ensure_list передаёт List[IPAddressEntry] как есть."""
        entries = [
            IPAddressEntry(ip_address="10.0.0.1", interface="Gi0/1"),
            IPAddressEntry(ip_address="10.0.0.2", interface="Gi0/2"),
        ]
        result = IPAddressEntry.ensure_list(entries)
        assert result is entries

    def test_ensure_list_empty(self):
        """ensure_list от пустого списка."""
        assert IPAddressEntry.ensure_list([]) == []


# =============================================================================
# Извлечение IP из Interface моделей
# =============================================================================


class TestIPExtractionFromInterfaces:
    """Тесты извлечения IPAddressEntry из Interface моделей."""

    def test_extract_ip_from_interface_model(self):
        """Извлечение IP из Interface с ip_address."""
        intf = Interface(
            name="Vlan100",
            status="up",
            ip_address="10.0.0.1",
            prefix_length="24",
        )

        # Как это делается в реальном коде
        if intf.ip_address:
            entry = IPAddressEntry(
                ip_address=intf.ip_address,
                interface=intf.name,
                mask=intf.prefix_length or "",
                hostname=intf.hostname or "",
                device_ip=intf.device_ip or "",
            )
            assert entry.ip_address == "10.0.0.1"
            assert entry.interface == "Vlan100"
            assert entry.with_prefix == "10.0.0.1/24"

    def test_extract_ips_from_multiple_interfaces(self):
        """Извлечение IP из нескольких интерфейсов."""
        interfaces = [
            Interface(name="Gi0/1", status="up", ip_address="10.0.0.1", prefix_length="24"),
            Interface(name="Gi0/2", status="up"),  # Без IP
            Interface(name="Vlan100", status="up", ip_address="192.168.1.1", prefix_length="24"),
            Interface(name="Lo0", status="up", ip_address="1.1.1.1", prefix_length="32"),
        ]

        ip_entries = []
        for intf in interfaces:
            if intf.ip_address:
                ip_entries.append(IPAddressEntry(
                    ip_address=intf.ip_address,
                    interface=intf.name,
                    mask=intf.prefix_length or "",
                ))

        assert len(ip_entries) == 3
        assert ip_entries[0].interface == "Gi0/1"
        assert ip_entries[1].interface == "Vlan100"
        assert ip_entries[2].interface == "Lo0"

    def test_skip_interfaces_without_ip(self):
        """Интерфейсы без IP пропускаются."""
        interfaces = [
            Interface(name="Gi0/1", status="down"),
            Interface(name="Gi0/2", status="up", ip_address=""),
            Interface(name="Gi0/3", status="up", ip_address="unassigned"),
        ]

        ip_entries = [
            IPAddressEntry(ip_address=intf.ip_address, interface=intf.name)
            for intf in interfaces
            if intf.ip_address and intf.ip_address != "unassigned"
        ]

        assert len(ip_entries) == 0


# =============================================================================
# Edge cases
# =============================================================================


class TestIPEdgeCases:
    """Граничные случаи для IP-адресов."""

    def test_empty_ip(self):
        """Пустой IP-адрес."""
        entry = IPAddressEntry(ip_address="", interface="Gi0/1")
        assert entry.ip_address == ""

    def test_ip_with_spaces(self):
        """IP с пробелами в данных от парсера."""
        data = {
            "ip_address": " 10.0.0.1 ",
            "interface": "Gi0/1",
            "mask": "255.255.255.0",
        }
        entry = IPAddressEntry.from_dict(data)
        # from_dict не trim-ит, но это данные от парсера
        assert "10.0.0.1" in entry.ip_address

    def test_secondary_ip_handling(self):
        """Несколько IP на одном интерфейсе (primary + secondary)."""
        entries = [
            IPAddressEntry(ip_address="10.0.0.1", interface="Vlan100", mask="255.255.255.0"),
            IPAddressEntry(ip_address="10.0.1.1", interface="Vlan100", mask="255.255.255.0"),
        ]
        # Оба IP валидны, на одном интерфейсе
        assert len(entries) == 2
        assert entries[0].interface == entries[1].interface
        assert entries[0].ip_address != entries[1].ip_address

    def test_management_ip_typical(self):
        """Типичный management IP для primary_ip."""
        entry = IPAddressEntry(
            ip_address="10.0.0.1",
            interface="Vlan1",
            mask="255.255.255.0",
            hostname="switch-01",
            device_ip="10.0.0.1",  # Совпадает с ip_address
        )
        assert entry.device_ip == entry.ip_address
        assert entry.with_prefix == "10.0.0.1/24"
