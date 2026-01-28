"""
Модули экспорта данных.

Поддерживаемые форматы:
- Excel (.xlsx) - с форматированием, цветами, фильтрами
- CSV (.csv) - с настраиваемым разделителем
- JSON (.json) - структурированные данные
- Raw (stdout) - JSON в stdout для pipeline

Пример использования:
    from network_collector.exporters import CSVExporter, ExcelExporter, RawExporter

    # CSV с точкой с запятой
    exporter = CSVExporter(delimiter=";")
    exporter.export(data, "report.csv")

    # Excel с автофильтром
    exporter = ExcelExporter(autofilter=True)
    exporter.export(data, "report.xlsx")

    # Raw JSON в stdout
    exporter = RawExporter()
    exporter.export(data, "ignored")  # -> stdout
"""

from .base import BaseExporter
from .csv_exporter import CSVExporter
from .json_exporter import JSONExporter
from .excel import ExcelExporter
from .raw_exporter import RawExporter

__all__ = ["BaseExporter", "CSVExporter", "JSONExporter", "ExcelExporter", "RawExporter"]

