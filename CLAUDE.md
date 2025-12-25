# Network Collector

Утилита для сбора данных с сетевого оборудования и синхронизации с NetBox.

## Описание

Network Collector собирает информацию с сетевых устройств (Cisco, Arista, Juniper, QTech) через SSH, парсит вывод команд с помощью NTC Templates и экспортирует в различные форматы или синхронизирует с NetBox.

## Архитектура

```
CLI (cli.py)
    │
    ├── collectors/      # Сбор данных с устройств
    │   ├── DeviceCollector, DeviceInventoryCollector
    │   ├── MACCollector
    │   ├── LLDPCollector
    │   ├── InterfaceCollector
    │   ├── InventoryCollector  # модули, SFP, PSU
    │   └── ConfigBackupCollector
    │
    ├── core/            # Ядро: подключения, устройства, креды
    │   ├── Device, DeviceStatus
    │   ├── ConnectionManager (Scrapli)
    │   └── CredentialsManager
    │
    ├── parsers/         # NTC Templates парсер
    │
    ├── exporters/       # Excel, CSV, JSON
    │
    ├── configurator/    # MAC matching + push descriptions
    │
    └── netbox/          # NetBox API клиент + синхронизация
```

## Технологии

- **Scrapli** — SSH подключения (transport: ssh2)
- **NTC Templates** — парсинг вывода команд
- **pynetbox** — NetBox API клиент
- **pandas** — работа с данными, Excel
- **Python 3.10+**

## Команды CLI

```bash
# Инвентаризация устройств
python -m network_collector devices --format csv

# Сбор MAC-адресов
python -m network_collector mac --format excel

# Сбор MAC с port-security (offline устройства)
python -m network_collector mac --with-port-security --format excel

# Сбор LLDP соседей
python -m network_collector lldp --protocol lldp --format csv

# Сбор CDP соседей
python -m network_collector lldp --protocol cdp --format csv

# Оба протокола (LLDP + CDP)
python -m network_collector lldp --protocol both --format csv

# Сбор интерфейсов
python -m network_collector interfaces --format json

# Резервное копирование конфигураций
python -m network_collector backup --output backups

# Произвольная команда с NTC парсингом
python -m network_collector run "show version" --format json

# Сопоставление MAC с хостами (GLPI)
python -m network_collector match-mac --mac-file mac.xlsx --hosts-file glpi.xlsx

# Применение описаний портов
python -m network_collector push-descriptions --matched-file matched.xlsx --apply

# Синхронизация с NetBox (полная)
python -m network_collector sync-netbox --sync-all --site "Office" --role "switch" --dry-run

# Отдельные флаги синхронизации
python -m network_collector sync-netbox --create-devices --site "Office" --dry-run
python -m network_collector sync-netbox --interfaces --dry-run
python -m network_collector sync-netbox --ip-addresses --dry-run
python -m network_collector sync-netbox --vlans --site "Office" --dry-run
python -m network_collector sync-netbox --cables --protocol both --dry-run
python -m network_collector sync-netbox --inventory --dry-run
```

## Команда push-descriptions

Применяет описания портов на устройства на основе файла сопоставления MAC → имя хоста.

### Ключи команды

| Ключ | Описание |
|------|----------|
| `--matched-file FILE` | Путь к Excel файлу с сопоставлениями (обязательный) |
| `--only-empty` | Применять только на порты без описания |
| `--overwrite` | Перезаписывать существующие описания |
| `--apply` | Реально применить изменения (без флага — dry-run) |

### Формат входного файла (matched.xlsx)

Файл должен содержать колонки:
- **Device** — hostname устройства
- **Interface** — имя интерфейса (Gi0/1, Eth1/1)
- **Host_Name** — новое описание для порта
- **Current_Description** — текущее описание (для сравнения)
- **Matched** — "Yes" для применения

### Примеры использования

```bash
# Показать что будет изменено (dry-run)
python -m network_collector push-descriptions --matched-file matched.xlsx

# Применить только на пустые порты
python -m network_collector push-descriptions --matched-file matched.xlsx --only-empty --apply

# Перезаписать все описания
python -m network_collector push-descriptions --matched-file matched.xlsx --overwrite --apply
```

### Важные особенности

- Без `--apply` команда работает в режиме dry-run (показывает что будет сделано)
- Если текущее описание совпадает с новым — порт пропускается
- Конфигурация автоматически сохраняется (`write memory`)
- Поддерживаются платформы: cisco_ios, cisco_iosxe, cisco_nxos, arista_eos

## Файл устройств (devices_ips.py)

### Ключевые поля

| Поле | Описание | Пример |
|------|----------|--------|
| `host` | IP-адрес устройства (обязательный) | `192.168.1.1` |
| `platform` | Драйвер для SSH (Scrapli/Netmiko/NTC) | `cisco_iosxe`, `arista_eos` |
| `device_type` | Модель для NetBox (опционально) | `C9200L-24P-4X` |
| `role` | Роль устройства для NetBox | `switch`, `router` |

### Новый формат (рекомендуется)

```python
devices_list = [
    # platform - драйвер для SSH (обязательный)
    # device_type - модель для NetBox (опционально, определяется из show version)
    {"host": "192.168.1.1", "platform": "cisco_iosxe", "device_type": "C9200L-24P-4X"},
    {"host": "192.168.1.2", "platform": "cisco_iosxe"},  # модель определится из show version
    {"host": "192.168.1.3", "platform": "arista_eos", "role": "switch"},
    {"host": "192.168.1.4", "platform": "juniper_junos"},
]
```

### Старый формат (backward compatible)

```python
# device_type используется как platform (автоматически конвертируется)
devices_list = [
    {"host": "192.168.1.1", "device_type": "cisco_ios"},
    {"host": "192.168.1.2", "device_type": "cisco_ios"},
]
```

### Автоопределение

- **vendor** — определяется автоматически из platform (cisco, arista, juniper)
- **device_type (модель)** — если не указан, определяется из `show version`
- При синхронизации с NetBox, если device_type не существует — создаётся автоматически

## Поддерживаемые платформы

- `cisco_ios` — Cisco IOS/IOS-XE
- `cisco_nxos` — Cisco NX-OS
- `cisco_iosxr` — Cisco IOS-XR
- `arista_eos` — Arista EOS
- `juniper_junos` — Juniper JunOS
- `qtech` / `qtech_qsw` — QTech

## Добавление новой платформы (QTech, Eltex и др.)

### Архитектура маппингов

```
devices_ips.py           core/device.py                 core/constants.py
─────────────────        ─────────────                  ─────────────────
platform: "qtech"  →     vendor = get_vendor_by_platform("qtech")  →  VENDOR_MAP
                              ↓ автоопределение                        "qtech": ["qtech"]
                         vendor = "qtech"                                    ↓
                              ↓                           manufacturer = "Qtech" (для NetBox)
device_type: "QSW-M3..."  →  model для NetBox (если указан)

                         core/connection.py             collectors/
                         ───────────────────            ───────────
                         SCRAPLI_PLATFORM_MAP:          platform_commands:
                          "qtech": "cisco_iosxe"         "qtech": "show mac-address-table"
                                    ↓ SSH драйвер                  ↓ своя команда
                         NTC_PLATFORM_MAP:
                          "qtech": "cisco_ios"
                                    ↓ парсинг (fallback)

                         CUSTOM_TEXTFSM_TEMPLATES:      templates/
                          ("qtech", "show mac..."): →   qtech_show_mac.textfsm
                                    ↓ кастомный парсинг (приоритет)
```

### Шаг 1: Добавить маппинг платформы

В `core/constants.py`:
```python
SCRAPLI_PLATFORM_MAP = {
    "qtech": "cisco_iosxe",  # SSH драйвер
}

NTC_PLATFORM_MAP = {
    "qtech": "cisco_ios",    # парсинг (если вывод как у Cisco)
}
```

### Шаг 2: Добавить команду (если отличается)

В коллекторе (например `collectors/mac.py`):
```python
platform_commands = {
    "qtech": "show mac-address-table",  # своя команда
}
```

### Шаг 3: Добавить кастомный шаблон (если вывод отличается)

1. Добавь маппинг в `core/constants.py`:
```python
CUSTOM_TEXTFSM_TEMPLATES = {
    ("qtech", "show mac address-table"): "qtech_show_mac.textfsm",
}
```

2. Создай шаблон в `templates/qtech_show_mac.textfsm`

См. `templates/README.md` для примеров шаблонов.

## NetBox интеграция

Переменные окружения:
```bash
export NETBOX_URL="https://netbox.example.com"
export NETBOX_TOKEN="your-api-token"
```

Версия NetBox: 4.4.x (pynetbox >= 7.4.0)

### Флаги синхронизации sync-netbox

| Флаг | Что делает | С `--update-devices` |
|------|------------|----------------------|
| `--create-devices` | Создаёт устройства в NetBox | Обновляет serial/model/site/role |
| `--interfaces` | Синхронизирует интерфейсы | Обновляет type/mode/description |
| `--ip-addresses` | Создаёт IP-адреса | Обновляет tenant/description |
| `--vlans` | Создаёт VLAN | Нет эффекта |
| `--cables` | Создаёт кабели из LLDP/CDP | Нет эффекта |
| `--inventory` | Синхронизирует модули/SFP | Нет эффекта |
| `--sync-all` | Все флаги вместе | Включает автоматически |

### Флаг --update-devices

**Работает с `--create-devices`, `--interfaces`, `--ip-addresses`**

**Без флага:**
```bash
# Только создаёт НОВЫЕ устройства, существующие пропускает
sync-netbox --create-devices --site "Office"
```

**С флагом:**
```bash
# Создаёт новые И ОБНОВЛЯЕТ существующие (serial, model, site, role, tenant)
sync-netbox --create-devices --update-devices --site "Office"
```

**Что обновляется:**
- ✅ Serial number
- ✅ Model (device_type)
- ✅ Site
- ✅ Role
- ✅ Tenant
- ✅ Platform

### Приоритет role

Role берётся в таком порядке:

1. **devices_ips.py** (для конкретного устройства) — высший приоритет
2. **CLI параметр** `--role` — дефолт для устройств без роли

```python
# devices_ips.py
devices_list = [
    {"host": "10.0.0.1", "platform": "cisco_ios", "role": "Router"},  # → Router
    {"host": "10.0.0.2", "platform": "cisco_ios"},                     # → Switch (дефолт CLI)
]
```

```bash
# CLI: role из devices_ips.py имеет приоритет
sync-netbox --create-devices --role switch
# 10.0.0.1 → Router (из devices_ips.py)
# 10.0.0.2 → Switch (из CLI)
```

### IP-адреса: создание и обновление

```bash
# Только создать новые IP (существующие пропускаются)
sync-netbox --ip-addresses

# Создать новые И обновить существующие (tenant, description)
sync-netbox --ip-addresses --update-devices
```

**Без `--update-devices`:**
- ✅ Новые IP создаются
- ⏭️ Существующие IP пропускаются

**С `--update-devices`:**
- ✅ Новые IP создаются
- ✅ Существующие IP обновляются:
  - tenant (от устройства)
  - description (от интерфейса)
  - привязка к интерфейсу

**При создании IP-адреса:**
- Tenant берётся от устройства
- Description берётся от интерфейса

### Примеры синхронизации

```bash
# Первая синхронизация (создать всё)
sync-netbox --sync-all --site "Office" --dry-run

# Добавить только новые устройства (существующие не трогать)
sync-netbox --create-devices --site "Office"

# Обновить serial/model на существующих устройствах
sync-netbox --create-devices --update-devices --site "Office"

# Только добавить новые IP-адреса
sync-netbox --ip-addresses

# Только интерфейсы (без устройств)
sync-netbox --interfaces
```

## Соглашения по коду

- Типизация: `typing` для всех публичных методов
- Docstrings: Google style
- Логирование: `logging` модуль
- Паттерны: Strategy (collectors, exporters), Template Method (BaseCollector)

## Важные файлы

- `cli.py` — точка входа CLI, все команды
- `core/connection.py` — SSH подключения через Scrapli
- `collectors/base.py` — базовый класс коллекторов
- `netbox/sync.py` — синхронизация с NetBox
- `configurator/description.py` — MAC matching и push descriptions

## Запуск

```bash
# ВАЖНО: Запускать из директории /home/sa/project (не из network_collector!)
cd /home/sa/project

# Активация виртуального окружения
source network_collector/myenv/bin/activate

# Установка зависимостей
pip install -r network_collector/requirements.txt

# Запуск (модуль должен быть виден из родительской директории)
python -m network_collector --help
```

**Примечание:** Модуль `network_collector` должен запускаться из `/home/sa/project`, чтобы Python корректно разрешал импорты.
