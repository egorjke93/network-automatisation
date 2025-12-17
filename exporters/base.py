"""
Базовый класс экспортера данных.

Определяет интерфейс для всех экспортеров и общую логику.
Все экспортеры должны наследоваться от BaseExporter.

Пример создания кастомного экспортера:
    class XMLExporter(BaseExporter):
        def _write(self, data, file_path):
            # Логика записи в XML
            pass
"""

import os
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional, Union

logger = logging.getLogger(__name__)


class BaseExporter(ABC):
    """
    Абстрактный базовый класс для экспортеров.
    
    Определяет общий интерфейс и логику для всех форматов экспорта.
    
    Attributes:
        output_folder: Папка для сохранения файлов
        encoding: Кодировка файлов
        
    Example:
        class MyExporter(BaseExporter):
            def _write(self, data, file_path):
                with open(file_path, 'w') as f:
                    f.write(str(data))
    """
    
    # Расширение файла (переопределяется в наследниках)
    file_extension: str = ".txt"
    
    def __init__(
        self,
        output_folder: str = "reports",
        encoding: str = "utf-8",
    ):
        """
        Инициализация экспортера.
        
        Args:
            output_folder: Папка для сохранения отчётов
            encoding: Кодировка файлов
        """
        self.output_folder = Path(output_folder)
        self.encoding = encoding
    
    def export(
        self,
        data: List[Dict[str, Any]],
        filename: Optional[str] = None,
        columns: Optional[List[str]] = None,
    ) -> Optional[Path]:
        """
        Экспортирует данные в файл.
        
        Args:
            data: Список словарей с данными
            filename: Имя файла (без пути). Если None — генерируется автоматически
            columns: Список колонок для экспорта. Если None — все колонки
            
        Returns:
            Path: Путь к созданному файлу или None при ошибке
        """
        if not data:
            logger.warning("Нет данных для экспорта")
            return None
        
        # Создаём папку если не существует
        self._ensure_output_folder()
        
        # Генерируем имя файла если не указано
        if not filename:
            filename = self._generate_filename()
        
        # Добавляем расширение если отсутствует
        if not filename.endswith(self.file_extension):
            filename += self.file_extension
        
        file_path = self.output_folder / filename
        
        # Фильтруем колонки если указаны
        if columns:
            data = self._filter_columns(data, columns)
        
        try:
            self._write(data, file_path)
            logger.info(f"Данные экспортированы: {file_path}")
            return file_path
        except Exception as e:
            logger.error(f"Ошибка экспорта в {file_path}: {e}")
            return None
    
    @abstractmethod
    def _write(self, data: List[Dict[str, Any]], file_path: Path) -> None:
        """
        Записывает данные в файл.
        
        Абстрактный метод — должен быть реализован в наследниках.
        
        Args:
            data: Данные для записи
            file_path: Путь к файлу
        """
        pass
    
    def _ensure_output_folder(self) -> None:
        """Создаёт папку для отчётов если не существует."""
        if not self.output_folder.exists():
            self.output_folder.mkdir(parents=True, exist_ok=True)
            logger.info(f"Создана папка: {self.output_folder}")
    
    def _generate_filename(self) -> str:
        """Генерирует имя файла с текущей датой."""
        date_str = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        return f"export_{date_str}"
    
    def _filter_columns(
        self,
        data: List[Dict[str, Any]],
        columns: List[str],
    ) -> List[Dict[str, Any]]:
        """
        Фильтрует данные, оставляя только указанные колонки.
        
        Args:
            data: Исходные данные
            columns: Список нужных колонок
            
        Returns:
            List[Dict]: Отфильтрованные данные
        """
        columns_lower = [c.lower() for c in columns]
        return [
            {k: v for k, v in row.items() if k.lower() in columns_lower}
            for row in data
        ]
    
    def _get_all_columns(self, data: List[Dict[str, Any]]) -> List[str]:
        """
        Извлекает все уникальные колонки из данных.
        
        Сохраняет порядок появления колонок.
        
        Args:
            data: Данные
            
        Returns:
            List[str]: Список колонок
        """
        columns = []
        seen = set()
        for row in data:
            for key in row.keys():
                if key not in seen:
                    columns.append(key)
                    seen.add(key)
        return columns

