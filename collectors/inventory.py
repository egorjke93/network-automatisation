"""
Коллектор инвентаризации оборудования.

Собирает информацию о модулях, трансиверах, блоках питания.
Использует команду show inventory.

Данные для NetBox:
- name: Имя компонента
- pid: Product ID (модель)
- serial: Серийный номер
- description: Описание

Пример использования:
    collector = InventoryCollector()
    data = collector.collect(devices)
"""

import re
import logging
from typing import List, Dict, Any

from .base import BaseCollector
from ..core.device import Device
from ..core.models import InventoryItem
from ..core.constants import get_vendor_by_platform
from ..core.exceptions import (
    CollectorError,
    ConnectionError,
    AuthenticationError,
    TimeoutError,
    format_error_for_log,
)

logger = logging.getLogger(__name__)


class InventoryCollector(BaseCollector):
    """
    Коллектор инвентаризации оборудования.

    Собирает модули, трансиверы, блоки питания с серийниками.

    Example:
        collector = InventoryCollector()
        inventory = collector.collect(devices)  # List[Dict]

        # Или типизированные модели
        items = collector.collect_models(devices)  # List[InventoryItem]
    """

    # Типизированная модель
    model_class = InventoryItem

    # Команды для разных платформ
    platform_commands = {
        "cisco_ios": "show inventory",
        "cisco_iosxe": "show inventory",
        "cisco_nxos": "show inventory",
        "arista_eos": "show inventory",
    }

    # Команды для получения трансиверов
    # NX-OS: show inventory не содержит SFP/QSFP, они в show interface transceiver
    transceiver_commands = {
        "cisco_nxos": "show interface transceiver",
    }

    def __init__(
        self,
        collect_transceivers: bool = True,
        **kwargs,
    ):
        """
        Инициализация коллектора инвентаризации.

        Args:
            collect_transceivers: Собирать трансиверы (для NX-OS из show interface transceiver)
            **kwargs: Аргументы для BaseCollector
        """
        super().__init__(**kwargs)
        self.collect_transceivers = collect_transceivers

    def _parse_output(
        self,
        output: str,
        device: Device,
    ) -> List[Dict[str, Any]]:
        """
        Парсит вывод команды show inventory.

        Args:
            output: Сырой вывод команды
            device: Устройство

        Returns:
            List[Dict]: Список компонентов
        """
        # Пробуем NTC Templates
        if self.use_ntc:
            data = self._parse_with_textfsm(output, device)
            if data:
                return self._normalize_data(data, device)

        # Fallback на regex
        items = self._parse_with_regex(output)
        # Добавляем manufacturer
        manufacturer = self._detect_manufacturer(device)
        for item in items:
            item["manufacturer"] = self._detect_manufacturer_by_pid(item.get("pid", "")) or manufacturer
        return items

    def _parse_with_regex(self, output: str) -> List[Dict[str, Any]]:
        """
        Парсит вывод с помощью regex.

        Args:
            output: Сырой вывод

        Returns:
            List[Dict]: Компоненты
        """
        items = []

        # Паттерн для Cisco show inventory
        # NAME: "Chassis", DESCR: "Cisco ..."
        # PID: WS-C3750X-48P-S, VID: V02, SN: FDO1234X5YZ
        pattern = re.compile(
            r'NAME:\s*"([^"]+)".*?DESCR:\s*"([^"]*)".*?'
            r'PID:\s*(\S+).*?(?:VID:\s*(\S+).*?)?SN:\s*(\S+)',
            re.DOTALL | re.IGNORECASE
        )

        for match in pattern.finditer(output):
            name, descr, pid, vid, serial = match.groups()

            items.append({
                "name": name.strip(),
                "description": descr.strip() if descr else "",
                "pid": pid.strip() if pid else "",
                "vid": vid.strip() if vid else "",
                "serial": serial.strip() if serial else "",
            })

        return items

    def _normalize_data(
        self,
        data: List[Dict[str, Any]],
        device: Device = None,
    ) -> List[Dict[str, Any]]:
        """
        Нормализует данные инвентаризации.

        Args:
            data: Сырые данные
            device: Устройство (для определения manufacturer)

        Returns:
            List[Dict]: Нормализованные данные
        """
        normalized = []

        # Определяем manufacturer по платформе устройства
        manufacturer = self._detect_manufacturer(device)

        for row in data:
            pid = row.get("pid", "")
            item = {
                "name": row.get("name", ""),
                "description": row.get("descr", row.get("description", "")),
                "pid": pid,
                "vid": row.get("vid", ""),
                "serial": row.get("sn", row.get("serial", "")),
                "manufacturer": self._detect_manufacturer_by_pid(pid) or manufacturer,
            }
            normalized.append(item)

        return normalized

    def _detect_manufacturer(self, device: Device = None) -> str:
        """
        Определяет производителя по платформе устройства.

        Использует централизованный маппинг из core/constants.py.

        Args:
            device: Устройство

        Returns:
            str: Название производителя (Cisco, Arista, Juniper, etc.)
        """
        if not device or not device.platform:
            return ""

        # Используем централизованный маппинг
        vendor = get_vendor_by_platform(device.platform)

        # Capitalize для NetBox (cisco -> Cisco)
        return vendor.capitalize() if vendor and vendor != "unknown" else ""

    def _detect_manufacturer_by_pid(self, pid: str) -> str:
        """
        Определяет производителя по PID (Product ID).

        Args:
            pid: Product ID

        Returns:
            str: Название производителя или пустая строка
        """
        if not pid:
            return ""

        pid_upper = pid.upper()

        # Cisco PIDs
        if any(x in pid_upper for x in ["WS-", "C9", "N9K", "N7K", "N5K", "ISR", "ASR", "SFP-", "GLC-", "XENPAK"]):
            return "Cisco"

        # Arista
        if pid_upper.startswith("DCS-") or "ARISTA" in pid_upper:
            return "Arista"

        # Juniper
        if pid_upper.startswith("EX") or pid_upper.startswith("QFX") or pid_upper.startswith("MX"):
            return "Juniper"

        return ""

    def _collect_from_device(self, device: Device) -> List[Dict[str, Any]]:
        """
        Собирает данные инвентаризации с устройства.

        Для NX-OS дополнительно собирает трансиверы из show interface transceiver.

        Args:
            device: Устройство

        Returns:
            List[Dict]: Данные инвентаризации
        """
        from ..core.connection import get_ntc_platform
        from ..core.device import DeviceStatus

        command = self._get_command(device)
        if not command:
            logger.warning(f"Нет команды для {device.platform}")
            return []

        try:
            with self._conn_manager.connect(device, self.credentials) as conn:
                # Получаем hostname
                hostname = self._conn_manager.get_hostname(conn)
                device.metadata["hostname"] = hostname
                device.status = DeviceStatus.ONLINE

                # Основная команда show inventory
                response = conn.send_command(command)
                data = self._parse_output(response.result, device)

                # Собираем трансиверы если включено
                transceiver_items = []
                if self.collect_transceivers:
                    tr_cmd = self.transceiver_commands.get(device.platform)
                    if tr_cmd:
                        try:
                            tr_response = conn.send_command(tr_cmd)
                            transceiver_items = self._parse_transceivers(
                                tr_response.result,
                                get_ntc_platform(device.platform),
                                tr_cmd,
                                device,
                            )
                        except Exception as e:
                            logger.debug(f"Ошибка получения transceivers: {e}")

                # Объединяем inventory + transceivers
                all_items = data + transceiver_items

                # Добавляем hostname ко всем записям
                for row in all_items:
                    row["hostname"] = hostname
                    row["device_ip"] = device.host

                logger.info(f"{hostname}: собрано {len(all_items)} компонентов inventory (из них {len(transceiver_items)} трансиверов)")
                return all_items

        except (ConnectionError, AuthenticationError, TimeoutError) as e:
            device.status = DeviceStatus.ERROR
            logger.error(f"Ошибка подключения к {device.host}: {format_error_for_log(e)}")
            return []
        except Exception as e:
            device.status = DeviceStatus.ERROR
            logger.error(f"Неизвестная ошибка с {device.host}: {e}")
            return []

    def _parse_transceivers(
        self,
        output: str,
        ntc_platform: str,
        command: str,
        device: Device,
    ) -> List[Dict[str, Any]]:
        """
        Парсит show interface transceiver для получения SFP/QSFP.

        Конвертирует данные в формат inventory:
        - name: "Transceiver Ethernet1/1"
        - pid: part_number (SFP+ LR)
        - serial: serial_number
        - description: type (10Gbase-LR)
        - manufacturer: name (OEM, CISCO, etc.)

        Args:
            output: Вывод команды
            ntc_platform: Платформа для NTC
            command: Команда для NTC парсера
            device: Устройство

        Returns:
            List[Dict]: Трансиверы в формате inventory
        """
        from ntc_templates.parse import parse_output

        items = []
        manufacturer = self._detect_manufacturer(device)

        try:
            parsed = parse_output(
                platform=ntc_platform,
                command=command,
                data=output
            )

            for row in parsed:
                # Пропускаем интерфейсы без трансиверов
                transceiver_type = row.get("type", "")
                if not transceiver_type or "not present" in str(transceiver_type).lower():
                    continue

                interface = row.get("interface", "")
                part_number = row.get("part_number", "")
                # NTC шаблон возвращает "serial", не "serial_number"
                serial_number = row.get("serial", row.get("serial_number", ""))
                name = row.get("name", "")  # OEM, CISCO-FINISAR, etc.

                # Определяем manufacturer по name или PID
                item_manufacturer = ""
                if name:
                    name_upper = name.upper()
                    if "CISCO" in name_upper:
                        item_manufacturer = "Cisco"
                    elif "FINISAR" in name_upper:
                        item_manufacturer = "Finisar"
                    elif "OEM" in name_upper:
                        item_manufacturer = manufacturer  # Используем vendor устройства

                if not item_manufacturer:
                    item_manufacturer = self._detect_manufacturer_by_pid(part_number) or manufacturer

                items.append({
                    "name": f"Transceiver {interface}",
                    "description": transceiver_type,
                    "pid": part_number,
                    "serial": serial_number,
                    "manufacturer": item_manufacturer,
                })

        except Exception as e:
            logger.debug(f"Ошибка парсинга transceivers через NTC: {e}")

        return items
