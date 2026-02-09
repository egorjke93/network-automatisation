# 04. Сбор данных с устройств

Как Network Collector подключается к сетевому оборудованию, получает данные
и превращает текстовый вывод команд в структурированные объекты Python.

---

## 1. Общая схема сбора

Весь процесс от начала до конца:

```
Список устройств (devices.json / CLI аргументы)
    │
    ▼
SSH подключение (Scrapli)
    │
    ▼
Отправка команды ("show mac address-table", "show interfaces", ...)
    │
    ▼
Текстовый вывод с устройства (сырой текст)
    │
    ▼
TextFSM парсинг (NTC Templates / кастомные шаблоны)
    │
    ▼
Сырые данные (list of dicts)
    │
    ▼
Normalizer (Domain Layer) — приведение к единому формату
    │
    ▼
Модель (dataclass) — Interface, MACEntry, LLDPNeighbor, ...
```

Каждый шаг отвечает за своё:
- **Scrapli** -- подключение и передача команд
- **TextFSM** -- превращение текста в таблицу
- **Normalizer** -- единый формат для всех вендоров
- **Модель** -- типизированный объект для дальнейшей обработки

---

## 2. SSH через Scrapli

**Scrapli** -- это Python-библиотека для SSH-подключений к сетевому оборудованию.
Она знает особенности каждой платформы: как выглядит prompt, как войти в enable-режим,
какие символы экранировать.

**Файл:** `core/connection.py`

### Упрощённый пример -- как это работает внутри

```python
from scrapli import Scrapli

conn = Scrapli(
    host="10.0.0.1",
    auth_username="admin",
    auth_password="pass",
    platform="cisco_iosxe",       # Определяет поведение SSH-клиента
    transport="ssh2",             # SSH-библиотека (ssh2-python)
    auth_strict_key=False,        # Не проверять SSH-ключи (лаба/прод)
)
conn.open()
result = conn.send_command("show mac address-table")
print(result.result)  # Текстовый вывод команды, как если бы набрали руками
conn.close()
```

### Зачем нужен `platform`?

Разные устройства ведут себя по-разному:
- **Cisco IOS** -- prompt заканчивается на `#`, enable через `enable`
- **Arista EOS** -- prompt тоже `#`, но другие escape-последовательности
- **Juniper** -- prompt `>` или `#`, команды совсем другие (`show interfaces terse`)

Scrapli использует `platform` чтобы знать:
- как определить что команда завершилась (по prompt)
- нужно ли нажимать `--More--` (пагинация)
- как войти в privileged-режим

### Маппинг платформ в проекте

```python
# core/connection.py
SCRAPLI_PLATFORM_MAP = {
    "cisco_ios": "cisco_iosxe",     # IOS и IOS-XE используют один драйвер
    "cisco_iosxe": "cisco_iosxe",
    "cisco_nxos": "cisco_nxos",     # Nexus -- отдельный драйвер
    "arista_eos": "arista_eos",
    "juniper_junos": "juniper_junos",
    "qtech": "cisco_iosxe",        # QTech ведёт себя как Cisco IOS
}
```

QTech не поддерживается Scrapli напрямую, поэтому используем драйвер Cisco IOS --
у них похожий CLI. Это рабочий подход для многих "cisco-like" устройств.

### ConnectionManager -- обёртка с retry

В реальном проекте мы не используем Scrapli напрямую. Вместо этого есть `ConnectionManager`,
который добавляет:

- **Retry** -- если устройство не ответило, пробуем снова (по умолчанию 2 попытки)
- **Context manager** -- подключение автоматически закрывается
- **Обработку ошибок** -- разные типы ошибок (таймаут, неправильный пароль, сеть недоступна)

```python
# Реальное использование в коллекторах
manager = ConnectionManager(
    timeout_socket=15,      # 15 сек на установку TCP-соединения
    timeout_transport=30,   # 30 сек на SSH handshake
    timeout_ops=60,         # 60 сек на выполнение команды
    max_retries=2,          # 2 повторные попытки
    retry_delay=5,          # 5 сек между попытками
)

with manager.connect(device, credentials) as conn:
    output = conn.send_command("show version")
    hostname = manager.get_hostname(conn)  # Извлекает hostname из prompt
```

Ошибки аутентификации (неправильный пароль) **не** повторяются -- нет смысла
отправлять тот же пароль ещё раз. Повторяются только таймауты и проблемы с сетью.

---

## 3. TextFSM парсинг

**Проблема:** устройство возвращает текст. Человеку удобно читать, программе -- нет.

### Пример: текст с устройства

```
Vlan    Mac Address       Type        Ports
----    -----------       --------    -----
10      0011.2233.4455    DYNAMIC     Gi0/1
20      aabb.ccdd.eeff    DYNAMIC     Gi0/2
```

### После TextFSM парсинга -- список словарей

```python
[
    {"vlan": "10", "mac": "0011.2233.4455", "type": "DYNAMIC", "interface": "Gi0/1"},
    {"vlan": "20", "mac": "aabb.ccdd.eeff", "type": "DYNAMIC", "interface": "Gi0/2"},
]
```

TextFSM -- это шаблонный парсер от Google. Он использует `.textfsm` файлы,
которые описывают формат вывода команды с помощью регулярных выражений.

### NTC Templates -- готовые шаблоны

**NTC Templates** (`ntc-templates`) -- это библиотека с 1000+ готовыми TextFSM шаблонами
для разных платформ и команд. Вместо того чтобы писать regex для каждой команды
каждого вендора, мы просто вызываем:

```python
from ntc_templates.parse import parse_output

# Автоматически находит шаблон для cisco_ios + show mac address-table
result = parse_output(
    platform="cisco_ios",
    command="show mac address-table",
    data=raw_text_output,
)
# result = [{"destination_address": "0011.2233.4455", ...}, ...]
```

**Файл:** `parsers/textfsm_parser.py`

### NTCParser -- обёртка в проекте

Проект использует класс `NTCParser`, который добавляет:

1. **Приоритет шаблонов**: сначала кастомный шаблон (для QTech/Eltex), потом NTC Templates
2. **Нормализация полей**: приводит разные имена к стандартным
   (`destination_address` -> `mac`, `port` -> `interface`)
3. **Фильтрация полей**: можно запросить только нужные поля

```python
parser = NTCParser()

# Парсинг с нормализацией полей
data = parser.parse(
    output=raw_output,
    platform="cisco_ios",
    command="show mac address-table",
)
# data = [{"mac": "0011.2233.4455", "vlan": "10", "interface": "Gi0/1", ...}]

# Только определённые поля
data = parser.parse(
    output=raw_output,
    platform="cisco_ios",
    command="show version",
    fields=["hostname", "version", "serial"],
)
```

### Маппинг платформ для NTC Templates

```python
# core/connection.py
NTC_PLATFORM_MAP = {
    "cisco_iosxe": "cisco_ios",    # NTC использует "cisco_ios" для IOS/IOS-XE
    "cisco_nxos": "cisco_nxos",
    "arista_eos": "arista_eos",
    "juniper_junos": "juniper_junos",
    "qtech": "cisco_ios",          # QTech парсим шаблонами Cisco IOS
}
```

### Отладка парсинга: --format parsed

Если TextFSM парсинг работает неправильно, можно посмотреть сырые данные **до**
нормализации — формат `parsed` показывает результат TextFSM с оригинальными ключами
NTC Templates (например, `destination_address` вместо `mac`):

```bash
# Посмотреть что вернул TextFSM для MAC-таблицы
python -m network_collector mac --format parsed

# Сравни с нормализованным форматом
python -m network_collector mac --format json
```

**Разница raw vs parsed:**
- `--format raw` — текст команды с устройства (как если бы набрали руками)
- `--format parsed` — результат TextFSM парсинга (список словарей до нормализации)

### Fallback на regex

Если TextFSM шаблон не нашёлся или парсинг не удался, коллектор переключается
на regex парсинг. Например, для MAC-таблицы:

```python
# collectors/mac.py -- _parse_with_regex_raw()
pattern = re.compile(
    r"^\s*(\d+)\s+"           # VLAN
    r"([0-9a-fA-F.:]+)\s+"    # MAC
    r"(\w+)\s+"               # TYPE (DYNAMIC, STATIC)
    r"(\S+)",                 # INTERFACE
    re.MULTILINE,
)
```

Это страховка: если NTC Templates обновили шаблон и он сломался, сбор данных
продолжит работать.

---

## 4. Нормализация (Domain Layer)

### Зачем нужна нормализация?

Разные вендоры возвращают данные в разных форматах:

```
Имена интерфейсов:
  Cisco:   "GigabitEthernet0/1", "Gi0/1"
  Arista:  "Ethernet1", "Et1"
  Juniper: "ge-0/0/1"

MAC-адреса:
  Cisco:   "0011.2233.4455"        (cisco-формат, точки)
  Arista:  "0011.2233.4455"        (тоже cisco-формат)
  Linux:   "00:11:22:33:44:55"     (ieee-формат, двоеточия)

Статусы интерфейсов:
  Cisco:   "connected", "notconnect", "err-disabled"
  Arista:  "connected", "notconnect"
  Общий:   "up", "down", "disabled", "error"
```

Нормализатор приводит все данные к единому формату, чтобы остальной код
не думал о различиях между вендорами.

### Классы нормализаторов

Каждый тип данных имеет свой нормализатор в `core/domain/`:

| Класс | Файл | Что делает |
|-------|------|-----------|
| `MACNormalizer` | `core/domain/mac.py` | MAC-адреса, интерфейсы, фильтрация VLAN |
| `InterfaceNormalizer` | `core/domain/interface.py` | Статусы, port_type, switchport mode |
| `LLDPNormalizer` | `core/domain/lldp.py` | Идентификация соседей, объединение LLDP+CDP |
| `InventoryNormalizer` | `core/domain/inventory.py` | Определение manufacturer по PID |

### Пример: MACNormalizer

```python
# core/domain/mac.py
normalizer = MACNormalizer(
    mac_format="ieee",                        # Формат вывода MAC
    normalize_interfaces=True,                # Сокращать имена интерфейсов
    exclude_interfaces=["^Vlan\\d+", "^Po\\d+"],  # Исключить эти интерфейсы
    exclude_vlans=[1, 4094],                  # Исключить эти VLAN
)

raw_data = [
    {"mac": "0011.2233.4455", "interface": "GigabitEthernet0/1", "vlan": "10", "type": "DYNAMIC"},
    {"mac": "aabb.ccdd.eeff", "interface": "Vlan100", "vlan": "100", "type": "STATIC"},
]

result = normalizer.normalize_dicts(
    raw_data,
    interface_status={"Gi0/1": "connected"},  # Для online/offline статуса
    hostname="switch-01",
    device_ip="10.0.0.1",
)
# result = [
#   {"mac": "00:11:22:33:44:55", "interface": "Gi0/1", "vlan": "10",
#    "type": "dynamic", "status": "online", "hostname": "switch-01", "device_ip": "10.0.0.1"},
# ]
# Vlan100 отфильтрован (exclude_interfaces), MAC нормализован в ieee формат
```

### Пример: InterfaceNormalizer

```python
# core/domain/interface.py
normalizer = InterfaceNormalizer()

raw_data = [
    {"interface": "GigabitEthernet0/1", "link_status": "connected", "mac": "0011.2233.4455"},
    {"interface": "GigabitEthernet0/2", "link_status": "administratively down"},
]

result = normalizer.normalize_dicts(raw_data, hostname="switch-01", device_ip="10.0.0.1")
# result = [
#   {"interface": "GigabitEthernet0/1", "status": "up", "port_type": "1g-rj45", ...},
#   {"interface": "GigabitEthernet0/2", "status": "disabled", "port_type": "1g-rj45", ...},
# ]
```

Нормализатор:
- `connected` -> `up`, `administratively down` -> `disabled`
- Определяет `port_type` по имени интерфейса и hardware_type
- Добавляет `hostname` и `device_ip` к каждой записи

### Зачем Domain Layer отдельно от коллекторов?

**Тестируемость.** Нормализаторы -- чистые функции: принимают данные, возвращают данные.
Не нужен SSH, не нужны реальные устройства. Можно тестировать отдельно:

```python
# В тестах
normalizer = MACNormalizer(mac_format="ieee")
result = normalizer.normalize_dicts([{"mac": "0011.2233.4455", "interface": "Gi0/1"}])
assert result[0]["mac"] == "00:11:22:33:44:55"
```

---

## 5. Модели данных (dataclass)

**Файл:** `core/models.py`

Модели -- это Python dataclass, которые описывают структуру данных.
Вместо работы с `dict` (где можно опечататься в ключе и не заметить),
используются типизированные объекты.

### Interface -- данные интерфейса

```python
@dataclass
class Interface:
    name: str               # GigabitEthernet0/1
    description: str = ""   # "К серверу DB-01"
    status: str = "unknown" # up / down / disabled / error
    ip_address: str = ""    # 10.0.0.1
    prefix_length: str = "" # 24
    mac: str = ""           # 00:11:22:33:44:55
    speed: str = ""         # 1000
    duplex: str = ""        # full / half / auto
    mtu: int = None         # 1500
    mode: str = ""          # access / tagged / tagged-all
    native_vlan: str = ""   # 1 (для trunk портов)
    tagged_vlans: str = ""  # "10,20,30" (для trunk портов)
    access_vlan: str = ""   # 100 (для access портов)
    port_type: str = ""     # 1g-rj45, 10g-sfp+, lag, virtual
    lag: str = ""           # Port-channel1 (если member LAG)
    hostname: str = ""      # switch-01
    device_ip: str = ""     # 10.0.0.1
```

### MACEntry -- запись MAC-таблицы

```python
@dataclass
class MACEntry:
    mac: str                # 00:11:22:33:44:55
    interface: str          # Gi0/1
    vlan: str = ""          # 10
    mac_type: str = "dynamic"  # dynamic / static / sticky
    hostname: str = ""      # switch-01
    device_ip: str = ""     # 10.0.0.1
    vendor: str = ""        # Cisco (определяется по OUI)
```

### Другие модели

```python
@dataclass
class LLDPNeighbor:
    local_interface: str     # GigabitEthernet0/1
    remote_hostname: str     # neighbor-switch-01
    remote_port: str         # GigabitEthernet0/2
    remote_mac: str = ""     # 00:11:22:33:44:55
    remote_ip: str = ""      # 10.0.0.2
    neighbor_type: str = ""  # hostname / mac / ip / unknown
    protocol: str = "lldp"   # lldp / cdp

@dataclass
class InventoryItem:
    name: str               # "Power Supply 1"
    pid: str = ""           # WS-C2960X-PSU (Product ID)
    serial: str = ""        # FDO1234ABCD
    description: str = ""   # "AC Power Supply"
    manufacturer: str = ""  # Cisco

@dataclass
class DeviceInfo:
    hostname: str           # switch-01
    ip_address: str = ""    # 10.0.0.1
    platform: str = ""      # cisco_ios
    model: str = ""         # WS-C2960X-48FPD-L
    serial: str = ""        # FDO1234ABCD
    version: str = ""       # 15.2(7)E7
    uptime: str = ""        # 45 days, 12:30:15
    manufacturer: str = ""  # Cisco
```

### Зачем модели вместо словарей?

1. **Автокомплит в IDE** -- редактор подскажет какие поля есть
2. **Type hints** -- mypy/pyright покажут ошибки до запуска
3. **Единый формат** -- все коллекторы возвращают одинаковые объекты
4. **Документация** -- поля описаны прямо в коде

### Конвертация

Модели поддерживают конвертацию из словарей и обратно:

```python
# Из словаря (данные от парсера)
intf = Interface.from_dict({"interface": "Gi0/1", "link_status": "up", "ip_address": "10.0.0.1"})

# Обратно в словарь (для экспорта в JSON/Excel)
data = intf.to_dict()  # {"name": "Gi0/1", "status": "up", "ip_address": "10.0.0.1"}

# Конвертация списка
interfaces = Interface.ensure_list(list_of_dicts)  # Если уже Interface -- вернёт как есть
```

---

## 6. Коллекторы

Коллектор -- один класс на один тип данных. Все наследуются от `BaseCollector`.

**Файлы:** `collectors/*.py`

### Иерархия

```
BaseCollector              # Базовый класс: SSH + парсинг + параллелизм
├── DeviceCollector        # show version → DeviceInfo
├── MACCollector           # show mac address-table → MACEntry
├── LLDPCollector          # show lldp/cdp neighbors → LLDPNeighbor
├── InterfaceCollector     # show interfaces → Interface
├── InventoryCollector     # show inventory → InventoryItem
└── ConfigBackupCollector  # show running-config → текстовый файл
```

### BaseCollector -- что даёт базовый класс

**Файл:** `collectors/base.py`

```python
class BaseCollector(ABC):
    # Переопределяется в наследниках
    command: str = ""                    # Команда для выполнения
    platform_commands: Dict[str, str] = {}  # Команды для разных платформ
    model_class: Type = None             # Класс модели (Interface, MACEntry, ...)

    def collect(self, devices):
        """Собирает данные → List[Model] (типизированные объекты)."""

    def collect_dicts(self, devices):
        """Собирает данные → List[Dict] (для экспортеров)."""

    def _collect_parallel(self, devices):
        """Параллельный сбор через ThreadPoolExecutor."""

    def _collect_from_device(self, device):
        """Сбор с одного устройства: connect → send_command → parse."""

    def _parse_with_ntc(self, output, device):
        """Парсинг через NTC Templates."""

    @abstractmethod
    def _parse_output(self, output, device):
        """Парсинг вывода -- реализуется в каждом наследнике."""
```

### Пример: как работает MACCollector

**Файл:** `collectors/mac.py`

```python
class MACCollector(BaseCollector):
    model_class = MACEntry  # Типизированная модель

    # Разные команды для разных платформ
    platform_commands = {
        "cisco_ios": "show mac address-table",
        "cisco_nxos": "show mac address-table",
        "arista_eos": "show mac address-table",
        "juniper_junos": "show ethernet-switching table",
    }
```

При сборе MACCollector выполняет несколько команд на каждом устройстве:

1. `show mac address-table` -- основная таблица MAC
2. `show interfaces status` -- статус портов (online/offline)
3. `show interfaces trunk` -- список trunk портов (для фильтрации)
4. `show interfaces description` -- описания портов (опционально)

Затем передаёт всё в `MACNormalizer` для нормализации.

### Пример: как работает InterfaceCollector

**Файл:** `collectors/interfaces.py`

```python
class InterfaceCollector(BaseCollector):
    model_class = Interface

    # Дополнительные команды для обогащения данных
    lag_commands = {"cisco_ios": "show etherchannel summary", ...}
    switchport_commands = {"cisco_ios": "show interfaces switchport", ...}
    media_type_commands = {"cisco_nxos": "show interface status", ...}
```

InterfaceCollector собирает данные в несколько этапов:

1. `show interfaces` -- основные данные (парсинг через NTC)
2. `InterfaceNormalizer.normalize_dicts()` -- нормализация статусов и типов
3. `show etherchannel summary` -- определение LAG membership
4. `show interfaces switchport` -- режим порта (access/trunk)
5. `InterfaceNormalizer.enrich_with_lag/switchport()` -- обогащение данных

Такая архитектура (парсинг отдельно, нормализация отдельно, обогащение отдельно)
позволяет легко тестировать каждый этап.

---

## 7. Параллельный сбор

**Проблема:** если устройств 22 штуки и каждое отвечает ~15 секунд,
последовательный сбор займёт 22 x 15 = 330 секунд (5,5 минут).

**Решение:** параллельный сбор через `ThreadPoolExecutor`.

### Как это работает

```python
# collectors/base.py -- _collect_parallel()
with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
    # Отправляем задачи: "собрать данные с каждого устройства"
    futures = {
        executor.submit(self._collect_from_device, device): device
        for device in devices
    }

    # Собираем результаты по мере готовности
    for future in as_completed(futures):
        device = futures[future]
        try:
            data = future.result()
            all_data.extend(data)
        except Exception as e:
            logger.error(f"Ошибка сбора с {device.host}: {e}")
```

### Простыми словами

Представьте что вы звоните 22 коллегам по очереди. Каждый разговор -- 15 секунд.
Итого: 22 x 15 = 330 секунд.

А теперь представьте что у вас 10 телефонов и вы звоните 10 коллегам одновременно:
- Раунд 1: 10 коллег одновременно = 15 секунд
- Раунд 2: 10 коллег одновременно = 15 секунд
- Раунд 3: 2 коллеги = 15 секунд
- Итого: ~45 секунд вместо 330

### Настройка

```yaml
# config.yaml
connection:
  max_workers: 10    # Максимум параллельных SSH-сессий
```

`max_workers: 10` означает не более 10 одновременных SSH-подключений.
Если устройств 22, первые 10 обрабатываются параллельно, потом следующие 10,
и наконец оставшиеся 2.

Зачем ограничение? Каждое SSH-подключение:
- занимает порт на управляющем сервере
- создаёт нагрузку на сетевое оборудование
- потребляет память Python-процесса

Для типичной инфраструктуры (20-50 устройств) значение 10 оптимально.

### Потокобезопасность

Потоки (`threads`) -- это не процессы. Они разделяют память, но:
- Каждый поток создаёт **своё** SSH-подключение (thread-safe)
- Результаты собираются в общий список через `as_completed()`
- Ошибка в одном потоке не влияет на остальные

---

## Итого: путь данных на конкретном примере

Допустим, мы собираем MAC-таблицу с Cisco switch-01 (10.0.0.1):

```
1. MACCollector.collect([switch-01])
   │
2. ThreadPoolExecutor → _collect_from_device(switch-01)
   │
3. ConnectionManager.connect("10.0.0.1", platform="cisco_iosxe")
   │  SSH подключение через Scrapli, hostname = "switch-01"
   │
4. conn.send_command("show mac address-table")
   │  Текст: "10  0011.2233.4455  DYNAMIC  Gi0/1\n..."
   │
5. NTCParser.parse(output, "cisco_ios", "show mac address-table")
   │  [{"mac": "0011.2233.4455", "vlan": "10", "interface": "Gi0/1", "type": "DYNAMIC"}]
   │
6. MACNormalizer.normalize_dicts(raw_data, interface_status, hostname, device_ip)
   │  [{"mac": "00:11:22:33:44:55", "vlan": "10", "interface": "Gi0/1",
   │    "type": "dynamic", "status": "online", "hostname": "switch-01"}]
   │
7. MACEntry.from_dict(normalized_data)
   │  MACEntry(mac="00:11:22:33:44:55", interface="Gi0/1", vlan="10", ...)
   │
8. Результат → экспорт в Excel / синхронизация с NetBox
```

---

## Ключевые файлы

| Файл | Описание |
|------|----------|
| `core/connection.py` | SSH через Scrapli, ConnectionManager, маппинг платформ |
| `parsers/textfsm_parser.py` | NTCParser, TextFSM парсинг, нормализация полей |
| `core/models.py` | Dataclass модели: Interface, MACEntry, LLDPNeighbor, ... |
| `collectors/base.py` | BaseCollector: общая логика SSH + парсинг + параллелизм |
| `collectors/mac.py` | MACCollector: сбор MAC-таблицы |
| `collectors/interfaces.py` | InterfaceCollector: сбор интерфейсов |
| `collectors/lldp.py` | LLDPCollector: сбор LLDP/CDP соседей |
| `collectors/inventory.py` | InventoryCollector: сбор инвентаризации |
| `collectors/device.py` | DeviceCollector: сбор show version |
| `core/domain/mac.py` | MACNormalizer: нормализация MAC-данных |
| `core/domain/interface.py` | InterfaceNormalizer: нормализация интерфейсов |
| `core/domain/lldp.py` | LLDPNormalizer: нормализация LLDP/CDP |
| `core/domain/inventory.py` | InventoryNormalizer: определение manufacturer |
| `config.yaml` | Настройки: max_workers, таймауты, фильтры |
