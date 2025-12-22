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
"""

import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from ..core.device import Device, DeviceStatus
from ..core.connection import ConnectionManager, get_ntc_platform
from ..core.credentials import Credentials
from ..parsers.textfsm_parser import NTCParser, NTC_AVAILABLE

logger = logging.getLogger(__name__)


class BaseCollector(ABC):
    """
    Абстрактный базовый класс для коллекторов данных.

    Определяет общий интерфейс и логику для сбора данных
    с сетевых устройств через Scrapli.

    Attributes:
        credentials: Учётные данные для подключения
        use_ntc: Использовать NTC Templates для парсинга
        max_workers: Максимум параллельных подключений

    Example:
        class MyCollector(BaseCollector):
            command = "show my data"

            def _parse_output(self, output, device):
                return [{"field": "value"}]
    """

    # Команда для выполнения (переопределяется в наследниках)
    command: str = ""

    # Платформо-зависимые команды
    # {device_type: command}
    platform_commands: Dict[str, str] = {}

    def __init__(
        self,
        credentials: Optional[Credentials] = None,
        use_ntc: bool = True,
        ntc_fields: Optional[List[str]] = None,
        max_workers: int = 10,
        timeout_socket: int = 15,
        timeout_transport: int = 30,
        transport: str = "ssh2",
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
        """
        self.credentials = credentials
        self.use_ntc = use_ntc and NTC_AVAILABLE
        self.ntc_fields = ntc_fields
        self.max_workers = max_workers

        # Менеджер подключений
        self._conn_manager = ConnectionManager(
            timeout_socket=timeout_socket,
            timeout_transport=timeout_transport,
            transport=transport,
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
                all_data.extend(data)

        logger.info(f"Собрано записей: {len(all_data)} с {len(devices)} устройств")
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
                    all_data.extend(data)
                except Exception as e:
                    logger.error(f"Ошибка сбора с {device.host}: {e}")

        return all_data

    def _collect_from_device(self, device: Device) -> List[Dict[str, Any]]:
        """
        Собирает данные с одного устройства.

        Args:
            device: Устройство

        Returns:
            List[Dict]: Данные с устройства
        """
        # Получаем команду для платформы
        command = self._get_command(device)

        if not command:
            logger.warning(f"Нет команды для {device.platform}")
            return []

        try:
            with self._conn_manager.connect(device, self.credentials) as conn:
                # Получаем hostname
                hostname = self._conn_manager.get_hostname(conn)
                device.metadata["hostname"] = hostname
                device.status = DeviceStatus.ONLINE

                # Выполняем команду
                response = conn.send_command(command)
                output = response.result

                # Парсим вывод
                data = self._parse_output(output, device)

                # Добавляем hostname ко всем записям
                for row in data:
                    row["hostname"] = hostname
                    row["device_ip"] = device.host

                logger.info(f"{hostname}: собрано {len(data)} записей")
                return data

        except Exception as e:
            device.status = DeviceStatus.ERROR
            logger.error(f"Ошибка подключения к {device.host}: {e}")
            return []

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
            logger.warning(f"NTC парсинг не удался для {device.platform}/{cmd}: {e}")
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
