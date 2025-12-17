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
import logging
from typing import List, Dict, Any, Optional

from .base import BaseCollector
from ..core.device import Device

logger = logging.getLogger(__name__)


class InterfaceCollector(BaseCollector):
    """
    Коллектор информации об интерфейсах.
    
    Собирает статус, описание, VLAN, ошибки.
    
    Attributes:
        include_errors: Собирать статистику ошибок
        
    Example:
        collector = InterfaceCollector(include_errors=True)
        interfaces = collector.collect(devices)
    """
    
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

    def __init__(
        self,
        include_errors: bool = False,
        collect_lag_info: bool = True,
        collect_switchport: bool = True,
        **kwargs,
    ):
        """
        Инициализация коллектора интерфейсов.

        Args:
            include_errors: Собирать статистику ошибок
            collect_lag_info: Собирать информацию о LAG membership
            collect_switchport: Собирать режим switchport (access/trunk)
            **kwargs: Аргументы для BaseCollector
        """
        super().__init__(**kwargs)
        self.include_errors = include_errors
        self.collect_lag_info = collect_lag_info
        self.collect_switchport = collect_switchport
    
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
            logger.warning(f"Нет команды для {device.device_type}")
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
                    lag_cmd = self.lag_commands.get(device.device_type)
                    if lag_cmd:
                        try:
                            lag_response = conn.send_command(lag_cmd)
                            lag_membership = self._parse_lag_membership(
                                lag_response.result, get_ntc_platform(device.device_type)
                            )
                        except Exception as e:
                            logger.debug(f"Ошибка получения LAG info: {e}")

                # Собираем switchport mode если включено
                switchport_modes = {}
                if self.collect_switchport:
                    sw_cmd = self.switchport_commands.get(device.device_type)
                    if sw_cmd:
                        try:
                            sw_response = conn.send_command(sw_cmd)
                            switchport_modes = self._parse_switchport_modes(
                                sw_response.result, get_ntc_platform(device.device_type)
                            )
                        except Exception as e:
                            logger.debug(f"Ошибка получения switchport info: {e}")

                # Добавляем metadata, LAG и switchport info к каждой записи
                for row in data:
                    row["hostname"] = hostname
                    row["device_ip"] = device.host

                    iface = row.get("interface", "")

                    # Добавляем LAG для member интерфейсов
                    if iface in lag_membership:
                        row["lag"] = lag_membership[iface]

                    # Добавляем switchport mode
                    if iface in switchport_modes:
                        sw_data = switchport_modes[iface]
                        row["mode"] = sw_data.get("mode", "")
                        row["native_vlan"] = sw_data.get("native_vlan", "")
                        row["access_vlan"] = sw_data.get("access_vlan", "")

                logger.info(f"{hostname}: собрано {len(data)} интерфейсов")
                return data

        except Exception as e:
            logger.error(f"Ошибка подключения к {device.host}: {e}")
            return []

    def _parse_lag_membership(
        self,
        output: str,
        ntc_platform: str,
    ) -> Dict[str, str]:
        """
        Парсит show etherchannel summary для определения LAG membership.

        Args:
            output: Вывод show etherchannel summary
            ntc_platform: Платформа для NTC

        Returns:
            Dict: {member_interface: lag_interface} например {"Gi0/1": "Po1", "Gi0/2": "Po1"}
        """
        from ntc_templates.parse import parse_output

        membership = {}

        try:
            parsed = parse_output(
                platform=ntc_platform,
                command="show etherchannel summary",
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
                        # Убираем статус из имени (Gi0/1(P) -> Gi0/1)
                        member_clean = re.sub(r'\([^)]*\)', '', member).strip()
                        if member_clean:
                            membership[member_clean] = lag_name
                            # Добавляем полное имя тоже
                            if member_clean.startswith("Gi"):
                                membership[f"GigabitEthernet{member_clean[2:]}"] = lag_name
                            elif member_clean.startswith("Te"):
                                membership[f"TenGigabitEthernet{member_clean[2:]}"] = lag_name

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

            # Парсим member порты: Gi0/1(P) Gi0/2(P) Te0/3(P)
            member_pattern = re.compile(r"([A-Za-z]+[\d/]+)\([^)]*\)")
            for member_match in member_pattern.finditer(members_str):
                member = member_match.group(1)
                membership[member] = lag_name
                # Добавляем полное имя
                if member.startswith("Gi"):
                    membership[f"GigabitEthernet{member[2:]}"] = lag_name
                elif member.startswith("Te"):
                    membership[f"TenGigabitEthernet{member[2:]}"] = lag_name
                elif member.startswith("Fa"):
                    membership[f"FastEthernet{member[2:]}"] = lag_name

        return membership

    def _parse_switchport_modes(
        self,
        output: str,
        ntc_platform: str,
    ) -> Dict[str, Dict[str, str]]:
        """
        Парсит show interfaces switchport для определения режимов портов.

        Args:
            output: Вывод show interfaces switchport
            ntc_platform: Платформа для NTC

        Returns:
            Dict: {interface: {mode, native_vlan, access_vlan}}
        """
        from ntc_templates.parse import parse_output

        modes = {}

        try:
            parsed = parse_output(
                platform=ntc_platform,
                command="show interfaces switchport",
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
                netbox_mode = ""
                if "access" in mode:
                    netbox_mode = "access"
                elif "trunk" in mode:
                    netbox_mode = "tagged"
                elif "dynamic" in mode:
                    netbox_mode = "tagged"  # DTP обычно в trunk

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
                    elif "trunk" in mode:
                        current_data["mode"] = "tagged"
                    elif "dynamic" in mode:
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
