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
from typing import List, Dict, Any, Optional, Set, Tuple

from ntc_templates.parse import parse_output

from .base import BaseCollector
from ..core.device import Device
from ..core.models import MACEntry
from ..core.connection import get_ntc_platform
from ..core.logging import get_logger
from ..core.domain import MACNormalizer
from ..core.constants import (
    COLLECTOR_COMMANDS,
    CUSTOM_TEXTFSM_TEMPLATES,
    ONLINE_PORT_STATUSES,
    get_interface_aliases,
    normalize_interface_short,
    normalize_mac,
)
from ..core.exceptions import (
    ConnectionError,
    AuthenticationError,
    TimeoutError,
    format_error_for_log,
)
from ..parsers.textfsm_parser import TextFSMParser
from ..config import config as app_config

logger = get_logger(__name__)


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
        data = collector.collect(devices)  # List[Dict]

        # Или типизированные модели
        macs = collector.collect(devices)  # List[MACEntry]
    """

    # Типизированная модель
    model_class = MACEntry

    # Команды для разных платформ (из централизованного хранилища)
    platform_commands = COLLECTOR_COMMANDS.get("mac", {})

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

        # Domain Layer: нормализатор MAC-данных
        self._normalizer = MACNormalizer(
            mac_format=self.mac_format,
            normalize_interfaces=self.normalize_interfaces,
            exclude_interfaces=self.exclude_interfaces,
            exclude_vlans=self.exclude_vlans,
        )

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
                hostname = self._init_device_connection(conn, device)

                # Получаем MAC-таблицу
                mac_response = conn.send_command(command)
                mac_output = mac_response.result

                # --format parsed: только MAC-таблица, без доп. команд и нормализации
                if self._skip_normalize:
                    raw_data = self._parse_raw(mac_output, device)
                    self._add_metadata_to_rows(raw_data, hostname, device.host)
                    logger.info(f"{hostname}: собрано {len(raw_data)} MAC-адресов (parsed, без нормализации)")
                    return raw_data

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

                # Парсим MAC-таблицу (сырые данные)
                raw_data = self._parse_raw(mac_output, device)

                # Domain Layer: нормализация через MACNormalizer
                data = self._normalizer.normalize_dicts(
                    raw_data,
                    interface_status=interface_status,
                    hostname=hostname,
                    device_ip=device.host,
                )

                # Собираем sticky MAC из port-security (show running-config)
                if self.collect_port_security:
                    sticky_macs = self._collect_sticky_macs(conn, device, interface_status)
                    # Domain Layer: объединение через MACNormalizer
                    data = self._normalizer.merge_sticky_macs(
                        data, sticky_macs, hostname=hostname, device_ip=device.host
                    )
                    logger.debug(f"{hostname}: добавлено {len(sticky_macs)} sticky MACs")

                # Добавляем описание интерфейса
                if self.collect_descriptions:
                    for row in data:
                        iface = row.get("interface", "")
                        row["description"] = descriptions.get(iface, "")

                # Domain Layer: фильтрация trunk портов через MACNormalizer
                if not self.collect_trunk_ports:
                    data = self._normalizer.filter_trunk_ports(data, trunk_interfaces)

                # Domain Layer: финальная дедупликация
                data = self._normalizer.deduplicate(data)

                logger.info(f"{hostname}: собрано {len(data)} MAC-адресов")
                return data

        except Exception as e:
            return self._handle_collection_error(e, device)

    def _parse_raw(
        self,
        output: str,
        device: Device,
    ) -> List[Dict[str, Any]]:
        """
        Парсит вывод команды show mac address-table (сырые данные).

        Сначала пробует NTC Templates, затем fallback на regex.
        Возвращает сырые данные БЕЗ нормализации — нормализация в Domain Layer.

        Args:
            output: Сырой вывод команды
            device: Устройство

        Returns:
            List[Dict]: Сырые данные от парсера
        """
        # Пробуем NTC Templates
        if self.use_ntc:
            data = self._parse_with_ntc(output, device)
            if data:
                return data  # Сырые данные, нормализация в Domain Layer

        # Fallback на regex парсинг
        return self._parse_with_regex_raw(output, device)

    def _parse_with_regex_raw(
        self,
        output: str,
        device: Device,
    ) -> List[Dict[str, Any]]:
        """
        Парсит вывод с помощью regex (fallback).

        Возвращает сырые данные БЕЗ нормализации.

        Args:
            output: Сырой вывод
            device: Устройство

        Returns:
            List[Dict]: Сырые данные
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

        return data  # Сырые данные, нормализация в Domain Layer

    def _parse_output(
        self,
        output: str,
        device: "Device",
    ) -> List[Dict[str, Any]]:
        """
        Парсит вывод команды (реализация абстрактного метода).

        Примечание: MACCollector переопределяет _collect_from_device целиком,
        поэтому этот метод не вызывается напрямую. Реализован для совместимости
        с абстрактным классом BaseCollector.

        Args:
            output: Сырой вывод команды
            device: Устройство

        Returns:
            List[Dict]: Распарсенные данные
        """
        return self._parse_raw(output, device)

    # Методы _normalize_data, _deduplicate_final, _should_exclude_interface
    # перенесены в Domain Layer: core/domain/mac.py (MACNormalizer)

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

        Использует get_interface_aliases() для генерации всех возможных
        форматов имени интерфейса (полное, короткое, альтернативные).

        Args:
            status_map: Словарь статусов
            iface: Имя интерфейса
            status: Статус
        """
        # Получаем все возможные варианты написания интерфейса
        for alias in get_interface_aliases(iface):
            status_map[alias] = status

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
                    short_iface = normalize_interface_short(iface)
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
                        # Добавляем все возможные варианты написания
                        trunk_interfaces.update(get_interface_aliases(iface))

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
                    interface = normalize_interface_short(interface)

                # Нормализуем MAC
                normalized_mac = normalize_mac(mac, format=self.mac_format)
                mac = normalized_mac if normalized_mac else mac

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
