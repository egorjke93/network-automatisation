# Network Collector — Полный учебный гайд

Этот документ объясняет проект от и до: от ввода команды до экспорта/синхронизации с NetBox.
Каждый раздел содержит примеры кода из проекта с объяснениями Python-концепций.

## Содержание

1. [Основы Python в проекте](#1-основы-python-в-проекте)
2. [Точка входа: CLI](#2-точка-входа-cli)
3. [Загрузка конфигурации](#3-загрузка-конфигурации)
4. [Подключение к устройствам](#4-подключение-к-устройствам)
5. [Сбор данных (Collectors)](#5-сбор-данных-collectors)
6. [Парсинг вывода (TextFSM/NTC)](#6-парсинг-вывода-textfsm-ntc)
7. [Нормализация данных](#7-нормализация-данных)
8. [Domain Layer (бизнес-логика)](#8-domain-layer-бизнес-логика)
9. [Экспорт данных](#9-экспорт-данных)
10. [Синхронизация с NetBox](#10-синхронизация-с-netbox)
11. [Полный путь данных](#11-полный-путь-данных)

---

## 1. Основы Python в проекте

### 1.1 Структура проекта

```
network_collector/
├── __init__.py          # Делает папку Python-пакетом
├── __main__.py          # Точка входа: python -m network_collector
├── cli/                 # CLI модуль (модульная структура)
│   ├── __init__.py      # main(), setup_parser()
│   ├── utils.py         # load_devices, get_exporter
│   └── commands/        # Обработчики команд
├── config.py            # Загрузка конфигурации
│
├── core/                # Ядро: модели, подключения
│   ├── models.py        # Dataclass-ы (Device, Interface, etc.)
│   ├── connection.py    # SSH подключения
│   ├── constants.py     # Константы (команды, маппинги)
│   └── domain/          # Бизнес-логика (нормализация)
│
├── collectors/          # Сборщики данных
│   ├── base.py          # Базовый класс
│   ├── device.py        # show version
│   ├── mac.py           # MAC-адреса
│   ├── lldp.py          # LLDP/CDP
│   └── ...
│
├── exporters/           # Экспорт (Excel, CSV, JSON)
│   ├── base.py
│   ├── excel.py
│   └── ...
│
└── netbox/              # Интеграция с NetBox
    ├── client.py        # API клиент
    └── sync/            # Синхронизация (модули)
        ├── main.py      # NetBoxSync
        └── *.py         # Mixins
```

### 1.2 Ключевые концепции Python

#### Импорты

```python
# Стандартные библиотеки (встроены в Python)
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

# Сторонние библиотеки (pip install)
from scrapli import Scrapli
import pandas as pd

# Локальные импорты (из нашего проекта)
from .core.models import Device
from ..collectors import MACCollector
```

**Что значит `.` и `..`:**
- `.core` — подпапка текущего пакета
- `..collectors` — папка на уровень выше

#### Dataclasses (модели данных)

```python
# core/models.py
from dataclasses import dataclass, field
from typing import Optional, List

@dataclass
class Device:
    """Устройство для подключения."""
    host: str                           # Обязательное поле
    platform: str = "cisco_ios"         # Значение по умолчанию
    port: int = 22
    status: str = "unknown"

    def __post_init__(self):
        """Вызывается после создания объекта."""
        # Валидация или преобразование
        if not self.host:
            raise ValueError("host не может быть пустым")
```

**Использование:**
```python
device = Device(host="10.0.0.1", platform="cisco_iosxe")
print(device.host)      # 10.0.0.1
print(device.platform)  # cisco_iosxe
```

#### Type Hints (типизация)

```python
def collect_data(
    devices: List[Device],              # Список объектов Device
    credentials: Credentials,           # Объект Credentials
    timeout: int = 30,                  # int с дефолтом
) -> List[Dict[str, Any]]:             # Возвращает список словарей
    """
    Собирает данные с устройств.

    Args:
        devices: Список устройств
        credentials: Учётные данные
        timeout: Таймаут в секундах

    Returns:
        Список словарей с данными
    """
    results = []
    for device in devices:
        data = process(device)
        results.append(data)
    return results
```

**Типы которые используются:**
- `str`, `int`, `bool`, `float` — простые типы
- `List[str]` — список строк
- `Dict[str, Any]` — словарь с ключами-строками и любыми значениями
- `Optional[str]` — строка или None
- `Tuple[str, int]` — кортеж (строка, число)

#### Классы и наследование

```python
# collectors/base.py
class BaseCollector:
    """Базовый класс для всех коллекторов."""

    def __init__(self, credentials: Credentials, transport: str = "ssh2"):
        self.credentials = credentials
        self.transport = transport
        self._logger = logging.getLogger(self.__class__.__name__)

    def collect(self, devices: List[Device]) -> List[Dict]:
        """Шаблонный метод — определяет общий алгоритм."""
        results = []
        for device in devices:
            data = self._collect_from_device(device)  # Вызывает метод потомка
            results.extend(data)
        return results

    def _collect_from_device(self, device: Device) -> List[Dict]:
        """Абстрактный метод — должен быть переопределён."""
        raise NotImplementedError("Переопредели в наследнике")


# collectors/mac.py
class MACCollector(BaseCollector):
    """Коллектор MAC-адресов. Наследует BaseCollector."""

    def _collect_from_device(self, device: Device) -> List[Dict]:
        """Реализация для MAC."""
        # Здесь логика сбора MAC
        return [{"mac": "aa:bb:cc:dd:ee:ff", "interface": "Gi0/1"}]
```

#### Context Managers (with)

```python
# Автоматическое закрытие ресурсов
with open("file.txt", "r") as f:
    content = f.read()
# Файл автоматически закрыт после выхода из with

# В проекте — для SSH подключений
with connection_manager.connect(device, credentials) as conn:
    response = conn.send_command("show version")
# Соединение автоматически закрыто
```

**Как это работает:**
```python
class ConnectionManager:
    def connect(self, device, credentials):
        return ConnectionContext(device, credentials)

class ConnectionContext:
    def __enter__(self):
        """Вызывается при входе в with."""
        self.conn = self._open_connection()
        return self.conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Вызывается при выходе из with (даже при ошибке)."""
        self.conn.close()
```

#### Декораторы

```python
# Простой декоратор — добавляет функциональность
def log_call(func):
    """Логирует вызов функции."""
    def wrapper(*args, **kwargs):
        print(f"Вызов {func.__name__}")
        result = func(*args, **kwargs)
        print(f"Результат: {result}")
        return result
    return wrapper

@log_call
def add(a, b):
    return a + b

add(2, 3)
# Вывод:
# Вызов add
# Результат: 5
```

**В проекте используются:**
- `@dataclass` — автоматическое создание __init__, __repr__
- `@property` — метод как свойство
- `@staticmethod` — метод без self

#### Исключения (Exceptions)

```python
try:
    with conn_manager.connect(device, credentials) as conn:
        response = conn.send_command(command)

except ConnectionError as e:
    # Ошибка подключения
    logger.error(f"Не удалось подключиться: {e}")

except TimeoutError as e:
    # Таймаут
    logger.error(f"Таймаут: {e}")

except Exception as e:
    # Любая другая ошибка
    logger.error(f"Неизвестная ошибка: {e}")

finally:
    # Выполнится в любом случае
    cleanup()
```

#### Словари (Dict) — основная структура данных

```python
# Создание
device_data = {
    "hostname": "switch1",
    "ip": "10.0.0.1",
    "interfaces": ["Gi0/1", "Gi0/2"]
}

# Доступ
hostname = device_data["hostname"]           # Ошибка если нет ключа
hostname = device_data.get("hostname")       # None если нет ключа
hostname = device_data.get("hostname", "")   # "" если нет ключа

# Проверка наличия ключа
if "hostname" in device_data:
    print(device_data["hostname"])

# Итерация
for key, value in device_data.items():
    print(f"{key}: {value}")

# Обновление
device_data["status"] = "online"
device_data.update({"vendor": "Cisco", "model": "C9200"})
```

---

## 2. Точка входа: CLI

### 2.1 Как запускается программа

```bash
python -m network_collector devices --format excel
```

**Что происходит:**

1. Python видит `-m network_collector` и ищет папку `network_collector/`
2. Находит `__main__.py` и выполняет его
3. `__main__.py` вызывает `cli.main()`

```python
# __main__.py
"""Точка входа при запуске python -m network_collector."""
from .cli import main

if __name__ == "__main__":
    main()
```

### 2.2 Разбор аргументов (argparse)

```python
# cli.py
import argparse

def build_parser() -> argparse.ArgumentParser:
    """Создаёт парсер аргументов командной строки."""

    # Главный парсер
    parser = argparse.ArgumentParser(
        prog="network_collector",
        description="Утилита для сбора данных с сетевых устройств",
    )

    # Общие аргументы (для всех команд)
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",      # Флаг: True если указан
        help="Подробный вывод (DEBUG)",
    )
    parser.add_argument(
        "-d", "--devices",
        default="devices_ips.py",
        help="Файл со списком устройств",
    )

    # Подкоманды (devices, mac, lldp, etc.)
    subparsers = parser.add_subparsers(dest="command", help="Команды")

    # Подкоманда: devices
    devices_parser = subparsers.add_parser("devices", help="Сбор инвентаризации")
    devices_parser.add_argument(
        "--format", "-f",
        choices=["excel", "csv", "json", "raw"],
        default="excel",
        help="Формат вывода",
    )

    # Подкоманда: mac
    mac_parser = subparsers.add_parser("mac", help="Сбор MAC-адресов")
    mac_parser.add_argument(
        "--format", "-f",
        choices=["excel", "csv", "json", "raw"],
        default="excel",
    )
    mac_parser.add_argument(
        "--with-descriptions",
        action="store_true",
        help="Собирать описания интерфейсов",
    )

    return parser


def main():
    """Главная функция CLI."""
    parser = build_parser()
    args = parser.parse_args()  # Парсит sys.argv

    # args.command = "devices", "mac", "lldp", etc.
    # args.format = "excel", "csv", etc.
    # args.verbose = True/False

    # Маршрутизация на обработчик команды
    if args.command == "devices":
        cmd_devices(args)
    elif args.command == "mac":
        cmd_mac(args)
    elif args.command == "lldp":
        cmd_lldp(args)
    # ...
```

### 2.3 Обработчик команды

```python
# cli.py
def cmd_mac(args, ctx=None) -> None:
    """Обработчик команды mac."""

    # 1. Загружаем устройства и credentials
    devices, credentials = prepare_collection(args)

    # 2. Создаём коллектор
    collector = MACCollector(
        credentials=credentials,
        transport=args.transport,
        collect_descriptions=getattr(args, "with_descriptions", False),
    )

    # 3. Собираем данные
    data = collector.collect(devices)

    # 4. Применяем фильтр полей из fields.yaml
    data = apply_fields_config(data, "mac")

    # 5. Экспортируем
    exporter = get_exporter(args.format, args.output, args.delimiter)
    file_path = exporter.export(data, "mac_addresses")

    if file_path:
        logger.info(f"Отчёт сохранён: {file_path}")
```

---

## 3. Загрузка конфигурации

### 3.1 YAML файлы

```yaml
# config.yaml
output:
  output_folder: "reports"
  default_format: "excel"

connection:
  conn_timeout: 10
  read_timeout: 30
  max_workers: 5

netbox:
  url: "https://netbox.example.com/"
  token: "your-token"
```

### 3.2 Чтение YAML в Python

```python
# config.py
import yaml
from pathlib import Path

def load_config(config_path: str = "config.yaml") -> dict:
    """Загружает конфигурацию из YAML файла."""

    path = Path(config_path)

    if not path.exists():
        return {}  # Пустой конфиг если файла нет

    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)  # Парсит YAML → dict

    return config or {}


# Использование
config = load_config()
timeout = config.get("connection", {}).get("conn_timeout", 10)
#                    ↑ секция          ↑ параметр      ↑ дефолт
```

### 3.3 Загрузка устройств

```python
# devices_ips.py (файл пользователя)
devices_list = [
    {"host": "10.0.0.1", "platform": "cisco_iosxe"},
    {"host": "10.0.0.2", "platform": "cisco_nxos"},
    {"host": "10.0.0.3", "platform": "arista_eos"},
]
```

```python
# cli.py
def load_devices(devices_file: str) -> List[Device]:
    """Загружает устройства из Python файла."""

    import importlib.util

    # Динамически импортируем Python файл
    spec = importlib.util.spec_from_file_location("devices", devices_file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # Получаем список devices_list из модуля
    devices_data = getattr(module, "devices_list", [])

    # Конвертируем dict → Device объекты
    devices = []
    for d in devices_data:
        device = Device(
            host=d["host"],
            platform=d.get("platform", "cisco_ios"),
            port=d.get("port", 22),
        )
        devices.append(device)

    return devices
```

---

## 4. Подключение к устройствам

### 4.1 SSH через Scrapli

```python
# core/connection.py
from scrapli import Scrapli

class ConnectionManager:
    """Управляет SSH подключениями."""

    def __init__(
        self,
        transport: str = "ssh2",
        max_retries: int = 2,
        retry_delay: int = 5,
    ):
        self.transport = transport
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def connect(self, device: Device, credentials: Credentials):
        """Создаёт подключение к устройству."""

        # Параметры для Scrapli
        conn_params = {
            "host": device.host,
            "port": device.port,
            "auth_username": credentials.username,
            "auth_password": credentials.password,
            "platform": device.platform,
            "transport": self.transport,
        }

        # Создаём и возвращаем объект соединения
        conn = Scrapli(**conn_params)
        conn.open()
        return conn
```

### 4.2 Отправка команд

```python
# Простая отправка команды
response = conn.send_command("show version")
print(response.result)  # Текстовый вывод

# Несколько команд
responses = conn.send_commands([
    "show version",
    "show interfaces",
    "show mac address-table",
])
for resp in responses:
    print(resp.result)
```

### 4.3 Retry логика

```python
def connect_with_retry(self, device: Device, credentials: Credentials):
    """Подключение с повторными попытками."""

    last_error = None

    for attempt in range(self.max_retries + 1):
        try:
            conn = self.connect(device, credentials)
            return conn  # Успех — возвращаем соединение

        except Exception as e:
            last_error = e

            if attempt < self.max_retries:
                logger.warning(
                    f"Попытка {attempt + 1} не удалась: {e}. "
                    f"Повтор через {self.retry_delay} сек..."
                )
                time.sleep(self.retry_delay)

    # Все попытки исчерпаны
    raise ConnectionError(f"Не удалось подключиться: {last_error}")
```

---

## 5. Сбор данных (Collectors)

### 5.1 Базовый класс

```python
# collectors/base.py
class BaseCollector:
    """Базовый класс для всех коллекторов."""

    # Команды для разных платформ
    platform_commands = {}  # Переопределяется в наследниках

    def __init__(
        self,
        credentials: Credentials = None,
        transport: str = "ssh2",
    ):
        self.credentials = credentials
        self.transport = transport
        self._conn_manager = ConnectionManager(transport=transport)

    def collect(self, devices: List[Device]) -> List[Dict[str, Any]]:
        """Собирает данные со всех устройств."""
        all_data = []

        for device in devices:
            try:
                data = self._collect_from_device(device)
                all_data.extend(data)
            except Exception as e:
                logger.error(f"Ошибка на {device.host}: {e}")

        return all_data

    def _collect_from_device(self, device: Device) -> List[Dict]:
        """Собирает данные с одного устройства."""
        raise NotImplementedError

    def _get_command(self, device: Device) -> str:
        """Возвращает команду для платформы."""
        return self.platform_commands.get(device.platform, "")
```

### 5.2 Конкретный коллектор (MAC)

```python
# collectors/mac.py
from .base import BaseCollector
from ..core.constants import COLLECTOR_COMMANDS

class MACCollector(BaseCollector):
    """Коллектор MAC-адресов."""

    platform_commands = COLLECTOR_COMMANDS.get("mac", {})
    # {
    #     "cisco_ios": "show mac address-table",
    #     "cisco_nxos": "show mac address-table",
    #     "arista_eos": "show mac address-table",
    # }

    def __init__(
        self,
        collect_descriptions: bool = False,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.collect_descriptions = collect_descriptions
        self._normalizer = MACNormalizer()

    def _collect_from_device(self, device: Device) -> List[Dict]:
        """Собирает MAC-таблицу с устройства."""

        command = self._get_command(device)
        if not command:
            logger.warning(f"Нет команды для {device.platform}")
            return []

        with self._conn_manager.connect(device, self.credentials) as conn:
            # 1. Получаем hostname
            hostname = self._get_hostname(conn)

            # 2. Отправляем команду
            response = conn.send_command(command)

            # 3. Парсим вывод
            raw_data = self._parse_output(response.result, device)

            # 4. Нормализуем
            data = self._normalizer.normalize_dicts(
                raw_data,
                hostname=hostname,
                device_ip=device.host,
            )

            # 5. Собираем описания (опционально)
            if self.collect_descriptions:
                descriptions = self._get_descriptions(conn)
                data = self._enrich_descriptions(data, descriptions)

            return data
```

---

## 6. Парсинг вывода (TextFSM/NTC)

### 6.1 Что такое TextFSM

TextFSM — библиотека для парсинга текста по шаблонам.
NTC Templates — готовые шаблоны для сетевых команд.

**Сырой вывод устройства:**
```
switch1#show mac address-table
          Mac Address Table
-------------------------------------------

Vlan    Mac Address       Type        Ports
----    -----------       --------    -----
   1    0011.2233.4455    DYNAMIC     Gi0/1
  10    aabb.ccdd.eeff    DYNAMIC     Gi0/2
```

**После парсинга NTC:**
```python
[
    {"vlan": "1", "mac": "0011.2233.4455", "type": "DYNAMIC", "ports": "Gi0/1"},
    {"vlan": "10", "mac": "aabb.ccdd.eeff", "type": "DYNAMIC", "ports": "Gi0/2"},
]
```

### 6.2 Использование в проекте

```python
from ntc_templates.parse import parse_output

def _parse_output(self, output: str, device: Device) -> List[Dict]:
    """Парсит вывод команды через NTC Templates."""

    # Определяем платформу для NTC
    ntc_platform = get_ntc_platform(device.platform)
    # cisco_iosxe → cisco_ios (NTC использует свои названия)

    command = self._get_command(device)

    try:
        # NTC парсит текст → список словарей
        parsed = parse_output(
            platform=ntc_platform,
            command=command,
            data=output,
        )
        return parsed

    except Exception as e:
        logger.warning(f"NTC парсинг не удался: {e}")
        return []
```

### 6.3 Маппинг платформ

```python
# core/constants.py
NTC_PLATFORM_MAP = {
    "cisco_iosxe": "cisco_ios",    # IOS-XE → cisco_ios в NTC
    "cisco_ios": "cisco_ios",
    "cisco_nxos": "cisco_nxos",
    "arista_eos": "arista_eos",
    "juniper_junos": "juniper_junos",
}

def get_ntc_platform(scrapli_platform: str) -> str:
    """Конвертирует Scrapli платформу в NTC."""
    return NTC_PLATFORM_MAP.get(scrapli_platform, scrapli_platform)
```

---

## 7. Нормализация данных

### 7.1 Зачем нужна нормализация

**Проблема:** разные платформы возвращают разные имена полей.

```python
# Cisco IOS (от NTC)
{"destination_address": "0011.2233.4455", "destination_port": "Gi0/1"}

# Cisco NX-OS (от NTC)
{"mac_address": "0011.2233.4455", "port": "Eth1/1"}

# Arista (от NTC)
{"mac": "00:11:22:33:44:55", "interface": "Et1"}
```

**Решение:** нормализатор приводит к единому формату.

```python
# После нормализации — единый формат для всех
{
    "hostname": "switch1",
    "device_ip": "10.0.0.1",
    "mac_address": "00:11:22:33:44:55",  # Единое имя
    "interface": "GigabitEthernet0/1",   # Полное имя
    "vlan": 10,
}
```

### 7.2 Класс нормализатора

```python
# core/domain/mac.py
class MACNormalizer:
    """Нормализатор MAC-таблицы."""

    # Маппинг имён полей: NTC → наши
    KEY_MAPPING = {
        "destination_address": "mac_address",
        "mac_address": "mac_address",
        "mac": "mac_address",
        "destination_port": "interface",
        "port": "interface",
        "ports": "interface",
        "vlan_id": "vlan",
        "vlan": "vlan",
    }

    def normalize_dicts(
        self,
        data: List[Dict],
        hostname: str = "",
        device_ip: str = "",
    ) -> List[Dict]:
        """Нормализует список словарей."""

        result = []

        for row in data:
            normalized = self._normalize_row(row)

            # Добавляем контекст
            normalized["hostname"] = hostname
            normalized["device_ip"] = device_ip

            result.append(normalized)

        return result

    def _normalize_row(self, row: Dict) -> Dict:
        """Нормализует одну запись."""

        result = {}

        for key, value in row.items():
            # Переименовываем ключ если есть маппинг
            new_key = self.KEY_MAPPING.get(key.lower(), key)
            result[new_key] = value

        # Нормализуем MAC формат
        if "mac_address" in result:
            result["mac_address"] = self._normalize_mac(result["mac_address"])

        # Нормализуем имя интерфейса
        if "interface" in result:
            result["interface"] = self._normalize_interface(result["interface"])

        return result

    def _normalize_mac(self, mac: str) -> str:
        """Приводит MAC к формату AA:BB:CC:DD:EE:FF."""
        # Убираем разделители
        mac_clean = mac.replace(".", "").replace(":", "").replace("-", "")
        # Форматируем
        return ":".join(mac_clean[i:i+2].upper() for i in range(0, 12, 2))

    def _normalize_interface(self, interface: str) -> str:
        """Разворачивает сокращение интерфейса."""
        expansions = {
            "Gi": "GigabitEthernet",
            "Fa": "FastEthernet",
            "Te": "TenGigabitEthernet",
            "Eth": "Ethernet",
            "Po": "Port-channel",
        }
        for short, full in expansions.items():
            if interface.startswith(short) and not interface.startswith(full):
                return interface.replace(short, full, 1)
        return interface
```

---

## 8. Domain Layer (бизнес-логика)

Domain Layer — это слой бизнес-логики. Здесь живёт вся логика преобразования данных, не зависящая от внешних систем (SSH, NetBox API, файлы).

### 8.1 Что такое Domain Layer

**Принцип:** отделить бизнес-логику от инфраструктуры.

```
┌─────────────────────────────────────────────────────────────┐
│                    ИНФРАСТРУКТУРА                            │
│  SSH (Scrapli)  │  NetBox API  │  Файлы (Excel, JSON)       │
└────────┬────────────────┬─────────────────┬─────────────────┘
         │                │                 │
         ▼                ▼                 ▼
┌─────────────────────────────────────────────────────────────┐
│                     DOMAIN LAYER                             │
│  Нормализаторы  │  Валидаторы  │  Сравнение (Diff)          │
│  Объединение    │  Фильтрация  │  Преобразование            │
└─────────────────────────────────────────────────────────────┘
```

**Зачем это нужно:**
- Код легко тестировать (не нужен SSH/NetBox для тестов)
- Логика в одном месте (не размазана по проекту)
- Можно переиспользовать (CLI, API, тесты)

### 8.2 Структура папки core/domain/

```
core/domain/
├── __init__.py         # Экспорт классов
├── mac.py              # MACNormalizer
├── lldp.py             # LLDPNormalizer + merge логика
├── interface.py        # InterfaceNormalizer
├── inventory.py        # InventoryNormalizer
└── sync.py             # DiffCalculator, SyncComparator
```

### 8.3 Паттерн: Normalizer

Каждый тип данных имеет свой нормализатор с единым интерфейсом.

```python
# core/domain/base.py (концептуально)
class BaseNormalizer:
    """Базовый класс нормализатора."""

    # Маппинг NTC полей → наши поля
    KEY_MAPPING: Dict[str, str] = {}

    def normalize_dicts(
        self,
        data: List[Dict[str, Any]],
        **context,  # hostname, device_ip, etc.
    ) -> List[Dict[str, Any]]:
        """Нормализует список словарей."""
        return [self._normalize_row(row, **context) for row in data]

    def _normalize_row(self, row: Dict, **context) -> Dict:
        """Нормализует одну запись."""
        result = {}

        # 1. Переименовываем ключи
        for key, value in row.items():
            new_key = self.KEY_MAPPING.get(key.lower(), key)
            result[new_key] = value

        # 2. Добавляем контекст
        result.update(context)

        # 3. Специфичная обработка (переопределяется)
        return self._post_process(result)

    def _post_process(self, row: Dict) -> Dict:
        """Хук для дополнительной обработки."""
        return row
```

### 8.4 Пример: LLDPNormalizer

```python
# core/domain/lldp.py
class LLDPNormalizer:
    """Нормализатор LLDP/CDP данных."""

    KEY_MAPPING = {
        # NTC поля → наши поля
        "neighbor": "remote_hostname",
        "chassis_id": "remote_mac",
        "port_id": "remote_port",
        "port_description": "port_description",
        "system_name": "remote_hostname",
        "system_description": "remote_description",
        "management_ip": "remote_ip",
        "platform": "remote_platform",
        "local_interface": "local_interface",
        "local_port": "local_interface",
    }

    def normalize_dicts(
        self,
        data: List[Dict],
        protocol: str = "lldp",
        hostname: str = "",
        device_ip: str = "",
    ) -> List[Dict]:
        """Нормализует LLDP/CDP данные."""

        result = []

        for row in data:
            normalized = {}

            # 1. Переименовываем ключи
            for key, value in row.items():
                new_key = self.KEY_MAPPING.get(key.lower(), key)
                normalized[new_key] = value

            # 2. Добавляем контекст
            normalized["hostname"] = hostname
            normalized["device_ip"] = device_ip
            normalized["protocol"] = protocol.upper()

            # 3. Определяем тип соседа
            normalized["neighbor_type"] = self._determine_neighbor_type(
                normalized.get("remote_hostname", ""),
                normalized.get("remote_description", ""),
            )

            # 4. Нормализуем MAC
            if "remote_mac" in normalized:
                normalized["remote_mac"] = self._normalize_mac(
                    normalized["remote_mac"]
                )

            result.append(normalized)

        return result

    def _determine_neighbor_type(self, hostname: str, description: str) -> str:
        """Определяет тип соседа: switch, phone, ap, server, unknown."""

        text = f"{hostname} {description}".lower()

        if "phone" in text or "cp-" in text:
            return "phone"
        if "ap" in text or "air-" in text:
            return "ap"
        if any(x in text for x in ["switch", "router", "nexus", "catalyst"]):
            return "switch"
        if any(x in text for x in ["server", "linux", "vmware", "esxi"]):
            return "server"

        return "unknown"
```

### 8.5 Пример: Merge LLDP + CDP

Ключевая логика — объединение данных из двух протоколов.

```python
# core/domain/lldp.py
class LLDPNormalizer:
    # ... (предыдущий код)

    def merge_lldp_cdp(
        self,
        lldp_data: List[Dict],
        cdp_data: List[Dict],
    ) -> List[Dict]:
        """
        Объединяет LLDP и CDP данные.

        Логика:
        - CDP — база (содержит platform)
        - LLDP — дополняет MAC (chassis_id)
        - Совпадение по local_interface + remote_hostname
        """

        # Только LLDP
        if not cdp_data:
            for row in lldp_data:
                row["protocol"] = "BOTH"
            return lldp_data

        # Только CDP
        if not lldp_data:
            for row in cdp_data:
                row["protocol"] = "BOTH"
            return cdp_data

        # Индексируем LLDP по ключу
        lldp_index = {}
        for row in lldp_data:
            key = self._make_merge_key(row)
            lldp_index[key] = row

        result = []

        # Проходим по CDP (база)
        for cdp_row in cdp_data:
            key = self._make_merge_key(cdp_row)
            merged = cdp_row.copy()

            # Ищем соответствующую LLDP запись
            if key in lldp_index:
                lldp_row = lldp_index[key]

                # Берём MAC из LLDP (chassis_id более надёжен)
                if lldp_row.get("remote_mac"):
                    merged["remote_mac"] = lldp_row["remote_mac"]

            merged["protocol"] = "BOTH"
            result.append(merged)

            # Удаляем из индекса (чтобы не дублировать)
            lldp_index.pop(key, None)

        # Добавляем LLDP записи, которых нет в CDP
        for lldp_row in lldp_index.values():
            lldp_row["protocol"] = "BOTH"
            result.append(lldp_row)

        return result

    def _make_merge_key(self, row: Dict) -> tuple:
        """Создаёт ключ для объединения."""
        return (
            row.get("local_interface", "").lower(),
            self._normalize_hostname(row.get("remote_hostname", "")),
        )

    def _normalize_hostname(self, hostname: str) -> str:
        """Убирает домен из hostname."""
        return hostname.split(".")[0].lower()
```

### 8.6 Пример: DiffCalculator (Sync)

```python
# core/domain/sync.py
from dataclasses import dataclass
from typing import List, Dict, Any

@dataclass
class SyncDiff:
    """Результат сравнения локальных и удалённых данных."""
    to_create: List[Dict]   # Есть локально, нет удалённо
    to_update: List[Dict]   # Есть и там, и там, но отличаются
    to_delete: List[Dict]   # Есть удалённо, нет локально
    unchanged: List[Dict]   # Одинаковые

    @property
    def has_changes(self) -> bool:
        """Есть ли изменения."""
        return bool(self.to_create or self.to_update or self.to_delete)


class SyncComparator:
    """Сравнивает локальные и удалённые данные."""

    def __init__(self, key_field: str = "name"):
        self.key_field = key_field

    def compare(
        self,
        local: List[Dict],
        remote: List[Dict],
        compare_fields: List[str] = None,
    ) -> SyncDiff:
        """
        Сравнивает два списка и возвращает diff.

        Args:
            local: Локальные данные (с устройств)
            remote: Удалённые данные (из NetBox)
            compare_fields: Поля для сравнения (если None — все)
        """
        local_by_key = {item[self.key_field]: item for item in local}
        remote_by_key = {item[self.key_field]: item for item in remote}

        to_create = []
        to_update = []
        unchanged = []

        # Проходим по локальным
        for key, local_item in local_by_key.items():
            if key not in remote_by_key:
                # Нет в remote → создать
                to_create.append(local_item)
            else:
                # Есть в remote → проверяем изменения
                remote_item = remote_by_key[key]
                if self._has_differences(local_item, remote_item, compare_fields):
                    to_update.append({
                        "local": local_item,
                        "remote": remote_item,
                        "changes": self._get_changes(local_item, remote_item, compare_fields),
                    })
                else:
                    unchanged.append(local_item)

        # Есть в remote, нет локально → удалить
        to_delete = [
            remote_by_key[key]
            for key in remote_by_key
            if key not in local_by_key
        ]

        return SyncDiff(
            to_create=to_create,
            to_update=to_update,
            to_delete=to_delete,
            unchanged=unchanged,
        )

    def _has_differences(
        self,
        local: Dict,
        remote: Dict,
        fields: List[str] = None,
    ) -> bool:
        """Проверяет есть ли различия."""
        fields = fields or list(local.keys())

        for field in fields:
            if local.get(field) != remote.get(field):
                return True
        return False

    def _get_changes(
        self,
        local: Dict,
        remote: Dict,
        fields: List[str] = None,
    ) -> Dict:
        """Возвращает словарь изменений."""
        fields = fields or list(local.keys())
        changes = {}

        for field in fields:
            local_val = local.get(field)
            remote_val = remote.get(field)
            if local_val != remote_val:
                changes[field] = {"old": remote_val, "new": local_val}

        return changes
```

### 8.7 Почему Domain Layer важен

**Без Domain Layer:**
```python
# Всё в одном месте — каша
def cmd_lldp(args):
    for device in devices:
        output = ssh_connect_and_run(device, "show lldp")
        parsed = ntc_parse(output)

        # Нормализация прямо здесь
        for row in parsed:
            row["hostname"] = get_hostname(device)
            if row.get("neighbor"):
                row["remote_hostname"] = row.pop("neighbor")
            # ... ещё 50 строк преобразований

        # Сравнение с NetBox прямо здесь
        for row in parsed:
            existing = netbox.get(row["remote_hostname"])
            if existing:
                # ... логика update
            else:
                # ... логика create
```

**С Domain Layer:**
```python
# Чистый, понятный код
def cmd_lldp(args):
    # 1. Сбор (инфраструктура)
    collector = LLDPCollector(credentials)
    raw_data = collector.collect(devices)

    # 2. Нормализация (domain)
    normalizer = LLDPNormalizer()
    data = normalizer.normalize_dicts(raw_data)

    # 3. Экспорт или sync (инфраструктура)
    exporter.export(data, "lldp")
```

**Тестирование:**
```python
# test_domain/test_lldp_normalizer.py
def test_merge_lldp_cdp():
    """Тестируем merge БЕЗ SSH, БЕЗ NetBox."""
    normalizer = LLDPNormalizer()

    lldp = [{"local_interface": "Gi0/1", "remote_hostname": "switch2"}]
    cdp = [{"local_interface": "Gi0/1", "remote_hostname": "switch2", "platform": "Cisco"}]

    result = normalizer.merge_lldp_cdp(lldp, cdp)

    assert result[0]["protocol"] == "BOTH"
    assert result[0]["remote_platform"] == "Cisco"
```

---

## 9. Экспорт данных

### 9.1 Базовый экспортер

```python
# exporters/base.py
from abc import ABC, abstractmethod
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

class BaseExporter(ABC):
    """Абстрактный базовый класс для экспортеров."""

    file_extension = ""  # Переопределяется в наследниках

    def __init__(
        self,
        output_folder: str = "reports",
        encoding: str = "utf-8",
    ):
        self.output_folder = Path(output_folder)
        self.encoding = encoding

    def export(
        self,
        data: List[Dict[str, Any]],
        filename: str,
    ) -> Optional[str]:
        """
        Экспортирует данные в файл.

        Args:
            data: Список словарей с данными
            filename: Имя файла (без расширения)

        Returns:
            Путь к созданному файлу или None
        """
        if not data:
            return None

        # Создаём папку если нет
        self.output_folder.mkdir(parents=True, exist_ok=True)

        # Формируем путь: reports/2026-01-12_mac_addresses.xlsx
        timestamp = datetime.now().strftime("%Y-%m-%d")
        file_path = self.output_folder / f"{timestamp}_{filename}{self.file_extension}"

        # Вызываем абстрактный метод записи
        self._write(data, file_path)

        return str(file_path)

    @abstractmethod
    def _write(self, data: List[Dict], file_path: Path) -> None:
        """Записывает данные в файл. Реализуется в наследниках."""
        pass
```

### 9.2 Excel экспортер

```python
# exporters/excel.py
import pandas as pd
from openpyxl.styles import Font, PatternFill
from .base import BaseExporter

class ExcelExporter(BaseExporter):
    """Экспортер в Excel с форматированием."""

    file_extension = ".xlsx"

    def _write(self, data: List[Dict], file_path: Path) -> None:
        """Записывает данные в Excel."""

        # Конвертируем список словарей в DataFrame
        df = pd.DataFrame(data)

        # Записываем в Excel
        with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Data")

            # Форматируем
            workbook = writer.book
            worksheet = writer.sheets["Data"]

            # Заголовок — жирный, с фоном
            header_font = Font(bold=True)
            header_fill = PatternFill("solid", fgColor="CCCCCC")

            for cell in worksheet[1]:
                cell.font = header_font
                cell.fill = header_fill

            # Автоширина колонок
            for column in worksheet.columns:
                max_length = max(len(str(cell.value or "")) for cell in column)
                worksheet.column_dimensions[column[0].column_letter].width = max_length + 2
```

### 9.3 Фабрика экспортеров

```python
# cli.py
def get_exporter(format_type: str, output_folder: str, delimiter: str = ","):
    """Возвращает экспортер по типу формата."""

    from .exporters import CSVExporter, JSONExporter, ExcelExporter, RawExporter

    if format_type == "csv":
        return CSVExporter(output_folder=output_folder, delimiter=delimiter)
    elif format_type == "json":
        return JSONExporter(output_folder=output_folder)
    elif format_type == "raw":
        return RawExporter()  # Вывод в stdout
    else:
        return ExcelExporter(output_folder=output_folder)
```

---

## 10. Синхронизация с NetBox

### 10.1 NetBox API клиент

```python
# netbox/client.py
import pynetbox

class NetBoxClient:
    """Клиент для работы с NetBox API."""

    def __init__(self, url: str, token: str):
        self.api = pynetbox.api(url, token=token)

    def get_device(self, name: str):
        """Получает устройство по имени."""
        return self.api.dcim.devices.get(name=name)

    def create_device(self, data: dict):
        """Создаёт устройство."""
        return self.api.dcim.devices.create(data)

    def get_interfaces(self, device_id: int):
        """Получает интерфейсы устройства."""
        return self.api.dcim.interfaces.filter(device_id=device_id)
```

### 10.2 Логика синхронизации

```python
# netbox/sync/main.py (mixins в отдельных файлах)
class NetBoxSync:
    """Синхронизация данных с NetBox."""

    def __init__(self, client: NetBoxClient):
        self.client = client

    def sync_interfaces(
        self,
        hostname: str,
        interfaces: List[Dict],
        update_existing: bool = True,
    ) -> Dict[str, int]:
        """
        Синхронизирует интерфейсы устройства.

        Returns:
            Статистика: {"created": N, "updated": N, "skipped": N}
        """
        stats = {"created": 0, "updated": 0, "skipped": 0, "failed": 0}

        # Получаем устройство из NetBox
        device = self.client.get_device(hostname)
        if not device:
            logger.error(f"Устройство {hostname} не найдено в NetBox")
            return stats

        # Получаем существующие интерфейсы
        existing = {i.name: i for i in self.client.get_interfaces(device.id)}

        for iface_data in interfaces:
            name = iface_data["name"]

            if name in existing:
                # Интерфейс существует
                if update_existing:
                    self._update_interface(existing[name], iface_data)
                    stats["updated"] += 1
                else:
                    stats["skipped"] += 1
            else:
                # Создаём новый
                self._create_interface(device.id, iface_data)
                stats["created"] += 1

        return stats

    def _create_interface(self, device_id: int, data: Dict):
        """Создаёт интерфейс в NetBox."""
        self.client.api.dcim.interfaces.create({
            "device": device_id,
            "name": data["name"],
            "type": data.get("type", "other"),
            "enabled": data.get("enabled", True),
            "description": data.get("description", ""),
        })

    def _update_interface(self, interface, data: Dict):
        """Обновляет интерфейс в NetBox."""
        interface.description = data.get("description", interface.description)
        interface.enabled = data.get("enabled", interface.enabled)
        interface.save()
```

### 10.3 Diff и Dry-Run

```python
# core/domain/sync.py
class DiffCalculator:
    """Вычисляет разницу между локальными и удалёнными данными."""

    def diff_interfaces(
        self,
        hostname: str,
        local_interfaces: List[Dict],
    ) -> SyncDiff:
        """
        Сравнивает локальные интерфейсы с NetBox.

        Returns:
            SyncDiff: to_create, to_update, to_delete, unchanged
        """
        # Получаем из NetBox
        remote = self._get_netbox_interfaces(hostname)
        remote_by_name = {i["name"]: i for i in remote}

        to_create = []
        to_update = []
        unchanged = []

        for local in local_interfaces:
            name = local["name"]

            if name not in remote_by_name:
                to_create.append(local)
            else:
                remote_iface = remote_by_name[name]
                if self._has_changes(local, remote_iface):
                    to_update.append({"local": local, "remote": remote_iface})
                else:
                    unchanged.append(local)

        # Интерфейсы для удаления (есть в NetBox, нет локально)
        local_names = {i["name"] for i in local_interfaces}
        to_delete = [r for r in remote if r["name"] not in local_names]

        return SyncDiff(
            to_create=to_create,
            to_update=to_update,
            to_delete=to_delete,
            unchanged=unchanged,
        )
```

---

## 11. Полный путь данных

### Пример: `python -m network_collector mac --format excel`

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. ТОЧКА ВХОДА                                                   │
├─────────────────────────────────────────────────────────────────┤
│ __main__.py → cli.main() → argparse → cmd_mac()                  │
│                                                                   │
│ args.command = "mac"                                              │
│ args.format = "excel"                                             │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. ПОДГОТОВКА                                                    │
├─────────────────────────────────────────────────────────────────┤
│ prepare_collection(args)                                          │
│   ├── load_devices("devices_ips.py") → [Device, Device, ...]     │
│   └── get_credentials() → Credentials(username, password)        │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 3. СБОР ДАННЫХ                                                   │
├─────────────────────────────────────────────────────────────────┤
│ MACCollector.collect(devices)                                     │
│                                                                   │
│ Для каждого device:                                               │
│   ├── SSH подключение (Scrapli)                                   │
│   ├── send_command("show mac address-table")                      │
│   └── response.result = "Vlan Mac Address Type Ports\n..."       │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 4. ПАРСИНГ (NTC Templates)                                       │
├─────────────────────────────────────────────────────────────────┤
│ parse_output(platform="cisco_ios", command="show mac...")         │
│                                                                   │
│ Вход (текст):                                                     │
│   "  10  aabb.ccdd.eeff  DYNAMIC  Gi0/1"                         │
│                                                                   │
│ Выход (список словарей):                                          │
│   [{"vlan": "10", "destination_address": "aabb.ccdd.eeff",       │
│     "type": "DYNAMIC", "destination_port": "Gi0/1"}]              │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 5. НОРМАЛИЗАЦИЯ                                                  │
├─────────────────────────────────────────────────────────────────┤
│ MACNormalizer.normalize_dicts(raw_data, hostname, device_ip)      │
│                                                                   │
│ Вход:                                                             │
│   {"destination_address": "aabb.ccdd.eeff", "destination_port":  │
│    "Gi0/1", "vlan": "10"}                                         │
│                                                                   │
│ Выход:                                                            │
│   {"hostname": "switch1", "device_ip": "10.0.0.1",               │
│    "mac_address": "AA:BB:CC:DD:EE:FF",                           │
│    "interface": "GigabitEthernet0/1", "vlan": 10}                 │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 6. ФИЛЬТР ПОЛЕЙ (fields.yaml)                                    │
├─────────────────────────────────────────────────────────────────┤
│ apply_fields_config(data, "mac")                                  │
│                                                                   │
│ fields.yaml:                                                      │
│   mac:                                                            │
│     hostname: {enabled: true, name: "Device", order: 1}           │
│     vlan: {enabled: false}  # Не включать VLAN                    │
│                                                                   │
│ Результат: убраны/переименованы колонки по конфигу                │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 7. ЭКСПОРТ                                                       │
├─────────────────────────────────────────────────────────────────┤
│ get_exporter("excel", "reports") → ExcelExporter                  │
│ exporter.export(data, "mac_addresses")                            │
│                                                                   │
│ Результат: reports/2026-01-12_mac_addresses.xlsx                  │
└─────────────────────────────────────────────────────────────────┘
```

### Пример: `python -m network_collector sync-netbox --interfaces`

```
┌─────────────────────────────────────────────────────────────────┐
│ 1-5. Сбор и нормализация (как выше)                              │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 6. DIFF (сравнение с NetBox)                                     │
├─────────────────────────────────────────────────────────────────┤
│ DiffCalculator.diff_interfaces(hostname, local_interfaces)        │
│                                                                   │
│ Локально: [Gi0/1, Gi0/2, Gi0/3]                                   │
│ NetBox:   [Gi0/1, Gi0/2, Gi0/4]                                   │
│                                                                   │
│ Результат:                                                        │
│   to_create: [Gi0/3]      # Есть локально, нет в NetBox          │
│   to_update: [Gi0/1]      # Изменились поля                      │
│   to_delete: [Gi0/4]      # Есть в NetBox, нет локально          │
│   unchanged: [Gi0/2]                                              │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 7. DRY-RUN или ПРИМЕНЕНИЕ                                        │
├─────────────────────────────────────────────────────────────────┤
│ --dry-run:                                                        │
│   Показать что будет изменено, ничего не менять                   │
│                                                                   │
│ Без --dry-run:                                                    │
│   NetBoxSync.sync_interfaces(hostname, interfaces)                │
│   → API вызовы: POST (create), PATCH (update), DELETE             │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 8. ОТЧЁТ                                                         │
├─────────────────────────────────────────────────────────────────┤
│ ============================================================      │
│ СВОДКА СИНХРОНИЗАЦИИ NetBox                                       │
│ ============================================================      │
│   Интерфейсы: +1 создано, ~1 обновлено, -1 удалено               │
│ ------------------------------------------------------------      │
│   ИТОГО: +1 создано, ~1 обновлено, -1 удалено                    │
│ ============================================================      │
└─────────────────────────────────────────────────────────────────┘
```

---

## Заключение

Теперь ты понимаешь:

1. **Как запускается программа** — `__main__.py` → `cli.main()` → argparse
2. **Как загружаются данные** — YAML конфиг, Python файл устройств
3. **Как работает SSH** — Scrapli, retry логика
4. **Как парсится вывод** — NTC Templates (TextFSM)
5. **Зачем нормализация** — единый формат для всех платформ
6. **Как экспортируется** — Excel/CSV/JSON через экспортеры
7. **Как синхронизируется** — diff → dry-run → API вызовы

**Следующие шаги:**
- Прочитать код коллекторов (`collectors/*.py`)
- Прочитать нормализаторы (`core/domain/*.py`)
- Запустить с `-v` для debug логов
- Добавить свою платформу/команду
