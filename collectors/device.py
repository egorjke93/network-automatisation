"""
Коллектор информации об устройствах.

Собирает инвентаризационные данные с сетевых устройств:
- Hostname
- Модель (hardware)
- Серийный номер
- Версия ПО
- Uptime

Использует Scrapli для подключения и NTC Templates для парсинга.

Пример использования:
    collector = DeviceCollector()
    data = collector.collect(devices)

    # С указанием полей для CSV
    collector = DeviceCollector(csv_fields=["name", "model", "serial"])
"""

import logging
from typing import List, Dict, Any, Optional, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

from scrapli import Scrapli
from ntc_templates.parse import parse_output

from ..core.device import Device, DeviceStatus
from ..core.connection import ConnectionManager, get_ntc_platform, get_scrapli_platform
from ..core.credentials import Credentials
from ..core.constants import normalize_device_model
from ..core.exceptions import (
    CollectorError,
    ConnectionError,
    AuthenticationError,
    TimeoutError,
    format_error_for_log,
)

logger = logging.getLogger(__name__)


# Маппинг полей устройства → CSV
DEFAULT_DEVICE_FIELDS = {
    "hostname": "hostname",
    "hardware": "model",
    "serial": "serial",
    "version": "version",
    "uptime": "uptime",
}

# Дополнительные поля со статическими значениями или функциями
# manufacturer определяется динамически из device.vendor
DEFAULT_EXTRA_FIELDS = {
    "status": "active",
    "u_height": "1",
}


class DeviceCollector:
    """
    Коллектор инвентаризационных данных устройств.

    Собирает информацию через команду show version и другие
    команды для получения полных данных об устройстве.

    Attributes:
        credentials: Учётные данные для подключения
        max_workers: Максимум параллельных подключений
        device_fields: Маппинг полей устройства → CSV
        extra_fields: Дополнительные поля

    Example:
        collector = DeviceCollector()
        data = collector.collect(devices)

        for device_data in data:
            print(f"{device_data['name']}: {device_data['model']}")
    """

    def __init__(
        self,
        credentials: Optional[Credentials] = None,
        max_workers: int = 10,
        device_fields: Optional[Dict[str, str]] = None,
        extra_fields: Optional[Dict[str, Any]] = None,
        timeout_socket: int = 15,
        timeout_transport: int = 30,
        transport: str = "ssh2",
    ):
        """
        Инициализация коллектора устройств.

        Args:
            credentials: Учётные данные (если None — запросит интерактивно)
            max_workers: Максимум параллельных подключений
            device_fields: Маппинг полей устройства → CSV
            extra_fields: Дополнительные поля (статика или функции)
            timeout_socket: Таймаут сокета
            timeout_transport: Таймаут транспорта
            transport: Тип транспорта (ssh2, paramiko, system)
        """
        self.credentials = credentials
        self.max_workers = max_workers
        self.device_fields = device_fields or DEFAULT_DEVICE_FIELDS
        self.extra_fields = extra_fields or DEFAULT_EXTRA_FIELDS
        self.timeout_socket = timeout_socket
        self.timeout_transport = timeout_transport
        self.transport = transport

        self._conn_manager = ConnectionManager(
            timeout_socket=timeout_socket,
            timeout_transport=timeout_transport,
            transport=transport,
        )

    def collect(
        self,
        devices: List[Device],
        parallel: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Собирает данные со списка устройств.

        Args:
            devices: Список устройств
            parallel: Параллельный сбор

        Returns:
            List[Dict]: Собранные данные со всех устройств
        """
        all_data = []

        if parallel and len(devices) > 1:
            all_data = self._collect_parallel(devices)
        else:
            for device in devices:
                data = self._collect_from_device(device)
                if data:
                    all_data.append(data)

        logger.info(f"Собрано устройств: {len(all_data)} из {len(devices)}")
        return all_data

    def _collect_parallel(self, devices: List[Device]) -> List[Dict[str, Any]]:
        """
        Параллельный сбор данных.

        Args:
            devices: Список устройств

        Returns:
            List[Dict]: Собранные данные
        """
        all_data = []

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self._collect_from_device, device): device
                for device in devices
            }

            for future in as_completed(futures):
                device = futures[future]
                try:
                    data = future.result()
                    if data:
                        all_data.append(data)
                except CollectorError as e:
                    logger.error(f"Ошибка сбора с {device.host}: {format_error_for_log(e)}")
                except Exception as e:
                    logger.error(f"Неизвестная ошибка с {device.host}: {e}")

        return all_data

    def _collect_from_device(self, device: Device) -> Optional[Dict[str, Any]]:
        """
        Собирает данные с одного устройства.

        Args:
            device: Устройство

        Returns:
            Dict или None: Данные устройства
        """
        data = {}

        # Добавляем IP, платформу и manufacturer
        data["ip_address"] = device.host
        data["platform"] = device.platform
        data["manufacturer"] = device.vendor.capitalize() if device.vendor else "Cisco"

        # Определяем платформы
        scrapli_platform = get_scrapli_platform(device.platform)
        ntc_platform = get_ntc_platform(device.platform)

        try:
            with self._conn_manager.connect(device, self.credentials) as conn:
                # Выполняем show version
                response = conn.send_command("show version")
                output = response.result

                # Парсим через NTC Templates
                parsed_data = parse_output(
                    platform=ntc_platform,
                    command="show version",
                    data=output
                )

                # Нормализуем результат
                if isinstance(parsed_data, list) and parsed_data:
                    parsed = parsed_data[0]
                elif isinstance(parsed_data, dict):
                    parsed = parsed_data
                else:
                    parsed = {}

                # Извлекаем поля
                for device_key, csv_key in self.device_fields.items():
                    value = self._get_parsed_value(parsed, device_key)
                    data[csv_key] = value

                # Нормализуем модель (убираем WS- и лицензии)
                if "model" in data and data["model"]:
                    data["model"] = normalize_device_model(data["model"])
                # Fallback: используем device.device_type если модель не найдена в show version
                elif device.device_type:
                    data["model"] = normalize_device_model(device.device_type)

                # Получаем hostname
                hostname = self._conn_manager.get_hostname(conn)
                data["hostname"] = hostname

                # Имя устройства (hostname или IP)
                data["name"] = hostname if hostname != "Unknown" else device.host

                logger.info(f"[SUCCESS] {device.host}: Данные получены")

        except (ConnectionError, AuthenticationError, TimeoutError) as e:
            logger.error(f"[ERROR] {device.host}: {format_error_for_log(e)}")
            # Заполняем поля ошибками
            for _, csv_key in self.device_fields.items():
                data[csv_key] = "ERROR"
            data["_error"] = format_error_for_log(e)
            data["name"] = device.host
            data["hostname"] = device.host
        except Exception as e:
            logger.error(f"[ERROR] {device.host}: неизвестная ошибка: {e}")
            for _, csv_key in self.device_fields.items():
                data[csv_key] = "ERROR"
            data["_error"] = str(e)
            data["name"] = device.host
            data["hostname"] = device.host

        # Добавляем дополнительные поля
        for csv_key, value in self.extra_fields.items():
            if callable(value):
                data[csv_key] = value(data, device)
            else:
                data[csv_key] = value

        return data

    def _get_parsed_value(self, parsed: Dict[str, Any], key: str) -> str:
        """
        Извлекает значение из распарсенных данных.

        Учитывает различные варианты названий полей.

        Args:
            parsed: Распарсенные данные
            key: Ключ для поиска

        Returns:
            str: Найденное значение
        """
        # Алиасы для разных платформ
        key_aliases = {
            "hostname": ["hostname", "host", "switchname", "chassis_id"],
            "hardware": ["hardware", "platform", "model", "chassis", "device_model"],
            "serial": ["serial", "serial_number", "sn", "chassis_sn", "serialnum"],
            "version": ["version", "software_version", "os", "kickstart_ver", "sys_ver"],
        }

        aliases = key_aliases.get(key, [key])

        for alias in aliases:
            # Пробуем разные варианты регистра
            for variant in [alias, alias.lower(), alias.upper(), alias.capitalize()]:
                val = parsed.get(variant)
                if val:
                    # Если список — берем первый элемент
                    if isinstance(val, list):
                        return val[0] if val else ""
                    if isinstance(val, str):
                        return val.strip("[]'\"")
                    return str(val)

        return ""


class DeviceInventoryCollector(DeviceCollector):
    """
    Расширенный коллектор для инвентаризации с поддержкой NetBox.

    Добавляет поля, необходимые для загрузки в NetBox:
    - role
    - site
    - tenant
    - manufacturer
    - device_type (модель)
    """

    # Стандартные поля для NetBox CSV импорта
    NETBOX_CSV_FIELDS = [
        "role",
        "manufacturer",
        "model",
        "status",
        "site",
        "name",
        "serial",
        "tenant",
        "platform",
    ]

    def __init__(
        self,
        credentials: Optional[Credentials] = None,
        site: str = "Main",
        role: str = "Switch",
        tenant: str = "",
        manufacturer: str = "Cisco",
        **kwargs,
    ):
        """
        Инициализация коллектора для NetBox.

        Args:
            credentials: Учётные данные
            site: Сайт по умолчанию
            role: Роль устройства по умолчанию
            tenant: Арендатор по умолчанию
            manufacturer: Производитель по умолчанию
            **kwargs: Дополнительные параметры для DeviceCollector
        """
        # Сохраняем дефолтные значения для использования в lambda
        default_role = role

        extra_fields = {
            "status": "active",
            "manufacturer": manufacturer,
            "site": site,
            # role из devices_ips.py имеет приоритет над CLI дефолтом
            "role": lambda data, dev: dev.role if dev.role else default_role,
            "tenant": tenant,
            "u_height": "1",
            # slug для модели (lowercase)
            "slug": lambda data, dev: str(data.get("model", "")).lower().replace(" ", "-"),
        }

        super().__init__(
            credentials=credentials,
            extra_fields=extra_fields,
            **kwargs,
        )

    def get_csv_fields(self) -> List[str]:
        """Возвращает список полей для CSV."""
        return self.NETBOX_CSV_FIELDS
