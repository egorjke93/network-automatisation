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

## Что дальше

Теперь ты знаешь Python-концепции, которые используются в проекте. В следующем документе ([02 Структура проекта](02_PROJECT_STRUCTURE.md)) разберём, как организованы папки и модули, и зачем проект разделён на слои.
