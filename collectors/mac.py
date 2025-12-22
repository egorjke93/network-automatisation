"""
Коллектор MAC-адресов.

Собирает MAC-адреса с сетевых устройств разных вендоров.
Поддерживает Cisco, Arista, Juniper, QTech.

Использует Scrapli для подключения и NTC Templates для парсинга.

Пример использования:
    collector = MACCollector()
    data = collector.collect(devices)

    # С фильтрацией полей
    collector = MACCollector(ntc_fields=["mac", "vlan", "interface"])

    # С определённым форматом MAC
    collector = MACCollector(mac_format="cisco")
"""

import re
import logging
from typing import List, Dict, Any, Optional, Set, Tuple

from ntc_templates.parse import parse_output

from .base import BaseCollector
from ..core.device import Device
from ..core.connection import ConnectionManager, get_ntc_platform
from ..core.constants import (
    INTERFACE_SHORT_MAP,
    ONLINE_PORT_STATUSES,
    normalize_interface_short,
    CUSTOM_TEXTFSM_TEMPLATES,
)
from ..parsers.textfsm_parser import TextFSMParser
from ..config import config as app_config

logger = logging.getLogger(__name__)


class MACCollector(BaseCollector):
    """
    Коллектор MAC-адресов.

    Собирает таблицу MAC-адресов с устройств.
    Поддерживает нормализацию MAC и интерфейсов.

    Attributes:
        mac_format: Формат MAC-адреса (cisco, ieee, unix)
        normalize_interfaces: Сокращать имена интерфейсов
        exclude_interfaces: Паттерны интерфейсов для исключения
        exclude_vlans: VLAN для исключения
        collect_descriptions: Собирать описания интерфейсов

    Example:
        collector = MACCollector(mac_format="ieee")
        data = collector.collect(devices)
    """

    # Команды для разных платформ
    platform_commands = {
        "cisco_ios": "show mac address-table",
        "cisco_iosxe": "show mac address-table",
        "cisco_nxos": "show mac address-table",
        "arista_eos": "show mac address-table",
        "juniper_junos": "show ethernet-switching table",
        "juniper": "show ethernet-switching table",
        "qtech": "show mac address-table",
        "qtech_qsw": "show mac address-table",
    }

    # Маппинг сокращений интерфейсов (из core.constants)
    INTERFACE_MAP = INTERFACE_SHORT_MAP

    def __init__(
        self,
        mac_format: str = "ieee",
        normalize_interfaces: bool = True,
        exclude_interfaces: Optional[List[str]] = None,
        exclude_vlans: Optional[List[int]] = None,
        collect_descriptions: bool = False,
        collect_trunk_ports: bool = False,
        collect_port_security: bool = False,
        **kwargs,
    ):
        """
        Инициализация коллектора MAC.

        Args:
            mac_format: Формат MAC (cisco, ieee, unix)
            normalize_interfaces: Сокращать имена интерфейсов
            exclude_interfaces: Regex паттерны интерфейсов для исключения
            exclude_vlans: Список VLAN для исключения
            collect_descriptions: Собирать описания интерфейсов
            collect_trunk_ports: Включать trunk порты
            collect_port_security: Собирать sticky MAC из port-security (offline устройства)
            **kwargs: Аргументы для BaseCollector
        """
        super().__init__(**kwargs)
        self.mac_format = mac_format
        self.normalize_interfaces = normalize_interfaces

        # Берём настройки из конфига если не переданы явно
        self.exclude_interfaces = exclude_interfaces or app_config.filters.exclude_interfaces
        self.exclude_vlans = exclude_vlans or app_config.filters.exclude_vlans

        self.collect_descriptions = collect_descriptions
        self.collect_trunk_ports = collect_trunk_ports
        self.collect_port_security = collect_port_security

        # Компилируем паттерны для исключения
        self._exclude_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.exclude_interfaces
        ]

        # Кэш для хранения статуса интерфейсов текущего устройства
        self._current_interface_status: Dict[str, str] = {}

        # Парсер для кастомных шаблонов
        self._textfsm_parser = TextFSMParser()

    def _collect_from_device(self, device: Device) -> List[Dict[str, Any]]:
        """
        Собирает MAC-адреса с одного устройства.

        Переопределяем базовый метод для дополнительных команд.

        Args:
            device: Устройство

        Returns:
            List[Dict]: Данные с устройства
        """
        command = self._get_command(device)
        ntc_platform = get_ntc_platform(device.platform)

        if not command:
            logger.warning(f"Нет команды для {device.platform}")
            return []

        try:
            with self._conn_manager.connect(device, self.credentials) as conn:
                hostname = self._conn_manager.get_hostname(conn)
                device.metadata["hostname"] = hostname

                # Получаем MAC-таблицу
                mac_response = conn.send_command(command)
                mac_output = mac_response.result

                # Получаем статус интерфейсов для определения online/offline
                # Используем "show interfaces status" - компактный вывод, быстрый парсинг
                status_response = conn.send_command("show interfaces status")
                interface_status = self._parse_interface_status(
                    status_response.result, ntc_platform
                )

                # Получаем описания интерфейсов если нужно
                descriptions = {}
                if self.collect_descriptions:
                    desc_response = conn.send_command("show interfaces description")
                    descriptions = self._parse_interface_descriptions(
                        desc_response.result, ntc_platform
                    )

                # Получаем trunk порты для фильтрации
                trunk_interfaces: Set[str] = set()
                if not self.collect_trunk_ports:
                    trunk_response = conn.send_command("show interfaces trunk")
                    trunk_interfaces = self._parse_trunk_interfaces(trunk_response.result)

                # Сохраняем статус интерфейсов для использования в _parse_output
                self._current_interface_status = interface_status

                # Парсим MAC-таблицу (статус берётся из self._current_interface_status)
                data = self._parse_output(mac_output, device)

                # Собираем sticky MAC из port-security (show running-config)
                if self.collect_port_security:
                    sticky_macs = self._collect_sticky_macs(conn, device, interface_status)
                    # Merge: добавляем sticky MACs которых нет в основной таблице
                    existing_macs = {row.get("mac", "").lower() for row in data}
                    for sticky in sticky_macs:
                        if sticky.get("mac", "").lower() not in existing_macs:
                            # Sticky MAC нет в активной таблице → offline
                            sticky["status"] = "offline"
                            data.append(sticky)
                    logger.debug(f"{hostname}: добавлено {len(sticky_macs)} sticky MACs")

                # Добавляем metadata к каждой записи
                for row in data:
                    row["hostname"] = hostname
                    row["device_ip"] = device.host

                    # Добавляем описание интерфейса
                    if self.collect_descriptions:
                        iface = row.get("interface", "")
                        row["description"] = descriptions.get(iface, "")

                    # Фильтруем trunk порты
                    if not self.collect_trunk_ports:
                        iface = row.get("interface", "")
                        if iface in trunk_interfaces:
                            row["_exclude"] = True

                # Исключаем помеченные записи
                data = [r for r in data if not r.get("_exclude")]

                # Финальная дедупликация по полному ключу (hostname, mac, vlan, interface)
                data = self._deduplicate_final(data)

                logger.info(f"{hostname}: собрано {len(data)} MAC-адресов")
                return data

        except Exception as e:
            logger.error(f"Ошибка подключения к {device.host}: {e}")
            return []

    def _parse_output(
        self,
        output: str,
        device: Device,
    ) -> List[Dict[str, Any]]:
        """
        Парсит вывод команды show mac address-table.

        Сначала пробует NTC Templates, затем fallback на regex.
        Статус интерфейсов берётся из self._current_interface_status.

        Args:
            output: Сырой вывод команды
            device: Устройство

        Returns:
            List[Dict]: Список MAC-записей
        """
        # Пробуем NTC Templates
        if self.use_ntc:
            data = self._parse_with_ntc(output, device)
            if data:
                return self._normalize_data(data)

        # Fallback на regex парсинг
        return self._parse_with_regex(output, device)

    def _parse_with_regex(
        self,
        output: str,
        device: Device,
    ) -> List[Dict[str, Any]]:
        """
        Парсит вывод с помощью regex (fallback).

        Args:
            output: Сырой вывод
            device: Устройство

        Returns:
            List[Dict]: Распарсенные данные
        """
        data = []

        # Универсальный regex для MAC-таблицы
        # Формат: VLAN  MAC  TYPE  INTERFACE
        pattern = re.compile(
            r"^\s*(\d+)\s+"  # VLAN
            r"([0-9a-fA-F.:]+)\s+"  # MAC
            r"(\w+)\s+"  # TYPE (DYNAMIC, STATIC, etc.)
            r"(\S+)",  # INTERFACE
            re.MULTILINE,
        )

        for match in pattern.finditer(output):
            vlan, mac, mac_type, interface = match.groups()

            data.append(
                {
                    "vlan": vlan,
                    "mac": mac,
                    "type": mac_type.lower(),
                    "interface": interface,
                }
            )

        return self._normalize_data(data)

    def _normalize_data(
        self,
        data: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Нормализует данные (MAC формат, интерфейсы, фильтрация).

        Статус online/offline определяется по состоянию порта:
        - Порт connected → online
        - Порт notconnect/disabled/etc → offline

        Статус интерфейсов берётся из self._current_interface_status.

        Args:
            data: Сырые данные

        Returns:
            List[Dict]: Нормализованные данные
        """
        interface_status = self._current_interface_status
        normalized = []
        seen_macs: Set[Tuple[str, str, str]] = set()  # Для дедупликации

        for row in data:
            # Нормализуем интерфейс
            interface = row.get("interface", row.get("destination_port", ""))
            if self.normalize_interfaces:
                interface = self._normalize_interface(interface)
            row["interface"] = interface

            # Проверяем исключения по интерфейсу
            if self._should_exclude_interface(interface):
                continue

            # Проверяем исключения по VLAN
            vlan = str(row.get("vlan", row.get("vlan_id", "")))
            if vlan:
                try:
                    if int(vlan) in self.exclude_vlans:
                        continue
                except ValueError:
                    pass
            row["vlan"] = vlan

            # Нормализуем MAC
            mac = row.get("mac", row.get("destination_address", ""))
            mac_normalized = self._normalize_mac_for_compare(mac)
            if mac:
                row["mac"] = self._normalize_mac(mac)

            # Дедупликация
            key = (mac_normalized, vlan, interface)
            if key in seen_macs:
                continue
            seen_macs.add(key)

            # Тип MAC: dynamic или static (sticky = static)
            raw_type = str(row.get("type", "")).lower()
            if "dynamic" in raw_type:
                row["type"] = "dynamic"
            else:
                row["type"] = "static"

            # Определяем status по состоянию порта
            port_status = interface_status.get(interface, "")
            if port_status.lower() in ONLINE_PORT_STATUSES:
                row["status"] = "online"
            elif port_status:
                row["status"] = "offline"
            else:
                # Если нет данных о порте — unknown
                row["status"] = "unknown"

            normalized.append(row)

        return normalized

    def _normalize_mac_for_compare(self, mac: str) -> str:
        """Нормализует MAC для сравнения (убирает разделители, lowercase)."""
        return re.sub(r"[.:\-]", "", mac.lower())

    def _deduplicate_final(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Финальная дедупликация по полному ключу.

        Удаляет полные дубликаты (hostname, mac, vlan, interface).
        Сохраняет первую запись с каждым ключом.

        Args:
            data: Список записей

        Returns:
            List[Dict]: Дедуплицированные записи
        """
        seen: Set[Tuple[str, str, str, str]] = set()
        result = []

        for row in data:
            hostname = row.get("hostname", "")
            mac = self._normalize_mac_for_compare(row.get("mac", ""))
            vlan = str(row.get("vlan", ""))
            interface = row.get("interface", "")

            key = (hostname, mac, vlan, interface)
            if key in seen:
                continue

            seen.add(key)
            result.append(row)

        duplicates_removed = len(data) - len(result)
        if duplicates_removed > 0:
            logger.debug(f"Удалено {duplicates_removed} дубликатов")

        return result

    def _should_exclude_interface(self, interface: str) -> bool:
        """
        Проверяет, нужно ли исключить интерфейс.

        Args:
            interface: Имя интерфейса

        Returns:
            bool: True если нужно исключить
        """
        for pattern in self._exclude_patterns:
            if pattern.match(interface):
                return True
        return False

    def _normalize_mac(self, mac: str) -> str:
        """
        Нормализует MAC-адрес в указанный формат.

        Форматы:
        - cisco: 0011.2233.4455
        - ieee: 00:11:22:33:44:55
        - unix: 00-11-22-33-44-55

        Args:
            mac: Исходный MAC

        Returns:
            str: Нормализованный MAC
        """
        # Убираем все разделители
        clean_mac = re.sub(r"[.:\-]", "", mac.lower())

        if len(clean_mac) != 12:
            return mac  # Возвращаем как есть если некорректный

        if self.mac_format == "cisco":
            # 0011.2233.4455
            return f"{clean_mac[0:4]}.{clean_mac[4:8]}.{clean_mac[8:12]}"
        elif self.mac_format == "unix":
            # 00-11-22-33-44-55
            return "-".join(clean_mac[i : i + 2] for i in range(0, 12, 2))
        else:
            # ieee (default): 00:11:22:33:44:55
            return ":".join(clean_mac[i : i + 2] for i in range(0, 12, 2))

    def _normalize_interface(self, interface: str) -> str:
        """
        Сокращает имя интерфейса.

        GigabitEthernet0/1 -> Gi0/1

        Args:
            interface: Полное имя интерфейса

        Returns:
            str: Сокращённое имя
        """
        for full_name, short_name in self.INTERFACE_MAP.items():
            if interface.startswith(full_name):
                return interface.replace(full_name, short_name, 1)
        return interface

    def _parse_interface_status(
        self,
        output: str,
        ntc_platform: str,
    ) -> Dict[str, str]:
        """
        Парсит статус интерфейсов из show interfaces status.

        Args:
            output: Вывод show interfaces status
            ntc_platform: Платформа для NTC

        Returns:
            Dict: {interface: status} например {"Gi0/1": "connected", "Gi0/2": "notconnect"}
        """
        status_map = {}

        try:
            parsed = parse_output(
                platform=ntc_platform,
                command="show interfaces status",
                data=output
            )

            for row in parsed:
                # NTC шаблон show interfaces status возвращает port и status
                # status уже в нужном формате: connected, notconnect, disabled, etc.
                iface = row.get("port", "")
                status = row.get("status", "").lower()

                if iface and status:
                    self._add_interface_status(status_map, iface, status)

        except Exception as e:
            logger.debug(f"Ошибка парсинга interface status через NTC: {e}")
            # Fallback на regex парсинг
            status_map = self._parse_interface_status_regex(output)

        return status_map

    def _add_interface_status(
        self,
        status_map: Dict[str, str],
        iface: str,
        status: str,
    ) -> None:
        """
        Добавляет статус интерфейса во все возможные варианты имени.

        Покрывает все возможные форматы интерфейсов:
        - GigabitEthernet0/1, Gi0/1, Gig0/1
        - FastEthernet0/1, Fa0/1
        - TenGigabitEthernet0/1, Te0/1, Ten0/1
        - Ethernet0/0, Et0/0, Eth0/0
        - Port-channel1, Po1

        Args:
            status_map: Словарь статусов
            iface: Имя интерфейса
            status: Статус
        """
        # Убираем возможные пробелы в имени (Gi 0/1 -> Gi0/1)
        iface = iface.replace(" ", "")
        status_map[iface] = status

        # Добавляем сокращённую версию
        short_iface = self._normalize_interface(iface)
        if short_iface != iface:
            status_map[short_iface] = status

        # Добавляем альтернативные сокращения для разных форматов
        if iface.startswith("Ethernet"):
            suffix = iface[8:]
            status_map[f"Et{suffix}"] = status
            status_map[f"Eth{suffix}"] = status
        elif iface.startswith("GigabitEthernet"):
            suffix = iface[15:]
            status_map[f"Gi{suffix}"] = status
            status_map[f"Gig{suffix}"] = status
        elif iface.startswith("FastEthernet"):
            suffix = iface[12:]
            status_map[f"Fa{suffix}"] = status
        elif iface.startswith("TenGigabitEthernet"):
            suffix = iface[18:]
            status_map[f"Te{suffix}"] = status
            status_map[f"Ten{suffix}"] = status
        elif iface.startswith("TwentyFiveGigE"):
            suffix = iface[14:]
            status_map[f"Twe{suffix}"] = status
        elif iface.startswith("FortyGigabitEthernet"):
            suffix = iface[20:]
            status_map[f"Fo{suffix}"] = status
        elif iface.startswith("HundredGigE"):
            suffix = iface[11:]
            status_map[f"Hu{suffix}"] = status
        elif iface.startswith("Port-channel"):
            suffix = iface[12:]
            status_map[f"Po{suffix}"] = status
        # Обратные маппинги (короткие -> полные)
        elif iface.startswith("Gig"):
            suffix = iface[3:]
            status_map[f"GigabitEthernet{suffix}"] = status
            status_map[f"Gi{suffix}"] = status
        elif iface.startswith("Gi"):
            suffix = iface[2:]
            status_map[f"GigabitEthernet{suffix}"] = status
            status_map[f"Gig{suffix}"] = status
        elif iface.startswith("Fa"):
            suffix = iface[2:]
            status_map[f"FastEthernet{suffix}"] = status
        elif iface.startswith("Ten"):
            suffix = iface[3:]
            status_map[f"TenGigabitEthernet{suffix}"] = status
            status_map[f"Te{suffix}"] = status
        elif iface.startswith("Te"):
            suffix = iface[2:]
            status_map[f"TenGigabitEthernet{suffix}"] = status
            status_map[f"Ten{suffix}"] = status
        elif iface.startswith("Eth"):
            suffix = iface[3:]
            status_map[f"Ethernet{suffix}"] = status
            status_map[f"Et{suffix}"] = status
        elif iface.startswith("Et"):
            suffix = iface[2:]
            status_map[f"Ethernet{suffix}"] = status
            status_map[f"Eth{suffix}"] = status
        elif iface.startswith("Twe"):
            suffix = iface[3:]
            status_map[f"TwentyFiveGigE{suffix}"] = status
        elif iface.startswith("Fo"):
            suffix = iface[2:]
            status_map[f"FortyGigabitEthernet{suffix}"] = status
        elif iface.startswith("Hu"):
            suffix = iface[2:]
            status_map[f"HundredGigE{suffix}"] = status
        elif iface.startswith("Po"):
            suffix = iface[2:]
            status_map[f"Port-channel{suffix}"] = status

    def _parse_interface_status_regex(self, output: str) -> Dict[str, str]:
        """
        Fallback regex парсинг статуса интерфейсов из show interfaces status.

        Формат вывода:
        Port      Name               Status       Vlan       Duplex  Speed Type
        Gi0/1     Description        connected    1          a-full  auto  10/100/1000BaseTX
        Gi0/2                        notconnect   1          auto    auto  10/100/1000BaseTX

        Args:
            output: Вывод show interfaces status

        Returns:
            Dict: {interface: status}
        """
        status_map = {}

        # Regex для парсинга строки show interfaces status
        # Port может быть Gi0/1, Fa0/1, Te0/1, Et0/1 и т.д.
        # Status: connected, notconnect, disabled, err-disabled, etc.
        pattern = re.compile(
            r"^((?:Gi|Fa|Te|Et|Po|Vl)\S+)\s+"  # Port (Gi0/1, Fa0/1, etc.)
            r"(?:\S.*?)?\s+"  # Name (optional, может быть пустым)
            r"(connected|notconnect|disabled|err-disabled|inactive|suspended)\s+",  # Status
            re.MULTILINE | re.IGNORECASE
        )

        for match in pattern.finditer(output):
            iface = match.group(1)
            status = match.group(2).lower()
            self._add_interface_status(status_map, iface, status)

        return status_map

    def _parse_interface_descriptions(
        self,
        output: str,
        ntc_platform: str,
    ) -> Dict[str, str]:
        """
        Парсит описания интерфейсов.

        Args:
            output: Вывод show interfaces description
            ntc_platform: Платформа для NTC

        Returns:
            Dict: {interface: description}
        """
        descriptions = {}

        try:
            parsed = parse_output(
                platform=ntc_platform,
                command="show interfaces description",
                data=output
            )

            for row in parsed:
                iface = row.get("interface", row.get("port", ""))
                desc = row.get("description", row.get("descrip", ""))
                if iface:
                    descriptions[iface] = desc
                    # Добавляем сокращённую версию
                    short_iface = self._normalize_interface(iface)
                    if short_iface != iface:
                        descriptions[short_iface] = desc

        except Exception as e:
            logger.debug(f"Ошибка парсинга описаний интерфейсов: {e}")

        return descriptions

    def _parse_trunk_interfaces(self, output: str) -> Set[str]:
        """
        Парсит trunk интерфейсы.

        Args:
            output: Вывод show interfaces trunk

        Returns:
            Set: Множество trunk интерфейсов
        """
        trunk_interfaces = set()
        in_port_section = False

        for line in output.splitlines():
            line = line.strip()

            if not line:
                continue

            # Начало секции с портами
            if line.startswith("Port") and "Mode" in line:
                in_port_section = True
                continue

            # Другая секция - выходим
            if "Vlans allowed" in line or "Vlans in spanning" in line:
                break

            # Парсим trunk порт
            if in_port_section:
                parts = line.split()
                if parts:
                    iface = parts[0]
                    if re.match(r"^(Gi|Fa|Te|Eth|Po)", iface, re.IGNORECASE):
                        trunk_interfaces.add(iface)
                        # Добавляем полное имя тоже
                        for full, short in self.INTERFACE_MAP.items():
                            if iface.startswith(short):
                                full_iface = iface.replace(short, full, 1)
                                trunk_interfaces.add(full_iface)
                                break

        return trunk_interfaces

    def _collect_sticky_macs(
        self,
        conn,
        device: Device,
        interface_status: Dict[str, str],
    ) -> List[Dict[str, Any]]:
        """
        Собирает sticky MAC из port-security (show running-config).

        Парсит конфигурацию интерфейсов для извлечения sticky MAC-адресов.
        Используется для обнаружения offline устройств.

        Args:
            conn: Активное подключение
            device: Устройство
            interface_status: Статус интерфейсов {interface: status}

        Returns:
            List[Dict]: Список sticky MAC записей
        """
        sticky_macs = []
        platform = device.platform

        # Проверяем есть ли шаблон для этой платформы
        template_key = (platform, "port-security")
        if template_key not in CUSTOM_TEXTFSM_TEMPLATES:
            # Пробуем cisco_ios как fallback
            template_key = ("cisco_ios", "port-security")
            if template_key not in CUSTOM_TEXTFSM_TEMPLATES:
                logger.debug(f"Нет шаблона port-security для {platform}")
                return []

        try:
            # Получаем show running-config
            response = conn.send_command("show running-config")
            output = response.result

            # Парсим через кастомный шаблон
            parsed = self._textfsm_parser.parse(output, platform, "port-security")

            if not parsed:
                return []

            for row in parsed:
                interface = row.get("interface", "")
                mac = row.get("mac", "")
                vlan = row.get("vlan", "")
                mac_type = row.get("type", "sticky")

                if not interface or not mac:
                    continue

                # Нормализуем интерфейс
                if self.normalize_interfaces:
                    interface = self._normalize_interface(interface)

                # Нормализуем MAC
                mac = self._normalize_mac(mac)

                # Определяем статус порта
                port_status = interface_status.get(interface, "")
                if port_status.lower() in ONLINE_PORT_STATUSES:
                    status = "online"
                elif port_status:
                    status = "offline"
                else:
                    status = "unknown"

                sticky_macs.append({
                    "interface": interface,
                    "mac": mac,
                    "vlan": vlan,
                    "type": mac_type,
                    "status": status,
                })

            logger.debug(f"Найдено {len(sticky_macs)} sticky MAC из port-security")

        except Exception as e:
            logger.warning(f"Ошибка сбора sticky MAC: {e}")

        return sticky_macs
