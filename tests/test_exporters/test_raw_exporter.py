"""
Tests for RawExporter.

Тестирует вывод данных в stdout как JSON.
"""

import pytest
import json
from datetime import datetime, date
from io import StringIO
from unittest.mock import patch

from network_collector.exporters.raw_exporter import RawExporter


class TestRawExporterInit:
    """Тесты инициализации."""

    def test_default_init(self):
        """По умолчанию indent=2."""
        exporter = RawExporter()
        assert exporter.indent == 2
        assert exporter.encoding == "utf-8"

    def test_custom_indent(self):
        """Можно задать свой indent."""
        exporter = RawExporter(indent=4)
        assert exporter.indent == 4

    def test_compact_output(self):
        """indent=None для компактного вывода."""
        exporter = RawExporter(indent=None)
        assert exporter.indent is None

    def test_output_folder_ignored(self):
        """output_folder игнорируется - вывод в stdout."""
        exporter = RawExporter(output_folder="/some/path")
        assert exporter.file_extension == ""


class TestRawExporterExport:
    """Тесты метода export."""

    @pytest.fixture
    def exporter(self):
        return RawExporter(indent=2)

    def test_export_empty_list(self, exporter):
        """Пустой список выводит []."""
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            with patch("builtins.print", side_effect=lambda x: mock_stdout.write(x + "\n")):
                result = exporter.export([])

        assert result is None

    def test_export_simple_data(self):
        """Простые данные выводятся как JSON."""
        exporter = RawExporter(indent=2)
        data = [{"hostname": "switch1", "ip": "10.0.0.1"}]

        with patch("builtins.print") as mock_print:
            result = exporter.export(data)

        assert result is None
        mock_print.assert_called_once()
        output = mock_print.call_args[0][0]
        parsed = json.loads(output)
        assert parsed == data

    def test_export_multiple_records(self):
        """Несколько записей."""
        exporter = RawExporter(indent=None)
        data = [
            {"hostname": "switch1", "ip": "10.0.0.1"},
            {"hostname": "switch2", "ip": "10.0.0.2"},
        ]

        with patch("builtins.print") as mock_print:
            exporter.export(data)

        output = mock_print.call_args[0][0]
        parsed = json.loads(output)
        assert len(parsed) == 2
        assert parsed[0]["hostname"] == "switch1"
        assert parsed[1]["hostname"] == "switch2"

    def test_export_unicode(self):
        """Юникод корректно выводится."""
        exporter = RawExporter()
        data = [{"description": "Сервер 1"}]

        with patch("builtins.print") as mock_print:
            exporter.export(data)

        output = mock_print.call_args[0][0]
        parsed = json.loads(output)
        assert parsed[0]["description"] == "Сервер 1"

    def test_export_filename_ignored(self):
        """filename игнорируется."""
        exporter = RawExporter()
        data = [{"test": "data"}]

        with patch("builtins.print"):
            result = exporter.export(data, filename="ignored.json")

        assert result is None

    def test_export_kwargs_ignored(self):
        """Дополнительные kwargs игнорируются."""
        exporter = RawExporter()
        data = [{"test": "data"}]

        with patch("builtins.print"):
            result = exporter.export(data, some_param="ignored")

        assert result is None


class TestJsonSerializer:
    """Тесты сериализатора нестандартных типов."""

    def test_serialize_datetime(self):
        """datetime сериализуется в ISO формат."""
        exporter = RawExporter()
        dt = datetime(2024, 1, 15, 12, 30, 45)
        data = [{"created": dt}]

        with patch("builtins.print") as mock_print:
            exporter.export(data)

        output = mock_print.call_args[0][0]
        parsed = json.loads(output)
        assert parsed[0]["created"] == "2024-01-15T12:30:45"

    def test_serialize_date(self):
        """date сериализуется в ISO формат."""
        exporter = RawExporter()
        d = date(2024, 1, 15)
        data = [{"date": d}]

        with patch("builtins.print") as mock_print:
            exporter.export(data)

        output = mock_print.call_args[0][0]
        parsed = json.loads(output)
        assert parsed[0]["date"] == "2024-01-15"

    def test_serialize_set(self):
        """set сериализуется в list."""
        exporter = RawExporter()
        data = [{"tags": {"a", "b", "c"}}]

        with patch("builtins.print") as mock_print:
            exporter.export(data)

        output = mock_print.call_args[0][0]
        parsed = json.loads(output)
        assert set(parsed[0]["tags"]) == {"a", "b", "c"}

    def test_serialize_object_with_dict(self):
        """Объект с __dict__ сериализуется."""
        class SimpleObj:
            def __init__(self):
                self.name = "test"
                self.value = 42

        exporter = RawExporter()
        obj = SimpleObj()
        data = [{"obj": obj}]

        with patch("builtins.print") as mock_print:
            exporter.export(data)

        output = mock_print.call_args[0][0]
        parsed = json.loads(output)
        assert parsed[0]["obj"]["name"] == "test"
        assert parsed[0]["obj"]["value"] == 42

    def test_serialize_unsupported_type_raises(self):
        """Неподдерживаемый тип вызывает TypeError."""
        exporter = RawExporter()

        class NoDict:
            __slots__ = ()  # Нет __dict__

        obj = NoDict()
        data = [{"obj": obj}]

        with pytest.raises(TypeError, match="not JSON serializable"):
            with patch("builtins.print"):
                exporter.export(data)


class TestWriteMethod:
    """Тесты метода _write."""

    def test_write_is_noop(self):
        """_write не делает ничего."""
        exporter = RawExporter()
        # Должен отработать без ошибок
        exporter._write([{"test": "data"}], "/some/path")


class TestCompactOutput:
    """Тесты компактного вывода."""

    def test_compact_no_newlines(self):
        """indent=None даёт компактный JSON."""
        exporter = RawExporter(indent=None)
        data = [{"a": 1, "b": 2}]

        with patch("builtins.print") as mock_print:
            exporter.export(data)

        output = mock_print.call_args[0][0]
        # Компактный JSON - без переносов строк внутри
        assert "\n" not in output

    def test_pretty_has_newlines(self):
        """indent=2 форматирует с отступами."""
        exporter = RawExporter(indent=2)
        data = [{"a": 1, "b": 2}]

        with patch("builtins.print") as mock_print:
            exporter.export(data)

        output = mock_print.call_args[0][0]
        # С форматированием есть переносы строк
        assert "\n" in output
