# Тестирование Network Collector

Документация по запуску и написанию тестов для Network Collector.

## Содержание

1. [Быстрый старт](#быстрый-старт)
2. [Структура тестов](#структура-тестов)
3. [Запуск тестов](#запуск-тестов)
4. [Типы тестов](#типы-тестов)
5. [Что тестируем](#что-тестируем)
6. [Написание новых тестов](#написание-новых-тестов)
7. [Fixtures](#fixtures)
8. [Добавление нового вендора](#добавление-нового-вендора)

---

## Быстрый старт

### Установка зависимостей

```bash
# Из корневой директории проекта
pip install -r requirements-dev.txt
```

### Запуск всех тестов

```bash
# Все тесты
pytest tests/ -v

# Только unit тесты (быстрые)
pytest tests/ -v -m unit

# С coverage
pytest tests/ --cov=network_collector --cov-report=html
```

### Запуск конкретного теста

```bash
# Тесты определения типа интерфейса
pytest tests/test_collectors/test_port_type_detection.py -v

# Тесты NetBox маппинга
pytest tests/test_netbox/test_interface_type_mapping.py -v

# Тесты switchport mode
pytest tests/test_collectors/test_switchport_mode.py -v

# Конкретный тест-кейс
pytest tests/test_collectors/test_port_type_detection.py::TestPortTypeDetection::test_production_bug_25g_port_with_10g_sfp -v
```

---

## Структура тестов

```
tests/
├── conftest.py                                    # Общие fixtures для всех тестов
│
├── fixtures/                                      # Реальные выводы команд (для integration тестов)
│   ├── cisco_ios/
│   │   ├── show_interfaces.txt
│   │   ├── show_interfaces_switchport.txt
│   │   └── show_etherchannel_summary.txt
│   ├── cisco_nxos/
│   ├── arista_eos/
│   └── juniper_junos/
│
├── test_collectors/                               # Тесты коллекторов и нормализации
│   ├── test_port_type_detection.py                # _detect_port_type() (collectors/interfaces.py)
│   └── test_switchport_mode.py                    # Switchport mode логика (tagged vs tagged-all)
│
├── test_netbox/                                   # Тесты NetBox синхронизации
│   └── test_interface_type_mapping.py             # _get_interface_type() (netbox/sync.py)
│
└── test_parsers/                                  # Тесты парсинга (NTC Templates)
    └── (планируется)
```

---

## Запуск тестов

### Основные команды

```bash
# Все тесты с подробным выводом
pytest tests/ -v

# Тесты с коротким выводом
pytest tests/ -q

# Остановиться на первой ошибке
pytest tests/ -x

# Показать локальные переменные при ошибках
pytest tests/ -l

# Запустить последние упавшие тесты
pytest tests/ --lf

# Параллельный запуск (требует pytest-xdist)
pytest tests/ -n 4
```

### Фильтрация по markers

```bash
# Только unit тесты (быстрые)
pytest tests/ -m unit

# Только NetBox тесты
pytest tests/ -m netbox

# Только integration тесты
pytest tests/ -m integration

# Исключить медленные тесты
pytest tests/ -m "not slow"
```

### Coverage отчёты

```bash
# HTML отчёт (откроется в браузере)
pytest tests/ --cov=network_collector --cov-report=html
open htmlcov/index.html  # Linux/macOS
start htmlcov/index.html # Windows

# Terminal отчёт
pytest tests/ --cov=network_collector --cov-report=term

# Только непокрытые строки
pytest tests/ --cov=network_collector --cov-report=term-missing
```

### Отладка

```bash
# Запустить тест с pdb отладчиком
pytest tests/test_collectors/test_port_type_detection.py::test_name -v --pdb

# Показать print() вывод
pytest tests/ -v -s

# Verbose вывод pytest
pytest tests/ -vv
```

---

## Типы тестов

### 1. Unit Tests (`@pytest.mark.unit`)

**Что тестируем:** Отдельные функции и методы без внешних зависимостей.

**Примеры:**
- `test_port_type_detection.py` — логика определения типа порта
- `test_interface_type_mapping.py` — маппинг в NetBox типы
- `test_switchport_mode.py` — логика tagged vs tagged-all

**Характеристики:**
- ✅ Быстрые (миллисекунды)
- ✅ Не требуют fixtures с реальными данными
- ✅ Параметризованные (один тест → много кейсов)

**Запуск:**
```bash
pytest tests/ -m unit -v
```

### 2. Integration Tests (`@pytest.mark.integration`)

**Что тестируем:** Парсинг реальных выводов команд с устройств.

**Примеры:**
- Парсинг `show interfaces` (Cisco IOS, NX-OS, Arista)
- Парсинг `show etherchannel summary`
- Проверка единообразия вывода с разных платформ

**Характеристики:**
- 🟡 Средняя скорость
- 🟡 Требуют fixtures (реальные выводы команд)
- ✅ Параметризованные по платформам

**Запуск:**
```bash
pytest tests/ -m integration -v
```

### 3. NetBox Tests (`@pytest.mark.netbox`)

**Что тестируем:** Логика синхронизации с NetBox (с mock API).

**Примеры:**
- Создание/обновление устройств
- Синхронизация интерфейсов
- Создание кабелей из LLDP

**Характеристики:**
- 🟡 Требуют mock NetBox клиента
- 🟡 Тестируют бизнес-логику без реального API

**Запуск:**
```bash
pytest tests/ -m netbox -v
```

---

## Что тестируем

### 🔴 Приоритет 1: Критичная логика (unit tests)

#### 1. Определение типа интерфейса (`_detect_port_type`)

**Файл:** `collectors/interfaces.py:640-732`
**Тест:** `tests/test_collectors/test_port_type_detection.py`

**Зачем:** Нормализует данные с разных платформ в единый формат.

**Проверяем:**
- ✅ 25G порт с 10G SFP → `"10g-sfp+"` (по трансиверу, не по порту) — **ПРОДОВЫЙ БАГ**
- ✅ Приоритет: `media_type` > `hardware_type` > `interface name`
- ✅ LAG интерфейсы → `"lag"`
- ✅ Виртуальные интерфейсы → `"virtual"`
- ✅ Copper vs SFP (GigE по умолчанию RJ45, если нет SFP в hardware)

#### 2. Маппинг в NetBox типы (`_get_interface_type`)

**Файл:** `netbox/sync.py:485-520`
**Тест:** `tests/test_netbox/test_interface_type_mapping.py`

**Зачем:** Конвертирует наши типы в NetBox interface types.

**Проверяем:**
- ✅ `SFP-10GBase-LR` → `"10gbase-lr"` (не `"10gbase-x-sfpp"`) — **ПРОДОВЫЙ БАГ**
- ✅ Приоритет: `media_type` > `port_type` > `hardware_type` > `speed`
- ✅ Все варианты оптики (10G SR/LR/ER, 25G, 40G, 100G)
- ✅ Copper (RJ45, 10GBase-T)
- ✅ LAG и virtual интерфейсы

#### 3. Switchport Mode (`tagged` vs `tagged-all`)

**Файл:** `collectors/interfaces.py:524-637`
**Тест:** `tests/test_collectors/test_switchport_mode.py`

**Зачем:** Правильное определение режима транка для NetBox.

**Проверяем:**
- ✅ `trunk` + `"ALL"` → `"tagged-all"`
- ✅ `trunk` + `"1-4094"` → `"tagged-all"`
- ✅ `trunk` + `"10,20,30"` → `"tagged"`
- ✅ `access` → `"access"`
- ✅ LAG наследует mode от members (приоритет `tagged-all`)

---

### 🟡 Приоритет 2: Парсинг и нормализация (integration tests)

#### 4. Парсинг выводов команд (планируется)

**Проверяем:**
- Все платформы возвращают обязательные поля (`interface`, `status`, `mac`, `mode`)
- Статусы нормализуются (`up`/`down`/`disabled`/`error`)
- MAC-адреса в едином формате

#### 5. LAG Membership (планируется)

**Файл:** `collectors/interfaces.py:356-433`

**Проверяем:**
- Парсинг `show etherchannel summary` (Cisco IOS)
- Парсинг `show port-channel summary` (NX-OS, Arista)
- Fallback на regex если NTC не сработал

#### 6. LLDP/CDP Merge (планируется)

**Проверяем:**
- Объединение LLDP + CDP данных по `local_interface`
- CDP дополняет hostname если LLDP не дал `system_name`
- Определение `neighbor_type` (hostname/mac/ip/unknown)

---

## Написание новых тестов

### Шаблон unit теста

```python
"""
Описание что тестируется и зачем.
"""

import pytest
from network_collector.collectors.interfaces import InterfaceCollector


@pytest.fixture
def collector():
    """Создаём коллектор для тестирования."""
    return InterfaceCollector()


@pytest.mark.unit
class TestFeatureName:
    """Тесты для конкретной фичи."""

    @pytest.mark.parametrize("input_data,expected_output", [
        ({"interface": "Gi1/0/1", "media_type": "SFP-10GBase-LR"}, "10g-sfp+"),
        ({"interface": "Gi1/0/2", "media_type": "RJ45"}, "1g-rj45"),
    ])
    def test_something(self, collector, input_data, expected_output):
        """
        Описание теста.
        """
        result = collector.some_method(input_data)

        assert result == expected_output, (
            f"Input: {input_data}\n"
            f"Expected: {expected_output}, Got: {result}"
        )

    def test_production_bug_description(self, collector, sample_interface_data):
        """
        Регрессионный тест для конкретного бага из прода.
        """
        data = sample_interface_data["c9500_25g_with_10g_sfp"]
        result = collector.some_method(data)

        assert result == "expected_value", (
            f"Проблема из прода: описание\n"
            f"Expected: 'expected_value', Got: '{result}'"
        )
```

### Использование fixtures из conftest.py

```python
def test_with_fixtures(sample_interface_data, mock_netbox_client):
    """
    Используем готовые fixtures.

    - sample_interface_data: примеры интерфейсов
    - mock_netbox_client: mock NetBox API
    - load_fixture: загрузка из файлов
    """
    data = sample_interface_data["c9500_25g_with_10g_sfp"]
    # ... тест
```

### Параметризация

```python
@pytest.mark.parametrize("media_type,expected_type", [
    ("SFP-10GBase-LR", "10gbase-lr"),
    ("SFP-10GBase-SR", "10gbase-sr"),
    ("QSFP-40G-SR4", "40gbase-x-qsfpp"),
])
def test_parametrized(media_type, expected_type):
    """Один тест → много тест-кейсов."""
    result = map_media_type(media_type)
    assert result == expected_type
```

---

## Fixtures

### Встроенные fixtures (conftest.py)

#### `sample_interface_data`
Примеры данных интерфейсов для тестирования.

```python
def test_example(sample_interface_data):
    data = sample_interface_data["c9500_25g_with_10g_sfp"]
    # {
    #   "interface": "TwentyFiveGigE1/0/1",
    #   "media_type": "SFP-10GBase-LR",
    #   ...
    # }
```

**Доступные примеры:**
- `c9500_25g_with_10g_sfp` — 25G порт с 10G SFP (продовый баг)
- `standard_10g_sfp` — 10G порт с 10G SFP
- `gigabit_copper` — 1G RJ45
- `gigabit_sfp` — 1G SFP
- `port_channel` — LAG интерфейс
- `vlan_interface` — Виртуальный интерфейс
- `nxos_ethernet` — NX-OS Ethernet (100/1000/10000)

#### `sample_switchport_data`
Примеры switchport данных для тестирования mode.

```python
def test_example(sample_switchport_data):
    data = sample_switchport_data["trunk_all_vlans"]
    # {
    #   "switchport_mode": "trunk",
    #   "trunk_vlans": "ALL",
    #   ...
    # }
```

**Доступные примеры:**
- `trunk_all_vlans` — trunk с ALL
- `trunk_1_4094` — trunk с полным диапазоном
- `trunk_specific_vlans` — trunk 10,20,30
- `access_mode` — access VLAN 100

#### `mock_netbox_client`
Mock NetBox клиента для тестов без реального API.

```python
def test_example(mock_netbox_client):
    client = mock_netbox_client
    client.get_device_by_name.return_value = MagicMock(id=1)
```

#### `load_fixture`
Загрузка реальных выводов команд из файлов.

```python
def test_example(load_fixture):
    output = load_fixture("cisco_ios", "show_interfaces.txt")
    # Парсим output...
```

---

## Добавление нового вендора

### Процесс

1. **Собрать реальные выводы команд** с устройства

```bash
# На устройстве
show interfaces
show interfaces switchport
show etherchannel summary
show mac address-table
show lldp neighbors detail
```

2. **Создать fixtures**

```bash
mkdir tests/fixtures/new_vendor
# Сохранить выводы в .txt файлы
```

3. **Добавить платформу в параметризованные тесты**

```python
@pytest.mark.parametrize("platform,fixture_file", [
    ("cisco_ios", "show_interfaces.txt"),
    ("cisco_nxos", "show_interface.txt"),
    ("new_vendor", "show_interfaces.txt"),  # <-- Добавить
])
def test_parsing(platform, fixture_file):
    # ...
```

4. **Запустить тесты** — увидеть что падает

```bash
pytest tests/test_parsers/ -v
```

5. **Добавить парсинг/маппинг** в код

6. **Все тесты должны пройти** ✅

---

## Best Practices

### ✅ Рекомендуется

- **Параметризовать тесты** для проверки множества сценариев
- **Использовать fixtures** для переиспользования данных
- **Проверять продовые баги** (регрессионные тесты)
- **Проверять edge cases** (пустые значения, "unknown", регистр)
- **Писать docstrings** к тестам (что и зачем тестируем)
- **Группировать тесты** в классы (`TestPortTypeDetection`)
- **Использовать markers** (`@pytest.mark.unit`)

### ❌ Не рекомендуется

- Делать тесты зависимыми друг от друга
- Использовать реальные подключения к устройствам в unit тестах
- Дублировать логику тестов
- Игнорировать упавшие тесты
- Писать тесты без assert

---

## Troubleshooting

### Тесты не запускаются

```bash
# Проверить установку pytest
pytest --version

# Переустановить зависимости
pip install -r requirements-dev.txt
```

### Import errors

```bash
# Убедиться что запускаем из корня проекта
cd /home/sa/project
python -m pytest network_collector/tests/ -v

# Или добавить PYTHONPATH
export PYTHONPATH=/home/sa/project:$PYTHONPATH
pytest tests/ -v
```

### Fixture not found

Проверить что `conftest.py` находится в правильной директории:
```
tests/conftest.py  ✅
tests/test_collectors/conftest.py  ❌ (не нужен)
```

---

## CI/CD Integration

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

## Дополнительные ресурсы

- [Pytest Documentation](https://docs.pytest.org/)
- [Parametrize Guide](https://docs.pytest.org/en/stable/how-to/parametrize.html)
- [Fixtures Guide](https://docs.pytest.org/en/stable/how-to/fixtures.html)
- [Coverage.py](https://coverage.readthedocs.io/)

---

## Контакты

Если возникли вопросы по тестам, создайте issue в репозитории.
