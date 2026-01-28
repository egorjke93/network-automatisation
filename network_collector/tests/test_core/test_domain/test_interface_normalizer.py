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
class TestInterfaceNormalizerPortType:
    """Тесты определения port_type."""

    def setup_method(self):
        self.normalizer = InterfaceNormalizer()

    @pytest.mark.parametrize("iface_lower, expected", [
        ("port-channel1", "lag"),
        ("po1", "lag"),
        ("vlan10", "virtual"),
        ("loopback0", "virtual"),
        ("null0", "virtual"),
        ("tunnel1", "virtual"),
        ("nve1", "virtual"),
        ("mgmt0", "1g-rj45"),
        ("management0", "1g-rj45"),
    ])
    def test_detect_port_type_special(self, iface_lower, expected):
        """Тест определения специальных типов портов."""
        result = self.normalizer.detect_port_type({}, iface_lower)
        assert result == expected

    @pytest.mark.parametrize("media_type, expected", [
        ("100GBase-SR4", "100g-qsfp28"),
        ("100G", "100g-qsfp28"),
        ("40GBase-LR4", "40g-qsfp"),
        ("40G", "40g-qsfp"),
        ("25GBase-SR", "25g-sfp28"),
        ("25G", "25g-sfp28"),
        ("10GBase-LR", "10g-sfp+"),
        ("10G", "10g-sfp+"),
        ("1000Base-T", "1g-rj45"),
        ("RJ45", "1g-rj45"),
        ("1000Base-SX", "1g-sfp"),
        ("SFP", "1g-sfp"),
    ])
    def test_detect_port_type_from_media_type(self, media_type, expected):
        """Тест определения port_type из media_type."""
        row = {"media_type": media_type}
        result = self.normalizer.detect_port_type(row, "ethernet1/1")
        assert result == expected

    @pytest.mark.parametrize("hardware_type, expected", [
        ("Hundred Gigabit Ethernet", "100g-qsfp28"),
        ("100000 Ethernet", "100g-qsfp28"),
        ("Forty Gigabit Ethernet", "40g-qsfp"),
        ("40000 Ethernet", "40g-qsfp"),
        ("Twenty Five Gigabit Ethernet", "25g-sfp28"),
        ("25000 Ethernet", "25g-sfp28"),
        ("Ten Gigabit Ethernet", "10g-sfp+"),
        ("10000 Ethernet", "10g-sfp+"),
        ("100/1000/10000 Ethernet", "10g-sfp+"),  # NX-OS multi-speed
        ("Gigabit Ethernet", "1g-rj45"),
        ("1000 Ethernet", "1g-rj45"),
        ("Gigabit Ethernet SFP", "1g-sfp"),
    ])
    def test_detect_port_type_from_hardware_type(self, hardware_type, expected):
        """Тест определения port_type из hardware_type."""
        row = {"hardware_type": hardware_type}
        result = self.normalizer.detect_port_type(row, "ethernet1/1")
        assert result == expected

    @pytest.mark.parametrize("iface_lower, expected", [
        ("hundredgigabitethernet1/0/1", "100g-qsfp28"),
        ("hu1/0/1", "100g-qsfp28"),
        ("fortygigabitethernet1/0/1", "40g-qsfp"),
        ("fo1/0/1", "40g-qsfp"),
        ("twentyfivegige1/0/1", "25g-sfp28"),
        ("twe1/0/1", "25g-sfp28"),
        ("tengigabitethernet1/0/1", "10g-sfp+"),
        ("te1/1", "10g-sfp+"),
        ("gigabitethernet0/1", "1g-rj45"),
        ("gi0/1", "1g-rj45"),
        ("fastethernet0/1", "100m-rj45"),
        ("fa0/1", "100m-rj45"),
    ])
    def test_detect_port_type_from_interface_name(self, iface_lower, expected):
        """Тест определения port_type из имени интерфейса."""
        result = self.normalizer.detect_port_type({}, iface_lower)
        assert result == expected

    def test_media_type_priority_over_hardware_type(self):
        """media_type имеет приоритет над hardware_type."""
        row = {
            "media_type": "10GBase-LR",
            "hardware_type": "Twenty Five Gigabit Ethernet",
        }
        result = self.normalizer.detect_port_type(row, "twentyfivegige1/0/1")
        assert result == "10g-sfp+"  # По media_type, не 25g

    def test_media_type_unknown_ignored(self):
        """media_type='unknown' игнорируется."""
        row = {"media_type": "unknown", "hardware_type": "Ten Gigabit Ethernet"}
        result = self.normalizer.detect_port_type(row, "te1/1")
        assert result == "10g-sfp+"

    def test_media_type_not_present_ignored(self):
        """media_type='not present' игнорируется."""
        row = {"media_type": "not present", "hardware_type": "Gigabit Ethernet"}
        result = self.normalizer.detect_port_type(row, "gi0/1")
        assert result == "1g-rj45"


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

    def test_get_interface_name_variants(self):
        """Генерация вариантов имён интерфейсов."""
        # Полное -> сокращённое
        variants = self.normalizer._get_interface_name_variants("GigabitEthernet0/1")
        assert "Gi0/1" in variants
        assert "GigabitEthernet0/1" in variants

        # Сокращённое -> полное
        variants = self.normalizer._get_interface_name_variants("Te1/0/1")
        assert "TenGigabitEthernet1/0/1" in variants
        assert "Te1/0/1" in variants

        # Port-channel
        variants = self.normalizer._get_interface_name_variants("Port-channel1")
        assert "Po1" in variants

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
