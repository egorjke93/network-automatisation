"""
Базовый класс коллектора данных.

Определяет общий интерфейс для всех коллекторов.
Все коллекторы должны наследоваться от BaseCollector.

Использует Scrapli для подключения и NTC Templates для парсинга.

Пример создания кастомного коллектора:
    class ARPCollector(BaseCollector):
        command = "show ip arp"

        def _parse_output(self, output, device):
            # Парсинг вывода
            return parsed_data

Поддержка типизированных моделей:
    # Collectors возвращают List[Dict] для обратной совместимости
    data = collector.collect(devices)

    # Или типизированные модели
    interfaces = collector.collect_models(devices)  # List[Interface]

    # Конвертация существующих данных
    from network_collector.core import interfaces_from_dicts
    interfaces = interfaces_from_dicts(data)
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Type, TypeVar, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

# TypeVar для типизированных моделей
T = TypeVar("T")

# Callback для прогресса: (current_index, total, device_host, success)
ProgressCallback = Callable[[int, int, str, bool], None]

from ..core.device import Device, DeviceStatus
from ..core.connection import ConnectionManager, get_ntc_platform
from ..core.credentials import Credentials
from ..core.context import RunContext, get_current_context
from ..core.exceptions import (
    CollectorError,
    ConnectionError,
    AuthenticationError,
    TimeoutError,
    format_error_for_log,
)
from ..core.logging import get_logger
from ..parsers.textfsm_parser import NTCParser, NTC_AVAILABLE

logger = get_logger(__name__)


class BaseCollector(ABC):
    """
    Абстрактный базовый класс для коллекторов данных.

    Определяет общий интерфейс и логику для сбора данных
    с сетевых устройств через Scrapli.

    Attributes:
        credentials: Учётные данные для подключения
        use_ntc: Использовать NTC Templates для парсинга
        max_workers: Максимум параллельных подключений
        model_class: Класс модели для типизированного вывода

    Example:
        class MyCollector(BaseCollector):
            command = "show my data"
            model_class = MyModel  # опционально

            def _parse_output(self, output, device):
                return [{"field": "value"}]

    Типизированный сбор:
        collector = InterfaceCollector()
        interfaces = collector.collect_models(devices)  # List[Interface]
    """

    # Команда для выполнения (переопределяется в наследниках)
    command: str = ""

    # Платформо-зависимые команды
    # {device_type: command}
    platform_commands: Dict[str, str] = {}

    # Класс модели для типизированного вывода (переопределяется в наследниках)
    # Должен иметь метод from_dict(data: Dict) -> Model
    model_class: Optional[Type[T]] = None

    def __init__(
        self,
        credentials: Optional[Credentials] = None,
        use_ntc: bool = True,
        ntc_fields: Optional[List[str]] = None,
        max_workers: int = 10,
        timeout_socket: int = 15,
        timeout_transport: int = 30,
        transport: str = "ssh2",
        max_retries: int = 2,
        retry_delay: int = 5,
        context: Optional[RunContext] = None,
    ):
        """
        Инициализация коллектора.

        Args:
            credentials: Учётные данные (если None — запросит интерактивно)
            use_ntc: Использовать NTC Templates для парсинга
            ntc_fields: Список полей для извлечения из NTC
            max_workers: Максимум параллельных подключений
            timeout_socket: Таймаут сокета
            timeout_transport: Таймаут транспорта
            transport: Тип транспорта
            max_retries: Максимум повторных попыток при ошибке подключения
            retry_delay: Задержка между попытками (секунды)
            context: Контекст выполнения (если None — использует глобальный)
        """
        self.credentials = credentials
        # Контекст: явный или глобальный
        self.ctx = context or get_current_context()
        self.use_ntc = use_ntc and NTC_AVAILABLE
        self.ntc_fields = ntc_fields
        self.max_workers = max_workers

        # Менеджер подключений с retry логикой
        self._conn_manager = ConnectionManager(
            timeout_socket=timeout_socket,
            timeout_transport=timeout_transport,
            transport=transport,
            max_retries=max_retries,
            retry_delay=retry_delay,
        )

        # NTC парсер
        if self.use_ntc:
            try:
                self._parser = NTCParser()
            except ImportError:
                self._parser = None
                self.use_ntc = False
        else:
            self._parser = None

        # Флаг для --format parsed: пропускает нормализацию, возвращает сырые данные TextFSM
        self._skip_normalize = False

    def _log_prefix(self) -> str:
        """Возвращает префикс для логов с run_id."""
        if self.ctx:
            return f"[{self.ctx.run_id}] "
        return ""

    def collect(
        self,
        devices: List[Device],
        parallel: bool = True,
    ) -> List[T]:
        """
        Собирает данные и возвращает типизированные модели.

        Args:
            devices: Список устройств
            parallel: Параллельный сбор

        Returns:
            List[Model]: Типизированные объекты (Interface, MACEntry, etc.)

        Raises:
            ValueError: Если model_class не определён для коллектора

        Example:
            collector = InterfaceCollector()
            interfaces = collector.collect(devices)
            for intf in interfaces:
                print(intf.name, intf.status)  # автокомплит в IDE
        """
        if self.model_class is None:
            raise ValueError(
                f"{self.__class__.__name__} не имеет model_class. "
                f"Используйте collect_dicts() для сырых данных."
            )

        data = self.collect_dicts(devices, parallel=parallel)
        return [self.model_class.from_dict(row) for row in data]

    def collect_dicts(
        self,
        devices: List[Device],
        parallel: bool = True,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> List[Dict[str, Any]]:
        """
        Собирает данные как словари (для экспортеров, pandas).

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
                success = len(data) > 0
                all_data.extend(data)
                if progress_callback:
                    progress_callback(idx + 1, total, device.host, success)

        logger.info(f"{self._log_prefix()}Собрано записей: {len(all_data)} с {len(devices)} устройств")
        return all_data

    # Алиас для обратной совместимости
    def collect_models(
        self,
        devices: List[Device],
        parallel: bool = True,
    ) -> List[T]:
        """Алиас для collect() (обратная совместимость)."""
        return self.collect(devices, parallel=parallel)

    def to_models(self, data: List[Dict[str, Any]]) -> List[T]:
        """
        Конвертирует словари в типизированные модели.

        Args:
            data: Список словарей

        Returns:
            List[Model]: Типизированные объекты
        """
        if self.model_class is None:
            raise ValueError(
                f"{self.__class__.__name__} не имеет model_class."
            )
        return [self.model_class.from_dict(row) for row in data]

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
                    all_data.extend(data)
                    success = len(data) > 0
                except CollectorError as e:
                    # Наши типизированные ошибки — логируем с деталями
                    logger.error(f"{self._log_prefix()}Ошибка сбора с {device.host}: {format_error_for_log(e)}")
                except Exception as e:
                    # Неизвестные ошибки — оборачиваем
                    logger.error(f"{self._log_prefix()}Неизвестная ошибка сбора с {device.host}: {e}")

                # Вызываем callback после каждого устройства
                if progress_callback:
                    progress_callback(completed_count, total, device.host, success)

        return all_data

    def _collect_from_device(self, device: Device) -> List[Dict[str, Any]]:
        """
        Собирает данные с одного устройства.

        Args:
            device: Устройство

        Returns:
            List[Dict]: Данные с устройства
        """
        command = self._get_command(device)
        if not command:
            logger.warning(f"Нет команды для {device.platform}")
            return []

        try:
            with self._conn_manager.connect(device, self.credentials) as conn:
                hostname = self._init_device_connection(conn, device)

                response = conn.send_command(command)
                data = self._parse_output(response.result, device)

                self._add_metadata_to_rows(data, hostname, device.host)
                logger.info(f"{hostname}: собрано {len(data)} записей")
                return data

        except Exception as e:
            return self._handle_collection_error(e, device)

    def _get_command(self, device: Device) -> str:
        """
        Возвращает команду для конкретной платформы.

        Args:
            device: Устройство

        Returns:
            str: Команда для выполнения
        """
        # Сначала проверяем платформо-зависимые команды
        if device.platform in self.platform_commands:
            return self.platform_commands[device.platform]

        # Иначе используем общую команду
        return self.command

    def _init_device_connection(self, conn, device: Device) -> str:
        """
        Инициализирует подключение: hostname, metadata, status.

        Вызывается в начале _collect_from_device для устранения
        дублирования в каждом коллекторе.

        Args:
            conn: Активное соединение
            device: Устройство

        Returns:
            str: hostname устройства
        """
        hostname = self._conn_manager.get_hostname(conn)
        device.metadata["hostname"] = hostname
        device.status = DeviceStatus.ONLINE
        return hostname

    def _add_metadata_to_rows(
        self,
        data: List[Dict[str, Any]],
        hostname: str,
        device_ip: str,
    ) -> None:
        """
        Добавляет hostname и device_ip к каждой записи (in-place).

        Args:
            data: Список записей
            hostname: Hostname устройства
            device_ip: IP устройства
        """
        for row in data:
            row["hostname"] = hostname
            row["device_ip"] = device_ip

    def _handle_collection_error(
        self,
        e: Exception,
        device: Device,
    ) -> List[Dict[str, Any]]:
        """
        Обрабатывает ошибку при сборе данных.

        Устанавливает status=ERROR и логирует.

        Args:
            e: Исключение
            device: Устройство

        Returns:
            List: Пустой список (для return)
        """
        device.status = DeviceStatus.ERROR
        if isinstance(e, (ConnectionError, AuthenticationError, TimeoutError)):
            logger.error(f"Ошибка подключения к {device.host}: {format_error_for_log(e)}")
        else:
            logger.error(f"Неизвестная ошибка с {device.host}: {e}")
        return []

    @abstractmethod
    def _parse_output(
        self,
        output: str,
        device: Device,
    ) -> List[Dict[str, Any]]:
        """
        Парсит вывод команды.

        Абстрактный метод — должен быть реализован в наследниках.

        Args:
            output: Сырой вывод команды
            device: Устройство

        Returns:
            List[Dict]: Распарсенные данные
        """
        pass

    def _parse_with_ntc(
        self,
        output: str,
        device: Device,
        command: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Парсит вывод с помощью NTC Templates.

        Args:
            output: Сырой вывод
            device: Устройство
            command: Команда (если отличается от self.command)

        Returns:
            List[Dict]: Распарсенные данные
        """
        if not self._parser:
            return []

        cmd = command or self._get_command(device)
        ntc_platform = get_ntc_platform(device.platform)

        try:
            return self._parser.parse(
                output=output,
                platform=ntc_platform,
                command=cmd,
                fields=self.ntc_fields,
            )
        except Exception as e:
            # Логируем как warning — fallback парсинг может сработать
            logger.warning(f"NTC парсинг не удался для {device.platform}/{cmd}: {e}")
            # Не бросаем ParseError — даём возможность fallback парсингу
            return []

    # Алиас для обратной совместимости
    def _parse_with_textfsm(
        self,
        output: str,
        device: Device,
        command: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Алиас для _parse_with_ntc (обратная совместимость)."""
        return self._parse_with_ntc(output, device, command)
