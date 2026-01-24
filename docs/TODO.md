# Network Collector - План развития

> Последнее обновление: Январь 2026

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
| Tests | `tests/test_core/test_pipeline/` + `tests/test_cli/test_pipeline.py` | 95 тестов |

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
| `netbox/client.py` | 1059 | Много методов, но терпимо |

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

### 5. Документация (Средний приоритет)

#### 5.1 Обновить MANUAL.md

- [ ] Добавить раздел "Pipeline"
- [ ] Добавить раздел "Web интерфейс"
- [ ] Добавить раздел "API"
- [ ] Обновить оглавление

#### 5.2 Создать WEB_API.md

Полная документация REST API:
- Все endpoints с примерами
- Request/Response schemas
- Коды ошибок
- Примеры curl

#### 5.3 Создать PIPELINES.md

Детальная документация Pipeline:
- Архитектура
- YAML формат
- Типы шагов
- Зависимости
- Примеры

**Оценка:** 4-5 часов

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

### 8. Синхронизация VLAN на интерфейсы (Средний приоритет)

**Проблема:** NetBox поддерживает VLAN на интерфейсах (untagged_vlan, tagged_vlans), но мы не синхронизируем эти поля.

**Текущее состояние:**

| Компонент | Статус |
|-----------|--------|
| Сбор mode (access/trunk) | ✅ Есть |
| Сбор native_vlan | ✅ Есть |
| Сбор access_vlan | ✅ Есть |
| Поля в fields.yaml | ✅ Настроены |
| Sync mode в NetBox | ✅ Работает |
| **Sync untagged_vlan** | ❌ Не реализовано |
| **Sync tagged_vlans** | ❌ Не реализовано |

**Что нужно реализовать:**

1. **Сбор списка tagged VLANs:**
   - Команда: `show interfaces trunk`
   - Парсинг: "Vlans allowed on trunk: 10,20,30-50,100"
   - Сохранение в `Interface.tagged_vlans` как список

2. **Поиск VLAN в NetBox:**
   - Метод `get_vlan_by_vid(vid, site=None)` в NetBox клиенте
   - Кэширование VID → VLAN ID для производительности

3. **Синхронизация в `netbox/sync/interfaces.py`:**
   ```python
   # Access port
   if mode == "access" and access_vlan:
       vlan = client.get_vlan_by_vid(access_vlan, site=device.site)
       updates["untagged_vlan"] = vlan.id

   # Trunk port
   if mode in ("tagged", "tagged-all") and native_vlan:
       vlan = client.get_vlan_by_vid(native_vlan, site=device.site)
       updates["untagged_vlan"] = vlan.id

   if mode == "tagged" and tagged_vlans:
       vlan_ids = [client.get_vlan_by_vid(v).id for v in tagged_vlans]
       updates["tagged_vlans"] = vlan_ids
   ```

4. **Парсинг диапазонов VLAN:**
   - "10-20,30,100" → [10,11,12...20,30,100]
   - Утилита `parse_vlan_range()`

**Сложности:**
- VLAN должен существовать в NetBox (по VID и site)
- Для trunk с 1-4094 (tagged-all) — не синхронизировать список
- Обработка ошибок если VLAN не найден

**Файлы для изменения:**
- `collectors/interfaces.py` — добавить парсинг `show interfaces trunk`
- `netbox/client.py` — добавить `get_vlan_by_vid()`
- `netbox/sync/interfaces.py` — добавить sync untagged_vlan, tagged_vlans
- `core/models.py` — tagged_vlans как List[int] вместо str

**Оценка:** 6-8 часов

---

### 9. Тестирование (Низкий приоритет)

| Тип | Текущее | Нужно |
|-----|---------|-------|
| Unit tests | 1049 | ✅ OK |
| Integration tests | 13 (pipeline) | Добавить для API |
| E2E tests | 2 | Расширить |
| Coverage | ~70% | 80%+ |

**Задачи:**
- [ ] API integration tests (FastAPI TestClient)
- [ ] E2E tests для collectors
- [ ] Mock-based tests для NetBox sync

**Оценка:** 8-10 часов

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
| 6 | Документация | 4-5ч | MANUAL, WEB_API, PIPELINES |
| 7 | **VLAN sync на интерфейсы** | 6-8ч | untagged_vlan, tagged_vlans → NetBox |

### 🟢 Низкий приоритет

| # | Задача | Оценка | Описание |
|---|--------|--------|----------|
| 8 | Web UI улучшения | 10+ч | Темы, графики, drag-drop |
| 9 | Расширение тестов | 8-10ч | API tests, E2E, coverage |

---

## Что уже хорошо ✅

- ✅ 1049 тестов (хорошее покрытие)
- ✅ Структурированное JSON логирование
- ✅ Domain Layer с нормализаторами
- ✅ Pipeline система с транзакциями
- ✅ Pydantic модели для валидации
- ✅ Подробная документация (6 файлов)
- ✅ Type hints в 344 функциях

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
    │ (TODO)  │        │ (FastAPI) │       │  (Vue.js) │
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

## Статистика проекта

| Метрика | Значение |
|---------|----------|
| Python файлов | ~90 |
| Строк кода | ~17,000 |
| Тестов | 1356+ |
| CLI команд | 11 |
| API endpoints | 13 |
| Vue компонентов | 14 |
| Поддерживаемых платформ | 7 |
| Функций с type hints | 370+ |
| Документов | 8 |
