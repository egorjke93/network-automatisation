# Поток данных LLDP/CDP: от устройства до NetBox

Детальное описание как данные проходят через все слои приложения.

## Общая схема

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              УСТРОЙСТВО                                      │
│                     show lldp neighbors detail                               │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │ сырой текст
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           1. COLLECTOR                                       │
│                        collectors/lldp.py                                    │
│                                                                              │
│  LLDPCollector._collect_from_device()                                       │
│       │                                                                      │
│       ├── _parse_output()                                                    │
│       │       │                                                              │
│       │       ├── _parse_with_textfsm()  ← ПРИОРИТЕТ (NTC Templates)        │
│       │       │                                                              │
│       │       └── _parse_lldp_regex()    ← FALLBACK (если TextFSM не смог)  │
│       │                                                                      │
│       └── возвращает: List[Dict] СЫРЫЕ данные                               │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │ {port_id, chassis_id, system_name, ...}
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           2. DOMAIN LAYER                                    │
│                        core/domain/lldp.py                                   │
│                                                                              │
│  LLDPNormalizer.normalize_dicts()                                           │
│       │                                                                      │
│       ├── _normalize_row()     ← маппинг ключей, логика remote_port         │
│       │                                                                      │
│       └── возвращает: List[Dict] НОРМАЛИЗОВАННЫЕ данные                     │
│                                                                              │
│  LLDPNormalizer.merge_lldp_cdp()  ← если protocol="both"                    │
│       │                                                                      │
│       └── CDP база + LLDP дополняет (MAC)                                   │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │ {remote_port, remote_mac, remote_hostname}
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           3. MODEL                                           │
│                        core/models.py                                        │
│                                                                              │
│  LLDPNeighbor.from_dict()      ← конвертация в типизированный объект        │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │ LLDPNeighbor(...)
                                  ▼
                    ┌─────────────┴─────────────┐
                    │                           │
                    ▼                           ▼
┌───────────────────────────────┐ ┌───────────────────────────────────────────┐
│        4a. EXPORTER           │ │              4b. NETBOX SYNC              │
│      exporters/*.py           │ │            netbox/sync.py                 │
│                               │ │                                           │
│  ExcelExporter.export()       │ │  NetBoxSync.sync_cables_from_lldp()       │
│  CSVExporter.export()         │ │       │                                   │
│  JSONExporter.export()        │ │       ├── _find_device()                  │
│                               │ │       ├── _find_interface()               │
│       │                       │ │       ├── _find_neighbor_device()         │
│       ▼                       │ │       └── _create_cable()                 │
│  Excel/CSV/JSON файл          │ │                                           │
└───────────────────────────────┘ └───────────────────────────────────────────┘
```

---

## Шаг 1: Сбор данных с устройства

### 1.1 Точка входа: CLI

**Файл:** `cli.py`

```python
# Команда: python -m network_collector lldp --protocol both --format excel

def cmd_lldp(args):
    # Создаём коллектор
    collector = LLDPCollector(
        protocol=args.protocol,      # "lldp", "cdp", "both"
        credentials=credentials,
        transport=args.transport,
    )

    # Собираем данные со всех устройств
    data = collector.collect(devices)  # → List[Dict]

    # Экспорт или синхронизация
    if args.format:
        exporter.export(data, filename)
```

### 1.2 Коллектор: LLDPCollector

**Файл:** `collectors/lldp.py`

```python
class LLDPCollector(BaseCollector):

    def __init__(self, protocol="lldp", **kwargs):
        super().__init__(**kwargs)
        self.protocol = protocol
        self._normalizer = LLDPNormalizer()  # Domain Layer

    def _collect_from_device(self, device: Device) -> List[Dict]:
        """Собирает данные с одного устройства."""

        # 1. Подключаемся к устройству
        with self._conn_manager.connect(device, self.credentials) as conn:
            hostname = self._conn_manager.get_hostname(conn)

            # 2. Выбираем режим сбора
            if self.protocol == "both":
                # Собираем оба протокола
                raw_data = self._collect_both_protocols(conn, device, hostname)
            else:
                # Один протокол
                command = self._get_command(device)  # "show lldp neighbors detail"
                response = conn.send_command(command)

                # 3. Парсим вывод
                raw_data = self._parse_output(response.result, device)

                # 4. Нормализуем через Domain Layer
                raw_data = self._normalizer.normalize_dicts(
                    raw_data,
                    protocol=self.protocol,
                    hostname=hostname,
                    device_ip=device.host,
                )

            return raw_data
```

### 1.3 Парсинг: TextFSM или Regex

**Файл:** `collectors/lldp.py`

```python
def _parse_output(self, output: str, device: Device) -> List[Dict]:
    """
    Парсит сырой вывод команды.

    Приоритет:
    1. TextFSM (NTC Templates) — если есть шаблон
    2. Regex — fallback
    """

    # ====== ПРИОРИТЕТ: TextFSM ======
    if self.use_ntc:  # True по умолчанию
        data = self._parse_with_textfsm(output, device)
        if data:  # Если шаблон вернул данные
            return data

    # ====== FALLBACK: Regex ======
    if self.protocol == "cdp":
        return self._parse_cdp_regex(output)
    else:
        return self._parse_lldp_regex(output)
```

### 1.4 TextFSM парсинг (NTC Templates)

**Файл:** `collectors/base.py` → `parsers/textfsm_parser.py`

```python
def _parse_with_textfsm(self, output: str, device: Device) -> List[Dict]:
    """Использует NTC Templates для парсинга."""

    # Получаем платформу для NTC
    ntc_platform = get_ntc_platform(device.platform)  # "cisco_ios"

    # Вызываем NTC parser
    return self._parser.parse(
        output=output,
        platform=ntc_platform,           # "cisco_ios"
        command="show lldp neighbors detail",
        fields=self.ntc_fields,
    )
```

**Файл:** `parsers/textfsm_parser.py`

```python
class NTCParser:
    def parse(self, output, platform, command, fields=None):
        """
        Парсит через ntc-templates.

        Шаблон выбирается автоматически:
        cisco_ios + show lldp neighbors detail
        → cisco_ios_show_lldp_neighbors_detail.textfsm
        """

        # ntc_templates.parse.parse_output — библиотечная функция
        parsed_data = parse_output(
            platform=platform,   # "cisco_ios"
            command=command,     # "show lldp neighbors detail"
            data=output          # сырой текст
        )

        # Результат: список словарей с полями из шаблона
        return parsed_data
```

**TextFSM шаблон** (из библиотеки ntc-templates):
```
# cisco_ios_show_lldp_neighbors_detail.textfsm

Value LOCAL_INTERFACE (\S+)
Value CHASSIS_ID (\S+)
Value NEIGHBOR_PORT_ID (.+)
Value NEIGHBOR (.+)
Value SYSTEM_DESCRIPTION (.+)
Value CAPABILITIES (.+)
Value MANAGEMENT_IP (\d+\.\d+\.\d+\.\d+)

Start
  ^Local Intf:\s+${LOCAL_INTERFACE}
  ^Chassis id:\s+${CHASSIS_ID}
  ^Port id:\s+${NEIGHBOR_PORT_ID}
  ^System Name:\s+${NEIGHBOR}
  ^System Description -> GetDescription
  ...
```

**Результат TextFSM:**
```python
[
    {
        "local_interface": "Gi1/0/49",
        "chassis_id": "001a.3008.6c00",
        "neighbor_port_id": "Gi3/13",
        "neighbor": "c6509-e.corp.ogk4.ru",
        "management_ip": "10.195.124.8",
    }
]
```

### 1.5 Regex парсинг (fallback)

**Файл:** `collectors/lldp.py`

```python
def _parse_lldp_regex(self, output: str) -> List[Dict]:
    """
    Парсит LLDP через regex.
    Используется если TextFSM не смог или нет шаблона.
    """
    neighbors = []

    # Паттерны
    local_intf_pattern = re.compile(r"Local Intf:\s*(\S+)")
    chassis_id_pattern = re.compile(r"Chassis id:\s*(\S+)")
    port_id_pattern = re.compile(r"Port id:\s*(.+?)(?:\n|$)")
    system_name_pattern = re.compile(r"System Name:\s*(.+?)(?:\n|$)")

    # Разбиваем на блоки по соседям
    blocks = re.split(r"(?=Local Intf:)", output)

    for block in blocks:
        neighbor = {}

        # Извлекаем поля
        match = local_intf_pattern.search(block)
        if match:
            neighbor["local_interface"] = match.group(1)

        match = chassis_id_pattern.search(block)
        if match:
            neighbor["chassis_id"] = match.group(1)

        match = port_id_pattern.search(block)
        if match:
            neighbor["port_id"] = match.group(1).strip()

        # ... остальные поля

        if neighbor:
            neighbors.append(neighbor)

    return neighbors
```

**Результат Regex:**
```python
[
    {
        "local_interface": "Gi1/0/49",
        "chassis_id": "001a.3008.6c00",
        "port_id": "Gi3/13",
        "port_description": "GigabitEthernet3/13",
        "remote_hostname": "c6509-e.corp.ogk4.ru",
        "remote_ip": "10.195.124.8",
    }
]
```

---

## Шаг 2: Нормализация (Domain Layer)

### 2.1 LLDPNormalizer.normalize_dicts()

**Файл:** `core/domain/lldp.py`

```python
class LLDPNormalizer:
    """
    Нормализует LLDP/CDP данные.

    Входные данные могут иметь разные имена полей:
    - TextFSM: neighbor_port_id, neighbor, chassis_id
    - Regex: port_id, remote_hostname, chassis_id

    Выходные данные — единый формат:
    - remote_port, remote_hostname, remote_mac
    """

    def normalize_dicts(
        self,
        data: List[Dict],
        protocol: str = "lldp",
        hostname: str = "",
        device_ip: str = "",
    ) -> List[Dict]:
        """Нормализует список записей."""

        result = []
        for row in data:
            # Нормализуем каждую запись
            normalized = self._normalize_row(row)

            # Добавляем метаданные
            normalized["hostname"] = hostname      # Наш хост
            normalized["device_ip"] = device_ip    # IP нашего хоста
            normalized["protocol"] = protocol.upper()

            result.append(normalized)

        return result
```

### 2.2 _normalize_row() — маппинг полей

**Файл:** `core/domain/lldp.py`

```python
# Маппинг ключей: сырое имя → нормализованное
KEY_MAPPING = {
    # Hostname соседа
    "neighbor": "remote_hostname",
    "system_name": "remote_hostname",
    "device_id": "remote_hostname",

    # MAC соседа
    "chassis_id": "remote_mac",

    # Порт соседа (neighbor_port_id маппится напрямую)
    "neighbor_port_id": "remote_port",

    # IP соседа
    "mgmt_ip": "remote_ip",
    "management_ip": "remote_ip",

    # Платформа
    "platform": "remote_platform",
}

def _normalize_row(self, row: Dict) -> Dict:
    """Нормализует одну запись."""

    result = {}
    port_id_value = None

    # 1. Маппинг ключей
    for key, value in row.items():
        key_lower = key.lower()

        # port_id обрабатываем отдельно (сложная логика)
        if key_lower == "port_id":
            port_id_value = value
            continue

        # Применяем маппинг
        new_key = KEY_MAPPING.get(key_lower, key_lower)
        result[new_key] = value

    # 2. Определяем remote_port (сложная логика)
    if not result.get("remote_port"):
        port_desc = result.get("port_description", "")

        if port_id_value:
            port_id_str = str(port_id_value).strip()

            # Если port_id — интерфейс (Te1/0/2, Gi0/1)
            if self._is_interface_name(port_id_str):
                result["remote_port"] = port_id_str

            # Если port_id — MAC адрес
            elif self.is_mac_address(port_id_str):
                result["remote_mac"] = port_id_str
                # Используем port_description для remote_port
                if port_desc:
                    result["remote_port"] = port_desc

            # port_id не интерфейс и не MAC
            else:
                # Если port_description — интерфейс, используем его
                if port_desc and self._is_interface_name(port_desc):
                    result["remote_port"] = port_desc
                else:
                    result["remote_port"] = port_id_str

        elif port_desc:
            result["remote_port"] = port_desc

    # 3. Определяем neighbor_type
    result["neighbor_type"] = self.determine_neighbor_type(result)

    # 4. Fallback для hostname
    if not result.get("remote_hostname"):
        if result.get("remote_mac"):
            result["remote_hostname"] = f"[MAC:{result['remote_mac']}]"
        elif result.get("remote_ip"):
            result["remote_hostname"] = f"[IP:{result['remote_ip']}]"
        else:
            result["remote_hostname"] = "[unknown]"

    return result
```

**Пример трансформации:**

```python
# ВХОД (из TextFSM или Regex)
{
    "local_interface": "Gi1/0/49",
    "chassis_id": "001a.3008.6c00",
    "port_id": "Gi3/13",
    "port_description": "GigabitEthernet3/13",
    "system_name": "c6509-e.corp.ogk4.ru",
    "management_ip": "10.195.124.8",
}

# ВЫХОД (нормализованный)
{
    "local_interface": "Gi1/0/49",
    "remote_mac": "001a.3008.6c00",       # из chassis_id
    "remote_port": "Gi3/13",               # из port_id (это интерфейс)
    "port_description": "GigabitEthernet3/13",
    "remote_hostname": "c6509-e.corp.ogk4.ru",  # из system_name
    "remote_ip": "10.195.124.8",           # из management_ip
    "neighbor_type": "hostname",
    "hostname": "our-switch",              # наш хост
    "device_ip": "10.0.0.1",               # IP нашего хоста
    "protocol": "LLDP",
}
```

### 2.3 merge_lldp_cdp() — объединение протоколов

**Файл:** `core/domain/lldp.py`

```python
def merge_lldp_cdp(
    self,
    lldp_data: List[Dict],
    cdp_data: List[Dict],
) -> List[Dict]:
    """
    Объединяет LLDP и CDP данные.

    CDP имеет ПРИОРИТЕТ (Cisco проприетарный, надёжнее):
    - local_interface
    - remote_port
    - remote_hostname
    - remote_platform
    - remote_ip

    LLDP ДОПОЛНЯЕТ:
    - remote_mac (chassis_id)
    """

    if not lldp_data:
        return cdp_data
    if not cdp_data:
        return lldp_data

    # Индекс LLDP по local_interface
    lldp_by_interface = {}
    for lldp_row in lldp_data:
        local_intf = normalize_interface_short(
            lldp_row.get("local_interface", "")
        )
        if local_intf:
            lldp_by_interface[local_intf] = lldp_row

    merged = []
    used_lldp_interfaces = set()

    # CDP как БАЗА
    for cdp_row in cdp_data:
        local_intf = normalize_interface_short(
            cdp_row.get("local_interface", "")
        )
        lldp_row = lldp_by_interface.get(local_intf)

        if lldp_row:
            # CDP + LLDP → объединяем
            result = self._merge_cdp_with_lldp(cdp_row, lldp_row)
            used_lldp_interfaces.add(local_intf)
        else:
            # Только CDP
            result = dict(cdp_row)

        result["protocol"] = "BOTH"
        merged.append(result)

    # Добавляем LLDP соседей без CDP (не-Cisco устройства)
    for lldp_row in lldp_data:
        local_intf = normalize_interface_short(
            lldp_row.get("local_interface", "")
        )
        if local_intf not in used_lldp_interfaces:
            lldp_row = dict(lldp_row)
            lldp_row["protocol"] = "BOTH"
            merged.append(lldp_row)

    return merged

def _merge_cdp_with_lldp(self, cdp_row: Dict, lldp_row: Dict) -> Dict:
    """CDP база, LLDP дополняет."""

    # CDP как база
    result = dict(cdp_row)

    # LLDP дополняет MAC
    if not result.get("remote_mac") and lldp_row.get("remote_mac"):
        result["remote_mac"] = lldp_row["remote_mac"]

    # LLDP дополняет capabilities
    if not result.get("capabilities") and lldp_row.get("capabilities"):
        result["capabilities"] = lldp_row["capabilities"]

    return result
```

**Пример merge:**

```python
# LLDP данные
lldp_data = [{
    "local_interface": "Gi1/0/49",
    "remote_mac": "001a.3008.6c00",      # ← LLDP даёт MAC
    "remote_hostname": "[MAC:001a.3008.6c00]",  # fallback
    "protocol": "LLDP",
}]

# CDP данные
cdp_data = [{
    "local_interface": "GigabitEthernet1/0/49",
    "remote_hostname": "c6509-e.corp.ogk4.ru",  # ← CDP даёт hostname
    "remote_port": "Gi3/13",                     # ← CDP даёт port
    "remote_platform": "cisco WS-C6509-E",       # ← CDP даёт platform
    "remote_ip": "10.195.124.8",                 # ← CDP даёт IP
    "protocol": "CDP",
}]

# РЕЗУЛЬТАТ merge
merged = [{
    "local_interface": "GigabitEthernet1/0/49",  # из CDP
    "remote_hostname": "c6509-e.corp.ogk4.ru",   # из CDP
    "remote_port": "Gi3/13",                      # из CDP
    "remote_platform": "cisco WS-C6509-E",        # из CDP
    "remote_ip": "10.195.124.8",                  # из CDP
    "remote_mac": "001a.3008.6c00",               # из LLDP ← дополнение!
    "protocol": "BOTH",
}]
```

---

## Шаг 3: Модель (опционально)

### 3.1 LLDPNeighbor dataclass

**Файл:** `core/models.py`

```python
@dataclass
class LLDPNeighbor:
    """Модель LLDP/CDP соседа."""

    hostname: str = ""           # Наш хост
    device_ip: str = ""          # IP нашего хоста
    local_interface: str = ""    # Наш интерфейс
    remote_hostname: str = ""    # Имя соседа
    remote_port: str = ""        # Порт соседа
    remote_mac: str = ""         # MAC соседа
    remote_ip: str = ""          # IP соседа
    remote_platform: str = ""    # Платформа соседа
    neighbor_type: str = ""      # hostname/mac/ip/unknown
    protocol: str = ""           # LLDP/CDP/BOTH
    capabilities: str = ""       # Router, Switch, etc.

    @classmethod
    def from_dict(cls, data: Dict) -> "LLDPNeighbor":
        """Создаёт объект из словаря."""
        return cls(
            hostname=data.get("hostname", ""),
            device_ip=data.get("device_ip", ""),
            local_interface=data.get("local_interface", ""),
            remote_hostname=data.get("remote_hostname", ""),
            remote_port=data.get("remote_port", ""),
            remote_mac=data.get("remote_mac", ""),
            remote_ip=data.get("remote_ip", ""),
            remote_platform=data.get("remote_platform", ""),
            neighbor_type=data.get("neighbor_type", ""),
            protocol=data.get("protocol", ""),
            capabilities=data.get("capabilities", ""),
        )

    def to_dict(self) -> Dict:
        """Конвертирует в словарь."""
        return {
            "hostname": self.hostname,
            "device_ip": self.device_ip,
            "local_interface": self.local_interface,
            "remote_hostname": self.remote_hostname,
            "remote_port": self.remote_port,
            "remote_mac": self.remote_mac,
            "remote_ip": self.remote_ip,
            "remote_platform": self.remote_platform,
            "neighbor_type": self.neighbor_type,
            "protocol": self.protocol,
            "capabilities": self.capabilities,
        }
```

---

## Шаг 4a: Экспорт

### 4a.1 ExcelExporter

**Файл:** `exporters/excel_exporter.py`

```python
class ExcelExporter:
    def export(self, data: List[Dict], filename: str, fields_config: Dict):
        """
        Экспортирует данные в Excel.

        Args:
            data: Нормализованные данные из collector
            filename: Путь к файлу
            fields_config: Конфиг из fields.yaml (какие колонки выводить)
        """

        # Получаем включённые поля из fields.yaml
        enabled_fields = [
            f["name"] for f in fields_config.get("fields", [])
            if f.get("enabled", True)
        ]

        # Создаём DataFrame
        df = pd.DataFrame(data)

        # Фильтруем колонки
        df = df[[col for col in enabled_fields if col in df.columns]]

        # Переименовываем колонки (name → title)
        column_titles = {
            f["name"]: f.get("title", f["name"])
            for f in fields_config.get("fields", [])
        }
        df = df.rename(columns=column_titles)

        # Сохраняем
        df.to_excel(filename, index=False)
```

**fields.yaml:**
```yaml
lldp:
  fields:
    - name: hostname
      title: Device
      enabled: true
    - name: local_interface
      title: Local Port
      enabled: true
    - name: remote_hostname
      title: Neighbor
      enabled: true
    - name: remote_port
      title: Neighbor Port
      enabled: true
    - name: remote_mac
      title: Neighbor MAC
      enabled: true
    - name: protocol
      title: Protocol
      enabled: true
```

---

## Шаг 4b: Синхронизация с NetBox

### 4b.1 sync_cables_from_lldp()

**Файл:** `netbox/sync.py`

```python
class NetBoxSync:
    def sync_cables_from_lldp(
        self,
        lldp_data: List[LLDPNeighbor],
        skip_unknown: bool = True,
    ) -> Dict[str, int]:
        """
        Создаёт кабели в NetBox на основе LLDP/CDP данных.

        Для каждого соседа:
        1. Находим локальное устройство и интерфейс
        2. Находим удалённое устройство (по hostname/MAC/IP)
        3. Находим удалённый интерфейс
        4. Создаём кабель
        """

        stats = {"created": 0, "skipped": 0, "failed": 0}

        for entry in lldp_data:
            # 1. Ищем ЛОКАЛЬНОЕ устройство
            local_device = self._find_device(entry.hostname)
            if not local_device:
                logger.warning(f"Устройство не найдено: {entry.hostname}")
                stats["failed"] += 1
                continue

            # 2. Ищем ЛОКАЛЬНЫЙ интерфейс
            local_intf = self._find_interface(
                local_device.id,
                entry.local_interface
            )
            if not local_intf:
                logger.warning(
                    f"Интерфейс не найден: {entry.hostname}:{entry.local_interface}"
                )
                stats["failed"] += 1
                continue

            # 3. Ищем УДАЛЁННОЕ устройство
            remote_device = self._find_neighbor_device(entry)
            if not remote_device:
                logger.warning(f"Сосед не найден: {entry.remote_hostname}")
                stats["skipped"] += 1
                continue

            # 4. Ищем УДАЛЁННЫЙ интерфейс
            remote_intf = self._find_interface(
                remote_device.id,
                entry.remote_port
            )
            if not remote_intf:
                logger.warning(
                    f"Интерфейс соседа не найден: "
                    f"{remote_device.name}:{entry.remote_port}"
                )
                stats["skipped"] += 1
                continue

            # 5. Создаём КАБЕЛЬ
            result = self._create_cable(local_intf, remote_intf)

            if result == "created":
                stats["created"] += 1
            elif result == "exists":
                stats["already_exists"] += 1
            else:
                stats["failed"] += 1

        return stats
```

### 4b.2 _find_neighbor_device() — поиск соседа

**Файл:** `netbox/sync.py`

```python
def _find_neighbor_device(self, entry: LLDPNeighbor):
    """
    Ищет устройство-сосед в NetBox.

    Порядок поиска:
    1. По hostname (если neighbor_type == "hostname")
    2. По MAC адресу (если neighbor_type == "mac")
    3. По IP адресу (если neighbor_type == "ip")
    """

    neighbor_type = entry.neighbor_type

    # 1. Поиск по hostname
    if neighbor_type == "hostname":
        hostname = entry.remote_hostname
        # Убираем домен: switch1.corp.local → switch1
        short_name = hostname.split(".")[0]

        device = self.client.get_device_by_name(short_name)
        if device:
            return device

        # Пробуем полное имя
        device = self.client.get_device_by_name(hostname)
        if device:
            return device

    # 2. Поиск по MAC
    if neighbor_type == "mac" or entry.remote_mac:
        mac = entry.remote_mac
        device = self.client.get_device_by_mac(mac)
        if device:
            return device

    # 3. Поиск по IP
    if neighbor_type == "ip" or entry.remote_ip:
        ip = entry.remote_ip
        device = self.client.get_device_by_ip(ip)
        if device:
            return device

    return None
```

### 4b.3 _create_cable() — создание кабеля

**Файл:** `netbox/sync.py`

```python
def _create_cable(self, interface_a, interface_b):
    """
    Создаёт кабель между двумя интерфейсами.

    Args:
        interface_a: Локальный интерфейс (объект NetBox)
        interface_b: Удалённый интерфейс (объект NetBox)

    Returns:
        str: "created", "exists", или "failed"
    """

    # Проверяем нет ли уже кабеля
    existing = self.client.get_cable_by_interfaces(
        interface_a.id,
        interface_b.id
    )
    if existing:
        return "exists"

    # Создаём кабель
    if self.dry_run:
        logger.info(
            f"[DRY-RUN] Создание кабеля: "
            f"{interface_a.device.name}:{interface_a.name} ↔ "
            f"{interface_b.device.name}:{interface_b.name}"
        )
        return "created"

    try:
        self.client.create_cable(
            a_terminations=[{
                "object_type": "dcim.interface",
                "object_id": interface_a.id,
            }],
            b_terminations=[{
                "object_type": "dcim.interface",
                "object_id": interface_b.id,
            }],
        )
        logger.info(
            f"Создан кабель: "
            f"{interface_a.device.name}:{interface_a.name} ↔ "
            f"{interface_b.device.name}:{interface_b.name}"
        )
        return "created"
    except Exception as e:
        logger.error(f"Ошибка создания кабеля: {e}")
        return "failed"
```

---

## Полная цепочка вызовов

```
cli.py: cmd_lldp()
    │
    ├── LLDPCollector(protocol="both")
    │       │
    │       └── _collect_from_device(device)
    │               │
    │               ├── conn.send_command("show lldp neighbors detail")
    │               │       └── сырой текст
    │               │
    │               ├── _parse_output()
    │               │       │
    │               │       ├── _parse_with_textfsm()  ← NTC Templates
    │               │       │       └── [{"neighbor_port_id": "Gi3/13", ...}]
    │               │       │
    │               │       └── _parse_lldp_regex()    ← fallback
    │               │               └── [{"port_id": "Gi3/13", ...}]
    │               │
    │               └── LLDPNormalizer.normalize_dicts()
    │                       │
    │                       ├── _normalize_row()
    │                       │       └── {"remote_port": "Gi3/13", ...}
    │                       │
    │                       └── merge_lldp_cdp()  ← если both
    │                               └── CDP база + LLDP MAC
    │
    ├── [Экспорт]
    │       │
    │       └── ExcelExporter.export(data, "neighbors.xlsx")
    │               └── DataFrame → Excel
    │
    └── [NetBox Sync]
            │
            └── NetBoxSync.sync_cables_from_lldp(data)
                    │
                    ├── _find_device("switch1")
                    ├── _find_interface(device_id, "Gi1/0/49")
                    ├── _find_neighbor_device(entry)
                    ├── _find_interface(neighbor_id, "Gi3/13")
                    └── _create_cable(local_intf, remote_intf)
```

---

## Ключевые файлы

| Файл | Роль |
|------|------|
| `cli.py` | Точка входа, команды CLI |
| `collectors/lldp.py` | Сбор и парсинг LLDP/CDP |
| `collectors/base.py` | Базовый класс, TextFSM парсинг |
| `parsers/textfsm_parser.py` | NTC Templates обёртка |
| `core/domain/lldp.py` | Нормализация, merge |
| `core/models.py` | Dataclass модели |
| `exporters/*.py` | Экспорт в файлы |
| `netbox/sync.py` | Синхронизация с NetBox |
| `netbox/client.py` | API клиент NetBox |
