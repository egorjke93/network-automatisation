# Network Collector — Контекст для Claude

## Описание

Всегда документируем изменения и актуализируем документацию в папке `docs/`


Утилита для сбора данных с сетевого оборудования (Cisco, Arista, Juniper, QTech) и синхронизации с NetBox.

## Запуск

```bash
# ВАЖНО: Запускать из /home/sa/project (не из network_collector!)
cd /home/sa/project
source network_collector/myenv/bin/activate
python -m network_collector --help
```

## Документация

### Официальная (для использования и разработки)

| Документ | Описание |
|----------|----------|
| **[docs/MANUAL.md](docs/MANUAL.md)** | Полное руководство: CLI, Web UI, API, Pipeline |
| **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** | Архитектура, слои, поток данных |
| **[docs/WEB_API.md](docs/WEB_API.md)** | REST API документация, endpoints, примеры |
| **[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)** | Разработка, добавление платформ |
| **[docs/PLATFORM_GUIDE.md](docs/PLATFORM_GUIDE.md)** | Полная цепочка: платформы, шаблоны, парсинг, отладка |
| **[docs/TESTING.md](docs/TESTING.md)** | Тестирование: структура, запуск, написание тестов |
| **[docs/TODO.md](docs/TODO.md)** | План развития проекта |
| **[docs/BUGFIX_LOG.md](docs/BUGFIX_LOG.md)** | Журнал багов: причины, цепочки, исправления |

### Обучающая (изучение проекта с нуля)

| # | Документ | Описание |
|---|----------|----------|
| -- | **[docs/learning/README.md](docs/learning/README.md)** | Путеводитель: с чего начать, порядок чтения |
| 01 | **[01_PYTHON_BASICS.md](docs/learning/01_PYTHON_BASICS.md)** | Python-концепции на примерах проекта |
| 02 | **[02_PROJECT_OVERVIEW.md](docs/learning/02_PROJECT_OVERVIEW.md)** | Обзор проекта: зачем, слои, структура папок |
| 03 | **[03_CLI_INTERNALS.md](docs/learning/03_CLI_INTERNALS.md)** | CLI: от ввода команды до результата |
| 04 | **[04_DATA_COLLECTION.md](docs/learning/04_DATA_COLLECTION.md)** | Сбор данных: SSH, парсинг, модели |
| 05 | **[05_SYNC_NETBOX.md](docs/learning/05_SYNC_NETBOX.md)** | Синхронизация с NetBox: diff, batch API, кэши |
| 06 | **[06_PIPELINE.md](docs/learning/06_PIPELINE.md)** | Pipeline: автоматизация цепочек операций |
| 07 | **[07_DATA_FLOWS.md](docs/learning/07_DATA_FLOWS.md)** | Потоки данных: LLDP, MAC match, interfaces |
| 08 | **[08_WEB_ARCHITECTURE.md](docs/learning/08_WEB_ARCHITECTURE.md)** | Web: FastAPI backend, Vue.js frontend |
| 09 | **[09_MIXINS_PATTERNS.md](docs/learning/09_MIXINS_PATTERNS.md)** | Mixins: паттерн, self: SyncBase, MRO, собеседование |
| 10 | **[10_COLLECTORS_DEEP_DIVE.md](docs/learning/10_COLLECTORS_DEEP_DIVE.md)** | Collectors Deep Dive: CLI → SSH → TextFSM → Normalizer → Export |
| 11 | **[11_SYNC_DEEP_DIVE.md](docs/learning/11_SYNC_DEEP_DIVE.md)** | Sync Deep Dive: SyncComparator → миксины → batch API → NetBox |
| 12 | **[12_INTERNALS_AND_TESTING.md](docs/learning/12_INTERNALS_AND_TESTING.md)** | Internals: Config, Constants, Exceptions, Testing patterns |
| 13 | **[13_SWITCHPORT_FLOW.md](docs/learning/13_SWITCHPORT_FLOW.md)** | Switchport Flow: SSH → TextFSM → нормализация → NetBox sync |
| 14 | **[14_INTERFACE_NAME_MAPPINGS.md](docs/learning/14_INTERFACE_NAME_MAPPINGS.md)** | Маппинг имён интерфейсов: Gi0/1 vs GigabitEthernet0/1 |
| 15 | **[15_PUSH_CONFIG.md](docs/learning/15_PUSH_CONFIG.md)** | Push Config: YAML → маппинг платформ → ConfigPusher → Netmiko |
| 16 | **[16_NETBOX_CLIENT_DEEP_DIVE.md](docs/learning/16_NETBOX_CLIENT_DEEP_DIVE.md)** | NetBox Client: pynetbox, 6 миксинов, bulk API, slug, lazy loading |
| 17 | **[17_PYTHON_WORKBOOK.md](docs/learning/17_PYTHON_WORKBOOK.md)** | Workbook: ~60 задач, 15 блоков, 3 мини-проекта — пиши код сам |
| 18 | **[18_PORT_TYPE_AND_SPEED.md](docs/learning/18_PORT_TYPE_AND_SPEED.md)** | Полная цепочка: тип порта + скорость, все маппинги, номинальная скорость |
| 19 | **[19_GIT_BACKUP.md](docs/learning/19_GIT_BACKUP.md)** | Бэкап конфигов в Git: CLI → SSH → GitBackupPusher → Gitea REST API, site_map, SSL |

## Ключевые файлы

| Файл | Описание |
|------|----------|
| `cli/` | CLI модуль (модульная структура) |
| `cli/__init__.py` | Точка входа CLI, `main()` и `setup_parser()` |
| `cli/commands/` | Обработчики команд (collect, sync, backup, pipeline) |
| `api/` | FastAPI backend |
| `api/routes/` | Эндпоинты (devices, sync, pipelines, history) |
| `api/services/` | Сервисы (sync_service, history_service, task_manager) |
| `frontend/` | Vue.js frontend |
| `frontend/src/views/` | Страницы (Sync.vue, Pipelines.vue, History.vue) |
| `core/pipeline/` | Pipeline система (executor, models) |
| `core/git_pusher.py` | GitBackupPusher: push бэкапов в Gitea через REST API |
| `core/constants/` | Маппинги платформ, команды, интерфейсы (пакет модулей) |
| `netbox/sync/` | Синхронизация с NetBox (модульная структура) |
| `config_commands.yaml` | Команды конфигурации по платформам (push-config) |
| `fields.yaml` | Поля экспорта/синхронизации (sync_vlans option) |
| `config.yaml` | Настройки приложения |
| `data/` | Данные: devices.json, history.json |

## Быстрые команды

```bash
# Сбор данных (CLI)
python -m network_collector devices --format excel
python -m network_collector mac --format excel
python -m network_collector lldp --protocol both

# Синхронизация с NetBox
python -m network_collector sync-netbox --sync-all --site "Office" --dry-run

# Синхронизация с VLAN на интерфейсы (включить sync_vlans: true в fields.yaml)
python -m network_collector sync-netbox --interfaces --dry-run

# Бэкап с push в Git (Gitea)
python -m network_collector backup --push-git --site "Main"
python -m network_collector backup --git-test

# Конфигурация устройств по платформам
python -m network_collector push-config --commands config_commands.yaml
python -m network_collector push-config --commands config_commands.yaml --apply

# Pipeline (cleanup работает для interfaces, cables, inventory, ip_addresses)
python -m network_collector pipeline run default --apply
# LLDP в pipeline по умолчанию собирает оба протокола (protocol=both)

# Тесты
pytest tests/ -v
```

## Web интерфейс

```bash
# Backend (FastAPI) - порт 8080
cd /home/sa/project
source network_collector/myenv/bin/activate
uvicorn network_collector.api.main:app --host 0.0.0.0 --port 8080 --reload

# Frontend (Vue.js) - порт 5173
cd /home/sa/project/network_collector/frontend
npm run dev
```

**URL:**
- Web UI: http://localhost:5173
- API Docs: http://localhost:8080/docs

**Страницы Web UI:**
| URL | Описание |
|-----|----------|
| `/sync` | Синхронизация с NetBox |
| `/pipelines` | Управление Pipeline |
| `/history` | Журнал операций (полные детали) |
| `/device-management` | CRUD устройств |
| `/devices`, `/mac`, `/lldp` | Сбор данных |

**История операций:**
- Хранится в `data/history.json` (макс. 1000 записей)
- Sync сохраняет полный diff всех изменений
- Pipeline сохраняет детали по каждому шагу

## Git: как пушить изменения

**ВАЖНО:** Рабочая папка `/home/sa/project/network_collector` НЕ имеет git remote!

Git репозиторий с remote находится в другой папке:
- **Рабочая папка:** `/home/sa/project/network_collector` — здесь работаем
- **Git папка:** `/home/sa/project/network-automatisation/network_collector` — здесь пушим

**Процедура git push:**

```bash
# 1. Копируем изменённые файлы в git папку
cp /home/sa/project/network_collector/<файл> /home/sa/project/network-automatisation/network_collector/<файл>

# 2. Переходим в git папку, добавляем, коммитим, пушим
cd /home/sa/project/network-automatisation/network_collector
git add <файлы>
git commit -m "Описание изменений"
git push
```

**Правила:**
- НЕ трогать рабочую папку для git операций
- Только копировать файлы в git папку и пушить оттуда
- Remote: `https://github.com/egorjke93/network-automatisation.git`

## Подробности

Смотри документацию в `docs/` для полной информации.
