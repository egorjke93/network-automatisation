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

    # Команды для разных платформ
    # Используем "show interfaces" для получения полной информации:
    # статус, MAC, IP-адреса (включая Vlan SVI), description
    platform_commands = {
        "cisco_ios": "show interfaces",
        "cisco_iosxe": "show interfaces",
        "cisco_nxos": "show interface",
        "arista_eos": "show interfaces",
        "juniper_junos": "show interfaces extensive",
    }

    # Команды для ошибок
    error_commands = {
        "cisco_ios": "show interfaces | include errors|CRC|input|output",
        "cisco_iosxe": "show interfaces | include errors|CRC|input|output",
        "cisco_nxos": "show interface counters errors",
        "arista_eos": "show interfaces counters errors",
    }

    # Команды для LAG (etherchannel/port-channel)
    lag_commands = {
        "cisco_ios": "show etherchannel summary",
        "cisco_iosxe": "show etherchannel summary",
        "cisco_nxos": "show port-channel summary",
        "arista_eos": "show port-channel summary",
    }

    # Команды для switchport mode
    switchport_commands = {
        "cisco_ios": "show interfaces switchport",
        "cisco_iosxe": "show interfaces switchport",
        "cisco_nxos": "show interface switchport",
        "arista_eos": "show interfaces switchport",
    }

    # Команды для получения media_type (тип трансивера)
    # NX-OS: show interface возвращает только "10G", а show interface status - "10Gbase-LR"
    media_type_commands = {
        "cisco_nxos": "show interface status",
    }

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
            collect_media_type: Собирать точный media_type (для NX-OS из show interface status)
            **kwargs: Аргументы для BaseCollector
        """
        super().__init__(**kwargs)
        self.include_errors = include_errors
        self.collect_lag_info = collect_lag_info
        self.collect_switchport = collect_switchport
        self.collect_media_type = collect_media_type
    
    def _parse_output(
        self,
        output: str,
        device: Device,
    ) -> List[Dict[str, Any]]:
        """
        Парсит вывод команды show interfaces.

        Args:
            output: Сырой вывод команды
            device: Устройство

        Returns:
            List[Dict]: Список интерфейсов с полями:
                - interface: имя интерфейса
                - status: up/down/disabled
                - mac: MAC-адрес интерфейса
                - ip_address: IP-адрес (если есть)
                - prefix_length: маска сети
                - description: описание
                - speed, duplex, mtu и др.
        """
        # Пробуем TextFSM
        if self.use_ntc:
            data = self._parse_with_textfsm(output, device)
            if data:
                return self._normalize_data(data)

        # Fallback на regex
        return self._parse_with_regex(output, device)
    
    def _parse_with_regex(
        self,
        output: str,
        device: Device,
    ) -> List[Dict[str, Any]]:
        """
        Парсит вывод show interfaces с помощью regex (fallback).

        Args:
            output: Сырой вывод
            device: Устройство

        Returns:
            List[Dict]: Интерфейсы
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
                    "status": intf_match.group(2),
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

        return self._normalize_data(interfaces)
    
    def _normalize_data(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Нормализует данные интерфейсов.

        Args:
            data: Сырые данные

        Returns:
            List[Dict]: Нормализованные данные
        """
        # Маппинг статусов из show interfaces
        status_map = {
            "connected": "up",
            "up": "up",
            "notconnect": "down",
            "down": "down",
            "disabled": "disabled",
            "err-disabled": "error",
            "administratively down": "disabled",
        }

        for row in data:
            # Нормализуем статус (link_status из NTC или status)
            status = row.get("link_status", row.get("status", ""))
            if status:
                status_lower = str(status).lower()
                row["status"] = status_map.get(status_lower, status_lower)

            # Унифицируем имена полей из NTC шаблона
            # NTC может возвращать MAC в разных полях: mac_address, address, bia
            if not row.get("mac"):
                for mac_field in ["mac_address", "address", "bia", "hardware_address"]:
                    if row.get(mac_field):
                        row["mac"] = row[mac_field]
                        break

            # Унифицируем имена из NTC Templates (hardware_type, media_type)
            if "hardware_type" not in row and "hardware" in row:
                row["hardware_type"] = row["hardware"]
            if "media_type" not in row and "media" in row:
                row["media_type"] = row["media"]

        return data

    def _collect_from_device(self, device: Device) -> List[Dict[str, Any]]:
        """
        Собирает данные с одного устройства включая LAG membership.

        Args:
            device: Устройство

        Returns:
            List[Dict]: Данные с устройства
        """
        from ..core.connection import get_ntc_platform

        command = self._get_command(device)
        if not command:
            logger.warning(f"Нет команды для {device.platform}")
            return []

        try:
            with self._conn_manager.connect(device, self.credentials) as conn:
                # Получаем hostname
                hostname = self._conn_manager.get_hostname(conn)
                device.metadata["hostname"] = hostname

                # Основная команда show interfaces
                response = conn.send_command(command)
                data = self._parse_output(response.result, device)

                # Собираем LAG membership если включено
                lag_membership = {}
                if self.collect_lag_info:
                    lag_cmd = self.lag_commands.get(device.platform)
                    if lag_cmd:
                        try:
                            lag_response = conn.send_command(lag_cmd)
                            lag_membership = self._parse_lag_membership(
                                lag_response.result,
                                get_ntc_platform(device.platform),
                                lag_cmd,  # Передаём команду для NTC
                            )
                        except Exception as e:
                            logger.debug(f"Ошибка получения LAG info: {e}")

                # Собираем switchport mode если включено
                switchport_modes = {}
                if self.collect_switchport:
                    sw_cmd = self.switchport_commands.get(device.platform)
                    if sw_cmd:
                        try:
                            sw_response = conn.send_command(sw_cmd)
                            switchport_modes = self._parse_switchport_modes(
                                sw_response.result,
                                get_ntc_platform(device.platform),
                                sw_cmd,  # Передаём команду для NTC
                            )
                        except Exception as e:
                            logger.debug(f"Ошибка получения switchport info: {e}")

                # Собираем media_type если включено (NX-OS: тип трансивера из show interface status)
                media_types = {}
                if self.collect_media_type:
                    mt_cmd = self.media_type_commands.get(device.platform)
                    if mt_cmd:
                        try:
                            mt_response = conn.send_command(mt_cmd)
                            media_types = self._parse_media_types(
                                mt_response.result,
                                get_ntc_platform(device.platform),
                                mt_cmd,
                            )
                        except Exception as e:
                            logger.debug(f"Ошибка получения media_type info: {e}")

                # Определяем mode для LAG на основе members
                # Если хотя бы один member в trunk → LAG тоже tagged/tagged-all
                lag_modes: Dict[str, str] = {}
                for member_iface, lag_name in lag_membership.items():
                    if member_iface in switchport_modes:
                        member_mode = switchport_modes[member_iface].get("mode", "")
                        # tagged-all имеет приоритет над tagged
                        if member_mode == "tagged-all":
                            lag_modes[lag_name] = "tagged-all"
                        elif member_mode == "tagged" and lag_modes.get(lag_name) != "tagged-all":
                            lag_modes[lag_name] = "tagged"

                # Добавляем metadata, LAG и switchport info к каждой записи
                for row in data:
                    row["hostname"] = hostname
                    row["device_ip"] = device.host

                    iface = row.get("interface", "")
                    iface_lower = iface.lower()

                    # Обогащаем media_type из show interface status (NX-OS)
                    # Это важно для правильного определения типа интерфейса в NetBox
                    if iface in media_types and media_types[iface]:
                        # Перезаписываем только если есть более точный тип
                        existing_mt = row.get("media_type", "").lower()
                        new_mt = media_types[iface].lower()
                        # show interface status возвращает "10Gbase-LR", а show interface - "10G"
                        # "10Gbase-LR" более информативно
                        if "base" in new_mt or "sfp" in new_mt or "qsfp" in new_mt:
                            row["media_type"] = media_types[iface]

                    # Нормализуем port_type (платформонезависимо)
                    # Это поле используется в sync.py для определения типа интерфейса
                    row["port_type"] = self._detect_port_type(row, iface_lower)

                    # Добавляем LAG для member интерфейсов
                    if iface in lag_membership:
                        row["lag"] = lag_membership[iface]

                    # Добавляем switchport mode
                    if iface in switchport_modes:
                        sw_data = switchport_modes[iface]
                        row["mode"] = sw_data.get("mode", "")
                        row["native_vlan"] = sw_data.get("native_vlan", "")
                        row["access_vlan"] = sw_data.get("access_vlan", "")
                    # Для LAG интерфейсов берём mode из members
                    elif iface_lower.startswith(("po", "port-channel")):
                        # Ищем mode по любому варианту имени (Po1, Port-channel1)
                        for lag_name, lag_mode in lag_modes.items():
                            if lag_name.lower() == iface_lower or \
                               f"po{lag_name}".lower() == iface_lower or \
                               lag_name.lower().replace("po", "port-channel") == iface_lower:
                                row["mode"] = lag_mode
                                break
                    # Для member интерфейсов без mode - наследуем от LAG
                    elif iface in lag_membership and not row.get("mode"):
                        lag_name = lag_membership[iface]
                        if lag_name in lag_modes:
                            row["mode"] = lag_modes[lag_name]

                logger.info(f"{hostname}: собрано {len(data)} интерфейсов")
                return data

        except (ConnectionError, AuthenticationError, TimeoutError) as e:
            logger.error(f"Ошибка подключения к {device.host}: {format_error_for_log(e)}")
            return []
        except Exception as e:
            logger.error(f"Неизвестная ошибка с {device.host}: {e}")
            return []

    def _parse_lag_membership(
        self,
        output: str,
        ntc_platform: str,
        command: str = "show etherchannel summary",
    ) -> Dict[str, str]:
        """
        Парсит show etherchannel/port-channel summary для определения LAG membership.

        Args:
            output: Вывод команды
            ntc_platform: Платформа для NTC
            command: Команда для NTC парсера (show etherchannel summary / show port-channel summary)

        Returns:
            Dict: {member_interface: lag_interface} например {"Gi0/1": "Po1", "Eth1/1": "Po1"}
        """
        from ntc_templates.parse import parse_output

        membership = {}

        try:
            parsed = parse_output(
                platform=ntc_platform,
                command=command,
                data=output
            )

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
                            membership[member_clean] = lag_name
                            # Добавляем полное имя тоже (для сопоставления с show interface)
                            if member_clean.startswith("Hu"):
                                # C9500: Hu1/0/51 -> HundredGigE1/0/51
                                membership[f"HundredGigE{member_clean[2:]}"] = lag_name
                                membership[f"HundredGigabitEthernet{member_clean[2:]}"] = lag_name
                            elif member_clean.startswith("Fo"):
                                # Fo1/0/1 -> FortyGigabitEthernet1/0/1
                                membership[f"FortyGigabitEthernet{member_clean[2:]}"] = lag_name
                            elif member_clean.startswith("Twe"):
                                # C9500: Twe1/0/27 -> TwentyFiveGigE1/0/27
                                membership[f"TwentyFiveGigE{member_clean[3:]}"] = lag_name
                                membership[f"TwentyFiveGigabitEthernet{member_clean[3:]}"] = lag_name
                            elif member_clean.startswith("Te"):
                                membership[f"TenGigabitEthernet{member_clean[2:]}"] = lag_name
                            elif member_clean.startswith("Gi"):
                                membership[f"GigabitEthernet{member_clean[2:]}"] = lag_name
                            elif member_clean.startswith("Eth"):
                                # NX-OS: Eth1/1 -> Ethernet1/1
                                membership[f"Ethernet{member_clean[3:]}"] = lag_name
                            elif member_clean.startswith("Fa"):
                                membership[f"FastEthernet{member_clean[2:]}"] = lag_name

        except Exception as e:
            logger.debug(f"Ошибка парсинга LAG через NTC: {e}")
            # Fallback на regex
            membership = self._parse_lag_membership_regex(output)

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
                membership[member] = lag_name
                # Добавляем полное имя (для сопоставления с show interface)
                if member.startswith("Hu"):
                    membership[f"HundredGigE{member[2:]}"] = lag_name
                    membership[f"HundredGigabitEthernet{member[2:]}"] = lag_name
                elif member.startswith("Fo"):
                    membership[f"FortyGigabitEthernet{member[2:]}"] = lag_name
                elif member.startswith("Twe"):
                    membership[f"TwentyFiveGigE{member[3:]}"] = lag_name
                    membership[f"TwentyFiveGigabitEthernet{member[3:]}"] = lag_name
                elif member.startswith("Te"):
                    membership[f"TenGigabitEthernet{member[2:]}"] = lag_name
                elif member.startswith("Gi"):
                    membership[f"GigabitEthernet{member[2:]}"] = lag_name
                elif member.startswith("Eth"):
                    # NX-OS: Eth1/1 -> Ethernet1/1
                    membership[f"Ethernet{member[3:]}"] = lag_name
                elif member.startswith("Fa"):
                    membership[f"FastEthernet{member[2:]}"] = lag_name

        return membership

    def _parse_switchport_modes(
        self,
        output: str,
        ntc_platform: str,
        command: str = "show interfaces switchport",
    ) -> Dict[str, Dict[str, str]]:
        """
        Парсит show interfaces switchport для определения режимов портов.

        Args:
            output: Вывод команды
            ntc_platform: Платформа для NTC
            command: Команда для NTC парсера

        Returns:
            Dict: {interface: {mode, native_vlan, access_vlan}}
        """
        from ntc_templates.parse import parse_output

        modes = {}

        try:
            parsed = parse_output(
                platform=ntc_platform,
                command=command,
                data=output
            )

            for row in parsed:
                iface = row.get("interface", "")
                mode = row.get("mode", row.get("admin_mode", "")).lower()
                native_vlan = row.get("native_vlan", row.get("trunking_native_vlan", ""))
                access_vlan = row.get("access_vlan", "")

                if not iface:
                    continue

                # Конвертируем режим в формат NetBox
                # NetBox: access, tagged, tagged-all
                # tagged-all = полный транк (все VLAN)
                # tagged = транк с ограниченным списком VLAN
                netbox_mode = ""
                if "access" in mode:
                    netbox_mode = "access"
                elif "trunk" in mode or "dynamic" in mode:
                    # Проверяем список VLAN - если ALL или полный диапазон, то tagged-all
                    trunking_vlans = row.get("trunking_vlans", "").lower().strip()
                    # Варианты "все VLAN":
                    # - "all" (IOS)
                    # - "" (пустая строка)
                    # - "1-4094" (NX-OS полный диапазон)
                    # - "1-4093" (некоторые устройства)
                    if (not trunking_vlans or
                        trunking_vlans == "all" or
                        trunking_vlans in ("1-4094", "1-4093", "1-4095")):
                        netbox_mode = "tagged-all"
                    else:
                        netbox_mode = "tagged"

                modes[iface] = {
                    "mode": netbox_mode,
                    "native_vlan": str(native_vlan) if native_vlan else "",
                    "access_vlan": str(access_vlan) if access_vlan else "",
                }

                # Добавляем альтернативные имена
                if iface.startswith("Gi"):
                    modes[f"GigabitEthernet{iface[2:]}"] = modes[iface]
                elif iface.startswith("Fa"):
                    modes[f"FastEthernet{iface[2:]}"] = modes[iface]
                elif iface.startswith("Te"):
                    modes[f"TenGigabitEthernet{iface[2:]}"] = modes[iface]
                elif iface.startswith("Eth"):
                    # NX-OS: Eth1/1 -> Ethernet1/1
                    modes[f"Ethernet{iface[3:]}"] = modes[iface]

        except Exception as e:
            logger.debug(f"Ошибка парсинга switchport через NTC: {e}")
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
        ntc_platform: str,
        command: str = "show interface status",
    ) -> Dict[str, str]:
        """
        Парсит show interface status для получения media_type (Type колонка).

        На NX-OS `show interface` возвращает media_type как "10G" (только скорость),
        а `show interface status` возвращает Type как "10Gbase-LR" (полный тип).

        Args:
            output: Вывод команды show interface status
            ntc_platform: Платформа для NTC
            command: Команда для NTC парсера

        Returns:
            Dict: {interface: media_type} например {"Ethernet1/1": "10Gbase-LR"}
        """
        from ntc_templates.parse import parse_output

        media_types = {}

        try:
            parsed = parse_output(
                platform=ntc_platform,
                command=command,
                data=output
            )

            for row in parsed:
                # NTC возвращает: port, name, status, vlan, duplex, speed, type
                port = row.get("port", "")
                media_type = row.get("type", "")

                if not port:
                    continue

                # Пропускаем пустые и "--"
                if not media_type or media_type == "--":
                    continue

                # Нормализуем имя порта
                # NX-OS show interface status: Eth1/1 -> Ethernet1/1
                if port.startswith("Eth") and not port.startswith("Ethernet"):
                    full_name = f"Ethernet{port[3:]}"
                else:
                    full_name = port

                media_types[full_name] = media_type

                # Добавляем также короткое имя для сопоставления
                if full_name.startswith("Ethernet"):
                    short_name = f"Eth{full_name[8:]}"
                    media_types[short_name] = media_type

        except Exception as e:
            logger.debug(f"Ошибка парсинга media_type через NTC: {e}")

        return media_types

    def _detect_port_type(self, row: Dict[str, Any], iface_lower: str) -> str:
        """
        Определяет тип порта на основе данных интерфейса.

        Нормализует данные с разных платформ в единый формат:
        - "100g-sfp28" - 100GE QSFP28
        - "40g-qsfp" - 40GE QSFP+
        - "25g-sfp28" - 25GE SFP28
        - "10g-sfp+" - 10GE SFP+
        - "1g-sfp" - 1GE SFP
        - "1g-rj45" - 1GE RJ45 (copper)
        - "100m-rj45" - 100M RJ45
        - "lag" - Port-channel/LAG
        - "virtual" - Vlan, Loopback, etc.
        - "" - не определён

        Args:
            row: Данные интерфейса от NTC
            iface_lower: Имя интерфейса в нижнем регистре

        Returns:
            str: Тип порта
        """
        hardware_type = row.get("hardware_type", "").lower()
        media_type = row.get("media_type", "").lower()

        # LAG интерфейсы
        if iface_lower.startswith(("port-channel", "po")):
            return "lag"

        # Виртуальные интерфейсы
        if iface_lower.startswith(("vlan", "loopback", "null", "tunnel", "nve")):
            return "virtual"

        # Management - обычно copper
        if iface_lower.startswith(("mgmt", "management")):
            return "1g-rj45"

        # 1. По media_type (наиболее точный - есть информация о трансивере)
        if media_type and media_type not in ("unknown", "not present", ""):
            if "100gbase" in media_type or "100g" in media_type:
                return "100g-qsfp28"
            if "40gbase" in media_type or "40g" in media_type:
                return "40g-qsfp"
            if "25gbase" in media_type or "25g" in media_type:
                return "25g-sfp28"
            if "10gbase" in media_type or "10g" in media_type:
                return "10g-sfp+"
            if "1000base-t" in media_type or "rj45" in media_type:
                return "1g-rj45"
            if "1000base" in media_type or "sfp" in media_type:
                return "1g-sfp"

        # 2. По hardware_type (максимальная скорость порта)
        # NX-OS: "100/1000/10000 Ethernet" = порт поддерживает 10G = SFP+
        if hardware_type:
            if "100000" in hardware_type or "100g" in hardware_type:
                return "100g-qsfp28"
            if "40000" in hardware_type or "40g" in hardware_type:
                return "40g-qsfp"
            if "25000" in hardware_type or "25g" in hardware_type:
                return "25g-sfp28"
            if "10000" in hardware_type or "10g" in hardware_type:
                return "10g-sfp+"
            # Только 1G без 10G - copper
            if "1000" in hardware_type and "10000" not in hardware_type:
                if "sfp" in hardware_type:
                    return "1g-sfp"
                return "1g-rj45"

        # 3. По имени интерфейса (IOS/IOS-XE)
        if iface_lower.startswith(("hundredgig", "hu")):
            return "100g-qsfp28"
        if iface_lower.startswith(("fortygig", "fo")):
            return "40g-qsfp"
        if iface_lower.startswith(("twentyfivegig", "twe")):
            return "25g-sfp28"
        if iface_lower.startswith("tengig"):
            return "10g-sfp+"
        # Te1/1 - короткий формат
        if len(iface_lower) >= 3 and iface_lower[:2] == "te" and iface_lower[2].isdigit():
            return "10g-sfp+"
        if iface_lower.startswith(("gigabit", "gi")):
            # GigabitEthernet по умолчанию RJ45, если нет SFP в hardware/media
            if "sfp" in hardware_type or "sfp" in media_type:
                return "1g-sfp"
            return "1g-rj45"
        if iface_lower.startswith(("fastethernet", "fa")):
            return "100m-rj45"

        # 4. Ethernet (NX-OS, Arista) - уже обработан через hardware_type выше
        # Если дошли сюда - не удалось определить
        return ""
