# 14. Маппинг имён интерфейсов

**Время чтения:** ~35 мин

**Что узнаешь:**
- Почему один интерфейс может называться по-разному
- Как работает система нормализации имён
- Как маппинги используются на каждом слое (collector → domain → sync → NetBox API)
- Python-концепции: List[tuple] с порядком, dict vs set, startswith, replace

**Файл с кодом:** `core/constants/interfaces.py`

---

## 1. Проблема: один интерфейс — много имён

Сетевое оборудование возвращает имена интерфейсов в **разных форматах** в зависимости от команды, платформы и даже прошивки:

```
Одна и та же физическая розетка на коммутаторе:

show interfaces        → "GigabitEthernet0/1"     (полное имя)
show interfaces status → "Gi0/1"                  (короткое имя)
show cdp neighbors     → "Gig 0/1"                (CDP формат с пробелом)

QTech 10G порт:
show interface         → "TFGigabitEthernet0/1"   (полное имя)
show interface status  → "TF0/1"                  (короткое)

QTech LAG:
show aggregatePort     → "Ag1"                    (короткое)
show interface         → "AggregatePort 1"         (полное с пробелом!)

NX-OS:
show interface         → "Ethernet1/1"             (полное)
show interface status  → "Eth1/1"                  (короткое)
```

### Почему это проблема

Мы собираем данные из **нескольких команд** и объединяем их. Если команда `show interfaces` вернула `"GigabitEthernet0/1"`, а команда `show interfaces status` вернула `"Gi0/1"` — это **один и тот же** интерфейс. Но Python этого не знает:

```python
# Данные из show interfaces
interfaces = {"GigabitEthernet0/1": {"status": "up", "speed": "1000"}}

# Данные из show interfaces status (другая команда — другой формат)
media_types = {"Gi0/1": "10/100/1000BaseTX"}

# Пытаемся объединить:
for name, intf in interfaces.items():
    intf["media_type"] = media_types.get(name, "")
    # name = "GigabitEthernet0/1"
    # media_types.get("GigabitEthernet0/1") → "" ← НЕ НАЙДЕНО!
    # А данные лежат под ключом "Gi0/1"
```

Результат: интерфейс без `media_type`. Тип порта определится неправильно.

---

## 2. Решение: два маппинга + три функции

Вся система нормализации живёт в одном файле: `core/constants/interfaces.py`.

### 2.1. INTERFACE_SHORT_MAP — сокращение имён

```python
# List[tuple]: (полное_имя_lowercase, короткое)
# Порядок ВАЖЕН! Длинные паттерны первыми
INTERFACE_SHORT_MAP: List[tuple] = [
    ("twentyfivegigabitethernet", "Twe"),   # 25G
    ("twentyfivegige", "Twe"),              # 25G (альтернативное)
    ("hundredgigabitethernet", "Hu"),        # 100G
    ("hundredgige", "Hu"),                   # 100G (альтернативное)
    ("fortygigabitethernet", "Fo"),           # 40G
    ("tfgigabitethernet", "TF"),             # QTech 10G
    ("tengigabitethernet", "Te"),             # 10G
    ("gigabitethernet", "Gi"),               # 1G
    ("fastethernet", "Fa"),                  # 100M
    ("aggregateport", "Ag"),                 # QTech LAG
    ("ethernet", "Eth"),                     # NX-OS
    ("port-channel", "Po"),                  # Cisco LAG
    ("vlan", "Vl"),                          # VLAN интерфейсы
    ("loopback", "Lo"),                      # Loopback
    ("eth", "Eth"),                          # Уже короткое — не менять
    ("twe", "Twe"),                          # Уже короткое
    ("ten", "Te"),                           # CDP формат (Ten 1/1/4)
]
```

**Python-концепция: List[tuple] с важным порядком**

Почему `List[tuple]`, а не `Dict`? Потому что **порядок проверки критичен**.

Представь, что маппинг был бы `Dict`:

```python
# Плохо — dict не гарантирует порядок проверки
MAP = {
    "ethernet": "Eth",           # ← проверится первым?
    "tengigabitethernet": "Te",  # ← или этот?
    "gigabitethernet": "Gi",
}

# Если "ethernet" проверится раньше "tengigabitethernet":
# "TenGigabitEthernet1/1" → startswith("ethernet") → False ← OK (тут нет проблемы)
# Но:
# "ethernet1/1" → startswith("ethernet") → True → "Eth1/1" ← OK
```

На самом деле для `startswith` проблема возникает с вложенными префиксами:

```python
"gigabitethernet" — это подстрока для проверки startswith
"tengigabitethernet" — содержит "gigabitethernet"

# Если "gigabitethernet" проверится РАНЬШЕ "tengigabitethernet":
name = "tengigabitethernet1/1"
name.startswith("gigabitethernet")  # → False (не начинается с "gigabitethernet")
# Тут OK, потому что startswith проверяет с начала строки

# Но вот проблема:
name = "gigabitethernet0/1"
# Если "ethernet" проверится раньше "gigabitethernet":
name.startswith("ethernet")  # → False (начинается с "gi...")
# Тоже OK...
```

На самом деле проблема с порядком актуальна для `"twentyfivegige"` vs `"twentyfivegigabitethernet"`:

```python
name = "twentyfivegigabitethernet1/0/27"

# Если "twentyfivegige" проверится РАНЬШЕ:
name.startswith("twentyfivegige")  # → True! (начинается с "twentyfivegige...")
# Результат: "Twe" + "thabitethernet1/0/27" = "Twebitethernet1/0/27" — МУСОР!

# Поэтому "twentyfivegigabitethernet" ДОЛЖЕН быть первым:
name.startswith("twentyfivegigabitethernet")  # → True
# Результат: "Twe" + "1/0/27" = "Twe1/0/27" ← ПРАВИЛЬНО
```

Правило: **длинные паттерны первыми**, чтобы более специфичные совпадения имели приоритет.

---

### 2.2. INTERFACE_FULL_MAP — расширение имён

```python
# Dict: короткое → полное
INTERFACE_FULL_MAP: Dict[str, str] = {
    "Gi": "GigabitEthernet",
    "Fa": "FastEthernet",
    "Te": "TenGigabitEthernet",
    "TF": "TFGigabitEthernet",    # QTech 10G
    "Twe": "TwentyFiveGigE",
    "Fo": "FortyGigabitEthernet",
    "Hu": "HundredGigE",
    "Eth": "Ethernet",
    "Et": "Ethernet",             # Et → Ethernet (оба варианта)
    "Ag": "AggregatePort",        # QTech LAG
    "Po": "Port-channel",
    "Vl": "Vlan",
    "Lo": "Loopback",
}
```

Здесь `Dict` подходит — порядок проверки не критичен, потому что ключи — короткие формы, и они не пересекаются (`"Gi"` не является префиксом `"Gig"`... ну, на самом деле является, но `startswith("Gi")` для `"Gi0/1"` и `startswith("Gig")` для `"Gig0/1"` — это разные строки).

Безопасность обеспечивается дополнительной проверкой — символ после аббревиатуры должен быть **цифрой**:

```python
# Gi0/1 → за "Gi" идёт "0" (цифра) → ОК, расширяем
# GigabitEthernet0/1 → за "Gi" идёт "g" (буква) → НЕ расширяем
```

---

### 2.3. normalize_interface_short() — сокращение

```python
def normalize_interface_short(interface: str, lowercase: bool = False) -> str:
    """GigabitEthernet0/1 → Gi0/1"""
    result = interface.replace(" ", "").strip()  # Убираем пробелы
    result_lower = result.lower()

    for full_lower, short in INTERFACE_SHORT_MAP:
        if result_lower.startswith(full_lower):
            result = short + result[len(full_lower):]
            break  # Нашли — выходим (порядок маппинга гарантирует правильность)

    return result.lower() if lowercase else result
```

**Python-концепция: `str.replace(" ", "")` для нормализации**

Пробелы убираются сразу, потому что CDP/LLDP часто добавляет пробел:
```python
"Ten 1/1/4".replace(" ", "")  # → "Ten1/1/4"
"AggregatePort 1".replace(" ", "")  # → "AggregatePort1"
```

**Python-концепция: срез строки `result[len(full_lower):]`**

Это ключ к замене — берём всё после совпавшей части:
```python
result = "gigabitethernet0/1"
full_lower = "gigabitethernet"
short = "Gi"

result[len(full_lower):]  # "gigabitethernet0/1"[15:] → "0/1"
short + result[len(full_lower):]  # "Gi" + "0/1" → "Gi0/1"
```

**Python-концепция: `break` в цикле**

`break` останавливает цикл после первого совпадения. Без него:
```python
# "tengigabitethernet1/1" совпадёт с "tengigabitethernet" → "Te1/1"
# Без break: цикл продолжится, "ten" тоже совпадёт с "te1/1" → повторная замена!
```

---

### 2.4. normalize_interface_full() — расширение

```python
def normalize_interface_full(interface: str) -> str:
    """Gi0/1 → GigabitEthernet0/1"""
    # Убираем пробелы между типом и номером
    # QTech: "TFGigabitEthernet 0/48" → "TFGigabitEthernet0/48"
    interface = interface.replace(" ", "").strip()

    for short_name, full_name in INTERFACE_FULL_MAP.items():
        if (
            interface.startswith(short_name)       # Начинается с сокращения
            and not interface.startswith(full_name) # НЕ уже полное имя
            and len(interface) > len(short_name)    # Есть что-то после сокращения
            and interface[len(short_name)].isdigit() # После сокращения — цифра
        ):
            return interface.replace(short_name, full_name, 1)
    return interface
```

> **Важно:** `.replace(" ", "")` добавлен по аналогии с `normalize_interface_short()`. QTech возвращает имена с пробелом (`TFGigabitEthernet 0/48`), а в NetBox они хранятся без пробела. Без этой нормализации `_find_interface()` не находил интерфейсы при синхронизации кабелей (LLDP).

**Python-концепция: `str.replace(old, new, 1)` — замена только первого вхождения**

Третий аргумент `1` — максимальное количество замен:
```python
"Po1".replace("Po", "Port-channel", 1)  # → "Port-channel1"
# Без count=1:
"Po1Po2".replace("Po", "Port-channel")  # → "Port-channel1Port-channel2" (обе!)
```

**Python-концепция: четыре условия в `if`**

Каждое условие предотвращает конкретную ошибку:

```python
interface = "GigabitEthernet0/1"
short_name = "Gi"

interface.startswith("Gi")                    # True — начинается с "Gi"
not interface.startswith("GigabitEthernet")   # False! — уже полное имя
# → Условие НЕ выполняется → не расширяем (правильно!)

interface = "Gi0/1"
interface.startswith("Gi")                    # True
not interface.startswith("GigabitEthernet")   # True — не полное
len(interface) > len("Gi")                     # True — есть "0/1"
interface[len("Gi")].isdigit()                 # "0".isdigit() → True
# → Все условия True → расширяем: "GigabitEthernet0/1"

interface = "Gig0/1"  # Cisco CDP формат
interface.startswith("Gi")                    # True
not interface.startswith("GigabitEthernet")   # True
interface[len("Gi")].isdigit()                 # "g".isdigit() → False!
# → Не расширяем (правильно! "Gig" — это не "Gi")
```

---

### 2.5. get_interface_aliases() — все варианты имени

Это **главная рабочая лошадка** — генерирует все возможные формы написания:

```python
def get_interface_aliases(interface: str) -> List[str]:
    """Возвращает все варианты написания интерфейса."""
    aliases = {interface}          # set — для автоматической уникальности
    clean = interface.replace(" ", "")
    aliases.add(clean)

    # Короткая форма
    short = normalize_interface_short(clean)
    if short != clean:
        aliases.add(short)

    # Полная форма
    full = normalize_interface_full(clean)
    if full != clean:
        aliases.add(full)

    # Дополнительные альтернативные сокращения
    EXTRA_ALIASES = {
        "gigabitethernet": ["Gig"],       # Cisco CDP формат
        "tengigabitethernet": ["Ten"],    # Cisco CDP формат
        "ethernet": ["Et", "Eth"],        # NX-OS оба варианта
    }

    for prefix, extras in EXTRA_ALIASES.items():
        if clean.lower().startswith(prefix):
            suffix = clean[len(prefix):]
            for extra in extras:
                aliases.add(f"{extra}{suffix}")

    # Обратные маппинги для коротких форм
    SHORT_TO_EXTRA = {
        "gi": ["Gig"],
        "te": ["Ten"],
        "hu": ["HundredGigabitEthernet"],
        "eth": ["Et"],
        "et": ["Eth"],
    }

    for short_prefix, extras in SHORT_TO_EXTRA.items():
        if clean.lower().startswith(short_prefix) and len(clean) > len(short_prefix):
            if clean[len(short_prefix)].isdigit():
                suffix = clean[len(short_prefix):]
                for extra in extras:
                    aliases.add(f"{extra}{suffix}")

    return list(aliases)
```

**Пример результата:**

```python
get_interface_aliases("GigabitEthernet0/1")
# → ["GigabitEthernet0/1", "Gi0/1", "Gig0/1"]

get_interface_aliases("Gi0/1")
# → ["Gi0/1", "GigabitEthernet0/1", "Gig0/1"]

get_interface_aliases("Ag1")
# → ["Ag1", "AggregatePort1"]

get_interface_aliases("AggregatePort 1")
# → ["AggregatePort 1", "AggregatePort1", "Ag1"]

get_interface_aliases("Eth1/1")
# → ["Eth1/1", "Ethernet1/1", "Et1/1"]
```

**Python-концепция: set для автоматической уникальности**

```python
aliases = {interface}  # set, не list!
aliases.add("Gi0/1")
aliases.add("Gi0/1")  # Дубликат — set проигнорирует
aliases.add("GigabitEthernet0/1")

# Когда добавляем из нескольких источников (short, full, extra),
# некоторые пути могут дать один результат. set автоматически дедуплицирует.

return list(aliases)  # Конвертируем в list для вызывающего кода
```

**Почему `set`, а потом `list`?**
- `set` — удобно для добавления (`.add()` игнорирует дубликаты)
- `list` — удобно для вызывающего кода (индексация, итерация)

---

## 3. Где маппинги используются

Маппинги — это сквозной механизм. Они используются на **всех слоях** приложения.

### 3.1. Общий паттерн: "словарь алиасов"

Паттерн один и тот же во всех местах:

```python
# 1. Получаем данные из команды (одно имя)
data = {"Gi0/1": "some_value"}

# 2. Генерируем ВСЕ варианты и записываем тот же value
for alias in get_interface_aliases("Gi0/1"):
    data[alias] = "some_value"

# Результат:
# data = {
#     "Gi0/1": "some_value",
#     "GigabitEthernet0/1": "some_value",
#     "Gig0/1": "some_value",
# }

# 3. Теперь ЛЮБАЯ другая команда найдёт данные по любому формату имени
data.get("GigabitEthernet0/1")  # → "some_value" ← найдено!
data.get("Gi0/1")               # → "some_value" ← найдено!
data.get("Gig0/1")              # → "some_value" ← найдено!
```

**Python-концепция: разделяемая ссылка (reference sharing)**

Важный момент — все алиасы указывают на **один и тот же объект** в памяти:

```python
mode_data = {"mode": "access", "native_vlan": "1"}

modes["Gi0/1"] = mode_data
modes["GigabitEthernet0/1"] = mode_data  # Та же ссылка, не копия!

# mode_data создаётся ОДИН раз, все ключи указывают на него
# id(modes["Gi0/1"]) == id(modes["GigabitEthernet0/1"]) → True

# Это экономит память: не 3 копии словаря, а 3 ссылки на один
```

---

### 3.2. Collector: LAG membership

**Файл:** `collectors/interfaces.py`
**Метод:** `_add_lag_member_aliases()`

Когда парсим `show etherchannel summary`, получаем привязку member → LAG:

```python
def _add_lag_member_aliases(self, membership, member, lag_name):
    """Добавляет member и все его алиасы в LAG membership dict."""
    membership[member] = lag_name

    # Все алиасы из constants
    for alias in get_interface_aliases(member):
        membership[alias] = lag_name
        # QTech формат: пробел перед номером ("HundredGigabitEthernet 0/55")
        spaced = re.sub(r'(\D)(\d)', r'\1 \2', alias, count=1)
        if spaced != alias:
            membership[spaced] = lag_name
```

**Зачем:** `show etherchannel summary` возвращает `"Gi0/1"`, а `show interfaces` возвращает `"GigabitEthernet0/1"`. При обогащении интерфейсов нужно найти LAG для `"GigabitEthernet0/1"` → ищем в `membership["GigabitEthernet0/1"]` → находим, потому что записали алиас.

```
show etherchannel summary → "Gi0/1" в Port-channel1
                             ↓
_add_lag_member_aliases("Gi0/1", "Port-channel1")
                             ↓
membership = {
    "Gi0/1": "Port-channel1",
    "GigabitEthernet0/1": "Port-channel1",    ← алиас
    "Gig0/1": "Port-channel1",                ← алиас
}
                             ↓
show interfaces → "GigabitEthernet0/1"
                             ↓
membership.get("GigabitEthernet0/1") → "Port-channel1" ← НАЙДЕНО!
```

---

### 3.3. Collector: media types

**Файл:** `collectors/interfaces.py`
**Метод:** `_enrich_media_types()`

`show interfaces status` возвращает тип физического порта:

```python
# NTC парсер возвращает: port="Gi0/1", type="10/100/1000BaseTX"
for alias in get_interface_aliases(port):
    media_types[alias] = media_type

# media_types = {
#     "Gi0/1": "10/100/1000BaseTX",
#     "GigabitEthernet0/1": "10/100/1000BaseTX",   ← алиас
#     "Gig0/1": "10/100/1000BaseTX",               ← алиас
# }
```

**Зачем:** позже `detect_port_type()` ищет `media_type` по полному имени интерфейса, который пришёл из `show interfaces`.

---

### 3.4. Collector: MAC статус портов

**Файл:** `collectors/mac.py`
**Метод:** `_add_status_for_aliases()`

```python
def _add_status_for_aliases(self, status_map, iface, status):
    """Добавляет статус для всех вариантов имени."""
    for alias in get_interface_aliases(iface):
        status_map[alias] = status
```

**Зачем:** MAC collector фильтрует порты по статусу (up/down). `show interfaces status` возвращает `"Gi0/1"`, а MAC таблица содержит `"GigabitEthernet0/1"` — алиасы обеспечивают совпадение.

---

### 3.5. Collector: trunk порты

**Файл:** `collectors/mac.py`
**Метод:** `_parse_trunk_interfaces_from_output()`

```python
if re.match(r"^(Gi|Fa|Te|Eth|Po)", iface, re.IGNORECASE):
    trunk_interfaces.update(get_interface_aliases(iface))
```

**Python-концепция: `set.update()` vs `set.add()`**

```python
trunk_interfaces = set()

# add — добавляет ОДИН элемент
trunk_interfaces.add("Gi0/1")  # {"Gi0/1"}

# update — добавляет ВСЕ элементы из iterable
trunk_interfaces.update(["Gi0/1", "GigabitEthernet0/1", "Gig0/1"])
# {"Gi0/1", "GigabitEthernet0/1", "Gig0/1"}

# update(list) = множественный add за один вызов
```

---

### 3.6. Domain: switchport modes

**Файл:** `core/domain/interface.py`
**Метод:** `normalize_switchport_data()`

После парсинга switchport данных, каждый mode записывается под всеми алиасами:

```python
mode_data = {
    "mode": netbox_mode,
    "native_vlan": str(native_vlan) if native_vlan else "",
    "access_vlan": str(access_vlan) if access_vlan else "",
    "tagged_vlans": trunking_vlans if netbox_mode == "tagged" else "",
}
modes[iface] = mode_data

# Добавляем альтернативные имена через единый источник
for alias in get_interface_aliases(iface):
    if alias != iface:
        modes[alias] = mode_data
```

---

### 3.7. Domain: enrichment — поиск по алиасам

**Файл:** `core/domain/interface.py`
**Метод:** `enrich_with_switchport()`

Обратная сторона — при поиске switchport mode для интерфейса, если точное имя не найдено, пробуем алиасы:

```python
sw_data = None
if iface_name in switchport_modes:
    sw_data = switchport_modes[iface_name]
else:
    # Пробуем все варианты написания имени
    for variant in get_interface_aliases(iface_name):
        if variant in switchport_modes:
            sw_data = switchport_modes[variant]
            break
```

**Двойная защита:** алиасы добавляются и при **записи** (3.6), и при **чтении** (3.7). Это гарантирует совпадение даже если одна из сторон пропустила какой-то формат.

---

### 3.8. Sync: нормализация для кэша

**Файл:** `netbox/sync/base.py`
**Метод:** `_normalize_interface_name()`

```python
def _normalize_interface_name(self, name):
    """Нормализует имя для сравнения."""
    name = normalize_interface_full(name.strip())
    return name.lower()
```

**Зачем:** когда sync ищет интерфейс в кэше NetBox, имена приводятся к единому формату:
```python
# В кэше:    "GigabitEthernet0/1" (как в NetBox)
# Ищем:      "Gi0/1" (как из коллектора)
# normalize: "Gi0/1" → "GigabitEthernet0/1" → "gigabitethernet0/1"
# В кэше:    "GigabitEthernet0/1" → "gigabitethernet0/1"
# Совпадение!
```

---

### 3.9. NetBox API: поиск LAG интерфейса

**Файл:** `netbox/client/interfaces.py`
**Метод:** `get_interface_by_name()`

Трёхшаговый поиск с нарастающей "размытостью":

```python
def get_interface_by_name(self, device_id, interface_name):
    # Шаг 1: Точное совпадение
    interfaces = list(self.api.dcim.interfaces.filter(
        device_id=device_id, name=interface_name))
    if interfaces:
        return interfaces[0]

    # Шаг 2: Нормализованное имя (Ag1 → AggregatePort1)
    normalized = normalize_interface_full(interface_name)
    if normalized != interface_name:
        interfaces = list(self.api.dcim.interfaces.filter(
            device_id=device_id, name=normalized))
        if interfaces:
            return interfaces[0]

    # Шаг 3: Case-insensitive (для LAG)
    if interface_name.lower().startswith(("po", "port-channel", "ag", "aggregateport")):
        all_interfaces = list(self.api.dcim.interfaces.filter(device_id=device_id))
        name_lower = normalized.lower()
        for intf in all_interfaces:
            if intf.name.lower() == name_lower:
                return intf

    return None
```

**Зачем 3 шага:**

```
Шаг 1: filter(name="Ag1")           → нет (в NetBox "AggregatePort1")
Шаг 2: normalize → "AggregatePort1"
        filter(name="AggregatePort1") → нет (в NetBox "aggregateport1" — другой регистр!)
Шаг 3: Загружаем все, сравниваем .lower() → НАШЛИ!
```

Шаг 3 — "тяжёлый" (загружает все интерфейсы устройства), поэтому используется только для LAG.

---

## 4. Полная схема: как алиасы связывают данные

```
Команда 1: show interfaces status
  Парсер: port="Gi0/1", type="10/100/1000BaseTX"
    ↓
  get_interface_aliases("Gi0/1")
    ↓
  media_types = {
    "Gi0/1": "10/100/1000BaseTX",
    "GigabitEthernet0/1": "10/100/1000BaseTX",
    "Gig0/1": "10/100/1000BaseTX",
  }

Команда 2: show interfaces
  Парсер: interface="GigabitEthernet0/1", status="up"
    ↓
  Enrichment:
    media_types.get("GigabitEthernet0/1") → "10/100/1000BaseTX" ← НАЙДЕНО через алиас!
    ↓
  Interface(name="GigabitEthernet0/1", media_type="10/100/1000BaseTX")
    ↓
  detect_port_type() → анализирует media_type → port_type="1g-rj45"

Команда 3: show etherchannel summary
  Парсер: member="Gi0/1", lag="Port-channel1"
    ↓
  _add_lag_member_aliases("Gi0/1", "Port-channel1")
    ↓
  membership = {"Gi0/1": "Po1", "GigabitEthernet0/1": "Po1", ...}
    ↓
  Enrichment:
    membership.get("GigabitEthernet0/1") → "Port-channel1" ← НАЙДЕНО через алиас!
    ↓
  Interface(name="GigabitEthernet0/1", lag="Port-channel1")

Команда 4: show interface switchport
  Парсер: interface="Gi0/1", mode="access"
    ↓
  normalize_switchport_data():
    modes["Gi0/1"] = {"mode": "access", ...}
    for alias in get_interface_aliases("Gi0/1"):
        modes[alias] = {"mode": "access", ...}
    ↓
  enrich_with_switchport():
    switchport_modes.get("GigabitEthernet0/1") → {"mode": "access"} ← НАЙДЕНО!
    ↓
  Interface(name="GigabitEthernet0/1", mode="access")
```

**Ключевая идея:** каждая команда пишет данные под всеми алиасами, поэтому другие команды всегда найдут их, независимо от формата имени.

---

## 5. Как добавить новую платформу

Если новая платформа использует свой формат имён (например, `XPort0/1` — сокращение от `XtraPort0/1`):

### Шаг 1: Добавить в INTERFACE_SHORT_MAP

```python
INTERFACE_SHORT_MAP: List[tuple] = [
    # ... существующие ...
    ("xtraport", "XPort"),  # Новая платформа
]
```

**Правило порядка:** если новый префикс является подстрокой существующего (или наоборот), ставь длинный первым.

### Шаг 2: Добавить в INTERFACE_FULL_MAP

```python
INTERFACE_FULL_MAP: Dict[str, str] = {
    # ... существующие ...
    "XPort": "XtraPort",  # Новая платформа
}
```

### Шаг 3: Готово

Функции `normalize_interface_short()`, `normalize_interface_full()` и `get_interface_aliases()` автоматически подхватят новые маппинги. Все использования во всех слоях (collector, domain, sync, client) заработают без изменений.

### Шаг 4 (опционально): Дополнительные алиасы

Если у платформы есть альтернативный формат (как `Gig` для Cisco CDP), добавь в `EXTRA_ALIASES` или `SHORT_TO_EXTRA` внутри `get_interface_aliases()`.

---

## 6. Архитектурные принципы

### 6.1. Единый источник правды (Single Source of Truth)

Все маппинги определены в **одном файле** (`core/constants/interfaces.py`). Все слои импортируют и используют оттуда. Не дублируют.

```
core/constants/interfaces.py     ← ОПРЕДЕЛЕНИЕ
       ↓ import
  collectors/interfaces.py       ← использует get_interface_aliases()
  collectors/mac.py              ← использует get_interface_aliases()
  core/domain/interface.py       ← использует get_interface_aliases()
  netbox/sync/base.py            ← использует normalize_interface_full()
  netbox/client/interfaces.py    ← использует normalize_interface_full()
```

### 6.2. Подход "записать все + искать точно" vs "записать точно + искать все"

В проекте используются **оба** подхода:

**Запись алиасов (при создании словаря):**
```python
# Записываем value для КАЖДОГО алиаса
for alias in get_interface_aliases(port):
    media_types[alias] = media_type
# Потом ищем точно:
media_types.get("GigabitEthernet0/1")
```

**Поиск по алиасам (при чтении):**
```python
# Записали точно:
modes["Gi0/1"] = {"mode": "access"}
# Ищем по всем вариантам:
for variant in get_interface_aliases("GigabitEthernet0/1"):
    if variant in modes:
        return modes[variant]
```

В `enrich_with_switchport()` используются **оба** одновременно — двойная защита.

### 6.3. Баланс: память vs надёжность

Добавление алиасов в словарь увеличивает его размер в 3-5 раз по количеству ключей. Но:
- Значения — **ссылки**, не копии (экономия памяти)
- Интерфейсов на устройстве обычно 24-96 → словарь в 72-480 ключей → мизерный расход
- Надёжность сопоставления важнее нескольких килобайт памяти

---

## 7. `is_lag_name()` — определение LAG по имени

Помимо алиасов, в `core/constants/interfaces.py` есть функция для определения LAG:

```python
LAG_PREFIXES = ("port-channel", "po", "aggregateport", "ag")

def is_lag_name(interface: str) -> bool:
    """Проверяет, является ли интерфейс LAG по имени."""
    iface_lower = interface.lower().replace(" ", "")
    if iface_lower.startswith(("port-channel", "aggregateport")):
        return True
    for prefix in ("po", "ag"):
        if (iface_lower.startswith(prefix)
                and len(iface_lower) > len(prefix)
                and iface_lower[len(prefix)].isdigit()):
            return True
    return False
```

**Зачем отдельная функция?** Проверка "это LAG?" нужна в 3+ местах:
- `detect_port_type()` — чтобы вернуть `port_type="lag"`
- `enrich_with_switchport()` — чтобы определить mode LAG по member портам
- `get_netbox_interface_type()` — чтобы вернуть NetBox тип `"lag"`

Раньше каждое место содержало свою копию проверки (`startswith(("port-channel", "po"))` + отдельный блок для `"ag"`). Теперь — единый источник `is_lag_name()`.

**Для новой платформы:** если LAG называется не Port-channel и не AggregatePort — добавить один префикс в `is_lag_name()`.

---

## 8. Итоговая таблица: кто что использует

| Слой | Файл | Функция | Что делает |
|------|------|---------|------------|
| **Constants** | `core/constants/interfaces.py` | определение | Маппинги + 4 функции (включая `is_lag_name()`) |
| **Collector** | `collectors/interfaces.py` | `get_interface_aliases()` | Алиасы для LAG members |
| **Collector** | `collectors/interfaces.py` | `get_interface_aliases()` | Алиасы для media types |
| **Collector** | `collectors/mac.py` | `get_interface_aliases()` | Алиасы для статусов портов |
| **Collector** | `collectors/mac.py` | `get_interface_aliases()` | Алиасы для trunk портов |
| **Domain** | `core/domain/interface.py` | `get_interface_aliases()` | Алиасы для switchport modes |
| **Domain** | `core/domain/interface.py` | `get_interface_aliases()` | Fallback поиск при enrichment |
| **Sync** | `netbox/sync/base.py` | `normalize_interface_full()` | Нормализация для кэша |
| **Client** | `netbox/client/interfaces.py` | `normalize_interface_full()` | Поиск LAG в NetBox API |

---

## 9. Упражнения

### Упражнение 1: Предскажи результат

Что вернёт `get_interface_aliases()` для каждого вызова?

```python
get_interface_aliases("Te1/0/1")
get_interface_aliases("Port-channel1")
get_interface_aliases("AggregatePort 1")
```

<details>
<summary>Ответ</summary>

```python
get_interface_aliases("Te1/0/1")
# → ["Te1/0/1", "TenGigabitEthernet1/0/1", "Ten1/0/1"]

get_interface_aliases("Port-channel1")
# → ["Port-channel1", "Po1"]

get_interface_aliases("AggregatePort 1")
# → ["AggregatePort 1", "AggregatePort1", "Ag1"]
# "AggregatePort 1" → clean="AggregatePort1"
# short: "Ag1", full: уже полное → без изменений
```
</details>

### Упражнение 2: Найди баг

```python
INTERFACE_SHORT_MAP = [
    ("ethernet", "Eth"),
    ("tengigabitethernet", "Te"),
    ("gigabitethernet", "Gi"),
]

normalize_interface_short("TenGigabitEthernet1/1")
# Что вернёт?
```

<details>
<summary>Ответ</summary>

Вернёт `"Te1/1"` — правильно! Потому что `"tengigabitethernet"`.lower() не начинается с `"ethernet"`, а `"ethernet"` не совпадёт (startswith проверяет с начала строки).

Но если бы маппинг содержал `("ten", "Te")` ПЕРЕД `("tengigabitethernet", "Te")`:
```python
INTERFACE_SHORT_MAP = [
    ("ten", "Te"),                  # ← первый!
    ("tengigabitethernet", "Te"),
]
normalize_interface_short("TenGigabitEthernet1/1")
# "tengigabitethernet1/1".startswith("ten") → True!
# Результат: "Te" + "gigabitethernet1/1" = "Tegigabitethernet1/1" ← МУСОР!
```

Поэтому длинные паттерны ВСЕГДА первыми.
</details>

### Упражнение 3: Зачем set?

Почему `get_interface_aliases()` внутри использует `set`, а возвращает `list`?

<details>
<summary>Ответ</summary>

`set` автоматически убирает дубликаты. Разные пути нормализации могут дать одинаковый результат:

```python
interface = "Ethernet1/1"

clean = "Ethernet1/1"       # Совпадает с оригиналом → дубликат
short = "Eth1/1"            # Новый вариант
full = "Ethernet1/1"        # Совпадает с оригиналом → дубликат
extra_Et = "Et1/1"          # Новый
extra_Eth = "Eth1/1"        # Совпадает с short → дубликат

# Без set: ["Ethernet1/1", "Ethernet1/1", "Eth1/1", "Ethernet1/1", "Et1/1", "Eth1/1"]
# С set:   {"Ethernet1/1", "Eth1/1", "Et1/1"} → list: 3 элемента
```

Возвращает `list` потому что вызывающий код использует `for alias in aliases:` — list и set оба поддерживают итерацию, но list привычнее и предсказуемее (хотя тут порядок не важен).
</details>
