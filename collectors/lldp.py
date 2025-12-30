"""
Коллектор LLDP/CDP соседей.

Собирает информацию о соседях по протоколам LLDP и CDP.
Поддерживает Cisco, Arista, Juniper.

Данные для NetBox кабелей:
- local_interface: Локальный интерфейс
- remote_hostname: Имя соседа (может быть MAC если имя неизвестно)
- remote_port: Интерфейс соседа
- remote_mac: MAC-адрес соседа (для поиска в NetBox)
- remote_ip: IP соседа (если есть, для поиска в NetBox)
- neighbor_type: Тип определения (hostname/mac/ip/unknown)

Пример использования:
    collector = LLDPCollector()
    data = collector.collect(devices)

    # Только CDP
    collector = LLDPCollector(protocol="cdp")

    # Оба протокола
    collector = LLDPCollector(protocol="both")
"""

import re
from typing import List, Dict, Any, Optional

from .base import BaseCollector
from ..core.device import Device
from ..core.models import LLDPNeighbor
from ..core.logging import get_logger
from ..core.exceptions import (
    ConnectionError,
    AuthenticationError,
    TimeoutError,
    format_error_for_log,
)
from ..core.constants import normalize_interface_short
from ..core.domain.lldp import LLDPNormalizer

logger = get_logger(__name__)


class LLDPCollector(BaseCollector):
    """
    Коллектор LLDP/CDP соседей.

    Собирает информацию о соседних устройствах.

    Attributes:
        protocol: Протокол (lldp, cdp, both)

    Example:
        collector = LLDPCollector(protocol="both")
        neighbors = collector.collect(devices)  # List[Dict]

        # Или типизированные модели
        neighbors = collector.collect_models(devices)  # List[LLDPNeighbor]
    """

    # Типизированная модель
    model_class = LLDPNeighbor

    # Команды для LLDP
    lldp_commands = {
        "cisco_ios": "show lldp neighbors detail",
        "cisco_iosxe": "show lldp neighbors detail",
        "cisco_nxos": "show lldp neighbors detail",
        "arista_eos": "show lldp neighbors detail",
        "juniper_junos": "show lldp neighbors",
    }

    # Команды для CDP
    cdp_commands = {
        "cisco_ios": "show cdp neighbors detail",
        "cisco_iosxe": "show cdp neighbors detail",
        "cisco_nxos": "show cdp neighbors detail",
    }

    def __init__(
        self,
        protocol: str = "lldp",
        **kwargs,
    ):
        """
        Инициализация коллектора LLDP.

        Args:
            protocol: Протокол (lldp, cdp, both)
            **kwargs: Аргументы для BaseCollector
        """
        super().__init__(**kwargs)
        self.protocol = protocol.lower()
        self._normalizer = LLDPNormalizer()

        # Устанавливаем команды в зависимости от протокола
        if self.protocol == "cdp":
            self.platform_commands = self.cdp_commands
        elif self.protocol == "both":
            # Для both используем LLDP как основной, CDP как fallback
            self.platform_commands = self.lldp_commands
        else:
            self.platform_commands = self.lldp_commands

    def _collect_from_device(self, device: Device) -> List[Dict[str, Any]]:
        """
        Собирает LLDP/CDP данные с устройства.

        Для protocol="both" собирает оба протокола и объединяет данные:
        - MAC адрес из LLDP (chassis_id)
        - Platform из CDP

        Архитектура:
        1. Collector: парсинг (TextFSM/regex) → сырые данные
        2. Domain (LLDPNormalizer): нормализация → типизированные данные
        """
        command = self._get_command(device)

        if not command:
            logger.warning(f"Нет команды для {device.platform}")
            return []

        try:
            with self._conn_manager.connect(device, self.credentials) as conn:
                hostname = self._conn_manager.get_hostname(conn)
                device.metadata["hostname"] = hostname

                if self.protocol == "both":
                    # Собираем оба протокола и объединяем
                    raw_data = self._collect_both_protocols(conn, device, hostname)
                else:
                    # Один протокол - парсим сырые данные
                    response = conn.send_command(command)
                    raw_data = self._parse_output(response.result, device)
                    # Нормализация через Domain Layer
                    raw_data = self._normalizer.normalize_dicts(
                        raw_data,
                        protocol=self.protocol,
                        hostname=hostname,
                        device_ip=device.host,
                    )

                logger.info(f"{hostname}: собрано {len(raw_data)} записей")
                return raw_data

        except (ConnectionError, AuthenticationError, TimeoutError) as e:
            logger.error(f"Ошибка подключения к {device.host}: {format_error_for_log(e)}")
            return []
        except Exception as e:
            logger.error(f"Неизвестная ошибка с {device.host}: {e}")
            return []

    def _collect_both_protocols(
        self, conn, device: Device, hostname: str
    ) -> List[Dict[str, Any]]:
        """
        Собирает LLDP и CDP, объединяет данные для получения полной информации.

        LLDP даёт: MAC адрес (chassis_id)
        CDP даёт: Platform, capabilities

        Использует Domain Layer для нормализации и объединения.

        Args:
            conn: Активное подключение
            device: Устройство
            hostname: Имя устройства

        Returns:
            List[Dict]: Объединённые нормализованные данные
        """
        lldp_data = []
        cdp_data = []

        # Собираем и нормализуем LLDP
        lldp_command = self.lldp_commands.get(device.platform)
        if lldp_command:
            response = conn.send_command(lldp_command)
            raw_lldp = self._parse_output(response.result, device)
            lldp_data = self._normalizer.normalize_dicts(
                raw_lldp, protocol="lldp", hostname=hostname, device_ip=device.host
            )

        # Собираем и нормализуем CDP
        cdp_command = self.cdp_commands.get(device.platform)
        if cdp_command:
            response = conn.send_command(cdp_command)
            raw_cdp = self._parse_output(response.result, device)
            cdp_data = self._normalizer.normalize_dicts(
                raw_cdp, protocol="cdp", hostname=hostname, device_ip=device.host
            )

        # Объединяем через Domain Layer
        return self._normalizer.merge_lldp_cdp(lldp_data, cdp_data)

    # Объединение LLDP/CDP перенесено в Domain Layer: core/domain/lldp.py → merge_lldp_cdp

    def _parse_output(
        self,
        output: str,
        device: Device,
    ) -> List[Dict[str, Any]]:
        """
        Парсит вывод команды show lldp/cdp neighbors.

        Возвращает СЫРЫЕ данные. Нормализация происходит в Domain Layer.

        Args:
            output: Сырой вывод команды
            device: Устройство

        Returns:
            List[Dict]: Сырые данные соседей
        """
        # Пробуем TextFSM
        if self.use_ntc:
            data = self._parse_with_textfsm(output, device)
            if data:
                return data

        # Fallback на regex
        if self.protocol == "cdp":
            return self._parse_cdp_regex(output)
        else:
            return self._parse_lldp_regex(output)

    def _parse_lldp_regex(self, output: str) -> List[Dict[str, Any]]:
        """
        Парсит LLDP вывод с помощью regex.

        Поддерживает два формата:
        1. С "Local Intf:" (новые IOS)
        2. Без "Local Intf:" (старые устройства) - берём local_interface из заголовка

        Args:
            output: Сырой вывод

        Returns:
            List[Dict]: Соседи
        """
        neighbors = []

        # Паттерны для Cisco IOS LLDP
        local_intf_pattern = re.compile(r"Local Intf:\s*(\S+)")
        chassis_id_pattern = re.compile(r"Chassis id:\s*(\S+)")
        port_id_pattern = re.compile(r"Port id:\s*(.+?)(?:\n|$)")
        port_desc_pattern = re.compile(r"Port Description:\s*(.+?)(?:\n|$)")
        system_name_pattern = re.compile(r"System Name:\s*(.+?)(?:\n|$)")
        system_desc_pattern = re.compile(r"System Description:\s*\n(.+?)(?:\n\n|\nTime)", re.DOTALL)
        mgmt_ip_pattern = re.compile(r"IP:\s*(\d+\.\d+\.\d+\.\d+)")

        # Определяем формат вывода
        has_local_intf = "Local Intf:" in output

        if has_local_intf:
            # Формат с "Local Intf:" - разбиваем по нему
            blocks = re.split(r"(?=Local Intf:)", output)
        else:
            # Формат без "Local Intf:" - разбиваем по разделителю блоков
            blocks = re.split(r"-{20,}", output)

        for block in blocks:
            if not block.strip():
                continue
            # Пропускаем блоки без данных соседа
            if "Chassis id:" not in block:
                continue

            neighbor = {}

            # Локальный интерфейс (может отсутствовать в старом формате)
            match = local_intf_pattern.search(block)
            if match:
                neighbor["local_interface"] = match.group(1)

            # Chassis ID (обычно MAC)
            match = chassis_id_pattern.search(block)
            if match:
                neighbor["chassis_id"] = match.group(1)

            # Port ID (remote port)
            match = port_id_pattern.search(block)
            if match:
                port_id = match.group(1).strip()
                # Port ID может быть числом, MAC или именем интерфейса
                neighbor["port_id"] = port_id

            # Port Description (может содержать имя интерфейса)
            match = port_desc_pattern.search(block)
            if match:
                port_desc = match.group(1).strip()
                if port_desc and port_desc != "- not advertised":
                    neighbor["port_description"] = port_desc

            # System Name (remote hostname)
            match = system_name_pattern.search(block)
            if match:
                sys_name = match.group(1).strip()
                if sys_name and sys_name != "- not advertised":
                    neighbor["remote_hostname"] = sys_name

            # System Description
            match = system_desc_pattern.search(block)
            if match:
                sys_desc = match.group(1).strip()
                if sys_desc:
                    neighbor["remote_description"] = sys_desc

            # Management IP
            match = mgmt_ip_pattern.search(block)
            if match:
                neighbor["remote_ip"] = match.group(1)

            # Определяем remote_port: port_description > port_id (если это интерфейс)
            if "port_description" in neighbor and neighbor["port_description"]:
                neighbor["remote_port"] = neighbor["port_description"]
            elif "port_id" in neighbor:
                neighbor["remote_port"] = neighbor["port_id"]

            # Добавляем только если есть хоть какие-то данные о соседе
            if neighbor.get("chassis_id") or neighbor.get("remote_hostname"):
                neighbors.append(neighbor)

        return neighbors

    def _parse_cdp_regex(self, output: str) -> List[Dict[str, Any]]:
        """
        Парсит CDP вывод с помощью regex.

        Args:
            output: Сырой вывод

        Returns:
            List[Dict]: Соседи
        """
        neighbors = []

        # Паттерны для CDP
        device_id_pattern = re.compile(r"Device ID:\s*(\S+)")
        local_intf_pattern = re.compile(r"Interface:\s*(\S+),")
        remote_intf_pattern = re.compile(r"Port ID.*?:\s*(\S+)")
        platform_pattern = re.compile(r"Platform:\s*(.+?),")
        ip_pattern = re.compile(r"IP address:\s*(\S+)")

        # Разбиваем по "Device ID:"
        blocks = re.split(r"(?=Device ID:)", output)

        for block in blocks:
            if not block.strip():
                continue

            neighbor = {}

            # Device ID (hostname)
            match = device_id_pattern.search(block)
            if match:
                neighbor["remote_hostname"] = match.group(1)

            # Локальный интерфейс
            match = local_intf_pattern.search(block)
            if match:
                neighbor["local_interface"] = match.group(1)

            # Удалённый интерфейс
            match = remote_intf_pattern.search(block)
            if match:
                neighbor["remote_port"] = match.group(1)

            # Платформа
            match = platform_pattern.search(block)
            if match:
                neighbor["remote_platform"] = match.group(1).strip()

            # IP адрес
            match = ip_pattern.search(block)
            if match:
                neighbor["remote_ip"] = match.group(1)

            if neighbor.get("local_interface"):
                neighbors.append(neighbor)

        return neighbors

    # Нормализация перенесена в Domain Layer: core/domain/lldp.py → LLDPNormalizer
