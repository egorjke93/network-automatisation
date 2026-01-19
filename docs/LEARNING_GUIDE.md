# Python для понимания проекта — Полный учебник

Этот документ — учебник по Python, написанный на примерах из проекта Network Collector.
Цель: объяснить все конструкции языка, которые встречаются в коде, чтобы вы могли
понимать и модифицировать проект, даже если только начинаете изучать Python.

---

## Содержание

1. [Основы Python](#1-основы-python)
   - [Переменные и типы данных](#11-переменные-и-типы-данных)
   - [Списки, словари, множества](#12-списки-словари-множества)
   - [Условия и циклы](#13-условия-и-циклы)
   - [Функции](#14-функции)
2. [Модули и пакеты](#2-модули-и-пакеты)
   - [Импорты](#21-импорты)
   - [Структура пакета](#22-структура-пакета)
   - [\_\_init\_\_.py](#23-__init__py)
3. [Объектно-ориентированное программирование](#3-объектно-ориентированное-программирование)
   - [Классы и объекты](#31-классы-и-объекты)
   - [Конструктор \_\_init\_\_](#32-конструктор-__init__)
   - [Методы и self](#33-методы-и-self)
   - [Наследование](#34-наследование)
   - [Множественное наследование и Mixin](#35-множественное-наследование-и-mixin)
4. [Специальные методы (dunder)](#4-специальные-методы-dunder)
5. [Декораторы](#5-декораторы)
   - [@property](#51-property)
   - [@staticmethod и @classmethod](#52-staticmethod-и-classmethod)
   - [@dataclass](#53-dataclass)
6. [Type Hints (аннотации типов)](#6-type-hints-аннотации-типов)
7. [Enum — перечисления](#7-enum--перечисления)
8. [Dataclasses](#8-dataclasses)
9. [Pydantic — валидация данных](#9-pydantic--валидация-данных)
10. [Исключения](#10-исключения)
11. [Контекстные менеджеры (with)](#11-контекстные-менеджеры-with)
12. [Генераторы и comprehensions](#12-генераторы-и-comprehensions)
13. [Асинхронное программирование](#13-асинхронное-программирование)
14. [Многопоточность](#14-многопоточность)
15. [Полезные паттерны из проекта](#15-полезные-паттерны-из-проекта)

---

## 1. Основы Python

### 1.1 Переменные и типы данных

В Python переменные создаются при присваивании. Тип определяется автоматически.

```python
# Числа
port = 22                    # int (целое число)
timeout = 30.5               # float (дробное число)

# Строки
hostname = "switch-01"       # str (строка)
command = 'show version'     # str (одинарные кавычки тоже работают)

# Многострочная строка
description = """
Это многострочная
строка описания
"""

# Логический тип
is_enabled = True            # bool: True или False
dry_run = False

# None — специальное значение "ничего"
result = None                # Пока нет результата
```

**Из проекта (`core/models.py`):**
```python
class Interface:
    def __init__(self):
        self.name: str = ""           # Строка
        self.status: str = "unknown"  # Строка со значением по умолчанию
        self.speed: int = 0           # Целое число
        self.mtu: Optional[int] = None  # Может быть int или None
```

### 1.2 Списки, словари, множества

#### Список (list) — упорядоченная коллекция

```python
# Создание списка
devices = ["192.168.1.1", "192.168.1.2", "192.168.1.3"]

# Доступ по индексу (начинается с 0)
first = devices[0]      # "192.168.1.1"
last = devices[-1]      # "192.168.1.3" (с конца)

# Добавление элементов
devices.append("192.168.1.4")        # В конец
devices.insert(0, "192.168.1.0")     # В начало

# Удаление
devices.remove("192.168.1.2")        # По значению
del devices[0]                        # По индексу
popped = devices.pop()               # Удалить и вернуть последний

# Длина списка
count = len(devices)    # 3

# Проверка наличия
if "192.168.1.1" in devices:
    print("Устройство в списке")

# Итерация
for device in devices:
    print(device)

# Итерация с индексом
for i, device in enumerate(devices):
    print(f"{i}: {device}")
```

**Из проекта (`collectors/base.py`):**
```python
def collect(self, devices: List[Device]) -> List[Any]:
    """Собирает данные с устройств."""
    results = []  # Пустой список для результатов

    for device in devices:
        result = self._collect_one(device)
        if result is not None:
            results.append(result)  # Добавляем результат

    return results
```

#### Словарь (dict) — пары ключ-значение

```python
# Создание словаря
device = {
    "host": "192.168.1.1",
    "platform": "cisco_ios",
    "port": 22,
}

# Доступ по ключу
host = device["host"]              # "192.168.1.1"
host = device.get("host")          # То же самое, но безопаснее
port = device.get("port", 22)      # 22, если ключа нет — вернёт 22

# Изменение
device["port"] = 2222
device["timeout"] = 30             # Добавление нового ключа

# Удаление
del device["timeout"]
port = device.pop("port", None)    # Удалить и вернуть

# Проверка наличия ключа
if "host" in device:
    print("Ключ есть")

# Итерация
for key in device:
    print(key)

for key, value in device.items():
    print(f"{key} = {value}")

for value in device.values():
    print(value)
```

**Из проекта (`api/services/sync_service.py`):**
```python
stats = {
    "devices": {"created": 0, "updated": 0, "skipped": 0},
    "interfaces": {"created": 0, "updated": 0, "skipped": 0},
}

# Обновление вложенного словаря
stats["devices"]["created"] += 1
stats["interfaces"]["updated"] += result.get("updated", 0)
```

#### Множество (set) — уникальные элементы

```python
# Создание множества
vlans = {10, 20, 30, 10}    # {10, 20, 30} — дубликаты удаляются

# Добавление
vlans.add(40)

# Операции над множествами
vlans_a = {10, 20, 30}
vlans_b = {20, 30, 40}

union = vlans_a | vlans_b           # {10, 20, 30, 40} — объединение
intersection = vlans_a & vlans_b    # {20, 30} — пересечение
difference = vlans_a - vlans_b      # {10} — разность
```

**Из проекта (`core/pipeline/executor.py`):**
```python
def _check_dependencies(self, step, results):
    """Проверяет что все зависимости выполнены."""
    # Множество завершённых шагов
    completed_steps = {r.step_id for r in results if r.status == StepStatus.COMPLETED}

    for dep_id in step.depends_on:
        if dep_id not in completed_steps:  # Быстрая проверка O(1)
            return False
    return True
```

### 1.3 Условия и циклы

#### if/elif/else

```python
status = "up"

if status == "up":
    print("Интерфейс активен")
elif status == "down":
    print("Интерфейс выключен")
else:
    print("Неизвестный статус")

# Сокращённая форма (тернарный оператор)
message = "active" if status == "up" else "inactive"

# Проверка на None
result = get_result()
if result is None:
    print("Нет результата")

# Проверка на пустоту
devices = []
if not devices:  # Пустой список = False
    print("Список пуст")

if devices:  # Непустой список = True
    print(f"Есть {len(devices)} устройств")
```

**Из проекта (`netbox/sync/interfaces.py`):**
```python
def _update_interface(self, nb_interface, intf):
    updates = {}

    # Проверяем каждое поле
    if sync_cfg.is_field_enabled("description"):
        if intf.description != nb_interface.description:
            updates["description"] = intf.description

    if sync_cfg.is_field_enabled("enabled"):
        enabled = intf.status not in ("disabled", "error")
        if enabled != nb_interface.enabled:
            updates["enabled"] = enabled

    # Если нет изменений — выходим
    if not updates:
        return False

    # Применяем изменения
    self.client.update_interface(nb_interface.id, **updates)
    return True
```

#### for — цикл по коллекции

```python
# Простой цикл
for device in devices:
    print(device.host)

# range() — последовательность чисел
for i in range(5):          # 0, 1, 2, 3, 4
    print(i)

for i in range(1, 6):       # 1, 2, 3, 4, 5
    print(i)

for i in range(0, 10, 2):   # 0, 2, 4, 6, 8 (шаг 2)
    print(i)

# enumerate() — индекс + элемент
for index, device in enumerate(devices):
    print(f"{index}: {device}")

# zip() — параллельная итерация
names = ["eth0", "eth1"]
statuses = ["up", "down"]
for name, status in zip(names, statuses):
    print(f"{name}: {status}")

# break — прервать цикл
for device in devices:
    if device.host == target:
        print("Найдено!")
        break

# continue — перейти к следующей итерации
for device in devices:
    if not device.enabled:
        continue  # Пропустить отключённые
    process(device)
```

#### while — цикл с условием

```python
# Повторять пока условие истинно
retries = 3
while retries > 0:
    try:
        connect()
        break  # Успех — выходим
    except ConnectionError:
        retries -= 1
        time.sleep(1)
```

**Из проекта (`core/connection.py`):**
```python
def connect_with_retry(self, max_retries=3):
    """Подключение с повторами."""
    attempt = 0
    while attempt < max_retries:
        try:
            self._connect()
            return True
        except Exception as e:
            attempt += 1
            if attempt >= max_retries:
                raise
            time.sleep(2 ** attempt)  # Экспоненциальная задержка
```

### 1.4 Функции

```python
# Простая функция
def greet(name):
    """Приветствует пользователя."""  # Docstring — документация
    return f"Привет, {name}!"

message = greet("Мир")  # "Привет, Мир!"

# Параметры по умолчанию
def connect(host, port=22, timeout=30):
    """Подключается к хосту."""
    print(f"Connecting to {host}:{port} (timeout={timeout})")

connect("192.168.1.1")                    # port=22, timeout=30
connect("192.168.1.1", 2222)              # port=2222, timeout=30
connect("192.168.1.1", timeout=60)        # port=22, timeout=60

# *args — произвольное число позиционных аргументов
def log(*messages):
    """Логирует сообщения."""
    for msg in messages:
        print(msg)

log("Ошибка", "Подробности", "Стек")

# **kwargs — произвольное число именованных аргументов
def create_device(**kwargs):
    """Создаёт устройство из параметров."""
    print(kwargs)  # {'host': '192.168.1.1', 'platform': 'cisco_ios'}

create_device(host="192.168.1.1", platform="cisco_ios")
```

**Из проекта (`netbox/client.py`):**
```python
def create_interface(
    self,
    device_id: int,
    name: str,
    interface_type: str = "other",
    **kwargs,  # Дополнительные поля: description, mtu, enabled...
):
    """Создаёт интерфейс в NetBox."""
    data = {
        "device": device_id,
        "name": name,
        "type": interface_type,
        **kwargs,  # Распаковка словаря
    }
    return self.api.dcim.interfaces.create(data)

# Вызов
create_interface(
    device_id=42,
    name="Gi0/1",
    interface_type="1000base-t",
    description="Uplink",  # Пойдёт в kwargs
    mtu=9000,              # Пойдёт в kwargs
)
```

---

## 2. Модули и пакеты

### 2.1 Импорты

```python
# Импорт всего модуля
import os
print(os.path.exists("/tmp"))

# Импорт с псевдонимом
import numpy as np
arr = np.array([1, 2, 3])

# Импорт конкретных объектов
from pathlib import Path
p = Path("/home/user")

# Импорт нескольких объектов
from typing import List, Dict, Optional

# Относительный импорт (внутри пакета)
from . import utils           # Из текущего пакета
from .. import config         # Из родительского пакета
from .models import Device    # Из текущего пакета, модуль models
from ...core import logging   # На 3 уровня вверх
```

**Из проекта (`cli/commands/sync.py`):**
```python
# Стандартная библиотека
import logging
import time

# Относительные импорты
from ..utils import load_devices, get_credentials
from ...netbox import NetBoxClient, NetBoxSync
from ...collectors import InterfaceCollector, LLDPCollector
from ...config import config
```

### 2.2 Структура пакета

```
network_collector/           # Корневой пакет
├── __init__.py             # Делает папку пакетом
├── __main__.py             # python -m network_collector
├── config.py
├── cli/                    # Подпакет
│   ├── __init__.py
│   ├── utils.py
│   └── commands/           # Под-подпакет
│       ├── __init__.py
│       ├── collect.py
│       └── sync.py
├── core/
│   ├── __init__.py
│   ├── models.py
│   └── pipeline/
│       ├── __init__.py
│       ├── models.py
│       └── executor.py
└── netbox/
    ├── __init__.py
    ├── client.py
    └── sync/
        ├── __init__.py
        ├── base.py
        └── main.py
```

### 2.3 \_\_init\_\_.py

`__init__.py` выполняется при импорте пакета. Используется для:
1. Обозначения папки как пакета
2. Экспорта публичного API
3. Инициализации пакета

```python
# collectors/__init__.py

"""
Collectors — сбор данных с устройств.

Экспортируем классы для удобного импорта:
    from network_collector.collectors import DeviceCollector
вместо:
    from network_collector.collectors.device import DeviceCollector
"""

from .device import DeviceCollector
from .mac import MACCollector
from .lldp import LLDPCollector
from .interfaces import InterfaceCollector
from .inventory import InventoryCollector

# __all__ определяет что экспортируется при "from package import *"
__all__ = [
    "DeviceCollector",
    "MACCollector",
    "LLDPCollector",
    "InterfaceCollector",
    "InventoryCollector",
]
```

---

## 3. Объектно-ориентированное программирование

### 3.1 Классы и объекты

**Класс** — это шаблон (чертёж) для создания объектов.
**Объект** (экземпляр) — конкретная реализация класса.

```python
# Определение класса
class Device:
    """Представляет сетевое устройство."""
    pass  # Пустой класс

# Создание объекта (экземпляра)
device = Device()
```

### 3.2 Конструктор \_\_init\_\_

`__init__` — специальный метод, вызывается при создании объекта.

```python
class Device:
    """Сетевое устройство."""

    def __init__(self, host, platform="cisco_ios"):
        """
        Конструктор.

        Args:
            host: IP адрес устройства
            platform: Платформа (по умолчанию cisco_ios)
        """
        # self — ссылка на создаваемый объект
        # self.xxx — атрибуты объекта
        self.host = host
        self.platform = platform
        self.connected = False

# Создание объекта — вызывается __init__
device = Device("192.168.1.1")
print(device.host)       # "192.168.1.1"
print(device.platform)   # "cisco_ios"
print(device.connected)  # False

device2 = Device("192.168.1.2", platform="cisco_nxos")
print(device2.platform)  # "cisco_nxos"
```

**Из проекта (`core/device.py`):**
```python
class Device:
    """
    Модель сетевого устройства.

    Содержит информацию для подключения и идентификации.
    """

    def __init__(
        self,
        host: str,
        platform: Optional[str] = None,
        device_type: Optional[str] = None,
        port: int = 22,
        role: Optional[str] = None,
    ):
        self.host = host
        self.platform = platform
        self.device_type = device_type or self._detect_device_type()
        self.port = port
        self.role = role

    def _detect_device_type(self) -> str:
        """Определяет тип устройства из platform."""
        if self.platform:
            return PLATFORM_TO_DEVICE_TYPE.get(self.platform, "cisco_ios")
        return "cisco_ios"
```

### 3.3 Методы и self

**Метод** — функция внутри класса.
**self** — первый параметр метода, ссылка на объект.

```python
class Device:
    def __init__(self, host):
        self.host = host
        self.connected = False

    def connect(self):
        """Подключается к устройству."""
        print(f"Connecting to {self.host}...")
        self.connected = True  # Изменяем атрибут объекта

    def disconnect(self):
        """Отключается от устройства."""
        if self.connected:
            print(f"Disconnecting from {self.host}")
            self.connected = False

    def send_command(self, command):
        """Отправляет команду."""
        if not self.connected:
            raise RuntimeError("Not connected")
        print(f"Sending: {command}")
        return f"Output of {command}"

# Использование
device = Device("192.168.1.1")
device.connect()                    # self = device
output = device.send_command("show version")  # self = device
device.disconnect()
```

### 3.4 Наследование

**Наследование** — создание нового класса на основе существующего.
Дочерний класс получает все атрибуты и методы родителя.

```python
# Родительский класс (базовый)
class BaseCollector:
    """Базовый сборщик данных."""

    def __init__(self, credentials):
        self.credentials = credentials

    def collect(self, devices):
        """Собирает данные со всех устройств."""
        results = []
        for device in devices:
            result = self._collect_one(device)
            if result:
                results.append(result)
        return results

    def _collect_one(self, device):
        """Собирает с одного устройства. Переопределяется в дочерних."""
        raise NotImplementedError("Subclass must implement _collect_one")


# Дочерний класс
class MACCollector(BaseCollector):
    """Сборщик MAC-адресов."""

    def __init__(self, credentials, mac_format="ieee"):
        # Вызываем конструктор родителя
        super().__init__(credentials)
        # Добавляем свои атрибуты
        self.mac_format = mac_format

    def _collect_one(self, device):
        """Переопределяем метод родителя."""
        # Собираем MAC-адреса с устройства
        output = self._send_command(device, "show mac address-table")
        return self._parse_mac_table(output)


# Использование
collector = MACCollector(credentials, mac_format="cisco")
# collect() — из родителя BaseCollector
# _collect_one() — переопределён в MACCollector
results = collector.collect(devices)
```

**Из проекта (`collectors/mac.py`):**
```python
class MACCollector(BaseCollector):
    """Сборщик MAC-адресов."""

    def __init__(
        self,
        credentials: Credentials = None,
        mac_format: str = "ieee",
        collect_descriptions: bool = True,
        transport: str = "ssh2",
    ):
        # Вызов конструктора родителя
        super().__init__(credentials=credentials, transport=transport)
        # Свои атрибуты
        self.mac_format = mac_format
        self.collect_descriptions = collect_descriptions

    def _collect_one(self, device: Device) -> List[MACEntry]:
        """Переопределение метода сбора."""
        # Реализация для MAC-адресов
        ...
```

### 3.5 Множественное наследование и Mixin

Python поддерживает наследование от нескольких классов.
**Mixin** — класс, добавляющий функциональность, не предназначен для использования отдельно.

```python
# Базовый класс
class SyncBase:
    """Базовая функциональность синхронизации."""

    def __init__(self, client, dry_run=False):
        self.client = client
        self.dry_run = dry_run

    def _find_device(self, name):
        """Находит устройство в NetBox."""
        return self.client.get_device_by_name(name)


# Mixin для интерфейсов
class InterfacesSyncMixin:
    """Добавляет методы синхронизации интерфейсов."""

    def sync_interfaces(self, device_name, interfaces):
        """Синхронизирует интерфейсы."""
        device = self._find_device(device_name)  # Метод из SyncBase
        # ...реализация...
        return {"created": 5, "updated": 3}


# Mixin для кабелей
class CablesSyncMixin:
    """Добавляет методы синхронизации кабелей."""

    def sync_cables_from_lldp(self, lldp_data):
        """Создаёт кабели из LLDP данных."""
        # ...реализация...
        return {"created": 10}


# Главный класс — наследует всё
class NetBoxSync(
    InterfacesSyncMixin,  # sync_interfaces()
    CablesSyncMixin,      # sync_cables_from_lldp()
    SyncBase,             # _find_device(), client, dry_run
):
    """
    Синхронизация с NetBox.

    Объединяет функциональность всех Mixin.
    """
    pass  # Всё уже унаследовано!


# Использование
sync = NetBoxSync(client, dry_run=True)
sync.sync_interfaces("switch-01", interfaces)   # Из InterfacesSyncMixin
sync.sync_cables_from_lldp(lldp_data)           # Из CablesSyncMixin
device = sync._find_device("switch-01")          # Из SyncBase
```

**Порядок наследования важен!** Python ищет методы слева направо (MRO — Method Resolution Order).

```python
# Порядок поиска метода:
# NetBoxSync → InterfacesSyncMixin → CablesSyncMixin → SyncBase → object

# Посмотреть MRO:
print(NetBoxSync.__mro__)
```

---

## 4. Специальные методы (dunder)

**Dunder** (double underscore) — методы вида `__name__`.
Они определяют поведение объекта в различных ситуациях.

### \_\_str\_\_ и \_\_repr\_\_

```python
class Device:
    def __init__(self, host, platform):
        self.host = host
        self.platform = platform

    def __str__(self):
        """Человекочитаемое представление (для print)."""
        return f"Device({self.host})"

    def __repr__(self):
        """Техническое представление (для отладки)."""
        return f"Device(host={self.host!r}, platform={self.platform!r})"


device = Device("192.168.1.1", "cisco_ios")
print(device)        # Device(192.168.1.1)     — вызывает __str__
print(repr(device))  # Device(host='192.168.1.1', platform='cisco_ios')
print([device])      # [Device(host='192.168.1.1', ...)]  — __repr__ в списках
```

### \_\_eq\_\_, \_\_hash\_\_

```python
class Device:
    def __init__(self, host):
        self.host = host

    def __eq__(self, other):
        """Сравнение на равенство (==)."""
        if not isinstance(other, Device):
            return False
        return self.host == other.host

    def __hash__(self):
        """Хеш для использования в set и dict."""
        return hash(self.host)


d1 = Device("192.168.1.1")
d2 = Device("192.168.1.1")
d3 = Device("192.168.1.2")

print(d1 == d2)  # True
print(d1 == d3)  # False

# Можно использовать в set
devices = {d1, d2, d3}  # {d1, d3} — d2 дубликат d1
```

### \_\_enter\_\_, \_\_exit\_\_ (контекстные менеджеры)

```python
class Connection:
    """SSH подключение с автоматическим закрытием."""

    def __init__(self, host):
        self.host = host
        self.connected = False

    def __enter__(self):
        """Вызывается при входе в with."""
        print(f"Connecting to {self.host}")
        self.connected = True
        return self  # Возвращается в as

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Вызывается при выходе из with (даже при ошибке)."""
        print(f"Disconnecting from {self.host}")
        self.connected = False
        return False  # Не подавляем исключения

    def send_command(self, cmd):
        return f"Output of {cmd}"


# Использование
with Connection("192.168.1.1") as conn:
    # __enter__ вызван, conn — результат __enter__
    output = conn.send_command("show version")
    print(output)
# __exit__ вызван автоматически
```

**Из проекта (`core/connection.py`):**
```python
class Connection:
    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
        return False

# Использование в коде
with Connection(device, credentials) as conn:
    output = conn.send_command("show interfaces")
# Соединение автоматически закрыто
```

---

## 5. Декораторы

### Что такое декоратор

**Декоратор** — функция, которая модифицирует другую функцию.
Синтаксис `@decorator` — это просто сокращение.

```python
# Без декоратора
def my_function():
    pass
my_function = decorator(my_function)

# С декоратором — то же самое
@decorator
def my_function():
    pass
```

### 5.1 @property

Превращает метод в атрибут (без скобок при вызове).

```python
class Interface:
    def __init__(self, name, speed_mbps):
        self.name = name
        self._speed_mbps = speed_mbps  # "Приватный" атрибут

    @property
    def speed(self):
        """Скорость в читаемом формате."""
        if self._speed_mbps >= 1000:
            return f"{self._speed_mbps // 1000} Gbps"
        return f"{self._speed_mbps} Mbps"

    @property
    def speed_mbps(self):
        """Скорость в Mbps."""
        return self._speed_mbps

    @speed_mbps.setter
    def speed_mbps(self, value):
        """Setter для speed_mbps."""
        if value < 0:
            raise ValueError("Speed cannot be negative")
        self._speed_mbps = value


intf = Interface("Gi0/1", 1000)
print(intf.speed)      # "1 Gbps" — вызов без скобок!
print(intf.speed_mbps) # 1000

intf.speed_mbps = 10000  # Использует setter
print(intf.speed)        # "10 Gbps"
```

**Из проекта (`core/context.py`):**
```python
class RunContext:
    def __init__(self, run_id, start_time):
        self.run_id = run_id
        self._start_time = start_time

    @property
    def elapsed(self) -> float:
        """Прошедшее время в секундах."""
        return time.time() - self._start_time

    @property
    def elapsed_human(self) -> str:
        """Прошедшее время в читаемом формате."""
        seconds = int(self.elapsed)
        if seconds < 60:
            return f"{seconds}s"
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes}m {seconds}s"
```

### 5.2 @staticmethod и @classmethod

```python
class Device:
    default_port = 22

    def __init__(self, host):
        self.host = host

    @staticmethod
    def validate_ip(ip):
        """
        Статический метод — не принимает self или cls.
        Просто функция внутри класса.
        """
        parts = ip.split(".")
        return len(parts) == 4 and all(0 <= int(p) <= 255 for p in parts)

    @classmethod
    def from_string(cls, string):
        """
        Метод класса — принимает cls (класс) вместо self.
        Используется как альтернативный конструктор.
        """
        # cls — это класс Device (или его подкласс)
        host, port = string.split(":")
        device = cls(host)  # Создаём экземпляр
        device.port = int(port)
        return device

    @classmethod
    def get_default_port(cls):
        """Доступ к атрибутам класса."""
        return cls.default_port


# Статический метод
print(Device.validate_ip("192.168.1.1"))  # True
print(Device.validate_ip("invalid"))       # False

# Метод класса
device = Device.from_string("192.168.1.1:2222")
print(device.host)  # "192.168.1.1"
print(device.port)  # 2222
```

### 5.3 @dataclass

Автоматически создаёт `__init__`, `__repr__`, `__eq__` и другие методы.

```python
from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class Device:
    """Устройство с автоматическими методами."""
    host: str
    platform: str = "cisco_ios"  # Значение по умолчанию
    port: int = 22
    tags: List[str] = field(default_factory=list)  # Мутабельное значение


# Автоматически создан __init__:
device = Device(host="192.168.1.1", platform="cisco_nxos")

# Автоматически создан __repr__:
print(device)  # Device(host='192.168.1.1', platform='cisco_nxos', port=22, tags=[])

# Автоматически создан __eq__:
device2 = Device(host="192.168.1.1", platform="cisco_nxos")
print(device == device2)  # True
```

**Из проекта (`core/pipeline/models.py`):**
```python
@dataclass
class PipelineStep:
    """Один шаг pipeline."""
    id: str
    type: StepType
    target: str
    enabled: bool = True
    options: Dict = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)

    # Runtime поля
    status: StepStatus = StepStatus.PENDING
    result: Optional[Dict] = None
    error: Optional[str] = None
```

---

## 6. Type Hints (аннотации типов)

Type hints — подсказки о типах. Python их не проверяет, но IDE и mypy используют.

### Базовые типы

```python
# Аннотации переменных
name: str = "switch-01"
port: int = 22
timeout: float = 30.5
enabled: bool = True

# Аннотации параметров и возвращаемого значения
def connect(host: str, port: int = 22) -> bool:
    """Подключается."""
    return True
```

### Optional, Union, List, Dict

```python
from typing import Optional, Union, List, Dict, Any, Tuple

# Optional[X] = X или None
def find_device(name: str) -> Optional[Device]:
    """Возвращает Device или None."""
    pass

# Union[X, Y] = X или Y
def process(value: Union[str, int]) -> str:
    """Принимает строку или число."""
    return str(value)

# List[X] — список элементов типа X
def get_devices() -> List[Device]:
    return []

# Dict[K, V] — словарь
def get_stats() -> Dict[str, int]:
    return {"created": 5, "updated": 3}

# Tuple[X, Y, Z] — кортеж фиксированной длины
def get_coordinates() -> Tuple[float, float]:
    return (10.5, 20.3)

# Any — любой тип
def process_any(data: Any) -> Any:
    return data
```

**Из проекта (`api/services/sync_service.py`):**
```python
from typing import List, Dict, Optional, Any

class SyncService:
    def _get_devices(self, device_list: List[str] = None) -> List[Device]:
        """Получает список устройств."""
        pass

    def _do_sync(
        self,
        request: SyncRequest,
        devices: List[Device],
        task_id: str,
        steps: List[str],
    ) -> Dict[str, Any]:
        """Выполняет синхронизацию."""
        pass
```

---

## 7. Enum — перечисления

**Enum** — набор именованных констант.

```python
from enum import Enum, auto

class StepStatus(str, Enum):
    """
    Статус выполнения шага.

    str, Enum — наследование от str позволяет сравнивать со строками.
    """
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


# Использование
status = StepStatus.COMPLETED

# Сравнение
if status == StepStatus.COMPLETED:
    print("Done!")

# Доступ к значению
print(status.value)  # "completed"

# Доступ к имени
print(status.name)   # "COMPLETED"

# Итерация по всем значениям
for s in StepStatus:
    print(f"{s.name} = {s.value}")

# Создание из строки
status = StepStatus("pending")  # StepStatus.PENDING
```

**Из проекта (`core/pipeline/models.py`):**
```python
class StepType(str, Enum):
    """Тип шага pipeline."""
    COLLECT = "collect"
    SYNC = "sync"
    EXPORT = "export"


class StepStatus(str, Enum):
    """Статус выполнения."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
```

---

## 8. Dataclasses

**dataclass** — декоратор для автоматического создания методов класса.

```python
from dataclasses import dataclass, field, asdict, astuple
from typing import List, Optional

@dataclass
class Interface:
    """Интерфейс с автоматическими методами."""

    # Обязательные поля
    name: str

    # Поля со значением по умолчанию
    status: str = "unknown"
    speed: int = 0
    mtu: Optional[int] = None

    # Мутабельные значения — через field()
    tags: List[str] = field(default_factory=list)

    # Поле не в __repr__ и сравнении
    _cache: dict = field(default_factory=dict, repr=False, compare=False)

    # Вычисляемое поле
    full_name: str = field(init=False)

    def __post_init__(self):
        """Вызывается после __init__."""
        self.full_name = f"{self.name} ({self.status})"


# Создание
intf = Interface(name="Gi0/1", status="up", speed=1000)

# __repr__ автоматический
print(intf)

# __eq__ автоматический
intf2 = Interface(name="Gi0/1", status="up", speed=1000)
print(intf == intf2)  # True

# Конвертация в dict/tuple
d = asdict(intf)
t = astuple(intf)
```

---

## 9. Pydantic — валидация данных

**Pydantic** — библиотека для валидации и сериализации данных.
Используется в FastAPI для автоматической валидации запросов.

### BaseModel

```python
from pydantic import BaseModel, Field
from typing import Optional, List

class SyncRequest(BaseModel):
    """Запрос на синхронизацию."""

    # Обязательные поля
    site: str

    # Опциональные с значением по умолчанию
    dry_run: bool = True
    sync_all: bool = False

    # Field() — дополнительные настройки
    timeout: int = Field(default=30, ge=1, le=300)  # 1 <= timeout <= 300

    # Опциональные поля
    devices: Optional[List[str]] = None


# Создание — автоматическая валидация
request = SyncRequest(site="Office", dry_run=False)

# Ошибка валидации
try:
    bad_request = SyncRequest(site="Office", timeout=1000)  # > 300
except ValueError as e:
    print(e)  # timeout must be <= 300
```

### model_dump() и model_validate()

```python
from pydantic import BaseModel

class Interface(BaseModel):
    name: str
    status: str = "unknown"
    speed: int = 0

# Создание из словаря
data = {"name": "Gi0/1", "status": "up", "speed": 1000}
intf = Interface.model_validate(data)

# Конвертация в словарь
d = intf.model_dump()
# {'name': 'Gi0/1', 'status': 'up', 'speed': 1000}

# JSON сериализация
json_str = intf.model_dump_json()
```

**Из проекта (`api/schemas.py`):**
```python
class SyncStats(BaseModel):
    """Статистика синхронизации."""
    created: int = 0
    updated: int = 0
    deleted: int = 0
    skipped: int = 0
    failed: int = 0


class DiffEntry(BaseModel):
    """Одно изменение."""
    entity_type: str
    entity_name: str
    action: str
    device: Optional[str] = None
```

---

## 10. Исключения

### try/except/finally

```python
def connect_to_device(host):
    """Подключение с обработкой ошибок."""
    try:
        connection = create_connection(host)
        return connection

    except ConnectionError as e:
        print(f"Connection failed: {e}")
        return None

    except TimeoutError:
        print("Connection timed out")
        return None

    except Exception as e:
        print(f"Unexpected error: {e}")
        raise  # Пробросить дальше

    finally:
        # Выполняется ВСЕГДА
        print("Connection attempt finished")
```

### raise

```python
def validate_port(port):
    """Проверяет номер порта."""
    if not isinstance(port, int):
        raise TypeError(f"Port must be int, got {type(port)}")

    if not 1 <= port <= 65535:
        raise ValueError(f"Port must be 1-65535, got {port}")

    return port

# Пробросить текущее исключение
try:
    something()
except Exception:
    logger.error("Failed")
    raise
```

### Собственные исключения

```python
class NetworkCollectorError(Exception):
    """Базовое исключение проекта."""
    pass


class ConnectionError(NetworkCollectorError):
    """Ошибка подключения."""

    def __init__(self, host, message="Connection failed"):
        self.host = host
        self.message = message
        super().__init__(f"{message}: {host}")


# Использование
try:
    connect("192.168.1.1", None)
except ConnectionError as e:
    print(f"Cannot connect to {e.host}: {e.message}")
```

---

## 11. Контекстные менеджеры (with)

**Через класс:**
```python
class DatabaseConnection:
    def __init__(self, connection_string):
        self.connection_string = connection_string
        self.connection = None

    def __enter__(self):
        print("Opening connection")
        self.connection = connect(self.connection_string)
        return self.connection

    def __exit__(self, exc_type, exc_val, exc_tb):
        print("Closing connection")
        if self.connection:
            self.connection.close()
        return False


with DatabaseConnection("localhost:5432") as conn:
    conn.execute("SELECT * FROM devices")
# Соединение закрыто автоматически
```

**Через contextlib:**
```python
from contextlib import contextmanager

@contextmanager
def connection(host):
    """Контекстный менеджер через генератор."""
    conn = None
    try:
        print(f"Connecting to {host}")
        conn = create_connection(host)
        yield conn  # Возвращаем и "замораживаем"
    finally:
        print(f"Disconnecting from {host}")
        if conn:
            conn.close()


with connection("192.168.1.1") as conn:
    conn.send_command("show version")
```

---

## 12. Генераторы и comprehensions

### yield

**Генератор** — функция, которая возвращает значения по одному (лениво).

```python
def count_up_to(n):
    """Генератор чисел от 1 до n."""
    i = 1
    while i <= n:
        yield i  # Возвращаем и "замораживаем"
        i += 1


for num in count_up_to(5):
    print(num)  # 1, 2, 3, 4, 5
```

### List comprehension

```python
# Обычный способ
squares = []
for x in range(10):
    squares.append(x ** 2)

# List comprehension
squares = [x ** 2 for x in range(10)]

# С условием
even_squares = [x ** 2 for x in range(10) if x % 2 == 0]
```

**Из проекта:**
```python
# Фильтрация интерфейсов
enabled_interfaces = [
    intf for intf in interfaces
    if intf.status == "up"
]

# Извлечение IP адресов
hosts = [device.host for device in devices]
```

### Dict comprehension

```python
# Создание словаря
squares = {x: x ** 2 for x in range(5)}
# {0: 0, 1: 1, 2: 4, 3: 9, 4: 16}

# Фильтрация
config = {"host": "localhost", "port": 22, "debug": None}
clean_config = {k: v for k, v in config.items() if v is not None}
# {"host": "localhost", "port": 22}
```

### Set comprehension

```python
# Уникальные значения
vlans = {intf.vlan for intf in interfaces if intf.vlan}
```

---

## 13. Асинхронное программирование

### async/await

**Асинхронный код** — выполнение нескольких операций "одновременно" без потоков.

```python
import asyncio

async def fetch_data(url):
    """Асинхронно получает данные."""
    print(f"Fetching {url}...")
    await asyncio.sleep(1)  # await — ждём
    return f"Data from {url}"


async def main():
    # Параллельное выполнение
    results = await asyncio.gather(
        fetch_data("http://api1.com"),
        fetch_data("http://api2.com"),
        fetch_data("http://api3.com"),
    )
    # Занимает 1 секунду (все параллельно)
    return results


asyncio.run(main())
```

**Из проекта (`api/services/sync_service.py`):**
```python
class SyncService:
    async def _run_in_executor(self, func, *args):
        """Запускает синхронную функцию в executor."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, func, *args)

    async def sync(self, request: SyncRequest) -> SyncResponse:
        """Асинхронная синхронизация."""
        result = await self._run_in_executor(
            lambda: self._do_sync(request, devices, task_id, steps)
        )
        return SyncResponse(**result)
```

---

## 14. Многопоточность

### ThreadPoolExecutor

**ThreadPoolExecutor** — пул потоков для параллельных задач.

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

def collect_from_device(device):
    """Собирает данные с одного устройства."""
    return f"Data from {device}"


devices = ["192.168.1.1", "192.168.1.2", "192.168.1.3"]

# Пул из 5 потоков
with ThreadPoolExecutor(max_workers=5) as executor:
    # Способ 1: map
    results = list(executor.map(collect_from_device, devices))

    # Способ 2: submit + as_completed
    futures = {
        executor.submit(collect_from_device, d): d
        for d in devices
    }

    for future in as_completed(futures):
        device = futures[future]
        try:
            result = future.result()
            print(f"{device}: {result}")
        except Exception as e:
            print(f"{device}: Error - {e}")
```

**Из проекта (`collectors/base.py`):**
```python
class BaseCollector:
    def __init__(self, credentials=None, max_workers=5):
        self.credentials = credentials
        self.max_workers = max_workers

    def collect(self, devices: List[Device]) -> List[Any]:
        """Собирает данные параллельно."""
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            results = list(executor.map(self._collect_one, devices))
        return [r for r in results if r is not None]
```

---

## 15. Полезные паттерны из проекта

### Singleton

**Singleton** — только один экземпляр класса.

```python
# Модульный singleton — глобальная переменная
_config: Optional[AppConfig] = None

def load_config(path: str = None) -> AppConfig:
    global _config
    if _config is None:
        _config = AppConfig.from_yaml(path or "config.yaml")
    return _config

config = load_config()
```

### Factory

**Factory** — создание объектов без указания класса.

```python
class CollectorFactory:
    _collectors = {
        "devices": DeviceCollector,
        "mac": MACCollector,
        "lldp": LLDPCollector,
    }

    @classmethod
    def create(cls, collector_type: str, **kwargs) -> BaseCollector:
        collector_class = cls._collectors.get(collector_type)
        if not collector_class:
            raise ValueError(f"Unknown: {collector_type}")
        return collector_class(**kwargs)


# Использование
collector = CollectorFactory.create("mac", credentials=creds)
```

### Strategy

**Strategy** — выбор алгоритма во время выполнения.

```python
def get_exporter(format_type: str, output_folder: str):
    """Возвращает экспортер по типу (Strategy)."""
    if format_type == "csv":
        return CSVExporter(output_folder=output_folder)
    elif format_type == "json":
        return JSONExporter(output_folder=output_folder)
    else:
        return ExcelExporter(output_folder=output_folder)
```

---

## Резюме

### Ключевые файлы для изучения

| Сложность | Файл | Что изучить |
|-----------|------|-------------|
| Начальный | `core/device.py` | Простой класс |
| Начальный | `core/models.py` | Dataclass, property |
| Средний | `collectors/base.py` | Наследование, ThreadPoolExecutor |
| Средний | `netbox/sync/base.py` | Методы, кэширование |
| Средний | `api/schemas.py` | Pydantic модели |
| Продвинутый | `netbox/sync/main.py` | Множественное наследование |
| Продвинутый | `core/pipeline/executor.py` | Сложная логика |
| Продвинутый | `api/services/sync_service.py` | Async, threading |

### Порядок изучения

1. **Основы**: переменные, списки, словари, циклы, функции
2. **ООП**: классы, наследование, `self`, `__init__`
3. **Модули**: импорты, пакеты, `__init__.py`
4. **Исключения**: try/except, raise
5. **Type hints**: для понимания сигнатур
6. **Декораторы**: @property, @staticmethod, @dataclass
7. **Pydantic**: BaseModel для API
8. **Async/Threading**: для понимания параллелизма
