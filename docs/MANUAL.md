# Network Collector - Полное руководство

Полное руководство пользователя по всем командам, настройкам и опциям.

## Содержание

1. [Установка и настройка](#1-установка-и-настройка)
2. [Конфигурация](#2-конфигурация)
3. [Команды CLI](#3-команды-cli)
4. [Синхронизация с NetBox](#4-синхронизация-с-netbox)
5. [Pipeline (конвейеры)](#5-pipeline-конвейеры)
6. [Web интерфейс](#6-web-интерфейс)
7. [REST API](#7-rest-api)
8. [Фильтры и исключения](#8-фильтры-и-исключения)
9. [Безопасность](#9-безопасность)
10. [Примеры использования](#10-примеры-использования)
11. [Устранение неполадок](#11-устранение-неполадок)

---

## 1. Установка и настройка

### 1.1 Требования

- Python 3.10+
- SSH доступ к сетевым устройствам
- NetBox 4.x (для синхронизации)

### 1.2 Установка

```bash
cd /home/sa/project
source network_collector/myenv/bin/activate
pip install -r network_collector/requirements.txt
```

### 1.3 Настройка устройств

Создайте файл `devices_ips.py`:

```python
devices_list = [
    # Новый формат (рекомендуется)
    {"host": "192.168.1.1", "platform": "cisco_iosxe"},
    {"host": "192.168.1.2", "platform": "cisco_iosxe", "device_type": "C9200L-24P-4X"},
    {"host": "192.168.1.3", "platform": "arista_eos", "role": "switch"},

    # Старый формат (совместимость)
    {"host": "192.168.1.4", "device_type": "cisco_ios"},
]
```

**Поля:**

| Поле | Описание | Обязательный |
|------|----------|--------------|
| `host` | IP-адрес устройства | Да |
| `platform` | Драйвер SSH (cisco_iosxe, arista_eos, etc.) | Да* |
| `device_type` | Модель для NetBox (C9200L-24P-4X) | Нет |
| `role` | Роль устройства для NetBox | Нет |
| `tenant` | Арендатор для NetBox | Нет |

*Если не указан `platform`, используется `device_type` как драйвер.

### 1.4 Поддерживаемые платформы

| Платформа | platform | Описание |
|-----------|----------|----------|
| Cisco IOS | `cisco_ios` | IOS классический |
| Cisco IOS-XE | `cisco_iosxe` | IOS-XE (C9xxx, ISR4xxx) |
| Cisco NX-OS | `cisco_nxos` | Nexus |
| Cisco IOS-XR | `cisco_iosxr` | IOS-XR (ASR9000) |
| Arista EOS | `arista_eos` | Arista |
| Juniper JunOS | `juniper_junos` | Juniper |
| QTech | `qtech`, `qtech_qsw` | QTech |

### 1.5 Учётные данные

**Переменные окружения (рекомендуется):**

```bash
export NET_USERNAME="admin"
export NET_PASSWORD="password"
export NETBOX_URL="https://netbox.example.com"
export NETBOX_TOKEN="your-api-token"
```

**Или config.yaml:**

```yaml
credentials:
  username: admin
  password: password

netbox:
  url: https://netbox.example.com
  token: your-api-token
```

---

## 2. Конфигурация

### 2.1 config.yaml — Настройки приложения

```yaml
# Вывод
output:
  output_folder: "reports"      # Папка для отчётов
  default_format: "excel"       # excel, csv, json, raw
  mac_format: "ieee"            # ieee, cisco, netbox, raw

# SSH подключение
connection:
  conn_timeout: 10              # Таймаут подключения (сек)
  read_timeout: 30              # Таймаут чтения (сек)
  max_workers: 5                # Параллельные подключения

# NetBox API
netbox:
  url: "http://localhost:8000/"
  token: ""                     # Лучше через NETBOX_TOKEN
  verify_ssl: true

# Фильтры для MAC коллектора
filters:
  exclude_vlans: [1, 4094]      # Исключить VLAN
  exclude_interfaces:           # Исключить интерфейсы (regex)
    - "^Po\\d+"
    - "^Vlan\\d+"
    - "^Loopback"

# MAC коллектор
mac:
  collect_descriptions: true    # Собирать descriptions
  collect_trunk_ports: false    # Включать trunk порты
  collect_port_security: false  # Собирать sticky MAC

# Логирование
logging:
  level: "INFO"                 # DEBUG, INFO, WARNING, ERROR
  json_format: false            # JSON формат в консоль
  file_path: ""                 # Путь к лог-файлу
  max_bytes: 10485760           # Макс. размер (10MB)
  backup_count: 5               # Кол-во ротируемых файлов
```

### 2.2 fields.yaml — Поля экспорта и синхронизации

**Экспорт (mac, devices, lldp, interfaces, inventory):**

```yaml
mac:
  hostname:
    enabled: true               # Включить в экспорт
    name: "Device"              # Имя колонки
    order: 1                    # Порядок (меньше = левее)
    default: null               # Значение по умолчанию
  interface:
    enabled: true
    name: "Port"
    order: 2
  vlan:
    enabled: false              # НЕ включать в экспорт
```

**Синхронизация с NetBox:**

```yaml
sync:
  devices:
    fields:
      name:
        enabled: true
        source: hostname        # Откуда брать данные
    defaults:
      site: "Main"
      role: "switch"
    options:
      create_missing: true
      update_existing: true

  interfaces:
    fields:
      enabled:
        enabled: true
        source: status
      description:
        enabled: true
        source: description
    defaults:
      type: "1000base-t"
    options:
      auto_detect_type: true
      exclude_interfaces:       # Исключить из синхронизации
        - "^Vlan1$"
        - "^Null\\d+"
      sync_mac_only_with_ip: true  # MAC только на L3 интерфейсы
```

---

## 3. Команды CLI

### 3.1 Общие опции

```bash
python -m network_collector [команда] [опции]

# Общие опции (для всех команд):
  -v, --verbose              Подробный вывод (DEBUG)
  -d, --devices FILE         Файл устройств (default: devices_ips.py)
  -o, --output PATH          Папка/файл отчётов (default: reports)
  --transport {ssh2,system}  SSH транспорт (default: system)
```

**Форматы вывода (`--format`):**

| Формат | Описание | Вывод |
|--------|----------|-------|
| `excel` | Excel файл с форматированием | `reports/имя.xlsx` |
| `csv` | CSV файл | `reports/имя.csv` |
| `json` | JSON с метаданными | `reports/имя.json` |
| `raw` | JSON в stdout (для pipeline) | stdout |

**Пример использования raw:**
```bash
# JSON в консоль (без сохранения в файл)
python -m network_collector devices --format raw

# Pipeline с jq
python -m network_collector devices --format raw | jq '.[].hostname'

# Сохранить raw JSON в файл
python -m network_collector mac --format raw > mac_data.json
```

### 3.2 devices — Инвентаризация устройств

```bash
python -m network_collector devices [опции]

Опции:
  --format {excel,csv,json,raw}  Формат вывода (default: excel)

Собирает:
  - hostname, model, serial, version, uptime
```

**Примеры:**

```bash
# Excel отчёт
python -m network_collector devices --format excel

# CSV с указанием файла
python -m network_collector devices --format csv -o devices.csv
```

### 3.3 mac — Сбор MAC-адресов

```bash
python -m network_collector mac [опции]

Опции:
  --format {excel,csv,json,raw}  Формат вывода (default: excel)
  --with-descriptions        Собрать описания интерфейсов
  --with-port-security       Собрать sticky MAC (offline устройства)
  --include-trunk            Включить trunk порты (по умолчанию исключены)
  --exclude-trunk            Исключить trunk порты (по умолчанию)

Собирает:
  - hostname, interface, mac, vlan, type, description
```

**Примеры:**

```bash
# Базовый сбор MAC
python -m network_collector mac --format excel

# С описаниями и включая trunk порты
python -m network_collector mac --with-descriptions --include-trunk

# Со sticky MAC для offline устройств
python -m network_collector mac --with-port-security
```

### 3.4 lldp — Сбор LLDP/CDP соседей

```bash
python -m network_collector lldp [опции]

Опции:
  --format {excel,csv,json,raw}    Формат вывода
  --protocol {lldp,cdp,both}   Протокол (default: lldp)

Собирает:
  - hostname, local_interface, remote_hostname, remote_port,
    remote_platform, remote_ip, protocol, neighbor_type
```

**Примеры:**

```bash
# Только LLDP
python -m network_collector lldp --protocol lldp

# Только CDP
python -m network_collector lldp --protocol cdp

# Оба протокола (объединённые данные)
python -m network_collector lldp --protocol both
```

**Protocol field:**
- `LLDP` — запись только из LLDP
- `CDP` — запись только из CDP
- `BOTH` — запись объединена из LLDP и CDP

### 3.5 interfaces — Сбор интерфейсов

```bash
python -m network_collector interfaces [опции]

Опции:
  --format {excel,csv,json,raw}  Формат вывода

Собирает:
  - hostname, interface, status, description, ip_address, mac,
    speed, duplex, mtu, mode, port_type, lag_group
```

### 3.6 inventory — Сбор модулей/SFP

```bash
python -m network_collector inventory [опции]

Опции:
  --format {excel,csv,json,raw}  Формат вывода

Собирает:
  - hostname, name, pid, serial, description, slot
```

### 3.7 backup — Резервное копирование

```bash
python -m network_collector backup [опции]

Опции:
  --output DIR               Директория для бэкапов (default: backups)

Сохраняет:
  - running-config каждого устройства в отдельный файл
```

### 3.8 run — Произвольная команда

```bash
python -m network_collector run "команда" [опции]

Опции:
  --format {excel,csv,json,raw}  Формат вывода
  --platform PLATFORM            Платформа для NTC Templates

Примеры:
  python -m network_collector run "show version" --format json
  python -m network_collector run "show ip route" --format csv
```

### 3.9 match-mac — Сопоставление MAC с хостами

```bash
python -m network_collector match-mac [опции]

Опции:
  --mac-file FILE            Excel файл с MAC-данными (от команды mac)
  --hosts-file FILE          Справочник хостов (GLPI export)
  --mac-column NAME          Колонка MAC в справочнике (default: MAC)
  --name-column NAME         Колонка имени хоста (default: Name)
  --output FILE              Выходной файл
  --include-unmatched        Включить несопоставленные записи
```

**Workflow:**

```bash
# 1. Собираем MAC-адреса
python -m network_collector mac --with-descriptions -o mac_data.xlsx

# 2. Сопоставляем с GLPI
python -m network_collector match-mac \
    --mac-file mac_data.xlsx \
    --hosts-file glpi_computers.xlsx \
    --output matched.xlsx
```

### 3.10 push-descriptions — Применение описаний

```bash
python -m network_collector push-descriptions [опции]

Опции:
  --matched-file FILE        Файл сопоставления (от match-mac) [обязательный]
  --only-empty               Применять только на порты без описания
  --overwrite                Перезаписывать существующие описания
  --apply                    Реально применить (без флага = dry-run)

Формат входного файла (matched.xlsx):
  - Device (или IP) — hostname/IP устройства
  - Interface — имя интерфейса
  - Host_Name — новое описание
  - Current_Description — текущее описание
  - Matched — "Yes" для применения
```

**Примеры:**

```bash
# Показать что будет изменено (dry-run)
python -m network_collector push-descriptions --matched-file matched.xlsx

# Применить только на пустые порты
python -m network_collector push-descriptions --matched-file matched.xlsx --only-empty --apply

# Перезаписать все описания
python -m network_collector push-descriptions --matched-file matched.xlsx --overwrite --apply
```

---

## 4. Синхронизация с NetBox

### 4.1 Команда sync-netbox

```bash
python -m network_collector sync-netbox [опции]

# Основные флаги синхронизации:
  --sync-all                 Полная синхронизация (все флаги)
  --create-devices           Создать устройства
  --update-devices           Обновить существующие устройства
  --interfaces               Синхронизировать интерфейсы
  --ip-addresses             Синхронизировать IP-адреса
  --vlans                    Создать VLAN из SVI
  --cables                   Создать кабели из LLDP/CDP
  --inventory                Синхронизировать модули/SFP
  --cleanup                  Удалить устройства не из списка

# Флаги удаления (cleanup):
  --cleanup-interfaces       Удалить интерфейсы которых нет на устройстве
  --cleanup-ips              Удалить IP-адреса которых нет на устройстве
  --cleanup-cables           Удалить кабели которых нет в LLDP/CDP
  --update-ips               Обновить существующие IP-адреса

# Параметры:
  --site SITE                Сайт для создаваемых устройств
  --role ROLE                Роль для создаваемых устройств
  --tenant TENANT            Tenant (обязателен для --cleanup)
  --protocol {lldp,cdp,both} Протокол для кабелей (default: both)

# Режимы:
  --dry-run                  Режим симуляции (без изменений)
  --show-diff                Показать детальный diff изменений
```

### 4.2 Полная матрица CRUD операций

#### Сводная таблица

| Сущность | CREATE | READ | UPDATE | DELETE |
|----------|--------|------|--------|--------|
| **Device** | `--create-devices` | Всегда | `--update-devices` | `--cleanup --tenant` |
| **Interface** | `--interfaces` | Всегда | `--interfaces` | `--cleanup-interfaces` |
| **IP Address** | `--ip-addresses` | Всегда | `--update-ips` | `--cleanup-ips` |
| **Cable** | `--cables` | Проверка наличия | ❌ Нет | `--cleanup-cables` |
| **VLAN** | `--vlans` | Проверка наличия | ❌ Нет | ❌ Нет |
| **Inventory** | `--inventory` | Всегда | `--inventory` (автоматически) | ❌ Нет |

#### Детальный расклад по сущностям

##### Devices (устройства)

| Операция | Флаг | Что делает | Поля |
|----------|------|------------|------|
| **CREATE** | `--create-devices` | Создаёт новое устройство | name, device_type, site, role, serial, platform, tenant |
| **UPDATE** | `--update-devices` | Обновляет существующее | serial, device_type, site, role, platform, tenant |
| **DELETE** | `--cleanup` | Удаляет устройства не из devices_ips.py | Требует `--tenant` |

```bash
# Только CREATE
sync-netbox --create-devices --site Office
# Существующие устройства → SKIP

# CREATE + UPDATE
sync-netbox --create-devices --update-devices --site Office
# Новые → CREATE, существующие → UPDATE
```

##### Interfaces (интерфейсы)

| Операция | Условие | Поля |
|----------|---------|------|
| **CREATE** | Интерфейс не существует | name, type, enabled, description, mode, mtu, speed, lag |
| **UPDATE** | Интерфейс существует + `update_existing: true` в fields.yaml | description, enabled, type, mode, mtu, speed, lag |
| **DELETE** | `--cleanup-interfaces` | Удаляет интерфейсы которых нет на устройстве |

**Что обновляется (fields.yaml):**
```yaml
sync:
  interfaces:
    fields:
      description: true   # Обновлять описание
      enabled: true       # Обновлять статус up/down
      mac_address: true   # Синхронизировать MAC
      mtu: true           # Обновлять MTU
      speed: true         # Обновлять скорость
      duplex: true        # Обновлять duplex
      mode: true          # 802.1Q mode (access/tagged)
    options:
      update_existing: true    # ← Включает UPDATE
      auto_detect_type: true   # Автоопределение типа
```

##### IP Addresses

| Операция | Флаг | Что делает |
|----------|------|------------|
| **CREATE** | `--ip-addresses` | Создаёт новые IP, привязывает к интерфейсу |
| **UPDATE** | `--update-ips` | Обновляет tenant, description, привязку |
| **DELETE** | `--cleanup-ips` | Удаляет IP которых нет на устройстве |

```bash
# Только CREATE
sync-netbox --ip-addresses
# Новые IP → CREATE, существующие → SKIP

# CREATE + UPDATE
sync-netbox --ip-addresses --update-ips
# Новые IP → CREATE, существующие → UPDATE (tenant, description)

# CREATE + UPDATE + DELETE
sync-netbox --ip-addresses --update-ips --cleanup-ips
# Удаляет IP которых нет на устройстве
```

**При CREATE IP-адреса:**
- tenant → берётся от устройства
- description → берётся от интерфейса
- assigned_object → привязка к интерфейсу

##### Cables (кабели)

| Операция | Условие | Результат |
|----------|---------|-----------|
| **CREATE** | Оба интерфейса без кабеля | Создаётся кабель |
| **UPDATE** | ❌ Не реализовано | — |
| **DELETE** | `--cleanup-cables` | Удаляет кабели которых нет в LLDP/CDP |
| **SKIP** | Интерфейс уже имеет кабель | Пропуск |
| **SKIP** | LAG интерфейс | Пропуск (кабели на LAG не поддерживаются) |

```bash
sync-netbox --cables --protocol both  # LLDP + CDP
sync-netbox --cables --protocol lldp  # Только LLDP
sync-netbox --cables --protocol cdp   # Только CDP

# С удалением устаревших кабелей
sync-netbox --cables --cleanup-cables --dry-run
```

##### VLAN

| Операция | Условие | Источник данных |
|----------|---------|-----------------|
| **CREATE** | VLAN не существует | SVI интерфейсы (Vlan10 → VLAN 10) |
| **UPDATE** | ❌ Не реализовано | — |
| **DELETE** | ❌ Не реализовано | — |

**Имя VLAN:** берётся из description интерфейса Vlan<N>, иначе "VLAN <N>"

##### Inventory Items

| Операция | Условие | Поля |
|----------|---------|------|
| **CREATE** | Компонент не существует | name, part_id, serial, description |
| **UPDATE** | Компонент существует + поля отличаются | part_id, serial, description |
| **DELETE** | ❌ Не реализовано | — |
| **SKIP** | Нет серийного номера | Пропуск |

### 4.3 Флаг --update-devices детально

**Работает с:** `--create-devices`, `--interfaces`, `--ip-addresses`

| С флагом | Влияет на | Поведение |
|----------|-----------|-----------|
| `--create-devices` | Устройства | Обновляет serial, model, site, role, tenant, platform |
| `--interfaces` | Интерфейсы | Включает update_existing (из fields.yaml) |
| `--ip-addresses` | IP-адреса | Обновляет tenant, description, привязку |

**Без --update-devices:**
```bash
sync-netbox --create-devices --site Office
# Существующее устройство → SKIP (не трогаем)
```

**С --update-devices:**
```bash
sync-netbox --create-devices --update-devices --site Office
# Существующее устройство → UPDATE:
#   serial: "" → "FDO123456"
#   model: "Unknown" → "C9200L-24P-4X"
#   site: "Old" → "Office"
#   role: "switch" → "router" (если указано в devices_ips.py)
```

### 4.4 Флаг --cleanup (DELETE устройств)

**Требует:** `--tenant` (обязательно для безопасности)

```bash
# ❌ Ошибка — tenant не указан
sync-netbox --cleanup

# ✅ Правильно — удаляет только устройства tenant="MyCompany"
sync-netbox --cleanup --tenant "MyCompany" --dry-run
```

**Логика удаления:**
1. Получаем все устройства из devices_ips.py → `inventory_names`
2. Получаем устройства из NetBox с фильтром `site + tenant`
3. Удаляем устройства которых **нет** в `inventory_names`

**Защита:** Удаляются ТОЛЬКО устройства указанного tenant. Устройства других tenant не затрагиваются.

### 4.5 Приоритет role

Role берётся в порядке:

1. **devices_ips.py** (для конкретного устройства) — высший приоритет
2. **CLI параметр** `--role` — дефолт для устройств без роли

```python
# devices_ips.py
devices_list = [
    {"host": "10.0.0.1", "platform": "cisco_ios", "role": "router"},  # → router
    {"host": "10.0.0.2", "platform": "cisco_ios"},                     # → switch (из CLI)
]
```

```bash
sync-netbox --create-devices --role switch
# 10.0.0.1 → router (из devices_ips.py)
# 10.0.0.2 → switch (из CLI)
```

### 4.6 Primary IP

Primary IP устанавливается **только** при использовании `--ip-addresses`:

```bash
# НЕ устанавливает primary IP
sync-netbox --create-devices --update-devices

# Устанавливает primary IP
sync-netbox --ip-addresses
```

### 4.7 Что НЕ реализовано (можно добавить)

| Функция | Статус | Описание |
|---------|--------|----------|
| UPDATE кабелей | ❌ | Обновление типа кабеля |
| UPDATE VLAN | ❌ | Обновление имени VLAN |
| DELETE VLAN | ❌ | Удаление неиспользуемых VLAN |
| DELETE Inventory | ❌ | Удаление модулей которых нет на устройстве |
| Sync untagged/tagged VLANs | ❌ | Привязка VLAN к интерфейсам |

**Реализовано:**
- ✅ `--cleanup-interfaces` — удаление интерфейсов которых нет на устройстве
- ✅ `--cleanup-ips` — удаление IP-адресов которых нет на устройстве
- ✅ `--cleanup-cables` — удаление кабелей при изменении топологии
- ✅ `--update-ips` — обновление существующих IP-адресов

### 4.8 Порядок выполнения --sync-all

```
1. sync_devices          → Создание/обновление устройств
2. sync_interfaces       → Синхронизация интерфейсов
3. sync_ip_addresses     → Привязка IP-адресов + primary IP
4. sync_vlans            → Создание VLAN из SVI
5. sync_cables           → Построение топологии (LLDP/CDP)
6. sync_inventory        → Синхронизация модулей/SFP
7. cleanup (если --cleanup) → Удаление устаревших устройств
```

### 4.9 Примеры синхронизации

```bash
# Первая синхронизация (dry-run)
python -m network_collector sync-netbox --sync-all \
    --site "Office" --role "switch" --dry-run

# Создать только устройства
python -m network_collector sync-netbox --create-devices \
    --site "Office" --role "switch"

# Обновить существующие устройства
python -m network_collector sync-netbox --create-devices --update-devices \
    --site "Office"

# Только интерфейсы
python -m network_collector sync-netbox --interfaces

# Только IP-адреса (с установкой primary IP)
python -m network_collector sync-netbox --ip-addresses

# Кабели из обоих протоколов
python -m network_collector sync-netbox --cables --protocol both

# Удаление устаревших устройств (требует --tenant)
python -m network_collector sync-netbox --cleanup --tenant "MyTenant" --dry-run

# ПОЛНАЯ СИНХРОНИЗАЦИЯ с очисткой (UPDATE + DELETE)
python -m network_collector sync-netbox \
    --create-devices --update-devices \
    --interfaces --cleanup-interfaces \
    --ip-addresses --update-ips --cleanup-ips \
    --cables --cleanup-cables \
    --site "Office" --dry-run
```

### 4.10 DiffCalculator — предпросмотр изменений

Показывает что будет создано/обновлено ДО применения изменений.

#### CLI использование

```bash
# Показать diff для интерфейсов
python -m network_collector sync-netbox --interfaces --show-diff --dry-run

# Вывод:
# ============================================================
# DIFF SUMMARY
# ============================================================
# interfaces: +5 new, ~2 update, =10 skip
# ------------------------------------------------------------
# CREATE:
#   + Gi0/10
#   + Gi0/11
# UPDATE:
#   ~ Gi0/1: description: '' → 'Server-01'
#   ~ Gi0/2: enabled: True → False
```

#### Программное использование

```python
from network_collector.netbox import NetBoxClient, DiffCalculator

client = NetBoxClient(url, token)
diff_calc = DiffCalculator(client)

# Diff для интерфейсов
diff = diff_calc.diff_interfaces("switch-01", collected_interfaces)
print(diff.summary())           # "interfaces: +5 new, ~2 update"
print(diff.format_detailed())   # Полный вывод

# Diff для устройств
diff = diff_calc.diff_devices(inventory_data, update_existing=True)

# Diff для IP-адресов
diff = diff_calc.diff_ip_addresses("switch-01", ip_data)

# Проверка наличия изменений
if diff.has_changes:
    print(f"Будет изменено: {diff.total_changes} объектов")

# Доступ к изменениям
for change in diff.creates:
    print(f"CREATE: {change.name}")
for change in diff.updates:
    print(f"UPDATE: {change.name}")
    for field_change in change.changes:
        print(f"  {field_change.field}: {field_change.old_value} → {field_change.new_value}")
```

#### Методы DiffResult

| Метод | Описание |
|-------|----------|
| `summary()` | Краткая сводка: `interfaces: +5 new, ~2 update` |
| `format_detailed()` | Полный вывод с деталями |
| `has_changes` | `True` если есть изменения |
| `total_changes` | Количество изменений (create + update + delete) |
| `to_dict()` | Сериализация в словарь (для JSON) |

---

## 5. Pipeline (конвейеры)

Pipeline позволяет создавать настраиваемые конвейеры для автоматизации сбора и синхронизации данных.

### 5.1 Что такое Pipeline

Pipeline — это последовательность шагов (steps), где каждый шаг выполняет определённую операцию:

| Тип шага | Описание | Примеры target |
|----------|----------|----------------|
| `collect` | Сбор данных с устройств | devices, interfaces, mac, lldp, cdp, inventory, backup |
| `sync` | Синхронизация с NetBox | devices, interfaces, cables, inventory, vlans |
| `export` | Экспорт в файл | devices, interfaces, mac (любой собранный) |

### 5.2 YAML формат Pipeline

Pipelines хранятся в `pipelines/*.yaml`:

```yaml
# pipelines/full_sync.yaml
id: full_sync
name: "Full Sync"
description: "Полная синхронизация с NetBox"
enabled: true

steps:
  # Шаг 1: Сбор устройств
  - id: collect_devices
    type: collect
    target: devices
    enabled: true
    options: {}

  # Шаг 2: Синхронизация устройств
  - id: sync_devices
    type: sync
    target: devices
    enabled: true
    depends_on:
      - collect_devices
    options:
      site: "Office"
      role: "switch"

  # Шаг 3: Сбор интерфейсов
  - id: collect_interfaces
    type: collect
    target: interfaces
    enabled: true
    depends_on:
      - sync_devices

  # Шаг 4: Синхронизация интерфейсов
  - id: sync_interfaces
    type: sync
    target: interfaces
    enabled: true
    depends_on:
      - collect_interfaces

  # Шаг 5: Сбор LLDP/CDP
  - id: collect_lldp
    type: collect
    target: lldp
    enabled: true
    depends_on:
      - sync_interfaces
    options:
      protocol: both

  # Шаг 6: Синхронизация кабелей
  - id: sync_cables
    type: sync
    target: cables
    enabled: true
    depends_on:
      - collect_lldp
```

### 5.3 Зависимости между шагами

Шаги выполняются последовательно. Опция `depends_on` указывает какие шаги должны завершиться успешно:

```yaml
- id: sync_interfaces
  type: sync
  target: interfaces
  depends_on:
    - sync_devices        # Сначала устройства
    - collect_interfaces  # И интерфейсы собраны
```

**Правила зависимостей:**

| Sync target | Требует |
|-------------|---------|
| interfaces | sync_devices + collect_interfaces |
| cables | sync_interfaces + collect_lldp |
| inventory | sync_devices + collect_inventory |
| vlans | sync_devices |

### 5.4 Доступные опции шагов

**Collect шаги:**

```yaml
# collect lldp
options:
  protocol: both  # lldp, cdp, both

# collect backup
options:
  output_dir: "backups"
```

**Sync шаги:**

```yaml
# sync devices
options:
  site: "Office"
  role: "switch"
  create: true
  update: true

# sync interfaces
options:
  sync_mac: true
  sync_mode: true  # 802.1Q mode
```

**Export шаги:**

```yaml
# export
options:
  format: excel  # excel, csv, json
  output_dir: "reports"
```

### 5.5 Использование Pipeline через Web UI

1. Открыть http://localhost:8080 (API) и http://localhost:5173 (Frontend)
2. Перейти в раздел "Pipelines"
3. Создать/редактировать pipeline через UI
4. Нажать "Run Pipeline"
5. Выбрать устройства и режим (dry-run / real)

### 5.6 Использование Pipeline через API

```bash
# Список pipelines
curl http://localhost:8080/api/pipelines

# Получить pipeline
curl http://localhost:8080/api/pipelines/full_sync

# Запустить pipeline
curl -X POST http://localhost:8080/api/pipelines/full_sync/run \
  -H "Content-Type: application/json" \
  -H "X-SSH-Username: admin" \
  -H "X-SSH-Password: admin" \
  -H "X-NetBox-URL: http://netbox:8000" \
  -H "X-NetBox-Token: your-token" \
  -d '{
    "devices": [
      {"host": "10.0.0.1", "platform": "cisco_ios"},
      {"host": "10.0.0.2", "platform": "cisco_ios"}
    ],
    "dry_run": true
  }'

# Валидировать pipeline
curl -X POST http://localhost:8080/api/pipelines/full_sync/validate

# Создать pipeline
curl -X POST http://localhost:8080/api/pipelines \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Pipeline",
    "description": "Custom pipeline",
    "steps": [
      {"id": "collect", "type": "collect", "target": "devices", "enabled": true}
    ]
  }'
```

### 5.7 Результат выполнения Pipeline

```json
{
  "pipeline_id": "full_sync",
  "status": "completed",
  "steps": [
    {"step_id": "collect_devices", "status": "completed", "duration_ms": 5230},
    {"step_id": "sync_devices", "status": "completed", "duration_ms": 1250},
    {"step_id": "collect_interfaces", "status": "completed", "duration_ms": 8100},
    {"step_id": "sync_interfaces", "status": "completed", "duration_ms": 3400}
  ],
  "total_duration_ms": 17980
}
```

**Статусы шагов:**

| Статус | Описание |
|--------|----------|
| `pending` | Ожидает выполнения |
| `running` | Выполняется |
| `completed` | Успешно завершён |
| `failed` | Ошибка выполнения |
| `skipped` | Пропущен (зависимости не выполнены или disabled) |

---

## 6. Web интерфейс

Network Collector имеет Web интерфейс для удобного управления.

### 6.1 Архитектура

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Frontend   │────▶│   Backend   │────▶│   Devices   │
│  (Vue.js)   │     │  (FastAPI)  │     │   NetBox    │
│  :5173      │     │   :8080     │     │             │
└─────────────┘     └─────────────┘     └─────────────┘
```

### 6.2 Запуск Web интерфейса

**Backend (FastAPI):**

```bash
cd /home/sa/project
source network_collector/myenv/bin/activate

# Запуск с hot-reload (для разработки)
uvicorn network_collector.api.main:app --reload --host 0.0.0.0 --port 8080

# Запуск для продакшена
uvicorn network_collector.api.main:app --host 0.0.0.0 --port 8080 --workers 4
```

**Frontend (Vue.js):**

```bash
cd /home/sa/project/network_collector/frontend

# Установка зависимостей (первый раз)
npm install

# Запуск dev server
npm run dev
# http://localhost:5173

# Production build
npm run build
# Результат в dist/
```

### 6.3 Страницы Web UI

| Страница | URL | Описание |
|----------|-----|----------|
| Home | `/` | Главная страница |
| Credentials | `/credentials` | Настройка учётных данных SSH и NetBox |
| Devices | `/devices` | Сбор инвентаризации устройств |
| MAC Table | `/mac` | Сбор MAC-адресов |
| LLDP/CDP | `/lldp` | Сбор соседей |
| Interfaces | `/interfaces` | Сбор интерфейсов |
| Inventory | `/inventory` | Сбор модулей/SFP |
| Backup | `/backup` | Резервное копирование конфигураций |
| Sync NetBox | `/sync` | Синхронизация с NetBox |
| Pipelines | `/pipelines` | Управление конвейерами |

### 6.4 Настройка Credentials

1. Перейти в `/credentials`
2. Ввести SSH credentials (username/password)
3. Ввести NetBox URL и Token (для синхронизации)
4. Нажать "Save"

Credentials хранятся в сессии и передаются в каждый запрос через headers.

### 6.5 Использование Pipelines через UI

**Создание Pipeline:**
1. Перейти в `/pipelines`
2. Нажать "+ Создать Pipeline"
3. Задать имя и описание
4. Добавить шаги (+ Добавить шаг)
5. Для каждого шага выбрать: ID, Type, Target, Enabled
6. Сохранить

**Запуск Pipeline:**
1. Найти нужный pipeline в списке
2. Нажать "Run Pipeline"
3. Ввести IP устройств через запятую
4. Выбрать dry-run (preview) или реальное выполнение
5. Нажать Run

**Результаты:**
- Статус каждого шага (completed/failed/skipped)
- Время выполнения
- Ошибки (если есть)

---

## 7. REST API

Полная документация API доступна по адресам:
- Swagger UI: http://localhost:8080/docs
- ReDoc: http://localhost:8080/redoc

### 7.1 Аутентификация

Credentials передаются через HTTP headers:

```
X-SSH-Username: admin
X-SSH-Password: admin
X-NetBox-URL: http://netbox:8000
X-NetBox-Token: your-token
```

### 7.2 Endpoints

| Method | Endpoint | Описание |
|--------|----------|----------|
| GET | `/health` | Проверка состояния API |
| POST | `/api/auth/credentials` | Установить credentials |
| GET | `/api/auth/credentials/status` | Проверить credentials |
| POST | `/api/devices` | Сбор инвентаризации |
| POST | `/api/mac` | Сбор MAC-адресов |
| POST | `/api/lldp` | Сбор LLDP/CDP |
| POST | `/api/interfaces` | Сбор интерфейсов |
| POST | `/api/inventory` | Сбор модулей |
| POST | `/api/backup` | Резервное копирование |
| POST | `/api/sync` | Синхронизация с NetBox |
| POST | `/api/match` | Сопоставление MAC |
| POST | `/api/push` | Push описаний |
| GET | `/api/pipelines` | Список pipelines |
| GET | `/api/pipelines/{id}` | Получить pipeline |
| POST | `/api/pipelines` | Создать pipeline |
| PUT | `/api/pipelines/{id}` | Обновить pipeline |
| DELETE | `/api/pipelines/{id}` | Удалить pipeline |
| POST | `/api/pipelines/{id}/run` | Запустить pipeline |
| POST | `/api/pipelines/{id}/validate` | Валидировать pipeline |

### 7.3 Примеры запросов

**Сбор устройств:**

```bash
curl -X POST http://localhost:8080/api/devices \
  -H "Content-Type: application/json" \
  -H "X-SSH-Username: admin" \
  -H "X-SSH-Password: admin" \
  -d '{
    "devices": ["10.0.0.1", "10.0.0.2"]
  }'
```

**Синхронизация с NetBox:**

```bash
curl -X POST http://localhost:8080/api/sync \
  -H "Content-Type: application/json" \
  -H "X-SSH-Username: admin" \
  -H "X-SSH-Password: admin" \
  -H "X-NetBox-URL: http://netbox:8000" \
  -H "X-NetBox-Token: your-token" \
  -d '{
    "devices": ["10.0.0.1"],
    "sync_all": true,
    "dry_run": true,
    "site": "Office"
  }'
```

### 7.4 Коды ответов

| Код | Описание |
|-----|----------|
| 200 | Успех |
| 201 | Создано |
| 204 | Удалено (no content) |
| 400 | Ошибка валидации |
| 401 | Не авторизован |
| 404 | Не найдено |
| 500 | Внутренняя ошибка |

---

## 8. Фильтры и исключения

### 8.1 MAC export — config.yaml

```yaml
# config.yaml
filters:
  exclude_vlans: [1, 4094]           # Исключить VLAN 1 и 4094
  exclude_interfaces:                 # Исключить интерфейсы (regex)
    - "^Po\\d+"                       # Port-channel
    - "^Vlan\\d+"                     # VLAN интерфейсы
    - "^Loopback"                     # Loopback
    - "^Null.*"                       # Null
```

**Применяется в:** `MACCollector`

### 8.2 NetBox sync — fields.yaml

```yaml
# fields.yaml
sync:
  interfaces:
    options:
      exclude_interfaces:             # Исключить из синхронизации
        - "^Vlan1$"                   # Только Vlan1
        - "^Null\\d+"                 # Null интерфейсы
```

**Применяется в:** `sync_interfaces()`

### 8.3 Почему разные конфиги?

| Функция | Конфиг | Назначение |
|---------|--------|------------|
| MAC export | `config.yaml` | Фильтрация при сборе MAC-таблицы |
| NetBox sync | `fields.yaml` | Фильтрация при синхронизации интерфейсов |

Разные задачи — разные фильтры. Например, можно синхронизировать Vlan интерфейсы, но не собирать с них MAC.

---

## 9. Безопасность

### 9.1 Хранение токенов

**Приоритет источников:**

```
1. Переменные окружения (NETBOX_TOKEN)     — высший приоритет
2. Системное хранилище (Credential Manager) — рекомендуется
3. config.yaml                              — fallback
```

### 9.2 Windows Credential Manager

```bash
# Добавить токен
Win+R → "Credential Manager" → Generic Credentials → Add
  Internet address: network_collector
  User name:        netbox_token
  Password:         <ваш токен>
```

### 9.3 Переменные окружения

```bash
# Windows CMD
set NETBOX_TOKEN=your-token
set NET_USERNAME=admin
set NET_PASSWORD=password

# Windows PowerShell
$env:NETBOX_TOKEN="your-token"

# Linux/macOS
export NETBOX_TOKEN=your-token
```

### 9.4 SSL сертификаты

Для корпоративных CA:

```bash
pip install python-certifi-win32
```

Network Collector автоматически использует Windows Certificate Store.

---

## 10. Примеры использования

### 10.1 Полный аудит оборудования

```bash
# Сбор всех данных
python -m network_collector devices --format excel -o devices.xlsx
python -m network_collector mac --with-descriptions --format excel -o mac.xlsx
python -m network_collector lldp --protocol both --format excel -o neighbors.xlsx
python -m network_collector interfaces --format excel -o interfaces.xlsx
```

### 10.2 Первичная синхронизация с NetBox

```bash
# 1. Проверяем доступность
python -m network_collector devices --format csv

# 2. Dry-run синхронизации
python -m network_collector sync-netbox --sync-all \
    --site "Office" --role "switch" --dry-run

# 3. Применяем (без dry-run)
python -m network_collector sync-netbox --sync-all \
    --site "Office" --role "switch"
```

### 10.3 MAC → Описания портов

```bash
# 1. Сбор MAC с описаниями
python -m network_collector mac --with-descriptions -o mac.xlsx

# 2. Сопоставление с GLPI
python -m network_collector match-mac \
    --mac-file mac.xlsx \
    --hosts-file glpi.xlsx \
    --output matched.xlsx

# 3. Проверка (dry-run)
python -m network_collector push-descriptions --matched-file matched.xlsx

# 4. Применение
python -m network_collector push-descriptions --matched-file matched.xlsx --apply
```

### 10.4 Обновление существующих устройств

```bash
# Обновить serial, model на существующих
python -m network_collector sync-netbox --create-devices --update-devices

# Обновить интерфейсы
python -m network_collector sync-netbox --interfaces --update-devices
```

### 10.5 Резервное копирование

```bash
# Бэкап конфигураций
python -m network_collector backup --output ./backups/$(date +%Y-%m-%d)
```

---

## 11. Устранение неполадок

### 11.1 Ошибка подключения SSH

```
ConnectionError: Unable to connect to device
```

**Решение:**
1. Проверьте доступность: `ping 192.168.1.1`
2. Проверьте SSH: `ssh admin@192.168.1.1`
3. Проверьте учётные данные (`NET_USERNAME`, `NET_PASSWORD`)
4. Проверьте `platform` в devices_ips.py

### 11.2 Ошибка парсинга NTC Templates

```
NTC Template not found for command
```

**Решение:**
- Проверьте поддержку платформы в NTC Templates
- Используйте `--format raw` для просмотра сырого вывода
- Добавьте кастомный шаблон в `templates/`

### 11.3 Ошибка NetBox API

```
RequestError: 400 Bad Request
```

**Решение:**
1. Проверьте что site/role существуют в NetBox
2. Убедитесь что токен имеет права на запись
3. Проверьте версию NetBox (требуется 4.x)

### 11.4 Устройство не найдено в NetBox

```
Device 'switch1' not found in NetBox
```

**Решение:**
- Сначала создайте устройство: `--create-devices`
- Убедитесь что hostname совпадает

### 11.5 Включить debug логирование

```bash
# Через CLI
python -m network_collector mac -v --format json

# Через config.yaml
logging:
  level: "DEBUG"
```

### 11.6 Проверить данные на каждом этапе

```bash
# Сырые данные (JSON)
python -m network_collector interfaces --format json > interfaces.json

# Проверить NTC парсинг
python -c "
from ntc_templates.parse import parse_output
output = open('show_output.txt').read()
print(parse_output(platform='cisco_ios', command='show interfaces', data=output))
"
```

---

## Справочник

### Форматы MAC-адресов

| Формат | Пример | Опция |
|--------|--------|-------|
| IEEE | 00:11:22:33:44:55 | `mac_format: ieee` |
| Cisco | 0011.2233.4455 | `mac_format: cisco` |
| NetBox | 00-11-22-33-44-55 | `mac_format: netbox` |
| Raw | 001122334455 | `mac_format: raw` |

### Типы интерфейсов NetBox

| Наш тип | NetBox тип | Описание |
|---------|------------|----------|
| 100g-qsfp28 | 100gbase-x-qsfp28 | 100G QSFP28 |
| 40g-qsfp | 40gbase-x-qsfpp | 40G QSFP+ |
| 25g-sfp28 | 25gbase-x-sfp28 | 25G SFP28 |
| 10g-sfp+ | 10gbase-x-sfpp | 10G SFP+ |
| 1g-sfp | 1000base-x-sfp | 1G SFP |
| 1g-rj45 | 1000base-t | 1G RJ45 |
| 100m-rj45 | 100base-tx | 100M RJ45 |
| lag | lag | Port-channel |
| virtual | virtual | Vlan, Loopback |

### Switchport Modes

| Из устройства | В NetBox | Условие |
|---------------|----------|---------|
| access | access | Всегда |
| trunk + ALL | tagged-all | trunk_vlans = "ALL" или "1-4094" |
| trunk + конкретные | tagged | trunk_vlans = "10,20,30" |

---

## Контакты

Вопросы и баги: создайте issue в репозитории.
