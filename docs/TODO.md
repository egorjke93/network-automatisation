# Network Collector - План развития

> Последнее обновление: Февраль 2026

## Текущее состояние

### CLI Команды (11 штук)

| Команда | Описание | Статус |
|---------|----------|--------|
| `devices` | Инвентаризация устройств | OK |
| `mac` | Сбор MAC-адресов | OK |
| `lldp` | Сбор LLDP/CDP соседей | OK |
| `interfaces` | Сбор интерфейсов | OK |
| `inventory` | Сбор модулей/SFP | OK |
| `backup` | Резервное копирование | OK |
| `run` | Произвольная команда | OK |
| `match-mac` | Сопоставление MAC с хостами | OK |
| `push-descriptions` | Применение описаний | OK |
| `sync-netbox` | Синхронизация с NetBox | OK |
| `pipeline` | Управление pipelines | ✅ OK |

### Web API (FastAPI)

| Endpoint | Методы | Статус |
|----------|--------|--------|
| `/api/auth/*` | POST credentials | OK |
| `/api/devices` | POST collect | OK |
| `/api/mac` | POST collect | OK |
| `/api/lldp` | POST collect | OK |
| `/api/interfaces` | POST collect | OK |
| `/api/inventory` | POST collect | OK |
| `/api/backup` | POST run | OK |
| `/api/sync` | POST sync | OK |
| `/api/match` | POST match | OK |
| `/api/push` | POST push | OK |
| `/api/pipelines` | GET, POST, PUT, DELETE, RUN | **NEW** |
| `/api/tasks` | GET, DELETE | **NEW** |

### Web UI (Vue.js)

| Страница | Функционал | Статус |
|----------|------------|--------|
| Home | Главная | OK |
| Credentials | Настройка credentials | OK |
| Devices | Сбор устройств | OK |
| MAC Table | Сбор MAC | OK |
| LLDP/CDP | Сбор соседей | OK |
| Interfaces | Сбор интерфейсов | OK |
| Inventory | Сбор модулей | OK |
| Backup | Резервное копирование | OK |
| Sync NetBox | Синхронизация | OK |
| Pipelines | CRUD + Run | **NEW** |

### Pipeline System (✅ COMPLETE)

| Компонент | Файл | Статус |
|-----------|------|--------|
| Models | `core/pipeline/models.py` | ✅ OK |
| Executor | `core/pipeline/executor.py` | ✅ OK |
| API Schemas | `api/schemas/pipeline.py` | ✅ OK |
| API Routes | `api/routes/pipelines.py` | ✅ OK |
| Vue UI | `frontend/src/views/Pipelines.vue` | ✅ OK |
| CLI command | `cli/commands/pipeline.py` | ✅ OK |
| Tests | `tests/test_core/test_pipeline/` + `tests/test_cli/test_pipeline.py` | 102 теста |

---

## Что нужно доработать

### 1. CLI Pipeline команда ✅ ВЫПОЛНЕНО

**Решение:** Добавлен `cli/commands/pipeline.py` с полным функционалом:

```bash
# Список pipelines
python -m network_collector pipeline list

# Показать детали pipeline
python -m network_collector pipeline show default

# Запустить pipeline
python -m network_collector pipeline run default --dry-run
python -m network_collector pipeline run default --apply  # Применить изменения

# Валидировать pipeline
python -m network_collector pipeline validate default

# Создать из YAML
python -m network_collector pipeline create my_pipeline.yaml

# Удалить
python -m network_collector pipeline delete my_pipeline --force
```

**Тесты:** 27 тестов в `tests/test_cli/test_pipeline.py`

---

### 2. API Сервисы-заглушки ✅ ВЫПОЛНЕНО

**Проблема:** В API были сервисы-заглушки, которые не были реализованы.

**Решение:** Реализованы полные версии сервисов:

| Файл | Описание | Статус |
|------|----------|--------|
| `api/services/match_service.py` | Сопоставление MAC с хостами | ✅ Реализовано |
| `api/services/push_service.py` | Применение описаний на устройства | ✅ Реализовано |

Оба сервиса используют логику из CLI команд через `DescriptionMatcher` и `DescriptionPusher`.

---

### 3. Рефакторинг больших файлов (Средний приоритет)

**Проблема:** Некоторые файлы слишком большие, сложно поддерживать:

| Файл | Строк | Статус |
|------|-------|--------|
| `netbox/sync.py` | 1973 | ✅ Разбит на модули |
| `cli.py` | 1641 | ✅ Разбит на модули |
| `netbox/client.py` | 1154 | ✅ Разбит на модули |
| `core/constants.py` | 1210 | ✅ Разбит на модули |

#### 3.1 ✅ `netbox/sync.py` → `netbox/sync/` (ВЫПОЛНЕНО)

Разбит на модули с mixin-классами:

```
netbox/sync/
├── __init__.py          # re-export NetBoxSync
├── base.py              # SyncBase — общие методы (_find_device, _get_or_create, etc.)
├── main.py              # NetBoxSync — объединяет все mixins
├── interfaces.py        # InterfacesSyncMixin (sync_interfaces)
├── cables.py            # CablesSyncMixin (sync_cables_from_lldp)
├── ip_addresses.py      # IPAddressesSyncMixin (sync_ip_addresses)
├── devices.py           # DevicesSyncMixin (sync_devices_from_inventory)
├── vlans.py             # VLANsSyncMixin (sync_vlans_from_interfaces)
└── inventory.py         # InventorySyncMixin (sync_inventory)
```

**Архитектура:**
```python
class NetBoxSync(
    InterfacesSyncMixin,
    CablesSyncMixin,
    IPAddressesSyncMixin,
    DevicesSyncMixin,
    VLANsSyncMixin,
    InventorySyncMixin,
    SyncBase,
):
    """Объединяет все sync-операции через mixins."""
```

#### 3.2 ✅ Разбить `cli.py` (ВЫПОЛНЕНО)

Разбит на модули:

```
cli/
├── __init__.py          # main(), setup_parser(), re-exports
├── utils.py             # load_devices, get_exporter, get_credentials
└── commands/
    ├── __init__.py      # re-exports
    ├── collect.py       # cmd_devices, cmd_mac, cmd_lldp, cmd_interfaces, cmd_inventory
    ├── sync.py          # cmd_sync_netbox, _print_sync_summary
    ├── backup.py        # cmd_backup, cmd_run
    ├── match.py         # cmd_match_mac
    ├── push.py          # cmd_push_descriptions
    └── validate.py      # cmd_validate_fields
```

**Архитектура:** Каждая команда в своём файле, общие утилиты вынесены в `utils.py`.
Точка входа `main()` и `setup_parser()` в `cli/__init__.py`.

**Обратная совместимость:** Все функции re-экспортируются через `cli/__init__.py`,
поэтому `from network_collector.cli import cmd_mac` продолжает работать.

#### 3.3 ✅ `netbox/client.py` → `netbox/client/` (ВЫПОЛНЕНО)

Разбит на модули с mixin-классами:

```
netbox/client/
├── __init__.py          # re-export NetBoxClient
├── base.py              # NetBoxClientBase — инициализация, _resolve_*
├── main.py              # NetBoxClient — объединяет все mixins
├── devices.py           # DevicesMixin (get_devices, get_device_by_*)
├── interfaces.py        # InterfacesMixin (get/create/update_interface)
├── ip_addresses.py      # IPAddressesMixin (get_ip_addresses, get_cables)
├── vlans.py             # VLANsMixin (get_vlans, create_vlan)
├── inventory.py         # InventoryMixin (get/create/update/delete_inventory_item)
└── dcim.py              # DCIMMixin (device_types, manufacturers, roles, sites, platforms, MAC)
```

**Архитектура:**
```python
class NetBoxClient(
    DevicesMixin,
    InterfacesMixin,
    IPAddressesMixin,
    VLANsMixin,
    InventoryMixin,
    DCIMMixin,
    NetBoxClientBase,
):
    """Объединяет все NetBox операции через mixins."""
```

**Обратная совместимость:** `from network_collector.netbox.client import NetBoxClient` работает.

#### 3.4 ✅ `core/constants.py` → `core/constants/` (ВЫПОЛНЕНО)

Разбит на модули по функционалу:

```
core/constants/
├── __init__.py          # re-export всё (обратная совместимость)
├── interfaces.py        # нормализация интерфейсов (160 строк)
├── platforms.py         # маппинг платформ (115 строк)
├── mac.py               # MAC нормализация (95 строк)
├── netbox.py            # типы интерфейсов NetBox (310 строк)
├── devices.py           # нормализация моделей (65 строк)
├── commands.py          # команды коллекторов (100 строк)
└── utils.py             # slug, маски, дефолты (140 строк)
```

**Обратная совместимость:** `from network_collector.core.constants import normalize_mac_ieee` работает.

#### 3.5 ✅ `_get_devices()` дублирование (ВЫПОЛНЕНО)

Извлечена общая утилита `api/services/common.py`:

```python
def get_devices_for_operation(device_list: List[str] = None) -> List[Device]:
    """Получает устройства с обогащением из device_service."""
```

**Использовалась в:**
- `api/services/collector_service.py`
- `api/services/sync_service.py`
- `api/services/push_service.py`

**Результат:** Удалено ~100 строк дублирующегося кода.

---

### 4. CI/CD с GitHub Actions (Средний приоритет)

**Проблема:** Нет автоматического запуска тестов при push/PR.

**Решение:** Создать `.github/workflows/tests.yml`:

```yaml
name: Tests

on:
  push:
    branches: [master, main]
  pull_request:
    branches: [master, main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Run tests
        run: pytest tests/ -v --tb=short
```

**Дополнительно:**
- [ ] Линтинг (ruff, black)
- [ ] Type checking (mypy)
- [ ] Coverage report
- [ ] Build Docker image

**Оценка:** 2-3 часа

---

### 5. Документация ✅ ВЫПОЛНЕНО

#### 5.1 MANUAL.md

- [x] Добавлен раздел "Pipeline" (раздел 5)
- [x] Добавлен раздел "Web интерфейс" (раздел 6)
- [x] Добавлен раздел "REST API" (раздел 7)
- [x] Обновлено оглавление

#### 5.2 WEB_API.md ✅

Создана полная документация REST API:
- Все endpoints с примерами
- Request/Response schemas
- Async Mode документация
- History API
- Примеры curl

#### 5.3 Дополнительная документация

- [x] **ARCHITECTURE.md** — архитектура, mixin-классы, pipeline
- [x] **DEVELOPMENT.md** — разработка, тесты, добавление платформ
- [x] **TESTING.md** — тестирование, fixtures, маркеры
- [x] **SYNC_PIPELINE_INTERNALS.md** — для начинающих
- [x] **CLI_INTERNALS.md** — для начинающих

---

### 6. CRUD улучшения ✅ ВЫПОЛНЕНО

#### 6.1 sync-netbox improvements

| Операция | Статус | Флаг |
|----------|--------|------|
| DELETE interfaces | ✅ OK | `--cleanup-interfaces` |
| DELETE IP addresses | ✅ OK | `--cleanup-ips` |
| DELETE cables | ✅ OK | `--cleanup-cables` |
| DELETE inventory | ✅ OK | `--cleanup-inventory` |
| UPDATE IP addresses | ✅ OK | `--update-ips` |
| UPDATE inventory manufacturer | ✅ OK | Автоматически по PID |
| UPDATE cables | — | Низкий приоритет |
| DELETE VLAN | — | Низкий приоритет |

#### 6.2 Inventory Manufacturer Logic

Manufacturer для inventory items определяется автоматически:
- Определяется **только по PID** (Product ID), не по платформе устройства
- Если PID не распознан — manufacturer остаётся **пустым**
- При sync пустой manufacturer **очищает** поле в NetBox (убирает неверный Cisco)

Паттерны PID → Manufacturer:
- `WS-`, `C9`, `N9K`, `SFP-`, `GLC-` → Cisco
- `DCS-`, `ARISTA` → Arista
- `EX`, `QFX`, `MX` → Juniper
- `FINISAR`, `FTLX` → Finisar

#### 6.3 Interface Enabled Mode

Конфигурируемая логика определения `enabled` для интерфейсов в `fields.yaml`:

```yaml
sync:
  interfaces:
    options:
      enabled_mode: "admin"  # или "link"
```

| Режим | status=up | status=down | status=disabled |
|-------|-----------|-------------|-----------------|
| `admin` | enabled=true | enabled=true | enabled=false |
| `link` | enabled=true | enabled=false | enabled=false |

- `admin` — по административному статусу (up/down = включён, порт активен)
- `link` — по состоянию линка (только up = есть соединение)

#### 6.4 Архитектура (Domain Layer)

Реализована чистая архитектура:
- `core/domain/sync.py` — бизнес-логика сравнения (SyncComparator)
- `netbox/sync/*.py` — инфраструктура (API операции, mixin-модули)

```python
# Domain Layer — чистые функции
comparator = SyncComparator()
diff = comparator.compare_interfaces(local, remote, cleanup=True)
# diff.to_create, diff.to_update, diff.to_delete

# Infrastructure Layer — API
sync.sync_interfaces(device, interfaces, cleanup=True)
```

**Документация:** см. [docs/MANUAL.md](MANUAL.md) раздел 4

---

### 7. Web UI улучшения

#### 7.1 ✅ Progress Bar с Async Mode (ВЫПОЛНЕНО)

Добавлен визуальный прогресс-бар с real-time отслеживанием прогресса:

| Компонент | Файл | Статус |
|-----------|------|--------|
| TaskManager | `api/services/task_manager.py` | ✅ OK |
| Tasks API | `api/routes/tasks.py` | ✅ OK |
| ProgressBar Vue | `frontend/src/components/ProgressBar.vue` | ✅ OK |
| Progress Callbacks | `collectors/base.py` | ✅ OK |
| Async Mode | `api/services/collector_service.py` | ✅ OK |
| Интеграция | Все views (Devices, MAC, LLDP, Interfaces, Inventory, Backup, Sync) | ✅ OK |

**Функционал:**
- **Async Mode:** `async_mode: true` — запрос возвращается сразу с `task_id`, сбор в фоне
- Real-time progress: показывает текущее устройство ("Обработка 10.0.0.5 (3/10)")
- Polling API `/api/tasks/{id}` каждые 500ms
- Результаты в `task.result.data` после завершения
- Визуализация статусов: pending, running, completed, failed
- Автоматическое скрытие после завершения

**Sync vs Async Mode:**

| Режим | Поведение | Когда использовать |
|-------|-----------|-------------------|
| `async_mode: false` | Запрос блокируется, результат сразу | API клиенты, скрипты |
| `async_mode: true` | task_id сразу, polling для прогресса | Web UI, много устройств |

**API Request (async):**
```json
{
  "devices": [],
  "async_mode": true
}
```

**Progress Response:**
```json
{
  "id": "abc12345",
  "type": "collect_devices",
  "status": "running",
  "progress_percent": 30,
  "current_item": 3,
  "total_items": 10,
  "message": "Обработка 10.0.0.3 (3/10)",
  "elapsed_ms": 5432
}
```

**Completed Response:**
```json
{
  "id": "abc12345",
  "status": "completed",
  "result": {
    "total": 10,
    "data": [{"hostname": "switch-01", ...}, ...]
  },
  "message": "Завершено: 10 записей"
}
```

**Документация:** см. [WEB_API.md](WEB_API.md) — раздел "Async Mode"

#### 7.2 Pipelines UI

- [ ] Drag-and-drop редактор шагов
- [ ] Визуализация зависимостей (граф)
- [ ] Real-time лог выполнения (WebSocket)
- [ ] История запусков
- [ ] Шаблоны pipelines

#### 7.3 General UI

- [ ] Темная тема
- [x] Экспорт данных из UI (JSON добавлен в DataTable)
- [ ] Графики и дашборды
- [x] Пагинация больших таблиц (в DataTable)

**Оценка:** Низкий приоритет (кроме Progress Bar - выполнено)

---

### 8. Синхронизация VLAN на интерфейсы ✅ ВЫПОЛНЕНО

| Компонент | Статус |
|-----------|--------|
| Сбор mode (access/trunk) | ✅ Есть |
| Сбор native_vlan | ✅ Есть |
| Сбор access_vlan | ✅ Есть |
| Сбор tagged_vlans | ✅ Добавлено |
| Sync mode в NetBox | ✅ Работает |
| **Sync untagged_vlan** | ✅ Реализовано |
| **Sync tagged_vlans** | ✅ Реализовано |

**Реализовано:**
- Опция `sync_vlans: false` в fields.yaml (по умолчанию выключена)
- Кэш VLAN в SyncBase (`_vlan_cache`, `_get_vlan_by_vid()`)
- Парсинг диапазонов VLAN: "10,20,30-50" → [10,20,30..50] (`_parse_vlan_range()`)
- Sync untagged_vlan: access_vlan для access, native_vlan для trunk
- Sync tagged_vlans: список VLAN для tagged портов
- VLAN ищется только в сайте устройства
- Если VLAN не найден → пропуск (debug лог)
- Access port очищает tagged_vlans
- tagged-all не синхронизирует список (все VLAN разрешены)
- 19 тестов в `tests/test_netbox/test_sync_interfaces_vlan.py`

**Использование:**
```yaml
# fields.yaml
sync:
  interfaces:
    options:
      sync_vlans: true  # Включить sync VLAN на интерфейсы
```

**Файлы изменены:**
- `fields.yaml` — опция sync_vlans
- `netbox/sync/base.py` — кэш VLAN, `_get_vlan_by_vid()`, `_parse_vlan_range()`
- `netbox/sync/interfaces.py` — sync untagged_vlan и tagged_vlans
- `collectors/interfaces.py` — сохранение tagged_vlans в switchport данных
- `core/domain/interface.py` — enrich с tagged_vlans
- `tests/test_netbox/test_sync_interfaces_vlan.py` — 19 тестов

---

### 9. Тестирование (Низкий приоритет) ✅

| Тип | Текущее | Нужно |
|-----|---------|-------|
| Unit tests | 1350+ | ✅ OK |
| Integration tests | 290+ (API, pipeline, bulk, cables, IP) | ✅ OK |
| E2E tests | 186 | ✅ OK |
| Coverage | ~85% | ✅ OK |

**Задачи:**
- [x] API integration tests (FastAPI TestClient) — ✅ 148 тестов
- [x] E2E tests для collectors — ✅ 189 тестов (IP, sync, multi-device, NX-OS enrichment)
- [x] Mock-based tests для NetBox sync — ✅ 286 тестов (bulk, VLAN, LAG batch, diff)
- [x] Unit-тесты cables sync — ✅ 21 тест (dedup, LAG skip, neighbor lookup, cleanup)
- [x] Unit-тесты ip_addresses sync — ✅ 17 тестов (batch create/fallback, mask recreate, primary IP)

**Статус:** ✅ Выполнено. Всего 1906 тестов

---

## Приоритеты

### 🔴 Высокий приоритет

| # | Задача | Оценка | Описание |
|---|--------|--------|----------|
| 1 | ~~CLI Pipeline команда~~ | ~~2-3ч~~ | ✅ Выполнено (list, show, run, validate, create, delete) |
| 2 | ~~API сервисы-заглушки~~ | ~~4-6ч~~ | ✅ Выполнено (match_service, push_service) |

### 🟡 Средний приоритет

| # | Задача | Оценка | Описание |
|---|--------|--------|----------|
| 3 | ~~Рефакторинг sync.py~~ | ~~4-5ч~~ | ✅ Разбит на модули (netbox/sync/*) |
| 4 | ~~Рефакторинг cli.py~~ | ~~4-5ч~~ | ✅ Разбит на модули (cli/*) |
| 5 | GitHub Actions CI | 2-3ч | Автотесты при push/PR |
| 6 | ~~Документация~~ | ~~4-5ч~~ | ✅ MANUAL, WEB_API, ARCHITECTURE |
| 7 | ~~VLAN sync на интерфейсы~~ | ~~6-8ч~~ | ✅ untagged_vlan + tagged_vlans |

### 🟢 Низкий приоритет

| # | Задача | Оценка | Описание |
|---|--------|--------|----------|
| 8 | Web UI улучшения | 10+ч | Темы, графики, drag-drop |
| 9 | Расширение тестов | 8-10ч | API tests, E2E, coverage |

---

## Что уже хорошо ✅

- ✅ 1906 тестов (хорошее покрытие)
- ✅ Структурированное JSON логирование
- ✅ Domain Layer с нормализаторами
- ✅ Pipeline система с транзакциями
- ✅ Pydantic модели для валидации
- ✅ Подробная документация (официальная + обучающая)
- ✅ Batch API для sync (3-5x ускорение)
- ✅ Batch MAC assignment (48→1 API запрос на устройство)
- ✅ N+1 оптимизация кэширования (95→3 API запроса на устройство)
- ✅ Exponential backoff + jitter в retry (anti-thundering herd)
- ✅ Type hints в 370+ функциях

---

## Архитектура Pipeline

```
                    ┌─────────────────┐
                    │   Pipeline YAML │
                    │   (pipelines/)  │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │ Pipeline Models │
                    │ (core/pipeline) │
                    └────────┬────────┘
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
    ┌────▼────┐        ┌─────▼─────┐       ┌─────▼─────┐
    │   CLI   │        │  Web API  │       │  Web UI   │
    │ (cli/)  │        │ (FastAPI) │       │  (Vue.js) │
    └────┬────┘        └─────┬─────┘       └─────┬─────┘
         │                   │                   │
         └───────────────────┼───────────────────┘
                             │
                    ┌────────▼────────┐
                    │PipelineExecutor │
                    └────────┬────────┘
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
    ┌────▼────┐        ┌─────▼─────┐       ┌─────▼─────┐
    │Collectors│       │NetBox Sync│       │ Exporters │
    └─────────┘        └───────────┘       └───────────┘
```

### Step Types

| Type | Target | Описание |
|------|--------|----------|
| `collect` | devices, interfaces, mac, lldp, cdp, inventory, backup | Сбор данных |
| `sync` | devices, interfaces, cables, inventory, vlans | Синхронизация с NetBox |
| `export` | любой | Экспорт в Excel/CSV/JSON |

### Зависимости шагов

```
collect_devices → sync_devices → collect_interfaces → sync_interfaces → ...
```

Шаг с `depends_on` не выполнится пока зависимости не завершатся успешно.

---

## Оптимизация производительности (Февраль 2026) ✅ ВЫПОЛНЕНО

### Batch API для синхронизации ✅ ВЫПОЛНЕНО

**Проблема:** Pipeline на 22 устройства выполнялся ~30 минут. Sync фаза выполнялась последовательно —
по одному API-вызову на каждый интерфейс/inventory/IP.

**Решение:** Переход на batch API (pynetbox bulk create/update/delete):

| Компонент | Файл | Изменение |
|-----------|------|-----------|
| Client bulk interfaces | `netbox/client/interfaces.py` | +3 метода: `bulk_create/update/delete_interfaces` |
| Client bulk inventory | `netbox/client/inventory.py` | +3 метода: `bulk_create/update/delete_inventory_items` |
| Client bulk IP | `netbox/client/ip_addresses.py` | +3 метода: `bulk_create/update/delete_ip_addresses` |
| Batch sync interfaces | `netbox/sync/interfaces.py` | Рефакторинг на batch create/update/delete |
| Batch sync inventory | `netbox/sync/inventory.py` | Рефакторинг на batch create/update/delete |
| Batch sync IP | `netbox/sync/ip_addresses.py` | Рефакторинг на batch create/update/delete |
| Параллелизм collect | `config.yaml` | `max_workers: 5` → `10` |
| Тесты | `tests/test_netbox/test_bulk_operations.py` | 32 теста |

**Архитектура batch sync:**
```python
# Было: по одному API-вызову на каждый интерфейс
for item in diff.to_create:
    self._create_interface(device.id, intf)  # 1 API call

# Стало: один bulk-вызов на все интерфейсы
create_batch = [self._build_create_data(device.id, intf) for intf in ...]
self.client.bulk_create_interfaces(create_batch)  # 1 API call
```

**Безопасность:**
- Fallback: если bulk-вызов падает → автоматический переход на поштучные операции
- dry-run: batch пропускает API-вызовы, логирует как раньше
- Обратная совместимость: старые методы (`create_interface`, `update_interface`) остаются

**Ожидаемое ускорение:** 3-5x для sync фазы (22 устройства × ~48 портов):
- До: 22 × ~100 API calls × ~100ms = ~3.5 мин (только interfaces)
- После: 22 × ~3 API calls (bulk) + MAC = ~1 мин

### N+1 Query Optimization ✅ ВЫПОЛНЕНО

**Проблема:** Кэш `_find_interface` был по `(device_id, name)` — каждый вызов делал отдельный API запрос.
При 22 устройствах × ~48 интерфейсов = ~1056 запросов только для поиска интерфейсов.

**Решение:** Кэш по `device_id` — загружаем ВСЕ интерфейсы устройства одним запросом:

```python
# Было: ~95 API запросов на устройство
def _find_interface(self, device_id, name):
    return self.client.get_interfaces(device_id=device_id, name=name)  # 1 запрос на интерфейс

# Стало: ~3 API запроса на устройство
def _find_interface(self, device_id, name):
    if device_id not in self._interface_cache:
        interfaces = self.client.get_interfaces(device_id=device_id)  # 1 запрос на ВСЕ
        self._interface_cache[device_id] = {intf.name: intf for intf in interfaces}
    return self._interface_cache[device_id].get(name)
```

**Результат:**
- 95 → 3 API запроса на устройство
- Pipeline 22 устройства: 32 мин → 13 мин

**Файлы:** `netbox/sync/base.py` (кэш), `netbox/sync/interfaces.py`, `netbox/sync/ip_addresses.py`

### Batch MAC Assignment ✅ ВЫПОЛНЕНО

**Проблема:** `assign_mac_to_interface()` вызывался в цикле — 1 API запрос на каждый MAC.
При 22 устройствах × 48 портов = ~1056 запросов.

**Решение:** Новый метод `bulk_assign_macs()` в `netbox/client/dcim.py` — один bulk-вызов
с fallback на поштучные при ошибке.

**Файлы:** `netbox/client/dcim.py`, `netbox/sync/interfaces.py`

**Ускорение:** ~48 запросов → 1 на устройство. Pipeline MAC-фаза: ~105с → ~2с.

### Exponential Backoff + Jitter в Retry ✅ ВЫПОЛНЕНО

**Проблема:** Фиксированная задержка retry при параллельном сборе → thundering herd.

**Решение:** `_get_retry_delay()` в `ConnectionManager` — экспоненциальный backoff
(`delay * 2^attempt`, cap 60с) + random jitter (+0..50%).

**Файлы:** `core/connection.py`

---

## QTech полная поддержка (Февраль 2026) ✅ ВЫПОЛНЕНО

### Что сделано

- Config.get() — исправлен TypeError в cmd_run
- AggregatePort (QTech LAG) — распознаётся как LAG в detect_port_type, get_netbox_interface_type
- TFGigabitEthernet (QTech 25G SFP28) — распознаётся как 25g-sfp28 / 25gbase-x-sfp28
- Маппинги интерфейсов: TF ↔ TFGigabitEthernet, Ag ↔ AggregatePort
- TextFSM шаблон qtech_show_aggregatePort_summary.textfsm для LAG парсинга
- LAG парсинг: _parse_lag_membership_qtech() с алиасами всех имён
- Switchport: универсальная `InterfaceNormalizer.normalize_switchport_data()` для Cisco и QTech форматов
- TextFSM fix: VLAN regex (\d+) → (\S+) для поддержки "routed"
- Команда `show interface` (без 's') для QTech
- normalize_interface_full() — исправлен баг с ложным срабатыванием на полных именах + добавлен `.replace(" ", "")` для QTech пробелов
- get_interface_aliases() — добавлен HundredGigabitEthernet алиас
- TextFSM шаблон qtech_show_interface: LINK_STATUS расширен для `administratively down`
- _post_sync_mac_check() — пост-обработка MAC для пропущенных интерфейсов (баг: MAC не назначался если все поля совпали)
- 75+ новых тестов (1880 всего): QTech support, templates, refactoring utils

### ✅ QTech transceiver (media_type) — ВЫПОЛНЕНО

Реализован Вариант A (минимальный код): QTech добавлен в `SECONDARY_COMMANDS["media_type"]`
с командой `show interface transceiver`. Метод `_parse_media_types()` расширен для поддержки
полей TextFSM (`INTERFACE`/`TYPE`).

- [x] Добавить `show interface transceiver` в media_type_commands для qtech/qtech_qsw
- [x] `_parse_media_types()` поддерживает оба формата: NTC (port/type) и TextFSM (INTERFACE/TYPE)
- [x] Двухуровневый маппинг: media_type → port_type (грубый) + media_type → NETBOX_INTERFACE_TYPE_MAP (точный)
- [x] Результат: `10GBASE-SR-SFP+` → NetBox тип `10gbase-sr` (вместо generic `10gbase-x-sfpp`)
- [x] TextFSM шаблон уже был: `qtech_show_interface_transceiver.textfsm`
- [x] Новый парсер не нужен — используется существующий `_parse_media_types()` с fallback на поля TextFSM

---

## Bug Fixes (Февраль 2026)

### LAG Member Interfaces Not Assigned in Batch Create ✅

**Проблема:** При запуске pipeline LAG интерфейсы (Port-channel) создавались, но member-интерфейсы
не привязывались к LAG. При повторном запуске sync отдельно — LAG назначался.

**Причина:** `_batch_create_interfaces` создавал ВСЕ интерфейсы одним batch-запросом.
Когда `_build_create_data()` для Gi0/1 вызывал `get_interface_by_name("Port-channel1")`,
Port-channel1 ещё не существовал в NetBox (был в том же batch).

**Решение:** Двухфазное создание:
1. Фаза 1: создаём LAG интерфейсы (Port-channel/Po)
2. Фаза 2: создаём member-интерфейсы (теперь `get_interface_by_name` находит LAG)

**Файл:** `netbox/sync/interfaces.py`

**Тесты:** 8 тестов в `tests/test_netbox/test_lag_batch_create.py`

### Pipeline Auto-Collect Silent Failure Fix ✅

**Проблема:** Если auto-collect упал при sync шаге, pipeline возвращал `{"failed": True}`
как data, но `_execute_step` оборачивал это в `StepStatus.COMPLETED`. Шаг считался успешным.

**Решение:** Вместо `return {"failed": True}` бросаем `RuntimeError`, которую ловит
`_execute_step` и корректно ставит `StepStatus.FAILED`.

**Файл:** `core/pipeline/executor.py`

### Pipeline YAML Load Silent Error Fix ✅

**Проблема:** `_load_pipelines()` в API при битом YAML файле делал `except: pass`.
Pipeline пропадал молча без логирования.

**Решение:** `except Exception as e: logger.warning(f"Ошибка загрузки pipeline {file}: {e}")`

**Файл:** `api/routes/pipelines.py`

### Cable Cleanup Stats Fix ✅

**Проблема:** При cleanup кабелей, если `get_cables()` падал для устройства — устройство
тихо пропускалось. Stats показывали "deleted=5" хотя часть устройств была пропущена.

**Решение:** `_cleanup_cables` теперь считает `failed_devices` и пробрасывает в stats.
Логирует warning о пропущенных устройствах.

**Файл:** `netbox/sync/cables.py`

### Primary IP Silent Failure Fix ✅

**Проблема:** `_set_primary_ip()` мог вернуть `False` (IP не найден/ошибка), но
caller в `_update_device()` игнорировал return value и возвращал `True`.

**Решение:** Проверяется return value `_set_primary_ip()`, при неудаче — `logger.warning`.

**Файл:** `netbox/sync/devices.py`

### Pipeline Cleanup Options Fix ✅

**Проблема:** Pipeline не передавал `cleanup` опцию в sync методы.

**Причина:** `executor.py` не извлекал `cleanup` из `options` при вызове sync.

**Решение:**
- `sync_interfaces`: теперь передаёт `cleanup=options.get("cleanup", False)`
- `sync_cables_from_lldp`: теперь передаёт `cleanup=options.get("cleanup", False)`
- `sync_inventory`: теперь передаёт `cleanup=options.get("cleanup", False)`
- `sync_ip_addresses`: теперь передаёт `cleanup=options.get("cleanup", False)`
- `sync_devices`: **НЕ передаёт cleanup** (требует tenant для безопасности, как в CLI)

**YAML пример:**
```yaml
steps:
  - id: sync_interfaces
    type: sync
    target: interfaces
    options:
      cleanup: true  # Теперь работает!
```

**Файл:** `core/pipeline/executor.py`

**Тесты:** 7 тестов в `tests/test_core/test_pipeline/test_executor_cleanup.py`

### Mode Clearing for Shutdown Ports Fix ✅

**Проблема:** Shutdown порты сохраняли старый mode (Tagged all) в NetBox.

**Причина:** Когда порт без switchport настроек (только shutdown), mode приходил пустым.
Код пропускал пустой mode вместо очистки значения в NetBox.

**Решение:**
```python
# Было: if intf.mode and intf.mode != current_mode:
# Стало:
if intf.mode and intf.mode != current_mode:
    updates["mode"] = intf.mode  # Устанавливаем новый
elif not intf.mode and current_mode:
    updates["mode"] = ""  # Очищаем если порт без mode
```

**Файл:** `netbox/sync/interfaces.py`

**Тесты:** 3 теста в `TestModeClearOnShutdown`

### Per-Device Site from devices_ips.py ✅

**Фича:** Каждое устройство в `devices_ips.py` может иметь свой `site`.

**Приоритет site:** CLI `--site` > `device.site` из devices_ips.py > `fields.yaml` defaults.site > `"Main"`

**Файлы:**
- `core/device.py` — поле `site: Optional[str] = None` в Device
- `cli/utils.py` — `load_devices()` читает `site=d.get("site")`
- `collectors/device.py` — `result["site"] = device.site`
- `netbox/sync/devices.py` — `device_site = entry.site or site` (per-device fallback)
- `cli/commands/sync.py` — вычисление `default_site` из fields.yaml
- `core/pipeline/executor.py` — default_site из fields.yaml при отсутствии в options

**Тесты:** 7 тестов в `tests/test_core/test_device.py`

### VLAN Assignment on Interface CREATE ✅

**Проблема:** При первом запуске pipeline VLAN на интерфейсы не назначались.
Они назначались только при UPDATE (второй запуск).

**Причина:** `_build_create_data()` не включала VLAN-поля (untagged_vlan, tagged_vlans)
при создании нового интерфейса.

**Решение:** `_build_create_data()` теперь включает `untagged_vlan` и `tagged_vlans`
при создании, если `sync_vlans` включён в `fields.yaml`.

**Файл:** `netbox/sync/interfaces.py`

### --format parsed (Raw TextFSM Output) ✅

**Фича:** Новый формат экспорта `--format parsed` — показывает сырые данные
из TextFSM парсинга **до** нормализации. Сохраняются оригинальные ключи NTC Templates.

**Использование:**
```bash
python -m network_collector interfaces --format parsed
python -m network_collector mac --format parsed
```

**Отличие от raw:** `raw` выводит текст команды с устройства,
`parsed` — результат TextFSM парсинга (структурированные данные до нормализации).

**Файлы:** `cli/commands/collect.py`, `cli/utils.py`, `cli/__init__.py`

### LLDP Protocol Default in Pipeline Fix ✅

**Проблема:** Pipeline LLDP collect использовал protocol=lldp, не собирая CDP соседей.

**Решение:** Добавлен дефолт `protocol=both` для LLDP сбора в pipeline.

```python
# executor.py
if target == "lldp":
    options.setdefault("protocol", "both")
```

**Файл:** `core/pipeline/executor.py`

---

## Bug Fixes (Январь 2026)

### Interface Description Clearing Fix ✅

**Проблема:** Пустой description на устройстве не обновлялся в NetBox.

**Причина:**
- `core/models.py`: `Interface.to_dict()` исключал пустые строки
- Description не попадал в данные для сравнения

**Решение:**
- `Interface.to_dict()` теперь всегда включает `description` (даже пустой)
- `_get_local_field()` корректно различает "пусто" и "отсутствует"

**Тесты:** 4 теста в `TestInterfaceDescriptionClearing`

### Primary IP Display Fix ✅

**Проблема:** Установка primary_ip не отображалась в деталях изменений.

**Решение:** Добавлен вывод `PRIMARY IP:` в `_print_changes_details()`

**Файл:** `cli/commands/sync.py`

### Inventory Skip Logging Fix ✅

**Проблема:** Пропуск inventory items без серийного номера логировался на DEBUG.

**Решение:** Изменён уровень лога на WARNING для видимости.

**Файл:** `netbox/sync/inventory.py`

### Test enabled_mode Mock Fix ✅

**Проблема:** Тест `test_diff_compare_interface_enabled` падал из-за зависимости от конфига.

**Решение:** Добавлен мок `get_sync_config` с `enabled_mode="admin"`

**Файл:** `tests/test_fixes/test_interface_enabled.py`

### Inventory Name Truncation Logging ✅

**Проблема:** Обрезка длинных имён (>64 символов) логировалась непонятно — не было ясно, добавлен элемент или пропущен.

**Решение:** Улучшено логирование с чёткими сообщениями:

| Ситуация | Сообщение |
|----------|-----------|
| Пропущен (нет serial) | `WARNING: Пропущен inventory 'name' - нет серийного номера` |
| Пропущен + обрезано | `WARNING: Пропущен inventory 'long...' - нет серийного номера (имя было бы обрезано до 'short...')` |
| Создан + обрезано | `INFO: Создан inventory: short... [обрезано с 'long...']` |
| Обновлён + обрезано | `INFO: Обновлён inventory: short... [обрезано с 'long...'] (['serial'])` |

**Файл:** `netbox/sync/inventory.py`

---

## Рефакторинг: единый поток парсинга (Февраль 2026) ✅

### NX-OS Switchport Mode Bug ✅

**Проблема:** Все NX-OS trunk-порты с конкретным списком VLAN (10,30,38) стали `tagged-all` вместо `tagged`. VLAN-списки терялись при sync.

**Причина — неучтённый формат NX-OS в `normalize_switchport_data()` (ранее в collectors, теперь в `InterfaceNormalizer`):**

NTC парсер возвращает разные поля для разных платформ:

| Платформа | admin_mode | mode | trunking_vlans | switchport |
|-----------|-----------|------|----------------|------------|
| Cisco IOS | `static access` / `trunk` | `down` / `trunk` (oper) | `["ALL"]` (список) | — |
| NX-OS | **отсутствует** | `trunk` / `access` | `"10,30,38"` (строка) | `Enabled` |
| QTech | — | `ACCESS` / `TRUNK` | — (есть `vlan_lists`) | `enabled` |

Код проверял только `admin_mode` (IOS) и `switchport=="enabled"` (QTech). NX-OS не имеет `admin_mode` → попадал в QTech ветку → искал `vlan_lists` → пустая строка → `tagged-all`.

**Поток данных ДО исправления:**
```
NX-OS → NTC: {mode: "trunk", trunking_vlans: "10,30,38"}
→ normalize_switchport_data()
→ if admin_mode: FALSE (нет у NX-OS)
→ elif switchport == "enabled": TRUE → QTech ветка!
→ vlan_lists = "" (нет такого поля) → tagged-all ❌
```

**Поток данных ПОСЛЕ исправления:**
```
NX-OS → NTC: {mode: "trunk", trunking_vlans: "10,30,38"}
→ normalize_switchport_data()
→ if admin_mode: FALSE
→ elif trunking_vlans + mode: TRUE → NX-OS ветка ✅
→ trunking_vlans = "10,30,38" → tagged ✅
```

**Решение:** Добавлена NX-OS ветка (определяется по наличию `trunking_vlans` + `mode` при отсутствии `admin_mode`).

**Файл:** `core/domain/interface.py` — `InterfaceNormalizer.normalize_switchport_data()`

**Тесты:** +13 тестов NX-OS в `tests/test_collectors/test_switchport_mode.py`

### Дублирование логики парсинга ✅

**Проблема:** `NTCParser.parse()` уже содержит универсальную логику:
1. Ищет кастомный шаблон по `(platform, command)`
2. Fallback на NTC с маппингом `NTC_PLATFORM_MAP`

Но коллекторы дублировали эту логику:
- `_parse_with_ntc()` конвертировал платформу через `get_ntc_platform()` перед вызовом парсера → кастомные шаблоны не находились
- `_parse_switchport_modes()` вызывал парсер дважды (кастомный + NTC) вместо одного вызова
- `_parse_lag_membership()` и `_parse_media_types()` передавали конвертированную платформу

**Поток ДО исправления:**
```
InterfaceCollector._parse_with_ntc(device)
→ ntc_platform = get_ntc_platform("qtech") → "cisco_ios"
→ NTCParser.parse(platform="cisco_ios", command="show interface")
→ Custom lookup: ("cisco_ios", "show interface") → НЕ НАЙДЕН ❌
→ NTC fallback: cisco_ios / show interface → Cisco IOS шаблон (неправильный!)
```

**Поток ПОСЛЕ исправления:**
```
InterfaceCollector._parse_with_ntc(device)
→ NTCParser.parse(platform="qtech", command="show interface")
→ Custom lookup: ("qtech", "show interface") → НАЙДЕН ✅ → qtech_show_interface.textfsm
```

**Решение:**
- `_parse_with_ntc()` — передаёт `device.platform` (не ntc_platform), парсер сам конвертирует
- `_parse_switchport_modes()` — один вызов парсера вместо двух (убрано дублирование)
- `_parse_lag_membership()` — переименован параметр `ntc_platform` → `platform`
- `_parse_media_types()` — переименован параметр `ntc_platform` → `platform`
- Удалён неиспользуемый `get_ntc_platform` из interfaces.py

**Файлы:** `collectors/base.py`, `collectors/interfaces.py`

### Switchport нормализация перенесена в domain layer ✅

**Проблема:** Нормализация switchport данных (`_normalize_switchport_data()`) находилась в `collectors/interfaces.py`,
хотя по архитектуре вся нормализация должна быть в domain layer. Генерация алиасов интерфейсов дублировалась
в трёх местах: `_add_switchport_aliases()` в коллекторе, `_get_interface_name_variants()` в domain,
и частично в `get_interface_aliases()` в constants.

**Решение:**
- `_normalize_switchport_data()` перенесён из `collectors/interfaces.py` в `core/domain/interface.py`
  как `InterfaceNormalizer.normalize_switchport_data()` — статический метод нормализатора
- `_add_switchport_aliases()` **удалён** из коллектора — заменён на `get_interface_aliases()` из `core/constants/interfaces.py`
- `_get_interface_name_variants()` **удалён** из domain — заменён на `get_interface_aliases()`
- Коллектор теперь только парсит (SSH → TextFSM), вся нормализация в domain layer

**Поток данных:**
```
collectors/interfaces.py          → только парсинг (SSH + TextFSM)
core/domain/interface.py          → InterfaceNormalizer.normalize_switchport_data() (нормализация)
core/constants/interfaces.py      → get_interface_aliases() (единый источник алиасов)
```

**Результат:**
- Устранено тройное дублирование генерации алиасов → единый источник `get_interface_aliases()`
- Архитектурная консистентность: collector парсит, domain нормализует
- Упрощено тестирование: нормализация тестируется отдельно от SSH/парсинга

**Файлы:**
- `core/domain/interface.py` — `InterfaceNormalizer.normalize_switchport_data()` (перенесён)
- `core/constants/interfaces.py` — `get_interface_aliases()` (единый источник алиасов)
- `collectors/interfaces.py` — удалены `_normalize_switchport_data()`, `_add_switchport_aliases()`

### Мелкие фиксы ✅

| Баг | Файл | Описание |
|-----|------|----------|
| Alias `Etherneternet` | `core/constants/interfaces.py` | `get_interface_aliases()` (ранее `_add_switchport_aliases()`): Ethernet1/1 → Etherneternet1/1 (двойное ernet). Исправлено в единой функции алиасов |
| Config test hardcode | `tests/test_qtech_support.py` | Тест `max_retries == 2` зависел от config.yaml. Заменён на проверку типа `isinstance(int)` |

## Рефакторинг: унификация платформо-зависимого кода (Февраль 2026) ✅

### Что было

~90% системы уже data-driven (маппинги в constants, шаблоны TextFSM), но в нескольких местах
оставалось дублирование, которое усложняло добавление новых платформ:

| Проблема | Где дублировалось | Сколько мест |
|----------|-------------------|--------------|
| LAG проверка по имени | `detect_port_type()`, `enrich_with_switchport()`, `get_netbox_interface_type()` | 3 |
| Inline разворачивание алиасов LAG members | `_parse_lag_membership()`, `_parse_lag_membership_regex()` | 2 × 20 строк |
| LLDP platform detection | `_extract_platform_from_description()` — if/elif цепочка | 1 (не расширяемо) |
| Platform maps | `core/connection.py` дублировал `core/constants/platforms.py` | 2 копии |
| Default platform `"cisco_ios"` | `cli/utils.py`, `api/routes/device_management.py`, `connection.py` | 4 |

### Что сделано

#### 1. `is_lag_name()` — единый источник LAG определения ✅

**Файл:** `core/constants/interfaces.py`

Добавлены `LAG_PREFIXES` и `is_lag_name()` — одна функция для проверки, является ли интерфейс LAG.
Поддерживает все форматы: Port-channel1, Po1, AggregatePort 1, Ag1.

3 места дублирования заменены на `is_lag_name()`:
- `core/domain/interface.py:detect_port_type()` — определение port_type="lag"
- `core/domain/interface.py:enrich_with_switchport()` — LAG mode из members
- `core/constants/netbox.py:get_netbox_interface_type()` — NetBox type "lag"

**Что стало лучше:** Добавление нового LAG формата — одно изменение в `is_lag_name()` вместо трёх.

#### 2. LAG alias expansion через `_add_lag_member_aliases()` ✅

**Файл:** `collectors/interfaces.py`

`_parse_lag_membership()` и `_parse_lag_membership_regex()` содержали по 20 строк
inline if/elif для разворачивания алиасов (Hu→HundredGigE, Te→TenGigabitEthernet...).
При этом уже существовал метод `_add_lag_member_aliases()`, использующий `get_interface_aliases()`.

Два дублирующих блока заменены на вызов `self._add_lag_member_aliases()`.

**Что стало лучше:** 40 строк дублирующего кода удалено. Новый тип интерфейса автоматически
поддерживается через `get_interface_aliases()` без изменения LAG парсеров.

#### 3. LLDP platform detection — data-driven ✅

**Файл:** `core/domain/lldp.py`

if/elif цепочка для извлечения платформы из LLDP System Description заменена на
data-driven `_PLATFORM_PATTERNS` — список кортежей `(keyword, regex, prefix)`.

**Что стало лучше:** Добавление нового вендора — одна строка в `_PLATFORM_PATTERNS` вместо
нового блока if/elif с regex.

#### 4. Platform maps — единый источник в constants ✅

**Файл:** `core/connection.py`

`SCRAPLI_PLATFORM_MAP` и `NTC_PLATFORM_MAP` дублировались: определены в `core/constants/platforms.py`
и скопированы в `core/connection.py`. Теперь connection.py импортирует из constants.

**Что стало лучше:** Одна копия маппинга вместо двух. Изменение в одном месте.

#### 5. `DEFAULT_PLATFORM` константа ✅

**Файл:** `core/constants/platforms.py`

Строка `"cisco_ios"` как дефолтная платформа была в 4 местах. Заменена на константу
`DEFAULT_PLATFORM` из `core/constants/platforms.py`.

Используется в: `core/connection.py`, `cli/utils.py`, `api/routes/device_management.py`.

**Что стало лучше:** Изменение default platform — одно место вместо четырёх.

### Что ещё можно улучшить (TODO)

*Все три задачи ниже выполнены (1906 тестов):*

#### ~~LAG parser dispatch~~ ✅ ВЫПОЛНЕНО

`collectors/interfaces.py` — заменён `if/elif` на data-driven `LAG_PARSERS` dict:
```python
LAG_PARSERS = {
    "qtech": "_parse_lag_membership_qtech",
    "qtech_qsw": "_parse_lag_membership_qtech",
}
# Dispatch: getattr(self, LAG_PARSERS.get(platform))(output)
# Default: _parse_lag_membership() для всех остальных платформ
```
Для новой платформы с кастомным парсером — добавить метод и запись в `LAG_PARSERS`.

#### ~~Switchport normalization~~ ✅ ВЫПОЛНЕНО

Извлечён `_resolve_trunk_mode(raw_vlans)` в `core/domain/interface.py`:
```python
@staticmethod
def _resolve_trunk_mode(raw_vlans) -> tuple:
    # list → str, "all"/"1-4094"/"1-4093"/"1-4095" → ("tagged-all", "")
    # Конкретные VLAN → ("tagged", vlans_str)
```
Дублирование trunk VLAN resolution между Cisco IOS и NX-OS ветками устранено.
Три ветки определения платформы (по полям) сохранены — они необходимы.

#### ~~Domain layer deduplication~~ ✅ ВЫПОЛНЕНО

Три новых маппинга в `core/constants/interfaces.py`:
- `MEDIA_TYPE_PORT_TYPE_MAP` — media_type паттерн → port_type
- `HARDWARE_TYPE_PORT_TYPE_MAP` — hardware_type паттерн → port_type
- `INTERFACE_NAME_PORT_TYPE_MAP` — префикс имени → port_type

Методы `_detect_from_media_type()`, `_detect_from_hardware_type()`, `_detect_from_interface_name()`
теперь итерируют по маппингам вместо if/elif. Порядок ключей критичен (более специфичные первыми).
`get_netbox_interface_type()` в `netbox.py` не изменён — использует свои более специфичные маппинги.

---

## Статистика проекта

| Метрика | Значение |
|---------|----------|
| Python файлов | ~90 |
| Строк кода | ~17,000 |
| Тестов | 1906 |
| Тестовых категорий | 12 (включая test_configurator, корневые) |
| CLI команд | 11 |
| API endpoints | 13 |
| Vue компонентов | 14 |
| Поддерживаемых платформ | 7 |
| Функций с type hints | 370+ |
| Документов | 20 (7 официальных + 13 обучающих) |
