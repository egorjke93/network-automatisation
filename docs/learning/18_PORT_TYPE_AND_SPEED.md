# 18. Определение типа порта и скорости: полная цепочка

## Зачем это нужно

Когда ты синхронизируешь интерфейсы с NetBox, для каждого порта нужно определить:
1. **Тип порта** (`1000base-t`, `10gbase-x-sfpp`, `100base-tx`) — для поля `type` в NetBox
2. **Скорость** (1000000 Kbps, 10000000 Kbps) — для поля `speed` в NetBox

Проблема: устройства разных вендоров возвращают эти данные в совершенно разных форматах. А для down-портов данные вообще неполные или ненадёжные.

---

## Общая архитектура: 5 шагов pipeline

```
┌──────────────────────────────────────────────────────────────────────┐
│  1. TextFSM / NTC Templates                                         │
│     show interfaces → {speed, bandwidth, hardware_type, media_type}  │
│     Ключи в разном формате по платформам                             │
└──────────────────────────┬───────────────────────────────────────────┘
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│  2. NTCParser._normalize_fields() — UNIVERSAL_FIELD_MAP              │
│     Приводит ключи к единым стандартным именам                       │
│     "link_status" → "status", "mac_address" → "mac"                  │
│     ⚠ bandwidth НЕ маппится на speed (разная семантика!)             │
└──────────────────────────┬───────────────────────────────────────────┘
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│  3. InterfaceNormalizer._normalize_row()                             │
│     a) detect_port_type() — определяет port_type                     │
│        Приоритет: media_type → hardware_type → имя интерфейса        │
│     b) Номинальная скорость для down-портов                          │
│        Если speed пустой/unknown/auto → берём из port_type           │
└──────────────────────────┬───────────────────────────────────────────┘
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│  4. Interface.from_dict() → модель Interface                         │
│     speed = data.get("speed") or ""                                  │
│     ⚠ bandwidth НЕ используется (ненадёжный для down-портов)        │
└──────────────────────────┬───────────────────────────────────────────┘
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│  5. Sync: get_netbox_interface_type() + _parse_speed()               │
│     a) Определяет NetBox тип (1000base-t, 10gbase-x-sfpp)           │
│        Приоритет: LAG → virtual → mgmt → media → port_type → hw →   │
│                   имя → speed → default                              │
│     b) Парсит speed в Kbps для NetBox API                            │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Шаг 1: TextFSM — что возвращает каждая платформа

### Cisco IOS (`show interfaces`)

```
GigabitEthernet0/1 is up, line protocol is up (connected)
  Hardware is Gigabit Ethernet, address is 0011.2233.4455
  Full-duplex, 1000Mb/s, media type is 10/100/1000BaseTX
  ...
  MTU 1500 bytes, BW 1000000 Kbit/sec
```

NTC Template возвращает:

| Поле | UP порт | DOWN порт |
|------|---------|-----------|
| `speed` | `"1000Mb/s"` | `"Auto-speed"` или `""` |
| `bandwidth` | `"1000000 Kbit"` | `"10000 Kbit"` ⚠ ненадёжно |
| `hardware_type` | `"Gigabit Ethernet"` | `"Gigabit Ethernet"` |
| `media_type` | `"10/100/1000BaseTX"` | `"10/100/1000BaseTX"` |

**Ключевое:** `bandwidth` для down-порта может показывать 10000 Kbit (10 Mbps) — это дефолтный BW для QoS, а НЕ номинальная скорость порта.

### FastEthernet на Cisco IOS

| Поле | UP порт | DOWN порт |
|------|---------|-----------|
| `speed` | `"100Mb/s"` | `""` |
| `bandwidth` | `"100000 Kbit"` | `"10000 Kbit"` ⚠ |
| `hardware_type` | `"Fast Ethernet"` | `"Fast Ethernet"` |
| `media_type` | `"10/100BaseTX"` | `"10/100BaseTX"` |

### QTech (`show interfaces`)

| Поле | UP порт | DOWN порт |
|------|---------|-----------|
| `speed` | `"10G"`, `"1G"` | `"Unknown"` |
| `bandwidth` | `"10000000"` | `"10000"` ⚠ |
| `hardware_type` | из TextFSM | из TextFSM |
| `media_type` | из `show interface transceiver` (отдельная команда) | `""` (нет трансивера) |

### NX-OS (`show interfaces`)

| Поле | UP порт | DOWN порт |
|------|---------|-----------|
| `speed` | `"10 Gb/s"` | `"auto-speed"` |
| `bandwidth` | `"10000000 Kbit"` | `"10000000 Kbit"` |
| `hardware_type` | `"100/1000/10000 Ethernet"` | `"100/1000/10000 Ethernet"` |

---

## Шаг 2: UNIVERSAL_FIELD_MAP — нормализация ключей

**Файл:** `parsers/textfsm_parser.py`

Разные NTC-шаблоны возвращают одни и те же данные под разными ключами. `UNIVERSAL_FIELD_MAP` приводит их к единым стандартным именам:

```python
UNIVERSAL_FIELD_MAP = {
    "mac": ["mac", "mac_address", "destination_address"],
    "status": ["status", "link_status", "link"],
    "speed": ["speed"],          # ← ТОЛЬКО speed, НЕ bandwidth!
    "hostname": ["hostname", "host", "switchname", "device_id"],
    ...
}
```

### Как работает _normalize_fields()

```python
for key, value in row.items():
    key_lower = key.lower()
    # Ищем стандартное имя
    standard_key = key_lower
    for std_name, aliases in UNIVERSAL_FIELD_MAP.items():
        if key_lower in aliases:
            standard_key = std_name
            break
    new_row[standard_key] = value  # ← если два ключа маппятся на один — ПОСЛЕДНИЙ побеждает
```

### Правило: алиас только для ОДНОГО поля

```python
# ✅ Правильно — одно поле с разным именем:
"mac": ["mac", "mac_address"]

# ❌ Неправильно — разные поля (bandwidth ≠ speed):
"speed": ["speed", "bandwidth"]
# bandwidth это BW для QoS, speed это согласованная скорость
```

Если маппить `bandwidth → speed`, то bandwidth (10000 Kbit) перезаписывает пустой speed для down-портов.

---

## Шаг 3: InterfaceNormalizer — port_type и номинальная скорость

**Файл:** `core/domain/interface.py`

### 3a. detect_port_type() — три приоритета

Определяет нормализованный тип порта (`"1g-rj45"`, `"10g-sfp+"`, `"100m-rj45"`).

**Приоритет определения:**

```
1. media_type  → MEDIA_TYPE_PORT_TYPE_MAP    (самый точный: "10GBASE-SR" → "10g-sfp+")
2. hardware_type → HARDWARE_TYPE_PORT_TYPE_MAP  ("100/1000/10000 Ethernet" → "10g-sfp+")
3. имя интерфейса → INTERFACE_NAME_PORT_TYPE_MAP  ("fastethernet" → "100m-rj45")
```

**Маппинги (файл `core/constants/interfaces.py`):**

```python
# media_type паттерн → port_type
MEDIA_TYPE_PORT_TYPE_MAP = {
    "100gbase": "100g-qsfp28",
    "10gbase": "10g-sfp+",
    "1000base-t": "1g-rj45",    # медь
    "1000base": "1g-sfp",       # оптика (generic)
    ...
}

# hardware_type паттерн → port_type
HARDWARE_TYPE_PORT_TYPE_MAP = {
    "100/1000/10000": "10g-sfp+",   # NX-OS multi-speed
    "gigabit": "1g-rj45",
    "1000": "1g-rj45",
    ...
}

# имя интерфейса → port_type
INTERFACE_NAME_PORT_TYPE_MAP = {
    "hundredgig": "100g-qsfp28",
    "hu": "100g-qsfp28",
    "tengig": "10g-sfp+",
    "te": "10g-sfp+",
    "gigabit": "1g-rj45",
    "gi": "1g-rj45",
    "fastethernet": "100m-rj45",
    "fa": "100m-rj45",
    ...
}
```

### 3b. Номинальная скорость для down-портов

После определения `port_type`, если speed пустой или неизвестный:

```python
_UNKNOWN_SPEED_VALUES = {"unknown", "auto", "auto-speed", ""}

# В _normalize_row():
speed = result.get("speed", "")
if speed.lower().strip() in _UNKNOWN_SPEED_VALUES:
    nominal = get_nominal_speed_from_port_type(result.get("port_type", ""))
    if nominal:
        result["speed"] = nominal
```

**Как get_nominal_speed_from_port_type() парсит скорость из port_type:**

```python
def get_nominal_speed_from_port_type(port_type: str) -> str:
    """
    "1g-rj45"   → "1000000 Kbit"    (1G)
    "10g-sfp+"  → "10000000 Kbit"   (10G)
    "25g-sfp28" → "25000000 Kbit"   (25G)
    "100m-rj45" → "100000 Kbit"     (100M)
    """
    prefix = port_type.split("-", 1)[0]  # "1g", "10g", "100m"
    if prefix.endswith("g"):
        return f"{int(prefix[:-1]) * 1000000} Kbit"
    elif prefix.endswith("m"):
        return f"{int(prefix[:-1]) * 1000} Kbit"
```

**Новых маппингов не нужно** — скорость уже закодирована в port_type.

---

## Шаг 4: Interface.from_dict()

**Файл:** `core/models.py`

```python
speed=data.get("speed") or ""   # ← ТОЛЬКО speed, НЕ bandwidth
```

К этому моменту speed уже содержит правильное значение:
- UP порт: реальная скорость (`"1000Mb/s"`, `"10G"`)
- DOWN порт: номинальная скорость (`"1000000 Kbit"`, `"100000 Kbit"`)

---

## Шаг 5: Sync — NetBox тип и скорость

### 5a. get_netbox_interface_type()

**Файл:** `core/constants/netbox.py`

Определяет тип интерфейса для NetBox API. Приоритет:

```
1. LAG (Port-channel, AggregatePort) → "lag"
2. Virtual (Vlan, Loopback) → "virtual"
3. Management (mgmt, Management) → "1000base-t"
4. media_type → NETBOX_INTERFACE_TYPE_MAP     ← ВЫСШИЙ приоритет для физических портов
5. port_type → PORT_TYPE_MAP
6. hardware_type → NETBOX_HARDWARE_TYPE_MAP
7. имя интерфейса → _detect_type_by_name_prefix()
8. speed → fallback по скорости
9. default → "1000base-t"
```

**NETBOX_INTERFACE_TYPE_MAP (медные паттерны):**

```python
# Порядок КРИТИЧЕН! Специфичные перед общими.
"10/100/1000baset": "1000base-t",   # GigE copper
"10/100/1000": "1000base-t",
"1000baset": "1000base-t",
"100baset": "100base-tx",            # FastEthernet copper
"10/100": "100base-tx",
"10baset": "10base-t",
"basetx": "1000base-t",              # generic — ПОСЛЕДНИМ
"base-tx": "1000base-t",
"rj45": "1000base-t",
```

**Почему порядок важен:** маппинг использует `if pattern in media_lower` (поиск подстроки). Если `"basetx"` стоит перед `"10/100"`, то `"basetx"` матчит `"10/100basetx"` и возвращает `1000base-t` (НЕПРАВИЛЬНО для FastEthernet).

### 5b. _parse_speed()

**Файл:** `netbox/sync/base.py`

Конвертирует speed в Kbps для NetBox API:

```python
def _parse_speed(self, speed_str):
    if "kbit" in speed_str:    # "1000000 Kbit" → 1000000
        return int(speed_str.split()[0])
    if "gbit" in speed_str:    # "1 Gbit" → 1000000
        return int(float(speed_str.split()[0]) * 1000000)
    if "mbit" in speed_str:    # "100 Mbit" → 100000
        return int(float(speed_str.split()[0]) * 1000)
    return int(speed_str.split()[0])  # fallback
```

Для DOWN-портов наши номинальные скорости всегда в формате "X Kbit" — `_parse_speed` обрабатывает их корректно.

---

## Примеры: полная цепочка для каждого сценария

### Cisco IOS GigabitEthernet DOWN

```
show interfaces:
  speed=""  bandwidth="10000"  media_type="10/100/1000BaseTX"  hw="Gigabit Ethernet"
    ↓
UNIVERSAL_FIELD_MAP:
  speed=""  (bandwidth остаётся отдельным ключом, НЕ перезаписывает speed)
    ↓
detect_port_type():
  media "10/100/1000basetx" → "1000base" match → port_type = "1g-sfp" (или "1g-rj45" по имени)
    ↓
Номинальная скорость:
  speed="" IS in _UNKNOWN_SPEED_VALUES → get_nominal("1g-...") = "1000000 Kbit"
    ↓
Interface.from_dict():
  speed = "1000000 Kbit"
    ↓
get_netbox_interface_type():
  media "10/100/1000baset" match → "1000base-t" ✓
    ↓
_parse_speed("1000000 Kbit"):
  "kbit" match → 1000000 Kbps = 1 Gbps ✓
```

### FastEthernet DOWN

```
show interfaces:
  speed=""  bandwidth="10000"  media_type="10/100BaseTX"  hw="Fast Ethernet"
    ↓
UNIVERSAL_FIELD_MAP:
  speed=""  (bandwidth — отдельный ключ)
    ↓
detect_port_type():
  media "10/100basetx" — нет совпадения в MEDIA_TYPE_PORT_TYPE_MAP
  hw "fast ethernet" — нет совпадения в HARDWARE_TYPE_PORT_TYPE_MAP
  name "fastethernet0/1" → port_type = "100m-rj45"
    ↓
Номинальная скорость:
  speed="" IS in _UNKNOWN_SPEED_VALUES → get_nominal("100m-rj45") = "100000 Kbit"
    ↓
Interface.from_dict():
  speed = "100000 Kbit"
    ↓
get_netbox_interface_type():
  media "10/100basetx" → "100baset" match → "100base-tx" ✓
    ↓
_parse_speed("100000 Kbit"):
  "kbit" match → 100000 Kbps = 100 Mbps ✓
```

### QTech TFGigabitEthernet DOWN (без трансивера)

```
show interfaces:
  speed="Unknown"  media_type=""  hw=""
    ↓
detect_port_type():
  media пустой  hw пустой
  name "tfgigabitethernet0/3" → port_type = "25g-sfp28"
    ↓
Номинальная скорость:
  "unknown" IS in _UNKNOWN_SPEED_VALUES → get_nominal("25g-sfp28") = "25000000 Kbit"
    ↓
get_netbox_interface_type():
  media пустой → port_type "25g-sfp28" in PORT_TYPE_MAP → "25gbase-x-sfp28" ✓
    ↓
_parse_speed("25000000 Kbit"):
  "kbit" match → 25000000 Kbps = 25 Gbps ✓
```

### NX-OS Ethernet DOWN

```
show interfaces:
  speed="auto-speed"  hw="100/1000/10000 Ethernet"
    ↓
detect_port_type():
  hw "100/1000/10000 ethernet" → "100/1000/10000" match → port_type = "10g-sfp+"
    ↓
Номинальная скорость:
  "auto-speed" IS in _UNKNOWN_SPEED_VALUES → get_nominal("10g-sfp+") = "10000000 Kbit"
    ↓
get_netbox_interface_type():
  port_type "10g-sfp+" in PORT_TYPE_MAP → "10gbase-x-sfpp" ✓
    ↓
_parse_speed("10000000 Kbit"):
  "kbit" match → 10000000 Kbps = 10 Gbps ✓
```

---

## Все маппинги и где они живут

### Маппинги port_type (domain layer)

**Файл:** `core/constants/interfaces.py`

| Маппинг | Что делает | Формат значений |
|---------|-----------|----------------|
| `MEDIA_TYPE_PORT_TYPE_MAP` | media_type → port_type | `"10gbase" → "10g-sfp+"` |
| `HARDWARE_TYPE_PORT_TYPE_MAP` | hardware_type → port_type | `"gigabit" → "1g-rj45"` |
| `INTERFACE_NAME_PORT_TYPE_MAP` | имя интерфейса → port_type | `"fastethernet" → "100m-rj45"` |

### Маппинги NetBox типа (sync layer)

**Файл:** `core/constants/netbox.py`

| Маппинг | Что делает | Формат значений |
|---------|-----------|----------------|
| `PORT_TYPE_MAP` | port_type → NetBox API тип | `"1g-rj45" → "1000base-t"` |
| `NETBOX_INTERFACE_TYPE_MAP` | media_type → NetBox тип | `"10gbase-sr" → "10gbase-sr"` |
| `NETBOX_HARDWARE_TYPE_MAP` | hardware_type → NetBox тип | `"fast ethernet" → "100base-tx"` |

### Маппинг ключей полей

**Файл:** `parsers/textfsm_parser.py`

| Маппинг | Что делает |
|---------|-----------|
| `UNIVERSAL_FIELD_MAP` | Нормализация имён полей NTC: `"link_status" → "status"` |

### Номинальная скорость

**Файл:** `core/constants/interfaces.py`

| Константа / Функция | Что делает |
|---------------------|-----------|
| `_UNKNOWN_SPEED_VALUES` | Множество значений speed, которые считаются "неизвестными" |
| `get_nominal_speed_from_port_type()` | Парсит скорость из префикса port_type |

---

## Правила порядка в маппингах

### Правило: substring-маппинги — специфичные перед общими

Все маппинги с `if pattern in value` (substring match) требуют правильного порядка:

```python
# ✅ Правильно — специфичные перед общими:
"10/100/1000baset": "1000base-t",   # матчит "10/100/1000basetx"
"100baset": "100base-tx",            # матчит "10/100basetx"
"basetx": "1000base-t",              # generic, ПОСЛЕДНИЙ

# ❌ Неправильно — "basetx" матчит "10/100basetx" первым:
"basetx": "1000base-t",              # ПЕРЕХВАТЫВАЕТ FastEthernet!
"10/100/1000baset": "1000base-t",    # никогда не достигается для "10/100basetx"
```

Это относится ко ВСЕМ маппингам:
- `NETBOX_INTERFACE_TYPE_MAP` (медные паттерны)
- `HARDWARE_TYPE_PORT_TYPE_MAP` ("10000" перед "1000")
- `MEDIA_TYPE_PORT_TYPE_MAP`

---

## Добавление нового типа порта

### Шаг 1: Определить характеристики

- Какой port_type? (например `"2.5g-rj45"`)
- Какой NetBox тип? (например `"2.5gbase-t"`)
- Какой media_type на устройстве? (например `"2.5GbaseT"`)
- Какой hardware_type? (например `"2500 Ethernet"`)
- Какой префикс имени? (например `"TwoDotFiveGigE"`)

### Шаг 2: Обновить маппинги

```python
# 1. core/constants/interfaces.py

# Имя → port_type (если новый префикс)
INTERFACE_NAME_PORT_TYPE_MAP["twodotfivegige"] = "2.5g-rj45"

# Media → port_type
MEDIA_TYPE_PORT_TYPE_MAP["2.5gbase"] = "2.5g-rj45"

# Hardware → port_type
HARDWARE_TYPE_PORT_TYPE_MAP["2500"] = "2.5g-rj45"

# 2. core/constants/netbox.py

# port_type → NetBox тип
PORT_TYPE_MAP["2.5g-rj45"] = "2.5gbase-t"

# media_type → NetBox тип (если есть уникальный media)
NETBOX_INTERFACE_TYPE_MAP["2.5gbase"] = "2.5gbase-t"

# hardware_type → NetBox тип
NETBOX_HARDWARE_TYPE_MAP["2500"] = "2.5gbase-t"
```

### Шаг 3: Номинальная скорость

Если port_type в формате `"Xg-..."` или `"Xm-..."` — `get_nominal_speed_from_port_type()` автоматически распарсит скорость. Для нестандартных форматов (как `"2.5g"`) нужно проверить парсинг:

```python
# "2.5g-rj45" → parts[0] = "2.5g" → "2.5g".endswith("g") → int("2.5") → ValueError!
# Нужен float: float("2.5") * 1000000 = 2500000
```

Если стандартный парсинг не работает, нужно обновить `get_nominal_speed_from_port_type()`.

### Шаг 4: Проверить

```bash
# Собрать с устройства
python -m network_collector interfaces --format parsed --host 10.0.0.1

# Проверить тесты
pytest tests/ -v -k "port_type or interface_type"
```

---

## Частые ошибки и уроки

### 1. bandwidth ≠ speed

**bandwidth** (BW) — это сконфигурированная пропускная способность для QoS. Для down-портов на некоторых моделях показывает 10000 Kbit (10 Mbps) — это НЕ номинальная скорость 1G порта.

**speed** — это реальная согласованная скорость (1000Mb/s при UP) или пустая строка при DOWN.

### 2. Порядок паттернов в substring-маппингах

Python 3.7+ гарантирует порядок dict. Если маппинг использует `in` (подстрока), общий паттерн может перехватить значения, предназначенные для специфичного. Всегда ставь специфичные паттерны первыми.

### 3. Два слоя маппингов

`detect_port_type()` (domain) определяет промежуточный `port_type` ("1g-rj45").
`get_netbox_interface_type()` (sync) определяет финальный NetBox тип ("1000base-t").

Это **два независимых маппинга** с разными приоритетами. `get_netbox_interface_type()` может вернуть правильный тип даже если `port_type` неточный.

### 4. media_type — самый точный источник

Если на порту стоит трансивер, `media_type = "SFP-10GBase-SR"` — это самый точный источник типа. Он определяет и тип порта, и NetBox тип напрямую.

Без трансивера (down-порт, пустой SFP) — fallback на hardware_type и имя интерфейса.

### 5. Номинальная скорость — из port_type, не из нового маппинга

Скорость уже закодирована в port_type: `"1g"` → 1G, `"10g"` → 10G, `"100m"` → 100M. Функция `get_nominal_speed_from_port_type()` парсит префикс. Не нужно создавать отдельный маппинг port_type → speed.

---

## Связь с другими документами

| Документ | Что дополняет |
|----------|--------------|
| [04_DATA_COLLECTION.md](04_DATA_COLLECTION.md) | TextFSM парсинг, NTC Templates |
| [10_COLLECTORS_DEEP_DIVE.md](10_COLLECTORS_DEEP_DIVE.md) | InterfaceCollector, InterfaceNormalizer |
| [13_SWITCHPORT_FLOW.md](13_SWITCHPORT_FLOW.md) | Switchport mode определение |
| [14_INTERFACE_NAME_MAPPINGS.md](14_INTERFACE_NAME_MAPPINGS.md) | Нормализация имён интерфейсов |
| [PLATFORM_GUIDE.md 12.18](../PLATFORM_GUIDE.md) | Сводная таблица всех маппингов |
| [PLATFORM_GUIDE.md 12.19](../PLATFORM_GUIDE.md) | UNIVERSAL_FIELD_MAP: правила и чеклист |
| [BUGFIX_LOG.md Баги 22-24](../BUGFIX_LOG.md) | История багов speed и port_type |
