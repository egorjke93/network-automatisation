# 11. Sync Deep Dive -- полный разбор синхронизации с NetBox

> **Предварительное чтение:** [05_SYNC_NETBOX.md](05_SYNC_NETBOX.md) (обзор), [09_MIXINS_PATTERNS.md](09_MIXINS_PATTERNS.md) (паттерн mixin)
>
> В этом документе мы разберём **каждую функцию** sync-пайплайна, читая реальный код проекта.
> Цель -- после прочтения вы сможете объяснить, что происходит на каждом этапе от CLI-команды до API-вызова в NetBox.

---

## Содержание

1. [Обзор -- архитектура sync](#1-обзор----архитектура-sync)
2. [SyncBase -- фундамент](#2-syncbase----фундамент)
3. [SyncComparator -- сравнение данных](#3-synccomparator----сравнение-данных)
4. [InterfacesSyncMixin -- полный трейс](#4-interfacessyncmixin----полный-трейс)
5. [CablesSyncMixin](#5-cablessyncmixin)
6. [DevicesSyncMixin](#6-devicessyncmixin)
7. [IPAddressesSyncMixin](#7-ipaddressessyncmixin)
8. [VLANsSyncMixin](#8-vlanssyncmixin)
9. [InventorySyncMixin](#9-inventorysyncmixin)
10. [NetBoxClient -- API-обертка](#10-netboxclient----api-обертка)
11. [Итог -- полная цепочка sync](#11-итог----полная-цепочка-sync)

---

## 1. Обзор -- архитектура sync

### Полный pipeline синхронизации

```
CLI (sync-netbox --interfaces)
  |
  v
NetBoxSync.sync_interfaces(device_name, interfaces)
  |
  +-- 1. Получить устройство из NetBox (client.get_device_by_name)
  +-- 2. Получить существующие интерфейсы (client.get_interfaces)
  +-- 3. Подготовить локальные данные (type, speed, duplex, vlan)
  |
  v
SyncComparator.compare_interfaces(local, remote)
  |
  +-- Построить local_dict и remote_dict (O(n))
  +-- Forward pass: local -> CREATE или UPDATE или SKIP
  +-- Backward pass: remote \ local -> DELETE или SKIP
  |
  v
SyncDiff {to_create, to_update, to_delete, to_skip}
  |
  v
Batch API операции:
  +-- _batch_create_interfaces()  -> client.bulk_create_interfaces()
  +-- _batch_update_interfaces()  -> client.bulk_update_interfaces()
  +-- _batch_delete_interfaces()  -> client.bulk_delete_interfaces()
  |                                    | (при ошибке)
  |                              fallback -> поштучные операции
  v
NetBox (через pynetbox API)
```

### Композиция класса NetBoxSync

`NetBoxSync` собирается из 6 mixin-классов и базового класса:

```python
# Файл: netbox/sync/main.py
class NetBoxSync(
    InterfacesSyncMixin,    # sync_interfaces, _build_create_data, _build_update_data
    CablesSyncMixin,        # sync_cables_from_lldp, _find_neighbor_device
    IPAddressesSyncMixin,   # sync_ip_addresses, _set_primary_ip
    DevicesSyncMixin,       # create_device, sync_devices_from_inventory
    VLANsSyncMixin,         # sync_vlans_from_interfaces
    InventorySyncMixin,     # sync_inventory
    SyncBase,               # кэши, _safe_netbox_call, _batch_with_fallback, _parse_*
):
    def __init__(
        self,
        client: NetBoxClient,
        dry_run: bool = False,
        create_only: bool = False,
        update_only: bool = False,
        context: Optional[RunContext] = None,
    ):
        super().__init__(
            client=client, dry_run=dry_run,
            create_only=create_only, update_only=update_only,
            context=context,
        )
```

### Что здесь происходит

Каждый mixin добавляет методы для своего типа данных. При вызове `sync.sync_interfaces(...)` Python ищет метод по MRO (Method Resolution Order) -- находит его в `InterfacesSyncMixin`. Внутри mixin вызывает методы из `SyncBase` (кэши, batch, парсинг) через `self`, потому что `self` -- это экземпляр `NetBoxSync`, который наследует всё.

`SyncBase` стоит **последним** в цепочке наследования. Это важно: `super().__init__()` в `NetBoxSync` вызывает именно `SyncBase.__init__()`, потому что ни один mixin не определяет свой `__init__`.

> **Python-концепция: MRO (Method Resolution Order)**
> Python обходит базовые классы слева направо, в глубину, используя алгоритм C3-линеаризации. Для `NetBoxSync` MRO:
> `NetBoxSync -> InterfacesSyncMixin -> CablesSyncMixin -> ... -> SyncBase -> object`.
> Метод ищется в этом порядке, первое совпадение побеждает. Проверить можно: `NetBoxSync.__mro__`.

---

## 2. SyncBase -- фундамент

`SyncBase` -- это базовый класс, содержащий:
- Инициализацию (client, dry_run, кэши)
- SyncStats для единообразной инициализации статистики
- Систему кэширования (устройства, VLAN, интерфейсы)
- Паттерн get-or-create для NetBox-объектов
- Обёртку для безопасных API-вызовов
- Batch с автоматическим fallback
- Парсинг скорости и duplex

### 2.1 Инициализация -- `__init__()`

```python
# Файл: netbox/sync/base.py
class SyncBase:
    def __init__(
        self,
        client: NetBoxClient,
        dry_run: bool = False,
        create_only: bool = False,
        update_only: bool = False,
        context: Optional[RunContext] = None,
    ):
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
```

### Что здесь происходит

При создании `NetBoxSync(client, dry_run=True)` вызывается `SyncBase.__init__()`. Инициализируются пять словарей-кэшей, каждый со своей структурой:

| Кэш | Ключ | Значение | Зачем |
|-----|------|----------|-------|
| `_device_cache` | `"switch-01"` | Device object | Не искать устройство повторно |
| `_mac_cache` | `"aabbccddeeff"` | Device object | Поиск по MAC для LLDP |
| `_vlan_cache` | `(100, "Office")` | VLAN object | Один GET на все VLAN сайта |
| `_vlan_id_to_vid` | `42` (NetBox ID) | `100` (VID) | Избежать lazy-load pynetbox |
| `_interface_cache` | `15` (device_id) | `{"Gi0/1": obj}` | Один GET на все интерфейсы |

> **Python-концепция: Dict[Tuple[int, str], Any]**
> Ключом словаря может быть любой неизменяемый (hashable) объект. Кортеж `(vid, site)` -- отличный составной ключ. Список `[vid, site]` ключом быть не может, потому что он изменяемый.

---

### 2.2 SyncStats -- инициализация статистики

```python
# Файл: netbox/sync/base.py
class SyncStats:
    # Маппинг ключей stats -> ключей details (created->create, etc.)
    _DETAIL_KEY_MAP = {
        "created": "create",
        "updated": "update",
        "deleted": "delete",
        "skipped": "skip",
    }

    def __init__(self, *operations: str):
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
```

### Что здесь происходит

`SyncStats` убирает дублирование инициализации `stats` и `details` в каждом sync-методе:

```python
# Было (повторялось в 6 местах):
stats = {"created": 0, "updated": 0, "deleted": 0, "skipped": 0}
details = {"create": [], "update": [], "delete": [], "skip": []}

# Стало:
ss = SyncStats("created", "updated", "deleted", "skipped")
stats, details = ss.stats, ss.details
```

Маппинг `_DETAIL_KEY_MAP` конвертирует прошедшее время (`"created"`) в императив (`"create"`), потому что stats считает "сколько создано", а details хранит "что создать".

Трансформация данных:

```
Вход:  SyncStats("created", "updated", "deleted", "skipped", "failed")
                     |
stats:   {"created": 0, "updated": 0, "deleted": 0, "skipped": 0, "failed": 0}
details: {"create": [], "update": [], "delete": [], "skip": []}
         (для "failed" нет маппинга -- не попадёт в details)
                     |
result(): {"created": 3, "updated": 1, "deleted": 0, "skipped": 10, "failed": 0,
           "details": {"create": [...], "update": [...], "delete": [], "skip": []}}
```

> **Python-концепция: *args (variadic arguments)**
> `*operations: str` принимает произвольное количество строковых аргументов. Внутри функции `operations` -- это tuple: `("created", "updated", ...)`. Dict comprehension `{op: 0 for op in operations}` создаёт словарь из этого tuple.

---

### 2.3 `_safe_netbox_call()` -- централизованная обработка ошибок

```python
# Файл: netbox/sync/base.py
def _safe_netbox_call(
    self,
    operation: str,
    fn: Callable,
    *args,
    default: Any = None,
    log_level: str = "error",
    **kwargs,
) -> Any:
    log_fn = getattr(logger, log_level)
    try:
        return fn(*args, **kwargs)
    except (NetBoxError, NetBoxValidationError, NetBoxConnectionError) as e:
        log_fn(f"{self._log_prefix()}Ошибка {operation}: {format_error_for_log(e)}")
        return default
    except Exception as e:
        log_fn(f"{self._log_prefix()}Неизвестная ошибка {operation}: {e}")
        return default
```

### Что здесь происходит

Этот метод оборачивает любой API-вызов в единый `try/except`. Вместо повторения блока обработки ошибок:

```python
# Вместо:
try:
    device.update(updates)
except NetBoxError as e:
    logger.error(f"Ошибка обновления: {e}")
    return False

# Пишем:
result = self._safe_netbox_call(
    "обновление устройства",
    device.update, updates,
    default=False,
)
```

Ключевые моменты:
- `fn: Callable` -- принимает любую вызываемую функцию (метод, лямбду)
- `*args, **kwargs` -- передаются в `fn` как есть
- `log_level` позволяет использовать `"warning"` вместо `"error"` для некритичных операций
- `getattr(logger, log_level)` динамически выбирает `logger.error` или `logger.warning`

> **Python-концепция: Callable и getattr**
> `Callable` -- тип-подсказка для "любого вызываемого объекта". Функция, метод, lambda -- всё подходит.
> `getattr(logger, "error")` эквивалентен `logger.error` -- это доступ к атрибуту по строке. Позволяет выбирать метод динамически, в runtime.

---

### 2.4 `_batch_with_fallback()` -- batch с автоматическим откатом

Это один из ключевых методов проекта. Он реализует паттерн: "попробуй batch, если не получилось -- обработай по одному".

```python
# Файл: netbox/sync/base.py
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
    if not batch_data:
        return None

    # Определяем ключ для details: created -> create, deleted -> delete
    detail_section = operation.rstrip("d").rstrip("e") + "e"

    try:
        result = bulk_fn(batch_data)
        for name in item_names:
            logger.info(
                f"{self._log_prefix()}"
                f"{'Создан' if operation == 'created' "
                f"else 'Удалён' if operation == 'deleted' "
                f"else 'Обновлён'} {entity_name}: {name}"
            )
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
                logger.info(f"{self._log_prefix()}... {entity_name}: {name}")
                stats[operation] = stats.get(operation, 0) + 1
                details[detail_section].append({detail_key: name})
            except Exception as exc:
                logger.error(
                    f"{self._log_prefix()}Ошибка {operation} {entity_name} {name}: {exc}"
                )
                stats["failed"] = stats.get("failed", 0) + 1
        return None
```

### Что здесь происходит

**Алгоритм:**
1. Если `batch_data` пустой -- сразу выходим
2. Вычисляем ключ для details: `"created"` -> `"create"` (строковые манипуляции)
3. Пробуем `bulk_fn(batch_data)` -- один API-вызов на весь список
4. Если успех -- обновляем stats и details для каждого элемента
5. Если ошибка -- `fallback_fn(data, name)` для каждого элемента отдельно
6. При ошибке отдельного элемента -- увеличиваем `stats["failed"]`

**Трансформация detail_section:**
```
"created" -> rstrip("d") -> "create" -> rstrip("e") -> "creat" -> + "e" -> "create"
"deleted" -> rstrip("d") -> "delete" -> rstrip("e") -> "delet" -> + "e" -> "delete"
"updated" -> rstrip("d") -> "update" -> rstrip("e") -> "updat" -> + "e" -> "update"
```

**Пример вызова из InterfacesSyncMixin:**

```python
self._batch_with_fallback(
    batch_data=delete_ids,                              # [101, 102, 103]
    item_names=delete_names,                            # ["Gi0/1", "Gi0/2", "Gi0/3"]
    bulk_fn=self.client.bulk_delete_interfaces,         # один вызов DELETE
    fallback_fn=lambda item_id, name:
        self.client.api.dcim.interfaces.get(item_id).delete(),  # поштучно
    stats=stats, details=details,
    operation="deleted", entity_name="интерфейс",
)
```

> **Python-концепция: zip() для параллельных списков**
> `zip(batch_data, item_names)` объединяет два списка в пары: `[(data1, name1), (data2, name2), ...]`.
> Это позволяет обойти два списка одновременно в fallback-цикле. Если списки разной длины, `zip` остановится на более коротком.

---

### 2.5 Система кэширования -- подробный разбор

#### `_find_device()` -- кэш устройств по имени

```python
# Файл: netbox/sync/base.py
def _find_device(self, name: str) -> Optional[Any]:
    if name in self._device_cache:
        return self._device_cache[name]
    device = self.client.get_device_by_name(name)
    if device:
        self._device_cache[name] = device
    return device
```

Простой паттерн "проверь кэш, иначе запроси и сохрани".

#### `_get_vlan_by_vid()` -- VLAN по составному ключу (vid, site)

```python
# Файл: netbox/sync/base.py
def _get_vlan_by_vid(self, vid: int, site: Optional[str] = None) -> Optional[Any]:
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
```

### Что здесь происходит

**Трёхуровневая стратегия:**
1. Проверяем кэш по ключу `(vid, site)`
2. Если сайт ещё не загружен -- загружаем **ВСЕ** VLAN сайта одним запросом
3. Проверяем кэш повторно (VLAN мог появиться после загрузки)

Ключ `f"_site_loaded_{site}"` -- это маркер-флаг в том же словаре, что сайт уже загружен.

#### `_load_site_vlans()` и обратный кэш `_vlan_id_to_vid`

```python
# Файл: netbox/sync/base.py
def _load_site_vlans(self, site: Optional[str] = None) -> None:
    try:
        vlans = list(self.client.get_vlans(site=site))
        count = 0
        for vlan in vlans:
            cache_key = (vlan.vid, site or "")
            self._vlan_cache[cache_key] = vlan
            # Обратный кэш: ID -> VID (для _check_untagged_vlan без lazy-load)
            self._vlan_id_to_vid[vlan.id] = vlan.vid
            count += 1
        logger.debug(f"Загружено {count} VLANs для сайта '{site}'")
    except Exception as e:
        logger.warning(f"Ошибка загрузки VLANs для сайта '{site}': {e}")
```

`_vlan_id_to_vid` -- обратный кэш, позволяющий по NetBox ID (например, 42) получить VID (например, 100) без обращения к API. Это критично для решения N+1 проблемы (подробнее в секции 3).

#### `_find_interface()` -- кэш интерфейсов с нормализацией имён

```python
# Файл: netbox/sync/base.py
def _find_interface(self, device_id: int, interface_name: str) -> Optional[Any]:
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
```

### Что здесь происходит

Двухэтапный поиск:
1. **Точное совпадение** -- O(1) по хэш-таблице
2. **Нормализованное** -- перебор с нормализацией обоих имён (Gi0/1 -> gigabitethernet0/1)

Кэш загружается один раз на `device_id` -- все интерфейсы одним API-запросом.

---

### 2.6 Get-or-Create паттерн

```python
# Файл: netbox/sync/base.py
def _get_or_create(
    self, endpoint, name: str,
    extra_data: Optional[Dict[str, Any]] = None,
    get_field: str = "name",
    use_transliterate: bool = False,
    log_level: str = "error",
) -> Optional[Any]:
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
```

Все `_get_or_create_*` методы делегируют сюда:

```python
# Файл: netbox/sync/base.py
def _get_or_create_manufacturer(self, name: str) -> Optional[Any]:
    return self._get_or_create(self.client.api.dcim.manufacturers, name)

def _get_or_create_device_type(self, model: str, manufacturer_id: int) -> Optional[Any]:
    normalized = normalize_device_model(model)
    return self._get_or_create(
        self.client.api.dcim.device_types, normalized,
        extra_data={"manufacturer": manufacturer_id},
        get_field="model",
    )

def _get_or_create_site(self, name: str) -> Optional[Any]:
    return self._get_or_create(
        self.client.api.dcim.sites, name,
        extra_data={"status": "active"},
    )

def _get_or_create_tenant(self, name: str) -> Optional[Any]:
    return self._get_or_create(
        self.client.api.tenancy.tenants, name,
        use_transliterate=True,
    )
```

> **Python-концепция: **kwargs в endpoint.get()**
> `endpoint.get(**{get_field: name})` -- распаковка словаря в именованные аргументы. Если `get_field="model"`, вызов превращается в `endpoint.get(model=name)`. Это позволяет одной функции искать по разным полям.

---

### 2.7 `_parse_speed()` и `_parse_duplex()` -- парсинг строк

```python
# Файл: netbox/sync/base.py
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
```

### Что здесь происходит

NetBox хранит скорость в **kbps** (килобитах в секунду). Устройства отдают скорость в разных форматах.

```
_parse_speed:
  "1 Gbit"    -> 1000000 (kbps)
  "100 Mbit"  -> 100000  (kbps)
  "10000"     -> 10000   (kbps)
  ""          -> None

_parse_duplex:
  "Full-duplex" -> "full"
  "Half"        -> "half"
  "auto"        -> "auto"
  ""            -> None
```

---

## 3. SyncComparator -- сравнение данных

`SyncComparator` находится в domain-слое (`core/domain/sync.py`). Это **чистые функции** -- они не зависят от NetBox, не делают API-вызовов. Принимают данные, возвращают diff.

### 3.1 Структуры данных

```python
# Файл: core/domain/sync.py
class ChangeType(str, Enum):
    """Тип изменения."""
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    SKIP = "skip"


@dataclass
class FieldChange:
    """Изменение одного поля."""
    field: str
    old_value: Any
    new_value: Any

    def __str__(self) -> str:
        return f"{self.field}: {self.old_value!r} -> {self.new_value!r}"


@dataclass
class SyncItem:
    """Элемент для синхронизации."""
    name: str
    change_type: ChangeType
    local_data: Optional[Dict[str, Any]] = None
    remote_data: Optional[Any] = None
    changes: List[FieldChange] = field(default_factory=list)
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "change_type": self.change_type.value,
            "changes": [
                {"field": c.field, "old": c.old_value, "new": c.new_value}
                for c in self.changes
            ],
            "reason": self.reason,
        }


@dataclass
class SyncDiff:
    """Результат сравнения для синхронизации."""
    object_type: str
    target: str = ""
    to_create: List[SyncItem] = field(default_factory=list)
    to_update: List[SyncItem] = field(default_factory=list)
    to_delete: List[SyncItem] = field(default_factory=list)
    to_skip: List[SyncItem] = field(default_factory=list)

    @property
    def total_changes(self) -> int:
        return len(self.to_create) + len(self.to_update) + len(self.to_delete)

    @property
    def has_changes(self) -> bool:
        return self.total_changes > 0

    def summary(self) -> str:
        parts = []
        if self.to_create:
            parts.append(f"+{len(self.to_create)} create")
        if self.to_update:
            parts.append(f"~{len(self.to_update)} update")
        if self.to_delete:
            parts.append(f"-{len(self.to_delete)} delete")
        if self.to_skip:
            parts.append(f"={len(self.to_skip)} skip")
        return f"{self.object_type}: {', '.join(parts)}" if parts \
            else f"{self.object_type}: no changes"
```

### Что здесь происходит

Три dataclass-а образуют иерархию результата сравнения:

```
SyncDiff (один на операцию)
+-- to_create: [SyncItem, SyncItem, ...]
|   +-- SyncItem.name = "GigabitEthernet0/3"
|       SyncItem.local_data = {"name": "...", "type": "1000base-t", ...}
+-- to_update: [SyncItem, ...]
|   +-- SyncItem.changes = [FieldChange("description", "old", "new"),
|                            FieldChange("enabled", True, False)]
+-- to_delete: [SyncItem, ...]
|   +-- SyncItem.remote_data = <NetBox object>
+-- to_skip: [SyncItem, ...]
    +-- SyncItem.reason = "no changes"
```

> **Python-концепция: @dataclass и field(default_factory=list)**
> `@dataclass` автоматически генерирует `__init__`, `__repr__`, `__eq__`. Ты определяешь только поля с типами.
> `field(default_factory=list)` -- создаёт **новый** пустой список для каждого экземпляра. Без `default_factory` все экземпляры разделяли бы один список -- классическая ловушка Python с мутабельными значениями по умолчанию.

> **Python-концепция: Enum наследующий str**
> `ChangeType(str, Enum)` -- наследование от `str` позволяет использовать значения enum как строки: `ChangeType.CREATE == "create"` вернёт `True`. Это удобно для сериализации в JSON.

---

### 3.2 `compare_interfaces()` -- полный алгоритм

```python
# Файл: core/domain/sync.py
class SyncComparator:
    def compare_interfaces(
        self,
        local: List[Dict[str, Any]],
        remote: List[Any],
        exclude_patterns: Optional[List[str]] = None,
        create_missing: bool = True,
        update_existing: bool = True,
        cleanup: bool = False,
        compare_fields: Optional[List[str]] = None,
        enabled_mode: str = "admin",
    ) -> SyncDiff:
        diff = SyncDiff(object_type="interfaces")
        exclude_patterns = exclude_patterns or []
        compare_fields = compare_fields or ["description", "enabled", "mode"]

        # ШАГ 1: Строим словари O(n)
        local_dict = {}
        for item in local:
            if hasattr(item, "to_dict"):
                item = item.to_dict()
            name = item.get("name") or item.get("interface", "")
            if name:
                local_dict[name] = item

        remote_dict = {}
        for item in remote:
            name = item.name if hasattr(item, "name") else item.get("name", "")
            if name:
                remote_dict[name] = item

        # Множество обработанных имён
        processed = set()

        # ШАГ 2: Forward pass -- проходим по локальным интерфейсам
        for name, local_data in local_dict.items():
            if self._is_excluded(name, exclude_patterns):
                diff.to_skip.append(SyncItem(
                    name=name, change_type=ChangeType.SKIP,
                    local_data=local_data, reason="excluded by pattern",
                ))
                processed.add(name)
                continue

            processed.add(name)

            if name in remote_dict:
                # Существует -- проверяем обновление
                if update_existing:
                    changes = self._compare_interface_fields(
                        local_data, remote_dict[name], compare_fields, enabled_mode
                    )
                    if changes:
                        diff.to_update.append(SyncItem(
                            name=name, change_type=ChangeType.UPDATE,
                            local_data=local_data, remote_data=remote_dict[name],
                            changes=changes,
                        ))
                    else:
                        diff.to_skip.append(SyncItem(
                            name=name, change_type=ChangeType.SKIP,
                            local_data=local_data, remote_data=remote_dict[name],
                            reason="no changes",
                        ))
                else:
                    diff.to_skip.append(SyncItem(
                        name=name, change_type=ChangeType.SKIP,
                        reason="update_existing=False",
                    ))
            else:
                # Новый интерфейс
                if create_missing:
                    diff.to_create.append(SyncItem(
                        name=name, change_type=ChangeType.CREATE,
                        local_data=local_data,
                    ))

        # ШАГ 3: Backward pass -- ищем лишние в remote
        if cleanup:
            for name, remote_data in remote_dict.items():
                if name not in processed:
                    if not self._is_excluded(name, exclude_patterns):
                        diff.to_delete.append(SyncItem(
                            name=name, change_type=ChangeType.DELETE,
                            remote_data=remote_data,
                        ))

        return diff
```

### Что здесь происходит

Алгоритм сравнения за **O(n)** состоит из двух проходов:

```
Вход:
  local  = [Gi0/1, Gi0/2, Gi0/3]  (собрано с устройства)
  remote = [Gi0/1, Gi0/2, Gi0/99] (есть в NetBox)

Шаг 1 (построение dict, O(n)):
  local_dict  = {"Gi0/1": {...}, "Gi0/2": {...}, "Gi0/3": {...}}
  remote_dict = {"Gi0/1": <nb_obj>, "Gi0/2": <nb_obj>, "Gi0/99": <nb_obj>}

Шаг 2 (forward pass, O(n)):
  Gi0/1: есть в remote -> сравниваем поля -> UPDATE или SKIP
  Gi0/2: есть в remote -> сравниваем поля -> UPDATE или SKIP
  Gi0/3: нет в remote  -> CREATE
  processed = {"Gi0/1", "Gi0/2", "Gi0/3"}

Шаг 3 (backward pass, O(n), только если cleanup=True):
  Gi0/99: не в processed -> DELETE

Результат:
  to_create = [Gi0/3]
  to_update = [Gi0/1] (если были изменения)
  to_delete = [Gi0/99]
  to_skip   = [Gi0/2] (если без изменений)
```

Общая сложность O(n), потому что:
- Построение dict -- O(n)
- Проверка `name in remote_dict` -- O(1) для хэш-таблицы
- Проверка `name not in processed` -- O(1) для множества

> **Python-концепция: set для O(1) lookup**
> `processed = set()` используется вместо списка, потому что проверка `name not in processed` для множества -- O(1), для списка -- O(n). Для устройства с 100 интерфейсами разница ощутима.

---

### 3.3 `_compare_interface_fields()` и N+1 проблема

```python
# Файл: core/domain/sync.py
def _compare_interface_fields(
    self, local: Dict[str, Any], remote: Any,
    fields: List[str], enabled_mode: str = "admin",
) -> List[FieldChange]:
    changes = []
    for field_name in fields:
        local_val = self._get_local_field(local, field_name, enabled_mode)
        remote_val = self._get_remote_field(remote, field_name)

        if local_val is not None and local_val != remote_val:
            # Для mode: "" и None -- оба означают "нет mode"
            if field_name == "mode" and not local_val and not remote_val:
                continue
            changes.append(FieldChange(
                field=field_name, old_value=remote_val, new_value=local_val,
            ))
    return changes
```

`_get_local_field()` извлекает значение из словаря с нормализацией:

```python
# Файл: core/domain/sync.py
def _get_local_field(self, data: Dict[str, Any], field_name: str,
                     enabled_mode: str = "admin") -> Any:
    if field_name == "enabled":
        status = data.get("status", "")
        if status:
            if enabled_mode == "link":
                return status.lower() == "up"           # Только up = enabled
            else:
                return status.lower() not in ("disabled", "error")  # admin mode
        return None
    elif field_name == "description":
        if "description" in data:
            return data["description"]    # Пустая строка -- валидное значение
        return None                       # None = пропустить сравнение
    elif field_name == "untagged_vlan":
        val = data.get("untagged_vlan")
        try:
            return int(val) if val is not None else None
        except (ValueError, TypeError):
            return None
    else:
        return data.get(field_name)
```

`_get_remote_field()` извлекает значение из pynetbox-объекта:

```python
# Файл: core/domain/sync.py
def _get_remote_field(self, remote: Any, field_name: str) -> Any:
    if isinstance(remote, dict):
        return remote.get(field_name)

    if not hasattr(remote, field_name):
        return None

    val = getattr(remote, field_name)

    # Для VLAN полей: извлекаем VID напрямую, БЕЗ hasattr(val, "value").
    # hasattr на pynetbox nested Record вызывает __getattr__ -> full_details()
    # -> лишний GET-запрос к API на каждый интерфейс (N+1 проблема).
    # .vid доступен в brief response и не вызывает lazy-load.
    if field_name == "untagged_vlan":
        if val is None:
            return None
        try:
            return val.vid
        except (AttributeError, TypeError):
            return None

    if field_name == "tagged_vlans":
        if not val:
            return []
        try:
            return sorted(v.vid for v in val)
        except (AttributeError, TypeError):
            return []

    # Для enum-like объектов (type, mode, duplex) извлекаем value
    if hasattr(val, "value"):
        return val.value
    return val
```

### N+1 проблема -- критичный момент

Это одно из самых важных мест в коде. Pynetbox использует **lazy loading**: при обращении к неизвестному атрибуту (через `__getattr__`) делает полный GET-запрос к API.

```python
# ПЛОХО -- N+1 проблема:
if hasattr(val, "value"):     # для untagged_vlan это вызовет __getattr__
    return val.value           # -> pynetbox делает GET /api/ipam/vlans/{id}/
                               # -> на КАЖДЫЙ интерфейс = N лишних запросов!

# ХОРОШО -- прямой доступ к .vid:
return val.vid                 # .vid доступен в brief response, без lazy-load
```

`hasattr()` внутри вызывает `getattr()`, а для pynetbox nested Record неизвестный атрибут триггерит `__getattr__` -> `full_details()` -> GET-запрос к API. Атрибут `.vid` доступен в brief response (приходит вместе со списком интерфейсов), поэтому лишний запрос не нужен.

---

## 4. InterfacesSyncMixin -- полный трейс

Это самый большой и важный mixin. Разберём `sync_interfaces()` шаг за шагом.

### 4.1 `sync_interfaces()` -- главный метод

```python
# Файл: netbox/sync/interfaces.py
class InterfacesSyncMixin:
    def sync_interfaces(
        self: SyncBase,
        device_name: str,
        interfaces: List[Interface],
        create_missing: Optional[bool] = None,
        update_existing: Optional[bool] = None,
        cleanup: bool = False,
    ) -> Dict[str, Any]:
```

> **Python-концепция: self: SyncBase**
> Аннотация типа `self: SyncBase` в mixin -- это подсказка IDE и разработчику:
> "этот метод вызывается на объекте, у которого есть атрибуты SyncBase".
> В runtime `self` -- это экземпляр `NetBoxSync`, но IDE покажет автодополнение для `SyncBase`.
> Python не проверяет это ограничение -- это чистая документация.

**Шаг 1: Инициализация stats и загрузка конфигурации**

```python
        ss = SyncStats("created", "updated", "deleted", "skipped")
        stats, details = ss.stats, ss.details
        sync_cfg = get_sync_config("interfaces")

        if create_missing is None:
            create_missing = sync_cfg.get_option("create_missing", True)
        if update_existing is None:
            update_existing = sync_cfg.get_option("update_existing", True)
```

`get_sync_config("interfaces")` загружает настройки из `fields.yaml` -- какие поля синхронизировать, sync_vlans, enabled_mode и т.д. Если `create_missing` / `update_existing` не переданы явно, берутся из конфига.

**Шаг 2: Поиск устройства с fallback по IP**

```python
        device = self.client.get_device_by_name(device_name)
        if not device:
            device_ip = None
            if interfaces:
                first_intf = interfaces[0] if isinstance(interfaces, list) else None
                if first_intf:
                    device_ip = first_intf.get("device_ip") if isinstance(first_intf, dict) \
                        else getattr(first_intf, "device_ip", None)
            if not device_ip and device_name and device_name.replace(".", "").isdigit():
                device_ip = device_name
            if device_ip:
                device = self.client.get_device_by_ip(device_ip)
        if not device:
            logger.error(f"Устройство не найдено в NetBox: {device_name}")
            stats["failed"] = 1
            return stats
```

Если устройство не найдено по имени -- пробуем по IP (полезно, когда hostname в инвентаре = IP-адрес).

**Шаг 3: Кэширование site_name и предзагрузка VLAN**

```python
        site_name = None
        if hasattr(device, 'site') and device.site:
            site_name = getattr(device.site, 'name', None)

        # Предзагружаем кэш VLAN для сайта (один API-запрос)
        if sync_cfg.get_option("sync_vlans", False) and site_name:
            self._get_vlan_by_vid(1, site_name)  # Форсирует загрузку всех VLAN сайта
```

Один вызов `_get_vlan_by_vid(1, site_name)` загружает ВСЕ VLAN сайта в кэш. Дальше все обращения к VLAN идут из кэша без API-запросов.

**Шаг 4: Получение существующих интерфейсов и сортировка LAG-first**

```python
        existing = list(self.client.get_interfaces(device_id=device.id))
        exclude_patterns = sync_cfg.get_option("exclude_interfaces", [])
        interface_models = Interface.ensure_list(interfaces)

        # port_type заполняется нормализатором (detect_port_type)
        sorted_interfaces = sorted(
            interface_models,
            key=lambda intf: 0 if intf.port_type == "lag" else 1,
        )
```

### Что здесь происходит (сортировка)

LAG интерфейсы идут первыми, потому что при создании member-интерфейса нужен ID LAG, а LAG должен уже существовать в NetBox. Тип определяется через `port_type` — поле модели `Interface`, заполненное нормализатором (`detect_port_type()`) до вызова sync.

```
Вход:  [Gi0/1, Po1, Gi0/2, Ag10, Gi0/3]
                  | sorted(key=lambda intf: 0 if intf.port_type == "lag" else 1)
Выход: [Po1, Ag10, Gi0/1, Gi0/2, Gi0/3]
         ^          ^
      port_type="lag"   port_type!="lag"
```

Универсальность: не проверяем имена напрямую (`"port-channel"`, `"ag"` и т.д.), а используем уже вычисленный `port_type`. Если добавится новая платформа с другим именем LAG — достаточно обновить только `detect_port_type()`.

> **Python-концепция: sorted(key=)**
> Параметр `key` принимает функцию, которая вызывается для каждого элемента и возвращает значение для сортировки. `sorted` стабилен: элементы с одинаковым ключом сохраняют исходный порядок.

**Шаг 5: Подготовка локальных данных с вычисляемыми полями**

```python
        comparator = SyncComparator()
        local_data = []
        for intf in sorted_interfaces:
            if intf.name:
                data = intf.to_dict()
                if sync_cfg.get_option("auto_detect_type", True):
                    data["type"] = get_netbox_interface_type(interface=intf)
                if intf.speed:
                    data["speed"] = self._parse_speed(intf.speed)
                if intf.duplex:
                    data["duplex"] = self._parse_duplex(intf.duplex)
                if sync_cfg.get_option("sync_vlans", False):
                    if intf.mode == "access" and intf.access_vlan:
                        data["untagged_vlan"] = intf.access_vlan
                    elif intf.mode in ("tagged", "tagged-all") and intf.native_vlan:
                        data["untagged_vlan"] = intf.native_vlan
                local_data.append(data)
```

Трансформация данных на этом этапе:

```
Interface(name="Gi0/1", speed="1 Gbit", duplex="Full",
          mode="access", access_vlan="10")
                              |
{"name": "Gi0/1", "type": "1000base-t", "speed": 1000000,
 "duplex": "full", "mode": "access", "untagged_vlan": "10",
 "description": "Server1", ...}
```

**Шаг 6: Вызов SyncComparator и batch-операции**

```python
        enabled_mode = sync_cfg.get_option("enabled_mode", "admin")
        compare_fields = ["description", "enabled", "mode", "mtu", "duplex", "speed"]
        if sync_cfg.get_option("auto_detect_type", True):
            compare_fields.append("type")
        if sync_cfg.get_option("sync_vlans", False):
            compare_fields.extend(["untagged_vlan", "tagged_vlans"])

        diff = comparator.compare_interfaces(
            local=local_data, remote=existing,
            exclude_patterns=exclude_patterns,
            create_missing=create_missing, update_existing=update_existing,
            cleanup=cleanup, enabled_mode=enabled_mode,
            compare_fields=compare_fields,
        )

        # === BATCH CREATE ===
        self._batch_create_interfaces(
            device.id, diff.to_create, sorted_interfaces, stats, details,
            site_name=site_name,
        )
        # === BATCH UPDATE ===
        self._batch_update_interfaces(
            diff.to_update, sorted_interfaces, stats, details, site_name=site_name
        )
        # === BATCH DELETE ===
        self._batch_delete_interfaces(diff.to_delete, stats, details)

        stats["skipped"] += len(diff.to_skip)
        stats["local_count"] = len(sorted_interfaces)
        stats["remote_count"] = len(existing)
        stats["details"] = details
        return stats
```

---

### 4.2 `_build_create_data()` -- подготовка данных для создания

```python
# Файл: netbox/sync/interfaces.py
def _build_create_data(
    self: SyncBase, device_id: int, intf: Interface,
    site_name: Optional[str] = None,
) -> Tuple[Optional[Dict], Optional[str]]:
    sync_cfg = get_sync_config("interfaces")

    data = {
        "device": device_id,
        "name": intf.name,
        "type": get_netbox_interface_type(interface=intf),
    }

    if sync_cfg.is_field_enabled("description"):
        data["description"] = intf.description
    if sync_cfg.is_field_enabled("enabled"):
        data["enabled"] = intf.status not in ("disabled", "error")

    mac_to_assign = None
    if sync_cfg.is_field_enabled("mac_address") and intf.mac:
        sync_mac_only_with_ip = sync_cfg.get_option("sync_mac_only_with_ip", False)
        if not (sync_mac_only_with_ip and not intf.ip_address):
            mac_to_assign = normalize_mac_netbox(intf.mac)

    if sync_cfg.is_field_enabled("mtu") and intf.mtu:
        data["mtu"] = intf.mtu
    if sync_cfg.is_field_enabled("speed") and intf.speed:
        data["speed"] = self._parse_speed(intf.speed)
    if sync_cfg.is_field_enabled("duplex") and intf.duplex:
        data["duplex"] = self._parse_duplex(intf.duplex)
    if sync_cfg.is_field_enabled("mode") and intf.mode:
        data["mode"] = intf.mode

    # LAG привязка
    if intf.lag:
        lag_interface = self.client.get_interface_by_name(device_id, intf.lag)
        if lag_interface:
            data["lag"] = lag_interface.id

    # VLAN назначение при создании
    if sync_cfg.get_option("sync_vlans", False):
        target_vid = None
        if intf.mode == "access" and intf.access_vlan:
            try:
                target_vid = int(intf.access_vlan)
            except ValueError:
                pass
        elif intf.mode in ("tagged", "tagged-all") and intf.native_vlan:
            try:
                target_vid = int(intf.native_vlan)
            except ValueError:
                pass

        if target_vid:
            vlan = self._get_vlan_by_vid(target_vid, site_name)
            if vlan:
                data["untagged_vlan"] = vlan.id

        # Tagged VLANs (trunk порты)
        if intf.mode == "tagged" and intf.tagged_vlans:
            target_vids = parse_vlan_range(intf.tagged_vlans)
            if target_vids:
                tagged_ids = []
                for vid in target_vids:
                    vlan = self._get_vlan_by_vid(vid, site_name)
                    if vlan:
                        tagged_ids.append(vlan.id)
                if tagged_ids:
                    data["tagged_vlans"] = sorted(tagged_ids)

    return data, mac_to_assign
```

### Что здесь происходит

Метод возвращает кортеж `(data, mac_to_assign)`:
- `data` -- словарь для NetBox API (создание интерфейса)
- `mac_to_assign` -- MAC-адрес, который нужно назначить **отдельным** API-вызовом (MAC в NetBox 4.x назначается через отдельный endpoint)

Обратите внимание: `untagged_vlan` в API -- это NetBox ID объекта VLAN, а не VID. Поэтому нужен кэш для конвертации VID -> ID.

```
Interface(name="Gi0/1", description="Server", status="up",
          mac="aa:bb:cc:dd:ee:ff", speed="1 Gbit", mode="access",
          access_vlan="10", lag=None)
                              |
data = {
    "device": 42,
    "name": "Gi0/1",
    "type": "1000base-t",
    "description": "Server",
    "enabled": True,
    "speed": 1000000,
    "mode": "access",
    "untagged_vlan": 17,      # NetBox ID VLAN 10 (не VID!)
}
mac_to_assign = "AA:BB:CC:DD:EE:FF"
```

---

### 4.3 `_build_update_data()` -- оркестратор 11 проверок

```python
# Файл: netbox/sync/interfaces.py
def _build_update_data(
    self: SyncBase, nb_interface, intf: Interface,
    site_name: Optional[str] = None,
) -> Tuple[Dict, List[str], Optional[str]]:
    updates = {}
    actual_changes = []
    sync_cfg = get_sync_config("interfaces")

    # Проверка каждого поля через отдельный хелпер
    self._check_type(nb_interface, intf, sync_cfg, updates, actual_changes)
    self._check_description(nb_interface, intf, sync_cfg, updates, actual_changes)
    self._check_enabled(nb_interface, intf, sync_cfg, updates, actual_changes)
    mac_to_assign = self._check_mac(nb_interface, intf, sync_cfg, actual_changes)
    self._check_mtu(nb_interface, intf, sync_cfg, updates, actual_changes)
    self._check_speed(nb_interface, intf, sync_cfg, updates, actual_changes)
    self._check_duplex(nb_interface, intf, sync_cfg, updates, actual_changes)
    self._check_mode(nb_interface, intf, sync_cfg, updates, actual_changes)
    self._check_untagged_vlan(nb_interface, intf, sync_cfg, updates, actual_changes,
                               site_name=site_name)
    self._check_tagged_vlans(nb_interface, intf, sync_cfg, updates, actual_changes,
                              site_name=site_name)
    self._check_lag(nb_interface, intf, sync_cfg, updates, actual_changes)

    return updates, actual_changes, mac_to_assign
```

### Что здесь происходит

`_build_update_data()` -- это оркестратор, который вызывает 11 независимых `_check_*()` хелперов. Каждый хелпер модифицирует `updates` и `actual_changes` **in-place** (мутабельные словарь и список передаются по ссылке).

Рассмотрим ключевые хелперы:

#### `_check_type()` -- определение типа интерфейса

```python
# Файл: netbox/sync/interfaces.py
def _check_type(self: SyncBase, nb_interface, intf: Interface,
                sync_cfg, updates: Dict, actual_changes: List[str]) -> None:
    if not sync_cfg.get_option("auto_detect_type", True):
        return
    new_type = get_netbox_interface_type(interface=intf)
    current_type = getattr(nb_interface.type, 'value', None) if nb_interface.type else None
    if new_type and new_type != current_type:
        updates["type"] = new_type
        actual_changes.append(f"type: {current_type} -> {new_type}")
```

#### `_check_mode()` -- режим порта (access/tagged/tagged-all)

```python
# Файл: netbox/sync/interfaces.py
def _check_mode(self: SyncBase, nb_interface, intf: Interface,
                sync_cfg, updates: Dict, actual_changes: List[str]) -> None:
    if not sync_cfg.is_field_enabled("mode"):
        return
    current_mode = getattr(nb_interface.mode, 'value', None) if nb_interface.mode else None
    if intf.mode and intf.mode != current_mode:
        updates["mode"] = intf.mode
        actual_changes.append(f"mode: {current_mode} -> {intf.mode}")
    elif not intf.mode and current_mode:
        updates["mode"] = ""                  # Очистка mode для shutdown портов
        actual_changes.append(f"mode: {current_mode} -> None")
```

#### `_check_untagged_vlan()` -- проверка VLAN с защитой от N+1

```python
# Файл: netbox/sync/interfaces.py
def _check_untagged_vlan(
    self: SyncBase, nb_interface, intf: Interface,
    sync_cfg, updates: Dict, actual_changes: List[str],
    site_name: Optional[str] = None,
) -> None:
    if not (sync_cfg.is_field_enabled("untagged_vlan") and
            sync_cfg.get_option("sync_vlans", False)):
        return

    target_vid = None
    if intf.mode == "access" and intf.access_vlan:
        try:
            target_vid = int(intf.access_vlan)
        except ValueError:
            pass
    elif intf.mode in ("tagged", "tagged-all") and intf.native_vlan:
        try:
            target_vid = int(intf.native_vlan)
        except ValueError:
            pass

    # Получаем текущий VLAN без lazy-load pynetbox
    current_vlan_id = None
    current_vlan_vid = None
    if nb_interface.untagged_vlan:
        current_vlan_id = getattr(nb_interface.untagged_vlan, 'id', None)
        # VID из обратного кэша (без lazy-load), fallback на .vid
        if current_vlan_id:
            current_vlan_vid = self._vlan_id_to_vid.get(current_vlan_id)
        if current_vlan_vid is None:
            current_vlan_vid = getattr(nb_interface.untagged_vlan, 'vid', None)

    if target_vid:
        vlan = self._get_vlan_by_vid(target_vid, site_name)
        if vlan:
            if vlan.id != current_vlan_id:
                updates["untagged_vlan"] = vlan.id
                actual_changes.append(f"untagged_vlan: {current_vlan_vid} -> {target_vid}")
    elif current_vlan_id:
        updates["untagged_vlan"] = None
        actual_changes.append(f"untagged_vlan: {current_vlan_vid} -> None")
```

### Что здесь происходит

Обратите внимание на получение `current_vlan_vid`:
1. Сначала пробуем `self._vlan_id_to_vid.get(current_vlan_id)` -- из обратного кэша, **ноль API-вызовов**
2. Только если нет в кэше -- `getattr(nb_interface.untagged_vlan, 'vid', None)` -- `.vid` доступен в brief

`site_name` передаётся из `sync_interfaces()`, где он уже закэширован. Без этого каждый вызов обращался бы к `nb_interface.device.site.name`, вызывая GET-запрос на каждый интерфейс.

#### `_check_tagged_vlans()` -- массовое сравнение VLAN через VlanSet

```python
# Файл: netbox/sync/interfaces.py
def _check_tagged_vlans(
    self: SyncBase, nb_interface, intf: Interface,
    sync_cfg, updates: Dict, actual_changes: List[str],
    site_name: Optional[str] = None,
) -> None:
    if not (sync_cfg.is_field_enabled("tagged_vlans") and
            sync_cfg.get_option("sync_vlans", False)):
        return

    if intf.mode == "tagged" and intf.tagged_vlans:
        target_vids = parse_vlan_range(intf.tagged_vlans)

        if target_vids:
            target_vlan_ids = []
            matched_vids = []
            for vid in target_vids:
                vlan = self._get_vlan_by_vid(vid, site_name)
                if vlan:
                    target_vlan_ids.append(vlan.id)
                    matched_vids.append(vid)

            current = VlanSet.from_vlan_objects(nb_interface.tagged_vlans)
            target = VlanSet.from_ids(matched_vids)

            if current != target:
                updates["tagged_vlans"] = sorted(target_vlan_ids)
                added = target.added(current)
                removed = target.removed(current)
                parts = []
                if added:
                    parts.append(f"+{sorted(added)}")
                if removed:
                    parts.append(f"-{sorted(removed)}")
                change_detail = ", ".join(parts) if parts else "изменено"
                actual_changes.append(f"tagged_vlans: {change_detail}")

    elif intf.mode != "tagged":
        current = VlanSet.from_vlan_objects(nb_interface.tagged_vlans)
        if current:
            updates["tagged_vlans"] = []
            actual_changes.append(f"tagged_vlans: -{current.sorted_list}")
```

`VlanSet` -- доменный объект из `core/domain/vlan.py` для сравнения множеств VLAN:

```
Пример:
  Устройство:  tagged_vlans = "10,20,30"      -> target  = VlanSet({10, 20, 30})
  NetBox:      tagged_vlans = [VLAN10, VLAN20] -> current = VlanSet({10, 20})

  current != target -> True
  target.added(current)   = {30}    (добавленные)
  target.removed(current) = set()   (удалённые)
  actual_changes: "tagged_vlans: +[30]"
```

Полный список check-хелперов:

| Хелпер | Поле | Особенности |
|--------|------|-------------|
| `_check_type` | `type` | auto-detect по имени/speed/media |
| `_check_description` | `description` | Пустая строка -- валидное значение |
| `_check_enabled` | `enabled` | Два режима: admin/link |
| `_check_mac` | MAC address | Отдельный endpoint, возвращает mac |
| `_check_mtu` | `mtu` | int сравнение |
| `_check_speed` | `speed` | Парсинг в kbps |
| `_check_duplex` | `duplex` | Нормализация full/half/auto |
| `_check_mode` | `mode` | access/tagged/tagged-all, очистка для shutdown |
| `_check_untagged_vlan` | `untagged_vlan` | Обратный кэш, N+1 защита |
| `_check_tagged_vlans` | `tagged_vlans` | VlanSet для сравнения множеств |
| `_check_lag` | `lag` | Поиск LAG интерфейса по имени |

---

### 4.4 Batch-операции создания -- двухфазная стратегия

```python
# Файл: netbox/sync/interfaces.py
def _batch_create_interfaces(
    self: SyncBase, device_id: int, to_create: list,
    sorted_interfaces: List[Interface], stats: dict, details: dict,
    site_name: Optional[str] = None,
) -> None:
    if not to_create:
        return

    # Разделяем на LAG и остальные интерфейсы
    lag_items = []
    member_items = []
    for item in to_create:
        intf = next((i for i in sorted_interfaces if i.name == item.name), None)
        if not intf:
            continue
        if intf.name.lower().startswith(("port-channel", "po")):
            lag_items.append((item, intf))
        else:
            member_items.append((item, intf))

    # Фаза 1: создаём LAG интерфейсы
    if lag_items:
        self._do_batch_create(device_id, lag_items, stats, details,
                               sorted_interfaces, site_name=site_name)

    # Фаза 2: создаём остальные интерфейсы (теперь LAG существуют в NetBox)
    if member_items:
        self._do_batch_create(device_id, member_items, stats, details,
                               sorted_interfaces, site_name=site_name)
```

### Что здесь происходит

Создание разделено на две фазы:

```
Фаза 1 (LAG):     [Po1, Po2]        -> bulk_create -> NetBox
                                        Po1.id = 100, Po2.id = 101

Фаза 2 (members): [Gi0/1, Gi0/2]   -> _build_create_data:
                                        Gi0/1: lag=Po1 -> data["lag"] = 100
                                        Gi0/2: lag=Po2 -> data["lag"] = 101
                                      -> bulk_create -> NetBox
```

Если создать member с `lag: Po1`, а Po1 ещё не существует -- NetBox вернёт ошибку.

#### `_do_batch_create()` -- реальное создание с MAC-очередью

```python
# Файл: netbox/sync/interfaces.py
def _do_batch_create(
    self: SyncBase, device_id: int, items: List[Tuple],
    stats: dict, details: dict,
    sorted_interfaces: List[Interface],
    site_name: Optional[str] = None,
) -> None:
    create_batch = []
    create_mac_queue = []  # (batch_index, mac_address) для post-create
    create_names = []

    for item, intf in items:
        data, mac = self._build_create_data(device_id, intf, site_name=site_name)
        if data:
            create_batch.append(data)
            create_names.append(item.name)
            if mac:
                create_mac_queue.append((len(create_batch) - 1, mac))

    if self.dry_run:
        for name in create_names:
            logger.info(f"[DRY-RUN] Создание интерфейса: {name}")
            stats["created"] += 1
            details["create"].append({"name": name})
        return

    try:
        created = self.client.bulk_create_interfaces(create_batch)
        for i, name in enumerate(create_names):
            stats["created"] += 1
            details["create"].append({"name": name})

        # Post-create: назначаем MAC (отдельный endpoint)
        for idx, mac in create_mac_queue:
            if idx < len(created):
                try:
                    self.client.assign_mac_to_interface(created[idx].id, mac)
                except Exception as e:
                    logger.warning(f"Ошибка назначения MAC {mac}: {e}")

    except Exception as e:
        logger.warning(f"Batch create не удался ({e}), fallback")
        for _item, intf in items:
            try:
                self._create_interface(device_id, intf)
                stats["created"] += 1
                details["create"].append({"name": intf.name})
            except Exception as exc:
                logger.error(f"Ошибка создания интерфейса {intf.name}: {exc}")
```

**MAC-очередь**: MAC назначается ПОСЛЕ создания интерфейса отдельным API-вызовом. `create_mac_queue` хранит пары `(индекс_в_batch, mac_адрес)`, чтобы после bulk_create привязать MAC к правильному интерфейсу по индексу.

---

### 4.5 Batch-обновление и удаление

```python
# Файл: netbox/sync/interfaces.py
def _batch_update_interfaces(
    self: SyncBase, to_update: list, sorted_interfaces: List[Interface],
    stats: dict, details: dict, site_name: Optional[str] = None,
) -> None:
    if not to_update:
        return

    update_batch = []     # (updates_with_id, name, changes)
    update_mac_queue = [] # (interface_id, mac_address, name)

    for item in to_update:
        intf = next((i for i in sorted_interfaces if i.name == item.name), None)
        if not intf or not item.remote_data:
            continue

        updates, actual_changes, mac = self._build_update_data(
            item.remote_data, intf, site_name=site_name
        )

        if not updates and not mac:
            stats["skipped"] += 1
            continue

        if updates:
            updates["id"] = item.remote_data.id
            update_batch.append((updates, item.name, actual_changes))
        if mac:
            update_mac_queue.append((item.remote_data.id, mac, item.name))

    # Batch update field changes
    if update_batch:
        batch_data = [upd for upd, _, _ in update_batch]
        try:
            self.client.bulk_update_interfaces(batch_data)
            for _, name, changes in update_batch:
                stats["updated"] += 1
                details["update"].append({"name": name, "changes": changes})
        except Exception as e:
            logger.warning(f"Batch update не удался ({e}), fallback")
            for upd, name, changes in update_batch:
                intf_id = upd.pop("id")
                try:
                    self.client.update_interface(intf_id, **upd)
                    stats["updated"] += 1
                    details["update"].append({"name": name, "changes": changes})
                except Exception as exc:
                    logger.error(f"Ошибка обновления интерфейса {name}: {exc}")

    # Post-update: назначаем MAC
    for intf_id, mac, name in update_mac_queue:
        try:
            self.client.assign_mac_to_interface(intf_id, mac)
        except Exception as e:
            logger.warning(f"Ошибка назначения MAC {mac} на {name}: {e}")
```

### Что здесь происходит

Для bulk update каждый dict должен содержать `"id"`:

```python
# batch_data для bulk_update_interfaces:
[
    {"id": 101, "description": "New desc", "enabled": False},
    {"id": 102, "speed": 1000000},
    {"id": 103, "mode": "access", "untagged_vlan": 17},
]
```

При fallback `upd.pop("id")` извлекает ID из словаря (и удаляет его), потому что `update_interface(intf_id, **upd)` принимает ID отдельным аргументом.

### 4.6 Post-sync MAC: `_post_sync_mac_check()`

**Проблема:** MAC не входит в `compare_fields` компаратора (description, enabled, mode, mtu, duplex, speed). Если все поля совпали — интерфейс попадает в `to_skip` и `_check_mac()` никогда не вызывается. MAC, не назначенный при создании, остаётся пустым навсегда.

**Решение:** Пост-обработка MAC после `_batch_update_interfaces()`:

```python
# Файл: netbox/sync/interfaces.py
def _post_sync_mac_check(
    self: SyncBase, to_skip: list, sorted_interfaces: List[Interface],
    stats: dict, details: dict,
) -> int:
    """Проверяет и назначает MAC для пропущенных интерфейсов."""
    sync_cfg = get_sync_config("interfaces")
    if not sync_cfg.is_field_enabled("mac_address"):
        return 0

    mac_queue = []
    for item in to_skip:
        intf = next((i for i in sorted_interfaces if i.name == item.name), None)
        if not intf or not intf.mac:
            continue
        # Проверяем sync_mac_only_with_ip
        if sync_cfg.get_option("sync_mac_only_with_ip", False) and not intf.ip_address:
            continue
        new_mac = normalize_mac_netbox(intf.mac)
        current_mac = self.client.get_interface_mac(item.remote_data.id)
        if new_mac.upper() != (current_mac or "").upper():
            mac_queue.append((item.remote_data.id, new_mac, item.name))

    # Batch назначение через bulk_assign_macs()
    if mac_queue:
        self.client.bulk_assign_macs([(id, mac) for id, mac, _ in mac_queue])
    return len(mac_queue)
```

**Когда это нужно:** Интерфейс был создан без MAC (не было IP → `sync_mac_only_with_ip` заблокировал). Позже IP появился, но при повторном sync все поля совпадают → `to_skip`. Без `_post_sync_mac_check()` MAC не назначится никогда.

**Вызов в `sync_interfaces()`:**
```python
# После _batch_update_interfaces() и перед _batch_delete_interfaces():
mac_assigned = self._post_sync_mac_check(diff.to_skip, sorted_interfaces, stats, details)
stats["skipped"] += len(diff.to_skip) - mac_assigned
```

---

Удаление использует `_batch_with_fallback` из SyncBase:

```python
# Файл: netbox/sync/interfaces.py
def _batch_delete_interfaces(self: SyncBase, to_delete: list,
                              stats: dict, details: dict) -> None:
    if not to_delete:
        return

    if self.dry_run:
        for item in to_delete:
            stats["deleted"] += 1
            details["delete"].append({"name": item.name})
        return

    delete_ids = []
    delete_names = []
    for item in to_delete:
        if item.remote_data:
            delete_ids.append(item.remote_data.id)
            delete_names.append(item.name)

    self._batch_with_fallback(
        batch_data=delete_ids,
        item_names=delete_names,
        bulk_fn=self.client.bulk_delete_interfaces,
        fallback_fn=lambda item_id, name:
            self.client.api.dcim.interfaces.get(item_id).delete(),
        stats=stats, details=details,
        operation="deleted", entity_name="интерфейс",
    )
```

---

## 5. CablesSyncMixin

### 5.1 `sync_cables_from_lldp()` -- создание кабелей

```python
# Файл: netbox/sync/cables.py
def sync_cables_from_lldp(
    self: SyncBase,
    lldp_data: List[LLDPNeighbor],
    skip_unknown: bool = True,
    cleanup: bool = False,
) -> Dict[str, int]:
    ss = SyncStats("created", "deleted", "skipped", "failed", "already_exists")
    stats, details = ss.stats, ss.details
    seen_cables = set()  # Дедупликация

    neighbors = LLDPNeighbor.ensure_list(lldp_data)

    for entry in neighbors:
        local_device = entry.hostname
        local_intf = entry.local_interface
        remote_hostname = entry.remote_hostname
        remote_port = entry.remote_port
        neighbor_type = entry.neighbor_type or "unknown"

        # 1. Пропуск unknown
        if neighbor_type == "unknown" and skip_unknown:
            stats["skipped"] += 1
            continue

        # 2. Поиск локального устройства и интерфейса
        local_device_obj = self._find_device(local_device)
        local_intf_obj = self._find_interface(local_device_obj.id, local_intf)

        # 3. Поиск удалённого устройства (4 стратегии)
        remote_device_obj = self._find_neighbor_device(entry)

        # 4. Поиск удалённого интерфейса
        remote_intf_obj = self._find_interface(remote_device_obj.id, remote_port)

        # 5. Пропуск LAG интерфейсов (кабели идут на физические порты)
        local_intf_type = getattr(local_intf_obj.type, 'value', None) \
            if local_intf_obj.type else None
        if local_intf_type == "lag" or remote_intf_type == "lag":
            stats["skipped"] += 1
            continue

        # 6. Создание кабеля
        result = self._create_cable(local_intf_obj, remote_intf_obj)

        # 7. Дедупликация
        if result == "created":
            cable_key = tuple(sorted([
                f"{local_device_obj.name}:{local_intf}",
                f"{remote_device_obj.name}:{remote_port}",
            ]))
            if cable_key not in seen_cables:
                seen_cables.add(cable_key)
                stats["created"] += 1
```

### 5.2 Четыре стратегии поиска соседа

```python
# Файл: netbox/sync/cables.py
def _find_neighbor_device(self: SyncBase, entry: LLDPNeighbor) -> Optional[Any]:
    hostname = entry.remote_hostname or ""
    mac = entry.remote_mac
    ip = entry.remote_ip
    neighbor_type = entry.neighbor_type or "unknown"

    if neighbor_type == "hostname":
        # Стратегия: hostname -> IP -> MAC
        clean_hostname = hostname.split(".")[0] if "." in hostname else hostname
        device = self._find_device(clean_hostname)
        if device:
            return device
        if ip:
            device = self.client.get_device_by_ip(ip)
            if device:
                return device
        if mac:
            device = self._find_device_by_mac(mac)
            if device:
                return device

    elif neighbor_type == "mac":
        # Стратегия: MAC -> IP
        if mac:
            device = self._find_device_by_mac(mac)
            if device:
                return device
        if ip:
            device = self.client.get_device_by_ip(ip)
            if device:
                return device

    elif neighbor_type == "ip":
        # Стратегия: IP -> MAC
        if ip:
            device = self.client.get_device_by_ip(ip)
            if device:
                return device
        if mac:
            device = self._find_device_by_mac(mac)
            if device:
                return device

    else:  # unknown -- пробуем всё подряд
        if ip:
            device = self.client.get_device_by_ip(ip)
            if device:
                return device
        if mac:
            device = self._find_device_by_mac(mac)
            if device:
                return device

    return None
```

### Что здесь происходит

LLDP/CDP соседи приходят с разным типом идентификации. `neighbor_type` определяет первичный идентификатор, остальные используются как fallback. Hostname обрезается от домена: `switch2.mylab.local` -> `switch2`.

### 5.3 Дедупликация и создание кабеля

LLDP видит один физический кабель с двух сторон. Без дедупликации кабель создался бы дважды:

```
Switch-A:Gi0/1 -> видит Switch-B:Gi0/1  ->  кабель A:Gi0/1 <-> B:Gi0/1
Switch-B:Gi0/1 -> видит Switch-A:Gi0/1  ->  тот же кабель!

Sorted tuple: ("Switch-A:Gi0/1", "Switch-B:Gi0/1") -- одинаковый ключ для обоих
```

Создание кабеля в NetBox 4.x использует формат A/B termination:

```python
# Файл: netbox/sync/cables.py
def _create_cable(self: SyncBase, interface_a, interface_b) -> str:
    if interface_a.cable or interface_b.cable:
        return "exists"

    if self.dry_run:
        return "created"

    try:
        self.client.api.dcim.cables.create({
            "a_terminations": [{
                "object_type": "dcim.interface",
                "object_id": interface_a.id,
            }],
            "b_terminations": [{
                "object_type": "dcim.interface",
                "object_id": interface_b.id,
            }],
            "status": "connected",
        })
        return "created"
    except NetBoxError as e:
        return "error"
```

> **Python-концепция: tuple как элемент set**
> `tuple(sorted([...]))` создаёт неизменяемый (hashable) кортеж, который можно хранить в `set`. Сортировка гарантирует, что `("A:Gi0/1", "B:Gi0/2")` и `("B:Gi0/2", "A:Gi0/1")` дадут одинаковый кортеж.

---

## 6. DevicesSyncMixin

### 6.1 `create_device()` -- создание устройства с цепочкой get-or-create

```python
# Файл: netbox/sync/devices.py
def create_device(
    self: SyncBase,
    name: str, device_type: str,
    site: Optional[str] = None, role: Optional[str] = None,
    manufacturer: Optional[str] = None, serial: str = "",
    status: Optional[str] = None, platform: str = "",
    tenant: Optional[str] = None,
) -> Optional[Any]:
    sync_cfg = get_sync_config("devices")

    # Defaults из fields.yaml
    if site is None:
        site = sync_cfg.get_default("site", "Main")
    if role is None:
        role = sync_cfg.get_default("role", "switch")
    if manufacturer is None:
        manufacturer = sync_cfg.get_default("manufacturer", "Cisco")

    existing = self.client.get_device_by_name(name)
    if existing:
        return existing

    try:
        mfr = self._get_or_create_manufacturer(manufacturer)
        dtype = self._get_or_create_device_type(device_type, mfr.id)
        site_obj = self._get_or_create_site(site)
        role_obj = self._get_or_create_role(role)

        device_data = {
            "name": name,
            "device_type": dtype.id,
            "site": site_obj.id,
            "role": role_obj.id,
            "status": status,
        }
        if serial:
            device_data["serial"] = serial
        if tenant:
            tenant_obj = self._get_or_create_tenant(tenant)
            if tenant_obj:
                device_data["tenant"] = tenant_obj.id

        device = self.client.api.dcim.devices.create(device_data)
        return device
    except NetBoxError as e:
        logger.error(f"Ошибка: {format_error_for_log(e)}")
        return None
```

### Что здесь происходит

Перед созданием устройства нужно обеспечить существование всех связанных объектов:

```
Manufacturer ("Cisco") --> get_or_create --> id=1
                                              |
DeviceType ("C2960X-48") --> get_or_create(manufacturer=1) --> id=5
                                                                 |
Site ("Main") --> get_or_create --> id=2                         |
                                     |                           |
Role ("switch") --> get_or_create --> id=3                      |
                                       |                        |
                      devices.create(name, device_type=5, site=2, role=3)
```

### 6.2 `sync_devices_from_inventory()` -- массовая синхронизация

Метод обрабатывает массив устройств из инвентаря. Для каждого:
1. Ищет по имени, fallback по IP
2. Если найдено и `update_existing` -- вызывает `_update_device()` (сравниваем serial, model, platform, tenant, site, role)
3. Если не найдено -- вызывает `create_device()`
4. Per-device site: каждое устройство может иметь свой сайт (`entry.site`), с fallback на default
5. Если `cleanup` и `tenant` -- удаляет устройства, которых нет в инвентаре (только для данного tenant)

---

## 7. IPAddressesSyncMixin

### 7.1 `sync_ip_addresses()` -- синхронизация IP

```python
# Файл: netbox/sync/ip_addresses.py
def sync_ip_addresses(
    self: SyncBase,
    device_name: str,
    ip_data: List[IPAddressEntry],
    device_ip: Optional[str] = None,
    update_existing: bool = False,
    cleanup: bool = False,
) -> Dict[str, int]:
    device = self.client.get_device_by_name(device_name)

    interfaces = {
        intf.name: intf for intf in self.client.get_interfaces(device_id=device.id)
    }
    existing_ips = list(self.client.get_ip_addresses(device_id=device.id))
    entries = IPAddressEntry.ensure_list(ip_data)

    comparator = SyncComparator()
    local_data = [entry.to_dict() for entry in entries if entry.ip_address]
    diff = comparator.compare_ip_addresses(
        local=local_data, remote=existing_ips,
        create_missing=True, update_existing=update_existing, cleanup=cleanup,
    )

    # Batch create
    self._batch_create_ip_addresses(device, diff.to_create, entries, interfaces,
                                     stats, details)

    # Update -- поштучно (может требоваться пересоздание IP при смене маски)
    for item in diff.to_update:
        entry = next((e for e in entries if e.ip_address.split("/")[0] == item.name), None)
        if entry and item.remote_data:
            intf = self._find_interface(device.id, entry.interface)
            if intf:
                self._update_ip_address(item.remote_data, device, intf, entry, item.changes)

    # Batch delete
    self._batch_delete_ip_addresses(diff.to_delete, stats, details)

    # Primary IP
    if device_ip:
        self._set_primary_ip(device, device_ip)
```

### 7.2 Пересоздание IP при смене маски

```python
# Файл: netbox/sync/ip_addresses.py
def _update_ip_address(self: SyncBase, ip_obj, device, interface,
                       entry=None, changes=None) -> bool:
    prefix_change = next((c for c in changes if c.field == "prefix_length"), None)
    if prefix_change and entry:
        # NetBox не позволяет изменить маску напрямую -- пересоздаём
        ip_obj.delete()
        new_ip = self.client.api.ipam.ip_addresses.create({
            "address": entry.with_prefix,     # "10.0.0.1/24"
            "status": "active",
            "assigned_object_type": "dcim.interface",
            "assigned_object_id": interface.id,
        })
        return True
```

Это важная особенность: NetBox не позволяет изменить prefix/маску IP-адреса через update API. Единственный способ -- удалить и создать заново.

### 7.3 `_set_primary_ip()` -- установка primary IP

```python
# Файл: netbox/sync/ip_addresses.py
def _set_primary_ip(self: SyncBase, device, ip_address: str) -> bool:
    ip_only = ip_address.split("/")[0]

    # Проверяем текущий primary
    if device.primary_ip4:
        current_ip = str(device.primary_ip4.address).split("/")[0]
        if current_ip == ip_only:
            return False  # Уже установлен

    # Ищем IP на интерфейсах устройства
    ip_obj = None
    device_ips = list(self.client.get_ip_addresses(device_id=device.id))
    for ip in device_ips:
        if str(ip.address).split("/")[0] == ip_only:
            ip_obj = ip
            break

    # Если не найден -- создаём и привязываем к management интерфейсу
    if not ip_obj:
        mgmt_interface = self._find_management_interface(device.id, ip_only)
        ip_data = {"address": ip_with_mask}
        if mgmt_interface:
            ip_data["assigned_object_type"] = "dcim.interface"
            ip_data["assigned_object_id"] = mgmt_interface.id
        ip_obj = self.client.api.ipam.ip_addresses.create(ip_data)

    # Устанавливаем primary
    device.primary_ip4 = ip_obj.id
    device.save()
    return True
```

`_find_management_interface()` ищет интерфейс для привязки IP в порядке приоритета: интерфейс с этим IP, Management1/0, Mgmt0, VLAN-интерфейсы (не Vlan1).

---

## 8. VLANsSyncMixin

```python
# Файл: netbox/sync/vlans.py
def sync_vlans_from_interfaces(
    self: SyncBase,
    device_name: str,
    interfaces: List[Interface],
    site: Optional[str] = None,
) -> Dict[str, int]:
    ss = SyncStats("created", "skipped", "failed")
    stats, details = ss.stats, ss.details

    vlan_pattern = re.compile(r"^[Vv]lan(\d+)$")
    interface_models = Interface.ensure_list(interfaces)

    vlans_to_create = {}
    for intf in interface_models:
        match = vlan_pattern.match(intf.name)
        if match:
            vid = int(match.group(1))
            description = intf.description.strip() if intf.description else ""
            vlan_name = description if description else f"VLAN {vid}"
            vlans_to_create[vid] = vlan_name

    for vid, name in vlans_to_create.items():
        existing = self.client.get_vlan_by_vid(vid, site=site)
        if existing:
            stats["skipped"] += 1
            continue

        self.client.create_vlan(vid=vid, name=name, site=site, status="active")
        stats["created"] += 1
```

### Что здесь происходит

VLAN создаются из SVI-интерфейсов (Switch Virtual Interface):

```
Интерфейсы: [Gi0/1, Vlan10 (desc="Servers"), Vlan20 (desc=""), Gi0/2]
                       |                          |
                  vid=10, name="Servers"      vid=20, name="VLAN 20"
```

Имя VLAN берётся из description SVI-интерфейса. Если пустое -- генерируется `"VLAN {vid}"`. VLAN привязываются к сайту (site-scoped) -- на разных сайтах может быть VLAN с одинаковым VID, но разными именами.

---

## 9. InventorySyncMixin

```python
# Файл: netbox/sync/inventory.py
def sync_inventory(
    self: SyncBase,
    device_name: str,
    inventory_data: List[InventoryItem],
    cleanup: bool = False,
) -> Dict[str, int]:
    device = self._find_device(device_name)
    items = InventoryItem.ensure_list(inventory_data) if inventory_data else []

    # Один GET запрос на все existing items (решение N+1)
    existing_items = {}
    for nb_item in self.client.get_inventory_items(device_id=device.id):
        existing_items[nb_item.name] = nb_item

    processed_names = set()
    create_batch = []
    update_batch = []

    for item in items:
        name = item.name.strip() if item.name else ""
        serial = item.serial.strip() if item.serial else ""

        if not name:
            continue

        # NetBox ограничивает name до 64 символов
        if len(name) > 64:
            name = name[:61] + "..."

        processed_names.add(name)

        # Без серийного номера -- пропускаем
        if not serial:
            stats["skipped"] += 1
            continue

        existing = existing_items.get(name)
        if existing:
            # Проверяем обновления (part_id, serial, description, manufacturer)
            ...
            if needs_update:
                update_batch.append((existing.id, updates, name, changes, truncate_note))
        else:
            # Новый item -- резолвим manufacturer ID заранее для bulk create
            kwargs = {"device": device.id, "name": name, "discovered": True}
            if manufacturer:
                mfr = self.client.api.dcim.manufacturers.get(slug=manufacturer.lower())
                if not mfr:
                    mfr = self.client.api.dcim.manufacturers.get(name=manufacturer)
                if mfr:
                    kwargs["manufacturer"] = mfr.id
            create_batch.append((kwargs, name, truncate_note))

    # Batch create
    if create_batch:
        self._batch_with_fallback(
            batch_data=[data for data, _, _ in create_batch],
            item_names=[f"{name}{tn}" for _, name, tn in create_batch],
            bulk_fn=self.client.bulk_create_inventory_items,
            fallback_fn=lambda data, name:
                self.client.api.dcim.inventory_items.create(data),
            stats=stats, details=details,
            operation="created", entity_name="inventory",
        )

    # Batch delete (cleanup)
    if cleanup:
        delete_ids = []
        delete_names = []
        for nb_name, nb_item in existing_items.items():
            if nb_name not in processed_names:
                delete_ids.append(nb_item.id)
                delete_names.append(nb_name)
        if delete_ids:
            self._batch_with_fallback(
                batch_data=delete_ids,
                item_names=delete_names,
                bulk_fn=self.client.bulk_delete_inventory_items,
                fallback_fn=lambda item_id, name:
                    self.client.delete_inventory_item(item_id),
                stats=stats, details=details,
                operation="deleted", entity_name="inventory",
            )
```

### Что здесь происходит

Ключевые особенности inventory sync:

1. **64-символьный лимит** -- NetBox ограничивает поле `name` до 64 символов. Длинные имена модулей обрезаются: `name[:61] + "..."`.

2. **Пропуск без серийного номера** -- items без serial не несут полезной информации для отслеживания оборудования.

3. **Один GET на все items** -- `existing_items` загружается одним запросом, а не N запросами в цикле.

4. **Manufacturer резолвинг** -- для bulk create нужен ID производителя, он ищется заранее: по slug, fallback по name.

5. **Batch create/update/delete** -- через `_batch_with_fallback` из SyncBase, единый паттерн для всех сущностей.

---

## 10. NetBoxClient -- API-обертка

### 10.1 Mixin-структура клиента

```python
# Файл: netbox/client/main.py
class NetBoxClient(
    DevicesMixin,       # get_devices, get_device_by_name, get_device_by_ip, get_device_by_mac
    InterfacesMixin,    # get_interfaces, create_interface, bulk_create/update/delete_interfaces
    IPAddressesMixin,   # get_ip_addresses, bulk_create/delete_ip_addresses, get_cables
    VLANsMixin,         # get_vlans, get_vlan_by_vid, create_vlan
    InventoryMixin,     # get_inventory_items, bulk_create/update/delete_inventory_items
    DCIMMixin,          # device types, manufacturers, roles, sites, platforms
    NetBoxClientBase,   # __init__(url, token), self.api = pynetbox.api(...)
):
    pass
```

### Что здесь происходит

Клиент -- **зеркальная копия** паттерна `NetBoxSync`: пустой класс, собранный из mixins. `NetBoxClientBase` инициализирует pynetbox:

```python
# Файл: netbox/client/base.py
class NetBoxClientBase:
    def __init__(self, url=None, token=None, ssl_verify=True):
        self.url = url or os.environ.get("NETBOX_URL")
        self._token = get_netbox_token(config_token=token)
        self.api = pynetbox.api(self.url, token=self._token)
```

### 10.2 Bulk-операции в клиенте

```python
# Файл: netbox/client/interfaces.py
def bulk_create_interfaces(self, interfaces_data: List[dict]) -> List[Any]:
    if not interfaces_data:
        return []
    result = self.api.dcim.interfaces.create(interfaces_data)
    created = result if isinstance(result, list) else [result]
    return created

def bulk_update_interfaces(self, updates: List[dict]) -> List[Any]:
    if not updates:
        return []
    result = self.api.dcim.interfaces.update(updates)
    updated = result if isinstance(result, list) else [result]
    return updated

def bulk_delete_interfaces(self, ids: List[int]) -> bool:
    if not ids:
        return True
    # pynetbox 7.5+ принимает список int ID напрямую
    self.api.dcim.interfaces.delete(ids)
    return True
```

### Что здесь происходит

Pynetbox поддерживает bulk-операции нативно:
- `endpoint.create([dict1, dict2, ...])` -- создаёт список объектов одним POST
- `endpoint.update([{id: 1, ...}, {id: 2, ...}])` -- обновляет одним PATCH
- `endpoint.delete([id1, id2, ...])` -- удаляет одним DELETE

Обработка `result if isinstance(result, list) else [result]` нужна, потому что pynetbox при создании одного объекта возвращает объект, а при нескольких -- список. Мы нормализуем в список.

Аналогичные bulk методы есть для всех сущностей:
- `bulk_create_ip_addresses` / `bulk_delete_ip_addresses`
- `bulk_create_inventory_items` / `bulk_update_inventory_items` / `bulk_delete_inventory_items`

---

## 11. Итог -- полная цепочка sync

Полная цепочка вызовов для `sync_interfaces`:

```
sync_interfaces("switch-01", interfaces)
  |
  +-- SyncStats("created", "updated", "deleted", "skipped")
  +-- get_sync_config("interfaces")          <-- fields.yaml
  +-- client.get_device_by_name("switch-01") <-- 1 GET
  +-- _get_vlan_by_vid(1, site)              <-- 1 GET (все VLAN сайта в кэш)
  +-- client.get_interfaces(device_id=42)    <-- 1 GET
  |
  +-- sorted(interfaces, key=port_type=="lag") <-- LAG первыми
  |
  +-- for intf in sorted_interfaces:
  |     data = intf.to_dict()
  |     data["type"] = get_netbox_interface_type(intf)
  |     data["speed"] = _parse_speed(intf.speed)
  |
  +-- SyncComparator().compare_interfaces(local, remote)
  |     +-- forward pass: match by name
  |     +-- backward pass: detect deleted
  |     -> SyncDiff(to_create=3, to_update=2, to_delete=1, to_skip=44)
  |
  +-- _batch_create_interfaces()
  |     +-- Фаза 1: LAG -> bulk_create([lag_data])             <-- 1 POST
  |     +-- Фаза 2: members -> bulk_create([data...])          <-- 1 POST
  |           +-- post-create: assign_mac_to_interface()        <-- N POST
  |
  +-- _batch_update_interfaces()
  |     +-- for item in to_update:
  |     |     _build_update_data(nb_intf, local_intf)
  |     |       +-- _check_type()
  |     |       +-- _check_description()
  |     |       +-- _check_enabled()
  |     |       +-- _check_mac()
  |     |       +-- _check_mtu()
  |     |       +-- _check_speed()
  |     |       +-- _check_duplex()
  |     |       +-- _check_mode()
  |     |       +-- _check_untagged_vlan()
  |     |       +-- _check_tagged_vlans()
  |     |       +-- _check_lag()
  |     +-- bulk_update([{id:1, ...}, ...])                     <-- 1 PATCH
  |
  +-- _post_sync_mac_check()                                    <-- NEW
  |     +-- for item in to_skip:
  |     |     проверяем: mac_address enabled, intf.mac, sync_mac_only_with_ip
  |     |     сравниваем: new_mac vs get_interface_mac()
  |     +-- bulk_assign_macs([(id, mac), ...])                  <-- N POST
  |
  +-- _batch_delete_interfaces()
        +-- bulk_delete([id1, id2, ...])                        <-- 1 DELETE
```

**Количество API-запросов для типичного sync (50 интерфейсов, 3 новых, 2 обновления, 1 удаление):**
- **3 GET** (device, VLANs, interfaces) вместо 50+ без кэширования
- **2-3 POST** (LAG create + member create + MAC assign)
- **1 PATCH** (bulk update)
- **1 DELETE** (bulk delete)
- **~7 запросов** вместо ~150 без batch и кэшей

Ключевые архитектурные решения:

1. **Mixin-архитектура** -- каждый домен (interfaces, cables, IPs) живёт в своём файле, но все используют общие хелперы из `SyncBase`

2. **Domain layer** (`SyncComparator`) -- чистое сравнение без API-вызовов. Можно тестировать без NetBox

3. **Build data / check helpers** -- подготовка данных отделена от API-вызовов. `_build_create_data()` и `_check_*()` не делают POST/PATCH

4. **Batch с fallback** -- один API-вызов на операцию, с автоматическим переключением на поштучную обработку при ошибке

5. **Кэши** -- 5 кэшей решают проблему N+1 запросов. Все загрузки -- "один GET на всю коллекцию", а не "один GET на элемент"

6. **dry_run** -- пронизывает весь код. Каждая операция проверяет `self.dry_run` и логирует `[DRY-RUN]` вместо API-вызова

---

> **Дальнейшее чтение:**
> - [05_SYNC_NETBOX.md](05_SYNC_NETBOX.md) -- обзорный документ по sync (начальный уровень)
> - [09_MIXINS_PATTERNS.md](09_MIXINS_PATTERNS.md) -- детальный разбор паттерна mixin
> - [07_DATA_FLOWS.md](07_DATA_FLOWS.md) -- потоки данных LLDP, MAC, interfaces
