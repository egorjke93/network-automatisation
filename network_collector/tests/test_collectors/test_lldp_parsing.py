"""
Тесты парсинга LLDP/CDP.

Проверяет regex парсинг и нормализацию через Domain Layer.
"""

import pytest
from network_collector.collectors.lldp import LLDPCollector
from network_collector.core.domain.lldp import LLDPNormalizer


class TestLLDPRegexParsing:
    """Тесты regex парсинга LLDP."""

    @pytest.fixture
    def collector(self):
        """Создаёт коллектор без подключения."""
        return LLDPCollector(protocol="lldp")

    @pytest.fixture
    def normalizer(self):
        """Создаёт нормализатор."""
        return LLDPNormalizer()

    def test_lldp_with_local_intf(self, collector):
        """Тест парсинга LLDP с Local Intf (стандартный формат)."""
        output = """
------------------------------------------------
Local Intf: Gi1/0/49
Chassis id: 001a.3008.6c00
Port id: Gi3/13
Port Description: GigabitEthernet3/13
System Name: c6509-e.corp.ogk4.ru

System Description:
Cisco IOS Software, s72033_rp Software

Time remaining: 115 seconds
System Capabilities: B,R
Enabled Capabilities: B,R
Management Addresses:
    IP: 10.195.124.8
"""
        result = collector._parse_lldp_regex(output)

        assert len(result) == 1
        assert result[0]["local_interface"] == "Gi1/0/49"
        assert result[0]["chassis_id"] == "001a.3008.6c00"
        # Collector возвращает сырые данные, remote_port ставится в Domain
        assert result[0]["port_id"] == "Gi3/13"
        assert result[0]["port_description"] == "GigabitEthernet3/13"
        assert result[0]["remote_hostname"] == "c6509-e.corp.ogk4.ru"
        assert result[0]["remote_ip"] == "10.195.124.8"

    def test_lldp_without_local_intf(self, collector):
        """Тест парсинга LLDP БЕЗ Local Intf (старый формат)."""
        output = """
------------------------------------------------
Chassis id: 0090.e86f.a0f6
Port id: 3
Port Description: 100TX,RJ45.
System Name: Managed Redundant Switch 06355

System Description:
EDS-405A-MM-SC

Time remaining: 106 seconds
System Capabilities: B
Enabled Capabilities: B
Management Addresses:
    IP: 10.195.37.36
"""
        result = collector._parse_lldp_regex(output)

        assert len(result) == 1
        assert result[0]["chassis_id"] == "0090.e86f.a0f6"
        # Collector возвращает сырые данные
        assert result[0]["port_id"] == "3"
        assert result[0]["port_description"] == "100TX,RJ45."
        assert result[0]["remote_hostname"] == "Managed Redundant Switch 06355"
        assert result[0]["remote_ip"] == "10.195.37.36"
        # local_interface отсутствует в этом формате
        assert "local_interface" not in result[0]

    def test_lldp_med_device(self, collector):
        """Тест парсинга LLDP MED устройства (IP телефон и т.п.)."""
        output = """
------------------------------------------------
Local Intf: Gi1/0/14
Chassis id: 6c02.e080.2d9e
Port id: 6c02.e080.2d9e
Port Description - not advertised
System Name - not advertised
System Description - not advertised

Time remaining: 3195 seconds
System Capabilities - not advertised
Enabled Capabilities - not advertised
Management Addresses - not advertised

MED Information:
    Device type: Endpoint Class I
"""
        result = collector._parse_lldp_regex(output)

        assert len(result) == 1
        assert result[0]["local_interface"] == "Gi1/0/14"
        assert result[0]["chassis_id"] == "6c02.e080.2d9e"
        # port_id - это MAC, должен попасть в remote_port
        assert result[0]["port_id"] == "6c02.e080.2d9e"
        # remote_hostname отсутствует (not advertised)
        assert "remote_hostname" not in result[0]

    def test_lldp_multiple_neighbors(self, collector):
        """Тест парсинга нескольких соседей."""
        output = """
------------------------------------------------
Local Intf: Gi1/0/1
Chassis id: aaaa.bbbb.cccc
Port id: Gi0/1
System Name: switch1

------------------------------------------------
Local Intf: Gi1/0/2
Chassis id: dddd.eeee.ffff
Port id: Gi0/2
System Name: switch2
"""
        result = collector._parse_lldp_regex(output)

        assert len(result) == 2
        assert result[0]["local_interface"] == "Gi1/0/1"
        assert result[0]["remote_hostname"] == "switch1"
        assert result[1]["local_interface"] == "Gi1/0/2"
        assert result[1]["remote_hostname"] == "switch2"


class TestCDPRegexParsing:
    """Тесты regex парсинга CDP."""

    @pytest.fixture
    def collector(self):
        """Создаёт коллектор для CDP."""
        return LLDPCollector(protocol="cdp")

    def test_cdp_standard_format(self, collector):
        """Тест парсинга стандартного формата CDP."""
        output = """
-------------------------
Device ID: SU-MSLH-C2960C-8PC-L.corp.ogk4.ru
Entry address(es):
  IP address: 10.177.30.223
Platform: cisco WS-C2960C-8PC-L,  Capabilities: Switch IGMP
Interface: GigabitEthernet1/0/52,  Port ID (outgoing port): GigabitEthernet0/2
Holdtime : 130 sec

Version :
Cisco IOS Software, C2960C Software
"""
        result = collector._parse_cdp_regex(output)

        assert len(result) == 1
        assert result[0]["remote_hostname"] == "SU-MSLH-C2960C-8PC-L.corp.ogk4.ru"
        assert result[0]["local_interface"] == "GigabitEthernet1/0/52"
        assert result[0]["remote_port"] == "GigabitEthernet0/2"
        assert result[0]["remote_platform"] == "cisco WS-C2960C-8PC-L"
        assert result[0]["remote_ip"] == "10.177.30.223"

    def test_cdp_multiple_neighbors(self, collector):
        """Тест парсинга нескольких CDP соседей."""
        output = """
-------------------------
Device ID: switch1.domain.local
Entry address(es):
  IP address: 10.0.0.1
Platform: cisco WS-C3750,  Capabilities: Switch
Interface: Gi1/0/1,  Port ID (outgoing port): Gi0/1

-------------------------
Device ID: switch2.domain.local
Entry address(es):
  IP address: 10.0.0.2
Platform: cisco WS-C2960,  Capabilities: Switch
Interface: Gi1/0/2,  Port ID (outgoing port): Gi0/2
"""
        result = collector._parse_cdp_regex(output)

        assert len(result) == 2
        assert result[0]["remote_hostname"] == "switch1.domain.local"
        assert result[1]["remote_hostname"] == "switch2.domain.local"


class TestLLDPNormalization:
    """Тесты нормализации LLDP данных через Domain Layer."""

    @pytest.fixture
    def normalizer(self):
        return LLDPNormalizer()

    def test_normalize_port_id_as_mac(self, normalizer):
        """port_id с MAC не должен попадать в remote_port."""
        raw_data = [
            {
                "local_interface": "Gi1/0/1",
                "chassis_id": "aabb.ccdd.eeff",
                "port_id": "aabb.ccdd.eeff",  # MAC в port_id
                "system_name": "device1",
            }
        ]
        result = normalizer.normalize_dicts(raw_data)

        assert len(result) == 1
        # port_id с MAC должен попасть в remote_mac, а не remote_port
        assert result[0].get("remote_mac") == "aabb.ccdd.eeff"
        # remote_port не должен содержать MAC
        assert result[0].get("remote_port") != "aabb.ccdd.eeff"

    def test_normalize_port_description_priority(self, normalizer):
        """port_description имеет приоритет над port_id."""
        raw_data = [
            {
                "local_interface": "Gi1/0/1",
                "port_id": "3",
                "port_description": "GigabitEthernet0/1",
                "system_name": "switch1",
            }
        ]
        result = normalizer.normalize_dicts(raw_data)

        assert len(result) == 1
        # remote_port = port_description
        assert result[0]["remote_port"] == "GigabitEthernet0/1"

    def test_normalize_fallback_to_mac(self, normalizer):
        """Без hostname используется MAC."""
        raw_data = [
            {
                "local_interface": "Gi1/0/1",
                "chassis_id": "aabb.ccdd.eeff",
            }
        ]
        result = normalizer.normalize_dicts(raw_data)

        assert len(result) == 1
        assert result[0]["remote_hostname"] == "[MAC:aabb.ccdd.eeff]"
        assert result[0]["neighbor_type"] == "mac"


class TestMergeProtocols:
    """Тесты объединения LLDP и CDP через Domain Layer."""

    @pytest.fixture
    def normalizer(self):
        return LLDPNormalizer()

    def test_merge_by_local_interface(self, normalizer):
        """Объединение по local_interface."""
        lldp_data = [
            {
                "local_interface": "Gi1/0/1",
                "remote_mac": "aabb.ccdd.eeff",
                "remote_hostname": "[MAC:aabb.ccdd.eeff]",
                "protocol": "LLDP",
            }
        ]
        cdp_data = [
            {
                "local_interface": "GigabitEthernet1/0/1",
                "remote_hostname": "switch1.domain.local",
                "remote_platform": "cisco WS-C3750",
                "remote_ip": "10.0.0.1",
                "protocol": "CDP",
            }
        ]

        result = normalizer.merge_lldp_cdp(lldp_data, cdp_data)

        assert len(result) == 1
        # Hostname из CDP (LLDP дал только MAC)
        assert result[0]["remote_hostname"] == "switch1.domain.local"
        # MAC из LLDP
        assert result[0]["remote_mac"] == "aabb.ccdd.eeff"
        # Platform из CDP
        assert result[0]["remote_platform"] == "cisco WS-C3750"
        # Protocol = BOTH
        assert result[0]["protocol"] == "BOTH"
