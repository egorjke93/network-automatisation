"""
Tests for InterfaceNormalizer.

Проверяет нормализацию интерфейсов:
- Статусы (up/down/disabled)
- Port type detection
- LAG/switchport enrichment
"""

import pytest

from network_collector.core.domain import InterfaceNormalizer
from network_collector.core.models import Interface


@pytest.mark.unit
class TestInterfaceNormalizerStatus:
    """Тесты нормализации статуса интерфейса."""

    def setup_method(self):
        self.normalizer = InterfaceNormalizer()

    @pytest.mark.parametrize("raw_status, expected", [
        ("connected", "up"),
        ("up", "up"),
        ("notconnect", "down"),
        ("notconnected", "down"),
        ("down", "down"),
        ("disabled", "disabled"),
        ("err-disabled", "error"),
        ("administratively down", "disabled"),
        ("admin down", "disabled"),
        ("CONNECTED", "up"),  # Case insensitive
        ("Down", "down"),
    ])
    def test_normalize_status(self, raw_status, expected):
        """Тест нормализации статуса."""
        result = self.normalizer.normalize_status(raw_status)
        assert result == expected

    def test_normalize_status_unknown(self):
        """Неизвестный статус возвращается как есть."""
        result = self.normalizer.normalize_status("some-custom-status")
        assert result == "some-custom-status"


@pytest.mark.unit
class TestInterfaceNormalizerNormalize:
    """Тесты метода normalize."""

    def setup_method(self):
        self.normalizer = InterfaceNormalizer()

    def test_normalize_basic(self):
        """Базовая нормализация интерфейсов."""
        raw_data = [
            {"interface": "Gi0/1", "link_status": "up", "ip_address": "10.0.0.1"},
            {"interface": "Gi0/2", "status": "down", "description": "Server"},
        ]
        result = self.normalizer.normalize(raw_data)

        assert len(result) == 2
        assert isinstance(result[0], Interface)
        assert result[0].name == "Gi0/1"
        assert result[0].status == "up"
        assert result[0].ip_address == "10.0.0.1"

        assert result[1].name == "Gi0/2"
        assert result[1].status == "down"
        assert result[1].description == "Server"

    def test_normalize_with_metadata(self):
        """Нормализация с hostname и device_ip."""
        raw_data = [{"interface": "Gi0/1", "status": "up"}]
        result = self.normalizer.normalize(
            raw_data, hostname="switch-01", device_ip="192.168.1.1"
        )

        assert result[0].hostname == "switch-01"
        assert result[0].device_ip == "192.168.1.1"

    def test_normalize_mac_field_unification(self):
        """Унификация MAC из разных полей."""
        test_cases = [
            {"interface": "Gi0/1", "mac_address": "00:11:22:33:44:55"},
            {"interface": "Gi0/2", "address": "00:11:22:33:44:66"},
            {"interface": "Gi0/3", "bia": "00:11:22:33:44:77"},
            {"interface": "Gi0/4", "hardware_address": "00:11:22:33:44:88"},
        ]
        result = self.normalizer.normalize(test_cases)

        assert result[0].mac == "00:11:22:33:44:55"
        assert result[1].mac == "00:11:22:33:44:66"
        assert result[2].mac == "00:11:22:33:44:77"
        assert result[3].mac == "00:11:22:33:44:88"

    def test_normalize_hardware_media_unification(self):
        """Унификация hardware_type и media_type из NTC полей."""
        raw_data = [
            {"interface": "Gi0/1", "hardware": "Gigabit Ethernet", "media": "RJ45"},
        ]
        result = self.normalizer.normalize_dicts(raw_data)

        assert result[0]["hardware_type"] == "Gigabit Ethernet"
        assert result[0]["media_type"] == "RJ45"

    def test_normalize_auto_port_type(self):
        """Автоматическое определение port_type."""
        raw_data = [
            {"interface": "Te1/1", "status": "up"},
            {"interface": "Po1", "status": "up"},
            {"interface": "Vlan10", "status": "up"},
        ]
        result = self.normalizer.normalize_dicts(raw_data)

        assert result[0]["port_type"] == "10g-sfp+"
        assert result[1]["port_type"] == "lag"
        assert result[2]["port_type"] == "virtual"


@pytest.mark.unit
class TestInterfaceNormalizerEnrich:
    """Тесты методов обогащения данных."""

    def setup_method(self):
        self.normalizer = InterfaceNormalizer()

    def test_enrich_with_lag(self):
        """Обогащение LAG membership."""
        interfaces = [
            {"interface": "Gi0/1"},
            {"interface": "Gi0/2"},
            {"interface": "Gi0/3"},
        ]
        lag_membership = {"Gi0/1": "Po1", "Gi0/2": "Po1"}

        result = self.normalizer.enrich_with_lag(interfaces, lag_membership)

        assert result[0]["lag"] == "Po1"
        assert result[1]["lag"] == "Po1"
        assert "lag" not in result[2]

    def test_enrich_with_switchport(self):
        """Обогащение switchport mode."""
        interfaces = [
            {"interface": "Gi0/1"},
            {"interface": "Gi0/2"},
        ]
        switchport_modes = {
            "Gi0/1": {"mode": "access", "access_vlan": "10", "native_vlan": ""},
            "Gi0/2": {"mode": "tagged", "access_vlan": "", "native_vlan": "1"},
        }

        result = self.normalizer.enrich_with_switchport(interfaces, switchport_modes)

        assert result[0]["mode"] == "access"
        assert result[0]["access_vlan"] == "10"
        assert result[1]["mode"] == "tagged"
        assert result[1]["native_vlan"] == "1"

    def test_enrich_lag_inherits_mode_from_members(self):
        """LAG наследует mode от member портов."""
        interfaces = [
            {"interface": "Gi0/1"},
            {"interface": "Gi0/2"},
            {"interface": "Po1"},
        ]
        switchport_modes = {
            "Gi0/1": {"mode": "tagged", "access_vlan": "", "native_vlan": "1"},
            "Gi0/2": {"mode": "tagged", "access_vlan": "", "native_vlan": "1"},
        }
        lag_membership = {"Gi0/1": "Po1", "Gi0/2": "Po1"}

        result = self.normalizer.enrich_with_switchport(
            interfaces, switchport_modes, lag_membership
        )

        assert result[2]["mode"] == "tagged"

    def test_enrich_lag_tagged_all_priority(self):
        """tagged-all имеет приоритет над tagged."""
        interfaces = [{"interface": "Po1"}]
        switchport_modes = {
            "Gi0/1": {"mode": "tagged", "access_vlan": "", "native_vlan": ""},
            "Gi0/2": {"mode": "tagged-all", "access_vlan": "", "native_vlan": ""},
        }
        lag_membership = {"Gi0/1": "Po1", "Gi0/2": "Po1"}

        result = self.normalizer.enrich_with_switchport(
            interfaces, switchport_modes, lag_membership
        )

        assert result[0]["mode"] == "tagged-all"

    def test_enrich_with_switchport_name_variants(self):
        """Обогащение switchport с разными форматами имён (GigabitEthernet0/1 vs Gi0/1)."""
        # show interfaces возвращает полные имена
        interfaces = [
            {"interface": "GigabitEthernet0/1"},
            {"interface": "TenGigabitEthernet1/0/1"},
        ]
        # show interfaces switchport возвращает сокращённые имена
        switchport_modes = {
            "Gi0/1": {"mode": "access", "access_vlan": "10", "native_vlan": ""},
            "Te1/0/1": {"mode": "tagged", "access_vlan": "", "native_vlan": "1"},
        }

        result = self.normalizer.enrich_with_switchport(interfaces, switchport_modes)

        assert result[0]["mode"] == "access"
        assert result[0]["access_vlan"] == "10"
        assert result[1]["mode"] == "tagged"
        assert result[1]["native_vlan"] == "1"

    def test_interface_aliases_used_in_enrichment(self):
        """get_interface_aliases() используется для сопоставления имён."""
        from network_collector.core.constants.interfaces import get_interface_aliases

        # Полное -> сокращённое
        aliases = get_interface_aliases("GigabitEthernet0/1")
        assert "Gi0/1" in aliases
        assert "GigabitEthernet0/1" in aliases

        # Сокращённое -> полное
        aliases = get_interface_aliases("Te1/0/1")
        assert "TenGigabitEthernet1/0/1" in aliases
        assert "Te1/0/1" in aliases

        # Port-channel
        aliases = get_interface_aliases("Port-channel1")
        assert "Po1" in aliases

    def test_enrich_with_media_type(self):
        """Обогащение media_type."""
        interfaces = [
            {"interface": "Eth1/1", "media_type": "10G"},
            {"interface": "Eth1/2"},
        ]
        media_types = {
            "Eth1/1": "10GBase-LR",
            "Eth1/2": "10GBase-SR",
        }

        result = self.normalizer.enrich_with_media_type(interfaces, media_types)

        # 10GBase-LR более информативно чем 10G
        assert result[0]["media_type"] == "10GBase-LR"
        assert result[0]["port_type"] == "10g-sfp+"
        assert result[1]["media_type"] == "10GBase-SR"

    def test_qtech_space_in_interface_name_removed(self):
        """QTech имена с пробелом нормализуются: 'TFGigabitEthernet 0/1' → 'TFGigabitEthernet0/1'."""
        raw = [
            {"interface": "TFGigabitEthernet 0/1", "link_status": "UP", "address": "001f.ce62.1e96"},
            {"interface": "TFGigabitEthernet 0/39", "link_status": "DOWN", "address": "001f.ce62.1ebc"},
        ]

        result = self.normalizer.normalize_dicts(raw, hostname="switch01")

        assert result[0]["interface"] == "TFGigabitEthernet0/1"
        assert result[1]["interface"] == "TFGigabitEthernet0/39"

    def test_qtech_transceiver_matches_after_space_removal(self):
        """Трансивер-данные (с пробелом) матчатся с нормализованным интерфейсом (без пробела)."""
        from network_collector.core.constants.interfaces import get_interface_aliases

        # Интерфейсы после нормализации (пробел убран)
        interfaces = [
            {"interface": "TFGigabitEthernet0/1"},
            {"interface": "TFGigabitEthernet0/2"},
        ]

        # media_types строятся из TextFSM с пробелом через get_interface_aliases
        media_types = {}
        for alias in get_interface_aliases("TFGigabitEthernet 0/1"):
            media_types[alias] = "10GBASE-SR-SFP+"
        for alias in get_interface_aliases("TFGigabitEthernet 0/2"):
            media_types[alias] = "10GBASE-LR-SFP+"

        result = self.normalizer.enrich_with_media_type(interfaces, media_types)

        assert result[0]["media_type"] == "10GBASE-SR-SFP+"
        assert result[0]["port_type"] == "10g-sfp+"
        assert result[1]["media_type"] == "10GBASE-LR-SFP+"

    def test_get_interface_aliases_removes_space(self):
        """get_interface_aliases генерирует вариант без пробела для QTech."""
        from network_collector.core.constants.interfaces import get_interface_aliases

        aliases = get_interface_aliases("TFGigabitEthernet 0/39")
        assert "TFGigabitEthernet0/39" in aliases  # Без пробела
        assert "TFGigabitEthernet 0/39" in aliases  # С пробелом (оригинал)


@pytest.mark.unit
class TestResolveTrunkMode:
    """Тесты для _resolve_trunk_mode — helper определения trunk type из VLAN списка."""

    def setup_method(self):
        self.normalizer = InterfaceNormalizer()

    @pytest.mark.parametrize("raw_vlans,expected_mode,expected_vlans", [
        # tagged-all: пустые, "all", полные диапазоны
        ("", "tagged-all", ""),
        ("ALL", "tagged-all", ""),
        ("all", "tagged-all", ""),
        ("1-4094", "tagged-all", ""),
        ("1-4093", "tagged-all", ""),
        ("1-4095", "tagged-all", ""),
        # tagged: конкретные VLAN
        ("10,20,30", "tagged", "10,20,30"),
        ("100-200", "tagged", "100-200"),
        ("10,20,100-200", "tagged", "10,20,100-200"),
        # list → str (Cisco IOS NTC формат)
        (["10", "20", "30"], "tagged", "10,20,30"),
        (["ALL"], "tagged-all", ""),
        (["1-4094"], "tagged-all", ""),
        ([], "tagged-all", ""),
    ])
    def test_resolve_trunk_mode(self, raw_vlans, expected_mode, expected_vlans):
        """Проверяет определение trunk mode из raw VLAN данных."""
        mode, vlans = self.normalizer._resolve_trunk_mode(raw_vlans)
        assert mode == expected_mode
        assert vlans == expected_vlans
