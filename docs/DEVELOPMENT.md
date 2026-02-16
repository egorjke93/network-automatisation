# Разработка Network Collector

Руководство для разработчиков: тестирование, добавление платформ, соглашения по коду.

## Содержание

1. [Быстрый старт](#1-быстрый-старт)
2. [Тестирование](#2-тестирование)
3. [Добавление новой платформы](#3-добавление-новой-платформы)
4. [Добавление типа интерфейса](#4-добавление-типа-интерфейса)
5. [Кастомные TextFSM шаблоны](#5-кастомные-textfsm-шаблоны)
6. [Соглашения по коду](#6-соглашения-по-коду)

---

## 1. Быстрый старт

### 1.1 Настройка окружения

```bash
cd /home/sa/project
source network_collector/myenv/bin/activate
pip install -r network_collector/requirements.txt
pip install -r network_collector/requirements-dev.txt  # для тестов
```

### 1.2 Запуск проекта

```bash
# ВАЖНО: Запускать из /home/sa/project (не из network_collector!)
cd /home/sa/project
python -m network_collector --help
```

### 1.3 Запуск тестов

```bash
# Все тесты
pytest tests/ -v

# С coverage
pytest tests/ --cov=network_collector --cov-report=html
```

---

## 2. Тестирование

### 2.1 Структура тестов

```
tests/
├── conftest.py                    # Общие fixtures
├── fixtures/                      # Реальные выводы команд
│   ├── cisco_ios/
│   ├── cisco_nxos/
│   ├── qtech/
│   └── real_output/               # Реальные данные с устройств
├── test_api/                      # Тесты REST API (148 тестов)
│   ├── test_auth.py               # Аутентификация
│   ├── test_collectors.py         # API коллекторов
│   ├── test_device_management.py  # Device Management API
│   ├── test_health.py             # Health check
│   ├── test_history_service.py    # History Service
│   ├── test_integration.py        # Интеграционные тесты API
│   ├── test_pipelines.py          # Pipeline API
│   ├── test_sync.py               # Sync API
│   └── test_tasks.py              # Tasks API (async mode)
├── test_cli/                      # Тесты CLI
│   ├── test_format_parsed.py      # --format parsed
│   ├── test_pipeline.py           # Pipeline команды
│   └── test_sync_summary.py       # Sync summary
├── test_collectors/               # Тесты коллекторов
│   ├── test_lldp_parsing.py       # LLDP/CDP парсинг
│   ├── test_port_type_detection.py # Определение типа порта
│   └── test_switchport_mode.py    # Режимы switchport
├── test_configurator/             # Тесты конфигуратора
│   └── test_pusher_retry.py       # Retry логика Netmiko
├── test_contracts/                # Contract тесты
│   └── test_fields_contract.py    # Контракт fields.yaml ↔ Models
├── test_core/                     # Тесты core модулей
│   ├── test_config_schema.py      # Валидация config.yaml
│   ├── test_connection_retry.py   # Retry логика Scrapli
│   ├── test_constants.py          # Константы и маппинги
│   ├── test_constants_extra.py    # Функции нормализации
│   ├── test_context.py            # RunContext
│   ├── test_credentials.py        # CredentialsManager
│   ├── test_exceptions.py         # Custom exceptions
│   ├── test_field_registry.py     # Field registry
│   ├── test_fields_config.py      # fields_config.py
│   ├── test_logging.py
│   ├── test_models.py
│   ├── test_domain/               # Тесты Domain Layer
│   │   ├── test_interface_normalizer.py
│   │   ├── test_inventory_normalizer.py
│   │   ├── test_lldp_normalizer.py
│   │   ├── test_lldp_real_data.py
│   │   ├── test_mac_normalizer.py
│   │   └── test_sync_comparator.py
│   └── test_pipeline/             # Тесты Pipeline
│       ├── test_executor.py
│       ├── test_executor_integration.py
│       └── test_models.py
├── test_e2e/                      # E2E тесты
│   ├── test_config_backup_e2e.py  # Config backup E2E
│   ├── test_device_collector_e2e.py  # Device collector E2E
│   ├── test_interface_collector_e2e.py  # Interface collector E2E
│   ├── test_inventory_collector_e2e.py  # Inventory collector E2E
│   ├── test_ip_collector_e2e.py   # IP collector E2E
│   ├── test_lldp_collector_e2e.py # LLDP collector E2E
│   ├── test_mac_collector_e2e.py  # MAC collector E2E
│   ├── test_multi_device_collection.py  # Multi-device E2E
│   ├── test_nxos_enrichment_e2e.py  # NX-OS enrichment E2E
│   ├── test_pipeline.py           # Pipeline E2E
│   ├── test_sync_full_device.py   # Full device sync E2E
│   └── test_sync_pipeline.py      # Sync pipeline E2E
├── test_exporters/                # Тесты экспорта
│   ├── test_csv_exporter.py       # CSV экспорт
│   ├── test_excel_exporter.py     # Excel экспорт
│   ├── test_json_exporter.py      # JSON экспорт
│   └── test_raw_exporter.py       # Raw JSON stdout
├── test_fixes/                    # Регрессионные тесты
│   ├── test_interface_enabled.py  # Bug fix: interface enabled
│   ├── test_platform_mapping.py   # Platform mapping
│   └── test_sync_preview.py       # Sync preview
├── test_netbox/                   # Тесты NetBox синхронизации
│   ├── test_diff.py               # DiffCalculator
│   ├── test_interface_type_mapping.py
│   ├── test_inventory_sync.py     # Inventory sync
│   ├── test_sync_base.py          # SyncBase class
│   ├── test_sync_integration.py   # Sync integration
│   ├── test_sync_interfaces_vlan.py  # Interface VLAN sync (19 тестов)
│   └── test_vlans_sync.py         # VLANs sync
├── test_parsers/                  # Тесты парсинга
│   ├── test_interfaces.py
│   ├── test_inventory.py
│   ├── test_lldp.py               # LLDP/CDP парсинг
│   ├── test_mac.py
│   ├── test_nxos_enrichment.py
│   └── test_version.py
├── test_qtech_support.py          # Поддержка QTech платформы
├── test_qtech_templates.py        # QTech TextFSM шаблоны
└── test_refactoring_utils.py      # Утилиты рефакторинга
```

**Всего: 1788 тестов, покрытие ~85%**

### 2.2 Описание тестовых модулей

| Модуль | Что тестируется |
|--------|-----------------|
| **test_api/** | REST API endpoints: аутентификация, коллекторы, пайплайны, async mode (Tasks API), history |
| **test_cli/** | CLI команды: pipeline, sync summary |
| **test_collectors/** | Парсинг данных с устройств: LLDP/CDP, switchport mode, port type detection |
| **test_configurator/** | Отправка конфигурации на устройства: retry логика Netmiko |
| **test_contracts/** | Контракт между fields.yaml и моделями данных |
| **test_core/** | Core модули: config schema, constants, context, credentials, exceptions, logging, models |
| **test_core/test_domain/** | Domain Layer: нормализаторы (interface, inventory, lldp, mac), sync comparator |
| **test_core/test_pipeline/** | Pipeline: executor, models, интеграция |
| **test_e2e/** | End-to-end тесты: pipeline, sync pipeline |
| **test_exporters/** | Экспорт данных: CSV, Excel, JSON, Raw |
| **test_fixes/** | Регрессионные тесты для исправленных багов |
| **test_netbox/** | NetBox синхронизация: diff, inventory, interfaces, vlans, cables |
| **test_parsers/** | TextFSM парсинг: interfaces, inventory, lldp, mac, version |

### 2.3 Запуск тестов

```bash
# Все тесты
pytest tests/ -v

# Конкретный файл
pytest tests/test_collectors/test_port_type_detection.py -v

# Конкретный тест
pytest tests/test_netbox/test_sync.py::test_create_device -v

# С остановкой на первой ошибке
pytest tests/ -x

# Только unit тесты
pytest tests/ -m unit

# Параллельный запуск
pytest tests/ -n 4
```

### 2.3 Coverage

```bash
# HTML отчёт
pytest tests/ --cov=network_collector --cov-report=html
open htmlcov/index.html

# Terminal отчёт
pytest tests/ --cov=network_collector --cov-report=term-missing
```

### 2.4 Написание тестов

```python
"""Тесты для определения типа интерфейса."""

import pytest
from network_collector.core.domain.interface import InterfaceNormalizer


@pytest.fixture
def normalizer():
    """Создаём нормализатор для тестирования."""
    return InterfaceNormalizer()


@pytest.mark.unit
class TestPortTypeDetection:
    """Тесты для detect_port_type() (Domain Layer)."""

    @pytest.mark.parametrize("input_data,expected", [
        ({"interface": "Gi1/0/1", "media_type": "SFP-10GBase-LR"}, "10g-sfp+"),
        ({"interface": "Gi1/0/2", "media_type": "RJ45"}, "1g-rj45"),
    ])
    def test_basic(self, normalizer, input_data, expected):
        """Базовые кейсы."""
        result = normalizer.detect_port_type(input_data, input_data["interface"].lower())
        assert result == expected

    def test_production_bug_25g_with_10g_sfp(self, normalizer):
        """Регрессионный тест для бага из прода."""
        data = {
            "interface": "TwentyFiveGigE1/0/1",
            "media_type": "SFP-10GBase-LR",
        }
        result = normalizer.detect_port_type(data, data["interface"].lower())
        assert result == "10g-sfp+", "Должен определяться по трансиверу, не по порту"
```

### 2.5 Fixtures

**Встроенные fixtures (conftest.py):**

```python
@pytest.fixture
def sample_interface_data():
    """Примеры данных интерфейсов."""
    return {
        "c9500_25g_with_10g_sfp": {
            "interface": "TwentyFiveGigE1/0/1",
            "media_type": "SFP-10GBase-LR",
        },
        "gigabit_copper": {
            "interface": "GigabitEthernet0/1",
            "hardware_type": "10/100/1000 RJ45",
        },
    }

@pytest.fixture
def load_fixture():
    """Загрузка реальных выводов команд."""
    def _load(platform, filename):
        path = Path(__file__).parent / "fixtures" / platform / filename
        return path.read_text()
    return _load
```

### 2.6 Retry тесты

Тесты для проверки retry логики при SSH подключениях.

**Scrapli (ConnectionManager)** — `tests/test_core/test_connection_retry.py`:

```python
# 11 тестов:
- test_connect_success_first_try      # Успешное подключение с первой попытки
- test_connect_retry_on_timeout       # Retry при timeout
- test_connect_no_retry_on_auth_error # НЕ retry при ошибке аутентификации
- test_connect_max_retries_exceeded   # Превышение max_retries
- test_connect_retry_delay_applied    # Проверка задержки между попытками
- test_connect_success_after_retry    # Успех после retry
- test_default_retry_values           # Дефолтные значения (2 попытки, 5 сек)
- test_custom_retry_values            # Кастомные значения
- test_connect_closes_on_failure      # Закрытие соединения при ошибке
- test_retry_on_connection_refused    # Retry при connection refused
- test_retry_on_socket_error          # Retry при socket error
```

**Netmiko (ConfigPusher)** — `tests/test_configurator/test_pusher_retry.py`:

```python
# 12 тестов:
- test_dry_run_no_connection          # dry_run не подключается
- test_push_success_first_try         # Успех с первой попытки
- test_push_retry_on_timeout          # Retry при timeout
- test_push_no_retry_on_auth_error    # НЕ retry при auth error
- test_push_max_retries_exceeded      # Превышение лимита
- test_push_retry_delay_applied       # Задержка между попытками
- test_push_success_after_retry       # Успех после retry
- test_default_retry_values           # Дефолтные значения
- test_custom_retry_values            # Кастомные значения
- test_save_config_called             # Вызов save_config
- test_disconnect_called_on_success   # Отключение после успеха
- test_disconnect_called_on_failure   # Отключение после ошибки
```

**Запуск retry тестов:**

```bash
# Все retry тесты
pytest tests/test_core/test_connection_retry.py tests/test_configurator/test_pusher_retry.py -v

# Только Scrapli
pytest tests/test_core/test_connection_retry.py -v

# Только Netmiko
pytest tests/test_configurator/test_pusher_retry.py -v
```

**Push-config тесты** — `tests/test_configurator/test_push_config.py`:

```python
# 25 тестов:
# Загрузка YAML:
- test_load_valid_yaml                  # Корректный YAML
- test_load_common_commands             # Содержимое _common
- test_load_platform_commands           # Содержимое платформенных секций
- test_file_not_found                   # Несуществующий файл
- test_invalid_yaml_syntax              # Ошибка парсинга
- test_empty_yaml                       # Пустой файл
- test_non_dict_yaml                    # Некорректный формат
- test_non_list_commands                # Команды не список
- test_commands_converted_to_strings    # Конвертация в строки

# Сборка команд:
- test_common_plus_platform             # _common + платформенные
- test_only_platform_no_common          # Без _common
- test_only_common                      # Только _common
- test_unknown_platform_with_common     # Неизвестная платформа + _common
- test_unknown_platform_no_common       # Неизвестная платформа без _common
- test_nxos_commands                    # Команды для NX-OS

# Backward compatibility:
- test_old_format_device_type_as_platform     # device_type → platform
- test_old_format_device_type_cisco_ios       # cisco_ios как device_type
- test_new_format_both_fields                 # platform + device_type
- test_commands_match_regardless_of_format    # Одинаковый результат

# Интеграция cmd_push_config:
- test_dry_run_shows_commands           # dry-run без применения
- test_platform_filter                  # Фильтр --platform
- test_apply_calls_pusher              # --apply вызывает ConfigPusher
- test_apply_no_save                   # --no-save не сохраняет конфиг
- test_no_commands_for_platform        # Платформа без команд
- test_no_commands_at_all              # Нет команд совсем
```

**Запуск push-config тестов:**

```bash
# Push-config тесты
pytest tests/test_configurator/test_push_config.py -v

# Все configurator тесты (push-config + retry)
pytest tests/test_configurator/ -v
```

---

## 3. Добавление новой платформы

### 3.1 Что нужно добавить

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. core/constants.py — МАППИНГИ                                              │
│    • SCRAPLI_PLATFORM_MAP  → какой SSH драйвер использовать                 │
│    • NTC_PLATFORM_MAP      → какой парсер NTC использовать                  │
│    • VENDOR_MAP            → определение производителя                       │
├─────────────────────────────────────────────────────────────────────────────┤
│ 2. core/constants/commands.py — КОМАНДЫ (централизованные)                   │
│    • COLLECTOR_COMMANDS    → основные команды коллекторов                    │
│    • SECONDARY_COMMANDS    → вторичные команды (lag, switchport, etc.)       │
├─────────────────────────────────────────────────────────────────────────────┤
│ 3. templates/*.textfsm — КАСТОМНЫЕ ШАБЛОНЫ (если NTC не парсит)             │
│    • CUSTOM_TEXTFSM_TEMPLATES + файл шаблона                                │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Шаг 1: Маппинги

```python
# core/constants.py

# SSH драйвер
SCRAPLI_PLATFORM_MAP = {
    "eltex": "cisco_iosxe",      # CLI как Cisco IOS
    "eltex_mes": "cisco_iosxe",
}

# NTC парсер
NTC_PLATFORM_MAP = {
    "eltex": "cisco_ios",        # Вывод как Cisco IOS
    "eltex_mes": "cisco_ios",
}

# Производитель (для inventory)
VENDOR_MAP = {
    "eltex": ["eltex", "eltex_mes", "eltex_esr"],
}
```

### 3.3 Шаг 2: Команды в коллекторах

Команды централизованы в `core/constants/commands.py`. Коллекторы загружают их оттуда:

```python
# Команды загружаются из централизованного хранилища
from network_collector.core.constants.commands import COLLECTOR_COMMANDS

class MACCollector(BaseCollector):
    platform_commands = COLLECTOR_COMMANDS.get("mac", {})

class InterfaceCollector(BaseCollector):
    platform_commands = COLLECTOR_COMMANDS.get("interfaces", {})
```

**Для добавления новой платформы** — добавьте команду в `core/constants/commands.py` → `COLLECTOR_COMMANDS`:

```python
# core/constants/commands.py → COLLECTOR_COMMANDS
"mac": {
    "cisco_ios": "show mac address-table",
    "eltex": "show mac address-table",      # ← ДОБАВИТЬ
},
"interfaces": {
    "cisco_ios": "show interfaces",
    "eltex": "show interfaces",              # ← ДОБАВИТЬ
},
```

**Вторичные команды (enrichment)** — тоже в `core/constants/commands.py` → `SECONDARY_COMMANDS`:

```python
from network_collector.core.constants.commands import SECONDARY_COMMANDS

lag_commands = SECONDARY_COMMANDS.get("lag", {})
switchport_commands = SECONDARY_COMMANDS.get("switchport", {})
```

Группы вторичных команд: `lag`, `switchport`, `media_type`, `transceiver`, `lldp_summary`, `interface_errors`.

```python
# core/constants/commands.py → SECONDARY_COMMANDS
"lag": {
    "cisco_ios": "show etherchannel summary",
    "qtech": "show aggregatePort summary",
    "eltex": "show lacp summary",            # ← если команда другая
},
"switchport": {
    "cisco_ios": "show interfaces switchport",
    "eltex": "show interfaces switchport",   # ← ДОБАВИТЬ
},
```

### 3.4 Шаг 3: Кастомные шаблоны (если нужно)

```python
# core/constants.py
CUSTOM_TEXTFSM_TEMPLATES = {
    ("eltex", "show mac address-table"): "eltex_show_mac.textfsm",
}
```

```textfsm
# templates/eltex_show_mac.textfsm
Value Required VLAN (\d+)
Value Required MAC ([0-9a-fA-F]{4}\.[0-9a-fA-F]{4}\.[0-9a-fA-F]{4})
Value Required INTERFACE (\S+)
Value TYPE (\S+)

Start
  ^${VLAN}\s+${MAC}\s+${TYPE}\s+${INTERFACE} -> Record
```

### 3.5 Шаг 4: Тестирование

```bash
# Проверить подключение
python -m network_collector run "show version" --format raw

# Проверить парсинг MAC
python -m network_collector mac --format json

# Проверить интерфейсы
python -m network_collector interfaces --format json

# Проверить sync (dry-run)
python -m network_collector sync-netbox --interfaces --dry-run
```

### 3.6 Таблица: где что добавлять

| Что | Файл | Переменная |
|-----|------|------------|
| SSH драйвер | `core/constants/platforms.py` | `SCRAPLI_PLATFORM_MAP` |
| NTC парсер | `core/constants/platforms.py` | `NTC_PLATFORM_MAP` |
| Производитель | `core/constants/platforms.py` | `VENDOR_MAP` |
| Команда MAC | `core/constants/commands.py` | `COLLECTOR_COMMANDS["mac"]` |
| Команда interfaces | `core/constants/commands.py` | `COLLECTOR_COMMANDS["interfaces"]` |
| Команда LAG | `core/constants/commands.py` | `SECONDARY_COMMANDS["lag"]` |
| Команда switchport | `core/constants/commands.py` | `SECONDARY_COMMANDS["switchport"]` |
| Команда LLDP | `core/constants/commands.py` | `COLLECTOR_COMMANDS["lldp"]` |
| Команда CDP | `core/constants/commands.py` | `COLLECTOR_COMMANDS["cdp"]` |
| Команда inventory | `core/constants/commands.py` | `COLLECTOR_COMMANDS["inventory"]` |
| Команда transceiver | `core/constants/commands.py` | `SECONDARY_COMMANDS["transceiver"]` |
| Команда backup | `collectors/config_backup.py` | `BACKUP_COMMANDS` |
| Кастомный шаблон | `core/constants/commands.py` | `CUSTOM_TEXTFSM_TEMPLATES` |
| LAG формат (если новый) | `core/constants/interfaces.py` | `is_lag_name()` — добавить префикс |
| Интерфейс маппинг | `core/constants/interfaces.py` | `INTERFACE_SHORT_MAP`, `INTERFACE_FULL_MAP` |
| LLDP определение | `core/domain/lldp.py` | `_PLATFORM_PATTERNS` — добавить запись |

---

## 4. Добавление типа интерфейса

### 4.1 Двухуровневая архитектура

```
┌────────────────────────────────────────────────────────────────┐
│ 1. Коллектор → port_type (платформонезависимый)                 │
│    InterfaceNormalizer.detect_port_type() в core/domain/interface.py │
│    Результат: "10g-sfp+", "1g-rj45", "lag", "virtual"          │
├────────────────────────────────────────────────────────────────┤
│ 2. Sync → NetBox type                                           │
│    _get_interface_type() в netbox/sync/interfaces.py            │
│    Результат: "10gbase-x-sfpp", "1000base-t", "lag"            │
└────────────────────────────────────────────────────────────────┘
```

### 4.2 Добавление нового типа

**Пример: добавить 400G**

```python
# 1. core/domain/interface.py → detect_port_type() → _detect_from_interface_name()
if iface_lower.startswith(("fourhundredgig", "fh")):
    return "400g-qsfp-dd"

# 2. core/constants/netbox.py → get_netbox_interface_type()
# Добавить в INTERFACE_NAME_PREFIX_MAP или в логику функции

# 3. core/constants/interfaces.py → INTERFACE_SHORT_MAP / INTERFACE_FULL_MAP
# Если нужны сокращения/расширения имён
```

**Пример из QTech: TFGigabitEthernet = 10G, AggregatePort = LAG**

```python
# core/domain/interface.py → detect_port_type()
if iface_lower.startswith(("tfgigabitethernet", "tf")):
    return "10g-sfp+"
if iface_lower.startswith(("aggregateport", "ag")):
    return "lag"

# core/constants/interfaces.py
INTERFACE_SHORT_MAP: ("tfgigabitethernet", "TF"), ("aggregateport", "Ag")
INTERFACE_FULL_MAP: "TF": "TFGigabitEthernet", "Ag": "AggregatePort"
```

### 4.3 Добавление нового media_type

Когда устройство возвращает неизвестный media_type (SFP модуль):

```python
# core/constants.py → NETBOX_INTERFACE_TYPE_MAP
NETBOX_INTERFACE_TYPE_MAP = {
    # Добавить новый маппинг media_type → NetBox type
    "sfp-25gbase-sr": "25gbase-x-sfp28",
    "100gbase-zr4": "100gbase-zr",
    "qsfp 100g cwdm4": "100gbase-x-qsfp28",
}
```

**Пример:** устройство возвращает `media_type: "SFP 100GBASE-LR4"` но в NetBox ошибка.

1. Проверить текущие маппинги в `NETBOX_INTERFACE_TYPE_MAP`
2. Добавить новый маппинг (ключ в lowercase):
   ```python
   "sfp 100gbase-lr4": "100gbase-lr4",
   ```

### 4.4 Таблица: где что добавлять

| Источник | Файл | Переменная | Когда использовать |
|----------|------|------------|-------------------|
| Имя интерфейса | `core/domain/interface.py` | `InterfaceNormalizer.detect_port_type()` | Новый тип порта (400G, 800G) |
| port_type → NetBox | `core/constants.py` | `PORT_TYPE_MAP` | Маппинг port_type в NetBox |
| media_type → NetBox | `core/constants.py` | `NETBOX_INTERFACE_TYPE_MAP` | Новый SFP/трансивер |
| hardware_type → NetBox | `core/constants.py` | `NETBOX_HARDWARE_TYPE_MAP` | Маппинг скорости |

### 4.5 Приоритет определения типа

```
1. port_type (из коллектора)     — платформонезависимый
   ↓ если пустой
2. media_type (SFP-10GBase-SR)   — самый точный (NETBOX_INTERFACE_TYPE_MAP)
   ↓ если пустой
3. hardware_type (100/1000/10000) — макс. скорость (NETBOX_HARDWARE_TYPE_MAP)
   ↓ если пустой
4. interface_name (TenGigabit)    — по имени
   ↓ если не определился
5. defaults.type из fields.yaml   — fallback
```

### 4.6 Проверка доступных типов NetBox

```bash
# Получить все типы интерфейсов из NetBox API
curl -s "$NETBOX_URL/api/dcim/interfaces/" \
  -H "Authorization: Token $NETBOX_TOKEN" | jq '.results[].type.value' | sort -u

# Или через pynetbox
python -c "
import pynetbox
nb = pynetbox.api('$NETBOX_URL', token='$NETBOX_TOKEN')
print([choice['value'] for choice in nb.dcim.interfaces.choices()['type']])
"
```

---

## 5. Кастомные TextFSM шаблоны

### 5.1 Приоритет парсинга

```
1. CUSTOM_TEXTFSM_TEMPLATES (core/constants.py)  ← приоритет
   │
   ▼
2. templates/*.textfsm (локальные шаблоны)
   │
   ▼
3. NTC Templates (fallback)
```

### 5.2 Виртуальные команды

Для одной команды можно использовать разные шаблоны:

```python
# core/constants.py
CUSTOM_TEXTFSM_TEMPLATES = {
    # Виртуальный ключ "port-security" для парсинга sticky MAC
    ("cisco_ios", "port-security"): "cisco_ios_port_security.textfsm",
}
```

```python
# Использование в коллекторе
response = conn.send_command("show running-config")
parsed = self._textfsm_parser.parse(
    output=response.result,
    platform="cisco_ios",
    command="port-security"  # виртуальный ключ
)
```

### 5.3 Пример шаблона

```textfsm
# templates/cisco_ios_port_security.textfsm
Value Required INTERFACE (\S+)
Value VLAN (\d+)
Value Required MAC ([0-9a-fA-F]{4}\.[0-9a-fA-F]{4}\.[0-9a-fA-F]{4})
Value TYPE (sticky)

Start
  ^interface\s+${INTERFACE} -> Interface

Interface
  ^\s+switchport\s+access\s+vlan\s+${VLAN}
  ^\s+switchport\s+port-security\s+mac-address\s+${TYPE}\s+${MAC} -> Record
  ^interface\s+${INTERFACE} -> Continue.Clearall
  ^interface\s+${INTERFACE} -> Interface
  ^end -> End
```

---

## 6. Соглашения по коду

### 6.1 Стиль кода

- **Типизация:** `typing` для всех публичных методов
- **Docstrings:** Google style
- **Логирование:** `logging` модуль или `get_logger()`
- **Форматирование:** black (опционально)

### 6.2 Паттерны

- **Strategy:** Collectors, Exporters — подключаемые стратегии
- **Template Method:** BaseCollector определяет скелет
- **Factory:** Создание устройств, коллекторов

### 6.3 Примеры

**Коллектор:**

```python
from typing import List, Dict, Any
from ..core.device import Device
from ..core.constants.commands import COLLECTOR_COMMANDS
from .base import BaseCollector

class NewCollector(BaseCollector):
    """Коллектор для сбора чего-то."""

    model_class = NewModel  # Модель данных

    # Команды загружаются из централизованного хранилища
    platform_commands = COLLECTOR_COMMANDS.get("new_collector", {})

    def _parse_output(
        self,
        output: str,
        device: Device,
    ) -> List[Dict[str, Any]]:
        """Парсит вывод команды."""
        return self._parse_with_ntc(output, device)
```

**Domain Normalizer:**

```python
from dataclasses import dataclass
from typing import List, Dict, Any

@dataclass
class NewNormalizer:
    """Нормализатор данных."""

    def normalize_dicts(
        self,
        raw_data: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Нормализует сырые данные."""
        return [self._normalize_row(row) for row in raw_data]

    def _normalize_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """Нормализует одну запись."""
        return {
            "field1": row.get("field1", "").strip(),
            "field2": self._normalize_field2(row.get("field2", "")),
        }
```

### 6.4 Логирование

```python
import logging

logger = logging.getLogger(__name__)

# Или через get_logger()
from network_collector.core import get_logger
logger = get_logger(__name__)

# Использование
logger.debug("Подключение к %s", device.host)
logger.info("Собрано %d записей", len(data))
logger.warning("Устройство %s недоступно", device.host)
logger.error("Ошибка парсинга: %s", str(e))
```

### 6.5 Исключения

```python
from network_collector.core.exceptions import (
    ConnectionError,
    AuthenticationError,
    TimeoutError,
    is_retryable,
)

try:
    conn = connection_manager.connect(device)
except AuthenticationError:
    logger.error("Неверные учётные данные для %s", device.host)
    raise
except ConnectionError as e:
    if is_retryable(e):
        # Можно повторить
        pass
    else:
        raise
```

---

## CI/CD

### GitHub Actions (пример)

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.10'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-dev.txt

      - name: Run tests
        run: |
          pytest tests/ -v --cov=network_collector --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

---

## Ресурсы

- [Pytest Documentation](https://docs.pytest.org/)
- [NTC Templates](https://github.com/networktocode/ntc-templates)
- [Scrapli Documentation](https://carlmontanari.github.io/scrapli/)
- [pynetbox Documentation](https://pynetbox.readthedocs.io/)
