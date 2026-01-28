"""
Тесты TextFSM шаблонов для QTech.
"""

import pytest
import textfsm
from pathlib import Path

# Путь к шаблонам и fixtures
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "qtech"


def parse_with_template(template_name: str, fixture_name: str) -> list:
    """Парсит fixture с помощью TextFSM шаблона."""
    template_path = TEMPLATES_DIR / template_name
    fixture_path = FIXTURES_DIR / fixture_name

    with open(template_path) as f:
        template = textfsm.TextFSM(f)

    with open(fixture_path) as f:
        output = f.read()

    result = template.ParseText(output)
    # Конвертируем в список словарей
    headers = template.header
    return [dict(zip(headers, row)) for row in result]


class TestQtechShowVersion:
    """Тесты show version."""

    def test_parse_version(self):
        """Парсинг show version."""
        result = parse_with_template(
            "qtech_show_version.textfsm",
            "show_version.txt"
        )

        print(f"Result: {result}")
        assert len(result) >= 1, "Должна быть хотя бы одна запись"

        entry = result[0]
        assert "MODEL" in entry
        assert "SERIAL" in entry
        assert "VERSION" in entry

        # Проверяем значения
        assert "QSW-6900-56F" in entry.get("MODEL", "")
        assert entry.get("SERIAL") == "G1S82H800078B"


class TestQtechShowInterface:
    """Тесты show interface."""

    def test_parse_interfaces(self):
        """Парсинг show interface."""
        result = parse_with_template(
            "qtech_show_interface.textfsm",
            "show_interface.txt"
        )

        print(f"Parsed {len(result)} interfaces")
        assert len(result) > 0, "Должны быть интерфейсы"

        # Проверяем первый интерфейс
        intf = result[0]
        print(f"First interface: {intf}")

        assert "INTERFACE" in intf
        assert "LINK_STATUS" in intf
        assert "ADDRESS" in intf

        # Проверяем значения
        assert "TFGigabitEthernet" in intf.get("INTERFACE", "")
        assert intf.get("LINK_STATUS") in ["UP", "DOWN"]


class TestQtechShowInterfaceStatus:
    """Тесты show interface status."""

    def test_parse_status(self):
        """Парсинг show interface status."""
        result = parse_with_template(
            "qtech_show_interface_status.textfsm",
            "show_interface_status.txt"
        )

        print(f"Parsed {len(result)} interfaces")
        assert len(result) > 0, "Должны быть интерфейсы"

        intf = result[0]
        print(f"First interface: {intf}")

        assert "INTERFACE" in intf
        assert "STATUS" in intf
        assert "VLAN" in intf
        assert "SPEED" in intf

        # Проверяем значения
        assert intf.get("STATUS") in ["up", "down", "disabled"]


class TestQtechShowInterfaceSwitchport:
    """Тесты show interface switchport."""

    def test_parse_switchport(self):
        """Парсинг show interface switchport."""
        result = parse_with_template(
            "qtech_show_interface_switchport.textfsm",
            "show_interface_switchport.txt"
        )

        print(f"Parsed {len(result)} interfaces")
        assert len(result) > 0, "Должны быть интерфейсы"

        intf = result[0]
        print(f"First interface: {intf}")

        assert "INTERFACE" in intf
        assert "SWITCHPORT" in intf
        assert "MODE" in intf


class TestQtechShowMacAddressTable:
    """Тесты show mac address-table."""

    def test_parse_mac(self):
        """Парсинг show mac address-table."""
        result = parse_with_template(
            "qtech_show_mac_address_table.textfsm",
            "show_mac_address_table.txt"
        )

        print(f"Parsed {len(result)} MAC entries")
        assert len(result) > 0, "Должны быть MAC записи"

        # Фильтруем CPU записи
        dynamic_macs = [m for m in result if m.get("TYPE") == "DYNAMIC"]
        print(f"Dynamic MACs: {len(dynamic_macs)}")

        if dynamic_macs:
            mac = dynamic_macs[0]
            print(f"First dynamic MAC: {mac}")

            assert "MAC" in mac
            assert "VLAN" in mac
            assert "INTERFACE" in mac


class TestQtechShowLldpNeighborsDetail:
    """Тесты show lldp neighbors detail."""

    def test_parse_lldp(self):
        """Парсинг show lldp neighbors detail."""
        result = parse_with_template(
            "qtech_show_lldp_neighbors_detail.textfsm",
            "show_lldp_neighbors_detail.txt"
        )

        print(f"Parsed {len(result)} LLDP neighbors")
        assert len(result) > 0, "Должны быть LLDP соседи"

        neighbor = result[0]
        print(f"First neighbor: {neighbor}")

        assert "LOCAL_INTERFACE" in neighbor
        assert "NEIGHBOR" in neighbor or "CHASSIS_ID" in neighbor


class TestQtechShowInterfaceTransceiver:
    """Тесты show interface transceiver."""

    def test_parse_transceiver(self):
        """Парсинг show interface transceiver."""
        result = parse_with_template(
            "qtech_show_interface_transceiver.textfsm",
            "show_interface_transceiver.txt"
        )

        print(f"Parsed {len(result)} transceivers")
        assert len(result) > 0, "Должны быть трансиверы"

        sfp = result[0]
        print(f"First SFP: {sfp}")

        assert "INTERFACE" in sfp
        assert "TYPE" in sfp
        assert "SERIAL" in sfp


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
