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
    devices_info = collector.collect(devices)  # List[DeviceInfo]

    # Для экспорта в файлы
    data = collector.collect_dicts(devices)  # List[Dict]
"""

from typing import List, Dict, Any, Optional, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

# Callback для прогресса: (current_index, total, device_host, success)
ProgressCallback = Callable[[int, int, str, bool], None]

from ..parsers.textfsm_parser import NTCParser

from ..core.device import Device
from ..core.connection import ConnectionManager
from ..core.credentials import Credentials
from ..core.constants import normalize_device_model
from ..core.logging import get_logger
from ..core.models import DeviceInfo
from ..core.exceptions import (
    CollectorError,
    ConnectionError,
    AuthenticationError,
    TimeoutError,
    format_error_for_log,
)

logger = get_logger(__name__)


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
        model_class: Класс модели (DeviceInfo)

    Example:
        collector = DeviceCollector()
        devices = collector.collect(devices)  # List[DeviceInfo]

        for device in devices:
            print(f"{device.name}: {device.model}")

        # Для экспорта
        data = collector.collect_dicts(devices)  # List[Dict]
    """

    # Класс модели для типизированного вывода
    model_class = DeviceInfo

    def __init__(
        self,
        credentials: Optional[Credentials] = None,
        max_workers: int = 10,
        device_fields: Optional[Dict[str, str]] = None,
        extra_fields: Optional[Dict[str, Any]] = None,
        timeout_socket: int = 15,
        timeout_transport: int = 30,
        transport: str = "ssh2",
        max_retries: int = 2,
        retry_delay: int = 5,
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
            max_retries: Максимум повторных попыток при ошибке подключения
            retry_delay: Задержка между попытками (секунды)
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
            max_retries=max_retries,
            retry_delay=retry_delay,
        )

        self._parser = NTCParser()

        # Флаг для --format parsed: пропускает нормализацию
        self._skip_normalize = False

    def collect(
        self,
        devices: List[Device],
        parallel: bool = True,
    ) -> List[DeviceInfo]:
        """
        Собирает данные и возвращает типизированные модели.

        Args:
            devices: Список устройств
            parallel: Параллельный сбор

        Returns:
            List[DeviceInfo]: Типизированные объекты
        """
        data = self.collect_dicts(devices, parallel=parallel)
        return [self.model_class.from_dict(row) for row in data]

    def collect_dicts(
        self,
        devices: List[Device],
        parallel: bool = True,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> List[Dict[str, Any]]:
        """
        Собирает данные как словари (для экспортеров).

        Args:
            devices: Список устройств
            parallel: Параллельный сбор
            progress_callback: Callback для отслеживания прогресса
                               (current_index, total, device_host, success)

        Returns:
            List[Dict]: Собранные данные со всех устройств
        """
        all_data = []
        total = len(devices)

        if parallel and len(devices) > 1:
            all_data = self._collect_parallel(devices, progress_callback)
        else:
            for idx, device in enumerate(devices):
                data = self._collect_from_device(device)
                success = data is not None
                if data:
                    all_data.append(data)
                if progress_callback:
                    progress_callback(idx + 1, total, device.host, success)

        logger.info(f"Собрано устройств: {len(all_data)} из {len(devices)}")
        return all_data

    # Алиас для совместимости
    def collect_models(
        self,
        devices: List[Device],
        parallel: bool = True,
    ) -> List[DeviceInfo]:
        """Алиас для collect() (обратная совместимость)."""
        return self.collect(devices, parallel=parallel)

    def _collect_parallel(
        self,
        devices: List[Device],
        progress_callback: Optional[ProgressCallback] = None,
    ) -> List[Dict[str, Any]]:
        """
        Параллельный сбор данных.

        Args:
            devices: Список устройств
            progress_callback: Callback для отслеживания прогресса

        Returns:
            List[Dict]: Собранные данные
        """
        all_data = []
        total = len(devices)
        completed_count = 0

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self._collect_from_device, device): device
                for device in devices
            }

            for future in as_completed(futures):
                device = futures[future]
                completed_count += 1
                success = False
                try:
                    data = future.result()
                    if data:
                        all_data.append(data)
                        success = True
                except CollectorError as e:
                    logger.error(f"Ошибка сбора с {device.host}: {format_error_for_log(e)}")
                except Exception as e:
                    logger.error(f"Неизвестная ошибка с {device.host}: {e}")

                if progress_callback:
                    progress_callback(completed_count, total, device.host, success)

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

        try:
            with self._conn_manager.connect(device, self.credentials) as conn:
                # Выполняем show version
                response = conn.send_command("show version")
                output = response.result

                # Парсим через NTCParser (кастомный шаблон → NTC Templates fallback)
                parsed_data = self._parser.parse(
                    output=output,
                    platform=device.platform,
                    command="show version",
                )

                # Нормализуем результат
                if isinstance(parsed_data, list) and parsed_data:
                    parsed = parsed_data[0]
                elif isinstance(parsed_data, dict):
                    parsed = parsed_data
                else:
                    parsed = {}

                # --format parsed: сырые данные NTC Templates, без нормализации
                if self._skip_normalize:
                    result = dict(parsed)
                    result["ip_address"] = device.host
                    result["platform"] = device.platform
                    logger.info(f"[SUCCESS] {device.host}: parsed данные получены (без нормализации)")
                    return result

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
            # Заполняем поля значениями из Device Management (fallback)
            data["_error"] = format_error_for_log(e)
            # Используем hostname из Device Management или IP как fallback
            fallback_hostname = device.hostname or device.host
            data["name"] = fallback_hostname
            data["hostname"] = fallback_hostname
            # Используем device_type из Device Management или Unknown
            data["model"] = normalize_device_model(device.device_type) if device.device_type else "Unknown"
            data["serial"] = ""
            data["version"] = ""
            data["uptime"] = ""
        except Exception as e:
            logger.error(f"[ERROR] {device.host}: неизвестная ошибка: {e}")
            data["_error"] = str(e)
            fallback_hostname = device.hostname or device.host
            data["name"] = fallback_hostname
            data["hostname"] = fallback_hostname
            data["model"] = normalize_device_model(device.device_type) if device.device_type else "Unknown"
            data["serial"] = ""
            data["version"] = ""
            data["uptime"] = ""

        # Добавляем дополнительные поля
        for csv_key, value in self.extra_fields.items():
            if callable(value):
                data[csv_key] = value(data, device)
            else:
                data[csv_key] = value

        # Передаём site из devices_ips.py (для per-device site в sync)
        if device.site:
            data["site"] = device.site

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
