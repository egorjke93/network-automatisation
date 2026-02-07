# 09. Mixins: паттерн композиции в Python

> Этот документ готовит к вопросам на собеседовании по Software Engineering.
> Все примеры кода — реальные, из нашего проекта.

---

## 1. Что такое Mixin (простым языком)

**Аналогия:** Представьте персонажа в игре. Он может быть Воином (основной класс).
Но мы можем «подмешать» ему умения: Плавание, Готовка, Взлом замков.
Каждое умение — это Mixin: набор методов без собственного состояния.

**Определение:** Mixin — это класс, который:
- Содержит методы (поведение)
- **Не имеет** собственного `__init__` (не создаёт своё состояние)
- **Не имеет** самостоятельного смысла (нельзя создать экземпляр Mixin напрямую)
- Предназначен для «подмешивания» в другой класс через множественное наследование

**Разница с обычным наследованием:**

```
Обычное наследование (IS-A):
  Animal -> Dog        # Собака ЯВЛЯЕТСЯ Животным

Mixin (CAN-DO):
  SwimmingMixin       # Класс УМЕЕТ плавать
  FlyingMixin         # Класс УМЕЕТ летать
  class Duck(SwimmingMixin, FlyingMixin, Bird): ...
```

В обычном наследовании мы строим иерархию «кто есть кто».
С Mixin мы собираем класс из «что умеет делать».

---

## 2. Mixins в нашем проекте — NetBoxSync

Файл: `netbox/sync/main.py`

```python
class NetBoxSync(
    InterfacesSyncMixin,     # sync_interfaces, _build_create_data, _build_update_data
    CablesSyncMixin,         # sync_cables_from_lldp, _create_cable, _cleanup_cables
    IPAddressesSyncMixin,    # sync_ip_addresses, _set_primary_ip
    DevicesSyncMixin,        # create_device, sync_devices_from_inventory
    VLANsSyncMixin,          # sync_vlans_from_interfaces
    InventorySyncMixin,      # sync_inventory
    SyncBase,                # Базовый класс — ПОСЛЕДНИЙ!
):
    """
    Синхронизация данных с NetBox.

    ВАЖНО: Мы ТОЛЬКО ЧИТАЕМ с устройств и ЗАПИСЫВАЕМ в NetBox!
    """

    def __init__(
        self,
        client: NetBoxClient,
        dry_run: bool = False,
        create_only: bool = False,
        update_only: bool = False,
        context: Optional[RunContext] = None,
    ):
        super().__init__(
            client=client,
            dry_run=dry_run,
            create_only=create_only,
            update_only=update_only,
            context=context,
        )
```

### Что даёт каждый Mixin

| Mixin | Публичные методы | Назначение |
|-------|-----------------|------------|
| `InterfacesSyncMixin` | `sync_interfaces()` | Синхронизация интерфейсов: create/update/delete через batch API |
| `CablesSyncMixin` | `sync_cables_from_lldp()` | Создание кабелей из LLDP/CDP данных, cleanup лишних |
| `IPAddressesSyncMixin` | `sync_ip_addresses()` | Синхронизация IP-адресов, установка primary IP |
| `DevicesSyncMixin` | `create_device()`, `sync_devices_from_inventory()` | Создание и обновление устройств в NetBox |
| `VLANsSyncMixin` | `sync_vlans_from_interfaces()` | Создание VLAN из SVI-интерфейсов |
| `InventorySyncMixin` | `sync_inventory()` | Синхронизация модулей, SFP, PSU |

### Базовый класс SyncBase

Файл: `netbox/sync/base.py`

SyncBase содержит **общее состояние** и **утилиты**, которые используют все mixins:

```python
class SyncBase:
    """Базовый класс для синхронизации с NetBox."""

    def __init__(
        self,
        client: NetBoxClient,
        dry_run: bool = False,
        create_only: bool = False,
        update_only: bool = False,
        context: Optional[RunContext] = None,
    ):
        self.client = client                           # NetBox API клиент
        self.ctx = context or get_current_context()    # Контекст выполнения
        self.dry_run = dry_run                         # Режим симуляции
        self.create_only = create_only                 # Только создавать
        self.update_only = update_only                 # Только обновлять

        # === Кэши (общие для ВСЕХ mixins) ===
        self._device_cache: Dict[str, Any] = {}        # name -> Device
        self._mac_cache: Dict[str, Any] = {}            # mac -> Device
        self._vlan_cache: Dict[Tuple[int, str], Any] = {}  # (vid, site) -> VLAN
        self._vlan_id_to_vid: Dict[int, int] = {}      # NetBox ID -> VID
        self._interface_cache: Dict[int, Dict[str, Any]] = {}  # device_id -> {name: intf}
```

Утилиты из SyncBase, доступные всем mixins:

```python
# Поиск с кэшированием
def _find_device(self, name: str) -> Optional[Any]: ...
def _find_interface(self, device_id: int, interface_name: str) -> Optional[Any]: ...
def _find_device_by_mac(self, mac: str) -> Optional[Any]: ...
def _get_vlan_by_vid(self, vid: int, site: Optional[str] = None) -> Optional[Any]: ...

# Get-or-create паттерн
def _get_or_create_manufacturer(self, name: str) -> Optional[Any]: ...
def _get_or_create_device_type(self, model: str, manufacturer_id: int) -> Optional[Any]: ...
def _get_or_create_site(self, name: str) -> Optional[Any]: ...

# Batch с fallback
def _batch_with_fallback(self, batch_data, item_names, bulk_fn, fallback_fn, ...): ...

# Парсинг
def _parse_speed(self, speed_str: str) -> Optional[int]: ...
def _parse_duplex(self, duplex_str: str) -> Optional[str]: ...
```

---

## 3. Mixins в NetBoxClient

Тот же паттерн используется для клиента API.

Файл: `netbox/client/main.py`

```python
class NetBoxClient(
    DevicesMixin,        # get_devices, get_device_by_name, get_device_by_ip
    InterfacesMixin,     # get_interfaces, create_interface, bulk_create_interfaces
    IPAddressesMixin,    # get_ip_addresses, bulk_create_ip_addresses, get_cables
    VLANsMixin,          # get_vlans, get_vlan_by_vid, create_vlan
    InventoryMixin,      # get_inventory_items, bulk_create_inventory_items
    DCIMMixin,           # assign_mac_to_interface, get_interface_mac
    NetBoxClientBase,    # __init__ с pynetbox API (ПОСЛЕДНИЙ!)
):
    """
    Клиент для работы с NetBox API через pynetbox.
    """
    pass  # Всё поведение собрано из mixins
```

Обратите внимание: тело класса — `pass`. Все методы приходят из mixins.

Базовый класс `NetBoxClientBase` (`netbox/client/base.py`):

```python
class NetBoxClientBase:
    """Базовый класс — инициализация подключения к NetBox API."""

    def __init__(self, url=None, token=None, ssl_verify=True):
        self.url = url or os.environ.get("NETBOX_URL")
        self._token = get_netbox_token(config_token=token)
        self.api = pynetbox.api(self.url, token=self._token)
```

Все client mixins используют `self.api` из базового класса — по тому же принципу,
что sync mixins используют `self.client` и `self.dry_run` из SyncBase.

---

## 4. Паттерн `self: SyncBase` — как IDE понимает Mixins

Файл: `netbox/sync/interfaces.py`

```python
class InterfacesSyncMixin:
    """Mixin для синхронизации интерфейсов."""

    def sync_interfaces(
        self: SyncBase,         # <-- Аннотация типа для self!
        device_name: str,
        interfaces: List[Interface],
        ...
    ) -> Dict[str, Any]:
```

### Зачем аннотация `self: SyncBase`?

Mixin — это класс `InterfacesSyncMixin`. Без аннотации IDE думает:
- `self` имеет тип `InterfacesSyncMixin`
- У `InterfacesSyncMixin` нет атрибутов `.client`, `.dry_run`, `._device_cache`
- IDE подчёркивает **все** обращения к self красным цветом

С аннотацией `self: SyncBase`:
- IDE знает, что `self` будет объектом с атрибутами SyncBase
- Автодополнение работает: `self.client.` показывает методы NetBoxClient
- mypy не ругается на `self.dry_run` или `self._find_device()`

### Пример из реального кода

Каждый метод в каждом mixin использует этот паттерн:

```python
# netbox/sync/cables.py
class CablesSyncMixin:
    def sync_cables_from_lldp(self: SyncBase, lldp_data, ...) -> Dict[str, int]:
        # self.dry_run     — из SyncBase
        # self._find_device() — из SyncBase
        # self.client      — из SyncBase
        device = self._find_device(local_device)   # IDE знает этот метод
        ...

# netbox/sync/devices.py
class DevicesSyncMixin:
    def create_device(self: SyncBase, name: str, ...) -> Optional[Any]:
        existing = self.client.get_device_by_name(name)  # IDE знает self.client
        if self.dry_run:                                  # IDE знает self.dry_run
            ...
```

Этот паттерн используется **последовательно во всех 6 sync-mixin файлах**.

---

## 5. Правила композиции Mixins

### Правило 1: Базовый класс ПОСЛЕДНИЙ в списке наследования

```python
# ПРАВИЛЬНО: SyncBase последний
class NetBoxSync(
    InterfacesSyncMixin,
    CablesSyncMixin,
    SyncBase,            # <-- последний
): ...

# НЕПРАВИЛЬНО: базовый класс не последний
class NetBoxSync(
    SyncBase,            # <-- первый (ОШИБКА!)
    InterfacesSyncMixin,
    CablesSyncMixin,
): ...
```

Это связано с MRO (Method Resolution Order). Python ищет метод по порядку:
`NetBoxSync -> InterfacesSyncMixin -> CablesSyncMixin -> ... -> SyncBase`.
Если SyncBase стоит первым, его методы будут найдены раньше методов mixins.

### Правило 2: Mixins НЕ зависят друг от друга

```python
# InterfacesSyncMixin НЕ вызывает методы CablesSyncMixin
# CablesSyncMixin НЕ вызывает методы DevicesSyncMixin
# Каждый mixin зависит ТОЛЬКО от SyncBase
```

Это видно в импортах каждого mixin-файла:

```python
# netbox/sync/interfaces.py
from .base import SyncBase, SyncComparator, Interface, ...

# netbox/sync/cables.py
from .base import SyncBase, LLDPNeighbor, get_cable_endpoints, ...

# netbox/sync/devices.py
from .base import SyncBase, DeviceInfo, get_sync_config, ...
```

Каждый файл импортирует **только из base** — никогда из другого mixin.

### Правило 3: Mixins НЕ переопределяют методы друг друга

У каждого mixin — свой уникальный namespace методов:

| Mixin | Методы (начинаются с) |
|-------|----------------------|
| InterfacesSyncMixin | `sync_interfaces`, `_batch_create_interfaces`, `_build_create_data`, `_check_*` |
| CablesSyncMixin | `sync_cables_from_lldp`, `_create_cable`, `_cleanup_cables`, `_find_neighbor_device` |
| IPAddressesSyncMixin | `sync_ip_addresses`, `_batch_create_ip_addresses`, `_set_primary_ip` |
| DevicesSyncMixin | `create_device`, `sync_devices_from_inventory`, `_update_device`, `_cleanup_devices` |
| VLANsSyncMixin | `sync_vlans_from_interfaces` |
| InventorySyncMixin | `sync_inventory` |

Никаких пересечений имён методов. Конфликтов нет.

### Правило 4: Общее состояние только через базовый класс

Mixins не создают своих атрибутов. Все `self.*` атрибуты определены в `SyncBase.__init__`:

```python
# ВСЕ эти атрибуты создаются в SyncBase.__init__:
self.client           # используется в КАЖДОМ mixin
self.dry_run          # используется в КАЖДОМ mixin
self._device_cache    # используется в cables, devices, inventory
self._vlan_cache      # используется в interfaces, vlans
self._interface_cache # используется в cables, ip_addresses
```

---

## 6. Пример: как вызов проходит через Mixin

```python
# 1. Создаём объект — вызывается __init__ из SyncBase
sync = NetBoxSync(client, dry_run=True)
#   self.client = client           (из SyncBase)
#   self.dry_run = True            (из SyncBase)
#   self._device_cache = {}        (из SyncBase)

# 2. Вызываем метод из InterfacesSyncMixin
sync.sync_interfaces("switch-01", interfaces_list)

# Python ищет sync_interfaces() по MRO:
#   NetBoxSync -> InterfacesSyncMixin (НАЙДЕН!) -> ... -> SyncBase

# 3. Внутри sync_interfaces (файл: netbox/sync/interfaces.py):
def sync_interfaces(self: SyncBase, device_name, interfaces, ...):
    device = self.client.get_device_by_name(device_name)  # self.client из SyncBase
    if self.dry_run:                                       # self.dry_run из SyncBase
        ...
    self._batch_with_fallback(...)                         # метод из SyncBase

# 4. Кэш накапливается между вызовами разных mixins:
sync.sync_interfaces("switch-01", interfaces)   # _device_cache["switch-01"] = device
sync.sync_cables_from_lldp(lldp_data)           # _device_cache["switch-01"] уже в кэше!
sync.sync_ip_addresses("switch-01", ip_data)    # _device_cache["switch-01"] — из кэша!
```

Ключевой момент: **один объект `sync`** накапливает кэши при последовательных вызовах.
Когда pipeline вызывает сначала `sync_interfaces`, потом `sync_cables` — второй
вызов уже не ходит в NetBox API за устройством, а берёт его из `_device_cache`.

---

## 7. Mixins vs Composition (DI) — сравнение для собеседования

| Критерий | Mixins (наш подход) | Composition (DI) |
|----------|-------------------|-----------------|
| **Как выглядит** | `class Sync(MixinA, MixinB, Base)` | `class Sync: def __init__(self, intf_service, cable_service)` |
| **Общее состояние** | Через `self` (один объект) | Через параметры конструктора |
| **Кэши** | Один `_device_cache` для всех | Каждый сервис свой кэш (или общий через DI) |
| **Тестирование** | Mock один объект, привязать mixin | Mock каждый сервис отдельно |
| **Добавить функцию** | Новый mixin + добавить в класс | Новый service + передать в конструктор |
| **Type safety** | `self: SyncBase` аннотация | Полноценная через интерфейсы/протоколы |
| **Python-идиома** | Да (Django, DRF, stdlib) | Больше Java/C# стиль |
| **Файловая структура** | 1 файл = 1 mixin | 1 файл = 1 сервис |
| **Количество объектов** | 1 (NetBoxSync) | N (sync + 6 сервисов + cache) |
| **Связность** | Через общий self | Через конструктор |

### Как бы выглядел Composition:

```python
# Composition (DI) — альтернативный подход
class InterfaceSyncService:
    def __init__(self, client, cache, config):
        self.client = client
        self.cache = cache       # отдельный объект кэша
        self.config = config

    def sync_interfaces(self, device_name, interfaces): ...

class CableSyncService:
    def __init__(self, client, cache, config):
        self.client = client
        self.cache = cache       # тот же объект кэша (через DI)
        self.config = config

    def sync_cables(self, lldp_data): ...

class NetBoxSync:
    def __init__(self, client, dry_run=False):
        cache = SharedCache()
        config = SyncConfig(dry_run=dry_run)
        self.interfaces = InterfaceSyncService(client, cache, config)
        self.cables = CableSyncService(client, cache, config)
        self.ip_addresses = IPAddressSyncService(client, cache, config)
        self.devices = DeviceSyncService(client, cache, config)
        self.vlans = VLANSyncService(client, cache, config)
        self.inventory = InventorySyncService(client, cache, config)

# Вызов:
sync = NetBoxSync(client, dry_run=True)
sync.interfaces.sync_interfaces("switch-01", data)  # <-- через вложенный объект
sync.cables.sync_cables(lldp_data)
```

Видно, что Composition требует:
- Отдельный класс `SharedCache` для общих кэшей
- Отдельный класс `SyncConfig` для общих настроек
- Конструктор с 6 сервисами
- Вызов через `sync.interfaces.sync_interfaces()` вместо `sync.sync_interfaces()`

---

## 8. Почему мы выбрали Mixins, а не Composition

### 1. Общие кэши без лишних абстракций

```python
# С Mixins: кэш — просто атрибут self, доступен ВСЕМ mixins
self._device_cache["switch-01"] = device  # записал InterfacesSyncMixin
self._device_cache["switch-01"]           # прочитал CablesSyncMixin (из кэша!)

# С Composition: нужен отдельный SharedCache, передаём его в каждый сервис
cache = SharedCache()
InterfaceSyncService(client, cache)
CableSyncService(client, cache)    # тот же cache (нужно не забыть передать!)
```

В нашем проекте 5 кэшей (`_device_cache`, `_mac_cache`, `_vlan_cache`,
`_vlan_id_to_vid`, `_interface_cache`). С Composition это 5 разделяемых объектов
или один CacheService с 5 словарями.

### 2. Единый self — кэши накапливаются

Pipeline вызывает операции последовательно на одном объекте:

```python
sync = NetBoxSync(client)
# Pipeline шаг 1: sync_interfaces — заполняет _device_cache, _interface_cache
# Pipeline шаг 2: sync_cables — берёт устройства из _device_cache (0 API-запросов)
# Pipeline шаг 3: sync_ip_addresses — берёт интерфейсы из _interface_cache
```

### 3. Python-идиоматично

Этот паттерн используется в популярных Python-фреймворках:

- **Django**: `LoginRequiredMixin`, `PermissionRequiredMixin` для views
- **DRF (Django REST Framework)**: `CreateModelMixin`, `ListModelMixin`, `RetrieveModelMixin`
- **Стандартная библиотека**: `socketserver.ThreadingMixIn`, `socketserver.ForkingMixIn`

```python
# DRF — точно такой же паттерн как у нас:
class ModelViewSet(
    CreateModelMixin,      # create()
    RetrieveModelMixin,    # retrieve()
    UpdateModelMixin,      # update()
    DestroyModelMixin,     # destroy()
    ListModelMixin,        # list()
    GenericViewSet,        # базовый класс — ПОСЛЕДНИЙ
): ...
```

### 4. Простота

- Не нужен DI-контейнер (injector, dependency-injector)
- Не нужен конструктор с 6 параметрами
- Одна строка для добавления нового функционала:

```python
# Добавляем новый mixin:
class NetBoxSync(
    InterfacesSyncMixin,
    CablesSyncMixin,
    NewFeatureSyncMixin,    # <-- добавили одну строку
    SyncBase,
): ...
```

### 5. Файловая организация: один файл = одна ответственность

```
netbox/sync/
    base.py          # SyncBase: состояние + утилиты (~400 строк)
    interfaces.py    # InterfacesSyncMixin (~840 строк)
    cables.py        # CablesSyncMixin (~350 строк)
    ip_addresses.py  # IPAddressesSyncMixin (~450 строк)
    devices.py       # DevicesSyncMixin (~400 строк)
    vlans.py         # VLANsSyncMixin (~95 строк)
    inventory.py     # InventorySyncMixin (~240 строк)
    main.py          # NetBoxSync: объединяет всё (~90 строк)
```

Каждый файл можно читать и модифицировать независимо.

---

## 9. Когда Mixins НЕ подходят

### Diamond Problem (ромбовидное наследование)

Если два mixin наследуются от общего класса (не object), возникает конфликт:

```python
# ПРОБЛЕМА: два mixin зависят друг от друга
class MixinA(SharedBase):
    def process(self): ...

class MixinB(SharedBase):
    def process(self): ...     # Конфликт! Кто вызовется?

class MyClass(MixinA, MixinB): ...  # MRO разрулит, но это неочевидно
```

В нашем проекте проблемы нет: mixins не наследуются ни от чего (кроме object),
и не имеют пересекающихся имён методов.

### Подмена реализации в runtime

```python
# С Composition можно подменить реализацию:
sync.interfaces = MockInterfaceService()  # подменили в runtime

# С Mixins — нельзя подменить один mixin в runtime
```

### Языки без множественного наследования

Java, C#, Go не поддерживают множественное наследование.
Там используют интерфейсы + композицию (или трейты в Scala/Rust).

### Слишком много mixins (>10)

Когда mixins > 10, MRO становится длинным и неочевидным.
Отладка `super()` вызовов превращается в головоломку.

В нашем проекте 6 sync-mixins — это комфортное количество.

---

## 10. Вопросы для самопроверки (собеседование)

### Q1: Что такое Mixin и чем отличается от обычного наследования?

**A:** Mixin — класс с методами, но без собственного `__init__` и состояния.
Обычное наследование моделирует отношение IS-A (Собака ЯВЛЯЕТСЯ Животным).
Mixin моделирует CAN-DO (класс УМЕЕТ синхронизировать интерфейсы).
Mixin подмешивает поведение, а не определяет сущность.

### Q2: Почему SyncBase стоит ПОСЛЕДНИМ в списке наследования?

**A:** Из-за MRO (Method Resolution Order). Python ищет методы слева направо:
`NetBoxSync -> InterfacesSyncMixin -> CablesSyncMixin -> ... -> SyncBase -> object`.
Если SyncBase будет первым, его `__init__` найдётся раньше, а методы mixins
могут быть «перекрыты» утилитами из базового класса (если имена совпадут).
Базовый класс должен быть «последней инстанцией» для поиска методов.

### Q3: Как mixins видят общее состояние?

**A:** Все mixins используют `self`, который является экземпляром `NetBoxSync`.
В runtime `self` — это один объект, созданный через `NetBoxSync(client, dry_run=True)`.
`SyncBase.__init__` создаёт атрибуты (`self.client`, `self.dry_run`, `self._device_cache`),
и все mixins обращаются к ним через тот же `self`.

### Q4: Что такое MRO и как его посмотреть?

**A:** MRO (Method Resolution Order) — порядок, в котором Python ищет метод
в цепочке наследования. Алгоритм C3-линеаризации гарантирует
предсказуемый порядок. Посмотреть можно так:

```python
print(NetBoxSync.__mro__)
# (NetBoxSync, InterfacesSyncMixin, CablesSyncMixin, IPAddressesSyncMixin,
#  DevicesSyncMixin, VLANsSyncMixin, InventorySyncMixin, SyncBase, object)
```

### Q5: Как mixin знает о `self.client`, если у него нет `__init__`?

**A:** Mixin не знает на уровне runtime. Он **доверяет**, что к моменту вызова
его метода, `self` уже будет иметь атрибуты из SyncBase (потому что
конструктор NetBoxSync вызывает `super().__init__()`, который вызывает
`SyncBase.__init__()`). Для IDE и type-checker мы добавляем аннотацию
`self: SyncBase` — это подсказка, что self имеет атрибуты SyncBase.

### Q6: Почему не Composition / DI?

**A:** Три главные причины:
1. **Общие кэши** — 5 словарей-кэшей используются разными операциями.
   С Composition нужен отдельный CacheService и DI для его передачи.
2. **Python-идиоматично** — Django, DRF, stdlib используют тот же паттерн.
   Python-разработчики привыкли к mixins.
3. **Простота** — один объект, один конструктор, плоский API
   (`sync.sync_interfaces()` вместо `sync.interfaces.sync()`).

### Q7: Как тестировать mixin в изоляции?

**A:** Создаём объект через MagicMock с привязкой нужных атрибутов:

```python
from unittest.mock import MagicMock
from netbox.sync.interfaces import InterfacesSyncMixin

# Вариант 1: MagicMock с нужными атрибутами
sync = MagicMock(spec=SyncBase)
sync.client = MagicMock()
sync.dry_run = False
sync._device_cache = {}

# Привязка метода mixin к mock-объекту
sync._build_update_data = lambda nb, intf, **kw: \
    InterfacesSyncMixin._build_update_data(sync, nb, intf, **kw)
```

Или создаём минимальный тестовый класс:

```python
class TestableSync(InterfacesSyncMixin, SyncBase):
    pass

sync = TestableSync(client=mock_client, dry_run=True)
sync.sync_interfaces("switch-01", test_interfaces)
```

### Q8: Какие проблемы могут быть с Mixins?

**A:**
1. **Неочевидный MRO** — при >10 mixins сложно предсказать порядок поиска методов.
2. **Неявные зависимости** — mixin использует `self.client`, но это не видно
   в его определении класса (только через аннотацию `self: SyncBase`).
3. **Конфликты имён** — если два mixin определят метод с одним именем,
   вызовется только первый (по MRO). Ошибки не будет, но поведение неожиданное.
4. **Невозможность подмены в runtime** — нельзя заменить один mixin на другой
   без создания нового класса.

### Q9: Как добавить новый sync-функционал в проект?

**A:** Три шага:
1. Создать файл `netbox/sync/new_feature.py` с классом `NewFeatureSyncMixin`
2. Определить методы с аннотацией `self: SyncBase`
3. Добавить mixin в `NetBoxSync` в файле `main.py`:

```python
class NetBoxSync(
    InterfacesSyncMixin,
    CablesSyncMixin,
    NewFeatureSyncMixin,   # <-- новый mixin
    SyncBase,
): ...
```

### Q10: В чём разница между client mixins и sync mixins?

**A:** Обе группы используют паттерн mixins, но на разных уровнях:
- **Client mixins** — CRUD-операции с NetBox API (низкий уровень: `get_interfaces`,
  `bulk_create_interfaces`). Зависят от `NetBoxClientBase.api` (pynetbox).
- **Sync mixins** — бизнес-логика синхронизации (высокий уровень: `sync_interfaces`).
  Зависят от `SyncBase.client` (который является NetBoxClient), `SyncBase.dry_run`,
  кэшей и утилит.

Sync mixins вызывают client mixins:
```
sync.sync_interfaces()           # InterfacesSyncMixin
  -> self.client.get_interfaces()  # InterfacesMixin (client)
  -> self.client.bulk_create_interfaces()  # InterfacesMixin (client)
```

---

## Итого

Mixins в нашем проекте — это способ разбить ~2500 строк sync-кода на 6 логических
файлов, сохранив **единый объект** с **общими кэшами** и **простым API**.

Ключевые идеи:
1. Mixin = поведение без состояния (CAN-DO, не IS-A)
2. Базовый класс последний (MRO), содержит `__init__` и общее состояние
3. Аннотация `self: SyncBase` делает код понятным для IDE и type-checker
4. Mixins не зависят друг от друга, только от базового класса
5. Паттерн Python-идиоматичен: Django, DRF, stdlib используют его же
