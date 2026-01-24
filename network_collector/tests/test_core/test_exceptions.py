"""
Тесты для типизированных исключений.

Проверяет:
- Создание исключений
- Сериализация to_dict()
- Форматирование для логов
- Проверка retryable
"""

import pytest

from network_collector.core.exceptions import (
    NetworkCollectorError,
    CollectorError,
    ConnectionError,
    AuthenticationError,
    CommandError,
    ParseError,
    TimeoutError,
    NetBoxError,
    NetBoxConnectionError,
    NetBoxAPIError,
    NetBoxValidationError,
    ConfigError,
    format_error_for_log,
    is_retryable,
)


class TestNetworkCollectorError:
    """Тесты базового исключения."""

    def test_basic_creation(self):
        """Тест создания с message."""
        error = NetworkCollectorError("Something went wrong")

        assert error.message == "Something went wrong"
        assert error.details == {}
        assert str(error) == "Something went wrong"

    def test_with_details(self):
        """Тест создания с details."""
        error = NetworkCollectorError("Error", details={"key": "value"})

        assert error.details == {"key": "value"}
        assert "key='value'" in str(error)

    def test_to_dict(self):
        """Тест сериализации."""
        error = NetworkCollectorError("Error", details={"foo": "bar"})
        data = error.to_dict()

        assert data["error_type"] == "NetworkCollectorError"
        assert data["message"] == "Error"
        assert data["details"]["foo"] == "bar"


class TestCollectorError:
    """Тесты ошибок сбора данных."""

    def test_with_device(self):
        """Тест с указанием устройства."""
        error = CollectorError("Failed", device="192.168.1.1")

        assert error.device == "192.168.1.1"
        assert error.details["device"] == "192.168.1.1"

    def test_without_device(self):
        """Тест без устройства."""
        error = CollectorError("Failed")

        assert error.device is None


class TestConnectionError:
    """Тесты ошибок подключения."""

    def test_with_port(self):
        """Тест с указанием порта."""
        error = ConnectionError("Refused", device="10.0.0.1", port=22)

        assert error.device == "10.0.0.1"
        assert error.details["port"] == 22

    def test_default_port(self):
        """Тест порта по умолчанию."""
        error = ConnectionError("Refused", device="10.0.0.1")

        assert error.details["port"] == 22


class TestCommandError:
    """Тесты ошибок выполнения команд."""

    def test_with_command_and_output(self):
        """Тест с командой и выводом."""
        error = CommandError(
            "Invalid input",
            device="sw1",
            command="show xyz",
            output="% Invalid input detected",
        )

        assert error.command == "show xyz"
        assert error.output == "% Invalid input detected"
        assert error.details["command"] == "show xyz"

    def test_output_truncation(self):
        """Тест обрезки длинного вывода."""
        long_output = "x" * 500
        error = CommandError("Error", output=long_output)

        # Вывод обрезается до 200 символов
        assert len(error.details["output"]) == 200


class TestParseError:
    """Тесты ошибок парсинга."""

    def test_with_all_params(self):
        """Тест со всеми параметрами."""
        error = ParseError(
            "No template",
            device="sw1",
            command="show mac",
            platform="cisco_ios",
            parser="ntc",
        )

        assert error.command == "show mac"
        assert error.platform == "cisco_ios"
        assert error.parser == "ntc"

    def test_default_parser(self):
        """Тест парсера по умолчанию."""
        error = ParseError("Error")

        assert error.parser == "ntc"
        assert error.details["parser"] == "ntc"


class TestTimeoutError:
    """Тесты ошибок таймаута."""

    def test_with_timeout(self):
        """Тест с указанием таймаута."""
        error = TimeoutError("Timeout", device="sw1", timeout_seconds=30)

        assert error.timeout_seconds == 30
        assert error.details["timeout_seconds"] == 30


class TestNetBoxError:
    """Тесты ошибок NetBox."""

    def test_with_url(self):
        """Тест с URL."""
        error = NetBoxError("API error", url="https://netbox.local")

        assert error.url == "https://netbox.local"
        assert error.details["url"] == "https://netbox.local"


class TestNetBoxAPIError:
    """Тесты ошибок NetBox API."""

    def test_with_status_code(self):
        """Тест с HTTP кодом."""
        error = NetBoxAPIError(
            "Not found",
            url="https://netbox.local",
            status_code=404,
            endpoint="/api/dcim/devices/",
        )

        assert error.status_code == 404
        assert error.endpoint == "/api/dcim/devices/"
        assert error.details["status_code"] == 404


class TestNetBoxValidationError:
    """Тесты ошибок валидации NetBox."""

    def test_with_field_and_value(self):
        """Тест с полем и значением."""
        error = NetBoxValidationError(
            "Invalid format",
            field="address",
            value="not-an-ip",
        )

        assert error.field == "address"
        assert error.value == "not-an-ip"
        assert error.details["field"] == "address"

    def test_value_truncation(self):
        """Тест обрезки длинного значения."""
        long_value = "x" * 200
        error = NetBoxValidationError("Error", value=long_value)

        assert len(error.details["value"]) == 100


class TestConfigError:
    """Тесты ошибок конфигурации."""

    def test_with_file_and_key(self):
        """Тест с файлом и ключом."""
        error = ConfigError(
            "Missing field",
            config_file="config.yaml",
            key="netbox.url",
        )

        assert error.config_file == "config.yaml"
        assert error.key == "netbox.url"


class TestFormatErrorForLog:
    """Тесты форматирования для логов."""

    def test_network_collector_error(self):
        """Тест форматирования наших ошибок."""
        error = ConnectionError("Refused", device="sw1", port=22)
        result = format_error_for_log(error)

        assert "Refused" in result
        assert "sw1" in result

    def test_standard_exception(self):
        """Тест форматирования стандартных исключений."""
        error = ValueError("bad value")
        result = format_error_for_log(error)

        assert "ValueError" in result
        assert "bad value" in result


class TestIsRetryable:
    """Тесты проверки retryable."""

    def test_connection_error_is_retryable(self):
        """ConnectionError можно retry."""
        error = ConnectionError("Refused", device="sw1")
        assert is_retryable(error) is True

    def test_timeout_error_is_retryable(self):
        """TimeoutError можно retry."""
        error = TimeoutError("Timeout", device="sw1")
        assert is_retryable(error) is True

    def test_netbox_connection_error_is_retryable(self):
        """NetBoxConnectionError можно retry."""
        error = NetBoxConnectionError("Connection refused")
        assert is_retryable(error) is True

    def test_parse_error_not_retryable(self):
        """ParseError нельзя retry."""
        error = ParseError("No template")
        assert is_retryable(error) is False

    def test_auth_error_not_retryable(self):
        """AuthenticationError нельзя retry."""
        error = AuthenticationError("Wrong password")
        assert is_retryable(error) is False

    def test_validation_error_not_retryable(self):
        """NetBoxValidationError нельзя retry."""
        error = NetBoxValidationError("Invalid data")
        assert is_retryable(error) is False


class TestInheritance:
    """Тесты иерархии наследования."""

    def test_collector_errors_inherit(self):
        """Все Collector ошибки наследуют CollectorError."""
        errors = [
            ConnectionError("test"),
            AuthenticationError("test"),
            CommandError("test"),
            ParseError("test"),
            TimeoutError("test"),
        ]

        for error in errors:
            assert isinstance(error, CollectorError)
            assert isinstance(error, NetworkCollectorError)

    def test_netbox_errors_inherit(self):
        """Все NetBox ошибки наследуют NetBoxError."""
        errors = [
            NetBoxConnectionError("test"),
            NetBoxAPIError("test"),
            NetBoxValidationError("test"),
        ]

        for error in errors:
            assert isinstance(error, NetBoxError)
            assert isinstance(error, NetworkCollectorError)

    def test_config_error_inherits(self):
        """ConfigError наследует NetworkCollectorError."""
        error = ConfigError("test")

        assert isinstance(error, NetworkCollectorError)
