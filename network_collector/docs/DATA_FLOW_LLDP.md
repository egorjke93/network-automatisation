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
│      exporters/*.py           │ │            netbox/sync/*.py               │
│                               │ │                                           │
│  ExcelExporter.export()       │ │  NetBoxSync.sync_cables_from_lldp()       │
│  CSVExporter.export()         │ │       │ (cables.py mixin)                 │
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

**Файл:** `cli/commands/collect.py`

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

## Шаг 4b: Синхронизация с NetBox (Кабели)

### 4b.1 sync_cables_from_lldp() — Главный метод

**Файл:** `netbox/sync/cables.py`

Метод принимает LLDP/CDP данные и создаёт кабели в NetBox. В отличие от interfaces/inventory,
кабели создаются **поштучно** (не через batch API), потому что каждый кабель требует проверки
обоих интерфейсов.

```python
class CablesSyncMixin:
    def sync_cables_from_lldp(
        self: SyncBase,
        lldp_data: List[LLDPNeighbor],
        skip_unknown: bool = True,    # Пропускать соседей с типом "unknown"
        cleanup: bool = False,        # Удалять кабели которых нет в LLDP данных
    ) -> Dict[str, int]:
        """
        Создаёт кабели в NetBox на основе LLDP/CDP данных.

        Returns:
            Dict: {created, deleted, skipped, failed, already_exists, details}
        """
        stats = {"created": 0, "deleted": 0, "skipped": 0, "failed": 0, "already_exists": 0}
        details = {"create": [], "delete": []}

        # ══════════════════════════════════════════════════════════
        # 1. ДЕДУПЛИКАЦИЯ: LLDP видит кабель с обеих сторон
        #    switch1:Gi0/1 → switch2:Gi0/2  (запись от switch1)
        #    switch2:Gi0/2 → switch1:Gi0/1  (запись от switch2)
        #    Это ОДИН кабель, но два LLDP-записи. seen_cables это фильтрует.
        # ══════════════════════════════════════════════════════════
        seen_cables = set()

        neighbors = LLDPNeighbor.ensure_list(lldp_data)

        # Собираем множество устройств из LLDP данных (для cleanup)
        lldp_devices = set()
        for entry in neighbors:
            if entry.hostname:
                lldp_devices.add(entry.hostname)

        for entry in neighbors:
            local_device = entry.hostname
            local_intf = entry.local_interface
            remote_hostname = entry.remote_hostname
            remote_port = entry.remote_port
            neighbor_type = entry.neighbor_type or "unknown"

            # ══════════════════════════════════════════════════════════
            # 2. ПРОПУСК UNKNOWN: если skip_unknown=True, пропускаем
            #    соседей с типом "unknown" (нет ни hostname, ни MAC, ни IP)
            # ══════════════════════════════════════════════════════════
            if neighbor_type == "unknown" and skip_unknown:
                stats["skipped"] += 1
                continue

            # 3. Ищем ЛОКАЛЬНОЕ устройство и интерфейс
            local_device_obj = self._find_device(local_device)
            if not local_device_obj:
                stats["failed"] += 1
                continue

            local_intf_obj = self._find_interface(local_device_obj.id, local_intf)
            if not local_intf_obj:
                stats["failed"] += 1
                continue

            # 4. Ищем УДАЛЁННОЕ устройство (4 стратегии поиска)
            remote_device_obj = self._find_neighbor_device(entry)
            if not remote_device_obj:
                stats["skipped"] += 1
                continue

            # 5. Ищем УДАЛЁННЫЙ интерфейс
            remote_intf_obj = self._find_interface(remote_device_obj.id, remote_port)
            if not remote_intf_obj:
                stats["skipped"] += 1
                continue

            # ══════════════════════════════════════════════════════════
            # 6. LAG-ПРОПУСК: кабели на LAG интерфейсы не создаём.
            #    LLDP может показать LAG как сосед, но кабель
            #    должен быть на физическом интерфейсе.
            # ══════════════════════════════════════════════════════════
            local_intf_type = getattr(local_intf_obj.type, 'value', None) if local_intf_obj.type else None
            remote_intf_type = getattr(remote_intf_obj.type, 'value', None) if remote_intf_obj.type else None

            if local_intf_type == "lag":
                stats["skipped"] += 1
                continue
            if remote_intf_type == "lag":
                stats["skipped"] += 1
                continue

            # 7. Создаём КАБЕЛЬ
            result = self._create_cable(local_intf_obj, remote_intf_obj)

            if result == "created":
                a_name = local_device_obj.name
                b_name = remote_device_obj.name
                # Дедупликация: сортируем endpoints чтобы A↔B и B↔A = одинаковый ключ
                cable_key = tuple(sorted([f"{a_name}:{local_intf}", f"{b_name}:{remote_port}"]))
                if cable_key not in seen_cables:
                    seen_cables.add(cable_key)
                    stats["created"] += 1
                    details["create"].append({
                        "name": f"{a_name}:{local_intf} ↔ {b_name}:{remote_port}",
                        "a_device": a_name,
                        "a_interface": local_intf,
                        "b_device": b_name,
                        "b_interface": remote_port,
                    })
            elif result == "exists":
                stats["already_exists"] += 1
            else:
                stats["failed"] += 1

        # ══════════════════════════════════════════════════════════
        # 8. CLEANUP: удаление кабелей, которых нет в LLDP данных
        # ══════════════════════════════════════════════════════════
        if cleanup and lldp_devices:
            deleted_details = self._cleanup_cables(neighbors, lldp_devices)
            stats["deleted"] = len(deleted_details)
            details["delete"].extend(deleted_details)

        stats["details"] = details
        return stats
```

**Диаграмма решений для одного LLDP-соседа:**

```
LLDP запись: switch1:Gi0/1 → switch2:Gi0/2
    │
    ├─ neighbor_type == "unknown" && skip_unknown? → SKIP
    │
    ├─ Локальное устройство не найдено? → FAILED
    ├─ Локальный интерфейс не найден? → FAILED
    │
    ├─ Удалённое устройство не найдено? → SKIP
    ├─ Удалённый интерфейс не найден? → SKIP
    │
    ├─ Локальный тип == "lag"? → SKIP
    ├─ Удалённый тип == "lag"? → SKIP
    │
    ├─ interface_a.cable или interface_b.cable? → EXISTS
    │
    ├─ Дедупликация: cable_key уже в seen_cables? → (не считаем дважды)
    │
    └─ Всё ок → CREATE кабель
```

### 4b.2 _find_neighbor_device() — Поиск соседа (4 стратегии)

**Файл:** `netbox/sync/cables.py`

Ключевой метод — определяет как найти соседа в NetBox. В зависимости от `neighbor_type`
(определяется в Domain Layer нормализатором) применяется своя цепочка fallback.

```python
def _find_neighbor_device(
    self: SyncBase,
    entry: LLDPNeighbor,
) -> Optional[Any]:
    """Ищет устройство соседа в NetBox."""
    hostname = entry.remote_hostname or ""
    mac = entry.remote_mac
    ip = entry.remote_ip
    neighbor_type = entry.neighbor_type or "unknown"

    # ═══════════════════════════════════════════════════
    # СТРАТЕГИЯ 1: neighbor_type == "hostname"
    #   Приоритет: hostname → IP → MAC
    #   Самый надёжный тип — сосед передал своё имя.
    # ═══════════════════════════════════════════════════
    if neighbor_type == "hostname":
        # Убираем домен: switch1.corp.local → switch1
        clean_hostname = hostname.split(".")[0] if "." in hostname else hostname
        device = self._find_device(clean_hostname)
        if device:
            return device

        # Fallback: поиск по IP
        if ip:
            device = self.client.get_device_by_ip(ip)
            if device:
                return device

        # Fallback: поиск по MAC
        if mac:
            device = self._find_device_by_mac(mac)
            if device:
                return device

    # ═══════════════════════════════════════════════════
    # СТРАТЕГИЯ 2: neighbor_type == "mac"
    #   Приоритет: MAC → IP
    #   Сосед не передал hostname, но передал chassis_id (MAC).
    # ═══════════════════════════════════════════════════
    elif neighbor_type == "mac":
        if mac:
            device = self._find_device_by_mac(mac)
            if device:
                return device

        if ip:
            device = self.client.get_device_by_ip(ip)
            if device:
                return device

    # ═══════════════════════════════════════════════════
    # СТРАТЕГИЯ 3: neighbor_type == "ip"
    #   Приоритет: IP → MAC
    #   Сосед передал management IP.
    # ═══════════════════════════════════════════════════
    elif neighbor_type == "ip":
        if ip:
            device = self.client.get_device_by_ip(ip)
            if device:
                return device

        if mac:
            device = self._find_device_by_mac(mac)
            if device:
                return device

    # ═══════════════════════════════════════════════════
    # СТРАТЕГИЯ 4: unknown / другие типы
    #   Пробуем всё что есть: IP → MAC
    # ═══════════════════════════════════════════════════
    else:
        if ip:
            device = self.client.get_device_by_ip(ip)
            if device:
                return device
        if mac:
            device = self._find_device_by_mac(mac)
            if device:
                return device

    return None
```

**Таблица стратегий поиска:**

| neighbor_type | Источник | Цепочка поиска |
|---------------|----------|----------------|
| `hostname` | LLDP System Name / CDP Device ID | hostname → IP → MAC |
| `mac` | LLDP Chassis ID (MAC формат) | MAC → IP |
| `ip` | LLDP Management IP | IP → MAC |
| `unknown` | Нет данных для идентификации | IP → MAC |

### 4b.3 _create_cable() — Создание кабеля

**Файл:** `netbox/sync/cables.py`

Проверка существования кабеля выполняется через атрибут `interface.cable` (один атрибут
вместо отдельного API-запроса).

```python
def _create_cable(
    self: SyncBase,
    interface_a,
    interface_b,
) -> str:
    """
    Создаёт кабель между интерфейсами.

    Returns:
        str: "created", "exists", "error"
    """
    # ══════════════════════════════════════════════════════════
    # Проверка: если на ЛЮБОМ из интерфейсов уже есть кабель → exists.
    # Используем атрибут interface.cable (pynetbox), не отдельный запрос.
    # ══════════════════════════════════════════════════════════
    if interface_a.cable or interface_b.cable:
        return "exists"

    # Учёт create_only / update_only режимов
    if self.create_only is False and self.update_only:
        return "exists"

    # dry_run: только возвращаем "created", лог пишется в sync_cables_from_lldp
    if self.dry_run:
        return "created"

    # Реальное создание через NetBox API
    try:
        self.client.api.dcim.cables.create(
            {
                "a_terminations": [
                    {
                        "object_type": "dcim.interface",
                        "object_id": interface_a.id,
                    }
                ],
                "b_terminations": [
                    {
                        "object_type": "dcim.interface",
                        "object_id": interface_b.id,
                    }
                ],
                "status": "connected",
            }
        )
        return "created"
    except NetBoxError as e:
        logger.error(f"Ошибка NetBox при создании кабеля: {format_error_for_log(e)}")
        return "error"
    except Exception as e:
        logger.error(f"Неизвестная ошибка создания кабеля: {e}")
        return "error"
```

**Отличие от interfaces/inventory:**

| Аспект | Interfaces/Inventory | Cables |
|--------|---------------------|--------|
| API вызовы | Batch (bulk create/update/delete) | Поштучно |
| Сравнение | SyncComparator → SyncDiff | Проверка `interface.cable` |
| Cleanup | Batch delete по ID | Поштучное удаление |
| Причина | Множество полей, diff | Простая проверка наличия |

### 4b.4 _cleanup_cables() — Удаление устаревших кабелей

**Файл:** `netbox/sync/cables.py`

Cleanup удаляет кабели из NetBox, которых нет в LLDP данных. Ключевая защита: кабель удаляется
**только если ОБА устройства** на его концах присутствуют в LLDP-скане.

```python
def _cleanup_cables(
    self: SyncBase,
    lldp_neighbors: List[LLDPNeighbor],
    lldp_devices: set,
) -> List[Dict[str, Any]]:
    """Удаляет кабели из NetBox которых нет в LLDP данных."""
    deleted_details = []

    def normalize_hostname(name: str) -> str:
        """Убирает домен из hostname (switch2.mylab.local -> switch2)."""
        return name.split(".")[0] if "." in name else name

    # ══════════════════════════════════════════════════════════
    # 1. Строим set ВАЛИДНЫХ endpoints из LLDP данных.
    #    Endpoint = "device:interface" в сортированном порядке.
    #    Сортировка нужна чтобы A→B и B→A давали одинаковый ключ.
    # ══════════════════════════════════════════════════════════
    valid_endpoints = set()
    for entry in lldp_neighbors:
        if entry.hostname and entry.local_interface and entry.remote_hostname and entry.remote_port:
            endpoints = tuple(sorted([
                f"{normalize_hostname(entry.hostname)}:{entry.local_interface}",
                f"{normalize_hostname(entry.remote_hostname)}:{entry.remote_port}",
            ]))
            valid_endpoints.add(endpoints)

    # Нормализуем lldp_devices для проверки
    normalized_lldp_devices = {normalize_hostname(d) for d in lldp_devices}

    # ══════════════════════════════════════════════════════════
    # 2. Для каждого устройства из LLDP данных:
    #    получаем кабели из NetBox и проверяем каждый.
    # ══════════════════════════════════════════════════════════
    for device_name in lldp_devices:
        device = self._find_device(device_name)
        if not device:
            continue

        try:
            cables = self.client.get_cables(device_id=device.id)
        except Exception as e:
            logger.error(f"Ошибка получения кабелей для {device_name}: {e}")
            continue

        for cable in cables:
            cable_endpoints = get_cable_endpoints(cable)

            # Кабель не в LLDP данных?
            if cable_endpoints and cable_endpoints not in valid_endpoints:
                # ══════════════════════════════════════════════════
                # ЗАЩИТА: удаляем только если ОБА устройства
                # на концах кабеля есть в нашем LLDP-скане.
                # Это предотвращает удаление кабелей к устройствам
                # которые мы не сканировали.
                # ══════════════════════════════════════════════════
                endpoint_devices = set()
                for ep in cable_endpoints:
                    dev = ep.split(":")[0]
                    endpoint_devices.add(dev)

                if endpoint_devices.issubset(normalized_lldp_devices):
                    # Оба устройства в нашем скане → безопасно удалять
                    self._delete_cable(cable)
                    deleted_details.append({...})  # Детали для отчёта

    return deleted_details
```

**Логика защиты cleanup:**

```
Кабель в NetBox: switch1:Gi0/1 ↔ switch2:Gi0/2

Случай 1: switch1 и switch2 оба в LLDP-скане
  → Кабеля нет в valid_endpoints
  → ОБА устройства в lldp_devices → УДАЛЯЕМ

Случай 2: switch1 в скане, router1 НЕ в скане
  → Кабель switch1:Gi0/48 ↔ router1:Gi0/1
  → router1 NOT in lldp_devices → НЕ УДАЛЯЕМ
  → Мы не знаем актуальную топологию router1

Случай 3: Кабель switch1:Gi0/1 ↔ switch2:Gi0/2 ЕСТЬ в LLDP
  → Кабель в valid_endpoints → НЕ УДАЛЯЕМ (кабель актуален)
```

### 4b.5 Дедупликация seen_cables

LLDP работает двусторонне: если switch1 и switch2 соединены кабелем, LLDP-скан покажет:

```
От switch1: local=Gi0/1 → remote=switch2:Gi0/2
От switch2: local=Gi0/2 → remote=switch1:Gi0/1
```

Это **один и тот же кабель**. Без дедупликации мы бы:
1. Попытались создать его дважды (второй раз → "exists")
2. Считали бы `created: 2` вместо `created: 1` в dry_run

Решение — `seen_cables` set с сортированными ключами:

```python
# Оба варианта дают одинаковый ключ:
cable_key = tuple(sorted(["switch1:Gi0/1", "switch2:Gi0/2"]))
# → ("switch1:Gi0/1", "switch2:Gi0/2")

cable_key = tuple(sorted(["switch2:Gi0/2", "switch1:Gi0/1"]))
# → ("switch1:Gi0/1", "switch2:Gi0/2")  ← тот же ключ!
```

### 4b.6 get_cable_endpoints() — Domain Layer

**Файл:** `core/domain/sync.py`

Утилитная функция для извлечения endpoints кабеля в нормализованном виде.
Используется и в cleanup, и в логировании.

```python
def get_cable_endpoints(cable: Any) -> Optional[Tuple[str, str]]:
    """
    Извлекает endpoints кабеля как ("device:interface", "device:interface").
    Endpoints сортируются для единообразия (A↔B == B↔A).
    """
    a_terms = cable.a_terminations
    b_terms = cable.b_terminations

    if not a_terms or not b_terms:
        return None

    a_term = a_terms[0] if isinstance(a_terms, list) else a_terms
    b_term = b_terms[0] if isinstance(b_terms, list) else b_terms

    # Нормализуем hostname (убираем домен)
    a_device = a_term.device.name.split(".")[0]
    b_device = b_term.device.name.split(".")[0]

    a_endpoint = f"{a_device}:{a_term.name}"
    b_endpoint = f"{b_device}:{b_term.name}"

    return tuple(sorted([a_endpoint, b_endpoint]))
```

---

## Полная цепочка вызовов

```
cli/commands/collect.py: cmd_lldp()
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
    │                       │       └── {"remote_port": "Gi3/13", "neighbor_type": "hostname"}
    │                       │
    │                       └── merge_lldp_cdp()  ← если both
    │                               └── CDP база + LLDP MAC
    │
    ├── [Экспорт]
    │       └── ExcelExporter.export(data, "neighbors.xlsx")
    │
    └── [NetBox Sync]
            │
            └── NetBoxSync.sync_cables_from_lldp(lldp_data, skip_unknown, cleanup)
                    │
                    ├── for entry in lldp_data:
                    │   ├── skip_unknown check
                    │   ├── _find_device(local_device)
                    │   ├── _find_interface(device_id, local_intf)
                    │   ├── _find_neighbor_device(entry)  ← 4 стратегии
                    │   │       ├── hostname → _find_device(clean_hostname)
                    │   │       ├── fallback → get_device_by_ip(ip)
                    │   │       └── fallback → _find_device_by_mac(mac)
                    │   ├── _find_interface(neighbor_id, remote_port)
                    │   ├── LAG check (type == "lag" → skip)
                    │   ├── _create_cable(local_intf, remote_intf)
                    │   │       └── interface.cable check → exists / create
                    │   └── seen_cables дедупликация
                    │
                    └── cleanup? → _cleanup_cables(neighbors, lldp_devices)
                            ├── valid_endpoints из LLDP
                            ├── get_cables(device_id) из NetBox
                            ├── get_cable_endpoints(cable) → сравнение
                            ├── ЗАЩИТА: оба устройства в скане?
                            └── _delete_cable(cable)
```

---

## Ключевые файлы

| Файл | Роль |
|------|------|
| `cli/` | CLI модуль (модульная структура) |
| `cli/commands/collect.py` | cmd_lldp команда |
| `collectors/lldp.py` | Сбор и парсинг LLDP/CDP |
| `collectors/base.py` | Базовый класс, TextFSM парсинг |
| `parsers/textfsm_parser.py` | NTC Templates обёртка |
| `core/domain/lldp.py` | Нормализация, merge |
| `core/models.py` | Dataclass модели |
| `exporters/*.py` | Экспорт в файлы |
| `netbox/sync/*.py` | Синхронизация с NetBox (модули) |
| `netbox/client.py` | API клиент NetBox |
