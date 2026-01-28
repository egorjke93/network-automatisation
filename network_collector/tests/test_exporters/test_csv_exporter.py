"""
Integration tests для CSV экспортера.

Проверяет что файлы создаются и содержат корректные данные.
"""

import csv
import pytest
from pathlib import Path

from network_collector.exporters import CSVExporter


class TestCSVExporterIntegration:
    """Integration tests для CSVExporter."""

    @pytest.fixture
    def sample_data(self):
        """Тестовые данные."""
        return [
            {"hostname": "switch-01", "ip": "10.0.0.1", "mac": "00:11:22:33:44:55", "vlan": 10},
            {"hostname": "switch-01", "ip": "10.0.0.1", "mac": "aa:bb:cc:dd:ee:ff", "vlan": 20},
            {"hostname": "switch-02", "ip": "10.0.0.2", "mac": "11:22:33:44:55:66", "vlan": 10},
        ]

    def test_csv_file_created(self, tmp_path, sample_data):
        """Файл CSV создаётся."""
        exporter = CSVExporter(output_folder=str(tmp_path))
        result = exporter.export(sample_data, "test_export.csv")

        assert result is not None
        assert result.exists()
        assert result.suffix == ".csv"

    def test_csv_has_header(self, tmp_path, sample_data):
        """CSV содержит заголовок."""
        exporter = CSVExporter(output_folder=str(tmp_path))
        result = exporter.export(sample_data, "test.csv")

        with open(result, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader)

        assert "hostname" in header
        assert "ip" in header
        assert "mac" in header
        assert "vlan" in header

    def test_csv_has_correct_row_count(self, tmp_path, sample_data):
        """CSV содержит все строки данных."""
        exporter = CSVExporter(output_folder=str(tmp_path))
        result = exporter.export(sample_data, "test.csv")

        with open(result, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)

        # 1 header + 3 data rows
        assert len(rows) == 4

    def test_csv_data_integrity(self, tmp_path, sample_data):
        """Данные в CSV соответствуют исходным."""
        exporter = CSVExporter(output_folder=str(tmp_path))
        result = exporter.export(sample_data, "test.csv")

        with open(result, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert rows[0]["hostname"] == "switch-01"
        assert rows[0]["mac"] == "00:11:22:33:44:55"
        assert rows[2]["hostname"] == "switch-02"

    def test_csv_semicolon_delimiter(self, tmp_path, sample_data):
        """CSV с разделителем точка с запятой."""
        exporter = CSVExporter(output_folder=str(tmp_path), delimiter=";")
        result = exporter.export(sample_data, "test.csv")

        with open(result, "r", encoding="utf-8") as f:
            content = f.read()

        assert ";" in content
        assert "hostname;ip;mac;vlan" in content or "hostname;mac;ip;vlan" in content

    def test_csv_for_excel_factory(self, tmp_path, sample_data):
        """Фабрика for_excel создаёт правильный экспортер."""
        exporter = CSVExporter.for_excel(output_folder=str(tmp_path))
        result = exporter.export(sample_data, "excel_compat.csv")

        assert result.exists()

        # Проверяем BOM (UTF-8-sig начинается с EF BB BF)
        with open(result, "rb") as f:
            bom = f.read(3)

        assert bom == b"\xef\xbb\xbf", "Файл должен содержать UTF-8 BOM"

    def test_csv_without_header(self, tmp_path, sample_data):
        """CSV без заголовка."""
        exporter = CSVExporter(output_folder=str(tmp_path), include_header=False)
        result = exporter.export(sample_data, "no_header.csv")

        with open(result, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)

        # Только 3 data rows, без header
        assert len(rows) == 3
        # Первая строка - данные, не заголовок
        assert "switch-01" in rows[0]

    def test_csv_column_filter(self, tmp_path, sample_data):
        """Экспорт только выбранных колонок."""
        exporter = CSVExporter(output_folder=str(tmp_path))
        result = exporter.export(sample_data, "filtered.csv", columns=["hostname", "mac"])

        with open(result, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        # Только 2 колонки
        assert set(rows[0].keys()) == {"hostname", "mac"}

    def test_csv_empty_data_returns_none(self, tmp_path):
        """Пустые данные возвращают None."""
        exporter = CSVExporter(output_folder=str(tmp_path))
        result = exporter.export([], "empty.csv")

        assert result is None

    def test_csv_cyrillic_content(self, tmp_path):
        """Кириллица корректно записывается."""
        data = [
            {"hostname": "коммутатор-01", "description": "Серверная стойка"},
            {"hostname": "маршрутизатор-01", "description": "Ядро сети"},
        ]

        exporter = CSVExporter(output_folder=str(tmp_path))
        result = exporter.export(data, "cyrillic.csv")

        with open(result, "r", encoding="utf-8") as f:
            content = f.read()

        assert "коммутатор-01" in content
        assert "Серверная стойка" in content

    def test_csv_special_characters(self, tmp_path):
        """Спецсимволы корректно экранируются."""
        data = [
            {"description": 'Value with "quotes"'},
            {"description": "Value with, comma"},
            {"description": "Value with\nnewline"},
        ]

        exporter = CSVExporter(output_folder=str(tmp_path))
        result = exporter.export(data, "special.csv")

        with open(result, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert rows[0]["description"] == 'Value with "quotes"'
        assert rows[1]["description"] == "Value with, comma"
