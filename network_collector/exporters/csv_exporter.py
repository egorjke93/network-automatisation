"""
CSV экспортер с настраиваемыми параметрами.

Поддерживает:
- Выбор разделителя (запятая, точка с запятой, табуляция)
- Выбор символа кавычек
- Кодировку файла
- BOM для Excel совместимости

Пример использования:
    exporter = CSVExporter(
        delimiter=";",
        quotechar='"',
        encoding="utf-8-sig"  # с BOM для Excel
    )
    exporter.export(data, "report.csv")
"""

import csv
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

from .base import BaseExporter

logger = logging.getLogger(__name__)


class CSVExporter(BaseExporter):
    """
    Экспортер данных в CSV формат.
    
    Позволяет гибко настроить формат CSV файла для совместимости
    с различными программами (Excel, LibreOffice, etc.)
    
    Attributes:
        delimiter: Разделитель полей
        quotechar: Символ кавычек
        quoting: Режим кавычек (csv.QUOTE_MINIMAL, etc.)
        include_header: Включить заголовок
        
    Example:
        # Для Excel (русская локаль)
        exporter = CSVExporter(delimiter=";", encoding="utf-8-sig")
        
        # Для Unix/Linux
        exporter = CSVExporter(delimiter=",", encoding="utf-8")
        
        # TSV (табуляция)
        exporter = CSVExporter(delimiter="\\t")
    """
    
    file_extension = ".csv"
    
    # Предустановленные разделители
    DELIMITERS = {
        "comma": ",",
        "semicolon": ";",
        "tab": "\t",
        "pipe": "|",
    }
    
    def __init__(
        self,
        output_folder: str = "reports",
        encoding: str = "utf-8",
        delimiter: str = ",",
        quotechar: str = '"',
        quoting: int = csv.QUOTE_MINIMAL,
        include_header: bool = True,
        add_bom: bool = False,
    ):
        """
        Инициализация CSV экспортера.
        
        Args:
            output_folder: Папка для сохранения
            encoding: Кодировка файла
            delimiter: Разделитель (или имя: comma, semicolon, tab, pipe)
            quotechar: Символ кавычек
            quoting: Режим кавычек (csv.QUOTE_MINIMAL, QUOTE_ALL, etc.)
            include_header: Добавлять строку заголовка
            add_bom: Добавить BOM для Excel совместимости
        """
        # Если add_bom=True, используем utf-8-sig
        if add_bom and encoding == "utf-8":
            encoding = "utf-8-sig"
        
        super().__init__(output_folder, encoding)
        
        # Преобразуем имя разделителя в символ
        self.delimiter = self.DELIMITERS.get(delimiter, delimiter)
        self.quotechar = quotechar
        self.quoting = quoting
        self.include_header = include_header
    
    def _write(self, data: List[Dict[str, Any]], file_path: Path) -> None:
        """
        Записывает данные в CSV файл.
        
        Args:
            data: Данные для записи
            file_path: Путь к файлу
        """
        # Получаем все колонки
        columns = self._get_all_columns(data)
        
        with open(file_path, "w", newline="", encoding=self.encoding) as f:
            writer = csv.DictWriter(
                f,
                fieldnames=columns,
                delimiter=self.delimiter,
                quotechar=self.quotechar,
                quoting=self.quoting,
                extrasaction="ignore",  # Игнорировать лишние ключи
            )
            
            # Заголовок
            if self.include_header:
                writer.writeheader()
            
            # Данные
            writer.writerows(data)
        
        logger.debug(
            f"CSV записан: {len(data)} строк, {len(columns)} колонок, "
            f"разделитель='{self.delimiter}'"
        )
    
    @classmethod
    def for_excel(cls, output_folder: str = "reports") -> "CSVExporter":
        """
        Фабричный метод для создания экспортера, совместимого с Excel.
        
        Excel лучше открывает CSV с:
        - Разделитель точка с запятой
        - BOM в начале файла (для корректного UTF-8)
        
        Returns:
            CSVExporter: Настроенный экспортер
        """
        return cls(
            output_folder=output_folder,
            delimiter=";",
            encoding="utf-8-sig",  # UTF-8 с BOM
            add_bom=True,
        )

