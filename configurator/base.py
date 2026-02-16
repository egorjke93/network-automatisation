"""
Базовый класс для применения конфигурационных изменений.

Использует Netmiko для надёжного применения конфигураций.

Пример использования:
    pusher = ConfigPusher(credentials)

    # Применить команды на устройстве
    result = pusher.push_config(device, [
        "interface Gi0/1",
        "description Server-01",
    ])
"""

import logging
import time
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from netmiko import ConnectHandler
from netmiko.exceptions import (
    NetmikoTimeoutException,
    NetmikoAuthenticationException,
)

from ..core.device import Device
from ..core.credentials import Credentials
from ..core.constants import NETMIKO_PLATFORM_MAP

logger = logging.getLogger(__name__)


@dataclass
class ConfigResult:
    """Результат применения конфигурации."""
    success: bool
    device: str
    commands_sent: int
    output: str = ""
    error: str = ""


class ConfigPusher:
    """
    Базовый класс для применения конфигурационных изменений.

    Использует Netmiko для надёжного применения конфигураций на устройствах.
    Поддерживает dry-run режим для тестирования без реальных изменений.
    При ошибках подключения выполняет повторные попытки.

    Attributes:
        credentials: Учётные данные
        timeout: Таймаут подключения
        save_config: Сохранять конфигурацию после изменений
        max_retries: Максимум повторных попыток
        retry_delay: Задержка между попытками

    Example:
        pusher = ConfigPusher(credentials)

        # Dry-run (только показать команды)
        result = pusher.push_config(device, commands, dry_run=True)

        # Реальное применение
        result = pusher.push_config(device, commands, dry_run=False)
    """

    def __init__(
        self,
        credentials: Credentials,
        timeout: int = 30,
        save_config: bool = True,
        max_retries: int = 2,
        retry_delay: int = 5,
    ):
        """
        Инициализация конфигуратора.

        Args:
            credentials: Учётные данные
            timeout: Таймаут подключения
            save_config: Сохранять конфигурацию после изменений
            max_retries: Максимум повторных попыток при ошибке подключения
            retry_delay: Задержка между попытками (секунды)
        """
        self.credentials = credentials
        self.timeout = timeout
        self.save_config = save_config
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def _build_connection_params(self, device: Device) -> Dict[str, Any]:
        """
        Формирует параметры подключения для Netmiko.

        Args:
            device: Устройство

        Returns:
            Dict: Параметры для Netmiko
        """
        # Конвертируем platform в формат Netmiko
        netmiko_device_type = NETMIKO_PLATFORM_MAP.get(
            device.platform, device.platform
        )
        params = {
            "device_type": netmiko_device_type,
            "host": device.host,
            "username": self.credentials.username,
            "password": self.credentials.password,
            "timeout": self.timeout,
        }

        if self.credentials.secret:
            params["secret"] = self.credentials.secret

        if device.port and device.port != 22:
            params["port"] = device.port

        return params

    def push_config(
        self,
        device: Device,
        commands: List[str],
        dry_run: bool = True,
        exec_commands: Optional[List[str]] = None,
    ) -> ConfigResult:
        """
        Применяет конфигурационные команды на устройстве с retry.

        Args:
            device: Устройство
            commands: Список конфигурационных команд (config mode)
            dry_run: Режим симуляции (без реальных изменений)
            exec_commands: Список exec-команд (privileged mode, после config)

        Returns:
            ConfigResult: Результат применения
        """
        total_cmds = len(commands) + len(exec_commands or [])

        if not commands and not exec_commands:
            return ConfigResult(
                success=True,
                device=device.host,
                commands_sent=0,
                output="Нет команд для применения",
            )

        if dry_run:
            logger.info(f"[DRY RUN] {device.host}: {total_cmds} команд")
            for cmd in commands:
                logger.debug(f"  [config] {cmd}")
            for cmd in (exec_commands or []):
                logger.debug(f"  [exec] {cmd}")
            return ConfigResult(
                success=True,
                device=device.host,
                commands_sent=total_cmds,
                output="[DRY RUN] Команды не применены",
            )

        params = self._build_connection_params(device)
        total_attempts = 1 + self.max_retries
        last_error = ""

        for attempt in range(1, total_attempts + 1):
            try:
                if attempt == 1:
                    logger.info(f"Подключение к {device.host}...")
                else:
                    logger.info(
                        f"Подключение к {device.host} (попытка {attempt}/{total_attempts})..."
                    )

                with ConnectHandler(**params) as conn:
                    # Переходим в enable если нужно
                    if self.credentials.secret:
                        conn.enable()

                    # Применяем конфигурационные команды (config mode)
                    output = ""
                    if commands:
                        output = conn.send_config_set(commands)

                    # Выполняем exec-команды (privileged mode)
                    if exec_commands:
                        for exec_cmd in exec_commands:
                            exec_output = conn.send_command(exec_cmd)
                            output += f"\n{exec_output}"
                            logger.debug(f"{device.host}: [exec] {exec_cmd}")

                    # Сохраняем если нужно
                    if self.save_config:
                        save_output = conn.save_config()
                        output += f"\n{save_output}"

                    logger.info(f"{device.host}: применено {total_cmds} команд")

                    return ConfigResult(
                        success=True,
                        device=device.host,
                        commands_sent=total_cmds,
                        output=output,
                    )

            except NetmikoAuthenticationException as e:
                # Ошибки аутентификации НЕ повторяем
                error_msg = f"Ошибка аутентификации: {e}"
                logger.error(f"{device.host}: {error_msg}")
                return ConfigResult(
                    success=False,
                    device=device.host,
                    commands_sent=0,
                    error=error_msg,
                )

            except NetmikoTimeoutException as e:
                last_error = f"Таймаут подключения: {e}"
                if attempt < total_attempts:
                    logger.warning(
                        f"{device.host}: {last_error}, "
                        f"повтор через {self.retry_delay}с ({attempt}/{total_attempts})"
                    )
                    time.sleep(self.retry_delay)
                else:
                    logger.error(
                        f"{device.host}: {last_error} "
                        f"(исчерпаны все {total_attempts} попыток)"
                    )

            except Exception as e:
                last_error = f"Ошибка: {e}"
                if attempt < total_attempts:
                    logger.warning(
                        f"{device.host}: {last_error}, "
                        f"повтор через {self.retry_delay}с ({attempt}/{total_attempts})"
                    )
                    time.sleep(self.retry_delay)
                else:
                    logger.error(
                        f"{device.host}: {last_error} "
                        f"(исчерпаны все {total_attempts} попыток)"
                    )

        # Все попытки исчерпаны
        return ConfigResult(
            success=False,
            device=device.host,
            commands_sent=0,
            error=last_error,
        )

    def push_config_batch(
        self,
        devices: List[Device],
        commands_per_device: Dict[str, List[str]],
        dry_run: bool = True,
    ) -> List[ConfigResult]:
        """
        Применяет конфигурацию на нескольких устройствах.

        Args:
            devices: Список устройств
            commands_per_device: {device_host: [commands]}
            dry_run: Режим симуляции

        Returns:
            List[ConfigResult]: Результаты для каждого устройства
        """
        results = []

        for device in devices:
            commands = commands_per_device.get(device.host, [])
            if not commands:
                # Пробуем по hostname
                hostname = device.metadata.get("hostname", "")
                commands = commands_per_device.get(hostname, [])

            if commands:
                result = self.push_config(device, commands, dry_run=dry_run)
                results.append(result)

        return results
