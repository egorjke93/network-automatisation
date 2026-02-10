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
8. [E2E тесты](#8-e2e-тесты)
9. [Добавление тестов для новых платформ](#9-добавление-тестов-для-новых-платформ)
10. [Покрытие и дублирование тестов](#10-покрытие-и-дублирование-тестов)
11. [CI/CD](#11-cicd)

---

## 1. Обзор

| Метрика | Значение |
|---------|----------|
| **Всего тестов** | 1788 |
| **Framework** | pytest |
| **Coverage** | ~85% |

**Категории тестов:**

| Категория | Описание | Количество |
|-----------|----------|------------|
| `test_core/` | Ядро: models, domain, pipeline, constants | 763 |
| `test_collectors/` | Парсинг вывода устройств | 76 |
| `test_parsers/` | NTC Templates, TextFSM | 66 |
| `test_netbox/` | NetBox синхронизация (включая bulk, VLAN) | 286 |
| `test_api/` | REST API endpoints | 148 |
| `test_exporters/` | Excel, CSV, JSON, Raw экспорт | 61 |
| `test_contracts/` | Контракты fields.yaml ↔ models | 28 |
| `test_fixes/` | Регрессионные тесты для багфиксов | 31 |
| `test_e2e/` | End-to-end тесты pipeline и collectors | 189 |
| `test_cli/` | CLI команды (pipeline, sync summary, format) | 53 |
| `test_configurator/` | Push описаний, retry логика | 12 |
| *корневые* | QTech support, templates, refactoring utils | 75 |

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
├── test_qtech_support.py    # QTech: config, interface maps, LAG, inventory
├── test_qtech_templates.py  # QTech TextFSM шаблоны: парсинг всех команд
├── test_refactoring_utils.py # SyncStats, SECONDARY_COMMANDS, detect_type
├── fixtures/                # Тестовые данные
│   ├── cisco_ios/          # Вывод команд Cisco IOS
│   ├── cisco_nxos/         # Вывод команд Cisco NX-OS
│   ├── qtech/              # Вывод команд QTech
│   └── real_output/        # Реальные выводы с продакшена
│
├── test_api/               # API тесты (148)
│   ├── conftest.py         # API fixtures (TestClient, auth headers)
│   ├── test_health.py      # Health endpoints
│   ├── test_auth.py        # Authentication
│   ├── test_collectors.py  # /api/devices, /api/mac, etc.
│   ├── test_sync.py        # /api/sync
│   ├── test_pipelines.py   # /api/pipelines
│   ├── test_history_service.py  # History service
│   ├── test_tasks.py       # Task manager
│   ├── test_device_management.py  # CRUD устройств
│   └── test_integration.py # Интеграционные тесты API
│
├── test_core/              # Core модули (763)
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
│   │   ├── test_sync_comparator.py
│   │   ├── test_lldp_real_data.py    # Тесты на реальных LLDP данных
│   │   └── test_vlan.py              # VlanSet: операции над множествами VLAN
│   └── test_pipeline/      # Pipeline система
│       ├── test_models.py
│       ├── test_executor.py
│       ├── test_executor_cleanup.py   # Cleanup в pipeline
│       └── test_executor_integration.py
│
├── test_collectors/        # Collectors (76)
│   ├── test_port_type_detection.py    # Определение типа порта (SFP/RJ45)
│   ├── test_switchport_mode.py
│   └── test_lldp_parsing.py
│
├── test_parsers/           # Парсинг (66)
│   ├── test_mac.py
│   ├── test_lldp.py
│   ├── test_interfaces.py
│   ├── test_inventory.py
│   ├── test_version.py
│   └── test_nxos_enrichment.py
│
├── test_netbox/            # NetBox синхронизация (286)
│   ├── test_sync_integration.py
│   ├── test_sync_base.py
│   ├── test_sync_interfaces_vlan.py   # Interface VLAN sync (19 тестов)
│   ├── test_inventory_sync.py
│   ├── test_vlans_sync.py
│   ├── test_bulk_operations.py        # Bulk API операции (32 теста)
│   ├── test_diff.py                   # DiffCalculator тесты
│   ├── test_interface_type_mapping.py # get_netbox_interface_type() маппинг
│   ├── test_lag_batch_create.py       # LAG batch create (2-фазное создание)
│   └── test_polygon_emulation.py      # Polygon эмуляция NetBox
│
├── test_exporters/         # Экспорт (61)
│   ├── test_csv_exporter.py
│   ├── test_excel_exporter.py
│   ├── test_json_exporter.py
│   └── test_raw_exporter.py
│
├── test_contracts/         # Контракты (28)
│   └── test_fields_contract.py
│
├── test_fixes/             # Регрессия (31)
│   ├── test_sync_preview.py
│   ├── test_interface_enabled.py
│   └── test_platform_mapping.py
│
├── test_e2e/               # End-to-end тесты (189)
│   ├── conftest.py         # E2E fixtures (mock_device, PLATFORM_FIXTURES)
│   ├── test_interface_collector_e2e.py  # Interface collector E2E
│   ├── test_mac_collector_e2e.py        # MAC collector E2E
│   ├── test_lldp_collector_e2e.py       # LLDP collector E2E
│   ├── test_inventory_collector_e2e.py  # Inventory collector E2E
│   ├── test_ip_collector_e2e.py         # IP-адреса: parse → IPAddressEntry (24 теста)
│   ├── test_sync_full_device.py         # Полный sync: inventory, IP, VLAN (16 тестов)
│   ├── test_multi_device_collection.py  # Параллельный сбор, partial failures (12 тестов)
│   ├── test_nxos_enrichment_e2e.py      # NX-OS enrichment: switchport, transceiver, LAG (15 тестов)
│   ├── test_config_backup_e2e.py        # Config backup E2E
│   ├── test_device_collector_e2e.py     # Device collector E2E
│   ├── test_pipeline.py    # Pipeline E2E
│   └── test_sync_pipeline.py  # Sync pipeline E2E
│
├── test_configurator/      # Push описаний (12)
│   └── test_pusher_retry.py  # Retry логика push описаний
│
└── test_cli/               # CLI тесты (53)
    ├── test_format_parsed.py  # --format parsed
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
    netbox: NetBox sync tests (54 теста)
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

## 8. E2E тесты

End-to-end тесты проверяют полный цикл: fixture → parse → normalize → model → sync.
Без реального SSH или NetBox — все зависимости замоканы.

### 8.1 Структура E2E тестов

| Файл | Что тестирует | Тестов |
|------|--------------|--------|
| `test_ip_collector_e2e.py` | IP из show interfaces → IPAddressEntry, with_prefix, ensure_list | 24 |
| `test_sync_full_device.py` | Inventory/IP/VLAN sync (dry_run), full device workflow | 16 |
| `test_multi_device_collection.py` | Параллельный сбор, partial failures, progress callback | 12 |
| `test_nxos_enrichment_e2e.py` | NX-OS enrichment: switchport, transceiver, LAG, full pipeline | 15 |
| `test_interface_collector_e2e.py` | Interface collector E2E по платформам | ~30 |
| `test_mac_collector_e2e.py` | MAC collector E2E | ~20 |
| `test_lldp_collector_e2e.py` | LLDP/CDP collector E2E | ~25 |
| `test_inventory_collector_e2e.py` | Inventory collector E2E | ~20 |
| `test_pipeline.py` | Pipeline: parse → normalize → export | ~20 |
| `test_sync_pipeline.py` | Sync pipeline: LLDP→cables, interfaces, devices | ~14 |

### 8.2 Паттерн sync E2E теста

```python
from network_collector.netbox.sync import NetBoxSync

def test_sync_pipeline(parser, mock_netbox_client):
    """Parse → Model → sync (dry_run)."""
    # 1. Загружаем fixture
    output = load_fixture("cisco_ios", "show_inventory.txt")
    parsed = parser.parse(output, "cisco_ios", "show inventory")

    # 2. Конвертируем в модели
    items = [InventoryItem.from_dict(row) for row in parsed]

    # 3. Sync (dry_run — без реального NetBox)
    sync = NetBoxSync(mock_netbox_client, dry_run=True)
    result = sync.sync_inventory("switch-01", items)

    # 4. Проверяем stats
    assert result["created"] >= 0
    assert result["failed"] == 0
```

### 8.3 Паттерн multi-device теста

```python
def test_partial_failure():
    """1 из 3 устройств падает — остальные работают."""
    def fake_collect(device):
        if device.host == "10.0.0.2":
            raise ConnectionError("unreachable")
        return [{"interface": "Gi0/1", ...}]

    collector = InterfaceCollector(credentials=None)
    with patch.object(collector, '_collect_from_device', side_effect=fake_collect):
        result = collector.collect_dicts(devices, parallel=True)

    assert len(result) == 2  # Данные от 2 из 3
```

### 8.4 Паттерн enrichment теста

```python
def test_enrichment_pipeline(normalizer):
    """Базовые данные + enrichment → обогащённые модели."""
    data = normalizer.normalize_dicts(parsed, hostname="nxos-switch")

    # Enrichment: LAG → switchport → media_type
    data = normalizer.enrich_with_lag(data, lag_membership)
    data = normalizer.enrich_with_switchport(data, switchport_modes)
    data = normalizer.enrich_with_media_type(data, media_types)

    # Конвертируем в модели
    interfaces = [Interface.from_dict(row) for row in data]
    assert any(i.lag for i in interfaces)
```

---

## 9. Добавление тестов для новых платформ

При добавлении новой платформы (например, `arista_eos`, `juniper_junos`) большинство E2E тестов подхватятся **автоматически** — нужно только добавить fixture-файлы и зарегистрировать платформу.

### 9.1 Чеклист

| # | Что сделать | Где |
|---|-----------|-----|
| 1 | Создать папку с fixture-файлами | `tests/fixtures/<platform>/` |
| 2 | Добавить платформу в `SUPPORTED_PLATFORMS` | `tests/test_e2e/conftest.py` |
| 3 | Добавить маппинг файлов в `PLATFORM_FIXTURES` | `tests/test_e2e/conftest.py` |
| 4 | (Опционально) Добавить platform-specific тесты | `tests/test_e2e/` |

### 9.2 Шаг 1: Fixture-файлы

Создайте папку `tests/fixtures/<platform>/` и поместите туда реальные выводы команд:

```
tests/fixtures/arista_eos/
├── show_interfaces.txt          # show interfaces
├── show_mac_address_table.txt   # show mac address-table
├── show_lldp_neighbors_detail.txt  # show lldp neighbors detail
├── show_inventory.txt           # show inventory
├── show_version.txt             # show version
├── show_interfaces_switchport.txt  # show interfaces switchport
└── show_interface_status.txt    # show interface status
```

### 9.3 Шаг 2: Регистрация в conftest.py

```python
# tests/test_e2e/conftest.py

SUPPORTED_PLATFORMS = [
    "cisco_ios",
    "cisco_nxos",
    "qtech",
    "arista_eos",  # ← добавить
]

PLATFORM_FIXTURES = {
    # ... существующие ...
    "arista_eos": {  # ← добавить
        "interfaces": "show_interfaces.txt",
        "mac": "show_mac_address_table.txt",
        "lldp": "show_lldp_neighbors_detail.txt",
        "inventory": "show_inventory.txt",
        "version": "show_version.txt",
    },
}
```

### 9.4 Что запустится автоматически

После регистрации платформы все параметризованные E2E тесты запустятся для неё:

- `test_interface_collector_e2e.py` — парсинг интерфейсов, нормализация, модели
- `test_mac_collector_e2e.py` — парсинг MAC-таблицы
- `test_lldp_collector_e2e.py` — парсинг LLDP/CDP
- `test_inventory_collector_e2e.py` — парсинг inventory

Тесты используют `@pytest.mark.parametrize("platform", SUPPORTED_PLATFORMS)` — новая платформа автоматически включается во все проверки.

### 9.5 Когда нужны отдельные тесты

Отдельные тесты пишутся только при наличии **платформо-специфичной логики**:

| Ситуация | Пример | Действие |
|----------|--------|----------|
| Уникальная enrichment-команда | NX-OS: `show interface transceiver` | Отдельный E2E тест |
| Особый формат вывода | QTech: другой формат MAC | Тест в `test_parsers/` |
| Специфичная нормализация | Juniper: `xe-0/0/0` → `xe-0/0/0` | Тест в `test_core/test_domain/` |
| Стандартный вывод | Arista EOS (похож на IOS) | **Не нужен** — хватит E2E |

### 9.6 Проверка

```bash
# Запустить E2E тесты для новой платформы
pytest tests/test_e2e/ -v -k "arista_eos"

# Проверить что парсинг работает
pytest tests/test_e2e/ -v -k "arista_eos" --tb=short
```

---

## 10. Покрытие и дублирование тестов

### 10.1 Принципы

- **Каждый тест проверяет одну вещь** — unit тест проверяет функцию, E2E проверяет pipeline
- **Допустимое пересечение** — unit тест проверяет `normalize()` изолированно, E2E проверяет `parse → normalize → model` цепочку
- **Избегать дублирования** — не писать одинаковые тесты в разных файлах

### 10.2 Слои тестирования

```
┌─────────────────────────────────────────────┐
│  E2E тесты (test_e2e/)                      │
│  fixture → parse → normalize → model → sync │
│  Проверяют: интеграция слоёв, полный цикл   │
├─────────────────────────────────────────────┤
│  Integration тесты (test_netbox/)           │
│  Проверяют: sync логику, batch API, VLANs   │
├─────────────────────────────────────────────┤
│  Unit тесты (test_core/, test_parsers/)     │
│  Проверяют: отдельные функции, модели       │
└─────────────────────────────────────────────┘
```

### 10.3 Где что тестировать

| Что тестируется | Где | Пример |
|----------------|-----|--------|
| Маппинг ключей NTC → стандартные | `test_core/test_domain/` | `test_interface_normalizer.py` |
| Парсинг конкретного вывода | `test_parsers/` | `test_interfaces.py` |
| Полный pipeline (parse → model) | `test_e2e/` | `test_interface_collector_e2e.py` |
| Sync логика (create/update/delete) | `test_netbox/` | `test_sync_integration.py` |
| Sync pipeline (parse → sync dry_run) | `test_e2e/` | `test_sync_full_device.py` |
| Batch API (bulk операции) | `test_netbox/` | `test_bulk_operations.py` |
| API endpoints | `test_api/` | `test_sync.py` |
| Регрессия конкретного бага | `test_fixes/` | `test_interface_enabled.py` |

### 10.4 Известные пересечения

Некоторые E2E collector тесты (`test_interface_collector_e2e.py`, `test_mac_collector_e2e.py` и др.) содержат тесты нормализации, которые частично совпадают с unit тестами в `test_core/test_domain/`. Это **допустимо** — unit тесты проверяют edge cases функции, E2E проверяют что вся цепочка работает с реальным fixture.

**Не допускается** дублирование одинаковых тестов внутри одного слоя (например, два E2E файла проверяющих одно и то же).

---

## 11. CI/CD



### 11.1 Локальный pre-commit

```bash
# Запуск перед коммитом
pytest tests/ -x -q --tb=short

# Быстрая проверка (только unit)
pytest tests/ -m unit -x -q
```

### 11.2 GitHub Actions (пример)

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

### 11.3 Рекомендации

1. **Перед коммитом:** `pytest tests/ -x -q`
2. **Новый код:** писать тесты сразу
3. **Багфикс:** добавить регрессионный тест в `test_fixes/`
4. **Маркеры:** использовать `@pytest.mark.unit` для быстрых тестов
5. **Fixtures:** переиспользовать из `conftest.py`

---

## Контакты

Вопросы по тестам — создайте issue в репозитории.
