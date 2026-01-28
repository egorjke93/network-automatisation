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
class TestLLDPNormalizerRemotePort:
    """Тесты правильного определения remote_port.

    ВАЖНО: remote_port должен быть ТОЛЬКО реальным интерфейсом!
    MAC-адреса и hostname'ы НЕ должны попадать в remote_port.
    """

    def setup_method(self):
        self.normalizer = LLDPNormalizer()

    def test_port_id_mac_not_in_remote_port(self):
        """Если port_id это MAC — он НЕ должен быть в remote_port."""
        raw_data = [{
            "local_interface": "Gi0/1",
            "port_id": "00e0.db43.8145",  # MAC-адрес
            "remote_hostname": "some-device",
        }]
        result = self.normalizer.normalize_dicts(raw_data)

        # remote_port должен быть пустым, а не MAC
        assert result[0].get("remote_port", "") == ""
        # MAC должен быть в remote_mac
        assert result[0].get("remote_mac") == "00e0.db43.8145"

    def test_port_id_mac_with_hostname_port_description(self):
        """port_id=MAC, port_description=hostname — remote_port пустой."""
        raw_data = [{
            "local_interface": "Gi0/1",
            "port_id": "c8d3.ffa5.dc1e",  # MAC
            "port_description": "switch-01.corp.domain.ru",  # Hostname, не интерфейс!
            "remote_hostname": "[MAC:c8d3.ffa5.dc1e]",
        }]
        result = self.normalizer.normalize_dicts(raw_data)

        # remote_port НЕ должен содержать hostname!
        remote_port = result[0].get("remote_port", "")
        assert remote_port == "", f"remote_port should be empty, got: {remote_port}"
        # MAC в remote_mac
        assert result[0].get("remote_mac") == "c8d3.ffa5.dc1e"

    def test_port_id_mac_with_interface_port_description(self):
        """port_id=MAC, port_description=интерфейс — remote_port берётся из port_description."""
        raw_data = [{
            "local_interface": "Gi0/1",
            "port_id": "cc8e.713b.7a00",  # MAC
            "port_description": "Te1/0/2",  # Это интерфейс!
            "remote_hostname": "switch-02",
        }]
        result = self.normalizer.normalize_dicts(raw_data)

        # remote_port должен быть Te1/0/2
        assert result[0].get("remote_port") == "Te1/0/2"
        # MAC в remote_mac
        assert result[0].get("remote_mac") == "cc8e.713b.7a00"

    def test_port_id_interface_used(self):
        """port_id=интерфейс — используется как remote_port."""
        raw_data = [{
            "local_interface": "Gi0/1",
            "port_id": "Te1/1/4",  # Интерфейс
            "remote_hostname": "switch-02",
        }]
        result = self.normalizer.normalize_dicts(raw_data)

        assert result[0].get("remote_port") == "Te1/1/4"

    def test_neighbor_port_id_from_textfsm(self):
        """neighbor_port_id (TextFSM LLDP) → remote_port."""
        raw_data = [{
            "local_interface": "Te1/1/4",
            "neighbor_port_id": "Te1/0/2",  # Реальный порт из Port ID
            "neighbor_interface": "SU-316-C9200L-48P-4X-01",  # Port Description (hostname!)
            "system_name": "SU-316-C2960X-48LPD-L-01.corp.ogk4.ru",
            "chassis_id": "cc8e.713b.7a00",
        }]
        result = self.normalizer.normalize_dicts(raw_data)

        # remote_port = neighbor_port_id (реальный порт)
        assert result[0].get("remote_port") == "Te1/0/2"
        # port_description сохранён отдельно (это НЕ порт!)
        assert result[0].get("port_description") == "SU-316-C9200L-48P-4X-01"
        # remote_hostname из system_name
        assert "SU-316-C2960X" in result[0].get("remote_hostname", "")

    def test_empty_remote_port_is_ok(self):
        """Пустой remote_port лучше чем неправильный."""
        raw_data = [{
            "local_interface": "Gi0/16",
            "chassis_id": "c8d3.ffa5.dc1e",  # Только MAC
            # Нет port_id, нет port_description
        }]
        result = self.normalizer.normalize_dicts(raw_data)

        # remote_port пустой — это нормально
        assert result[0].get("remote_port", "") == ""
        # remote_mac заполнен
        assert result[0].get("remote_mac") == "c8d3.ffa5.dc1e"


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
        """CDP hostname имеет приоритет (CDP база)."""
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

        # CDP как база — hostname из CDP
        assert result[0]["remote_hostname"] == "real-switch"
        # MAC из LLDP дополняет
        assert result[0]["remote_mac"] == "00:11:22:33:44:55"

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

    def test_merge_cdp_port_priority(self):
        """CDP port имеет приоритет (CDP база)."""
        lldp_data = [
            {
                "local_interface": "Gi0/1",
                "remote_hostname": "switch2",
                "remote_port": "Eth1/1",
                "remote_mac": "aa:bb:cc:dd:ee:ff",
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

        # CDP как база — port из CDP
        assert result[0]["remote_port"] == "Ethernet1/1"
        # MAC из LLDP дополняет
        assert result[0]["remote_mac"] == "aa:bb:cc:dd:ee:ff"


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
