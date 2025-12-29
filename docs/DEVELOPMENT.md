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
│   ├── arista_eos/
│   └── juniper_junos/
├── test_collectors/               # Тесты коллекторов
├── test_netbox/                   # Тесты NetBox синхронизации
├── test_parsers/                  # Тесты парсинга
├── test_core/                     # Тесты core модулей
│   ├── test_constants.py
│   ├── test_config_schema.py
│   └── test_domain/               # Тесты Domain Layer
├── test_contracts/                # Contract тесты
├── test_integration/              # Интеграционные тесты
└── test_e2e/                      # E2E тесты
```

### 2.2 Запуск тестов

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
from network_collector.collectors.interfaces import InterfaceCollector


@pytest.fixture
def collector():
    """Создаём коллектор для тестирования."""
    return InterfaceCollector()


@pytest.mark.unit
class TestPortTypeDetection:
    """Тесты для _detect_port_type()."""

    @pytest.mark.parametrize("input_data,expected", [
        ({"interface": "Gi1/0/1", "media_type": "SFP-10GBase-LR"}, "10g-sfp+"),
        ({"interface": "Gi1/0/2", "media_type": "RJ45"}, "1g-rj45"),
    ])
    def test_basic(self, collector, input_data, expected):
        """Базовые кейсы."""
        result = collector._detect_port_type(input_data, input_data["interface"].lower())
        assert result == expected

    def test_production_bug_25g_with_10g_sfp(self, collector):
        """Регрессионный тест для бага из прода."""
        data = {
            "interface": "TwentyFiveGigE1/0/1",
            "media_type": "SFP-10GBase-LR",
        }
        result = collector._detect_port_type(data, data["interface"].lower())
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
│ 2. collectors/*.py — КОМАНДЫ                                                 │
│    • platform_commands = {"newvendor": "show ..."}                          │
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

```python
# collectors/mac.py
class MACCollector(BaseCollector):
    platform_commands = {
        "cisco_ios": "show mac address-table",
        "eltex": "show mac address-table",      # ← ДОБАВИТЬ
    }

# collectors/interfaces.py
class InterfaceCollector(BaseCollector):
    platform_commands = {
        "cisco_ios": "show interfaces",
        "eltex": "show interfaces",              # ← ДОБАВИТЬ
    }

    lag_commands = {
        "cisco_ios": "show etherchannel summary",
        "eltex": "show lacp summary",            # ← если команда другая
    }
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
| SSH драйвер | `core/constants.py` | `SCRAPLI_PLATFORM_MAP` |
| NTC парсер | `core/constants.py` | `NTC_PLATFORM_MAP` |
| Производитель | `core/constants.py` | `VENDOR_MAP` |
| Команда MAC | `collectors/mac.py` | `platform_commands` |
| Команда interfaces | `collectors/interfaces.py` | `platform_commands` |
| Команда LAG | `collectors/interfaces.py` | `lag_commands` |
| Команда switchport | `collectors/interfaces.py` | `switchport_commands` |
| Команда LLDP | `collectors/lldp.py` | `lldp_commands` |
| Команда CDP | `collectors/lldp.py` | `cdp_commands` |
| Команда inventory | `collectors/inventory.py` | `platform_commands` |
| Команда backup | `collectors/config_backup.py` | `BACKUP_COMMANDS` |
| Кастомный шаблон | `core/constants.py` | `CUSTOM_TEXTFSM_TEMPLATES` |

---

## 4. Добавление типа интерфейса

### 4.1 Двухуровневая архитектура

```
┌────────────────────────────────────────────────────────────────┐
│ 1. Коллектор → port_type (платформонезависимый)                 │
│    _detect_port_type() в collectors/interfaces.py               │
│    Результат: "10g-sfp+", "1g-rj45", "lag", "virtual"          │
├────────────────────────────────────────────────────────────────┤
│ 2. Sync → NetBox type                                           │
│    _get_interface_type() в netbox/sync.py                       │
│    Результат: "10gbase-x-sfpp", "1000base-t", "lag"            │
└────────────────────────────────────────────────────────────────┘
```

### 4.2 Добавление нового типа

**Пример: добавить 400G**

```python
# 1. collectors/interfaces.py → _detect_port_type()
if iface_lower.startswith(("fourhundredgig", "fh")):
    return "400g-qsfp-dd"

# 2. netbox/sync.py → _get_interface_type() → port_type_map
port_type_map = {
    "400g-qsfp-dd": "400gbase-x-qsfpdd",
}
```

### 4.3 Приоритет определения

```
1. port_type (из коллектора)     — платформонезависимый
   ↓ если пустой
2. media_type (SFP-10GBase-SR)   — самый точный
   ↓ если пустой
3. hardware_type (100/1000/10000) — макс. скорость
   ↓ если пустой
4. interface_name (TenGigabit)    — по имени
   ↓ если не определился
5. defaults.type из fields.yaml   — fallback
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
from .base import BaseCollector

class NewCollector(BaseCollector):
    """Коллектор для сбора чего-то."""

    model_class = NewModel  # Модель данных

    platform_commands = {
        "cisco_ios": "show something",
        "arista_eos": "show something else",
    }

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
