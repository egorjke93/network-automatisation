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

| Документ | Описание |
|----------|----------|
| **[docs/MANUAL.md](docs/MANUAL.md)** | Полное руководство: CLI, Web UI, API, Pipeline |
| **[docs/WEB_API.md](docs/WEB_API.md)** | REST API документация, endpoints, примеры |
| **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** | Архитектура, слои, поток данных |
| **[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)** | Разработка, тесты, добавление платформ |
| **[docs/DATA_FLOW_LLDP.md](docs/DATA_FLOW_LLDP.md)** | Детальный поток данных LLDP/CDP |
| **[docs/TODO.md](docs/TODO.md)** | План развития проекта |

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
| `core/constants.py` | Маппинги платформ |
| `netbox/sync/` | Синхронизация с NetBox (модульная структура) |
| `fields.yaml` | Поля экспорта/синхронизации |
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

# Pipeline
python -m network_collector pipeline run default --apply

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
