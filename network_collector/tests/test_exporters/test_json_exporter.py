"""
Integration tests для JSON экспортера.

Проверяет что файлы создаются и содержат корректные данные.
"""

import json
import pytest
from datetime import datetime

from network_collector.exporters import JSONExporter


class TestJSONExporterIntegration:
    """Integration tests для JSONExporter."""

    @pytest.fixture
    def sample_data(self):
        """Тестовые данные."""
        return [
            {"hostname": "switch-01", "ip": "10.0.0.1", "mac": "00:11:22:33:44:55", "vlan": 10},
            {"hostname": "switch-01", "ip": "10.0.0.1", "mac": "aa:bb:cc:dd:ee:ff", "vlan": 20},
            {"hostname": "switch-02", "ip": "10.0.0.2", "mac": "11:22:33:44:55:66", "vlan": 10},
        ]

    def test_json_file_created(self, tmp_path, sample_data):
        """Файл JSON создаётся."""
        exporter = JSONExporter(output_folder=str(tmp_path))
        result = exporter.export(sample_data, "test_export.json")

        assert result is not None
        assert result.exists()
        assert result.suffix == ".json"

    def test_json_is_valid(self, tmp_path, sample_data):
        """JSON файл валидный."""
        exporter = JSONExporter(output_folder=str(tmp_path))
        result = exporter.export(sample_data, "test.json")

        with open(result, "r", encoding="utf-8") as f:
            data = json.load(f)  # Не должно выбросить исключение

        assert data is not None

    def test_json_has_metadata(self, tmp_path, sample_data):
        """JSON содержит метаданные."""
        exporter = JSONExporter(output_folder=str(tmp_path), include_metadata=True)
        result = exporter.export(sample_data, "with_meta.json")

        with open(result, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert "metadata" in data
        assert "data" in data
        assert "generated_at" in data["metadata"]
        assert "total_records" in data["metadata"]
        assert data["metadata"]["total_records"] == 3

    def test_json_without_metadata(self, tmp_path, sample_data):
        """JSON без метаданных - только массив данных."""
        exporter = JSONExporter(output_folder=str(tmp_path), include_metadata=False)
        result = exporter.export(sample_data, "no_meta.json")

        with open(result, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Должен быть просто список
        assert isinstance(data, list)
        assert len(data) == 3

    def test_json_data_integrity(self, tmp_path, sample_data):
        """Данные в JSON соответствуют исходным."""
        exporter = JSONExporter(output_folder=str(tmp_path), include_metadata=True)
        result = exporter.export(sample_data, "test.json")

        with open(result, "r", encoding="utf-8") as f:
            parsed = json.load(f)

        data = parsed["data"]
        assert data[0]["hostname"] == "switch-01"
        assert data[0]["mac"] == "00:11:22:33:44:55"
        assert data[0]["vlan"] == 10
        assert data[2]["hostname"] == "switch-02"

    def test_json_formatted_with_indent(self, tmp_path, sample_data):
        """JSON форматирован с отступами."""
        exporter = JSONExporter(output_folder=str(tmp_path), indent=4)
        result = exporter.export(sample_data, "formatted.json")

        with open(result, "r", encoding="utf-8") as f:
            content = f.read()

        # Форматированный JSON содержит переносы строк
        assert "\n" in content
        # И отступы
        assert "    " in content

    def test_json_compact_no_indent(self, tmp_path, sample_data):
        """Компактный JSON без отступов."""
        exporter = JSONExporter(output_folder=str(tmp_path), indent=None)
        result = exporter.export(sample_data, "compact.json")

        with open(result, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # Компактный JSON - одна строка
        assert len(lines) == 1

    def test_json_empty_data_returns_none(self, tmp_path):
        """Пустые данные возвращают None."""
        exporter = JSONExporter(output_folder=str(tmp_path))
        result = exporter.export([], "empty.json")

        assert result is None

    def test_json_cyrillic_content(self, tmp_path):
        """Кириллица корректно записывается."""
        data = [
            {"hostname": "коммутатор-01", "description": "Серверная стойка"},
            {"hostname": "маршрутизатор-01", "description": "Ядро сети"},
        ]

        exporter = JSONExporter(output_folder=str(tmp_path), ensure_ascii=False)
        result = exporter.export(data, "cyrillic.json")

        with open(result, "r", encoding="utf-8") as f:
            content = f.read()

        # Кириллица должна быть читаемой, а не escaped
        assert "коммутатор-01" in content
        assert "\\u" not in content  # Не должно быть Unicode escape

    def test_json_ensure_ascii(self, tmp_path):
        """ensure_ascii экранирует Unicode."""
        data = [{"name": "коммутатор"}]

        exporter = JSONExporter(output_folder=str(tmp_path), ensure_ascii=True)
        result = exporter.export(data, "ascii.json")

        with open(result, "r", encoding="utf-8") as f:
            content = f.read()

        # Unicode должен быть escaped
        assert "\\u" in content

    def test_json_column_filter(self, tmp_path, sample_data):
        """Экспорт только выбранных колонок."""
        exporter = JSONExporter(output_folder=str(tmp_path), include_metadata=False)
        result = exporter.export(sample_data, "filtered.json", columns=["hostname", "mac"])

        with open(result, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Только 2 колонки
        assert set(data[0].keys()) == {"hostname", "mac"}

    def test_json_sorted_keys(self, tmp_path, sample_data):
        """Ключи отсортированы."""
        exporter = JSONExporter(output_folder=str(tmp_path), sort_keys=True, include_metadata=False)
        result = exporter.export(sample_data, "sorted.json")

        with open(result, "r", encoding="utf-8") as f:
            content = f.read()

        # hostname должен быть перед ip, ip перед mac, mac перед vlan
        hostname_pos = content.find('"hostname"')
        ip_pos = content.find('"ip"')
        mac_pos = content.find('"mac"')
        vlan_pos = content.find('"vlan"')

        assert hostname_pos < ip_pos < mac_pos < vlan_pos

    def test_json_metadata_columns(self, tmp_path, sample_data):
        """Метаданные содержат список колонок."""
        exporter = JSONExporter(output_folder=str(tmp_path), include_metadata=True)
        result = exporter.export(sample_data, "test.json")

        with open(result, "r", encoding="utf-8") as f:
            data = json.load(f)

        columns = data["metadata"]["columns"]
        assert "hostname" in columns
        assert "ip" in columns
        assert "mac" in columns
        assert "vlan" in columns

    def test_json_datetime_serialization(self, tmp_path):
        """datetime сериализуется в ISO формат."""
        now = datetime(2025, 12, 28, 10, 30, 0)
        data = [{"timestamp": now, "event": "test"}]

        exporter = JSONExporter(output_folder=str(tmp_path), include_metadata=False)
        result = exporter.export(data, "datetime.json")

        with open(result, "r", encoding="utf-8") as f:
            parsed = json.load(f)

        assert parsed[0]["timestamp"] == "2025-12-28T10:30:00"
