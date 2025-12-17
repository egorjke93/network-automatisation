"""
JSON экспортер.

Сохраняет данные в структурированном JSON формате.
Поддерживает форматирование для читаемости.

Пример использования:
    exporter = JSONExporter(indent=2, ensure_ascii=False)
    exporter.export(data, "report.json")
"""

import json
import logging
from pathlib import Path
from datetime import datetime, date
from typing import List, Dict, Any, Optional

from .base import BaseExporter

logger = logging.getLogger(__name__)


class JSONExporter(BaseExporter):
    """
    Экспортер данных в JSON формат.
    
    Attributes:
        indent: Отступ для форматирования (None = компактный)
        ensure_ascii: Экранировать не-ASCII символы
        include_metadata: Добавить метаданные (дата, количество записей)
        
    Example:
        # Форматированный JSON
        exporter = JSONExporter(indent=2)
        
        # Компактный JSON
        exporter = JSONExporter(indent=None)
        
        # С метаданными
        exporter = JSONExporter(include_metadata=True)
    """
    
    file_extension = ".json"
    
    def __init__(
        self,
        output_folder: str = "reports",
        encoding: str = "utf-8",
        indent: Optional[int] = 2,
        ensure_ascii: bool = False,
        include_metadata: bool = True,
        sort_keys: bool = False,
    ):
        """
        Инициализация JSON экспортера.
        
        Args:
            output_folder: Папка для сохранения
            encoding: Кодировка файла
            indent: Отступ (None для компактного вывода)
            ensure_ascii: True = экранировать Unicode
            include_metadata: Добавить метаданные в файл
            sort_keys: Сортировать ключи
        """
        super().__init__(output_folder, encoding)
        
        self.indent = indent
        self.ensure_ascii = ensure_ascii
        self.include_metadata = include_metadata
        self.sort_keys = sort_keys
    
    def _write(self, data: List[Dict[str, Any]], file_path: Path) -> None:
        """
        Записывает данные в JSON файл.
        
        Args:
            data: Данные для записи
            file_path: Путь к файлу
        """
        # Формируем структуру
        if self.include_metadata:
            output = {
                "metadata": {
                    "generated_at": datetime.now().isoformat(),
                    "total_records": len(data),
                    "columns": self._get_all_columns(data),
                },
                "data": data,
            }
        else:
            output = data
        
        with open(file_path, "w", encoding=self.encoding) as f:
            json.dump(
                output,
                f,
                indent=self.indent,
                ensure_ascii=self.ensure_ascii,
                sort_keys=self.sort_keys,
                default=self._json_serializer,
            )
        
        logger.debug(f"JSON записан: {len(data)} записей")
    
    @staticmethod
    def _json_serializer(obj: Any) -> Any:
        """
        Сериализатор для нестандартных типов данных.
        
        Обрабатывает datetime, date, set и другие типы.
        
        Args:
            obj: Объект для сериализации
            
        Returns:
            Сериализуемое значение
        """
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if isinstance(obj, set):
            return list(obj)
        if hasattr(obj, "__dict__"):
            return obj.__dict__
        
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

