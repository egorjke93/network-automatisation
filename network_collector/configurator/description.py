"""
Модуль для сопоставления MAC-адресов и установки описаний интерфейсов.

Рабочий процесс:
1. Собираем MAC-адреса с устройств (MACCollector)
2. Сопоставляем с таблицей хостов (DescriptionMatcher)
3. Генерируем команды для описаний
4. Применяем на устройствах (DescriptionPusher)

Пример использования:
    # Шаг 1: Сопоставление
    matcher = DescriptionMatcher()
    matcher.load_hosts_file("glpi_hosts.xlsx", mac_column="MAC", name_column="Name")
    matched = matcher.match_mac_data(mac_data)
    matcher.save_matched("matched_data.xlsx")

    # Шаг 2: Генерация команд
    commands = matcher.generate_description_commands()

    # Шаг 3: Применение
    pusher = DescriptionPusher(credentials)
    results = pusher.push_descriptions(devices, commands, dry_run=True)
"""

import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass, field

from .base import ConfigPusher, ConfigResult
from ..core.device import Device
from ..core.credentials import Credentials

logger = logging.getLogger(__name__)

# Опционально: pandas для работы с Excel
try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False


def normalize_mac(mac: str) -> str:
    """
    Нормализует MAC-адрес для сравнения.

    Args:
        mac: MAC-адрес в любом формате

    Returns:
        str: Нормализованный MAC (12 символов, нижний регистр)
    """
    if not mac:
        return ""
    if PANDAS_AVAILABLE and pd.isna(mac):
        return ""

    mac_str = str(mac).strip().lower()
    for char in [" ", ":", "-", "."]:
        mac_str = mac_str.replace(char, "")

    return mac_str


@dataclass
class MatchedEntry:
    """Запись сопоставления MAC с хостом."""
    hostname: str  # Hostname устройства (коммутатора)
    device_ip: str  # IP устройства
    interface: str  # Интерфейс
    mac: str  # MAC-адрес
    vlan: str = ""  # VLAN
    host_name: str = ""  # Имя хоста (ПК) для description
    current_description: str = ""  # Текущее описание
    matched: bool = False  # Найдено соответствие


class DescriptionMatcher:
    """
    Сопоставление MAC-адресов с таблицей хостов.

    Загружает справочные данные о хостах (имена ПК, пользователи)
    и сопоставляет их с MAC-адресами, собранными с коммутаторов.

    Attributes:
        reference_data: {normalized_mac: {name: ..., user: ..., ...}}
        matched_data: Список сопоставленных записей

    Example:
        matcher = DescriptionMatcher()

        # Загружаем справочник хостов
        matcher.load_hosts_file("glpi_hosts.xlsx")

        # Сопоставляем с данными MAC
        matched = matcher.match_mac_data(mac_data)

        # Сохраняем результат
        matcher.save_matched("result.xlsx")

        # Генерируем команды
        commands = matcher.generate_description_commands()
    """

    def __init__(self):
        """Инициализация матчера."""
        if not PANDAS_AVAILABLE:
            raise ImportError(
                "pandas не установлен. Установите: pip install pandas openpyxl"
            )

        # Справочные данные: {normalized_mac: {field: value}}
        self.reference_data: Dict[str, Dict[str, Any]] = {}

        # Сопоставленные данные
        self.matched_data: List[MatchedEntry] = []

        # Статистика
        self._loaded_files: List[str] = []
        self._total_matched = 0

    def load_hosts_file(
        self,
        file_path: str,
        mac_column: str = "MAC",
        name_column: str = "Name",
        additional_columns: Optional[List[str]] = None,
        sheet_name: Optional[str] = None,
    ) -> int:
        """
        Загружает справочник хостов из Excel файла.

        Args:
            file_path: Путь к Excel файлу
            mac_column: Название колонки с MAC-адресами
            name_column: Название колонки с именем хоста (для description)
            additional_columns: Дополнительные колонки для извлечения
            sheet_name: Имя листа (None = первый)

        Returns:
            int: Количество загруженных записей
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Файл не найден: {file_path}")

        try:
            if sheet_name:
                df = pd.read_excel(path, sheet_name=sheet_name)
            else:
                df = pd.read_excel(path)
        except Exception as e:
            logger.error(f"Ошибка чтения файла {file_path}: {e}")
            raise

        # Ищем колонку с MAC
        mac_col = self._find_column(df, mac_column)
        if not mac_col:
            raise ValueError(
                f"Колонка '{mac_column}' не найдена. Доступные: {list(df.columns)}"
            )

        # Ищем колонку с именем
        name_col = self._find_column(df, name_column)
        if not name_col:
            logger.warning(f"Колонка '{name_column}' не найдена, используем MAC как имя")

        # Определяем дополнительные колонки
        extra_cols = []
        if additional_columns:
            for col in additional_columns:
                found = self._find_column(df, col)
                if found:
                    extra_cols.append(found)

        # Загружаем данные
        count = 0
        for _, row in df.iterrows():
            raw_mac = row[mac_col]
            if pd.isna(raw_mac):
                continue

            # Разбиваем ячейку с несколькими MAC (разделители: \n, ;, ,)
            mac_list = str(raw_mac).replace(';', '\n').replace(',', '\n').split('\n')
            mac_list = [normalize_mac(m) for m in mac_list if normalize_mac(m)]

            if not mac_list:
                continue

            data = {"_source_file": path.name}

            # Имя хоста
            if name_col and pd.notna(row[name_col]):
                data["name"] = str(row[name_col]).strip()
            else:
                data["name"] = ""

            # Дополнительные колонки
            for col in extra_cols:
                if pd.notna(row[col]):
                    data[col] = str(row[col]).strip()

            # Добавляем каждый MAC из ячейки
            if data.get("name"):  # Только если есть имя
                for mac in mac_list:
                    self.reference_data[mac] = data
                    count += 1

        self._loaded_files.append(str(path))
        logger.info(f"Загружено {count} хостов из {path.name}")

        return count

    def load_hosts_folder(
        self,
        folder_path: str,
        mac_column: str = "MAC",
        name_column: str = "Name",
    ) -> int:
        """
        Загружает справочники из всех Excel файлов в папке.

        Args:
            folder_path: Путь к папке
            mac_column: Колонка с MAC
            name_column: Колонка с именем

        Returns:
            int: Общее количество загруженных записей
        """
        folder = Path(folder_path)
        if not folder.exists():
            raise FileNotFoundError(f"Папка не найдена: {folder_path}")

        total = 0
        files = list(folder.glob("*.xlsx")) + list(folder.glob("*.xls"))

        for file_path in files:
            try:
                count = self.load_hosts_file(
                    str(file_path),
                    mac_column=mac_column,
                    name_column=name_column,
                )
                total += count
            except Exception as e:
                logger.warning(f"Ошибка загрузки {file_path}: {e}")

        return total

    def match_mac_data(
        self,
        mac_data: List[Dict[str, Any]],
        mac_field: str = "mac",
        hostname_field: str = "hostname",
        interface_field: str = "interface",
        vlan_field: str = "vlan",
        description_field: str = "description",
    ) -> List[MatchedEntry]:
        """
        Сопоставляет данные MAC со справочником хостов.

        Args:
            mac_data: Данные MAC (от MACCollector)
            mac_field: Поле с MAC-адресом
            hostname_field: Поле с hostname устройства
            interface_field: Поле с интерфейсом
            vlan_field: Поле с VLAN
            description_field: Поле с текущим описанием

        Returns:
            List[MatchedEntry]: Сопоставленные записи
        """
        self.matched_data = []
        self._total_matched = 0

        for row in mac_data:
            mac = row.get(mac_field, "")
            normalized_mac = normalize_mac(mac)

            entry = MatchedEntry(
                hostname=row.get(hostname_field, ""),
                device_ip=row.get("device_ip", ""),
                interface=row.get(interface_field, ""),
                mac=mac,
                vlan=str(row.get(vlan_field, "")),
                current_description=row.get(description_field, ""),
            )

            # Ищем в справочнике
            if normalized_mac in self.reference_data:
                ref = self.reference_data[normalized_mac]
                entry.host_name = ref.get("name", "")
                entry.matched = True
                self._total_matched += 1

            self.matched_data.append(entry)

        logger.info(
            f"Сопоставлено {self._total_matched} из {len(self.matched_data)} записей"
        )

        return self.matched_data

    def save_matched(
        self,
        output_file: str,
        include_unmatched: bool = True,
    ) -> str:
        """
        Сохраняет результаты сопоставления в Excel.

        Args:
            output_file: Путь к выходному файлу
            include_unmatched: Включать несопоставленные записи

        Returns:
            str: Путь к сохранённому файлу
        """
        if not self.matched_data:
            raise ValueError("Нет данных для сохранения. Сначала вызовите match_mac_data()")

        data = []
        for entry in self.matched_data:
            if not include_unmatched and not entry.matched:
                continue

            data.append({
                "Device": entry.hostname,
                "IP": entry.device_ip,
                "Interface": entry.interface,
                "MAC": entry.mac,
                "VLAN": entry.vlan,
                "Current_Description": entry.current_description,
                "Host_Name": entry.host_name,
                "Matched": "Yes" if entry.matched else "No",
            })

        df = pd.DataFrame(data)
        df.to_excel(output_file, index=False)

        logger.info(f"Результаты сохранены: {output_file}")
        return output_file

    def generate_description_commands(
        self,
        only_empty: bool = False,
        overwrite: bool = False,
    ) -> Dict[str, List[str]]:
        """
        Генерирует команды для установки описаний интерфейсов.

        Args:
            only_empty: Только для портов без текущего описания
            overwrite: Перезаписывать существующие описания

        Returns:
            Dict: {hostname: [команды]}
        """
        commands: Dict[str, List[str]] = {}

        for entry in self.matched_data:
            # Пропускаем несопоставленные
            if not entry.matched or not entry.host_name:
                continue

            # Проверяем нужно ли обновлять
            if only_empty and entry.current_description:
                continue

            if not overwrite and entry.current_description:
                continue

            # Добавляем команды для устройства
            hostname = entry.hostname
            if hostname not in commands:
                commands[hostname] = []

            commands[hostname].append(f"interface {entry.interface}")
            commands[hostname].append(f"description {entry.host_name}")

        logger.info(
            f"Сгенерировано команд для {len(commands)} устройств"
        )

        return commands

    def get_stats(self) -> Dict[str, Any]:
        """
        Возвращает статистику сопоставления.

        Returns:
            Dict: Статистика
        """
        return {
            "reference_hosts": len(self.reference_data),
            "loaded_files": self._loaded_files,
            "total_mac_entries": len(self.matched_data),
            "matched": self._total_matched,
            "unmatched": len(self.matched_data) - self._total_matched,
            "match_rate": f"{(self._total_matched / len(self.matched_data) * 100):.1f}%"
            if self.matched_data else "0%",
        }

    def _find_column(self, df: pd.DataFrame, column_name: str) -> Optional[str]:
        """Находит колонку с учётом регистра."""
        for col in df.columns:
            if col.lower() == column_name.lower():
                return col
        return None


class DescriptionPusher(ConfigPusher):
    """
    Применение описаний интерфейсов на устройствах.

    Наследуется от ConfigPusher и добавляет удобные методы
    для работы с описаниями.

    Example:
        pusher = DescriptionPusher(credentials)

        # Применить из результатов сопоставления
        commands = matcher.generate_description_commands()
        results = pusher.push_descriptions(devices, commands, dry_run=True)

        # Или напрямую
        results = pusher.push_interface_description(
            device, "Gi0/1", "Server-01", dry_run=True
        )
    """

    def push_descriptions(
        self,
        devices: List[Device],
        commands: Dict[str, List[str]],
        dry_run: bool = True,
    ) -> List[ConfigResult]:
        """
        Применяет описания интерфейсов на устройствах.

        Args:
            devices: Список устройств
            commands: {hostname: [команды]} от DescriptionMatcher
            dry_run: Режим симуляции

        Returns:
            List[ConfigResult]: Результаты применения
        """
        results = []

        # Создаём маппинг по hostname и IP
        device_map: Dict[str, Device] = {}
        for dev in devices:
            device_map[dev.host] = dev
            if dev.metadata.get("hostname"):
                device_map[dev.metadata["hostname"]] = dev

        # Применяем команды
        for hostname, cmds in commands.items():
            device = device_map.get(hostname)

            if not device:
                logger.warning(f"Устройство {hostname} не найдено в списке")
                continue

            result = self.push_config(device, cmds, dry_run=dry_run)
            results.append(result)

        # Статистика
        success = sum(1 for r in results if r.success)
        logger.info(
            f"Применено на {success}/{len(results)} устройствах"
            + (" [DRY RUN]" if dry_run else "")
        )

        return results

    def push_interface_description(
        self,
        device: Device,
        interface: str,
        description: str,
        dry_run: bool = True,
    ) -> ConfigResult:
        """
        Устанавливает описание на одном интерфейсе.

        Args:
            device: Устройство
            interface: Интерфейс (например, "Gi0/1")
            description: Описание для установки
            dry_run: Режим симуляции

        Returns:
            ConfigResult: Результат
        """
        commands = [
            f"interface {interface}",
            f"description {description}",
        ]

        return self.push_config(device, commands, dry_run=dry_run)
