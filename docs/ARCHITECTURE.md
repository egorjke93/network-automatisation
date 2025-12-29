# Архитектура Network Collector

Техническая документация по архитектуре, потоку данных и внутреннему устройству.

## Содержание

1. [Обзор архитектуры](#1-обзор-архитектуры)
2. [Слои системы](#2-слои-системы)
3. [Поток данных](#3-поток-данных)
4. [Data Models](#4-data-models)
5. [Domain Layer](#5-domain-layer)
6. [Конфигурация](#6-конфигурация)
7. [Ключевые файлы](#7-ключевые-файлы)

---

## 1. Обзор архитектуры

### 1.1 Архитектурные слои

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           PRESENTATION LAYER                                 │
│                              cli.py                                          │
│         Парсинг аргументов, координация, вывод результатов                  │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                ┌───────────────────┼───────────────────┐
                │                   │                   │
                ▼                   ▼                   ▼
┌───────────────────────┐ ┌─────────────────┐ ┌─────────────────────────────┐
│   COLLECTION LAYER    │ │  EXPORT LAYER   │ │    SYNCHRONIZATION LAYER    │
│                       │ │                 │ │                             │
│  collectors/*.py      │ │ exporters/*.py  │ │  netbox/sync.py             │
│  Сбор данных с        │ │ Форматирование  │ │  Логика синхронизации       │
│  устройств            │ │ и сохранение    │ │  с NetBox                   │
└───────────────────────┘ └─────────────────┘ └─────────────────────────────┘
         │                                               │
         ▼                                               ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                             DOMAIN LAYER                                    │
│                          core/domain/*.py                                   │
│        Нормализация данных: MACNormalizer, InterfaceNormalizer, etc.       │
└───────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CONFIGURATION LAYER                                │
│                                                                              │
│  config.py          fields_config.py        fields.yaml      config.yaml    │
│  Загрузка           Поля экспорта и         Какие поля       Настройки      │
│  config.yaml        синхронизации           включать         приложения     │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CORE LAYER                                      │
│                                                                              │
│  core/connection.py    core/device.py    core/credentials.py   constants.py │
│  SSH подключения       Модель устройства  Учётные данные      Маппинги      │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                ┌───────────────────┼───────────────────┐
                │                   │                   │
                ▼                   ▼                   ▼
┌───────────────────────┐ ┌─────────────────┐ ┌─────────────────────────────┐
│    PARSING LAYER      │ │ EXTERNAL: SSH   │ │   EXTERNAL: NetBox API      │
│                       │ │                 │ │                             │
│  parsers/textfsm.py   │ │ Scrapli         │ │  netbox/client.py           │
│  NTC Templates        │ │ (ssh2 transport)│ │  (pynetbox wrapper)         │
│  + кастомные шаблоны  │ │                 │ │                             │
└───────────────────────┘ └─────────────────┘ └─────────────────────────────┘
```

### 1.2 Принципы

- **Separation of Concerns**: Каждый слой отвечает за свою задачу
- **Dependency Inversion**: Верхние слои не зависят от реализации нижних
- **Strategy Pattern**: Collectors, Exporters — подключаемые стратегии
- **Template Method**: BaseCollector определяет скелет, наследники переопределяют детали
- **Models Everywhere**: Коллекторы возвращают `List[Model]`, sync принимает `List[Model]`

---

## 2. Слои системы

### 2.1 Presentation Layer (cli.py)

**Ответственность:**
- Парсинг аргументов командной строки
- Координация между collectors, exporters, sync
- Вывод результатов пользователю

**Не делает:**
- Прямые SSH подключения
- Парсинг вывода команд
- Работу с NetBox API

### 2.2 Collection Layer (collectors/*.py)

**Ответственность:**
- Сбор данных с устройств через SSH
- Парсинг вывода команд (NTC Templates)
- Возврат типизированных моделей

**Классы:**
- `BaseCollector` — абстрактный базовый класс
- `DeviceCollector` → `DeviceInfo`
- `MACCollector` → `MACEntry`
- `LLDPCollector` → `LLDPNeighbor`
- `InterfaceCollector` → `Interface`
- `InventoryCollector` → `InventoryItem`
- `ConfigBackupCollector` → файлы конфигов

### 2.3 Domain Layer (core/domain/*.py)

**Ответственность:**
- Нормализация данных с разных платформ
- Бизнес-логика преобразования
- Фильтрация и дедупликация

**Классы:**
- `MACNormalizer` — MAC форматы, фильтрация trunk
- `InterfaceNormalizer` — имена интерфейсов, port_type, mode
- `LLDPNormalizer` — neighbor_type, hostname
- `InventoryNormalizer` — PID, serial

### 2.4 Synchronization Layer (netbox/*.py)

**Ответственность:**
- Синхронизация данных с NetBox API
- CRUD операции через pynetbox
- Diff и preview изменений

**Классы:**
- `NetBoxClient` — обёртка над pynetbox
- `NetBoxSync` — логика синхронизации
- `DiffCalculator` — предпросмотр изменений

### 2.5 Export Layer (exporters/*.py)

**Ответственность:**
- Форматирование данных для экспорта
- Сохранение в файлы (Excel, CSV, JSON)

**Классы:**
- `BaseExporter` — абстрактный базовый класс
- `ExcelExporter` → .xlsx
- `CSVExporter` → .csv
- `JSONExporter` → .json

---

## 3. Поток данных

### 3.1 Сбор MAC-адресов

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. CLI PARSING                                                               │
│    python -m network_collector mac --format excel                            │
│    cli.py:cmd_mac() → MACCollector                                          │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 2. DEVICE LOADING                                                            │
│    load_devices() → devices_ips.py                                           │
│    → List[Device]                                                            │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 3. DATA COLLECTION (параллельно через ThreadPool)                            │
│                                                                              │
│    Для каждого устройства:                                                   │
│    ┌─────────────────────────────────────────────────────────────────────┐   │
│    │ a) ConnectionManager.connect(device)                                │   │
│    │    → Scrapli SSH подключение                                        │   │
│    │                                                                     │   │
│    │ b) conn.send_command("show mac address-table")                      │   │
│    │    → Raw output                                                     │   │
│    │                                                                     │   │
│    │ c) textfsm_parser.parse(output, platform, command)                  │   │
│    │    → List[Dict] (NTC Templates)                                     │   │
│    │                                                                     │   │
│    │ d) MACNormalizer.normalize(raw_data)                                │   │
│    │    → List[MACEntry]                                                 │   │
│    └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│    → List[MACEntry]                                                          │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 4. FIELDS TRANSFORMATION                                                     │
│    fields_config.apply_fields_config(data, "mac")                            │
│                                                                              │
│    - Фильтрация по enabled: true                                             │
│    - Переименование полей (hostname → "Device")                              │
│    - Сортировка по order                                                     │
│    → List[Dict]                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 5. EXPORT                                                                    │
│    ExcelExporter.export(data, filename)                                      │
│    → reports/mac_2025-01-01.xlsx                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Синхронизация с NetBox

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. CLI PARSING                                                               │
│    python -m network_collector sync-netbox --interfaces --dry-run            │
│    cli.py:cmd_sync_netbox() → NetBoxSync                                    │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 2. DATA COLLECTION                                                           │
│    InterfaceCollector.collect(devices)                                       │
│    → List[Interface]                                                         │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 3. SYNC CONFIGURATION                                                        │
│    fields_config.get_sync_config("interfaces")                               │
│                                                                              │
│    - fields (какие поля синхронизировать)                                    │
│    - defaults (значения по умолчанию)                                        │
│    - options (exclude_interfaces, auto_detect_type)                          │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 4. INTERFACE TYPE DETECTION (двухуровневая)                                  │
│                                                                              │
│    УРОВЕНЬ 1: Коллектор → port_type                                          │
│    _detect_port_type() нормализует в единый формат:                          │
│    • media_type → "10g-sfp+"                                                 │
│    • hardware_type → "1g-rj45"                                               │
│    • interface_name → "lag", "virtual"                                       │
│                                                                              │
│    УРОВЕНЬ 2: Sync → NetBox type                                             │
│    _get_interface_type() конвертирует в NetBox формат:                       │
│    • "10g-sfp+" → "10gbase-x-sfpp"                                          │
│    • "1g-rj45" → "1000base-t"                                               │
│    • "lag" → "lag"                                                           │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 5. NETBOX API OPERATIONS                                                     │
│                                                                              │
│    Для каждого интерфейса:                                                   │
│    ┌─────────────────────────────────────────────────────────────────────┐   │
│    │ a) client.get_device_by_name(hostname)                              │   │
│    │    → Найти устройство в NetBox                                      │   │
│    │                                                                     │   │
│    │ b) client.get_interfaces(device_id)                                 │   │
│    │    → Получить существующие интерфейсы                               │   │
│    │                                                                     │   │
│    │ c) Сравнение:                                                       │   │
│    │    - Нет в NetBox? → CREATE                                         │   │
│    │    - Есть изменения? → UPDATE                                       │   │
│    │    - Нет изменений? → SKIP                                          │   │
│    │                                                                     │   │
│    │ d) Если dry_run: только логирование                                 │   │
│    └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│    → {"created": 5, "updated": 3, "skipped": 2, "failed": 0}                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.3 Порядок --sync-all

```
┌───────────────────────────────────────────────────────────────────┐
│ 1. sync_devices_from_inventory()                                   │
│    Создание устройств (должны существовать до всего остального)   │
└───────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────────────┐
│ 2. sync_interfaces()                                               │
│    Создание интерфейсов (нужны для IP и кабелей)                  │
└───────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────────────┐
│ 3. sync_ip_addresses()                                             │
│    Привязка IP к интерфейсам + установка primary IP               │
└───────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────────────┐
│ 4. sync_vlans_from_interfaces()                                    │
│    Создание VLAN из SVI интерфейсов (Vlan10 → VLAN 10)            │
└───────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────────────┐
│ 5. sync_cables_from_lldp()                                         │
│    Построение топологии (нужны устройства и интерфейсы)           │
└───────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────────────┐
│ 6. sync_inventory()                                                │
│    Модули, SFP, PSU                                                │
└───────────────────────────────────────────────────────────────────┘
```

---

## 4. Data Models

### 4.1 Модели (core/models.py)

| Модель | Коллектор | Описание |
|--------|-----------|----------|
| `DeviceInfo` | `DeviceCollector` | Информация об устройстве |
| `Interface` | `InterfaceCollector` | Интерфейс с IP, MAC, mode |
| `MACEntry` | `MACCollector` | Запись MAC-таблицы |
| `LLDPNeighbor` | `LLDPCollector` | LLDP/CDP сосед |
| `InventoryItem` | `InventoryCollector` | Модуль, SFP, PSU |
| `IPAddressEntry` | — | IP-адрес на интерфейсе |

### 4.2 Использование

```python
from network_collector.core import Interface, MACEntry

# Создание из dict (от парсера)
intf = Interface.from_dict(parsed_data)

# Доступ к полям с автокомплитом
print(intf.name, intf.status, intf.ip_address)

# Конвертация обратно в dict (для экспорта)
data = intf.to_dict()

# Автоконвертация списков
interfaces = Interface.ensure_list(data)  # Dict или Model → List[Model]
```

### 4.3 API коллекторов

```python
collector = MACCollector(credentials)

# Типизированные модели (для sync, нового кода)
entries = collector.collect(devices)       # → List[MACEntry]

# Словари (для экспорта, pandas)
data = collector.collect_dicts(devices)    # → List[Dict]
```

---

## 5. Domain Layer

### 5.1 Нормализаторы (core/domain/)

| Normalizer | Что делает |
|------------|------------|
| `MACNormalizer` | MAC формат (ieee/cisco/raw), фильтрация trunk, дедупликация |
| `InterfaceNormalizer` | Имена интерфейсов, port_type, mode |
| `LLDPNormalizer` | neighbor_type (hostname/mac/ip), remote_hostname |
| `InventoryNormalizer` | PID, serial, manufacturer |

### 5.2 Использование

```python
from network_collector.core.domain import MACNormalizer

normalizer = MACNormalizer(
    mac_format="ieee",
    exclude_vlans=[1, 4094],
    exclude_interfaces=["^Po.*", "^Vlan.*"],
)

# Нормализация сырых данных
normalized = normalizer.normalize_dicts(raw_data)

# Дедупликация
deduplicated = normalizer.deduplicate(normalized)
```

### 5.3 Преимущества

- Легко тестировать изолированно
- Переиспользуется между коллекторами
- Бизнес-логика отделена от сбора данных

---

## 6. Конфигурация

### 6.1 Файлы конфигурации

```
network_collector/
├── config.yaml        # Настройки приложения
├── fields.yaml        # Поля экспорта и синхронизации
└── devices_ips.py     # Список устройств
```

### 6.2 Приоритет конфигурации

```
1. Аргументы CLI          (--site "DC1")
2. Переменные окружения   (NETBOX_URL)
3. config.yaml            (netbox.url)
4. Дефолты в коде         (config.py)
```

### 6.3 Маппинги (core/constants.py)

```python
# SSH драйвер — какой Scrapli driver использовать
SCRAPLI_PLATFORM_MAP = {
    "qtech": "cisco_iosxe",
    "eltex": "cisco_iosxe",
}

# NTC парсер — какой шаблон NTC Templates использовать
NTC_PLATFORM_MAP = {
    "qtech": "cisco_ios",
    "eltex": "cisco_ios",
}

# Кастомные TextFSM шаблоны (приоритет над NTC)
CUSTOM_TEXTFSM_TEMPLATES = {
    ("qtech", "show mac address-table"): "qtech_show_mac.textfsm",
}

# Маппинг типов интерфейсов в NetBox
NETBOX_INTERFACE_TYPE_MAP = {
    "sfp-10gbase-lr": "10gbase-lr",
    "10gbase-sr": "10gbase-sr",
}
```

---

## 7. Ключевые файлы

### 7.1 Основные модули

| Файл | Описание |
|------|----------|
| `cli.py` | Точка входа CLI, все команды |
| `core/connection.py` | SSH подключения через Scrapli |
| `core/device.py` | Модель Device |
| `core/models.py` | Data Models (Interface, MACEntry, ...) |
| `core/constants.py` | Маппинги платформ, типов интерфейсов |
| `core/context.py` | RunContext (run_id, dry_run, timing) |
| `core/exceptions.py` | Типизированные исключения |
| `core/logging.py` | Structured Logs (JSON + ротация) |

### 7.2 Коллекторы

| Файл | Описание |
|------|----------|
| `collectors/base.py` | BaseCollector, collect_models() |
| `collectors/device.py` | DeviceCollector, DeviceInventoryCollector |
| `collectors/mac.py` | MACCollector |
| `collectors/lldp.py` | LLDPCollector |
| `collectors/interfaces.py` | InterfaceCollector |
| `collectors/inventory.py` | InventoryCollector |
| `collectors/config_backup.py` | ConfigBackupCollector |

### 7.3 Domain Layer

| Файл | Описание |
|------|----------|
| `core/domain/interface.py` | InterfaceNormalizer |
| `core/domain/mac.py` | MACNormalizer |
| `core/domain/lldp.py` | LLDPNormalizer |
| `core/domain/inventory.py` | InventoryNormalizer |

### 7.4 NetBox

| Файл | Описание |
|------|----------|
| `netbox/client.py` | NetBoxClient (pynetbox wrapper) |
| `netbox/sync.py` | NetBoxSync (логика синхронизации) |
| `netbox/diff.py` | DiffCalculator (preview changes) |

### 7.5 Конфигурация

| Файл | Описание |
|------|----------|
| `config.py` | Загрузчик config.yaml |
| `fields_config.py` | Загрузчик fields.yaml |
| `core/config_schema.py` | Pydantic схемы для валидации |

### 7.6 Структура проекта

```
network_collector/
├── __init__.py
├── __main__.py              # python -m network_collector
├── cli.py                   # CLI интерфейс
│
├── config.py                # Загрузка config.yaml
├── config.yaml              # Настройки
├── fields_config.py         # Загрузка fields.yaml
├── fields.yaml              # Поля экспорта/синхронизации
├── devices_ips.py           # Список устройств
│
├── core/                    # Ядро
│   ├── connection.py        # SSH через Scrapli
│   ├── credentials.py       # Учётные данные
│   ├── device.py            # Модель Device
│   ├── models.py            # Data Models
│   ├── constants.py         # Маппинги
│   ├── context.py           # RunContext
│   ├── exceptions.py        # Исключения
│   ├── logging.py           # Логирование
│   └── domain/              # Domain Layer
│       ├── interface.py
│       ├── mac.py
│       ├── lldp.py
│       └── inventory.py
│
├── collectors/              # Сборщики данных
│   ├── base.py
│   ├── device.py
│   ├── mac.py
│   ├── lldp.py
│   ├── interfaces.py
│   ├── inventory.py
│   └── config_backup.py
│
├── parsers/                 # Парсеры
│   └── textfsm_parser.py
│
├── templates/               # Кастомные TextFSM шаблоны
│   └── *.textfsm
│
├── exporters/               # Экспорт
│   ├── base.py
│   ├── excel.py
│   ├── csv_exporter.py
│   └── json_exporter.py
│
├── netbox/                  # NetBox интеграция
│   ├── client.py
│   ├── sync.py
│   └── diff.py
│
├── configurator/            # Конфигурация устройств
│   ├── base.py
│   └── description.py
│
├── docs/                    # Документация
│   ├── MANUAL.md
│   ├── ARCHITECTURE.md
│   └── DEVELOPMENT.md
│
└── tests/                   # Тесты
    ├── conftest.py
    ├── fixtures/
    ├── test_collectors/
    ├── test_netbox/
    ├── test_parsers/
    └── test_core/
```

---

## Зависимости

| Библиотека | Назначение |
|------------|------------|
| `scrapli[ssh2]` | SSH подключения |
| `ntc-templates` | Парсинг вывода команд |
| `textfsm` | TextFSM парсинг |
| `pynetbox` | NetBox API клиент |
| `pandas` | Работа с данными, Excel |
| `openpyxl` | Excel файлы |
| `pyyaml` | YAML конфигурация |
| `pydantic` | Валидация конфигов |
| `keyring` | Безопасное хранение секретов |
