"""
Коллектор для резервного копирования конфигураций.

Собирает running-config с сетевых устройств и сохраняет в файлы.

Поддерживаемые платформы:
- Cisco IOS/IOS-XE/NX-OS/IOS-XR
- Arista EOS
- Juniper JunOS
- QTech

Пример использования:
    collector = ConfigBackupCollector(credentials)
    results = collector.backup(devices, output_folder="backups")
"""

import re
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from ..core.device import Device
from ..core.connection import ConnectionManager
from ..core.credentials import Credentials

logger = logging.getLogger(__name__)


# Команды для получения конфигурации по платформам
CONFIG_COMMANDS = {
    "cisco_ios": "show running-config",
    "cisco_iosxe": "show running-config",
    "cisco_nxos": "show running-config",
    "cisco_iosxr": "show running-config",
    "arista_eos": "show running-config",
    "juniper_junos": "show configuration | display set",
    "juniper": "show configuration | display set",
    "qtech": "show running-config",
    "qtech_qsw": "show running-config",
}


@dataclass
class BackupResult:
    """Результат резервного копирования одного устройства."""
    device_ip: str
    hostname: str
    success: bool
    file_path: Optional[str] = None
    error: Optional[str] = None


class ConfigBackupCollector:
    """
    Коллектор для резервного копирования конфигураций.

    Сохраняет running-config в файлы с именованием:
    {hostname}.cfg

    Attributes:
        credentials: Учётные данные для подключения
        output_folder: Папка для сохранения бэкапов

    Example:
        collector = ConfigBackupCollector(credentials)
        results = collector.backup(devices, output_folder="backups")

        for r in results:
            if r.success:
                print(f"{r.hostname}: saved to {r.file_path}")
            else:
                print(f"{r.hostname}: FAILED - {r.error}")
    """

    def __init__(
        self,
        credentials: Credentials,
        timeout_socket: int = 15,
        timeout_transport: int = 30,
        timeout_ops: int = 120,
        transport: str = "ssh2",
    ):
        """
        Инициализация коллектора бэкапов.

        Args:
            credentials: Учётные данные
            timeout_socket: Таймаут сокета
            timeout_transport: Таймаут транспорта
            timeout_ops: Таймаут операций (для больших конфигов)
            transport: Транспорт SSH
        """
        self.credentials = credentials

        self._conn_manager = ConnectionManager(
            timeout_socket=timeout_socket,
            timeout_transport=timeout_transport,
            timeout_ops=timeout_ops,
            transport=transport,
        )

    def backup(
        self,
        devices: List[Device],
        output_folder: str = "backups",
    ) -> List[BackupResult]:
        """
        Выполняет резервное копирование конфигураций.

        Args:
            devices: Список устройств
            output_folder: Папка для сохранения

        Returns:
            List[BackupResult]: Результаты для каждого устройства
        """
        results = []
        folder = Path(output_folder)

        # Создаём папку если не существует
        if not folder.exists():
            folder.mkdir(parents=True, exist_ok=True)
            logger.info(f"Создана папка: {folder}")

        for device in devices:
            result = self._backup_device(device, folder)
            results.append(result)

        # Статистика
        success = sum(1 for r in results if r.success)
        logger.info(f"Бэкап завершён: {success}/{len(results)} успешно")

        return results

    def _backup_device(
        self,
        device: Device,
        output_folder: Path,
    ) -> BackupResult:
        """
        Бэкапит конфигурацию одного устройства.

        Args:
            device: Устройство
            output_folder: Папка для сохранения

        Returns:
            BackupResult: Результат
        """
        result = BackupResult(
            device_ip=device.host,
            hostname=device.host,
            success=False,
        )

        # Получаем команду для платформы
        command = CONFIG_COMMANDS.get(
            device.platform.lower(),
            "show running-config"
        )

        try:
            with self._conn_manager.connect(device, self.credentials) as conn:
                # Получаем hostname
                hostname = self._conn_manager.get_hostname(conn)
                result.hostname = hostname

                logger.info(f"Получение конфигурации с {hostname}...")

                # Выполняем команду
                response = conn.send_command(command)
                config = response.result

                # Сохраняем файл
                safe_hostname = re.sub(r'[^\w\-.]', '_', hostname)
                file_path = output_folder / f"{safe_hostname}.cfg"

                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(config)

                result.file_path = str(file_path)
                result.success = True

                logger.info(f"[OK] {hostname}: сохранено в {file_path.name}")

        except Exception as e:
            result.error = str(e)
            logger.error(f"[ERROR] {device.host}: {e}")

        return result
