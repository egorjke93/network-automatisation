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
from typing import List, Dict, Any, Optional, Union

from .client import NetBoxClient
from ..core.context import RunContext, get_current_context
from ..core.models import Interface, IPAddressEntry, InventoryItem
from ..core.exceptions import (
    NetBoxError,
    NetBoxConnectionError,
    NetBoxAPIError,
    NetBoxValidationError,
    format_error_for_log,
)
from ..core.constants import (
    INTERFACE_FULL_MAP,
    DEFAULT_PREFIX_LENGTH,
    normalize_interface_full,
    normalize_device_model,
    normalize_mac_netbox,
    get_netbox_interface_type,
    slugify,
    mask_to_prefix,
    transliterate_to_slug,
)
from ..fields_config import get_sync_config

logger = logging.getLogger(__name__)


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
        context: Optional[RunContext] = None,
    ):
        """
        Инициализация синхронизатора.

        Args:
            client: NetBox клиент
            dry_run: Режим симуляции (ничего не меняет)
            create_only: Только создавать новые объекты
            update_only: Только обновлять существующие
            context: Контекст выполнения (если None — использует глобальный)
        """
        self.client = client
        self.ctx = context or get_current_context()
        self.dry_run = dry_run
        self.create_only = create_only
        self.update_only = update_only

        # Кэш для поиска устройств
        self._device_cache: Dict[str, Any] = {}
        self._mac_cache: Dict[str, Any] = {}

    def _log_prefix(self) -> str:
        """Возвращает префикс для логов с run_id."""
        if self.ctx:
            return f"[{self.ctx.run_id}] "
        return ""

    def sync_interfaces(
        self,
        device_name: str,
        interfaces: Union[List[Dict[str, Any]], List[Interface]],
        create_missing: Optional[bool] = None,
        update_existing: Optional[bool] = None,
    ) -> Dict[str, int]:
        """
        Синхронизирует интерфейсы устройства.

        Args:
            device_name: Имя устройства в NetBox
            interfaces: Список интерфейсов (Dict или Interface модели)
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

        # Конвертируем в Interface модели если нужно
        interface_models = Interface.ensure_list(interfaces)

        # Сортируем: сначала LAG интерфейсы (Po*), потом остальные
        def is_lag(intf: Interface) -> int:
            return 0 if intf.name.lower().startswith(("port-channel", "po")) else 1

        sorted_interfaces = sorted(interface_models, key=is_lag)

        for intf in sorted_interfaces:
            if not intf.name:
                continue

            # Проверяем фильтры исключения
            excluded = False
            for pattern in exclude_patterns:
                if re.match(pattern, intf.name, re.IGNORECASE):
                    logger.debug(f"Пропуск интерфейса {intf.name} (паттерн: {pattern})")
                    excluded = True
                    break
            if excluded:
                stats["skipped"] += 1
                continue

            if intf.name in existing:
                # Обновляем существующий
                if update_existing:
                    updated = self._update_interface(existing[intf.name], intf)
                    if updated:
                        stats["updated"] += 1
                    else:
                        stats["skipped"] += 1
                else:
                    stats["skipped"] += 1
            else:
                # Создаём новый
                if create_missing:
                    self._create_interface(device.id, intf)
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
        intf: Interface,
    ) -> None:
        """Создаёт интерфейс в NetBox."""
        sync_cfg = get_sync_config("interfaces")

        if self.dry_run:
            logger.info(f"[DRY-RUN] Создание интерфейса: {intf.name}")
            return

        # Формируем данные согласно настройкам
        kwargs = {}
        if sync_cfg.is_field_enabled("description"):
            kwargs["description"] = intf.description
        if sync_cfg.is_field_enabled("enabled"):
            kwargs["enabled"] = intf.status == "up"

        # MAC будет добавлен отдельно через assign_mac_to_interface (NetBox 4.x)
        mac_to_assign = None
        if sync_cfg.is_field_enabled("mac_address") and intf.mac:
            sync_mac_only_with_ip = sync_cfg.get_option("sync_mac_only_with_ip", False)
            if not (sync_mac_only_with_ip and not intf.ip_address):
                mac_to_assign = normalize_mac_netbox(intf.mac)

        if sync_cfg.is_field_enabled("mtu") and intf.mtu:
            kwargs["mtu"] = intf.mtu
        if sync_cfg.is_field_enabled("speed") and intf.speed:
            kwargs["speed"] = self._parse_speed(intf.speed)
        if sync_cfg.is_field_enabled("duplex") and intf.duplex:
            kwargs["duplex"] = self._parse_duplex(intf.duplex)

        # 802.1Q mode (access, tagged, tagged-all)
        if sync_cfg.is_field_enabled("mode") and intf.mode:
            kwargs["mode"] = intf.mode

        # Получаем LAG интерфейс если указан
        if intf.lag:
            lag_interface = self.client.get_interface_by_name(device_id, intf.lag)
            if lag_interface:
                kwargs["lag"] = lag_interface.id
                logger.debug(f"Привязка {intf.name} к LAG {intf.lag} (id={lag_interface.id})")
            else:
                logger.warning(f"LAG интерфейс {intf.lag} не найден для {intf.name}")

        interface = self.client.create_interface(
            device_id=device_id,
            name=intf.name,
            interface_type=get_netbox_interface_type(interface=intf),
            **kwargs,
        )

        # Привязываем MAC-адрес (NetBox 4.x - отдельная модель)
        if mac_to_assign and interface:
            self.client.assign_mac_to_interface(interface.id, mac_to_assign)

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

    def _update_interface(
        self,
        nb_interface,  # NetBox interface object
        intf: Interface,  # Our Interface model
    ) -> bool:
        """
        Обновляет интерфейс в NetBox.

        Args:
            nb_interface: Объект интерфейса из NetBox API
            intf: Наша модель Interface с новыми данными

        Returns:
            bool: True если были реальные изменения, False если нет
        """
        updates = {}
        sync_cfg = get_sync_config("interfaces")

        # Обновляем тип интерфейса если auto_detect_type включен
        if sync_cfg.get_option("auto_detect_type", True):
            new_type = get_netbox_interface_type(interface=intf)
            current_type = getattr(nb_interface.type, 'value', None) if nb_interface.type else None
            if new_type and new_type != current_type:
                updates["type"] = new_type

        # Проверяем что нужно обновить (согласно настройкам)
        if sync_cfg.is_field_enabled("description"):
            if intf.description != nb_interface.description:
                updates["description"] = intf.description

        if sync_cfg.is_field_enabled("enabled"):
            enabled = intf.status == "up"
            if enabled != nb_interface.enabled:
                updates["enabled"] = enabled

        # MAC обрабатывается отдельно через assign_mac_to_interface (NetBox 4.x)
        mac_to_assign = None
        if sync_cfg.is_field_enabled("mac_address") and intf.mac:
            sync_mac_only_with_ip = sync_cfg.get_option("sync_mac_only_with_ip", False)
            if not (sync_mac_only_with_ip and not intf.ip_address):
                new_mac = normalize_mac_netbox(intf.mac)
                current_mac = self.client.get_interface_mac(nb_interface.id) if not self.dry_run else None
                if new_mac and new_mac.upper() != (current_mac or "").upper():
                    mac_to_assign = new_mac

        if sync_cfg.is_field_enabled("mtu") and intf.mtu:
            if intf.mtu != (nb_interface.mtu or 0):
                updates["mtu"] = intf.mtu

        if sync_cfg.is_field_enabled("speed") and intf.speed:
            new_speed = self._parse_speed(intf.speed)
            if new_speed and new_speed != (nb_interface.speed or 0):
                updates["speed"] = new_speed

        if sync_cfg.is_field_enabled("duplex") and intf.duplex:
            new_duplex = self._parse_duplex(intf.duplex)
            current_duplex = getattr(nb_interface.duplex, 'value', None) if nb_interface.duplex else None
            if new_duplex and new_duplex != current_duplex:
                updates["duplex"] = new_duplex

        # 802.1Q mode
        if sync_cfg.is_field_enabled("mode") and intf.mode:
            current_mode = getattr(nb_interface.mode, 'value', None) if nb_interface.mode else None
            if intf.mode != current_mode:
                updates["mode"] = intf.mode

        # Обновляем LAG привязку
        if intf.lag:
            device_id = getattr(nb_interface.device, 'id', None) if nb_interface.device else None
            if device_id:
                lag_interface = self.client.get_interface_by_name(device_id, intf.lag)
                if lag_interface:
                    current_lag_id = getattr(nb_interface.lag, 'id', None) if nb_interface.lag else None
                    if lag_interface.id != current_lag_id:
                        updates["lag"] = lag_interface.id
                else:
                    logger.debug(f"LAG интерфейс {intf.lag} не найден в NetBox")

        if not updates and not mac_to_assign:
            logger.debug(f"  → нет изменений для интерфейса {nb_interface.name}")
            return False

        if self.dry_run:
            if updates:
                logger.info(f"[DRY-RUN] Обновление интерфейса {nb_interface.name}: {updates}")
            if mac_to_assign:
                logger.info(f"[DRY-RUN] Назначение MAC {mac_to_assign} на {nb_interface.name}")
            return True

        if updates:
            self.client.update_interface(nb_interface.id, **updates)

        # Привязываем MAC-адрес (NetBox 4.x - отдельная модель)
        if mac_to_assign:
            self.client.assign_mac_to_interface(nb_interface.id, mac_to_assign)

        return True

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

            # Проверяем что интерфейсы не LAG (NetBox не поддерживает кабели на LAG)
            local_intf_type = getattr(local_intf_obj.type, 'value', None) if local_intf_obj.type else None
            remote_intf_type = getattr(remote_intf_obj.type, 'value', None) if remote_intf_obj.type else None

            if local_intf_type == "lag":
                logger.debug(
                    f"Пропускаем LAG интерфейс: {local_device}:{local_intf} (кабели на LAG не поддерживаются)"
                )
                stats["skipped"] += 1
                continue
            if remote_intf_type == "lag":
                logger.debug(
                    f"Пропускаем LAG интерфейс соседа: {remote_device_obj.name}:{remote_port}"
                )
                stats["skipped"] += 1
                continue

            # Создаём кабель на физических интерфейсах
            result = self._create_cable(local_intf_obj, remote_intf_obj)

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

        Стратегия поиска зависит от neighbor_type, но всегда пробует
        несколько методов для надёжности:
        - hostname: Поиск по имени (основной)
        - mac: Поиск по MAC-адресу в dcim.mac_addresses
        - ip: Поиск по IP-адресу

        Args:
            entry: Данные LLDP/CDP
            neighbor_type: Тип идентификации (hostname, mac, ip, unknown)

        Returns:
            Device или None
        """
        hostname = entry.get("remote_hostname", "")
        mac = entry.get("remote_mac")
        ip = entry.get("remote_ip")

        # Приоритет поиска зависит от neighbor_type
        if neighbor_type == "hostname":
            # Убираем domain если есть (switch-01.domain.local → switch-01)
            clean_hostname = hostname.split(".")[0] if "." in hostname else hostname
            device = self._find_device(clean_hostname)
            if device:
                return device

            # Fallback: пробуем по IP если есть
            if ip:
                device = self.client.get_device_by_ip(ip)
                if device:
                    logger.debug(f"Устройство {hostname} найдено по IP {ip}")
                    return device

            # Fallback: пробуем по MAC если есть
            if mac:
                device = self._find_device_by_mac(mac)
                if device:
                    logger.debug(f"Устройство {hostname} найдено по MAC {mac}")
                    return device

        elif neighbor_type == "mac":
            # Основной поиск по MAC
            if mac:
                device = self._find_device_by_mac(mac)
                if device:
                    return device

            # Fallback: пробуем по IP если есть
            if ip:
                device = self.client.get_device_by_ip(ip)
                if device:
                    logger.debug(f"Устройство (MAC {mac}) найдено по IP {ip}")
                    return device

        elif neighbor_type == "ip":
            # Основной поиск по IP
            if ip:
                device = self.client.get_device_by_ip(ip)
                if device:
                    return device

            # Fallback: пробуем по MAC если есть
            if mac:
                device = self._find_device_by_mac(mac)
                if device:
                    logger.debug(f"Устройство (IP {ip}) найдено по MAC {mac}")
                    return device

        else:
            # unknown - пробуем все методы
            if ip:
                device = self.client.get_device_by_ip(ip)
                if device:
                    return device
            if mac:
                device = self._find_device_by_mac(mac)
                if device:
                    return device

        return None

    def _find_device_by_mac(self, mac: str) -> Optional[Any]:
        """
        Ищет устройство по MAC-адресу.

        Использует таблицу dcim.mac_addresses (NetBox 4.x) и fallback
        на поиск по MAC в интерфейсах.

        Args:
            mac: MAC-адрес в любом формате

        Returns:
            Device или None
        """
        if not mac:
            return None

        # Нормализуем MAC для кэша
        mac_normalized = mac.replace(":", "").replace("-", "").replace(".", "").lower()

        # Проверяем кэш
        if mac_normalized in self._mac_cache:
            return self._mac_cache[mac_normalized]

        # Используем метод клиента для поиска
        device = self.client.get_device_by_mac(mac)
        if device:
            self._mac_cache[mac_normalized] = device
            return device

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
        except NetBoxError as e:
            logger.error(f"Ошибка NetBox при создании кабеля: {format_error_for_log(e)}")
            return "error"
        except Exception as e:
            logger.error(f"Неизвестная ошибка создания кабеля: {e}")
            return "error"

    # ==================== IP-АДРЕСА ====================

    def sync_ip_addresses(
        self,
        device_name: str,
        ip_data: Union[List[Dict[str, Any]], List[IPAddressEntry]],
        device_ip: Optional[str] = None,
        update_existing: bool = False,
    ) -> Dict[str, int]:
        """
        Синхронизирует IP-адреса устройства с NetBox.

        Args:
            device_name: Имя устройства в NetBox
            ip_data: Список IP-адресов (Dict или IPAddressEntry модели)
            device_ip: IP-адрес подключения (будет установлен как primary_ip4)
            update_existing: Обновлять существующие IP (tenant, description)

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

        # Конвертируем в модели если нужно
        entries = IPAddressEntry.ensure_list(ip_data)

        for entry in entries:
            interface_name = entry.interface
            ip_address = entry.ip_address

            if not interface_name or not ip_address:
                continue

            # Нормализуем IP (убираем маску если есть)
            ip_only = ip_address.split("/")[0]

            # Используем with_prefix для получения IP с маской
            ip_with_mask = entry.with_prefix

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
                if update_existing:
                    # Обновляем существующий IP
                    existing_ip = existing_ips[ip_only]
                    updated = self._update_ip_address(existing_ip, device, intf)
                    if updated:
                        stats["updated"] += 1
                    else:
                        stats["skipped"] += 1
                else:
                    stats["skipped"] += 1
                continue

            # Создаём IP-адрес
            if self.dry_run:
                logger.info(f"[DRY-RUN] Создание IP: {ip_with_mask} на {interface_name}")
                stats["created"] += 1
                continue

            try:
                # Собираем дополнительные параметры
                extra_params = {}

                # Tenant от устройства
                if hasattr(device, 'tenant') and device.tenant:
                    extra_params['tenant'] = device.tenant.id

                # Description от интерфейса
                if hasattr(intf, 'description') and intf.description:
                    extra_params['description'] = intf.description

                self.client.create_ip_address(
                    address=ip_with_mask,
                    interface_id=intf.id,
                    status="active",
                    **extra_params,
                )
                logger.info(f"Создан IP: {ip_with_mask} на {device_name}:{interface_name}")
                stats["created"] += 1
            except NetBoxValidationError as e:
                logger.error(f"Ошибка валидации IP {ip_with_mask}: {format_error_for_log(e)}")
                stats["failed"] += 1
            except NetBoxError as e:
                logger.error(f"Ошибка NetBox создания IP {ip_with_mask}: {format_error_for_log(e)}")
                stats["failed"] += 1
            except Exception as e:
                logger.error(f"Неизвестная ошибка создания IP {ip_with_mask}: {e}")
                stats["failed"] += 1

        # Устанавливаем primary_ip4 если указан device_ip
        if device_ip and not self.dry_run:
            self._set_primary_ip(device, device_ip)

        logger.info(
            f"Синхронизация IP {device_name}: создано={stats['created']}, "
            f"пропущено={stats['skipped']}, ошибок={stats['failed']}"
        )
        return stats

    def _update_ip_address(self, ip_obj, device, interface) -> bool:
        """
        Обновляет существующий IP-адрес (tenant, description, interface).

        Args:
            ip_obj: Объект IP-адреса из NetBox
            device: Устройство NetBox
            interface: Интерфейс NetBox

        Returns:
            bool: True если были изменения
        """
        updates = {}

        # Обновляем tenant от устройства
        if hasattr(device, 'tenant') and device.tenant:
            current_tenant = getattr(ip_obj, 'tenant', None)
            current_tenant_id = current_tenant.id if current_tenant else None
            if current_tenant_id != device.tenant.id:
                updates['tenant'] = device.tenant.id

        # Обновляем description от интерфейса
        if hasattr(interface, 'description') and interface.description:
            current_desc = getattr(ip_obj, 'description', '') or ''
            if current_desc != interface.description:
                updates['description'] = interface.description

        # Обновляем привязку к интерфейсу
        if hasattr(interface, 'id'):
            current_intf = getattr(ip_obj, 'assigned_object_id', None)
            if current_intf != interface.id:
                updates['assigned_object_type'] = 'dcim.interface'
                updates['assigned_object_id'] = interface.id

        if not updates:
            return False

        if self.dry_run:
            logger.info(f"[DRY-RUN] Обновление IP {ip_obj.address}: {updates}")
            return True

        try:
            ip_obj.update(updates)
            logger.info(f"Обновлён IP {ip_obj.address}: {list(updates.keys())}")
            return True
        except NetBoxError as e:
            logger.error(f"Ошибка NetBox обновления IP {ip_obj.address}: {format_error_for_log(e)}")
            return False
        except Exception as e:
            logger.error(f"Неизвестная ошибка обновления IP {ip_obj.address}: {e}")
            return False

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
            tenant: Арендатор (None = из config)

        Note:
            Primary IP НЕ устанавливается при создании устройства.
            Используйте sync_ip_addresses() для установки primary IP после
            синхронизации IP адресов.

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
            # ПРИМЕЧАНИЕ: Primary IP НЕ устанавливается здесь
            # Он будет установлен позже при синхронизации IP адресов (sync_ip_addresses)
            return device

        except NetBoxValidationError as e:
            logger.error(f"Ошибка валидации устройства {name}: {format_error_for_log(e)}")
            return None
        except NetBoxError as e:
            logger.error(f"Ошибка NetBox создания устройства {name}: {format_error_for_log(e)}")
            return None
        except Exception as e:
            logger.error(f"Неизвестная ошибка создания устройства {name}: {e}")
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
                        primary_ip=ip_address,
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
                tenant=tenant,
            )
            # Primary IP будет установлен позже при sync_ip_addresses()

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
        primary_ip: str = "",
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
            primary_ip: Primary IP адрес

        Returns:
            bool: True если были изменения
        """
        updates = {}

        # Нормализуем входные данные (убираем лишние пробелы)
        serial = (serial or "").strip()
        model = (model or "").strip()
        platform = (platform or "").strip()
        tenant = (tenant or "").strip() if tenant else None
        site = (site or "").strip() if site else None
        role = (role or "").strip() if role else None
        primary_ip = (primary_ip or "").strip()

        # Получаем текущие значения из устройства
        current_serial = (device.serial or "").strip()
        current_model = (device.device_type.model if device.device_type else "").strip()
        current_platform = (device.platform.name if device.platform else "").strip()
        current_tenant = (device.tenant.name if device.tenant else "").strip()
        current_site = (device.site.name if device.site else "").strip()
        current_role = (device.role.name if device.role else "").strip()

        # Debug логирование для сравнения значений
        logger.debug(
            f"Сравнение устройства {device.name}: "
            f"serial=[{serial!r}] vs [{current_serial!r}], "
            f"model=[{model!r}→{normalize_device_model(model)!r}] vs [{current_model!r}], "
            f"platform=[{platform!r}] vs [{current_platform!r}], "
            f"site=[{site!r}] vs [{current_site!r}], "
            f"role=[{role!r}] vs [{current_role!r}]"
        )

        # Проверяем серийный номер
        if serial and serial != current_serial:
            updates["serial"] = serial
            logger.debug(f"  → serial изменится: {current_serial!r} → {serial!r}")

        # Проверяем device_type (модель)
        if model and model != "Unknown":
            normalized_model = normalize_device_model(model)
            # Сравниваем нормализованные значения
            if normalized_model != current_model:
                # Получаем или создаём тип устройства
                mfr = self._get_or_create_manufacturer(manufacturer or "Cisco")
                if mfr:
                    dtype = self._get_or_create_device_type(model, mfr.id)
                    if dtype:
                        updates["device_type"] = dtype.id
                        logger.debug(f"  → model изменится: {current_model!r} → {normalized_model!r}")

        # Проверяем платформу
        if platform and platform != current_platform:
            platform_obj = self._get_or_create_platform(platform)
            if platform_obj:
                updates["platform"] = platform_obj.id
                logger.debug(f"  → platform изменится: {current_platform!r} → {platform!r}")

        # Проверяем tenant
        if tenant and tenant != current_tenant:
            tenant_obj = self._get_or_create_tenant(tenant)
            if tenant_obj:
                updates["tenant"] = tenant_obj.id
                logger.debug(f"  → tenant изменится: {current_tenant!r} → {tenant!r}")

        # Проверяем site
        if site and site != current_site:
            site_obj = self._get_or_create_site(site)
            if site_obj:
                updates["site"] = site_obj.id
                logger.debug(f"  → site изменится: {current_site!r} → {site!r}")

        # Проверяем role
        if role and role != current_role:
            role_obj = self._get_or_create_role(role)
            if role_obj:
                updates["role"] = role_obj.id
                logger.debug(f"  → role изменится: {current_role!r} → {role!r}")

        # Проверяем primary_ip (обрабатывается отдельно через _set_primary_ip)
        need_primary_ip = False
        if primary_ip:
            primary_ip_only = primary_ip.split("/")[0]
            current_primary = ""
            if device.primary_ip4:
                current_primary = str(device.primary_ip4.address).split("/")[0]
            if primary_ip_only != current_primary:
                need_primary_ip = True
                logger.debug(f"  → primary_ip изменится: {current_primary!r} → {primary_ip_only!r}")

        if not updates and not need_primary_ip:
            logger.debug(f"  → нет изменений для {device.name}")
            return False

        if self.dry_run:
            if updates:
                logger.info(f"[DRY-RUN] Обновление устройства {device.name}: {updates}")
            if need_primary_ip:
                logger.info(f"[DRY-RUN] Установка primary IP {primary_ip} для {device.name}")
            return True

        try:
            if updates:
                device.update(updates)
                logger.info(f"Обновлено устройство: {device.name}")

            # Устанавливаем primary IP (отдельная операция)
            if need_primary_ip:
                self._set_primary_ip(device, primary_ip)

            return True
        except NetBoxError as e:
            logger.error(f"Ошибка NetBox обновления устройства {device.name}: {format_error_for_log(e)}")
            return False
        except Exception as e:
            logger.error(f"Неизвестная ошибка обновления устройства {device.name}: {e}")
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
        except NetBoxConnectionError as e:
            logger.error(f"Ошибка подключения к NetBox: {format_error_for_log(e)}")
            return 0
        except NetBoxError as e:
            logger.error(f"Ошибка NetBox получения устройств: {format_error_for_log(e)}")
            return 0
        except Exception as e:
            logger.error(f"Неизвестная ошибка получения устройств: {e}")
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
                    except NetBoxError as e:
                        logger.error(f"Ошибка NetBox удаления устройства {device.name}: {format_error_for_log(e)}")
                    except Exception as e:
                        logger.error(f"Неизвестная ошибка удаления устройства {device.name}: {e}")

        return deleted

    # ==================== ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ====================

    def _get_or_create(
        self,
        endpoint,
        name: str,
        extra_data: Optional[Dict[str, Any]] = None,
        get_field: str = "name",
        use_transliterate: bool = False,
        log_level: str = "error",
    ) -> Optional[Any]:
        """
        Generic get-or-create для NetBox объектов.

        Args:
            endpoint: NetBox API endpoint (e.g., self.client.api.dcim.sites)
            name: Значение для поиска/создания
            extra_data: Дополнительные поля для создания (status, color, etc.)
            get_field: Поле для поиска (по умолчанию "name")
            use_transliterate: Использовать транслитерацию для slug (для кириллицы)
            log_level: Уровень логирования ошибок ("error" или "debug")

        Returns:
            Найденный или созданный объект, либо None при ошибке
        """
        try:
            # Ищем существующий
            obj = endpoint.get(**{get_field: name})
            if obj:
                return obj

            # Создаём новый
            slug = transliterate_to_slug(name) if use_transliterate else slugify(name)
            create_data = {get_field: name, "slug": slug}
            if extra_data:
                create_data.update(extra_data)

            return endpoint.create(create_data)

        except NetBoxError as e:
            log_fn = logger.debug if log_level == "debug" else logger.error
            log_fn(f"Ошибка NetBox ({get_field}={name}): {format_error_for_log(e)}")
            return None
        except Exception as e:
            log_fn = logger.debug if log_level == "debug" else logger.error
            log_fn(f"Неизвестная ошибка ({get_field}={name}): {e}")
            return None

    def _get_or_create_manufacturer(self, name: str) -> Optional[Any]:
        """Получает или создаёт производителя."""
        return self._get_or_create(self.client.api.dcim.manufacturers, name)

    def _get_or_create_device_type(
        self,
        model: str,
        manufacturer_id: int,
    ) -> Optional[Any]:
        """Получает или создаёт тип устройства."""
        normalized = normalize_device_model(model)
        return self._get_or_create(
            self.client.api.dcim.device_types,
            normalized,
            extra_data={"manufacturer": manufacturer_id},
            get_field="model",
        )

    def _get_or_create_site(self, name: str) -> Optional[Any]:
        """Получает или создаёт сайт."""
        return self._get_or_create(
            self.client.api.dcim.sites,
            name,
            extra_data={"status": "active"},
        )

    def _get_or_create_role(self, name: str) -> Optional[Any]:
        """Получает или создаёт роль устройства."""
        return self._get_or_create(
            self.client.api.dcim.device_roles,
            name,
            extra_data={"color": "9e9e9e"},
        )

    def _get_or_create_platform(self, name: str) -> Optional[Any]:
        """Получает или создаёт платформу."""
        return self._get_or_create(
            self.client.api.dcim.platforms,
            name,
            log_level="debug",
        )

    def _get_or_create_tenant(self, name: str) -> Optional[Any]:
        """Получает или создаёт арендатора (tenant)."""
        return self._get_or_create(
            self.client.api.tenancy.tenants,
            name,
            use_transliterate=True,
        )

    def _set_primary_ip(self, device, ip_address: str) -> None:
        """
        Устанавливает primary IP для устройства.

        Если IP не существует в NetBox, создаёт его и привязывает
        к management интерфейсу устройства (если есть) или без интерфейса.
        """
        if not ip_address:
            return

        # Нормализуем IP - убираем маску если есть
        ip_only = ip_address.split("/")[0]

        # Проверяем: уже установлен?
        if device.primary_ip4:
            current_ip = str(device.primary_ip4.address).split("/")[0]
            if current_ip == ip_only:
                logger.debug(f"Primary IP уже установлен: {ip_only}")
                return

        # Добавляем маску если её нет (по умолчанию /32 для management IP)
        if "/" in ip_address:
            ip_with_mask = ip_address
        else:
            ip_with_mask = f"{ip_only}/32"

        try:
            # Ищем IP в NetBox (без маски - get() может принять любой формат)
            ip_obj = self.client.api.ipam.ip_addresses.get(address=ip_only)

            if not ip_obj:
                # IP не найден - создаём его
                if self.dry_run:
                    logger.info(f"[DRY-RUN] Создание IP {ip_with_mask} для {device.name}")
                else:
                    # Ищем management интерфейс для привязки IP
                    mgmt_interface = self._find_management_interface(device.id, ip_only)

                    ip_data = {"address": ip_with_mask}

                    if mgmt_interface:
                        # Привязываем к management интерфейсу
                        ip_data["assigned_object_type"] = "dcim.interface"
                        ip_data["assigned_object_id"] = mgmt_interface.id
                        logger.debug(f"Привязка IP {ip_with_mask} к интерфейсу {mgmt_interface.name}")
                    else:
                        logger.debug(f"Management интерфейс не найден, IP {ip_with_mask} без привязки")

                    ip_obj = self.client.api.ipam.ip_addresses.create(ip_data)
                    logger.info(f"Создан IP {ip_with_mask} для устройства {device.name}")

            if ip_obj and not self.dry_run:
                # Устанавливаем как primary
                device.primary_ip4 = ip_obj.id
                device.save()
                logger.info(f"Установлен primary IP {ip_only} для {device.name}")
            elif self.dry_run:
                logger.info(f"[DRY-RUN] Установка primary IP {ip_only} для {device.name}")

        except NetBoxError as e:
            logger.warning(f"Ошибка NetBox установки primary IP {ip_address} для {device.name}: {format_error_for_log(e)}")
        except Exception as e:
            logger.warning(f"Неизвестная ошибка установки primary IP {ip_address} для {device.name}: {e}")

    def _find_management_interface(self, device_id: int, target_ip: str = "") -> Optional[Any]:
        """
        Ищет management интерфейс устройства для привязки IP.

        Приоритет поиска:
        1. Интерфейс с указанным IP (если передан target_ip)
        2. Management1, Management0, Mgmt0
        3. Loopback0
        4. SVI интерфейсы (Vlan*, но не Vlan1)

        Args:
            device_id: ID устройства в NetBox
            target_ip: IP адрес для поиска (опционально)
        """
        interfaces = self.client.get_interfaces(device_id=device_id)
        interfaces_by_name = {intf.name.lower(): intf for intf in interfaces}

        # 1. Ищем интерфейс с указанным IP
        if target_ip:
            ip_only = target_ip.split("/")[0]
            for intf in interfaces:
                # Проверяем есть ли уже IP на интерфейсе
                intf_ips = self.client.get_ip_addresses(interface_id=intf.id)
                for ip in intf_ips:
                    if str(ip.address).split("/")[0] == ip_only:
                        return intf

        # 2. Стандартные management интерфейсы
        mgmt_names = [
            "Management1", "Management0", "Mgmt0", "mgmt0",
        ]

        for name in mgmt_names:
            if name.lower() in interfaces_by_name:
                return interfaces_by_name[name.lower()]

        # 3. SVI интерфейсы (Vlan*, но не Vlan1 - это по умолчанию везде)
        for intf in interfaces:
            name_lower = intf.name.lower()
            if name_lower.startswith("vlan") and name_lower != "vlan1":
                return intf

        return None

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
            except NetBoxValidationError as e:
                logger.error(f"Ошибка валидации VLAN {vid}: {format_error_for_log(e)}")
                stats["failed"] += 1
            except NetBoxError as e:
                logger.error(f"Ошибка NetBox создания VLAN {vid}: {format_error_for_log(e)}")
                stats["failed"] += 1
            except Exception as e:
                logger.error(f"Неизвестная ошибка создания VLAN {vid}: {e}")
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
        inventory_data: Union[List[Dict[str, Any]], List[InventoryItem]],
    ) -> Dict[str, int]:
        """
        Синхронизирует inventory items (модули, SFP, PSU) в NetBox.

        Args:
            device_name: Имя устройства в NetBox
            inventory_data: Данные (Dict или InventoryItem модели)

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

        # Конвертируем в модели если нужно
        items = InventoryItem.ensure_list(inventory_data)

        logger.info(f"Синхронизация inventory для {device_name}: {len(items)} компонентов")

        sync_cfg = get_sync_config("inventory")

        for item in items:
            name = item.name.strip() if item.name else ""
            pid = item.pid.strip() if item.pid else ""
            serial = item.serial.strip() if item.serial else ""
            description = item.description.strip() if item.description else ""
            manufacturer = item.manufacturer.strip() if item.manufacturer else ""

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

                if sync_cfg.is_field_enabled("part_id") and pid and existing.part_id != pid:
                    updates["part_id"] = pid
                    needs_update = True
                if sync_cfg.is_field_enabled("serial") and serial and existing.serial != serial:
                    updates["serial"] = serial
                    needs_update = True
                if sync_cfg.is_field_enabled("description") and description and existing.description != description:
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
                        except NetBoxError as e:
                            logger.error(f"Ошибка NetBox обновления {name}: {format_error_for_log(e)}")
                            stats["failed"] += 1
                        except Exception as e:
                            logger.error(f"Неизвестная ошибка обновления {name}: {e}")
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
                if sync_cfg.is_field_enabled("part_id") and pid:
                    kwargs["part_id"] = pid
                if sync_cfg.is_field_enabled("serial") and serial:
                    kwargs["serial"] = serial
                if sync_cfg.is_field_enabled("description") and description:
                    kwargs["description"] = description
                if sync_cfg.is_field_enabled("manufacturer") and manufacturer:
                    kwargs["manufacturer"] = manufacturer

                self.client.create_inventory_item(
                    device_id=device.id,
                    name=name,
                    **kwargs,
                )
                stats["created"] += 1
            except NetBoxValidationError as e:
                logger.error(f"Ошибка валидации inventory {name}: {format_error_for_log(e)}")
                stats["failed"] += 1
            except NetBoxError as e:
                logger.error(f"Ошибка NetBox создания inventory {name}: {format_error_for_log(e)}")
                stats["failed"] += 1
            except Exception as e:
                logger.error(f"Неизвестная ошибка создания inventory {name}: {e}")
                stats["failed"] += 1

        logger.info(
            f"Синхронизация inventory {device_name}: "
            f"создано={stats['created']}, обновлено={stats['updated']}, "
            f"пропущено={stats['skipped']}, ошибок={stats['failed']}"
        )
        return stats
