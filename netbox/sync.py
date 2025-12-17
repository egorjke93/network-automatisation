"""
Синхронизация данных с NetBox.

Автоматическая синхронизация собранных данных с NetBox:
- Интерфейсы
- IP-адреса
- MAC-адреса
- LLDP/CDP соседи → Кабели

ВАЖНО: С сетевых устройств мы ТОЛЬКО ЧИТАЕМ данные!
Синхронизация — это выгрузка собранных данных В NetBox.

Режимы работы:
- dry_run: Показать что будет изменено (без изменений)
- create_only: Только создавать новые объекты
- update_only: Только обновлять существующие
- skip_cables: Не трогать кабели

Пример использования:
    sync = NetBoxSync(client, dry_run=True)

    # Проверить что будет изменено
    sync.sync_interfaces("switch-01", interfaces)

    # Синхронизировать кабели из LLDP
    sync.sync_cables_from_lldp(lldp_data)
"""

import re
import logging
from typing import List, Dict, Any, Optional

from .client import NetBoxClient
from ..core.constants import (
    INTERFACE_FULL_MAP,
    DEFAULT_PREFIX_LENGTH,
    NETBOX_INTERFACE_TYPE_MAP,
    NETBOX_HARDWARE_TYPE_MAP,
    VIRTUAL_INTERFACE_PREFIXES,
    MGMT_INTERFACE_PATTERNS,
    normalize_interface_full,
    normalize_device_model,
)
from ..fields_config import get_sync_config

logger = logging.getLogger(__name__)

# Таблица транслитерации кириллицы в латиницу
_TRANSLIT_TABLE = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
    'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
    'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
    'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
    'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
}


def transliterate_to_slug(name: str) -> str:
    """
    Транслитерирует кириллицу в латиницу и создаёт валидный slug.

    Args:
        name: Имя (может содержать кириллицу)

    Returns:
        str: Валидный slug (только латиница, цифры, дефисы, подчёркивания)
    """
    result = []
    for char in name.lower():
        if char in _TRANSLIT_TABLE:
            result.append(_TRANSLIT_TABLE[char])
        elif char.isalnum() or char in '-_':
            result.append(char)
        elif char == ' ':
            result.append('-')
        # Другие символы пропускаем
    return ''.join(result)


class NetBoxSync:
    """
    Синхронизация данных с NetBox.

    ВАЖНО: Мы ТОЛЬКО ЧИТАЕМ с устройств и ЗАПИСЫВАЕМ в NetBox!
    Никаких изменений на сетевых устройствах.

    Attributes:
        client: NetBox клиент
        dry_run: Режим симуляции (без изменений)
        create_only: Только создавать новые объекты
        update_only: Только обновлять существующие

    Example:
        # Проверить что будет изменено
        sync = NetBoxSync(client, dry_run=True)
        sync.sync_interfaces("switch-01", interfaces)

        # Только создавать новое
        sync = NetBoxSync(client, create_only=True)
        sync.sync_cables_from_lldp(lldp_data)
    """

    def __init__(
        self,
        client: NetBoxClient,
        dry_run: bool = False,
        create_only: bool = False,
        update_only: bool = False,
    ):
        """
        Инициализация синхронизатора.

        Args:
            client: NetBox клиент
            dry_run: Режим симуляции (ничего не меняет)
            create_only: Только создавать новые объекты
            update_only: Только обновлять существующие
        """
        self.client = client
        self.dry_run = dry_run
        self.create_only = create_only
        self.update_only = update_only

        # Кэш для поиска устройств
        self._device_cache: Dict[str, Any] = {}
        self._mac_cache: Dict[str, Any] = {}

    def sync_interfaces(
        self,
        device_name: str,
        interfaces: List[Dict[str, Any]],
        create_missing: Optional[bool] = None,
        update_existing: Optional[bool] = None,
    ) -> Dict[str, int]:
        """
        Синхронизирует интерфейсы устройства.

        Args:
            device_name: Имя устройства в NetBox
            interfaces: Список интерфейсов для синхронизации
            create_missing: Создавать отсутствующие (None = из config)
            update_existing: Обновлять существующие (None = из config)

        Returns:
            Dict: Статистика {created: N, updated: N, skipped: N}
        """
        stats = {"created": 0, "updated": 0, "skipped": 0}
        sync_cfg = get_sync_config("interfaces")

        # Используем значения из config если не переданы явно
        if create_missing is None:
            create_missing = sync_cfg.get_option("create_missing", True)
        if update_existing is None:
            update_existing = sync_cfg.get_option("update_existing", True)

        # Получаем устройство
        device = self.client.get_device_by_name(device_name)
        if not device:
            logger.error(f"Устройство не найдено в NetBox: {device_name}")
            return stats

        # Получаем существующие интерфейсы
        existing = {
            intf.name: intf for intf in self.client.get_interfaces(device_id=device.id)
        }

        # Фильтры исключения интерфейсов
        exclude_patterns = sync_cfg.get_option("exclude_interfaces", [])

        for intf_data in interfaces:
            intf_name = intf_data.get("interface", intf_data.get("name"))
            if not intf_name:
                continue

            # Проверяем фильтры исключения
            excluded = False
            for pattern in exclude_patterns:
                if re.match(pattern, intf_name, re.IGNORECASE):
                    logger.debug(f"Пропуск интерфейса {intf_name} (паттерн: {pattern})")
                    excluded = True
                    break
            if excluded:
                stats["skipped"] += 1
                continue

            if intf_name in existing:
                # Обновляем существующий
                if update_existing:
                    self._update_interface(existing[intf_name], intf_data)
                    stats["updated"] += 1
                else:
                    stats["skipped"] += 1
            else:
                # Создаём новый
                if create_missing:
                    self._create_interface(device.id, intf_name, intf_data)
                    stats["created"] += 1
                else:
                    stats["skipped"] += 1

        logger.info(
            f"Синхронизация интерфейсов {device_name}: "
            f"создано={stats['created']}, обновлено={stats['updated']}, "
            f"пропущено={stats['skipped']}"
        )
        return stats

    def _create_interface(
        self,
        device_id: int,
        name: str,
        data: Dict[str, Any],
    ) -> None:
        """Создаёт интерфейс в NetBox."""
        sync_cfg = get_sync_config("interfaces")

        if self.dry_run:
            logger.info(f"[DRY-RUN] Создание интерфейса: {name}")
            return

        # Формируем данные согласно настройкам
        kwargs = {}
        if sync_cfg.is_field_enabled("description"):
            kwargs["description"] = data.get("description", "")
        if sync_cfg.is_field_enabled("enabled"):
            kwargs["enabled"] = data.get("status", "up") == "up"
        # MAC будет добавлен отдельно через assign_mac_to_interface (NetBox 4.x)
        mac_to_assign = None
        if sync_cfg.is_field_enabled("mac_address") and data.get("mac"):
            mac_to_assign = self._normalize_mac(data.get("mac", ""))
        if sync_cfg.is_field_enabled("mtu") and data.get("mtu"):
            try:
                kwargs["mtu"] = int(data.get("mtu"))
            except (ValueError, TypeError):
                pass
        if sync_cfg.is_field_enabled("speed") and data.get("speed"):
            # speed в NetBox в kbps
            kwargs["speed"] = self._parse_speed(data.get("speed", ""))
        if sync_cfg.is_field_enabled("duplex") and data.get("duplex"):
            kwargs["duplex"] = self._parse_duplex(data.get("duplex", ""))

        # 802.1Q mode (access, tagged, tagged-all)
        if sync_cfg.is_field_enabled("mode") and data.get("mode"):
            kwargs["mode"] = data.get("mode")

        # Получаем LAG интерфейс если указан
        lag_name = data.get("lag")
        if lag_name:
            lag_interface = self.client.get_interface_by_name(device_id, lag_name)
            if lag_interface:
                kwargs["lag"] = lag_interface.id
            else:
                logger.debug(f"LAG интерфейс {lag_name} не найден в NetBox")

        interface = self.client.create_interface(
            device_id=device_id,
            name=name,
            interface_type=self._get_interface_type(data),
            **kwargs,
        )

        # Привязываем MAC-адрес (NetBox 4.x - отдельная модель)
        if mac_to_assign and interface:
            self.client.assign_mac_to_interface(interface.id, mac_to_assign)

    def _normalize_mac(self, mac: str) -> str:
        """Нормализует MAC в формат NetBox (AA:BB:CC:DD:EE:FF)."""
        if not mac:
            return ""
        # Убираем все разделители
        mac_clean = mac.replace(":", "").replace("-", "").replace(".", "").upper()
        if len(mac_clean) != 12:
            return ""
        # Форматируем с двоеточиями
        return ":".join(mac_clean[i:i+2] for i in range(0, 12, 2))

    def _parse_speed(self, speed_str: str) -> Optional[int]:
        """Парсит скорость в kbps для NetBox."""
        if not speed_str:
            return None
        speed_str = speed_str.lower()
        try:
            # "10000 Kbit" → 10000
            if "kbit" in speed_str:
                return int(speed_str.split()[0])
            # "1 Gbit" → 1000000
            if "gbit" in speed_str:
                return int(float(speed_str.split()[0]) * 1000000)
            # "100 Mbit" → 100000
            if "mbit" in speed_str:
                return int(float(speed_str.split()[0]) * 1000)
            # Просто число - считаем kbps
            return int(speed_str.split()[0])
        except (ValueError, IndexError):
            return None

    def _parse_duplex(self, duplex_str: str) -> Optional[str]:
        """Парсит duplex для NetBox (half, full, auto)."""
        if not duplex_str:
            return None
        duplex_lower = duplex_str.lower()
        if "full" in duplex_lower:
            return "full"
        if "half" in duplex_lower:
            return "half"
        if "auto" in duplex_lower:
            return "auto"
        return None

    def _get_interface_type(self, data: Dict[str, Any]) -> str:
        """
        Определяет тип интерфейса для NetBox на основе hardware_type, media_type, скорости.

        Приоритет определения:
        1. media_type (наиболее точный: "10/100/1000BaseTX", "SFP-10GBase-SR")
        2. hardware_type ("Gigabit Ethernet", "Ten Gigabit Ethernet SFP+")
        3. speed + имя интерфейса (fallback)

        Маппинги типов определены в core/constants.py:
        - NETBOX_INTERFACE_TYPE_MAP (media_type → NetBox type)
        - NETBOX_HARDWARE_TYPE_MAP (hardware_type → NetBox type)

        Args:
            data: Данные интерфейса

        Returns:
            str: Тип интерфейса для NetBox API
        """
        sync_cfg = get_sync_config("interfaces")

        # Проверяем включено ли автоопределение
        if not sync_cfg.get_option("auto_detect_type", True):
            return sync_cfg.get_default("type", "1000base-t")

        hardware_type = data.get("hardware_type", "").lower()
        media_type = data.get("media_type", "").lower()
        interface_name = data.get("interface", data.get("name", "")).lower()
        speed_str = data.get("speed", "")

        # LAG интерфейсы (Port-channel, Po)
        if interface_name.startswith(("port-channel", "po")):
            return "lag"

        # Виртуальные интерфейсы (Vlan, Loopback, и т.д.)
        if interface_name.startswith(VIRTUAL_INTERFACE_PREFIXES):
            return "virtual"

        # Management интерфейсы - всегда медь
        if any(x in interface_name for x in MGMT_INTERFACE_PATTERNS):
            return "1000base-t"

        # 1. Определяем по media_type (маппинг из constants.py)
        if media_type and media_type not in ("unknown", "not present", ""):
            for pattern, netbox_type in NETBOX_INTERFACE_TYPE_MAP.items():
                if pattern in media_type:
                    return netbox_type

            # Универсальный SFP для 1G если не определился конкретный
            if "sfp" in media_type and ("1000base" in media_type or "1g" in media_type):
                if "baset" in media_type:
                    return "1000base-t"  # SFP-T (медный SFP)
                return "1000base-x-sfp"

        # 2. Определяем по hardware_type (маппинг из constants.py)
        if hardware_type and hardware_type not in ("amdp2", "ethersvi", ""):
            for pattern, netbox_type in NETBOX_HARDWARE_TYPE_MAP.items():
                if pattern in hardware_type:
                    # Для 10G проверяем SFP в названии
                    if "10g" in pattern and "sfp" in hardware_type:
                        return "10gbase-x-sfpp"
                    # Для 1G проверяем SFP
                    if pattern in ("gigabit", "gige", "igbe", "1g") and "sfp" in hardware_type:
                        return "1000base-x-sfp"
                    return netbox_type

        # 3. Fallback: по скорости и имени интерфейса
        speed_kbps = self._parse_speed(speed_str)
        speed_mbps = speed_kbps // 1000 if speed_kbps else None

        # Определяем тип по имени интерфейса
        is_sfp = any(x in interface_name for x in ["sfp", "xfp", "qsfp"])
        is_tengig = any(x in interface_name for x in ["te", "tengig", "ten-gig", "xgig"])
        is_fortygig = any(x in interface_name for x in ["fo", "forty", "qsfp"])
        is_hundredgig = any(x in interface_name for x in ["hu", "hundred"])

        # По имени интерфейса без скорости
        if is_hundredgig:
            return "100gbase-x-qsfp28"
        if is_fortygig:
            return "40gbase-x-qsfpp"
        if is_tengig:
            return "10gbase-x-sfpp"

        # По скорости
        if speed_mbps:
            if speed_mbps <= 1000:
                return "1000base-x-sfp" if is_sfp else "1000base-t"
            elif speed_mbps <= 2500:
                return "2.5gbase-t"
            elif speed_mbps <= 5000:
                return "5gbase-t"
            elif speed_mbps <= 10000:
                return "10gbase-x-sfpp" if (is_sfp or is_tengig) else "10gbase-t"
            elif speed_mbps <= 25000:
                return "25gbase-x-sfp28"
            elif speed_mbps <= 40000:
                return "40gbase-x-qsfpp"
            elif speed_mbps <= 100000:
                return "100gbase-x-qsfp28"

        # Fallback: по умолчанию из конфига
        return sync_cfg.get_default("type", "1000base-t")

    def _update_interface(
        self,
        interface,
        data: Dict[str, Any],
    ) -> None:
        """Обновляет интерфейс в NetBox."""
        updates = {}
        sync_cfg = get_sync_config("interfaces")

        # Обновляем тип интерфейса если auto_detect_type включен
        if sync_cfg.get_option("auto_detect_type", True):
            new_type = self._get_interface_type(data)
            current_type = getattr(interface.type, 'value', None) if interface.type else None
            if new_type and new_type != current_type:
                updates["type"] = new_type

        # Проверяем что нужно обновить (согласно настройкам)
        if sync_cfg.is_field_enabled("description"):
            if "description" in data and data["description"] != interface.description:
                updates["description"] = data["description"]

        if sync_cfg.is_field_enabled("enabled"):
            if "status" in data:
                enabled = data["status"] == "up"
                if enabled != interface.enabled:
                    updates["enabled"] = enabled

        # MAC обрабатывается отдельно через assign_mac_to_interface (NetBox 4.x)
        mac_to_assign = None
        if sync_cfg.is_field_enabled("mac_address"):
            if data.get("mac"):
                new_mac = self._normalize_mac(data.get("mac", ""))
                # Проверяем текущий MAC через client
                current_mac = self.client.get_interface_mac(interface.id) if not self.dry_run else None
                if new_mac and new_mac != (current_mac or ""):
                    mac_to_assign = new_mac

        if sync_cfg.is_field_enabled("mtu"):
            if data.get("mtu"):
                try:
                    new_mtu = int(data.get("mtu"))
                    if new_mtu != (interface.mtu or 0):
                        updates["mtu"] = new_mtu
                except (ValueError, TypeError):
                    pass

        if sync_cfg.is_field_enabled("speed"):
            if data.get("speed"):
                new_speed = self._parse_speed(data.get("speed", ""))
                if new_speed and new_speed != (interface.speed or 0):
                    updates["speed"] = new_speed

        if sync_cfg.is_field_enabled("duplex"):
            if data.get("duplex"):
                new_duplex = self._parse_duplex(data.get("duplex", ""))
                current_duplex = getattr(interface.duplex, 'value', None) if interface.duplex else None
                if new_duplex and new_duplex != current_duplex:
                    updates["duplex"] = new_duplex

        # 802.1Q mode
        if sync_cfg.is_field_enabled("mode"):
            if data.get("mode"):
                new_mode = data.get("mode")
                current_mode = getattr(interface.mode, 'value', None) if interface.mode else None
                if new_mode and new_mode != current_mode:
                    updates["mode"] = new_mode

        # Обновляем LAG привязку
        lag_name = data.get("lag")
        if lag_name:
            # Получаем device_id из интерфейса
            device_id = getattr(interface.device, 'id', None) if interface.device else None
            if device_id:
                lag_interface = self.client.get_interface_by_name(device_id, lag_name)
                if lag_interface:
                    current_lag_id = getattr(interface.lag, 'id', None) if interface.lag else None
                    if lag_interface.id != current_lag_id:
                        updates["lag"] = lag_interface.id
                else:
                    logger.debug(f"LAG интерфейс {lag_name} не найден в NetBox")

        if not updates and not mac_to_assign:
            return

        if self.dry_run:
            if updates:
                logger.info(f"[DRY-RUN] Обновление интерфейса {interface.name}: {updates}")
            if mac_to_assign:
                logger.info(f"[DRY-RUN] Назначение MAC {mac_to_assign} на {interface.name}")
            return

        if updates:
            self.client.update_interface(interface.id, **updates)

        # Привязываем MAC-адрес (NetBox 4.x - отдельная модель)
        if mac_to_assign:
            self.client.assign_mac_to_interface(interface.id, mac_to_assign)

    # ==================== КАБЕЛИ ИЗ LLDP/CDP ====================

    def sync_cables_from_lldp(
        self,
        lldp_data: List[Dict[str, Any]],
        skip_unknown: bool = True,
    ) -> Dict[str, int]:
        """
        Создаёт кабели в NetBox на основе LLDP/CDP данных.

        Логика поиска соседа:
        1. По hostname (если neighbor_type == "hostname")
        2. По MAC-адресу (если neighbor_type == "mac")
        3. По IP-адресу (если neighbor_type == "ip")
        4. Пропустить (если neighbor_type == "unknown" и skip_unknown=True)

        Args:
            lldp_data: Данные LLDP/CDP с полями:
                - hostname: Локальное устройство
                - local_interface: Локальный интерфейс
                - remote_hostname: Имя соседа
                - remote_port: Порт соседа
                - remote_mac: MAC соседа (опционально)
                - remote_ip: IP соседа (опционально)
                - neighbor_type: Тип идентификации
            skip_unknown: Пропускать соседей с типом "unknown"

        Returns:
            Dict: Статистика {created, skipped, failed, already_exists}
        """
        stats = {"created": 0, "skipped": 0, "failed": 0, "already_exists": 0}

        for entry in lldp_data:
            local_device = entry.get("hostname")
            local_intf = entry.get("local_interface")
            remote_hostname = entry.get("remote_hostname")
            remote_port = entry.get("remote_port")
            neighbor_type = entry.get("neighbor_type", "unknown")

            # Пропускаем unknown если указано
            if neighbor_type == "unknown" and skip_unknown:
                logger.debug(f"Пропущен unknown сосед на {local_device}:{local_intf}")
                stats["skipped"] += 1
                continue

            # Ищем локальное устройство и интерфейс
            local_device_obj = self._find_device(local_device)
            if not local_device_obj:
                logger.warning(f"Устройство не найдено в NetBox: {local_device}")
                stats["failed"] += 1
                continue

            local_intf_obj = self._find_interface(local_device_obj.id, local_intf)
            if not local_intf_obj:
                logger.warning(f"Интерфейс не найден: {local_device}:{local_intf}")
                stats["failed"] += 1
                continue

            # Ищем удалённое устройство
            remote_device_obj = self._find_neighbor_device(entry, neighbor_type)
            if not remote_device_obj:
                logger.warning(
                    f"Сосед не найден в NetBox: {remote_hostname} "
                    f"(тип: {neighbor_type})"
                )
                stats["skipped"] += 1
                continue

            # Ищем удалённый интерфейс
            remote_intf_obj = self._find_interface(remote_device_obj.id, remote_port)
            if not remote_intf_obj:
                logger.warning(
                    f"Интерфейс соседа не найден: "
                    f"{remote_device_obj.name}:{remote_port}"
                )
                stats["skipped"] += 1
                continue

            # Если интерфейс входит в LAG, кабель создаём на LAG а не на member
            local_cable_intf = self._get_lag_or_self(local_intf_obj)
            remote_cable_intf = self._get_lag_or_self(remote_intf_obj)

            # Логируем если был редирект на LAG
            if local_cable_intf.id != local_intf_obj.id:
                logger.info(
                    f"  {local_device}:{local_intf} → LAG {local_cable_intf.name}"
                )
            if remote_cable_intf.id != remote_intf_obj.id:
                logger.info(
                    f"  {remote_device_obj.name}:{remote_port} → LAG {remote_cable_intf.name}"
                )

            # Создаём кабель (на LAG если member, иначе на исходный интерфейс)
            result = self._create_cable(local_cable_intf, remote_cable_intf)

            if result == "created":
                stats["created"] += 1
            elif result == "exists":
                stats["already_exists"] += 1
            else:
                stats["failed"] += 1

        logger.info(
            f"Синхронизация кабелей: создано={stats['created']}, "
            f"существует={stats['already_exists']}, "
            f"пропущено={stats['skipped']}, ошибок={stats['failed']}"
        )
        return stats

    def _find_device(self, name: str) -> Optional[Any]:
        """
        Находит устройство в NetBox (с кэшированием).

        Args:
            name: Имя устройства

        Returns:
            Device или None
        """
        if name in self._device_cache:
            return self._device_cache[name]

        device = self.client.get_device_by_name(name)
        if device:
            self._device_cache[name] = device
        return device

    def _find_interface(self, device_id: int, interface_name: str) -> Optional[Any]:
        """
        Находит интерфейс устройства.

        Args:
            device_id: ID устройства
            interface_name: Имя интерфейса

        Returns:
            Interface или None
        """
        interfaces = self.client.get_interfaces(device_id=device_id)

        # Точное совпадение
        for intf in interfaces:
            if intf.name == interface_name:
                return intf

        # Попробуем нормализованное имя (Gi0/1 vs GigabitEthernet0/1)
        normalized = self._normalize_interface_name(interface_name)
        for intf in interfaces:
            if self._normalize_interface_name(intf.name) == normalized:
                return intf

        return None

    def _normalize_interface_name(self, name: str) -> str:
        """
        Нормализует имя интерфейса для сравнения.

        Args:
            name: Имя интерфейса

        Returns:
            str: Нормализованное имя
        """
        # Убираем лишние пробелы и расширяем сокращения
        name = normalize_interface_full(name.strip())
        return name.lower()

    def _find_neighbor_device(
        self,
        entry: Dict[str, Any],
        neighbor_type: str,
    ) -> Optional[Any]:
        """
        Ищет устройство соседа в NetBox.

        Стратегия поиска зависит от neighbor_type:
        - hostname: Поиск по имени
        - mac: Поиск по MAC-адресу интерфейса
        - ip: Поиск по IP-адресу

        Args:
            entry: Данные LLDP
            neighbor_type: Тип идентификации

        Returns:
            Device или None
        """
        if neighbor_type == "hostname":
            hostname = entry.get("remote_hostname", "")
            # Убираем domain если есть (switch-01.domain.local → switch-01)
            hostname = hostname.split(".")[0] if "." in hostname else hostname
            return self._find_device(hostname)

        elif neighbor_type == "mac":
            mac = entry.get("remote_mac")
            if mac:
                return self._find_device_by_mac(mac)

        elif neighbor_type == "ip":
            ip = entry.get("remote_ip")
            if ip:
                return self.client.get_device_by_ip(ip)

        return None

    def _find_device_by_mac(self, mac: str) -> Optional[Any]:
        """
        Ищет устройство по MAC-адресу интерфейса.

        Args:
            mac: MAC-адрес

        Returns:
            Device или None
        """
        # Нормализуем MAC
        mac_normalized = mac.replace(":", "").replace("-", "").replace(".", "").lower()

        # Кэш
        if mac_normalized in self._mac_cache:
            return self._mac_cache[mac_normalized]

        # Ищем интерфейс с таким MAC
        # В NetBox MAC хранится в формате 00:11:22:33:44:55
        mac_formatted = ":".join(mac_normalized[i : i + 2] for i in range(0, 12, 2))

        try:
            interfaces = list(
                self.client.api.dcim.interfaces.filter(mac_address=mac_formatted)
            )
            if interfaces and interfaces[0].device:
                device = interfaces[0].device
                self._mac_cache[mac_normalized] = device
                return device
        except Exception as e:
            logger.debug(f"Ошибка поиска по MAC {mac}: {e}")

        return None

    def _get_lag_or_self(self, interface) -> Any:
        """
        Возвращает LAG интерфейс если интерфейс является его членом,
        иначе возвращает сам интерфейс.

        Используется для создания кабелей: если физический порт входит в LAG,
        кабель должен создаваться на LAG интерфейсе, а не на member порту.

        Args:
            interface: Интерфейс NetBox

        Returns:
            LAG интерфейс или исходный интерфейс
        """
        if hasattr(interface, "lag") and interface.lag:
            lag_intf = interface.lag
            logger.debug(
                f"Интерфейс {interface.name} входит в LAG {lag_intf.name}, "
                f"кабель будет на LAG"
            )
            return lag_intf
        return interface

    def _create_cable(
        self,
        interface_a,
        interface_b,
    ) -> str:
        """
        Создаёт кабель между интерфейсами.

        Args:
            interface_a: Первый интерфейс
            interface_b: Второй интерфейс

        Returns:
            str: "created", "exists", "error"
        """
        # Проверяем что кабель уже не существует
        if interface_a.cable or interface_b.cable:
            return "exists"

        if self.create_only is False and self.update_only:
            # В режиме update_only не создаём новые
            return "exists"

        if self.dry_run:
            logger.info(
                f"[DRY-RUN] Создание кабеля: "
                f"{interface_a.device.name}:{interface_a.name} ↔ "
                f"{interface_b.device.name}:{interface_b.name}"
            )
            return "created"

        try:
            self.client.api.dcim.cables.create(
                {
                    "a_terminations": [
                        {
                            "object_type": "dcim.interface",
                            "object_id": interface_a.id,
                        }
                    ],
                    "b_terminations": [
                        {
                            "object_type": "dcim.interface",
                            "object_id": interface_b.id,
                        }
                    ],
                    "status": "connected",
                }
            )
            logger.info(
                f"Создан кабель: {interface_a.device.name}:{interface_a.name} ↔ "
                f"{interface_b.device.name}:{interface_b.name}"
            )
            return "created"
        except Exception as e:
            logger.error(f"Ошибка создания кабеля: {e}")
            return "error"

    # ==================== IP-АДРЕСА ====================

    def sync_ip_addresses(
        self,
        device_name: str,
        ip_data: List[Dict[str, Any]],
    ) -> Dict[str, int]:
        """
        Синхронизирует IP-адреса устройства с NetBox.

        Args:
            device_name: Имя устройства в NetBox
            ip_data: Список IP-адресов с полями:
                - interface: Имя интерфейса
                - ip_address: IP-адрес (может быть с маской или без)
                - mask или prefix_length: Маска сети

        Returns:
            Dict: Статистика {created, updated, skipped, failed}
        """
        stats = {"created": 0, "updated": 0, "skipped": 0, "failed": 0}

        # Получаем устройство
        device = self.client.get_device_by_name(device_name)
        if not device:
            logger.error(f"Устройство не найдено в NetBox: {device_name}")
            return stats

        # Получаем существующие интерфейсы
        interfaces = {
            intf.name: intf for intf in self.client.get_interfaces(device_id=device.id)
        }

        # Получаем существующие IP-адреса устройства
        existing_ips = {}
        for ip in self.client.get_ip_addresses(device_id=device.id):
            if ip.address:
                # Убираем маску для ключа
                ip_only = str(ip.address).split("/")[0]
                existing_ips[ip_only] = ip

        for entry in ip_data:
            interface_name = entry.get("interface", "")
            ip_address = entry.get("ip_address", "")

            if not interface_name or not ip_address:
                continue

            # Нормализуем IP (убираем маску если есть)
            ip_only = ip_address.split("/")[0]

            # Определяем маску
            if "/" in ip_address:
                ip_with_mask = ip_address
            else:
                mask = entry.get("mask", entry.get("prefix_length", "24"))
                # Если маска в формате 255.255.255.0, конвертируем
                if "." in str(mask):
                    mask = self._mask_to_prefix(mask)
                ip_with_mask = f"{ip_only}/{mask}"

            # Ищем интерфейс
            intf = self._find_interface(device.id, interface_name)
            if not intf:
                # Попробуем найти с нормализацией
                normalized_name = self._normalize_interface_name(interface_name)
                for name, i in interfaces.items():
                    if self._normalize_interface_name(name) == normalized_name:
                        intf = i
                        break

            if not intf:
                logger.warning(f"Интерфейс не найден: {device_name}:{interface_name}")
                stats["failed"] += 1
                continue

            # Проверяем существует ли IP
            if ip_only in existing_ips:
                stats["skipped"] += 1
                continue

            # Создаём IP-адрес
            if self.dry_run:
                logger.info(f"[DRY-RUN] Создание IP: {ip_with_mask} на {interface_name}")
                stats["created"] += 1
                continue

            try:
                self.client.create_ip_address(
                    address=ip_with_mask,
                    interface_id=intf.id,
                    status="active",
                )
                logger.info(f"Создан IP: {ip_with_mask} на {device_name}:{interface_name}")
                stats["created"] += 1
            except Exception as e:
                logger.error(f"Ошибка создания IP {ip_with_mask}: {e}")
                stats["failed"] += 1

        logger.info(
            f"Синхронизация IP {device_name}: создано={stats['created']}, "
            f"пропущено={stats['skipped']}, ошибок={stats['failed']}"
        )
        return stats

    def _mask_to_prefix(self, mask: str) -> int:
        """
        Конвертирует маску сети в длину префикса.

        Args:
            mask: Маска в формате 255.255.255.0

        Returns:
            int: Длина префикса (например, 24)
        """
        try:
            octets = [int(x) for x in mask.split(".")]
            binary = "".join(format(x, "08b") for x in octets)
            return binary.count("1")
        except Exception:
            return DEFAULT_PREFIX_LENGTH

    # ==================== СОЗДАНИЕ УСТРОЙСТВ ====================

    def create_device(
        self,
        name: str,
        device_type: str,
        site: Optional[str] = None,
        role: Optional[str] = None,
        manufacturer: Optional[str] = None,
        serial: str = "",
        status: Optional[str] = None,
        platform: str = "",
        primary_ip: str = "",
        tenant: Optional[str] = None,
    ) -> Optional[Any]:
        """
        Создаёт устройство в NetBox.

        Сначала проверяет/создаёт зависимые объекты:
        - Manufacturer
        - Device Type
        - Site
        - Device Role
        - Tenant (опционально)

        Args:
            name: Имя устройства (hostname)
            device_type: Тип/модель устройства (например, "WS-C2960-24TT-L")
            site: Название сайта (None = из config)
            role: Роль устройства (None = из config)
            manufacturer: Производитель (None = из config)
            serial: Серийный номер
            status: Статус (None = из config)
            platform: Платформа (cisco_ios, etc.)
            primary_ip: Primary IP (без маски)
            tenant: Арендатор (None = из config)

        Returns:
            Device или None при ошибке
        """
        sync_cfg = get_sync_config("devices")

        # Используем дефолты из config если не указаны
        if site is None:
            site = sync_cfg.get_default("site", "Main")
        if role is None:
            role = sync_cfg.get_default("role", "switch")
        if manufacturer is None:
            manufacturer = sync_cfg.get_default("manufacturer", "Cisco")
        if status is None:
            status = sync_cfg.get_default("status", "active")
        if tenant is None:
            tenant = sync_cfg.get_default("tenant", None)

        # Проверяем не существует ли уже
        existing = self.client.get_device_by_name(name)
        if existing:
            logger.info(f"Устройство {name} уже существует в NetBox")
            return existing

        if self.dry_run:
            tenant_info = f", tenant={tenant}" if tenant else ""
            logger.info(
                f"[DRY-RUN] Создание устройства: {name} "
                f"(type={device_type}, site={site}, role={role}{tenant_info})"
            )
            return None

        try:
            # Получаем или создаём Manufacturer
            mfr = self._get_or_create_manufacturer(manufacturer)
            if not mfr:
                logger.error(f"Не удалось создать производителя: {manufacturer}")
                return None

            # Получаем или создаём Device Type
            dtype = self._get_or_create_device_type(device_type, mfr.id)
            if not dtype:
                logger.error(f"Не удалось создать тип устройства: {device_type}")
                return None

            # Получаем или создаём Site
            site_obj = self._get_or_create_site(site)
            if not site_obj:
                logger.error(f"Не удалось создать сайт: {site}")
                return None

            # Получаем или создаём Role
            role_obj = self._get_or_create_role(role)
            if not role_obj:
                logger.error(f"Не удалось создать роль: {role}")
                return None

            # Получаем или создаём Tenant (опционально)
            tenant_obj = None
            if tenant:
                tenant_obj = self._get_or_create_tenant(tenant)
                if not tenant_obj:
                    logger.warning(f"Не удалось создать tenant: {tenant}")

            # Создаём устройство
            device_data = {
                "name": name,
                "device_type": dtype.id,
                "site": site_obj.id,
                "role": role_obj.id,
                "status": status,
            }

            if serial:
                device_data["serial"] = serial

            if tenant_obj:
                device_data["tenant"] = tenant_obj.id

            if platform:
                platform_obj = self._get_or_create_platform(platform)
                if platform_obj:
                    device_data["platform"] = platform_obj.id

            device = self.client.api.dcim.devices.create(device_data)
            logger.info(f"Создано устройство: {name}")

            # Добавляем Primary IP если указан
            if primary_ip and device:
                self._set_primary_ip(device, primary_ip)

            return device

        except Exception as e:
            logger.error(f"Ошибка создания устройства {name}: {e}")
            return None

    def sync_devices_from_inventory(
        self,
        inventory_data: List[Dict[str, Any]],
        site: str = "Main",
        role: str = "switch",
        update_existing: bool = True,
        cleanup: bool = False,
        tenant: Optional[str] = None,
    ) -> Dict[str, int]:
        """
        Синхронизирует устройства в NetBox из инвентаризационных данных.

        Создаёт новые устройства, обновляет существующие и опционально
        удаляет устройства которых нет в списке.

        Args:
            inventory_data: Данные от DeviceInventoryCollector с полями:
                - name/hostname: Имя устройства
                - model: Модель
                - serial: Серийный номер
                - manufacturer: Производитель
                - ip_address: IP-адрес
                - platform: Платформа
            site: Сайт по умолчанию
            role: Роль по умолчанию
            update_existing: Обновлять существующие устройства
            cleanup: Удалять устройства не из списка (для данного site и tenant)
            tenant: Арендатор - ОБЯЗАТЕЛЕН для cleanup, фильтрует какие устройства удалять

        Returns:
            Dict: Статистика {created, updated, skipped, deleted, failed}
        """
        stats = {"created": 0, "updated": 0, "skipped": 0, "deleted": 0, "failed": 0}

        # Собираем имена устройств из инвентаризации
        inventory_names = set()

        for entry in inventory_data:
            name = entry.get("name", entry.get("hostname", ""))
            model = entry.get("model") or "Unknown"
            serial = entry.get("serial", "")
            manufacturer = entry.get("manufacturer") or "Cisco"
            ip_address = entry.get("ip_address", "")
            platform = entry.get("platform", "")
            # Параметры CLI имеют приоритет над значениями из inventory_data
            # site и role из CLI передаются в функцию, используем их
            # entry.get("site") используется только если site не передан в функцию

            if not name:
                logger.warning("Пропущена запись без имени устройства")
                stats["failed"] += 1
                continue

            inventory_names.add(name)

            # Проверяем существует ли
            existing = self.client.get_device_by_name(name)
            if existing:
                if update_existing:
                    # Обновляем существующее устройство (включая tenant, site, role)
                    updated = self._update_device(
                        existing,
                        model=model,
                        serial=serial,
                        manufacturer=manufacturer,
                        platform=platform,
                        tenant=tenant,
                        site=site,
                        role=role,
                    )
                    if updated:
                        stats["updated"] += 1
                    else:
                        stats["skipped"] += 1
                else:
                    logger.debug(f"Устройство {name} уже существует")
                    stats["skipped"] += 1
                continue

            # Создаём новое устройство
            # site, role, tenant берутся из параметров функции (CLI)
            result = self.create_device(
                name=name,
                device_type=model,
                site=site,
                role=role,
                manufacturer=manufacturer,
                serial=serial,
                platform=platform,
                primary_ip=ip_address,
                tenant=tenant,
            )

            if result:
                stats["created"] += 1
            else:
                if not self.dry_run:
                    stats["failed"] += 1
                else:
                    stats["created"] += 1

        # Удаляем устройства не из списка
        if cleanup and tenant:
            deleted = self._cleanup_devices(inventory_names, site, tenant)
            stats["deleted"] = deleted

        logger.info(
            f"Синхронизация устройств: создано={stats['created']}, "
            f"обновлено={stats['updated']}, пропущено={stats['skipped']}, "
            f"удалено={stats['deleted']}, ошибок={stats['failed']}"
        )
        return stats

    def _update_device(
        self,
        device,
        model: str = "",
        serial: str = "",
        manufacturer: str = "",
        platform: str = "",
        tenant: Optional[str] = None,
        site: Optional[str] = None,
        role: Optional[str] = None,
    ) -> bool:
        """
        Обновляет существующее устройство в NetBox.

        Args:
            device: Объект устройства из pynetbox
            model: Новая модель
            serial: Новый серийный номер
            manufacturer: Производитель
            platform: Платформа
            tenant: Арендатор
            site: Сайт
            role: Роль

        Returns:
            bool: True если были изменения
        """
        updates = {}

        # Проверяем серийный номер
        if serial and serial != device.serial:
            updates["serial"] = serial

        # Проверяем device_type (модель)
        if model and model != "Unknown":
            current_model = device.device_type.model if device.device_type else ""
            normalized_model = normalize_device_model(model)
            # Сравниваем нормализованные значения
            if normalized_model != current_model:
                # Получаем или создаём тип устройства
                mfr = self._get_or_create_manufacturer(manufacturer or "Cisco")
                if mfr:
                    dtype = self._get_or_create_device_type(model, mfr.id)
                    if dtype:
                        updates["device_type"] = dtype.id

        # Проверяем платформу
        if platform:
            current_platform = device.platform.name if device.platform else ""
            if platform != current_platform:
                platform_obj = self._get_or_create_platform(platform)
                if platform_obj:
                    updates["platform"] = platform_obj.id

        # Проверяем tenant
        if tenant:
            current_tenant = device.tenant.name if device.tenant else ""
            if tenant != current_tenant:
                tenant_obj = self._get_or_create_tenant(tenant)
                if tenant_obj:
                    updates["tenant"] = tenant_obj.id

        # Проверяем site
        if site:
            current_site = device.site.name if device.site else ""
            if site != current_site:
                site_obj = self._get_or_create_site(site)
                if site_obj:
                    updates["site"] = site_obj.id

        # Проверяем role
        if role:
            current_role = device.role.name if device.role else ""
            if role != current_role:
                role_obj = self._get_or_create_role(role)
                if role_obj:
                    updates["role"] = role_obj.id

        if not updates:
            return False

        if self.dry_run:
            logger.info(f"[DRY-RUN] Обновление устройства {device.name}: {updates}")
            return True

        try:
            device.update(updates)
            logger.info(f"Обновлено устройство: {device.name}")
            return True
        except Exception as e:
            logger.error(f"Ошибка обновления устройства {device.name}: {e}")
            return False

    def _cleanup_devices(
        self,
        inventory_names: set,
        site: str,
        tenant: str,
    ) -> int:
        """
        Удаляет устройства из NetBox которых нет в списке инвентаризации.

        ВАЖНО: Удаляются ТОЛЬКО устройства указанного tenant!
        Это защищает от случайного удаления устройств других пользователей.

        Args:
            inventory_names: Множество имён устройств из инвентаризации
            site: Сайт для фильтрации (name или slug)
            tenant: Арендатор - удаляются только устройства этого tenant

        Returns:
            int: Количество удалённых устройств
        """
        deleted = 0

        # Получаем все устройства на сайте И с нужным tenant
        try:
            # Преобразуем name в slug если нужно
            site_slug = site.lower().replace(" ", "-")
            tenant_slug = tenant.lower().replace(" ", "-")

            # Фильтруем по site и tenant
            netbox_devices = self.client.get_devices(site=site_slug, tenant=tenant_slug)
            logger.info(
                f"Найдено {len(netbox_devices)} устройств для проверки "
                f"(site={site_slug}, tenant={tenant_slug})"
            )
        except Exception as e:
            logger.error(f"Ошибка получения устройств из NetBox: {e}")
            return 0

        for device in netbox_devices:
            if device.name not in inventory_names:
                # Дополнительная проверка tenant на всякий случай
                device_tenant = device.tenant.slug if device.tenant else None
                if device_tenant != tenant_slug:
                    logger.debug(
                        f"Пропуск {device.name}: tenant={device_tenant} != {tenant_slug}"
                    )
                    continue

                if self.dry_run:
                    logger.info(f"[DRY-RUN] Удаление устройства: {device.name}")
                    deleted += 1
                else:
                    try:
                        device.delete()
                        logger.info(f"Удалено устройство: {device.name}")
                        deleted += 1
                    except Exception as e:
                        logger.error(f"Ошибка удаления устройства {device.name}: {e}")

        return deleted

    def create_devices_from_inventory(
        self,
        inventory_data: List[Dict[str, Any]],
        site: str = "Main",
        role: str = "switch",
    ) -> Dict[str, int]:
        """
        Создаёт устройства в NetBox из инвентаризационных данных.

        DEPRECATED: Используйте sync_devices_from_inventory для полной синхронизации.

        Args:
            inventory_data: Данные от DeviceInventoryCollector
            site: Сайт по умолчанию
            role: Роль по умолчанию

        Returns:
            Dict: Статистика {created, skipped, failed}
        """
        # Вызываем новый метод без обновления и cleanup
        result = self.sync_devices_from_inventory(
            inventory_data,
            site=site,
            role=role,
            update_existing=False,
            cleanup=False,
        )
        # Возвращаем в старом формате для совместимости
        return {
            "created": result["created"],
            "skipped": result["skipped"] + result["updated"],
            "failed": result["failed"],
        }

    # ==================== ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ====================

    def _get_or_create_manufacturer(self, name: str) -> Optional[Any]:
        """Получает или создаёт производителя."""
        try:
            mfr = self.client.api.dcim.manufacturers.get(name=name)
            if mfr:
                return mfr

            # Создаём
            slug = name.lower().replace(" ", "-")
            return self.client.api.dcim.manufacturers.create(
                {"name": name, "slug": slug}
            )
        except Exception as e:
            logger.error(f"Ошибка работы с производителем {name}: {e}")
            return None

    def _get_or_create_device_type(
        self,
        model: str,
        manufacturer_id: int,
    ) -> Optional[Any]:
        """Получает или создаёт тип устройства.

        Нормализует модель перед поиском/созданием:
        - WS-C2960C-8TC-L → C2960C-8TC
        """
        try:
            # Нормализуем модель (убираем WS- и лицензии)
            normalized_model = normalize_device_model(model)

            dtype = self.client.api.dcim.device_types.get(model=normalized_model)
            if dtype:
                return dtype

            # Создаём
            slug = normalized_model.lower().replace(" ", "-").replace("/", "-")
            return self.client.api.dcim.device_types.create({
                "model": normalized_model,
                "slug": slug,
                "manufacturer": manufacturer_id,
            })
        except Exception as e:
            logger.error(f"Ошибка работы с типом устройства {model} → {normalize_device_model(model)}: {e}")
            return None

    def _get_or_create_site(self, name: str) -> Optional[Any]:
        """Получает или создаёт сайт."""
        try:
            site = self.client.api.dcim.sites.get(name=name)
            if site:
                return site

            # Создаём
            slug = name.lower().replace(" ", "-")
            return self.client.api.dcim.sites.create(
                {"name": name, "slug": slug, "status": "active"}
            )
        except Exception as e:
            logger.error(f"Ошибка работы с сайтом {name}: {e}")
            return None

    def _get_or_create_role(self, name: str) -> Optional[Any]:
        """Получает или создаёт роль устройства."""
        try:
            role = self.client.api.dcim.device_roles.get(name=name)
            if role:
                return role

            # Создаём
            slug = name.lower().replace(" ", "-")
            return self.client.api.dcim.device_roles.create(
                {"name": name, "slug": slug, "color": "9e9e9e"}
            )
        except Exception as e:
            logger.error(f"Ошибка работы с ролью {name}: {e}")
            return None

    def _get_or_create_platform(self, name: str) -> Optional[Any]:
        """Получает или создаёт платформу."""
        try:
            platform = self.client.api.dcim.platforms.get(name=name)
            if platform:
                return platform

            # Создаём
            slug = name.lower().replace(" ", "-").replace("_", "-")
            return self.client.api.dcim.platforms.create(
                {"name": name, "slug": slug}
            )
        except Exception as e:
            logger.debug(f"Ошибка работы с платформой {name}: {e}")
            return None

    def _get_or_create_tenant(self, name: str) -> Optional[Any]:
        """Получает или создаёт арендатора (tenant)."""
        try:
            tenant = self.client.api.tenancy.tenants.get(name=name)
            if tenant:
                return tenant

            # Создаём (транслитерируем кириллицу для slug)
            slug = transliterate_to_slug(name)
            return self.client.api.tenancy.tenants.create(
                {"name": name, "slug": slug}
            )
        except Exception as e:
            logger.error(f"Ошибка работы с tenant {name}: {e}")
            return None

    def _set_primary_ip(self, device, ip_address: str) -> None:
        """Устанавливает primary IP для устройства."""
        try:
            # Ищем IP в NetBox
            ip_obj = self.client.api.ipam.ip_addresses.get(address=ip_address)
            if ip_obj:
                device.primary_ip4 = ip_obj.id
                device.save()
                logger.debug(f"Установлен primary IP: {ip_address}")
        except Exception as e:
            logger.debug(f"Не удалось установить primary IP: {e}")

    # ==================== VLAN ====================

    def sync_vlans_from_interfaces(
        self,
        device_name: str,
        interfaces: List[Dict[str, Any]],
        site: Optional[str] = None,
    ) -> Dict[str, int]:
        """
        Синхронизирует VLAN в NetBox на основе SVI интерфейсов.

        Логика:
        - Ищет интерфейсы с именем Vlan<N> или vlan<N>
        - Создаёт VLAN с номером N в NetBox
        - Имя VLAN берётся из description интерфейса (если есть)
        - Если description пустой, имя = "VLAN <N>"

        Args:
            device_name: Имя устройства в NetBox
            interfaces: Данные интерфейсов от InterfaceCollector
            site: Сайт для создания VLAN (опционально)

        Returns:
            Dict: Статистика {created, skipped, failed}

        Example:
            # Интерфейс Vlan10 с description "Management"
            # → Создаёт VLAN 10 с именем "Management"
        """
        import re

        stats = {"created": 0, "skipped": 0, "failed": 0}

        # Паттерн для извлечения номера VLAN из имени интерфейса
        vlan_pattern = re.compile(r"^[Vv]lan(\d+)$")

        # Собираем уникальные VLAN
        vlans_to_create = {}  # {vid: name}

        for intf in interfaces:
            intf_name = intf.get("interface", "")
            match = vlan_pattern.match(intf_name)
            if match:
                vid = int(match.group(1))
                # Имя VLAN = description интерфейса или "VLAN <N>"
                description = intf.get("description", "").strip()
                vlan_name = description if description else f"VLAN {vid}"
                vlans_to_create[vid] = vlan_name

        if not vlans_to_create:
            logger.info(f"VLAN SVI интерфейсы не найдены на {device_name}")
            return stats

        logger.info(f"Найдено {len(vlans_to_create)} VLAN SVI на {device_name}")

        # Создаём VLAN в NetBox
        for vid, name in vlans_to_create.items():
            # Проверяем существует ли
            existing = self.client.get_vlan_by_vid(vid, site=site)
            if existing:
                logger.debug(f"VLAN {vid} уже существует")
                stats["skipped"] += 1
                continue

            if self.dry_run:
                logger.info(f"[DRY-RUN] Создание VLAN: {vid} ({name})")
                stats["created"] += 1
                continue

            try:
                self.client.create_vlan(
                    vid=vid,
                    name=name,
                    site=site,
                    status="active",
                )
                stats["created"] += 1
            except Exception as e:
                logger.error(f"Ошибка создания VLAN {vid}: {e}")
                stats["failed"] += 1

        logger.info(
            f"Синхронизация VLAN {device_name}: "
            f"создано={stats['created']}, пропущено={stats['skipped']}, "
            f"ошибок={stats['failed']}"
        )
        return stats

    # ==================== INVENTORY ITEMS ====================

    def sync_inventory(
        self,
        device_name: str,
        inventory_data: List[Dict[str, Any]],
    ) -> Dict[str, int]:
        """
        Синхронизирует inventory items (модули, SFP, PSU) в NetBox.

        Args:
            device_name: Имя устройства в NetBox
            inventory_data: Данные от InventoryCollector:
                - name: Имя компонента
                - pid: Product ID (модель)
                - serial: Серийный номер
                - description: Описание
                - vid: Version ID (опционально)

        Returns:
            Dict: Статистика {created, updated, skipped, failed}

        Example:
            inventory_data = [
                {"name": "Chassis", "pid": "WS-C3750X", "serial": "FDO123"},
                {"name": "GigabitEthernet0/1", "pid": "SFP-1G-SX", "serial": "ABC"},
            ]
            sync.sync_inventory("switch1", inventory_data)
        """
        stats = {"created": 0, "updated": 0, "skipped": 0, "failed": 0}

        if not inventory_data:
            logger.info(f"Нет inventory данных для {device_name}")
            return stats

        # Ищем устройство в NetBox
        device = self._find_device(device_name)
        if not device:
            logger.error(f"Устройство не найдено в NetBox: {device_name}")
            return stats

        logger.info(f"Синхронизация inventory для {device_name}: {len(inventory_data)} компонентов")

        sync_cfg = config.sync.inventory

        for item in inventory_data:
            name = item.get("name", "").strip()
            pid = item.get("pid", "").strip()
            serial = item.get("serial", "").strip()
            description = item.get("description", "").strip()
            manufacturer = item.get("manufacturer", "").strip()

            if not name:
                continue

            # Пропускаем если нет серийника (скорее всего не физический компонент)
            if not serial:
                logger.debug(f"Пропущен {name} - нет серийного номера")
                stats["skipped"] += 1
                continue

            # Проверяем существует ли
            existing = self.client.get_inventory_item(device.id, name)

            if existing:
                # Обновляем если отличается (согласно настройкам)
                needs_update = False
                updates = {}

                if sync_cfg.sync_part_id and pid and existing.part_id != pid:
                    updates["part_id"] = pid
                    needs_update = True
                if sync_cfg.sync_serial and serial and existing.serial != serial:
                    updates["serial"] = serial
                    needs_update = True
                if sync_cfg.sync_description and description and existing.description != description:
                    updates["description"] = description
                    needs_update = True

                if needs_update:
                    if self.dry_run:
                        logger.info(f"[DRY-RUN] Обновление inventory: {name}")
                        stats["updated"] += 1
                    else:
                        try:
                            self.client.update_inventory_item(existing.id, **updates)
                            stats["updated"] += 1
                        except Exception as e:
                            logger.error(f"Ошибка обновления {name}: {e}")
                            stats["failed"] += 1
                else:
                    stats["skipped"] += 1
                continue

            # Создаём новый
            if self.dry_run:
                logger.info(f"[DRY-RUN] Создание inventory: {name} (pid={pid}, serial={serial})")
                stats["created"] += 1
                continue

            try:
                # Формируем данные согласно настройкам
                kwargs = {}
                if sync_cfg.sync_part_id and pid:
                    kwargs["part_id"] = pid
                if sync_cfg.sync_serial and serial:
                    kwargs["serial"] = serial
                if sync_cfg.sync_description and description:
                    kwargs["description"] = description
                if sync_cfg.sync_manufacturer and manufacturer:
                    kwargs["manufacturer"] = manufacturer

                self.client.create_inventory_item(
                    device_id=device.id,
                    name=name,
                    **kwargs,
                )
                stats["created"] += 1
            except Exception as e:
                logger.error(f"Ошибка создания inventory {name}: {e}")
                stats["failed"] += 1

        logger.info(
            f"Синхронизация inventory {device_name}: "
            f"создано={stats['created']}, обновлено={stats['updated']}, "
            f"пропущено={stats['skipped']}, ошибок={stats['failed']}"
        )
        return stats
