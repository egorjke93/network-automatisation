"""Тесты парсинга port-security sticky MAC из show running-config.

Fixture: реалистичный show running-config с port-security на access-коммутаторе.
Интерфейсы:
  Gi0/1, Gi0/2   — trunk (без port-security)
  Gi0/3           — 1 sticky MAC (PC-Ivanov)
  Gi0/4           — 2 sticky MAC (IP-телефон + ПК)
  Gi0/5           — 3 sticky MAC (хаб, 3 устройства)
  Gi0/6           — 1 sticky MAC (принтер, VLAN 300)
  Gi0/7           — access без port-security
  Gi0/8           — shutdown, без port-security
  Gi0/9           — 2 sticky MAC (VoIP, VLAN 200)
  Gi0/10          — trunk (без port-security)
Итого: 9 sticky MAC на 5 интерфейсах.
"""

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


def _prepare_sticky_for_merge(sticky_parsed):
    """Нормализует MAC формат sticky записей для merge."""
    result = []
    for s in sticky_parsed:
        nm = normalize_mac(s["mac"], format="ieee")
        result.append({
            "mac": nm if nm else s["mac"],
            "interface": s["interface"],
            "vlan": s["vlan"],
            "type": s["type"],
        })
    return result


class TestPortSecurityTemplate:
    """Тесты TextFSM шаблона cisco_ios_port_security на реалистичном конфиге."""

    def test_parse_all_sticky_macs(self, parser, running_config):
        """Из полного running-config находит все 9 sticky MAC."""
        result = parser.parse(running_config, "cisco_ios", "port-security")

        assert len(result) == 9

    def test_single_mac_interface(self, parser, running_config):
        """Gi0/3: один sticky MAC (PC-Ivanov)."""
        result = parser.parse(running_config, "cisco_ios", "port-security")

        gi03 = [r for r in result if "0/3" in r["interface"]]
        assert len(gi03) == 1
        assert gi03[0]["mac"] == "0011.2233.4455"
        assert gi03[0]["vlan"] == "100"
        assert gi03[0]["type"] == "sticky"

    def test_two_macs_phone_plus_pc(self, parser, running_config):
        """Gi0/4: два sticky MAC (IP-телефон + ПК за ним)."""
        result = parser.parse(running_config, "cisco_ios", "port-security")

        gi04 = [r for r in result if "0/4" in r["interface"]]
        assert len(gi04) == 2
        macs = {r["mac"] for r in gi04}
        assert "aabb.ccdd.ee01" in macs
        assert "aabb.ccdd.ee02" in macs
        for r in gi04:
            assert r["vlan"] == "100"

    def test_three_macs_hub(self, parser, running_config):
        """Gi0/5: три sticky MAC (хаб с 3 устройствами)."""
        result = parser.parse(running_config, "cisco_ios", "port-security")

        gi05 = [r for r in result if "0/5" in r["interface"]]
        assert len(gi05) == 3
        macs = {r["mac"] for r in gi05}
        assert "1111.2222.3333" in macs
        assert "4444.5555.6666" in macs
        assert "7777.8888.9999" in macs

    def test_printer_different_vlan(self, parser, running_config):
        """Gi0/6: принтер в VLAN 300 (не 100)."""
        result = parser.parse(running_config, "cisco_ios", "port-security")

        gi06 = [r for r in result if "0/6" in r["interface"]]
        assert len(gi06) == 1
        assert gi06[0]["vlan"] == "300"
        assert gi06[0]["mac"] == "dead.beef.0001"

    def test_voip_vlan_200(self, parser, running_config):
        """Gi0/9: VoIP в VLAN 200."""
        result = parser.parse(running_config, "cisco_ios", "port-security")

        gi09 = [r for r in result if "0/9" in r["interface"]]
        assert len(gi09) == 2
        for r in gi09:
            assert r["vlan"] == "200"

    def test_trunk_interfaces_skipped(self, parser, running_config):
        """Gi0/1, Gi0/2, Gi0/10 — trunk без port-security, не попадают."""
        result = parser.parse(running_config, "cisco_ios", "port-security")

        gi01 = [r for r in result if r["interface"].endswith("0/1")]
        gi02 = [r for r in result if r["interface"].endswith("0/2")]
        gi10 = [r for r in result if "0/10" in r["interface"]]
        assert len(gi01) == 0
        assert len(gi02) == 0
        assert len(gi10) == 0

    def test_access_without_ps_skipped(self, parser, running_config):
        """Gi0/7 (access без ps) и Gi0/8 (shutdown) — не попадают."""
        result = parser.parse(running_config, "cisco_ios", "port-security")

        gi07 = [r for r in result if "0/7" in r["interface"]]
        gi08 = [r for r in result if "0/8" in r["interface"]]
        assert len(gi07) == 0
        assert len(gi08) == 0

    def test_vlan_not_inherited_from_previous(self, parser, running_config):
        """VLAN не наследуется: Gi0/6 (VLAN 300) после Gi0/5 (VLAN 100)."""
        result = parser.parse(running_config, "cisco_ios", "port-security")

        gi05 = [r for r in result if "0/5" in r["interface"]]
        gi06 = [r for r in result if "0/6" in r["interface"]]
        assert gi05[0]["vlan"] == "100"
        assert gi06[0]["vlan"] == "300"

    def test_all_records_have_type_sticky(self, parser, running_config):
        """Все записи имеют type=sticky."""
        result = parser.parse(running_config, "cisco_ios", "port-security")

        for r in result:
            assert r["type"] == "sticky"

    def test_cisco_iosxe_same_result(self, parser, running_config):
        """cisco_iosxe использует тот же шаблон — результат идентичный."""
        result_ios = parser.parse(running_config, "cisco_ios", "port-security")
        result_iosxe = parser.parse(running_config, "cisco_iosxe", "port-security")

        assert len(result_ios) == len(result_iosxe) == 9

    def test_empty_config(self, parser):
        """Конфиг без port-security — пустой результат."""
        config = Path(__file__).parent.parent / "fixtures" / "cisco_ios" / "show_running_config.txt"
        result = parser.parse(config.read_text(), "cisco_ios", "port-security")

        assert result == []

    def test_unknown_platform(self, parser, running_config):
        """Неизвестная платформа — пустой результат (не ошибка)."""
        result = parser.parse(running_config, "unknown_platform", "port-security")

        assert result == []

    def test_five_macs_on_one_interface(self, parser):
        """Стресс: 5 sticky MAC на одном интерфейсе."""
        config = (
            "interface GigabitEthernet0/10\n"
            " switchport access vlan 50\n"
            " switchport port-security\n"
            " switchport port-security maximum 5\n"
            " switchport port-security mac-address sticky\n"
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
    """Интеграционные тесты: парсинг sticky → merge с MAC-таблицей."""

    def test_online_mac_not_duplicated(self, parser):
        """MAC в обеих таблицах — 1 запись (online), не дублируется."""
        config = (
            "interface GigabitEthernet0/1\n"
            " switchport access vlan 100\n"
            " switchport port-security mac-address sticky 0011.2233.4455\n"
            "!\nend\n"
        )
        sticky = _prepare_sticky_for_merge(
            parser.parse(config, "cisco_ios", "port-security")
        )
        mac_table = [
            {"mac": "00:11:22:33:44:55", "interface": "Gi0/1", "status": "online"},
        ]

        normalizer = MACNormalizer(mac_format="ieee")
        result = normalizer.merge_sticky_macs(mac_table, sticky)

        assert len(result) == 1
        assert result[0]["status"] == "online"

    def test_offline_sticky_added(self, parser):
        """Sticky MAC без записи в MAC-таблице — offline."""
        config = (
            "interface GigabitEthernet0/1\n"
            " switchport access vlan 100\n"
            " switchport port-security mac-address sticky aabb.ccdd.eeff\n"
            "!\nend\n"
        )
        sticky = _prepare_sticky_for_merge(
            parser.parse(config, "cisco_ios", "port-security")
        )

        normalizer = MACNormalizer(mac_format="ieee")
        result = normalizer.merge_sticky_macs([], sticky, hostname="sw1", device_ip="10.0.0.1")

        assert len(result) == 1
        assert result[0]["status"] == "offline"
        assert result[0]["hostname"] == "sw1"
        assert result[0]["device_ip"] == "10.0.0.1"

    def test_phone_plus_pc_partial_online(self, parser):
        """IP-телефон online + ПК за ним offline (2 sticky, 1 в MAC-таблице)."""
        config = (
            "interface GigabitEthernet0/4\n"
            " switchport access vlan 100\n"
            " switchport port-security mac-address sticky aabb.ccdd.ee01\n"
            " switchport port-security mac-address sticky aabb.ccdd.ee02\n"
            "!\nend\n"
        )
        sticky = _prepare_sticky_for_merge(
            parser.parse(config, "cisco_ios", "port-security")
        )

        mac_table = [
            {"mac": "aa:bb:cc:dd:ee:01", "interface": "Gi0/4", "status": "online"},
        ]

        normalizer = MACNormalizer(mac_format="ieee")
        result = normalizer.merge_sticky_macs(mac_table, sticky)

        assert len(result) == 2
        online = [r for r in result if r["status"] == "online"]
        offline = [r for r in result if r["status"] == "offline"]
        assert len(online) == 1
        assert len(offline) == 1
        assert offline[0]["mac"] == "aa:bb:cc:dd:ee:02"

    def test_hub_all_offline(self, parser):
        """Хаб с 3 устройствами — все offline (ни одного в MAC-таблице)."""
        config = (
            "interface GigabitEthernet0/5\n"
            " switchport access vlan 100\n"
            " switchport port-security mac-address sticky 1111.2222.3333\n"
            " switchport port-security mac-address sticky 4444.5555.6666\n"
            " switchport port-security mac-address sticky 7777.8888.9999\n"
            "!\nend\n"
        )
        sticky = _prepare_sticky_for_merge(
            parser.parse(config, "cisco_ios", "port-security")
        )

        normalizer = MACNormalizer(mac_format="ieee")
        result = normalizer.merge_sticky_macs([], sticky, hostname="sw1", device_ip="10.0.0.1")

        assert len(result) == 3
        for r in result:
            assert r["status"] == "offline"
            assert r["hostname"] == "sw1"

    def test_full_realistic_scenario(self, parser, running_config):
        """Полный сценарий: реальный конфиг + MAC-таблица с пересечением."""
        sticky = _prepare_sticky_for_merge(
            parser.parse(running_config, "cisco_ios", "port-security")
        )
        assert len(sticky) == 9

        # MAC-таблица: часть устройств online
        mac_table = [
            # Gi0/3 PC-Ivanov — online
            {"mac": "00:11:22:33:44:55", "interface": "Gi0/3", "vlan": "100",
             "status": "online", "hostname": "SW-ACCESS-01", "device_ip": "10.100.0.1"},
            # Gi0/4 телефон — online, ПК — offline (нет в таблице)
            {"mac": "aa:bb:cc:dd:ee:01", "interface": "Gi0/4", "vlan": "100",
             "status": "online", "hostname": "SW-ACCESS-01", "device_ip": "10.100.0.1"},
            # Gi0/5 хаб — все 3 offline (нет в таблице)
            # Gi0/6 принтер — online
            {"mac": "de:ad:be:ef:00:01", "interface": "Gi0/6", "vlan": "300",
             "status": "online", "hostname": "SW-ACCESS-01", "device_ip": "10.100.0.1"},
            # Gi0/9 VoIP — один online, один offline
            {"mac": "cc:cc:dd:dd:ee:ee", "interface": "Gi0/9", "vlan": "200",
             "status": "online", "hostname": "SW-ACCESS-01", "device_ip": "10.100.0.1"},
        ]

        normalizer = MACNormalizer(mac_format="ieee")
        result = normalizer.merge_sticky_macs(
            mac_table, sticky, hostname="SW-ACCESS-01", device_ip="10.100.0.1"
        )

        online = [r for r in result if r.get("status") == "online"]
        offline = [r for r in result if r.get("status") == "offline"]

        # 4 online (из MAC-таблицы) + 5 offline sticky
        assert len(online) == 4
        assert len(offline) == 5
        assert len(result) == 9

        # Проверяем конкретные offline
        offline_macs = {r["mac"] for r in offline}
        assert "aa:bb:cc:dd:ee:02" in offline_macs  # ПК за телефоном
        assert "11:11:22:22:33:33" in offline_macs  # Хаб device 1
        assert "44:44:55:55:66:66" in offline_macs  # Хаб device 2
        assert "77:77:88:88:99:99" in offline_macs  # Хаб device 3
        assert "ff:ff:00:00:11:11" in offline_macs  # VoIP второй
