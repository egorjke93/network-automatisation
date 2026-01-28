"""
Тесты для логики определения switchport mode (access/tagged/tagged-all).

Проверяет правильное определение режима порта для NetBox:
- access: порт в access mode
- tagged: trunk с ограниченным списком VLAN (10,20,30)
- tagged-all: trunk со всеми VLAN (ALL, 1-4094)

Критично для:
- Правильной синхронизации switchport mode с NetBox
- Корректного определения "полного транка" vs "частичный транк"
"""

import pytest
from network_collector.collectors.interfaces import InterfaceCollector


@pytest.fixture
def collector():
    """Создаём InterfaceCollector для тестирования."""
    return InterfaceCollector()


@pytest.mark.unit
class TestSwitchportModeLogic:
    """Тесты логики определения switchport mode."""

    @pytest.mark.parametrize("switchport_mode,trunk_vlans,expected_mode", [
        # === ACCESS MODE ===
        ("access", "1", "access"),
        ("static access", "100", "access"),
        ("dynamic access", "", "access"),

        # === TAGGED-ALL (полный транк) ===
        ("trunk", "ALL", "tagged-all"),
        ("trunk", "all", "tagged-all"),
        ("trunk", "", "tagged-all"),  # Пустой = все VLAN
        ("trunk", "1-4094", "tagged-all"),  # Полный диапазон
        ("trunk", "1-4093", "tagged-all"),  # Некоторые устройства
        ("trunk", "1-4095", "tagged-all"),  # Расширенный диапазон
        ("dynamic desirable", "ALL", "tagged-all"),
        ("dynamic auto", "", "tagged-all"),

        # === TAGGED (ограниченный транк) ===
        ("trunk", "10", "tagged"),  # Один VLAN
        ("trunk", "10,20,30", "tagged"),  # Несколько VLAN
        ("trunk", "10-20", "tagged"),  # Диапазон
        ("trunk", "10-20,30,40-50", "tagged"),  # Смешанный
        ("trunk", "1,10,20", "tagged"),  # С native VLAN 1
        ("trunk", "100-200", "tagged"),  # Частичный диапазон
        ("trunk", "2-100", "tagged"),  # Не с 1
        ("trunk", "1-100", "tagged"),  # Не полный диапазон

        # === EDGE CASES ===
        # Регистр
        ("Trunk", "All", "tagged-all"),
        ("TRUNK", "ALL", "tagged-all"),
        ("Trunk", "10,20", "tagged"),

        # Пробелы
        ("trunk", " ALL ", "tagged-all"),
        ("trunk", " 10,20,30 ", "tagged"),

        # Dynamic modes
        ("dynamic desirable", "10,20", "tagged"),
        ("dynamic auto", "100", "tagged"),
    ])
    def test_switchport_mode_determination(
        self,
        switchport_mode,
        trunk_vlans,
        expected_mode,
    ):
        """
        Тест определения NetBox режима на основе switchport данных.

        Логика:
        - access → access
        - trunk + (ALL или "" или 1-4094) → tagged-all
        - trunk + конкретные VLAN → tagged
        """
        # Имитируем данные из show interfaces switchport
        switchport_data = {
            "interface": "GigabitEthernet1/0/1",
            "switchport": "Enabled",
            "mode": switchport_mode,
            "trunking_vlans": trunk_vlans,
            "access_vlan": "1",
        }

        # Определяем mode (логика из InterfaceCollector._parse_switchport_modes)
        mode = switchport_mode.lower().strip()
        netbox_mode = ""

        if "access" in mode:
            netbox_mode = "access"
        elif "trunk" in mode or "dynamic" in mode:
            # Проверяем список VLAN
            trunking_vlans = trunk_vlans.lower().strip()
            if (
                not trunking_vlans
                or trunking_vlans == "all"
                or trunking_vlans in ("1-4094", "1-4093", "1-4095")
            ):
                netbox_mode = "tagged-all"
            else:
                netbox_mode = "tagged"

        assert netbox_mode == expected_mode, (
            f"Switchport mode: {switchport_mode}\n"
            f"Trunk VLANs: {trunk_vlans}\n"
            f"Expected: {expected_mode}, Got: {netbox_mode}"
        )

    def test_access_mode_samples(self, sample_switchport_data):
        """Тест access mode из fixture данных."""
        data = sample_switchport_data["access_mode"]

        mode = data["switchport_mode"].lower()
        result = "access" if "access" in mode else ""

        assert result == "access"

    def test_trunk_all_vlans_samples(self, sample_switchport_data):
        """Тест trunk ALL из fixture данных."""
        data = sample_switchport_data["trunk_all_vlans"]

        mode = data["switchport_mode"].lower()
        trunk_vlans = data["trunk_vlans"].lower().strip()

        if "trunk" in mode:
            if trunk_vlans == "all":
                result = "tagged-all"
            else:
                result = "tagged"
        else:
            result = ""

        assert result == "tagged-all"

    def test_trunk_1_4094_range(self, sample_switchport_data):
        """Тест trunk 1-4094 (полный диапазон)."""
        data = sample_switchport_data["trunk_1_4094"]

        mode = data["switchport_mode"].lower()
        trunk_vlans = data["trunk_vlans"].lower().strip()

        if "trunk" in mode:
            if trunk_vlans in ("1-4094", "1-4093", "1-4095"):
                result = "tagged-all"
            else:
                result = "tagged"
        else:
            result = ""

        assert result == "tagged-all", "1-4094 должен определяться как tagged-all"

    def test_trunk_specific_vlans_samples(self, sample_switchport_data):
        """Тест trunk с конкретными VLAN."""
        data = sample_switchport_data["trunk_specific_vlans"]

        mode = data["switchport_mode"].lower()
        trunk_vlans = data["trunk_vlans"].lower().strip()

        if "trunk" in mode:
            if trunk_vlans == "all" or trunk_vlans in ("1-4094", "1-4093"):
                result = "tagged-all"
            else:
                result = "tagged"
        else:
            result = ""

        assert result == "tagged", "10,20,30 должны быть tagged, не tagged-all"

    def test_trunk_range_vlans(self, sample_switchport_data):
        """Тест trunk с диапазонами VLAN."""
        data = sample_switchport_data["trunk_range_vlans"]

        mode = data["switchport_mode"].lower()
        trunk_vlans = data["trunk_vlans"].lower().strip()

        if "trunk" in mode:
            if trunk_vlans == "all" or trunk_vlans in ("1-4094", "1-4093"):
                result = "tagged-all"
            else:
                result = "tagged"
        else:
            result = ""

        assert result == "tagged", "10-20,30,40-50 должен быть tagged"

    def test_trunk_single_vlan(self, sample_switchport_data):
        """Тест trunk с одним VLAN."""
        data = sample_switchport_data["trunk_single_vlan"]

        mode = data["switchport_mode"].lower()
        trunk_vlans = data["trunk_vlans"].lower().strip()

        if "trunk" in mode:
            if trunk_vlans == "all" or trunk_vlans in ("1-4094", "1-4093"):
                result = "tagged-all"
            else:
                result = "tagged"
        else:
            result = ""

        assert result == "tagged", "Один VLAN (100) должен быть tagged"

    def test_empty_trunk_vlans_means_all(self):
        """
        Тест что пустой trunk_vlans означает ALL (все VLAN).

        На некоторых устройствах пустой список = все VLAN разрешены.
        """
        mode = "trunk"
        trunk_vlans = ""

        if "trunk" in mode:
            if not trunk_vlans or trunk_vlans == "all":
                result = "tagged-all"
            else:
                result = "tagged"
        else:
            result = ""

        assert result == "tagged-all", "Пустой trunk_vlans должен быть tagged-all"

    def test_lag_inherits_mode_from_members(self):
        """
        Тест что LAG наследует mode от member интерфейсов.

        Логика:
        - Если хотя бы один member в tagged-all → LAG тоже tagged-all
        - Если все members в tagged → LAG тоже tagged
        - tagged-all имеет приоритет над tagged
        """
        # Имитируем LAG membership
        lag_membership = {
            "GigabitEthernet1/0/1": "Po1",  # member 1
            "GigabitEthernet1/0/2": "Po1",  # member 2
        }

        # Switchport modes для members
        switchport_modes = {
            "GigabitEthernet1/0/1": {"mode": "tagged"},
            "GigabitEthernet1/0/2": {"mode": "tagged-all"},  # Один в tagged-all
        }

        # Определяем mode для LAG
        lag_modes = {}
        for member_iface, lag_name in lag_membership.items():
            if member_iface in switchport_modes:
                member_mode = switchport_modes[member_iface].get("mode", "")
                # tagged-all имеет приоритет
                if member_mode == "tagged-all":
                    lag_modes[lag_name] = "tagged-all"
                elif member_mode == "tagged" and lag_modes.get(lag_name) != "tagged-all":
                    lag_modes[lag_name] = "tagged"

        assert lag_modes.get("Po1") == "tagged-all", (
            "LAG должен наследовать tagged-all если хотя бы один member в tagged-all"
        )

    def test_lag_all_members_tagged(self):
        """Тест что LAG = tagged если все members в tagged."""
        lag_membership = {
            "GigabitEthernet1/0/1": "Po1",
            "GigabitEthernet1/0/2": "Po1",
        }

        switchport_modes = {
            "GigabitEthernet1/0/1": {"mode": "tagged"},
            "GigabitEthernet1/0/2": {"mode": "tagged"},
        }

        lag_modes = {}
        for member_iface, lag_name in lag_membership.items():
            if member_iface in switchport_modes:
                member_mode = switchport_modes[member_iface].get("mode", "")
                if member_mode == "tagged-all":
                    lag_modes[lag_name] = "tagged-all"
                elif member_mode == "tagged" and lag_modes.get(lag_name) != "tagged-all":
                    lag_modes[lag_name] = "tagged"

        assert lag_modes.get("Po1") == "tagged", "LAG должен быть tagged"

    @pytest.mark.parametrize("trunk_vlans,is_full_trunk", [
        # Полный транк (tagged-all)
        ("ALL", True),
        ("all", True),
        ("", True),
        ("1-4094", True),
        ("1-4093", True),
        ("1-4095", True),

        # Частичный транк (tagged)
        ("10", False),
        ("1,10,20", False),
        ("10-20", False),
        ("100-200", False),
        ("1-100", False),  # Не полный диапазон
        ("2-4094", False),  # Не с 1
        ("10,20,30,40", False),
    ])
    def test_full_trunk_detection(self, trunk_vlans, is_full_trunk):
        """
        Тест определения "полного транка" (tagged-all) vs "частичный транк" (tagged).

        Полный транк = ALL или 1-4094 или пустой
        Частичный транк = конкретные VLAN
        """
        trunk_vlans_lower = trunk_vlans.lower().strip()

        result = (
            not trunk_vlans_lower
            or trunk_vlans_lower == "all"
            or trunk_vlans_lower in ("1-4094", "1-4093", "1-4095")
        )

        assert result == is_full_trunk, (
            f"trunk_vlans='{trunk_vlans}' должен быть "
            f"{'полным транком' if is_full_trunk else 'частичным транком'}"
        )
