# Network Collector — Тестирование

Документация по тестам проекта: структура, запуск, написание новых тестов.

## Содержание

1. [Обзор](#1-обзор)
2. [Запуск тестов](#2-запуск-тестов)
3. [Структура тестов](#3-структура-тестов)
4. [Fixtures](#4-fixtures)
5. [Маркеры](#5-маркеры)
6. [Написание тестов](#6-написание-тестов)
7. [Примеры тестов](#7-примеры-тестов)
8. [CI/CD](#8-cicd)

---

## 1. Обзор

| Метрика | Значение |
|---------|----------|
| **Всего тестов** | ~1340 |
| **Framework** | pytest |
| **Coverage** | ~85% |

**Категории тестов:**

| Категория | Описание | Количество |
|-----------|----------|------------|
| `test_core/` | Ядро: models, domain, pipeline, constants | ~400 |
| `test_collectors/` | Парсинг вывода устройств | ~150 |
| `test_parsers/` | NTC Templates, TextFSM | ~200 |
| `test_netbox/` | NetBox синхронизация | ~150 |
| `test_api/` | REST API endpoints | ~200 |
| `test_exporters/` | Excel, CSV, JSON экспорт | ~50 |
| `test_contracts/` | Контракты fields.yaml ↔ models | ~50 |
| `test_fixes/` | Регрессионные тесты для багфиксов | ~100 |
| `test_e2e/` | End-to-end тесты pipeline | ~40 |

---

## 2. Запуск тестов

### 2.1 Базовые команды

```bash
cd /home/sa/project
source network_collector/myenv/bin/activate

# Все тесты
pytest network_collector/tests/ -v

# Быстрый запуск (без verbose)
pytest network_collector/tests/ -q

# Остановиться на первой ошибке
pytest network_collector/tests/ -x

# Краткий вывод ошибок
pytest network_collector/tests/ --tb=short

# Показать самые медленные тесты
pytest network_collector/tests/ --durations=10
```

### 2.2 Запуск конкретных тестов

```bash
# Один файл
pytest tests/test_api/test_health.py -v

# Один класс
pytest tests/test_api/test_health.py::TestHealthEndpoints -v

# Один тест
pytest tests/test_api/test_health.py::TestHealthEndpoints::test_health -v

# По имени (pattern matching)
pytest tests/ -k "lldp" -v
pytest tests/ -k "test_normalize and not cdp" -v

# По директории
pytest tests/test_core/ -v
pytest tests/test_api/ -v
```

### 2.3 Запуск по маркерам

```bash
# Только unit тесты (быстрые)
pytest tests/ -m unit -v

# Только integration тесты
pytest tests/ -m integration -v

# Только API тесты
pytest tests/ -m api -v

# Исключить медленные
pytest tests/ -m "not slow" -v

# Комбинации
pytest tests/ -m "unit and not netbox" -v
```

### 2.4 Coverage

```bash
# Запуск с coverage
pytest tests/ --cov=network_collector --cov-report=html

# Открыть отчёт
open htmlcov/index.html

# Краткий отчёт в консоли
pytest tests/ --cov=network_collector --cov-report=term-missing
```

### 2.5 Параллельный запуск

```bash
# Установить pytest-xdist
pip install pytest-xdist

# Запуск на всех ядрах
pytest tests/ -n auto

# Запуск на 4 ядрах
pytest tests/ -n 4
```

---

## 3. Структура тестов

```
tests/
├── conftest.py              # Глобальные fixtures
├── fixtures/                # Тестовые данные
│   ├── cisco_ios/          # Вывод команд Cisco IOS
│   ├── cisco_nxos/         # Вывод команд Cisco NX-OS
│   ├── qtech/              # Вывод команд QTech
│   └── real_output/        # Реальные выводы с продакшена
│
├── test_api/               # API тесты
│   ├── conftest.py         # API fixtures (TestClient, auth headers)
│   ├── test_health.py      # Health endpoints
│   ├── test_auth.py        # Authentication
│   ├── test_collectors.py  # /api/devices, /api/mac, etc.
│   ├── test_sync.py        # /api/sync
│   ├── test_pipelines.py   # /api/pipelines
│   ├── test_history_service.py  # History service
│   └── test_tasks.py       # Task manager
│
├── test_core/              # Core модули
│   ├── test_models.py      # Data models (Interface, MACEntry, etc.)
│   ├── test_constants.py   # Platform mappings
│   ├── test_credentials.py # Credentials management
│   ├── test_context.py     # RunContext
│   ├── test_exceptions.py  # Custom exceptions
│   ├── test_logging.py     # Structured logging
│   ├── test_field_registry.py  # Field Registry
│   ├── test_domain/        # Domain layer
│   │   ├── test_lldp_normalizer.py
│   │   ├── test_mac_normalizer.py
│   │   ├── test_interface_normalizer.py
│   │   ├── test_inventory_normalizer.py
│   │   └── test_sync_comparator.py
│   └── test_pipeline/      # Pipeline система
│       ├── test_models.py
│       ├── test_executor.py
│       └── test_executor_integration.py
│
├── test_collectors/        # Collectors
│   ├── test_port_type_detection.py
│   ├── test_switchport_mode.py
│   └── test_lldp_parsing.py
│
├── test_parsers/           # Парсинг
│   ├── test_mac.py
│   ├── test_lldp.py
│   ├── test_interfaces.py
│   ├── test_inventory.py
│   ├── test_version.py
│   └── test_nxos_enrichment.py
│
├── test_netbox/            # NetBox синхронизация
│   ├── test_sync_integration.py
│   ├── test_sync_base.py
│   ├── test_inventory_sync.py
│   └── test_vlans_sync.py
│
├── test_exporters/         # Экспорт
│   ├── test_csv_exporter.py
│   └── test_raw_exporter.py
│
├── test_contracts/         # Контракты
│   └── test_fields_contract.py
│
├── test_fixes/             # Регрессия
│   ├── test_sync_preview.py
│   ├── test_interface_enabled.py
│   └── test_platform_mapping.py
│
├── test_e2e/               # End-to-end
│   └── test_sync_pipeline.py
│
└── test_cli/               # CLI тесты
    ├── test_pipeline.py
    └── test_sync_summary.py
```

---

## 4. Fixtures

### 4.1 Глобальные fixtures (conftest.py)

| Fixture | Описание |
|---------|----------|
| `fixtures_dir` | Путь к `tests/fixtures/` |
| `load_fixture` | Загрузка тестовых данных из файлов |
| `mock_netbox_client` | Mock NetBox клиента |
| `sample_interface_data` | Примеры данных интерфейсов |
| `sample_switchport_data` | Примеры switchport данных |
| `expected_fields` | Обязательные поля для каждого типа данных |

### 4.2 Использование load_fixture

```python
def test_parse_mac(load_fixture):
    """Тест парсинга MAC-таблицы."""
    output = load_fixture("cisco_ios", "show_mac_address-table.txt")
    result = parse_output("cisco_ios", "show mac address-table", output)
    assert len(result) > 0
```

### 4.3 API fixtures (test_api/conftest.py)

| Fixture | Описание |
|---------|----------|
| `client` | TestClient для FastAPI |
| `credentials_data` | Тестовые SSH credentials |
| `netbox_config_data` | Тестовый NetBox config |
| `auth_headers` | Headers с SSH credentials |
| `full_auth_headers` | Headers с SSH + NetBox |
| `client_with_credentials` | Client с auto-auth |
| `client_with_netbox` | Client с NetBox auth |

### 4.4 Использование API fixtures

```python
def test_health(client):
    """Тест health endpoint."""
    response = client.get("/health")
    assert response.status_code == 200

def test_collect_devices(client_with_credentials):
    """Тест сбора с auth."""
    response = client_with_credentials.post(
        "/api/devices/collect",
        json={"devices": []}
    )
    assert response.status_code == 200
```

---

## 5. Маркеры

Определены в `pytest.ini`:

```ini
[pytest]
markers =
    unit: Unit tests (fast, isolated)
    e2e: End-to-end tests (full pipeline)
    integration: Integration tests (real I/O)
    api: API endpoint tests
```

### 5.1 Использование маркеров

```python
import pytest

@pytest.mark.unit
class TestMACNormalizer:
    """Unit тесты нормализации MAC."""

    def test_normalize_mac(self):
        ...

@pytest.mark.integration
class TestNetBoxSync:
    """Integration тесты синхронизации."""

    def test_sync_interfaces(self):
        ...

@pytest.mark.slow
def test_full_pipeline():
    """Медленный тест полного pipeline."""
    ...
```

---

## 6. Написание тестов

### 6.1 Структура теста

```python
"""
Tests for <Module>.

Проверяет:
- Функция A
- Функция B
"""

import pytest

from network_collector.core.domain import LLDPNormalizer
from network_collector.core.models import LLDPNeighbor


@pytest.mark.unit
class TestLLDPNormalizer:
    """Тесты нормализации LLDP."""

    def setup_method(self):
        """Инициализация перед каждым тестом."""
        self.normalizer = LLDPNormalizer()

    def test_normalize_basic(self):
        """Базовая нормализация LLDP записей."""
        raw_data = [{"local_interface": "Gi0/1", "remote_hostname": "switch2"}]
        result = self.normalizer.normalize(raw_data)

        assert len(result) == 1
        assert isinstance(result[0], LLDPNeighbor)
        assert result[0].local_interface == "Gi0/1"
```

### 6.2 Параметризованные тесты

```python
@pytest.mark.parametrize("ntc_key, standard_key, value", [
    ("local_intf", "local_interface", "Gi0/1"),
    ("neighbor", "remote_hostname", "switch2"),
    ("neighbor_name", "remote_hostname", "switch2"),
    ("mgmt_ip", "remote_ip", "10.0.0.1"),
])
def test_key_mapping(self, ntc_key, standard_key, value):
    """Тест маппинга NTC ключей в стандартные."""
    raw_data = [{ntc_key: value, "local_interface": "Gi0/1"}]
    result = self.normalizer.normalize_dicts(raw_data)

    assert result[0].get(standard_key) == value
```

### 6.3 Mocking

```python
from unittest.mock import Mock, MagicMock, patch

def test_sync_with_mock(self):
    """Тест синхронизации с mock NetBox."""
    mock_client = Mock()
    mock_client.get_device_by_name.return_value = MagicMock(id=1)
    mock_client.get_interfaces.return_value = []

    sync = NetBoxSync(mock_client)
    result = sync.sync_interfaces("switch-01", [])

    mock_client.get_device_by_name.assert_called_once_with("switch-01")

@patch("network_collector.core.connection.Scrapli")
def test_connection(self, mock_scrapli):
    """Тест подключения с mock SSH."""
    mock_scrapli.return_value.open.return_value = None
    ...
```

### 6.4 Тестирование исключений

```python
def test_invalid_input_raises(self):
    """Неверный ввод вызывает исключение."""
    with pytest.raises(ValueError, match="Invalid MAC"):
        normalize_mac("invalid")

def test_connection_error(self):
    """Ошибка подключения."""
    with pytest.raises(ConnectionError):
        connect_to_device("unreachable", timeout=1)
```

### 6.5 Тестирование API

```python
class TestHealthEndpoints:
    """Тесты health check."""

    def test_health(self, client):
        """GET /health возвращает статус."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data

    def test_collect_requires_auth(self, client):
        """Сбор требует credentials."""
        response = client.post("/api/devices/collect", json={"devices": []})

        # Без auth — работает (credentials опциональны для пустого списка)
        assert response.status_code == 200
```

---

## 7. Примеры тестов

### 7.1 Unit тест модели

```python
# tests/test_core/test_models.py

from network_collector.core.models import Interface

class TestInterfaceModel:
    """Тесты модели Interface."""

    def test_from_dict(self):
        """Создание из словаря."""
        data = {
            "name": "GigabitEthernet0/1",
            "status": "up",
            "ip_address": "10.0.0.1",
        }
        intf = Interface.from_dict(data)

        assert intf.name == "GigabitEthernet0/1"
        assert intf.status == "up"
        assert intf.ip_address == "10.0.0.1"

    def test_to_dict(self):
        """Сериализация в словарь."""
        intf = Interface(name="Gi0/1", status="up")
        data = intf.to_dict()

        assert data["name"] == "Gi0/1"
        assert data["status"] == "up"
```

### 7.2 Integration тест NetBox

```python
# tests/test_netbox/test_sync_integration.py

class TestNetBoxSyncInterfaces:
    """Тесты синхронизации интерфейсов."""

    @pytest.fixture
    def mock_client(self):
        client = Mock()
        client.get_device_by_name.return_value = MagicMock(id=1, name="switch-01")
        client.get_interfaces.return_value = []
        return client

    def test_sync_creates_interface(self, mock_client):
        """Синхронизация создаёт новый интерфейс."""
        sync = NetBoxSync(mock_client, dry_run=False)
        interfaces = [Interface(name="Gi0/1", status="up")]

        result = sync.sync_interfaces("switch-01", interfaces)

        assert result["created"] == 1
        mock_client.create_interface.assert_called_once()
```

### 7.3 API тест

```python
# tests/test_api/test_pipelines.py

class TestPipelinesAPI:
    """Тесты Pipeline API."""

    def test_list_pipelines(self, client):
        """GET /api/pipelines возвращает список."""
        response = client.get("/api/pipelines")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_get_pipeline(self, client):
        """GET /api/pipelines/{id} возвращает pipeline."""
        response = client.get("/api/pipelines/default")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "default"
        assert "steps" in data
```

### 7.4 Тест с fixtures файлами

```python
# tests/test_parsers/test_lldp.py

class TestLLDPParsing:
    """Тесты парсинга LLDP."""

    def test_parse_cisco_ios(self, load_fixture):
        """Парсинг LLDP с Cisco IOS."""
        output = load_fixture("cisco_ios", "show_lldp_neighbors_detail.txt")
        result = parse_lldp(output, "cisco_ios")

        assert len(result) > 0
        assert "local_interface" in result[0]
        assert "remote_hostname" in result[0]
```

---

## 8. CI/CD

### 8.1 Локальный pre-commit

```bash
# Запуск перед коммитом
pytest tests/ -x -q --tb=short

# Быстрая проверка (только unit)
pytest tests/ -m unit -x -q
```

### 8.2 GitHub Actions (пример)

```yaml
# .github/workflows/tests.yml
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
          pip install pytest pytest-cov

      - name: Run tests
        run: pytest tests/ -v --cov=network_collector

      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

### 8.3 Рекомендации

1. **Перед коммитом:** `pytest tests/ -x -q`
2. **Новый код:** писать тесты сразу
3. **Багфикс:** добавить регрессионный тест в `test_fixes/`
4. **Маркеры:** использовать `@pytest.mark.unit` для быстрых тестов
5. **Fixtures:** переиспользовать из `conftest.py`

---

## Контакты

Вопросы по тестам — создайте issue в репозитории.
