# Архитектура Network Collector

Техническая документация по архитектуре, потоку данных и внутреннему устройству.

## Содержание

1. [Обзор архитектуры](#1-обзор-архитектуры)
2. [Слои системы](#2-слои-системы)
3. [Поток данных](#3-поток-данных)
4. [Data Models](#4-data-models)
5. [Domain Layer](#5-domain-layer)
6. [Конфигурация](#6-конфигурация)
7. [Web Architecture](#7-web-architecture)
8. [Pipeline System](#8-pipeline-system)
9. [Field Registry](#9-field-registry)
10. [Ключевые файлы](#10-ключевые-файлы)
11. [Зависимости](#11-зависимости)

---

## 1. Обзор архитектуры

### 1.1 Архитектурные слои

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           PRESENTATION LAYER                                 │
│                                                                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐  │
│  │     CLI         │  │   Web API       │  │      Web UI                 │  │
│  │   cli/          │  │  api/*.py       │  │   frontend/ (Vue.js)        │  │
│  │  (модульная)    │  │  (FastAPI)      │  │                             │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                ┌───────────────────┼───────────────────┐
                │                   │                   │
                ▼                   ▼                   ▼
┌───────────────────────┐ ┌─────────────────┐ ┌─────────────────────────────┐
│   COLLECTION LAYER    │ │  EXPORT LAYER   │ │    SYNCHRONIZATION LAYER    │
│                       │ │                 │ │                             │
│  collectors/*.py      │ │ exporters/*.py  │ │  netbox/sync/*.py           │
│  Сбор данных с        │ │ Форматирование  │ │  Логика синхронизации       │
│  устройств            │ │ и сохранение    │ │  с NetBox (модули)          │
└───────────────────────┘ └─────────────────┘ └─────────────────────────────┘
         │                        │                       │
         │                        ▼                       │
         │          ┌─────────────────────────┐           │
         │          │    PIPELINE LAYER       │           │
         │          │  core/pipeline/*.py     │           │
         │          │  Оркестрация шагов      │           │
         │          └─────────────────────────┘           │
         │                        │                       │
         └────────────────────────┼───────────────────────┘
                                  ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                             DOMAIN LAYER                                    │
│                          core/domain/*.py                                   │
│        Нормализация: MACNormalizer, LLDPNormalizer, SyncComparator         │
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
│  core/connection.py    core/device.py    core/credentials.py  constants/   │
│  SSH подключения       Модель устройства  Учётные данные      Маппинги     │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                ┌───────────────────┼───────────────────┐
                │                   │                   │
                ▼                   ▼                   ▼
┌───────────────────────┐ ┌─────────────────┐ ┌─────────────────────────────┐
│    PARSING LAYER      │ │ EXTERNAL: SSH   │ │   EXTERNAL: NetBox API      │
│                       │ │                 │ │                             │
│  parsers/textfsm.py   │ │ Scrapli         │ │  netbox/client/             │
│  NTC Templates        │ │ (ssh2 transport)│ │  (pynetbox wrapper, mixins) │
│  + кастомные шаблоны  │ │                 │ │                             │
└───────────────────────┘ └─────────────────┘ └─────────────────────────────┘
```

> **Примечание:** `netbox/client.py` — обёртка для обратной совместимости.
> Реальная реализация находится в `netbox/client/` (пакет с mixin-модулями):
> `base.py`, `main.py`, `devices.py`, `interfaces.py`, `vlans.py`,
> `inventory.py`, `ip_addresses.py`, `dcim.py`.

### 1.2 Принципы

- **Separation of Concerns**: Каждый слой отвечает за свою задачу
- **Dependency Inversion**: Верхние слои не зависят от реализации нижних
- **Strategy Pattern**: Collectors, Exporters — подключаемые стратегии
- **Template Method**: BaseCollector определяет скелет, наследники переопределяют детали
- **Models Everywhere**: Коллекторы возвращают `List[Model]`, sync принимает `List[Model]`

---

## 2. Слои системы

### 2.1 Presentation Layer (cli/)

CLI организован в модульную структуру:

```
cli/
├── __init__.py           # Точка входа: main(), setup_parser()
├── utils.py              # load_devices, get_exporter, get_credentials
└── commands/             # Обработчики команд
    ├── collect.py        # cmd_devices, cmd_mac, cmd_lldp, cmd_interfaces, cmd_inventory
    ├── sync.py           # cmd_sync_netbox
    ├── backup.py         # cmd_backup, cmd_run
    ├── match.py          # cmd_match_mac
    ├── push.py           # cmd_push_descriptions
    └── validate.py       # cmd_validate_fields
```

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
- `SyncComparator` — сравнение локальных и удалённых данных (diff)
- `SyncDiff` — результат сравнения (to_create, to_update, to_delete)

### 2.4 Synchronization Layer (netbox/sync/*)

**Ответственность:**
- Синхронизация данных с NetBox API
- CRUD операции через pynetbox (batch и поштучные)
- Diff и preview изменений

**Архитектура:**

Модуль `netbox/sync/` использует mixin-классы для организации кода по доменам:

```
netbox/sync/
├── __init__.py          # re-export NetBoxSync
├── base.py              # SyncBase — общие методы
├── main.py              # NetBoxSync — объединяет mixins
├── interfaces.py        # InterfacesSyncMixin (batch API)
├── cables.py            # CablesSyncMixin
├── ip_addresses.py      # IPAddressesSyncMixin (batch API)
├── devices.py           # DevicesSyncMixin
├── vlans.py             # VLANsSyncMixin
└── inventory.py         # InventorySyncMixin (batch API)
```

**Классы:**
- `NetBoxClient` — обёртка над pynetbox (`netbox/client/`) — mixin архитектура с bulk-методами
- `NetBoxSync` — объединяет все mixins (`netbox/sync/main.py`)
- `SyncBase` — базовый класс с общими методами (`netbox/sync/base.py`)
  - `_batch_with_fallback()` — универсальный batch с автоматическим fallback на поштучные операции
  - `_vlan_cache` — кэш VLAN для производительности (batch загрузка)
  - `_vlan_id_to_vid` — обратный кэш (NetBox ID → VID) для избежания lazy-load
  - `_interface_cache` — кэш интерфейсов (device_id → {name: obj}), 1 запрос на устройство
  - `_get_vlan_by_vid()` — поиск VLAN по VID с кэшированием
  - `_load_site_vlans()` — загрузка всех VLAN сайта одним запросом
- `DiffCalculator` — предпросмотр изменений (`netbox/diff.py`)

**SyncStats** — вспомогательный класс для инициализации stats/details в sync-операциях:
- Автоматический маппинг: created->create, updated->update, deleted->delete, skipped->skip
- `.result()` возвращает dict со stats и details
- Используется во всех sync-методах для единообразной инициализации

**_safe_netbox_call()** — обёртка для обработки ошибок NetBox API:
- Централизованная обработка NetBoxError, NetBoxAPIError
- Настраиваемый уровень логирования
- Возвращает default при ошибке

**Mixins:**
- `InterfacesSyncMixin` — sync_interfaces() + batch create/update/delete + VLAN sync
  - `_build_create_data()` — подготовка данных для CREATE (включая VLAN если sync_vlans)
  - `_build_update_data()` — оркестратор, делегирует 11 хелперам `_check_*()`
  - `_check_type/description/enabled/mac/mtu/speed/duplex/mode/untagged_vlan/tagged_vlans/lag`
- `CablesSyncMixin` — sync_cables_from_lldp() + cleanup + дедупликация
- `IPAddressesSyncMixin` — sync_ip_addresses() + batch create/delete
- `DevicesSyncMixin` — create_device(), sync_devices_from_inventory() (per-device site)
- `VLANsSyncMixin` — sync_vlans_from_interfaces() (создание VLAN из SVI)
- `InventorySyncMixin` — sync_inventory() + batch create/update/delete

**Batch API (Февраль 2026):**

Sync операции для interfaces, inventory и IP используют **пакетные API-вызовы**:
- Все данные подготавливаются через `_build_create_data()` / `_build_update_data()` без API
- Один `bulk_create/update/delete()` вместо цикла поштучных вызовов
- `SyncBase._batch_with_fallback()` — единый метод для batch с автоматическим fallback
- MAC-адреса назначаются через отдельный endpoint (не в bulk)

```
Подготовка данных → _batch_with_fallback(bulk_fn, fallback_fn) → Post-process (MAC)
                         ↓ (при ошибке batch)
                    Fallback → Поштучные операции
```

**Оптимизация N+1 запросов (Февраль 2026):**

pynetbox использует lazy-loading: обращение к атрибуту вложенного объекта (Record)
вызывает `full_details()` — дополнительный API-запрос. Это приводит к N+1 паттерну:

| Проблема | Где | Решение |
|----------|-----|---------|
| `hasattr(val, "value")` на VLAN Record | SyncComparator._get_remote_field() | Прямое обращение к `.vid` (есть в brief serializer) |
| `nb_interface.device.site.name` на каждый интерфейс | _check_untagged_vlan / _check_tagged_vlans | Кэширование `site_name` в sync_interfaces() |
| Per-item `get_inventory_item()` в цикле | sync_inventory() | Pre-fetch всех items одним запросом |
| VLAN ID → VID lookup через lazy-load | _check_untagged_vlan | Обратный кэш `_vlan_id_to_vid` |

Результат: ~95 лишних запросов на устройство → 0 (для 55 интерфейсов).

**Cable Sync — отличия от других sync-операций:**

`CablesSyncMixin` работает принципиально иначе, чем interfaces/inventory/IP:

| Аспект | Interfaces/Inventory/IP | Cables |
|--------|------------------------|--------|
| API вызовы | Batch (bulk create/update/delete) | Поштучно |
| Сравнение | SyncComparator → SyncDiff | Проверка `interface.cable` |
| Источник | Коллектор (1 устройство) | LLDP (2 устройства на кабель) |

Ключевые особенности cable sync:
- **Поиск соседа** — 4 стратегии по `neighbor_type`: hostname → IP → MAC
- **Дедупликация** — `seen_cables` set (LLDP видит кабель с обеих сторон)
- **LAG-пропуск** — кабели на LAG интерфейсы не создаются
- **skip_unknown** — пропуск соседей без идентификационных данных
- **Cleanup защита** — кабель удаляется только если ОБА устройства в LLDP-скане

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
│    cli/commands/collect.py:cmd_mac() → MACCollector                         │
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
│    cli/commands/sync.py:cmd_sync_netbox() → NetBoxSync                      │
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
│    Источники media_type:                                                     │
│    • NX-OS: show interface status → "10Gbase-SR"                             │
│    • QTech: show interface transceiver → "10GBASE-SR-SFP+"                   │
│                                                                              │
│    УРОВЕНЬ 1: Коллектор → port_type (грубая категория)                       │
│    detect_port_type() нормализует в единый формат:                           │
│    • media_type "10GBASE-SR-SFP+" → "10g-sfp+"                              │
│    • hardware_type → "1g-rj45"                                               │
│    • interface_name → "lag", "virtual"                                       │
│                                                                              │
│    УРОВЕНЬ 2: Sync → NetBox type (точный тип)                                │
│    get_netbox_interface_type() — media_type приоритетнее port_type:          │
│    • media_type "10GBASE-SR-SFP+" → "10gbase-sr" (ТОЧНЫЙ!)                  │
│    • port_type "10g-sfp+" → "10gbase-x-sfpp" (generic, если нет media_type) │
│    • "lag" → "lag"                                                           │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 5. NETBOX API OPERATIONS (Batch API)                                         │
│                                                                              │
│    Для каждого устройства:                                                   │
│    ┌─────────────────────────────────────────────────────────────────────┐   │
│    │ a) client.get_device_by_name(hostname)                              │   │
│    │    → Найти устройство в NetBox (1 запрос)                           │   │
│    │                                                                     │   │
│    │ b) client.get_interfaces(device_id)                                 │   │
│    │    → Получить существующие интерфейсы (1 запрос)                    │   │
│    │                                                                     │   │
│    │ c) SyncComparator.compare_interfaces(local, remote)                 │   │
│    │    → diff: to_create[], to_update[], to_delete[], to_skip[]        │   │
│    │                                                                     │   │
│    │ d) Batch create (двухфазный для LAG):                                │   │
│    │    Фаза 1: LAG (Port-channel/AggregatePort) → bulk_create_interfaces│   │
│    │    Фаза 2: Member интерфейсы (с lag ID) → bulk_create_interfaces   │   │
│    │    VLAN: назначаются при CREATE если sync_vlans включён             │   │
│    │                                                                     │   │
│    │ e) Batch update — _build_update_data() для каждого → 1 PATCH        │   │
│    │    client.bulk_update_interfaces([{id:1,...}, {id:2,...}])          │   │
│    │                                                                     │   │
│    │ f) Batch delete → 1 DELETE                                          │   │
│    │    client.bulk_delete_interfaces([id1, id2, ...])                  │   │
│    │                                                                     │   │
│    │ g) Post-process: MAC назначение (по одному, отдельный endpoint)     │   │
│    │                                                                     │   │
│    │ h) Если dry_run: шаги d-g пропускаются, только логирование          │   │
│    │                                                                     │   │
│    │ i) Если batch упал: fallback на поштучные операции                   │   │
│    └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│    Раньше: ~100 API-запросов на устройство (48 портов)                       │
│    Сейчас: ~3 API-запроса + MAC                                              │
│                                                                              │
│    → {"created": 5, "updated": 3, "skipped": 2, "failed": 0}                │
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

### 6.3 Маппинги (core/constants/)

> **Примечание:** `core/constants/` — это пакет (не один файл). Структура:
>
> ```
> core/constants/
> ├── __init__.py       # Обратная совместимость (re-export всех констант)
> ├── commands.py       # COLLECTOR_COMMANDS, SECONDARY_COMMANDS
> ├── interfaces.py     # INTERFACE_SHORT_MAP, INTERFACE_FULL_MAP, LAG_PREFIXES, is_lag_name()
> ├── netbox.py         # NETBOX_INTERFACE_TYPE_MAP, PORT_TYPE_MAP
> ├── platforms.py      # SCRAPLI_PLATFORM_MAP, NTC_PLATFORM_MAP, DEFAULT_PLATFORM
> ├── mac.py            # MAC нормализация
> ├── devices.py        # Устройства
> └── utils.py          # Утилиты (get_collector_command, normalize_interface_*)
> ```

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
    ("qtech", "show mac address-table"): "qtech_show_mac_address_table.textfsm",
    ("qtech", "show interface"): "qtech_show_interface.textfsm",
    ("qtech", "show interface status"): "qtech_show_interface_status.textfsm",
    ("qtech", "show interface switchport"): "qtech_show_interface_switchport.textfsm",
    ("qtech", "show aggregateport summary"): "qtech_show_aggregatePort_summary.textfsm",
    # ... + аналогичные для qtech_qsw
}

# Централизованные команды коллекторов
COLLECTOR_COMMANDS = {
    "mac": {"cisco_ios": "show mac address-table", ...},
    "interfaces": {"cisco_ios": "show interfaces", "qtech": "show interface", ...},
    "lldp": {"cisco_ios": "show lldp neighbors detail", ...},
    "cdp": {"cisco_ios": "show cdp neighbors detail", ...},
    "inventory": {"cisco_ios": "show inventory", ...},
}
# Дополнительные команды в InterfaceCollector:
# lag_commands: {"qtech": "show aggregatePort summary", ...}
# switchport_commands: {"qtech": "show interface switchport", ...}

# Маппинг типов интерфейсов в NetBox
NETBOX_INTERFACE_TYPE_MAP = {
    "sfp-10gbase-lr": "10gbase-lr",
    "10gbase-sr": "10gbase-sr",
}
```

### 6.4 Функции-помощники (core/constants/)

```python
# Получить команду для коллектора и платформы
get_collector_command("mac", "cisco_ios")  # → "show mac address-table"

# Проверить, является ли интерфейс LAG (единый источник)
is_lag_name("Port-channel1")      # → True
is_lag_name("Po1")                # → True
is_lag_name("AggregatePort 1")    # → True  (QTech)
is_lag_name("Ag1")                # → True  (QTech короткий)
is_lag_name("GigabitEthernet0/1") # → False

# Получить все варианты написания интерфейса
get_interface_aliases("GigabitEthernet0/1")  # → ["GigabitEthernet0/1", "Gi0/1", "Gig0/1"]
get_interface_aliases("Hu0/55")  # → ["Hu0/55", "HundredGigE0/55", "HundredGigabitEthernet0/55"]

# Нормализация интерфейсов (Cisco и QTech)
normalize_interface_short("GigabitEthernet0/1")      # → "Gi0/1"
normalize_interface_short("TFGigabitEthernet 0/1")   # → "TF0/1"    (QTech 10G)
normalize_interface_short("AggregatePort 1")          # → "Ag1"      (QTech LAG)
normalize_interface_full("Gi0/1")                     # → "GigabitEthernet0/1"
normalize_interface_full("TF0/1")                     # → "TFGigabitEthernet0/1"
normalize_interface_full("Ag1")                       # → "AggregatePort1"

# Платформа по умолчанию (fallback)
DEFAULT_PLATFORM = "cisco_ios"
```

---

## 7. Web Architecture

### 7.1 Обзор

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              WEB ARCHITECTURE                                │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                          FRONTEND                                    │    │
│  │                     frontend/ (Vue.js 3)                            │    │
│  │                                                                      │    │
│  │  Views: Home, Devices, MAC, LLDP, Interfaces, Inventory, Backup     │    │
│  │  → HTTP запросы к API через fetch/axios                             │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                    │                                         │
│                               HTTP/JSON                                      │
│                                    │                                         │
│                                    ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                          BACKEND                                     │    │
│  │                    api/main.py (FastAPI)                            │    │
│  │                                                                      │    │
│  │  Routes:                                                             │    │
│  │    /api/auth        - Проверка credentials                          │    │
│  │    /api/devices     - Сбор show version                             │    │
│  │    /api/mac         - Сбор MAC-адресов                              │    │
│  │    /api/lldp        - Сбор LLDP/CDP                                 │    │
│  │    /api/interfaces  - Сбор интерфейсов                              │    │
│  │    /api/inventory   - Сбор модулей/SFP                              │    │
│  │    /api/backup      - Backup конфигураций                           │    │
│  │    /api/sync        - Синхронизация с NetBox                        │    │
│  │    /api/match       - Сопоставление MAC ↔ hostname                  │    │
│  │    /api/push        - Push описаний на устройства                   │    │
│  │    /api/pipelines   - Управление pipeline                          │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                    │                                         │
│                                    ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                        SERVICES                                      │    │
│  │                  api/services/*.py                                   │    │
│  │                                                                      │    │
│  │  CollectorService  → Оркестрация collectors                         │    │
│  │  SyncService       → Оркестрация NetBox sync                        │    │
│  │  MatchService      → MAC ↔ hostname matching                        │    │
│  │  PushService       → Push descriptions to devices                   │    │
│  │  HistoryService    → Журнал операций (data/history.json)           │    │
│  │  TaskManager       → Отслеживание async задач                       │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                    │                                         │
│                                    ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                      CORE LAYER                                      │    │
│  │           collectors/, netbox/, core/domain/                        │    │
│  │           (Общий код с CLI)                                         │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 7.2 Stateless Architecture

Web API **не имеет базы данных**. Все данные:
- Собираются с устройств в реальном времени (SSH)
- Синхронизируются напрямую с NetBox (REST API)
- Credentials передаются в каждом запросе

```
┌─────────┐     credentials      ┌─────────┐      SSH        ┌─────────┐
│ Browser │ ─────────────────▶ │   API   │ ──────────────▶ │ Device  │
└─────────┘                      └─────────┘                  └─────────┘
                                      │
                                      │ netbox_token
                                      ▼
                                ┌─────────┐
                                │ NetBox  │
                                └─────────┘
```

### 7.3 API Endpoints

| Endpoint | Method | Описание |
|----------|--------|----------|
| `/health` | GET | Health check |
| `/api/auth/verify` | POST | Проверка SSH credentials |
| `/api/devices/collect` | POST | Сбор show version |
| `/api/mac/collect` | POST | Сбор MAC-адресов |
| `/api/lldp/collect` | POST | Сбор LLDP/CDP |
| `/api/interfaces/collect` | POST | Сбор интерфейсов |
| `/api/inventory/collect` | POST | Сбор модулей |
| `/api/backup/collect` | POST | Backup конфигураций |
| `/api/sync/devices` | POST | Sync устройств в NetBox |
| `/api/sync/interfaces` | POST | Sync интерфейсов |
| `/api/sync/cables` | POST | Sync кабелей |
| `/api/pipelines/run` | POST | Запуск pipeline |
| `/api/fields` | GET | Получение конфигурации полей |
| `/api/fields` | POST | Обновление конфигурации полей |
| `/api/device-management` | GET | Список устройств (CRUD) |
| `/api/device-management` | POST | Создание устройства |
| `/api/tasks` | GET | Список задач (task tracking) |
| `/api/tasks/{task_id}` | GET | Статус задачи |
| `/api/match/collect` | POST | MAC matching (сопоставление MAC - hostname) |
| `/api/push/collect` | POST | Push описаний на устройства |
| `/api/history` | GET | Журнал операций |

### 7.4 Services Layer

| Сервис | Файл | Описание |
|--------|------|----------|
| `CollectorService` | `api/services/collector_service.py` | Оркестрация collectors с async mode |
| `SyncService` | `api/services/sync_service.py` | Синхронизация с NetBox, сохранение diff в историю |
| `HistoryService` | `api/services/history_service.py` | Журнал операций (JSON файл) |
| `TaskManager` | `api/services/task_manager.py` | Отслеживание async задач, progress |
| `DeviceService` | `api/services/device_service.py` | CRUD устройств (data/devices.json) |
| `common` | `api/services/common.py` | Общие утилиты (get_devices_for_operation) |

**HistoryService:**
- Хранит историю в `data/history.json`
- Максимум 1000 записей (старые автоматически удаляются)
- Записывает только реальные операции (не dry-run)
- Сохраняет полные детали: diff для sync, stats для pipeline

**TaskManager:**
- In-memory хранение задач
- Поддержка статусов: pending, running, completed, failed, cancelled
- Progress tracking: current_item, total_items, progress_percent
- Результаты доступны после завершения

### 7.5 Запуск

```bash
# Backend (FastAPI)
cd /home/sa/project
source network_collector/myenv/bin/activate
uvicorn network_collector.api.main:app --reload --host 0.0.0.0 --port 8080

# Frontend (Vue.js)
cd /home/sa/project/network_collector/frontend
npm run dev

# Документация API
http://localhost:8080/docs      # Swagger UI
http://localhost:8080/redoc     # ReDoc
```

---

## 8. Pipeline System

### 8.1 Концепция

Pipeline — набор шагов для автоматизации сбора и синхронизации.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           PIPELINE EXECUTION                                 │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                       YAML Definition                                │    │
│  │                   pipelines/default.yaml                            │    │
│  │                                                                      │    │
│  │  steps:                                                              │    │
│  │    - collect devices                                                 │    │
│  │    - sync devices                                                    │    │
│  │    - collect interfaces                                              │    │
│  │    - sync interfaces                                                 │    │
│  │    - collect lldp                                                    │    │
│  │    - sync cables                                                     │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                    │                                         │
│                                    ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                      PipelineExecutor                                │    │
│  │                  core/pipeline/executor.py                          │    │
│  │                                                                      │    │
│  │  1. Validate pipeline                                                │    │
│  │  2. Check dependencies                                               │    │
│  │  3. Execute steps sequentially                                       │    │
│  │  4. Pass data between steps via context                              │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                    │                                         │
│                ┌───────────────────┼───────────────────┐                     │
│                ▼                   ▼                   ▼                     │
│         ┌───────────┐       ┌───────────┐       ┌───────────┐               │
│         │  COLLECT  │       │   SYNC    │       │  EXPORT   │               │
│         │  Сбор     │       │  NetBox   │       │  Excel/   │               │
│         │  данных   │       │  sync     │       │  CSV/JSON │               │
│         └───────────┘       └───────────┘       └───────────┘               │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 8.2 Модели (core/pipeline/models.py)

| Класс | Описание |
|-------|----------|
| `Pipeline` | Набор шагов с именем и описанием |
| `PipelineStep` | Один шаг (id, type, target, options) |
| `StepType` | Enum: `collect`, `sync`, `export` |
| `StepStatus` | Enum: `pending`, `running`, `completed`, `failed`, `skipped` |

### 8.3 Типы шагов

| Тип | Target | Описание |
|-----|--------|----------|
| `collect` | `devices`, `interfaces`, `mac`, `lldp`, `cdp`, `inventory`, `backup` | Сбор данных с устройств |
| `sync` | `devices`, `interfaces`, `cables`, `inventory`, `vlans` | Синхронизация с NetBox |
| `export` | любой target | Экспорт в файл |

### 8.4 Зависимости

Sync шаги имеют зависимости:

```
devices ──────────────────┐
                          │
interfaces ◀──────────────┤ (требует devices)
                          │
cables ◀──────────────────┤ (требует interfaces)
                          │
inventory ◀───────────────┤ (требует devices)
                          │
vlans ◀───────────────────┘ (требует devices)
```

### 8.5 Формат YAML

```yaml
id: default
name: "Full Sync"
description: "Полная синхронизация с NetBox"
enabled: true

steps:
  - id: collect_devices
    type: collect
    target: devices
    enabled: true
    options: {}

  - id: sync_devices
    type: sync
    target: devices
    depends_on:
      - collect_devices
    options:
      create: true
      update: true
      site: "Default"

  - id: collect_interfaces
    type: collect
    target: interfaces
    depends_on:
      - sync_devices

  - id: sync_interfaces
    type: sync
    target: interfaces
    depends_on:
      - collect_interfaces
    options:
      sync_mac: true
      sync_mode: true

  - id: export_interfaces
    type: export
    target: interfaces
    options:
      format: excel
      output_dir: output
```

### 8.6 Использование

```python
from network_collector.core.pipeline.models import Pipeline
from network_collector.core.pipeline.executor import PipelineExecutor

# Загрузка из YAML
pipeline = Pipeline.from_yaml("pipelines/default.yaml")

# Валидация
errors = pipeline.validate()
if errors:
    print(f"Errors: {errors}")

# Выполнение
executor = PipelineExecutor(pipeline, dry_run=True)
result = executor.run(
    devices=devices,
    credentials={"username": "admin", "password": "pass"},
    netbox_config={"url": "http://netbox", "token": "xxx"},
)

print(f"Status: {result.status}")
for step in result.steps:
    print(f"  {step.step_id}: {step.status}")
```

---

## 9. Field Registry

### 9.1 Обзор

Field Registry — централизованный реестр всех полей с их алиасами, display names и маппингом на NetBox.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            FIELD FLOW                                        │
│                                                                              │
│  ┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐     │
│  │   NTC Templates  │ ──▶ │   Normalizer     │ ──▶ │     Model        │     │
│  │   (raw aliases)  │     │ (domain layer)   │     │  (dataclass)     │     │
│  │                  │     │                  │     │                  │     │
│  │ NEIGHBOR_NAME    │     │ remote_hostname  │     │ remote_hostname  │     │
│  │ LOCAL_INTERFACE  │     │ local_interface  │     │ local_interface  │     │
│  │ MGMT_ADDRESS     │     │ remote_ip        │     │ remote_ip        │     │
│  └──────────────────┘     └──────────────────┘     └──────────────────┘     │
│                                                              │               │
│                                    ┌─────────────────────────┤               │
│                                    ▼                         ▼               │
│                           ┌──────────────────┐     ┌──────────────────┐     │
│                           │  fields.yaml     │     │   sync.fields    │     │
│                           │  (export config) │     │  (NetBox sync)   │     │
│                           │                  │     │                  │     │
│                           │  remote_hostname │     │  source: mac     │     │
│                           │    → "Neighbor"  │     │  → mac_address   │     │
│                           └──────────────────┘     └──────────────────┘     │
│                                    │                         │               │
│                                    ▼                         ▼               │
│                           ┌──────────────────┐     ┌──────────────────┐     │
│                           │    Excel/CSV     │     │     NetBox       │     │
│                           │  (display names) │     │   (API fields)   │     │
│                           └──────────────────┘     └──────────────────┘     │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 9.2 Уровни трансформации

| Уровень | Где | Что делает |
|---------|-----|-----------|
| **1. Raw (NTC)** | `ntc_templates.parse()` | Поля из NTC Templates (SCREAMING_CASE) |
| **2. Normalizer** | `core/domain/*.py` | Унификация в snake_case, добавление metadata |
| **3. Model** | `core/models.py` | Типизированные dataclasses, алиасы в from_dict() |
| **4. Export Config** | `fields.yaml` (секции lldp, mac, etc) | Display names, order, enabled/disabled |
| **5. Sync Config** | `fields.yaml` (секция sync) | Маппинг на NetBox API поля |

### 9.3 Field Registry (core/field_registry.py)

```python
from core.field_registry import (
    get_canonical_name,
    get_all_aliases,
    get_netbox_field,
    validate_fields_config,
)

# Найти каноническое имя для любого алиаса
get_canonical_name("lldp", "NEIGHBOR_NAME")  # → "remote_hostname"
get_canonical_name("mac", "destination_port")  # → "interface"

# Получить все алиасы
get_all_aliases("lldp", "remote_hostname")
# → {"remote_hostname", "NEIGHBOR_NAME", "neighbor_name", ...}

# Получить имя поля в NetBox API
get_netbox_field("interfaces", "native_vlan")  # → "untagged_vlan"

# Валидировать fields.yaml
errors = validate_fields_config()
if errors:
    for e in errors:
        print(f"Error: {e}")
```

### 9.4 Структура FieldDefinition

```python
@dataclass
class FieldDefinition:
    canonical: str           # Имя в модели (remote_hostname)
    aliases: List[str]       # Алиасы из NTC/парсеров (NEIGHBOR_NAME, neighbor_name)
    display: str            # Display name для Excel (Neighbor)
    netbox_field: str       # Поле в NetBox API (если отличается)
    description: str        # Описание
```

### 9.5 Пример записи в реестре

```python
FIELD_REGISTRY = {
    "lldp": {
        "remote_hostname": FieldDefinition(
            canonical="remote_hostname",
            aliases=[
                "NEIGHBOR_NAME", "NEIGHBOR", "neighbor", "neighbor_name",
                "SYSTEM_NAME", "system_name", "DEVICE_ID", "device_id",
            ],
            display="Neighbor",
            description="Имя соседа (hostname)",
        ),
        ...
    },
    "interfaces": {
        "native_vlan": FieldDefinition(
            canonical="native_vlan",
            aliases=["NATIVE_VLAN"],
            display="Native VLAN",
            netbox_field="untagged_vlan",  # ← NetBox использует другое имя!
            description="Native VLAN (для trunk портов)",
        ),
        ...
    },
}
```

### 9.6 Валидация fields.yaml

CLI команда для проверки конфигурации:

```bash
# Валидация
python -m network_collector validate-fields

# Подробный вывод
python -m network_collector validate-fields -v

# Показать реестр полей
python -m network_collector validate-fields --show-registry

# Только определённый тип
python -m network_collector validate-fields --show-registry --type lldp
```

Пример вывода:
```
Validating fields.yaml against models...

✓ All fields are valid!

Field Registry Statistics:
  lldp: 12 fields (8 with aliases)
  mac: 9 fields (5 with aliases)
  interfaces: 19 fields (16 with aliases)
  devices: 14 fields (14 with aliases)
  inventory: 8 fields (6 with aliases)
```

### 9.7 Типы полей

| Тип | Где определяется | Пример |
|-----|-----------------|--------|
| **Parsed** | Model + Field Registry | `hostname`, `mac`, `status` — парсятся с устройств |
| **Enriched** | Model + Field Registry | `native_vlan`, `port_type` — добавляются normalizer'ом |
| **Export-only** | EXPORT_ONLY_FIELDS | `status` в MAC — вычисляется, не хранится |
| **Sync-only** | SYNC_ONLY_FIELDS | `asset_tag`, `comments` — NetBox-only, не парсятся |

### 9.8 Чек-лист при добавлении полей

**Если поле ПАРСИТСЯ с устройства:**

1. **Модель** (`core/models.py`)
   - Добавить поле в dataclass
   - Добавить обработку алиасов в `from_dict()`

2. **Field Registry** (`core/field_registry.py`)
   - Добавить `FieldDefinition` с canonical, aliases, display, netbox_field

3. **fields.yaml** (если нужен экспорт/sync)
   - Секция экспорта: display name, order, enabled
   - Секция sync: source → netbox_field mapping

4. **Валидация**
   ```bash
   python -m network_collector validate-fields
   ```

5. **Тесты**
   ```bash
   pytest tests/test_contracts/
   ```

**Если поле НЕ парсится (NetBox-only):**

1. **SYNC_ONLY_FIELDS** (`core/field_registry.py`)
   ```python
   SYNC_ONLY_FIELDS = {
       "devices": {"asset_tag", "comments"},  # ← добавить сюда
   }
   ```

2. **fields.yaml** — sync секция
   ```yaml
   sync:
     devices:
       fields:
         asset_tag:
           enabled: true
           source: asset_tag  # Будет пустым если не заполнено
   ```

**Принцип**: Модели содержат только то, что реально собирается с устройств.

---

## 10. Ключевые файлы

### 10.1 Основные модули

| Файл | Описание |
|------|----------|
| `cli/` | CLI модуль (модульная структура) |
| `cli/__init__.py` | Точка входа CLI: `main()`, `setup_parser()` |
| `cli/commands/` | Обработчики команд (collect, sync, backup, etc.) |
| `core/connection.py` | SSH подключения через Scrapli |
| `core/device.py` | Модель Device |
| `core/models.py` | Data Models (Interface, MACEntry, ...) |
| `core/constants/` | Модульные константы (interfaces, mac, platforms, netbox, etc.) |
| `core/context.py` | RunContext (run_id, dry_run, timing) |
| `core/exceptions.py` | Типизированные исключения |
| `core/logging.py` | Structured Logs (JSON + ротация) |

### 10.2 Коллекторы

| Файл | Описание |
|------|----------|
| `collectors/base.py` | BaseCollector, collect_models() |
| `collectors/device.py` | DeviceCollector, DeviceInventoryCollector |
| `collectors/mac.py` | MACCollector |
| `collectors/lldp.py` | LLDPCollector |
| `collectors/interfaces.py` | InterfaceCollector |
| `collectors/inventory.py` | InventoryCollector |
| `collectors/config_backup.py` | ConfigBackupCollector |

### 10.3 Domain Layer

| Файл | Описание |
|------|----------|
| `core/domain/interface.py` | InterfaceNormalizer |
| `core/domain/mac.py` | MACNormalizer |
| `core/domain/lldp.py` | LLDPNormalizer |
| `core/domain/inventory.py` | InventoryNormalizer |
| `core/domain/sync.py` | SyncComparator, SyncDiff, get_cable_endpoints |
| `core/domain/vlan.py` | parse_vlan_range(), VlanSet — парсинг и сравнение VLAN |
| `core/field_registry.py` | Field Registry — реестр полей, алиасов, валидация |

### 10.4 NetBox

**Client (netbox/client/) — обёртка над pynetbox:**

| Файл | Описание |
|------|----------|
| `netbox/client/__init__.py` | Re-export NetBoxClient |
| `netbox/client/base.py` | NetBoxClientBase — инициализация |
| `netbox/client/main.py` | NetBoxClient — объединяет mixins |
| `netbox/client/devices.py` | DevicesMixin (get_devices, get_device_by_*) |
| `netbox/client/interfaces.py` | InterfacesMixin — get/create/update + **bulk_create/update/delete_interfaces** |
| `netbox/client/vlans.py` | VLANsMixin (get_vlans, create_vlan) |
| `netbox/client/inventory.py` | InventoryMixin — CRUD + **bulk_create/update/delete_inventory_items** |
| `netbox/client/ip_addresses.py` | IPAddressesMixin — get/cables + **bulk_create/delete_ip_addresses** |
| `netbox/client/dcim.py` | DCIMMixin (device types, manufacturers, etc.) |

**Sync (netbox/sync/) — логика синхронизации:**

| Файл | Описание |
|------|----------|
| `netbox/sync/__init__.py` | Re-export NetBoxSync |
| `netbox/sync/base.py` | SyncBase — общие методы синхронизации |
| `netbox/sync/main.py` | NetBoxSync — объединяет все mixins |
| `netbox/sync/interfaces.py` | InterfacesSyncMixin — **batch API**: _build_create/update_data, _batch_create/update/delete |
| `netbox/sync/cables.py` | CablesSyncMixin (sync_cables_from_lldp) |
| `netbox/sync/ip_addresses.py` | IPAddressesSyncMixin — **batch API**: _batch_create/delete_ip_addresses |
| `netbox/sync/devices.py` | DevicesSyncMixin (sync_devices_from_inventory) |
| `netbox/sync/vlans.py` | VLANsSyncMixin (sync_vlans_from_interfaces) |
| `netbox/sync/inventory.py` | InventorySyncMixin — **batch API**: batch create/update/delete inventory |
| `netbox/diff.py` | DiffCalculator (preview changes) |

### 10.5 Web API

| Файл | Описание |
|------|----------|
| `api/main.py` | FastAPI приложение, роутинг |
| `api/routes/*.py` | Эндпоинты (devices, mac, lldp, sync, pipelines, history) |
| `api/routes/history.py` | История операций (/api/history) |
| `api/routes/pipelines.py` | Pipeline management (/api/pipelines) |
| `api/routes/tasks.py` | Task tracking (/api/tasks) |
| `api/schemas/*.py` | Pydantic схемы запросов/ответов |
| `api/services/*.py` | Сервисы |
| `api/services/common.py` | Общие утилиты (get_devices_for_operation) |
| `api/services/history_service.py` | HistoryService — журнал операций |
| `api/services/sync_service.py` | SyncService — синхронизация с NetBox |
| `api/services/task_manager.py` | TaskManager — async tasks |

### 10.6 Pipeline

| Файл | Описание |
|------|----------|
| `core/pipeline/models.py` | Pipeline, PipelineStep, StepType |
| `core/pipeline/executor.py` | PipelineExecutor |
| `pipelines/default.yaml` | Default pipeline (Full Sync) |

### 10.7 Конфигурация

| Файл | Описание |
|------|----------|
| `config.py` | Загрузчик config.yaml |
| `fields_config.py` | Загрузчик fields.yaml |
| `core/config_schema.py` | Pydantic схемы для валидации |

### 10.8 Структура проекта

```
network_collector/
├── __init__.py
├── __main__.py              # python -m network_collector
├── cli/                     # CLI модуль (модульная структура)
│   ├── __init__.py          # main(), setup_parser()
│   ├── utils.py             # load_devices, get_exporter, get_credentials
│   └── commands/            # Обработчики команд
│       ├── collect.py       # cmd_devices, cmd_mac, cmd_lldp, cmd_interfaces, cmd_inventory
│       ├── sync.py          # cmd_sync_netbox, _print_sync_summary
│       ├── backup.py        # cmd_backup, cmd_run
│       ├── match.py         # cmd_match_mac
│       ├── push.py          # cmd_push_descriptions
│       └── validate.py      # cmd_validate_fields
│
├── config.py                # Загрузка config.yaml
├── config.yaml              # Настройки
├── fields_config.py         # Загрузка fields.yaml
├── fields.yaml              # Поля экспорта/синхронизации
├── devices_ips.py           # Список устройств
│
├── api/                     # Web API (FastAPI)
│   ├── main.py              # Точка входа API
│   ├── routes/              # Эндпоинты
│   │   ├── devices.py
│   │   ├── mac.py
│   │   ├── lldp.py
│   │   ├── interfaces.py
│   │   ├── inventory.py
│   │   ├── backup.py
│   │   ├── sync.py
│   │   ├── match.py
│   │   ├── push.py
│   │   └── pipelines.py
│   ├── schemas/             # Pydantic схемы
│   │   ├── common.py
│   │   ├── credentials.py
│   │   └── pipeline.py
│   └── services/            # Бизнес-логика
│       ├── collector_service.py
│       ├── sync_service.py
│       ├── match_service.py
│       └── push_service.py
│
├── frontend/                # Web UI (Vue.js 3)
│   ├── package.json
│   ├── vite.config.js
│   ├── index.html
│   └── src/
│       └── views/           # Страницы
│           ├── Home.vue
│           ├── Devices.vue
│           ├── Mac.vue
│           ├── Lldp.vue
│           ├── Interfaces.vue
│           ├── Inventory.vue
│           └── Backup.vue
│
├── core/                    # Ядро
│   ├── connection.py        # SSH через Scrapli
│   ├── credentials.py       # Учётные данные
│   ├── device.py            # Модель Device
│   ├── models.py            # Data Models
│   ├── constants/           # Маппинги (пакет, см. раздел 6.3)
│   ├── context.py           # RunContext
│   ├── exceptions.py        # Исключения
│   ├── logging.py           # Логирование
│   ├── field_registry.py    # Field Registry — реестр полей
│   ├── domain/              # Domain Layer
│   │   ├── interface.py
│   │   ├── mac.py
│   │   ├── lldp.py
│   │   ├── inventory.py
│   │   ├── sync.py
│   │   └── vlan.py          # VlanSet, parse_vlan_range
│   └── pipeline/            # Pipeline система
│       ├── models.py        # Pipeline, PipelineStep
│       └── executor.py      # PipelineExecutor
│
├── pipelines/               # Pipeline definitions
│   └── default.yaml         # Full Sync pipeline
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
│   ├── client.py            # Обратная совместимость (re-export)
│   ├── client/              # NetBoxClient — mixin-архитектура
│   │   ├── __init__.py      # Re-export NetBoxClient
│   │   ├── base.py          # NetBoxClientBase — инициализация
│   │   ├── main.py          # NetBoxClient — объединяет mixins
│   │   ├── devices.py       # DevicesMixin
│   │   ├── interfaces.py    # InterfacesMixin (+ bulk)
│   │   ├── vlans.py         # VLANsMixin
│   │   ├── inventory.py     # InventoryMixin (+ bulk)
│   │   ├── ip_addresses.py  # IPAddressesMixin (+ bulk)
│   │   └── dcim.py          # DCIMMixin
│   ├── diff.py              # DiffCalculator
│   └── sync/                # Модули синхронизации
│       ├── __init__.py      # Re-export NetBoxSync
│       ├── base.py          # SyncBase — общие методы
│       ├── main.py          # NetBoxSync — mixins composition
│       ├── interfaces.py    # InterfacesSyncMixin
│       ├── cables.py        # CablesSyncMixin
│       ├── ip_addresses.py  # IPAddressesSyncMixin
│       ├── devices.py       # DevicesSyncMixin
│       ├── vlans.py         # VLANsSyncMixin
│       └── inventory.py     # InventorySyncMixin
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
    ├── test_core/
    └── test_api/
```

---

## 11. Зависимости

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
| `fastapi` | Web API framework |
| `uvicorn` | ASGI сервер |
| `vue` | Frontend framework (Vue.js 3) |
| `vite` | Frontend build tool |
