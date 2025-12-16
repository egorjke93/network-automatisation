# Network Collector

Универсальная утилита для сбора данных с сетевых устройств и управления конфигурациями.

## Возможности

- **Сбор MAC-адресов** — таблицы MAC с нормализацией форматов
- **Сбор инвентаря** — hostname, модель, серийный номер, версия ПО
- **LLDP/CDP соседи** — топология сети
- **Интерфейсы** — статус, описание, VLAN, ошибки
- **Сопоставление MAC с хостами** — матчинг MAC-адресов с GLPI/Excel справочниками
- **Push описаний** — автоматическая установка описаний интерфейсов
- **NTC Templates** — парсинг через `ntc_templates.parse.parse_output`
- **Экспорт** — Excel, CSV, JSON
- **NetBox API** — синхронизация данных

## Архитектура

- **Scrapli** — сбор данных (SSH подключения)
- **Netmiko** — применение конфигураций (push changes)
- **NTC Templates** — парсинг вывода команд

## Установка

```bash
pip install -r requirements.txt
```

Или вручную:

```bash
pip install scrapli[ssh2] netmiko ntc-templates pandas openpyxl pynetbox
```

## Быстрый старт

### 1. Создайте файл устройств `devices_ips.py`:

```python
devices_list = [
    {"device_type": "cisco_ios", "host": "192.168.1.1"},
    {"device_type": "cisco_ios", "host": "192.168.1.2"},
    {"device_type": "qtech", "host": "192.168.1.10"},
]
```

### 2. Запустите сбор:

```bash
# Инвентарь устройств
python -m network_collector devices --format excel

# MAC-адреса в Excel
python -m network_collector mac --format excel

# LLDP соседи в CSV
python -m network_collector lldp --format csv
```

## Команды

### `devices` — Сбор инвентаря устройств

```bash
python -m network_collector devices [опции]

Опции:
  --format {excel,csv,json}  Формат вывода (default: excel)
  --transport {ssh2,system}  SSH транспорт (default: system)
```

Собирает: hostname, model, serial, version, uptime.

### `mac` — Сбор MAC-адресов

```bash
python -m network_collector mac [опции]

Опции:
  --format {excel,csv,json}  Формат вывода (default: excel)
  --with-descriptions        Собрать описания интерфейсов
  --include-trunk            Включить trunk порты
  --transport {ssh2,system}  SSH транспорт
```

### `match-mac` — Сопоставление MAC с хостами

```bash
python -m network_collector match-mac [опции]

Опции:
  --mac-file FILE           Excel файл с MAC-данными (от команды mac)
  --hosts-file FILE         Справочник хостов (GLPI export)
  --mac-column NAME         Колонка MAC в справочнике (default: MAC)
  --name-column NAME        Колонка имени хоста (default: Name)
  --output FILE             Выходной файл
  --include-unmatched       Включить несопоставленные записи
```

**Пример workflow:**

```bash
# 1. Собираем MAC-адреса
python -m network_collector mac --with-descriptions -o mac_data.xlsx

# 2. Сопоставляем с GLPI
python -m network_collector match-mac \
    --mac-file mac_data.xlsx \
    --hosts-file glpi_computers.xlsx \
    --output matched.xlsx
```

### `push-descriptions` — Применение описаний интерфейсов

```bash
python -m network_collector push-descriptions [опции]

Опции:
  --matched-file FILE       Файл сопоставления (от match-mac)
  --dry-run                 Режим симуляции (без изменений)
  --overwrite               Перезаписывать существующие описания
  --only-empty              Только для портов без описания
```

**Пример workflow:**

```bash
# 1. Сопоставляем MAC
python -m network_collector match-mac ...

# 2. Проверяем что будет изменено (dry-run)
python -m network_collector push-descriptions \
    --matched-file matched.xlsx \
    --dry-run

# 3. Применяем изменения
python -m network_collector push-descriptions \
    --matched-file matched.xlsx
```

### `lldp` — Сбор LLDP/CDP соседей

```bash
python -m network_collector lldp [опции]

Опции:
  --format {excel,csv,json}  Формат вывода
  --protocol {lldp,cdp,both} Протокол (default: lldp)
```

### `interfaces` — Сбор интерфейсов

```bash
python -m network_collector interfaces [опции]

Опции:
  --format {excel,csv,json}  Формат вывода
```

### `run` — Произвольная команда

```bash
python -m network_collector run "show version" [опции]

Опции:
  --platform PLATFORM        Платформа для NTC Templates
  --format {excel,csv,json,raw}  Формат вывода
```

### `sync-netbox` — Синхронизация с NetBox

```bash
python -m network_collector sync-netbox [опции]

Опции:
  --url URL                  URL NetBox (или env NETBOX_URL)
  --token TOKEN              API токен (или env NETBOX_TOKEN)
  --sync-all                 Полная синхронизация (все флаги в правильном порядке)
  --create-devices           Создать устройства в NetBox
  --update-devices           Обновить существующие устройства
  --interfaces               Синхронизировать интерфейсы
  --ip-addresses             Синхронизировать IP-адреса
  --cables                   Создать кабели из LLDP/CDP данных
  --vlans                    Создать VLAN из SVI интерфейсов
  --inventory                Синхронизировать модули, SFP, PSU
  --cleanup                  Удалить устройства не из списка (требует --tenant)
  --site SITE                Сайт для создаваемых устройств
  --role ROLE                Роль для создаваемых устройств
  --tenant TENANT            Tenant для --cleanup
  --protocol {lldp,cdp,both} Протокол для кабелей (default: both)
  --dry-run                  Режим симуляции
```

## Общие опции

```bash
-v, --verbose    Подробный вывод (DEBUG)
-d, --devices    Файл устройств (default: devices_ips.py)
-o, --output     Папка/файл отчётов (default: reports)
```

## Полный workflow: MAC -> Описания

```bash
# Шаг 1: Сбор MAC-адресов с описаниями интерфейсов
python -m network_collector mac \
    --with-descriptions \
    --format excel \
    -o reports/mac_table.xlsx


# Шаг 2: Сопоставление с GLPI/справочником хостов
python -m network_collector match-mac \

    --mac-file reports/mac_table.xlsx \
    --hosts-file /path/to/glpi_computers.xlsx \
    --mac-column "MAC" \
    --name-column "Name" \
    --output reports/matched.xlsx

# Шаг 3: Проверка (dry-run)
python -m network_collector push-descriptions \
    --matched-file reports/matched.xlsx \
    --dry-run

# Шаг 4: Применение описаний
python -m network_collector push-descriptions \
    --matched-file reports/matched.xlsx
```

## Структура проекта

```
network_collector/
├── __init__.py              # Экспорты модуля
├── __main__.py              # Точка входа
├── cli.py                   # CLI интерфейс
├── config.py                # Конфигурация
├── devices_ips.py           # Список устройств
├── requirements.txt         # Зависимости
│
├── core/                    # Ядро
│   ├── connection.py        # Scrapli ConnectionManager
│   ├── credentials.py       # Учётные данные
│   └── device.py            # Модель устройства
│
├── collectors/              # Сборщики данных (Scrapli)
│   ├── base.py              # Базовый класс
│   ├── device.py            # Инвентарь устройств
│   ├── mac.py               # MAC-адреса
│   ├── lldp.py              # LLDP/CDP
│   ├── interfaces.py        # Интерфейсы
│   ├── inventory.py         # Inventory (модули, SFP, PSU)
│   └── config_backup.py     # Резервное копирование
│
├── configurator/            # Применение конфигураций (Netmiko)
│   ├── base.py              # ConfigPusher
│   └── description.py       # DescriptionMatcher, DescriptionPusher
│
├── parsers/                 # Парсеры
│   └── textfsm_parser.py    # NTC Templates parser
│
├── exporters/               # Экспортеры
│   ├── excel.py             # Excel
│   ├── csv_exporter.py      # CSV
│   └── json_exporter.py     # JSON
│
├── netbox/                  # NetBox интеграция
│   ├── client.py            # API клиент (pynetbox)
│   └── sync.py              # Синхронизация
│
├── utils/                   # Утилиты
│   └── mac_matching.py      # Нормализация MAC
│
└── templates/               # Кастомные TextFSM шаблоны
```

## Поддерживаемые платформы

| Платформа | Scrapli driver | NTC platform |
|-----------|---------------|--------------|
| Cisco IOS | cisco_iosxe | cisco_ios |
| Cisco IOS-XE | cisco_iosxe | cisco_ios |
| Cisco NX-OS | cisco_nxos | cisco_nxos |
| QTech | cisco_iosxe | cisco_ios |
| Arista EOS | arista_eos | arista_eos |
| Juniper | juniper_junos | juniper_junos |

## NetBox интеграция

### Переменные окружения:

```bash
export NETBOX_URL="https://netbox.example.com"
export NETBOX_TOKEN="your-api-token"
```

### Синхронизация:

```bash
# Полная синхронизация (рекомендуемый способ)
python -m network_collector sync-netbox --sync-all --site "Main" --role "switch" --dry-run

# Создать устройства
python -m network_collector sync-netbox --create-devices --site "Main" --role "switch" --dry-run

# Синхронизировать интерфейсы
python -m network_collector sync-netbox --interfaces --dry-run

# Привязать IP-адреса
python -m network_collector sync-netbox --ip-addresses --dry-run

# Создать VLAN из SVI интерфейсов
python -m network_collector sync-netbox --vlans --site "Main" --dry-run

# Создать кабели из LLDP/CDP (топология)
python -m network_collector sync-netbox --cables --protocol both --dry-run

# Синхронизировать inventory (модули, SFP, PSU)
python -m network_collector sync-netbox --inventory --dry-run
```

### Порядок выполнения --sync-all:
1. Создание/обновление устройств
2. Синхронизация интерфейсов
3. Привязка IP-адресов
4. Создание VLAN из SVI
5. Построение топологии (кабели)
6. Синхронизация inventory
