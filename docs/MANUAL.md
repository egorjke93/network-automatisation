# Network Collector - Полное руководство

Полное руководство пользователя по всем командам, настройкам и опциям.

## Содержание

1. [Установка и настройка](#1-установка-и-настройка)
2. [Конфигурация](#2-конфигурация)
3. [Команды CLI](#3-команды-cli)
4. [Синхронизация с NetBox](#4-синхронизация-с-netbox)
5. [Фильтры и исключения](#5-фильтры-и-исключения)
6. [Безопасность](#6-безопасность)
7. [Примеры использования](#7-примеры-использования)
8. [Устранение неполадок](#8-устранение-неполадок)

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
  default_format: "excel"       # excel, csv, json
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

### 3.2 devices — Инвентаризация устройств

```bash
python -m network_collector devices [опции]

Опции:
  --format {excel,csv,json}  Формат вывода (default: excel)

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
  --format {excel,csv,json}  Формат вывода (default: excel)
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
  --format {excel,csv,json}    Формат вывода
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
  --format {excel,csv,json}  Формат вывода

Собирает:
  - hostname, interface, status, description, ip_address, mac,
    speed, duplex, mtu, mode, port_type, lag_group
```

### 3.6 inventory — Сбор модулей/SFP

```bash
python -m network_collector inventory [опции]

Опции:
  --format {excel,csv,json}  Формат вывода

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
| **Device** | `--create-devices` | Всегда | `--update-devices` | `--cleanup` |
| **Interface** | `--interfaces` | Всегда | `--interfaces` | ❌ Нет |
| **IP Address** | `--ip-addresses` | Всегда | `--update-devices` + `--ip-addresses` | ❌ Нет |
| **Cable** | `--cables` | Проверка наличия | ❌ Нет | ❌ Нет |
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
| **DELETE** | ❌ Не реализовано | — |

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
| **UPDATE** | `--ip-addresses --update-devices` | Обновляет tenant, description, привязку |
| **DELETE** | ❌ Не реализовано | — |

```bash
# Только CREATE
sync-netbox --ip-addresses
# Новые IP → CREATE, существующие → SKIP

# CREATE + UPDATE
sync-netbox --ip-addresses --update-devices
# Новые IP → CREATE, существующие → UPDATE (tenant, description)
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
| **DELETE** | ❌ Не реализовано | — |
| **SKIP** | Интерфейс уже имеет кабель | Пропуск |
| **SKIP** | LAG интерфейс | Пропуск (кабели на LAG не поддерживаются) |

```bash
sync-netbox --cables --protocol both  # LLDP + CDP
sync-netbox --cables --protocol lldp  # Только LLDP
sync-netbox --cables --protocol cdp   # Только CDP
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
| DELETE интерфейсов | ❌ | Удаление интерфейсов которых нет на устройстве |
| DELETE IP-адресов | ❌ | Удаление IP которых нет на устройстве |
| DELETE кабелей | ❌ | Удаление кабелей при изменении топологии |
| UPDATE кабелей | ❌ | Обновление типа кабеля |
| UPDATE VLAN | ❌ | Обновление имени VLAN |
| DELETE VLAN | ❌ | Удаление неиспользуемых VLAN |
| CLEANUP интерфейсов | ❌ | Удаление старых интерфейсов (аналог --cleanup для devices) |
| Sync untagged/tagged VLANs | ❌ | Привязка VLAN к интерфейсам |

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
```

---

## 5. Фильтры и исключения

### 5.1 MAC export — config.yaml

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

### 5.2 NetBox sync — fields.yaml

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

### 5.3 Почему разные конфиги?

| Функция | Конфиг | Назначение |
|---------|--------|------------|
| MAC export | `config.yaml` | Фильтрация при сборе MAC-таблицы |
| NetBox sync | `fields.yaml` | Фильтрация при синхронизации интерфейсов |

Разные задачи — разные фильтры. Например, можно синхронизировать Vlan интерфейсы, но не собирать с них MAC.

---

## 6. Безопасность

### 6.1 Хранение токенов

**Приоритет источников:**

```
1. Переменные окружения (NETBOX_TOKEN)     — высший приоритет
2. Системное хранилище (Credential Manager) — рекомендуется
3. config.yaml                              — fallback
```

### 6.2 Windows Credential Manager

```bash
# Добавить токен
Win+R → "Credential Manager" → Generic Credentials → Add
  Internet address: network_collector
  User name:        netbox_token
  Password:         <ваш токен>
```

### 6.3 Переменные окружения

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

### 6.4 SSL сертификаты

Для корпоративных CA:

```bash
pip install python-certifi-win32
```

Network Collector автоматически использует Windows Certificate Store.

---

## 7. Примеры использования

### 7.1 Полный аудит оборудования

```bash
# Сбор всех данных
python -m network_collector devices --format excel -o devices.xlsx
python -m network_collector mac --with-descriptions --format excel -o mac.xlsx
python -m network_collector lldp --protocol both --format excel -o neighbors.xlsx
python -m network_collector interfaces --format excel -o interfaces.xlsx
```

### 7.2 Первичная синхронизация с NetBox

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

### 7.3 MAC → Описания портов

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

### 7.4 Обновление существующих устройств

```bash
# Обновить serial, model на существующих
python -m network_collector sync-netbox --create-devices --update-devices

# Обновить интерфейсы
python -m network_collector sync-netbox --interfaces --update-devices
```

### 7.5 Резервное копирование

```bash
# Бэкап конфигураций
python -m network_collector backup --output ./backups/$(date +%Y-%m-%d)
```

---

## 8. Устранение неполадок

### 8.1 Ошибка подключения SSH

```
ConnectionError: Unable to connect to device
```

**Решение:**
1. Проверьте доступность: `ping 192.168.1.1`
2. Проверьте SSH: `ssh admin@192.168.1.1`
3. Проверьте учётные данные (`NET_USERNAME`, `NET_PASSWORD`)
4. Проверьте `platform` в devices_ips.py

### 8.2 Ошибка парсинга NTC Templates

```
NTC Template not found for command
```

**Решение:**
- Проверьте поддержку платформы в NTC Templates
- Используйте `--format raw` для просмотра сырого вывода
- Добавьте кастомный шаблон в `templates/`

### 8.3 Ошибка NetBox API

```
RequestError: 400 Bad Request
```

**Решение:**
1. Проверьте что site/role существуют в NetBox
2. Убедитесь что токен имеет права на запись
3. Проверьте версию NetBox (требуется 4.x)

### 8.4 Устройство не найдено в NetBox

```
Device 'switch1' not found in NetBox
```

**Решение:**
- Сначала создайте устройство: `--create-devices`
- Убедитесь что hostname совпадает

### 8.5 Включить debug логирование

```bash
# Через CLI
python -m network_collector mac -v --format json

# Через config.yaml
logging:
  level: "DEBUG"
```

### 8.6 Проверить данные на каждом этапе

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
