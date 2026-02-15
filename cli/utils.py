"""
Утилиты CLI.

Общие функции для всех команд CLI.
"""

import sys
import logging
from pathlib import Path
from typing import List, Tuple

from ..core.constants.platforms import DEFAULT_PLATFORM

logger = logging.getLogger(__name__)


def load_devices(devices_file: str) -> List:
    """
    Загружает список устройств из файла.

    Args:
        devices_file: Путь к файлу с устройствами

    Returns:
        List: Список устройств

    Raises:
        SystemExit: Если файл не найден или содержит ошибки
    """
    from ..core.device import Device

    devices_path = Path(devices_file)

    # Если не найден — ищем в директории модуля
    if not devices_path.exists():
        module_dir = Path(__file__).parent.parent
        devices_path = module_dir / devices_file

    if not devices_path.exists():
        logger.error(f"Файл устройств не найден: {devices_file}")
        sys.exit(1)

    # Импортируем devices_list из файла
    import importlib.util

    try:
        spec = importlib.util.spec_from_file_location("devices", devices_path)
        if spec is None or spec.loader is None:
            logger.error(f"Не удалось загрузить спецификацию модуля: {devices_path}")
            sys.exit(1)

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except SyntaxError as e:
        logger.error(f"Синтаксическая ошибка в файле {devices_path}: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Ошибка загрузки файла {devices_path}: {e}")
        sys.exit(1)

    devices_list = getattr(module, "devices_list", None)

    if devices_list is None:
        logger.error(f"Переменная 'devices_list' не найдена в {devices_path}")
        sys.exit(1)

    if not isinstance(devices_list, list):
        logger.error(f"'devices_list' должен быть списком, получен {type(devices_list).__name__}")
        sys.exit(1)

    # Преобразуем в объекты Device
    devices = []
    for idx, d in enumerate(devices_list):
        if not isinstance(d, dict):
            logger.warning(f"Пропущен элемент #{idx}: ожидался dict, получен {type(d).__name__}")
            continue

        host = d.get("host")
        if not host:
            logger.warning(f"Пропущен элемент #{idx}: отсутствует 'host'")
            continue

        # Новый формат (рекомендуется):
        # {"host": "10.0.0.1", "platform": "cisco_iosxe", "device_type": "C9200L-24P-4X", "role": "Switch"}
        platform = d.get("platform")
        device_type = d.get("device_type")
        role = d.get("role")

        # Backward compatibility: если platform не указан, используем device_type
        # (в Device.__post_init__ есть логика конвертации device_type → platform)
        if not platform and not device_type:
            logger.warning(f"Устройство {host}: ни 'platform' ни 'device_type' не указаны, используется '{DEFAULT_PLATFORM}'")
            platform = DEFAULT_PLATFORM

        devices.append(
            Device(
                host=host,
                platform=platform,
                device_type=device_type,
                role=role,
                site=d.get("site"),
            )
        )

    if not devices:
        logger.error("Список устройств пуст или все записи некорректны")
        sys.exit(1)

    logger.info(f"Загружено устройств: {len(devices)}")
    return devices


def get_exporter(format_type: str, output_folder: str, delimiter: str = ","):
    """
    Возвращает экспортер по типу формата.

    Args:
        format_type: Тип формата (excel, csv, json, raw)
        output_folder: Папка для вывода
        delimiter: Разделитель для CSV

    Returns:
        BaseExporter: Экспортер
    """
    from ..exporters import CSVExporter, JSONExporter, ExcelExporter, RawExporter

    if format_type == "csv":
        return CSVExporter(output_folder=output_folder, delimiter=delimiter)
    elif format_type == "json":
        return JSONExporter(output_folder=output_folder)
    elif format_type == "raw":
        return RawExporter()
    else:
        return ExcelExporter(output_folder=output_folder)


def get_credentials():
    """
    Получает учётные данные для подключения.

    Returns:
        Credentials: Объект с учётными данными
    """
    from ..core.credentials import CredentialsManager

    creds_manager = CredentialsManager()
    return creds_manager.get_credentials()


def prepare_collection(args) -> Tuple[List, object]:
    """
    Подготавливает устройства и credentials для сбора данных.

    Args:
        args: Аргументы командной строки

    Returns:
        tuple: (devices, credentials)
    """
    devices = load_devices(args.devices)
    credentials = get_credentials()
    return devices, credentials
