"""
Raw экспортер.

Выводит данные в JSON формате напрямую в stdout.
Без метаданных, без сохранения в файл.

Пример использования:
    exporter = RawExporter()
    exporter.export(data, "ignored_name")  # Выведет JSON в stdout
"""

import json
import sys
from datetime import datetime, date
from typing import List, Dict, Any, Optional
from pathlib import Path

from .base import BaseExporter


class RawExporter(BaseExporter):
    """
    Экспортер данных в stdout (raw JSON).

    Выводит данные как чистый JSON без обёрток и метаданных.
    Полезно для pipeline обработки и интеграции с другими инструментами.

    Example:
        exporter = RawExporter()
        exporter.export(data, "any_name")  # -> stdout

        # В командной строке:
        # python -m network_collector devices --format raw | jq '.[] | .hostname'
    """

    file_extension = ""  # Не сохраняем в файл

    def __init__(
        self,
        output_folder: str = "",
        encoding: str = "utf-8",
        indent: Optional[int] = 2,
    ):
        """
        Инициализация raw экспортера.

        Args:
            output_folder: Игнорируется (вывод в stdout)
            encoding: Кодировка (по умолчанию utf-8)
            indent: Отступ JSON (2 для читаемости, None для компактного)
        """
        super().__init__(output_folder, encoding)
        self.indent = indent

    def export(
        self,
        data: List[Dict[str, Any]],
        filename: str = "",
        **kwargs,
    ) -> Optional[str]:
        """
        Выводит данные в stdout как JSON.

        Args:
            data: Данные для вывода
            filename: Игнорируется
            **kwargs: Игнорируются

        Returns:
            None (вывод в stdout)
        """
        if not data:
            print("[]")
            return None

        json_str = json.dumps(
            data,
            indent=self.indent,
            ensure_ascii=False,
            default=self._json_serializer,
        )
        print(json_str)
        return None

    def _write(self, data: List[Dict[str, Any]], file_path: Path) -> None:
        """Не используется - переопределён export()."""
        pass

    @staticmethod
    def _json_serializer(obj: Any) -> Any:
        """Сериализатор для нестандартных типов."""
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if isinstance(obj, set):
            return list(obj)
        if hasattr(obj, "__dict__"):
            return obj.__dict__
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")
