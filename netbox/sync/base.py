"""
Базовые классы и утилиты для синхронизации с NetBox.

Содержит:
- Импорты общих зависимостей
- Базовый класс SyncBase с общими методами
- Вспомогательные функции
"""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple, Callable

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


class SyncStats:
    """
    Инициализация stats/details для sync-операций.

    Убирает дублирование dict-литералов в каждом sync-методе.
    Результат — обычные dict, совместимые с существующим кодом.

    Example:
        s = SyncStats("created", "updated", "deleted", "skipped", "failed")
        stats, details = s.stats, s.details
        # stats = {"created": 0, "updated": 0, ...}
        # details = {"create": [], "update": [], "delete": [], "skip": []}
    """

    # Маппинг ключей stats → ключей details (created→create, etc.)
    _DETAIL_KEY_MAP = {
        "created": "create",
        "updated": "update",
        "deleted": "delete",
        "skipped": "skip",
    }

    def __init__(self, *operations: str):
        """
        Args:
            *operations: Ключи для stats (created, updated, deleted, skipped, failed)
        """
        self.stats: Dict[str, int] = {op: 0 for op in operations}
        self.details: Dict[str, list] = {}
        for op in operations:
            detail_key = self._DETAIL_KEY_MAP.get(op)
            if detail_key:
                self.details[detail_key] = []

    def result(self) -> Dict[str, Any]:
        """Возвращает stats с вложенным details."""
        result = dict(self.stats)
        if self.details:
            result["details"] = dict(self.details)
        return result


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
        # Обратный кэш VLAN: NetBox ID -> VID (для избежания lazy-load pynetbox)
        self._vlan_id_to_vid: Dict[int, int] = {}
        # Кэш интерфейсов: device_id -> {name: interface_obj}
        self._interface_cache: Dict[int, Dict[str, Any]] = {}

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
        Находит интерфейс устройства (с кэшированием).

        Загружает интерфейсы один раз на device_id, повторные вызовы берут из кэша.

        Args:
            device_id: ID устройства
            interface_name: Имя интерфейса

        Returns:
            Interface или None
        """
        # Загружаем интерфейсы в кэш (1 раз на device_id)
        if device_id not in self._interface_cache:
            interfaces = self.client.get_interfaces(device_id=device_id)
            self._interface_cache[device_id] = {intf.name: intf for intf in interfaces}

        cache = self._interface_cache[device_id]

        # Точное совпадение
        if interface_name in cache:
            return cache[interface_name]

        # Попробуем нормализованное имя (Gi0/1 vs GigabitEthernet0/1)
        normalized = self._normalize_interface_name(interface_name)
        for name, intf in cache.items():
            if self._normalize_interface_name(name) == normalized:
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
                # Обратный кэш: ID → VID (для _check_untagged_vlan без lazy-load)
                self._vlan_id_to_vid[vlan.id] = vlan.vid
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

    # ==================== ОБРАБОТКА ОШИБОК ====================

    def _safe_netbox_call(
        self,
        operation: str,
        fn: Callable,
        *args,
        default: Any = None,
        log_level: str = "error",
        **kwargs,
    ) -> Any:
        """
        Выполняет NetBox API вызов с обработкой ошибок.

        Заменяет повторяющийся паттерн try/except в sync-методах.

        Args:
            operation: Описание операции (для лога)
            fn: Функция для вызова
            *args: Аргументы функции
            default: Значение по умолчанию при ошибке
            log_level: Уровень логирования (error/warning)
            **kwargs: Именованные аргументы функции

        Returns:
            Результат fn() или default при ошибке

        Example:
            result = self._safe_netbox_call(
                "обновление устройства",
                device.update, updates,
                default=False,
            )
        """
        log_fn = getattr(logger, log_level)
        try:
            return fn(*args, **kwargs)
        except (NetBoxError, NetBoxValidationError, NetBoxConnectionError) as e:
            log_fn(f"{self._log_prefix()}Ошибка {operation}: {format_error_for_log(e)}")
            return default
        except Exception as e:
            log_fn(f"{self._log_prefix()}Неизвестная ошибка {operation}: {e}")
            return default

    # ==================== BATCH С FALLBACK ====================

    def _batch_with_fallback(
        self,
        batch_data: list,
        item_names: List[str],
        bulk_fn: Callable,
        fallback_fn: Callable,
        stats: dict,
        details: dict,
        operation: str,
        entity_name: str,
        detail_key: str = "name",
    ) -> Optional[list]:
        """
        Batch операция с автоматическим fallback на поштучную обработку.

        При ошибке batch вызывает fallback_fn для каждого элемента отдельно.

        Args:
            batch_data: Данные для batch (list of dicts или list of ids)
            item_names: Имена для логов (параллельный список)
            bulk_fn: Batch функция — вызывается один раз на весь список
            fallback_fn: Поштучная функция (data, name) -> None, может бросить Exception
            stats: Статистика (modified in-place)
            details: Детали (modified in-place)
            operation: Ключ для stats/details ("created"/"deleted"/"updated")
            entity_name: Название сущности для логов ("интерфейс"/"inventory"/"IP")
            detail_key: Ключ для details dict ("name" или "address")

        Returns:
            Результат bulk_fn при успехе, None при fallback
        """
        if not batch_data:
            return None

        # Определяем ключ для details (created -> create, deleted -> delete, updated -> update)
        detail_section = operation.rstrip("d").rstrip("e") + "e"  # created->create, deleted->delete

        try:
            result = bulk_fn(batch_data)
            for name in item_names:
                logger.info(f"{self._log_prefix()}{'Создан' if operation == 'created' else 'Удалён' if operation == 'deleted' else 'Обновлён'} {entity_name}: {name}")
                stats[operation] = stats.get(operation, 0) + 1
                details[detail_section].append({detail_key: name})
            return result
        except Exception as e:
            logger.warning(
                f"{self._log_prefix()}Batch {operation} {entity_name} не удался ({e}), "
                f"fallback на поштучную обработку"
            )
            for data, name in zip(batch_data, item_names):
                try:
                    fallback_fn(data, name)
                    logger.info(f"{self._log_prefix()}{'Создан' if operation == 'created' else 'Удалён' if operation == 'deleted' else 'Обновлён'} {entity_name}: {name}")
                    stats[operation] = stats.get(operation, 0) + 1
                    details[detail_section].append({detail_key: name})
                except Exception as exc:
                    logger.error(f"{self._log_prefix()}Ошибка {operation} {entity_name} {name}: {exc}")
                    stats["failed"] = stats.get("failed", 0) + 1
            return None

    # ==================== ПАРСИНГ ====================
    # Парсинг VLAN перенесён в core/domain/vlan.py (parse_vlan_range)

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
