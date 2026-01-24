"""
Тесты для Structured Logging.

Проверяет:
- JSON форматирование
- Human-readable форматирование
- StructuredLogger с extra полями
- bind() для создания child логгеров
- LogContext для временных полей
- OperationLog для tracking операций
"""

import pytest
import json
import logging
from datetime import datetime
from io import StringIO
from unittest.mock import patch, MagicMock

from network_collector.core.logging import (
    LogRecord,
    JSONFormatter,
    HumanFormatter,
    StructuredLogger,
    get_logger,
    setup_json_logging,
    setup_human_logging,
    setup_logging,
    setup_file_logging,
    setup_logging_from_config,
    LogContext,
    OperationLog,
    LogLevel,
    LogConfig,
    RotationType,
)


class TestLogRecord:
    """Тесты LogRecord dataclass."""

    def test_to_dict_basic(self):
        """Базовая сериализация."""
        record = LogRecord(
            timestamp="2025-12-27T10:30:15",
            level="INFO",
            message="Test message",
        )
        data = record.to_dict()

        assert data["timestamp"] == "2025-12-27T10:30:15"
        assert data["level"] == "INFO"
        assert data["message"] == "Test message"

    def test_to_dict_with_all_fields(self):
        """Сериализация со всеми полями."""
        record = LogRecord(
            timestamp="2025-12-27T10:30:15",
            level="ERROR",
            message="Connection failed",
            logger="network_collector.core",
            run_id="2025-12-27T10-30-00",
            device="switch-01",
            operation="connect",
            extra={"ip": "10.0.0.1", "port": 22},
        )
        data = record.to_dict()

        assert data["logger"] == "network_collector.core"
        assert data["run_id"] == "2025-12-27T10-30-00"
        assert data["device"] == "switch-01"
        assert data["operation"] == "connect"
        assert data["ip"] == "10.0.0.1"
        assert data["port"] == 22

    def test_to_dict_excludes_empty(self):
        """Пустые поля не включаются."""
        record = LogRecord(
            timestamp="2025-12-27T10:30:15",
            level="INFO",
            message="Test",
        )
        data = record.to_dict()

        assert "logger" not in data  # пустой
        assert "run_id" not in data
        assert "device" not in data

    def test_to_json(self):
        """Конвертация в JSON строку."""
        record = LogRecord(
            timestamp="2025-12-27T10:30:15",
            level="INFO",
            message="Test",
        )
        json_str = record.to_json()
        data = json.loads(json_str)

        assert data["timestamp"] == "2025-12-27T10:30:15"
        assert data["level"] == "INFO"


class TestJSONFormatter:
    """Тесты JSON форматтера."""

    def test_basic_format(self):
        """Базовое форматирование."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        result = formatter.format(record)
        data = json.loads(result)

        assert data["level"] == "INFO"
        assert data["message"] == "Test message"
        assert data["logger"] == "test.logger"
        assert "timestamp" in data

    def test_format_with_extra(self):
        """Форматирование с extra полями."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Connected",
            args=(),
            exc_info=None,
        )
        record.device = "switch-01"
        record.ip = "10.0.0.1"
        record.run_id = "test-run"

        result = formatter.format(record)
        data = json.loads(result)

        assert data["device"] == "switch-01"
        assert data["ip"] == "10.0.0.1"
        assert data["run_id"] == "test-run"

    def test_format_with_exception(self):
        """Форматирование с exception."""
        formatter = JSONFormatter()

        try:
            raise ValueError("Test error")
        except ValueError:
            import sys
            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=10,
            msg="Error occurred",
            args=(),
            exc_info=exc_info,
        )

        result = formatter.format(record)
        data = json.loads(result)

        assert "exception" in data
        assert "ValueError" in data["exception"]
        assert "Test error" in data["exception"]

    def test_format_with_args(self):
        """Форматирование с аргументами."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Device %s connected on port %d",
            args=("switch-01", 22),
            exc_info=None,
        )

        result = formatter.format(record)
        data = json.loads(result)

        assert data["message"] == "Device switch-01 connected on port 22"


class TestHumanFormatter:
    """Тесты human-readable форматтера."""

    def test_basic_format(self):
        """Базовое форматирование."""
        formatter = HumanFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        result = formatter.format(record)

        assert "INFO" in result
        assert "Test message" in result

    def test_format_with_run_id(self):
        """Форматирование с run_id."""
        formatter = HumanFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test",
            args=(),
            exc_info=None,
        )
        record.run_id = "test-run-id"

        result = formatter.format(record)

        assert "[test-run-id]" in result

    def test_format_with_extras(self):
        """Форматирование с extra полями."""
        formatter = HumanFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Connected",
            args=(),
            exc_info=None,
        )
        record.device = "switch-01"
        record.ip = "10.0.0.1"

        result = formatter.format(record)

        assert "device=switch-01" in result
        assert "ip=10.0.0.1" in result


class TestStructuredLogger:
    """Тесты StructuredLogger."""

    def test_info_with_extra(self):
        """Логирование INFO с extra полями."""
        stream = StringIO()
        setup_json_logging(level=logging.DEBUG, stream=stream)

        logger = StructuredLogger("test")
        logger.info("Test message", device="switch-01", ip="10.0.0.1")

        output = stream.getvalue()
        data = json.loads(output.strip())

        assert data["message"] == "Test message"
        assert data["device"] == "switch-01"
        assert data["ip"] == "10.0.0.1"

    def test_error_with_exc_info(self):
        """Логирование ERROR с traceback."""
        stream = StringIO()
        setup_json_logging(level=logging.DEBUG, stream=stream)

        logger = StructuredLogger("test")

        try:
            raise ValueError("Test error")
        except ValueError:
            logger.exception("Error occurred", device="switch-01")

        output = stream.getvalue()
        data = json.loads(output.strip())

        assert data["level"] == "ERROR"
        assert "exception" in data
        assert "ValueError" in data["exception"]

    def test_bind_creates_child_logger(self):
        """bind() создаёт логгер с default полями."""
        stream = StringIO()
        setup_json_logging(level=logging.DEBUG, stream=stream)

        parent = StructuredLogger("test")
        child = parent.bind(device="switch-01", ip="10.0.0.1")

        child.info("Connected")

        output = stream.getvalue()
        data = json.loads(output.strip())

        assert data["device"] == "switch-01"
        assert data["ip"] == "10.0.0.1"

    def test_bind_override_fields(self):
        """bind() можно перезаписать поля."""
        stream = StringIO()
        setup_json_logging(level=logging.DEBUG, stream=stream)

        parent = StructuredLogger("test")
        child = parent.bind(device="default")

        child.info("Test", device="override")

        output = stream.getvalue()
        data = json.loads(output.strip())

        assert data["device"] == "override"

    def test_all_levels(self):
        """Все уровни логирования."""
        stream = StringIO()
        setup_json_logging(level=logging.DEBUG, stream=stream)

        logger = StructuredLogger("test")

        logger.debug("debug")
        logger.info("info")
        logger.warning("warning")
        logger.warn("warn")  # alias
        logger.error("error")
        logger.critical("critical")

        lines = stream.getvalue().strip().split("\n")
        assert len(lines) == 6

        levels = [json.loads(line)["level"] for line in lines]
        assert levels == ["DEBUG", "INFO", "WARNING", "WARNING", "ERROR", "CRITICAL"]


class TestGetLogger:
    """Тесты get_logger()."""

    def test_returns_structured_logger(self):
        """Возвращает StructuredLogger."""
        logger = get_logger("test.module")
        assert isinstance(logger, StructuredLogger)

    def test_caches_loggers(self):
        """Кэширует логгеры."""
        logger1 = get_logger("test.cache")
        logger2 = get_logger("test.cache")
        assert logger1 is logger2

    def test_different_names_different_loggers(self):
        """Разные имена — разные логгеры."""
        logger1 = get_logger("test.a")
        logger2 = get_logger("test.b")
        assert logger1 is not logger2


class TestSetupLogging:
    """Тесты setup функций."""

    def test_setup_json_logging(self):
        """setup_json_logging настраивает JSON формат."""
        stream = StringIO()
        setup_json_logging(level=logging.INFO, stream=stream)

        logging.info("Test")

        output = stream.getvalue()
        data = json.loads(output.strip())
        assert data["message"] == "Test"

    def test_setup_human_logging(self):
        """setup_human_logging настраивает human формат."""
        stream = StringIO()
        setup_human_logging(level=logging.INFO, stream=stream)

        logging.info("Test")

        output = stream.getvalue()
        assert "INFO" in output
        assert "Test" in output
        # Не JSON
        with pytest.raises(json.JSONDecodeError):
            json.loads(output)

    def test_setup_logging_switch(self):
        """setup_logging переключает формат."""
        stream = StringIO()

        # JSON
        setup_logging(json_format=True, level=logging.INFO, stream=stream)
        logging.info("JSON")
        json_output = stream.getvalue()
        assert json.loads(json_output.strip())["message"] == "JSON"

        # Human
        stream = StringIO()
        setup_logging(json_format=False, level=logging.INFO, stream=stream)
        logging.info("Human")
        human_output = stream.getvalue()
        assert "Human" in human_output


class TestLogContext:
    """Тесты LogContext context manager."""

    def test_adds_fields_in_context(self):
        """Добавляет поля внутри контекста."""
        stream = StringIO()
        setup_json_logging(level=logging.INFO, stream=stream)

        with LogContext(device="switch-01", operation="collect"):
            logging.info("Inside context")

        output = stream.getvalue()
        data = json.loads(output.strip())

        assert data["device"] == "switch-01"
        assert data["operation"] == "collect"

    def test_removes_fields_after_context(self):
        """Убирает поля после выхода из контекста."""
        stream = StringIO()
        setup_json_logging(level=logging.INFO, stream=stream)

        with LogContext(device="switch-01"):
            logging.info("Inside")

        # Очищаем stream для второго лога
        stream.truncate(0)
        stream.seek(0)

        logging.info("Outside")

        output = stream.getvalue()
        data = json.loads(output.strip())

        assert "device" not in data


class TestOperationLog:
    """Тесты OperationLog."""

    def test_start(self):
        """start() устанавливает время и статус."""
        op = OperationLog(operation="collect", device="switch-01")
        op.start()

        assert op.status == "running"
        assert op.started_at is not None

    def test_success(self):
        """success() завершает операцию."""
        op = OperationLog(operation="collect", device="switch-01")
        op.start()
        op.success(records=100, interfaces=10)

        assert op.status == "success"
        assert op.completed_at is not None
        assert op.result["records"] == 100
        assert op.result["interfaces"] == 10

    def test_failure(self):
        """failure() завершает с ошибкой."""
        op = OperationLog(operation="collect", device="switch-01")
        op.start()
        op.failure("Connection timeout")

        assert op.status == "failure"
        assert op.error == "Connection timeout"

    def test_duration_ms(self):
        """duration_ms вычисляется правильно."""
        op = OperationLog(operation="test")
        op.start()

        # Имитируем прошедшее время
        import time
        time.sleep(0.01)  # 10ms

        op.success()

        assert op.duration_ms is not None
        assert op.duration_ms >= 10  # минимум 10ms

    def test_duration_ms_none_before_complete(self):
        """duration_ms = None до завершения."""
        op = OperationLog(operation="test")
        assert op.duration_ms is None

        op.start()
        assert op.duration_ms is None  # ещё не завершена

    def test_to_dict(self):
        """Сериализация в словарь."""
        op = OperationLog(operation="collect", device="switch-01")
        op.start()
        op.success(records=100)

        data = op.to_dict()

        assert data["operation"] == "collect"
        assert data["device"] == "switch-01"
        assert data["status"] == "success"
        assert "started_at" in data
        assert "completed_at" in data
        assert "duration_ms" in data
        assert data["result"]["records"] == 100

    def test_to_dict_failure(self):
        """Сериализация с ошибкой."""
        op = OperationLog(operation="connect", device="switch-01")
        op.start()
        op.failure("Connection refused")

        data = op.to_dict()

        assert data["status"] == "failure"
        assert data["error"] == "Connection refused"

    def test_to_json(self):
        """Конвертация в JSON."""
        op = OperationLog(operation="test")
        op.start()
        op.success()

        json_str = op.to_json()
        data = json.loads(json_str)

        assert data["operation"] == "test"
        assert data["status"] == "success"

    def test_log(self):
        """log() отправляет в логгер."""
        stream = StringIO()
        setup_json_logging(level=logging.INFO, stream=stream)

        op = OperationLog(operation="collect", device="switch-01")
        op.start()
        op.success(records=50)
        op.log()

        output = stream.getvalue()
        data = json.loads(output.strip())

        assert "Operation collect success" in data["message"]
        assert data["device"] == "switch-01"
        assert data["records"] == 50

    def test_log_failure_is_error(self):
        """log() для failure использует ERROR уровень."""
        stream = StringIO()
        setup_json_logging(level=logging.DEBUG, stream=stream)

        op = OperationLog(operation="connect")
        op.start()
        op.failure("Timeout")
        op.log()

        output = stream.getvalue()
        data = json.loads(output.strip())

        assert data["level"] == "ERROR"
        assert data["error"] == "Timeout"


class TestLogLevel:
    """Тесты LogLevel enum."""

    def test_values(self):
        """Значения enum."""
        assert LogLevel.DEBUG.value == "DEBUG"
        assert LogLevel.INFO.value == "INFO"
        assert LogLevel.WARNING.value == "WARNING"
        assert LogLevel.ERROR.value == "ERROR"
        assert LogLevel.CRITICAL.value == "CRITICAL"

    def test_is_string(self):
        """LogLevel наследуется от str и сравнивается со строками."""
        assert LogLevel.INFO == "INFO"
        assert LogLevel.ERROR == "ERROR"
        assert LogLevel.WARNING == "WARNING"


class TestIntegrationWithRunContext:
    """Тесты интеграции с RunContext."""

    def test_auto_run_id_from_context(self):
        """run_id автоматически берётся из RunContext."""
        from network_collector.core.context import RunContext, set_current_context

        stream = StringIO()
        setup_json_logging(level=logging.INFO, stream=stream)

        # Создаём контекст
        ctx = RunContext.create(command="test")
        set_current_context(ctx)

        try:
            logger = StructuredLogger("test")
            logger.info("Test message")

            output = stream.getvalue()
            data = json.loads(output.strip())

            assert data["run_id"] == ctx.run_id
        finally:
            set_current_context(None)

    def test_explicit_run_id_overrides(self):
        """Явный run_id перезаписывает контекст."""
        from network_collector.core.context import RunContext, set_current_context

        stream = StringIO()
        setup_json_logging(level=logging.INFO, stream=stream)

        ctx = RunContext.create(command="test")
        set_current_context(ctx)

        try:
            logger = StructuredLogger("test")
            logger.info("Test", run_id="explicit-id")

            output = stream.getvalue()
            data = json.loads(output.strip())

            assert data["run_id"] == "explicit-id"
        finally:
            set_current_context(None)


class TestRotationType:
    """Тесты RotationType enum."""

    def test_values(self):
        """Значения enum."""
        assert RotationType.SIZE.value == "size"
        assert RotationType.TIME.value == "time"
        assert RotationType.NONE.value == "none"


class TestLogConfig:
    """Тесты LogConfig dataclass."""

    def test_defaults(self):
        """Значения по умолчанию."""
        config = LogConfig()

        assert config.level == logging.INFO
        assert config.json_format is False
        assert config.console is True
        assert config.file_path is None
        assert config.rotation == RotationType.SIZE
        assert config.max_bytes == 10 * 1024 * 1024
        assert config.backup_count == 5
        assert config.when == "midnight"
        assert config.interval == 1

    def test_from_dict_basic(self):
        """Создание из словаря."""
        data = {
            "level": "DEBUG",
            "json_format": True,
            "file_path": "logs/app.log",
        }
        config = LogConfig.from_dict(data)

        assert config.level == logging.DEBUG
        assert config.json_format is True
        assert config.file_path == "logs/app.log"

    def test_from_dict_with_rotation(self):
        """Создание из словаря с ротацией."""
        data = {
            "rotation": "time",
            "when": "H",
            "interval": 2,
            "backup_count": 48,
        }
        config = LogConfig.from_dict(data)

        assert config.rotation == RotationType.TIME
        assert config.when == "H"
        assert config.interval == 2
        assert config.backup_count == 48


class TestFileLogging:
    """Тесты файлового логирования."""

    def test_setup_file_logging_creates_directory(self, tmp_path):
        """setup_file_logging создаёт директорию."""
        log_file = tmp_path / "subdir" / "app.log"

        setup_file_logging(
            str(log_file),
            console=False,
        )

        # Директория создана
        assert log_file.parent.exists()

        logging.info("Test message")

        # Файл создан и содержит лог
        assert log_file.exists()
        content = log_file.read_text()
        data = json.loads(content.strip())
        assert data["message"] == "Test message"

    def test_setup_file_logging_json_format(self, tmp_path):
        """JSON формат в файле."""
        log_file = tmp_path / "app.log"

        setup_file_logging(
            str(log_file),
            json_format=True,
            console=False,
        )

        logging.info("Test", extra={"device": "switch-01"})

        content = log_file.read_text()
        data = json.loads(content.strip())
        assert data["level"] == "INFO"
        assert data["device"] == "switch-01"

    def test_setup_file_logging_with_console(self, tmp_path):
        """Файл + консоль."""
        log_file = tmp_path / "app.log"
        stream = StringIO()

        # Патчим stderr
        with patch("sys.stderr", stream):
            setup_file_logging(
                str(log_file),
                console=True,
            )

            logging.info("Test message")

        # В файле — JSON
        file_content = log_file.read_text()
        data = json.loads(file_content.strip())
        assert data["message"] == "Test message"

        # В консоли — human-readable
        console_output = stream.getvalue()
        assert "Test message" in console_output
        # Не JSON
        with pytest.raises(json.JSONDecodeError):
            json.loads(console_output)

    def test_setup_logging_from_config(self, tmp_path):
        """Настройка из LogConfig."""
        log_file = tmp_path / "app.log"

        config = LogConfig(
            level=logging.DEBUG,
            json_format=True,
            console=False,
            file_path=str(log_file),
            rotation=RotationType.SIZE,
            max_bytes=1024,
            backup_count=3,
        )

        setup_logging_from_config(config)

        logging.debug("Debug message")
        logging.info("Info message")

        content = log_file.read_text()
        lines = content.strip().split("\n")
        assert len(lines) == 2

        # Оба сообщения записаны
        assert "Debug message" in lines[0]
        assert "Info message" in lines[1]

    def test_rotation_by_size(self, tmp_path):
        """Ротация по размеру файла."""
        log_file = tmp_path / "app.log"

        setup_file_logging(
            str(log_file),
            rotation=RotationType.SIZE,
            max_bytes=100,  # Очень маленький для теста
            backup_count=3,
            console=False,
        )

        # Пишем много логов чтобы превысить лимит
        for i in range(20):
            logging.info(f"Message number {i} with some extra text to fill the log")

        # Должны появиться backup файлы
        log_files = list(tmp_path.glob("app.log*"))
        assert len(log_files) > 1  # Основной + backup

    def test_rotation_type_none(self, tmp_path):
        """Без ротации."""
        log_file = tmp_path / "app.log"

        setup_file_logging(
            str(log_file),
            rotation=RotationType.NONE,
            console=False,
        )

        logging.info("Test")

        assert log_file.exists()
        content = log_file.read_text()
        assert "Test" in content
