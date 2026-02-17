# План: добавление Cisco WLC и точек доступа (AP)

## Обзор

Добавить поддержку Cisco WLC (Wireless LAN Controller) на AireOS для:
1. **WLC как устройство** — сбор данных (модель, серийник, версия), синхронизация с NetBox
2. **Точки доступа (AP)** — сбор списка AP с WLC, создание каждой AP как отдельного устройства в NetBox

---

## Критическая проблема: SSH-подключение

### Проблема
Проект использует **Scrapli** для SSH. Scrapli **НЕ поддерживает** `cisco_wlc` без пакета `scrapli-community`.

WLC AireOS — это НЕ IOS:
- Другой промпт: `(Cisco Controller) >` вместо `Switch#`
- Нет стандартного enable mode
- Интерактивные подтверждения
- Пагинация отключается через `config paging disable`, а не `terminal length 0`

### Решение
**Netmiko** уже установлен в проекте (используется в `ConfigPusher`) и имеет готовый драйвер `cisco_wlc_ssh`, который корректно обрабатывает все особенности WLC.

**План:** Создать `NetmikoConnectionManager` — обёртку над Netmiko с тем же интерфейсом, что у `ConnectionManager` (Scrapli). Коллекторы WLC будут использовать Netmiko-менеджер.

---

## Этап 1: SSH через Netmiko (основа для WLC)

### 1.1 Создать `core/netmiko_connection.py`

Новый менеджер подключений для Netmiko:

```python
class NetmikoConnectionManager:
    """Менеджер SSH через Netmiko для платформ без поддержки Scrapli (WLC)."""

    def __init__(self, timeout=15, max_retries=2, retry_delay=5):
        ...

    @contextmanager
    def connect(self, device: Device, credentials: Credentials):
        """Контекстный менеджер — тот же интерфейс, что у ConnectionManager."""
        # Используем device.platform → NETMIKO_PLATFORM_MAP
        # Для WLC: "cisco_wlc" → "cisco_wlc_ssh"
        ...
        yield connection  # netmiko ConnectHandler

    def send_command(self, connection, command: str) -> str:
        """Выполняет команду, возвращает вывод."""
        return connection.send_command(command)

    @staticmethod
    def get_hostname(connection) -> str:
        """Извлекает hostname из промпта WLC."""
        # WLC prompt: "(WLC-Name) >" → "WLC-Name"
        prompt = connection.find_prompt()
        match = re.search(r'\((.+?)\)', prompt)
        return match.group(1) if match else "Unknown"
```

**Почему отдельный класс, а не расширение ConnectionManager:**
- ConnectionManager завязан на Scrapli API (`.open()`, `.get_prompt()`, `Response` objects)
- WLC имеет принципиально другое поведение
- Чистое разделение: Scrapli для IOS/NX-OS/EOS, Netmiko для WLC

### 1.2 Обновить `core/constants/platforms.py`

```python
# Добавить в NETMIKO_PLATFORM_MAP:
"cisco_wlc": "cisco_wlc_ssh",

# Добавить в NTC_PLATFORM_MAP:
"cisco_wlc": "cisco_wlc_ssh",

# Добавить в VENDOR_MAP → "cisco":
"cisco": [...existing..., "cisco_wlc"],

# Добавить в NETBOX_TO_SCRAPLI_PLATFORM (для обратного маппинга из NetBox):
"cisco-wlc": "cisco_wlc",
"cisco_wlc": "cisco_wlc",

# НЕ добавлять в SCRAPLI_PLATFORM_MAP (Scrapli не поддерживает WLC)

# Новая константа — список платформ, использующих Netmiko вместо Scrapli:
NETMIKO_ONLY_PLATFORMS = {"cisco_wlc"}
```

### 1.3 Обновить `core/constants/commands.py`

```python
# COLLECTOR_COMMANDS:
"devices": {
    ...,
    "cisco_wlc": "show sysinfo",  # НЕ "show version"!
},
"inventory": {
    ...,
    "cisco_wlc": "show inventory",
},

# Новая группа для AP:
"access_points": {
    "cisco_wlc": "show ap summary",
},
"access_points_detail": {
    "cisco_wlc": "show ap config general",  # serial, version, uptime
},

# SECONDARY_COMMANDS:
"cdp": {
    ...,
    "cisco_wlc": "show cdp neighbors detail",
},
"wlan": {
    "cisco_wlc": "show wlan summary",
},
```

---

## Этап 2: Коллектор WLC (само устройство)

### 2.1 Создать `collectors/wlc.py`

Новый коллектор для WLC-контроллера:

```python
class WLCCollector:
    """Коллектор информации о WLC-контроллере."""

    def __init__(self):
        self._conn_manager = NetmikoConnectionManager()
        self._parser = NTCParser()

    def collect(self, devices, credentials) -> List[DeviceInfo]:
        """Собирает данные WLC (show sysinfo + show inventory)."""
        ...

    def _collect_from_device(self, device, credentials) -> Optional[DeviceInfo]:
        with self._conn_manager.connect(device, credentials) as conn:
            hostname = self._conn_manager.get_hostname(conn)

            # show sysinfo → версия, имя, MAC, IP, uptime, макс AP
            sysinfo_output = conn.send_command("show sysinfo")
            sysinfo = self._parser.parse(sysinfo_output, "cisco_wlc_ssh", "show sysinfo")

            # show inventory → serial, PID (model), VID
            inv_output = conn.send_command("show inventory")
            inventory = self._parser.parse(inv_output, "cisco_wlc_ssh", "show inventory")

            return DeviceInfo(
                hostname=sysinfo[0].get("system_name", hostname),
                model=inventory[0].get("pid", "Unknown"),
                serial=inventory[0].get("sn", ""),
                version=sysinfo[0].get("product_version", ""),
                platform="cisco_wlc",
                vendor="cisco",
                site=device.site,
            )
```

**Поля из NTC шаблонов:**

| Команда | Поле шаблона | Куда маппим |
|---------|-------------|------------|
| `show sysinfo` | `SYSTEM_NAME` | hostname |
| `show sysinfo` | `PRODUCT_VERSION` | version |
| `show sysinfo` | `MAC_ADDRESS` | mac_address |
| `show sysinfo` | `MAXIMUM_APS` | custom_data |
| `show sysinfo` | `IP_ADDRESS` | ip_address |
| `show inventory` | `PID` | model (device_type) |
| `show inventory` | `SN` | serial |

### 2.2 Добавить в `devices_ips.py`

```python
devices_list = [
    ...,
    {
        "device_type": "cisco_wlc",
        "host": "192.168.x.x",
    },
]
```

### 2.3 Регистрация в CLI

В `cli/__init__.py` → `setup_parser()`:
- WLC не требует отдельной команды — команда `devices` уже работает
- Нужно добавить определение платформы `cisco_wlc` → использует `WLCCollector` вместо `DeviceCollector`

В `cli/commands/collect.py` (`cmd_devices`):
- Проверка: если устройство `cisco_wlc` → использовать `WLCCollector`
- Или: сделать `DeviceCollector` достаточно гибким для WLC (через маппинг полей)

**Рекомендация:** Расширить `DeviceCollector`, добавив маппинг полей per-platform:

```python
# В device.py — маппинг полей для разных платформ
PLATFORM_FIELD_MAP = {
    "default": {
        "hostname": ["hostname"],
        "hardware": ["hardware", "platform", "model"],
        "serial": ["serial", "serialnum"],
        "version": ["version", "os_version", "rommon"],
    },
    "cisco_wlc": {
        "hostname": ["system_name"],
        "hardware": ["pid"],
        "serial": ["sn"],
        "version": ["product_version"],
    },
}
```

И в `_collect_from_device()` — определять, какой connection manager использовать:

```python
if device.platform in NETMIKO_ONLY_PLATFORMS:
    conn_manager = self._netmiko_conn_manager
else:
    conn_manager = self._conn_manager  # Scrapli
```

---

## Этап 3: Коллектор точек доступа (AP)

### 3.1 Создать `collectors/access_points.py`

Это **новый тип коллектора** — собирает AP с WLC:

```python
class AccessPointCollector:
    """Собирает список точек доступа с WLC-контроллера."""

    def __init__(self):
        self._conn_manager = NetmikoConnectionManager()
        self._parser = NTCParser()

    def collect(self, devices, credentials) -> List[AccessPointInfo]:
        """
        Подключается к каждому WLC и собирает список AP.

        Args:
            devices: Список WLC-контроллеров (только cisco_wlc)
            credentials: Учётные данные

        Returns:
            Список AP со всех WLC
        """
        all_aps = []
        for device in devices:
            aps = self._collect_from_wlc(device, credentials)
            all_aps.extend(aps)
        return all_aps

    def _collect_from_wlc(self, device, credentials) -> List[AccessPointInfo]:
        with self._conn_manager.connect(device, credentials) as conn:
            wlc_name = self._conn_manager.get_hostname(conn)

            # show ap summary → список всех AP
            ap_output = conn.send_command("show ap summary")
            ap_list = self._parser.parse(ap_output, "cisco_wlc_ssh", "show ap summary")

            results = []
            for ap in ap_list:
                results.append(AccessPointInfo(
                    hostname=ap.get("ap_name", ""),
                    model=ap.get("ap_model", ""),
                    ip_address=ap.get("ip_address", ""),
                    mac_address=ap.get("mac_address", ""),
                    location=ap.get("location", ""),
                    state=ap.get("state", ""),
                    clients=int(ap.get("clients", 0)),
                    wlc_name=wlc_name,
                    wlc_ip=device.host,
                ))
            return results
```

**Поля из `show ap summary` (NTC шаблон):**

| Поле шаблона | Описание | Куда маппим |
|-------------|----------|------------|
| `AP_NAME` | Имя точки | hostname (имя устройства в NetBox) |
| `AP_MODEL` | Модель (AIR-AP2802I-R-K9) | device_type в NetBox |
| `MAC_ADDRESS` | MAC | идентификация |
| `IP_ADDRESS` | IP точки | primary_ip (опционально) |
| `LOCATION` | Описание расположения | location / comments |
| `CLIENTS` | Кол-во клиентов | custom field (опционально) |
| `STATE` | Registered / Not Joined | status в NetBox |

### 3.2 Создать модель `core/models.py` → `AccessPointInfo`

```python
@dataclass
class AccessPointInfo:
    """Информация о точке доступа."""
    hostname: str           # Имя AP
    model: str              # Модель (AIR-AP2802I-R-K9)
    ip_address: str = ""    # IP
    mac_address: str = ""   # MAC
    serial: str = ""        # Серийный номер (из show ap config general)
    location: str = ""      # Расположение
    state: str = ""         # Состояние (Registered, etc.)
    clients: int = 0        # Кол-во подключённых клиентов
    wlc_name: str = ""      # Имя WLC-контроллера
    wlc_ip: str = ""        # IP WLC
    vendor: str = "Cisco"   # Производитель
    site: str = ""          # Сайт для NetBox
```

### 3.3 Опционально: детальный сбор через `show ap config general`

`show ap summary` даёт базовую информацию. Для серийного номера и версии нужен `show ap config general <AP_NAME>` — **per-AP команда**.

**Варианты:**
1. **Без serial** — только `show ap summary` (быстро, одна команда на WLC)
2. **С serial** — `show ap config general <AP_NAME>` для каждой AP (медленно, N+1 команд)

**Рекомендация:** Начать с варианта 1. Добавить `--detail` флаг для варианта 2 позже.

Поля из `show ap config general`:
| Поле | Описание |
|------|----------|
| `SERIAL_NUMBER` | Серийный номер AP |
| `VERSION` | Версия прошивки |
| `UPTIME` | Аптайм |
| `PRIMARY_SWITCH_NAME` | Основной WLC |
| `PRIMARY_SWITCH_IP` | IP основного WLC |

---

## Этап 4: Синхронизация с NetBox

### 4.1 WLC → NetBox (через существующий sync)

WLC — это обычное устройство. Синхронизация через **существующий** `DevicesSyncMixin.sync_devices_from_inventory()`:

- `DeviceInfo` уже содержит всё необходимое (hostname, model, serial, vendor)
- `manufacturer` = "Cisco" (через `VENDOR_MAP`)
- `device_type` = PID из `show inventory` (например "AIR-CT5520-K9")
- `role` = "wlc" (новая роль, или "switch" по умолчанию)

**Что добавить:**
- В `fields.yaml` → `defaults` → добавить `wlc_role: "wlc"` (опционально)
- Роль "wlc" создастся автоматически через `get_or_create_device_role()`

### 4.2 AP → NetBox (новый sync mixin)

Создать `netbox/sync/access_points.py`:

```python
class AccessPointsSyncMixin:
    """Mixin для синхронизации точек доступа с NetBox."""

    def sync_access_points(
        self: SyncBase,
        access_points: List[AccessPointInfo],
        site: str = "Main",
        role: str = "access-point",
        manufacturer: str = "Cisco",
        dry_run: bool = False,
    ) -> Dict:
        """
        Синхронизирует AP с NetBox.

        Для каждой AP:
        1. Находит/создаёт manufacturer (Cisco)
        2. Находит/создаёт device_type (AIR-AP2802I-R-K9)
        3. Находит/создаёт site
        4. Находит/создаёт role (access-point)
        5. Ищет устройство по имени → создаёт или обновляет

        Returns:
            Dict: Статистика {created, updated, skipped, errors}
        """
        stats = {"created": 0, "updated": 0, "skipped": 0, "errors": 0}

        for ap in access_points:
            # Определяем site: из AP location, или default
            ap_site = ap.site or site

            # Ищем существующее устройство
            existing = self._find_device_by_name(ap.hostname)

            if existing:
                # Обновляем (если изменились model, serial, IP)
                self._update_ap_device(existing, ap)
                stats["updated"] += 1
            else:
                # Создаём
                self.create_device(
                    name=ap.hostname,
                    device_type=ap.model,
                    site=ap_site,
                    role=role,
                    manufacturer=manufacturer,
                    serial=ap.serial,
                    platform="cisco_wlc",  # или "cisco_ap" если нужно отличать
                )
                stats["created"] += 1

        return stats
```

### 4.3 Обновить `netbox/sync/__init__.py`

Добавить `AccessPointsSyncMixin` в цепочку наследования `NetBoxSync`:

```python
class NetBoxSync(
    SyncBase,
    DevicesSyncMixin,
    InterfacesSyncMixin,
    CablesSyncMixin,
    InventorySyncMixin,
    IPAddressesSyncMixin,
    VlansSyncMixin,
    AccessPointsSyncMixin,  # НОВЫЙ
):
    pass
```

---

## Этап 5: CLI интеграция

### 5.1 Новая CLI-команда: `access-points`

В `cli/__init__.py` → `setup_parser()`:

```python
# Подкоманда: access-points
ap_parser = subparsers.add_parser(
    "access-points",
    help="Сбор точек доступа с WLC",
)
ap_parser.add_argument("--format", choices=["table", "json", "csv", "excel"], default="table")
ap_parser.add_argument("--detail", action="store_true", help="Детальный сбор (serial, version)")
ap_parser.set_defaults(func=cmd_access_points)
```

### 5.2 Обработчик `cli/commands/collect.py` → `cmd_access_points()`

```python
def cmd_access_points(args, devices, credentials, context):
    """Сбор AP с WLC-контроллеров."""
    # Фильтруем только WLC-устройства
    wlc_devices = [d for d in devices if d.platform == "cisco_wlc"]
    if not wlc_devices:
        print("Нет WLC-устройств в devices_ips.py")
        return

    collector = AccessPointCollector()
    aps = collector.collect(wlc_devices, credentials)
    # Экспорт в table/json/csv/excel
    ...
```

### 5.3 Интеграция в `sync-netbox`

Добавить флаг `--access-points` в sync-netbox:

```python
# cli/__init__.py
sync_parser.add_argument(
    "--access-points", action="store_true",
    help="Синхронизация точек доступа с WLC в NetBox"
)

# cli/commands/sync.py → cmd_sync_netbox()
if getattr(args, "access_points", False) or sync_all:
    wlc_devices = [d for d in devices if d.platform == "cisco_wlc"]
    if wlc_devices:
        collector = AccessPointCollector()
        aps = collector.collect(wlc_devices, credentials)
        ap_stats = sync.sync_access_points(aps, site=default_site, dry_run=dry_run)
```

### 5.4 Интеграция в Pipeline

В `pipelines/default.yaml` (или отдельный pipeline):

```yaml
steps:
  - name: collect_access_points
    type: collect
    collector: access_points
    description: "Сбор точек доступа с WLC"

  - name: sync_access_points
    type: sync
    operation: access_points
    description: "Синхронизация AP с NetBox"
```

---

## Этап 6: Тестирование

### 6.1 Fixtures (примеры вывода)

Создать `tests/fixtures/cisco_wlc/`:

```
tests/fixtures/cisco_wlc/
├── show_sysinfo.txt              # Вывод show sysinfo
├── show_ap_summary.txt           # Вывод show ap summary (5-10 AP)
├── show_inventory.txt            # Вывод show inventory
├── show_ap_config_general.txt    # Вывод show ap config general <AP>
├── show_cdp_neighbors_detail.txt # CDP соседи
└── show_wlan_summary.txt         # WLAN список
```

**Важно:** Нужен реальный вывод с WLC для создания фикстур. Снять с прода:
```bash
ssh wlc
show sysinfo
show ap summary
show inventory
show ap config general <AP_NAME>
```

### 6.2 Тесты парсинга

`tests/test_wlc_templates.py`:

```python
class TestWLCParsing:
    def test_parse_sysinfo(self):
        """show sysinfo → hostname, version, MAC, max APs."""
        ...

    def test_parse_ap_summary(self):
        """show ap summary → список AP с именами, моделями, IP."""
        ...

    def test_parse_inventory(self):
        """show inventory → serial, PID."""
        ...
```

### 6.3 Тесты коллекторов

`tests/test_collectors/test_wlc_collector.py`:

```python
class TestWLCCollector:
    def test_collect_wlc_device_info(self):
        """WLC collector → DeviceInfo с правильными полями."""
        ...

class TestAccessPointCollector:
    def test_collect_ap_list(self):
        """AP collector → список AccessPointInfo."""
        ...

    def test_empty_ap_list(self):
        """WLC без AP → пустой список."""
        ...
```

### 6.4 Тесты синхронизации

`tests/test_netbox/test_access_points_sync.py`:

```python
class TestAccessPointsSync:
    def test_create_new_ap(self):
        """Новая AP → create_device с role=access-point."""
        ...

    def test_update_existing_ap(self):
        """Существующая AP → обновление serial/model."""
        ...

    def test_dry_run(self):
        """dry_run → no API calls, stats counted."""
        ...
```

### 6.5 Тест NetmikoConnectionManager

`tests/test_core/test_netmiko_connection.py`:

```python
class TestNetmikoConnectionManager:
    def test_wlc_hostname_extraction(self):
        """Промпт '(WLC-01) >' → hostname 'WLC-01'."""
        ...

    def test_connect_uses_cisco_wlc_ssh(self):
        """Platform cisco_wlc → netmiko device_type cisco_wlc_ssh."""
        ...
```

---

## Этап 7: Документация

### 7.1 Обновить `docs/MANUAL.md`
- Раздел «WLC и точки доступа»
- Примеры CLI-команд
- Формат вывода

### 7.2 Обновить `docs/PLATFORM_GUIDE.md`
- Добавить раздел «Cisco WLC (AireOS)»
- Описать отличия от IOS (промпт, команды, пагинация)
- Маппинг полей show sysinfo → DeviceInfo

### 7.3 Обновить `docs/ARCHITECTURE.md`
- Упомянуть NetmikoConnectionManager
- Описать поток данных для AP: WLC SSH → AP collector → NetBox sync

### 7.4 Добавить `docs/learning/16_WLC_ACCESS_POINTS.md`
- Обучающий гайд: WLC + AP, полная цепочка

---

## Порядок реализации (приоритеты)

| # | Задача | Зависимости | Сложность |
|---|--------|-------------|-----------|
| 1 | `core/netmiko_connection.py` — Netmiko connection manager | — | Низкая |
| 2 | `core/constants/platforms.py` — маппинги cisco_wlc | — | Низкая |
| 3 | `core/constants/commands.py` — команды WLC | — | Низкая |
| 4 | Снять вывод с реального WLC → fixtures | Доступ к WLC | — |
| 5 | `collectors/wlc.py` или расширение `device.py` — коллектор WLC | 1, 2, 3 | Средняя |
| 6 | Интеграция WLC в `sync-netbox --devices` | 5 | Низкая |
| 7 | `core/models.py` → `AccessPointInfo` | — | Низкая |
| 8 | `collectors/access_points.py` — коллектор AP | 1, 7 | Средняя |
| 9 | `netbox/sync/access_points.py` — sync AP → NetBox | 8 | Средняя |
| 10 | CLI: команда `access-points` + флаг `--access-points` в sync | 8, 9 | Низкая |
| 11 | Pipeline интеграция | 10 | Низкая |
| 12 | Тесты | 4, 5, 8, 9 | Средняя |
| 13 | Документация | 12 | Низкая |

**Общая оценка:** ~5-7 дней работы
- Этапы 1-3 (инфраструктура): 1 день
- Этап 4 (fixtures): зависит от доступа к WLC
- Этапы 5-6 (WLC коллектор + sync): 1-2 дня
- Этапы 7-10 (AP коллектор + sync + CLI): 2-3 дня
- Этапы 11-13 (pipeline, тесты, docs): 1-2 дня

---

## Что НЕ нужно менять

- `netbox/sync/interfaces.py` — AP не имеют управляемых интерфейсов
- `netbox/sync/cables.py` — AP подключены по Wi-Fi, не по кабелям
- `collectors/mac.py` — MAC клиентов на WLC это отдельная задача
- `collectors/lldp.py` — WLC CDP можно добавить позже
- `core/constants/interfaces.py` — WLC не имеет стандартных интерфейсов
- `core/constants/netbox.py` — нет маппинга типов портов для WLC

---

## Открытые вопросы (уточнить перед реализацией)

1. **Роль AP в NetBox** — "access-point" или "wireless-ap" или другое?
2. **Site для AP** — брать из `location` поля AP или из WLC?
3. **Platform AP** — отдельная "cisco_ap" или общая "cisco_wlc"?
4. **Серийники AP** — нужны ли сразу? (`show ap config general` — медленно, по одному)
5. **Обновление AP** — что обновлять при повторном sync? (IP, clients, state?)
6. **WLAN/SSID** — синхронизировать ли информацию о WLAN в NetBox?
7. **Удаление AP** — cleanup: удалять AP из NetBox если пропали с WLC?
