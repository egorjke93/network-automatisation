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
| **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** | Архитектура, слои, поток данных |
| **[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)** | Разработка, тесты, добавление платформ |
| **[docs/DATA_FLOW_LLDP.md](docs/DATA_FLOW_LLDP.md)** | Детальный поток данных LLDP/CDP |
| **[docs/TODO.md](docs/TODO.md)** | План развития проекта |

## Ключевые файлы

| Файл | Описание |
|------|----------|
| `cli.py` | CLI команды |
| `api/` | FastAPI backend |
| `frontend/` | Vue.js frontend |
| `core/constants.py` | Маппинги платформ |
| `netbox/sync.py` | Синхронизация с NetBox |
| `fields.yaml` | Поля экспорта/синхронизации |
| `config.yaml` | Настройки приложения |

## Быстрые команды

```bash
# Сбор данных
python -m network_collector devices --format excel
python -m network_collector mac --format excel
python -m network_collector lldp --protocol both

# Синхронизация с NetBox
python -m network_collector sync-netbox --sync-all --site "Office" --dry-run

# Тесты
pytest tests/ -v
```

## Подробности

Смотри документацию в `docs/` для полной информации.
