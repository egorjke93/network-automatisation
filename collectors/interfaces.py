"""
Коллектор информации об интерфейсах.

Собирает статус, описание, MAC, IP-адреса, ошибки интерфейсов.
Включает Vlan SVI интерфейсы с IP-адресами.
Поддерживает Cisco, Arista, Juniper.

Пример использования:
    collector = InterfaceCollector()
    data = collector.collect(devices)

    # Только определённые поля
    collector = InterfaceCollector(
        textfsm_fields=["interface", "status", "ip_address"]
    )
"""

import re
from typing import List, Dict, Any, Optional

from .base import BaseCollector
from ..core.device import Device
from ..core.models import Interface
from ..core.logging import get_logger
from ..core.exceptions import (
    ConnectionError,
    AuthenticationError,
    TimeoutError,
    format_error_for_log,
)
from ..core.domain.interface import InterfaceNormalizer
from ..core.constants import COLLECTOR_COMMANDS
from ..core.constants.commands import SECONDARY_COMMANDS
from ..core.constants.interfaces import get_interface_aliases, normalize_interface_full

logger = get_logger(__name__)


class InterfaceCollector(BaseCollector):
    """
    Коллектор информации об интерфейсах.

    Собирает статус, описание, VLAN, ошибки.

    Attributes:
        include_errors: Собирать статистику ошибок

    Example:
        collector = InterfaceCollector(include_errors=True)
        interfaces = collector.collect(devices)  # List[Dict]

        # Или типизированные модели
        interfaces = collector.collect_models(devices)  # List[Interface]
        for intf in interfaces:
            print(intf.name, intf.status, intf.ip_address)
    """

    # Типизированная модель для collect_models()
    model_class = Interface

    # Команды для разных платформ (из централизованного хранилища)
    platform_commands = COLLECTOR_COMMANDS.get("interfaces", {})

    # Вторичные команды (из централизованного хранилища commands.py)
    error_commands = SECONDARY_COMMANDS.get("interface_errors", {})
    lag_commands = SECONDARY_COMMANDS.get("lag", {})
    switchport_commands = SECONDARY_COMMANDS.get("switchport", {})
    media_type_commands = SECONDARY_COMMANDS.get("media_type", {})

    def __init__(
        self,
        include_errors: bool = False,
        collect_lag_info: bool = True,
        collect_switchport: bool = True,
        collect_media_type: bool = True,
        **kwargs,
    ):
        """
        Инициализация коллектора интерфейсов.

        Args:
            include_errors: Собирать статистику ошибок
            collect_lag_info: Собирать информацию о LAG membership
            collect_switchport: Собирать режим switchport (access/trunk)
            collect_media_type: Собирать точный media_type (NX-OS: show interface status, QTech: show interface transceiver)
            **kwargs: Аргументы для BaseCollector
        """
        super().__init__(**kwargs)
        self.include_errors = include_errors
        self.collect_lag_info = collect_lag_info
        self.collect_switchport = collect_switchport
        self.collect_media_type = collect_media_type
        self._normalizer = InterfaceNormalizer()
    
    def _parse_output(
        self,
        output: str,
        device: Device,
    ) -> List[Dict[str, Any]]:
        """
        Парсит вывод команды show interfaces.

        Возвращает СЫРЫЕ данные. Нормализация происходит в Domain Layer.

        Args:
            output: Сырой вывод команды
            device: Устройство

        Returns:
            List[Dict]: Сырые данные интерфейсов
        """
        # Пробуем TextFSM
        if self.use_ntc:
            data = self._parse_with_textfsm(output, device)
            if data:
                return data

        # Fallback на regex
        return self._parse_with_regex_raw(output, device)
    
    def _parse_with_regex_raw(
        self,
        output: str,
        device: Device,
    ) -> List[Dict[str, Any]]:
        """
        Парсит вывод show interfaces с помощью regex (fallback).

        Возвращает СЫРЫЕ данные. Нормализация в Domain Layer.

        Args:
            output: Сырой вывод
            device: Устройство

        Returns:
            List[Dict]: Сырые данные интерфейсов
        """
        interfaces = []
        current_interface = None

        # Паттерны для Cisco IOS "show interfaces"
        intf_pattern = re.compile(r"^(\S+)\s+is\s+(up|down|administratively down)", re.MULTILINE)
        ip_pattern = re.compile(r"Internet address is (\d+\.\d+\.\d+\.\d+)/(\d+)")
        mac_pattern = re.compile(r"address is ([0-9a-fA-F]{4}\.[0-9a-fA-F]{4}\.[0-9a-fA-F]{4})")
        desc_pattern = re.compile(r"Description: (.+)")
        mtu_pattern = re.compile(r"MTU (\d+) bytes")

        for line in output.splitlines():
            # Новый интерфейс
            intf_match = intf_pattern.match(line)
            if intf_match:
                if current_interface:
                    interfaces.append(current_interface)
                current_interface = {
                    "interface": intf_match.group(1),
                    "link_status": intf_match.group(2),  # Сырой статус
                    "ip_address": "",
                    "prefix_length": "",
                    "mac": "",
                    "description": "",
                    "mtu": "",
                }
                continue

            if current_interface:
                # IP-адрес
                ip_match = ip_pattern.search(line)
                if ip_match:
                    current_interface["ip_address"] = ip_match.group(1)
                    current_interface["prefix_length"] = ip_match.group(2)

                # MAC-адрес
                mac_match = mac_pattern.search(line)
                if mac_match:
                    current_interface["mac"] = mac_match.group(1)

                # Description
                desc_match = desc_pattern.search(line)
                if desc_match:
                    current_interface["description"] = desc_match.group(1).strip()

                # MTU
                mtu_match = mtu_pattern.search(line)
                if mtu_match:
                    current_interface["mtu"] = mtu_match.group(1)

        # Последний интерфейс
        if current_interface:
            interfaces.append(current_interface)

        return interfaces
    
    # Нормализация перенесена в Domain Layer: core/domain/interface.py (InterfaceNormalizer)

    def _collect_from_device(self, device: Device) -> List[Dict[str, Any]]:
        """
        Собирает данные с одного устройства.

        Архитектура:
        1. Collector: парсинг (TextFSM/regex) → сырые данные
        2. Domain (InterfaceNormalizer): нормализация и обогащение

        Args:
            device: Устройство

        Returns:
            List[Dict]: Нормализованные данные с устройства
        """
        command = self._get_command(device)
        if not command:
            logger.warning(f"Нет команды для {device.platform}")
            return []

        try:
            with self._conn_manager.connect(device, self.credentials) as conn:
                hostname = self._init_device_connection(conn, device)

                # 1. Парсим основную команду show interfaces (СЫРЫЕ данные)
                response = conn.send_command(command)
                raw_data = self._parse_output(response.result, device)

                # --format parsed: сырые данные TextFSM, без нормализации
                if self._skip_normalize:
                    self._add_metadata_to_rows(raw_data, hostname, device.host)
                    logger.info(f"{hostname}: собрано {len(raw_data)} интерфейсов (parsed, без нормализации)")
                    return raw_data

                # 2. Domain Layer: нормализация через InterfaceNormalizer
                data = self._normalizer.normalize_dicts(
                    raw_data, hostname=hostname, device_ip=device.host
                )

                # 3. Собираем дополнительные данные для обогащения
                lag_membership = {}
                if self.collect_lag_info:
                    lag_cmd = self.lag_commands.get(device.platform)
                    if lag_cmd:
                        try:
                            lag_response = conn.send_command(lag_cmd)
                            # QTech: отдельный парсер для show aggregatePort summary
                            if device.platform in ("qtech", "qtech_qsw"):
                                lag_membership = self._parse_lag_membership_qtech(
                                    lag_response.result,
                                )
                            else:
                                lag_membership = self._parse_lag_membership(
                                    lag_response.result,
                                    device.platform,
                                    lag_cmd,
                                )
                        except Exception as e:
                            logger.debug(f"Ошибка получения LAG info: {e}")

                switchport_modes = {}
                if self.collect_switchport:
                    sw_cmd = self.switchport_commands.get(device.platform)
                    logger.debug(f"{hostname}: collect_switchport={self.collect_switchport}, platform={device.platform}, sw_cmd={sw_cmd}")
                    if sw_cmd:
                        try:
                            sw_response = conn.send_command(sw_cmd)
                            switchport_modes = self._parse_switchport_modes(
                                sw_response.result,
                                device.platform,
                                sw_cmd,
                            )
                            logger.debug(f"{hostname}: switchport_modes содержит {len(switchport_modes)} записей")
                            if switchport_modes:
                                # Показываем первые 3 для отладки
                                sample = list(switchport_modes.items())[:3]
                                logger.debug(f"{hostname}: пример switchport_modes: {sample}")
                        except Exception as e:
                            logger.warning(f"{hostname}: ошибка получения switchport info: {e}")
                    else:
                        logger.debug(f"{hostname}: нет команды switchport для платформы {device.platform}")

                media_types = {}
                if self.collect_media_type:
                    mt_cmd = self.media_type_commands.get(device.platform)
                    if mt_cmd:
                        try:
                            mt_response = conn.send_command(mt_cmd)
                            media_types = self._parse_media_types(
                                mt_response.result,
                                device.platform,
                                mt_cmd,
                            )
                        except Exception as e:
                            logger.debug(f"Ошибка получения media_type info: {e}")

                # 4. Domain Layer: обогащение данных
                if lag_membership:
                    data = self._normalizer.enrich_with_lag(data, lag_membership)

                if switchport_modes:
                    data = self._normalizer.enrich_with_switchport(
                        data, switchport_modes, lag_membership
                    )

                if media_types:
                    data = self._normalizer.enrich_with_media_type(data, media_types)

                logger.info(f"{hostname}: собрано {len(data)} интерфейсов")
                return data

        except Exception as e:
            return self._handle_collection_error(e, device)

    def _parse_lag_membership(
        self,
        output: str,
        platform: str,
        command: str = "show etherchannel summary",
    ) -> Dict[str, str]:
        """
        Парсит show etherchannel/port-channel summary для определения LAG membership.

        Args:
            output: Вывод команды
            platform: Платформа устройства (NTCParser сам ищет кастомный шаблон и NTC fallback)
            command: Команда для парсера (show etherchannel summary / show port-channel summary)

        Returns:
            Dict: {member_interface: lag_interface} например {"Gi0/1": "Po1", "Eth1/1": "Po1"}
        """
        membership = {}

        try:
            parsed = self._parser.parse(
                output=output,
                platform=platform,
                command=command,
                normalize=False,
            ) if self._parser else []

            for row in parsed:
                # NTC шаблон возвращает: po_name, po_status, protocol, member_interface
                lag_name = row.get("po_name", row.get("bundle_name", ""))
                members = row.get("member_interface", row.get("member_ports", []))

                if not lag_name:
                    continue

                # Нормализуем имя LAG
                if not lag_name.lower().startswith("po"):
                    lag_name = f"Po{lag_name}"

                # members может быть строкой или списком
                if isinstance(members, str):
                    members = [members] if members else []

                for member in members:
                    if member:
                        # Убираем статус из имени (Gi0/1(P) -> Gi0/1, Eth1/1(P) -> Eth1/1)
                        member_clean = re.sub(r'\([^)]*\)', '', member).strip()
                        if member_clean:
                            self._add_lag_member_aliases(membership, member_clean, lag_name)

        except Exception as e:
            logger.debug(f"Ошибка парсинга LAG через NTC: {e}")
            # Fallback на regex
            membership = self._parse_lag_membership_regex(output)

        return membership

    def _add_lag_member_aliases(
        self, membership: Dict[str, str], member: str, lag_name: str,
    ) -> None:
        """Добавляет member и все его алиасы в LAG membership dict."""
        membership[member] = lag_name
        # Все алиасы из constants (HundredGigE0/55, HundredGigabitEthernet0/55, ...)
        for alias in get_interface_aliases(member):
            membership[alias] = lag_name
            # Вариант с пробелом перед номером (QTech: HundredGigabitEthernet 0/55)
            spaced = re.sub(r'(\D)(\d)', r'\1 \2', alias, count=1)
            if spaced != alias:
                membership[spaced] = lag_name

    def _parse_lag_membership_qtech(self, output: str) -> Dict[str, str]:
        """
        Парсит show aggregatePort summary для QTech.

        TextFSM шаблон парсит текст → этот метод строит dict {member: lag}.

        Args:
            output: Вывод команды show aggregatePort summary

        Returns:
            Dict: {member_interface: lag_interface}
                  Например {"Hu0/55": "Ag1", "HundredGigabitEthernet 0/55": "Ag1"}
        """
        membership = {}

        # Сначала пробуем кастомный TextFSM шаблон
        if self._parser:
            try:
                parsed = self._parser.parse(
                    output=output,
                    platform="qtech",
                    command="show aggregatePort summary",
                    normalize=False,
                )
                for row in parsed:
                    lag_name = row.get("aggregate_port", "")
                    ports_str = row.get("ports", "")
                    if not lag_name or not ports_str:
                        continue

                    # Парсим порты: "Hu0/55  ,Hu0/56" → ["Hu0/55", "Hu0/56"]
                    members = [p.strip() for p in ports_str.split(",") if p.strip()]
                    for member in members:
                        self._add_lag_member_aliases(membership, member, lag_name)

                if membership:
                    return membership
            except Exception as e:
                logger.debug(f"Ошибка парсинга QTech LAG через TextFSM: {e}")

        # Fallback на regex
        pattern = re.compile(
            r"^(Ag\d+)\s+\d+\s+\S+\s+\S+\s+\S+\s+(.+)$",
            re.MULTILINE,
        )
        for match in pattern.finditer(output):
            lag_name = match.group(1)
            members = [p.strip() for p in match.group(2).split(",") if p.strip()]
            for member in members:
                self._add_lag_member_aliases(membership, member, lag_name)

        return membership

    def _parse_lag_membership_regex(self, output: str) -> Dict[str, str]:
        """
        Fallback regex парсинг LAG membership.

        Формат вывода show etherchannel summary:
        Group  Port-channel  Protocol    Ports
        ------+-------------+-----------+-----------------------------------------------
        1      Po1(SU)         LACP      Gi0/1(P)    Gi0/2(P)

        Args:
            output: Вывод show etherchannel summary

        Returns:
            Dict: {member_interface: lag_interface}
        """
        membership = {}

        # Ищем строки с Port-channel и member портами
        # Po1(SU)  LACP  Gi0/1(P) Gi0/2(P)
        pattern = re.compile(
            r"(Po\d+)\([^)]*\)\s+"  # Po1(SU)
            r"(?:LACP|PAgP|ON|-)\s+"  # Protocol
            r"(.+)$",  # Member ports
            re.MULTILINE
        )

        for match in pattern.finditer(output):
            lag_name = match.group(1)  # Po1
            members_str = match.group(2)

            # Парсим member порты: Gi0/1(P) Twe1/0/27(P) Hu1/0/51(P) Eth1/1(P)
            member_pattern = re.compile(r"([A-Za-z]+[\d/]+)\([^)]*\)")
            for member_match in member_pattern.finditer(members_str):
                member = member_match.group(1)
                self._add_lag_member_aliases(membership, member, lag_name)

        return membership

    def _parse_switchport_modes(
        self,
        output: str,
        platform: str,
        command: str = "show interfaces switchport",
    ) -> Dict[str, Dict[str, str]]:
        """
        Парсит show interfaces/interface switchport для определения режимов портов.

        NTCParser.parse() сам обрабатывает приоритеты:
        1. Кастомный TextFSM шаблон (QTech и другие нестандартные)
        2. NTC Templates с маппингом платформы (Cisco, Arista)
        3. Regex fallback (если парсер не справился)

        Args:
            output: Вывод команды
            platform: Платформа устройства (qtech, cisco_nxos, cisco_ios, etc.)
            command: Команда (show interfaces switchport / show interface switchport)

        Returns:
            Dict: {interface: {mode, native_vlan, access_vlan, tagged_vlans}}
        """
        modes = {}

        # NTCParser.parse() сам ищет кастомный шаблон, потом NTC fallback
        if self._parser:
            try:
                parsed = self._parser.parse(
                    output=output,
                    platform=platform,
                    command=command,
                    normalize=False,
                )
                if parsed:
                    # Domain layer нормализует switchport данные
                    modes = self._normalizer.normalize_switchport_data(parsed, platform)
                    if modes:
                        return modes
            except Exception as e:
                logger.debug(f"Парсинг switchport не сработал: {e}")

        # Fallback на regex
        modes = self._parse_switchport_modes_regex(output)
        return modes

    def _parse_switchport_modes_regex(self, output: str) -> Dict[str, Dict[str, str]]:
        """
        Fallback regex парсинг switchport modes.

        Формат вывода show interfaces switchport:
        Name: Gi0/1
        Administrative Mode: trunk
        Access Mode VLAN: 1 (default)
        Trunking Native Mode VLAN: 1 (default)

        Args:
            output: Вывод show interfaces switchport

        Returns:
            Dict: {interface: {mode, native_vlan, access_vlan}}
        """
        modes = {}
        current_interface = None
        current_data = {}

        for line in output.splitlines():
            line = line.strip()

            # Новый интерфейс
            if line.startswith("Name:"):
                if current_interface and current_data:
                    modes[current_interface] = current_data
                current_interface = line.split(":", 1)[1].strip()
                current_data = {"mode": "", "native_vlan": "", "access_vlan": ""}
                continue

            if current_interface:
                # Administrative Mode: trunk / access / dynamic
                if "Administrative Mode:" in line:
                    mode = line.split(":", 1)[1].strip().lower()
                    if "access" in mode:
                        current_data["mode"] = "access"
                    elif "trunk" in mode or "dynamic" in mode:
                        # По умолчанию tagged-all, если не указаны конкретные VLAN
                        current_data["mode"] = "tagged-all"

                # Trunking VLANs Enabled: ALL / 1,10,20
                elif "Trunking VLANs Enabled:" in line:
                    vlans = line.split(":", 1)[1].strip().lower()
                    if vlans != "all" and vlans and current_data.get("mode") in ("tagged-all", "tagged"):
                        # Есть конкретные VLAN - это tagged, не tagged-all
                        current_data["mode"] = "tagged"

                # Access Mode VLAN: 1
                elif "Access Mode VLAN:" in line:
                    parts = line.split(":", 1)[1].strip().split()
                    if parts:
                        current_data["access_vlan"] = parts[0]

                # Trunking Native Mode VLAN: 1
                elif "Native Mode VLAN:" in line:
                    parts = line.split(":", 1)[1].strip().split()
                    if parts:
                        current_data["native_vlan"] = parts[0]

        # Последний интерфейс
        if current_interface and current_data:
            modes[current_interface] = current_data

        return modes

    def _parse_media_types(
        self,
        output: str,
        platform: str,
        command: str = "show interface status",
    ) -> Dict[str, str]:
        """
        Парсит вывод команды для получения media_type.

        Источники media_type по платформам:
        - NX-OS: `show interface status` → поля NTC: port, type
        - QTech: `show interface transceiver` → поля TextFSM: INTERFACE, TYPE

        Args:
            output: Вывод команды (show interface status или show interface transceiver)
            platform: Платформа устройства (NTCParser сам ищет кастомный шаблон и NTC fallback)
            command: Команда для парсера

        Returns:
            Dict: {interface: media_type} например {"Ethernet1/1": "10Gbase-LR"}
                  или {"TFGigabitEthernet 0/1": "10GBASE-SR-SFP+"}
        """
        media_types = {}

        try:
            parsed = self._parser.parse(
                output=output,
                platform=platform,
                command=command,
                normalize=False,
            ) if self._parser else []

            for row in parsed:
                # NTC (show interface status): port, name, status, vlan, duplex, speed, type
                # TextFSM (show interface transceiver): INTERFACE, TYPE, SERIAL, BANDWIDTH
                port = row.get("port") or row.get("INTERFACE", "")
                media_type = row.get("type") or row.get("TYPE", "")

                if not port:
                    continue

                # Пропускаем пустые и "--"
                if not media_type or media_type == "--":
                    continue

                # Добавляем все варианты имени через единый источник из constants
                for alias in get_interface_aliases(port):
                    media_types[alias] = media_type

        except Exception as e:
            logger.debug(f"Ошибка парсинга media_type через NTC: {e}")

        return media_types

    # detect_port_type перенесён в Domain Layer: core/domain/interface.py (InterfaceNormalizer)
