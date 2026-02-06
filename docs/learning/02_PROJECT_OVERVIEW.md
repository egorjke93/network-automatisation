# 02. Обзор проекта Network Collector

> **Время чтения:** ~20 минут
>
> **Предыдущий документ:** [01. Python-концепции в проекте](01_PYTHON_BASICS.md)
>
> **Связанная документация:** [ARCHITECTURE.md](../ARCHITECTURE.md) -- полная архитектура

---

## 1. Зачем нужен Network Collector

### Проблема

Представь: ты сетевой инженер, и у тебя 200 коммутаторов. Руководство просит:

- "Дай список всех устройств с серийниками и версиями IOS"
- "Где подключён сервер с MAC-адресом `00:11:22:33:44:55`?"
- "Какие порты свободны на коммутаторах в офисе?"
- "Нарисуй карту соединений между свитчами"

Что ты делаешь? Заходишь на каждый коммутатор по SSH, вводишь `show version`, `show mac address-table`, `show lldp neighbors` -- и копируешь вывод в Excel. На 200 устройств это занимает пару дней. А через месяц надо повторить, потому что данные устарели.

Ещё есть NetBox -- база данных сетевой инфраструктуры, где должна быть актуальная информация. Но кто-то должен вручную вбивать туда каждый интерфейс, каждый IP-адрес, каждый кабель. Никто этого не делает, и данные в NetBox протухают на второй день.

### Решение

Network Collector автоматизирует оба процесса:

1. **Сбор данных** -- подключается ко всем устройствам по SSH, выполняет команды, парсит вывод и сохраняет в Excel/CSV/JSON.
2. **Синхронизация с NetBox** -- сравнивает собранные данные с тем, что уже есть в NetBox, и обновляет: создаёт новое, обновляет изменившееся, удаляет лишнее.

Вместо двух дней ручной работы -- одна команда в терминале:

```bash
# Собрать данные со всех устройств и сохранить в Excel
python -m network_collector devices --format excel

# Или собрать данные и сразу синхронизировать с NetBox
python -m network_collector sync-netbox --sync-all --dry-run
```

---

## 2. Что такое NetBox

**NetBox** -- это база данных сетевой инфраструктуры с веб-интерфейсом и REST API.

### Что хранит NetBox

| Объект | Пример | CLI-аналог |
|--------|--------|------------|
| Устройства (Devices) | `switch-01`, модель `C9200L-24P`, серийник `FCW12345` | `show version` |
| Интерфейсы (Interfaces) | `GigabitEthernet0/1`, тип `1000BASE-T`, статус `up` | `show interfaces status` |
| IP-адреса | `10.0.0.1/24` на интерфейсе `Vlan10` | `show ip interface brief` |
| Кабели (Cables) | `switch-01:Gi0/1` <-> `switch-02:Gi0/1` | `show lldp neighbors` |
| VLAN | VLAN 10 "Management", VLAN 20 "Users" | `show vlan brief` |
| Inventory | SFP-модуль в порту `Gi0/25`, серийник `AVD1234` | `show inventory` |

### Аналогия

Думай о NetBox как об **Excel для сетевиков, но с API и веб-интерфейсом:**

- В Excel ты создаёшь таблицу с колонками "Имя", "IP", "Модель", "Серийник" -- и вручную заполняешь.
- В NetBox то же самое, но:
  - Есть веб-интерфейс: можно смотреть и редактировать через браузер.
  - Есть REST API: можно программно читать и записывать данные.
  - Данные связаны: интерфейс привязан к устройству, IP привязан к интерфейсу, кабель связывает два интерфейса.

### Как Network Collector работает с NetBox

Network Collector общается с NetBox через его REST API:

```
Network Collector  ──HTTP запросы──>  NetBox API (https://netbox.example.com/api/)
                   <──JSON ответы──
```

Примеры запросов:
- `GET /api/dcim/devices/` -- получить список устройств
- `POST /api/dcim/interfaces/` -- создать интерфейс
- `PATCH /api/dcim/interfaces/42/` -- обновить интерфейс с ID=42
- `DELETE /api/dcim/interfaces/42/` -- удалить интерфейс

Тебе не нужно помнить эти URL -- Network Collector делает всё сам.

---

## 3. Что умеет Network Collector

### 3.1 Сбор данных с устройств

Каждая команда собирает определённый тип данных:

| Команда | Что собирает | Команды на устройстве |
|---------|-------------|----------------------|
| `devices` | Инвентаризация: имя, модель, серийник, версия ОС | `show version` |
| `mac` | Таблица MAC-адресов: MAC, порт, VLAN | `show mac address-table` |
| `lldp` | Соседи: кто подключён к какому порту | `show lldp neighbors detail` |
| `interfaces` | Интерфейсы: статус, скорость, описание, IP, VLAN | `show interfaces`, `show ip interface brief` |
| `inventory` | Модули: SFP, блоки питания, стеки | `show inventory` |
| `backup` | Резервная копия конфигурации | `show running-config` |

Примеры использования:

```bash
# Собрать MAC-адреса и сохранить в Excel
python -m network_collector mac --format excel

# Собрать LLDP-соседей и CDP-соседей одновременно
python -m network_collector lldp --protocol both

# Собрать информацию об интерфейсах в CSV
python -m network_collector interfaces --format csv

# Выполнить произвольную команду на всех устройствах
python -m network_collector run "show ip arp" --format json
```

### 3.2 Экспорт в разные форматы

Все собранные данные можно сохранить в:

| Формат | Флаг | Для кого |
|--------|------|----------|
| **Excel** (.xlsx) | `--format excel` | Отчёт руководству, удобный просмотр |
| **CSV** | `--format csv` | Импорт в другие системы, скрипты |
| **JSON** | `--format json` | Программная обработка, API |
| **Raw** | `--format raw` | Сырой вывод с устройства (для отладки) |

### 3.3 Синхронизация с NetBox

Синхронизация -- это главная "фишка" проекта. Вместо ручного ввода данных в NetBox:

```bash
# Полная синхронизация (сначала в режиме симуляции)
python -m network_collector sync-netbox --sync-all --dry-run

# Посмотрели что изменится, всё ОК -- применяем
python -m network_collector sync-netbox --sync-all

# Или по частям:
python -m network_collector sync-netbox --interfaces           # Только интерфейсы
python -m network_collector sync-netbox --ip-addresses         # Только IP-адреса
python -m network_collector sync-netbox --cables               # Только кабели
python -m network_collector sync-netbox --inventory            # Только модули (SFP, PSU)
python -m network_collector sync-netbox --vlans                # Только VLAN
```

**Что значит `--dry-run`?** Режим симуляции. Network Collector покажет, что он *собирается* сделать, но ничего не изменит в NetBox. Всегда запускай с `--dry-run` сначала!

### 3.4 Pipeline -- автоматические цепочки

Pipeline -- это набор шагов, выполняемых последовательно. Вместо запуска 5 отдельных команд:

```bash
# Без pipeline: 5 команд вручную
python -m network_collector sync-netbox --create-devices
python -m network_collector sync-netbox --interfaces
python -m network_collector sync-netbox --ip-addresses
python -m network_collector sync-netbox --cables
python -m network_collector sync-netbox --inventory

# С pipeline: одна команда
python -m network_collector pipeline run default --apply
```

Pipeline описывается в YAML-файле и хранится в папке `pipelines/`.

### 3.5 Web UI и REST API

Помимо командной строки, есть веб-интерфейс:

- **Web UI** (Vue.js) -- http://localhost:5173 -- для тех, кто предпочитает кликать мышкой
- **REST API** (FastAPI) -- http://localhost:8080/docs -- для автоматизации и интеграции

Страницы Web UI:

| Страница | Что делает |
|----------|-----------|
| `/sync` | Запуск синхронизации с NetBox |
| `/pipelines` | Управление Pipeline |
| `/history` | Журнал всех операций |
| `/device-management` | Добавить/удалить устройства |
| `/devices`, `/mac`, `/lldp` | Сбор данных |

---

## 4. Архитектура простыми словами

### Что происходит, когда ты вводишь команду

```
python -m network_collector mac --format excel
```

Вот путь данных от начала до конца:

```
  Ты вводишь команду
        │
        ▼
  CLI парсит аргументы         # "mac" → cmd_mac(), "--format excel" → args.format="excel"
        │
        ▼
  Загружаем список устройств   # Из файла devices_ips.py: [{host: "10.0.0.1", ...}, ...]
        │
        ▼
  Collector подключается       # SSH к каждому устройству через Scrapli
  по SSH к устройству          # Выполняет: "show mac address-table"
        │
        ▼
  Парсер извлекает данные      # NTC Templates: сырой текст → структурированные данные
  из текста                    # [{mac: "00:11:22:33:44:55", interface: "Gi0/1", vlan: 10}, ...]
        │
        ▼
  Normalizer приводит          # Стандартизация: разные форматы MAC → единый формат
  к единому формату            # Имена интерфейсов: "Gi0/1" → "GigabitEthernet0/1"
        │
        ▼
  Exporter сохраняет           # Excel → mac_addresses_20250115.xlsx
  в нужный формат              # CSV → mac_addresses_20250115.csv
```

### Аналогия: конвейер на заводе

Представь конвейер по производству деталей:

1. **Заказ** (CLI) -- клиент говорит, что нужно ("хочу MAC-таблицу в Excel").
2. **Сбор сырья** (Collector) -- грузовик едет на склад (SSH к устройству) и привозит сырьё (текстовый вывод команды).
3. **Обработка** (Parser + Normalizer) -- сырьё режут, шлифуют, приводят к стандартному размеру (парсинг текста, нормализация данных).
4. **Упаковка** (Exporter) -- готовые детали упаковывают в коробку нужного формата (Excel, CSV, JSON).

Каждый этап делает одну вещь и передаёт результат дальше. Это называется **разделение ответственности** (separation of concerns) -- ключевой принцип архитектуры проекта.

---

## 5. Слои системы

Network Collector разделён на слои. Каждый слой отвечает за свою задачу:

```
┌─────────────────────────────────────────────────────┐
│              Presentation (CLI, Web)                 │  ← Принимает запрос
├─────────────────────────────────────────────────────┤
│              Collection (Collectors)                 │  ← Собирает данные
├─────────────────────────────────────────────────────┤
│              Domain (Normalizers, Comparators)       │  ← Обрабатывает
├─────────────────────────────────────────────────────┤
│              Export / Sync                           │  ← Отдаёт результат
├─────────────────────────────────────────────────────┤
│              Core (SSH, Models, Config)              │  ← Фундамент
└─────────────────────────────────────────────────────┘
```

### Presentation -- кассир в магазине

**Что делает:** принимает запрос от пользователя и вызывает нужные компоненты.

**Аналогия:** кассир в магазине -- ты говоришь "мне бигмак и колу", кассир передаёт заказ на кухню. Кассир не готовит еду сам.

**Файлы:**
- `cli/` -- команды в терминале
- `api/` -- HTTP-эндпоинты (FastAPI)
- `frontend/` -- веб-интерфейс (Vue.js)

**Пример:** когда ты набираешь `python -m network_collector mac --format excel`, CLI-слой:
1. Парсит аргументы (команда `mac`, формат `excel`).
2. Вызывает функцию `cmd_mac(args)`.
3. Та уже вызывает Collector и Exporter.

### Collection -- курьер

**Что делает:** подключается к устройствам по SSH, выполняет команды, парсит вывод.

**Аналогия:** курьер -- ездит по точкам (устройствам), забирает товар (данные) и привозит обратно.

**Файлы:**
- `collectors/mac.py` -- сбор MAC-таблиц
- `collectors/lldp.py` -- сбор LLDP/CDP-соседей
- `collectors/interfaces.py` -- сбор интерфейсов
- `collectors/inventory.py` -- сбор inventory (модули, SFP)
- `collectors/device.py` -- сбор инвентаризации (show version)
- `collectors/base.py` -- базовый класс (общая логика для всех)

### Domain -- лаборатория

**Что делает:** нормализует данные (приводит к единому формату), сравнивает (что изменилось?), валидирует (правильные ли данные?).

**Аналогия:** лаборатория контроля качества -- проверяет каждую деталь, измеряет, сравнивает с эталоном.

**Файлы:**
- `core/domain/mac.py` -- нормализация MAC-адресов
- `core/domain/lldp.py` -- нормализация LLDP-данных
- `core/domain/interface.py` -- нормализация интерфейсов
- `core/domain/sync.py` -- `SyncComparator` -- сравнение "что на устройстве" vs "что в NetBox"

**Пример работы SyncComparator:**
```
На устройстве:   [Gi0/1, Gi0/2, Gi0/3, Gi0/4]
В NetBox:        [Gi0/1, Gi0/2, Gi0/5]

Результат сравнения:
  to_create: [Gi0/3, Gi0/4]   ← Есть на устройстве, нет в NetBox
  to_update: [Gi0/1, Gi0/2]   ← Есть и там и там, проверить diff
  to_delete: [Gi0/5]          ← Есть в NetBox, нет на устройстве
```

### Export / Sync -- склад и доставка

**Что делает:**
- **Export** -- сохраняет данные в файл (Excel, CSV, JSON).
- **Sync** -- отправляет данные в NetBox через API.

**Аналогия:** склад (Export) -- складываем на полку в нужной упаковке. Доставка (Sync) -- отправляем клиенту.

**Файлы:**
- `exporters/excel.py` -- экспорт в Excel
- `exporters/csv_exporter.py` -- экспорт в CSV
- `exporters/json_exporter.py` -- экспорт в JSON
- `netbox/sync/interfaces.py` -- синхронизация интерфейсов
- `netbox/sync/ip_addresses.py` -- синхронизация IP-адресов
- `netbox/sync/cables.py` -- синхронизация кабелей
- `netbox/sync/inventory.py` -- синхронизация inventory
- `netbox/client/` -- HTTP-клиент для NetBox API (обёртка над запросами)

### Core -- фундамент

**Что делает:** базовые вещи, которые нужны всем остальным слоям.

**Аналогия:** фундамент здания -- его не видно, но без него ничего не стоит.

**Файлы:**
- `core/connection.py` -- SSH-подключения (через Scrapli)
- `core/device.py` -- модель устройства (`Device`)
- `core/models.py` -- модели данных (`Interface`, `MACEntry`, `LLDPNeighbor`, `IPAddressEntry`)
- `core/credentials.py` -- учётные данные (логин/пароль)
- `config.yaml` -- настройки приложения
- `fields.yaml` -- какие поля собирать и как называть

---

## 6. Структура папок

```
network_collector/
│
├── __main__.py              # Точка входа: python -m network_collector
├── __init__.py              # Инициализация пакета
│
├── cli/                     # Команды CLI (что ты набираешь в терминале)
│   ├── __init__.py          #   main() и setup_parser() -- точка входа CLI
│   ├── utils.py             #   Общие утилиты: загрузка устройств, credentials
│   └── commands/            #   Каждая команда -- отдельный файл
│       ├── collect.py       #     cmd_devices, cmd_mac, cmd_lldp, cmd_interfaces, cmd_inventory
│       ├── sync.py          #     cmd_sync_netbox -- синхронизация с NetBox
│       ├── backup.py        #     cmd_backup (конфигурации), cmd_run (произвольная команда)
│       ├── pipeline.py      #     cmd_pipeline -- управление pipeline
│       ├── match.py         #     cmd_match_mac -- сопоставление MAC с хостами
│       ├── push.py          #     cmd_push_descriptions -- применение описаний
│       └── validate.py      #     cmd_validate_fields -- валидация fields.yaml
│
├── collectors/              # Сбор данных с устройств по SSH
│   ├── base.py              #   BaseCollector -- общая логика для всех
│   ├── device.py            #   DeviceInventoryCollector (show version)
│   ├── mac.py               #   MACCollector (show mac address-table)
│   ├── lldp.py              #   LLDPCollector (show lldp neighbors)
│   ├── interfaces.py        #   InterfaceCollector (show interfaces)
│   ├── inventory.py         #   InventoryCollector (show inventory)
│   └── config_backup.py     #   ConfigBackupCollector (show running-config)
│
├── core/                    # Ядро: модели, подключения, конфиг
│   ├── models.py            #   Модели данных: Interface, MACEntry, LLDPNeighbor и др.
│   ├── device.py            #   Модель устройства: Device (host, platform, device_type)
│   ├── connection.py        #   SSH-подключения через Scrapli
│   ├── credentials.py       #   Загрузка логина/пароля
│   ├── exceptions.py        #   Классы ошибок (ConnectionError, TimeoutError и др.)
│   ├── context.py           #   RunContext -- контекст выполнения (dry_run, run_id)
│   ├── field_registry.py    #   Реестр полей для экспорта
│   ├── logging.py           #   Настройка логирования
│   ├── domain/              #   Бизнес-логика: нормализация, сравнение
│   │   ├── sync.py          #     SyncComparator -- сравнение данных с NetBox
│   │   ├── interface.py     #     Нормализация интерфейсов
│   │   ├── lldp.py          #     Нормализация LLDP-данных
│   │   ├── mac.py           #     Нормализация MAC-адресов
│   │   ├── inventory.py     #     Нормализация inventory
│   │   └── vlan.py          #     Работа с VLAN
│   ├── pipeline/            #   Система pipeline (автоматизация)
│   │   ├── models.py        #     Модели: Pipeline, PipelineStep
│   │   └── executor.py      #     PipelineExecutor -- выполнение шагов
│   └── constants/           #   Маппинги: платформы, команды, типы интерфейсов
│
├── parsers/                 # Парсинг текстового вывода устройств
│   └── textfsm_parser.py    #   NTC Templates: текст → структурированные данные
│
├── netbox/                  # Всё для работы с NetBox
│   ├── client/              #   HTTP-клиент для NetBox API
│   │   ├── base.py          #     Базовый HTTP-клиент (GET, POST, PATCH, DELETE)
│   │   ├── main.py          #     NetBoxClient -- главный класс (собирает mixin-ы)
│   │   ├── dcim.py          #     Устройства, интерфейсы, кабели
│   │   ├── interfaces.py    #     Операции с интерфейсами
│   │   ├── ip_addresses.py  #     Операции с IP-адресами
│   │   ├── inventory.py     #     Операции с inventory
│   │   ├── devices.py       #     Операции с устройствами
│   │   └── vlans.py         #     Операции с VLAN
│   ├── sync/                #   Логика синхронизации (что создать, обновить, удалить)
│   │   ├── base.py          #     BaseSyncMixin -- общая логика sync
│   │   ├── main.py          #     NetBoxSync -- главный класс (собирает mixin-ы)
│   │   ├── interfaces.py    #     Синхронизация интерфейсов
│   │   ├── ip_addresses.py  #     Синхронизация IP-адресов
│   │   ├── cables.py        #     Синхронизация кабелей
│   │   ├── inventory.py     #     Синхронизация inventory
│   │   ├── devices.py       #     Синхронизация устройств
│   │   └── vlans.py         #     Синхронизация VLAN
│   ├── diff.py              #   DiffCalculator -- показ различий
│   └── client.py            #   Обратная совместимость
│
├── exporters/               # Экспорт в файлы
│   ├── base.py              #   BaseExporter -- общий интерфейс
│   ├── excel.py             #   ExcelExporter → .xlsx
│   ├── csv_exporter.py      #   CSVExporter → .csv
│   ├── json_exporter.py     #   JSONExporter → .json
│   └── raw_exporter.py      #   RawExporter → stdout (вывод в терминал)
│
├── configurator/            # Работа с конфигурациями устройств
│
├── api/                     # Web API (FastAPI)
│   ├── main.py              #   Приложение FastAPI
│   ├── routes/              #   HTTP-эндпоинты (devices, sync, pipelines, history)
│   ├── services/            #   Сервисы (sync_service, task_manager)
│   └── schemas/             #   Pydantic-схемы для валидации запросов
│
├── frontend/                # Web интерфейс (Vue.js)
│   └── src/views/           #   Страницы: Sync.vue, Pipelines.vue, History.vue и др.
│
├── pipelines/               # YAML-файлы с описанием pipeline
│
├── templates/               # Шаблоны (NTC Templates для нестандартных платформ)
│
├── data/                    # Данные: devices.json, history.json
│
├── config.yaml              # Настройки приложения (таймауты, NetBox URL, форматы)
├── fields.yaml              # Какие поля собирать и как называть в экспорте
├── devices_ips.py           # Список устройств (host, platform, device_type)
│
└── tests/                   # Тесты (1538 штук!)
    ├── conftest.py          #   Общие fixtures для pytest
    ├── test_cli/            #   Тесты CLI
    ├── test_collectors/     #   Тесты коллекторов
    ├── test_core/           #   Тесты ядра
    ├── test_netbox/         #   Тесты NetBox sync
    ├── test_exporters/      #   Тесты экспортёров
    └── test_parsers/        #   Тесты парсеров
```

### На что обратить внимание

- **Каждая папка -- отдельный слой.** `collectors/` не знает про `exporters/`, `exporters/` не знает про `netbox/`. Они общаются через данные (модели из `core/models.py`).
- **Внутри каждого слоя -- файл на каждый тип данных.** Интерфейсы? `collectors/interfaces.py` + `netbox/sync/interfaces.py`. MAC? `collectors/mac.py`. Паттерн повторяется.
- **`core/` -- зависимость для всех.** Модели, подключения, конфиг -- это используется везде.

---

## 7. Быстрый старт

### Предварительные условия

- Доступ к сетевым устройствам по SSH (логин/пароль или ключи).
- Файл `devices_ips.py` с перечнем устройств.
- (Для синхронизации) Работающий NetBox с API-токеном.

### Запуск

```bash
# ВАЖНО: Запускать из /home/sa/project (не из network_collector!)
cd /home/sa/project
source network_collector/myenv/bin/activate

# Справка -- список всех команд
python -m network_collector --help

# Собрать инвентаризацию устройств в Excel
python -m network_collector devices --format excel

# Собрать MAC-таблицы в Excel
python -m network_collector mac --format excel

# Собрать LLDP/CDP соседей
python -m network_collector lldp --protocol both --format excel

# Посмотреть что изменится в NetBox (без применения)
python -m network_collector sync-netbox --interfaces --dry-run

# Запустить pipeline (полная синхронизация)
python -m network_collector pipeline run default --apply
```

### Конфигурация

Два главных файла:

**`config.yaml`** -- настройки приложения:
```yaml
# Подключение к NetBox
netbox:
  url: "https://netbox.example.com"
  token: "ваш-api-токен"

# Таймауты SSH
connection:
  conn_timeout: 10
  read_timeout: 30

# Формат вывода
output:
  default_format: "excel"
  mac_format: "ieee"
```

**`fields.yaml`** -- какие поля собирать и как их называть:
```yaml
# Пример для LLDP
lldp:
  hostname:
    enabled: true
    name: "Device"       # Название колонки в Excel
    order: 1             # Порядок (левее = меньше)
  remote_hostname:
    enabled: true
    name: "Neighbor"
    order: 4
```

---

## 8. Что читать дальше

Теперь ты знаешь, зачем нужен проект, что он умеет, и как организован. Следующие документы раскрывают каждый слой подробно:

| # | Документ | Что узнаешь |
|---|----------|-------------|
| 03 | [CLI изнутри](03_CLI_INTERNALS.md) | Как работают команды CLI: от ввода до результата |
| 04 | Модели данных | Dataclass-модели: Interface, MACEntry, зачем они вместо словарей |
| 05 | NetBox Sync | Как данные синхронизируются с NetBox, batch-операции, dry_run |
| 06 | Pipeline | Цепочки операций: collect -> sync -> cleanup |

Также полезно:
- [ARCHITECTURE.md](../ARCHITECTURE.md) -- полная техническая архитектура (для тех, кто хочет все детали)
- [MANUAL.md](../MANUAL.md) -- полное руководство по использованию (CLI, Web UI, API)
- [PLATFORM_GUIDE.md](../PLATFORM_GUIDE.md) -- как добавить поддержку новой платформы (Cisco, Arista, Juniper, QTech)
