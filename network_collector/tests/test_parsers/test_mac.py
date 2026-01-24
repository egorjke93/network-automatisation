"""
Тесты парсинга MAC-таблиц для разных платформ.

Использует фикстуры из tests/fixtures/ для проверки
парсинга реального вывода команд.
"""

import pytest
from ntc_templates.parse import parse_output


class TestCiscoIOSMacParsing:
    """Тесты парсинга MAC-таблицы Cisco IOS."""

    def test_parse_mac_address_table(self, load_fixture):
        """Парсинг show mac address-table."""
        output = load_fixture("cisco_ios", "show_mac_address_table.txt")

        result = parse_output(
            platform="cisco_ios",
            command="show mac address-table",
            data=output,
        )

        assert isinstance(result, list)
        assert len(result) > 0

        # Проверяем структуру записи
        entry = result[0]
        assert "destination_address" in entry or "mac" in entry
        assert "destination_port" in entry or "ports" in entry

    def test_dynamic_mac_entries(self, load_fixture):
        """Проверка DYNAMIC записей."""
        output = load_fixture("cisco_ios", "show_mac_address_table.txt")

        result = parse_output(
            platform="cisco_ios",
            command="show mac address-table",
            data=output,
        )

        # Находим динамические записи
        dynamic_entries = [
            e for e in result
            if e.get("type", "").upper() == "DYNAMIC"
        ]

        assert len(dynamic_entries) > 0

    def test_static_mac_entries(self, load_fixture):
        """Проверка STATIC записей (CPU, SVI)."""
        output = load_fixture("cisco_ios", "show_mac_address_table.txt")

        result = parse_output(
            platform="cisco_ios",
            command="show mac address-table",
            data=output,
        )

        # Находим статические записи
        static_entries = [
            e for e in result
            if e.get("type", "").upper() == "STATIC"
        ]

        assert len(static_entries) > 0

    def test_vlan_field_present(self, load_fixture):
        """VLAN должен присутствовать в записях."""
        output = load_fixture("cisco_ios", "show_mac_address_table.txt")

        result = parse_output(
            platform="cisco_ios",
            command="show mac address-table",
            data=output,
        )

        # NTC парсит VLAN в поле "vlan_id"
        entries_with_vlan = [
            e for e in result
            if e.get("vlan_id") and str(e.get("vlan_id", "")) not in ("All", "")
        ]

        assert len(entries_with_vlan) > 0


class TestCiscoNXOSMacParsing:
    """Тесты парсинга MAC-таблицы Cisco NX-OS."""

    def test_parse_mac_address_table(self, load_fixture):
        """Парсинг show mac address-table."""
        output = load_fixture("cisco_nxos", "show_mac_address_table.txt")

        result = parse_output(
            platform="cisco_nxos",
            command="show mac address-table",
            data=output,
        )

        assert isinstance(result, list)
        assert len(result) > 0

    def test_port_channel_entries(self, load_fixture):
        """Проверка записей на Port-channel."""
        output = load_fixture("cisco_nxos", "show_mac_address_table.txt")

        result = parse_output(
            platform="cisco_nxos",
            command="show mac address-table",
            data=output,
        )

        # Находим записи на Po
        po_entries = [
            e for e in result
            if "Po" in str(e.get("ports", e.get("destination_port", "")))
        ]

        assert len(po_entries) > 0

    def test_vlan_10_entries(self, load_fixture):
        """Проверка записей в VLAN 10."""
        output = load_fixture("cisco_nxos", "show_mac_address_table.txt")

        result = parse_output(
            platform="cisco_nxos",
            command="show mac address-table",
            data=output,
        )

        # NTC парсит VLAN в поле "vlan_id"
        vlan_10_entries = [
            e for e in result
            if str(e.get("vlan_id", "")) == "10"
        ]

        assert len(vlan_10_entries) > 0


class TestMacNormalization:
    """Тесты нормализации MAC-адресов."""

    def test_mac_format_cisco(self):
        """Нормализация в формат Cisco (xxxx.xxxx.xxxx)."""
        from network_collector.core.constants import normalize_mac_cisco

        assert normalize_mac_cisco("00:11:22:33:44:55") == "0011.2233.4455"
        assert normalize_mac_cisco("00-11-22-33-44-55") == "0011.2233.4455"
        assert normalize_mac_cisco("001122334455") == "0011.2233.4455"

    def test_mac_format_ieee(self):
        """Нормализация в формат IEEE (xx:xx:xx:xx:xx:xx)."""
        from network_collector.core.constants import normalize_mac_ieee

        assert normalize_mac_ieee("0011.2233.4455") == "00:11:22:33:44:55"
        assert normalize_mac_ieee("00-11-22-33-44-55") == "00:11:22:33:44:55"
        assert normalize_mac_ieee("001122334455") == "00:11:22:33:44:55"

    def test_mac_format_netbox(self):
        """Нормализация в формат NetBox (XX:XX:XX:XX:XX:XX)."""
        from network_collector.core.constants import normalize_mac_netbox

        assert normalize_mac_netbox("0011.2233.4455") == "00:11:22:33:44:55"
        assert normalize_mac_netbox("00-11-22-33-44-55") == "00:11:22:33:44:55"


class TestMACNormalizer:
    """Тесты MACNormalizer из Domain Layer."""

    def test_normalize_dicts(self):
        """Нормализация списка записей."""
        from network_collector.core.domain import MACNormalizer

        normalizer = MACNormalizer(mac_format="ieee")

        raw_data = [
            {"mac": "0011.2233.4455", "vlan": "10", "interface": "Gi0/1"},
            {"mac": "aabb.ccdd.eeff", "vlan": "20", "interface": "Gi0/2"},
        ]

        result = normalizer.normalize_dicts(raw_data)

        assert result[0]["mac"] == "00:11:22:33:44:55"
        assert result[1]["mac"] == "aa:bb:cc:dd:ee:ff"

    def test_deduplicate(self):
        """Дедупликация по hostname+MAC+VLAN+interface."""
        from network_collector.core.domain import MACNormalizer

        normalizer = MACNormalizer()

        # deduplicate ключ: (hostname, mac, vlan, interface)
        data = [
            {"hostname": "sw1", "mac": "00:11:22:33:44:55", "vlan": "10", "interface": "Gi0/1"},
            {"hostname": "sw1", "mac": "00:11:22:33:44:55", "vlan": "10", "interface": "Gi0/1"},  # полный дубликат
            {"hostname": "sw1", "mac": "00:11:22:33:44:55", "vlan": "20", "interface": "Gi0/1"},  # другой VLAN
        ]

        result = normalizer.deduplicate(data)

        assert len(result) == 2  # 2 уникальных по полному ключу

    def test_filter_trunk_ports(self):
        """Фильтрация trunk портов."""
        from network_collector.core.domain import MACNormalizer

        normalizer = MACNormalizer()

        data = [
            {"mac": "00:11:22:33:44:55", "vlan": "10", "interface": "Gi0/1"},
            {"mac": "aa:bb:cc:dd:ee:ff", "vlan": "20", "interface": "Po1"},
        ]

        # Передаём множество trunk интерфейсов
        trunk_interfaces = {"Po1"}
        result = normalizer.filter_trunk_ports(data, trunk_interfaces)

        assert len(result) == 1
        assert result[0]["interface"] == "Gi0/1"

    def test_exclude_vlans(self):
        """Исключение VLAN из результата."""
        from network_collector.core.domain import MACNormalizer

        normalizer = MACNormalizer(exclude_vlans=[1, 999])

        data = [
            {"mac": "00:11:22:33:44:55", "vlan": "1", "interface": "Gi0/1"},
            {"mac": "aa:bb:cc:dd:ee:ff", "vlan": "10", "interface": "Gi0/2"},
            {"mac": "11:22:33:44:55:66", "vlan": "999", "interface": "Gi0/3"},
        ]

        result = normalizer.normalize_dicts(data)

        assert len(result) == 1
        assert result[0]["vlan"] == "10"
