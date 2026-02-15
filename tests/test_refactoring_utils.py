"""
Тесты утилит рефакторинга: SyncStats, SECONDARY_COMMANDS, _detect_type_by_name_prefix.
"""

import pytest

from network_collector.core.constants.commands import SECONDARY_COMMANDS, get_secondary_command
from network_collector.core.constants.netbox import _detect_type_by_name_prefix
from network_collector.netbox.sync.base import SyncStats


class TestSyncStats:
    """Тесты SyncStats — инициализация stats/details."""

    def test_basic_operations(self):
        """Базовые операции создают stats и details."""
        ss = SyncStats("created", "updated", "deleted", "skipped", "failed")
        assert ss.stats == {
            "created": 0, "updated": 0, "deleted": 0, "skipped": 0, "failed": 0,
        }
        assert "create" in ss.details
        assert "update" in ss.details
        assert "delete" in ss.details
        assert "skip" in ss.details

    def test_failed_no_detail_key(self):
        """failed не создаёт ключ в details (нет маппинга)."""
        ss = SyncStats("created", "failed")
        assert ss.stats == {"created": 0, "failed": 0}
        assert "create" in ss.details
        assert "fail" not in ss.details

    def test_minimal_stats(self):
        """Минимальный набор (vlans)."""
        ss = SyncStats("created", "skipped", "failed")
        assert ss.stats == {"created": 0, "skipped": 0, "failed": 0}
        assert ss.details == {"create": [], "skip": []}

    def test_result_includes_details(self):
        """result() возвращает stats + details."""
        ss = SyncStats("created", "updated")
        ss.stats["created"] = 5
        ss.details["create"].append({"name": "test"})

        result = ss.result()
        assert result["created"] == 5
        assert result["details"]["create"] == [{"name": "test"}]

    def test_stats_are_mutable(self):
        """stats и details можно изменять напрямую."""
        ss = SyncStats("created", "skipped")
        stats, details = ss.stats, ss.details

        stats["created"] += 1
        details["create"].append({"name": "item1"})

        assert ss.stats["created"] == 1
        assert len(ss.details["create"]) == 1

    def test_cables_stats(self):
        """Кабели — с already_exists."""
        ss = SyncStats("created", "deleted", "skipped", "failed", "already_exists")
        assert "already_exists" in ss.stats
        assert ss.stats["already_exists"] == 0


class TestSecondaryCommands:
    """Тесты SECONDARY_COMMANDS — централизованные вторичные команды."""

    def test_lag_commands_present(self):
        """LAG команды для основных платформ."""
        lag = SECONDARY_COMMANDS["lag"]
        assert "cisco_ios" in lag
        assert "qtech" in lag
        assert lag["cisco_ios"] == "show etherchannel summary"
        assert lag["qtech"] == "show aggregatePort summary"

    def test_switchport_commands_present(self):
        """Switchport команды для основных платформ."""
        sw = SECONDARY_COMMANDS["switchport"]
        assert "cisco_ios" in sw
        assert "qtech" in sw
        assert sw["cisco_nxos"] == "show interface switchport"

    def test_transceiver_commands_present(self):
        """Transceiver команды для NX-OS и QTech."""
        tr = SECONDARY_COMMANDS["transceiver"]
        assert "cisco_nxos" in tr
        assert "qtech" in tr
        assert "qtech_qsw" in tr
        assert tr["cisco_nxos"] == "show interface transceiver"

    def test_get_secondary_command(self):
        """get_secondary_command возвращает команду."""
        assert get_secondary_command("lag", "cisco_ios") == "show etherchannel summary"
        assert get_secondary_command("lag", "unknown_platform") == ""
        assert get_secondary_command("nonexistent", "cisco_ios") == ""

    def test_media_type_platforms(self):
        """Media type для NX-OS и QTech (show interface status / show interface transceiver)."""
        mt = SECONDARY_COMMANDS["media_type"]
        assert "cisco_nxos" in mt
        assert "qtech" in mt
        assert "qtech_qsw" in mt
        assert "cisco_ios" not in mt

    def test_lldp_summary_present(self):
        """LLDP summary для Cisco/Arista."""
        ls = SECONDARY_COMMANDS["lldp_summary"]
        assert "cisco_ios" in ls
        assert "arista_eos" in ls

    def test_interface_errors_present(self):
        """Команды ошибок интерфейсов."""
        ie = SECONDARY_COMMANDS["interface_errors"]
        assert "cisco_ios" in ie
        assert "arista_eos" in ie


class TestDetectTypeByNamePrefix:
    """Тесты _detect_type_by_name_prefix — определение NetBox типа по имени."""

    @pytest.mark.parametrize("name,expected", [
        ("hundredgigabitethernet0/55", "100gbase-x-qsfp28"),
        ("hu0/55", "100gbase-x-qsfp28"),
        ("fortygigabitethernet1/1", "40gbase-x-qsfpp"),
        ("fo1/0/1", "40gbase-x-qsfpp"),
        ("twentyfivegige1/0/27", "25gbase-x-sfp28"),
        ("twe1/0/27", "25gbase-x-sfp28"),
        ("tengigabitethernet1/1", "10gbase-x-sfpp"),
        ("te1/1", "10gbase-x-sfpp"),
        ("tfgigabitethernet0/1", "10gbase-x-sfpp"),
        ("tf0/1", "10gbase-x-sfpp"),
        ("fastethernet0/1", "100base-tx"),
        ("fa0/1", "100base-tx"),
    ])
    def test_known_prefixes(self, name, expected):
        """Известные префиксы возвращают правильный тип."""
        assert _detect_type_by_name_prefix(name) == expected

    def test_gigabit_default_copper(self):
        """GigabitEthernet без SFP — медь."""
        assert _detect_type_by_name_prefix("gigabitethernet0/1") == "1000base-t"
        assert _detect_type_by_name_prefix("gi0/1") == "1000base-t"

    def test_gigabit_with_sfp(self):
        """GigabitEthernet с SFP — оптика."""
        result = _detect_type_by_name_prefix("gi0/1", media_lower="sfp-1000base-sx")
        assert result == "1000base-x-sfp"

    def test_gigabit_with_sfp_in_hw(self):
        """GigabitEthernet с SFP в hardware_type."""
        result = _detect_type_by_name_prefix("gi0/1", hw_lower="gigabit sfp")
        assert result == "1000base-x-sfp"

    def test_unknown_prefix_returns_empty(self):
        """Неизвестный префикс — пустая строка."""
        assert _detect_type_by_name_prefix("vlan100") == ""
        assert _detect_type_by_name_prefix("loopback0") == ""

    def test_short_prefix_needs_digit(self):
        """Короткий префикс без цифры не совпадает."""
        # "te" без цифры после — не должен совпать
        assert _detect_type_by_name_prefix("test_interface") == ""
        assert _detect_type_by_name_prefix("team1") == ""

    def test_hu_without_digit(self):
        """'hu' без цифры — не совпадает."""
        assert _detect_type_by_name_prefix("hub0") == ""
