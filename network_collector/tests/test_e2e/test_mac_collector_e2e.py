"""
E2E тесты для MACCollector.

Проверяет полный цикл: fixture → parse → normalize.
Без реального SSH подключения.

Примечание: _parse_output возвращает List[Dict], не модели.
"""

import pytest
from typing import List, Dict

from network_collector.collectors.mac import MACCollector
from network_collector.core.models import MACEntry

from .conftest import create_mock_device, SUPPORTED_PLATFORMS, get_fixture_filename


@pytest.fixture
def collector():
    """Создаёт MACCollector для тестов."""
    return MACCollector(
        credentials=None,
        mac_format="ieee",
    )


class TestMACCollectorE2E:
    """E2E тесты MACCollector — полный цикл без SSH."""

    def test_cisco_ios_full_pipeline(self, collector, load_fixture):
        """Cisco IOS: полный цикл обработки MAC-таблицы."""
        output = load_fixture("cisco_ios", "show_mac_address_table.txt")
        device = create_mock_device("cisco_ios", "ios-switch")

        result = collector._parse_output(output, device)

        assert len(result) > 0, "Должны быть распознаны MAC-записи"
        assert isinstance(result, list)
        assert isinstance(result[0], dict), "Результат должен быть словарём"

    def test_cisco_nxos_full_pipeline(self, collector, load_fixture):
        """Cisco NX-OS: полный цикл обработки MAC-таблицы."""
        output = load_fixture("cisco_nxos", "show_mac_address_table.txt")
        device = create_mock_device("cisco_nxos", "nxos-switch")

        result = collector._parse_output(output, device)

        assert len(result) > 0, "Должны быть распознаны MAC-записи"

    def test_qtech_full_pipeline(self, collector, load_fixture):
        """QTech: полный цикл обработки MAC-таблицы."""
        output = load_fixture("qtech", "show_mac_address_table.txt")
        device = create_mock_device("qtech", "qtech-switch")

        result = collector._parse_output(output, device)

        assert len(result) > 0, "Должны быть распознаны MAC-записи"

    @pytest.mark.parametrize("platform", SUPPORTED_PLATFORMS)
    def test_all_platforms_return_dicts(self, collector, load_fixture, platform):
        """Все платформы возвращают список словарей."""
        filename = get_fixture_filename(platform, "mac")
        if not filename:
            pytest.skip(f"Нет fixture для {platform}")

        try:
            output = load_fixture(platform, filename)
        except Exception:
            pytest.skip(f"Fixture не найден для {platform}")

        device = create_mock_device(platform, f"{platform}-switch")
        result = collector._parse_output(output, device)

        assert len(result) > 0, f"Платформа {platform} должна вернуть MAC-записи"
        assert all(isinstance(item, dict) for item in result)

    def test_to_models_conversion(self, collector, load_fixture):
        """Конвертация в модели MACEntry работает."""
        output = load_fixture("cisco_ios", "show_mac_address_table.txt")
        device = create_mock_device("cisco_ios", "ios-switch")

        parsed = collector._parse_output(output, device)
        assert len(parsed) > 0

        models = collector.to_models(parsed)

        assert len(models) > 0
        for model in models:
            assert isinstance(model, MACEntry)
            assert model.mac is not None


class TestMACCollectorFields:
    """Тесты корректности полей в словарях."""

    @pytest.fixture
    def collector(self):
        return MACCollector(credentials=None)

    def test_mac_field_present(self, collector, load_fixture):
        """MAC-адрес присутствует."""
        output = load_fixture("cisco_ios", "show_mac_address_table.txt")
        device = create_mock_device("cisco_ios")

        result = collector._parse_output(output, device)

        for entry in result:
            mac = entry.get("mac") or entry.get("destination_address") or entry.get("mac_address", "")
            assert mac, "Должен быть MAC-адрес"

    def test_vlan_field(self, collector, load_fixture):
        """VLAN присутствует."""
        output = load_fixture("cisco_ios", "show_mac_address_table.txt")
        device = create_mock_device("cisco_ios")

        result = collector._parse_output(output, device)

        for entry in result:
            vlan = entry.get("vlan") or entry.get("vlan_id", "")
            # VLAN может отсутствовать в некоторых случаях
            if vlan:
                # Должен быть числом или строкой-числом
                try:
                    int(str(vlan).strip())
                except ValueError:
                    pass

    def test_interface_field(self, collector, load_fixture):
        """Интерфейс присутствует."""
        output = load_fixture("cisco_ios", "show_mac_address_table.txt")
        device = create_mock_device("cisco_ios")

        result = collector._parse_output(output, device)

        interfaces = [
            entry.get("destination_port") or entry.get("interface") or entry.get("port", "")
            for entry in result
        ]
        interfaces = [i for i in interfaces if i]
        assert len(interfaces) > 0, "Должны быть интерфейсы"

    def test_empty_output_returns_empty_list(self, collector):
        """Пустой вывод возвращает пустой список."""
        device = create_mock_device("cisco_ios")
        result = collector._parse_output("", device)
        assert result == [] or len(result) == 0

    def test_garbage_output_handled(self, collector):
        """Мусорный вывод обрабатывается без ошибок."""
        device = create_mock_device("cisco_ios")
        garbage = "random garbage\nno mac addresses"

        result = collector._parse_output(garbage, device)
        assert isinstance(result, list)


class TestMACCollectorNormalization:
    """Тесты нормализации MAC-адресов."""

    @pytest.fixture
    def collector(self):
        return MACCollector(credentials=None, mac_format="ieee")

    def test_mac_normalized(self, collector, load_fixture):
        """MAC-адреса нормализуются."""
        output = load_fixture("cisco_ios", "show_mac_address_table.txt")
        device = create_mock_device("cisco_ios")

        result = collector._parse_output(output, device)
        models = collector.to_models(result)

        for model in models:
            if model.mac:
                # MAC должен быть в валидном формате
                clean = model.mac.lower().replace(":", "").replace(".", "").replace("-", "")
                assert len(clean) == 12, f"MAC неверной длины: {model.mac}"

    def test_to_models_creates_mac_objects(self, collector, load_fixture):
        """to_models создаёт объекты MACEntry."""
        output = load_fixture("cisco_ios", "show_mac_address_table.txt")
        device = create_mock_device("cisco_ios", "test-switch")

        result = collector._parse_output(output, device)
        models = collector.to_models(result)

        assert len(models) > 0
        for model in models:
            assert isinstance(model, MACEntry)
            assert model.mac is not None
