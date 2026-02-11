# 12. Внутренности проекта и тестирование

> Предыдущий документ: [09_MIXINS_PATTERNS.md](09_MIXINS_PATTERNS.md)

Этот документ раскрывает инфраструктурный слой проекта: как устроена конфигурация,
константы, обработка ошибок, контекст выполнения и тестирование. Мы рассмотрим
реальный код из репозитория и разберём каждый паттерн.

---

## Содержание

1. [Config система](#1-config-система)
2. [Constants пакет](#2-constants-пакет)
3. [Иерархия исключений](#3-иерархия-исключений)
4. [RunContext](#4-runcontext)
5. [Тестирование -- паттерны и практики](#5-тестирование----паттерны-и-практики)

---

## 1. Config система

Проект загружает настройки из двух YAML-файлов: `config.yaml` (общие настройки)
и `fields.yaml` (поля для экспорта и синхронизации). Рассмотрим каждый компонент.

### 1.1 Config и ConfigSection -- доступ через точку

```python
# Файл: config.py

class ConfigSection:
    """Секция конфигурации с доступом через точку."""

    def __init__(self, data: dict = None):
        self._data = data or {}

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            return super().__getattribute__(name)
        value = self._data.get(name)
        if isinstance(value, dict):
            return ConfigSection(value)
        return value

    def get(self, key: str, default: Any = None) -> Any:
        """Получить значение с дефолтом."""
        return self._data.get(key, default)
```

### Что здесь происходит

`ConfigSection` -- обёртка вокруг обычного словаря, позволяющая обращаться к ключам
как к атрибутам: `section.timeout` вместо `section["timeout"]`. Магический метод
`__getattr__` перехватывает обращение к несуществующим атрибутам. Если значение --
вложенный словарь, он оборачивается в новый `ConfigSection`, позволяя строить цепочки
вроде `config.netbox.url`.

Проверка `name.startswith("_")` защищает внутренние атрибуты (особенно `_data`) от
рекурсивного зацикливания.

> **Python-концепция: `__getattr__`**
> Вызывается Python только когда обычный поиск атрибута (`__dict__`, MRO) не нашёл
> результат. В отличие от `__getattribute__`, который перехватывает *все* обращения,
> `__getattr__` -- "последний шанс". Это безопасный способ добавить динамический
> доступ к атрибутам, не ломая стандартное поведение.

### 1.2 Класс Config -- загрузка и мерж

```python
# Файл: config.py

class Config:
    def __init__(self):
        self._data = self._get_defaults()
        self._load_yaml()
        self._load_env()

    def _load_yaml(self, config_file: Optional[str] = None) -> None:
        """Загружает настройки из YAML файла."""
        if not config_file:
            search_paths = [
                CONFIG_FILE,
                "config.yaml",
                "config.yml",
                ".network_collector.yaml",
            ]
            for path in search_paths:
                if os.path.exists(path):
                    config_file = path
                    break

        if not config_file or not os.path.exists(config_file):
            return

        import yaml
        with open(config_file, "r", encoding="utf-8") as f:
            yaml_data = yaml.safe_load(f) or {}

        # Мержим с дефолтами
        self._merge_dict(self._data, yaml_data)

    def _merge_dict(self, base: dict, override: dict) -> None:
        """Рекурсивно мержит словари."""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._merge_dict(base[key], value)
            else:
                base[key] = value

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            return super().__getattribute__(name)
        value = self._data.get(name)
        if isinstance(value, dict):
            return ConfigSection(value)
        return value
```

### Что здесь происходит

`Config.__init__` выполняет три шага: загружает дефолты (словарь с разумными
значениями), потом мержит YAML, потом мержит переменные окружения. Приоритет:
**env > YAML > defaults**. Это гарантирует что приложение всегда работает, даже
без `config.yaml`.

`_merge_dict` -- рекурсивный мерж: вложенные словари объединяются, а не
перезаписываются целиком. Если в YAML указать только `netbox.url`, остальные
ключи `netbox` (token, timeout и т.д.) останутся из дефолтов.

В конце файла создаётся глобальный синглтон:

```python
# Файл: config.py

# Глобальный экземпляр
config = Config()
```

Все модули проекта импортируют `from network_collector.config import config` и
работают с одним объектом.

### 1.3 fields.yaml -- конфигурация экспорта и синхронизации

```yaml
# Файл: fields.yaml

# Экспортные поля для MAC-адресов
mac:
  hostname:
    enabled: true
    name: "Device"
    order: 1
  interface:
    enabled: true
    name: "Port"
    order: 3
  mac:
    enabled: true
    name: "MAC Address"
    order: 4

# Настройки синхронизации с NetBox
sync:
  interfaces:
    fields:
      enabled:
        enabled: true
        source: status
      description:
        enabled: true
        source: description
      mac_address:
        enabled: true
        source: mac
    defaults:
      type: "1000base-t"
    options:
      sync_vlans: true
      enabled_mode: "link"
      sync_mac_only_with_ip: true
```

### Что здесь происходит

Файл разделён на две логические части:

**Экспортные секции** (`lldp`, `mac`, `devices`, `interfaces`, `inventory`) --
определяют какие поля попадут в Excel/CSV. Каждое поле имеет `enabled` (включено),
`name` (отображаемое имя в колонке), `order` (порядок слева направо).

**Секция `sync`** -- настройки синхронизации с NetBox. Для каждого типа сущности
(devices, interfaces, ip_addresses, vlans, cables, inventory) указаны:
- `fields` -- какие поля синхронизировать и откуда брать данные (`source`)
- `defaults` -- значения по умолчанию (site, role, status)
- `options` -- управляющие флаги (sync_vlans, enabled_mode)

### 1.4 fields_config.py -- dataclass-обёртки для YAML

```python
# Файл: fields_config.py

# Глобальный кэш конфигурации
_config_cache: Optional[Dict[str, Any]] = None


def _load_yaml() -> Dict[str, Any]:
    """Загружает YAML файл (с кэшированием)."""
    global _config_cache

    if _config_cache is not None:
        return _config_cache

    import yaml
    with open(FIELDS_CONFIG_FILE, "r", encoding="utf-8") as f:
        _config_cache = yaml.safe_load(f) or {}

    return _config_cache


@dataclass
class SyncFieldConfig:
    """Конфигурация одного поля для синхронизации."""
    enabled: bool = True
    source: str = ""


@dataclass
class SyncEntityConfig:
    """Конфигурация синхронизации для типа данных."""
    fields: Dict[str, SyncFieldConfig] = field(default_factory=dict)
    defaults: Dict[str, Any] = field(default_factory=dict)
    options: Dict[str, Any] = field(default_factory=dict)

    def is_field_enabled(self, field_name: str) -> bool:
        """Проверяет, включено ли поле для синхронизации."""
        if field_name in self.fields:
            return self.fields[field_name].enabled
        return False

    def get_option(self, key: str, default: Any = None) -> Any:
        """Возвращает опцию."""
        return self.options.get(key, default)


def get_sync_config(entity_type: str) -> SyncEntityConfig:
    """Возвращает конфигурацию синхронизации для типа сущности."""
    config = _load_yaml()
    sync_data = config.get("sync", {}).get(entity_type, {})

    result = SyncEntityConfig()

    if "fields" in sync_data:
        for field_name, field_data in sync_data["fields"].items():
            if isinstance(field_data, dict):
                result.fields[field_name] = SyncFieldConfig(
                    enabled=field_data.get("enabled", True),
                    source=field_data.get("source", field_name),
                )

    if "defaults" in sync_data:
        result.defaults = sync_data["defaults"]
    if "options" in sync_data:
        result.options = sync_data["options"]

    return result
```

### Что здесь происходит

`_config_cache` -- глобальная переменная уровня модуля. YAML-файл загружается один раз
при первом вызове `_load_yaml()`, после чего все последующие вызовы возвращают
кэшированный результат. Это важно, потому что `get_sync_config()` вызывается
десятки раз при синхронизации.

`SyncEntityConfig` -- dataclass, который структурирует плоский YAML в типизированный
объект. Вместо `config["sync"]["interfaces"]["options"]["sync_vlans"]` пишем:

```python
cfg = get_sync_config("interfaces")
cfg.get_option("sync_vlans")       # True
cfg.is_field_enabled("description") # True
cfg.get_source("mac_address")       # "mac"
```

> **Python-концепция: `@dataclass`**
> Декоратор `@dataclass` автоматически генерирует `__init__`, `__repr__`, `__eq__`
> на основе аннотаций типов. `field(default_factory=dict)` нужен для мутабельных
> значений по умолчанию -- Python не разрешает `fields: Dict = {}` напрямую,
> потому что один словарь был бы общим для всех экземпляров.

> **Python-концепция: Глобальный кэш модуля**
> Переменная `_config_cache` с `global` -- простейший паттерн кэширования.
> Подчёркивание в начале (`_`) говорит "это приватная деталь реализации".
> Функция `reload_config()` сбрасывает кэш, устанавливая `_config_cache = None`.

Функция `apply_fields_config()` применяет конфигурацию полей к данным перед
экспортом -- оставляет только включённые поля, переименовывает и сортирует:

```python
# Файл: fields_config.py

def apply_fields_config(data: List[Dict], data_type: str) -> List[Dict]:
    """Применяет конфигурацию полей к данным."""
    enabled_fields = get_enabled_fields(data_type)
    if not enabled_fields:
        return data

    result = []
    for row in data:
        new_row = {}
        for field_name, display_name, _, default_value in enabled_fields:
            value = None
            for key in row.keys():
                if key.lower() == field_name.lower():
                    value = row[key]
                    break

            if value is None or value == "":
                if default_value is not None:
                    value = default_value

            if value is not None:
                new_row[display_name] = value

        if new_row:
            result.append(new_row)

    return result
```

### Что здесь происходит

Для каждой строки данных функция проходит по включённым полям, находит значение
(case-insensitive поиск), применяет дефолт если значение пустое, и записывает
под отображаемым именем. Результат -- данные готовые для Excel/CSV.

---

## 2. Constants пакет

Все константы проекта собраны в пакете `core/constants/`, разбитом на модули
по назначению.

### 2.1 Реэкспорт через `__init__.py`

```python
# Файл: core/constants/__init__.py

# Интерфейсы
from .interfaces import (
    INTERFACE_SHORT_MAP,
    normalize_interface_short,
    normalize_interface_full,
)

# MAC
from .mac import (
    normalize_mac_raw,
    normalize_mac_ieee,
    normalize_mac_netbox,
)

# NetBox
from .netbox import (
    NETBOX_INTERFACE_TYPE_MAP,
    get_netbox_interface_type,
)

# ... и другие модули

__all__ = [
    "INTERFACE_SHORT_MAP",
    "normalize_interface_short",
    "normalize_mac_ieee",
    "get_netbox_interface_type",
    # ... полный список
]
```

### Что здесь происходит

`__init__.py` реэкспортирует символы из подмодулей, создавая "плоский" интерфейс.
Это обеспечивает обратную совместимость: старый код с
`from core.constants import normalize_mac_ieee` продолжает работать, хотя
функция переехала в `core.constants.mac`. Новый код может импортировать
напрямую: `from core.constants.mac import normalize_mac_ieee`.

`__all__` определяет что экспортируется при `from core.constants import *`,
но в проекте используется для документации -- явный список публичного API.

> **Python-концепция: Package `__init__.py` и реэкспорт**
> Когда вы пишете `from package import symbol`, Python выполняет `__init__.py`
> этого пакета. Импортируя символы из подмодулей в `__init__.py`, вы делаете их
> доступными на уровне пакета. Это позволяет рефакторить внутреннюю структуру,
> не ломая внешний API.

### 2.2 commands.py -- команды коллекторов

```python
# Файл: core/constants/commands.py

COLLECTOR_COMMANDS: Dict[str, Dict[str, str]] = {
    "mac": {
        "cisco_ios": "show mac address-table",
        "cisco_nxos": "show mac address-table",
        "arista_eos": "show mac address-table",
        "qtech": "show mac address-table",
    },
    "interfaces": {
        "cisco_ios": "show interfaces",
        "cisco_nxos": "show interface",   # Без s!
        "qtech": "show interface",
    },
    "lldp": {
        "cisco_ios": "show lldp neighbors detail",
        "arista_eos": "show lldp neighbors detail",
        "qtech": "show lldp neighbors detail",
    },
    # ...
}

SECONDARY_COMMANDS: Dict[str, Dict[str, str]] = {
    "lag": {
        "cisco_ios": "show etherchannel summary",
        "cisco_nxos": "show port-channel summary",
        "qtech": "show aggregatePort summary",
    },
    "switchport": {
        "cisco_ios": "show interfaces switchport",
        "qtech": "show interface switchport",
    },
    "transceiver": {
        "cisco_nxos": "show interface transceiver",
        "qtech": "show interface transceiver",
    },
}

CUSTOM_TEXTFSM_TEMPLATES: Dict[tuple, str] = {
    ("qtech", "show mac address-table"): "qtech_show_mac_address_table.textfsm",
    ("qtech", "show version"): "qtech_show_version.textfsm",
    ("qtech", "show interface"): "qtech_show_interface.textfsm",
    # ...
}
```

### Что здесь происходит

`COLLECTOR_COMMANDS` -- двухуровневый словарь: `коллектор -> платформа -> CLI-команда`.
Каждый коллектор заглядывает сюда, чтобы узнать какую команду выполнить на
конкретной платформе.

`SECONDARY_COMMANDS` -- дополнительные команды, вызываемые помимо основной:
LAG membership, switchport mode, трансиверы.

`CUSTOM_TEXTFSM_TEMPLATES` -- маппинг `(платформа, команда) -> файл шаблона`.
Для платформ вроде QTech, где NTC Templates не имеет готовых шаблонов, проект
использует свои, хранящиеся в папке `templates/`.

### 2.3 interfaces.py -- нормализация имён интерфейсов

```python
# Файл: core/constants/interfaces.py

INTERFACE_SHORT_MAP: List[tuple] = [
    ("twentyfivegigabitethernet", "Twe"),
    ("hundredgigabitethernet", "Hu"),
    ("tengigabitethernet", "Te"),
    ("gigabitethernet", "Gi"),
    ("fastethernet", "Fa"),
    ("aggregateport", "Ag"),    # QTech LAG
    ("ethernet", "Eth"),        # NX-OS
    ("port-channel", "Po"),
    ("vlan", "Vl"),
]

INTERFACE_FULL_MAP: Dict[str, str] = {
    "Gi": "GigabitEthernet",
    "Te": "TenGigabitEthernet",
    "TF": "TFGigabitEthernet",  # QTech 10G
    "Ag": "AggregatePort",      # QTech LAG
    "Po": "Port-channel",
}


def normalize_interface_short(interface: str, lowercase: bool = False) -> str:
    """GigabitEthernet0/1 -> Gi0/1"""
    if not interface:
        return ""

    result = interface.replace(" ", "").strip()
    result_lower = result.lower()

    for full_lower, short in INTERFACE_SHORT_MAP:
        if result_lower.startswith(full_lower):
            result = short + result[len(full_lower):]
            break

    return result.lower() if lowercase else result
```

### Что здесь происходит

Сетевое оборудование возвращает имена интерфейсов в разных форматах:
`GigabitEthernet0/1`, `Gi0/1`, `gigabitethernet0/1`. Функции нормализации
приводят их к единому виду.

`INTERFACE_SHORT_MAP` -- список кортежей `(полное_имя_lowercase, сокращение)`.
Порядок важен: длинные паттерны идут первыми, чтобы `twentyfivegigabitethernet`
не матчился как `ethernet`. Функция проходит список и заменяет первое совпадение.

`normalize_interface_full` делает обратное: `Gi0/1` -> `GigabitEthernet0/1`.
Обе функции нужны, потому что разные API и команды ожидают разные форматы.

### 2.4 netbox.py -- определение типа интерфейса

```python
# Файл: core/constants/netbox.py

def get_netbox_interface_type(
    interface_name: str = "",
    media_type: str = "",
    hardware_type: str = "",
    port_type: str = "",
    speed_mbps: int = 0,
    *,
    interface: Any = None,
) -> str:
    """
    Определяет тип интерфейса для NetBox.

    Приоритет определения:
    1. LAG/Virtual по имени или port_type
    2. Management интерфейсы -> медь
    3. media_type (наиболее точный)
    4. port_type (нормализованный)
    5. hardware_type
    6. interface_name
    7. speed (fallback)
    """
    name_lower = interface_name.lower()

    # 1. LAG
    if name_lower.startswith(("port-channel", "po", "aggregateport")):
        return "lag"

    # 2. Виртуальные
    if name_lower.startswith(VIRTUAL_INTERFACE_PREFIXES):
        return "virtual"

    # 3. Management
    if any(x in name_lower for x in MGMT_INTERFACE_PATTERNS):
        return "1000base-t"

    # 4. media_type -- ВЫСШИЙ ПРИОРИТЕТ
    if media_lower and media_lower not in ("unknown", "not present", ""):
        for pattern, netbox_type in NETBOX_INTERFACE_TYPE_MAP.items():
            if pattern in media_lower:
                return netbox_type

    # 5. port_type
    if port_type and port_type in PORT_TYPE_MAP:
        return PORT_TYPE_MAP[port_type]

    # 6. hardware_type
    # 7. По имени (через INTERFACE_NAME_PREFIX_MAP)
    # 8. Fallback по скорости

    return "1000base-t"  # Default
```

### Что здесь происходит

Это одна из самых сложных функций в проекте. Она принимает все известные данные
об интерфейсе и определяет его тип для NetBox API. Приоритет тщательно выбран
по практическому опыту: например, 25G порт с вставленным 10G трансивером должен
определяться как `10gbase-lr` (по трансиверу), а не как `25gbase-x-sfp28` (по порту).

Функция использует три словаря-маппинга:
- `NETBOX_INTERFACE_TYPE_MAP` -- media_type -> тип NetBox (120+ записей)
- `NETBOX_HARDWARE_TYPE_MAP` -- hardware_type -> тип NetBox
- `INTERFACE_NAME_PREFIX_MAP` -- префикс имени -> тип NetBox

### 2.5 mac.py -- нормализация MAC-адресов

```python
# Файл: core/constants/mac.py

def normalize_mac_raw(mac: str) -> str:
    """aabbccddeeff -- 12 символов, нижний регистр."""
    if not mac:
        return ""
    mac_clean = mac.strip().lower()
    for char in [":", "-", ".", " "]:
        mac_clean = mac_clean.replace(char, "")
    if len(mac_clean) != 12:
        return ""
    return mac_clean


def normalize_mac_ieee(mac: str) -> str:
    """aa:bb:cc:dd:ee:ff"""
    clean = normalize_mac_raw(mac)
    if not clean:
        return ""
    return ":".join(clean[i : i + 2] for i in range(0, 12, 2))


def normalize_mac_cisco(mac: str) -> str:
    """aabb.ccdd.eeff"""
    clean = normalize_mac_raw(mac)
    if not clean:
        return ""
    return f"{clean[0:4]}.{clean[4:8]}.{clean[8:12]}"


def normalize_mac_netbox(mac: str) -> str:
    """AA:BB:CC:DD:EE:FF"""
    clean = normalize_mac_raw(mac)
    if not clean:
        return ""
    return ":".join(clean[i : i + 2].upper() for i in range(0, 12, 2))
```

### Что здесь происходит

MAC-адреса приходят в разных форматах: Cisco `aabb.ccdd.eeff`, IEEE `aa:bb:cc:dd:ee:ff`,
NetBox `AA:BB:CC:DD:EE:FF`. Все функции строятся поверх `normalize_mac_raw`,
которая убирает разделители и приводит к 12-символьной строке. Это "каноническая"
форма для сравнения.

### 2.6 Другие модули пакета constants

**platforms.py** -- маппинг платформ между библиотеками:

```python
# Файл: core/constants/platforms.py

SCRAPLI_PLATFORM_MAP = {"cisco_ios": "cisco_iosxe", "qtech": "cisco_iosxe", ...}
NTC_PLATFORM_MAP = {"cisco_iosxe": "cisco_ios", "qtech": "cisco_ios", ...}
VENDOR_MAP = {"cisco": ["cisco_ios", "cisco_iosxe", ...], "qtech": ["qtech", "qtech_qsw"], ...}
```

QTech использует Cisco-совместимый CLI, поэтому маппится на `cisco_iosxe` для
Scrapli и `cisco_ios` для NTC Templates.

**devices.py** -- нормализация моделей устройств:

```python
# Файл: core/constants/devices.py

def normalize_device_model(model: str) -> str:
    """WS-C2960C-8TC-L -> C2960C-8TC"""
    result = model.strip().upper()
    for prefix in MODEL_PREFIXES_TO_REMOVE:  # ("WS-",)
        if result.startswith(prefix):
            result = result[len(prefix):]
            break
    for suffix in CISCO_LICENSE_SUFFIXES:     # ("-L", "-S", "-E", "-A", "-K9")
        if result.endswith(suffix):
            result = result[:-len(suffix)]
            break
    return result
```

**utils.py** -- утилиты: slugify (для NetBox), транслитерация, конвертация маски:

```python
# Файл: core/constants/utils.py

def mask_to_prefix(mask: str) -> int:
    """255.255.255.0 -> 24"""
    if str(mask).isdigit():
        return int(mask)
    octets = [int(x) for x in mask.split(".")]
    binary = "".join(format(x, "08b") for x in octets)
    return binary.count("1")
```

> **Python-концепция: `format(x, "08b")`**
> Форматирование числа как двоичной строки с ведущими нулями до 8 символов.
> `format(255, "08b")` -> `"11111111"`, `format(128, "08b")` -> `"10000000"`.
> Подсчёт единиц (`"1"`) даёт длину префикса.

---

## 3. Иерархия исключений

Проект определяет типизированные исключения для разных слоёв: сбор данных, NetBox API,
конфигурация. Это позволяет обработчикам ловить ошибки нужного уровня.

### 3.1 Дерево исключений

```
NetworkCollectorError (базовый)
├── CollectorError (сбор данных с устройств)
│   ├── ConnectionError (SSH подключение)
│   ├── AuthenticationError (авторизация)
│   ├── CommandError (выполнение команды)
│   ├── ParseError (парсинг вывода)
│   └── TimeoutError (таймаут)
├── NetBoxError (NetBox API)
│   ├── NetBoxConnectionError (подключение к API)
│   ├── NetBoxAPIError (ошибка API, status_code)
│   └── NetBoxValidationError (валидация данных)
└── ConfigError (конфигурация)
```

### 3.2 Базовый класс с сериализацией

```python
# Файл: core/exceptions.py

class NetworkCollectorError(Exception):
    """Базовое исключение для всех ошибок Network Collector."""

    def __init__(self, message: str, details: Optional[dict] = None):
        self.message = message
        self.details = details or {}
        super().__init__(message)

    def __str__(self) -> str:
        if self.details:
            details_str = ", ".join(f"{k}={v!r}" for k, v in self.details.items())
            return f"{self.message} ({details_str})"
        return self.message

    def to_dict(self) -> dict:
        """Сериализация для логов/отчётов."""
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "details": self.details,
        }
```

### Что здесь происходит

Каждое исключение несёт структурированные данные в `details`. Метод `to_dict()`
превращает исключение в словарь для JSON-логирования. `__str__` формирует
человекочитаемое сообщение. `self.__class__.__name__` автоматически подставляет
имя конкретного класса (`ConnectionError`, `ParseError`).

### 3.3 Доменные исключения с дополнительными полями

```python
# Файл: core/exceptions.py

class CommandError(CollectorError):
    """Ошибка выполнения команды на устройстве."""

    def __init__(
        self,
        message: str,
        device: Optional[str] = None,
        command: Optional[str] = None,
        output: Optional[str] = None,
        details: Optional[dict] = None,
    ):
        self.command = command
        self.output = output
        details = details or {}
        if command:
            details["command"] = command
        if output:
            details["output"] = output[:200]  # Ограничиваем размер
        super().__init__(message, device, details)


class NetBoxAPIError(NetBoxError):
    """Ошибка при вызове NetBox API."""

    def __init__(
        self,
        message: str,
        url: Optional[str] = None,
        status_code: Optional[int] = None,
        endpoint: Optional[str] = None,
        details: Optional[dict] = None,
    ):
        self.status_code = status_code
        self.endpoint = endpoint
        details = details or {}
        if status_code:
            details["status_code"] = status_code
        if endpoint:
            details["endpoint"] = endpoint
        super().__init__(message, url, details)
```

### Что здесь происходит

Каждый подкласс добавляет свои специфичные поля: `CommandError` хранит `command`
и `output` (обрезанный до 200 символов), `NetBoxAPIError` хранит `status_code`
и `endpoint`. Все они автоматически попадают в `details` для сериализации.

### 3.4 Утилиты для работы с ошибками

```python
# Файл: core/exceptions.py

def format_error_for_log(error: Exception) -> str:
    """Форматирует ошибку для вывода в лог."""
    if isinstance(error, NetworkCollectorError):
        return str(error)
    return f"{error.__class__.__name__}: {error}"


def is_retryable(error: Exception) -> bool:
    """Проверяет, можно ли повторить операцию после ошибки."""
    retryable_types = (
        ConnectionError,
        TimeoutError,
        NetBoxConnectionError,
    )
    return isinstance(error, retryable_types)
```

### Что здесь происходит

`format_error_for_log` -- единый формат для логов. Наши исключения форматируются
через `__str__` (с details), чужие -- через стандартный формат.

`is_retryable` классифицирует ошибки: проблемы с сетью (connection, timeout) можно
повторить, а ошибки авторизации или парсинга -- бессмысленно.

> **Python-концепция: `isinstance()` с кортежем**
> `isinstance(error, (ConnectionError, TimeoutError))` проверяет принадлежность
> к любому из перечисленных классов. Это удобнее чем цепочка `or`.

> **Python-концепция: Иерархия исключений**
> Если вы ловите `CollectorError`, то поймаете и `ConnectionError`,
> и `TimeoutError`, и `ParseError` -- все подклассы. Это позволяет
> обработчику ошибок выбирать уровень гранулярности:
> `except CollectorError` для общей обработки, `except ParseError`
> для специфичной.

---

## 4. RunContext

`RunContext` -- dataclass, который отслеживает запуск операции: когда началась,
каким CLI-командой вызвана, куда сохранять отчёты.

### 4.1 Создание через classmethod factory

```python
# Файл: core/context.py

@dataclass
class RunContext:
    """Контекст выполнения операции."""

    run_id: str
    started_at: datetime
    dry_run: bool = False
    triggered_by: TriggerSource = "cli"   # Literal["cli", "cron", "api", "test"]
    command: str = ""
    output_dir: Optional[Path] = None
    extra: dict = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        dry_run: bool = False,
        triggered_by: TriggerSource = "cli",
        command: str = "",
        base_output_dir: Optional[Path] = None,
        use_timestamp_id: bool = True,
    ) -> "RunContext":
        """Создаёт новый контекст выполнения."""
        started_at = datetime.now()

        if use_timestamp_id:
            run_id = started_at.strftime("%Y-%m-%dT%H-%M-%S")
        else:
            run_id = str(uuid.uuid4())[:8]

        if base_output_dir is None:
            base_output_dir = Path("reports")

        output_dir = base_output_dir / f"run_{run_id}"

        return cls(
            run_id=run_id,
            started_at=started_at,
            dry_run=dry_run,
            triggered_by=triggered_by,
            command=command,
            output_dir=output_dir,
        )
```

### Что здесь происходит

`RunContext.create()` -- фабричный метод, который инкапсулирует логику создания:
генерацию ID, определение папки для отчётов, установку времени старта. Вместо
конструктора с кучей параметров, вызывающий код пишет:

```python
ctx = RunContext.create(dry_run=True, command="sync-netbox")
```

> **Python-концепция: `@classmethod` как фабрика**
> `@classmethod` получает класс как первый аргумент (`cls`), а не экземпляр
> (`self`). Это позволяет создать "альтернативный конструктор" с собственной
> логикой. В отличие от `__init__`, фабричных методов может быть несколько,
> каждый со своими параметрами.

### 4.2 Работа с файлами отчётов

```python
# Файл: core/context.py

    def ensure_output_dir(self) -> Path:
        """Создаёт папку для отчётов если её нет."""
        if self.output_dir:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            return self.output_dir
        raise ValueError("output_dir not set")

    def get_output_path(self, filename: str) -> Path:
        """Возвращает полный путь для файла отчёта."""
        self.ensure_output_dir()
        return self.output_dir / filename

    def save_summary(self, stats: Optional[dict] = None) -> Path:
        """Сохраняет summary.json в папку отчётов."""
        import json
        summary = self.to_dict()
        summary["completed_at"] = datetime.now().isoformat()
        if stats:
            summary["stats"] = stats
        summary_path = self.get_output_path("summary.json")
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        return summary_path
```

### Что здесь происходит

Каждый запуск получает свою папку `reports/run_2025-03-14T12-30-22/`. Метод
`ensure_output_dir` создаёт её лениво (при первом обращении). `save_summary`
записывает метаданные запуска (время, dry_run, статистика) в JSON.

### 4.3 Глобальный контекст и логирование

```python
# Файл: core/context.py

_current_context: Optional[RunContext] = None


def get_current_context() -> Optional[RunContext]:
    """Возвращает текущий глобальный контекст."""
    return _current_context


def set_current_context(ctx: Optional[RunContext]) -> None:
    """Устанавливает текущий глобальный контекст."""
    global _current_context
    _current_context = ctx


class RunContextFilter(logging.Filter):
    """Logging filter для добавления run_id в каждое сообщение."""

    def filter(self, record: logging.LogRecord) -> bool:
        ctx = get_current_context()
        if ctx:
            record.run_id = ctx.run_id
            if not record.msg.startswith(f"[{ctx.run_id}]"):
                record.msg = f"[{ctx.run_id}] {record.msg}"
        else:
            record.run_id = "-"
        return True  # Всегда пропускаем запись
```

### Что здесь происходит

`_current_context` -- глобальная переменная модуля, хранящая текущий контекст.
Это нужно для мест, где контекст невозможно передать явно (например, глубоко
вложенные функции).

`RunContextFilter` -- стандартный `logging.Filter`, который модифицирует каждую
лог-запись, добавляя `[run_id]` в начало сообщения. Это позволяет в логах
отличать записи разных запусков:

```
2025-03-14 12:30:22 - INFO - [2025-03-14T12-30-22] Собрано 48 интерфейсов
2025-03-14 12:30:23 - INFO - [2025-03-14T12-30-22] Синхронизировано 12 из 48
```

> **Python-концепция: `logging.Filter`**
> Фильтры в модуле `logging` могут модифицировать записи (`LogRecord`), не
> только фильтровать их. Метод `filter()` возвращает `True` (пропустить) или
> `False` (отбросить). Здесь мы всегда пропускаем, но добавляем `run_id`.

> **Python-концепция: Глобальное состояние vs dependency injection**
> `_current_context` -- компромисс. Идеально передавать контекст через параметры
> (`def collect(devices, ctx: RunContext)`), но не все функции имеют доступ к
> контексту. Глобальная переменная -- fallback для таких случаев.

---

## 5. Тестирование -- паттерны и практики

В проекте 1500+ тестов. Рассмотрим ключевые паттерны.

### 5.1 conftest.py -- общие fixtures

```python
# Файл: tests/conftest.py

@pytest.fixture
def fixtures_dir() -> Path:
    """Возвращает путь к директории fixtures."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def load_fixture(fixtures_dir):
    """
    Fixture для загрузки тестовых данных из файлов.

    Usage:
        output = load_fixture("cisco_ios", "show_etherchannel_summary.txt")
    """
    def _load(platform: str, filename: str) -> str:
        fixture_path = fixtures_dir / platform / filename
        if not fixture_path.exists():
            pytest.skip(f"Fixture не найден: {fixture_path}")
        return fixture_path.read_text(encoding="utf-8")
    return _load
```

### Что здесь происходит

`load_fixture` -- фабричная fixture (fixture, возвращающая функцию). Тест вызывает
её с параметрами: `load_fixture("cisco_ios", "show_interfaces.txt")`. Если файл
не найден, тест пропускается (`pytest.skip`), а не падает.

В папке `tests/fixtures/` лежат реальные выводы команд с оборудования, организованные
по платформам:

```
tests/fixtures/
├── cisco_ios/
│   ├── show_interfaces.txt
│   ├── show_mac_address_table.txt
│   └── show_inventory.txt
├── cisco_nxos/
│   └── show_interface.txt
└── qtech/
    └── show_interface.txt
```

> **Python-концепция: Фабричная fixture**
> Fixture может возвращать функцию (фабрику), а не готовый объект. Это
> позволяет тесту вызывать фабрику с разными параметрами. Паттерн
> "fixture of fixtures" -- стандартный приём в pytest.

```python
# Файл: tests/conftest.py

@pytest.fixture
def mock_netbox_client():
    """Mock NetBox клиента для тестирования синхронизации."""
    client = MagicMock()
    client.get_device_by_name.return_value = None
    client.get_device_type_by_model.return_value = None
    client.create_device.return_value = MagicMock(id=1, name="test-device")
    client.get_interfaces.return_value = []
    return client


@pytest.fixture
def sample_interface_data() -> Dict[str, Any]:
    """Примеры данных интерфейсов для тестирования."""
    return {
        "c9500_25g_with_10g_sfp": {
            "interface": "TwentyFiveGigE1/0/1",
            "status": "up",
            "hardware_type": "Twenty Five Gigabit Ethernet",
            "media_type": "SFP-10GBase-LR",
            "speed": "10000000 Kbit",
        },
        "gigabit_copper": {
            "interface": "GigabitEthernet1/0/1",
            "status": "up",
            "hardware_type": "Gigabit Ethernet",
            "media_type": "RJ45",
        },
        # ...
    }
```

### Что здесь происходит

`mock_netbox_client` -- заранее настроенный mock NetBox клиента. Методы по
умолчанию возвращают "пустые" значения (`None`, `[]`), которые тесты могут
переопределить. `sample_interface_data` -- словарь с реалистичными данными
интерфейсов для тестирования нормализации и определения типов.

### 5.2 Маркеры для группировки тестов

```python
# Файл: tests/conftest.py

def pytest_configure(config):
    """Регистрация custom markers для pytest."""
    config.addinivalue_line(
        "markers", "unit: Unit tests (быстрые, без внешних зависимостей)"
    )
    config.addinivalue_line(
        "markers", "integration: Integration tests (требуют fixtures)"
    )
    config.addinivalue_line(
        "markers", "netbox: NetBox sync tests (требуют mock NetBox API)"
    )
    config.addinivalue_line(
        "markers", "slow: Медленные тесты"
    )
```

### Что здесь происходит

`pytest_configure` -- хук pytest, вызываемый при инициализации. Здесь
регистрируются пользовательские маркеры, чтобы `pytest --strict-markers`
не ругался на неизвестные маркеры.

Маркеры позволяют запускать подмножества тестов:

```bash
pytest -m unit          # Только быстрые unit-тесты
pytest -m "not slow"    # Всё кроме медленных
pytest -m netbox        # Только тесты NetBox синхронизации
```

### 5.3 Parametrize -- data-driven тесты

```python
# Файл: tests/test_collectors/test_port_type_detection.py

@pytest.mark.unit
class TestPortTypeDetection:
    """Тесты определения port_type в коллекторе."""

    @pytest.mark.parametrize("interface_data,expected_port_type", [
        # 25G порт с 10G трансивером - media_type важнее hardware_type
        (
            {
                "interface": "TwentyFiveGigE1/0/1",
                "hardware_type": "Twenty Five Gigabit Ethernet",
                "media_type": "SFP-10GBase-LR",
            },
            "10g-sfp+",
        ),
        # media_type = "unknown" - игнорируется
        (
            {
                "interface": "TenGigabitEthernet1/1/1",
                "hardware_type": "Ten Gigabit Ethernet",
                "media_type": "unknown",
            },
            "10g-sfp+",
        ),
        # LAG
        (
            {
                "interface": "Port-channel1",
                "hardware_type": "EtherChannel",
                "media_type": "",
            },
            "lag",
        ),
        # Виртуальный
        (
            {
                "interface": "Vlan100",
                "hardware_type": "Ethernet SVI",
                "media_type": "",
            },
            "virtual",
        ),
    ])
    def test_detect_port_type(self, normalizer, interface_data, expected_port_type):
        iface_lower = interface_data["interface"].lower()
        result = normalizer.detect_port_type(interface_data, iface_lower)

        assert result == expected_port_type, (
            f"Interface: {interface_data['interface']}\n"
            f"Hardware: {interface_data.get('hardware_type', '')}\n"
            f"Media: {interface_data.get('media_type', '')}\n"
            f"Expected: {expected_port_type}, Got: {result}"
        )
```

### Что здесь происходит

`@pytest.mark.parametrize` превращает один тест в 30+ параметризованных случаев.
Каждый кортеж в списке -- набор входных данных и ожидаемый результат. Pytest
создаёт отдельный тест-кейс для каждого набора и показывает в отчёте какой именно
провалился.

Сообщение в `assert` -- многострочное, с контекстом. Когда тест падает, видно
не просто "expected X, got Y", а все входные параметры.

> **Python-концепция: `@pytest.mark.parametrize`**
> Декоратор принимает строку с именами параметров и список значений.
> Параметры разделяются запятой. Каждый элемент списка -- кортеж значений
> (или одно значение если параметр один). Тест вызывается для каждого
> набора параметров.

### 5.4 Mocking Mixin-классов -- ключевой паттерн

Это самый нетривиальный паттерн тестирования в проекте.

**Проблема:** Mixin-класс (например, `InterfacesSyncMixin`) использует `self.client`,
`self.dry_run` и собственные методы. `MagicMock(spec=InterfacesSyncMixin)` создаёт
mock с правильной сигнатурой, но *не вызывает реальные методы*.

**Решение:** Привязка реальных методов через lambda:

```python
# Файл: tests/test_netbox/test_sync_interfaces_vlan.py

def bind_mixin_methods(mock_obj, mixin_class, method_names):
    """Привязывает реальные методы mixin к mock объекту."""
    for name in method_names:
        method = getattr(mixin_class, name)
        setattr(mock_obj, name, lambda *args, _m=method, **kw: _m(mock_obj, *args, **kw))

INTERFACE_SYNC_METHODS = [
    '_build_update_data', '_build_create_data',
    '_check_type', '_check_description', '_check_enabled', '_check_mac',
    '_check_mtu', '_check_speed', '_check_duplex', '_check_mode',
    '_check_untagged_vlan', '_check_tagged_vlans', '_check_lag',
]


class TestInterfaceVlanSync:
    def test_access_port_syncs_untagged_vlan(self, mock_sync_cfg_vlans_enabled):
        from network_collector.netbox.sync.interfaces import InterfacesSyncMixin

        # Создаём mock sync object
        sync = MagicMock(spec=InterfacesSyncMixin)
        sync.dry_run = False
        sync.client = MagicMock()

        # Привязываем РЕАЛЬНЫЕ методы к mock
        bind_mixin_methods(sync, InterfacesSyncMixin, INTERFACE_SYNC_METHODS)

        # Настраиваем зависимости
        mock_vlan = MockVLAN(id=100, vid=10, name="Users")
        sync._get_vlan_by_vid = MagicMock(return_value=mock_vlan)

        intf = MockInterface(name="Gi0/1", mode="access", access_vlan="10")

        with patch("network_collector.netbox.sync.interfaces.get_sync_config",
                    return_value=mock_sync_cfg_vlans_enabled):
            result = InterfacesSyncMixin._update_interface(sync, nb_interface, intf)

        # Проверяем что API вызван с untagged_vlan=100
        sync.client.update_interface.assert_called_once()
        call_kwargs = sync.client.update_interface.call_args[1]
        assert call_kwargs["untagged_vlan"] == 100
```

### Что здесь происходит

1. `MagicMock(spec=InterfacesSyncMixin)` создаёт mock, который *знает* про все
   методы mixin, но все они -- mock-заглушки.

2. `bind_mixin_methods` берёт реальные методы из класса и привязывает их к mock-объекту,
   подставляя mock как `self`. Lambda `lambda *args, _m=method, **kw: _m(mock_obj, *args, **kw)`
   захватывает ссылку на метод через default argument (`_m=method`).

3. `sync.client` остаётся mock -- мы не хотим реальных API-вызовов. Но бизнес-логика
   (`_build_update_data`, `_check_untagged_vlan`) выполняется по-настоящему.

4. `patch(...)` подменяет `get_sync_config` на mock, чтобы контролировать опции
   (sync_vlans=True).

> **Python-концепция: Default argument capture в lambda**
> `lambda *args, _m=method: _m(obj, *args)` -- приём для "заморозки" переменной
> цикла. Без `_m=method` все lambda ссылались бы на последнее значение `method`
> из цикла. Default argument вычисляется в момент создания lambda, а не вызова.

> **Python-концепция: `MagicMock(spec=...)`**
> `spec=SomeClass` ограничивает mock: обращение к несуществующему атрибуту
> класса вызовет `AttributeError`. Это ловит опечатки (вызвал `sync.clent`
> вместо `sync.client`) на этапе тестирования.

### 5.5 E2E тесты -- полный цикл без SSH

```python
# Файл: tests/test_e2e/conftest.py

def create_mock_device(
    platform: str = "cisco_ios",
    hostname: str = "test-switch",
    host: str = "10.0.0.1",
) -> Device:
    """Создаёт mock Device для тестирования."""
    device = MagicMock(spec=Device)
    device.platform = platform
    device.hostname = hostname
    device.host = host
    device.device_type = platform
    device.name = hostname
    return device


PLATFORM_FIXTURES = {
    "cisco_ios": {
        "interfaces": "show_interfaces.txt",
        "mac": "show_mac_address_table.txt",
        "lldp": "show_lldp_neighbors_detail.txt",
    },
    "cisco_nxos": {
        "interfaces": "show_interface.txt",
        "mac": "show_mac_address_table.txt",
    },
    "qtech": {
        "interfaces": "show_interface.txt",
        "lldp": "show_lldp_neighbors_detail.txt",
    },
}
```

```python
# Файл: tests/test_e2e/test_interface_collector_e2e.py

class TestInterfaceCollectorE2E:
    """E2E тесты InterfaceCollector -- полный цикл без SSH."""

    def test_cisco_ios_full_pipeline(self, collector, load_fixture):
        """Cisco IOS: полный цикл обработки интерфейсов."""
        output = load_fixture("cisco_ios", "show_interfaces.txt")
        device = create_mock_device("cisco_ios", "ios-switch")

        # _parse_output возвращает List[Dict]
        result = collector._parse_output(output, device)

        assert len(result) > 0, "Должны быть распознаны интерфейсы"
        assert isinstance(result[0], dict), "Результат должен быть словарём"

    @pytest.mark.parametrize("platform", SUPPORTED_PLATFORMS)
    def test_all_platforms_return_dicts(self, collector, load_fixture, platform):
        """Все платформы возвращают список словарей."""
        filename = get_fixture_filename(platform, "interfaces")
        if not filename:
            pytest.skip(f"Нет fixture для {platform}")

        output = load_fixture(platform, filename)
        device = create_mock_device(platform, f"{platform}-switch")
        result = collector._parse_output(output, device)

        assert isinstance(result, list)
        if len(result) > 0:
            assert all(isinstance(item, dict) for item in result)

    def test_to_models_conversion(self, collector, load_fixture):
        """Конвертация в модели Interface работает."""
        output = load_fixture("cisco_ios", "show_interfaces.txt")
        device = create_mock_device("cisco_ios", "ios-switch")

        parsed = collector._parse_output(output, device)
        models = collector.to_models(parsed)

        assert len(models) > 0
        for model in models:
            assert isinstance(model, Interface)
            assert model.name is not None
```

### Что здесь происходит

E2E тесты проверяют полную цепочку обработки: реальный вывод команды из файла ->
парсинг TextFSM -> нормализация -> создание моделей. SSH-подключение заменено
mock-устройством, но вся логика парсинга выполняется по-настоящему.

Это ловит регрессии, которые unit-тесты пропускают: например, изменение формата
TextFSM шаблона, несовместимость между парсером и нормализатором.

Параметризация `@pytest.mark.parametrize("platform", SUPPORTED_PLATFORMS)` гарантирует
что одни и те же проверки проходят для всех платформ.

### 5.6 API тесты -- AuthenticatedTestClient

```python
# Файл: tests/test_api/conftest.py

class AuthenticatedTestClient:
    """TestClient wrapper с автоматическими auth headers."""

    def __init__(self, client: TestClient, headers: dict):
        self._client = client
        self._headers = headers

    def _merge_headers(self, kwargs):
        """Объединяет auth headers с пользовательскими."""
        headers = kwargs.get("headers", {})
        headers.update(self._headers)
        kwargs["headers"] = headers
        return kwargs

    def get(self, *args, **kwargs):
        return self._client.get(*args, **self._merge_headers(kwargs))

    def post(self, *args, **kwargs):
        return self._client.post(*args, **self._merge_headers(kwargs))


@pytest.fixture
def auth_headers(credentials_data):
    """Headers с SSH credentials."""
    return {
        "X-SSH-Username": credentials_data["username"],
        "X-SSH-Password": credentials_data["password"],
    }


@pytest.fixture
def client_with_credentials(client, auth_headers):
    """Client с SSH credentials в каждом запросе."""
    return AuthenticatedTestClient(client, auth_headers)


@pytest.fixture
def client_with_netbox(client, full_auth_headers):
    """Client с SSH и NetBox credentials в каждом запросе."""
    return AuthenticatedTestClient(client, full_auth_headers)
```

### Что здесь происходит

API проекта принимает credentials через HTTP-заголовки: `X-SSH-Username`,
`X-SSH-Password`, `X-NetBox-URL`, `X-NetBox-Token`. Вместо того чтобы
дублировать заголовки в каждом тесте, `AuthenticatedTestClient` -- обёртка
вокруг FastAPI `TestClient`, которая автоматически добавляет заголовки
к каждому запросу.

Fixture `client_with_netbox` объединяет SSH и NetBox credentials, чтобы
тесты sync-эндпоинтов не заботились об авторизации:

```python
def test_sync_endpoint(client_with_netbox):
    response = client_with_netbox.post("/api/sync/interfaces", json={...})
    assert response.status_code == 200
```

`pytest.importorskip("fastapi")` в начале conftest пропускает все API-тесты если
FastAPI не установлен -- это позволяет запускать тесты в минимальном окружении.

### 5.7 Регрессионные тесты из продакшена

```python
# Файл: tests/test_collectors/test_port_type_detection.py

def test_production_bug_25g_port_with_10g_sfp(self, normalizer, sample_interface_data):
    """
    Регрессионный тест для Проблемы 1 из прода.

    C9500-48Y4C: 25G порт с 10G трансивером.
    Должен определяться как "10g-sfp+" (по трансиверу), не "25g-sfp28" (по порту).
    """
    data = sample_interface_data["c9500_25g_with_10g_sfp"]
    iface_lower = data["interface"].lower()

    result = normalizer.detect_port_type(data, iface_lower)

    assert result == "10g-sfp+", (
        f"Проблема 1 из прода: 25G порт с 10G SFP-10GBase-LR\n"
        f"media_type должен иметь приоритет над hardware_type!\n"
        f"Expected: '10g-sfp+', Got: '{result}'"
    )
```

### Что здесь происходит

Этот тест фиксирует конкретный баг с продакшена. Его docstring объясняет сценарий:
коммутатор C9500-48Y4C имеет 25G порты, но в них вставлены 10G трансиверы.
Тип должен определяться по трансиверу (media_type), а не по физическому порту
(hardware_type).

Такие тесты -- "охранники": если кто-то изменит логику приоритетов в
`detect_port_type`, тест сломается и напомнит о продакшен-проблеме.

### 5.8 Тестирование QTech-специфичной логики

```python
# Файл: tests/test_qtech_support.py

class TestQtechInterfaceMaps:
    """Тесты маппинга QTech интерфейсов."""

    @pytest.mark.parametrize("full_name,expected_short", [
        ("TFGigabitEthernet 0/1", "TF0/1"),
        ("TFGigabitEthernet 0/48", "TF0/48"),
        ("AggregatePort 1", "Ag1"),
        ("AggregatePort 100", "Ag100"),
        ("HundredGigabitEthernet 0/55", "Hu0/55"),
        ("GigabitEthernet0/1", "Gi0/1"),
    ])
    def test_normalize_short(self, full_name, expected_short):
        """Сокращение QTech имён интерфейсов."""
        result = normalize_interface_short(full_name)
        assert result == expected_short


class TestQtechLagParsing:
    """Тесты парсинга LAG membership для QTech."""

    @pytest.fixture
    def collector(self):
        collector = InterfaceCollector.__new__(InterfaceCollector)
        collector._parser = MagicMock()
        collector._parser.parse.return_value = []
        return collector

    @pytest.fixture
    def aggregate_output(self):
        return """AggregatePort MaxPorts SwitchPort Mode   Load balance  Ports
------------- -------- ---------- ------ ------------- --------
Ag1           16       Enabled    TRUNK  src-dst-mac   Hu0/55  ,Hu0/56
Ag10          16       Enabled    ACCESS src-dst-mac   TF0/1
"""

    def test_parse_lag_membership_qtech(self, collector, aggregate_output):
        result = collector._parse_lag_membership_qtech(aggregate_output)
        assert result.get("Hu0/55") == "Ag1"
        assert result.get("Hu0/56") == "Ag1"
        assert result.get("TF0/1") == "Ag10"
```

### Что здесь происходит

`InterfaceCollector.__new__(InterfaceCollector)` создаёт экземпляр *без вызова
`__init__`*. Это позволяет сконструировать минимальный объект с только нужными
атрибутами, избегая полной инициализации (которая требует credentials, конфигурацию).

Тест парсинга LAG использует реальный вывод QTech-коммутатора и проверяет что
regex-парсер правильно извлекает membership: `Hu0/55` и `Hu0/56` принадлежат `Ag1`,
а `TF0/1` принадлежит `Ag10`.

### 5.9 Итого: структура тестов

```
tests/
├── conftest.py                    # Общие fixtures
├── test_collectors/               # Тесты коллекторов
│   └── test_port_type_detection.py
├── test_netbox/                   # Тесты NetBox синхронизации
│   ├── test_sync_interfaces_vlan.py
│   ├── test_inventory_sync.py
│   └── test_bulk_operations.py
├── test_e2e/                      # E2E без SSH
│   ├── conftest.py                # mock devices, fixture maps
│   ├── test_interface_collector_e2e.py
│   └── test_inventory_collector_e2e.py
├── test_api/                      # API тесты
│   └── conftest.py                # AuthenticatedTestClient
├── test_qtech_support.py          # QTech-специфичные тесты
├── test_qtech_templates.py        # TextFSM шаблоны QTech
└── fixtures/                      # Реальные выводы оборудования
    ├── cisco_ios/
    ├── cisco_nxos/
    └── qtech/
```

Запуск тестов:

```bash
cd /home/sa/project
python -m pytest network_collector/tests/ -v          # Все тесты
python -m pytest network_collector/tests/ -m unit      # Только unit
python -m pytest network_collector/tests/ -m "not slow" # Без медленных
python -m pytest network_collector/tests/ -k "qtech"   # По ключевому слову
```

---

## Резюме

| Компонент | Файл | Назначение |
|-----------|------|------------|
| Config | `config.py` | Загрузка YAML с dot-access и мерж дефолтов |
| Fields Config | `fields_config.py` | Dataclass-обёртки для `fields.yaml` |
| Constants | `core/constants/` | Маппинги интерфейсов, MAC, платформ, команд |
| Exceptions | `core/exceptions.py` | Типизированная иерархия с сериализацией |
| RunContext | `core/context.py` | Контекст запуска с run_id и output_dir |
| Test Fixtures | `tests/conftest.py` | load_fixture, mock_netbox_client |
| Mixin Testing | `tests/test_netbox/` | bind_mixin_methods паттерн |
| E2E Tests | `tests/test_e2e/` | Полный цикл без SSH |
| API Tests | `tests/test_api/` | AuthenticatedTestClient |

> **Следующий шаг:** Изучите [docs/ARCHITECTURE.md](../ARCHITECTURE.md) для
> понимания как все эти компоненты взаимодействуют в реальном потоке данных.
