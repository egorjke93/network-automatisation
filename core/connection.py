"""
Модуль управления SSH подключениями через Scrapli.

ConnectionManager обеспечивает:
- Подключение к устройствам через Scrapli
- Выполнение команд
- Получение hostname из prompt
- Обработку ошибок подключения

Поддерживаемые платформы:
- cisco_iosxe / cisco_ios
- cisco_nxos
- cisco_iosxr
- arista_eos
- juniper_junos
- qtech

Пример использования:
    manager = ConnectionManager()
    with manager.connect(device, credentials) as conn:
        output = conn.send_command("show version")
        hostname = manager.get_hostname(conn)
"""

import logging
import re
import time
from typing import Optional, Generator, Any, Dict
from contextlib import contextmanager

from scrapli import Scrapli
from scrapli.exceptions import (
    ScrapliTimeout,
    ScrapliAuthenticationFailed,
    ScrapliConnectionError,
)

from .device import Device, DeviceStatus
from .credentials import Credentials
from .constants.platforms import (
    DEFAULT_PLATFORM,
    SCRAPLI_PLATFORM_MAP,
    NTC_PLATFORM_MAP,
)
from .exceptions import (
    ConnectionError as CollectorConnectionError,
    AuthenticationError,
    TimeoutError as CollectorTimeoutError,
    CommandError,
    is_retryable,
)

logger = logging.getLogger(__name__)


def get_scrapli_platform(platform: str) -> str:
    """
    Преобразует платформу устройства в драйвер Scrapli.

    Args:
        platform: Платформа устройства (cisco_ios, cisco_iosxe, arista_eos, etc.)

    Returns:
        str: Драйвер для Scrapli
    """
    if not platform:
        return "cisco_iosxe"
    return SCRAPLI_PLATFORM_MAP.get(platform.lower(), "cisco_iosxe")


def get_ntc_platform(platform: str) -> str:
    """
    Преобразует платформу устройства в формат NTC Templates.

    Args:
        platform: Платформа устройства (cisco_ios, cisco_iosxe, arista_eos, etc.)

    Returns:
        str: Платформа для NTC Templates
    """
    if not platform:
        return DEFAULT_PLATFORM

    # Сначала пробуем прямое соответствие
    if platform.lower() in NTC_PLATFORM_MAP:
        return NTC_PLATFORM_MAP[platform.lower()]

    # Пробуем через Scrapli платформу
    scrapli_platform = get_scrapli_platform(platform)
    return NTC_PLATFORM_MAP.get(scrapli_platform, DEFAULT_PLATFORM)


class ConnectionManager:
    """
    Менеджер SSH подключений через Scrapli.

    Управляет жизненным циклом подключений, обрабатывает ошибки
    и предоставляет удобные методы для выполнения команд.

    Attributes:
        timeout_socket: Таймаут сокета (секунды)
        timeout_transport: Таймаут транспорта (секунды)
        timeout_ops: Таймаут операций (секунды)
        transport: Тип транспорта (ssh2, paramiko, system)
        max_retries: Максимум повторных попыток при ошибке
        retry_delay: Задержка между попытками (секунды)

    Example:
        manager = ConnectionManager(timeout_socket=15, max_retries=2)
        with manager.connect(device, creds) as conn:
            result = conn.send_command("show version")
    """

    def __init__(
        self,
        timeout_socket: int = 15,
        timeout_transport: int = 30,
        timeout_ops: int = 60,
        transport: str = "ssh2",
        max_retries: int = 2,
        retry_delay: int = 5,
    ):
        """
        Инициализация менеджера подключений.

        Args:
            timeout_socket: Таймаут сокета
            timeout_transport: Таймаут транспорта
            timeout_ops: Таймаут операций
            transport: Тип транспорта (ssh2, paramiko, system)
            max_retries: Максимум повторных попыток (0 = без retry)
            retry_delay: Задержка между попытками в секундах
        """
        self.timeout_socket = timeout_socket
        self.timeout_transport = timeout_transport
        self.timeout_ops = timeout_ops
        self.transport = transport
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def _build_connection_params(
        self,
        device: Device,
        credentials: Credentials,
    ) -> Dict[str, Any]:
        """
        Формирует параметры подключения для Scrapli.

        Args:
            device: Объект устройства
            credentials: Учётные данные

        Returns:
            Dict: Параметры для Scrapli
        """
        scrapli_platform = get_scrapli_platform(device.platform)

        params = {
            "host": device.host,
            "auth_username": credentials.username,
            "auth_password": credentials.password,
            "platform": scrapli_platform,
            "transport": self.transport,
            "auth_strict_key": False,
            "timeout_socket": self.timeout_socket,
            "timeout_transport": self.timeout_transport,
            "timeout_ops": self.timeout_ops,
        }

        # Добавляем enable password если есть
        if credentials.secret:
            params["auth_secondary"] = credentials.secret

        # Порт если нестандартный
        if device.port and device.port != 22:
            params["port"] = device.port

        return params

    @contextmanager
    def connect(
        self,
        device: Device,
        credentials: Credentials,
    ) -> Generator[Scrapli, None, None]:
        """
        Контекстный менеджер для подключения к устройству с retry.

        Автоматически закрывает соединение при выходе из контекста.
        Обновляет статус устройства. При ошибках подключения (timeout,
        connection error) выполняет повторные попытки.

        Args:
            device: Объект устройства
            credentials: Учётные данные

        Yields:
            Scrapli: Активное подключение Scrapli

        Raises:
            CollectorTimeoutError: Таймаут подключения (после всех retry)
            AuthenticationError: Ошибка аутентификации (без retry)
            CollectorConnectionError: Ошибка подключения (после всех retry)
        """
        connection = None
        last_error = None
        params = self._build_connection_params(device, credentials)

        # Всего попыток = 1 (первая) + max_retries
        total_attempts = 1 + self.max_retries

        for attempt in range(1, total_attempts + 1):
            try:
                if attempt == 1:
                    logger.info(f"Подключение к {device.host}...")
                else:
                    logger.info(
                        f"Подключение к {device.host} (попытка {attempt}/{total_attempts})..."
                    )

                connection = Scrapli(**params)
                connection.open()

                # Успешное подключение
                device.status = DeviceStatus.ONLINE
                device.hostname = self.get_hostname(connection)
                logger.info(f"Подключено к {device.display_name}")

                try:
                    yield connection
                finally:
                    if connection:
                        try:
                            connection.close()
                            logger.debug(f"Отключено от {device.host}")
                        except Exception:
                            pass
                return  # Успешно завершено

            except ScrapliAuthenticationFailed as e:
                # Ошибки аутентификации НЕ повторяем
                device.status = DeviceStatus.ERROR
                device.last_error = f"Ошибка аутентификации: {e}"
                logger.error(f"Ошибка аутентификации на {device.host}: {e}")
                raise AuthenticationError(
                    f"Ошибка аутентификации: {e}",
                    device=device.host,
                ) from e

            except ScrapliTimeout as e:
                last_error = CollectorTimeoutError(
                    f"Таймаут подключения: {e}",
                    device=device.host,
                    timeout_seconds=self.timeout_socket,
                )
                device.status = DeviceStatus.OFFLINE
                device.last_error = f"Таймаут подключения: {e}"

                if attempt < total_attempts:
                    logger.warning(
                        f"Таймаут при подключении к {device.host}, "
                        f"повтор через {self.retry_delay}с ({attempt}/{total_attempts})"
                    )
                    time.sleep(self.retry_delay)
                else:
                    logger.error(
                        f"Таймаут при подключении к {device.host} "
                        f"(исчерпаны все {total_attempts} попыток)"
                    )

            except ScrapliConnectionError as e:
                last_error = CollectorConnectionError(
                    f"Ошибка подключения: {e}",
                    device=device.host,
                    port=device.port or 22,
                )
                device.status = DeviceStatus.ERROR
                device.last_error = f"Ошибка подключения: {e}"

                if attempt < total_attempts:
                    logger.warning(
                        f"Ошибка подключения к {device.host}, "
                        f"повтор через {self.retry_delay}с ({attempt}/{total_attempts})"
                    )
                    time.sleep(self.retry_delay)
                else:
                    logger.error(
                        f"Ошибка подключения к {device.host} "
                        f"(исчерпаны все {total_attempts} попыток)"
                    )

            except Exception as e:
                last_error = CollectorConnectionError(
                    f"Неизвестная ошибка: {e}",
                    device=device.host,
                )
                device.status = DeviceStatus.ERROR
                device.last_error = str(e)

                # Проверяем можно ли повторить
                if is_retryable(e) and attempt < total_attempts:
                    logger.warning(
                        f"Ошибка при подключении к {device.host}: {e}, "
                        f"повтор через {self.retry_delay}с ({attempt}/{total_attempts})"
                    )
                    time.sleep(self.retry_delay)
                else:
                    logger.error(f"Ошибка при подключении к {device.host}: {e}")
                    break  # Не retryable или исчерпаны попытки

            finally:
                # Закрываем соединение если было открыто частично
                if connection:
                    try:
                        connection.close()
                    except Exception:
                        pass
                    connection = None

        # Если дошли сюда - все попытки исчерпаны
        if last_error:
            raise last_error

    @staticmethod
    def get_hostname(connection: Scrapli) -> str:
        """
        Получает hostname устройства из prompt.

        Args:
            connection: Активное подключение Scrapli

        Returns:
            str: Hostname устройства
        """
        try:
            prompt = connection.get_prompt()
            # Убираем символы prompt (#, >, $, etc.)
            hostname = re.sub(r"[#>$\s]+$", "", prompt).strip()
            return hostname if hostname else "Unknown"
        except Exception as e:
            logger.warning(f"Не удалось получить hostname: {e}")
            return "Unknown"

    def send_command(
        self,
        connection: Scrapli,
        command: str,
        timeout: Optional[int] = None,
    ) -> str:
        """
        Выполняет команду на устройстве.

        Args:
            connection: Активное подключение
            command: Команда для выполнения
            timeout: Таймаут выполнения (опционально)

        Returns:
            str: Вывод команды
        """
        logger.debug(f"Выполнение команды: {command}")

        if timeout:
            response = connection.send_command(command, timeout_ops=timeout)
        else:
            response = connection.send_command(command)

        return response.result

    def send_commands(
        self,
        connection: Scrapli,
        commands: list,
        stop_on_failed: bool = False,
    ) -> list:
        """
        Выполняет список команд на устройстве.

        Args:
            connection: Активное подключение
            commands: Список команд
            stop_on_failed: Остановиться при ошибке

        Returns:
            list: Список результатов
        """
        logger.debug(f"Выполнение {len(commands)} команд")

        responses = connection.send_commands(
            commands,
            stop_on_failed=stop_on_failed,
        )

        return [r.result for r in responses]

    def send_config(
        self,
        connection: Scrapli,
        configs: list,
    ) -> str:
        """
        Отправляет конфигурационные команды.

        Args:
            connection: Активное подключение
            configs: Список конфигурационных команд

        Returns:
            str: Вывод команд
        """
        logger.debug(f"Отправка {len(configs)} конфигурационных команд")

        response = connection.send_configs(configs)
        return response.result

