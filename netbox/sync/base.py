"""
Базовые классы и утилиты для синхронизации с NetBox.

Содержит:
- Импорты общих зависимостей
- Базовый класс SyncBase с общими методами
- Вспомогательные функции
"""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple

from ..client import NetBoxClient
from ...core.context import RunContext, get_current_context
from ...core.models import Interface, IPAddressEntry, InventoryItem, LLDPNeighbor, DeviceInfo
from ...core.domain.sync import SyncComparator, SyncDiff, ChangeType, get_cable_endpoints
from ...core.exceptions import (
    NetBoxError,
    NetBoxConnectionError,
    NetBoxAPIError,
    NetBoxValidationError,
    format_error_for_log,
)
from ...core.constants import (
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
from ...fields_config import get_sync_config

logger = logging.getLogger(__name__)


class SyncBase:
    """
    Базовый класс для синхронизации с NetBox.

    Содержит общие атрибуты и вспомогательные методы,
    используемые во всех sync-операциях.
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
        # Кэш VLAN: (vid, site) -> VLAN object
        self._vlan_cache: Dict[Tuple[int, str], Any] = {}

    def _log_prefix(self) -> str:
        """Возвращает префикс для логов с run_id."""
        if self.ctx:
            return f"[{self.ctx.run_id}] "
        return ""

    # ==================== ПОИСК И КЭШИРОВАНИЕ ====================

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
        name = normalize_interface_full(name.strip())
        return name.lower()

    def _find_device_by_mac(self, mac: str) -> Optional[Any]:
        """
        Ищет устройство по MAC-адресу.

        Args:
            mac: MAC-адрес в любом формате

        Returns:
            Device или None
        """
        if not mac:
            return None

        mac_normalized = mac.replace(":", "").replace("-", "").replace(".", "").lower()

        if mac_normalized in self._mac_cache:
            return self._mac_cache[mac_normalized]

        device = self.client.get_device_by_mac(mac)
        if device:
            self._mac_cache[mac_normalized] = device
            return device

        return None

    def _get_vlan_by_vid(self, vid: int, site: Optional[str] = None) -> Optional[Any]:
        """
        Находит VLAN по VID с кэшированием.

        Args:
            vid: Номер VLAN (1-4094)
            site: Имя сайта (ищем VLAN только в этом сайте)

        Returns:
            VLAN или None
        """
        cache_key = (vid, site or "")
        if cache_key in self._vlan_cache:
            return self._vlan_cache[cache_key]

        # Загружаем все VLAN сайта одним запросом (если ещё не загружены)
        site_cache_key = f"_site_loaded_{site or ''}"
        if site_cache_key not in self._vlan_cache:
            self._load_site_vlans(site)
            self._vlan_cache[site_cache_key] = True

        # Теперь ищем в кэше
        if cache_key in self._vlan_cache:
            return self._vlan_cache[cache_key]

        return None

    def _load_site_vlans(self, site: Optional[str] = None) -> None:
        """Загружает все VLAN сайта в кэш одним запросом."""
        try:
            vlans = list(self.client.get_vlans(site=site))
            count = 0
            for vlan in vlans:
                cache_key = (vlan.vid, site or "")
                self._vlan_cache[cache_key] = vlan
                count += 1
            logger.debug(f"Загружено {count} VLANs для сайта '{site}'")
        except Exception as e:
            logger.warning(f"Ошибка загрузки VLANs для сайта '{site}': {e}")

    # ==================== GET OR CREATE ====================

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
            endpoint: NetBox API endpoint
            name: Значение для поиска/создания
            extra_data: Дополнительные поля для создания
            get_field: Поле для поиска (по умолчанию "name")
            use_transliterate: Использовать транслитерацию для slug
            log_level: Уровень логирования ошибок

        Returns:
            Найденный или созданный объект, либо None
        """
        try:
            obj = endpoint.get(**{get_field: name})
            if obj:
                return obj

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

    # ==================== ПАРСИНГ ====================

    def _parse_vlan_range(self, vlan_str: str) -> List[int]:
        """
        Парсит строку с диапазонами VLAN в список VID.

        Args:
            vlan_str: Строка типа "10,20,30-50,100" или "1-4094"

        Returns:
            List[int]: Список VID, например [10, 20, 30, 31, ..., 50, 100]
                       Пустой список если строка пустая или "all"
        """
        if not vlan_str:
            return []

        vlan_str = vlan_str.strip().lower()

        # Пропускаем "all" и полные диапазоны (tagged-all)
        if vlan_str in ("all", "1-4094", "1-4093", "1-4095", "none"):
            return []

        result = []
        try:
            # Разбиваем по запятым: "10,20,30-50" → ["10", "20", "30-50"]
            for part in vlan_str.split(","):
                part = part.strip()
                if not part:
                    continue

                if "-" in part:
                    # Диапазон: "30-50" → [30, 31, ..., 50]
                    start_end = part.split("-", 1)
                    if len(start_end) == 2:
                        start = int(start_end[0].strip())
                        end = int(start_end[1].strip())
                        result.extend(range(start, end + 1))
                else:
                    # Одиночный VLAN: "10" → [10]
                    result.append(int(part))
        except ValueError as e:
            logger.debug(f"Ошибка парсинга VLAN: {vlan_str} - {e}")
            return []

        # Убираем дубликаты и сортируем
        return sorted(set(result))

    def _parse_speed(self, speed_str: str) -> Optional[int]:
        """Парсит скорость в kbps для NetBox."""
        if not speed_str:
            return None
        speed_str = speed_str.lower()
        try:
            if "kbit" in speed_str:
                return int(speed_str.split()[0])
            if "gbit" in speed_str:
                return int(float(speed_str.split()[0]) * 1000000)
            if "mbit" in speed_str:
                return int(float(speed_str.split()[0]) * 1000)
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
