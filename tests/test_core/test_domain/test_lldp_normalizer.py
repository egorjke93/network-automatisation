"""
Tests for LLDPNormalizer.

Проверяет нормализацию LLDP/CDP соседей:
- Маппинг полей из NTC
- Определение neighbor_type
- Объединение LLDP и CDP данных
"""

import pytest

from network_collector.core.domain import LLDPNormalizer
from network_collector.core.models import LLDPNeighbor


@pytest.mark.unit
class TestLLDPNormalizerBasic:
    """Базовые тесты нормализации."""

    def setup_method(self):
        self.normalizer = LLDPNormalizer()

    def test_normalize_basic(self):
        """Базовая нормализация LLDP записей."""
        raw_data = [
            {
                "local_interface": "Gi0/1",
                "remote_hostname": "switch2",
                "remote_port": "Gi0/2",
            },
        ]
        result = self.normalizer.normalize(raw_data)

        assert len(result) == 1
        assert isinstance(result[0], LLDPNeighbor)
        assert result[0].local_interface == "Gi0/1"
        assert result[0].remote_hostname == "switch2"
        assert result[0].remote_port == "Gi0/2"

    def test_normalize_with_metadata(self):
        """Нормализация с hostname и device_ip."""
        raw_data = [{"local_interface": "Gi0/1", "remote_hostname": "switch2"}]
        result = self.normalizer.normalize(
            raw_data,
            protocol="lldp",
            hostname="switch-01",
            device_ip="192.168.1.1",
        )

        assert result[0].hostname == "switch-01"
        assert result[0].device_ip == "192.168.1.1"
        assert result[0].protocol == "LLDP"


@pytest.mark.unit
class TestLLDPNormalizerKeyMapping:
    """Тесты маппинга полей из NTC."""

    def setup_method(self):
        self.normalizer = LLDPNormalizer()

    @pytest.mark.parametrize("ntc_key, standard_key, value", [
        ("local_intf", "local_interface", "Gi0/1"),
        ("neighbor", "remote_hostname", "switch2"),
        ("neighbor_name", "remote_hostname", "switch2"),
        ("system_name", "remote_hostname", "switch2"),
        ("device_id", "remote_hostname", "switch2"),
        ("neighbor_interface", "remote_port", "Gi0/2"),
        ("port_id", "remote_port", "Gi0/2"),
        ("mgmt_ip", "remote_ip", "10.0.0.1"),
        ("mgmt_address", "remote_ip", "10.0.0.1"),
        ("management_ip", "remote_ip", "10.0.0.1"),
        ("hardware", "remote_platform", "C9200L"),
        ("platform", "remote_platform", "C9200L"),
        ("chassis_id", "remote_mac", "00:11:22:33:44:55"),
    ])
    def test_key_mapping(self, ntc_key, standard_key, value):
        """Тест маппинга NTC ключей в стандартные."""
        raw_data = [{ntc_key: value, "local_interface": "Gi0/1"}]
        result = self.normalizer.normalize_dicts(raw_data)

        assert result[0].get(standard_key) == value


@pytest.mark.unit
class TestLLDPNormalizerNeighborType:
    """Тесты определения типа соседа."""

    def setup_method(self):
        self.normalizer = LLDPNormalizer()

    def test_neighbor_type_hostname(self):
        """Сосед идентифицирован по hostname."""
        raw_data = [
            {"local_interface": "Gi0/1", "remote_hostname": "switch2"}
        ]
        result = self.normalizer.normalize_dicts(raw_data)

        assert result[0]["neighbor_type"] == "hostname"

    def test_neighbor_type_mac(self):
        """Сосед идентифицирован по MAC."""
        raw_data = [
            {"local_interface": "Gi0/1", "chassis_id": "00:11:22:33:44:55"}
        ]
        result = self.normalizer.normalize_dicts(raw_data)

        assert result[0]["neighbor_type"] == "mac"
        # hostname заполняется из MAC
        assert result[0]["remote_hostname"] == "[MAC:00:11:22:33:44:55]"

    def test_neighbor_type_ip(self):
        """Сосед идентифицирован по IP."""
        raw_data = [
            {"local_interface": "Gi0/1", "mgmt_ip": "10.0.0.1"}
        ]
        result = self.normalizer.normalize_dicts(raw_data)

        assert result[0]["neighbor_type"] == "ip"
        assert result[0]["remote_hostname"] == "[IP:10.0.0.1]"

    def test_neighbor_type_unknown(self):
        """Сосед не идентифицирован."""
        raw_data = [
            {"local_interface": "Gi0/1"}
        ]
        result = self.normalizer.normalize_dicts(raw_data)

        assert result[0]["neighbor_type"] == "unknown"
        assert result[0]["remote_hostname"] == "[unknown]"

    def test_hostname_is_mac_detected(self):
        """MAC в поле hostname определяется правильно."""
        raw_data = [
            {"local_interface": "Gi0/1", "remote_hostname": "00:11:22:33:44:55"}
        ]
        result = self.normalizer.normalize_dicts(raw_data)

        # MAC в hostname → neighbor_type = mac
        assert result[0]["neighbor_type"] == "mac"


@pytest.mark.unit
class TestLLDPNormalizerMACValidation:
    """Тесты валидации MAC-адресов."""

    def setup_method(self):
        self.normalizer = LLDPNormalizer()

    @pytest.mark.parametrize("value, expected", [
        ("00:11:22:33:44:55", True),
        ("00-11-22-33-44-55", True),
        ("0011.2233.4455", True),
        ("001122334455", True),
        ("switch-01", False),
        ("192.168.1.1", False),
        ("", False),
        ("00:11:22", False),  # Слишком короткий
    ])
    def test_is_mac_address(self, value, expected):
        """Тест определения MAC-адреса."""
        result = self.normalizer.is_mac_address(value)
        assert result == expected


@pytest.mark.unit
class TestLLDPNormalizerMerge:
    """Тесты объединения LLDP и CDP."""

    def setup_method(self):
        self.normalizer = LLDPNormalizer()

    def test_merge_lldp_cdp_basic(self):
        """Базовое объединение LLDP и CDP."""
        lldp_data = [
            {
                "local_interface": "Gi0/1",
                "remote_hostname": "",
                "remote_mac": "00:11:22:33:44:55",
                "remote_port": "Gi0/2",
            }
        ]
        cdp_data = [
            {
                "local_interface": "Gi0/1",
                "remote_hostname": "switch2",
                "remote_platform": "C9200L",
                "remote_ip": "10.0.0.2",
            }
        ]

        result = self.normalizer.merge_lldp_cdp(lldp_data, cdp_data)

        assert len(result) == 1
        assert result[0]["remote_hostname"] == "switch2"  # Из CDP
        assert result[0]["remote_mac"] == "00:11:22:33:44:55"  # Из LLDP
        assert result[0]["remote_platform"] == "C9200L"  # Из CDP
        assert result[0]["remote_ip"] == "10.0.0.2"  # Из CDP
        assert result[0]["protocol"] == "BOTH"

    def test_merge_lldp_only(self):
        """Только LLDP данные."""
        lldp_data = [{"local_interface": "Gi0/1", "remote_hostname": "switch2"}]
        cdp_data = []

        result = self.normalizer.merge_lldp_cdp(lldp_data, cdp_data)

        assert len(result) == 1
        assert result[0]["remote_hostname"] == "switch2"

    def test_merge_cdp_only(self):
        """Только CDP данные."""
        lldp_data = []
        cdp_data = [{"local_interface": "Gi0/1", "remote_hostname": "switch2"}]

        result = self.normalizer.merge_lldp_cdp(lldp_data, cdp_data)

        assert len(result) == 1
        assert result[0]["remote_hostname"] == "switch2"

    def test_merge_different_interfaces(self):
        """Соседи на разных интерфейсах."""
        lldp_data = [
            {"local_interface": "Gi0/1", "remote_hostname": "switch2"}
        ]
        cdp_data = [
            {"local_interface": "Gi0/2", "remote_hostname": "switch3"}
        ]

        result = self.normalizer.merge_lldp_cdp(lldp_data, cdp_data)

        assert len(result) == 2
        hostnames = {r["remote_hostname"] for r in result}
        assert hostnames == {"switch2", "switch3"}

    def test_merge_hostname_priority(self):
        """CDP hostname имеет приоритет над LLDP MAC."""
        lldp_data = [
            {
                "local_interface": "Gi0/1",
                "remote_hostname": "[MAC:00:11:22:33:44:55]",  # Только MAC
                "remote_mac": "00:11:22:33:44:55",
            }
        ]
        cdp_data = [
            {
                "local_interface": "Gi0/1",
                "remote_hostname": "real-switch",
            }
        ]

        result = self.normalizer.merge_lldp_cdp(lldp_data, cdp_data)

        assert result[0]["remote_hostname"] == "real-switch"
        assert result[0]["neighbor_type"] == "hostname"

    def test_merge_remote_port_cdp_preferred(self):
        """CDP port предпочтительнее если LLDP port похож на hostname."""
        lldp_data = [
            {
                "local_interface": "Gi0/1",
                "remote_hostname": "switch2",
                "remote_port": "some-very-long-hostname-like-string",
            }
        ]
        cdp_data = [
            {
                "local_interface": "Gi0/1",
                "remote_hostname": "switch2",
                "remote_port": "Gi0/2",
            }
        ]

        result = self.normalizer.merge_lldp_cdp(lldp_data, cdp_data)

        assert result[0]["remote_port"] == "Gi0/2"

    def test_merge_keeps_lldp_port_if_valid(self):
        """Если LLDP port валидный — не перезаписываем."""
        lldp_data = [
            {
                "local_interface": "Gi0/1",
                "remote_hostname": "switch2",
                "remote_port": "Eth1/1",
            }
        ]
        cdp_data = [
            {
                "local_interface": "Gi0/1",
                "remote_hostname": "switch2",
                "remote_port": "Ethernet1/1",
            }
        ]

        result = self.normalizer.merge_lldp_cdp(lldp_data, cdp_data)

        # LLDP port сохраняется
        assert result[0]["remote_port"] == "Eth1/1"


@pytest.mark.unit
class TestLLDPNormalizerFilter:
    """Тесты фильтрации соседей."""

    def setup_method(self):
        self.normalizer = LLDPNormalizer()

    def test_filter_by_local_interface(self):
        """Фильтрация по локальным интерфейсам."""
        data = [
            {"local_interface": "Gi0/1", "remote_hostname": "switch2"},
            {"local_interface": "Gi0/2", "remote_hostname": "switch3"},
            {"local_interface": "Te1/1", "remote_hostname": "switch4"},
        ]
        interfaces = ["Gi0/1", "Te1/1"]

        result = self.normalizer.filter_by_local_interface(data, interfaces)

        assert len(result) == 2
        hostnames = {r["remote_hostname"] for r in result}
        assert hostnames == {"switch2", "switch4"}
