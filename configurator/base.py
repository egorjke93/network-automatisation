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

    Attributes:
        credentials: Учётные данные
        timeout: Таймаут подключения
        save_config: Сохранять конфигурацию после изменений

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
    ):
        """
        Инициализация конфигуратора.

        Args:
            credentials: Учётные данные
            timeout: Таймаут подключения
            save_config: Сохранять конфигурацию после изменений
        """
        self.credentials = credentials
        self.timeout = timeout
        self.save_config = save_config

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
    ) -> ConfigResult:
        """
        Применяет конфигурационные команды на устройстве.

        Args:
            device: Устройство
            commands: Список конфигурационных команд
            dry_run: Режим симуляции (без реальных изменений)

        Returns:
            ConfigResult: Результат применения
        """
        if not commands:
            return ConfigResult(
                success=True,
                device=device.host,
                commands_sent=0,
                output="Нет команд для применения",
            )

        if dry_run:
            logger.info(f"[DRY RUN] {device.host}: {len(commands)} команд")
            for cmd in commands:
                logger.debug(f"  {cmd}")
            return ConfigResult(
                success=True,
                device=device.host,
                commands_sent=len(commands),
                output="[DRY RUN] Команды не применены",
            )

        try:
            params = self._build_connection_params(device)

            logger.info(f"Подключение к {device.host}...")
            with ConnectHandler(**params) as conn:
                # Переходим в enable если нужно
                if self.credentials.secret:
                    conn.enable()

                # Применяем конфигурацию
                output = conn.send_config_set(commands)

                # Сохраняем если нужно
                if self.save_config:
                    save_output = conn.save_config()
                    output += f"\n{save_output}"

                logger.info(f"{device.host}: применено {len(commands)} команд")

                return ConfigResult(
                    success=True,
                    device=device.host,
                    commands_sent=len(commands),
                    output=output,
                )

        except NetmikoTimeoutException as e:
            error_msg = f"Таймаут подключения: {e}"
            logger.error(f"{device.host}: {error_msg}")
            return ConfigResult(
                success=False,
                device=device.host,
                commands_sent=0,
                error=error_msg,
            )

        except NetmikoAuthenticationException as e:
            error_msg = f"Ошибка аутентификации: {e}"
            logger.error(f"{device.host}: {error_msg}")
            return ConfigResult(
                success=False,
                device=device.host,
                commands_sent=0,
                error=error_msg,
            )

        except Exception as e:
            error_msg = f"Ошибка: {e}"
            logger.error(f"{device.host}: {error_msg}")
            return ConfigResult(
                success=False,
                device=device.host,
                commands_sent=0,
                error=error_msg,
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
