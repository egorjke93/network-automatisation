"""
Типизированные исключения для Network Collector.

Иерархия:
    NetworkCollectorError (базовый)
    ├── CollectorError (сбор данных)
    │   ├── ConnectionError (SSH подключение)
    │   ├── AuthenticationError (авторизация)
    │   ├── CommandError (выполнение команды)
    │   ├── ParseError (парсинг вывода)
    │   └── TimeoutError (таймаут)
    ├── NetBoxError (NetBox API)
    │   ├── NetBoxConnectionError (подключение к API)
    │   ├── NetBoxAPIError (ошибка API)
    │   └── NetBoxValidationError (валидация данных)
    └── ConfigError (конфигурация)

Пример использования:
    from network_collector.core.exceptions import ConnectionError, ParseError

    try:
        data = collector.collect(devices)
    except ConnectionError as e:
        logger.error(f"SSH ошибка: {e.device} - {e.message}")
    except ParseError as e:
        logger.error(f"Парсинг: {e.command} - {e.message}")
"""

from typing import Optional, Any


class NetworkCollectorError(Exception):
    """
    Базовое исключение для всех ошибок Network Collector.

    Attributes:
        message: Описание ошибки
        details: Дополнительные детали (dict)
    """

    def __init__(self, message: str, details: Optional[dict] = None):
        self.message = message
        self.details = details or {}
        super().__init__(message)

    def __str__(self) -> str:
        if self.details:
            details_str = ", ".join(f"{k}={v!r}" for k, v in self.details.items())
            return f"{self.message} ({details_str})"
        return self.message

    def to_dict(self) -> dict:
        """Сериализация для логов/отчётов."""
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "details": self.details,
        }


# === Collector Errors ===

class CollectorError(NetworkCollectorError):
    """
    Ошибка при сборе данных с устройства.

    Attributes:
        device: IP или hostname устройства
        message: Описание ошибки
    """

    def __init__(
        self,
        message: str,
        device: Optional[str] = None,
        details: Optional[dict] = None,
    ):
        self.device = device
        details = details or {}
        if device:
            details["device"] = device
        super().__init__(message, details)


class ConnectionError(CollectorError):
    """
    Ошибка SSH подключения.

    Пример:
        raise ConnectionError("Connection refused", device="192.168.1.1", port=22)
    """

    def __init__(
        self,
        message: str,
        device: Optional[str] = None,
        port: int = 22,
        details: Optional[dict] = None,
    ):
        details = details or {}
        details["port"] = port
        super().__init__(message, device, details)


class AuthenticationError(CollectorError):
    """
    Ошибка аутентификации (неверный логин/пароль).

    Пример:
        raise AuthenticationError("Invalid credentials", device="192.168.1.1")
    """
    pass


class CommandError(CollectorError):
    """
    Ошибка выполнения команды на устройстве.

    Attributes:
        command: Команда которая вызвала ошибку
        output: Вывод устройства (если есть)

    Пример:
        raise CommandError("Invalid input", device="sw1", command="show xyz")
    """

    def __init__(
        self,
        message: str,
        device: Optional[str] = None,
        command: Optional[str] = None,
        output: Optional[str] = None,
        details: Optional[dict] = None,
    ):
        self.command = command
        self.output = output
        details = details or {}
        if command:
            details["command"] = command
        if output:
            details["output"] = output[:200]  # Ограничиваем размер
        super().__init__(message, device, details)


class ParseError(CollectorError):
    """
    Ошибка парсинга вывода команды.

    Attributes:
        command: Команда чей вывод не распарсился
        platform: Платформа устройства
        parser: Тип парсера (ntc/regex)

    Пример:
        raise ParseError("No template found", command="show mac", platform="cisco_ios")
    """

    def __init__(
        self,
        message: str,
        device: Optional[str] = None,
        command: Optional[str] = None,
        platform: Optional[str] = None,
        parser: str = "ntc",
        details: Optional[dict] = None,
    ):
        self.command = command
        self.platform = platform
        self.parser = parser
        details = details or {}
        if command:
            details["command"] = command
        if platform:
            details["platform"] = platform
        details["parser"] = parser
        super().__init__(message, device, details)


class TimeoutError(CollectorError):
    """
    Таймаут при подключении или выполнении команды.

    Attributes:
        timeout_seconds: Значение таймаута

    Пример:
        raise TimeoutError("Connection timeout", device="192.168.1.1", timeout_seconds=30)
    """

    def __init__(
        self,
        message: str,
        device: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        details: Optional[dict] = None,
    ):
        self.timeout_seconds = timeout_seconds
        details = details or {}
        if timeout_seconds:
            details["timeout_seconds"] = timeout_seconds
        super().__init__(message, device, details)


# === NetBox Errors ===

class NetBoxError(NetworkCollectorError):
    """
    Базовая ошибка NetBox API.

    Attributes:
        url: URL NetBox
    """

    def __init__(
        self,
        message: str,
        url: Optional[str] = None,
        details: Optional[dict] = None,
    ):
        self.url = url
        details = details or {}
        if url:
            details["url"] = url
        super().__init__(message, details)


class NetBoxConnectionError(NetBoxError):
    """
    Ошибка подключения к NetBox API.

    Пример:
        raise NetBoxConnectionError("Connection refused", url="https://netbox.local")
    """
    pass


class NetBoxAPIError(NetBoxError):
    """
    Ошибка при вызове NetBox API.

    Attributes:
        status_code: HTTP код ответа
        endpoint: API endpoint

    Пример:
        raise NetBoxAPIError("Not found", status_code=404, endpoint="/api/dcim/devices/")
    """

    def __init__(
        self,
        message: str,
        url: Optional[str] = None,
        status_code: Optional[int] = None,
        endpoint: Optional[str] = None,
        details: Optional[dict] = None,
    ):
        self.status_code = status_code
        self.endpoint = endpoint
        details = details or {}
        if status_code:
            details["status_code"] = status_code
        if endpoint:
            details["endpoint"] = endpoint
        super().__init__(message, url, details)


class NetBoxValidationError(NetBoxError):
    """
    Ошибка валидации данных для NetBox.

    Attributes:
        field: Поле с ошибкой
        value: Значение которое не прошло валидацию

    Пример:
        raise NetBoxValidationError("Invalid IP format", field="address", value="not-an-ip")
    """

    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        value: Optional[Any] = None,
        url: Optional[str] = None,
        details: Optional[dict] = None,
    ):
        self.field = field
        self.value = value
        details = details or {}
        if field:
            details["field"] = field
        if value is not None:
            details["value"] = str(value)[:100]  # Ограничиваем размер
        super().__init__(message, url, details)


# === Config Errors ===

class ConfigError(NetworkCollectorError):
    """
    Ошибка конфигурации.

    Attributes:
        config_file: Путь к файлу конфигурации
        key: Ключ конфигурации с ошибкой

    Пример:
        raise ConfigError("Missing required field", config_file="config.yaml", key="netbox.url")
    """

    def __init__(
        self,
        message: str,
        config_file: Optional[str] = None,
        key: Optional[str] = None,
        details: Optional[dict] = None,
    ):
        self.config_file = config_file
        self.key = key
        details = details or {}
        if config_file:
            details["config_file"] = config_file
        if key:
            details["key"] = key
        super().__init__(message, details)


# === Utility Functions ===

def format_error_for_log(error: Exception) -> str:
    """
    Форматирует ошибку для вывода в лог.

    Args:
        error: Исключение

    Returns:
        str: Отформатированная строка ошибки
    """
    if isinstance(error, NetworkCollectorError):
        return str(error)
    return f"{error.__class__.__name__}: {error}"


def is_retryable(error: Exception) -> bool:
    """
    Проверяет, можно ли повторить операцию после ошибки.

    Args:
        error: Исключение

    Returns:
        bool: True если можно retry
    """
    retryable_types = (
        ConnectionError,
        TimeoutError,
        NetBoxConnectionError,
    )
    return isinstance(error, retryable_types)
