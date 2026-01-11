# Network Collector - План развития

## Текущее состояние (Январь 2026)

### CLI Команды (10 штук)

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
| `pipeline` | Управление pipelines | **НЕТ** |

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

### Pipeline System (NEW)

| Компонент | Файл | Статус |
|-----------|------|--------|
| Models | `core/pipeline/models.py` | OK |
| Executor | `core/pipeline/executor.py` | OK |
| API Schemas | `api/schemas/pipeline.py` | OK |
| API Routes | `api/routes/pipelines.py` | OK |
| Vue UI | `frontend/src/views/Pipelines.vue` | OK |
| CLI command | `cli.py` | **НЕТ** |
| Tests | `tests/test_core/test_pipeline/` | 68 тестов |

---

## Что нужно доработать

### 1. CLI Pipeline команда (Высокий приоритет)

**Проблема:** Pipeline можно использовать только через Web UI/API, нет CLI команды.

**Решение:** Добавить `pipeline` subcommand в `cli.py`:

```bash
# Список pipelines
python -m network_collector pipeline list

# Показать детали pipeline
python -m network_collector pipeline show default

# Запустить pipeline
python -m network_collector pipeline run default --dry-run

# Валидировать pipeline
python -m network_collector pipeline validate default

# Создать из YAML
python -m network_collector pipeline create my_pipeline.yaml

# Удалить
python -m network_collector pipeline delete my_pipeline
```

**Оценка:** 2-3 часа

---

### 2. Документация (Высокий приоритет)

#### 2.1 Обновить MANUAL.md

- [ ] Добавить раздел "Pipeline"
- [ ] Добавить раздел "Web интерфейс"
- [ ] Добавить раздел "API"
- [ ] Обновить оглавление

#### 2.2 Создать WEB_API.md

Полная документация REST API:
- Все endpoints с примерами
- Request/Response schemas
- Коды ошибок
- Примеры curl

#### 2.3 Создать PIPELINES.md

Детальная документация Pipeline:
- Архитектура
- YAML формат
- Типы шагов
- Зависимости
- Примеры

**Оценка:** 4-5 часов

---

### 3. CRUD улучшения ✅ ВЫПОЛНЕНО

#### 3.1 sync-netbox improvements

| Операция | Статус | Флаг |
|----------|--------|------|
| DELETE interfaces | ✅ OK | `--cleanup-interfaces` |
| DELETE IP addresses | ✅ OK | `--cleanup-ips` |
| DELETE cables | ✅ OK | `--cleanup-cables` |
| UPDATE IP addresses | ✅ OK | `--update-ips` |
| UPDATE cables | — | Низкий приоритет |
| DELETE VLAN | — | Низкий приоритет |

#### 3.2 Архитектура (Domain Layer)

Реализована чистая архитектура:
- `core/domain/sync.py` — бизнес-логика сравнения (SyncComparator)
- `netbox/sync.py` — инфраструктура (API операции)

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

### 4. Web UI улучшения

#### 4.1 Pipelines UI

- [ ] Drag-and-drop редактор шагов
- [ ] Визуализация зависимостей (граф)
- [ ] Real-time лог выполнения (WebSocket)
- [ ] История запусков
- [ ] Шаблоны pipelines

#### 4.2 General UI

- [ ] Темная тема
- [ ] Экспорт данных из UI
- [ ] Графики и дашборды
- [ ] Пагинация больших таблиц

**Оценка:** Много часов, низкий приоритет

---

### 5. Тестирование

| Тип | Текущее | Нужно |
|-----|---------|-------|
| Unit tests | 987 | OK |
| Integration tests | 13 (pipeline) | Добавить для API |
| E2E tests | 1 | Расширить |
| Coverage | ~70% | 80%+ |

**Задачи:**
- [ ] API integration tests (FastAPI TestClient)
- [ ] E2E tests для collectors
- [ ] Mock-based tests для NetBox sync

**Оценка:** 8-10 часов

---

## Приоритеты

### Неделя 1: Критичное

1. **CLI Pipeline команда** - чтобы можно было запускать без Web UI
2. **Обновить MANUAL.md** - добавить Pipeline и Web разделы

### Неделя 2: Важное

3. **Создать WEB_API.md** - полная API документация
4. **Создать PIPELINES.md** - детальная pipeline документация

### Неделя 3+: Улучшения

5. CRUD cleanup операции (interfaces, IPs)
6. API integration tests
7. UI улучшения

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

## Статистика проекта

| Метрика | Значение |
|---------|----------|
| Python файлов | ~80 |
| Строк кода | ~15,000 |
| Тестов | 987 |
| CLI команд | 10 (+1 pipeline TODO) |
| API endpoints | 12 |
| Vue компонентов | 12 |
| Поддерживаемых платформ | 7 |
