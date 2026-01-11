"""
Structured Logging для Network Collector.

JSON-формат логов для интеграции с ELK/Grafana/Loki.

Преимущества:
- Машиночитаемый формат
- Структурированные поля (run_id, device, operation)
- Легко фильтровать и агрегировать
- Интеграция с log aggregation системами

Пример использования:
    from network_collector.core.logging import setup_json_logging, get_logger

    # Настройка в начале программы
    setup_json_logging()

    # Логирование с контекстом
    logger = get_logger(__name__)
    logger.info("Подключение к устройству", device="switch-01", ip="10.0.0.1")

Формат вывода (JSON):
    {"timestamp": "2025-12-27T10:30:15.123456", "level": "INFO",
     "message": "Подключение к устройству", "device": "switch-01",
     "ip": "10.0.0.1", "run_id": "2025-12-27T10-30-00"}
"""

import json
import logging
import logging.handlers
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Union, List
from dataclasses import dataclass, field, asdict
from enum import Enum


class LogLevel(str, Enum):
    """Уровни логирования."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class RotationType(str, Enum):
    """Тип ротации логов."""
    SIZE = "size"       # По размеру файла
    TIME = "time"       # По времени
    NONE = "none"       # Без ротации


@dataclass
class LogConfig:
    """
    Конфигурация логирования.

    Attributes:
        level: Уровень логирования (DEBUG, INFO, etc.)
        json_format: JSON формат (True) или human-readable (False)
        console: Выводить в консоль
        file_path: Путь к файлу логов (None = без файла)
        rotation: Тип ротации (size, time, none)
        max_bytes: Макс размер файла для size-ротации (default: 10MB)
        backup_count: Количество backup файлов (default: 5)
        when: Интервал для time-ротации (S, M, H, D, midnight)
        interval: Частота ротации для time (default: 1)

    Example:
        # JSON в консоль + файл с ротацией по размеру
        config = LogConfig(
            json_format=True,
            file_path="logs/app.log",
            rotation=RotationType.SIZE,
            max_bytes=10*1024*1024,  # 10 MB
            backup_count=5,
        )
        setup_logging_from_config(config)
    """
    level: int = logging.INFO
    json_format: bool = False
    console: bool = True
    file_path: Optional[str] = None
    rotation: RotationType = RotationType.SIZE
    max_bytes: int = 10 * 1024 * 1024  # 10 MB
    backup_count: int = 5
    when: str = "midnight"  # S, M, H, D, W0-W6, midnight
    interval: int = 1

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LogConfig":
        """Создаёт конфигурацию из словаря."""
        rotation = data.get("rotation", "size")
        if isinstance(rotation, str):
            rotation = RotationType(rotation)

        level = data.get("level", "INFO")
        if isinstance(level, str):
            level = getattr(logging, level.upper(), logging.INFO)

        return cls(
            level=level,
            json_format=data.get("json_format", False),
            console=data.get("console", True),
            file_path=data.get("file_path"),
            rotation=rotation,
            max_bytes=data.get("max_bytes", 10 * 1024 * 1024),
            backup_count=data.get("backup_count", 5),
            when=data.get("when", "midnight"),
            interval=data.get("interval", 1),
        )


@dataclass
class LogRecord:
    """
    Структурированная запись лога.

    Attributes:
        timestamp: ISO timestamp
        level: Уровень (INFO, ERROR, etc.)
        message: Текст сообщения
        logger: Имя логгера
        run_id: ID запуска (из RunContext)
        device: Имя устройства (опционально)
        operation: Тип операции (collect, sync, etc.)
        extra: Дополнительные поля
    """
    timestamp: str
    level: str
    message: str
    logger: str = ""
    run_id: str = ""
    device: str = ""
    operation: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Конвертирует в словарь (без пустых полей)."""
        result = {
            "timestamp": self.timestamp,
            "level": self.level,
            "message": self.message,
        }
        if self.logger:
            result["logger"] = self.logger
        if self.run_id:
            result["run_id"] = self.run_id
        if self.device:
            result["device"] = self.device
        if self.operation:
            result["operation"] = self.operation
        if self.extra:
            result.update(self.extra)
        return result

    def to_json(self) -> str:
        """Конвертирует в JSON строку."""
        return json.dumps(self.to_dict(), ensure_ascii=False)


class JSONFormatter(logging.Formatter):
    """
    JSON форматтер для logging.

    Преобразует LogRecord в JSON строку со всеми полями.

    Стандартные поля:
    - timestamp: ISO время
    - level: уровень (INFO, ERROR)
    - message: сообщение
    - logger: имя логгера
    - run_id: ID запуска
    - device: устройство (если есть)
    - operation: операция (если есть)

    Дополнительные поля из extra логируются как есть.
    """

    # Поля logging.LogRecord которые не нужно включать в JSON
    RESERVED_ATTRS = {
        "args", "asctime", "created", "exc_info", "exc_text",
        "filename", "funcName", "levelname", "levelno", "lineno",
        "module", "msecs", "msg", "name", "pathname", "process",
        "processName", "relativeCreated", "stack_info", "thread",
        "threadName", "taskName",
    }

    # Поля которые мы специально обрабатываем
    KNOWN_EXTRA = {"run_id", "device", "operation", "ip", "platform"}

    def format(self, record: logging.LogRecord) -> str:
        """
        Форматирует запись лога в JSON.

        Args:
            record: logging.LogRecord

        Returns:
            str: JSON строка
        """
        # Базовые поля
        log_data = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }

        # Добавляем известные extra поля
        for attr in self.KNOWN_EXTRA:
            value = getattr(record, attr, None)
            if value is not None:
                log_data[attr] = value

        # Добавляем любые другие extra поля
        for key, value in record.__dict__.items():
            if key not in self.RESERVED_ATTRS and key not in self.KNOWN_EXTRA:
                if not key.startswith("_"):
                    log_data[key] = value

        # Exception info
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data, ensure_ascii=False, default=str)


class HumanFormatter(logging.Formatter):
    """
    Human-readable форматтер с поддержкой extra полей.

    Формат: TIMESTAMP - LEVEL - [run_id] MESSAGE (device=X, ip=Y)
    """

    def format(self, record: logging.LogRecord) -> str:
        """Форматирует запись для человека."""
        # Базовый формат
        timestamp = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")
        level = record.levelname.ljust(8)
        message = record.getMessage()

        # Run ID prefix
        run_id = getattr(record, "run_id", None)
        if run_id:
            prefix = f"[{run_id}] "
        else:
            prefix = ""

        # Extra поля в скобках
        extras = []
        for attr in ("device", "ip", "platform", "operation"):
            value = getattr(record, attr, None)
            if value:
                extras.append(f"{attr}={value}")

        if extras:
            extra_str = f" ({', '.join(extras)})"
        else:
            extra_str = ""

        result = f"{timestamp} - {level} - {prefix}{message}{extra_str}"

        # Exception
        if record.exc_info:
            result += "\n" + self.formatException(record.exc_info)

        return result


class StructuredLogger:
    """
    Обёртка над logging.Logger с поддержкой структурированных полей.

    Позволяет логировать с именованными параметрами:
        logger.info("Подключение", device="switch-01", ip="10.0.0.1")

    Вместо:
        logger.info("Подключение к switch-01 (10.0.0.1)")
    """

    def __init__(self, name: str, default_extra: Optional[Dict[str, Any]] = None):
        """
        Инициализация.

        Args:
            name: Имя логгера
            default_extra: Поля добавляемые ко всем сообщениям
        """
        self._logger = logging.getLogger(name)
        self._default_extra = default_extra or {}

    def _log(
        self,
        level: int,
        message: str,
        exc_info: bool = False,
        **kwargs: Any,
    ) -> None:
        """
        Внутренний метод логирования.

        Args:
            level: Уровень (logging.INFO, etc.)
            message: Сообщение
            exc_info: Включить traceback
            **kwargs: Дополнительные поля
        """
        # Объединяем default_extra и kwargs
        extra = {**self._default_extra, **kwargs}

        # Добавляем run_id из глобального контекста если не указан
        if "run_id" not in extra:
            from network_collector.core.context import get_current_context
            ctx = get_current_context()
            if ctx:
                extra["run_id"] = ctx.run_id

        self._logger.log(level, message, exc_info=exc_info, extra=extra)

    def debug(self, message: str, **kwargs: Any) -> None:
        """Log DEBUG."""
        self._log(logging.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs: Any) -> None:
        """Log INFO."""
        self._log(logging.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        """Log WARNING."""
        self._log(logging.WARNING, message, **kwargs)

    def warn(self, message: str, **kwargs: Any) -> None:
        """Log WARNING (alias)."""
        self.warning(message, **kwargs)

    def error(self, message: str, exc_info: bool = False, **kwargs: Any) -> None:
        """Log ERROR."""
        self._log(logging.ERROR, message, exc_info=exc_info, **kwargs)

    def critical(self, message: str, exc_info: bool = False, **kwargs: Any) -> None:
        """Log CRITICAL."""
        self._log(logging.CRITICAL, message, exc_info=exc_info, **kwargs)

    def exception(self, message: str, **kwargs: Any) -> None:
        """Log ERROR с traceback."""
        self._log(logging.ERROR, message, exc_info=True, **kwargs)

    def bind(self, **kwargs: Any) -> "StructuredLogger":
        """
        Создаёт новый логгер с дополнительными default полями.

        Args:
            **kwargs: Поля добавляемые ко всем сообщениям

        Returns:
            StructuredLogger: Новый логгер

        Example:
            device_logger = logger.bind(device="switch-01", ip="10.0.0.1")
            device_logger.info("Connected")  # автоматически добавит device, ip
        """
        new_extra = {**self._default_extra, **kwargs}
        return StructuredLogger(self._logger.name, default_extra=new_extra)

    def setLevel(self, level: int) -> None:
        """Устанавливает уровень логирования."""
        self._logger.setLevel(level)

    @property
    def level(self) -> int:
        """Текущий уровень логирования."""
        return self._logger.level


# Кэш логгеров
_loggers: Dict[str, StructuredLogger] = {}


def get_logger(name: str) -> StructuredLogger:
    """
    Получает или создаёт StructuredLogger.

    Args:
        name: Имя логгера (обычно __name__)

    Returns:
        StructuredLogger: Логгер

    Example:
        logger = get_logger(__name__)
        logger.info("Started", operation="collect")
    """
    if name not in _loggers:
        _loggers[name] = StructuredLogger(name)
    return _loggers[name]


def setup_json_logging(
    level: int = logging.INFO,
    stream: Any = None,
) -> None:
    """
    Настраивает JSON логирование.

    Args:
        level: Уровень логирования
        stream: Поток вывода (по умолчанию sys.stderr)

    Example:
        setup_json_logging()
        # Все логи будут в JSON формате
    """
    if stream is None:
        stream = sys.stderr

    root_logger = logging.getLogger()

    # Удаляем существующие handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Создаём новый handler с JSON форматом
    handler = logging.StreamHandler(stream)
    handler.setLevel(level)
    handler.setFormatter(JSONFormatter())

    root_logger.addHandler(handler)
    root_logger.setLevel(level)


def setup_human_logging(
    level: int = logging.INFO,
    stream: Any = None,
) -> None:
    """
    Настраивает human-readable логирование.

    Args:
        level: Уровень логирования
        stream: Поток вывода (по умолчанию sys.stderr)

    Example:
        setup_human_logging()
        # Логи в формате: 2025-12-27 10:30:15 - INFO - [run_id] Message
    """
    if stream is None:
        stream = sys.stderr

    root_logger = logging.getLogger()

    # Удаляем существующие handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Создаём новый handler с human форматом
    handler = logging.StreamHandler(stream)
    handler.setLevel(level)
    handler.setFormatter(HumanFormatter())

    root_logger.addHandler(handler)
    root_logger.setLevel(level)


def setup_logging(
    json_format: bool = False,
    level: int = logging.INFO,
    stream: Any = None,
) -> None:
    """
    Универсальная настройка логирования.

    Args:
        json_format: True для JSON, False для human-readable
        level: Уровень логирования
        stream: Поток вывода

    Example:
        # CLI с флагом --json-logs
        setup_logging(json_format=args.json_logs)
    """
    if json_format:
        setup_json_logging(level=level, stream=stream)
    else:
        setup_human_logging(level=level, stream=stream)


def _create_file_handler(
    file_path: str,
    rotation: RotationType,
    max_bytes: int,
    backup_count: int,
    when: str,
    interval: int,
) -> logging.Handler:
    """
    Создаёт file handler с ротацией.

    Args:
        file_path: Путь к файлу
        rotation: Тип ротации
        max_bytes: Макс размер для size-ротации
        backup_count: Количество backup файлов
        when: Интервал для time-ротации
        interval: Частота ротации

    Returns:
        logging.Handler: FileHandler с нужной ротацией
    """
    # Создаём директорию если не существует
    log_path = Path(file_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    if rotation == RotationType.SIZE:
        return logging.handlers.RotatingFileHandler(
            filename=file_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
    elif rotation == RotationType.TIME:
        return logging.handlers.TimedRotatingFileHandler(
            filename=file_path,
            when=when,
            interval=interval,
            backupCount=backup_count,
            encoding="utf-8",
        )
    else:
        return logging.FileHandler(file_path, encoding="utf-8")


def setup_file_logging(
    file_path: str,
    level: int = logging.INFO,
    json_format: bool = True,
    rotation: RotationType = RotationType.SIZE,
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 5,
    when: str = "midnight",
    interval: int = 1,
    console: bool = True,
) -> None:
    """
    Настраивает логирование в файл с ротацией.

    Args:
        file_path: Путь к файлу логов
        level: Уровень логирования
        json_format: JSON формат (рекомендуется для файлов)
        rotation: Тип ротации (size, time, none)
        max_bytes: Макс размер файла (для size ротации, default 10MB)
        backup_count: Количество backup файлов (default 5)
        when: Интервал для time ротации (S, M, H, D, midnight)
        interval: Частота ротации для time (default 1)
        console: Также выводить в консоль

    Example:
        # JSON логи в файл с ротацией по 10MB, до 5 файлов
        setup_file_logging("logs/app.log")

        # Ротация по времени (каждый день в полночь)
        setup_file_logging(
            "logs/app.log",
            rotation=RotationType.TIME,
            when="midnight",
            backup_count=30,  # 30 дней
        )

        # Ротация каждый час
        setup_file_logging(
            "logs/app.log",
            rotation=RotationType.TIME,
            when="H",
            interval=1,
            backup_count=24,  # 24 часа
        )
    """
    formatter = JSONFormatter() if json_format else HumanFormatter()

    root_logger = logging.getLogger()

    # Удаляем существующие handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Файловый handler
    file_handler = _create_file_handler(
        file_path=file_path,
        rotation=rotation,
        max_bytes=max_bytes,
        backup_count=backup_count,
        when=when,
        interval=interval,
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # Консольный handler
    if console:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(level)
        # Консоль — human-readable (удобнее читать)
        console_handler.setFormatter(HumanFormatter())
        root_logger.addHandler(console_handler)

    root_logger.setLevel(level)


def setup_logging_from_config(config: LogConfig) -> None:
    """
    Настраивает логирование из конфигурации.

    Args:
        config: LogConfig с настройками

    Example:
        config = LogConfig(
            json_format=True,
            file_path="logs/app.log",
            rotation=RotationType.SIZE,
            max_bytes=50*1024*1024,  # 50 MB
            backup_count=10,
        )
        setup_logging_from_config(config)
    """
    formatter = JSONFormatter() if config.json_format else HumanFormatter()

    root_logger = logging.getLogger()

    # Удаляем существующие handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    handlers: List[logging.Handler] = []

    # Консольный handler
    if config.console:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(config.level)
        console_handler.setFormatter(HumanFormatter())  # Консоль всегда human
        handlers.append(console_handler)

    # Файловый handler
    if config.file_path:
        file_handler = _create_file_handler(
            file_path=config.file_path,
            rotation=config.rotation,
            max_bytes=config.max_bytes,
            backup_count=config.backup_count,
            when=config.when,
            interval=config.interval,
        )
        file_handler.setLevel(config.level)
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)

    for handler in handlers:
        root_logger.addHandler(handler)

    root_logger.setLevel(config.level)


class LogContext:
    """
    Context manager для временного добавления полей к логам.

    Example:
        with LogContext(device="switch-01"):
            logger.info("Connected")  # будет содержать device
            logger.info("Collecting")  # тоже
        logger.info("Done")  # уже без device
    """

    def __init__(self, **kwargs: Any):
        """
        Args:
            **kwargs: Поля добавляемые к логам
        """
        self._fields = kwargs
        self._old_factory = None

    def __enter__(self) -> "LogContext":
        """Входим в контекст."""
        # Сохраняем старую фабрику
        self._old_factory = logging.getLogRecordFactory()

        # Создаём новую фабрику которая добавляет наши поля
        fields = self._fields

        def record_factory(*args, **kwargs):
            record = self._old_factory(*args, **kwargs)
            for key, value in fields.items():
                if not hasattr(record, key):
                    setattr(record, key, value)
            return record

        logging.setLogRecordFactory(record_factory)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Выходим из контекста."""
        if self._old_factory:
            logging.setLogRecordFactory(self._old_factory)
        return False


@dataclass
class OperationLog:
    """
    Лог операции с timing и результатом.

    Использование:
        op = OperationLog(operation="collect_mac", device="switch-01")
        op.start()
        try:
            # ... работа ...
            op.success(records=100)
        except Exception as e:
            op.failure(str(e))
    """
    operation: str
    device: str = ""
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    status: str = "pending"
    result: Dict[str, Any] = field(default_factory=dict)
    error: str = ""

    def start(self) -> "OperationLog":
        """Начало операции."""
        self.started_at = datetime.now()
        self.status = "running"
        return self

    def success(self, **result: Any) -> "OperationLog":
        """Успешное завершение."""
        self.completed_at = datetime.now()
        self.status = "success"
        self.result = result
        return self

    def failure(self, error: str) -> "OperationLog":
        """Завершение с ошибкой."""
        self.completed_at = datetime.now()
        self.status = "failure"
        self.error = error
        return self

    @property
    def duration_ms(self) -> Optional[float]:
        """Длительность в миллисекундах."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds() * 1000
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Конвертирует в словарь для JSON."""
        data = {
            "operation": self.operation,
            "status": self.status,
        }
        if self.device:
            data["device"] = self.device
        if self.started_at:
            data["started_at"] = self.started_at.isoformat()
        if self.completed_at:
            data["completed_at"] = self.completed_at.isoformat()
        if self.duration_ms is not None:
            data["duration_ms"] = round(self.duration_ms, 2)
        if self.result:
            data["result"] = self.result
        if self.error:
            data["error"] = self.error
        return data

    def to_json(self) -> str:
        """Конвертирует в JSON строку."""
        return json.dumps(self.to_dict(), ensure_ascii=False)

    def log(self, logger: Optional[StructuredLogger] = None) -> None:
        """
        Логирует операцию.

        Args:
            logger: Логгер (по умолчанию network_collector)
        """
        if logger is None:
            logger = get_logger("network_collector")

        level = logging.INFO if self.status == "success" else logging.ERROR
        message = f"Operation {self.operation} {self.status}"

        extra = {
            "operation": self.operation,
            "status": self.status,
        }
        if self.device:
            extra["device"] = self.device
        if self.duration_ms is not None:
            extra["duration_ms"] = round(self.duration_ms, 2)
        if self.result:
            extra.update(self.result)
        if self.error:
            extra["error"] = self.error

        logger._log(level, message, **extra)
