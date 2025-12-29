# Network Collector — Контекст для Claude

## Описание

Утилита для сбора данных с сетевого оборудования (Cisco, Arista, Juniper, QTech) и синхронизации с NetBox.

## Запуск

```bash
# ВАЖНО: Запускать из /home/sa/project (не из network_collector!)
cd /home/sa/project
source network_collector/myenv/bin/activate
python -m network_collector --help
```

## Документация

- **[docs/MANUAL.md](docs/MANUAL.md)** — полное руководство (команды, опции, конфигурация)
- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** — архитектура, поток данных
- **[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)** — разработка, тесты, добавление платформ

## Структура проекта

```
network_collector/
├── cli.py                   # CLI команды
├── config.yaml              # Настройки приложения
├── fields.yaml              # Поля экспорта и синхронизации
├── devices_ips.py           # Список устройств
│
├── core/                    # Ядро
│   ├── connection.py        # SSH (Scrapli)
│   ├── device.py            # Модель Device
│   ├── models.py            # Data Models
│   ├── constants.py         # Маппинги платформ
│   └── domain/              # Нормализаторы
│
├── collectors/              # Сборщики данных
│   ├── mac.py, lldp.py, interfaces.py, ...
│
├── netbox/                  # NetBox синхронизация
│   ├── client.py            # API клиент
│   └── sync.py              # Логика синхронизации
│
├── exporters/               # Экспорт (Excel, CSV, JSON)
└── docs/                    # Документация
```

## Ключевые файлы

| Файл | Описание |
|------|----------|
| `cli.py` | Все CLI команды |
| `core/constants.py` | Маппинги платформ, типов интерфейсов |
| `netbox/sync.py` | Синхронизация с NetBox |
| `fields.yaml` | Какие поля экспортировать/синхронизировать |
| `config.yaml` | Настройки (credentials, фильтры, логирование) |

## Конфигурация

**config.yaml** — настройки приложения:
- `filters.exclude_interfaces` — исключить интерфейсы из MAC export
- `filters.exclude_vlans` — исключить VLAN
- `logging.level` — уровень логирования

**fields.yaml** — поля и синхронизация:
- `sync.interfaces.options.exclude_interfaces` — исключить из NetBox sync

## Тесты

```bash
pytest tests/ -v              # Все тесты
pytest tests/ --tb=short      # Короткий вывод
```

## Основные команды

```bash
# Сбор данных
python -m network_collector devices --format excel
python -m network_collector mac --format excel
python -m network_collector lldp --protocol both

# Синхронизация с NetBox
python -m network_collector sync-netbox --sync-all --site "Office" --dry-run
python -m network_collector sync-netbox --create-devices --update-devices
python -m network_collector sync-netbox --interfaces --show-diff
```

## Добавление платформы

1. `core/constants.py` — SCRAPLI_PLATFORM_MAP, NTC_PLATFORM_MAP
2. `collectors/*.py` — platform_commands
3. `templates/*.textfsm` — кастомные шаблоны (если нужно)

См. [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) для деталей.
