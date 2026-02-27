# 20. MAC-таблица, матчинг с GLPI, push описаний

Одна из ключевых задач сетевого инженера — понять, какое устройство подключено к какому порту коммутатора. Network Collector автоматизирует полную цепочку: сбор MAC-таблицы → сопоставление с базой GLPI → автоматическая установка описаний на портах.

В этом документе разберём **три команды** и **всю цепочку** от SSH до конфигурации устройства.

**Предварительное чтение:** [04_DATA_COLLECTION.md](04_DATA_COLLECTION.md), [10_COLLECTORS_DEEP_DIVE.md](10_COLLECTORS_DEEP_DIVE.md)

**Время:** ~45 мин

---

## Содержание

1. [Общая схема: три шага](#1-общая-схема-три-шага)
2. [Шаг 1: Сбор MAC-таблицы](#2-шаг-1-сбор-mac-таблицы)
3. [Команды по платформам](#3-команды-по-платформам)
4. [Парсинг и нормализация MAC](#4-парсинг-и-нормализация-mac)
5. [Фильтрация: VLAN, интерфейсы, trunk](#5-фильтрация-vlan-интерфейсы-trunk)
6. [Port-security: sticky MAC (offline устройства)](#6-port-security-sticky-mac-offline-устройства)
7. [Шаг 2: Матчинг с GLPI (match-mac)](#7-шаг-2-матчинг-с-glpi-match-mac)
8. [Шаг 3: Push описаний (push-descriptions)](#8-шаг-3-push-описаний-push-descriptions)
9. [Добавление новой платформы](#9-добавление-новой-платформы)
10. [Тестирование](#10-тестирование)
11. [Что можно доработать](#11-что-можно-доработать)
12. [Полная диаграмма потока данных](#12-полная-диаграмма-потока-данных)

---

## 1. Общая схема: три шага

```
Шаг 1: MAC                Шаг 2: Match              Шаг 3: Push
┌─────────────────┐       ┌──────────────────┐       ┌─────────────────┐
│ python -m nc    │       │ python -m nc     │       │ python -m nc    │
│ mac --format    │       │ match-mac        │       │ push-descriptions│
│ excel           │       │ --mac-file X     │       │ --matched-file Y │
│                 │       │ --hosts-file G   │       │ --apply          │
│ SSH → parse →   │  .xlsx│ MAC ↔ GLPI →     │  .xlsx│ → SSH → config  │
│ normalize →     ├──────►│ matched_data     ├──────►│ → description   │
│ mac_data.xlsx   │       │                  │       │                 │
└─────────────────┘       └──────────────────┘       └─────────────────┘
```

**Три файла в цепочке:**

| Файл | Создаётся | Содержит |
|------|-----------|----------|
| `mac_data.xlsx` | Шаг 1 (mac) | MAC-таблица: устройство, порт, MAC, VLAN, статус |
| `glpi_hosts.xlsx` | Вручную (экспорт из GLPI) | Справочник: MAC → имя ПК |
| `matched_data.xlsx` | Шаг 2 (match-mac) | Результат: порт + MAC + имя ПК + Matched |

---

## 2. Шаг 1: Сбор MAC-таблицы

### CLI команда

```bash
python -m network_collector mac --format excel -o mac_data.xlsx
```

### Что происходит внутри

```python
class MACCollector(BaseCollector):
    """Коллектор MAC-адресов."""
    model_class = MACEntry
    platform_commands = COLLECTOR_COMMANDS["mac"]  # Команды по платформам
```

`MACCollector` наследует `BaseCollector` и переопределяет `_collect_from_device()`.

### Для каждого устройства выполняются 4 SSH-команды

```
1. show mac address-table        → MAC-таблица (основные данные)
2. show interfaces status        → Статус портов (online/offline)
3. show interfaces description   → Текущие описания (опционально)
4. show interfaces trunk         → Список trunk-портов (для фильтрации)
```

Если включён `--with-port-security`, добавляется:
```
5. show running-config           → Sticky MAC из port-security
```

### Результат: MACEntry

```python
@dataclass
class MACEntry:
    mac: str              # "aa:bb:cc:dd:ee:ff" (формат из --mac-format)
    interface: str        # "Gi0/1"
    vlan: str = ""        # "100"
    mac_type: str = "dynamic"  # "dynamic", "static", "sticky"
    hostname: str = ""    # "switch-core-01"
    device_ip: str = ""   # "10.0.0.1"
    vendor: str = ""      # OUI vendor (не используется)
```

Дополнительные поля добавляются при нормализации:
- `status` — "online" / "offline" / "unknown"
- `description` — текущее описание порта (если `--with-descriptions`)

---

## 3. Команды по платформам

**Файл:** `core/constants/commands.py`

```python
COLLECTOR_COMMANDS["mac"] = {
    "cisco_ios":     "show mac address-table",
    "cisco_iosxe":   "show mac address-table",
    "cisco_nxos":    "show mac address-table",
    "arista_eos":    "show mac address-table",
    "juniper_junos": "show ethernet-switching table",
    "juniper":       "show ethernet-switching table",
    "qtech":         "show mac address-table",
    "qtech_qsw":    "show mac address-table",
}
```

**Ключевое:** Juniper использует другую команду (`show ethernet-switching table`) и другой формат вывода. Все остальные платформы — одна команда, но разные форматы вывода.

### Какой шаблон парсит вывод

| Платформа | TextFSM шаблон | Источник |
|-----------|----------------|----------|
| cisco_ios / iosxe | `cisco_ios_show_mac_address_table` | NTC Templates (встроенный) |
| cisco_nxos | `cisco_nxos_show_mac_address_table` | NTC Templates (встроенный) |
| arista_eos | `arista_eos_show_mac_address_table` | NTC Templates (встроенный) |
| juniper_junos | `juniper_junos_show_ethernet_switching_table` | NTC Templates (встроенный) |
| qtech | `qtech_show_mac_address_table.textfsm` | **Кастомный** (templates/) |

**Приоритет выбора шаблона:**

```
1. CUSTOM_TEXTFSM_TEMPLATES[(platform, command)]  ← кастомный шаблон
2. NTC Templates (ntc_templates.parse.parse_output)  ← встроенный
3. Fallback regex парсинг (если NTC не знает команду)
```

---

## 4. Парсинг и нормализация MAC

### MACNormalizer — центр обработки

**Файл:** `core/domain/mac.py`

```python
class MACNormalizer:
    def __init__(self, mac_format="ieee", normalize_interfaces=True,
                 exclude_interfaces=None, exclude_vlans=None):
        ...

    def normalize_dicts(self, data, interface_status=None,
                        hostname="", device_ip=""):
        """Нормализует список dict-записей MAC."""
        for row in data:
            normalized = self._normalize_row(row, interface_status)
            if normalized:
                results.append(normalized)
        return self.deduplicate(results)
```

### Что делает _normalize_row

Для каждой строки из TextFSM-парсинга:

```python
def _normalize_row(self, row, interface_status):
    # 1. Извлекаем поля (с алиасами для разных вендоров)
    mac = row.get("mac") or row.get("destination_address", "")
    interface = row.get("interface") or row.get("destination_port", "")
    vlan = row.get("vlan") or row.get("vlan_id", "")

    # 2. Нормализуем интерфейс: GigabitEthernet0/1 → Gi0/1
    interface = normalize_interface_short(interface)

    # 3. Проверяем exclude_interfaces (regex)
    if self._should_exclude_interface(interface):
        return None  # пропускаем

    # 4. Проверяем exclude_vlans
    if int(vlan) in self.exclude_vlans:
        return None

    # 5. Нормализуем формат MAC
    mac = normalize_mac(mac, format=self.mac_format)

    # 6. Определяем статус порта
    status = self._get_port_status(interface, interface_status)

    return {mac, interface, vlan, mac_type, status, hostname, device_ip}
```

### Форматы MAC

```python
normalize_mac("aabb.ccdd.eeff", "ieee")   → "aa:bb:cc:dd:ee:ff"
normalize_mac("aabb.ccdd.eeff", "cisco")  → "aabb.ccdd.eeff"
normalize_mac("aabb.ccdd.eeff", "netbox") → "AA:BB:CC:DD:EE:FF"
normalize_mac("aabb.ccdd.eeff", "raw")    → "aabbccddeeff"
```

### Определение online/offline

```python
ONLINE_PORT_STATUSES = ["connected", "connect", "up"]
OFFLINE_PORT_STATUSES = ["notconnect", "notconnected", "down", "disabled"]
```

Статус берётся из `show interfaces status` → маппится через алиасы интерфейсов:
```
GigabitEthernet0/1 → connected → "online"
Gi0/1              → notconnect → "offline"
```

---

## 5. Фильтрация: VLAN, интерфейсы, trunk

### 5.1 Исключение VLAN

```yaml
# config.yaml
filters:
  exclude_vlans: [1, 4094]  # Не собирать MAC из этих VLAN
```

### 5.2 Исключение интерфейсов (regex)

```yaml
# config.yaml
filters:
  exclude_interfaces:
    - "^Vlan\\d+"        # Виртуальные VLAN-интерфейсы
    - "^Loopback\\d+"    # Loopback
    - "^Port-channel\\d+" # LAG (агрегированные)
    - "^Po\\d+"          # Короткий формат LAG
    - "^CPU$"            # CPU
```

Каждый паттерн — это regex. Если имя интерфейса совпадает с любым паттерном, MAC-запись исключается.

### 5.3 Фильтрация trunk-портов

По умолчанию trunk-порты **исключаются** (на trunk обычно десятки MAC из разных VLAN — шум).

```bash
# Включить trunk-порты в результат
python -m network_collector mac --include-trunk
```

Trunk определяется из `show interfaces trunk` → набор trunk-интерфейсов.

### 5.4 Дедупликация

Одинаковые записи (hostname + mac + vlan + interface) объединяются:

```python
def deduplicate(self, data):
    seen = set()
    for row in data:
        key = (row["hostname"], normalize_mac_raw(row["mac"]),
               row["vlan"], row["interface"])
        if key not in seen:
            seen.add(key)
            result.append(row)
```

---

## 6. Port-security: sticky MAC (offline устройства)

### Зачем нужно

Обычная MAC-таблица (`show mac address-table`) показывает только **подключённые** устройства.
Если ПК выключен — его MAC пропадает из таблицы.

Port-security со sticky MAC **сохраняет MAC в конфигурации** — даже после отключения устройства.
Это позволяет узнать, какой ПК был подключён к порту, даже если он сейчас offline.

### CLI

```bash
python -m network_collector mac --with-port-security --format excel
```

### Как работает

```
1. show running-config → парсим TextFSM шаблоном cisco_ios_port_security.textfsm
2. Ищем: switchport port-security mac-address sticky <MAC>
3. Извлекаем: interface, MAC, VLAN (из switchport access vlan)
4. Мержим с основной MAC-таблицей (MACNormalizer.merge_sticky_macs)
```

### TextFSM шаблон

**Файл:** `templates/cisco_ios_port_security.textfsm`

```textfsm
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
```

**Что парсится из running-config:**

```
interface GigabitEthernet0/1
 switchport access vlan 100
 switchport port-security
 switchport port-security mac-address sticky aabb.ccdd.eeff
!
interface GigabitEthernet0/2
 switchport access vlan 100
 switchport port-security
 switchport port-security mac-address sticky 1122.3344.5566
```

### Merge со основной таблицей

```python
def merge_sticky_macs(self, mac_table, sticky_macs, hostname="", device_ip=""):
    # Собираем существующие MAC
    existing_macs = {normalize_mac_raw(row["mac"]) for row in mac_table}

    for sticky in sticky_macs:
        raw_mac = normalize_mac_raw(sticky["mac"])
        if raw_mac not in existing_macs:
            # MAC нет в таблице → устройство offline
            sticky["status"] = "offline"
            sticky["hostname"] = hostname
            sticky["device_ip"] = device_ip
            mac_table.append(sticky)
```

**Результат:** sticky MAC, которых нет в обычной таблице, добавляются со статусом "offline".

### Ограничения

| Ограничение | Описание |
|-------------|----------|
| Только Cisco IOS/IOS-XE | Для NX-OS, Arista, QTech нет шаблонов |
| Только access-порты | Trunk-порты с port-security не поддерживаются |
| Тип "sticky" → "static" | В финальном экспорте sticky нормализуется в static |
| Парсит весь running-config | На больших конфигах может быть медленно |

---

## 7. Шаг 2: Матчинг с GLPI (match-mac)

### CLI команда

```bash
python -m network_collector match-mac \
  --mac-file mac_data.xlsx \
  --hosts-file glpi_export.xlsx \
  --output matched_data.xlsx
```

### Входные файлы

**mac_data.xlsx** (от команды `mac`):

| Device | Device IP | Port | MAC Address | VLAN | Status |
|--------|-----------|------|-------------|------|--------|
| switch-01 | 10.0.0.1 | Gi0/1 | aa:bb:cc:dd:ee:ff | 100 | online |
| switch-01 | 10.0.0.1 | Gi0/2 | 11:22:33:44:55:66 | 100 | online |

**glpi_export.xlsx** (экспорт из GLPI):

| Name | MAC |
|------|-----|
| PC-Ivanov | aa:bb:cc:dd:ee:ff |
| PC-Petrov | 11:22:33:44:55:66; 77:88:99:aa:bb:cc |

### Как работает DescriptionMatcher

**Файл:** `configurator/description.py`

```python
class DescriptionMatcher:
    def __init__(self):
        self.reference_data = {}  # {normalized_mac: {"name": "PC-Ivanov"}}
        self.matched_data = []    # [MatchedEntry, ...]
```

#### 1. Загрузка справочника

```python
matcher.load_hosts_file("glpi_export.xlsx", mac_column="MAC", name_column="Name")
```

Для каждой строки GLPI:
- Нормализуем MAC → 12 символов, lowercase (`aabbccddeeff`)
- Если в ячейке **несколько MAC** (через `;`, `,`, перенос строки) — разбиваем
- Сохраняем: `reference_data["aabbccddeeff"] = {"name": "PC-Ivanov"}`

**Пример с несколькими MAC:**
```
Ячейка: "aa:bb:cc:dd:ee:ff; 11:22:33:44:55:66"
→ reference_data["aabbccddeeff"] = {"name": "PC-Petrov"}
→ reference_data["112233445566"] = {"name": "PC-Petrov"}
```

#### 2. Обратный маппинг колонок

MAC-файл может иметь кастомные имена колонок из `fields.yaml` (например "MAC Address" вместо "mac"). Перед матчингом колонки переименовываются обратно:

```python
reverse_map = get_reverse_mapping("mac")
# {"mac address": "mac", "port": "interface", "device": "hostname", ...}
mac_df.columns = [reverse_map.get(col.lower(), col.lower()) for col in mac_df.columns]
```

#### 3. Сопоставление

```python
def match_mac_data(self, mac_data):
    for row in mac_data:
        mac = row.get("mac", "")
        normalized_mac = normalize_mac(mac)  # → "aabbccddeeff"

        entry = MatchedEntry(
            hostname=row["hostname"],
            device_ip=row["device_ip"],
            interface=row["interface"],
            mac=mac,
        )

        if normalized_mac in self.reference_data:
            entry.host_name = self.reference_data[normalized_mac]["name"]
            entry.matched = True
```

**Алгоритм прост:** нормализуем MAC → ищем в словаре → если нашли, записываем имя ПК.

### Выходной файл

**matched_data.xlsx:**

| Device | IP | Interface | MAC | VLAN | Current_Description | Host_Name | Matched |
|--------|-----|-----------|-----|------|---------------------|-----------|---------|
| switch-01 | 10.0.0.1 | Gi0/1 | aa:bb:cc:dd:ee:ff | 100 | | PC-Ivanov | Yes |
| switch-01 | 10.0.0.1 | Gi0/2 | 11:22:33:44:55:66 | 100 | Old | PC-Petrov | Yes |
| switch-02 | 10.0.0.2 | Gi0/5 | xx:xx:xx:xx:xx:xx | 200 | | | No |

### Статистика

```
=== СТАТИСТИКА ===
Справочник хостов: 1500 записей
MAC-адресов: 3200
Сопоставлено: 2100 (65.6%)
Не сопоставлено: 1100
Результат сохранён: matched_data.xlsx
```

### Несколько файлов GLPI (--hosts-folder)

```bash
python -m network_collector match-mac \
  --mac-file mac_data.xlsx \
  --hosts-folder ./glpi_exports/ \
  --output matched_data.xlsx
```

Все `.xlsx` и `.xls` файлы из папки будут загружены — reference_data накапливается.

### Кастомные колонки

Если в GLPI колонки называются иначе:

```bash
python -m network_collector match-mac \
  --mac-file mac_data.xlsx \
  --hosts-file glpi.xlsx \
  --mac-column "MAC Address" \
  --name-column "Computer Name"
```

---

## 8. Шаг 3: Push описаний (push-descriptions)

### CLI команда

```bash
# Сначала dry-run (по умолчанию!)
python -m network_collector push-descriptions --matched-file matched_data.xlsx

# Потом применить
python -m network_collector push-descriptions --matched-file matched_data.xlsx --apply
```

### Как работает

**Файл:** `cli/commands/push.py`

```python
def cmd_push_descriptions(args, ctx=None):
    # 1. Читаем matched_data.xlsx
    df = pd.read_excel(args.matched_file)

    # 2. Фильтруем: только Matched == "Yes"
    matched_df = df[df["Matched"] == "Yes"]

    # 3. Для каждой строки генерируем команды
    for _, row in matched_df.iterrows():
        device_ip = row["IP"]
        interface = row["Interface"]
        host_name = row["Host_Name"]
        current_desc = row["Current_Description"]

        # Проверки: пустое описание, --only-empty, --overwrite
        # Пропускаем если описание уже совпадает

        commands[device_ip].append(f"interface {interface}")
        commands[device_ip].append(f"description {host_name}")
```

### Dry-run (по умолчанию)

```
=== DRY RUN (команды не будут применены) ===

switch-01 (10.0.0.1):
  interface Gi0/1
  description PC-Ivanov
  interface Gi0/2
  description PC-Petrov

Для применения используйте флаг --apply
```

### Применение (--apply)

При `--apply` используется `DescriptionPusher` → `ConfigPusher` → **Netmiko**:

```python
class DescriptionPusher(ConfigPusher):
    def push_descriptions(self, devices, commands, dry_run=True):
        for device_ip, cmds in commands.items():
            device = device_map[device_ip]  # Находим устройство по IP
            result = self.push_config(device, cmds, dry_run=dry_run)
```

`ConfigPusher` использует Netmiko (не Scrapli), потому что Netmiko умеет:
- Заходить в config mode (`conf t`)
- Отправлять набор команд (`send_config_set`)
- Сохранять конфигурацию (`write memory`)

### Флаги управления

| Флаг | Что делает |
|------|-----------|
| (по умолчанию) | Обновляет только порты с пустым описанием |
| `--only-empty` | То же — только пустые описания |
| `--overwrite` | Перезаписывает ВСЕ описания (и пустые, и существующие) |
| `--apply` | Реально применяет (без этого — dry-run) |

### Retry-логика

```python
class ConfigPusher:
    def push_config(self, device, commands, dry_run=True):
        for attempt in range(1, self.max_retries + 1):
            try:
                with ConnectHandler(**params) as conn:
                    conn.enable()
                    output = conn.send_config_set(commands)
                    conn.save_config()
                    return ConfigResult(success=True)
            except AuthenticationException:
                return ConfigResult(success=False)  # Не повторяем
            except (NetmikoTimeoutException, Exception):
                if attempt < self.max_retries:
                    time.sleep(5)  # Повторяем через 5 сек
```

**Важно:** ошибки аутентификации не повторяются. Таймауты — повторяются.

---

## 9. Добавление новой платформы

### Уровень 1: Минимальный (если вывод как у Cisco)

Если новая платформа выводит MAC-таблицу в формате, похожем на Cisco IOS:

**Шаг 1. Маппинги** (`core/constants/platforms.py`):

```python
SCRAPLI_PLATFORM_MAP["myplatform"] = "cisco_iosxe"   # SSH-драйвер
NTC_PLATFORM_MAP["myplatform"] = "cisco_ios"          # Шаблон парсинга
NETMIKO_PLATFORM_MAP["myplatform"] = "cisco_ios"      # Push-драйвер
VENDOR_MAP["myvendor"] = ["myplatform"]               # Группировка
```

**Шаг 2. Команда** (`core/constants/commands.py`):

```python
COLLECTOR_COMMANDS["mac"]["myplatform"] = "show mac address-table"
```

**Шаг 3.** Добавить устройство в `devices_ips.py` и запустить:

```bash
python -m network_collector mac --format json
```

Всё! Парсинг через NTC Templates сработает автоматически.

### Уровень 2: Кастомный шаблон (если вывод уникальный)

**Шаг 1-2.** Те же маппинги и команда.

**Шаг 3.** Создать TextFSM-шаблон (`templates/myplatform_show_mac_address_table.textfsm`):

```textfsm
Value VLAN (\S+)
Value MAC ([0-9a-fA-F]{4}\.[0-9a-fA-F]{4}\.[0-9a-fA-F]{4})
Value TYPE (STATIC|DYNAMIC)
Value INTERFACE (\S+)

Start
  ^\s*${VLAN}\s+${MAC}\s+${TYPE}\s+${INTERFACE} -> Record
```

**Как создать шаблон:**
1. Подключитесь к устройству: `ssh admin@device`
2. Выполните команду: `show mac address-table`
3. Скопируйте вывод в `tests/fixtures/myplatform/show_mac_address_table.txt`
4. Напишите TextFSM-шаблон, который парсит этот вывод
5. Проверьте: `python -c "import textfsm; ..."` или через тесты

**Шаг 4.** Зарегистрировать шаблон (`core/constants/commands.py`):

```python
CUSTOM_TEXTFSM_TEMPLATES[("myplatform", "show mac address-table")] = \
    "myplatform_show_mac_address_table.textfsm"
```

**Шаг 5.** Добавить тест (`tests/test_myplatform_templates.py`):

```python
class TestMyPlatformMAC:
    def test_parse_mac(self):
        fixture = Path("tests/fixtures/myplatform/show_mac_address_table.txt")
        output = fixture.read_text()
        parser = TextFSMParser()
        result = parser.parse_custom("myplatform", "show mac address-table", output)
        assert len(result) > 0
        assert result[0]["mac"]
        assert result[0]["interface"]
```

### Уровень 3: Полная поддержка (как QTech)

Для полной поддержки новой платформы нужны шаблоны для **всех команд**:

| Команда | Для чего | Шаблон |
|---------|----------|--------|
| `show mac address-table` | MAC-таблица | `myplatform_show_mac_address_table.textfsm` |
| `show interfaces status` | Статус портов | `myplatform_show_interface_status.textfsm` |
| `show interfaces` | Детали интерфейсов | `myplatform_show_interface.textfsm` |
| `show interfaces switchport` | Switchport mode | `myplatform_show_interface_switchport.textfsm` |
| `show version` | Модель, серийник | `myplatform_show_version.textfsm` |
| `show lldp neighbors detail` | Соседи | `myplatform_show_lldp_neighbors_detail.textfsm` |

Плюс маппинг интерфейсов если у платформы уникальные имена (как `TFGigabitEthernet` у QTech).

### Port-security: добавление sticky MAC для новой платформы

Port-security (sticky MAC) — это отдельный механизм, работающий поверх основной MAC-таблицы. Он собирает MAC-адреса из `show running-config` (а не из `show mac address-table`). Для новой платформы его нужно добавлять **отдельно** от основной MAC-таблицы.

#### Почему это безопасно

Код спроектирован так, что **отсутствие поддержки port-security не ломает ничего**:

```python
# collectors/mac.py → _collect_sticky_macs()
def _collect_sticky_macs(self, conn, device, interface_status):
    platform = device.platform

    # 1. Ищем шаблон для платформы
    template_key = (platform, "port-security")
    if template_key not in CUSTOM_TEXTFSM_TEMPLATES:
        # 2. Пробуем fallback на cisco_ios
        template_key = ("cisco_ios", "port-security")
        if template_key not in CUSTOM_TEXTFSM_TEMPLATES:
            # 3. Нет шаблона → пустой список (не ошибка!)
            logger.debug(f"Нет шаблона port-security для {platform}")
            return []

    try:
        response = conn.send_command("show running-config")
        parsed = self._textfsm_parser.parse(output, platform, "port-security")
        # ...обработка результатов...
    except Exception as e:
        # 4. Любая ошибка → предупреждение + пустой список
        logger.warning(f"Ошибка сбора sticky MAC: {e}")

    return sticky_macs
```

**Четыре уровня защиты:**

| # | Защита | Что происходит |
|---|--------|----------------|
| 1 | Шаблон не найден для платформы | Пробует cisco_ios как fallback |
| 2 | cisco_ios шаблон тоже не найден | Возвращает пустой список `[]` |
| 3 | Шаблон найден, но парсинг вернул пустоту | Возвращает пустой список `[]` |
| 4 | Любое исключение (SSH, парсинг, etc.) | Логирует warning, возвращает `[]` |

Это значит: **если ты добавляешь новую платформу и не создаёшь port-security шаблон — ничего не упадёт**. Просто sticky MAC не будут собираться, а основная MAC-таблица будет работать нормально.

#### Когда нужен свой шаблон port-security

Свой шаблон нужен если формат `show running-config` отличается от Cisco IOS.

**Cisco IOS/IOS-XE формат** (текущий шаблон покрывает):
```
interface GigabitEthernet0/1
 switchport access vlan 100
 switchport port-security mac-address sticky aabb.ccdd.eeff
!
```

**Если твоя платформа использует тот же формат** — дополнительный шаблон не нужен! Fallback на cisco_ios сработает автоматически:

```python
# Это уже есть в CUSTOM_TEXTFSM_TEMPLATES:
("cisco_ios", "port-security"): "cisco_ios_port_security.textfsm",
("cisco_iosxe", "port-security"): "cisco_ios_port_security.textfsm",
```

**Если формат другой** — нужен свой шаблон. Примеры отличий:

| Платформа | Синтаксис port-security | Нужен свой шаблон? |
|-----------|------------------------|-------------------|
| Cisco IOS/IOS-XE | `switchport port-security mac-address sticky XXXX.XXXX.XXXX` | Нет (уже есть) |
| NX-OS | `switchport port-security mac-address sticky XXXX.XXXX.XXXX vlan NNN` | Да (VLAN в той же строке) |
| QTech | `mac-address-table static XXXX.XXXX.XXXX vlan NNN interface GiX/X` | Да (другой синтаксис) |
| Eltex MES | `switchport port-security mac-address sticky XXXX.XXXX.XXXX` | Нет (как у Cisco) |
| Huawei | `mac-address sticky XXXX-XXXX-XXXX interface GiX/0/X vlan NNN` | Да (другой формат MAC) |

#### Пошаговое добавление port-security для новой платформы

**Пример:** добавляем port-security для NX-OS (Nexus).

**Шаг 1.** Узнать формат вывода — подключись к устройству и посмотри running-config:

```
ssh admin@nexus-switch
show running-config | include "port-security|interface"
```

Вывод NX-OS:
```
interface Ethernet1/1
  switchport access vlan 100
  switchport port-security mac-address sticky 0011.2233.4455 vlan 100
```

Отличие от IOS: `vlan NNN` в конце строки с MAC.

**Шаг 2.** Сохранить образец вывода в fixtures:

```bash
# Скопировать вывод running-config в файл
# tests/fixtures/cisco_nxos/show_running_config_port_security.txt
```

**Шаг 3.** Создать TextFSM-шаблон (`templates/cisco_nxos_port_security.textfsm`):

```textfsm
Value Required INTERFACE (\S+)
Value VLAN (\d+)
Value Required MAC ([0-9a-fA-F]{4}\.[0-9a-fA-F]{4}\.[0-9a-fA-F]{4})
Value TYPE (sticky)

Start
  ^interface\s+${INTERFACE} -> Interface

Interface
  ^\s+switchport\s+access\s+vlan\s+${VLAN}
  ^\s+switchport\s+port-security\s+mac-address\s+${TYPE}\s+${MAC} -> Record
  ^\s+switchport\s+port-security\s+mac-address\s+${TYPE}\s+${MAC}\s+vlan\s+${VLAN} -> Record
  ^interface\s+${INTERFACE} -> Continue.Clearall
  ^interface\s+${INTERFACE} -> Interface
  ^end -> End
```

**Важно:** поля должны называться точно `INTERFACE`, `VLAN`, `MAC`, `TYPE` — это имена, которые ожидает `_collect_sticky_macs()`.

**Шаг 4.** Зарегистрировать шаблон (`core/constants/commands.py`):

```python
CUSTOM_TEXTFSM_TEMPLATES = {
    # ...существующие...
    ("cisco_nxos", "port-security"): "cisco_nxos_port_security.textfsm",
}
```

**Шаг 5.** Написать тест:

```python
# tests/test_parsers/test_nxos_port_security.py
from pathlib import Path
from network_collector.parsers.textfsm_parser import NTCParser

class TestNXOSPortSecurity:
    def test_parse_sticky_mac(self):
        """Парсинг sticky MAC из NX-OS running-config."""
        fixture = Path("tests/fixtures/cisco_nxos/show_running_config_port_security.txt")
        output = fixture.read_text()

        parser = NTCParser()
        result = parser.parse(output, "cisco_nxos", "port-security")

        assert len(result) > 0
        row = result[0]
        assert row["interface"]
        assert row["mac"]
        assert row["type"] == "sticky"

    def test_parse_empty_config(self):
        """Если port-security не настроен — пустой список."""
        output = "interface Ethernet1/1\n  no shutdown\n!\nend"
        parser = NTCParser()
        result = parser.parse(output, "cisco_nxos", "port-security")
        assert result == []
```

**Шаг 6.** Проверить:

```bash
# Тесты
cd /home/sa/project
python -m pytest network_collector/tests/test_parsers/test_nxos_port_security.py -v

# Реальный сбор
python -m network_collector mac --with-port-security --format json
```

#### Чеклист безопасности при добавлении платформы

```
✅ Добавить маппинги в platforms.py (4 словаря)
✅ Добавить команду MAC в commands.py
✅ [Если нужно] Создать TextFSM шаблон для MAC-таблицы
✅ [Если нужно] Создать TextFSM шаблон для port-security
✅ Зарегистрировать шаблоны в CUSTOM_TEXTFSM_TEMPLATES
✅ Сохранить fixture с реальным выводом устройства
✅ Написать тесты для парсинга
✅ Проверить с --format json (без push!)
✅ Убедиться что старые платформы не сломались: pytest tests/ -v
```

#### Что будет если что-то пойдёт не так

| Проблема | Что произойдёт | Как исправить |
|----------|---------------|---------------|
| Шаблон не найден | Fallback на cisco_ios → пустой `[]` | Зарегистрировать в CUSTOM_TEXTFSM_TEMPLATES |
| Шаблон не парсит вывод | `parsed = []`, sticky MAC пустой | Исправить regex в шаблоне |
| Ошибка SSH (show running-config) | `logger.warning(...)`, sticky MAC = `[]` | Проверить права доступа |
| Неправильные имена полей в шаблоне | Пустые значения в mac/interface | Переименовать поля в INTERFACE, MAC, VLAN, TYPE |
| Новый формат MAC (не `XXXX.XXXX.XXXX`) | MAC не нормализуется | `normalize_mac()` поддерживает все форматы |
| Неправильный NETMIKO_PLATFORM_MAP | Ошибка при push-descriptions | Проверить маппинг, попробовать `cisco_ios` |

#### Полная диаграмма: что где добавлять для MAC + port-security

```
┌──────────────────────────────────────────────────────────────────┐
│ ФАЙЛ: core/constants/platforms.py                                │
│                                                                   │
│ SCRAPLI_PLATFORM_MAP["newplatform"] = "cisco_iosxe"  # SSH       │
│ NTC_PLATFORM_MAP["newplatform"] = "cisco_ios"         # TextFSM  │
│ NETMIKO_PLATFORM_MAP["newplatform"] = "cisco_ios"     # Netmiko  │
│ VENDOR_MAP["newvendor"] = ["newplatform"]              # Группа   │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│ ФАЙЛ: core/constants/commands.py                                 │
│                                                                   │
│ COLLECTOR_COMMANDS["mac"]["newplatform"] = "show mac address-table"
│                                                                   │
│ CUSTOM_TEXTFSM_TEMPLATES = {                                      │
│     ("newplatform", "show mac address-table"):                    │
│         "newplatform_show_mac_address_table.textfsm",  # если нужен
│     ("newplatform", "port-security"):                             │
│         "newplatform_port_security.textfsm",           # если нужен
│ }                                                                 │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│ ПАПКА: templates/                                                 │
│                                                                   │
│ newplatform_show_mac_address_table.textfsm    # MAC-таблица       │
│ newplatform_port_security.textfsm             # Sticky MAC        │
│                                                                   │
│ Поля MAC:     VLAN, MAC, TYPE, INTERFACE                          │
│ Поля Sticky:  INTERFACE, VLAN, MAC, TYPE                          │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│ ПАПКА: tests/                                                     │
│                                                                   │
│ fixtures/newplatform/show_mac_address_table.txt  # Реальный вывод │
│ fixtures/newplatform/show_running_config_ps.txt  # Port-security  │
│ test_parsers/test_newplatform_mac.py             # Тесты парсинга │
└──────────────────────────────────────────────────────────────────┘
```

---

## 10. Тестирование

### Структура тестов

```
tests/
├── test_parsers/
│   └── test_mac.py                    # TextFSM парсинг (3 платформы)
├── test_core/test_domain/
│   └── test_mac_normalizer.py         # MACNormalizer (52+ тестов)
├── test_e2e/
│   └── test_mac_collector_e2e.py      # E2E: parse → normalize → models
└── fixtures/
    ├── cisco_ios/show_mac_address_table.txt
    ├── cisco_nxos/show_mac_address_table.txt
    └── qtech/show_mac_address_table.txt
```

### Что покрыто тестами

| Компонент | Кол-во тестов | Покрытие |
|-----------|---------------|----------|
| TextFSM парсинг (3 платформы) | 11 | Хорошее |
| MACNormalizer (фильтры, формат, статус) | 52+ | Отличное |
| E2E: parse → normalize → export | 13 | Хорошее |
| **DescriptionMatcher** (match-mac) | **0** | Нет тестов |
| **cmd_push_descriptions** | **0** | Нет тестов |

### Запуск тестов

```bash
cd /home/sa/project
python -m pytest network_collector/tests/test_parsers/test_mac.py -v
python -m pytest network_collector/tests/test_core/test_domain/test_mac_normalizer.py -v
python -m pytest network_collector/tests/test_e2e/test_mac_collector_e2e.py -v
```

---

## 11. Что можно доработать

### Приоритет 1 — Критично

| Задача | Описание |
|--------|----------|
| Тесты DescriptionMatcher | Нет ни одного теста для match-mac. Нужны тесты на загрузку файла, сопоставление, статистику |
| Тесты push-descriptions | Нет тестов на генерацию команд, фильтрацию, dry-run, --only-empty/--overwrite |

### Приоритет 2 — Улучшения

| Задача | Описание |
|--------|----------|
| Port-security для NX-OS | Добавить TextFSM-шаблон для `show port-security interface` на NX-OS |
| Port-security для QTech | Добавить шаблон для QTech-специфичного синтаксиса port-security |
| Сохранить тип "sticky" | Сейчас sticky нормализуется в static — теряется информация |
| Port-security через show | Вместо парсинга всего running-config — использовать `show port-security address` |

### Приоритет 3 — Новые фичи

| Задача | Описание |
|--------|----------|
| GLPI API интеграция | Вместо Excel-экспорта — прямой запрос к GLPI REST API |
| OUI vendor lookup | Определять вендора по первым 3 байтам MAC (уже есть поле `vendor`, но не заполняется) |
| Автоматический pipeline | Объединить mac → match → push в один pipeline |
| NetBox MAC sync | Синхронизировать MAC-таблицу в NetBox (custom fields или journal) |

---

## 12. Полная диаграмма потока данных

```
┌──────────────────────────────────────────────────────────────────────────┐
│ ШАГ 1: python -m network_collector mac --with-port-security --format excel│
└──────────┬───────────────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────┐
│ MACCollector._collect_from_device(device)         │
│                                                   │
│  SSH → show mac address-table ──► NTC/TextFSM ──► [{mac, interface, vlan}]
│  SSH → show interfaces status ──► NTC ──────────► {interface: status}
│  SSH → show interfaces description ──► NTC ─────► {interface: description}
│  SSH → show interfaces trunk ──────────────────► {trunk_interfaces}
│  SSH → show running-config ───► TextFSM ────────► [{sticky_mac}]
└──────────┬───────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────┐
│ MACNormalizer                                     │
│ ├── normalize_interface_short()                   │
│ ├── normalize_mac(format="ieee")                  │
│ ├── exclude_interfaces (regex)                    │
│ ├── exclude_vlans [1, 4094]                       │
│ ├── filter_trunk_ports()                          │
│ ├── merge_sticky_macs() ── offline устройства     │
│ ├── add status (online/offline)                   │
│ ├── add description                               │
│ └── deduplicate()                                 │
└──────────┬───────────────────────────────────────┘
           │
           ▼
       mac_data.xlsx
           │
═══════════╪═══════════════════════════════════════════════════════════════
           │
           ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ ШАГ 2: python -m network_collector match-mac                             │
│         --mac-file mac_data.xlsx --hosts-file glpi.xlsx                   │
└──────────┬───────────────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────┐
│ DescriptionMatcher                                │
│                                                   │
│ 1. load_hosts_file(glpi.xlsx)                     │
│    ├── Каждый MAC нормализуется → 12 символов     │
│    ├── Несколько MAC в ячейке → разбиваем (;,\n)  │
│    └── reference_data = {mac: {name: "PC-01"}}    │
│                                                   │
│ 2. reverse_map: "MAC Address"→"mac" (fields.yaml) │
│                                                   │
│ 3. match_mac_data(mac_data)                       │
│    └── Для каждого MAC: lookup в reference_data   │
│        ├── Найден → matched=True, host_name=...   │
│        └── Не найден → matched=False              │
│                                                   │
│ 4. save_matched("matched_data.xlsx")              │
│    └── Device | IP | Interface | MAC | Host_Name  │
└──────────┬───────────────────────────────────────┘
           │
           ▼
       matched_data.xlsx
           │
═══════════╪═══════════════════════════════════════════════════════════════
           │
           ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ ШАГ 3: python -m network_collector push-descriptions                     │
│         --matched-file matched_data.xlsx --apply                         │
└──────────┬───────────────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────┐
│ cmd_push_descriptions()                           │
│                                                   │
│ 1. pd.read_excel(matched_data.xlsx)               │
│ 2. Фильтр: Matched == "Yes"                      │
│ 3. Проверка: only_empty? overwrite? same desc?    │
│ 4. Генерация команд:                              │
│    commands["10.0.0.1"] = [                       │
│        "interface Gi0/1",                         │
│        "description PC-Ivanov",                   │
│        "interface Gi0/2",                         │
│        "description PC-Petrov",                   │
│    ]                                              │
└──────────┬───────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────┐
│ DescriptionPusher(ConfigPusher)                   │
│                                                   │
│ Для каждого устройства (Netmiko):                 │
│ ├── SSH connect (по IP из matched_data)           │
│ ├── enable                                        │
│ ├── send_config_set(commands)                     │
│ │   → conf t                                      │
│ │   → interface Gi0/1                              │
│ │   → description PC-Ivanov                        │
│ │   → exit                                         │
│ ├── save_config()                                 │
│ │   → write memory                                │
│ └── disconnect                                    │
│                                                   │
│ Retry: 2 попытки, 5 сек пауза (кроме auth)       │
└──────────────────────────────────────────────────┘
```

---

## Связь с официальной документацией

| Тема | Где читать |
|------|------------|
| CLI команды mac, match-mac, push | [MANUAL.md](../MANUAL.md) — секции 3 и 10 |
| Конфигурация фильтров | [MANUAL.md](../MANUAL.md) — секция 2 и 8 |
| Платформы и шаблоны | [PLATFORM_GUIDE.md](../PLATFORM_GUIDE.md) |
| Архитектура коллекторов | [ARCHITECTURE.md](../ARCHITECTURE.md) |
| Тестирование | [TESTING.md](../TESTING.md) |
