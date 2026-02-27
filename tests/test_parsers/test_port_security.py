"""Тесты парсинга port-security sticky MAC из show running-config."""

from pathlib import Path

import pytest

from network_collector.parsers.textfsm_parser import NTCParser
from network_collector.core.domain.mac import MACNormalizer
from network_collector.core.constants import normalize_mac


FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "cisco_ios" / "show_running_config_port_security.txt"


@pytest.fixture
def parser():
    return NTCParser()


@pytest.fixture
def running_config():
    return FIXTURE_PATH.read_text()


class TestPortSecurityTemplate:
    """Тесты TextFSM шаблона cisco_ios_port_security."""

    def test_parse_all_sticky_macs(self, parser, running_config):
        """Парсинг всех sticky MAC из running-config."""
        result = parser.parse(running_config, "cisco_ios", "port-security")

        assert len(result) == 4

    def test_single_mac_per_interface(self, parser, running_config):
        """Gi0/1: один sticky MAC."""
        result = parser.parse(running_config, "cisco_ios", "port-security")

        gi01 = [r for r in result if "0/1" in r["interface"]]
        assert len(gi01) == 1
        assert gi01[0]["mac"] == "0011.2233.4455"
        assert gi01[0]["vlan"] == "100"
        assert gi01[0]["type"] == "sticky"

    def test_multiple_macs_per_interface(self, parser, running_config):
        """Gi0/2: два sticky MAC на одном интерфейсе (регрессия Filldown бага)."""
        result = parser.parse(running_config, "cisco_ios", "port-security")

        gi02 = [r for r in result if "0/2" in r["interface"]]
        assert len(gi02) == 2
        macs = {r["mac"] for r in gi02}
        assert "aabb.ccdd.eeff" in macs
        assert "1122.3344.5566" in macs
        # Оба должны иметь VLAN 200
        for r in gi02:
            assert r["vlan"] == "200"

    def test_interface_without_port_security_skipped(self, parser, running_config):
        """Gi0/3: нет port-security — не должен попасть в результат."""
        result = parser.parse(running_config, "cisco_ios", "port-security")

        gi03 = [r for r in result if "0/3" in r["interface"]]
        assert len(gi03) == 0

    def test_vlan_resets_between_interfaces(self, parser, running_config):
        """Gi0/4: VLAN 300, не должен унаследовать VLAN 200 от Gi0/2."""
        result = parser.parse(running_config, "cisco_ios", "port-security")

        gi04 = [r for r in result if "0/4" in r["interface"]]
        assert len(gi04) == 1
        assert gi04[0]["vlan"] == "300"
        assert gi04[0]["mac"] == "dead.beef.0001"

    def test_all_records_have_type_sticky(self, parser, running_config):
        """Все записи должны иметь type=sticky."""
        result = parser.parse(running_config, "cisco_ios", "port-security")

        for r in result:
            assert r["type"] == "sticky"

    def test_cisco_iosxe_uses_same_template(self, parser, running_config):
        """cisco_iosxe использует тот же шаблон что и cisco_ios."""
        result_ios = parser.parse(running_config, "cisco_ios", "port-security")
        result_iosxe = parser.parse(running_config, "cisco_iosxe", "port-security")

        assert len(result_ios) == len(result_iosxe)

    def test_empty_config_returns_empty(self, parser):
        """Конфиг без port-security — пустой результат."""
        config = "interface GigabitEthernet0/1\n no shutdown\n!\nend\n"
        result = parser.parse(config, "cisco_ios", "port-security")

        assert result == []

    def test_unknown_platform_returns_empty(self, parser, running_config):
        """Неизвестная платформа без шаблона — пустой результат."""
        result = parser.parse(running_config, "unknown_platform", "port-security")

        assert result == []

    def test_many_macs_on_one_interface(self, parser):
        """5 sticky MAC на одном интерфейсе — все должны быть найдены."""
        config = (
            "interface GigabitEthernet0/10\n"
            " switchport access vlan 50\n"
            " switchport port-security mac-address sticky 0001.0001.0001\n"
            " switchport port-security mac-address sticky 0002.0002.0002\n"
            " switchport port-security mac-address sticky 0003.0003.0003\n"
            " switchport port-security mac-address sticky 0004.0004.0004\n"
            " switchport port-security mac-address sticky 0005.0005.0005\n"
            "!\nend\n"
        )
        result = parser.parse(config, "cisco_ios", "port-security")

        assert len(result) == 5
        for r in result:
            assert "0/10" in r["interface"]
            assert r["vlan"] == "50"


class TestPortSecurityMerge:
    """Интеграционные тесты: парсинг → merge с MAC-таблицей."""

    def test_online_mac_not_duplicated(self, parser):
        """MAC из sticky, который уже есть в MAC-таблице — не дублируется."""
        config = (
            "interface GigabitEthernet0/1\n"
            " switchport access vlan 100\n"
            " switchport port-security mac-address sticky 0011.2233.4455\n"
            "!\nend\n"
        )
        sticky_parsed = parser.parse(config, "cisco_ios", "port-security")
        sticky_for_merge = []
        for s in sticky_parsed:
            nm = normalize_mac(s["mac"], format="ieee")
            sticky_for_merge.append({
                "mac": nm if nm else s["mac"],
                "interface": s["interface"],
                "vlan": s["vlan"],
                "type": s["type"],
            })

        mac_table = [
            {"mac": "00:11:22:33:44:55", "interface": "Gi0/1", "status": "online"},
        ]

        normalizer = MACNormalizer(mac_format="ieee")
        result = normalizer.merge_sticky_macs(mac_table, sticky_for_merge)

        assert len(result) == 1
        assert result[0]["status"] == "online"

    def test_offline_sticky_added(self, parser):
        """Sticky MAC без записи в MAC-таблице — добавляется как offline."""
        config = (
            "interface GigabitEthernet0/1\n"
            " switchport access vlan 100\n"
            " switchport port-security mac-address sticky aabb.ccdd.eeff\n"
            "!\nend\n"
        )
        sticky_parsed = parser.parse(config, "cisco_ios", "port-security")
        sticky_for_merge = []
        for s in sticky_parsed:
            nm = normalize_mac(s["mac"], format="ieee")
            sticky_for_merge.append({
                "mac": nm if nm else s["mac"],
                "interface": s["interface"],
                "vlan": s["vlan"],
                "type": s["type"],
            })

        mac_table = []  # Пустая таблица — устройство offline

        normalizer = MACNormalizer(mac_format="ieee")
        result = normalizer.merge_sticky_macs(mac_table, sticky_for_merge, hostname="sw1", device_ip="10.0.0.1")

        assert len(result) == 1
        assert result[0]["status"] == "offline"
        assert result[0]["hostname"] == "sw1"
        assert result[0]["device_ip"] == "10.0.0.1"

    def test_multiple_sticky_partial_online(self, parser):
        """2 sticky на Gi0/2: один online (в таблице), другой offline."""
        config = (
            "interface GigabitEthernet0/2\n"
            " switchport access vlan 200\n"
            " switchport port-security mac-address sticky aabb.ccdd.eeff\n"
            " switchport port-security mac-address sticky 1122.3344.5566\n"
            "!\nend\n"
        )
        sticky_parsed = parser.parse(config, "cisco_ios", "port-security")
        assert len(sticky_parsed) == 2

        sticky_for_merge = []
        for s in sticky_parsed:
            nm = normalize_mac(s["mac"], format="ieee")
            sticky_for_merge.append({
                "mac": nm if nm else s["mac"],
                "interface": s["interface"],
                "vlan": s["vlan"],
                "type": s["type"],
            })

        # Только один MAC в таблице (online)
        mac_table = [
            {"mac": "aa:bb:cc:dd:ee:ff", "interface": "Gi0/2", "status": "online"},
        ]

        normalizer = MACNormalizer(mac_format="ieee")
        result = normalizer.merge_sticky_macs(mac_table, sticky_for_merge)

        assert len(result) == 2
        online = [r for r in result if r["status"] == "online"]
        offline = [r for r in result if r["status"] == "offline"]
        assert len(online) == 1
        assert len(offline) == 1
        assert offline[0]["mac"] == "11:22:33:44:55:66"

    def test_full_chain_many_interfaces(self, parser):
        """Полная цепочка: 3 интерфейса, 6 sticky, 2 online."""
        config = (
            "interface GigabitEthernet0/1\n"
            " switchport access vlan 100\n"
            " switchport port-security mac-address sticky 0011.2233.4455\n"
            "!\n"
            "interface GigabitEthernet0/2\n"
            " switchport access vlan 200\n"
            " switchport port-security mac-address sticky aabb.ccdd.eeff\n"
            " switchport port-security mac-address sticky 1122.3344.5566\n"
            "!\n"
            "interface GigabitEthernet0/3\n"
            " switchport access vlan 300\n"
            " switchport port-security mac-address sticky dead.beef.0001\n"
            " switchport port-security mac-address sticky dead.beef.0002\n"
            " switchport port-security mac-address sticky dead.beef.0003\n"
            "!\nend\n"
        )
        sticky_parsed = parser.parse(config, "cisco_ios", "port-security")
        assert len(sticky_parsed) == 6

        sticky_for_merge = []
        for s in sticky_parsed:
            nm = normalize_mac(s["mac"], format="ieee")
            sticky_for_merge.append({
                "mac": nm if nm else s["mac"],
                "interface": s["interface"],
                "vlan": s["vlan"],
                "type": s["type"],
            })

        mac_table = [
            {"mac": "00:11:22:33:44:55", "interface": "Gi0/1", "status": "online"},
            {"mac": "aa:bb:cc:dd:ee:ff", "interface": "Gi0/2", "status": "online"},
        ]

        normalizer = MACNormalizer(mac_format="ieee")
        result = normalizer.merge_sticky_macs(mac_table, sticky_for_merge, hostname="sw1", device_ip="10.0.0.1")

        assert len(result) == 6
        online = [r for r in result if r["status"] == "online"]
        offline = [r for r in result if r["status"] == "offline"]
        assert len(online) == 2
        assert len(offline) == 4
