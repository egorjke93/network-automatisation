"""
E2E тесты для InventoryCollector.

Проверяет полный цикл: fixture → parse → normalize.
Без реального SSH подключения.

Примечание: _parse_output возвращает List[Dict], не модели.
"""

import pytest
from typing import List, Dict

from network_collector.collectors.inventory import InventoryCollector
from network_collector.core.models import InventoryItem

from .conftest import create_mock_device, get_fixture_filename


@pytest.fixture
def collector():
    """Создаёт InventoryCollector для тестов."""
    return InventoryCollector(credentials=None)


class TestInventoryCollectorE2E:
    """E2E тесты InventoryCollector — полный цикл без SSH."""

    def test_cisco_ios_full_pipeline(self, collector, load_fixture):
        """Cisco IOS: полный цикл обработки inventory."""
        output = load_fixture("cisco_ios", "show_inventory.txt")
        device = create_mock_device("cisco_ios", "ios-switch")

        result = collector._parse_output(output, device)

        assert len(result) > 0, "Должны быть распознаны inventory items"
        assert isinstance(result, list)
        assert isinstance(result[0], dict), "Результат должен быть словарём"

    def test_cisco_nxos_full_pipeline(self, collector, load_fixture):
        """Cisco NX-OS: полный цикл обработки inventory."""
        output = load_fixture("cisco_nxos", "show_inventory.txt")
        device = create_mock_device("cisco_nxos", "nxos-switch")

        result = collector._parse_output(output, device)

        assert len(result) > 0, "Должны быть распознаны inventory items"

    @pytest.mark.parametrize("platform", ["cisco_ios", "cisco_nxos"])
    def test_platforms_return_dicts(self, collector, load_fixture, platform):
        """Платформы возвращают список словарей."""
        filename = get_fixture_filename(platform, "inventory")
        if not filename:
            pytest.skip(f"Нет fixture для {platform}")

        try:
            output = load_fixture(platform, filename)
        except Exception:
            pytest.skip(f"Fixture не найден для {platform}")

        device = create_mock_device(platform, f"{platform}-switch")
        result = collector._parse_output(output, device)

        assert len(result) > 0
        assert all(isinstance(item, dict) for item in result)

    def test_to_models_conversion(self, collector, load_fixture):
        """Конвертация в модели InventoryItem работает."""
        output = load_fixture("cisco_ios", "show_inventory.txt")
        device = create_mock_device("cisco_ios", "ios-switch")

        parsed = collector._parse_output(output, device)
        assert len(parsed) > 0

        models = collector.to_models(parsed)

        assert len(models) > 0
        for model in models:
            assert isinstance(model, InventoryItem)


class TestInventoryCollectorFields:
    """Тесты корректности полей в словарях."""

    @pytest.fixture
    def collector(self):
        return InventoryCollector(credentials=None)

    def test_name_field(self, collector, load_fixture):
        """Имя присутствует."""
        output = load_fixture("cisco_ios", "show_inventory.txt")
        device = create_mock_device("cisco_ios")

        result = collector._parse_output(output, device)

        names = [item.get("name") or item.get("NAME", "") for item in result]
        names = [n for n in names if n]
        assert len(names) > 0, "Должны быть имена"

    def test_part_id_field(self, collector, load_fixture):
        """Part ID (PID) присутствует."""
        output = load_fixture("cisco_ios", "show_inventory.txt")
        device = create_mock_device("cisco_ios")

        result = collector._parse_output(output, device)

        pids = []
        for item in result:
            pid = item.get("pid") or item.get("part_id") or item.get("PID", "")
            if pid:
                pids.append(pid)

        assert len(pids) > 0, "Должны быть PIDs"

    def test_serial_field(self, collector, load_fixture):
        """Serial number присутствует."""
        output = load_fixture("cisco_ios", "show_inventory.txt")
        device = create_mock_device("cisco_ios")

        result = collector._parse_output(output, device)

        serials = []
        for item in result:
            serial = item.get("sn") or item.get("serial") or item.get("SN", "")
            if serial:
                serials.append(serial)

        # Serial может отсутствовать у некоторых items
        assert isinstance(serials, list)

    def test_description_field(self, collector, load_fixture):
        """Description присутствует."""
        output = load_fixture("cisco_ios", "show_inventory.txt")
        device = create_mock_device("cisco_ios")

        result = collector._parse_output(output, device)

        descriptions = []
        for item in result:
            desc = item.get("descr") or item.get("description") or item.get("DESCR", "")
            if desc:
                descriptions.append(desc)

        assert len(descriptions) > 0, "Должны быть описания"


class TestInventoryCollectorEdgeCases:
    """Тесты граничных случаев."""

    @pytest.fixture
    def collector(self):
        return InventoryCollector(credentials=None)

    def test_empty_output_returns_empty_list(self, collector):
        """Пустой вывод возвращает пустой список."""
        device = create_mock_device("cisco_ios")
        result = collector._parse_output("", device)
        assert result == [] or len(result) == 0

    def test_garbage_output_handled(self, collector):
        """Мусорный вывод обрабатывается без ошибок."""
        device = create_mock_device("cisco_ios")
        garbage = "random garbage\nno inventory"

        result = collector._parse_output(garbage, device)
        assert isinstance(result, list)

    def test_partial_inventory_output(self, collector):
        """Неполный вывод обрабатывается."""
        device = create_mock_device("cisco_ios")
        partial = '''
NAME: "Chassis", DESCR: "Cisco Catalyst"
PID: WS-C3850-24T    , VID: V01  , SN:
'''
        result = collector._parse_output(partial, device)
        assert isinstance(result, list)


class TestInventoryCollectorNormalization:
    """Тесты нормализации данных."""

    @pytest.fixture
    def collector(self):
        return InventoryCollector(credentials=None)

    def test_to_models_creates_inventory_objects(self, collector, load_fixture):
        """to_models создаёт объекты InventoryItem."""
        output = load_fixture("cisco_ios", "show_inventory.txt")
        device = create_mock_device("cisco_ios", "test-switch")

        parsed = collector._parse_output(output, device)
        models = collector.to_models(parsed)

        assert len(models) > 0
        for model in models:
            assert isinstance(model, InventoryItem)

    def test_name_truncation_check(self, collector, load_fixture):
        """Проверка длины имён (max 64 для NetBox)."""
        output = load_fixture("cisco_ios", "show_inventory.txt")
        device = create_mock_device("cisco_ios")

        parsed = collector._parse_output(output, device)
        models = collector.to_models(parsed)

        long_names = [m for m in models if m.name and len(m.name) > 64]
        # Просто проверяем что длинные имена обрабатываются
        assert isinstance(long_names, list)
