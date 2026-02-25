# 18. Тип порта и скорость: как всё работает

## Быстрый ответ: что происходит при синхронизации

Когда ты запускаешь `sync-netbox --interfaces`, система определяет для каждого порта две вещи:

1. **type** — тип порта в NetBox (`1000base-t`, `10gbase-x-sfpp`, `100base-tx`)
2. **speed** — скорость в Kbps (`1000000`, `10000000`)

**Всего 3 слоя, каждый делает своё:**

```
СЛОЙ 1: Сбор          SSH → TextFSM → сырые поля (speed, hardware_type, media_type)
СЛОЙ 2: Нормализация  → port_type + номинальная скорость (для down-портов)
СЛОЙ 3: Синхронизация  → NetBox type + speed в Kbps
```

---

## Одна страница: полная цепочка

```
┌─────────────────────────────────────────────────────────────────┐
│ СЛОЙ 1: СБОР (collectors → parsers)                             │
│                                                                 │
│  SSH: show interfaces                                           │
│  TextFSM → сырые поля:                                          │
│    speed        = "10 Gb/s" (UP) / "auto-speed" (DOWN)          │
│    hardware_type = "100/1000/10000 Ethernet"                    │
│    media_type   = "10G" или "SFP-10GBase-SR"                    │
│    bandwidth    = "10000000 Kbit" (ИГНОРИРУЕТСЯ для speed!)     │
│                                                                 │
│  UNIVERSAL_FIELD_MAP: нормализация ИМЁН полей                   │
│    "link_status" → "status", "mac_address" → "mac"              │
│    speed остаётся speed, bandwidth остаётся bandwidth            │
└──────────────────────────┬──────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│ СЛОЙ 2: НОРМАЛИЗАЦИЯ (core/domain/interface.py)                 │
│                                                                 │
│  ШАГ A: detect_port_type() — определяет port_type               │
│                                                                 │
│    Приоритет:                                                    │
│    ┌──────────────────┐   ┌─────────────────┐                   │
│    │ 0. LAG/Virtual/  │──▶│ "lag", "virtual" │                  │
│    │    Management    │   │ "1g-rj45" (mgmt) │                  │
│    └──────────────────┘   └─────────────────┘                   │
│    ┌──────────────────┐                                          │
│    │ 1. media_type    │──▶ "SFP-10GBase-SR" → "10g-sfp+"        │
│    │    (трансивер)   │   ⚠ "10G" пропускается (bare speed)     │
│    └──────────────────┘                                          │
│    ┌──────────────────┐                                          │
│    │ 2. hardware_type │──▶ "100/1000/10000" → "10g-sfp+"        │
│    │    (макс.скорость│   "Gigabit Ethernet" → "1g-rj45"        │
│    │     порта)       │                                          │
│    └──────────────────┘                                          │
│    ┌──────────────────┐                                          │
│    │ 3. имя интерфейса│──▶ "GigabitEthernet" → "1g-rj45"        │
│    │    (fallback)    │   "FastEthernet" → "100m-rj45"          │
│    └──────────────────┘                                          │
│                                                                 │
│  ШАГ B: скорость                                                │
│                                                                 │
│    UP порт?  → speed уже заполнен ("10 Gb/s") → оставляем      │
│    DOWN порт? → speed пустой/unknown/auto                       │
│                → get_nominal_speed_from_port_type("10g-sfp+")   │
│                → "10000000 Kbit"                                │
│                                                                 │
└──────────────────────────┬──────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│ СЛОЙ 3: СИНХРОНИЗАЦИЯ (netbox/sync/)                            │
│                                                                 │
│  get_netbox_interface_type(interface):                           │
│    port_type "10g-sfp+" → PORT_TYPE_MAP → "10gbase-x-sfpp"     │
│    media "SFP-10GBase-SR" → NETBOX_INTERFACE_TYPE_MAP           │
│                           → "10gbase-sr" (точнее!)              │
│                                                                 │
│  _parse_speed(speed_str):                                       │
│    "10000000 Kbit" → 10000000 (Kbps)     ← DOWN порт           │
│    "10 Gb/s"       → 10000000 (Kbps)     ← UP порт NX-OS       │
│    "1000Mb/s"      → 1000000 (Kbps)      ← UP порт IOS         │
│    "10G"           → 10000000 (Kbps)      ← UP порт QTech       │
│                                                                 │
│  → NetBox API: type="10gbase-x-sfpp", speed=10000000            │
└─────────────────────────────────────────────────────────────────┘
```

---

## UP порт vs DOWN порт — в чём разница

Это главный источник путаницы. Для UP и DOWN портов данные приходят **по-разному**:

### UP порт (линк поднят, есть трансивер)

```
speed:         "10 Gb/s" (NX-OS) / "1000Mb/s" (IOS) / "10G" (QTech)
                ↳ реальная согласованная скорость линка
media_type:    "SFP-10GBase-SR" (если собрали show interface transceiver)
                ↳ реальный тип трансивера
hardware_type: "100/1000/10000 Ethernet"
                ↳ максимальная ёмкость порта (всегда есть)
```

**Цепочка:** speed → `_parse_speed()` → Kbps. Всё просто.

### DOWN порт (линк не поднят / нет трансивера)

```
speed:         "" / "auto-speed" / "Unknown"
                ↳ ПУСТОЙ! Линк не согласован, скорости нет
media_type:    "" / "Not Present" / "10G" (NX-OS bare indicator)
                ↳ часто пустой или неточный
hardware_type: "100/1000/10000 Ethernet"
                ↳ максимальная ёмкость порта (всегда есть)
bandwidth:     "10000 Kbit" ← НЕНАДЁЖНЫЙ! Для QoS, не для реальной скорости
```

**Цепочка:** speed пустой → `detect_port_type()` из hw/name → `get_nominal_speed_from_port_type()` → "10000000 Kbit" → `_parse_speed()` → Kbps.

### Разница в таблице

| | UP порт | DOWN порт | LAG (Port-channel) |
|--|---------|-----------|-------------------|
| Откуда speed | Реальная с устройства | Номинальная из port_type | **bandwidth** (агрегат) |
| Формат speed | Платформо-зависимый | Всегда "X Kbit" | "X Kbit" (из bandwidth) |
| media_type | Точный (от трансивера) | Пустой или bare indicator | "unknown" обычно |
| Определяет port_type | media_type (приоритет 1) | hardware_type или имя | "lag" (по имени) |
| bandwidth | Не используется | **Не используется** | **Используется!** (сумма members) |

---

## Ключевые ловушки (почему были баги)

### Ловушка 1: NX-OS "media type is 10G" — это НЕ тип трансивера

NX-OS `show interfaces` для DOWN-порта:
```
Hardware: 100/1000/10000/25000 Ethernet    ← порт до 25G
auto-speed, media type is 10G              ← это НЕ трансивер, это дефолт
```

`"10G"` — это bare speed indicator. Если его принять за media_type:
- `detect_port_type()` → media `"10g"` → port_type `"10g-sfp+"` (10G)
- Но hardware `"100/1000/10000/25000"` → port_type `"25g-sfp28"` (25G) ← правильно!

**Решение:** bare speed indicators (`"10g"`, `"25g"`, `"1g"` и т.д.) пропускаются в `detect_port_type()`. Реальные media_type трансиверов содержат "base", "sfp" и т.д. (`"SFP-10GBase-SR"`).

### Ловушка 2: _parse_speed() и форматы разных платформ

| Платформа | Формат UP-порта | Если не обработать |
|-----------|----------------|-------------------|
| NX-OS | `"10 Gb/s"` | `int("10")` = **10 Kbps** (вместо 10G!) |
| Cisco IOS | `"1000Mb/s"` | `int("1000Mb/s")` = **ValueError → None** |
| QTech | `"10G"` | `int("10G")` = **ValueError → None** |
| DOWN (все) | `"1000000 Kbit"` | Работает корректно |

**Решение:** regex-паттерны в `_parse_speed()`:
```python
# Порядок проверки:
"kbit" → стандартный формат (down-порты)
"gbit" → "1 Gbit" формат
"mbit" → "100 Mbit" формат
regex r"(\d+)\s*(gb/s|gb|g)\b" → NX-OS "10 Gb/s", QTech "10G"
regex r"(\d+)\s*(mb/s|mb|m)\b" → IOS "1000Mb/s"
голое число → предполагаем Kbps
```

### Ловушка 3: bandwidth ≠ speed

`bandwidth` (BW) — это сконфигурированная полоса для QoS. Для down GigE на некоторых моделях:
```
BW 10000 Kbit/sec   ← 10 Mbps! Это НЕ скорость порта 1G!
```

Если маппить `bandwidth → speed` (через UNIVERSAL_FIELD_MAP), down GigE получит 10 Mbps вместо 1G.

**Решение:** bandwidth **никогда** не используется для speed.

### Ловушка 4: LAG speed ≠ member speed

Port-channel с 4×1G members:
```
BW 4000000 Kbit/sec              ← агрегатная скорость (4G = 4 × 1G)
Full-duplex, 1000Mb/s            ← скорость одного member-линка (1G)
Members: Gi1/0/1 Gi1/0/2 Gi1/0/3 Gi1/0/4
```

Если взять speed ("1000Mb/s") → NetBox получит 1G вместо 4G.

**Решение:** для LAG (port_type == "lag") берём bandwidth, а не speed:
```python
if result.get("port_type") == "lag" and result.get("bandwidth"):
    result["speed"] = result["bandwidth"]
```

Для обычных интерфейсов bandwidth по-прежнему **не используется** (ненадёжен для DOWN-портов).

### Ловушка 5: порядок паттернов в маппингах

Все маппинги с `if pattern in value` (поиск подстроки):
```python
# ❌ "basetx" матчит "10/100basetx" раньше "10/100":
"basetx": "1000base-t",     # перехватывает FastEthernet!
"10/100": "100base-tx",     # не достигается

# ✅ Специфичные перед общими:
"10/100": "100base-tx",     # матчит "10/100basetx" ПЕРВЫМ
"basetx": "1000base-t",     # только для generic
```

---

## Где живут маппинги (карта файлов)

```
core/constants/interfaces.py          ← port_type маппинги (domain layer)
├── MEDIA_TYPE_PORT_TYPE_MAP          media → port_type ("10gbase" → "10g-sfp+")
├── HARDWARE_TYPE_PORT_TYPE_MAP       hw → port_type ("100/1000/10000" → "10g-sfp+")
├── INTERFACE_NAME_PORT_TYPE_MAP      имя → port_type ("gigabit" → "1g-rj45")
├── _UNKNOWN_SPEED_VALUES             {"unknown", "auto", "auto-speed", ""}
└── get_nominal_speed_from_port_type  port_type → "X Kbit" ("10g-sfp+" → "10000000 Kbit")

core/constants/netbox.py              ← NetBox тип маппинги (sync layer)
├── NETBOX_INTERFACE_TYPE_MAP         media → NetBox ("10gbase-sr" → "10gbase-sr")
├── NETBOX_HARDWARE_TYPE_MAP          hw → NetBox ("fast ethernet" → "100base-tx")
├── PORT_TYPE_MAP                     port_type → NetBox ("10g-sfp+" → "10gbase-x-sfpp")
└── get_netbox_interface_type()       собирает всё вместе → финальный NetBox type

core/domain/interface.py              ← логика нормализации
├── detect_port_type()                media → hw → имя → port_type
└── _normalize_row()                  port_type + номинальная скорость

netbox/sync/base.py                   ← парсинг для API
└── _parse_speed()                    "10 Gb/s" → 10000000 Kbps

parsers/textfsm_parser.py            ← нормализация имён полей
└── UNIVERSAL_FIELD_MAP               "link_status" → "status"
```

---

## Два слоя маппингов — зачем

Это главный источник путаницы: **почему два набора маппингов?**

### Слой 1: port_type (domain layer)

```
"10g-sfp+"    "1g-rj45"    "25g-sfp28"    "100m-rj45"    "lag"    "virtual"
```

**Зачем:** универсальная категория, не привязанная к NetBox. Используется для:
- Номинальной скорости (`"10g"` → 10G, `"1g"` → 1G)
- Сортировки LAG перед member-портами
- Фильтрации виртуальных интерфейсов
- Передачи в sync layer как входной параметр

### Слой 2: NetBox type (sync layer)

```
"10gbase-x-sfpp"    "1000base-t"    "25gbase-x-sfp28"    "100base-tx"    "10gbase-sr"
```

**Зачем:** конкретный тип для NetBox API. Отличается от port_type:
- `media_type = "SFP-10GBase-SR"` → `"10gbase-sr"` (точный тип трансивера)
- `port_type = "10g-sfp+"` → `"10gbase-x-sfpp"` (generic SFP+)
- media_type даёт **точнее** результат, если есть трансивер

**Связь между ними:**

```
port_type "10g-sfp+"  ─── PORT_TYPE_MAP ───▶  "10gbase-x-sfpp"  (generic)
media "SFP-10GBase-SR" ── NETBOX_TYPE_MAP ──▶  "10gbase-sr"      (точный)
```

`get_netbox_interface_type()` проверяет media_type с **высшим приоритетом** и может дать более точный результат, чем PORT_TYPE_MAP.

---

## Примеры: полная цепочка

### Пример 1: Cisco IOS GigabitEthernet DOWN

```
show interfaces → speed=""  hw="Gigabit Ethernet"  media="10/100/1000BaseTX"

СЛОЙ 2 нормализация:
  detect_port_type():
    media "10/100/1000basetx" → не bare indicator → MEDIA_TYPE_PORT_TYPE_MAP
      "1000base" match → port_type = "1g-sfp" (можно спорить, но дальше исправится)
  speed "" IN _UNKNOWN_SPEED_VALUES → get_nominal("1g-sfp") = "1000000 Kbit"

СЛОЙ 3 sync:
  get_netbox_interface_type():
    media "10/100/1000basetx" → NETBOX_INTERFACE_TYPE_MAP
      "10/100/1000baset" match → type = "1000base-t" ✓
  _parse_speed("1000000 Kbit") → 1000000 Kbps = 1 Gbps ✓
```

### Пример 2: NX-OS Ethernet1/1 DOWN (25G hardware)

```
show interfaces → speed="auto-speed"  hw="100/1000/10000/25000 Ethernet"  media="10G"

СЛОЙ 2 нормализация:
  detect_port_type():
    media "10g" → IN bare indicators → ПРОПУСКАЕМ ✓
    hw "100/1000/10000/25000 ethernet" → HARDWARE_TYPE_PORT_TYPE_MAP
      "100/1000/10000/25000" match → port_type = "25g-sfp28" ✓
  speed "auto-speed" IN _UNKNOWN_SPEED_VALUES → get_nominal("25g-sfp28") = "25000000 Kbit"

СЛОЙ 3 sync:
  get_netbox_interface_type():
    port_type "25g-sfp28" → PORT_TYPE_MAP → "25gbase-x-sfp28" ✓
  _parse_speed("25000000 Kbit") → 25000000 Kbps = 25 Gbps ✓
```

### Пример 3: NX-OS Ethernet1/43 UP (10G линк)

```
show interfaces → speed="10 Gb/s"  hw="100/1000/10000 Ethernet"  media=""

СЛОЙ 2 нормализация:
  detect_port_type():
    media пустой → пропуск
    hw "100/1000/10000 ethernet" → port_type = "10g-sfp+"
  speed "10 Gb/s" NOT IN _UNKNOWN_SPEED_VALUES → оставляем как есть

СЛОЙ 3 sync:
  get_netbox_interface_type():
    port_type "10g-sfp+" → PORT_TYPE_MAP → "10gbase-x-sfpp" ✓
  _parse_speed("10 Gb/s"):
    regex r"(\d+)\s*(gb/s)" → group(1)="10" * 1000000 = 10000000 Kbps ✓
```

### Пример 4: FastEthernet DOWN

```
show interfaces → speed=""  hw="Fast Ethernet"  media="10/100BaseTX"

СЛОЙ 2 нормализация:
  detect_port_type():
    media "10/100basetx" → нет match в MEDIA_TYPE_PORT_TYPE_MAP
    hw "fast ethernet" → нет match в HARDWARE_TYPE_PORT_TYPE_MAP
    имя "fastethernet0/1" → INTERFACE_NAME_PORT_TYPE_MAP
      "fastethernet" match → port_type = "100m-rj45" ✓
  speed "" → get_nominal("100m-rj45") = "100000 Kbit"

СЛОЙ 3 sync:
  get_netbox_interface_type():
    media "10/100basetx" → NETBOX_INTERFACE_TYPE_MAP
      "100baset" match → "100base-tx" ✓   (не "basetx"! порядок важен)
  _parse_speed("100000 Kbit") → 100000 Kbps = 100 Mbps ✓
```

### Пример 5: Cisco IOS Port-channel (LAG 4×1G)

```
show interfaces → speed="1000Mb/s"  bandwidth="4000000 Kbit"  hw="EtherChannel"

СЛОЙ 2 нормализация:
  detect_port_type():
    имя "port-channel1" → is_lag_name() → port_type = "lag"
  LAG? Да → speed = bandwidth = "4000000 Kbit" ✓

СЛОЙ 3 sync:
  get_netbox_interface_type():
    port_type "lag" → type = "lag" ✓
  _parse_speed("4000000 Kbit") → 4000000 Kbps = 4 Gbps ✓
```

### Пример 6: QTech TFGigabitEthernet DOWN (25G, нет трансивера)

```
show interfaces → speed="Unknown"  hw=""  media=""

СЛОЙ 2 нормализация:
  detect_port_type():
    media пустой → пропуск
    hw пустой → пропуск
    имя "tfgigabitethernet0/3" → port_type = "25g-sfp28" ✓
  speed "unknown" → get_nominal("25g-sfp28") = "25000000 Kbit"

СЛОЙ 3 sync:
  get_netbox_interface_type():
    port_type "25g-sfp28" → PORT_TYPE_MAP → "25gbase-x-sfp28" ✓
  _parse_speed("25000000 Kbit") → 25000000 Kbps = 25 Gbps ✓
```

---

## Добавление нового устройства/платформы

### Если платформа уже поддерживается (Cisco IOS, NX-OS, QTech)

Ничего делать не нужно. Добавляешь устройство в `devices_ips.py` и запускаешь sync — всё работает автоматически.

### Если новый тип порта (например 2.5G)

**Шаг 1:** Определи исходные данные — что устройство отдаёт в `show interfaces`:
```bash
python -m network_collector interfaces --format parsed --host 10.0.0.1
```

Посмотри: speed, hardware_type, media_type для нового типа порта.

**Шаг 2:** Добавь в маппинги (от 2 до 6 записей):

```python
# core/constants/interfaces.py — port_type маппинги
HARDWARE_TYPE_PORT_TYPE_MAP["2500"] = "2.5g-rj45"       # если hw содержит "2500"
INTERFACE_NAME_PORT_TYPE_MAP["twodotfivegige"] = "2.5g-rj45"  # если новый префикс

# core/constants/netbox.py — NetBox маппинги
PORT_TYPE_MAP["2.5g-rj45"] = "2.5gbase-t"               # port_type → NetBox
NETBOX_HARDWARE_TYPE_MAP["2500"] = "2.5gbase-t"          # hw → NetBox
```

**Шаг 3:** Проверь номинальную скорость:
```python
get_nominal_speed_from_port_type("2.5g-rj45")
# "2.5g" → int("2.5") → ValueError!  Нужен float
```
Если `int()` не работает для нового префикса — обнови `get_nominal_speed_from_port_type()`.

**Шаг 4:** Проверь `_parse_speed()` — если платформа отдаёт speed в новом формате, добавь regex.

**Шаг 5:** Тесты:
```bash
pytest tests/ -v -k "port_type or interface_type"
```

### Если новая платформа целиком

1. Добавь TextFSM шаблон в `templates/`
2. Добавь платформу в `core/constants/platforms.py`
3. Собери `show interfaces` с реального устройства
4. Посмотри формат speed для UP и DOWN портов
5. Добавь regex в `_parse_speed()` если формат новый
6. Добавь маппинги hw/media в `core/constants/interfaces.py` и `netbox.py`
7. Протестируй: `python -m network_collector interfaces --format parsed --host X`

---

## Чеклист: как проверить что порт определился правильно

```bash
# 1. Собери данные с устройства
python -m network_collector interfaces --format parsed --host 10.0.0.1

# 2. Проверь port_type и speed в выводе
# Ожидание: port_type="10g-sfp+", speed="10000000 Kbit" (или "10 Gb/s" для UP)

# 3. Dry-run sync
python -m network_collector sync-netbox --interfaces --device HOSTNAME --dry-run

# 4. Посмотри что sync хочет изменить:
#    ~ HOSTNAME: Ethernet1/1 (type: 10gbase-x-sfpp, speed: 10000000) ← ожидаемо
#    ~ HOSTNAME: Ethernet1/1 (speed: 10000000 → 10)                  ← ПРОБЛЕМА!
```

Если speed/type неправильные — ищи причину по слоям:
1. **Сырые данные:** `--format parsed` покажет что вернул TextFSM
2. **Нормализация:** port_type в выводе — проверь какой маппинг сработал
3. **Sync:** `--dry-run` покажет что пойдёт в NetBox API

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
| [BUGFIX_LOG.md Баги 22-26](../BUGFIX_LOG.md) | История багов speed и port_type |
