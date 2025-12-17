# Network Collector - Руководство пользователя

Подробная инструкция по использованию Network Collector для сбора данных с сетевого оборудования и синхронизации с NetBox.

## Содержание

- [Установка и настройка](#установка-и-настройка)
- [Быстрый старт](#быстрый-старт)
- [Команды сбора данных](#команды-сбора-данных)
- [Синхронизация с NetBox](#синхронизация-с-netbox)
- [Примеры использования](#примеры-использования)
- [Поля в NetBox](#поля-в-netbox)
- [Устранение неполадок](#устранение-неполадок)

---

## Установка и настройка

### 1. Клонирование и установка зависимостей

```bash
cd /home/sa/project
source network_collector/myenv/bin/activate
pip install -r network_collector/requirements.txt
```

### 2. Настройка списка устройств

Создайте файл `devices_ips.py` в директории `network_collector`:

```python
devices_list = [
    {"host": "192.168.1.1", "device_type": "cisco_ios"},
    {"host": "192.168.1.2", "device_type": "cisco_iosxe"},
    {"host": "192.168.1.3", "device_type": "arista_eos"},
]
```

**Поддерживаемые платформы:**
| Платформа | device_type |
|-----------|-------------|
| Cisco IOS | `cisco_ios` |
| Cisco IOS-XE | `cisco_iosxe` |
| Cisco NX-OS | `cisco_nxos` |
| Cisco IOS-XR | `cisco_iosxr` |
| Arista EOS | `arista_eos` |
| Juniper JunOS | `juniper_junos` |
| QTech | `qtech` или `qtech_qsw` |

### 3. Настройка учетных данных

Установите переменные окружения:

```bash
export NET_USERNAME="admin"
export NET_PASSWORD="password"
```

Или используйте файл `config.yaml`:

```yaml
credentials:
  username: admin
  password: password
```

### 4. Настройка NetBox (опционально)

```bash
export NETBOX_URL="http://netbox.example.com"
export NETBOX_TOKEN="your-api-token"
```

---

## Быстрый старт

```bash
# Активация окружения
cd /home/sa/project
source network_collector/myenv/bin/activate

# Проверка доступности устройств
python -m network_collector devices --format csv

# Сбор MAC-адресов
python -m network_collector mac --format excel

# Синхронизация с NetBox (сначала dry-run!)
python -m network_collector sync-netbox --create-devices --dry-run
```

---

## Команды сбора данных

### Инвентаризация устройств

```bash
# Базовая информация (hostname, version, serial)
python -m network_collector devices

# Экспорт в различные форматы
python -m network_collector devices --format csv
python -m network_collector devices --format excel
python -m network_collector devices --format json
```

### Сбор MAC-адресов

```bash
# Все MAC-адреса с устройств
python -m network_collector mac --format excel

# Сохранить в конкретный файл
python -m network_collector mac --format excel --output mac_table.xlsx
```

### Сбор соседей (LLDP/CDP)

```bash
# Только LLDP
python -m network_collector lldp --protocol lldp --format csv

# Только CDP
python -m network_collector lldp --protocol cdp --format csv

# Оба протокола
python -m network_collector lldp --protocol both --format csv
```

### Сбор интерфейсов

```bash
# Список всех интерфейсов
python -m network_collector interfaces --format json
```

### Резервное копирование конфигураций

```bash
# Сохранить конфиги в директорию
python -m network_collector backup --output ./backups
```

### Произвольная команда

```bash
# Выполнить любую команду с парсингом NTC Templates
python -m network_collector run "show version" --format json
python -m network_collector run "show ip route" --format csv
```

---

## Синхронизация с NetBox

### Общие принципы

1. **Всегда начинайте с `--dry-run`** - показывает что будет сделано без изменений
2. **Порядок синхронизации важен:**
   - Сначала создайте устройства (`--create-devices`)
   - Затем интерфейсы (`--interfaces`)
   - Потом IP-адреса (`--ip-addresses`)
   - И кабели (`--cables`)
3. **Используйте `--sync-all`** для полной синхронизации в правильном порядке

### Полная синхронизация (--sync-all)

```bash
# Полная синхронизация всех данных (рекомендуемый способ)
python -m network_collector sync-netbox --sync-all --site "Main" --role "switch" --dry-run

# Без dry-run (применить изменения)
python -m network_collector sync-netbox --sync-all --site "Main" --role "switch"
```

**Порядок выполнения --sync-all:**
1. Создание/обновление устройств
2. Синхронизация интерфейсов
3. Привязка IP-адресов
4. Создание VLAN из SVI
5. Построение топологии (кабели из LLDP/CDP)
6. Синхронизация inventory (модули, SFP)

### Создание устройств

```bash
# Показать что будет создано
python -m network_collector sync-netbox --create-devices --dry-run

# Создать устройства с указанием site и role
python -m network_collector sync-netbox --create-devices --site "Main" --role "access-switch"

# Создать и обновить существующие
python -m network_collector sync-netbox --create-devices --update-devices
```

**Обязательные параметры для создания:**
- `--site` - сайт в NetBox (должен существовать)
- `--role` - роль устройства (должна существовать)

### Обновление устройств

```bash
# Обновить serial, platform, device_type существующих устройств
python -m network_collector sync-netbox --update-devices --dry-run
```

### Синхронизация интерфейсов

```bash
# Создать/обновить интерфейсы
python -m network_collector sync-netbox --interfaces --dry-run

# Выполнить синхронизацию
python -m network_collector sync-netbox --interfaces
```

### Синхронизация IP-адресов

```bash
# Привязать IP к интерфейсам
python -m network_collector sync-netbox --ip-addresses --dry-run
```

### Синхронизация кабелей (топология)

```bash
# Создать кабели на основе LLDP
python -m network_collector sync-netbox --cables --protocol lldp --dry-run

# На основе CDP
python -m network_collector sync-netbox --cables --protocol cdp --dry-run

# Оба протокола
python -m network_collector sync-netbox --cables --protocol both --dry-run
```

**Важно:** Кабели создаются только между устройствами, которые уже есть в NetBox.

### Синхронизация VLAN

```bash
# Создать VLAN из SVI интерфейсов (Vlan10 → VLAN 10)
python -m network_collector sync-netbox --vlans --site "Main" --dry-run
```

**Логика:**
- Интерфейс `Vlan10` → VLAN с vid=10
- Имя VLAN = description интерфейса или "VLAN 10"

### Синхронизация Inventory (модули, SFP)

```bash
# Синхронизировать модули, SFP, PSU
python -m network_collector sync-netbox --inventory --dry-run
```

### Удаление устаревших устройств

```bash
# Удалить устройства не из списка (требует --tenant!)
python -m network_collector sync-netbox --cleanup --tenant "MyTenant" --dry-run
```

**Безопасность:** `--cleanup` требует указания `--tenant` чтобы не удалить чужие устройства.

---

## Примеры использования

### Пример 1: Первичная синхронизация

```bash
# 1. Проверяем доступность
python -m network_collector devices --format csv

# 2. Создаём устройства (dry-run)
python -m network_collector sync-netbox --create-devices --site "Office" --role "access-switch" --dry-run

# 3. Если всё ок - создаём
python -m network_collector sync-netbox --create-devices --site "Office" --role "access-switch"

# 4. Синхронизируем интерфейсы
python -m network_collector sync-netbox --interfaces

# 5. Привязываем IP
python -m network_collector sync-netbox --ip-addresses

# 6. Строим топологию
python -m network_collector sync-netbox --cables --protocol both
```

### Пример 2: Обновление существующих данных

```bash
# Обновить устройства и интерфейсы
python -m network_collector sync-netbox --update-devices --interfaces
```

### Пример 3: Полный аудит оборудования

```bash
# Собрать всё: устройства, MAC, соседи
python -m network_collector devices --format excel --output devices.xlsx
python -m network_collector mac --format excel --output mac.xlsx
python -m network_collector lldp --protocol both --format excel --output neighbors.xlsx
```

---

## Поля в NetBox

### Устройства (Devices)

| Поле | Источник | Команда |
|------|----------|---------|
| name | hostname из show version | --create-devices |
| device_type | модель из show version | --create-devices |
| serial | серийный номер | --create-devices, --update-devices |
| platform | cisco_ios, arista_eos и т.д. | --create-devices |
| site | параметр --site | --create-devices |
| role | параметр --role | --create-devices |

### Интерфейсы (Interfaces)

| Поле | Источник | Команда |
|------|----------|---------|
| name | имя интерфейса | --interfaces |
| enabled | admin status | --interfaces |
| description | description с устройства | --interfaces |
| type | определяется по имени | --interfaces |

### IP-адреса (IP Addresses)

| Поле | Источник | Команда |
|------|----------|---------|
| address | IP/mask с интерфейса | --ip-addresses |
| assigned_object | привязка к интерфейсу | --ip-addresses |
| status | active | --ip-addresses |

### Кабели (Cables)

| Поле | Источник | Команда |
|------|----------|---------|
| a_terminations | локальный интерфейс | --cables |
| b_terminations | интерфейс соседа | --cables |
| status | connected | --cables |

### VLAN

| Поле | Источник | Команда |
|------|----------|---------|
| vid | номер из имени Vlan10 | --vlans |
| name | description интерфейса | --vlans |
| site | параметр --site | --vlans |
| status | active | --vlans |

### Inventory Items

| Поле | Источник | Команда |
|------|----------|---------|
| name | имя компонента | --inventory |
| part_id | PID (модель) | --inventory |
| serial | серийный номер | --inventory |
| manufacturer | определяется по PID | --inventory |
| description | описание | --inventory |

---

## Устранение неполадок

### Ошибка подключения SSH

```
ConnectionError: Unable to connect to device
```

**Решение:**
1. Проверьте доступность устройства: `ping 192.168.1.1`
2. Проверьте SSH: `ssh admin@192.168.1.1`
3. Проверьте учетные данные в переменных окружения

### Ошибка парсинга NTC Templates

```
NTC Template not found for command
```

**Решение:**
- Проверьте поддержку платформы в NTC Templates
- Убедитесь что `device_type` указан корректно

### Ошибка NetBox API

```
RequestError: 400 Bad Request
```

**Решение:**
1. Проверьте что site/role существуют в NetBox
2. Убедитесь что токен имеет права на запись
3. Проверьте версию NetBox (требуется 3.x+)

### Устройство не найдено в NetBox

```
Device 'switch1' not found in NetBox
```

**Решение:**
- Сначала создайте устройство: `--create-devices`
- Убедитесь что hostname совпадает

### LLDP/CDP не находит соседей

**Возможные причины:**
1. Протокол не включен на устройстве
2. Используйте `--protocol both` для поиска по обоим протоколам
3. Сосед не в списке устройств NetBox

---

## Конфигурация

### config.yaml

```yaml
# Настройки синхронизации
sync:
  devices:
    default_site: "Main"
    default_role: "Switch"
    update_serial: true
    update_platform: true

  interfaces:
    sync_description: true
    sync_enabled: true
    default_type: "1000base-t"

  ip_addresses:
    default_status: "active"

  cables:
    default_status: "connected"
    protocols:
      - lldp
      - cdp

  vlans:
    create_from_svi: true
    default_status: "active"

# NetBox
netbox:
  url: "http://netbox.example.com"
  # token лучше через переменную окружения NETBOX_TOKEN
  ssl_verify: true

# Credentials
credentials:
  # лучше через переменные окружения
  # username: admin
  # password: password
```

---

## Справка по командам

```bash
# Общая справка
python -m network_collector --help

# Справка по sync-netbox
python -m network_collector sync-netbox --help
```

### Флаги sync-netbox

| Флаг | Описание |
|------|----------|
| `--sync-all` | **Полная синхронизация** (все флаги в правильном порядке) |
| `--create-devices` | Создать новые устройства |
| `--update-devices` | Обновить существующие устройства |
| `--interfaces` | Синхронизировать интерфейсы |
| `--ip-addresses` | Синхронизировать IP-адреса |
| `--cables` | Создать кабели (топология) |
| `--vlans` | Создать VLAN из SVI |
| `--inventory` | Синхронизировать модули, SFP |
| `--cleanup` | Удалить устаревшие устройства |
| `--dry-run` | Режим симуляции |
| `--site` | Сайт NetBox |
| `--role` | Роль устройства |
| `--tenant` | Tenant (для --cleanup) |
| `--protocol` | lldp, cdp или both |
