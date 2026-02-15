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
        assert len(result) >= 6, "Должны быть физические + SVI интерфейсы"

        # Проверяем первый интерфейс
        intf = result[0]
        print(f"First interface: {intf}")

        assert "INTERFACE" in intf
        assert "LINK_STATUS" in intf
        assert "ADDRESS" in intf

        # Проверяем значения
        assert "TFGigabitEthernet" in intf.get("INTERFACE", "")
        assert intf.get("LINK_STATUS") in ["UP", "DOWN"]

        # Проверяем что SVI (VLAN) интерфейсы парсятся
        names = [r.get("INTERFACE", "") for r in result]
        assert any("Vlan" in n for n in names), f"Vlan SVI не найден в: {names}"


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

    def test_all_present_transceivers_parsed(self):
        """Все установленные трансиверы распарсены (включая после absent)."""
        result = parse_with_template(
            "qtech_show_interface_transceiver.textfsm",
            "show_interface_transceiver.txt"
        )

        # Записи с реальным типом (не absent)
        present = [r for r in result if r["TYPE"]]
        assert len(present) == 4, f"Должно быть 4 SFP, получено {len(present)}"

        # Проверяем конкретные интерфейсы (TF0/39 после серии absent)
        interfaces = [r["INTERFACE"] for r in present]
        assert "TFGigabitEthernet 0/1" in interfaces
        assert "TFGigabitEthernet 0/2" in interfaces
        assert "TFGigabitEthernet 0/39" in interfaces
        assert "TFGigabitEthernet 0/40" in interfaces

    def test_transceiver_serial_numbers(self):
        """Серийные номера трансиверов корректны."""
        result = parse_with_template(
            "qtech_show_interface_transceiver.textfsm",
            "show_interface_transceiver.txt"
        )

        present = {r["INTERFACE"]: r for r in result if r["TYPE"]}
        assert present["TFGigabitEthernet 0/1"]["SERIAL"] == "RQ114410301879"
        assert present["TFGigabitEthernet 0/39"]["SERIAL"] == "RQ114410303396"


class TestQtechShowAggregatePortSummary:
    """Тесты show aggregatePort summary."""

    def test_parse_aggregate_port(self):
        """Парсинг show aggregatePort summary."""
        result = parse_with_template(
            "qtech_show_aggregatePort_summary.textfsm",
            "show_aggregatePort_summary .txt"
        )

        assert len(result) == 7, "Должно быть 7 AggregatePort"

        # Проверяем Ag1 (2 member порта)
        ag1 = result[0]
        assert ag1["AGGREGATE_PORT"] == "Ag1"
        assert ag1["MODE"] == "TRUNK"
        assert "Hu0/55" in ag1["PORTS"]
        assert "Hu0/56" in ag1["PORTS"]

    def test_parse_access_aggregate(self):
        """AggregatePort в режиме ACCESS."""
        result = parse_with_template(
            "qtech_show_aggregatePort_summary.textfsm",
            "show_aggregatePort_summary .txt"
        )

        ag10 = result[1]
        assert ag10["AGGREGATE_PORT"] == "Ag10"
        assert ag10["MODE"] == "ACCESS"
        assert ag10["PORTS"].strip() == "TF0/1"


class TestQtechInterfaceStatusRouted:
    """Тест что routed VLAN парсится (баг с \\d+ регулярным выражением)."""

    def test_routed_vlan_parsed(self):
        """TFGigabitEthernet 0/48 с VLAN=routed не теряется."""
        result = parse_with_template(
            "qtech_show_interface_status.textfsm",
            "show_interface_status.txt"
        )

        # Ищем routed порт
        routed = [r for r in result if r["VLAN"] == "routed"]
        assert len(routed) == 1, "Должен быть один routed порт"
        assert routed[0]["INTERFACE"] == "TFGigabitEthernet 0/48"
        assert routed[0]["STATUS"] == "up"
        assert routed[0]["SPEED"] == "10G"

    def test_aggregate_port_parsed(self):
        """AggregatePort интерфейсы парсятся из show interface status."""
        result = parse_with_template(
            "qtech_show_interface_status.textfsm",
            "show_interface_status.txt"
        )

        ag_ports = [r for r in result if r["INTERFACE"].startswith("AggregatePort")]
        assert len(ag_ports) == 5, "Должно быть 5 AggregatePort"

        # AggregatePort 1 — 200G
        ag1 = [r for r in ag_ports if r["INTERFACE"] == "AggregatePort 1"][0]
        assert ag1["STATUS"] == "up"
        assert ag1["SPEED"] == "200G"

    def test_total_interfaces_count(self):
        """Общее количество интерфейсов (56 физических + 5 AggregatePort)."""
        result = parse_with_template(
            "qtech_show_interface_status.textfsm",
            "show_interface_status.txt"
        )

        assert len(result) == 61, "Должен быть 61 интерфейс"


class TestQtechSwitchportAggregatePort:
    """Тесты switchport для AggregatePort."""

    def test_aggregate_port_trunk(self):
        """AggregatePort 1 в режиме TRUNK."""
        result = parse_with_template(
            "qtech_show_interface_switchport.textfsm",
            "show_interface_switchport.txt"
        )

        ag_trunk = [r for r in result if r["INTERFACE"] == "AggregatePort 1"]
        assert len(ag_trunk) == 1
        assert ag_trunk[0]["MODE"] == "TRUNK"
        assert ag_trunk[0]["VLAN_LISTS"] == "ALL"

    def test_aggregate_port_access(self):
        """AggregatePort 10 в режиме ACCESS."""
        result = parse_with_template(
            "qtech_show_interface_switchport.textfsm",
            "show_interface_switchport.txt"
        )

        ag_access = [r for r in result if r["INTERFACE"] == "AggregatePort 10"]
        assert len(ag_access) == 1
        assert ag_access[0]["MODE"] == "ACCESS"
        assert ag_access[0]["ACCESS_VLAN"] == "40"

    def test_disabled_switchport_parsed(self):
        """TFGigabitEthernet 0/48 с disabled switchport."""
        result = parse_with_template(
            "qtech_show_interface_switchport.textfsm",
            "show_interface_switchport.txt"
        )

        disabled = [r for r in result if r["SWITCHPORT"] == "disabled"]
        assert len(disabled) >= 1
        assert disabled[0]["INTERFACE"] == "TFGigabitEthernet 0/48"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
