# Руководство по платформам и шаблонам

Полное описание цепочки: от добавления устройства до проверки вывода.

## Содержание

1. [Обзор цепочки](#1-обзор-цепочки)
2. [Добавление устройства](#2-добавление-устройства)
3. [Маппинг платформ](#3-маппинг-платформ)
4. [Команды для сбора данных](#4-команды-для-сбора-данных)
5. [TextFSM шаблоны](#5-textfsm-шаблоны)
6. [Нормализация данных](#6-нормализация-данных)
7. [Проверка вывода](#7-проверка-вывода)
8. [Пример: добавление QTech](#8-пример-добавление-qtech)
9. [Отладка проблем](#9-отладка-проблем)
10. [Рецепт: добавление нового TextFSM шаблона](#10-рецепт-добавление-нового-textfsm-шаблона-пошагово)
11. [QTech: специфика интерфейсов](#11-qtech-специфика-интерфейсов)
12. [Добавление нового вендора: полное руководство](#12-добавление-нового-вендора-полное-руководство)
13. [Inventory: show inventory vs transceiver](#1215-inventory-show-inventory-vs-show-interface-transceiver)
14. [QTech SVI: проверка VLAN интерфейсов](#1216-qtech-svi-добавление-vlan-интерфейсов)
15. [LLDP шаблоны и кабельная синхронизация](#1217-lldp-шаблоны-и-кабельная-синхронизация)
16. [UNIVERSAL_FIELD_MAP: нормализация имён полей NTC](#1219-universal_field_map-нормализация-имён-полей-ntc)

---

## 1. Обзор цепочки

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  1. УСТРОЙСТВО (devices_ips.py или devices.json)                                │
│     device_type: "qtech"  ←── платформа, определяет всё остальное               │
│     host: "192.168.1.1"                                                         │
└──────────────────────────────────┬──────────────────────────────────────────────┘
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  2. МАППИНГ ПЛАТФОРМ (core/constants/platforms.py)                              │
│     ┌─────────────────────────────────────────────────────────────────────────┐ │
│     │ SCRAPLI_PLATFORM_MAP:   qtech → cisco_iosxe  (SSH драйвер)              │ │
│     │ NTC_PLATFORM_MAP:       qtech → cisco_ios    (парсер по умолчанию)      │ │
│     │ NETMIKO_PLATFORM_MAP:   qtech → cisco_ios    (для конфигуратора)        │ │
│     │ NETBOX_TO_SCRAPLI:      qtech → cisco_ios    (импорт из NetBox)         │ │
│     └─────────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────┬──────────────────────────────────────────────┘
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  3. КОМАНДА ДЛЯ СБОРА (core/constants/commands.py)                              │
│     COLLECTOR_COMMANDS["mac"]["qtech"] = "show mac address-table"               │
└──────────────────────────────────┬──────────────────────────────────────────────┘
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  4. ПОДКЛЮЧЕНИЕ (collectors/base.py → core/connection.py)                       │
│     Scrapli подключается используя SCRAPLI_PLATFORM_MAP[device_type]            │
│     qtech → cisco_iosxe драйвер                                                 │
└──────────────────────────────────┬──────────────────────────────────────────────┘
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  5. ВЫПОЛНЕНИЕ КОМАНДЫ                                                          │
│     conn.send_command("show mac address-table")                                 │
│     Результат: сырой текст (raw output)                                         │
└──────────────────────────────────┬──────────────────────────────────────────────┘
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  6. ПАРСИНГ (parsers/textfsm_parser.py)                                         │
│     ┌─────────────────────────────────────────────────────────────────────────┐ │
│     │ Приоритет:                                                              │ │
│     │ 1. CUSTOM_TEXTFSM_TEMPLATES[(qtech, show mac address-table)]            │ │
│     │    → templates/qtech_show_mac_address_table.textfsm                     │ │
│     │                                                                         │ │
│     │ 2. Если нет кастомного → NTC Templates                                  │ │
│     │    NTC_PLATFORM_MAP[qtech] → cisco_ios                                  │ │
│     │    → ntc_templates cisco_ios_show_mac_address_table.textfsm             │ │
│     └─────────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────┬──────────────────────────────────────────────┘
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  7. НОРМАЛИЗАЦИЯ (core/domain/*_normalizer.py)                                  │
│     Приводит данные к единому формату независимо от платформы                   │
│     {"destination_address": "aa:bb:cc"} → {"mac": "AA:BB:CC:DD:EE:FF"}          │
└──────────────────────────────────┬──────────────────────────────────────────────┘
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  8. ЭКСПОРТ/СИНХРОНИЗАЦИЯ                                                       │
│     → JSON/Excel/CSV (exporters/)                                               │
│     → NetBox (netbox/sync/)                                                     │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Добавление устройства

### 2.1 Через devices_ips.py (для CLI)

```python
# devices_ips.py
devices_list = [
    {
        "host": "192.168.1.100",
        "platform": "qtech",          # ← платформа (SSH драйвер + парсер)
        "device_type": "QSW-3470-28T", # ← модель (для NetBox)
    },
    {
        "host": "192.168.1.101",
        "platform": "qtech_qsw",      # ← альтернативный тип для QTech QSW
        "device_type": "QSW-2800-28T",
        "role": "access-switch",       # ← роль в NetBox (опционально)
        "site": "DC-2",               # ← сайт в NetBox (опционально, per-device)
    },
]
# platform — определяет SSH драйвер и парсер (ключ для всех маппингов)
# site — если не указан, берётся из fields.yaml defaults.site или "Main"
```

### 2.2 Через data/devices.json (для Web UI)

```json
[
  {
    "name": "QTech-SW-01",
    "host": "192.168.1.100",
    "device_type": "qtech",
    "site": "Office"
  }
]
```

### 2.3 Поддерживаемые платформы (platform)

| platform | Описание | SSH драйвер | Парсер |
|-------------|----------|-------------|--------|
| `cisco_ios` | Cisco IOS | cisco_iosxe | cisco_ios |
| `cisco_iosxe` | Cisco IOS-XE | cisco_iosxe | cisco_ios |
| `cisco_nxos` | Cisco Nexus | cisco_nxos | cisco_nxos |
| `arista_eos` | Arista EOS | arista_eos | arista_eos |
| `juniper_junos` | Juniper | juniper_junos | juniper_junos |
| `qtech` | QTech | cisco_iosxe | cisco_ios* |
| `qtech_qsw` | QTech QSW | cisco_iosxe | cisco_ios* |

\* С кастомными шаблонами если зарегистрированы

---

## 3. Маппинг платформ

### 3.1 Файл: `core/constants/platforms.py`

#### SCRAPLI_PLATFORM_MAP — SSH драйвер

Определяет какой Scrapli драйвер использовать для подключения:

```python
SCRAPLI_PLATFORM_MAP: Dict[str, str] = {
    "cisco_ios": "cisco_iosxe",
    "cisco_iosxe": "cisco_iosxe",
    "cisco_nxos": "cisco_nxos",
    "arista_eos": "arista_eos",
    "juniper_junos": "juniper_junos",
    # QTech использует cisco-подобный CLI
    "qtech": "cisco_iosxe",
    "qtech_qsw": "cisco_iosxe",
}
```

#### NTC_PLATFORM_MAP — парсер по умолчанию

Если нет кастомного шаблона, какой NTC Templates использовать:

```python
NTC_PLATFORM_MAP: Dict[str, str] = {
    "cisco_iosxe": "cisco_ios",
    "cisco_ios": "cisco_ios",
    "cisco_nxos": "cisco_nxos",
    "arista_eos": "arista_eos",
    # QTech fallback на cisco_ios
    "qtech": "cisco_ios",
    "qtech_qsw": "cisco_ios",
}
```

#### NETMIKO_PLATFORM_MAP — для ConfigPusher

Используется при отправке конфигурации через Netmiko:

```python
NETMIKO_PLATFORM_MAP: Dict[str, str] = {
    "cisco_iosxe": "cisco_ios",
    "qtech": "cisco_ios",
    "qtech_qsw": "cisco_ios",
}
```

#### VENDOR_MAP — определение производителя

Для Inventory и логов:

```python
VENDOR_MAP: Dict[str, List[str]] = {
    "cisco": ["cisco_ios", "cisco_iosxe", "cisco_nxos"],
    "arista": ["arista_eos"],
    "juniper": ["juniper", "juniper_junos"],
    "qtech": ["qtech", "qtech_qsw"],
}
```

#### DEFAULT_PLATFORM — платформа по умолчанию

Используется как fallback когда платформа не указана:

```python
DEFAULT_PLATFORM = "cisco_ios"
```

Используется в: `core/connection.py`, `cli/utils.py`, `api/routes/device_management.py`.

> **Важно:** `core/connection.py` импортирует `SCRAPLI_PLATFORM_MAP` и `NTC_PLATFORM_MAP`
> из `core/constants/platforms.py` — не дублирует, а использует единый источник.

### 3.2 Как добавить новую платформу

```python
# 1. SCRAPLI_PLATFORM_MAP — SSH драйвер
"eltex": "cisco_iosxe",  # CLI как Cisco

# 2. NTC_PLATFORM_MAP — парсер fallback
"eltex": "cisco_ios",

# 3. NETMIKO_PLATFORM_MAP — для конфигуратора
"eltex": "cisco_ios",

# 4. VENDOR_MAP — производитель
"eltex": ["eltex", "eltex_mes"],

# 5. Если у платформы свой формат LAG (не Port-channel/Po):
#    core/constants/interfaces.py → is_lag_name() — добавить новый префикс
#    core/constants/interfaces.py → INTERFACE_SHORT_MAP, INTERFACE_FULL_MAP

# 6. Если LLDP System Description содержит имя вендора:
#    core/domain/lldp.py → _PLATFORM_PATTERNS — добавить запись
```

---

## 4. Команды для сбора данных

### 4.1 Файл: `core/constants/commands.py`

```python
COLLECTOR_COMMANDS: Dict[str, Dict[str, str]] = {
    # MAC-адреса
    "mac": {
        "cisco_ios": "show mac address-table",
        "cisco_iosxe": "show mac address-table",
        "cisco_nxos": "show mac address-table",
        "arista_eos": "show mac address-table",
        "juniper_junos": "show ethernet-switching table",
        "qtech": "show mac address-table",
        "qtech_qsw": "show mac address-table",
    },
    # Интерфейсы
    "interfaces": {
        "cisco_ios": "show interfaces",
        "qtech": "show interface",
    },
    # LLDP
    "lldp": {
        "cisco_ios": "show lldp neighbors detail",
        "qtech": "show lldp neighbors detail",
    },
    # Version (devices)
    "devices": {
        "cisco_ios": "show version",
        "qtech": "show version",
    },
    # Inventory
    "inventory": {
        "cisco_ios": "show inventory",
    },
}
# Примечание: QTech НЕ поддерживает show inventory.
# Inventory SFP модулей собирается через SECONDARY_COMMANDS["transceiver"].
```

### 4.2 Как узнать команду для коллектора

```python
from network_collector.core.constants import get_collector_command

command = get_collector_command("mac", "qtech")
# Результат: "show mac address-table"
```

### 4.3 Как добавить команду для новой платформы

```python
# core/constants/commands.py
COLLECTOR_COMMANDS["mac"]["eltex"] = "show mac address-table"
COLLECTOR_COMMANDS["interfaces"]["eltex"] = "show interfaces"
# и т.д.
```

---

## 5. TextFSM шаблоны

### 5.1 Приоритет парсинга

```
1. Кастомный шаблон в CUSTOM_TEXTFSM_TEMPLATES
   ↓ если не найден
2. NTC Templates (с маппингом через NTC_PLATFORM_MAP)
```

### 5.2 Регистрация кастомных шаблонов

**Файл:** `core/constants/commands.py`

```python
CUSTOM_TEXTFSM_TEMPLATES: Dict[tuple, str] = {
    # Формат: (платформа, команда): "имя_файла.textfsm"

    # Cisco port-security
    ("cisco_ios", "port-security"): "cisco_ios_port_security.textfsm",

    # QTech шаблоны
    ("qtech", "show mac address-table"): "qtech_show_mac_address_table.textfsm",
    ("qtech_qsw", "show mac address-table"): "qtech_show_mac_address_table.textfsm",
    ("qtech", "show version"): "qtech_show_version.textfsm",
    ("qtech_qsw", "show version"): "qtech_show_version.textfsm",
    ("qtech", "show interface"): "qtech_show_interface.textfsm",
    ("qtech_qsw", "show interface"): "qtech_show_interface.textfsm",
    ("qtech", "show lldp neighbors detail"): "qtech_show_lldp_neighbors_detail.textfsm",
    ("qtech_qsw", "show lldp neighbors detail"): "qtech_show_lldp_neighbors_detail.textfsm",
}
```

**Важно:**
- Ключ `(платформа, команда)` должен точно совпадать
- Платформа — device_type устройства (lowercase)
- Команда — команда из COLLECTOR_COMMANDS (lowercase)
- Файл шаблона должен лежать в `templates/`

### 5.3 Расположение шаблонов

```
network_collector/
└── templates/
    ├── cisco_ios_port_security.textfsm
    ├── qtech_show_mac_address_table.textfsm
    ├── qtech_show_version.textfsm
    ├── qtech_show_interface.textfsm
    ├── qtech_show_interface_status.textfsm
    ├── qtech_show_interface_switchport.textfsm
    ├── qtech_show_interface_transceiver.textfsm
    ├── qtech_show_lldp_neighbors_detail.textfsm
    └── qtech_show_aggregatePort_summary.textfsm
```

### 5.4 Структура TextFSM шаблона

```textfsm
# qtech_show_mac_address_table.textfsm
Value Required VLAN (\d+)
Value Required MAC ([0-9a-fA-F]{4}\.[0-9a-fA-F]{4}\.[0-9a-fA-F]{4})
Value Required INTERFACE (\S+)
Value TYPE (\S+)

Start
  ^${VLAN}\s+${MAC}\s+${TYPE}\s+${INTERFACE} -> Record
  ^\s*$$
  ^. -> Error
```

### 5.5 Как добавить новый шаблон

1. **Создать файл шаблона:**
   ```bash
   vim templates/myplatform_show_command.textfsm
   ```

2. **Зарегистрировать в CUSTOM_TEXTFSM_TEMPLATES:**
   ```python
   ("myplatform", "show command"): "myplatform_show_command.textfsm",
   ```

3. **Проверить:**
   ```bash
   python -m network_collector mac --format json
   ```

---

## 6. Нормализация данных

### 6.1 Файл: `parsers/textfsm_parser.py`

Универсальный маппинг полей приводит разные названия к стандартным:

```python
UNIVERSAL_FIELD_MAP = {
    "hostname": ["hostname", "host", "switchname", "device_id"],
    "mac": ["mac", "mac_address", "destination_address"],
    "vlan": ["vlan", "vlan_id"],
    "interface": ["interface", "port", "destination_port"],
    "neighbor": ["neighbor", "neighbor_id", "device_id", "remote_system_name"],
    # ...
}
```

### 6.2 Domain Normalizers

Более глубокая нормализация в `core/domain/`:

| Файл | Что нормализует |
|------|-----------------|
| `interface_normalizer.py` | Имена интерфейсов, скорости, типы |
| `mac_normalizer.py` | MAC-адреса (форматы) |
| `lldp_normalizer.py` | LLDP/CDP соседей |
| `inventory_normalizer.py` | Inventory данные |

---

## 7. Проверка вывода

### 7.1 Сырой текст с устройства (run --format raw)

Показывает что вернуло устройство **без парсинга** (только для команды `run`):

```bash
# Текстовый вывод с устройства (только run)
python -m network_collector run "show mac address-table" --format raw
python -m network_collector run "show interfaces" --format raw
```

> **Примечание:** `--format raw` для команд devices/mac/lldp/interfaces/inventory
> выводит **нормализованные** данные в JSON формате в stdout (не сырой текст).

### 7.2 После парсинга TextFSM (--format parsed)

Показывает данные **сразу после TextFSM парсинга**, до нормализации и обогащения.
Полезно для отладки шаблонов и проверки что парсер возвращает:

```bash
# Данные TextFSM без нормализации
python -m network_collector mac --format parsed
python -m network_collector interfaces --format parsed
python -m network_collector lldp --format parsed
python -m network_collector inventory --format parsed

# С pretty-print
python -m network_collector mac --format parsed | jq '.[0] | keys'
```

Что пропускается при `--format parsed`:
- Domain Layer нормализация (InterfaceNormalizer, MACNormalizer и т.д.)
- Обогащение данных (LAG, switchport, media_type)
- Фильтрация fields.yaml (apply_fields_config)
- Дополнительные SSH команды (show interfaces status, show interfaces trunk)

### 7.3 После нормализации (json / raw)

`--format json` и `--format raw` выводят **полностью обработанные** данные
(после нормализации Domain Layer + фильтрация fields.yaml):

```bash
# JSON файл с метаданными (в reports/)
python -m network_collector interfaces --format json

# JSON в stdout (для pipeline)
python -m network_collector interfaces --format raw

# Проверить конкретные поля
python -m network_collector interfaces --format raw | jq '.[0] | keys'
```

### 7.4 Сравнение parsed vs normalized

```bash
# 1. Данные TextFSM (до нормализации)
python -m network_collector mac --format parsed > parsed.json

# 2. Нормализованные данные
python -m network_collector mac --format raw > normalized.json

# 3. Сравнить ключи — они будут разные!
diff <(jq -S '.[0] | keys' parsed.json) <(jq -S '.[0] | keys' normalized.json)

# 4. Сырой текст (только через run)
python -m network_collector run "show mac address-table" --format raw > raw_text.txt
```

### 7.5 Таблица форматов

| Формат | Данные | Вывод | Для чего |
|--------|--------|-------|----------|
| `parsed` | После TextFSM, до нормализации | stdout (JSON) | Отладка шаблонов |
| `raw` | Нормализованные + fields.yaml | stdout (JSON) | Pipeline, скрипты |
| `json` | Нормализованные + fields.yaml | файл reports/ | Сохранение |
| `csv` | Нормализованные + fields.yaml | файл reports/ | Таблицы |
| `excel` | Нормализованные + fields.yaml | файл reports/ | Отчёты |

### 7.5 Проверка какой шаблон используется

Включить debug логирование:

```bash
# В config.yaml
logging:
  level: DEBUG

# Или через переменную окружения
LOG_LEVEL=DEBUG python -m network_collector mac --format json
```

В логах будет видно:
```
DEBUG - Используем кастомный шаблон: qtech_show_mac_address_table.textfsm
# или
DEBUG - Используем NTC Templates: cisco_ios/show mac address-table
```

### 7.6 Тестирование шаблона вручную

```python
import textfsm

# Загрузить сырой вывод
with open("raw_output.txt") as f:
    raw = f.read()

# Загрузить шаблон
with open("templates/qtech_show_mac_address_table.textfsm") as f:
    template = textfsm.TextFSM(f)

# Распарсить
result = template.ParseText(raw)

# Посмотреть результат
print("Headers:", template.header)
for row in result:
    print(row)
```

---

## 8. Пример: добавление QTech

### 8.1 Что уже сделано

#### Маппинги (`core/constants/platforms.py`):
```python
SCRAPLI_PLATFORM_MAP = {"qtech": "cisco_iosxe", "qtech_qsw": "cisco_iosxe"}
NTC_PLATFORM_MAP = {"qtech": "cisco_ios", "qtech_qsw": "cisco_ios"}
NETMIKO_PLATFORM_MAP = {"qtech": "cisco_ios", "qtech_qsw": "cisco_ios"}
VENDOR_MAP = {"qtech": ["qtech", "qtech_qsw"]}
```

#### Команды (`core/constants/commands.py`):
```python
COLLECTOR_COMMANDS = {
    "mac": {"qtech": "show mac address-table", "qtech_qsw": "show mac address-table"},
    "interfaces": {"qtech": "show interface", "qtech_qsw": "show interface"},
    "lldp": {"qtech": "show lldp neighbors detail", "qtech_qsw": "show lldp neighbors detail"},
    "devices": {"qtech": "show version", "qtech_qsw": "show version"},
    # Примечание: QTech НЕ поддерживает show inventory.
    # Inventory SFP собирается через SECONDARY_COMMANDS["transceiver"]:
    # "qtech": "show interface transceiver", "qtech_qsw": "show interface transceiver"
}
```

#### Кастомные шаблоны (`core/constants/commands.py`):
```python
CUSTOM_TEXTFSM_TEMPLATES = {
    ("qtech", "show mac address-table"): "qtech_show_mac_address_table.textfsm",
    ("qtech_qsw", "show mac address-table"): "qtech_show_mac_address_table.textfsm",
    ("qtech", "show version"): "qtech_show_version.textfsm",
    ("qtech_qsw", "show version"): "qtech_show_version.textfsm",
    ("qtech", "show interface"): "qtech_show_interface.textfsm",
    ("qtech_qsw", "show interface"): "qtech_show_interface.textfsm",
    ("qtech", "show lldp neighbors detail"): "qtech_show_lldp_neighbors_detail.textfsm",
    ("qtech_qsw", "show lldp neighbors detail"): "qtech_show_lldp_neighbors_detail.textfsm",
    # Дополнительные шаблоны
    ("qtech", "show interface status"): "qtech_show_interface_status.textfsm",
    ("qtech_qsw", "show interface status"): "qtech_show_interface_status.textfsm",
    ("qtech", "show interface switchport"): "qtech_show_interface_switchport.textfsm",
    ("qtech_qsw", "show interface switchport"): "qtech_show_interface_switchport.textfsm",
    ("qtech", "show interface transceiver"): "qtech_show_interface_transceiver.textfsm",
    ("qtech_qsw", "show interface transceiver"): "qtech_show_interface_transceiver.textfsm",
    # LAG (AggregatePort)
    ("qtech", "show aggregateport summary"): "qtech_show_aggregatePort_summary.textfsm",
    ("qtech_qsw", "show aggregateport summary"): "qtech_show_aggregatePort_summary.textfsm",
}
```

#### Файлы шаблонов (`templates/`):
```
templates/
├── qtech_show_mac_address_table.textfsm
├── qtech_show_version.textfsm
├── qtech_show_interface.textfsm
├── qtech_show_interface_status.textfsm
├── qtech_show_interface_switchport.textfsm
├── qtech_show_interface_transceiver.textfsm
├── qtech_show_lldp_neighbors_detail.textfsm
└── qtech_show_aggregatePort_summary.textfsm
```

### 8.2 Проверка QTech

```bash
# 1. Добавить устройство
vim devices_ips.py
# devices_list = [{"device_type": "qtech", "host": "192.168.x.x"}]

# 2. Проверить сырой вывод
python -m network_collector run "show version" --format raw

# 3. Проверить парсинг
python -m network_collector devices --format json

# 4. Проверить MAC
python -m network_collector mac --format json

# 5. Проверить интерфейсы
python -m network_collector interfaces --format json

# 6. Проверить LLDP
python -m network_collector lldp --format json
```

---

## 9. Отладка проблем

### 9.1 Устройство не подключается

```bash
# Проверить SSH вручную
ssh admin@192.168.1.100

# Проверить маппинг платформы
python -c "
from network_collector.core.constants import SCRAPLI_PLATFORM_MAP
print(SCRAPLI_PLATFORM_MAP.get('qtech'))
"
# Должно быть: cisco_iosxe
```

### 9.2 Парсинг возвращает пустой результат

```bash
# 1. Проверить что команда правильная
python -c "
from network_collector.core.constants import get_collector_command
print(get_collector_command('mac', 'qtech'))
"

# 2. Проверить сырой вывод
python -m network_collector run "show mac address-table" --format raw > raw.txt
cat raw.txt

# 3. Проверить регистрацию шаблона
python -c "
from network_collector.core.constants import CUSTOM_TEXTFSM_TEMPLATES
print(CUSTOM_TEXTFSM_TEMPLATES.get(('qtech', 'show mac address-table')))
"

# 4. Проверить существование файла шаблона
ls -la templates/qtech_show_mac_address_table.textfsm
```

### 9.3 Шаблон не парсит данные

```bash
# Тестировать шаблон вручную
python << 'EOF'
import textfsm

raw = open("raw.txt").read()
print("=== RAW OUTPUT ===")
print(raw[:500])

with open("templates/qtech_show_mac_address_table.textfsm") as f:
    template = textfsm.TextFSM(f)

result = template.ParseText(raw)
print("\n=== PARSED ===")
print("Headers:", template.header)
for row in result[:5]:
    print(row)
EOF
```

### 9.4 Проверить весь pipeline

```bash
# Включить debug
LOG_LEVEL=DEBUG python -m network_collector mac --format json 2>&1 | head -100
```

### 9.5 Тесты

```bash
# Запустить тесты QTech
pytest tests/ -k qtech -v

# Запустить тесты парсеров
pytest tests/test_parsers/ -v

# Запустить тесты с фикстурами
pytest tests/test_collectors/ -v
```

---

## 10. Рецепт: добавление нового TextFSM шаблона (пошагово)

Когда на реальном устройстве появляется новый вывод, который не парсится или парсится
неправильно — нужно добавить/обновить TextFSM шаблон. Вот универсальный рецепт.

### 10.1 Когда нужен новый шаблон

- NTC Templates не имеет шаблона для вашей платформы/команды (QTech, Eltex и т.д.)
- NTC шаблон парсит неправильно (формат вывода отличается от Cisco)
- Появился новый вывод, который раньше не встречался (например, тегированные VLAN)
- Формат данных изменился с новой прошивкой

### 10.2 Шаг 1: Сохранить сырой вывод с устройства

```bash
# Получить сырой текст (run --format raw)
python -m network_collector run "show interface switchport" --format raw > raw_switchport.txt

# Или скопировать вывод из SSH-сессии вручную
```

### 10.3 Шаг 2: Создать фикстуру для тестов

Сохранить реальный вывод в `tests/fixtures/<platform>/`:

```bash
cp raw_switchport.txt tests/fixtures/qtech/show_interface_switchport.txt
```

**Важно:** Фикстура — это точная копия вывода с устройства. Она гарантирует,
что шаблон будет работать с реальными данными.

### 10.4 Шаг 3: Написать TextFSM шаблон

Создать файл в `templates/`:

```textfsm
# templates/qtech_show_interface_switchport.textfsm

# 1. Объявить поля (Value)
Value Required INTERFACE (\S+\s+\d+(?:/\d+)?)
Value SWITCHPORT (enabled|disabled)
Value MODE (ACCESS|TRUNK|HYBRID)
Value ACCESS_VLAN (\d+)
Value NATIVE_VLAN (\d+)
Value PROTECTED (Enabled|Disabled)
Value VLAN_LISTS (\S+)

# 2. Правила парсинга
Start
  # Пропустить заголовок и разделитель
  ^Interface\s+Switchport -> Continue
  ^-+ -> Continue
  # Основная строка: все поля заполнены (enabled)
  ^${INTERFACE}\s+${SWITCHPORT}\s+${MODE}\s+${ACCESS_VLAN}\s+${NATIVE_VLAN}\s+${PROTECTED}\s+${VLAN_LISTS} -> Record
  # Строка disabled: только INTERFACE, SWITCHPORT и PROTECTED
  ^${INTERFACE}\s+${SWITCHPORT}\s+${PROTECTED}\s*$$ -> Record
```

**Основные правила TextFSM:**
- `Value Required FIELD (regex)` — обязательное поле, запись без него не создаётся
- `Value List FIELD (regex)` — поле-список (для множественных значений)
- `-> Record` — сохранить текущую запись и начать новую
- `-> Continue` — продолжить обработку строки (не переходить к следующей)
- `$$` — конец строки (экранированный `$` в TextFSM)
- `\s+` — один или более пробелов
- `\S+` — один или более непробельных символов

### 10.5 Шаг 4: Протестировать шаблон на фикстуре

```python
import textfsm
from pathlib import Path

template_path = Path("templates/qtech_show_interface_switchport.textfsm")
fixture_path = Path("tests/fixtures/qtech/show_interface_switchport.txt")

with open(template_path) as f:
    tpl = textfsm.TextFSM(f)

with open(fixture_path) as f:
    output = f.read()

result = tpl.ParseText(output)
headers = tpl.header

print(f"Распарсено записей: {len(result)}")
for row in result[:5]:
    print(dict(zip(headers, row)))
```

### 10.6 Шаг 5: Зарегистрировать шаблон

Добавить в `core/constants/commands.py` → `CUSTOM_TEXTFSM_TEMPLATES`:

```python
CUSTOM_TEXTFSM_TEMPLATES = {
    ...
    # Ключ: (платформа lowercase, команда lowercase)
    ("qtech", "show interface switchport"): "qtech_show_interface_switchport.textfsm",
    ("qtech_qsw", "show interface switchport"): "qtech_show_interface_switchport.textfsm",
}
```

**Важно:** Команда в ключе должна быть в **lowercase**. NTCParser автоматически
приводит команду к lowercase при поиске шаблона.

### 10.7 Шаг 6: Написать тесты

```python
# tests/test_qtech_templates.py

class TestQtechShowInterfaceSwitchport:
    def test_parse_switchport(self):
        result = parse_with_template(
            "qtech_show_interface_switchport.textfsm",
            "show_interface_switchport.txt"
        )
        assert len(result) > 0

        intf = result[0]
        assert "INTERFACE" in intf
        assert "MODE" in intf
        assert intf["MODE"] in ["ACCESS", "TRUNK", "HYBRID"]
```

### 10.8 Шаг 7: Проверить что парсер подхватывает шаблон

```bash
# 1. Проверить регистрацию
python -c "
from network_collector.core.constants import CUSTOM_TEXTFSM_TEMPLATES
key = ('qtech', 'show interface switchport')
print(CUSTOM_TEXTFSM_TEMPLATES.get(key, 'НЕ ЗАРЕГИСТРИРОВАН!'))
"

# 2. Проверить парсинг через NTCParser
python -c "
from network_collector.parsers.textfsm_parser import NTCParser
parser = NTCParser()
with open('tests/fixtures/qtech/show_interface_switchport.txt') as f:
    output = f.read()
result = parser.parse(output, 'qtech', 'show interface switchport')
print(f'Записей: {len(result)}')
for r in result[:3]:
    print(r)
"
```

### 10.9 Пример: добавление тегированных VLAN для QTech

Допустим, вы увидели на QTech вывод с тегированными VLAN:

```
Interface                        Switchport Mode   Access Native Protected VLAN lists
-------------------------------- ---------- ------ ------ ------ --------- ----------
TFGigabitEthernet 0/1            enabled    TRUNK  1      1      Disabled  10,20,30
AggregatePort 1                  enabled    TRUNK  1      1      Disabled  ALL
AggregatePort 10                 enabled    HYBRID 40     40     Disabled  10,20,30,40
```

**Что делать:**

1. Шаблон уже парсит VLAN_LISTS как `(\S+)` — значение `10,20,30` будет захвачено.
   Если VLAN на нескольких строках (перенос), нужен `Value List`.

2. Нормализация в `core/domain/interface.py` → `InterfaceNormalizer.normalize_switchport_data()`:
   - `MODE=TRUNK` + `VLAN_LISTS=ALL` → `mode="tagged-all"`, `vlans=[]`
   - `MODE=TRUNK` + `VLAN_LISTS=10,20,30` → `mode="tagged"`, `vlans=[10,20,30]`
   - `MODE=HYBRID` + `VLAN_LISTS=10,20,30,40` → `mode="tagged"`, `vlans=[10,20,30,40]`
   - `MODE=ACCESS` → `mode="access"`, `vlans=[access_vlan]`

3. Если формат VLAN отличается (например, через дефис `10-30`):
   Обновить `InterfaceNormalizer.normalize_switchport_data()` в `core/domain/interface.py` — добавить распарсивание диапазонов.

4. Если VLAN на нескольких строках, обновить TextFSM шаблон:
   ```textfsm
   Value List VLAN_LISTS (\S+)

   Start
     ^${INTERFACE}\s+${SWITCHPORT}\s+${MODE}\s+... -> Continue
     ^\s+${VLAN_LISTS} -> Continue
   ```

### 10.10 Цепочка данных: от TextFSM до NetBox

```
TextFSM шаблон парсит сырой текст
     ↓
NTCParser.parse() → список dict с полями шаблона
     ↓
InterfaceNormalizer.normalize_switchport_data() → единый формат {interface, mode, vlans}
     ↓
get_interface_aliases() (core/constants/interfaces.py) → алиасы имён интерфейсов
     ↓
enrich_with_switchport() (Domain Layer) → обогащает интерфейс
     ↓
NetBox sync → mode, tagged_vlans, untagged_vlan
```

Ключевой принцип: **TextFSM шаблон только парсит текст в структурированные данные**.
Вся логика нормализации, конвертации и обогащения — в Domain Layer (`core/domain/`).

---

## 11. QTech: специфика интерфейсов

### 11.1 Типы интерфейсов QTech

| Полное имя | Сокращение | Скорость | NetBox type | Примечание |
|------------|-----------|----------|-------------|-----------|
| TFGigabitEthernet 0/1 | TF0/1 | 25G | 25gbase-x-sfp28 | SFP28 порты |
| HundredGigabitEthernet 0/55 | Hu0/55 | 100G | 100gbase-x-qsfp28 | QSFP28 аплинки |
| AggregatePort 1 | Ag1 | — | lag | LAG (аналог Port-channel) |

**Важно:** QTech использует пробел между типом и номером: `TFGigabitEthernet 0/1`,
а не `TFGigabitEthernet0/1`. Это отличие от Cisco, где пробела нет.

### 11.2 Маппинг имён (`core/constants/interfaces.py`)

```python
# Сокращение → полное
INTERFACE_SHORT_MAP = [
    ("tfgigabitethernet", "TF"),   # QTech 25G
    ("aggregateport", "Ag"),       # QTech LAG
    ("hundredgigabitethernet", "Hu"),
    ...
]

# Полное → сокращение
INTERFACE_FULL_MAP = {
    "TF": "TFGigabitEthernet",
    "Ag": "AggregatePort",
    "Hu": "HundredGigE",
    ...
}
```

### 11.3 LAG парсинг для QTech

QTech использует `show aggregatePort summary` (вместо `show etherchannel summary`):

```
AggregatePort MaxPorts SwitchPort Mode   Load balance   Ports
------------- -------- ---------- ------ -------------- -----------
Ag1           16       Enabled    TRUNK  src-dst-mac    Hu0/55  ,Hu0/56
Ag10          16       Enabled    ACCESS src-dst-mac    TF0/1
```

Парсится через TextFSM шаблон `qtech_show_aggregatePort_summary.textfsm` →
`_parse_lag_membership_qtech()` создаёт маппинг member → LAG:

```python
{
    "Hu0/55": "Ag1",
    "HundredGigabitEthernet 0/55": "Ag1",   # Полное имя с пробелом
    "HundredGigE0/55": "Ag1",               # Полное имя без пробела
    "Hu0/56": "Ag1",
    "TF0/1": "Ag10",
    "TFGigabitEthernet 0/1": "Ag10",
}
```

### 11.4 Switchport парсинг для QTech

QTech выводит switchport в табличном формате (отличается от Cisco):

```
# QTech (табличный)
Interface                        Switchport Mode   Access Native Protected VLAN lists
TFGigabitEthernet 0/3            enabled    ACCESS 1      1      Disabled  ALL

# Cisco (блочный, через NTC Templates)
Name: Gi0/1
Switchport: Enabled
Administrative Mode: trunk
Operational Mode: trunk
Administrative Trunking Encapsulation: dot1q
Access Mode VLAN: 1
Trunking Native Mode VLAN: 1
Trunking VLANs Enabled: 10,20,30
```

Универсальная функция `InterfaceNormalizer.normalize_switchport_data()` (в `core/domain/interface.py`)
обрабатывает оба формата автоматически, определяя формат по наличию характерных полей.

### 11.5 TextFSM: show interface и administratively down

QTech `show interface` имеет особенности:

**1. Пробелы в именах:** `TFGigabitEthernet 0/1` (с пробелом) — TextFSM шаблон использует `\S+\s+\d+(?:/\d+)?` для захвата. Нормализатор (`_normalize_row`) убирает пробел: `TFGigabitEthernet0/1`.

**2. Статус administratively down:** QTech возвращает `administratively down` вместо просто `DOWN` для административно выключенных портов:

```
TFGigabitEthernet 0/3 is administratively down  , line protocol is DOWN
```

TextFSM шаблон (`qtech_show_interface.textfsm`):
```
Value LINK_STATUS ((?:administratively\s+)?(?:UP|DOWN|up|down))
```

Цепочка нормализации: `"administratively down"` → STATUS_MAP → `"disabled"` → NetBox: `enabled=False`.

**3. Функции нормализации имён:** Обе функции убирают пробелы:
- `normalize_interface_short()` — `interface.replace(" ", "")` на входе
- `normalize_interface_full()` — `interface.replace(" ", "")` на входе

Это критически важно для `_find_interface()` при синхронизации кабелей (LLDP), где имена приходят с пробелами.

---

## 12. Добавление нового вендора: полное руководство

Пошаговая инструкция на примере условного **Eltex MES** — что доработать, где, и какой код
написать. Все примеры из реального проекта (QTech, Cisco).

### 12.1 Оценка сложности: 3 уровня

Перед началом определите, насколько устройство похоже на Cisco:

| Уровень | Описание | Примеры | Объём работ |
|---------|----------|---------|-------------|
| **Cisco-like** | CLI и формат вывода почти как Cisco IOS | Eltex MES (IOS-like) | Только маппинги, шаблоны NTC работают |
| **Частично уникальный** | Команды те же, но формат вывода отличается | QTech QSW-6900 | + кастомные TextFSM шаблоны + парсинг LAG/switchport |
| **Полностью уникальный** | Другой CLI, другие команды | Juniper JunOS, Huawei VRP | + свои команды + свои парсеры + своя нормализация |

### 12.2 Шаг 1: Маппинги платформ

**Файл:** `core/constants/platforms.py`

Добавить новую платформу во **все 4 маппинга**:

```python
# 1. SSH драйвер (Scrapli)
# Какой SSH драйвер использовать для подключения?
SCRAPLI_PLATFORM_MAP = {
    ...
    "eltex": "cisco_iosxe",       # Eltex CLI как Cisco IOS
    "eltex_mes": "cisco_iosxe",   # Вариант с подтипом
}

# 2. NTC Templates (парсер по умолчанию)
# Если нет кастомного шаблона — какой NTC парсер использовать?
NTC_PLATFORM_MAP = {
    ...
    "eltex": "cisco_ios",         # Fallback: NTC Templates для cisco_ios
    "eltex_mes": "cisco_ios",
}

# 3. Netmiko (для отправки конфигурации)
NETMIKO_PLATFORM_MAP = {
    ...
    "eltex": "cisco_ios",
    "eltex_mes": "cisco_ios",
}

# 4. Определение производителя (для inventory, логов)
VENDOR_MAP = {
    ...
    "eltex": ["eltex", "eltex_mes"],  # Уже существует!
}
```

**Также:** `NETBOX_TO_SCRAPLI_PLATFORM` — для импорта устройств из NetBox:

```python
NETBOX_TO_SCRAPLI_PLATFORM = {
    ...
    "eltex": "cisco_ios",
    "eltex-mes": "cisco_ios",       # NetBox slug с дефисом
    "eltex_mes": "cisco_ios",       # С underscore
}
```

> **Вопрос:** Как выбрать SSH драйвер?
> - Если CLI как Cisco IOS (prompt `Switch#`, `enable`, `show`) → `cisco_iosxe`
> - Если CLI как Juniper (`>`, `cli`, `show`) → `juniper_junos`
> - Если CLI как Arista (`Switch#`, `enable`, `show`) → `arista_eos`

### 12.3 Шаг 2: Команды сбора данных

**Файл:** `core/constants/commands.py`

Добавить команды для каждого коллектора:

```python
COLLECTOR_COMMANDS = {
    # Какая команда для MAC-адресов?
    "mac": {
        ...
        "eltex": "show mac address-table",       # Как Cisco
        "eltex_mes": "show mac address-table",
    },
    # Какая команда для интерфейсов?
    "interfaces": {
        ...
        "eltex": "show interfaces",              # show interfaces (с 's')? или show interface?
        "eltex_mes": "show interfaces",
    },
    # LLDP
    "lldp": {
        ...
        "eltex": "show lldp neighbors detail",
        "eltex_mes": "show lldp neighbors detail",
    },
    # CDP
    "cdp": {
        ...
        "eltex": "show cdp neighbors detail",
        "eltex_mes": "show cdp neighbors detail",
    },
    # Devices (show version)
    "devices": {
        ...
        "eltex": "show version",
        "eltex_mes": "show version",
    },
    # Inventory
    "inventory": {
        ...
        "eltex": "show inventory",
        "eltex_mes": "show inventory",
    },
}
```

> **Как узнать команду?** Подключиться к устройству по SSH и попробовать стандартные Cisco-команды.
> Если формат вывода совпадает — NTC шаблон подхватит автоматически.

### 12.4 Шаг 3: Проверить — нужны ли кастомные TextFSM шаблоны

Запустить сбор данных с `--format parsed` и проверить результат:

```bash
# 1. Сохранить сырой вывод
python -m network_collector run "show version" --format raw > raw_version.txt

# 2. Попробовать парсинг (fallback на NTC cisco_ios)
python -m network_collector devices --format parsed

# 3. Если результат пустой или неправильный — нужен кастомный шаблон
```

**Когда кастомный шаблон НЕ нужен:**
- Вывод команды идентичен Cisco IOS → NTC Templates парсит корректно

**Когда кастомный шаблон НУЖЕН:**
- Вывод отличается (другой формат таблицы, другие поля, другие заголовки)
- NTC Templates не имеет шаблона для этой команды
- Пример: QTech `show interface` — формат почти как Cisco, но `Interface address is:` вместо `Internet address is`

Если нужен — см. [раздел 10](#10-рецепт-добавление-нового-textfsm-шаблона-пошагово).

### 12.5 Шаг 4: Команды и шаблоны для сбора интерфейсов

#### Сводная таблица: что нужно для sync интерфейсов

Интерфейсный коллектор выполняет **до 4 SSH-команд** на каждое устройство.
Только первая (основная) обязательна. Остальные — дополнительные: если для платформы
нет команды, коллектор **просто пропускает** этот этап и идёт дальше.

| # | Данные | Команда (Cisco) | Команда (QTech) | Обязат.? | Что даёт для NetBox |
|---|--------|-----------------|-----------------|----------|---------------------|
| 1 | **Основные** (имя, статус, скорость, описание, MAC, MTU, IP) | `show interfaces` | `show interface` | **Да** | Создание/обновление интерфейсов |
| 2 | **LAG membership** (какой порт в каком LAG) | `show etherchannel summary` | `show aggregatePort summary` | Нет | Поле `lag` (parent interface) |
| 3 | **Switchport mode** (access/trunk, VLAN) | `show interfaces switchport` | `show interface switchport` | Нет | Поля `mode`, `untagged_vlan`, `tagged_vlans` |
| 4 | **Media type** (тип SFP модуля) | IOS: из основной `show interfaces`; NX-OS: `show interface status` | `show interface transceiver` | Нет | Точный `type` порта (10gbase-sr vs generic 10gbase-x-sfpp) |

**Что будет если шаблон не добавить:**
- Нет шаблона для команды 1 (основной) → **интерфейсы не соберутся вообще**
- Нет шаблона для команды 2 (LAG) → интерфейсы соберутся, но без привязки к LAG
- Нет шаблона для команды 3 (switchport) → интерфейсы соберутся, но без VLAN и mode
- Нет шаблона для команды 4 (media_type) → тип порта определяется по имени (fallback: `GigabitEthernet` → `1000base-t`)

#### Как это работает: полная цепочка вызовов

Рассмотрим пошагово, что происходит когда вы запускаете:

```bash
python -m network_collector sync-netbox --interfaces
```

**Шаг 1. Инициализация коллектора** (`collectors/interfaces.py`, `__init__`)

```python
class InterfacesCollector(BaseCollector):
    # Атрибуты класса — берут команды из SECONDARY_COMMANDS
    lag_commands = SECONDARY_COMMANDS.get("lag", {})
    switchport_commands = SECONDARY_COMMANDS.get("switchport", {})
    media_type_commands = SECONDARY_COMMANDS.get("media_type", {})

    def __init__(
        self,
        collect_lag_info: bool = True,       # Собирать LAG? По умолчанию — да
        collect_switchport: bool = True,     # Собирать switchport? По умолчанию — да
        collect_media_type: bool = True,     # Собирать media_type? По умолчанию — да
        **kwargs,
    ):
```

Обратите внимание: все три флага **по умолчанию включены** (`True`).
Они НЕ берутся из `fields.yaml` — это параметры конструктора.

`SECONDARY_COMMANDS` — это словарь в `core/constants/commands.py`, где для каждой
группы данных (lag, switchport, media_type) указаны команды для каждой платформы:

```python
# core/constants/commands.py
SECONDARY_COMMANDS = {
    "lag": {
        "cisco_ios": "show etherchannel summary",
        "cisco_nxos": "show port-channel summary",
        "qtech": "show aggregatePort summary",
        "qtech_qsw": "show aggregatePort summary",
        ...
    },
    "switchport": {
        "cisco_ios": "show interfaces switchport",
        "cisco_nxos": "show interface switchport",   # NX-OS: без 's'
        "qtech": "show interface switchport",
        "qtech_qsw": "show interface switchport",
        ...
    },
    "media_type": {
        # Cisco IOS/IOS-XE: НЕ нужен — media_type из основной show interfaces
        "cisco_nxos": "show interface status",
        "qtech": "show interface transceiver",
        "qtech_qsw": "show interface transceiver",
    },
}
```

Если платформы нет в словаре — `.get(device.platform)` вернёт `None`, и команда
просто не выполнится. Это **нормально** — для Cisco IOS/IOS-XE media_type уже
приходит из основной команды `show interfaces` (NTC шаблон содержит поле `MEDIA_TYPE`).

**Шаг 2. Сбор данных с устройства** (`collectors/interfaces.py`, `_collect_from_device`)

Вот полная логика сбора. Каждый блок — независимый, ошибки одного не ломают остальные:

```
SSH-подключение к устройству
│
├─ 1. Основная команда (ОБЯЗАТЕЛЬНАЯ)
│     conn.send_command("show interfaces")
│     → _parse_output() → TextFSM/regex → сырые данные
│     → normalizer.normalize_dicts() → нормализованные данные
│
├─ 2. LAG membership (ОПЦИОНАЛЬНАЯ)
│     if collect_lag_info:                              # флаг включён?
│         lag_cmd = lag_commands.get(device.platform)    # есть команда для платформы?
│         if lag_cmd:                                    # если есть — выполняем
│             conn.send_command(lag_cmd)
│             → _parse_lag_membership() → {порт: LAG}
│         # Если нет команды — lag_membership = {} (пустой)
│
├─ 3. Switchport modes (ОПЦИОНАЛЬНАЯ)
│     if collect_switchport:                             # флаг включён?
│         sw_cmd = switchport_commands.get(platform)     # есть команда?
│         if sw_cmd:                                     # если есть — выполняем
│             conn.send_command(sw_cmd)
│             → _parse_switchport_modes() → {порт: {mode, vlans}}
│         # Если нет команды — switchport_modes = {} (пустой)
│
├─ 4. Media type (ОПЦИОНАЛЬНАЯ)
│     if collect_media_type:                             # флаг включён?
│         mt_cmd = media_type_commands.get(platform)     # есть команда?
│         if mt_cmd:                                     # если есть — выполняем
│             conn.send_command(mt_cmd)
│             → _parse_media_types() → {порт: тип}
│         # Если нет команды — media_types = {} (пустой)
│
└─ 5. Обогащение (Domain Layer)
      if lag_membership:     → normalizer.enrich_with_lag()
      if switchport_modes:   → normalizer.enrich_with_switchport()
      if media_types:        → normalizer.enrich_with_media_type()
```

**Ключевой момент:** каждый блок защищён **тройной проверкой**:

1. **Флаг включён?** (`collect_lag_info`, `collect_switchport`, `collect_media_type`) —
   если `False`, блок полностью пропускается
2. **Есть команда для платформы?** (`lag_commands.get(device.platform)`) —
   если платформы нет в `SECONDARY_COMMANDS`, команда не выполняется
3. **try/except** — если SSH-команда или парсинг упали с ошибкой, результат
   просто `{}` (пустой), и коллектор продолжает работу

Поэтому **для новой платформы достаточно добавить только основной шаблон** —
интерфейсы соберутся. Дополнительные шаблоны добавляются по мере необходимости.

**Шаг 3. Парсинг команд — как выбирается шаблон**

Каждая SSH-команда парсится через `TextFSMParser.parse()` (`parsers/textfsm_parser.py`).
Парсер выбирает шаблон по приоритету:

```
1. Кастомный шаблон (CUSTOM_TEXTFSM_TEMPLATES)
   Ключ: (platform, command) → файл шаблона
   Пример: ("qtech", "show interface switchport") → "qtech_show_interface_switchport.textfsm"
   Если найден → парсит и возвращает результат
   │
   ↓ (если не найден или результат пустой)

2. NTC Templates (стандартная библиотека)
   Платформа маппится через NTC_PLATFORM_MAP: "qtech" → "cisco_ios"
   Парсит как будто это Cisco
   │
   ↓ (если тоже пусто)

3. Regex fallback (только для основной команды show interfaces)
   Ручной парсинг регулярками
```

**Пример для QTech `show interface switchport`:**

```python
# core/constants/commands.py → CUSTOM_TEXTFSM_TEMPLATES
CUSTOM_TEXTFSM_TEMPLATES = {
    ("qtech", "show interface switchport"): "qtech_show_interface_switchport.textfsm",
    ...
}
```

Парсер видит ключ `("qtech", "show interface switchport")` в `CUSTOM_TEXTFSM_TEMPLATES`,
находит файл `templates/qtech_show_interface_switchport.textfsm`, парсит через него.
NTC Templates **не используется** — кастомный шаблон имеет приоритет.

**Пример для Cisco IOS `show interfaces switchport`:**

Ключа `("cisco_ios", "show interfaces switchport")` в `CUSTOM_TEXTFSM_TEMPLATES` нет.
Парсер переходит к NTC Templates, который имеет стандартный шаблон для этой команды.

**Шаг 4. Нормализация — где какая логика**

После парсинга сырые данные нужно нормализовать. Вся нормализация в **Domain Layer**:

| Данные | Функция | Файл | Что делает |
|--------|---------|------|------------|
| Основные | `normalize_dicts()` | `core/domain/interface.py` | Статус, скорость, описание, MAC, тип порта |
| LAG | `enrich_with_lag()` | `core/domain/interface.py` | Добавляет поле `lag` к member-портам |
| Switchport | `normalize_switchport_data()` → `enrich_with_switchport()` | `core/domain/interface.py` | Нормализует mode из разных форматов, добавляет VLANs |
| Media type | `enrich_with_media_type()` | `core/domain/interface.py` | Уточняет тип порта (SFP, copper) |

Коллектор **только парсит** (SSH → TextFSM/regex → словари). Вся логика
нормализации и обогащения — в `InterfaceNormalizer`.

#### Подробно: каждая дополнительная команда

#### 4a. LAG Membership

**Зачем:** Чтобы в NetBox у физического порта (например `GigabitEthernet0/1`) было
заполнено поле `LAG` (например `Port-channel1`).

**Цепочка вызовов:**

```
SSH: "show etherchannel summary" (Cisco) / "show aggregatePort summary" (QTech)
  ↓
TextFSMParser.parse(output, platform, command)
  ↓ (кастомный шаблон или NTC)
_parse_lag_membership() или _parse_lag_membership_qtech()
  ↓
Dict[str, str]  →  {"GigabitEthernet0/1": "Port-channel1", "Gi0/1": "Port-channel1"}
  ↓
normalizer.enrich_with_lag(data, lag_membership)
  ↓
Каждому интерфейсу добавляется поле "lag": "Port-channel1"
```

```python
# core/constants/commands.py → SECONDARY_COMMANDS["lag"]
SECONDARY_COMMANDS["lag"] = {
    "cisco_ios": "show etherchannel summary",
    "cisco_iosxe": "show etherchannel summary",
    "cisco_nxos": "show port-channel summary",
    "arista_eos": "show port-channel summary",
    "qtech": "show aggregatePort summary",
    "qtech_qsw": "show aggregatePort summary",
}
```

> **Если формат вывода как у Cisco** — парсинг через NTC Templates работает автоматически.
> **Если формат уникальный** (как QTech) — нужен кастомный шаблон + парсер `_parse_lag_membership_<vendor>()`.

Пример из QTech — кастомный парсер:

```python
# collectors/interfaces.py
def _parse_lag_membership_qtech(self, output: str) -> Dict[str, str]:
    """Парсинг LAG membership из show aggregatePort summary (QTech)."""
    parsed = self._parser.parse(
        output=output,
        platform="qtech",
        command="show aggregateport summary",
    )
    membership = {}
    for entry in parsed:
        lag_name = entry.get("AGGREGATE_PORT", "")
        members = entry.get("MEMBER_PORTS", [])
        if isinstance(members, str):
            members = [m.strip() for m in members.split(",") if m.strip()]
        for member in members:
            self._add_lag_member_aliases(membership, member, lag_name)
    return membership
```

#### 4b. Switchport Modes (для VLAN)

**Зачем:** Чтобы в NetBox у интерфейса были заполнены поля `mode` (access/tagged/tagged-all),
`untagged_vlan` и `tagged_vlans`.

**Цепочка вызовов:**

```
SSH: "show interfaces switchport" (Cisco) / "show interface switchport" (QTech)
  ↓
TextFSMParser.parse(output, platform, command)
  ↓ (кастомный шаблон или NTC)
_parse_switchport_modes(output, platform, command)
  ↓
Попытка 1: TextFSM парсинг → normalizer.normalize_switchport_data()
Попытка 2: Regex fallback → _parse_switchport_modes_regex()
  ↓
Dict[str, Dict[str, str]]  →  {
    "GigabitEthernet0/1": {"mode": "access", "access_vlan": "10", ...},
    "Gi0/1":              {"mode": "access", "access_vlan": "10", ...},  # алиас
}
  ↓
normalizer.enrich_with_switchport(data, switchport_modes, lag_membership)
  ↓
Каждому интерфейсу добавляются поля "mode", "untagged_vlan", "tagged_vlans"
```

```python
# core/constants/commands.py → SECONDARY_COMMANDS["switchport"]
SECONDARY_COMMANDS["switchport"] = {
    "cisco_ios": "show interfaces switchport",   # Cisco: с 's'
    "cisco_nxos": "show interface switchport",   # NX-OS: без 's'
    "arista_eos": "show interfaces switchport",
    "qtech": "show interface switchport",        # QTech: без 's'
    "qtech_qsw": "show interface switchport",
}
```

Нормализация switchport данных — **универсальная** (`InterfaceNormalizer.normalize_switchport_data()`
в `core/domain/interface.py`), поддерживает три формата платформ:

```python
# 1. Cisco IOS / Arista — NTC формат (поле admin_mode):
{"admin_mode": "trunk", "native_vlan": "1", "trunking_vlans": "10,20,30"}

# 2. Cisco NX-OS — NTC формат (поля mode + trunking_vlans):
{"mode": "trunk", "trunking_native_vlan": "1", "trunking_vlans": "1-4094"}

# 3. QTech — кастомный шаблон (поле switchport):
{"switchport": "Enabled", "MODE": "TRUNK", "NATIVE_VLAN": "1", "VLAN_LISTS": "ALL"}
```

Если ваш вендор возвращает один из этих форматов — работает автоматически.
Если другой формат — добавить условие в `InterfaceNormalizer.normalize_switchport_data()`.

#### 4c. Media Type / Transceiver (опционально)

**Зачем:** Чтобы в NetBox тип порта был **точным** (`10gbase-sr` для SR-модуля, а не
generic `10gbase-x-sfpp`). Без media_type тип определяется только по имени интерфейса (fallback).

**Источники media_type по платформам:**

| Платформа | Команда | Формат полей | Пример TYPE |
|-----------|---------|-------------|-------------|
| NX-OS | `show interface status` | NTC: `port`, `type` | `10Gbase-SR` |
| QTech | `show interface transceiver` | TextFSM: `INTERFACE`, `TYPE` | `10GBASE-SR-SFP+` |

**Цепочка вызовов:**

```
SSH: "show interface status" (NX-OS) или "show interface transceiver" (QTech)
  ↓
NTCParser.parse(output, platform, command)
  ↓
_parse_media_types(output, platform, command)
  поля: port/INTERFACE → имя интерфейса, type/TYPE → тип трансивера
  ↓
Dict[str, str]  →  {"Ethernet1/1": "10Gbase-SR"} или {"TFGigabitEthernet 0/1": "10GBASE-SR-SFP+"}
  ↓
get_interface_aliases() генерирует ВСЕ варианты имени:
  "TFGigabitEthernet 0/1"  (оригинал с пробелом)
  "TFGigabitEthernet0/1"   (без пробела — для матчинга!)
  "TF0/1"                   (короткая форма)
  ↓
normalizer.enrich_with_media_type(data, media_types)
  интерфейсы уже нормализованы (пробелы убраны в _normalize_row())
  ищет "TFGigabitEthernet0/1" в media_types → НАЙДЕНО (через alias)
  ↓
detect_port_type() → пересчитывает port_type по media_type
```

> **ВАЖНО (QTech):** TextFSM шаблон `qtech_show_interface_transceiver.textfsm` возвращает
> имена с пробелом (`TFGigabitEthernet 0/1`). Нормализатор убирает пробелы
> (`TFGigabitEthernet0/1`). Матчинг работает благодаря `get_interface_aliases()`,
> который создаёт ключи для ОБОИХ вариантов. См. подробную цепочку в `docs/BUGFIX_LOG.md` (Баг 5).

```python
# core/constants/commands.py → SECONDARY_COMMANDS["media_type"]
SECONDARY_COMMANDS["media_type"] = {
    "cisco_nxos": "show interface status",
    "qtech": "show interface transceiver",
    "qtech_qsw": "show interface transceiver",
}
```

**Двухуровневый маппинг: port_type vs NetBox type**

Media_type используется на **двух уровнях**, и это даёт разные результаты:

```
Уровень 1 — Collector (port_type, грубая категория):
  "10GBASE-SR-SFP+" → _detect_from_media_type() → "10g-sfp+" (содержит "10gbase")

Уровень 2 — NetBox Sync (точный тип для API):
  "10GBASE-SR-SFP+" → NETBOX_INTERFACE_TYPE_MAP → "10gbase-sr" (паттерн "10gbase-sr" найден!)
```

Вот как это работает для QTech до и после добавления media_type:

| | Без media_type | С media_type (transceiver) |
|---|---|---|
| **Источник** | Имя интерфейса | `show interface transceiver` → TYPE |
| **Данные** | `TFGigabitEthernet 0/1` | `10GBASE-SR-SFP+` |
| **port_type** | `25g-sfp28` (по имени) | `10g-sfp+` (по media_type — трансивер) |
| **NetBox type** | `25gbase-x-sfp28` (generic SFP28) | `10gbase-sr` (**ТОЧНЫЙ** 10GBASE-SR!) |

Разница: `get_netbox_interface_type()` проверяет media_type по `NETBOX_INTERFACE_TYPE_MAP`
**до** проверки port_type. Паттерн `"10gbase-sr"` совпадает с `"10gbase-sr-sfp+"` и
возвращает конкретный NetBox тип `"10gbase-sr"` вместо generic `"10gbase-x-sfpp"`.

**Если платформы нет** в `SECONDARY_COMMANDS["media_type"]` — тип порта определяется
по имени интерфейса (fallback):
- `GigabitEthernet` → `1000base-t`
- `TenGigabitEthernet` → `10gbase-x-sfpp`
- `TFGigabitEthernet` (QTech 25G) → `25gbase-x-sfp28`

**Как добавить media_type для новой платформы:**

1. Определить команду, которая возвращает тип трансивера
2. Создать TextFSM шаблон (если NTC не поддерживает) с полями `INTERFACE` и `TYPE`
3. Зарегистрировать шаблон в `CUSTOM_TEXTFSM_TEMPLATES`
4. Добавить платформу в `SECONDARY_COMMANDS["media_type"]`
5. Убедиться что значение TYPE содержит паттерн из `NETBOX_INTERFACE_TYPE_MAP`
   (например "10gbase-sr", "1000base-lx" и т.д.)

#### 4d. Готовые платформы и кастомные шаблоны

**Какие платформы можно подключить прямо сейчас (NTC шаблоны уже есть):**

| Платформа | Команда | NTC шаблон | Поля | Готовность |
|-----------|---------|------------|------|------------|
| `cisco_nxos` | `show interface status` | `cisco_nxos_show_interface_status.textfsm` | `port`, `type` | ✅ Подключено |
| `qtech` | `show interface transceiver` | кастомный `qtech_show_interface_transceiver.textfsm` | `INTERFACE`, `TYPE` | ✅ Подключено |
| `cisco_ios` | — | — | — | ✅ Не нужен (media_type из основной `show interfaces`) |
| `cisco_iosxe` | — | — | — | ✅ Не нужен (media_type из основной `show interfaces`) |
| `arista_eos` | — | — | — | Не используется |

**Почему Cisco IOS/IOS-XE не нужна доп. команда:**

На Cisco IOS основная команда `show interfaces` уже возвращает поле `MEDIA_TYPE`
в NTC шаблоне (например `"SFP-10GBase-SR"`, `"10/100/1000BaseTX"`). Оно попадает
в данные через `_normalize_row()` и используется в `detect_port_type()` и
`get_netbox_interface_type()`. Дополнительная команда была бы лишним SSH запросом.

На NX-OS `show interface` возвращает media_type как `"10G"` (только скорость) —
бесполезно. Поэтому нужна отдельная команда `show interface status` → `"10Gbase-LR"`.

Текущий конфиг:

```python
SECONDARY_COMMANDS["media_type"] = {
    "cisco_nxos": "show interface status",
    "qtech": "show interface transceiver",
    "qtech_qsw": "show interface transceiver",
}
```

**Кастомная настройка:** Можно добавить любую платформу в `SECONDARY_COMMANDS["media_type"]`,
даже если media_type уже приходит из основной команды. Например, для Cisco IOS/IOS-XE
или Arista EOS:

```python
"media_type": {
    "cisco_nxos": "show interface status",
    "cisco_ios": "show interfaces status",      # опционально (данные уже в show interfaces)
    "cisco_iosxe": "show interfaces status",    # опционально (данные уже в show interfaces)
    "arista_eos": "show interfaces status",     # опционально (NTC шаблон готов)
    "qtech": "show interface transceiver",
    "qtech_qsw": "show interface transceiver",
}
```

Механизм `enrich_with_media_type()` перезапишет media_type только если новое значение
более информативно (содержит "base", "sfp" или "qsfp"). Для Cisco IOS это лишний SSH
запрос, но технически будет работать.

**ВНИМАНИЕ: Cisco IOS `show interface transceiver` НЕ подходит!**

На Cisco IOS команда `show interface transceiver` возвращает **только оптические
параметры** (температура, напряжение, мощность TX/RX). Поля TYPE нет:

```
                                           Optical   Optical
           Temperature  Voltage  Current   Tx Power  Rx Power
Port       (Celsius)    (Volts)  (mA)      (dBm)     (dBm)
---------  -----------  -------  --------  --------  --------
Gi1/0/1    29.3         3.27     5.2       -5.5      -7.2
```

Это **не то же самое** что QTech `show interface transceiver`, который возвращает
`Transceiver Type: 10GBASE-SR-SFP+`. На Cisco IOS тип трансивера находится в
`show interfaces status` (поле Type: "10GBase-SR SFP+", "1000BaseSX SFP" и т.д.).

#### 4e. Кастомный TextFSM шаблон для media_type

Если для вашей платформы **нет** готового NTC шаблона с типом трансивера, нужно
создать кастомный TextFSM шаблон. Вот пошаговая инструкция.

**Требования к шаблону:**

Метод `_parse_media_types()` ожидает от шаблона **два поля** (одна из пар):

| Пара полей | Формат | Кто использует |
|------------|--------|---------------|
| `port` + `type` | NTC (lowercase) | Cisco NX-OS, IOS, Arista |
| `INTERFACE` + `TYPE` | TextFSM (UPPERCASE) | QTech (кастомный шаблон) |

Код определяет поля автоматически:
```python
# collectors/interfaces.py → _parse_media_types()
port = row.get("port") or row.get("INTERFACE", "")
media_type = row.get("type") or row.get("TYPE", "")
```

**Пример: создание кастомного шаблона**

Допустим, у вашего вендора команда `show transceiver detail` возвращает:

```
Interface     Type              Serial          Status
---------     ----              ------          ------
Gi1/0/1       1000BASE-LX SFP   AGM1234567      OK
Te1/0/1       10GBASE-SR SFP+   FNS5678901      OK
```

Шаг 1: Создать файл `templates/<vendor>_show_transceiver_detail.textfsm`:

```
Value INTERFACE (\S+)
Value TYPE (.+?)
Value SERIAL (\S+)
Value STATUS (\S+)

Start
  ^-+
  ^\s*${INTERFACE}\s+${TYPE}\s+${SERIAL}\s+${STATUS}\s*$$ -> Record
```

Шаг 2: Зарегистрировать в `core/constants/commands.py`:

```python
# SECONDARY_COMMANDS
"media_type": {
    "<vendor>": "show transceiver detail",
},

# CUSTOM_TEXTFSM_TEMPLATES
("<vendor>", "show transceiver detail"): "<vendor>_show_transceiver_detail.textfsm",
```

Шаг 3: Готово! `_parse_media_types()` найдёт поля `INTERFACE` и `TYPE` автоматически.

**Значения TYPE — что должен возвращать шаблон:**

Чтобы маппинг в NetBox тип работал правильно, значение TYPE должно содержать один
из паттернов `NETBOX_INTERFACE_TYPE_MAP` (`core/constants/netbox.py`). Примеры:

| Значение TYPE от устройства | Найденный паттерн | NetBox тип |
|-----------------------------|-------------------|------------|
| `10GBASE-SR-SFP+` | `10gbase-sr` | `10gbase-sr` |
| `10GBase-LR` | `10gbase-lr` | `10gbase-lr` |
| `1000BaseSX SFP` | `1000basesx` | `1000base-sx` |
| `1000BaseLX/LH` | `1000baselx` | `1000base-lx` |
| `SFP-10GBase-SR` | `sfp-10gbase-sr` | `10gbase-sr` |
| `10/100/1000BaseTX` | _(нет паттерна)_ | fallback на port_type |

Если значение TYPE не совпадает ни с одним паттерном — используется fallback
на `PORT_TYPE_MAP` (port_type → generic NetBox тип). Список всех паттернов
смотри в `NETBOX_INTERFACE_TYPE_MAP` (~80 записей).

#### Итого: что добавлять для новой платформы

**Минимум (только основные данные):**
1. Команда в `DEVICE_COMMANDS["interfaces"]` → `core/constants/commands.py`
2. Кастомный шаблон `templates/<platform>_show_interface.textfsm` (если формат не как у Cisco)
3. Регистрация в `CUSTOM_TEXTFSM_TEMPLATES` → `core/constants/commands.py`

**Полный набор (все данные для NetBox):**

| Шаг | Файл | Что добавить |
|-----|------|-------------|
| Основная команда | `core/constants/commands.py` | `DEVICE_COMMANDS["interfaces"]["<platform>"]` |
| Основной шаблон | `templates/` | `<platform>_show_interface.textfsm` |
| LAG команда | `core/constants/commands.py` | `SECONDARY_COMMANDS["lag"]["<platform>"]` |
| LAG шаблон | `templates/` | `<platform>_show_<lag_command>.textfsm` (если формат не как у Cisco) |
| Switchport команда | `core/constants/commands.py` | `SECONDARY_COMMANDS["switchport"]["<platform>"]` |
| Switchport шаблон | `templates/` | `<platform>_show_interface_switchport.textfsm` (если формат не как у Cisco) |
| Media type команда | `core/constants/commands.py` | `SECONDARY_COMMANDS["media_type"]["<platform>"]` |
| Media type шаблон | `templates/` | Шаблон для соответствующей команды |
| Регистрация всех | `core/constants/commands.py` | Каждый кастомный шаблон в `CUSTOM_TEXTFSM_TEMPLATES` |

### 12.6 Шаг 5: Имена интерфейсов

**Файл:** `core/constants/interfaces.py`

Если вендор использует **нестандартные имена** интерфейсов — добавить в маппинги:

```python
# 1. Полное → короткое (для нормализации)
# Порядок важен! Длинные имена ПЕРВЫМИ
INTERFACE_SHORT_MAP = [
    ...
    ("tfgigabitethernet", "TF"),  # QTech 25G: TFGigabitEthernet 0/1 → TF0/1
    ("aggregateport", "Ag"),      # QTech LAG: AggregatePort 1 → Ag1
    # Eltex пример (если есть уникальные имена):
    # ("extremeethernet", "Xe"),  # Eltex Extreme: ExtremeEthernet 0/1 → Xe0/1
]

# 2. Короткое → полное (для обратной нормализации)
INTERFACE_FULL_MAP = {
    ...
    "TF": "TFGigabitEthernet",
    "Ag": "AggregatePort",
    # "Xe": "ExtremeEthernet",  # Eltex пример
}
```

**Если Eltex использует стандартные Cisco имена** (GigabitEthernet, TenGigabitEthernet,
Port-channel) — ничего добавлять не нужно, маппинги уже есть.

### 12.7 Шаг 6: Определение типа порта для NetBox

Если вендор имеет **уникальные имена интерфейсов**, нужно добавить логику в 2 функции:

#### 6a. `detect_port_type()` — Domain Layer

**Файл:** `core/domain/interface.py`

```python
def detect_port_type(self, row, iface_lower):
    # LAG — единый источник: is_lag_name() из core/constants/interfaces.py
    if is_lag_name(iface_lower):
        return "lag"
    # Для нового LAG формата: добавить в is_lag_name()

    # Виртуальные интерфейсы (VIRTUAL_INTERFACE_PREFIXES из core/constants/netbox.py)
    # Включает: vlan, loopback, lo, null, tunnel, nve
    if iface_lower.startswith(VIRTUAL_INTERFACE_PREFIXES):
        return "virtual"

    # По media_type, hardware_type (data-driven маппинги)
    # → _detect_from_media_type()  — итерация MEDIA_TYPE_PORT_TYPE_MAP
    # → _detect_from_hardware_type() — итерация HARDWARE_TYPE_PORT_TYPE_MAP

    # По имени интерфейса (data-driven)
    # → _detect_from_interface_name() — итерация INTERFACE_NAME_PORT_TYPE_MAP
    # Для нового типа: добавить в INTERFACE_NAME_PORT_TYPE_MAP (core/constants/interfaces.py)
```

#### 6b. `get_netbox_interface_type()` — NetBox Layer

**Файл:** `core/constants/netbox.py`

```python
def get_netbox_interface_type(interface_name, media_type, hardware_type, port_type, speed_mbps, ...):
    name_lower = interface_name.lower()

    # LAG — единый источник: is_lag_name()
    if is_lag_name(name_lower) or port_type == "lag":
        return "lag"

    # Приоритеты: media_type → port_type → hardware_type → имя → speed
    # media_type → NETBOX_INTERFACE_TYPE_MAP (точный тип трансивера)
    # port_type → PORT_TYPE_MAP (нормализованный из коллектора)
    # Для нового вендора: если стандартные имена — ничего добавлять не нужно
    # Если уникальные имена — добавить в INTERFACE_NAME_PORT_TYPE_MAP (core/constants/interfaces.py)
    # и PORT_TYPE_MAP (core/constants/netbox.py) для конвертации в NetBox тип
```

**Если Eltex использует стандартные имена** — ничего добавлять не нужно.

### 12.7.1 Определение скорости для down-портов

Когда интерфейс admin up / link down, устройство не возвращает реальную negotiated
скорость. TextFSM захватывает `speed = ""` / `"Unknown"` / `"Auto-speed"`.

**Как работает:**

```
TextFSM → speed="Auto-speed", hardware="Gigabit Ethernet"
    ↓
detect_port_type() → port_type="1g-rj45" (из hardware/имени)
    ↓
speed в _UNKNOWN_SPEED_VALUES? → ДА
    ↓
get_nominal_speed_from_port_type("1g-rj45") → "1000000 Kbit" (1G)
    ↓
Результат: speed = "1000000 Kbit" (номинальная скорость порта)
```

**Приоритет:**

1. **LAG UP** (`port_type="lag"`, status="up") → bandwidth (агрегатная скорость, сумма members)
2. **UP-порт с реальной скоростью** (`"1000Mb/s"`, `"10G"`) → используется как есть
3. **DOWN-порт** (`speed` пустой/unknown/auto) → номинальная из `port_type`
4. **Virtual** (`port_type="virtual"`) → speed остаётся пустым

**Откуда берётся номинальная скорость:**

Парсится из префикса `port_type` — **отдельный маппинг не нужен**:

| port_type | Префикс | Номинальная скорость |
|-----------|---------|---------------------|
| `1g-rj45` | `1g` | 1000000 Kbit (1 Gbps) |
| `1g-sfp` | `1g` | 1000000 Kbit (1 Gbps) |
| `10g-sfp+` | `10g` | 10000000 Kbit (10 Gbps) |
| `25g-sfp28` | `25g` | 25000000 Kbit (25 Gbps) |
| `40g-qsfp` | `40g` | 40000000 Kbit (40 Gbps) |
| `100g-qsfp28` | `100g` | 100000000 Kbit (100 Gbps) |
| `100m-rj45` | `100m` | 100000 Kbit (100 Mbps) |
| `lag` | — | пусто (не физический порт) |
| `virtual` | — | пусто (не физический порт) |

**Поведение по платформам:**

| Платформа | Интерфейс | Статус | speed TextFSM | Результат в NetBox |
|-----------|-----------|--------|--------------|-------------------|
| Cisco IOS | Gi1/0/2 | UP, 1G | `"1000Mb/s"` | 1G — реальная |
| Cisco IOS | Gi1/0/1 | UP, 100M | `"100Mb/s"` | 100M — реальная |
| Cisco IOS | Gi1/0/4 | DOWN | `"Auto-speed"` | **1G — номинальная** |
| Cisco IOS | Te1/1/3 | DOWN | `"Auto-speed"` | **10G — номинальная** |
| QTech | TFGi 0/1 | UP | `"10G"` | 10G — реальная |
| QTech | TFGi 0/3 | DOWN | `"Unknown"` | **25G — номинальная** |
| NX-OS | Eth1/2 | UP | `"10 Gb/s"` | 10G — реальная |
| NX-OS | Eth1/7 | DOWN | `"auto-speed"` | **25G — номинальная** |
| NX-OS | mgmt0 | DOWN | `"auto-speed"` | **1G — номинальная** |

**Ключевые файлы:**

| Файл | Что делает |
|------|-----------|
| `core/constants/interfaces.py` | `_UNKNOWN_SPEED_VALUES` — набор значений speed, не содержащих реальной скорости |
| `core/constants/interfaces.py` | `get_nominal_speed_from_port_type()` — парсит `"1g-rj45"` → `"1000000 Kbit"` |
| `core/domain/interface.py` | `_normalize_row()` — подставляет номинальную если speed неизвестен |
| `core/models.py` | `Interface.from_dict()` — НЕ использует bandwidth как fallback |

**При добавлении новой платформы:**

Если новый port_type следует формату `{число}{g|m}-{коннектор}` (напр. `5g-rj45`),
номинальная скорость подхватится автоматически. Ничего дополнительно настраивать не нужно.

### 12.8 Шаг 7: Алиасы интерфейсов для LAG matching

**Файл:** `core/constants/interfaces.py` → `get_interface_aliases()`

Когда LAG парсер возвращает `"TF0/1"`, а основной список интерфейсов содержит
`"TFGigabitEthernet 0/1"` — нужно сопоставить. Функция `get_interface_aliases()` генерирует
все варианты имени:

```python
get_interface_aliases("TF0/1")
# → ["TF0/1", "TFGigabitEthernet0/1"]

get_interface_aliases("Hu0/55")
# → ["Hu0/55", "HundredGigE0/55", "HundredGigabitEthernet0/55"]
```

Если ваш вендор использует уникальные сокращения, добавьте в `SHORT_TO_EXTRA`:

```python
# core/constants/interfaces.py
SHORT_TO_EXTRA = {
    "gi": ["Gig"],              # Gi → Gig (CDP формат)
    "te": ["Ten"],              # Te → Ten
    "hu": ["HundredGigabitEthernet"],  # Hu → HundredGigabitEthernet (QTech LLDP)
    "eth": ["Et"],
    "et": ["Eth"],
    # "xe": ["ExtremeEthernet"],  # Eltex пример
}
```

### 12.9 Шаг 8: Фикстуры и тесты

#### 8a. Создать фикстуры из реального вывода

```bash
# Сохранить вывод с устройства
tests/fixtures/eltex/
├── show_version.txt                    # python -m network_collector run "show version" --format raw
├── show_interfaces.txt                 # python -m network_collector run "show interfaces" --format raw
├── show_interfaces_status.txt
├── show_interfaces_switchport.txt
├── show_mac_address_table.txt
├── show_lldp_neighbors_detail.txt
├── show_etherchannel_summary.txt       # LAG (если есть)
└── show_inventory.txt
```

#### 8b. Тесты TextFSM шаблонов

```python
# tests/test_eltex_templates.py
import textfsm
from pathlib import Path

TEMPLATE_DIR = Path(__file__).parent.parent / "templates"
FIXTURE_DIR = Path(__file__).parent / "fixtures" / "eltex"

def parse_with_template(template_name, fixture_name):
    """Парсит фикстуру через TextFSM шаблон."""
    with open(TEMPLATE_DIR / template_name) as t, open(FIXTURE_DIR / fixture_name) as f:
        tpl = textfsm.TextFSM(t)
        result = tpl.ParseText(f.read())
        return [dict(zip(tpl.header, row)) for row in result]

class TestEltexShowVersion:
    def test_parse_version(self):
        result = parse_with_template("eltex_show_version.textfsm", "show_version.txt")
        assert len(result) > 0
        assert "HOSTNAME" in result[0] or "VERSION" in result[0]
```

#### 8c. Тесты типов интерфейсов

```python
# tests/test_eltex_support.py
from network_collector.core.domain.interface import InterfaceNormalizer
from network_collector.core.constants.netbox import get_netbox_interface_type
from network_collector.core.constants.interfaces import (
    normalize_interface_short, normalize_interface_full,
)

class TestEltexInterfaceTypes:
    def test_detect_lag(self):
        normalizer = InterfaceNormalizer()
        # Если у Eltex LAG называется Port-channel (как Cisco)
        assert normalizer.detect_port_type({}, "port-channel1") == "lag"

    def test_netbox_type(self):
        assert get_netbox_interface_type("GigabitEthernet0/1") == "1000base-t"
```

### 12.10 Шаг 9: Inventory и IP адреса

#### Inventory

Команда `show inventory` обычно стандартная:
```
NAME: "1", DESCR: "MES2428 AC 28-port", PID: MES2428, VID: V01, SN: NQ12345678
```

Если формат как у Cisco — **работает через NTC fallback**, ничего не нужно.
Если формат другой — кастомный TextFSM шаблон + регистрация.

Manufacturer detection (`core/domain/inventory.py`):

```python
# Если PID устройства содержит "MES" или "Eltex" — автоматически определится?
# Нет! Нужно добавить паттерн:
MANUFACTURER_PATTERNS = {
    "Cisco": [...],
    "Eltex": ["MES", "ESR"],  # ← Добавить
}
```

#### IP адреса

IP адреса извлекаются из `show interfaces` → поле `ip_address`.
Regex Cisco формат: `Internet address is 10.0.0.1/24`.

Если ваш формат отличается — нужно обновить regex или TextFSM шаблон.

> **Примечание:** QTech physical порты не имеют IP (`Interface address is: no ip address`).
> IP только на VLAN SVI в `show running-config`. Для полной поддержки IP нужна
> отдельная команда (`show ip interface`) + парсер.

### 12.11 Шаг 10: Проверка на реальном устройстве

```bash
# 1. Добавить устройство в devices_ips.py
devices_list = [
    {"host": "10.0.0.1", "platform": "eltex", "device_type": "MES2428"},
]

# 2. Проверить подключение
python -m network_collector run "show version" --format raw

# 3. Проверить каждый коллектор поочерёдно
python -m network_collector devices --format parsed     # → hostname, model, serial
python -m network_collector interfaces --format parsed  # → интерфейсы
python -m network_collector mac --format parsed         # → MAC таблица
python -m network_collector lldp --format parsed        # → LLDP соседи
python -m network_collector inventory --format parsed   # → компоненты

# 4. Проверить обогащённые данные
python -m network_collector interfaces --format raw | jq '.[0]'
# Должны быть: port_type, nb_type, mode, lag (если есть)

# 5. Проверить sync в dry-run
python -m network_collector sync-netbox --interfaces --dry-run
python -m network_collector sync-netbox --sync-all --dry-run
```

### 12.12 Сводная таблица: что менять по коллекторам

| Коллектор | Файл команд | Доп. команды (SECONDARY_COMMANDS) | Нормализация | TextFSM |
|-----------|-------------|-----------------------------------|-------------|---------|
| **devices** | `COLLECTOR_COMMANDS["devices"]` | — | Автоматическая | Если формат ≠ Cisco |
| **interfaces** | `COLLECTOR_COMMANDS["interfaces"]` | — | `detect_port_type()`, `get_netbox_interface_type()` | Если формат ≠ Cisco |
| **mac** | `COLLECTOR_COMMANDS["mac"]` | — | Автоматическая (MAC format) | Если формат ≠ Cisco |
| **lldp** | `COLLECTOR_COMMANDS["lldp"]` | — | Автоматическая | Если формат ≠ Cisco |
| **inventory** | `COLLECTOR_COMMANDS["inventory"]` + `SECONDARY_COMMANDS["transceiver"]` | — | Manufacturer detection | Если формат ≠ Cisco |
| **LAG** | — | `SECONDARY_COMMANDS["lag"]` | `_parse_lag_membership()` | Если формат ≠ Cisco |
| **switchport** | — | `SECONDARY_COMMANDS["switchport"]` | `InterfaceNormalizer.normalize_switchport_data()` | Если формат ≠ Cisco |
| **media_type** | — | `SECONDARY_COMMANDS["media_type"]` | Автоматическая | Если формат ≠ NX-OS |
| **IP** | Из `show interfaces` | — | Regex | Если формат ≠ Cisco |

### 12.13 Минимальный набор для Cisco-like вендора

Если устройство полностью Cisco-like (как Eltex MES на базе IOS), достаточно:

```python
# core/constants/platforms.py (4 маппинга)
SCRAPLI_PLATFORM_MAP["eltex"] = "cisco_iosxe"
NTC_PLATFORM_MAP["eltex"] = "cisco_ios"
NETMIKO_PLATFORM_MAP["eltex"] = "cisco_ios"
VENDOR_MAP["eltex"] = ["eltex", "eltex_mes"]

# core/constants/commands.py (6 команд)
COLLECTOR_COMMANDS["mac"]["eltex"] = "show mac address-table"
COLLECTOR_COMMANDS["interfaces"]["eltex"] = "show interfaces"
COLLECTOR_COMMANDS["lldp"]["eltex"] = "show lldp neighbors detail"
COLLECTOR_COMMANDS["cdp"]["eltex"] = "show cdp neighbors detail"
COLLECTOR_COMMANDS["devices"]["eltex"] = "show version"
COLLECTOR_COMMANDS["inventory"]["eltex"] = "show inventory"

# core/constants/commands.py → SECONDARY_COMMANDS (3 доп. команды)
SECONDARY_COMMANDS["lag"]["eltex"] = "show etherchannel summary"
SECONDARY_COMMANDS["switchport"]["eltex"] = "show interfaces switchport"
```

**Итого:** ~12 строк конфигурации. Без единого кастомного шаблона или парсера.
Всё остальное работает через NTC Templates fallback на `cisco_ios`.

### 12.14 Максимальный набор для уникального вендора (на примере QTech)

Что потребовалось для QTech QSW-6900:

```
Файлы:
  core/constants/platforms.py     — 4 маппинга (SCRAPLI, NTC, NETMIKO, VENDOR)
  core/constants/commands.py      — 6 команд + 8 пар регистрации шаблонов
  core/constants/interfaces.py    — 2 записи SHORT_MAP + 2 записи FULL_MAP + SHORT_TO_EXTRA
  core/constants/netbox.py        — AggregatePort→lag, TFGigabitEthernet→25G
  core/domain/interface.py        — detect_port_type() для Ag/TF
  core/constants/commands.py      — SECONDARY_COMMANDS["lag"] + SECONDARY_COMMANDS["switchport"]
  collectors/interfaces.py        — _parse_lag_membership_qtech()

TextFSM шаблоны (8 файлов):
  qtech_show_version.textfsm
  qtech_show_interface.textfsm
  qtech_show_interface_status.textfsm
  qtech_show_interface_switchport.textfsm
  qtech_show_interface_transceiver.textfsm
  qtech_show_lldp_neighbors_detail.textfsm
  qtech_show_mac_address_table.textfsm
  qtech_show_aggregatePort_summary.textfsm

Тесты:
  tests/test_qtech_templates.py   — тесты всех шаблонов на фикстурах
  tests/test_qtech_support.py     — тесты типов, маппингов, LAG парсинга

Фикстуры (9 файлов в tests/fixtures/qtech/)
```

### 12.15 Inventory: show inventory vs show interface transceiver

Не все вендоры поддерживают `show inventory`. Есть два источника данных:

| Источник | Платформы | Что даёт |
|----------|-----------|----------|
| `show inventory` | Cisco IOS/NX-OS, Arista | Chassis, PSU, линейные карты + SFP |
| `show interface transceiver` | Cisco NX-OS, QTech | Только SFP модули (тип, серийник) |

**QTech:** Команда `show inventory` **не существует**. Inventory SFP модулей собирается
только через `show interface transceiver`:

```python
# core/constants/commands.py → SECONDARY_COMMANDS["transceiver"]
SECONDARY_COMMANDS["transceiver"] = {
    "cisco_nxos": "show interface transceiver",
    "qtech": "show interface transceiver",
    "qtech_qsw": "show interface transceiver",
}
```

Если у нового вендора нет `show inventory` — добавьте его в `SECONDARY_COMMANDS["transceiver"]`.
Inventory collector автоматически пропустит шаг `show inventory` и соберёт только трансиверы.

> **Важно:** Команда `show interface transceiver` используется **двумя коллекторами**:
> - **InventoryCollector** — для создания inventory items (SFP модули с серийниками)
> - **InterfaceCollector** — для определения media_type (точный тип порта в NetBox)
>
> Это две разные цепочки: InventoryCollector берёт команду из `SECONDARY_COMMANDS["transceiver"]`,
> InterfaceCollector — из `SECONDARY_COMMANDS["media_type"]`. Обе указывают на одну и ту же
> команду `show interface transceiver`, но парсят результат для разных целей.

### 12.16 QTech SVI: добавление VLAN интерфейсов

QTech поддерживает VLAN SVI (Switch Virtual Interface) — виртуальные L3 интерфейсы:

```
# Пример из show interface (QTech)
Vlan 1 is up, line protocol is up
  Interface address is: 10.0.0.3/24
```

Если `show interface` на QTech в проде показывает VLAN SVI с IP — они должны
парситься автоматически (шаблон `qtech_show_interface.textfsm` уже поддерживает).

**Как проверить:**

```bash
# 1. Снять вывод с устройства
python -m network_collector run "show interface" --format raw > raw_intf.txt

# 2. Проверить есть ли Vlan интерфейсы в выводе
grep -i "^Vlan" raw_intf.txt

# 3. Проверить парсинг
python -m network_collector interfaces --format parsed | jq '.[] | select(.interface | startswith("Vlan"))'

# 4. Если Vlan парсится — проверить sync в dry-run
python -m network_collector sync-netbox --interfaces --dry-run

# 5. Если Vlan НЕ парсится — сохранить вывод как фикстуру и обновить шаблон
cp raw_intf.txt tests/fixtures/qtech/show_interface_with_svi.txt
```

**Что проверить в NetBox:**

```bash
# Dry-run покажет какие интерфейсы будут созданы
python -m network_collector sync-netbox --interfaces --dry-run 2>&1 | grep -i vlan

# Vlan интерфейсы должны получить тип "virtual" в NetBox:
# - detect_port_type("vlan1") → "virtual"
# - get_netbox_interface_type("Vlan1") → "virtual"
```

**Если SVI есть в выводе, но шаблон не парсит:**

1. Сохранить вывод как фикстуру
2. Проверить шаблон `qtech_show_interface.textfsm` — возможно формат VLAN отличается
3. Обновить шаблон и тесты
4. IP адреса из SVI будут синхронизированы автоматически (если `ip_address` в результате)

---

## Чеклист добавления новой платформы

Подробности каждого шага — в [разделе 12](#12-добавление-нового-вендора-полное-руководство).

### Обязательно (для всех вендоров)

- [ ] `core/constants/platforms.py` — добавить в `SCRAPLI_PLATFORM_MAP` (SSH драйвер) [§12.2]
- [ ] `core/constants/platforms.py` — добавить в `NTC_PLATFORM_MAP` (парсер fallback) [§12.2]
- [ ] `core/constants/platforms.py` — добавить в `NETMIKO_PLATFORM_MAP` [§12.2]
- [ ] `core/constants/platforms.py` — добавить в `VENDOR_MAP` (производитель) [§12.2]
- [ ] `core/constants/platforms.py` — добавить в `NETBOX_TO_SCRAPLI_PLATFORM` [§12.2]
- [ ] `core/constants/commands.py` — добавить команды в `COLLECTOR_COMMANDS` (mac, interfaces, lldp, cdp, devices, inventory) [§12.3]
- [ ] `core/constants/commands.py` — добавить в `SECONDARY_COMMANDS` (lag, switchport и др.) [§12.5]
- [ ] `tests/fixtures/<platform>/` — фикстуры с реального устройства [§12.9]
- [ ] Проверить на реальном устройстве [§12.11]

### Если формат вывода отличается от Cisco

- [ ] Создать кастомные TextFSM шаблоны в `templates/` [§10]
- [ ] Зарегистрировать шаблоны в `CUSTOM_TEXTFSM_TEMPLATES` [§12.4]
- [ ] Написать тесты шаблонов [§12.9]

### Если интерфейсы имеют нестандартные имена

- [ ] `core/constants/interfaces.py` — добавить в `INTERFACE_SHORT_MAP` / `INTERFACE_FULL_MAP` [§12.6]
- [ ] `core/constants/interfaces.py` — добавить в `SHORT_TO_EXTRA` (алиасы для LAG matching) [§12.8]
- [ ] `core/constants/interfaces.py` — добавить в `INTERFACE_NAME_PORT_TYPE_MAP` (data-driven detect_port_type) [§12.7]
- [ ] `core/constants/netbox.py` — добавить в `PORT_TYPE_MAP` маппинг port_type → NetBox тип [§12.7]

### Если LAG/switchport формат уникальный

- [ ] `collectors/interfaces.py` — написать `_parse_lag_membership_<vendor>()` + добавить в `LAG_PARSERS` dict [§12.5]
- [ ] `core/constants/interfaces.py` — добавить LAG префикс в `is_lag_name()` [§12.7]
- [ ] `core/domain/interface.py` — обновить `InterfaceNormalizer.normalize_switchport_data()` (нормализация) [§12.5]

### Опционально

- [ ] `core/constants/commands.py` — добавить в `SECONDARY_COMMANDS["media_type"]` (для определения SFP) [§12.5]
- [ ] `core/domain/inventory.py` — добавить manufacturer patterns [§12.10]

### LLDP и кабели

- [ ] TextFSM шаблон LLDP: поле Port ID → `NEIGHBOR_PORT_ID` (НЕ `NEIGHBOR_INTERFACE`!) [§12.17]
- [ ] Если несколько LLDP neighbors на одном порту — `Filldown` на `LOCAL_INTERFACE` [§12.17]
- [ ] Проверить нормализацию имён интерфейсов: `INTERFACE_SHORT_MAP` содержит полное имя [§12.6]
- [ ] Проверить кабели с `--dry-run`: нет ложных удалений/созданий [§12.17]

---

## 12.17 LLDP шаблоны и кабельная синхронизация

При добавлении нового вендора с поддержкой LLDP/CDP нужно проверить несколько вещей.

### 17a. Именование полей в TextFSM LLDP шаблоне

**Критично:** поле Port ID соседа должно называться `NEIGHBOR_PORT_ID`, а **не** `NEIGHBOR_INTERFACE`.

Почему: нормализатор LLDP (`core/domain/lldp.py`) использует `KEY_MAPPING`:
```python
KEY_MAPPING = {
    "neighbor_interface": "port_description",   # ← НЕ port ID!
    "neighbor_port_id": "port_id",              # ← правильно
    ...
}
```

Если назвать поле `NEIGHBOR_INTERFACE`, оно попадёт в `port_description`, а затем
будет перезаписано реальным полем `PORT_DESCRIPTION`. Результат: `remote_port = ""`.

**Пример правильного шаблона:**
```
Value NEIGHBOR_PORT_ID (.+)         # ← Port ID соседа
Value PORT_DESCRIPTION (.+)         # ← описание порта (отдельное поле)

  ^\s+Port ID\s+:\s+${NEIGHBOR_PORT_ID}
  ^\s+Port description\s+:\s+${PORT_DESCRIPTION}
```

### 17b. Несколько соседей на одном порту

Некоторые устройства (например, Cisco 9500) отправляют **два LLDP TLV** с разными
`chassis_id_type` (MAC address и Locally assigned). Нормализатор автоматически
дедуплицирует записи по ключу `(local_interface, remote_hostname)`.

Для поддержки в TextFSM: если один `LLDP neighbor-information of port` блок содержит
несколько `Neighbor index`, нужно:
1. Добавить `Filldown` к `LOCAL_INTERFACE` (наследуется от первого блока)
2. Добавить переход по `Neighbor index` в `Start` state

**Пример:**
```
Value Filldown,Required LOCAL_INTERFACE (\S+\s+\d+(?:/\d+)?)

Start
  ^LLDP neighbor-information of port \[${LOCAL_INTERFACE}\] -> NeighborBlock
  ^\s+Neighbor index -> NeighborBlock

NeighborBlock
  ...
  ^\s+802\.1 organizationally -> Record Start
  ^LLDP neighbor-information of port \[${LOCAL_INTERFACE}\] -> Record Start
```

### 17c. Сопоставление имён интерфейсов в кабелях

При кабельной синхронизации LLDP имена сравниваются с NetBox именами.
Разные вендоры используют **разные полные имена** для одного типа порта:

| Тип | Cisco | QTech | Короткое |
|-----|-------|-------|----------|
| 100G | `HundredGigE` | `HundredGigabitEthernet` | `Hu` |
| 25G | — | `TFGigabitEthernet` | `TF` |
| 10G | `TenGigabitEthernet` | — | `Te` |
| 1G | `GigabitEthernet` | `GigabitEthernet` | `Gi` |

**Как система сопоставляет:**

1. **Поиск интерфейса** (`_find_interface()`): нормализует ОБА имени (LLDP и NetBox)
   через `normalize_interface_short(name, lowercase=True)` и сравнивает.
   Так `HundredGigE0/51` и `HundredGigabitEthernet0/51` оба → `hu0/51` — совпадение.

2. **Кабельный ключ**: при создании кабеля использует имена из NetBox объектов
   (уже нормализованные самим NetBox).

3. **Cleanup кабелей**: нормализует через short form для сравнения LLDP endpoints
   с NetBox endpoints.

**Что проверить для нового вендора:**

1. Полное имя интерфейса добавлено в `INTERFACE_SHORT_MAP` (lowercase → short):
   ```python
   ("новоеимя", "XX"),  # НовоеИмя0/1 → XX0/1
   ```

2. Короткое имя добавлено в `INTERFACE_FULL_MAP` (short → full):
   ```python
   "XX": "НовоеИмя",  # XX0/1 → НовоеИмя0/1
   ```

3. Запустить кабельную синхронизацию с `--dry-run` и проверить что:
   - Кабели создаются (а не пропускаются из-за "interface not found")
   - Кабели не удаляются ложно при повторном sync

### 17d. Пробелы в именах интерфейсов

QTech и некоторые другие платформы возвращают имена с пробелом:
`"TFGigabitEthernet 0/48"`, `"Mgmt 0"`.

Обе функции нормализации (`normalize_interface_short()` и `normalize_interface_full()`)
автоматически убирают пробелы. Но важно проверить что:
- TextFSM шаблон правильно захватывает имя с пробелом
- Value regex включает пробел: `(\S+\s+\d+(?:/\d+)?)` — пробел между типом и номером

---

## 12.18 Сводная таблица маппингов: что, где, зачем

Все маппинги собраны в двух файлах — `core/constants/interfaces.py` и `core/constants/netbox.py`.
Ниже — полная карта: какой маппинг для чего нужен, где используется, и что добавлять
при появлении нового вендора.

### Два потока данных

В проекте есть **два независимых потока**, использующих разные маппинги:

```
Поток 1: СРАВНЕНИЕ (поиск интерфейса, кабели)
  normalize_interface_short() → INTERFACE_SHORT_MAP
  "HundredGigabitEthernet 0/51" → "hu0/51"
  Цель: привести к одной форме для сравнения

Поток 2: ОПРЕДЕЛЕНИЕ ТИПА (какой тип записать в NetBox)
  detect_port_type() → INTERFACE_NAME_PORT_TYPE_MAP → PORT_TYPE_MAP
  "hu0/51" → port_type="100g-qsfp28" → netbox_type="100gbase-x-qsfp28"
  Цель: определить тип интерфейса для NetBox API
```

### Все маппинги на одной странице

#### 1. `INTERFACE_SHORT_MAP` — нормализация имён (полное → короткое)

**Файл:** `core/constants/interfaces.py`
**Тип:** `List[tuple]` (порядок важен! длинные префиксы первыми)

```python
INTERFACE_SHORT_MAP = [
    ("twentyfivegigabitethernet", "Twe"),   # 25G
    ("hundredgigabitethernet", "Hu"),        # QTech 100G
    ("hundredgige", "Hu"),                   # Cisco 100G  ← ОБА → "Hu"
    ("fortygigabitethernet", "Fo"),          # 40G
    ("tfgigabitethernet", "TF"),             # QTech 25G
    ("tengigabitethernet", "Te"),            # Cisco 10G
    ("gigabitethernet", "Gi"),               # 1G
    ("fastethernet", "Fa"),                  # 100M
    ("aggregateport", "Ag"),                 # QTech LAG
    ("ethernet", "Eth"),                     # NX-OS
    ("port-channel", "Po"),                  # Cisco LAG
]
```

**Используется в:** `normalize_interface_short(name, lowercase=True)`

**Кто вызывает:**

| Вызывающий | Файл | Зачем |
|------------|------|-------|
| `_normalize_interface_name()` | `netbox/sync/base.py:200` | Поиск интерфейса в NetBox по LLDP имени |
| `_cleanup_cables()` | `netbox/sync/cables.py:184-185` | Сравнение LLDP endpoints с кабелями NetBox |
| `compare_cables()` | `core/domain/sync.py:490-511` | Diff: какие кабели создать/удалить |
| `_deduplicate_neighbors()` | `core/domain/lldp.py:214` | Ключ дедупликации LLDP TLV |

**При добавлении нового вендора:** если у него уникальные полные имена интерфейсов
(как QTech `TFGigabitEthernet`) — добавить запись `("новоеимя", "XX")`.
Если имена стандартные (как у Cisco) — ничего добавлять не нужно.

---

#### 2. `INTERFACE_FULL_MAP` — обратная нормализация (короткое → полное)

**Файл:** `core/constants/interfaces.py`
**Тип:** `Dict[str, str]`

```python
INTERFACE_FULL_MAP = {
    "Gi": "GigabitEthernet",
    "Te": "TenGigabitEthernet",
    "TF": "TFGigabitEthernet",     # QTech 25G
    "Hu": "HundredGigE",           # ← всегда Cisco-стиль!
    "Fo": "FortyGigabitEthernet",
    "Ag": "AggregatePort",         # QTech LAG
    "Po": "Port-channel",
}
```

**Используется в:** `normalize_interface_full(name)`

**Кто вызывает:** отображение имён в UI/Excel/логах. **НЕ используется** для сравнения кабелей!

> **Важно:** `INTERFACE_FULL_MAP` расширяет `Hu` → `HundredGigE` (Cisco-стиль).
> Если NetBox хранит QTech-стиль `HundredGigabitEthernet` — имена **не совпадут**.
> Поэтому для сравнения используется `INTERFACE_SHORT_MAP` (→ short form), а не full.

**При добавлении нового вендора:** добавить `"XX": "НовоеИмя"` для обратного
раскрытия сокращений.

---

#### 3. `INTERFACE_NAME_PORT_TYPE_MAP` — определение типа порта по имени

**Файл:** `core/constants/interfaces.py`
**Тип:** `Dict[str, str]`

```python
INTERFACE_NAME_PORT_TYPE_MAP = {
    "hundredgig": "100g-qsfp28",       # 100G (Cisco + QTech)
    "hu": "100g-qsfp28",               # 100G (короткий)
    "fortygig": "40g-qsfp",            # 40G
    "fo": "40g-qsfp",                  # 40G (короткий)
    "twentyfivegig": "25g-sfp28",      # 25G
    "twe": "25g-sfp28",                # 25G (короткий)
    "tfgigabitethernet": "25g-sfp28",  # QTech 25G
    "tf": "25g-sfp28",                 # QTech 25G (короткий)
    "tengig": "10g-sfp+",              # Cisco 10G
    "te": "10g-sfp+",                  # Cisco 10G (короткий)
    "gigabit": "1g-rj45",              # 1G
    "gi": "1g-rj45",                   # 1G (короткий)
    "fastethernet": "100m-rj45",       # 100M
    "fa": "100m-rj45",                 # 100M (короткий)
}
```

**Значения** — domain-level port_type (платформонезависимая категория скорости).

**Используется в:**

| Вызывающий | Файл | Зачем |
|------------|------|-------|
| `_detect_from_interface_name()` | `core/domain/interface.py:232` | Domain: определить port_type по имени |
| `_detect_type_by_name_prefix()` | `core/constants/netbox.py:203` | NetBox: определить NetBox тип (через PORT_TYPE_MAP) |

**При добавлении нового вендора:** если у вендора уникальное имя → новая скорость
(например `FourHundredGigE` = 400G), добавить:
```python
"fourhundredgig": "400g-qsfp-dd",
"fh": "400g-qsfp-dd",
```
И добавить `"fh"` в `_SHORT_PORT_TYPE_PREFIXES`.

---

#### 4. `PORT_TYPE_MAP` — конвертация port_type → NetBox тип

**Файл:** `core/constants/netbox.py`
**Тип:** `Dict[str, str]`

```python
PORT_TYPE_MAP = {
    "100g-qsfp28": "100gbase-x-qsfp28",
    "40g-qsfp":    "40gbase-x-qsfpp",
    "25g-sfp28":   "25gbase-x-sfp28",
    "10g-sfp+":    "10gbase-x-sfpp",
    "1g-sfp":      "1000base-x-sfp",
    "1g-rj45":     "1000base-t",
    "100m-rj45":   "100base-tx",
    "lag":         "lag",
    "virtual":     "virtual",
}
```

**Мост** между domain-level port_type и NetBox API type.

**Используется в:**

| Вызывающий | Файл | Зачем |
|------------|------|-------|
| `get_netbox_interface_type()` приоритет 5 | `netbox.py:380` | Прямая конвертация port_type → NetBox |
| `_detect_type_by_name_prefix()` | `netbox.py:236` | Fallback: имя → port_type → NetBox |

**При добавлении нового типа порта:** добавить маппинг, например:
```python
"400g-qsfp-dd": "400gbase-x-qsfp-dd",
```

---

#### 5. `NETBOX_INTERFACE_TYPE_MAP` — media_type → NetBox тип (точный)

**Файл:** `core/constants/netbox.py`
**Тип:** `Dict[str, str]` (~80 записей)

```python
NETBOX_INTERFACE_TYPE_MAP = {
    "qsfp 100g lr4": "100gbase-lr4",
    "100gbase-sr4":  "100gbase-sr4",
    "sfp-10gbase-lr": "10gbase-lr",
    "sfp-10gbase-sr": "10gbase-sr",
    "1000basesx":     "1000base-sx",
    "sfp+":           "10gbase-x-sfpp",
    ...
}
```

**Самый точный маппинг** — определяет конкретный тип трансивера (не generic "10G SFP+",
а именно "10GBASE-SR").

**Используется в:** `get_netbox_interface_type()` приоритет 4 (строка 370)

**При добавлении нового трансивера:** добавить паттерн media_type в lowercase:
```python
"sfp-25gbase-aoc": "25gbase-sr",  # Active Optical Cable 25G
```

---

#### 6. `NETBOX_HARDWARE_TYPE_MAP` — hardware_type → NetBox тип

**Файл:** `core/constants/netbox.py`
**Тип:** `Dict[str, str]`

```python
NETBOX_HARDWARE_TYPE_MAP = {
    "hundred gig": "100gbase-x-qsfp28",
    "ten gig":     "10gbase-x-sfpp",
    "gigabit":     "1000base-t",
    "fast ethernet": "100base-tx",
    ...
}
```

**Используется в:** `get_netbox_interface_type()` приоритет 6 (строка 384)

**При добавлении нового вендора:** если hardware_type содержит нестандартные строки,
добавить паттерн в lowercase.

---

#### 7. `_SHORT_PORT_TYPE_PREFIXES` — короткие префиксы для port_type detection

**Файл:** `core/constants/interfaces.py`
**Тип:** `set`

```python
_SHORT_PORT_TYPE_PREFIXES = {"hu", "fo", "twe", "tf", "te", "gi", "fa"}
```

Защита от ложных совпадений: `"te"` не должен совпасть с `"test_interface"`.
Для коротких префиксов проверяется, что **после** них стоит цифра.

**При добавлении нового вендора:** если добавили короткий prefix (2-3 символа)
в `INTERFACE_NAME_PORT_TYPE_MAP` — добавить его сюда.

---

### Цепочка определения типа интерфейса для NetBox

`get_netbox_interface_type()` проверяет источники **по приоритету**:

```
Приоритет 1: LAG/Virtual                → по имени (is_lag_name) или port_type
Приоритет 2: Management                 → всегда "1000base-t"
Приоритет 3: media_type                 → NETBOX_INTERFACE_TYPE_MAP (самый точный!)
Приоритет 4: port_type                  → PORT_TYPE_MAP (из коллектора)
Приоритет 5: hardware_type              → NETBOX_HARDWARE_TYPE_MAP
Приоритет 6: interface_name             → INTERFACE_NAME_PORT_TYPE_MAP + PORT_TYPE_MAP
Приоритет 7: speed (fallback)           → по скорости в Mbps
```

**Пример для QTech TFGigabitEthernet с трансивером 10GBASE-SR:**

```
1. LAG? Нет
2. Management? Нет
3. media_type = "10GBASE-SR-SFP+"
   → NETBOX_INTERFACE_TYPE_MAP: паттерн "10gbase-sr" найден!
   → return "10gbase-sr"                                         ← ТОЧНЫЙ тип
```

**Пример для QTech TFGigabitEthernet БЕЗ трансивера:**

```
1. LAG? Нет
2. Management? Нет
3. media_type = "" (пусто)           → пропуск
4. port_type = "10g-sfp+"            → PORT_TYPE_MAP → "10gbase-x-sfpp"
   → return "10gbase-x-sfpp"                                     ← generic тип
```

**Пример когда ничего не задано (только имя):**

```
1-5. Все пусто                       → пропуск
6. interface_name = "tfgigabitethernet0/1"
   → INTERFACE_NAME_PORT_TYPE_MAP: "tfgigabitethernet" → "25g-sfp28"
   → PORT_TYPE_MAP: "25g-sfp28" → "25gbase-x-sfp28"
   → return "25gbase-x-sfp28"                                    ← fallback
```

---

### Цепочка сравнения кабелей

Кабельная синхронизация сравнивает имена из LLDP с именами из NetBox.
Всё сравнение через **short form** (`normalize_interface_short(lowercase=True)`):

```
LLDP:   "HundredGigabitEthernet 0/51"  (QTech, с пробелом)
NetBox: "HundredGigE0/51"              (Cisco-стиль, без пробела)

Нормализация обеих сторон:
  replace(" ","") → lower → INTERFACE_SHORT_MAP lookup
  "hundredgigabitethernet0/51" → startswith("hundredgigabitethernet") → "Hu" → "hu0/51"
  "hundredgige0/51"            → startswith("hundredgige")           → "Hu" → "hu0/51"
                                                                        ↓
                                                                  СОВПАДАЮТ
```

**Где происходит сравнение:**

| Этап | Метод | Файл | Что сравнивает |
|------|-------|------|----------------|
| Поиск интерфейса | `_find_interface()` | `base.py:177` | LLDP имя ↔ имена в кэше NetBox |
| Создание кабеля | `_create_cable()` | `cables.py:347` | Использует ID объектов (не имена!) |
| Дедупликация A↔B | `cable_key` | `cables.py:119` | Имена из NetBox объектов (sorted tuple) |
| Cleanup | `_cleanup_cables()` | `cables.py:184-219` | LLDP endpoints (short) ↔ NetBox endpoints (short) |
| Diff | `compare_cables()` | `sync.py:490-511` | local_set (short) ↔ remote_set (short) |

> **Кабель создаётся по числовым ID** (`object_id: 42, 78`), а не по именам.
> Short form нужна только для **поиска** и **сравнения**. Имена в NetBox остаются как есть.

---

### Сводная таблица: что добавлять при новом вендоре

| Ситуация | Файл | Маппинг | Что добавить |
|----------|------|---------|--------------|
| Уникальные имена (как QTech TF) | `interfaces.py` | `INTERFACE_SHORT_MAP` | `("новоеимя", "XX")` — порядок: длинные первыми! |
| | `interfaces.py` | `INTERFACE_FULL_MAP` | `"XX": "НовоеИмя"` |
| | `interfaces.py` | `SHORT_TO_EXTRA` в `get_interface_aliases()` | `"xx": ["НовоеИмя"]` — для switchport matching |
| Новая скорость (400G, 800G) | `interfaces.py` | `INTERFACE_NAME_PORT_TYPE_MAP` | `"fourhundredgig": "400g-qsfp-dd"` |
| | `interfaces.py` | `_SHORT_PORT_TYPE_PREFIXES` | `"fh"` (если добавлен короткий prefix) |
| | `netbox.py` | `PORT_TYPE_MAP` | `"400g-qsfp-dd": "400gbase-x-qsfp-dd"` |
| Новый трансивер/SFP | `netbox.py` | `NETBOX_INTERFACE_TYPE_MAP` | `"sfp-400g-dr4": "400gbase-dr4"` |
| Нестандартный hardware_type | `netbox.py` | `NETBOX_HARDWARE_TYPE_MAP` | `"four hundred gig": "400gbase-x-qsfp-dd"` |
| Новый тип LAG | `interfaces.py` | `is_lag_name()` → `LAG_PREFIXES` | Добавить prefix |
| Стандартные Cisco имена | — | — | **Ничего** не нужно |

### Пример: добавление Eltex MES с именем `ExtremeEthernet` (10G)

```python
# 1. core/constants/interfaces.py → INTERFACE_SHORT_MAP
INTERFACE_SHORT_MAP = [
    ...
    ("extremeethernet", "Xe"),    # Eltex 10G ← ДОБАВИТЬ
    ...
]

# 2. core/constants/interfaces.py → INTERFACE_FULL_MAP
INTERFACE_FULL_MAP = {
    ...
    "Xe": "ExtremeEthernet",      # Eltex 10G ← ДОБАВИТЬ
}

# 3. core/constants/interfaces.py → INTERFACE_NAME_PORT_TYPE_MAP
# НЕ нужно если ExtremeEthernet = 10G (уже покрыто "tengig"/"te")
# Нужно ТОЛЬКО если префикс уникальный:
INTERFACE_NAME_PORT_TYPE_MAP = {
    ...
    "extremeethernet": "10g-sfp+",   # ← ДОБАВИТЬ
    "xe": "10g-sfp+",                # ← ДОБАВИТЬ
}
# + добавить "xe" в _SHORT_PORT_TYPE_PREFIXES

# 4. core/constants/netbox.py → PORT_TYPE_MAP
# НЕ нужно — "10g-sfp+" уже есть в PORT_TYPE_MAP

# 5. Проверка:
# normalize_interface_short("ExtremeEthernet0/1") → "Xe0/1" ✓
# normalize_interface_short("ExtremeEthernet0/1", lowercase=True) → "xe0/1" ✓
# detect_port_type({"interface": "ExtremeEthernet0/1"}, "extremeethernet0/1") → "10g-sfp+" ✓
# get_netbox_interface_type("ExtremeEthernet0/1") → "10gbase-x-sfpp" ✓
```

---

## 12.19 UNIVERSAL_FIELD_MAP: нормализация имён полей NTC

### Что это

`UNIVERSAL_FIELD_MAP` в `parsers/textfsm_parser.py` — маппинг для приведения имён полей из разных NTC-шаблонов к единым стандартным именам.

Разные платформы возвращают одни и те же данные под разными ключами:

```
Cisco IOS:  {"mac_address": "aa:bb:cc:dd:ee:ff"}
NX-OS:      {"mac": "aa:bb:cc:dd:ee:ff"}
Arista:     {"destination_address": "aa:bb:cc:dd:ee:ff"}
```

`UNIVERSAL_FIELD_MAP` маппит все варианты на стандартный ключ `"mac"`:

```python
"mac": ["mac", "mac_address", "destination_address"],
```

После `_normalize_fields()` весь остальной код работает с единым `data.get("mac")`.

### Как работает _normalize_fields()

```python
def _normalize_fields(self, data):
    for row in data:
        new_row = {}
        for key, value in row.items():
            key_lower = key.lower()
            # Ищем стандартное имя для ключа
            standard_key = key_lower
            for std_name, aliases in UNIVERSAL_FIELD_MAP.items():
                if key_lower in aliases:
                    standard_key = std_name
                    break
            new_row[standard_key] = value
        normalized.append(new_row)
```

**Важно:** если два ключа из исходного dict маппятся на один `standard_key`, **последний перезаписывает первый**.

### Текущие маппинги

```python
UNIVERSAL_FIELD_MAP = {
    # Устройство
    "hostname": ["hostname", "host", "switchname", "device_id"],
    "hardware": ["hardware", "platform", "model", "chassis", "device_model"],
    "serial":   ["serial", "serial_number", "sn", "chassis_sn", "serialnum"],
    "version":  ["version", "software_version", "os", "kickstart_ver", "sys_ver", "os_version"],
    "uptime":   ["uptime", "uptime_string", "system_uptime"],

    # MAC таблица
    "mac":       ["mac", "mac_address", "destination_address"],
    "vlan":      ["vlan", "vlan_id"],
    "interface": ["interface", "port", "destination_port"],
    "type":      ["type", "mac_type", "entry_type"],

    # Интерфейсы
    "status":      ["status", "link_status", "link"],
    "protocol":    ["protocol", "protocol_status"],
    "description": ["description", "desc"],
    "speed":       ["speed"],          # ← только speed, НЕ bandwidth!
    "duplex":      ["duplex"],
    "mtu":         ["mtu"],

    # LLDP/CDP
    "neighbor":         ["neighbor", "neighbor_id", "device_id", "remote_system_name"],
    "local_interface":  ["local_interface", "local_port"],
    "remote_interface": ["remote_interface", "remote_port", "port_id"],
}
```

### Правила добавления алиасов

#### Когда МОЖНО добавлять алиас

Поле с **одинаковой семантикой**, но другим именем на другой платформе:

```python
# ✅ Одно и то же — MAC-адрес, просто разные имена полей:
"mac": ["mac", "mac_address", "destination_address"]

# ✅ Одно и то же — hostname устройства:
"hostname": ["hostname", "switchname", "host"]

# ✅ Одно и то же — серийный номер:
"serial": ["serial", "serial_number", "serialnum"]
```

#### Когда НЕЛЬЗЯ добавлять алиас

Поля с **разной семантикой**, даже если кажутся похожими:

```python
# ❌ НЕПРАВИЛЬНО — bandwidth и speed это РАЗНЫЕ поля:
"speed": ["speed", "bandwidth"]
#   speed     = согласованная скорость (1000Mb/s, auto-speed)
#   bandwidth = сконфигурированный BW для QoS (10000 Kbit — дефолт)

# ❌ НЕПРАВИЛЬНО — chassis_id это MAC в LLDP, не hostname:
"hostname": ["hostname", "chassis_id"]

# ❌ НЕПРАВИЛЬНО — input_rate и speed это разные метрики:
"speed": ["speed", "input_rate"]
```

### Проверка: конфликт ключей

Если NTC-шаблон возвращает **оба** ключа, маппящиеся на один `standard_key`, последний перезаписывает первый:

```python
# NTC вернул: {"speed": "1000Mb/s", "bandwidth": "10000"}
# _normalize_fields():
#   speed → standard_key="speed" → new_row["speed"] = "1000Mb/s"
#   bandwidth → standard_key="speed" → new_row["speed"] = "10000"  ← ПЕРЕЗАПИСЬ!
# Результат: speed = "10000" — НЕПРАВИЛЬНО
```

**Правило:** перед добавлением алиаса проверить, что NTC-шаблоны платформ НЕ возвращают оба ключа одновременно. Если возвращают — это разные поля, а не алиасы.

### Чеклист добавления нового алиаса

1. Убедиться что это **одно и то же поле** с другим именем (не разная семантика)
2. Проверить что NTC-шаблоны **НЕ** возвращают оба ключа одновременно
3. Если сомневаешься — НЕ добавлять алиас; лучше обработать в конкретном коллекторе
4. Проверить на всех платформах: `--format parsed` покажет сырые поля TextFSM

```bash
# Посмотреть какие поля возвращает TextFSM для платформы
python -m network_collector interfaces --format parsed --host 10.0.0.1
```

---

## Полезные ссылки

- [NTC Templates](https://github.com/networktocode/ntc-templates) — библиотека шаблонов
- [TextFSM Documentation](https://github.com/google/textfsm) — документация TextFSM
- [Scrapli Documentation](https://carlmontanari.github.io/scrapli/) — SSH библиотека
