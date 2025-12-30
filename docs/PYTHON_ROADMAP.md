# Python Roadmap для Network Collector

Пошаговый план изучения Python с примерами из этого проекта.

## Уровень 1: Основы Python

### 1.1 Типы данных и структуры

```python
# Примитивы
hostname = "switch1"           # str
port = 22                      # int
enabled = True                 # bool
speed = 10.5                   # float

# Коллекции
vlans = [1, 10, 20, 30]                    # list
interface = {"name": "Gi0/1", "status": "up"}  # dict
unique_macs = {"aa:bb:cc:dd:ee:ff"}        # set
coordinates = (10.5, 20.3)                 # tuple (неизменяемый)
```

**Где в проекте:**
- `collectors/mac.py:44-60` — работа со списками и словарями
- `core/models.py` — все модели используют эти типы

### 1.2 Условия и циклы

```python
# if/elif/else
if status == "up":
    print("Online")
elif status == "down":
    print("Offline")
else:
    print("Unknown")

# for loop
for interface in interfaces:
    print(interface["name"])

# for с enumerate (индекс + значение)
for i, vlan in enumerate(vlans):
    print(f"{i}: VLAN {vlan}")

# for с dict
for key, value in interface.items():
    print(f"{key} = {value}")

# while
while retry_count < 3:
    try_connect()
    retry_count += 1

# list comprehension (очень важно!)
names = [intf["name"] for intf in interfaces]
up_ports = [intf for intf in interfaces if intf["status"] == "up"]
```

**Где в проекте:**
- `collectors/base.py:200-250` — циклы по устройствам
- `core/domain/lldp.py:237-255` — list comprehension

### 1.3 Функции

```python
# Базовая функция
def get_hostname(device):
    return device["hostname"]

# Аргументы по умолчанию
def connect(host, port=22, timeout=30):
    pass

# *args и **kwargs
def log(*messages, level="INFO", **extra):
    for msg in messages:
        print(f"[{level}] {msg}")
    for key, value in extra.items():
        print(f"  {key}: {value}")

# Вызов
log("Connected", "Authenticated", level="DEBUG", device="switch1")
```

**Где в проекте:**
- `core/logging.py` — функции логирования
- `collectors/base.py:106-140` — `__init__` с **kwargs

### 1.4 Строки и форматирование

```python
# f-strings (основной способ)
name = "Gi0/1"
status = "up"
print(f"Interface {name} is {status}")

# Методы строк
hostname = "  Switch1.domain.local  "
hostname.strip()          # "Switch1.domain.local"
hostname.lower()          # "switch1.domain.local"
hostname.split(".")       # ["Switch1", "domain", "local"]
hostname.startswith("Sw") # True
hostname.replace(".", "-") # "Switch1-domain-local"

# join
parts = ["Gi", "0", "1"]
"/".join(parts)  # "Gi/0/1"
```

**Где в проекте:**
- `core/constants.py:50-100` — нормализация имён интерфейсов

---

## Уровень 2: ООП (Объектно-Ориентированное Программирование)

### 2.1 Классы и объекты

```python
class Device:
    """Класс устройства."""

    # Атрибут класса (общий для всех экземпляров)
    default_port = 22

    def __init__(self, host, platform):
        """Конструктор — вызывается при создании объекта."""
        # Атрибуты экземпляра
        self.host = host
        self.platform = platform
        self.connected = False

    def connect(self):
        """Метод экземпляра."""
        self.connected = True
        return f"Connected to {self.host}"

    def __str__(self):
        """Строковое представление."""
        return f"Device({self.host})"

    def __repr__(self):
        """Представление для отладки."""
        return f"Device(host='{self.host}', platform='{self.platform}')"

# Использование
switch = Device("10.0.0.1", "cisco_ios")
switch.connect()
print(switch)  # Device(10.0.0.1)
```

**Где в проекте:**
- `core/device.py` — класс Device
- `core/models.py` — все dataclass модели

### 2.2 Наследование

```python
class BaseCollector:
    """Базовый класс для всех коллекторов."""

    def __init__(self, credentials):
        self.credentials = credentials

    def collect(self, devices):
        """Общий метод — вызывает _collect_from_device для каждого."""
        results = []
        for device in devices:
            data = self._collect_from_device(device)
            results.extend(data)
        return results

    def _collect_from_device(self, device):
        """Абстрактный метод — должен быть переопределён."""
        raise NotImplementedError("Subclass must implement")


class MACCollector(BaseCollector):
    """Коллектор MAC-адресов."""

    def __init__(self, credentials, include_sticky=False):
        # Вызываем конструктор родителя
        super().__init__(credentials)
        self.include_sticky = include_sticky

    def _collect_from_device(self, device):
        """Реализация для MAC."""
        # Специфичная логика
        return [{"mac": "aa:bb:cc:dd:ee:ff", "vlan": 10}]
```

**Где в проекте:**
- `collectors/base.py` — BaseCollector
- `collectors/mac.py` — MACCollector(BaseCollector)
- `collectors/lldp.py` — LLDPCollector(BaseCollector)

### 2.3 Dataclasses (Python 3.7+)

```python
from dataclasses import dataclass, field
from typing import Optional, List

@dataclass
class Interface:
    """Интерфейс устройства."""
    name: str
    status: str = "down"
    speed: Optional[int] = None
    vlans: List[int] = field(default_factory=list)

    def is_up(self) -> bool:
        return self.status == "up"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status,
            "speed": self.speed,
            "vlans": self.vlans,
        }

# Использование
intf = Interface(name="Gi0/1", status="up", speed=1000)
print(intf.is_up())  # True
print(intf)  # Interface(name='Gi0/1', status='up', speed=1000, vlans=[])
```

**Где в проекте:**
- `core/models.py` — все модели (MACEntry, LLDPNeighbor, InterfaceInfo, DeviceInfo)

### 2.4 Property и статические методы

```python
class Device:
    def __init__(self, host):
        self._host = host
        self._connected = False

    @property
    def host(self):
        """Геттер — вызывается при device.host"""
        return self._host

    @property
    def is_connected(self):
        """Read-only property."""
        return self._connected

    @staticmethod
    def validate_ip(ip):
        """Статический метод — не нужен self."""
        parts = ip.split(".")
        return len(parts) == 4

    @classmethod
    def from_dict(cls, data):
        """Создаёт объект из словаря."""
        return cls(host=data["host"])

# Использование
device = Device("10.0.0.1")
print(device.host)  # 10.0.0.1 (вызывается property)
print(Device.validate_ip("10.0.0.1"))  # True (без создания объекта)
```

**Где в проекте:**
- `core/models.py` — `from_dict` classmethod
- `netbox/diff.py` — `has_changes` property

---

## Уровень 3: Типизация (Type Hints)

### 3.1 Базовые аннотации

```python
from typing import List, Dict, Optional, Any, Tuple, Union

def get_mac(interface: str) -> str:
    """Возвращает MAC-адрес интерфейса."""
    return "aa:bb:cc:dd:ee:ff"

def parse_output(output: str, device: Device) -> List[Dict[str, Any]]:
    """Парсит вывод команды."""
    return [{"mac": "aa:bb", "vlan": 10}]

def find_device(hostname: str) -> Optional[Device]:
    """Возвращает Device или None."""
    return None

def process(data: Union[str, bytes]) -> str:
    """Принимает str или bytes."""
    if isinstance(data, bytes):
        return data.decode()
    return data
```

**Где в проекте:**
- Почти все файлы используют типизацию
- `collectors/base.py` — примеры сложных типов
- `core/domain/lldp.py` — `List[Dict[str, Any]]`

### 3.2 Типы для коллекций

```python
from typing import List, Dict, Set, Tuple

# Список строк
interfaces: List[str] = ["Gi0/1", "Gi0/2"]

# Словарь str -> int
vlan_map: Dict[str, int] = {"management": 10, "users": 20}

# Множество
seen_macs: Set[str] = {"aa:bb:cc:dd:ee:ff"}

# Кортеж фиксированной длины
credentials: Tuple[str, str] = ("admin", "password")
```

### 3.3 Callable и TypeVar

```python
from typing import Callable, TypeVar

T = TypeVar("T")

# Функция как аргумент
def retry(func: Callable[[], T], attempts: int = 3) -> T:
    for i in range(attempts):
        try:
            return func()
        except Exception:
            if i == attempts - 1:
                raise
    raise RuntimeError("Should not reach here")
```

---

## Уровень 4: Работа с файлами и данными

### 4.1 Файлы

```python
# Чтение
with open("config.yaml", "r", encoding="utf-8") as f:
    content = f.read()

# Построчное чтение
with open("devices.txt") as f:
    for line in f:
        print(line.strip())

# Запись
with open("output.txt", "w") as f:
    f.write("Hello\n")

# Append
with open("log.txt", "a") as f:
    f.write("New line\n")
```

### 4.2 JSON

```python
import json

# Чтение
with open("data.json") as f:
    data = json.load(f)

# Запись
with open("output.json", "w") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

# Строка <-> объект
json_str = json.dumps({"name": "switch1"})
obj = json.loads(json_str)
```

**Где в проекте:**
- `exporters/json_exporter.py`

### 4.3 YAML

```python
import yaml

# Чтение
with open("config.yaml") as f:
    config = yaml.safe_load(f)

# Запись
with open("output.yaml", "w") as f:
    yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
```

**Где в проекте:**
- `config.py` — загрузка config.yaml
- `cli.py` — загрузка fields.yaml

### 4.4 CSV

```python
import csv

# Чтение
with open("data.csv") as f:
    reader = csv.DictReader(f)
    for row in reader:
        print(row["hostname"])

# Запись
with open("output.csv", "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["hostname", "ip"])
    writer.writeheader()
    writer.writerow({"hostname": "switch1", "ip": "10.0.0.1"})
```

**Где в проекте:**
- `exporters/csv_exporter.py`

---

## Уровень 5: Обработка ошибок

### 5.1 Try/Except

```python
try:
    result = risky_operation()
except ConnectionError as e:
    logger.error(f"Connection failed: {e}")
    result = None
except TimeoutError:
    logger.error("Timeout")
    raise  # Пробрасываем дальше
except Exception as e:
    logger.error(f"Unknown error: {e}")
finally:
    # Выполняется ВСЕГДА
    cleanup()
```

**Где в проекте:**
- `collectors/base.py:200-230` — обработка ошибок подключения
- `core/connection.py` — все исключения сети

### 5.2 Кастомные исключения

```python
class NetworkCollectorError(Exception):
    """Базовое исключение проекта."""
    pass

class ConnectionError(NetworkCollectorError):
    """Ошибка подключения."""
    def __init__(self, host: str, message: str):
        self.host = host
        self.message = message
        super().__init__(f"{host}: {message}")

class AuthenticationError(NetworkCollectorError):
    """Ошибка аутентификации."""
    pass

# Использование
raise ConnectionError("10.0.0.1", "Connection refused")
```

**Где в проекте:**
- `core/exceptions.py` — все кастомные исключения

---

## Уровень 6: Регулярные выражения

### 6.1 Основы regex

```python
import re

text = "Interface: GigabitEthernet0/1, Status: up"

# Поиск
match = re.search(r"Interface:\s*(\S+)", text)
if match:
    interface = match.group(1)  # "GigabitEthernet0/1"

# Найти все
ips = re.findall(r"\d+\.\d+\.\d+\.\d+", text)

# Замена
clean = re.sub(r"\s+", " ", text)  # Множественные пробелы -> один

# Разбиение
parts = re.split(r",\s*", text)  # ["Interface: Gi0/1", "Status: up"]

# Компиляция (для многократного использования)
pattern = re.compile(r"(\d+)\.(\d+)\.(\d+)\.(\d+)")
match = pattern.match("10.0.0.1")
```

### 6.2 Частые паттерны

```python
# IP адрес
ip_pattern = r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}"

# MAC адрес (разные форматы)
mac_patterns = [
    r"([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}",   # 00:11:22:33:44:55
    r"([0-9a-fA-F]{4}\.){2}[0-9a-fA-F]{4}",  # 0011.2233.4455
]

# Интерфейс Cisco
intf_pattern = r"(Gi|Fa|Te|Et|Po)\d+(/\d+)*"

# Группы с именами
pattern = r"(?P<name>\S+)\s+(?P<status>up|down)"
match = re.search(pattern, "Gi0/1 up")
if match:
    print(match.group("name"))    # "Gi0/1"
    print(match.groupdict())      # {"name": "Gi0/1", "status": "up"}
```

**Где в проекте:**
- `collectors/lldp.py:244-320` — парсинг LLDP
- `collectors/mac.py` — парсинг MAC-таблицы
- `core/constants.py` — нормализация интерфейсов

---

## Уровень 7: Паттерны проектирования

### 7.1 Template Method (Шаблонный метод)

Базовый класс определяет алгоритм, подклассы реализуют шаги.

```python
class BaseCollector:
    def collect(self, devices):
        """Шаблонный метод — алгоритм."""
        results = []
        for device in devices:
            data = self._collect_from_device(device)  # Абстрактный шаг
            normalized = self._normalize(data)         # Абстрактный шаг
            results.extend(normalized)
        return results

    def _collect_from_device(self, device):
        raise NotImplementedError

    def _normalize(self, data):
        raise NotImplementedError


class MACCollector(BaseCollector):
    def _collect_from_device(self, device):
        # Реализация для MAC
        return [{"mac": "aa:bb:cc"}]

    def _normalize(self, data):
        return data
```

**Где в проекте:**
- `collectors/base.py` → `collectors/mac.py`, `collectors/lldp.py`

### 7.2 Strategy (Стратегия)

Выбор алгоритма в runtime.

```python
class Exporter:
    def export(self, data, format: str):
        if format == "json":
            return self._export_json(data)
        elif format == "csv":
            return self._export_csv(data)
        elif format == "excel":
            return self._export_excel(data)
```

**Где в проекте:**
- `exporters/` — разные форматы экспорта
- `cli.py` — выбор экспортера по `--format`

### 7.3 Factory (Фабрика)

Создание объектов без указания конкретного класса.

```python
def get_collector(collector_type: str) -> BaseCollector:
    collectors = {
        "mac": MACCollector,
        "lldp": LLDPCollector,
        "interfaces": InterfaceCollector,
    }
    return collectors[collector_type]()
```

### 7.4 Singleton (Одиночка)

Один экземпляр на всё приложение.

```python
class ConnectionManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
```

**Где в проекте:**
- `core/connection.py` — ConnectionManager (неявный singleton через модуль)

### 7.5 Decorator (Декоратор)

Добавление функциональности без изменения кода.

```python
import functools
import time

def timing(func):
    """Декоратор для измерения времени выполнения."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        elapsed = time.time() - start
        print(f"{func.__name__} took {elapsed:.2f}s")
        return result
    return wrapper

@timing
def slow_function():
    time.sleep(1)
```

**Где в проекте:**
- `core/models.py` — `@dataclass`
- `core/logging.py` — возможные декораторы логирования

### 7.6 Context Manager (Менеджер контекста)

Автоматическое управление ресурсами.

```python
class Connection:
    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
        return False  # Не подавляем исключения

# Использование
with Connection() as conn:
    conn.send_command("show version")
# Автоматически вызовется disconnect()
```

**Где в проекте:**
- `core/connection.py` — ConnectionManager с context manager

---

## Уровень 8: Архитектура проекта

### 8.1 Слои приложения

```
┌─────────────────────────────────────────────┐
│                   CLI                        │  ← Точка входа
│                 (cli.py)                     │
├─────────────────────────────────────────────┤
│              Collectors                      │  ← Сбор данных
│    (mac.py, lldp.py, interfaces.py)         │
├─────────────────────────────────────────────┤
│            Domain Layer                      │  ← Бизнес-логика
│      (core/domain/mac.py, lldp.py)          │
├─────────────────────────────────────────────┤
│              Core Layer                      │  ← Общие компоненты
│  (models.py, connection.py, constants.py)   │
├─────────────────────────────────────────────┤
│         External Integrations                │  ← Внешние системы
│      (netbox/, exporters/)                   │
└─────────────────────────────────────────────┘
```

### 8.2 Принцип единственной ответственности

```
Collector     → только парсинг вывода команд
Domain        → нормализация, бизнес-логика
Exporter      → только форматирование вывода
NetBox Client → только API вызовы
NetBox Sync   → логика синхронизации
```

### 8.3 Поток данных

```
Device → Collector._collect_from_device()
                    ↓
            raw output (str)
                    ↓
            _parse_output() → TextFSM или Regex
                    ↓
            List[Dict] (сырые данные)
                    ↓
            Domain.normalize()
                    ↓
            List[Dict] (нормализованные)
                    ↓
      ┌─────────────┴─────────────┐
      ↓                           ↓
  Exporter                   NetBox Sync
  (Excel/CSV/JSON)           (API calls)
```

---

## Уровень 9: Практические задания

### Задание 1: Добавить новое поле в модель

1. Открой `core/models.py`
2. Найди класс `MACEntry`
3. Добавь поле `age: Optional[int] = None`
4. Обнови `from_dict()` и `to_dict()`

### Задание 2: Добавить новую команду CLI

1. Открой `cli.py`
2. Найди где создаются subparsers
3. Добавь новую команду по аналогии

### Задание 3: Написать тест

1. Открой `tests/test_collectors/`
2. Создай новый тест по аналогии с существующими
3. Запусти: `pytest tests/ -v`

### Задание 4: Добавить TextFSM шаблон

1. Получи вывод команды с устройства
2. Создай шаблон в `templates/`
3. Добавь маппинг в `core/constants.py`
4. Напиши тест

### Задание 5: Понять flow синхронизации

1. Открой `netbox/sync.py`
2. Найди метод `sync_interfaces`
3. Проследи путь данных от collector до API

---

## Ресурсы для изучения

### Книги
- "Python Crash Course" — основы
- "Fluent Python" — продвинутый уровень
- "Clean Code in Python" — чистый код

### Онлайн
- [Real Python](https://realpython.com/) — туториалы
- [Python Docs](https://docs.python.org/3/) — официальная документация
- [Type Hints Cheat Sheet](https://mypy.readthedocs.io/en/stable/cheat_sheet_py3.html)

### Инструменты
- `black` — автоформатирование
- `ruff` — быстрый линтер
- `mypy` — проверка типов
- `pytest` — тестирование

---

## Чек-лист готовности

- [ ] Понимаю list comprehension
- [ ] Понимаю классы и наследование
- [ ] Могу читать type hints
- [ ] Понимаю try/except
- [ ] Могу написать regex
- [ ] Понимаю декораторы
- [ ] Понимаю context manager (with)
- [ ] Могу написать тест
- [ ] Понимаю архитектуру проекта
- [ ] Могу добавить новый collector
