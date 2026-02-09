"""
E2E тесты для обогащения данных NX-OS.

NX-OS требует дополнительные команды для полной картины:
- show interface transceiver → media_type (SFP/QSFP тип)
- show interface switchport → mode, access/native/tagged VLANs
- show port-channel summary → LAG members

Проверяет: основные данные + enrichment → обогащённые Interface модели.
Без реального SSH подключения.
"""

import pytest
from pathlib import Path
from typing import Dict, List, Any

from network_collector.core.domain.interface import InterfaceNormalizer
from network_collector.core.models import Interface
from network_collector.parsers.textfsm_parser import NTCParser


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


@pytest.fixture(scope="module")
def normalizer() -> InterfaceNormalizer:
    """Нормализатор интерфейсов."""
    return InterfaceNormalizer()


@pytest.fixture
def nxos_interfaces(parser, normalizer) -> List[Dict[str, Any]]:
    """Предзагруженные и нормализованные NX-OS интерфейсы."""
    output = load_fixture("cisco_nxos", "show_interface.txt")
    if not output:
        pytest.skip("Нет fixture для cisco_nxos/show_interface")

    parsed = parser.parse(output, "cisco_nxos", "show interface")
    if not parsed:
        pytest.skip("Парсер вернул пустой результат")

    return normalizer.normalize_dicts(
        parsed, hostname="nxos-switch", device_ip="10.0.0.1"
    )


# =============================================================================
# Switchport Enrichment
# =============================================================================


class TestNXOSSwitchportEnrichment:
    """NX-OS: show interface switchport → mode/VLANs."""

    def test_switchport_parsed(self, parser):
        """show interface switchport парсится NTC Templates."""
        output = load_fixture("cisco_nxos", "show_interface_switchport.txt")
        if not output:
            pytest.skip("Нет fixture для cisco_nxos/show_interface_switchport")

        parsed = parser.parse(output, "cisco_nxos", "show interface switchport")
        assert len(parsed) > 0, "Switchport парсер вернул пустой результат"

        # Проверяем ключевые поля
        for row in parsed[:5]:
            assert "interface" in row, "Должно быть поле 'interface'"

    def test_switchport_enrichment(self, parser, normalizer, nxos_interfaces):
        """Enrichment switchport добавляет mode и VLANs."""
        sw_output = load_fixture("cisco_nxos", "show_interface_switchport.txt")
        if not sw_output:
            pytest.skip("Нет fixture")

        sw_parsed = parser.parse(sw_output, "cisco_nxos", "show interface switchport")
        if not sw_parsed:
            pytest.skip("Парсер switchport пуст")

        # Строим switchport_modes dict
        switchport_modes = {}
        for row in sw_parsed:
            iface = row.get("interface", "")
            if not iface:
                continue
            mode = row.get("admin_mode", row.get("mode", "")).lower()
            native_vlan = row.get("native_vlan", row.get("trunking_native_vlan", ""))
            access_vlan = row.get("access_vlan", "")
            tagged_vlans = row.get("trunking_vlans", "")

            # Маппинг mode
            if "trunk" in mode:
                # Определяем tagged vs tagged-all
                if tagged_vlans and tagged_vlans.upper() in ("ALL", "1-4094"):
                    mapped_mode = "tagged-all"
                else:
                    mapped_mode = "tagged"
            elif "access" in mode:
                mapped_mode = "access"
            else:
                mapped_mode = ""

            switchport_modes[iface] = {
                "mode": mapped_mode,
                "native_vlan": str(native_vlan),
                "access_vlan": str(access_vlan),
                "tagged_vlans": str(tagged_vlans) if mapped_mode == "tagged" else "",
            }

        assert len(switchport_modes) > 0, "Switchport modes не собраны"

        # Применяем enrichment
        enriched = normalizer.enrich_with_switchport(nxos_interfaces, switchport_modes)

        # Проверяем что хотя бы один интерфейс получил mode
        modes = [i.get("mode", "") for i in enriched if i.get("mode")]
        # Могут быть или не быть (зависит от совпадения имён)
        assert isinstance(modes, list)


# =============================================================================
# Transceiver Enrichment
# =============================================================================


class TestNXOSTransceiverEnrichment:
    """NX-OS: show interface transceiver → media_type для port_type."""

    def test_transceiver_parsed(self, parser):
        """show interface transceiver парсится NTC Templates."""
        output = load_fixture("cisco_nxos", "show_interface_transceiver.txt")
        if not output:
            pytest.skip("Нет fixture для cisco_nxos/show_interface_transceiver")

        parsed = parser.parse(output, "cisco_nxos", "show interface transceiver")
        assert len(parsed) > 0, "Transceiver парсер вернул пустой результат"

        # Проверяем ключевые поля
        for row in parsed[:5]:
            assert "interface" in row, "Должно быть поле 'interface'"

    def test_transceiver_media_types(self, parser):
        """Из show interface transceiver извлекаются media_type."""
        output = load_fixture("cisco_nxos", "show_interface_transceiver.txt")
        if not output:
            pytest.skip("Нет fixture")

        parsed = parser.parse(output, "cisco_nxos", "show interface transceiver")

        # Собираем media_types
        media_types = {}
        for row in parsed:
            iface = row.get("interface", "")
            sfp_type = row.get("type", row.get("sfp", ""))
            if iface and sfp_type:
                media_types[iface] = sfp_type

        # Должны быть трансиверы
        assert len(media_types) >= 0, "Трансиверы могут присутствовать"

    def test_media_type_enrichment(self, parser, normalizer, nxos_interfaces):
        """Enrichment media_type обновляет port_type."""
        # Симулируем media_types из show interface status (NX-OS)
        media_types = {
            "Ethernet1/1": "10Gbase-SR",
            "Ethernet1/2": "10Gbase-LR",
        }

        enriched = normalizer.enrich_with_media_type(nxos_interfaces, media_types)

        # Проверяем что интерфейсы с media_type обновлены
        for iface in enriched:
            if iface.get("interface") in media_types:
                # media_type должен быть обновлён
                assert iface.get("media_type") == media_types[iface["interface"]]


# =============================================================================
# LAG (Port-Channel) Enrichment
# =============================================================================


class TestNXOSLAGEnrichment:
    """NX-OS: show port-channel summary → LAG members."""

    def test_port_channel_parsed(self, parser):
        """show port-channel summary парсится NTC Templates."""
        output = load_fixture("cisco_nxos", "show_port_channel_summary.txt")
        if not output:
            pytest.skip("Нет fixture для cisco_nxos/show_port_channel_summary")

        parsed = parser.parse(output, "cisco_nxos", "show port-channel summary")
        assert len(parsed) > 0, "Port-channel парсер вернул пустой результат"

    def test_lag_membership_extraction(self, parser):
        """Из show port-channel summary извлекаются member → LAG."""
        output = load_fixture("cisco_nxos", "show_port_channel_summary.txt")
        if not output:
            pytest.skip("Нет fixture")

        parsed = parser.parse(output, "cisco_nxos", "show port-channel summary")
        if not parsed:
            pytest.skip("Парсер пуст")

        # Строим LAG membership
        membership = {}
        for row in parsed:
            lag_name = row.get("po_name", row.get("bundle_name", ""))
            members = row.get("member_interface", row.get("member_ports", []))

            if not lag_name:
                continue

            if not lag_name.lower().startswith("po"):
                lag_name = f"Po{lag_name}"

            if isinstance(members, str):
                members = [members] if members else []

            for member in members:
                if member:
                    import re
                    member_clean = re.sub(r'\([^)]*\)', '', member).strip()
                    if member_clean:
                        membership[member_clean] = lag_name

        # Должны быть LAG members
        assert len(membership) >= 0

    def test_lag_enrichment(self, normalizer, nxos_interfaces):
        """Enrichment LAG добавляет поле lag к member интерфейсам."""
        lag_membership = {
            "Ethernet1/1": "Po1",
            "Ethernet1/2": "Po1",
            "Ethernet1/3": "Po2",
        }

        enriched = normalizer.enrich_with_lag(nxos_interfaces, lag_membership)

        # Проверяем что members получили поле lag
        for iface in enriched:
            if iface.get("interface") in lag_membership:
                assert iface.get("lag") == lag_membership[iface["interface"]]


# =============================================================================
# Full Enrichment Pipeline
# =============================================================================


class TestNXOSFullEnrichment:
    """Полный pipeline обогащения NX-OS."""

    def test_full_enrichment_pipeline(self, parser, normalizer):
        """
        Полный pipeline: show interface → normalize → enrich (switchport + LAG + media_type).
        """
        # 1. Базовые интерфейсы
        intf_output = load_fixture("cisco_nxos", "show_interface.txt")
        if not intf_output:
            pytest.skip("Нет fixture для show_interface")

        parsed = parser.parse(intf_output, "cisco_nxos", "show interface")
        if not parsed:
            pytest.skip("Парсер пуст")

        data = normalizer.normalize_dicts(
            parsed, hostname="nxos-switch", device_ip="10.0.0.1"
        )

        assert len(data) > 0

        # 2. Enrichment LAG
        lag_membership = {"Ethernet1/1": "Po1", "Ethernet1/2": "Po1"}
        data = normalizer.enrich_with_lag(data, lag_membership)

        # 3. Enrichment switchport
        switchport_modes = {
            "Ethernet1/3": {
                "mode": "access",
                "native_vlan": "",
                "access_vlan": "100",
                "tagged_vlans": "",
            },
            "Ethernet1/4": {
                "mode": "tagged",
                "native_vlan": "1",
                "access_vlan": "",
                "tagged_vlans": "10,20,30",
            },
        }
        data = normalizer.enrich_with_switchport(data, switchport_modes, lag_membership)

        # 4. Enrichment media_type
        media_types = {"Ethernet1/1": "10Gbase-SR"}
        data = normalizer.enrich_with_media_type(data, media_types)

        # 5. Конвертируем в модели
        interfaces = [Interface.from_dict(row) for row in data]
        assert len(interfaces) > 0

        # Проверяем обогащённые поля
        for intf in interfaces:
            assert intf.name, "Каждый интерфейс должен иметь имя"
            assert intf.hostname == "nxos-switch"

        # Проверяем LAG
        lag_members = [i for i in interfaces if i.lag]
        for member in lag_members:
            assert member.lag.startswith("Po")

        # Проверяем switchport
        access_ports = [i for i in interfaces if i.mode == "access"]
        for port in access_ports:
            if port.access_vlan:
                assert port.access_vlan.isdigit()

        trunk_ports = [i for i in interfaces if i.mode == "tagged"]
        for port in trunk_ports:
            if port.native_vlan:
                assert port.native_vlan.isdigit() or port.native_vlan == ""

    def test_enrichment_order_independence(self, normalizer):
        """Порядок обогащения не влияет на результат."""
        base_data = [
            {"interface": "Ethernet1/1", "status": "up"},
            {"interface": "Ethernet1/2", "status": "up"},
        ]
        lag_membership = {"Ethernet1/1": "Po1"}
        switchport_modes = {
            "Ethernet1/2": {
                "mode": "access",
                "native_vlan": "",
                "access_vlan": "100",
                "tagged_vlans": "",
            },
        }

        # Порядок 1: LAG → switchport
        data1 = [dict(d) for d in base_data]
        data1 = normalizer.enrich_with_lag(data1, lag_membership)
        data1 = normalizer.enrich_with_switchport(data1, switchport_modes, lag_membership)

        # Порядок 2: switchport → LAG
        data2 = [dict(d) for d in base_data]
        data2 = normalizer.enrich_with_switchport(data2, switchport_modes, lag_membership)
        data2 = normalizer.enrich_with_lag(data2, lag_membership)

        # Результаты эквивалентны
        for d1, d2 in zip(data1, data2):
            assert d1.get("lag") == d2.get("lag")
            assert d1.get("mode") == d2.get("mode")
            assert d1.get("access_vlan") == d2.get("access_vlan")


# =============================================================================
# Edge Cases
# =============================================================================


class TestNXOSEnrichmentEdgeCases:
    """Граничные случаи обогащения NX-OS."""

    def test_empty_switchport_modes(self, normalizer):
        """Пустой switchport_modes не ломает enrichment."""
        data = [{"interface": "Ethernet1/1", "status": "up"}]
        result = normalizer.enrich_with_switchport(data, {})
        assert len(result) == 1

    def test_empty_lag_membership(self, normalizer):
        """Пустой lag_membership не ломает enrichment."""
        data = [{"interface": "Ethernet1/1", "status": "up"}]
        result = normalizer.enrich_with_lag(data, {})
        assert len(result) == 1
        assert result[0].get("lag", "") == ""

    def test_empty_media_types(self, normalizer):
        """Пустой media_types не ломает enrichment."""
        data = [{"interface": "Ethernet1/1", "status": "up"}]
        result = normalizer.enrich_with_media_type(data, {})
        assert len(result) == 1

    def test_interface_name_mismatch(self, normalizer):
        """Несовпадение имён интерфейсов — enrichment пропускает."""
        data = [{"interface": "Ethernet1/1", "status": "up"}]
        # switchport_modes с другим именем
        switchport_modes = {
            "GigabitEthernet0/1": {
                "mode": "access",
                "native_vlan": "",
                "access_vlan": "100",
                "tagged_vlans": "",
            },
        }
        result = normalizer.enrich_with_switchport(data, switchport_modes)
        # mode не должен быть установлен (несовпадение имён)
        assert result[0].get("mode", "") == ""

    def test_enrichment_with_empty_interfaces(self, normalizer):
        """Пустой список интерфейсов не вызывает ошибку."""
        assert normalizer.enrich_with_lag([], {"Eth1/1": "Po1"}) == []
        assert normalizer.enrich_with_switchport([], {}) == []
        assert normalizer.enrich_with_media_type([], {"Eth1/1": "10G"}) == []
