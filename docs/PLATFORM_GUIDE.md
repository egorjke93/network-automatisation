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
        "qtech": "show interfaces",
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
        "qtech": "show inventory",
    },
}
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
    ("qtech", "show interfaces"): "qtech_show_interface.textfsm",
    ("qtech_qsw", "show interfaces"): "qtech_show_interface.textfsm",
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
    └── qtech_show_lldp_neighbors_detail.textfsm
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
    "interfaces": {"qtech": "show interfaces", "qtech_qsw": "show interfaces"},
    "lldp": {"qtech": "show lldp neighbors detail", "qtech_qsw": "show lldp neighbors detail"},
    "devices": {"qtech": "show version", "qtech_qsw": "show version"},
    "inventory": {"qtech": "show inventory", "qtech_qsw": "show inventory"},
}
```

#### Кастомные шаблоны (`core/constants/commands.py`):
```python
CUSTOM_TEXTFSM_TEMPLATES = {
    ("qtech", "show mac address-table"): "qtech_show_mac_address_table.textfsm",
    ("qtech_qsw", "show mac address-table"): "qtech_show_mac_address_table.textfsm",
    ("qtech", "show version"): "qtech_show_version.textfsm",
    ("qtech_qsw", "show version"): "qtech_show_version.textfsm",
    ("qtech", "show interfaces"): "qtech_show_interface.textfsm",
    ("qtech_qsw", "show interfaces"): "qtech_show_interface.textfsm",
    ("qtech", "show lldp neighbors detail"): "qtech_show_lldp_neighbors_detail.textfsm",
    ("qtech_qsw", "show lldp neighbors detail"): "qtech_show_lldp_neighbors_detail.textfsm",
    # Дополнительные шаблоны
    ("qtech", "show interface status"): "qtech_show_interface_status.textfsm",
    ("qtech_qsw", "show interface status"): "qtech_show_interface_status.textfsm",
    ("qtech", "show interface switchport"): "qtech_show_interface_switchport.textfsm",
    ("qtech_qsw", "show interface switchport"): "qtech_show_interface_switchport.textfsm",
    ("qtech", "show interface transceiver"): "qtech_show_interface_transceiver.textfsm",
    ("qtech_qsw", "show interface transceiver"): "qtech_show_interface_transceiver.textfsm",
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
└── qtech_show_lldp_neighbors_detail.textfsm
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

## Чеклист добавления новой платформы

- [ ] Добавить в `SCRAPLI_PLATFORM_MAP` (SSH драйвер)
- [ ] Добавить в `NTC_PLATFORM_MAP` (парсер fallback)
- [ ] Добавить в `NETMIKO_PLATFORM_MAP` (если нужен конфигуратор)
- [ ] Добавить в `VENDOR_MAP` (производитель)
- [ ] Добавить команды в `COLLECTOR_COMMANDS` (mac, interfaces, lldp, devices, inventory)
- [ ] Создать кастомные шаблоны в `templates/` (если NTC не парсит)
- [ ] Зарегистрировать шаблоны в `CUSTOM_TEXTFSM_TEMPLATES`
- [ ] Добавить фикстуры в `tests/fixtures/`
- [ ] Написать тесты
- [ ] Проверить на реальном устройстве

---

## Полезные ссылки

- [NTC Templates](https://github.com/networktocode/ntc-templates) — библиотека шаблонов
- [TextFSM Documentation](https://github.com/google/textfsm) — документация TextFSM
- [Scrapli Documentation](https://carlmontanari.github.io/scrapli/) — SSH библиотека
