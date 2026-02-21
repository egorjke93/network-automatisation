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
from ..core.constants import COLLECTOR_COMMANDS, normalize_interface_short
from ..core.constants.commands import SECONDARY_COMMANDS
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
        neighbors = collector.collect(devices)  # List[LLDPNeighbor]
    """

    # Типизированная модель
    model_class = LLDPNeighbor

    # Команды для LLDP (detail) - из централизованного хранилища
    lldp_commands = COLLECTOR_COMMANDS.get("lldp", {})

    # Команды для LLDP summary (из централизованного хранилища commands.py)
    lldp_summary_commands = SECONDARY_COMMANDS.get("lldp_summary", {})

    # Команды для CDP - из централизованного хранилища
    cdp_commands = COLLECTOR_COMMANDS.get("cdp", {})

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
                hostname = self._init_device_connection(conn, device)

                # --format parsed: сырые данные TextFSM, без нормализации
                if self._skip_normalize:
                    if self.protocol == "both":
                        all_raw = []
                        for proto, cmds in [("lldp", self.lldp_commands), ("cdp", self.cdp_commands)]:
                            cmd = cmds.get(device.platform)
                            if cmd:
                                response = conn.send_command(cmd)
                                raw = self._parse_output(
                                    response.result, device, command=cmd, protocol=proto
                                )
                                self._add_metadata_to_rows(raw, hostname, device.host)
                                for row in raw:
                                    row["_protocol"] = proto
                                all_raw.extend(raw)
                        logger.info(f"{hostname}: собрано {len(all_raw)} записей (parsed, без нормализации)")
                        return all_raw
                    else:
                        response = conn.send_command(command)
                        raw_data = self._parse_output(response.result, device)
                        self._add_metadata_to_rows(raw_data, hostname, device.host)
                        logger.info(f"{hostname}: собрано {len(raw_data)} записей (parsed, без нормализации)")
                        return raw_data

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
                    # Для LLDP: дополняем local_interface из summary если пустой
                    if self.protocol == "lldp":
                        raw_data = self._enrich_from_summary(conn, device, raw_data)

                logger.info(f"{hostname}: собрано {len(raw_data)} записей")
                return raw_data

        except Exception as e:
            return self._handle_collection_error(e, device)

    def _collect_both_protocols(
        self, conn, device: Device, hostname: str
    ) -> List[Dict[str, Any]]:
        """
        Собирает LLDP и CDP, объединяет данные для получения полной информации.

        LLDP даёт: MAC адрес (chassis_id)
        CDP даёт: Platform, capabilities

        Использует Domain Layer для нормализации и объединения.

        Если в LLDP detail нет local_interface, дополняем из LLDP summary.

        Args:
            conn: Активное подключение
            device: Устройство
            hostname: Имя устройства

        Returns:
            List[Dict]: Объединённые нормализованные данные
        """
        lldp_data = []
        cdp_data = []
        lldp_summary = {}  # device_id -> local_interface

        # Сначала собираем LLDP summary для local_interface
        lldp_summary_cmd = self.lldp_summary_commands.get(device.platform)
        if lldp_summary_cmd:
            try:
                response = conn.send_command(lldp_summary_cmd)
                lldp_summary = self._parse_lldp_summary(response.result)
                logger.debug(f"{hostname}: LLDP summary: {len(lldp_summary)} записей")
            except Exception as e:
                logger.debug(f"{hostname}: Не удалось собрать LLDP summary: {e}")

        # Собираем и нормализуем LLDP detail
        lldp_command = self.lldp_commands.get(device.platform)
        if lldp_command:
            response = conn.send_command(lldp_command)
            # Передаём команду явно для правильного TextFSM шаблона
            raw_lldp = self._parse_output(response.result, device, command=lldp_command, protocol="lldp")
            lldp_data = self._normalizer.normalize_dicts(
                raw_lldp, protocol="lldp", hostname=hostname, device_ip=device.host
            )
            # Дополняем local_interface из summary если пустой
            if lldp_summary:
                lldp_data = self._enrich_local_interface(lldp_data, lldp_summary)

        # Собираем и нормализуем CDP
        cdp_command = self.cdp_commands.get(device.platform)
        if cdp_command:
            response = conn.send_command(cdp_command)
            # Передаём команду явно для правильного TextFSM шаблона (CDP!)
            raw_cdp = self._parse_output(response.result, device, command=cdp_command, protocol="cdp")
            cdp_data = self._normalizer.normalize_dicts(
                raw_cdp, protocol="cdp", hostname=hostname, device_ip=device.host
            )

        # Объединяем через Domain Layer
        return self._normalizer.merge_lldp_cdp(lldp_data, cdp_data)

    def _parse_lldp_summary(self, output: str) -> Dict[str, str]:
        """
        Парсит show lldp neighbors (без detail) для получения local interface.

        Формат вывода:
        Device ID           Local Intf     Hold-time  Capability      Port ID
        switch2.domain      Gi0/1          120        B,R             Gi0/24

        Returns:
            Dict[str, str]: {device_id: local_interface}
        """
        result = {}

        # Пропускаем заголовок и пустые строки
        lines = output.strip().split('\n')
        for line in lines:
            line = line.strip()
            if not line or line.startswith('Device ID') or line.startswith('Capability'):
                continue
            if 'Total entries' in line:
                continue

            # Парсим строку: device_id, local_intf, hold-time, capability, port_id
            # Формат может варьироваться, используем split
            parts = line.split()
            if len(parts) >= 2:
                device_id = parts[0]
                local_intf = parts[1]
                # Проверяем что local_intf похож на интерфейс
                if re.match(r'^(Gi|Fa|Te|Et|Eth|Po|mgmt)', local_intf, re.I):
                    result[device_id.lower()] = local_intf

        return result

    def _enrich_local_interface(
        self, data: List[Dict[str, Any]], summary: Dict[str, str]
    ) -> List[Dict[str, Any]]:
        """
        Дополняет local_interface из summary если он пустой.

        Учитывает усечение hostname в выводе show lldp neighbors:
        - Summary показывает "Managed Redundant S" (ограничение ширины столбца)
        - Detail показывает "Managed Redundant Switch 06355"
        - Сопоставляем по началу строки (startswith)

        Args:
            data: Нормализованные LLDP данные
            summary: {device_id: local_interface} из summary

        Returns:
            List[Dict]: Обогащённые данные
        """
        for entry in data:
            if not entry.get("local_interface"):
                remote = entry.get("remote_hostname", "").lower()
                if not remote:
                    continue

                # 1. Точное совпадение
                if remote in summary:
                    entry["local_interface"] = summary[remote]
                    logger.debug(f"Enriched local_interface: {remote} -> {summary[remote]}")
                    continue

                # 2. Без домена
                remote_short = remote.split('.')[0]
                if remote_short in summary:
                    entry["local_interface"] = summary[remote_short]
                    logger.debug(f"Enriched local_interface: {remote_short} -> {summary[remote_short]}")
                    continue

                # 3. Частичное совпадение (усечённые hostname)
                # Summary может обрезать длинные имена: "Managed Redundant S" → 19 chars
                # Собираем ВСЕ совпадения, используем только если УНИКАЛЬНОЕ
                partial_matches = []
                for summary_host, local_intf in summary.items():
                    # "managed redundant switch 06355".startswith("managed redundant s")
                    if remote.startswith(summary_host):
                        partial_matches.append((summary_host, local_intf))
                    # summary начинается с detail (если domain в summary)
                    elif summary_host.startswith(remote_short):
                        partial_matches.append((summary_host, local_intf))

                # Используем только если ОДНО совпадение (чтобы не путать разные устройства)
                if len(partial_matches) == 1:
                    summary_host, local_intf = partial_matches[0]
                    entry["local_interface"] = local_intf
                    logger.debug(f"Enriched local_interface (partial): {summary_host} -> {local_intf}")
                elif len(partial_matches) > 1:
                    logger.debug(
                        f"Multiple partial matches for {remote}, skipping: {partial_matches}"
                    )
        return data

    def _enrich_from_summary(
        self, conn, device: Device, data: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Дополняет local_interface из show lldp neighbors (summary).

        Используется когда show lldp neighbors detail не содержит Local Intf.

        Args:
            conn: Активное подключение
            device: Устройство
            data: Нормализованные данные

        Returns:
            List[Dict]: Обогащённые данные
        """
        # Проверяем есть ли записи без local_interface
        needs_enrichment = any(not d.get("local_interface") for d in data)
        if not needs_enrichment:
            return data

        # Собираем summary
        summary_cmd = self.lldp_summary_commands.get(device.platform)
        if not summary_cmd:
            return data

        try:
            response = conn.send_command(summary_cmd)
            summary = self._parse_lldp_summary(response.result)
            if summary:
                return self._enrich_local_interface(data, summary)
        except Exception as e:
            logger.debug(f"Не удалось обогатить из summary: {e}")

        return data

    # Объединение LLDP/CDP перенесено в Domain Layer: core/domain/lldp.py → merge_lldp_cdp

    def _parse_output(
        self,
        output: str,
        device: Device,
        command: str = None,
        protocol: str = None,
    ) -> List[Dict[str, Any]]:
        """
        Парсит вывод команды show lldp/cdp neighbors.

        Возвращает СЫРЫЕ данные. Нормализация происходит в Domain Layer.

        Args:
            output: Сырой вывод команды
            device: Устройство
            command: Команда для TextFSM (если None - определяется автоматически)
            protocol: Протокол для выбора regex парсера (если None - self.protocol)

        Returns:
            List[Dict]: Сырые данные соседей
        """
        proto = protocol or self.protocol

        # Пробуем TextFSM с явной командой
        if self.use_ntc:
            data = self._parse_with_textfsm(output, device, command=command)
            if data:
                return data

        # Fallback на regex
        if proto == "cdp":
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

            # remote_port определяется в Domain Layer (LLDPNormalizer)
            # Здесь оставляем сырые port_id и port_description

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
