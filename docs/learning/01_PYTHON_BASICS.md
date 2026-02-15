# 01. Python-концепции в проекте Network Collector

## Что ты уже знаешь

Из книги по основам Python ты знаешь: переменные, циклы, функции, базовые классы с `__init__`. Этого достаточно, чтобы написать простой скрипт подключения к коммутатору.

## Что узнаешь здесь

В реальном проекте используются возможности Python, которые в книгах для начинающих обычно пропускают. Здесь ты узнаешь:

- Как словари используются для хранения результатов и настроек
- Как одной строкой создать список или словарь (comprehensions)
- Как `@dataclass` избавляет от рутинного кода
- Зачем нужны type hints и как их читать
- Как наследование и mixin-классы помогают организовать код
- Как работает `with` и `try/except`
- Как устроены модули и импорты в Python-проекте

Каждый раздел: объяснение простым языком, пример из проекта, ссылка на файл.

---

## 1. Словари как основа данных

### Теория

Словарь (`dict`) -- это хранилище "ключ: значение". В сетевой автоматизации словари используются повсюду: данные с устройства приходят как словарь, результаты синхронизации -- словарь, настройки -- тоже словарь.

Важные приёмы:
- **`Dict[str, Any]`** -- словарь, где ключи -- строки, а значения -- что угодно (число, строка, другой словарь)
- **Вложенные словари** -- словарь внутри словаря
- **`.get()` с дефолтом** -- безопасное чтение: если ключа нет, вернёт значение по умолчанию вместо ошибки

### Пример из проекта

Результат синхронизации интерфейсов хранится в словаре:

```python
# netbox/sync/interfaces.py — sync_interfaces() возвращает такой словарь
stats = {"created": 0, "updated": 0, "deleted": 0, "skipped": 0}
details = {"create": [], "update": [], "delete": [], "skip": []}

# После работы:
# stats = {"created": 5, "updated": 3, "deleted": 0, "skipped": 12}
# details = {"create": [{"name": "GigabitEthernet0/1"}, ...], ...}
```

Безопасное чтение с `.get()`:

```python
# Если ключа "hostname" нет в словаре, вернётся пустая строка
hostname = data.get("hostname", "")

# Без .get() при отсутствии ключа будет ошибка KeyError:
# hostname = data["hostname"]  # KeyError если ключа нет!
```

Вложенные словари -- когда значение само является словарём:

```python
# Кэш интерфейсов: device_id -> {имя_интерфейса: объект_интерфейса}
self._interface_cache: Dict[int, Dict[str, Any]] = {}

# Добавляем данные:
# self._interface_cache[42] = {"GigabitEthernet0/1": <interface_obj>, ...}

# Читаем:
# cache = self._interface_cache[42]
# intf = cache["GigabitEthernet0/1"]
```

### Где это в проекте

- `netbox/sync/interfaces.py` -- stats и details словари
- `netbox/sync/base.py` -- кэши `_device_cache`, `_interface_cache`
- `core/pipeline/executor.py` -- результаты pipeline

---

## 2. List comprehensions и dict comprehensions

### Теория

Comprehension -- это способ создать список или словарь одной строкой вместо цикла. Это не магия, а просто короткая запись того же `for`.

Обычный цикл:
```python
# Создаём список имён из списка интерфейсов
names = []
for intf in interfaces:
    names.append(intf.name)
```

То же самое через list comprehension:
```python
names = [intf.name for intf in interfaces]
```

Dict comprehension -- то же самое, но создаёт словарь:
```python
# Словарь {имя: объект} из списка интерфейсов
cache = {intf.name: intf for intf in interfaces}
```

Можно добавить условие:
```python
# Только интерфейсы со статусом "up"
active = [intf for intf in interfaces if intf.status == "up"]
```

### Пример из проекта

Кэширование интерфейсов устройства -- загружаем список, превращаем в словарь для быстрого поиска по имени:

```python
# netbox/sync/base.py — _find_interface()
interfaces = self.client.get_interfaces(device_id=device_id)
self._interface_cache[device_id] = {intf.name: intf for intf in interfaces}

# Теперь вместо перебора всего списка:
#   for intf in interfaces:
#       if intf.name == "GigabitEthernet0/1":
#           return intf
# Можно найти мгновенно:
#   cache["GigabitEthernet0/1"]
```

Конвертация списка словарей в список моделей:

```python
# core/models.py — interfaces_from_dicts()
def interfaces_from_dicts(data: List[Dict[str, Any]]) -> Interfaces:
    """Конвертирует список словарей в список Interface."""
    return [Interface.from_dict(d) for d in data]
```

Фильтрация с условием -- метод `to_dict()` убирает пустые поля:

```python
# core/models.py — InventoryItem.to_dict()
def to_dict(self) -> Dict[str, Any]:
    """Конвертирует в словарь."""
    return {k: v for k, v in asdict(self).items() if v}
    # Оставляет только непустые поля:
    # {"name": "PSU 1", "serial": "ABC123"}
    # Убирает: {"pid": "", "vid": "", ...}
```

### Где это в проекте

- `netbox/sync/base.py` строка 125 -- `{intf.name: intf for intf in interfaces}`
- `core/models.py` строка 130 -- `{k: v for k, v in asdict(self).items() if v}`
- `core/models.py` строка 441 -- `[Interface.from_dict(d) for d in data]`

---

## 3. Dataclass

### Теория

Когда создаёшь класс для хранения данных, приходится писать много однотипного кода: `__init__`, присваивание атрибутов, иногда `__repr__`. Декоратор `@dataclass` делает это автоматически.

Без dataclass:
```python
class Interface:
    def __init__(self, name="", description="", status="unknown", ip_address=""):
        self.name = name
        self.description = description
        self.status = status
        self.ip_address = ip_address
```

С dataclass -- то же самое, но короче:
```python
from dataclasses import dataclass

@dataclass
class Interface:
    name: str = ""
    description: str = ""
    status: str = "unknown"
    ip_address: str = ""
```

Оба варианта работают одинаково: `intf = Interface(name="Gi0/1", status="up")`.

Что делает `@dataclass`:
- Автоматически создаёт `__init__` по полям класса
- Автоматически создаёт `__repr__` (красивый вывод при `print`)
- Автоматически создаёт `__eq__` (сравнение объектов)
- Значения по умолчанию (`= ""`) означают: если не передал -- будет пустая строка

### Пример из проекта

Модель интерфейса (упрощённо):

```python
# core/models.py
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Any, Dict

@dataclass
class Interface:
    name: str                     # Обязательное поле (нет значения по умолчанию)
    description: str = ""         # Необязательное, по умолчанию ""
    status: str = "unknown"       # Необязательное, по умолчанию "unknown"
    ip_address: str = ""
    mtu: Optional[int] = None     # Может быть числом или None (отсутствует)
    speed: str = ""
    hostname: str = ""
    device_ip: str = ""
```

Метод `from_dict()` -- создание объекта из словаря. Это classmethod (метод класса), который принимает словарь и возвращает объект:

```python
@classmethod
def from_dict(cls, data: Dict[str, Any]) -> "Interface":
    """Создаёт Interface из словаря."""
    return cls(
        name=data.get("interface") or data.get("name") or "",
        description=data.get("description") or "",
        status=data.get("status") or data.get("link_status") or "unknown",
        ip_address=data.get("ip_address") or "",
        # ...
    )
```

Зачем `from_dict()`? Данные с устройства приходят как словари (от парсера NTC Templates). Нам нужно превратить словарь в объект:

```python
# Словарь от парсера
raw = {"interface": "GigabitEthernet0/1", "link_status": "up", "ip_address": "10.0.0.1"}

# Превращаем в объект Interface
intf = Interface.from_dict(raw)

# Теперь можно обращаться к полям через точку
print(intf.name)        # "GigabitEthernet0/1"
print(intf.status)      # "up"
print(intf.ip_address)  # "10.0.0.1"
```

Метод `to_dict()` -- обратная операция, превращает объект в словарь:

```python
def to_dict(self) -> Dict[str, Any]:
    """Конвертирует в словарь."""
    result = {k: v for k, v in asdict(self).items() if v is not None and v != ""}
    return result
```

Функция `asdict()` из модуля `dataclasses` превращает dataclass-объект в обычный словарь.

### Где это в проекте

- `core/models.py` -- все модели данных: Interface, MACEntry, LLDPNeighbor, InventoryItem, IPAddressEntry, DeviceInfo
- `core/pipeline/executor.py` -- StepResult и PipelineResult
- `core/domain/sync.py` -- FieldChange и SyncDiff

---

## 4. Type hints (подсказки типов)

### Теория

Type hints -- это подсказки для Python и IDE о том, какие типы данных ожидает функция. Python их **не проверяет** при выполнении -- это просто документация для людей и инструментов.

```python
# Без type hints -- непонятно, что принимает и возвращает
def find_device(name):
    ...

# С type hints -- сразу видно: принимает строку, возвращает объект или None
def find_device(name: str) -> Optional[Any]:
    ...
```

Основные типы:

| Тип | Значение | Пример |
|-----|----------|--------|
| `str` | Строка | `name: str` |
| `int` | Целое число | `count: int` |
| `bool` | True или False | `dry_run: bool` |
| `List[str]` | Список строк | `names: List[str]` |
| `Dict[str, Any]` | Словарь (ключи строки, значения любые) | `data: Dict[str, Any]` |
| `Optional[str]` | Строка или None | `ip: Optional[str] = None` |
| `Any` | Что угодно | `result: Any` |
| `Tuple[str, int]` | Кортеж из строки и числа | `pair: Tuple[str, int]` |

`Optional[X]` -- это то же самое, что `X` или `None`. Используется когда значение может отсутствовать:

```python
# Функция может вернуть устройство, а может вернуть None (если не нашла)
def _find_device(self, name: str) -> Optional[Any]:
    device = self.client.get_device_by_name(name)
    if device:
        return device
    return None  # Не нашли
```

### Пример из проекта

Объявление кэша с типами:

```python
# netbox/sync/base.py
self._device_cache: Dict[str, Any] = {}
# Ключ -- строка (имя устройства), значение -- что угодно (объект NetBox)

self._vlan_cache: Dict[Tuple[int, str], Any] = {}
# Ключ -- кортеж (номер VLAN, имя сайта), значение -- объект VLAN
```

Сигнатура функции синхронизации:

```python
# netbox/sync/interfaces.py
def sync_interfaces(
    self: SyncBase,
    device_name: str,              # Имя устройства (строка)
    interfaces: List[Interface],   # Список объектов Interface
    create_missing: Optional[bool] = None,  # True/False/None
    update_existing: Optional[bool] = None,
    cleanup: bool = False,         # По умолчанию False
) -> Dict[str, Any]:              # Возвращает словарь со статистикой
```

Читая эту сигнатуру, ты сразу понимаешь:
- Функция принимает имя устройства и список интерфейсов
- `create_missing` можно не передавать (будет `None`, и функция сама решит)
- Возвращает словарь вроде `{"created": 5, "updated": 3, ...}`

### Где это в проекте

- `netbox/sync/base.py` -- type hints на кэшах и методах
- `core/models.py` -- type hints на полях dataclass
- `collectors/base.py` -- сигнатуры методов collect, _parse_output

---

## 5. Классы и наследование

### Теория

Наследование -- когда один класс получает все методы и атрибуты другого. Это позволяет написать общий код один раз, а потом переиспользовать.

```python
# Базовый класс -- общая логика
class BaseCollector:
    def __init__(self, credentials):
        self.credentials = credentials

    def connect(self, device):
        # Общий код подключения
        ...

    def collect(self, devices):
        # Общая логика сбора
        for device in devices:
            self.connect(device)
            data = self._parse_output(output, device)
            ...

# Наследник -- только то, что отличается
class MACCollector(BaseCollector):
    command = "show mac address-table"

    def _parse_output(self, output, device):
        # Свой парсинг для MAC-таблицы
        ...
```

`super().__init__()` -- вызов `__init__` родителя. Нужен, чтобы инициализация базового класса тоже выполнилась:

```python
class NetBoxSync(SyncBase):
    def __init__(self, client, dry_run=False):
        # Сначала инициализируем базовый класс
        super().__init__(client=client, dry_run=dry_run)
        # Потом свои атрибуты (если есть)
```

Переопределение метода -- наследник может заменить метод родителя своей версией. Например, `_parse_output` в `BaseCollector` -- абстрактный (пустой), каждый наследник реализует его по-своему.

### Пример из проекта

Базовый коллектор и его наследники:

```python
# collectors/base.py
class BaseCollector(ABC):
    """Абстрактный базовый класс для всех коллекторов."""

    command: str = ""  # Команда (переопределяется в наследниках)

    def collect(self, devices):
        """Общая логика сбора данных."""
        for device in devices:
            data = self._collect_from_device(device)
            ...

    @abstractmethod
    def _parse_output(self, output, device):
        """Должен быть реализован в наследниках."""
        pass


# collectors/mac.py
class MACCollector(BaseCollector):
    """Коллектор MAC-адресов. Наследует всю логику подключения и сбора."""

    command = "show mac address-table"  # Своя команда

    def _parse_output(self, output, device):
        """Свой парсинг для MAC-таблицы."""
        # Специфичный код для MAC
        ...
```

Что здесь происходит:
1. `BaseCollector` содержит логику подключения, выполнения команд, параллельного сбора
2. `MACCollector` наследует всё это и добавляет только свою команду и парсинг
3. Аналогично работают `DeviceCollector`, `LLDPCollector`, `InterfaceCollector`

### Где это в проекте

- `collectors/base.py` -- BaseCollector (базовый класс)
- `collectors/mac.py` -- MACCollector (наследник)
- `collectors/device.py` -- DeviceCollector (наследник)
- `collectors/lldp.py` -- LLDPCollector (наследник)
- `collectors/interfaces.py` -- InterfaceCollector (наследник)

---

## 6. Mixin-классы

### Теория

Mixin -- это класс, который добавляет набор методов к другому классу. Он не предназначен для использования сам по себе. Это способ разбить большой класс на логические части.

Аналогия: представь сетевого инженера. У него есть "навыки":
- Умеет настраивать интерфейсы
- Умеет настраивать кабели
- Умеет настраивать IP-адреса
- Умеет настраивать VLAN

Каждый "навык" -- это mixin. Инженер (класс) "наследует" все навыки.

В Python класс может наследовать от нескольких классов одновременно (множественное наследование):

```python
class NetBoxSync(InterfacesMixin, CablesMixin, IPAddressesMixin, SyncBase):
    pass
```

Теперь `NetBoxSync` имеет все методы из всех mixin-классов. При этом каждый mixin лежит в отдельном файле, и код легко читать.

### Пример из проекта

Класс `NetBoxSync` собирается из 6 mixin-классов и базового класса:

```python
# netbox/sync/main.py
class NetBoxSync(
    InterfacesSyncMixin,    # sync_interfaces() — синхронизация интерфейсов
    CablesSyncMixin,        # sync_cables_from_lldp() — синхронизация кабелей
    IPAddressesSyncMixin,   # sync_ip_addresses() — синхронизация IP
    DevicesSyncMixin,       # create_device(), sync_devices_from_inventory()
    VLANsSyncMixin,         # sync_vlans_from_interfaces()
    InventorySyncMixin,     # sync_inventory() — синхронизация inventory
    SyncBase,               # Базовый класс: кэш, _find_device(), _batch_with_fallback()
):
    """Синхронизация данных с NetBox."""

    def __init__(self, client, dry_run=False, ...):
        super().__init__(client=client, dry_run=dry_run, ...)
```

Каждый mixin -- отдельный файл с одним классом:

```python
# netbox/sync/interfaces.py
class InterfacesSyncMixin:
    """Mixin для синхронизации интерфейсов."""

    def sync_interfaces(self, device_name, interfaces, ...):
        # Использует методы из SyncBase: self._find_device(), self.client, ...
        device = self._find_device(device_name)
        ...
```

Mixin использует `self` для доступа к атрибутам базового класса (`self.client`, `self.dry_run`, `self._find_device()`). Это работает потому, что в итоговом классе `NetBoxSync` есть и mixin-методы, и атрибуты SyncBase.

Зачем так делать? Без mixin весь код синхронизации был бы в одном файле на 2000+ строк. С mixin каждая часть -- в своём файле по 100-300 строк. Легче читать, легче менять.

### Где это в проекте

- `netbox/sync/main.py` -- NetBoxSync (объединяет все mixin)
- `netbox/sync/interfaces.py` -- InterfacesSyncMixin
- `netbox/sync/cables.py` -- CablesSyncMixin
- `netbox/sync/ip_addresses.py` -- IPAddressesSyncMixin
- `netbox/sync/devices.py` -- DevicesSyncMixin
- `netbox/sync/vlans.py` -- VLANsSyncMixin
- `netbox/sync/inventory.py` -- InventorySyncMixin
- `netbox/sync/base.py` -- SyncBase (базовый класс)

---

## 7. Менеджер контекста (with)

### Теория

Конструкция `with` гарантирует, что ресурс будет корректно закрыт/освобождён, даже если произошла ошибка. Это называется "менеджер контекста".

Без `with`:
```python
file = open("config.txt")
data = file.read()
file.close()  # Легко забыть! А если ошибка на строке выше -- close() не вызовется
```

С `with`:
```python
with open("config.txt") as file:
    data = file.read()
# file.close() вызывается автоматически при выходе из блока with
# Даже если внутри блока произошла ошибка!
```

`with` используется для любых ресурсов, которые нужно закрывать: файлы, сетевые соединения, пулы потоков.

### Пример из проекта

Подключение к сетевому устройству:

```python
# collectors/base.py — _collect_from_device()
with self._conn_manager.connect(device, self.credentials) as conn:
    # conn -- SSH-соединение с устройством
    hostname = self._conn_manager.get_hostname(conn)
    response = conn.send_command(command)
    output = response.result
# Соединение автоматически закрывается при выходе из блока with
# Даже если send_command() бросит ошибку -- соединение будет закрыто
```

Параллельный сбор данных с нескольких устройств:

```python
# collectors/base.py — _collect_parallel()
with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
    # executor -- пул из max_workers потоков
    futures = {
        executor.submit(self._collect_from_device, device): device
        for device in devices
    }
    for future in as_completed(futures):
        data = future.result()
        ...
# При выходе из блока: ждём завершения всех потоков, потом очищаем пул
```

`ThreadPoolExecutor` -- это пул потоков. Он позволяет подключаться к нескольким устройствам одновременно (параллельно), а не по одному. `with` гарантирует, что пул будет корректно завершён.

### Где это в проекте

- `collectors/base.py` строка 264 -- `with ThreadPoolExecutor(...) as executor:`
- `collectors/base.py` строка 309 -- `with self._conn_manager.connect(...) as conn:`

---

## 8. try/except -- обработка ошибок

### Теория

`try/except` позволяет перехватить ошибку и обработать её вместо того, чтобы программа упала.

```python
try:
    # Пытаемся выполнить код
    result = risky_operation()
except SomeError as e:
    # Если произошла ошибка SomeError -- обрабатываем
    print(f"Ошибка: {e}")
except Exception as e:
    # Если произошла любая другая ошибка
    print(f"Неизвестная ошибка: {e}")
```

Важно:
- `except SomeError` -- ловит только конкретный тип ошибки
- `except Exception` -- ловит почти все ошибки (используй как "сеть безопасности")
- `as e` -- сохраняет ошибку в переменную для логирования

### Пример из проекта

Batch с fallback -- пытаемся отправить данные одним запросом, если не получилось -- по одному:

```python
# netbox/sync/base.py — _batch_with_fallback()
try:
    # Пытаемся создать все интерфейсы одним batch-запросом
    result = bulk_fn(batch_data)
    # Если успешно -- считаем статистику
    for name in item_names:
        stats[operation] = stats.get(operation, 0) + 1
    return result

except Exception as e:
    # Batch не удался -- переходим на поштучную обработку
    logger.warning(f"Batch {operation} не удался ({e}), fallback на поштучную обработку")

    for data, name in zip(batch_data, item_names):
        try:
            # Пытаемся создать каждый интерфейс отдельно
            fallback_fn(data, name)
            stats[operation] = stats.get(operation, 0) + 1
        except Exception as exc:
            # Если и поштучно не получилось -- логируем и идём дальше
            logger.error(f"Ошибка {operation} {name}: {exc}")
            stats["failed"] = stats.get("failed", 0) + 1
```

Зачем так сложно? Представь: ты синхронизируешь 100 интерфейсов. Batch-запрос отправляет все 100 за один раз (быстро). Но если хотя бы в одном интерфейсе ошибка -- весь batch падает. Fallback пробует каждый по отдельности: 99 создадутся, 1 упадёт -- лучше, чем потерять все 100.

Обработка ошибок подключения к устройству:

```python
# collectors/base.py — _collect_from_device()
try:
    with self._conn_manager.connect(device, self.credentials) as conn:
        response = conn.send_command(command)
        return self._parse_output(response.result, device)

except (ConnectionError, AuthenticationError, TimeoutError) as e:
    # Известные ошибки подключения -- логируем и продолжаем
    device.status = DeviceStatus.ERROR
    logger.error(f"Ошибка подключения к {device.host}: {e}")
    return []  # Пустой результат -- устройство пропускается

except Exception as e:
    # Неизвестная ошибка -- тоже логируем и продолжаем
    device.status = DeviceStatus.ERROR
    logger.error(f"Неизвестная ошибка с {device.host}: {e}")
    return []
```

Два уровня `except`:
1. Сначала ловим **конкретные** ошибки (`ConnectionError`, `AuthenticationError`) -- мы знаем что это и как обработать
2. Потом ловим **всё остальное** (`Exception`) -- на всякий случай, чтобы программа не упала

### Где это в проекте

- `netbox/sync/base.py` строка 356 -- `_batch_with_fallback()` (batch + fallback)
- `collectors/base.py` строка 330 -- обработка ошибок подключения
- `netbox/sync/base.py` строка 246 -- `_get_or_create()` (get-or-create с обработкой ошибок)

---

## 9. Модули и импорты

### Теория

В Python каждый `.py` файл -- это модуль. Папка с файлом `__init__.py` -- это пакет (набор модулей). Импорты позволяют использовать код из других файлов.

Три вида импортов:

```python
# 1. Абсолютный импорт -- полный путь от корня проекта
from network_collector.netbox.sync import NetBoxSync

# 2. Относительный импорт -- путь относительно текущего файла
from .base import SyncBase          # Файл base.py в той же папке
from ..client import NetBoxClient   # Папка client на уровень выше
from ...core.models import Interface  # Три уровня вверх, потом core/models

# 3. Импорт конкретных имён
from typing import List, Dict, Any, Optional
```

Точки в относительных импортах:
- `.` -- текущая папка
- `..` -- папка на уровень выше
- `...` -- на два уровня выше

Файл `__init__.py` делает папку пакетом и определяет, что доступно при импорте:

```python
# netbox/sync/__init__.py
from .main import NetBoxSync

__all__ = ["NetBoxSync"]

# Теперь можно импортировать так:
# from network_collector.netbox.sync import NetBoxSync
# Вместо:
# from network_collector.netbox.sync.main import NetBoxSync
```

### Пример из проекта

Структура модуля `netbox/sync/`:

```
netbox/sync/
    __init__.py         # Экспортирует NetBoxSync
    main.py             # Главный класс NetBoxSync
    base.py             # Базовый класс SyncBase
    interfaces.py       # InterfacesSyncMixin
    cables.py           # CablesSyncMixin
    ip_addresses.py     # IPAddressesSyncMixin
    devices.py          # DevicesSyncMixin
    vlans.py            # VLANsSyncMixin
    inventory.py        # InventorySyncMixin
```

Как модули импортируют друг друга:

```python
# netbox/sync/interfaces.py — импорты
from .base import (                          # Из файла base.py в этой же папке
    SyncBase, SyncComparator, Interface,
    get_sync_config, normalize_mac_netbox,
)
from ...core.domain.vlan import parse_vlan_range, VlanSet
#    ^^^--- три уровня вверх (sync -> netbox -> network_collector),
#           потом core/domain/vlan.py
```

Пакет `collectors/` экспортирует все коллекторы через `__init__.py`:

```python
# collectors/__init__.py
from .base import BaseCollector
from .mac import MACCollector
from .device import DeviceCollector
from .lldp import LLDPCollector
from .interfaces import InterfaceCollector

__all__ = ["BaseCollector", "MACCollector", "DeviceCollector", ...]

# Теперь пользователь может написать:
# from network_collector.collectors import MACCollector
# Вместо:
# from network_collector.collectors.mac import MACCollector
```

### Где это в проекте

- `netbox/sync/__init__.py` -- экспорт NetBoxSync
- `collectors/__init__.py` -- экспорт всех коллекторов
- `netbox/sync/base.py` строки 10-36 -- пример множественных импортов

---

## 10. Полезные паттерны

### Кэширование -- "запомнить, чтобы не спрашивать дважды"

Если операция дорогая (сетевой запрос к API), результат сохраняем в словарь. При повторном вызове -- берём из словаря.

```python
# netbox/sync/base.py — _find_device()
def _find_device(self, name: str) -> Optional[Any]:
    """Находит устройство в NetBox (с кэшированием)."""

    # 1. Сначала проверяем кэш
    if name in self._device_cache:
        return self._device_cache[name]

    # 2. Если нет в кэше -- делаем запрос к API
    device = self.client.get_device_by_name(name)

    # 3. Сохраняем в кэш для следующего раза
    if device:
        self._device_cache[name] = device

    return device
```

Без кэширования: синхронизация 100 интерфейсов одного устройства = 100 запросов `get_device_by_name()`. С кэшированием: 1 запрос, остальные 99 из словаря.

### None-проверки -- "сначала проверь, потом работай"

Многие функции могут вернуть `None` (например, устройство не найдено). Важно проверить это перед использованием:

```python
# netbox/sync/inventory.py
device = self._find_device(device_name)
if not device:
    logger.error(f"Устройство не найдено в NetBox: {device_name}")
    stats["failed"] = 1
    return stats  # Выходим из функции, дальше работать бессмысленно

# Здесь device точно не None -- можно безопасно использовать
device_id = device.id
```

Без этой проверки: `device.id` при `device = None` вызовет `AttributeError` и программа упадёт.

### `.get()` с дефолтом -- "если нет -- возьми запасное"

```python
# Вместо:
if "hostname" in data:
    hostname = data["hostname"]
else:
    hostname = ""

# Пишем:
hostname = data.get("hostname", "")

# Или с цепочкой or -- попробовать несколько ключей:
name = data.get("interface") or data.get("name") or ""
# Если "interface" есть -- берём его
# Если нет -- пробуем "name"
# Если и его нет -- пустая строка
```

Этот паттерн особенно полезен при работе с данными от разных вендоров -- одно и то же поле может называться по-разному (Cisco: "interface", Juniper: "name").

### Где это в проекте

- `netbox/sync/base.py` строки 91-107 -- `_find_device()` с кэшированием
- `netbox/sync/base.py` строки 109-139 -- `_find_interface()` с кэшированием
- `netbox/sync/inventory.py` строки 45-50 -- None-проверка устройства
- `core/models.py` строки 103-126 -- `.get()` с дефолтом и цепочкой `or`

---

## 11. @property -- вычисляемые атрибуты

### Теория

Декоратор `@property` превращает метод в атрибут. Снаружи он выглядит как обычное поле (без скобок), но внутри выполняется код. Это удобно для:

- **Вычисляемых значений** -- значение считается из других полей
- **Только для чтения** -- нельзя случайно присвоить неправильное значение
- **Всегда актуально** -- пересчитывается при каждом обращении

```python
# Без @property -- нужно вызывать как метод (со скобками)
total = diff.total_changes()

# С @property -- выглядит как обычное поле
total = diff.total_changes   # Без скобок!
```

### Пример из проекта

В `SyncDiff` два вычисляемых атрибута -- `total_changes` и `has_changes`:

```python
# core/domain/sync.py — SyncDiff
@dataclass
class SyncDiff:
    to_create: List[SyncItem] = field(default_factory=list)
    to_update: List[SyncItem] = field(default_factory=list)
    to_delete: List[SyncItem] = field(default_factory=list)

    @property
    def total_changes(self) -> int:
        """Общее количество изменений."""
        return len(self.to_create) + len(self.to_update) + len(self.to_delete)

    @property
    def has_changes(self) -> bool:
        """Есть ли изменения."""
        return self.total_changes > 0
```

Использование -- без скобок, как обычное поле:

```python
diff = comparator.compare_interfaces(local, remote)

if diff.has_changes:                        # Как поле, не как метод
    print(f"Изменений: {diff.total_changes}")  # Тоже как поле
```

Почему не хранить `total_changes` как обычное поле? Потому что списки `to_create`, `to_update`, `to_delete` могут меняться после создания объекта. Обычное поле устареет, а `@property` всегда вернёт актуальное значение.

### Где это в проекте

- `core/domain/sync.py` строки 147-155 -- `SyncDiff.total_changes` и `SyncDiff.has_changes`

---

## 12. Enum -- именованные константы

### Теория

`Enum` -- это набор именованных констант. Вместо "магических строк" (`"create"`, `"update"`) используются имена (`ChangeType.CREATE`, `ChangeType.UPDATE`).

Проблема с обычными строками:
```python
# Легко опечататься: "craete" вместо "create" -- и ошибку не найдёшь
status = "craete"   # Тихо работает с ошибкой!
```

С Enum:
```python
# Опечатка вызовет ошибку сразу
status = ChangeType.CRAETE  # AttributeError! Такого значения нет
```

### Пример из проекта

Типы изменений при синхронизации:

```python
# core/domain/sync.py
from enum import Enum

class ChangeType(str, Enum):
    """Тип изменения."""
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    SKIP = "skip"
```

Статусы шагов в pipeline:

```python
# core/pipeline/models.py
class StepType(str, Enum):
    """Тип шага pipeline."""
    COLLECT = "collect"
    SYNC = "sync"
    EXPORT = "export"

class StepStatus(str, Enum):
    """Статус выполнения шага."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
```

Трюк `(str, Enum)` -- наследование от `str` и `Enum` одновременно. Это позволяет сериализовать значение в JSON. Без `str` при `json.dumps(ChangeType.CREATE)` была бы ошибка. С `str` результат будет `"create"`.

Использование:
```python
# Сравнение
if item.change_type == ChangeType.CREATE:
    print(f"+ {item.name}")

# В to_dict() -- .value возвращает строку
{"change_type": item.change_type.value}  # "create"
```

### Где это в проекте

- `core/domain/sync.py` строка 64 -- `ChangeType(str, Enum)`
- `core/pipeline/models.py` строки 19, 26 -- `StepType`, `StepStatus`

---

## 13. Logging -- вместо print()

### Теория

`logging` -- стандартный модуль Python для вывода сообщений. В отличие от `print()`, он:

- **Уровни** -- можно фильтровать: показать только ошибки, или всё включая debug
- **Формат** -- автоматически добавляет время, имя модуля, уровень
- **Вывод** -- можно писать в файл, в консоль, или и туда и туда

Уровни (от самого тихого до самого громкого):

| Уровень | Когда использовать |
|---------|-------------------|
| `DEBUG` | Детали для отладки (обычно скрыты) |
| `INFO` | Важные события: "Создан интерфейс", "Подключено к устройству" |
| `WARNING` | Что-то не так, но работа продолжается |
| `ERROR` | Ошибка, операция не удалась |

### Пример из проекта

Создание логгера и использование:

```python
# netbox/sync/interfaces.py
import logging

logger = logging.getLogger(__name__)
# __name__ = "network_collector.netbox.sync.interfaces"
# В логах видно, из какого модуля сообщение

# Использование в коде:
logger.info(f"Создан интерфейс: {name}")
logger.warning(f"Batch create не удался ({e}), fallback на поштучное создание")
logger.error(f"Ошибка создания интерфейса {intf.name}: {exc}")
logger.debug(f"Привязка {intf.name} к LAG {intf.lag} (id={lag_interface.id})")
```

В консоли это выглядит примерно так:
```
2024-01-15 10:30:15 INFO     Создан интерфейс: GigabitEthernet0/1
2024-01-15 10:30:16 WARNING  Batch create не удался, fallback на поштучное создание
2024-01-15 10:30:17 ERROR    Ошибка создания интерфейса Vlan99: ...
```

`print()` просто выводит текст. `logger.info()` добавляет время и уровень, что помогает при анализе логов.

### Где это в проекте

- `netbox/sync/interfaces.py` строки 8, 17 -- создание логгера
- `collectors/base.py` -- логирование подключений и ошибок
- `core/pipeline/executor.py` строка 13 -- логгер для pipeline

---

## 14. *args и **kwargs

### Теория

`*args` и `**kwargs` позволяют функции принимать произвольное количество аргументов:

- `*args` -- собирает **позиционные** аргументы в кортеж (tuple)
- `**kwargs` -- собирает **именованные** аргументы в словарь (dict)

```python
def example(*args, **kwargs):
    print(args)     # (1, 2, 3) -- кортеж
    print(kwargs)   # {"name": "test", "count": 5} -- словарь

example(1, 2, 3, name="test", count=5)
```

Главное применение -- **передача аргументов дальше** (pass-through).

### Пример из проекта

Метод `create_interface` принимает `**kwargs` для дополнительных параметров:

```python
# netbox/client/interfaces.py
def create_interface(
    self,
    device_id: int,
    name: str,
    interface_type: str = "1000base-t",
    description: str = "",
    enabled: bool = True,
    **kwargs,                # Все остальные параметры (mtu, speed, mode, lag, ...)
) -> Any:
    data = {
        "device": device_id,
        "name": name,
        "type": interface_type,
        "description": description,
        "enabled": enabled,
        **kwargs,            # Распаковываем kwargs в словарь
    }
    return self.api.dcim.interfaces.create(data)
```

Зачем? Если без `**kwargs`, пришлось бы перечислить ВСЕ возможные параметры API (их десятки). С `**kwargs` можно передать любые дополнительные поля.

### Где это в проекте

- `netbox/client/interfaces.py` строка 96 -- `create_interface(..., **kwargs)`
- `netbox/client/interfaces.py` строка 128 -- `update_interface(interface_id, **updates)`
- `netbox/client/inventory.py` строка 68 -- `create_inventory_item(..., **kwargs)`

---

## 15. Lambda -- анонимные функции

### Теория

Lambda -- это маленькая одноразовая функция, записанная в одну строку. Используется там, где нужна простая функция на один раз, обычно для сортировки или фильтрации.

```python
# Обычная функция
def get_name(item):
    return item.name

# То же самое через lambda
get_name = lambda item: item.name
```

Lambda удобна как аргумент `key=` для сортировки.

### Пример из проекта

Сортировка интерфейсов -- LAG первыми:

```python
# netbox/sync/interfaces.py — sync_interfaces()
# port_type заполняется нормализатором (detect_port_type) до вызова sync
sorted_interfaces = sorted(
    interface_models,
    key=lambda intf: 0 if intf.port_type == "lag" else 1,
)
```

Здесь lambda возвращает 0 для LAG (они сортируются первыми) и 1 для остальных.
`port_type` — поле модели `Interface`, заполненное domain layer'ом.

Lambda в fallback-обработке:

```python
# netbox/sync/interfaces.py — _batch_delete_interfaces()
self._batch_with_fallback(
    bulk_fn=self.client.bulk_delete_interfaces,
    fallback_fn=lambda item_id, name: self.client.api.dcim.interfaces.get(item_id).delete(),
    ...
)
```

Здесь lambda создаёт маленькую функцию для поштучного удаления, которая нигде больше не нужна.

**Когда lambda, а когда def?** Если функция короткая (1 выражение) и используется один раз -- lambda. Если сложнее или используется повторно -- обычный `def`.

### Где это в проекте

- `netbox/sync/interfaces.py` — сортировка LAG через `lambda intf: 0 if intf.port_type == "lag" else 1`
- `netbox/sync/interfaces.py` строка 388 -- lambda в `fallback_fn`

---

## 16. Set (множество)

### Теория

Set (`set`) -- это коллекция **уникальных** значений. Дубликаты автоматически отбрасываются. Основные операции:

- `add(x)` -- добавить элемент
- `x in s` -- проверить наличие (очень быстро, O(1))
- `s1 - s2` -- разность (что есть в s1, но нет в s2)
- `s1 & s2` -- пересечение (что есть в обоих)

```python
names = set()           # Пустое множество
names.add("Gi0/1")
names.add("Gi0/2")
names.add("Gi0/1")     # Дубликат -- не добавится
print(names)            # {"Gi0/1", "Gi0/2"} -- только уникальные
print("Gi0/1" in names) # True -- быстрая проверка
```

### Пример из проекта

Отслеживание обработанных имён (чтобы не обработать дважды):

```python
# netbox/sync/inventory.py
processed_names = set()

for item in items:
    name = item.name.strip()
    processed_names.add(name)   # Запоминаем обработанное имя
    ...

# Потом: cleanup удаляет всё, что НЕ в processed_names
if cleanup:
    for nb_name, nb_item in existing_items.items():
        if nb_name not in processed_names:  # Быстрая проверка O(1)
            # Удаляем лишний элемент из NetBox
```

Операции над множествами -- сравнение кабелей:

```python
# core/domain/sync.py — compare_cables()
local_set = set()   # Кабели с устройств
remote_set = set()  # Кабели в NetBox

# Новые: есть на устройствах, но нет в NetBox
for endpoints in local_set - remote_set:
    diff.to_create.append(...)

# Существующие: есть в обоих
for endpoints in local_set & remote_set:
    diff.to_skip.append(...)

# Лишние: есть в NetBox, но нет на устройствах
for endpoints in remote_set - local_set:
    diff.to_delete.append(...)
```

### Где это в проекте

- `netbox/sync/inventory.py` строка 70 -- `processed_names = set()`
- `netbox/sync/cables.py` строки 41, 45 -- `seen_cables = set()`, `lldp_devices = set()`
- `core/domain/sync.py` строки 476, 497 -- `local_set`, `remote_set` для кабелей

---

## 17. Генераторы и yield

### Теория

Генератор -- это функция, которая **отдаёт значения по одному** вместо того, чтобы вернуть весь список сразу. Вместо `return` используется `yield`.

```python
# Обычная функция: создаёт весь список в памяти
def get_numbers():
    return [1, 2, 3, 4, 5]  # Весь список сразу

# Генератор: отдаёт по одному
def get_numbers():
    yield 1  # Отдали 1, функция "заморозилась"
    yield 2  # Продолжила, отдала 2
    yield 3  # И так далее
```

Зачем? Для больших данных. Если у тебя 10000 устройств, не нужно держать все в памяти -- генератор отдаёт их по одному.

### Пример из проекта

Менеджер контекста для SSH-подключения использует `yield`:

```python
# core/connection.py — connect()
@contextmanager
def connect(self, device, credentials):
    connection = Scrapli(**params)
    connection.open()

    try:
        yield connection      # Отдаём соединение в блок with
    finally:
        connection.close()    # Закрываем после выхода из with
```

Использование:
```python
with conn_manager.connect(device, creds) as conn:
    # conn -- это то, что было yield
    result = conn.send_command("show version")
# После выхода: finally-блок закрывает соединение
```

Здесь `yield` используется не для ленивой итерации, а для менеджера контекста (`@contextmanager`). Это частый паттерн: `yield` "передаёт управление" в блок `with`, а после выхода выполняется код `finally`.

### Где это в проекте

- `core/connection.py` строка 255 -- `yield connection` в менеджере контекста

---

## 18. raise ... from -- цепочка ошибок

### Теория

Когда ловишь одну ошибку и бросаешь другую, `raise ... from e` сохраняет исходную ошибку. Без `from` -- причина теряется.

```python
# Плохо: исходная ошибка потеряна
except Exception as e:
    raise RuntimeError("Что-то пошло не так")
    # При отладке непонятно: ПОЧЕМУ пошло не так?

# Хорошо: исходная ошибка сохранена как "причина"
except Exception as e:
    raise RuntimeError("Что-то пошло не так") from e
    # В traceback видно обе ошибки: новую и исходную
```

### Пример из проекта

В pipeline executor, если auto-collect не удался:

```python
# core/pipeline/executor.py — _execute_sync()
try:
    self._execute_collect(auto_collect_step)
except Exception as e:
    raise RuntimeError(
        f"Auto-collect {collect_target} failed for sync {target}: {e}"
    ) from e
```

Что произойдёт в traceback:
```
ConnectionError: Connection refused to 10.0.0.1

The above exception was the direct cause of the following exception:

RuntimeError: Auto-collect interfaces failed for sync interfaces: Connection refused to 10.0.0.1
```

Благодаря `from e` видно обе ошибки: и понятное описание ("auto-collect failed"), и настоящую причину ("connection refused"). Без `from e` причина бы потерялась.

### Где это в проекте

- `core/pipeline/executor.py` строки 415-417 -- `raise RuntimeError(...) from e`

---

## Что дальше

Теперь ты знаешь Python-концепции, которые используются в проекте. В следующем документе ([02 Обзор проекта](02_PROJECT_OVERVIEW.md)) разберём, как организован проект, его архитектуру и структуру папок.
