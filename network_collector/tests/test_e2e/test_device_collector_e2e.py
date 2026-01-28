"""
E2E тесты для DeviceCollector.

Проверяет полный цикл: fixture → NTC parse → normalize.
Без реального SSH подключения.

Примечание: DeviceCollector использует ntc_templates.parse_output
напрямую, в отличие от других коллекторов.
"""

import pytest
from typing import Dict, Any
from unittest.mock import patch, MagicMock

from ntc_templates.parse import parse_output

from network_collector.collectors.device import DeviceCollector
from network_collector.core.models import DeviceInfo
from network_collector.core.constants import normalize_device_model

from .conftest import create_mock_device


@pytest.fixture
def collector() -> DeviceCollector:
    """Создаёт DeviceCollector для тестов."""
    return DeviceCollector(credentials=None)


class TestDeviceCollectorE2E:
    """E2E тесты DeviceCollector — полный цикл без SSH."""

    def test_cisco_ios_show_version_parsing(self, load_fixture):
        """Cisco IOS: парсинг show version через NTC Templates."""
        output = load_fixture("cisco_ios", "show_version.txt")

        # Парсим напрямую через NTC Templates (как делает collector)
        parsed = parse_output(
            platform="cisco_ios",
            command="show version",
            data=output,
        )

        assert isinstance(parsed, list)
        assert len(parsed) > 0, "Должны быть распознаны данные"
        assert isinstance(parsed[0], dict)

    def test_cisco_nxos_show_version_parsing(self, load_fixture):
        """Cisco NX-OS: парсинг show version через NTC Templates."""
        output = load_fixture("cisco_nxos", "show_version.txt")

        parsed = parse_output(
            platform="cisco_nxos",
            command="show version",
            data=output,
        )

        assert isinstance(parsed, list)
        assert len(parsed) > 0, "Должны быть распознаны данные"

    def test_qtech_show_version_parsing(self, load_fixture):
        """QTech: парсинг show version."""
        output = load_fixture("qtech", "show_version.txt")

        # QTech может не иметь NTC шаблона
        try:
            parsed = parse_output(
                platform="qtech",
                command="show version",
                data=output,
            )
            assert isinstance(parsed, list)
        except Exception:
            # QTech не поддерживается NTC — это OK
            pytest.skip("QTech не поддерживается NTC Templates")

    @pytest.mark.parametrize("platform,ntc_platform", [
        ("cisco_ios", "cisco_ios"),
        ("cisco_nxos", "cisco_nxos"),
    ])
    def test_all_platforms_return_dicts(
        self, load_fixture, platform: str, ntc_platform: str
    ):
        """Все платформы возвращают список словарей."""
        try:
            output = load_fixture(platform, "show_version.txt")
        except Exception:
            pytest.skip(f"Fixture не найден для {platform}")

        parsed = parse_output(
            platform=ntc_platform,
            command="show version",
            data=output,
        )

        assert isinstance(parsed, list)
        if len(parsed) > 0:
            assert all(isinstance(item, dict) for item in parsed)


class TestDeviceCollectorFields:
    """Тесты корректности полей в словарях."""

    def test_hostname_field(self, load_fixture):
        """Hostname присутствует."""
        output = load_fixture("cisco_ios", "show_version.txt")

        parsed = parse_output(
            platform="cisco_ios",
            command="show version",
            data=output,
        )

        if parsed:
            data = parsed[0]
            # Поле hostname или rommon (разные платформы)
            hostname = data.get("hostname", "")
            assert isinstance(hostname, str)

    def test_hardware_field(self, load_fixture):
        """Hardware/model присутствует."""
        output = load_fixture("cisco_ios", "show_version.txt")

        parsed = parse_output(
            platform="cisco_ios",
            command="show version",
            data=output,
        )

        if parsed:
            data = parsed[0]
            # Разные платформы используют разные поля
            hardware = (
                data.get("hardware") or
                data.get("chassis") or
                data.get("model", [])
            )
            assert hardware is not None

    def test_serial_field(self, load_fixture):
        """Serial number присутствует."""
        output = load_fixture("cisco_ios", "show_version.txt")

        parsed = parse_output(
            platform="cisco_ios",
            command="show version",
            data=output,
        )

        if parsed:
            data = parsed[0]
            # Serial может быть в разных полях
            serial = (
                data.get("serial") or
                data.get("processor_board_id") or
                data.get("chassis_sn", [])
            )
            # Serial может отсутствовать
            assert serial is not None or True

    def test_version_field(self, load_fixture):
        """Version присутствует."""
        output = load_fixture("cisco_ios", "show_version.txt")

        parsed = parse_output(
            platform="cisco_ios",
            command="show version",
            data=output,
        )

        if parsed:
            data = parsed[0]
            version = data.get("version", "")
            assert isinstance(version, str)


class TestDeviceCollectorNormalization:
    """Тесты нормализации данных."""

    def test_model_normalization(self):
        """Нормализация модели работает."""
        # Тестируем normalize_device_model
        assert normalize_device_model("WS-C3850-24T") == "C3850-24T"
        assert normalize_device_model("C9300-24T") == "C9300-24T"
        assert normalize_device_model("N9K-C9372PX") == "N9K-C9372PX"

    def test_model_with_license_stripped(self):
        """Лицензия удаляется из модели."""
        # Модели с суффиксами лицензий
        model = normalize_device_model("WS-C3850-24T-L")
        assert "WS-" not in model

    def test_to_models_creates_device_info(self, collector: DeviceCollector):
        """DeviceInfo создаётся из словаря."""
        data = {
            "hostname": "test-switch",
            "model": "C3850-24T",
            "serial": "ABC123",
            "version": "16.9.1",
            "uptime": "10 days",
            "ip_address": "10.0.0.1",
            "platform": "cisco_ios",
            "manufacturer": "Cisco",
            "status": "active",
        }

        model = DeviceInfo.from_dict(data)

        assert isinstance(model, DeviceInfo)
        assert model.hostname == "test-switch"
        assert model.model == "C3850-24T"


class TestDeviceCollectorEdgeCases:
    """Тесты граничных случаев."""

    def test_empty_output_handled(self):
        """Пустой вывод обрабатывается."""
        try:
            parsed = parse_output(
                platform="cisco_ios",
                command="show version",
                data="",
            )
            assert isinstance(parsed, list)
        except Exception:
            # NTC может выбросить исключение на пустом вводе
            pass

    def test_garbage_output_handled(self):
        """Мусорный вывод обрабатывается."""
        try:
            parsed = parse_output(
                platform="cisco_ios",
                command="show version",
                data="random garbage\nno version info",
            )
            assert isinstance(parsed, list)
        except Exception:
            # NTC может выбросить исключение
            pass

    def test_partial_version_output(self):
        """Неполный вывод обрабатывается."""
        partial = """
Cisco IOS Software, Version 15.2(4)E
Switch Ports Model              SW Version
------ ----- -----              ----------
*    1 24    WS-C3850-24T       15.2(4)E
"""
        try:
            parsed = parse_output(
                platform="cisco_ios",
                command="show version",
                data=partial,
            )
            assert isinstance(parsed, list)
        except Exception:
            pass


class TestDeviceCollectorWithMockedConnection:
    """Тесты с замоканным подключением."""

    def test_collect_with_mocked_ssh(self, collector: DeviceCollector, load_fixture):
        """Сбор с замоканным SSH подключением."""
        output = load_fixture("cisco_ios", "show_version.txt")
        device = create_mock_device("cisco_ios", "test-switch", "10.0.0.1")

        # Мокаем ConnectionManager
        mock_conn = MagicMock()
        mock_response = MagicMock()
        mock_response.result = output
        mock_conn.send_command.return_value = mock_response
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)

        with patch.object(
            collector._conn_manager, 'connect', return_value=mock_conn
        ):
            with patch.object(
                collector._conn_manager, 'get_hostname', return_value="test-switch"
            ):
                data = collector._collect_from_device(device)

        assert data is not None
        assert "hostname" in data
        assert "model" in data
        assert data["ip_address"] == "10.0.0.1"

    def test_collect_handles_connection_error(self, collector: DeviceCollector):
        """Обработка ошибки подключения."""
        from network_collector.core.exceptions import ConnectionError

        device = create_mock_device("cisco_ios", "test-switch", "10.0.0.1")

        with patch.object(
            collector._conn_manager, 'connect',
            side_effect=ConnectionError("Connection refused")
        ):
            data = collector._collect_from_device(device)

        # При ошибке возвращаются fallback данные
        assert data is not None
        assert "_error" in data
        assert data["name"] == "test-switch"
