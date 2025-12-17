# Архитектура Network Collector

## Содержание

1. [Обзор и слои](#обзор-и-слои)
2. [Диаграмма зависимостей](#диаграмма-зависимостей)
3. [Поток данных: Экспорт](#поток-данных-экспорт)
4. [Поток данных: Синхронизация NetBox](#поток-данных-синхронизация-netbox)
5. [Основные классы](#основные-классы)
6. [CRUD операции NetBox](#crud-операции-netbox)
7. [Конфигурация](#конфигурация)
8. [Кастомные TextFSM шаблоны и виртуальные команды](#кастомные-textfsm-шаблоны-и-виртуальные-команды)
9. [Отладка и поиск проблем](#отладка-и-поиск-проблем)
10. [Масштабирование](#масштабирование)

---

## Обзор и слои

### Архитектурные слои

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           PRESENTATION LAYER                                 │
│                              cli.py                                          │
│         Парсинг аргументов, координация, вывод результатов                  │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                ┌───────────────────┼───────────────────┐
                │                   │                   │
                ▼                   ▼                   ▼
┌───────────────────────┐ ┌─────────────────┐ ┌─────────────────────────────┐
│   COLLECTION LAYER    │ │  EXPORT LAYER   │ │    SYNCHRONIZATION LAYER    │
│                       │ │                 │ │                             │
│  collectors/*.py      │ │ exporters/*.py  │ │  netbox/sync.py             │
│  Сбор данных с        │ │ Форматирование  │ │  Логика синхронизации       │
│  устройств            │ │ и сохранение    │ │  с NetBox                   │
└───────────────────────┘ └─────────────────┘ └─────────────────────────────┘
         │                        │                        │
         ▼                        ▼                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CONFIGURATION LAYER                                │
│                                                                              │
│  config.py          fields_config.py        fields.yaml      config.yaml    │
│  Загрузка           Поля экспорта и         Какие поля       Настройки      │
│  config.yaml        синхронизации           включать         приложения     │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CORE LAYER                                      │
│                                                                              │
│  core/connection.py    core/device.py    core/credentials.py   constants.py │
│  SSH подключения       Модель устройства  Учётные данные      Маппинги      │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                ┌───────────────────┼───────────────────┐
                │                   │                   │
                ▼                   ▼                   ▼
┌───────────────────────┐ ┌─────────────────┐ ┌─────────────────────────────┐
│    PARSING LAYER      │ │ EXTERNAL: SSH   │ │   EXTERNAL: NetBox API      │
│                       │ │                 │ │                             │
│  parsers/textfsm.py   │ │ Scrapli         │ │  netbox/client.py           │
│  NTC Templates        │ │ (ssh2 transport)│ │  (pynetbox wrapper)         │
│  + кастомные шаблоны  │ │                 │ │                             │
└───────────────────────┘ └─────────────────┘ └─────────────────────────────┘
```

### Принципы

- **Separation of Concerns**: Каждый слой отвечает за свою задачу
- **Dependency Inversion**: Верхние слои не зависят от реализации нижних
- **Strategy Pattern**: Collectors, Exporters — подключаемые стратегии
- **Template Method**: BaseCollector определяет скелет, наследники переопределяют детали

---

## Диаграмма зависимостей

### Что от чего зависит

```
cli.py
  │
  ├──► collectors/*.py ──► core/connection.py ──► Scrapli
  │         │
  │         └──► parsers/textfsm_parser.py ──► NTC Templates
  │                      │
  │                      └──► core/constants.py (CUSTOM_TEXTFSM_TEMPLATES)
  │
  ├──► exporters/*.py ──► fields_config.py ──► fields.yaml
  │
  ├──► netbox/sync.py ──► netbox/client.py ──► pynetbox ──► NetBox API
  │         │
  │         ├──► collectors/*.py (для сбора данных)
  │         │
  │         ├──► fields_config.py (sync секция)
  │         │
  │         └──► core/constants.py (маппинг типов интерфейсов)
  │
  ├──► config.py ──► config.yaml
  │
  └──► devices_ips.py (список устройств)
```

### Импорты между модулями

| Модуль | Импортирует |
|--------|-------------|
| `cli.py` | collectors, exporters, netbox/sync, config, fields_config |
| `collectors/base.py` | core/connection, core/device, parsers/textfsm |
| `collectors/mac.py` | collectors/base, core/constants |
| `netbox/sync.py` | netbox/client, collectors/*, fields_config, core/constants |
| `netbox/client.py` | pynetbox, config |
| `parsers/textfsm_parser.py` | ntc_templates, textfsm, core/constants |
| `fields_config.py` | fields.yaml (через PyYAML) |
| `exporters/*.py` | pandas (для Excel), fields_config |

---

## Поток данных: Экспорт

### Полная цепочка (пример: MAC-адреса)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. CLI PARSING                                                               │
│    python -m network_collector mac --format excel --with-descriptions        │
│                                                                              │
│    cli.py:cmd_mac()                                                          │
│    - Читает config.yaml через config.py                                      │
│    - Определяет collect_descriptions, exclude_trunk из конфига или флагов    │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 2. DEVICE LOADING                                                            │
│    load_devices() → devices_ips.py                                           │
│                                                                              │
│    devices_list = [                                                          │
│        {"host": "192.168.1.1", "device_type": "cisco_ios"},                  │
│        {"host": "192.168.1.2", "device_type": "cisco_ios"},                  │
│    ]                                                                         │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 3. DATA COLLECTION                                                           │
│    MACCollector.collect(devices)                                             │
│                                                                              │
│    Для каждого устройства (параллельно через ThreadPool):                    │
│    ┌─────────────────────────────────────────────────────────────────────┐   │
│    │ a) ConnectionManager.connect(device, credentials)                   │   │
│    │    - Scrapli SSH подключение                                        │   │
│    │    - platform из SCRAPLI_PLATFORM_MAP                               │   │
│    │                                                                     │   │
│    │ b) conn.send_command("show mac address-table")                      │   │
│    │    - Команда из platform_commands[device_type]                      │   │
│    │                                                                     │   │
│    │ c) textfsm_parser.parse(output, platform, command)                  │   │
│    │    1. Проверка CUSTOM_TEXTFSM_TEMPLATES → templates/*.textfsm       │   │
│    │    2. Fallback на NTC Templates                                     │   │
│    │                                                                     │   │
│    │ d) Добавление metadata: hostname, device_ip                         │   │
│    │                                                                     │   │
│    │ e) Если with_descriptions:                                          │   │
│    │    - conn.send_command("show interfaces description")               │   │
│    │    - Merge description в данные                                     │   │
│    └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│    Результат: List[Dict] — сырые данные                                      │
│    [                                                                         │
│      {"hostname": "SW1", "device_ip": "192.168.1.1", "interface": "Gi0/1",   │
│       "mac": "0011.2233.4455", "vlan": "10", "type": "DYNAMIC",              │
│       "description": "Server-1"},                                            │
│      ...                                                                     │
│    ]                                                                         │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 4. FIELDS TRANSFORMATION                                                     │
│    fields_config.apply_fields_config(data, "mac")                            │
│                                                                              │
│    Читает fields.yaml секцию mac:                                            │
│    ┌─────────────────────────────────────────────────────────────────────┐   │
│    │ mac:                                                                │   │
│    │   hostname:                                                         │   │
│    │     enabled: true                                                   │   │
│    │     name: "Device"        ← переименование                          │   │
│    │     order: 1              ← порядок колонки                         │   │
│    │     default: null         ← значение по умолчанию (опционально)     │   │
│    │   interface:                                                        │   │
│    │     enabled: true                                                   │   │
│    │     name: "Port"                                                    │   │
│    │     order: 3                                                        │   │
│    │   vlan:                                                             │   │
│    │     enabled: false        ← НЕ включать в экспорт                   │   │
│    │     ...                                                             │   │
│    └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│    Трансформация:                                                            │
│    1. Фильтрация: только enabled: true                                       │
│    2. Переименование: hostname → "Device"                                    │
│    3. Сортировка: по order                                                   │
│    4. Default: если значение пустое и есть default — подставить              │
│                                                                              │
│    Результат: List[Dict] — готовые данные                                    │
│    [{"Device": "SW1", "Port": "Gi0/1", "MAC Address": "0011.2233.4455", ...}]│
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 5. EXPORT                                                                    │
│    ExcelExporter.export(data, filename)                                      │
│                                                                              │
│    - pandas.DataFrame(data)                                                  │
│    - Колонки в порядке из fields_config.get_column_order("mac")              │
│    - Сохранение в .xlsx с автофильтром                                       │
│                                                                              │
│    Результат: reports/mac_2025-12-12.xlsx                                    │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Где искать проблемы экспорта

| Симптом | Где смотреть |
|---------|--------------|
| Поле не появляется в таблице | `fields.yaml` → `enabled: false`? |
| Неправильное имя колонки | `fields.yaml` → `name:` |
| Неправильный порядок | `fields.yaml` → `order:` |
| Пустое значение | Коллектор не возвращает поле? Проверить `--format json` |
| Данные не парсятся | `parsers/textfsm_parser.py`, NTC Templates |
| Нет подключения | `core/connection.py`, credentials |

---

## Поток данных: Синхронизация NetBox

### Полная цепочка (пример: интерфейсы)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. CLI PARSING                                                               │
│    python -m network_collector sync-netbox --interfaces --dry-run            │
│                                                                              │
│    cli.py:cmd_sync_netbox()                                                  │
│    - Создаёт NetBoxSync(client, dry_run=True)                                │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 2. NETBOX CLIENT INIT                                                        │
│    NetBoxClient(url, token)                                                  │
│                                                                              │
│    - Подключение к NetBox API через pynetbox                                 │
│    - URL и token из config.yaml или переменных окружения                     │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 3. DATA COLLECTION                                                           │
│    InterfaceCollector.collect(devices)                                       │
│                                                                              │
│    Собирает с устройств:                                                     │
│    - interface, status, description, ip_address                              │
│    - mac_address, mtu, speed, duplex                                         │
│    - hardware_type, media_type (для определения типа в NetBox)               │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 4. SYNC CONFIGURATION                                                        │
│    fields_config.get_sync_config("interfaces")                               │
│                                                                              │
│    Читает fields.yaml секцию sync.interfaces:                                │
│    ┌─────────────────────────────────────────────────────────────────────┐   │
│    │ sync:                                                               │   │
│    │   interfaces:                                                       │   │
│    │     fields:                                                         │   │
│    │       enabled:                                                      │   │
│    │         enabled: true                                               │   │
│    │         source: status     ← откуда брать данные                    │   │
│    │       description:                                                  │   │
│    │         enabled: true                                               │   │
│    │         source: description                                         │   │
│    │       mac_address:                                                  │   │
│    │         enabled: true                                               │   │
│    │         source: mac                                                 │   │
│    │     defaults:                                                       │   │
│    │       type: "1000base-t"   ← если не определён                      │   │
│    │     options:                                                        │   │
│    │       auto_detect_type: true                                        │   │
│    └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 5. INTERFACE TYPE DETECTION                                                  │
│    NetBoxSync._get_interface_type(interface_data)                            │
│                                                                              │
│    Использует маппинги из core/constants.py:                                 │
│    ┌─────────────────────────────────────────────────────────────────────┐   │
│    │ NETBOX_INTERFACE_TYPE_MAP = {                                       │   │
│    │     "10gbase-sr": "10gbase-x-sfpp",                                 │   │
│    │     "1000base-sx": "1000base-x-sfp",                                │   │
│    │     "basetx": "1000base-t",                                         │   │
│    │     ...                                                             │   │
│    │ }                                                                   │   │
│    │                                                                     │   │
│    │ VIRTUAL_INTERFACE_PREFIXES = ("vlan", "loopback", ...)              │   │
│    │ MGMT_INTERFACE_PATTERNS = ("mgmt", "management", ...)               │   │
│    └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│    Логика:                                                                   │
│    1. Виртуальный? (Vlan*, Loopback*) → "virtual"                            │
│    2. Management? (mgmt*, fxp*) → "1000base-t"                               │
│    3. По media_type через NETBOX_INTERFACE_TYPE_MAP                          │
│    4. По hardware_type через NETBOX_HARDWARE_TYPE_MAP                        │
│    5. Fallback → defaults.type из fields.yaml                                │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 6. NETBOX API OPERATIONS                                                     │
│    NetBoxSync.sync_interfaces(device_name, interfaces)                       │
│                                                                              │
│    Для каждого интерфейса:                                                   │
│    ┌─────────────────────────────────────────────────────────────────────┐   │
│    │ a) client.get_device_by_name(device_name)                           │   │
│    │    → Найти устройство в NetBox                                      │   │
│    │                                                                     │   │
│    │ b) client.get_interfaces(device_id)                                 │   │
│    │    → Получить существующие интерфейсы                               │   │
│    │                                                                     │   │
│    │ c) Сравнение:                                                       │   │
│    │    - Есть в NetBox? → UPDATE (если есть изменения)                  │   │
│    │    - Нет в NetBox? → CREATE                                         │   │
│    │                                                                     │   │
│    │ d) Если dry_run: только логирование, без API вызовов                │   │
│    └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│    Результат: {"created": 5, "updated": 3, "skipped": 2, "failed": 0}        │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Порядок --sync-all

```
┌───────────────────────────────────────────────────────────────────┐
│ 1. sync_devices_from_inventory()                                   │
│    Создание устройств (должны существовать до всего остального)   │
└───────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────────────┐
│ 2. sync_interfaces()                                               │
│    Создание интерфейсов (нужны для IP и кабелей)                  │
└───────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────────────┐
│ 3. sync_ip_addresses()                                             │
│    Привязка IP к интерфейсам                                       │
└───────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────────────┐
│ 4. sync_vlans_from_interfaces()                                    │
│    Создание VLAN из SVI интерфейсов (Vlan10 → VLAN 10)            │
└───────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────────────┐
│ 5. sync_cables_from_lldp()                                         │
│    Построение топологии (нужны устройства и интерфейсы)           │
└───────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────────────┐
│ 6. sync_inventory()                                                │
│    Модули, SFP, PSU                                                │
└───────────────────────────────────────────────────────────────────┘
```

---

## Основные классы

### Collectors

```python
# collectors/base.py
class BaseCollector:
    """Базовый класс для всех коллекторов."""

    # Переопределяется в наследниках
    platform_commands: Dict[str, str] = {}

    def collect(self, devices: List[Device]) -> List[Dict]:
        """Главный метод — собирает данные со всех устройств."""
        # ThreadPoolExecutor для параллельного сбора

    def _collect_from_device(self, device: Device) -> List[Dict]:
        """Сбор с одного устройства (переопределяется)."""

    def _get_command(self, device: Device) -> str:
        """Возвращает команду для платформы."""
        return self.platform_commands.get(device.device_type, self.default_command)

    def _parse_output(self, output: str, device: Device) -> List[Dict]:
        """Парсинг вывода (переопределяется)."""
```

```python
# collectors/mac.py
class MACCollector(BaseCollector):
    platform_commands = {
        "cisco_ios": "show mac address-table",
        "cisco_nxos": "show mac address-table",
        "arista_eos": "show mac address-table",
        "qtech": "show mac-address-table",  # кастомная команда
    }

    def collect(self, devices, collect_descriptions=False, collect_trunk_ports=False):
        """Расширенный сбор с опциями."""
```

### Exporters

```python
# exporters/base.py
class BaseExporter(ABC):
    """Абстрактный базовый экспортер."""

    file_extension: str = ".txt"

    def export(self, data: List[Dict], filename: str) -> Path:
        """Экспорт данных в файл."""

    @abstractmethod
    def _write(self, data: List[Dict], file_path: Path) -> None:
        """Реализация записи (в наследниках)."""
```

```python
# exporters/excel.py
class ExcelExporter(BaseExporter):
    file_extension = ".xlsx"

    def _write(self, data, file_path):
        df = pd.DataFrame(data)
        # Автофильтр, заморозка заголовка, автоширина колонок
```

### NetBox

```python
# netbox/client.py
class NetBoxClient:
    """Обёртка над pynetbox для типизированного доступа."""

    def __init__(self, url: str, token: str):
        self.api = pynetbox.api(url, token=token)

    # === DEVICES ===
    def get_devices(self, **filters) -> List
    def get_device_by_name(self, name: str) -> Optional[Device]
    def create_device(self, **data) -> Device
    def update_device(self, device_id: int, **data) -> Device
    def delete_device(self, device_id: int) -> bool

    # === INTERFACES ===
    def get_interfaces(self, device_id: int) -> List
    def create_interface(self, device_id, name, type, **data) -> Interface
    def update_interface(self, interface_id, **data) -> Interface
    def delete_interface(self, interface_id: int) -> bool

    # === IP ADDRESSES ===
    def get_ip_addresses(**filters) -> List
    def create_ip_address(address, interface_id) -> IP
    def delete_ip_address(ip_id: int) -> bool

    # === VLANS ===
    def get_vlans(**filters) -> List
    def create_vlan(vid, name, site) -> VLAN

    # === CABLES ===
    def get_cables(**filters) -> List
    def create_cable(a_termination, b_termination) -> Cable
    def delete_cable(cable_id: int) -> bool

    # === INVENTORY ===
    def get_inventory_items(device_id) -> List
    def create_inventory_item(device_id, name, **data) -> InventoryItem
    def update_inventory_item(item_id, **data) -> InventoryItem
```

```python
# netbox/sync.py
class NetBoxSync:
    """Логика синхронизации данных с NetBox."""

    def __init__(self, client: NetBoxClient, dry_run: bool = False):
        self.client = client
        self.dry_run = dry_run

    # === СИНХРОНИЗАЦИЯ ===
    def sync_devices_from_inventory(self, data, site, role) -> Dict[str, int]
    def sync_interfaces(self, device_name, interfaces) -> Dict[str, int]
    def sync_ip_addresses(self, device_name, ip_data) -> Dict[str, int]
    def sync_vlans_from_interfaces(self, device_name, interfaces, site) -> Dict[str, int]
    def sync_cables_from_lldp(self, lldp_data) -> Dict[str, int]
    def sync_inventory(self, device_name, inventory) -> Dict[str, int]

    # === ВСПОМОГАТЕЛЬНЫЕ ===
    def _get_interface_type(self, data: Dict) -> str
    def _normalize_mac(self, mac: str) -> str
```

### Configuration

```python
# config.py
@dataclass
class AppConfig:
    output: OutputConfig
    connection: ConnectionConfig
    netbox: NetBoxConfig
    filters: FiltersConfig
    mac: MACConfig  # настройки MAC коллектора

def load_config() -> AppConfig:
    """Загружает config.yaml с дефолтами."""
```

```python
# fields_config.py
def get_export_fields(data_type: str) -> Dict
def get_enabled_fields(data_type: str) -> List[Tuple[str, str, int, Any]]
def apply_fields_config(data: List[Dict], data_type: str) -> List[Dict]
def get_column_order(data_type: str) -> List[str]

def get_sync_config(entity_type: str) -> SyncEntityConfig
```

---

## CRUD операции NetBox

### Где что можно создавать/обновлять/удалять

| Сущность | CREATE | READ | UPDATE | DELETE | Файл |
|----------|--------|------|--------|--------|------|
| **Devices** | `--create-devices` | всегда | `--update-devices` | `--cleanup` | sync.py |
| **Interfaces** | `--interfaces` | всегда | `--interfaces` | нет | sync.py |
| **IP Addresses** | `--ip-addresses` | всегда | нет | нет | sync.py |
| **VLANs** | `--vlans` | всегда | нет | нет | sync.py |
| **Cables** | `--cables` | всегда | нет | пересоздание | sync.py |
| **Inventory** | `--inventory` | всегда | `--inventory` | нет | sync.py |

### Детали операций

```python
# Создание устройства
sync_devices_from_inventory():
    - Проверяет существование по hostname
    - CREATE: если нет в NetBox
    - UPDATE: если --update-devices и есть изменения
    - DELETE: если --cleanup и устройства нет в списке

# Синхронизация интерфейсов
sync_interfaces():
    - Получает список интерфейсов из NetBox
    - CREATE: если интерфейса нет
    - UPDATE: если есть изменения (description, enabled, type)
    - НЕ удаляет лишние интерфейсы!

# Синхронизация кабелей
sync_cables_from_lldp():
    - Проверяет существование кабеля между интерфейсами
    - CREATE: если кабеля нет
    - Пропускает: если один из концов не найден в NetBox
    - НЕ удаляет старые кабели!

# Cleanup устройств
--cleanup --tenant "X":
    - Получает все устройства tenant X из NetBox
    - Сравнивает со списком devices_ips.py
    - DELETE: устройства которых нет в списке
    - ТРЕБУЕТ --tenant для безопасности
```

### Безопасность

```python
# sync.py содержит проверки:

def cleanup_devices(self, tenant: str):
    if not tenant:
        raise ValueError("--cleanup требует --tenant")

    if self.dry_run:
        logger.info(f"[DRY-RUN] Удалил бы {device.name}")
    else:
        self.client.delete_device(device.id)
```

---

## Конфигурация

### Файлы конфигурации

```
network_collector/
├── config.yaml        # Настройки приложения
├── fields.yaml        # Поля экспорта и синхронизации
├── devices_ips.py     # Список устройств
└── .env (опционально) # Секреты
```

### config.yaml — структура

```yaml
# Настройки вывода
output:
  output_folder: "reports"
  default_format: "excel"
  mac_format: "ieee"

# SSH подключение
connection:
  conn_timeout: 10
  read_timeout: 30
  max_workers: 5         # параллельные подключения

# NetBox API
netbox:
  url: "http://localhost:8000/"
  token: "xxx"
  verify_ssl: true

# Фильтры для MAC коллектора (применяются везде)
filters:
  exclude_vlans: [1, 4094]
  exclude_interfaces:
    - "^Po\\d+"
    - "^Vlan\\d+"
    - "^Loopback"

# Настройки MAC коллектора
mac:
  collect_descriptions: true    # собирать descriptions по умолчанию
  collect_trunk_ports: false    # исключать trunk порты
```

### fields.yaml — структура

```yaml
# ===== ЭКСПОРТ =====
# Секции: mac, devices, lldp, interfaces, inventory

mac:
  hostname:
    enabled: true           # включить в экспорт
    name: "Device"          # имя колонки
    order: 1                # порядок (меньше = левее)
    default: null           # значение по умолчанию

# ===== СИНХРОНИЗАЦИЯ =====
sync:
  devices:
    fields:
      name:
        enabled: true
        source: hostname     # откуда брать данные
    defaults:
      site: "Main"
      role: "switch"
    options:
      create_missing: true
```

### Приоритет конфигурации

```
1. Аргументы CLI          (--site "DC1")
2. Переменные окружения   (NETBOX_URL)
3. config.yaml            (netbox.url)
4. Дефолты в коде         (config.py)
```

---

## Кастомные TextFSM шаблоны и виртуальные команды

### Архитектура парсинга

Парсер поддерживает несколько уровней шаблонов:

```
1. CUSTOM_TEXTFSM_TEMPLATES (core/constants.py)  ← приоритет
   │
   ▼
2. templates/*.textfsm (локальные шаблоны)
   │
   ▼
3. NTC Templates (fallback)
```

### Виртуальные ключи команд

Иногда одна и та же команда (например `show running-config`) используется для разных целей:
- **Бэкап**: сохранение всей конфигурации
- **Port-security**: извлечение sticky MAC-адресов

Для разделения используются **виртуальные ключи** — строки, которые не являются реальными командами,
но определяют какой шаблон использовать:

```python
# core/constants.py
CUSTOM_TEXTFSM_TEMPLATES = {
    # Реальная команда: show running-config
    # Виртуальный ключ: port-security
    # Результат: парсинг sticky MAC из show run
    ("cisco_ios", "port-security"): "cisco_ios_port_security.textfsm",
    ("cisco_iosxe", "port-security"): "cisco_ios_port_security.textfsm",

    # Для других вендоров — свои шаблоны
    # ("arista_eos", "port-security"): "arista_eos_port_security.textfsm",
    # ("qtech", "port-security"): "qtech_port_security.textfsm",
}
```

### Использование в коллекторе

```python
# collectors/mac.py
def _collect_sticky_macs(self, conn, device, interface_status):
    # 1. Выполняем реальную команду
    response = conn.send_command("show running-config")

    # 2. Парсим с виртуальным ключом "port-security"
    parsed = self._textfsm_parser.parse(
        output=response.result,
        platform=device.device_type,  # cisco_ios
        command="port-security"       # виртуальный ключ
    )

    # 3. Результат: список sticky MAC
    # [{"interface": "Gi0/1", "mac": "0011.2233.4455", "vlan": "10", "type": "sticky"}]
```

### Port-Security: сбор offline устройств

#### Проблема

Стандартная таблица MAC (`show mac address-table`) показывает только **активные** MAC-адреса.
Устройства с port-security sticky MAC, которые сейчас offline, не отображаются.

#### Решение

Парсинг `show running-config` для извлечения sticky MAC:

```
interface GigabitEthernet0/1
 switchport access vlan 10
 switchport port-security mac-address sticky 0011.2233.4455
```

#### Поток данных

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ MACCollector._collect_from_device()                                          │
│                                                                              │
│ 1. show mac address-table    → активные MAC (status: online/offline)        │
│ 2. show running-config       → sticky MAC (парсинг port-security)            │
│                                                                              │
│ Merge логика:                                                                │
│ - sticky MAC есть в активной таблице? → уже добавлен                         │
│ - sticky MAC НЕТ в активной таблице? → добавить со status: offline           │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### CLI использование

```bash
# Включить сбор port-security
python -m network_collector mac --with-port-security --format excel

# Или в config.yaml
mac:
  collect_port_security: true
```

### Добавление поддержки нового вендора

Чтобы добавить парсинг port-security для нового вендора:

1. **Создать шаблон** `templates/vendor_port_security.textfsm`

2. **Добавить маппинг** в `core/constants.py`:
```python
CUSTOM_TEXTFSM_TEMPLATES = {
    ("vendor_platform", "port-security"): "vendor_port_security.textfsm",
}
```

3. **Готово!** Коллектор автоматически использует шаблон для этой платформы.

### Пример шаблона port-security

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

## Отладка и поиск проблем

### Где искать по симптомам

| Проблема | Где смотреть | Что проверить |
|----------|--------------|---------------|
| **Нет подключения к устройству** | `core/connection.py` | credentials, device_type, timeout |
| **Команда не выполняется** | `collectors/*.py` | `platform_commands`, `_get_command()` |
| **Данные не парсятся** | `parsers/textfsm_parser.py` | NTC Templates, кастомные шаблоны |
| **Поле не в экспорте** | `fields.yaml` | `enabled: false`? |
| **Неправильный тип интерфейса** | `core/constants.py` | `NETBOX_INTERFACE_TYPE_MAP` |
| **NetBox API ошибка** | `netbox/client.py` | URL, token, версия API |
| **Sync не создаёт** | `netbox/sync.py` | `dry_run`? уже существует? |

### Логирование

```python
# Включить debug логирование
import logging
logging.basicConfig(level=logging.DEBUG)

# Или через CLI
python -m network_collector mac --format json 2>&1 | grep -i error
```

### Проверка данных на каждом этапе

```bash
# 1. Проверить сырые данные (до fields_config)
python -m network_collector mac --format json > raw.json

# 2. Проверить NTC парсинг
python -c "
from ntc_templates.parse import parse_output
output = open('show_mac.txt').read()
print(parse_output(platform='cisco_ios', command='show mac address-table', data=output))
"

# 3. Проверить NetBox API
python -c "
import pynetbox
api = pynetbox.api('http://localhost:8000', token='xxx')
print(list(api.dcim.devices.all()))
"
```

### Отладка коллектора

```python
# collectors/mac.py
def _collect_from_device(self, device):
    logger.debug(f"Подключение к {device.host}")

    conn = self.connection_manager.connect(device, self.credentials)
    logger.debug(f"Выполняю команду: {self._get_command(device)}")

    output = conn.send_command(self._get_command(device))
    logger.debug(f"Вывод: {output[:500]}...")

    parsed = self._parse_output(output, device)
    logger.debug(f"Распарсено записей: {len(parsed)}")

    return parsed
```

---

## Масштабирование

### Текущие ограничения

| Компонент | Ограничение | Причина |
|-----------|-------------|---------|
| Параллельность | `max_workers` в config | ThreadPoolExecutor |
| Размер данных | Память | Всё в List[Dict] |
| NetBox API | Rate limiting | pynetbox |
| SSH | Timeout | Scrapli |

### Варианты масштабирования

#### 1. Горизонтальное: больше устройств

```yaml
# config.yaml
connection:
  max_workers: 20       # увеличить параллельность
  conn_timeout: 5       # уменьшить timeout для быстрых устройств
  read_timeout: 60      # увеличить для медленных команд
```

#### 2. Разделение по сайтам

```python
# devices_ips.py — разные файлы для разных сайтов
# devices_dc1.py
# devices_dc2.py

# CLI с указанием файла
python -m network_collector mac --devices-file devices_dc1.py
```

#### 3. Очередь задач (будущее)

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Celery    │────►│   Workers   │────►│   NetBox    │
│   Queue     │     │  (collect)  │     │   API       │
└─────────────┘     └─────────────┘     └─────────────┘
       ▲
       │
┌─────────────┐
│  Scheduler  │  (cron, periodic)
└─────────────┘
```

#### 4. Кэширование

```python
# Возможное улучшение:
class CachedNetBoxClient(NetBoxClient):
    def __init__(self, *args, cache_ttl=300, **kwargs):
        super().__init__(*args, **kwargs)
        self._cache = {}
        self._cache_ttl = cache_ttl

    def get_device_by_name(self, name):
        if name in self._cache:
            return self._cache[name]
        result = super().get_device_by_name(name)
        self._cache[name] = result
        return result
```

#### 5. Streaming экспорт (большие данные)

```python
# Вместо List[Dict] в памяти — генератор + streaming write
class StreamingExporter:
    def export_streaming(self, data_generator, filename):
        with open(filename, 'w') as f:
            for row in data_generator:
                f.write(json.dumps(row) + '\n')
```

#### 6. Микросервисы (enterprise)

```
┌─────────────────────────────────────────────────────────────┐
│                      API Gateway                             │
└─────────────────────────────────────────────────────────────┘
         │              │              │              │
         ▼              ▼              ▼              ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│  Collector  │ │  Collector  │ │   NetBox    │ │   Export    │
│  Service    │ │  Service    │ │   Sync      │ │   Service   │
│  (MAC)      │ │  (LLDP)     │ │   Service   │ │             │
└─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘
         │              │              │              │
         └──────────────┴──────────────┴──────────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │   Message Broker    │
                    │   (RabbitMQ/Kafka)  │
                    └─────────────────────┘
```

### Что можно добавить

| Функционал | Сложность | Описание |
|------------|-----------|----------|
| Retry логика | Низкая | Повторные попытки при ошибках |
| Progress bar | Низкая | tqdm для длительных операций |
| Webhook уведомления | Средняя | Slack/Teams при ошибках |
| Scheduled runs | Средняя | Cron или APScheduler |
| Web UI | Высокая | FastAPI + React dashboard |
| Multi-tenancy | Высокая | Разные credentials для разных tenant |

---

## Структура файлов (полная)

```
network_collector/
├── __init__.py
├── __main__.py              # python -m network_collector
├── cli.py                   # CLI интерфейс (точка входа)
│
├── config.py                # Загрузчик config.yaml
├── config.yaml              # Настройки приложения
├── fields_config.py         # Загрузчик fields.yaml
├── fields.yaml              # Поля экспорта/синхронизации
├── devices_ips.py           # Список устройств
│
├── core/                    # Ядро
│   ├── __init__.py
│   ├── connection.py        # SSH через Scrapli
│   ├── credentials.py       # Управление учётными данными
│   ├── device.py            # Модель Device
│   └── constants.py         # Маппинги, константы
│
├── collectors/              # Сборщики данных
│   ├── __init__.py
│   ├── base.py              # BaseCollector
│   ├── device.py            # DeviceCollector, DeviceInventoryCollector
│   ├── mac.py               # MACCollector
│   ├── lldp.py              # LLDPCollector
│   ├── interfaces.py        # InterfaceCollector
│   ├── inventory.py         # InventoryCollector
│   └── config_backup.py     # ConfigBackupCollector
│
├── parsers/                 # Парсеры
│   ├── __init__.py
│   └── textfsm_parser.py    # NTC Templates + кастомные
│
├── templates/               # Кастомные TextFSM шаблоны
│   ├── README.md
│   └── *.textfsm
│
├── exporters/               # Экспорт
│   ├── __init__.py
│   ├── base.py              # BaseExporter
│   ├── excel.py             # ExcelExporter
│   ├── csv_exporter.py      # CSVExporter
│   └── json_exporter.py     # JSONExporter
│
├── netbox/                  # NetBox интеграция
│   ├── __init__.py
│   ├── client.py            # NetBoxClient (pynetbox wrapper)
│   └── sync.py              # NetBoxSync (логика синхронизации)
│
├── configurator/            # Конфигурация устройств
│   ├── __init__.py
│   ├── base.py
│   └── description.py       # MAC matching, push descriptions
│
├── reports/                 # Папка для экспорта (создаётся)
│
├── ARCHITECTURE.md          # Этот файл
├── CLAUDE.md                # Инструкции для Claude
├── USAGE.md                 # Инструкция пользователя
├── WORK_IN_PROGRESS.md      # Текущие задачи
└── requirements.txt         # Зависимости
```

---

## Зависимости (requirements.txt)

```
# SSH
scrapli[ssh2]>=2024.1.30

# Парсинг
ntc-templates>=5.0.0
textfsm>=1.1.3

# NetBox
pynetbox>=7.4.0

# Данные и экспорт
pandas>=2.0.0
openpyxl>=3.1.0

# Конфигурация
pyyaml>=6.0

# Опционально
python-dotenv>=1.0.0    # .env файлы
tqdm>=4.65.0            # progress bar (будущее)
```
