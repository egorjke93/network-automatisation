# Work In Progress - Текущие задачи

Этот файл отслеживает прогресс текущей сессии работы.
Последнее обновление: 2025-12-09

---

## Принцип работы

**ВАЖНО:** Прежде чем добавлять новый функционал:
1. Протестировать существующий функционал
2. Задокументировать что работает, что нет
3. Исправить баги
4. Написать документацию
5. Только потом развивать дальше

---

## Статус функционала NetBox синхронизации

### Протестировано и работает ✅

| Флаг | Статус | Что делает | Какие поля заполняет в NetBox |
|------|--------|------------|------------------------------|
| `--create-devices` | ✅ Работает | Создаёт устройства из show version | name, device_type, site, role, serial, platform |
| `--update-devices` | ✅ Работает | Обновляет существующие | serial, device_type, platform |
| `--interfaces` | ✅ Работает | Синхронизирует интерфейсы | name, enabled, description |
| `--ip-addresses` | ✅ Работает | Создаёт IP на интерфейсах | address, assigned_object (interface) |
| `--cables` | ✅ Работает | Создаёт кабели из LLDP/CDP | a_terminations, b_terminations, status |
| `--vlans` | ✅ Работает | Создаёт VLAN из SVI интерфейсов | vid, name, site, status |
| `--inventory` | ✅ Работает | Синхронизирует модули, SFP, PSU | name, part_id, serial, manufacturer, description |
| `--cleanup` | ✅ Работает | Удаляет устройства не из списка | Требует --tenant |
| `--dry-run` | ✅ Работает | Симуляция без изменений | - |

### Результаты тестирования (2025-12-09)

```
Тестовое окружение:
- NetBox: http://localhost:8000/
- Устройства: switch1 (192.168.3.35), switch2 (192.168.3.36)
- Платформа: cisco_iosxe (EVE-NG)

Текущее состояние NetBox после синхронизации:
- Devices: 2 (switch1, switch2)
- Interfaces: 5 на каждом устройстве
- IP Addresses: 2 (192.168.3.35/24, 192.168.3.36/24)
- Cables: 1 (switch1:Ethernet0/1 <-> switch2:Ethernet0/0)
```

### Известные ограничения

1. **device_type=Unknown** на EVE-NG - ожидаемо, на проде парсится из show version
2. **LLDP парсинг** - ошибка NTC шаблона для некоторых форматов (fallback на CDP работает)
3. **Соседи не в NetBox** - при создании кабелей пропускаются соседи которых нет в NetBox

---

## Следующие задачи (TODO)

### Этап 1: Довести до идеала текущий функционал

- [x] **Документация полей** - описать все поля которые заполняются/читаются ✅
- [x] **Анализ больших файлов** - cli.py (1180), sync.py (1152) - структура логична ✅
- [x] **Настройки синхронизации** - добавлена секция `sync:` в config.yaml ✅
- [x] **Архитектура** - создан ARCHITECTURE.md с диаграммами ✅
- [x] **Инструкция** - USAGE.md написан ✅

### Этап 2: Новый функционал (после Этапа 1!)

- [x] Синхронизация inventory (модули, SFP) — `--inventory` ✅
- [x] `--sync-all` для полной синхронизации ✅
- [ ] Прогресс-бар для длительных операций
- [ ] Retry логика при ошибках API

### Этап 3: Полный CRUD для NetBox

**Текущее состояние:**

| Сущность | CREATE | READ | UPDATE | DELETE |
|----------|--------|------|--------|--------|
| Devices | ✅ | ✅ | ✅ | ✅ `--cleanup` |
| Interfaces | ✅ | ✅ | ✅ | ❌ |
| IP Addresses | ✅ | ✅ | ❌ | ❌ |
| VLANs | ✅ | ✅ | ❌ | ❌ |
| Cables | ✅ | ✅ | ❌ | ❌ |
| Inventory | ✅ | ✅ | ✅ | ❌ |

**Задачи для полного CRUD:**

| # | Задача | Сложность | Статус |
|---|--------|-----------|--------|
| 3.1 | `--cleanup-interfaces` — удалить интерфейсы которых нет на устройстве | Средняя | ❌ |
| 3.2 | `--cleanup-ips` — удалить IP не найденные на интерфейсах | Низкая | ❌ |
| 3.3 | `--cleanup-vlans` — удалить VLAN без привязок | Низкая | ❌ |
| 3.4 | `--cleanup-cables` — удалить кабели не найденные в LLDP/CDP | Средняя | ❌ |
| 3.5 | `--cleanup-inventory` — удалить модули не найденные в show inventory | Низкая | ❌ |
| 3.6 | UPDATE IP — обновить prefix_length, status | Низкая | ❌ |
| 3.7 | UPDATE VLAN — обновить name, status | Низкая | ❌ |
| 3.8 | UPDATE Cable — обновить type, label, color | Низкая | ❌ |

**Приоритет:** После тестирования текущего функционала на проде.

---

## Команды sync-netbox

```bash
# Создать устройства
python -m network_collector sync-netbox --create-devices --dry-run

# Создать и обновить устройства
python -m network_collector sync-netbox --create-devices --update-devices --dry-run

# Удаление лишних (требует --tenant!)
python -m network_collector sync-netbox --create-devices --cleanup --tenant "MyTenant" --dry-run

# Синхронизация интерфейсов
python -m network_collector sync-netbox --interfaces --dry-run

# Синхронизация IP-адресов
python -m network_collector sync-netbox --ip-addresses --dry-run

# Синхронизация кабелей
python -m network_collector sync-netbox --cables --protocol both --dry-run

# Синхронизация VLAN из SVI
python -m network_collector sync-netbox --vlans --site Main --dry-run

# Синхронизация inventory (модули, SFP, PSU)
python -m network_collector sync-netbox --inventory --dry-run

# ПОЛНАЯ СИНХРОНИЗАЦИЯ (все флаги сразу)
python -m network_collector sync-netbox --sync-all --site Main --role switch --dry-run
```

---

## История изменений

### 2025-12-09: Добавлен --sync-all
- Полная синхронизация: devices → interfaces → ip-addresses → vlans → cables → inventory
- Порядок выполнения важен: сначала создаются устройства, потом остальное
- Использование: `python -m network_collector sync-netbox --sync-all --dry-run`
- Статус: ✅ Завершено

### 2025-12-09: Добавлен --inventory
- InventoryCollector уже существовал, добавлена синхронизация
- client.py: get_inventory_items(), create_inventory_item(), update_inventory_item()
- sync.py: sync_inventory()
- collectors/inventory.py: добавлено определение manufacturer по PID и платформе
- Поля в NetBox: name, part_id, serial, manufacturer, description
- Статус: ✅ Завершено

### 2025-12-09: Полное тестирование и документация
- Протестированы все флаги: --create-devices, --interfaces, --ip-addresses, --cables, --vlans
- Исправлен баг: site должен конвертироваться в slug для VLAN API
- Создан ARCHITECTURE.md с полным описанием архитектуры
- Добавлена секция `sync:` в config.yaml для настройки полей синхронизации
- Все флаги работают корректно
- Статус: ✅ Завершено

### 2025-12-09: Добавлен --vlans
- client.py: create_vlan(), update_interface_vlan()
- sync.py: sync_vlans_from_interfaces()
- Логика: Vlan10 с description → VLAN 10 с именем из description
- Статус: ✅ Завершено

### 2025-12-09: Добавлены --update-devices и --cleanup
- sync_devices_from_inventory() с полной синхронизацией
- --cleanup требует --tenant для безопасности
- Статус: ✅ Завершено

---

## Размеры файлов (требуют анализа)

```
1180  cli.py           <- много, возможно разбить
1152  netbox/sync.py   <- много, возможно разбить
604   collectors/mac.py
495   configurator/description.py
451   netbox/client.py
382   collectors/lldp.py
```

---

## Тестовое окружение

- NetBox URL: http://localhost:8000/
- NetBox Token: в config.yaml
- Устройства: devices_ips.py
- Платформа: cisco_iosxe (EVE-NG)



## Подзадачи (разбор замечаний)

### Задача 1: MAC экспорт - Description не попадает в таблицу ✅

**Проблема:** При `network_collector mac` в экспорт не попадает description интерфейса.

**Решение (2025-12-12):**
- [x] 1.1 `--with-descriptions` работает и добавляет поле
- [x] 1.2 Добавлена секция `mac:` в `config.yaml`:
  ```yaml
  mac:
    collect_descriptions: true   # по умолчанию собирать descriptions
    collect_trunk_ports: false   # по умолчанию исключать trunk
  ```
- [x] 1.3 Description берётся из `show interfaces description` (быстрее парсится)
- [x] Добавлены флаги `--no-descriptions` и `--exclude-trunk` для явного выключения

**Ответы на вопросы:**
- NTC Templates vs Regex: Используются NTC Templates как основной парсер, regex только как fallback если NTC не сработал
- TextFSM = NTC Templates (NTC это коллекция TextFSM шаблонов)
- Кастомные команды (`run "show ..."`) используют NTC если есть шаблон для платформы+команды

---

### Задача 2: Фильтры - разделить для MAC и NetBox ✅

**Проблема:** Фильтры `exclude_vlans`, `exclude_interfaces` в `config.py` непонятно для чего.

**Решение (2025-12-12):**
- [x] Фильтры УЖЕ в `config.yaml` (секция `filters:`)
- [x] `config.py` - это ЗАГРУЗЧИК конфигурации, не хардкод
- [x] Добавлены комментарии в config.yaml для ясности

**Архитектура конфигурации:**
- `config.yaml` → настройки сбора данных (фильтры, опции коллекторов, подключения)
- `fields.yaml` → настройки полей экспорта и маппинг для NetBox
- `config.py` → загрузчик config.yaml с дефолтами (НЕ удаляем)

---

### Задача 3: Поля по умолчанию для экспорта (tenant, site, role) ✅

**Проблема:** В `fields.yaml` секция `sync.devices.defaults` (site, role, tenant) не влияет на экспорт таблиц.

**Решение (2025-12-12):**
- [x] 3.1 Добавлена поддержка `default:` в поле конфигурации
- [x] 3.2 `apply_fields_config()` применяет default если значение пустое

**Использование в fields.yaml:**
```yaml
devices:
  site:
    enabled: true
    name: "Site"
    order: 14
    default: "Main"  # <- заполнится если поле пустое
```

---

### Задача 4: LLDP - MAC адрес не в экспорте ✅

**Проблема:** `lldp --format excel` не показывает MAC (CHASSIS_ID), хотя он есть в данных.

**Решение (2025-12-12):**
- [x] 4.1 `remote_mac` был в `fields.yaml` но `enabled: false`
- [x] 4.2 Включено `remote_mac: enabled: true` (order: 9)
- [x] 4.3 Маппинг `chassis_id` → `remote_mac` уже был в коллекторе

---

### Задача 5: Маппинг типов интерфейсов → constants.py ✅

**Проблема:** Маппинг типов интерфейсов в `sync.py` (функция `_get_interface_type`), логичнее в `constants.py`.

**Решение (2025-12-12):**
- [x] 5.1 Найден маппинг в `sync.py` (~200 строк)
- [x] 5.2 Вынесено в `core/constants.py`:
  - `NETBOX_INTERFACE_TYPE_MAP` — media_type → NetBox type
  - `NETBOX_HARDWARE_TYPE_MAP` — hardware_type → NetBox type
  - `VIRTUAL_INTERFACE_PREFIXES` — префиксы виртуальных интерфейсов
  - `MGMT_INTERFACE_PATTERNS` — паттерны management интерфейсов
- [x] 5.3 `sync.py` использует маппинги из constants (~100 строк вместо ~200)

---

### Задача 6: Документация - цепочка от парсинга до вывода ✅

**Проблема:** Непонятно как данные идут от парсинга до экспорта.

**Решение (2025-12-12):**
- [x] 6.1 Добавлена в CLAUDE.md секция "Добавление новой платформы" с диаграммой маппингов
- [x] 6.2 Документация добавления полей — см. ниже

**Как добавить новое поле в экспорт:**
1. Убедиться что поле приходит из коллектора (проверить json вывод)
2. Добавить в `fields.yaml` в нужную секцию (mac, devices, lldp, etc.):
   ```yaml
   field_name:
     enabled: true
     name: "Display Name"
     order: 10
     default: "value"  # опционально
   ```
3. Готово! Поле появится в экспорте

---

### Задача 7: Кастомные TextFSM шаблоны ✅ (бонус)

**Добавлено (2025-12-12):**
- [x] `CUSTOM_TEXTFSM_TEMPLATES` в `core/constants.py` — маппинг (platform, command) → шаблон
- [x] `textfsm_parser.py` — логика поиска кастомных шаблонов с fallback на NTC
- [x] `templates/` — папка для кастомных шаблонов
- [x] `templates/README.md` — инструкция по созданию шаблонов
- [x] `templates/qtech_show_mac_example.textfsm` — пример шаблона
- [x] `CLAUDE.md` — документация по добавлению новых платформ

---

## Чеклист для проверки на ПРОДЕ

### Перед тестированием
- [ ] NetBox доступен и токен валидный
- [ ] Устройства доступны по SSH
- [ ] Бэкап текущих данных NetBox (на всякий случай)

### 1. MAC коллектор
```bash
# Базовый сбор (без descriptions)
python -m network_collector mac --format json
```
- [ ] Собираются записи со всех устройств
- [ ] Поля: hostname, device_ip, interface, mac, vlan, type, status
- [ ] Status показывает online/offline корректно
- [ ] Фильтры exclude_vlans работают (VLAN 1 исключён?)
- [ ] Фильтры exclude_interfaces работают (Po*, Vlan* исключены?)

```bash
# С descriptions
python -m network_collector mac --format excel --with-descriptions
```
- [ ] Поле Description появилось в таблице
- [ ] Descriptions корректные (совпадают с show interfaces description)

```bash
# С trunk портами
python -m network_collector mac --format csv --include-trunk
```
- [ ] Trunk порты включены в вывод

### 2. LLDP коллектор
```bash
python -m network_collector lldp --protocol both --format json
```
- [ ] Собираются соседи LLDP
- [ ] Собираются соседи CDP (fallback)
- [ ] Поля: hostname, device_ip, local_interface, remote_hostname, remote_port
- [ ] remote_ip заполняется (если есть в LLDP/CDP)
- [ ] remote_platform заполняется
- [ ] remote_mac (CHASSIS_ID) - **ПРОВЕРИТЬ! Есть в JSON?**
- [ ] protocol показывает LLDP или CDP

### 3. Devices коллектор
```bash
python -m network_collector devices --format json
```
- [ ] Поля: hostname, ip_address, model, serial, version, uptime
- [ ] Model парсится корректно (не пустой на реальном оборудовании)
- [ ] Serial корректный
- [ ] Uptime показывается

### 4. Interfaces коллектор
```bash
python -m network_collector interfaces --format json
```
- [ ] Все интерфейсы собраны
- [ ] Status: up/down/disabled
- [ ] IP-адреса на SVI интерфейсах
- [ ] MAC-адреса интерфейсов
- [ ] Speed/Duplex заполнены
- [ ] hardware_type заполнен (для определения типа в NetBox)
- [ ] media_type заполнен (SFP тип)

### 5. Inventory коллектор
```bash
python -m network_collector inventory --format json
```
- [ ] Chassis собран с серийником
- [ ] Модули/линейные карты собраны
- [ ] SFP трансиверы собраны (если есть)
- [ ] Поля: name, pid, vid, serial, description
- [ ] manufacturer определяется по PID

### 6. NetBox синхронизация
```bash
# Всё с --dry-run сначала!
python -m network_collector sync-netbox --create-devices --dry-run
```
- [ ] Устройства определены для создания
- [ ] device_type определяется (не Unknown)
- [ ] site, role применяются из параметров

```bash
python -m network_collector sync-netbox --interfaces --dry-run
```
- [ ] Интерфейсы определены для создания/обновления
- [ ] Тип интерфейса определяется (1000base-t, 10gbase-sr, etc.)
- [ ] MAC-адреса готовы для привязки

```bash
python -m network_collector sync-netbox --ip-addresses --dry-run
```
- [ ] IP-адреса с SVI интерфейсов найдены
- [ ] Привязка к интерфейсам корректная

```bash
python -m network_collector sync-netbox --cables --protocol both --dry-run
```
- [ ] Кабели из LLDP/CDP определены
- [ ] Оба конца кабеля найдены в NetBox

```bash
python -m network_collector sync-netbox --vlans --site "SITE_NAME" --dry-run
```
- [ ] VLANs из SVI интерфейсов определены
- [ ] vid и name корректные

```bash
python -m network_collector sync-netbox --inventory --dry-run
```
- [ ] Inventory items определены
- [ ] manufacturer корректный

### 7. Полная синхронизация
```bash
python -m network_collector sync-netbox --sync-all --site "SITE" --role "switch" --dry-run
```
- [ ] Все этапы выполняются в правильном порядке
- [ ] Нет ошибок

### После тестирования (без --dry-run)
```bash
python -m network_collector sync-netbox --sync-all --site "SITE" --role "switch"
```
- [ ] Устройства созданы в NetBox
- [ ] Интерфейсы созданы с правильными типами
- [ ] IP-адреса привязаны
- [ ] Кабели созданы
- [ ] VLANs созданы
- [ ] Inventory items созданы

---

## Статус задач (2025-12-12)

| # | Задача | Статус |
|---|--------|--------|
| 1 | MAC + descriptions | ✅ Выполнено |
| 2 | Фильтры в yaml | ✅ Выполнено (уже были) |
| 3 | Defaults для экспорта | ✅ Выполнено |
| 4 | LLDP + remote_mac | ✅ Выполнено |
| 5 | Маппинги → constants.py | ✅ Выполнено |
| 6 | Документация | ✅ Выполнено |
| 7 | Кастомные TextFSM | ✅ Выполнено |

**Изменённые файлы:**
- `config.yaml` — добавлена секция `mac:` с настройками
- `config.py` — добавлены дефолты для секции `mac`
- `cli.py` — добавлены флаги `--no-descriptions`, `--exclude-trunk`, логика из config
- `fields.yaml` — включён `remote_mac` для LLDP
- `fields_config.py` — добавлена поддержка `default:` для экспорта
- `core/constants.py` — добавлены маппинги типов интерфейсов + `CUSTOM_TEXTFSM_TEMPLATES`
- `netbox/sync.py` — упрощена функция `_get_interface_type` (~100 строк вместо ~200)
- `parsers/textfsm_parser.py` — поддержка кастомных шаблонов
- `templates/` — папка для кастомных TextFSM шаблонов


---

### Задача 8: Рефакторинг device_type → platform (ЗАПЛАНИРОВАНО)

**Проблема:** Сейчас в `devices_ips.py` naming некорректный:
```python
# СЕЙЧАС (неправильно):
{
    "host": "10.177.30.243",
    "device_type": "cisco_iosxe",   # ← на самом деле это платформа (Scrapli/Netmiko)
    "platform": "C9200L-24P-4X",    # ← на самом деле это модель
}

# НАДО (правильно):
{
    "host": "10.177.30.243",
    "platform": "cisco_iosxe",      # ← платформа для подключения (Scrapli/Netmiko)
    "device_type": "C9200L-24P-4X", # ← модель устройства (для NetBox)
    "role": "Switch",
}
```

**Преимущества:**
- Семантически корректно (platform = драйвер, device_type = модель)
- Совместимо с NetBox (device_type = модель оборудования)
- Удобнее видеть какая модель в списке устройств
- Модель берётся из devices_ips, не нужен show version

**Затронутые файлы:**
| Файл | Что менять | Сложность |
|------|------------|-----------|
| `devices_ips.py` | Переименовать поля | Низкая |
| `core/device.py` | Класс Device, атрибуты | Средняя |
| `core/constants.py` | SCRAPLI_PLATFORM_MAP, NTC_PLATFORM_MAP | Низкая |
| `core/connection.py` | get_scrapli_platform(), get_ntc_platform() | Средняя |
| `collectors/*.py` | Все коллекторы используют device.device_type | Средняя |
| `configurator/description.py` | DescriptionPusher для Netmiko | Средняя |
| `netbox/sync.py` | create_device() | Низкая |
| `cli.py` | Парсинг устройств | Низкая |

**План реализации:**
1. [ ] Добавить в Device оба поля (platform для подключения, device_type для модели)
2. [ ] Обновить загрузку из devices_ips.py с поддержкой старого формата
3. [ ] Заменить использование device_type → platform для подключений
4. [ ] Протестировать на EVE-NG

**Сложность:** Средняя (2-3 часа)
**Статус:** ❌ Запланировано
