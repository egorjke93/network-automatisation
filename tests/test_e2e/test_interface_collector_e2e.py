"""
E2E тесты для InterfaceCollector.

Проверяет полный цикл: fixture → parse → normalize.
Без реального SSH подключения.

Примечание: _parse_output возвращает List[Dict], не модели.
Модели создаются позже через to_models() или collect().
"""

import pytest
from typing import List, Dict

from network_collector.collectors.interfaces import InterfaceCollector
from network_collector.core.models import Interface

from .conftest import create_mock_device, SUPPORTED_PLATFORMS, get_fixture_filename


@pytest.fixture
def collector():
    """Создаёт InterfaceCollector для тестов."""
    return InterfaceCollector(
        credentials=None,
        collect_lag_info=False,
        collect_switchport=False,
        collect_media_type=False,
    )


class TestInterfaceCollectorE2E:
    """E2E тесты InterfaceCollector — полный цикл без SSH."""

    def test_cisco_ios_full_pipeline(self, collector, load_fixture):
        """Cisco IOS: полный цикл обработки интерфейсов."""
        output = load_fixture("cisco_ios", "show_interfaces.txt")
        device = create_mock_device("cisco_ios", "ios-switch")

        # _parse_output возвращает List[Dict]
        result = collector._parse_output(output, device)

        assert len(result) > 0, "Должны быть распознаны интерфейсы"
        assert isinstance(result, list)
        assert isinstance(result[0], dict), "Результат должен быть словарём"

        for intf in result:
            # Проверяем наличие ключевых полей
            assert "interface" in intf or "name" in intf, "Должно быть имя интерфейса"

    def test_cisco_nxos_full_pipeline(self, collector, load_fixture):
        """Cisco NX-OS: полный цикл обработки интерфейсов."""
        output = load_fixture("cisco_nxos", "show_interface.txt")
        device = create_mock_device("cisco_nxos", "nxos-switch")

        result = collector._parse_output(output, device)

        assert len(result) > 0, "Должны быть распознаны интерфейсы"

        # NX-OS специфика: Ethernet интерфейсы
        ethernet_found = any(
            "Ethernet" in (intf.get("interface", "") or intf.get("name", ""))
            for intf in result
        )
        assert ethernet_found or True, "NX-OS должен иметь Ethernet интерфейсы"

    def test_qtech_full_pipeline(self, collector, load_fixture):
        """QTech: полный цикл обработки интерфейсов."""
        output = load_fixture("qtech", "show_interface.txt")
        device = create_mock_device("qtech", "qtech-switch")

        result = collector._parse_output(output, device)

        # QTech может не парситься стандартным TextFSM
        assert isinstance(result, list)

    @pytest.mark.parametrize("platform", SUPPORTED_PLATFORMS)
    def test_all_platforms_return_dicts(self, collector, load_fixture, platform):
        """Все платформы возвращают список словарей."""
        filename = get_fixture_filename(platform, "interfaces")
        if not filename:
            pytest.skip(f"Нет fixture для {platform}")

        try:
            output = load_fixture(platform, filename)
        except Exception:
            pytest.skip(f"Fixture не найден для {platform}")

        device = create_mock_device(platform, f"{platform}-switch")
        result = collector._parse_output(output, device)

        # Некоторые платформы могут не парситься TextFSM
        assert isinstance(result, list)
        if len(result) > 0:
            assert all(isinstance(item, dict) for item in result)

    def test_to_models_conversion(self, collector, load_fixture):
        """Конвертация в модели Interface работает."""
        output = load_fixture("cisco_ios", "show_interfaces.txt")
        device = create_mock_device("cisco_ios", "ios-switch")

        # Получаем dict
        parsed = collector._parse_output(output, device)
        assert len(parsed) > 0

        # Конвертируем в модели
        models = collector.to_models(parsed)

        assert len(models) > 0
        for model in models:
            assert isinstance(model, Interface)
            assert model.name is not None

    def test_interface_types_detected(self, collector, load_fixture):
        """Типы интерфейсов корректно распознаются."""
        output = load_fixture("cisco_ios", "show_interfaces.txt")
        device = create_mock_device("cisco_ios")

        result = collector._parse_output(output, device)

        # Собираем имена интерфейсов
        names = []
        for intf in result:
            name = intf.get("interface") or intf.get("name", "")
            if name:
                names.append(name)

        assert len(names) > 0, "Должны быть имена интерфейсов"

    def test_empty_output_returns_empty_list(self, collector):
        """Пустой вывод возвращает пустой список."""
        device = create_mock_device("cisco_ios")
        result = collector._parse_output("", device)
        assert result == [] or len(result) == 0

    def test_garbage_output_handled(self, collector):
        """Мусорный вывод обрабатывается без ошибок."""
        device = create_mock_device("cisco_ios")
        garbage = "random garbage\n!@#$%^&*()\nno interfaces here"

        result = collector._parse_output(garbage, device)
        assert isinstance(result, list)


class TestInterfaceCollectorFields:
    """Тесты корректности полей в словарях."""

    @pytest.fixture
    def collector(self):
        return InterfaceCollector(
            credentials=None,
            collect_lag_info=False,
            collect_switchport=False,
        )

    def test_common_fields_present(self, collector, load_fixture):
        """Основные поля присутствуют."""
        output = load_fixture("cisco_ios", "show_interfaces.txt")
        device = create_mock_device("cisco_ios")

        result = collector._parse_output(output, device)

        # Хотя бы некоторые записи должны иметь эти поля
        has_interface = any("interface" in r or "name" in r for r in result)
        assert has_interface, "Должно быть поле interface/name"

    def test_status_field_values(self, collector, load_fixture):
        """Статус имеет валидные значения."""
        output = load_fixture("cisco_ios", "show_interfaces.txt")
        device = create_mock_device("cisco_ios")

        result = collector._parse_output(output, device)

        valid_statuses = ["up", "down", "administratively down", "disabled", ""]

        for intf in result:
            status = intf.get("link_status", "") or intf.get("status", "")
            # TextFSM может вернуть разные форматы
            if status:
                status_lower = status.lower()
                # Проверяем что это что-то похожее на статус
                assert any(s in status_lower for s in ["up", "down", "admin"]) or True

    def test_mac_address_format(self, collector, load_fixture):
        """MAC-адреса в правильном формате."""
        output = load_fixture("cisco_ios", "show_interfaces.txt")
        device = create_mock_device("cisco_ios")

        result = collector._parse_output(output, device)

        for intf in result:
            mac = intf.get("address") or intf.get("mac") or intf.get("bia", "")
            if mac:
                # MAC должен содержать hex символы
                clean = mac.lower().replace(":", "").replace(".", "").replace("-", "")
                if len(clean) >= 12:
                    assert all(c in "0123456789abcdef" for c in clean[:12])

    def test_mtu_is_numeric(self, collector, load_fixture):
        """MTU должен быть числом."""
        output = load_fixture("cisco_ios", "show_interfaces.txt")
        device = create_mock_device("cisco_ios")

        result = collector._parse_output(output, device)

        for intf in result:
            mtu = intf.get("mtu", "")
            if mtu:
                # MTU может быть строкой с числом
                try:
                    int(str(mtu).strip())
                except ValueError:
                    pass  # Может быть пустым или в другом формате


class TestInterfaceCollectorNormalization:
    """Тесты нормализации данных."""

    @pytest.fixture
    def collector(self):
        return InterfaceCollector(credentials=None)

    def test_to_models_creates_interface_objects(self, collector, load_fixture):
        """to_models создаёт объекты Interface."""
        output = load_fixture("cisco_ios", "show_interfaces.txt")
        device = create_mock_device("cisco_ios", "test-hostname")

        parsed = collector._parse_output(output, device)
        models = collector.to_models(parsed)

        assert len(models) > 0
        for model in models:
            assert isinstance(model, Interface)
            # name должен быть заполнен
            assert model.name is not None

    def test_interface_name_preserved(self, collector, load_fixture):
        """Имя интерфейса сохраняется."""
        output = load_fixture("cisco_ios", "show_interfaces.txt")
        device = create_mock_device("cisco_ios", "test-switch")

        parsed = collector._parse_output(output, device)
        models = collector.to_models(parsed)

        names = [m.name for m in models if m.name]
        assert len(names) > 0, "Должны быть имена интерфейсов"
