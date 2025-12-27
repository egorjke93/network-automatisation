# План развития Network Collector

## Статус выполнения

### PRIORITY 1 — Надёжность и контроль (СДЕЛАНО)

| # | Задача | Статус | Описание |
|---|--------|--------|----------|
| 1 | RunContext | ✅ DONE | `core/context.py` — run_id, dry_run, timing, output_dir |
| 2 | Data Models | ✅ DONE | `core/models.py` — Interface, MACEntry, LLDPNeighbor, InventoryItem |
| 3 | Diff before Apply | ✅ DONE | `netbox/diff.py` — DiffCalculator, предпросмотр изменений |

### PRIORITY 2 — Ошибки, логи, тестируемость (СДЕЛАНО)

| # | Задача | Статус | Описание |
|---|--------|--------|----------|
| 4 | Typed Exceptions | ✅ DONE | `core/exceptions.py` — иерархия ошибок, is_retryable |
| 5 | Structured Logs | ✅ DONE | `core/logging.py` — JSON формат, ротация, LogConfig |
| 6 | Tests | ✅ DONE | 418 тестов проходят |

### PRIORITY 3 — Конфиги и безопасность (СДЕЛАНО)

| # | Задача | Статус | Описание |
|---|--------|--------|----------|
| 7 | Config Validation | ✅ DONE | `core/config_schema.py` — Pydantic схемы для config.yaml |
| 8 | Secrets Management | ✅ DONE | keyring уже есть в проекте |

### PRIORITY 4 — Архитектура (СДЕЛАНО)

| # | Задача | Статус | Описание |
|---|--------|--------|----------|
| 9 | Layer Boundaries | ✅ DONE | collectors не знают про NetBox (проверено) |
| 10 | Documentation | ✅ DONE | CLAUDE.md, ARCHITECTURE.md |

### Рефакторинг (СДЕЛАНО)

| Задача | Статус | Описание |
|--------|--------|----------|
| Дублирование кода | ✅ DONE | normalize_mac*, normalize_interface_short, slugify в constants.py |
| Логирование в CLI | ✅ DONE | get_logger() везде, config.yaml управляет |
| Тесты constants.py | ✅ DONE | 75 тестов для normalize_mac, normalize_interface, slugify |
| Тесты config_schema | ✅ DONE | 35 тестов для Pydantic валидации |
| Domain Layer | ✅ DONE | `core/domain/` — InterfaceNormalizer, MACNormalizer, LLDPNormalizer |

---

## Что было сделано

### Тесты для новых функций

```
tests/test_core/test_constants.py (75 тестов)
├── TestNormalizeMacRaw
├── TestNormalizeMacIeee
├── TestNormalizeMacNetbox
├── TestNormalizeMacCisco
├── TestNormalizeMacWithFormat
├── TestNormalizeInterfaceShort
├── TestNormalizeInterfaceShortLowercase
├── TestNormalizeInterfaceFull
└── TestSlugify
```

### Config Validation — Pydantic

```python
# core/config_schema.py
from pydantic import BaseModel, Field, field_validator

class AppConfig(BaseModel):
    output: OutputConfig
    connection: ConnectionConfig
    parser: ParserConfig
    netbox: NetBoxConfig
    mac: MACConfig
    filters: FiltersConfig
    logging: LoggingConfig
    debug: bool = False
    devices_file: str = "devices_ips.py"

def validate_config(config_dict: dict) -> AppConfig:
    """Валидирует словарь конфигурации."""

# Использование:
config.validate()  # raises ConfigError
config.get_validated()  # returns AppConfig
```

### Layer Boundaries — Аудит

Проверка показала:
- ✅ collectors НЕ импортируют netbox модули
- ✅ exporters НЕ импортируют connection модули
- ✅ Терминология (mode: access/tagged) — универсальная сетевая, не специфика NetBox

### Domain Layer (СДЕЛАНО)

Бизнес-логика вынесена из collectors в отдельный слой:

```
core/domain/
├── __init__.py
├── interface.py   # InterfaceNormalizer
├── mac.py         # MACNormalizer
├── lldp.py        # LLDPNormalizer
└── inventory.py   # InventoryNormalizer
```

**Использование:**
```python
from network_collector.core.domain import InterfaceNormalizer

normalizer = InterfaceNormalizer()
interfaces = normalizer.normalize(raw_data)  # List[Interface]
```

**Что делают Normalizers:**
- Нормализация статусов (connected → up)
- Унификация полей (mac_address → mac)
- Определение port_type (10g-sfp+, lag, virtual)
- Обогащение данных (LAG, switchport mode, media_type)
- Фильтрация и дедупликация

**Тесты:** 166 тестов в `tests/test_core/test_domain/`

---

## Будущие улучшения (опционально)

| Задача | Сложность | Описание |
|--------|-----------|----------|
| Pipeline | 🟢 Лёгкая | Явный SyncPipeline со steps |
| Async Backend | 🟡 Средняя | Параллельный сбор через asyncio |
| Web API | 🔴 Сложная | FastAPI поверх Application layer |
| Collectors Refactor | 🟡 Средняя | Использовать Domain Layer в collectors |

---

## Итого

- **Всего тестов:** 621
- **Все приоритеты:** P1, P2, P3, P4 — выполнены
- **Рефакторинг:** дублирование кода устранено
- **Domain Layer:** бизнес-логика отделена от сбора данных (4 normalizers)
