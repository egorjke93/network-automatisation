# 05. Синхронизация с NetBox

Как Network Collector сравнивает данные с устройств с данными в NetBox
и приводит их в соответствие. Самая сложная часть проекта -- разберём пошагово.

---

## 1. Что такое синхронизация

Синхронизация -- это процесс сравнения **того что есть на устройстве**
с **тем что записано в NetBox**, и приведения NetBox в актуальное состояние.

### Четыре варианта

```
Устройство               NetBox                  Действие
─────────────────────────────────────────────────────────────
GigabitEthernet0/1       (нет)                → CREATE  (создать в NetBox)
GigabitEthernet0/2       GigabitEthernet0/2   → UPDATE  (описание изменилось)
(нет)                    GigabitEthernet0/3   → DELETE  (если cleanup включён)
GigabitEthernet0/4       GigabitEthernet0/4   → SKIP    (всё совпадает)
```

Важно: мы **только читаем** с устройств и **записываем** в NetBox.
Никаких изменений конфигурации на сетевом оборудовании не происходит.

### CLI команда

```bash
# Посмотреть что будет изменено (ничего не меняет)
python -m network_collector sync-netbox --interfaces --dry-run

# Синхронизировать всё (интерфейсы, IP, inventory, кабели)
python -m network_collector sync-netbox --sync-all --site "Office"

# Только интерфейсы конкретного устройства
python -m network_collector sync-netbox --interfaces --device "switch-01"
```

---

## 2. Архитектура sync

Синхронизация разделена на два слоя: **Client** (HTTP-запросы) и **Sync** (логика).

```
NetBoxClient (HTTP-клиент)           NetBoxSync (бизнес-логика)
─────────────────────────────        ────────────────────────────────
get_interfaces()                     sync_interfaces()
bulk_create_interfaces([...])        sync_cables_from_lldp()
bulk_update_interfaces([...])        sync_ip_addresses()
bulk_delete_interfaces([...])        sync_inventory()
get_device_by_name()                 sync_devices_from_inventory()
get_vlans()                          sync_vlans_from_interfaces()
```

**Client** (`netbox/client/`) -- умеет отправлять HTTP-запросы к NetBox API.
Ничего не знает о бизнес-логике. Методы типа "получи список интерфейсов",
"создай интерфейс", "обнови интерфейс".

**Sync** (`netbox/sync/`) -- решает **что** отправлять. Сравнивает данные,
определяет что создать/обновить/удалить, вызывает методы Client.

### Файлы Client

| Файл | Описание |
|------|----------|
| `netbox/client/main.py` | Главный класс NetBoxClient (объединяет mixin-ы) |
| `netbox/client/interfaces.py` | get_interfaces, bulk_create/update/delete_interfaces |
| `netbox/client/ip_addresses.py` | get_ip_addresses, bulk_create/update/delete |
| `netbox/client/inventory.py` | get_inventory_items, bulk_create/update/delete |
| `netbox/client/devices.py` | get_device_by_name, get_device_by_ip |
| `netbox/client/vlans.py` | get_vlans |

### Файлы Sync

| Файл | Описание |
|------|----------|
| `netbox/sync/main.py` | Главный класс NetBoxSync (объединяет mixin-ы) |
| `netbox/sync/base.py` | SyncBase: кэши, _find_device, _batch_with_fallback |
| `netbox/sync/interfaces.py` | sync_interfaces, _build_create/update_data |
| `netbox/sync/ip_addresses.py` | sync_ip_addresses |
| `netbox/sync/cables.py` | sync_cables_from_lldp |
| `netbox/sync/inventory.py` | sync_inventory |
| `netbox/sync/devices.py` | sync_devices_from_inventory, create_device |
| `netbox/sync/vlans.py` | sync_vlans_from_interfaces |

---

## 3. SyncComparator -- сердце сравнения

**Файл:** `core/domain/sync.py`

SyncComparator -- это **чистая логика сравнения**. Он не знает про NetBox, HTTP,
SSH. Он принимает два списка (локальные данные и удалённые) и возвращает diff:
что создать, обновить, удалить, пропустить.

### Использование

```python
from network_collector.core.domain.sync import SyncComparator

comparator = SyncComparator()

# local = данные с устройства (после нормализации)
# remote = данные из NetBox (объекты pynetbox)
diff = comparator.compare_interfaces(
    local=collected_interfaces,    # List[Dict] -- данные с устройства
    remote=netbox_interfaces,      # List[NetBox objects] -- данные из NetBox
    exclude_patterns=["Vlan1"],    # Пропустить эти интерфейсы
    cleanup=True,                  # Помечать лишние для удаления
)

# Результат -- SyncDiff
print(f"Создать: {len(diff.to_create)}")   # Чего нет в NetBox
print(f"Обновить: {len(diff.to_update)}")  # Что изменилось
print(f"Удалить: {len(diff.to_delete)}")   # Что лишнее в NetBox
print(f"Пропустить: {len(diff.to_skip)}")  # Что совпадает
```

### SyncDiff -- результат сравнения

```python
@dataclass
class SyncDiff:
    object_type: str              # "interfaces", "ip_addresses", "cables"
    to_create: List[SyncItem]     # Объекты для создания
    to_update: List[SyncItem]     # Объекты для обновления
    to_delete: List[SyncItem]     # Объекты для удаления
    to_skip: List[SyncItem]       # Без изменений или исключены
```

Каждый `SyncItem` содержит:

```python
@dataclass
class SyncItem:
    name: str                     # Имя (GigabitEthernet0/1, 10.0.0.1, ...)
    change_type: ChangeType       # CREATE / UPDATE / DELETE / SKIP
    local_data: Dict              # Данные с устройства
    remote_data: Any              # Объект из NetBox (для update/delete)
    changes: List[FieldChange]    # Список изменённых полей (для update)
    reason: str                   # Причина пропуска (для skip)
```

### Пример: что внутри SyncItem для UPDATE

```python
SyncItem(
    name="GigabitEthernet0/1",
    change_type=ChangeType.UPDATE,
    local_data={"name": "GigabitEthernet0/1", "description": "К серверу DB-01", ...},
    remote_data=<NetBox interface object>,
    changes=[
        FieldChange(field="description", old_value="Старое описание", new_value="К серверу DB-01"),
        FieldChange(field="enabled", old_value=False, new_value=True),
    ],
)
```

### Какие поля сравниваются?

Для интерфейсов по умолчанию: `description`, `enabled`, `mode`, `mtu`, `duplex`, `speed`.
Если включён `sync_vlans: true` в `fields.yaml`, добавляются: `untagged_vlan`, `tagged_vlans`.

```python
compare_fields = ["description", "enabled", "mode", "mtu", "duplex", "speed"]
if sync_vlans:
    compare_fields.extend(["untagged_vlan", "tagged_vlans"])
```

### Три метода сравнения

SyncComparator умеет сравнивать три типа объектов:

```python
# Интерфейсы -- по имени (GigabitEthernet0/1)
diff = comparator.compare_interfaces(local, remote)

# IP-адреса -- по IP без маски (10.0.0.1)
diff = comparator.compare_ip_addresses(local, remote)

# Кабели -- по паре endpoints (switch-01:Gi0/1 <-> switch-02:Gi0/1)
diff = comparator.compare_cables(local, remote)
```

---

## 4. Batch API -- зачем

### Проблема: 48 интерфейсов = 48 HTTP-запросов

```
БЫЛО (медленно):
  POST /api/dcim/interfaces/ {name: "Gi0/1", ...}     → 1 запрос
  POST /api/dcim/interfaces/ {name: "Gi0/2", ...}     → 1 запрос
  POST /api/dcim/interfaces/ {name: "Gi0/3", ...}     → 1 запрос
  ...
  POST /api/dcim/interfaces/ {name: "Gi0/48", ...}    → 1 запрос
  Итого: 48 запросов, ~50 мс каждый = 2.4 секунды

СТАЛО (быстро):
  POST /api/dcim/interfaces/ [
    {name: "Gi0/1", ...},
    {name: "Gi0/2", ...},
    ...
    {name: "Gi0/48", ...},
  ]
  → 1 запрос = ~100 мс
```

NetBox API поддерживает bulk-операции: отправить массив объектов одним POST-запросом.
Вместо 48 запросов -- один.

### Реализация в Client

**Файл:** `netbox/client/interfaces.py`

```python
class InterfacesMixin:
    def bulk_create_interfaces(self, interfaces_data: List[dict]) -> List[Any]:
        """Создаёт несколько интерфейсов одним API-вызовом."""
        result = self.api.dcim.interfaces.create(interfaces_data)
        return result if isinstance(result, list) else [result]

    def bulk_update_interfaces(self, updates: List[dict]) -> List[Any]:
        """Обновляет несколько интерфейсов. Каждый dict содержит 'id'."""
        result = self.api.dcim.interfaces.update(updates)
        return result if isinstance(result, list) else [result]

    def bulk_delete_interfaces(self, ids: List[int]) -> bool:
        """Удаляет интерфейсы по списку ID."""
        self.api.dcim.interfaces.delete(ids)
        return True
```

### Fallback: если bulk упал -- по одному

Не все данные проходят bulk-валидацию. Если один интерфейс из 48 имеет ошибку,
весь bulk-запрос отклоняется. Поэтому реализован автоматический fallback:

```python
# netbox/sync/base.py -- _batch_with_fallback()
try:
    # Пробуем batch: 1 запрос на все 48 интерфейсов
    result = bulk_fn(batch_data)
    for name in item_names:
        stats["created"] += 1
except Exception as e:
    # Batch упал -- fallback на поштучную обработку
    logger.warning(f"Batch не удался ({e}), fallback на поштучную обработку")
    for data, name in zip(batch_data, item_names):
        try:
            fallback_fn(data, name)
            stats["created"] += 1
        except Exception as exc:
            logger.error(f"Ошибка создания {name}: {exc}")
            stats["failed"] += 1
```

Результат:
- **Обычно** -- 1 запрос на все объекты (быстро)
- **Если ошибка** -- по одному (медленнее, но не теряем остальные объекты)

---

## 5. Кэширование -- зачем и как

### Проблема без кэша

При синхронизации кабелей из LLDP нужно найти интерфейс каждого соседа в NetBox.
Для 22 устройств с 5 LLDP-соседями каждое:

```
Без кэша:
  22 устройства × 5 соседей × 2 стороны кабеля = 220 запросов к NetBox API
  Каждый запрос: GET /api/dcim/interfaces/?device_id=X&name=Y

  220 запросов × 50 мс = 11 секунд только на поиск интерфейсов
```

### Решение: кэш на уровне устройства

```
С кэшем:
  Первый запрос к устройству → GET /api/dcim/interfaces/?device_id=X
  → Загружает ВСЕ интерфейсы устройства в кэш (1 запрос)
  → Все последующие поиски интерфейсов этого устройства = из словаря (0 запросов)

  22 устройства × 1 запрос = 22 запроса вместо 220
```

### Реализация в SyncBase

**Файл:** `netbox/sync/base.py`

```python
class SyncBase:
    def __init__(self, client, ...):
        # Кэш устройств: hostname → NetBox device object
        self._device_cache: Dict[str, Any] = {}

        # Кэш VLAN: (vid, site) → NetBox VLAN object
        self._vlan_cache: Dict[Tuple[int, str], Any] = {}

        # Обратный кэш VLAN: NetBox ID → VID (для избежания lazy-load pynetbox)
        self._vlan_id_to_vid: Dict[int, int] = {}

        # Кэш интерфейсов: device_id → {имя_интерфейса: interface_object}
        self._interface_cache: Dict[int, Dict[str, Any]] = {}

    def _find_device(self, name: str):
        """Находит устройство с кэшированием."""
        if name in self._device_cache:
            return self._device_cache[name]    # Из кэша (0 запросов)
        device = self.client.get_device_by_name(name)
        if device:
            self._device_cache[name] = device  # Сохраняем в кэш
        return device

    def _find_interface(self, device_id: int, interface_name: str):
        """Находит интерфейс с кэшированием."""
        # Загружаем ВСЕ интерфейсы устройства 1 раз
        if device_id not in self._interface_cache:
            interfaces = self.client.get_interfaces(device_id=device_id)
            self._interface_cache[device_id] = {intf.name: intf for intf in interfaces}

        cache = self._interface_cache[device_id]

        # Точное совпадение
        if interface_name in cache:
            return cache[interface_name]

        # Нормализованное имя (Gi0/1 → GigabitEthernet0/1)
        normalized = self._normalize_interface_name(interface_name)
        for name, intf in cache.items():
            if self._normalize_interface_name(name) == normalized:
                return intf
        return None
```

### Кэш VLAN -- предзагрузка

При синхронизации интерфейсов с VLAN (если `sync_vlans: true`), нужно находить
VLAN по номеру (VID). Вместо поиска каждого VLAN отдельно -- загружаем все VLAN
сайта одним запросом:

```python
def _load_site_vlans(self, site: str = None):
    """Загружает ВСЕ VLAN сайта в кэш одним запросом."""
    vlans = list(self.client.get_vlans(site=site))
    for vlan in vlans:
        cache_key = (vlan.vid, site or "")
        self._vlan_cache[cache_key] = vlan
        self._vlan_id_to_vid[vlan.id] = vlan.vid  # Обратный кэш
```

---

## 6. N+1 проблема

### Что это такое

N+1 -- это антипаттерн, когда для обработки N объектов выполняется 1 + N запросов
вместо 1-2. Встречается когда ORM или API-клиент подгружает связанные объекты
"лениво" (lazy-load) -- по одному при обращении.

### Реальный пример из проекта

На одном устройстве с 55 интерфейсами наблюдались 95 лишних HTTP-запросов:

```
Было 95 лишних запросов на 1 устройство (55 интерфейсов):

  41× GET /api/ipam/vlans/102/  ← pynetbox дёргал VLAN на каждый интерфейс
  50× GET /api/dcim/devices/420/ ← загрузка устройства на каждый интерфейс
  4×  GET /api/ipam/vlans/205/

  Время: ~50 секунд на 1 устройство
  На 22 устройства: ~18 минут
```

### Почему это происходило

pynetbox (Python-клиент для NetBox API) использует lazy-load: когда ты обращаешься
к вложенному объекту (например, `interface.untagged_vlan.value`), pynetbox
автоматически делает GET-запрос для загрузки полного объекта VLAN.

```python
# ПЛОХО: каждое обращение к .value вызывает HTTP-запрос!
for intf in netbox_interfaces:
    # hasattr(intf.untagged_vlan, "value") → GET /api/ipam/vlans/102/
    if hasattr(intf.untagged_vlan, "value"):
        current_mode = intf.untagged_vlan.value  # ещё один GET!
```

### Как исправили

```python
# ХОРОШО: используем .vid (доступен в brief response, без lazy-load)
# и обратный кэш _vlan_id_to_vid

# Вместо hasattr(val, "value") → GET-запрос к API
# Используем .vid напрямую (не вызывает lazy-load):
if nb_interface.untagged_vlan:
    current_vlan_id = nb_interface.untagged_vlan.id   # ID уже в brief response
    current_vlan_vid = self._vlan_id_to_vid.get(current_vlan_id)  # Из кэша

# Вместо device.site.name на каждом интерфейсе → GET /api/dcim/devices/{id}/
# Кэшируем site_name один раз до цикла:
site_name = getattr(device.site, 'name', None)
# Передаём в каждый _check_untagged_vlan(... site_name=site_name)
```

Результат:
```
Стало: 3 запроса на устройство (device + vlans + interfaces)
Время: ~15 секунд на 1 устройство (было 50)
На 22 устройства: ~5 минут (было 18)
```

### Правило

Если видишь `hasattr(pynetbox_object, "value")` или обращение к вложенным объектам
в цикле -- это потенциальная N+1 проблема. Используй кэш или предзагрузку.

---

## 7. dry_run -- режим "посмотреть что будет"

`dry_run` -- режим симуляции. Проект выполняет всё: сбор данных, сравнение,
подготовку запросов -- но **не отправляет** изменения в NetBox.

### CLI

```bash
# Посмотреть что изменится
python -m network_collector sync-netbox --interfaces --dry-run
```

### Вывод

```
[DRY-RUN] Создание интерфейса: GigabitEthernet0/25
[DRY-RUN] Создание интерфейса: GigabitEthernet0/26
[DRY-RUN] Обновление интерфейса GigabitEthernet0/1: {'description': 'К серверу DB-01'}
[DRY-RUN] Обновление интерфейса GigabitEthernet0/2: {'enabled': True}

Синхронизация интерфейсов switch-01: создано=2, обновлено=2, удалено=0, пропущено=46
```

### Как это работает в коде

```python
# netbox/sync/interfaces.py
def _batch_create_interfaces(self, device_id, to_create, ...):
    # Разделяем на LAG и остальные (LAG нужно создать первым!)
    lag_items = [...]     # Port-channel
    member_items = [...]  # Остальные (включая member'ов LAG)

    # Фаза 1: LAG
    _do_batch_create(device_id, lag_items)
    # Фаза 2: member'ы (теперь get_interface_by_name найдёт LAG)
    _do_batch_create(device_id, member_items)

def _do_batch_create(self, device_id, items, ...):
    # Подготавливаем данные (это происходит ВСЕГДА)
    for item, intf in items:
        data, mac = self._build_create_data(device_id, intf)
        create_batch.append(data)

    # А вот отправка -- только если НЕ dry_run
    if self.dry_run:
        for name in create_names:
            logger.info(f"[DRY-RUN] Создание интерфейса: {name}")
            stats["created"] += 1    # Статистика считается
        return                        # Но запрос НЕ отправляется

    # Реальная отправка
    created = self.client.bulk_create_interfaces(create_batch)
```

Рекомендация: **всегда** запускайте `--dry-run` перед реальной синхронизацией,
особенно с `--cleanup` (удаление лишних объектов).

---

## 8. Mixin-архитектура sync

### Проблема: один огромный файл

Если вся логика синхронизации в одном классе -- это 2000+ строк кода.
Невозможно читать, тестировать, ревьюить.

### Решение: mixin-классы

Каждый тип синхронизации -- отдельный файл со своим mixin-классом.
Главный класс `NetBoxSync` просто наследуется от всех:

**Файл:** `netbox/sync/main.py`

```python
class NetBoxSync(
    InterfacesSyncMixin,    # sync_interfaces()        — netbox/sync/interfaces.py
    CablesSyncMixin,        # sync_cables_from_lldp()  — netbox/sync/cables.py
    IPAddressesSyncMixin,   # sync_ip_addresses()      — netbox/sync/ip_addresses.py
    DevicesSyncMixin,       # create_device(), sync_devices_from_inventory()
    VLANsSyncMixin,         # sync_vlans_from_interfaces()
    InventorySyncMixin,     # sync_inventory()         — netbox/sync/inventory.py
    SyncBase,               # Общие методы: кэши, _find_device, _batch_with_fallback
):
    pass  # Всё наследуется из mixin-классов
```

### Как работает mixin

Mixin -- это класс, который добавляет методы к другому классу через наследование.
Сам по себе не используется:

```python
# netbox/sync/interfaces.py
class InterfacesSyncMixin:
    """Mixin для синхронизации интерфейсов."""

    def sync_interfaces(
        self: SyncBase,              # Аннотация типа -- подсказка что self будет SyncBase
        device_name: str,
        interfaces: List[Interface],
        cleanup: bool = False,
    ) -> Dict[str, Any]:
        # Внутри можно использовать все методы SyncBase:
        device = self.client.get_device_by_name(device_name)  # client из SyncBase
        self._find_device(device_name)                         # _find_device из SyncBase
        self._batch_with_fallback(...)                         # _batch_with_fallback из SyncBase
```

`self: SyncBase` -- это type hint для IDE. Он говорит: "когда этот метод вызывается,
`self` будет экземпляром класса с атрибутами SyncBase (client, dry_run, кэши, ...)".

### SyncBase -- общие методы

**Файл:** `netbox/sync/base.py`

```python
class SyncBase:
    def __init__(self, client, dry_run=False, ...):
        self.client = client          # NetBoxClient
        self.dry_run = dry_run
        self._device_cache = {}       # Кэш устройств
        self._vlan_cache = {}         # Кэш VLAN
        self._interface_cache = {}    # Кэш интерфейсов

    # Поиск с кэшированием
    def _find_device(self, name): ...
    def _find_interface(self, device_id, name): ...
    def _get_vlan_by_vid(self, vid, site): ...

    # Batch с fallback
    def _batch_with_fallback(self, batch_data, bulk_fn, fallback_fn, ...): ...

    # Get-or-create
    def _get_or_create_manufacturer(self, name): ...
    def _get_or_create_site(self, name): ...
```

### Структура файлов

```
netbox/sync/
├── main.py           # NetBoxSync — объединяет все mixin-ы
├── base.py           # SyncBase — кэши, общие методы
├── interfaces.py     # InterfacesSyncMixin — sync_interfaces()
├── cables.py         # CablesSyncMixin — sync_cables_from_lldp()
├── ip_addresses.py   # IPAddressesSyncMixin — sync_ip_addresses()
├── inventory.py      # InventorySyncMixin — sync_inventory()
├── devices.py        # DevicesSyncMixin — create_device()
└── vlans.py          # VLANsSyncMixin — sync_vlans_from_interfaces()
```

---

## Полная картина: sync_interfaces шаг за шагом

Разберём полный путь синхронизации интерфейсов на конкретном примере.

### Шаг 1: Подготовка

```python
sync = NetBoxSync(client, dry_run=False)
stats = sync.sync_interfaces("switch-01", collected_interfaces, cleanup=True)
```

### Шаг 2: Найти устройство в NetBox

```python
# netbox/sync/interfaces.py — sync_interfaces()
device = self.client.get_device_by_name("switch-01")
# Если не найдено по имени — fallback поиск по IP
```

### Шаг 3: Предзагрузка кэшей

```python
# Загружаем VLAN сайта одним запросом (если sync_vlans включён)
if sync_vlans:
    self._get_vlan_by_vid(1, site_name)  # Форсирует _load_site_vlans()

# Загружаем текущие интерфейсы из NetBox
existing = list(self.client.get_interfaces(device_id=device.id))
```

### Шаг 4: Сравнение через SyncComparator

```python
comparator = SyncComparator()
diff = comparator.compare_interfaces(
    local=local_data,          # Данные с устройства
    remote=existing,           # Данные из NetBox
    exclude_patterns=["Vlan1"],
    compare_fields=["description", "enabled", "mode", "mtu", "duplex", "speed"],
    cleanup=True,
)
```

### Шаг 5: Batch CREATE (двухфазный для LAG)

Создание интерфейсов разделено на две фазы, чтобы member-интерфейсы
могли найти свой LAG по имени (он должен уже существовать в NetBox):

```python
# Фаза 1: сначала создаём LAG интерфейсы (Port-channel)
lag_batch = [_build_create_data(device.id, intf) for intf in lag_interfaces]
self.client.bulk_create_interfaces(lag_batch)
# Теперь Port-channel1, Port-channel2 существуют в NetBox

# Фаза 2: создаём member и standalone интерфейсы
# _build_create_data() для Gi0/1 с lag="Port-channel1" вызывает
# get_interface_by_name("Port-channel1") -- и НАХОДИТ его (создан в фазе 1)
member_batch = [_build_create_data(device.id, intf) for intf in other_interfaces]
self.client.bulk_create_interfaces(member_batch)
# data = {"device": 42, "name": "Gi0/1", "lag": 123, ...}  ← lag ID!
```

Без двухфазного создания member-интерфейсы не получали бы `lag` ID,
потому что Port-channel ещё не существовал в NetBox на момент вызова
`get_interface_by_name()`.

### Шаг 6: Batch UPDATE

```python
# Для каждого to_update: подготовить изменения
for item in diff.to_update:
    updates, changes, mac = self._build_update_data(item.remote_data, intf)
    # updates = {"description": "К серверу DB-01", "enabled": True}
    updates["id"] = item.remote_data.id   # ID для обновления
    update_batch.append(updates)

# Один HTTP-запрос на все обновления
self.client.bulk_update_interfaces(update_batch)
```

### Шаг 7: Batch DELETE (если cleanup=True)

```python
# Интерфейсы которые есть в NetBox, но нет на устройстве
delete_ids = [item.remote_data.id for item in diff.to_delete]
self.client.bulk_delete_interfaces(delete_ids)
```

### Шаг 8: Результат

```python
# stats = {"created": 2, "updated": 3, "deleted": 1, "skipped": 46}
logger.info(
    f"Синхронизация интерфейсов switch-01: "
    f"создано=2, обновлено=3, удалено=1, пропущено=46"
)
```

---

## _build_update_data: проверка каждого поля

**Файл:** `netbox/sync/interfaces.py`

Обновление интерфейса -- сложный процесс. Для каждого поля есть отдельный
`_check_*` хелпер, который решает: изменилось поле или нет.

```python
def _build_update_data(self, nb_interface, intf, site_name=None):
    updates = {}
    actual_changes = []

    # Каждый хелпер проверяет одно поле
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

Зачем отдельные хелперы? Каждое поле имеет свою логику:
- `enabled`: зависит от `enabled_mode` ("admin" или "link")
- `untagged_vlan`: нужно искать VLAN в NetBox по VID через кэш
- `tagged_vlans`: парсинг диапазона "10,20,30-40", сравнение множеств
- `mac`: отдельный API endpoint (не в bulk)

---

## Конфигурация sync через fields.yaml

Какие поля синхронизировать, какие пропускать -- настраивается в `fields.yaml`:

```yaml
# fields.yaml (пример секции interfaces)
interfaces:
  fields:
    description: true     # Синхронизировать описание
    enabled: true         # Синхронизировать статус enabled/disabled
    mac_address: true     # Синхронизировать MAC-адрес
    mode: true            # Синхронизировать switchport mode
    mtu: true             # Синхронизировать MTU
    speed: true           # Синхронизировать скорость
    duplex: true          # Синхронизировать duplex
    untagged_vlan: true   # Синхронизировать untagged VLAN
    tagged_vlans: true    # Синхронизировать tagged VLANs

  options:
    create_missing: true        # Создавать новые интерфейсы
    update_existing: true       # Обновлять существующие
    sync_vlans: true            # Включить синхронизацию VLAN
    enabled_mode: "admin"       # "admin" (up/down=enabled) или "link" (только up=enabled)
    auto_detect_type: true      # Автоопределение типа порта (1000base-t, 10gbase-x-sfpp, ...)
    sync_mac_only_with_ip: false # MAC только для интерфейсов с IP
    exclude_interfaces:         # Исключить из синхронизации
      - "Vlan1"
      - "Null.*"
```

---

## 9. VlanSet -- сравнение VLAN

**Файл:** `core/domain/vlan.py`

VlanSet -- абстракция для работы с множествами VLAN. Инкапсулирует парсинг,
сравнение и вычисление разницы между двумя наборами VLAN.

### Создание VlanSet

```python
from network_collector.core.domain.vlan import VlanSet

# Из строки диапазона (данные с устройства: "10,20,30-50")
local = VlanSet.from_string("10,20,30-50")

# Из списка VID (целые числа)
target = VlanSet.from_ids([10, 20, 30])

# Из объектов NetBox VLAN (имеющих атрибут .vid)
current = VlanSet.from_vlan_objects(nb_interface.tagged_vlans)
```

### Методы сравнения

```python
local = VlanSet.from_ids([10, 20, 30])
remote = VlanSet.from_ids([10, 20])

local == remote            # False -- множества не совпадают
local.added(remote)        # {30} -- есть в local, нет в remote (добавленные)
local.removed(remote)      # set() -- есть в remote, нет в local (удалённые)
local.intersection(remote) # {10, 20} -- общие VLAN
```

### Реальное использование в _check_tagged_vlans

```python
# netbox/sync/interfaces.py -- _check_tagged_vlans()
current = VlanSet.from_vlan_objects(nb_interface.tagged_vlans)  # Что сейчас в NetBox
target = VlanSet.from_ids(matched_vids)                         # Что должно быть

if current != target:
    updates["tagged_vlans"] = sorted(target_vlan_ids)
    added = target.added(current)     # Какие VLAN добавить
    removed = target.removed(current) # Какие VLAN убрать
    # Лог: "tagged_vlans: +[30, 40], -[50]"
```

Зачем нужен VlanSet: вместо ручного сравнения множеств через `set()` и
запутанных конструкций -- единый интерфейс с методами `added()` / `removed()`.
Это позволяет показать в логах **конкретно** какие VLAN добавлены и удалены,
а не просто "tagged_vlans изменились".

---

## 10. MAC-адреса -- отдельный endpoint

MAC-адрес интерфейса в NetBox назначается через **отдельный API endpoint**,
а не через bulk create/update. Это архитектурное ограничение NetBox API.

### Почему MAC не в bulk

NetBox API не принимает `mac_address` в теле bulk create/update для интерфейсов.
MAC назначается отдельным вызовом `assign_mac_to_interface(interface_id, mac)`.

### _build_create_data возвращает кортеж

```python
# netbox/sync/interfaces.py -- _build_create_data()
def _build_create_data(self, device_id, intf):
    data = {"device": device_id, "name": intf.name, "type": ...}
    # ... заполняем description, enabled, mtu, speed, duplex, mode ...

    mac_to_assign = None
    if sync_cfg.is_field_enabled("mac_address") and intf.mac:
        mac_to_assign = normalize_mac_netbox(intf.mac)  # "AA:BB:CC:DD:EE:FF"

    return data, mac_to_assign  # MAC отдельно от data!
```

### Post-create: назначение MAC после создания

```python
# После bulk_create_interfaces -- назначаем MAC по одному
created = self.client.bulk_create_interfaces(create_batch)

for idx, mac in create_mac_queue:
    # created[idx].id -- ID только что созданного интерфейса
    self.client.assign_mac_to_interface(created[idx].id, mac)
```

### Опция sync_mac_only_with_ip

В `fields.yaml` есть опция `sync_mac_only_with_ip`. Если `true` --
MAC синхронизируется **только** для интерфейсов с IP-адресом:

```python
sync_mac_only_with_ip = sync_cfg.get_option("sync_mac_only_with_ip", False)
if sync_mac_only_with_ip and not intf.ip_address:
    return None  # MAC не назначаем -- нет IP на интерфейсе
```

Это полезно когда не нужно засорять NetBox MAC-адресами access-портов,
а интересуют только management/SVI интерфейсы.

---

## 11. fields_config -- управление полями

**Файл:** `fields_config.py`

Модуль `fields_config` загружает настройки из `fields.yaml` и предоставляет
API для проверки: какие поля включены, какие опции заданы.

### Основные функции

```python
from network_collector.fields_config import get_sync_config

# Получаем конфиг для интерфейсов
cfg = get_sync_config("interfaces")

# Включено ли поле description для синхронизации?
cfg.is_field_enabled("description")   # True/False

# Получить опцию (из секции options в fields.yaml)
cfg.get_option("sync_vlans", False)           # True/False
cfg.get_option("enabled_mode", "admin")       # "admin" или "link"
cfg.get_option("sync_mac_only_with_ip", False)
```

### Структура SyncEntityConfig

```python
@dataclass
class SyncEntityConfig:
    fields: Dict[str, SyncFieldConfig]   # Конфигурация полей
    defaults: Dict[str, Any]             # Значения по умолчанию
    options: Dict[str, Any]              # Опции поведения

    def is_field_enabled(self, field_name: str) -> bool: ...
    def get_option(self, key: str, default=None) -> Any: ...
```

### Пример секции interfaces в fields.yaml

```yaml
sync:
  interfaces:
    fields:
      description: {enabled: true}
      enabled: {enabled: true}
      mac_address: {enabled: true}
      mode: {enabled: true}
      mtu: {enabled: true}
      speed: {enabled: true}
      duplex: {enabled: true}
    options:
      sync_vlans: true
      enabled_mode: "admin"
      sync_mac_only_with_ip: false
      exclude_interfaces: ["Vlan1", "Null.*"]
```

Как это влияет на sync: каждый `_check_*` хелпер в `_build_update_data()`
вызывает `sync_cfg.is_field_enabled(...)` перед проверкой поля. Если поле
выключено в `fields.yaml` -- оно полностью игнорируется при сравнении.

---

## 12. RunContext -- отслеживание выполнения

**Файл:** `core/context.py`

RunContext -- контекст выполнения операции. Создаётся один раз при запуске
команды и прокидывается через все слои (CLI -> Sync -> Client).

### Создание и использование

```python
from network_collector.core.context import RunContext

# Создаём контекст (уникальный run_id)
ctx = RunContext.create(command="sync-netbox", dry_run=True)
# ctx.run_id = "2025-03-14T12-30-22" (timestamp) или "abc12345" (UUID)
```

### Как прокидывается в Sync

```python
# netbox/sync/base.py -- SyncBase.__init__()
self.ctx = context or get_current_context()
```

Если контекст не передан явно -- берётся глобальный (установленный в CLI).

### _log_prefix -- привязка логов к запуску

```python
# netbox/sync/base.py
def _log_prefix(self) -> str:
    if self.ctx:
        return f"[{self.ctx.run_id}] "
    return ""

# Использование в логах:
logger.info(f"{self._log_prefix()}Создан интерфейс: Gi0/1")
# -> "[2025-03-14T12-30-22] Создан интерфейс: Gi0/1"
```

Зачем: когда несколько sync-операций запускаются параллельно (через API),
`_log_prefix()` позволяет отличить логи одного запуска от другого.
Каждый запуск имеет уникальный `run_id`, и все его логи помечены этим ID.

---

## Ключевые файлы

| Файл | Описание |
|------|----------|
| `core/domain/sync.py` | SyncComparator, SyncDiff, SyncItem -- чистая логика сравнения |
| `core/domain/vlan.py` | VlanSet -- сравнение множеств VLAN |
| `core/context.py` | RunContext -- контекст выполнения с run_id |
| `netbox/sync/main.py` | NetBoxSync -- главный класс (объединяет mixin-ы) |
| `netbox/sync/base.py` | SyncBase -- кэши, _find_device, _batch_with_fallback |
| `netbox/sync/interfaces.py` | InterfacesSyncMixin -- sync_interfaces, _build_create/update_data |
| `netbox/sync/cables.py` | CablesSyncMixin -- sync_cables_from_lldp |
| `netbox/sync/ip_addresses.py` | IPAddressesSyncMixin -- sync_ip_addresses |
| `netbox/sync/inventory.py` | InventorySyncMixin -- sync_inventory |
| `netbox/sync/devices.py` | DevicesSyncMixin -- create_device, sync_devices_from_inventory |
| `netbox/sync/vlans.py` | VLANsSyncMixin -- sync_vlans_from_interfaces |
| `netbox/client/interfaces.py` | bulk_create/update/delete_interfaces |
| `netbox/client/inventory.py` | bulk_create/update/delete_inventory_items |
| `netbox/client/ip_addresses.py` | bulk_create/update/delete_ip_addresses |
| `fields_config.py` | API для чтения fields.yaml (get_sync_config) |
| `fields.yaml` | Настройки полей синхронизации |
