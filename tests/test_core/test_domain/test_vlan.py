"""
Tests for VLAN domain logic.

Проверяет:
- Парсинг диапазонов VLAN
- VlanSet операции (сравнение, разница)
"""

import pytest

from network_collector.core.domain.vlan import (
    parse_vlan_range,
    is_full_vlan_range,
    VlanSet,
    FULL_VLAN_RANGES,
)


@pytest.mark.unit
class TestParseVlanRange:
    """Тесты парсинга диапазонов VLAN."""

    def test_single_vlan(self):
        """Одиночный VLAN."""
        assert parse_vlan_range("10") == [10]
        assert parse_vlan_range("100") == [100]
        assert parse_vlan_range("1") == [1]

    def test_multiple_vlans(self):
        """Список VLAN через запятую."""
        assert parse_vlan_range("10,20,30") == [10, 20, 30]
        assert parse_vlan_range("1,2,3,4") == [1, 2, 3, 4]

    def test_vlan_range(self):
        """Диапазон VLAN (start-end)."""
        assert parse_vlan_range("10-15") == [10, 11, 12, 13, 14, 15]
        assert parse_vlan_range("1-3") == [1, 2, 3]

    def test_mixed_vlans_and_ranges(self):
        """Комбинация одиночных VLAN и диапазонов."""
        assert parse_vlan_range("10,20,30-32,50") == [10, 20, 30, 31, 32, 50]
        assert parse_vlan_range("1,5-7,10") == [1, 5, 6, 7, 10]

    def test_empty_string(self):
        """Пустая строка возвращает пустой список."""
        assert parse_vlan_range("") == []
        assert parse_vlan_range("  ") == []

    def test_all_keyword(self):
        """Ключевое слово 'all' возвращает пустой список."""
        assert parse_vlan_range("all") == []
        assert parse_vlan_range("ALL") == []
        assert parse_vlan_range("All") == []

    def test_full_ranges(self):
        """Полные диапазоны (1-4094, etc) возвращают пустой список."""
        assert parse_vlan_range("1-4094") == []
        assert parse_vlan_range("1-4093") == []
        assert parse_vlan_range("1-4095") == []

    def test_none_keyword(self):
        """Ключевое слово 'none' возвращает пустой список."""
        assert parse_vlan_range("none") == []
        assert parse_vlan_range("NONE") == []

    def test_whitespace_handling(self):
        """Обработка пробелов."""
        assert parse_vlan_range(" 10 , 20 , 30 ") == [10, 20, 30]
        assert parse_vlan_range(" 10 - 12 ") == [10, 11, 12]

    def test_duplicates_removed(self):
        """Дубликаты удаляются."""
        assert parse_vlan_range("10,10,20,20") == [10, 20]
        assert parse_vlan_range("5-10,8-12") == [5, 6, 7, 8, 9, 10, 11, 12]

    def test_sorted_output(self):
        """Результат отсортирован."""
        assert parse_vlan_range("30,10,20") == [10, 20, 30]
        assert parse_vlan_range("100,5-7,50") == [5, 6, 7, 50, 100]

    def test_invalid_string(self):
        """Невалидная строка возвращает пустой список."""
        assert parse_vlan_range("abc") == []
        assert parse_vlan_range("10-abc") == []
        assert parse_vlan_range("abc-20") == []

    def test_large_range(self):
        """Большие диапазоны работают."""
        result = parse_vlan_range("1-1000")
        assert len(result) == 1000
        assert result[0] == 1
        assert result[-1] == 1000


@pytest.mark.unit
class TestIsFullVlanRange:
    """Тесты проверки полных диапазонов."""

    @pytest.mark.parametrize("vlan_str", [
        "all", "ALL", "All",
        "1-4094", "1-4093", "1-4095",
        "none", "NONE",
        "",
    ])
    def test_full_ranges(self, vlan_str):
        """Полные диапазоны возвращают True."""
        assert is_full_vlan_range(vlan_str) is True

    @pytest.mark.parametrize("vlan_str", [
        "10,20,30",
        "1-100",
        "10",
        "1-4090",
    ])
    def test_partial_ranges(self, vlan_str):
        """Частичные диапазоны возвращают False."""
        assert is_full_vlan_range(vlan_str) is False


@pytest.mark.unit
class TestVlanSetBasic:
    """Базовые тесты VlanSet."""

    def test_from_string(self):
        """Создание из строки."""
        vs = VlanSet.from_string("10,20,30")
        assert vs.vids == {10, 20, 30}

    def test_from_string_with_range(self):
        """Создание из строки с диапазоном."""
        vs = VlanSet.from_string("10-15")
        assert vs.vids == {10, 11, 12, 13, 14, 15}

    def test_from_ids(self):
        """Создание из списка ID."""
        vs = VlanSet.from_ids([10, 20, 30])
        assert vs.vids == {10, 20, 30}

    def test_from_vlan_objects(self):
        """Создание из списка объектов с .vid."""
        class MockVlan:
            def __init__(self, vid):
                self.vid = vid

        vlans = [MockVlan(10), MockVlan(20), MockVlan(30)]
        vs = VlanSet.from_vlan_objects(vlans)
        assert vs.vids == {10, 20, 30}

    def test_from_vlan_objects_empty(self):
        """Создание из пустого списка."""
        vs = VlanSet.from_vlan_objects([])
        assert vs.vids == set()

    def test_from_vlan_objects_none(self):
        """Создание из None."""
        vs = VlanSet.from_vlan_objects(None)
        assert vs.vids == set()

    def test_sorted_list(self):
        """Получение отсортированного списка."""
        vs = VlanSet.from_ids([30, 10, 20])
        assert vs.sorted_list == [10, 20, 30]

    def test_len(self):
        """Длина набора."""
        vs = VlanSet.from_ids([10, 20, 30])
        assert len(vs) == 3

    def test_bool_true(self):
        """Bool для непустого набора."""
        vs = VlanSet.from_ids([10])
        assert bool(vs) is True

    def test_bool_false(self):
        """Bool для пустого набора."""
        vs = VlanSet.from_ids([])
        assert bool(vs) is False

    def test_repr(self):
        """String representation."""
        vs = VlanSet.from_ids([30, 10, 20])
        assert repr(vs) == "VlanSet([10, 20, 30])"


@pytest.mark.unit
class TestVlanSetComparison:
    """Тесты сравнения VlanSet."""

    def test_equal(self):
        """Равные наборы."""
        vs1 = VlanSet.from_ids([10, 20, 30])
        vs2 = VlanSet.from_ids([10, 20, 30])
        assert vs1 == vs2

    def test_equal_different_order(self):
        """Равные наборы с разным порядком."""
        vs1 = VlanSet.from_ids([30, 10, 20])
        vs2 = VlanSet.from_ids([10, 20, 30])
        assert vs1 == vs2

    def test_not_equal(self):
        """Разные наборы."""
        vs1 = VlanSet.from_ids([10, 20, 30])
        vs2 = VlanSet.from_ids([10, 20, 40])
        assert vs1 != vs2

    def test_equal_different_type(self):
        """Сравнение с другим типом."""
        vs = VlanSet.from_ids([10, 20, 30])
        assert vs != [10, 20, 30]
        assert vs != {10, 20, 30}


@pytest.mark.unit
class TestVlanSetOperations:
    """Тесты операций с VlanSet."""

    def test_added(self):
        """VLAN добавленные (есть в self, нет в other)."""
        local = VlanSet.from_ids([10, 20, 30, 40])
        remote = VlanSet.from_ids([10, 20])
        assert local.added(remote) == {30, 40}

    def test_added_empty(self):
        """Нет добавленных VLAN."""
        local = VlanSet.from_ids([10, 20])
        remote = VlanSet.from_ids([10, 20, 30])
        assert local.added(remote) == set()

    def test_removed(self):
        """VLAN удалённые (есть в other, нет в self)."""
        local = VlanSet.from_ids([10, 20])
        remote = VlanSet.from_ids([10, 20, 30, 40])
        assert local.removed(remote) == {30, 40}

    def test_removed_empty(self):
        """Нет удалённых VLAN."""
        local = VlanSet.from_ids([10, 20, 30])
        remote = VlanSet.from_ids([10, 20])
        assert local.removed(remote) == set()

    def test_intersection(self):
        """Общие VLAN."""
        vs1 = VlanSet.from_ids([10, 20, 30])
        vs2 = VlanSet.from_ids([20, 30, 40])
        assert vs1.intersection(vs2) == {20, 30}

    def test_intersection_empty(self):
        """Нет общих VLAN."""
        vs1 = VlanSet.from_ids([10, 20])
        vs2 = VlanSet.from_ids([30, 40])
        assert vs1.intersection(vs2) == set()


@pytest.mark.unit
class TestVlanSetUseCases:
    """Тесты реальных use cases."""

    def test_sync_scenario_add_vlans(self):
        """Сценарий: добавление VLAN на интерфейс."""
        # На устройстве: 10,20,30,40
        # В NetBox: 10,20
        local = VlanSet.from_string("10,20,30,40")
        remote = VlanSet.from_ids([10, 20])

        assert not local == remote
        assert local.added(remote) == {30, 40}  # Нужно добавить
        assert local.removed(remote) == set()   # Ничего удалять не надо

    def test_sync_scenario_remove_vlans(self):
        """Сценарий: удаление VLAN с интерфейса."""
        # На устройстве: 10,20
        # В NetBox: 10,20,30,40
        local = VlanSet.from_string("10,20")
        remote = VlanSet.from_ids([10, 20, 30, 40])

        assert not local == remote
        assert local.added(remote) == set()     # Ничего добавлять не надо
        assert local.removed(remote) == {30, 40}  # Нужно удалить

    def test_sync_scenario_no_changes(self):
        """Сценарий: изменений нет."""
        local = VlanSet.from_string("10,20,30")
        remote = VlanSet.from_ids([10, 20, 30])

        assert local == remote
        assert local.added(remote) == set()
        assert local.removed(remote) == set()

    def test_sync_scenario_range(self):
        """Сценарий: большой диапазон VLAN."""
        # На устройстве: 100-200
        # В NetBox: 100-150,180-200
        local = VlanSet.from_string("100-200")
        remote = VlanSet.from_ids(list(range(100, 151)) + list(range(180, 201)))

        # Нужно добавить 151-179
        assert local.added(remote) == set(range(151, 180))
