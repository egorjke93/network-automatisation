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
        """
        from ..core.connection import get_ntc_platform

        command = self._get_command(device)
        ntc_platform = get_ntc_platform(device.platform)

        if not command:
            logger.warning(f"Нет команды для {device.platform}")
            return []

        try:
            with self._conn_manager.connect(device, self.credentials) as conn:
                hostname = self._conn_manager.get_hostname(conn)
                device.metadata["hostname"] = hostname

                if self.protocol == "both":
                    # Собираем оба протокола и объединяем
                    data = self._collect_both_protocols(conn, device)
                else:
                    # Один протокол
                    response = conn.send_command(command)
                    data = self._parse_output(response.result, device)

                # Добавляем hostname и протокол к каждой записи
                for row in data:
                    row["hostname"] = hostname
                    row["device_ip"] = device.host
                    if "protocol" not in row:
                        row["protocol"] = self.protocol.upper()

                logger.info(f"{hostname}: собрано {len(data)} записей")
                return data

        except (ConnectionError, AuthenticationError, TimeoutError) as e:
            logger.error(f"Ошибка подключения к {device.host}: {format_error_for_log(e)}")
            return []
        except Exception as e:
            logger.error(f"Неизвестная ошибка с {device.host}: {e}")
            return []

    def _collect_both_protocols(self, conn, device: Device) -> List[Dict[str, Any]]:
        """
        Собирает LLDP и CDP, объединяет данные для получения полной информации.

        LLDP даёт: MAC адрес (chassis_id)
        CDP даёт: Platform, capabilities

        Returns:
            List[Dict]: Объединённые данные соседей
        """
        lldp_data = []
        cdp_data = []

        # Собираем LLDP
        lldp_command = self.lldp_commands.get(device.platform)
        if lldp_command:
            self.protocol = "lldp"
            response = conn.send_command(lldp_command)
            lldp_data = self._parse_output(response.result, device)
            for row in lldp_data:
                row["protocol"] = "LLDP"

        # Собираем CDP
        cdp_command = self.cdp_commands.get(device.platform)
        if cdp_command:
            self.protocol = "cdp"
            response = conn.send_command(cdp_command)
            cdp_data = self._parse_output(response.result, device)
            for row in cdp_data:
                row["protocol"] = "CDP"

        self.protocol = "both"

        # Если только один протокол вернул данные
        if not lldp_data:
            return cdp_data
        if not cdp_data:
            return lldp_data

        # Объединяем данные по local_interface
        return self._merge_lldp_cdp(lldp_data, cdp_data)

    def _merge_lldp_cdp(
        self,
        lldp_data: List[Dict[str, Any]],
        cdp_data: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Объединяет данные LLDP и CDP.

        Берёт LLDP как базу (есть MAC chassis_id) и дополняет из CDP:
        - remote_hostname (если LLDP не дал system_name)
        - remote_platform
        - remote_ip
        - local_interface (если LLDP не дал)

        Соседи сопоставляются по local_interface или remote_hostname.

        Protocol field:
        - BOTH: запись объединена из LLDP и CDP
        - LLDP: запись только из LLDP
        - CDP: запись только из CDP

        Args:
            lldp_data: Данные LLDP
            cdp_data: Данные CDP

        Returns:
            List[Dict]: Объединённые данные
        """
        # Создаём индексы CDP по local_interface и remote_hostname
        cdp_by_interface = {}
        cdp_by_hostname = {}
        for cdp_row in cdp_data:
            local_intf = normalize_interface_short(
                cdp_row.get("local_interface", ""), lowercase=True
            )
            if local_intf:
                cdp_by_interface[local_intf] = cdp_row
            # Также индексируем по hostname для fallback matching
            hostname = cdp_row.get("remote_hostname", "").lower()
            if hostname and not hostname.startswith("["):
                cdp_by_hostname[hostname] = cdp_row

        # Дополняем LLDP данными из CDP
        merged = []
        matched_cdp_intfs = set()  # Отслеживаем использованные CDP записи

        for lldp_row in lldp_data:
            local_intf = normalize_interface_short(
                lldp_row.get("local_interface", ""), lowercase=True
            )

            # Пробуем найти CDP по local_interface
            cdp_row = cdp_by_interface.get(local_intf) if local_intf else None

            # Fallback: ищем по remote_hostname если local_interface не сматчился
            if not cdp_row:
                lldp_hostname = lldp_row.get("remote_hostname", "").lower()
                if lldp_hostname and not lldp_hostname.startswith("["):
                    cdp_row = cdp_by_hostname.get(lldp_hostname)

            if cdp_row:
                # Дополняем пустые поля из CDP
                # ВАЖНО: hostname из CDP если LLDP не дал system_name
                lldp_hostname = lldp_row.get("remote_hostname", "")
                # Если hostname пустой или это MAC-адрес в квадратных скобках
                if not lldp_hostname or lldp_hostname.startswith("["):
                    cdp_hostname = cdp_row.get("remote_hostname", "")
                    if cdp_hostname and not cdp_hostname.startswith("["):
                        lldp_row["remote_hostname"] = cdp_hostname
                        # Переопределяем neighbor_type т.к. теперь есть hostname
                        lldp_row["neighbor_type"] = "hostname"
                        logger.debug(
                            f"Hostname из CDP для {local_intf}: {cdp_hostname}"
                        )

                if not lldp_row.get("remote_platform") and cdp_row.get("remote_platform"):
                    lldp_row["remote_platform"] = cdp_row["remote_platform"]

                if not lldp_row.get("remote_ip") and cdp_row.get("remote_ip"):
                    lldp_row["remote_ip"] = cdp_row["remote_ip"]

                # local_interface: если пустой в LLDP, берём из CDP
                if not lldp_row.get("local_interface") and cdp_row.get("local_interface"):
                    lldp_row["local_interface"] = cdp_row["local_interface"]

                # remote_port: проверяем что это интерфейс, а не hostname
                lldp_port = lldp_row.get("remote_port", "")
                cdp_port = cdp_row.get("remote_port", "")

                # Если LLDP port пустой или похож на hostname (нет / и много букв)
                if not lldp_port or (
                    "/" not in lldp_port and
                    len(lldp_port) > 15 and
                    not lldp_port[0:2].lower() in ("gi", "fa", "te", "et", "po")
                ):
                    if cdp_port:
                        lldp_row["remote_port"] = cdp_port
                        logger.debug(f"remote_port из CDP: {cdp_port} (LLDP был: {lldp_port})")

                # Отмечаем CDP запись как использованную
                cdp_local_intf = normalize_interface_short(
                    cdp_row.get("local_interface", ""), lowercase=True
                )
                if cdp_local_intf:
                    matched_cdp_intfs.add(cdp_local_intf)

                # Запись объединена из обоих источников
                lldp_row["protocol"] = "BOTH"
            # else: сохраняем protocol = "LLDP" (установлен ранее)

            merged.append(lldp_row)

        # Добавляем CDP соседей, которых нет в LLDP
        # protocol = "CDP" уже установлен ранее
        for intf, cdp_row in cdp_by_interface.items():
            if intf not in matched_cdp_intfs:
                merged.append(cdp_row)

        return merged

    def _parse_output(
        self,
        output: str,
        device: Device,
    ) -> List[Dict[str, Any]]:
        """
        Парсит вывод команды show lldp/cdp neighbors.

        Args:
            output: Сырой вывод команды
            device: Устройство

        Returns:
            List[Dict]: Список соседей
        """
        # Пробуем TextFSM
        if self.use_ntc:
            data = self._parse_with_textfsm(output, device)
            if data:
                return self._normalize_data(data)

        # Fallback на regex
        if self.protocol == "cdp":
            data = self._parse_cdp_regex(output)
        else:
            data = self._parse_lldp_regex(output)

        return self._normalize_data(data) if data else []

    def _parse_lldp_regex(self, output: str) -> List[Dict[str, Any]]:
        """
        Парсит LLDP вывод с помощью regex.

        Args:
            output: Сырой вывод

        Returns:
            List[Dict]: Соседи
        """
        neighbors = []

        # Разбиваем на блоки по соседям
        # Ищем паттерны для Cisco IOS
        local_intf_pattern = re.compile(r"Local Intf:\s*(\S+)")
        chassis_id_pattern = re.compile(r"Chassis id:\s*(\S+)")
        port_id_pattern = re.compile(r"Port id:\s*(\S+)")
        system_name_pattern = re.compile(r"System Name:\s*(.+)")
        system_desc_pattern = re.compile(r"System Description:\s*(.+)")

        # Разбиваем по "Local Intf:"
        blocks = re.split(r"(?=Local Intf:)", output)

        for block in blocks:
            if not block.strip():
                continue

            neighbor = {}

            # Локальный интерфейс
            match = local_intf_pattern.search(block)
            if match:
                neighbor["local_interface"] = match.group(1)

            # Chassis ID (обычно MAC)
            match = chassis_id_pattern.search(block)
            if match:
                neighbor["chassis_id"] = match.group(1)

            # Port ID
            match = port_id_pattern.search(block)
            if match:
                neighbor["remote_port"] = match.group(1)

            # System Name
            match = system_name_pattern.search(block)
            if match:
                neighbor["remote_hostname"] = match.group(1).strip()

            # System Description
            match = system_desc_pattern.search(block)
            if match:
                neighbor["remote_description"] = match.group(1).strip()

            if neighbor.get("local_interface"):
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

    def _normalize_data(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Нормализует данные соседей.

        Добавляет поле neighbor_type для определения способа идентификации:
        - hostname: Известно имя устройства
        - mac: Только MAC-адрес
        - ip: Только IP-адрес
        - unknown: Не удалось идентифицировать

        Args:
            data: Сырые данные

        Returns:
            List[Dict]: Нормализованные данные с типом соседа
        """
        # Приводим ключи к единому формату
        # Маппинг полей из NTC Templates к нашим стандартным именам
        key_mapping = {
            # Локальный интерфейс
            "local_intf": "local_interface",
            # Имя соседа
            "neighbor": "remote_hostname",
            "neighbor_name": "remote_hostname",
            "system_name": "remote_hostname",
            "device_id": "remote_hostname",
            # Порт соседа
            "neighbor_interface": "remote_port",
            "port_id": "remote_port",
            # IP соседа
            "mgmt_ip": "remote_ip",
            "mgmt_address": "remote_ip",
            "management_ip": "remote_ip",
            # Платформа
            "hardware": "remote_platform",
            "platform": "remote_platform",
            # MAC
            "chassis_id": "remote_mac",
        }

        normalized = []
        for row in data:
            new_row = {}
            for key, value in row.items():
                # Применяем маппинг ключей
                new_key = key_mapping.get(key.lower(), key.lower())
                new_row[new_key] = value

            # Определяем тип идентификации соседа
            new_row["neighbor_type"] = self._determine_neighbor_type(new_row)

            # Если hostname отсутствует, но есть MAC — используем MAC как идентификатор
            if not new_row.get("remote_hostname"):
                if new_row.get("remote_mac"):
                    new_row["remote_hostname"] = f"[MAC:{new_row['remote_mac']}]"
                elif new_row.get("remote_ip"):
                    new_row["remote_hostname"] = f"[IP:{new_row['remote_ip']}]"
                else:
                    new_row["remote_hostname"] = "[unknown]"

            normalized.append(new_row)

        return normalized

    def _determine_neighbor_type(self, neighbor: Dict[str, Any]) -> str:
        """
        Определяет тип идентификации соседа.

        Args:
            neighbor: Данные соседа

        Returns:
            str: Тип (hostname, mac, ip, unknown)
        """
        hostname = neighbor.get("remote_hostname", "")

        # Проверяем что hostname — это реальное имя, а не MAC/IP
        if hostname and not hostname.startswith("["):
            # Проверяем что это не просто MAC-адрес в поле hostname
            if not self._is_mac_address(hostname):
                return "hostname"

        if neighbor.get("remote_mac"):
            return "mac"

        if neighbor.get("remote_ip"):
            return "ip"

        return "unknown"

    def _is_mac_address(self, value: str) -> bool:
        """
        Проверяет является ли строка MAC-адресом.

        Args:
            value: Строка для проверки

        Returns:
            bool: True если это MAC
        """
        # Паттерны MAC-адресов
        mac_patterns = [
            r"^([0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}$",  # 00:11:22:33:44:55
            r"^([0-9a-fA-F]{4}\.){2}[0-9a-fA-F]{4}$",  # 0011.2233.4455
            r"^[0-9a-fA-F]{12}$",  # 001122334455
        ]

        for pattern in mac_patterns:
            if re.match(pattern, value):
                return True
        return False
