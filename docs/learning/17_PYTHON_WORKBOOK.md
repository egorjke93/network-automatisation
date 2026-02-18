# 17. Python Workbook — Практические задачи на примерах Network Collector

## Зачем этот документ

Ты уже прочитал код проекта, понимаешь структуру и паттерны. Теперь нужно перевести знания из режима "читаю и понимаю" в режим "пишу сам". Этот документ — набор задач возрастающей сложности, все на примерах реального кода проекта.

**Правила работы:**
1. Закрой ChatGPT/Claude. Открой только документацию Python (docs.python.org)
2. Пиши код сам, не копируй из проекта
3. Будет медленно и больно — это нормально
4. После решения — сравни с эталоном в конце каждого блока
5. Если застрял больше 20 минут — подсмотри подсказку, но потом допиши сам

**Структура:**
- Блок 1-3: базовые операции (строки, словари, списки) — **неделя 1**
- Блок 4-6: функции, regex и файлы — **неделя 2**
- Блок 7-9: классы, обработка ошибок и SyncComparator — **неделя 3**
- Блок 10-12: продвинутые паттерны — **неделя 4**
- Блок 13-15: мини-проекты — **неделя 5-6**

**Время на задачу:** 15-40 минут. Не торопись.

---

## Блок 1. Строки — нормализация сетевых данных

В сетевой автоматизации 80% работы — это приведение строк к единому формату. MAC-адреса приходят в разных форматах, имена интерфейсов — в сокращённых и полных формах, статусы — в произвольном регистре.

### Теория-напоминание

```python
# Базовые методы строк
s = "  Hello World  "
s.lower()          # "  hello world  "
s.strip()          # "Hello World"
s.replace("o", "0") # "  Hell0 W0rld  "
s.startswith("He")  # True (после strip)
s.split(" ")        # ['', '', 'Hello', 'World', '', '']

# Срезы (slicing)
s = "GigabitEthernet0/1"
s[:15]    # "GigabitEthernet"
s[15:]    # "0/1"
s[0]      # "G"
s[-1]     # "1"

# f-строки
name = "Gi0/1"
status = "up"
f"{name}: {status}"  # "Gi0/1: up"

# Проверки символов
"5".isdigit()   # True
"abc".isalpha() # True
```

---

### Задача 1.1. Нормализация MAC-адреса

**Контекст:** MAC-адреса приходят с устройств в разных форматах:
- Cisco IOS: `0011.2233.4455`
- Linux/LLDP: `00:11:22:33:44:55`
- Windows: `00-11-22-33-44-55`
- Иногда с пробелами и в верхнем регистре: ` 00:11:22:33:44:55 `

**Задание:** Напиши функцию `normalize_mac(mac)`, которая:
1. Убирает пробелы по краям
2. Переводит в нижний регистр
3. Убирает все разделители (`:`, `-`, `.`)
4. Возвращает чистую строку из 12 символов, например `"001122334455"`
5. Если на вход пришла пустая строка или None — возвращает `""`

```python
def normalize_mac(mac):
    # Твой код здесь
    pass

# Тесты — запусти и проверь
assert normalize_mac("00:11:22:33:44:55") == "001122334455"
assert normalize_mac("0011.2233.4455") == "001122334455"
assert normalize_mac("00-11-22-33-44-55") == "001122334455"
assert normalize_mac("  AA:BB:CC:DD:EE:FF  ") == "aabbccddeeff"
assert normalize_mac("") == ""
assert normalize_mac(None) == ""
print("Все тесты пройдены!")
```

**Подсказка (открой если застрял 15+ мин):**
> Используй цепочку `.replace()` для каждого разделителя. Для None проверь `if not mac`.

---

### Задача 1.2. Определение формата MAC-адреса

**Контекст:** Иногда нужно не нормализовать MAC, а определить, в каком формате он пришёл.

**Задание:** Напиши функцию `detect_mac_format(mac)`, которая возвращает:
- `"cisco"` — если формат `XXXX.XXXX.XXXX` (точки, группы по 4)
- `"unix"` — если формат `XX:XX:XX:XX:XX:XX` (двоеточия)
- `"windows"` — если формат `XX-XX-XX-XX-XX-XX` (дефисы)
- `"raw"` — если нет разделителей (12 символов подряд)
- `"unknown"` — всё остальное

```python
def detect_mac_format(mac):
    # Твой код здесь
    pass

# Тесты
assert detect_mac_format("0011.2233.4455") == "cisco"
assert detect_mac_format("00:11:22:33:44:55") == "unix"
assert detect_mac_format("00-11-22-33-44-55") == "windows"
assert detect_mac_format("001122334455") == "raw"
assert detect_mac_format("not a mac") == "unknown"
assert detect_mac_format("") == "unknown"
print("Все тесты пройдены!")
```

**Подсказка:**
> Проверяй наличие разделителя через `"." in mac`, `":" in mac`, `"-" in mac`. Для raw — проверь длину и `mac.isalnum()`.

---

### Задача 1.3. Нормализация статуса интерфейса

**Контекст:** Разные платформы возвращают статус в разном виде:
- Cisco: `"up"`, `"down"`, `"administratively down"`
- Arista: `"connected"`, `"notconnect"`, `"disabled"`
- QTech: `"UP"`, `"DOWN"`, `"ADMIN_DOWN"`

В проекте это решается через словарь `STATUS_MAP` (файл `core/domain/interface.py`).

**Задание:** Напиши функцию `normalize_status(raw_status)`:
1. Приведи к нижнему регистру и убери пробелы
2. Используй словарь маппинга для конвертации
3. Если статус не найден в маппинге — верни как есть
4. Если вход пустой или None — верни `"unknown"`

```python
STATUS_MAP = {
    "up": "up",
    "down": "down",
    "connected": "up",
    "notconnect": "down",
    "disabled": "down",
    "administratively down": "down",
    "admin_down": "down",
    "err-disabled": "down",
    "link-up": "up",
    "link-down": "down",
}

def normalize_status(raw_status):
    # Твой код здесь
    pass

# Тесты
assert normalize_status("up") == "up"
assert normalize_status("UP") == "up"
assert normalize_status("  Connected  ") == "up"
assert normalize_status("administratively down") == "down"
assert normalize_status("ADMIN_DOWN") == "down"
assert normalize_status("err-disabled") == "down"
assert normalize_status("some_new_status") == "some_new_status"
assert normalize_status("") == "unknown"
assert normalize_status(None) == "unknown"
print("Все тесты пройдены!")
```

**Подсказка:**
> `STATUS_MAP.get(key, default)` — вернёт default если ключа нет. Для "как есть" передай нормализованную строку как default.

---

### Задача 1.4. Сокращение имени интерфейса

**Контекст:** NetBox хранит полные имена (`GigabitEthernet0/1`), а устройства часто возвращают сокращённые (`Gi0/1`). Нужно уметь конвертировать в обе стороны. См. `core/constants/interfaces.py`.

**Задание:** Напиши функцию `shorten_interface(name)`, которая:
1. `"GigabitEthernet0/1"` → `"Gi0/1"`
2. `"FastEthernet0/1"` → `"Fa0/1"`
3. `"TenGigabitEthernet1/0/1"` → `"Te1/0/1"`
4. `"Port-channel1"` → `"Po1"`
5. `"Loopback0"` → `"Lo0"`
6. Если не знает префикс — вернёт как есть

**Важно:** Проверяй длинные префиксы ПЕРЕД короткими! Иначе `"TenGigabitEthernet"` поймается на `"Ethernet"`.

```python
# Список: (полное_имя_в_нижнем_регистре, сокращение)
# Порядок важен — длинные префиксы первыми!
INTERFACE_SHORT_MAP = [
    ("tengigabitethernet", "Te"),
    ("gigabitethernet", "Gi"),
    ("fastethernet", "Fa"),
    ("ethernet", "Eth"),
    ("port-channel", "Po"),
    ("loopback", "Lo"),
    ("vlan", "Vlan"),
    ("management", "Mgmt"),
]

def shorten_interface(name):
    # Твой код здесь
    pass

# Тесты
assert shorten_interface("GigabitEthernet0/1") == "Gi0/1"
assert shorten_interface("FastEthernet0/24") == "Fa0/24"
assert shorten_interface("TenGigabitEthernet1/0/1") == "Te1/0/1"
assert shorten_interface("Port-channel1") == "Po1"
assert shorten_interface("Loopback0") == "Lo0"
assert shorten_interface("Vlan100") == "Vlan100"
assert shorten_interface("UnknownType0/1") == "UnknownType0/1"
print("Все тесты пройдены!")
```

**Подсказка:**
> `name_lower = name.lower()`. Проходишь по списку: `if name_lower.startswith(full_lower): return short + name[len(full_lower):]`. `return` сразу выходит из функции — `break` не нужен.

---

### Задача 1.5. Обрезка длинного имени инвентаря

**Контекст:** NetBox ограничивает поле `name` для inventory items до 64 символов. Если имя длиннее — нужно обрезать, но так чтобы было понятно что обрезано. В проекте (файл `core/domain/inventory.py`) используется схема: первые 61 символ + `"..."`.

**Задание:** Напиши функцию `truncate_name(name, max_length=64)`:
1. Если длина <= max_length — вернуть как есть
2. Если длиннее — обрезать до `max_length - 3` символов и добавить `"..."`
3. Если вход None или пустая строка — вернуть `""`

```python
def truncate_name(name, max_length=64):
    # Твой код здесь
    pass

# Тесты
assert truncate_name("Short name") == "Short name"
assert truncate_name("A" * 64) == "A" * 64
assert truncate_name("A" * 65) == "A" * 61 + "..."
assert truncate_name("A" * 100) == "A" * 61 + "..."
assert len(truncate_name("A" * 100)) == 64
assert truncate_name("") == ""
assert truncate_name(None) == ""
assert truncate_name("Test", max_length=5) == "Test"
assert truncate_name("TestLong", max_length=5) == "Te..."
print("Все тесты пройдены!")
```

---

### Задача 1.6. Извлечение номера из имени интерфейса

**Контекст:** Часто нужно отделить буквенный префикс от номера: `"Gi0/1"` → `("Gi", "0/1")`, `"Vlan100"` → `("Vlan", "100")`.

**Задание:** Напиши функцию `split_interface_name(name)`, которая возвращает кортеж `(prefix, number)`:
1. Пройди по символам: найди позицию, где начинается цифра
2. Всё до первой цифры — prefix, остальное — number
3. Если цифр нет — `(name, "")`
4. Если пустой вход — `("", "")`

```python
def split_interface_name(name):
    # Твой код здесь
    pass

# Тесты
assert split_interface_name("Gi0/1") == ("Gi", "0/1")
assert split_interface_name("GigabitEthernet0/1") == ("GigabitEthernet", "0/1")
assert split_interface_name("Vlan100") == ("Vlan", "100")
assert split_interface_name("Port-channel1") == ("Port-channel", "1")
assert split_interface_name("Loopback") == ("Loopback", "")
assert split_interface_name("100") == ("", "100")
assert split_interface_name("") == ("", "")
print("Все тесты пройдены!")
```

**Подсказка:**
> `for i, char in enumerate(name): if char.isdigit(): return (name[:i], name[i:])`. Используй `enumerate()` чтобы получить индекс и символ одновременно.

---

### Эталонные решения блока 1

<details>
<summary>Нажми чтобы раскрыть решения</summary>

**1.1. Нормализация MAC:**
```python
def normalize_mac(mac):
    if not mac:
        return ""
    mac = str(mac).strip().lower()
    mac = mac.replace(":", "").replace("-", "").replace(".", "")
    return mac
```

**1.2. Определение формата MAC:**
```python
def detect_mac_format(mac):
    if not mac:
        return "unknown"
    mac = mac.strip()
    if "." in mac and len(mac) == 14:
        return "cisco"
    if ":" in mac and len(mac) == 17:
        return "unix"
    if "-" in mac and len(mac) == 17:
        return "windows"
    if len(mac) == 12 and mac.isalnum():
        return "raw"
    return "unknown"
```

**1.3. Нормализация статуса:**
```python
def normalize_status(raw_status):
    if not raw_status:
        return "unknown"
    normalized = str(raw_status).lower().strip()
    if not normalized:
        return "unknown"
    return STATUS_MAP.get(normalized, normalized)
```

**1.4. Сокращение имени интерфейса:**
```python
def shorten_interface(name):
    if not name:
        return ""
    name_lower = name.lower()
    for full_lower, short in INTERFACE_SHORT_MAP:
        if name_lower.startswith(full_lower):
            return short + name[len(full_lower):]
    return name
```

**1.5. Обрезка имени:**
```python
def truncate_name(name, max_length=64):
    if not name:
        return ""
    if len(name) <= max_length:
        return name
    return name[:max_length - 3] + "..."
```

**1.6. Разделение имени интерфейса:**
```python
def split_interface_name(name):
    if not name:
        return ("", "")
    for i, char in enumerate(name):
        if char.isdigit():
            return (name[:i], name[i:])
    return (name, "")
```

</details>

---

## Блок 2. Словари — хранение и обработка сетевых данных

В проекте словари — основная структура данных. Результаты парсинга, настройки, кэши, статистика — всё это словари. Умение быстро создавать, читать и трансформировать словари — ключевой навык.

### Теория-напоминание

```python
# Создание
d = {"name": "sw1", "ip": "10.0.0.1"}
d = dict(name="sw1", ip="10.0.0.1")  # альтернативный способ

# Чтение
d["name"]              # "sw1" (KeyError если нет ключа)
d.get("name")          # "sw1" (None если нет ключа)
d.get("role", "switch") # "switch" (свой default)

# Изменение
d["role"] = "router"           # добавить/изменить
d.update({"site": "Office"})   # добавить несколько
del d["role"]                  # удалить ключ

# Итерация
for key in d:                  # по ключам
for key, value in d.items():   # по парам ключ-значение
for value in d.values():       # по значениям

# Проверки
"name" in d         # True — ключ существует
"role" not in d     # True — ключа нет
```

---

### Задача 2.1. Подсчёт статистики интерфейсов

**Контекст:** После сбора данных нужно посчитать сколько интерфейсов в каждом статусе. В проекте статистика хранится в `SyncStats` (файл `netbox/sync/base.py`).

**Задание:** Напиши функцию `count_by_status(interfaces)`, которая принимает список словарей и возвращает словарь с подсчётом.

```python
def count_by_status(interfaces):
    # Твой код здесь
    pass

# Тест
interfaces = [
    {"name": "Gi0/1", "status": "up"},
    {"name": "Gi0/2", "status": "down"},
    {"name": "Gi0/3", "status": "up"},
    {"name": "Gi0/4", "status": "up"},
    {"name": "Gi0/5", "status": "down"},
    {"name": "Gi0/6", "status": "admin_down"},
]
result = count_by_status(interfaces)
assert result == {"up": 3, "down": 2, "admin_down": 1}
print("Тест пройден!")
```

**Подсказка:**
> Создай пустой словарь `counts = {}`. В цикле: `status = intf["status"]`, потом `counts[status] = counts.get(status, 0) + 1`.

---

### Задача 2.2. Группировка интерфейсов по типу

**Контекст:** Часто нужно сгруппировать интерфейсы по типу (физические, LAG, виртуальные). В проекте такая группировка используется при синхронизации — LAG-интерфейсы создаются первыми.

**Задание:** Напиши функцию `group_by_type(interfaces)`, которая возвращает словарь, где ключ — тип, значение — список имён.

```python
def group_by_type(interfaces):
    # Твой код здесь
    pass

# Тест
interfaces = [
    {"name": "Gi0/1", "type": "physical"},
    {"name": "Gi0/2", "type": "physical"},
    {"name": "Po1", "type": "lag"},
    {"name": "Vlan100", "type": "virtual"},
    {"name": "Po2", "type": "lag"},
    {"name": "Vlan200", "type": "virtual"},
]
result = group_by_type(interfaces)
assert result == {
    "physical": ["Gi0/1", "Gi0/2"],
    "lag": ["Po1", "Po2"],
    "virtual": ["Vlan100", "Vlan200"],
}
print("Тест пройден!")
```

**Подсказка:**
> `groups = {}`. В цикле: `t = intf["type"]`. Если ключа ещё нет — создай пустой список: `if t not in groups: groups[t] = []`. Потом `groups[t].append(intf["name"])`.

---

### Задача 2.3. Безопасное извлечение с fallback-полями

**Контекст:** Разные платформы возвращают одно и то же поле под разными именами. Например, серийный номер может быть в поле `"sn"`, `"serial"` или `"serial_number"`. В проекте это решается цепочкой `.get()` (см. `core/domain/inventory.py`).

**Задание:** Напиши функцию `get_first_value(data, field_names, default="")`, которая пробует получить значение по списку имён полей и возвращает первое непустое.

```python
def get_first_value(data, field_names, default=""):
    # Твой код здесь
    pass

# Тесты
row1 = {"sn": "ABC123", "name": "Module1"}
row2 = {"serial": "DEF456", "name": "Module2"}
row3 = {"serial_number": "GHI789", "name": "Module3"}
row4 = {"name": "Module4"}  # нет серийного номера
row5 = {"sn": "", "serial": "XYZ000"}  # первое поле пустое

assert get_first_value(row1, ["sn", "serial", "serial_number"]) == "ABC123"
assert get_first_value(row2, ["sn", "serial", "serial_number"]) == "DEF456"
assert get_first_value(row3, ["sn", "serial", "serial_number"]) == "GHI789"
assert get_first_value(row4, ["sn", "serial", "serial_number"]) == ""
assert get_first_value(row4, ["sn", "serial"], "N/A") == "N/A"
assert get_first_value(row5, ["sn", "serial", "serial_number"]) == "XYZ000"
print("Все тесты пройдены!")
```

**Подсказка:**
> `for field in field_names:` → `value = data.get(field)` → `if value: return value`. После цикла `return default`.

---

### Задача 2.4. Маппинг ключей словаря

**Контекст:** LLDP-данные приходят с разными именами ключей (`local_intf` вместо `local_interface`, `neighbor` вместо `remote_hostname`). В проекте это решается словарём `KEY_MAPPING` (файл `core/domain/lldp.py`).

**Задание:** Напиши функцию `remap_keys(data, key_mapping)`, которая создаёт новый словарь с переименованными ключами. Если ключ не в маппинге — оставить как есть.

```python
def remap_keys(data, key_mapping):
    # Твой код здесь
    pass

# Тест
KEY_MAPPING = {
    "local_intf": "local_interface",
    "neighbor": "remote_hostname",
    "neighbor_intf": "remote_interface",
}

raw = {
    "local_intf": "Gi0/1",
    "neighbor": "switch-02",
    "neighbor_intf": "Gi0/2",
    "ttl": "120",
}

result = remap_keys(raw, KEY_MAPPING)
assert result == {
    "local_interface": "Gi0/1",
    "remote_hostname": "switch-02",
    "remote_interface": "Gi0/2",
    "ttl": "120",  # не в маппинге — осталось как есть
}
print("Тест пройден!")
```

**Подсказка:**
> `new_key = key_mapping.get(key, key)` — если ключ есть в маппинге, берём новое имя; если нет — оставляем старое.

---

### Задача 2.5. Построение индекса (имя → объект)

**Контекст:** При синхронизации нужно быстро находить интерфейс по имени. Линейный поиск по списку — медленно. В проекте строится индекс-словарь: `{intf.name: intf for intf in interfaces}` (файл `netbox/sync/base.py`).

**Задание:** Напиши функцию `build_index(items, key_field)`, которая из списка словарей строит словарь-индекс по указанному полю.

```python
def build_index(items, key_field):
    # Твой код здесь
    pass

# Тест
interfaces = [
    {"name": "Gi0/1", "status": "up", "speed": 1000},
    {"name": "Gi0/2", "status": "down", "speed": 1000},
    {"name": "Po1", "status": "up", "speed": 10000},
]

index = build_index(interfaces, "name")
assert index["Gi0/1"] == {"name": "Gi0/1", "status": "up", "speed": 1000}
assert index["Po1"]["speed"] == 10000
assert "Gi0/3" not in index
assert len(index) == 3
print("Тест пройден!")
```

**Подсказка:**
> Можно в одну строку: `return {item[key_field]: item for item in items}` — это dict comprehension.

---

### Задача 2.6. Слияние двух словарей с приоритетом

**Контекст:** При загрузке конфига в проекте (файл `config.py`) сначала загружаются дефолты, потом поверх — пользовательские настройки из YAML. Вложенные словари сливаются рекурсивно, а не перезаписываются целиком.

**Задание:** Напиши функцию `merge_dicts(base, override)`, которая:
1. Если ключ есть только в base — оставить
2. Если ключ есть только в override — добавить
3. Если ключ есть в обоих и оба значения — словари — слить рекурсивно
4. Если ключ есть в обоих и хотя бы одно значение не словарь — override побеждает
5. Не изменять оригинальные словари (работать с копией)

```python
def merge_dicts(base, override):
    # Твой код здесь
    pass

# Тесты
base = {
    "netbox": {"url": "http://localhost", "timeout": 30},
    "logging": {"level": "INFO"},
    "max_workers": 5,
}
override = {
    "netbox": {"url": "http://netbox.local", "verify_ssl": False},
    "logging": {"level": "DEBUG"},
    "dry_run": True,
}

result = merge_dicts(base, override)
assert result == {
    "netbox": {"url": "http://netbox.local", "timeout": 30, "verify_ssl": False},
    "logging": {"level": "DEBUG"},
    "max_workers": 5,
    "dry_run": True,
}
# Проверяем что оригиналы не изменились
assert base["netbox"]["url"] == "http://localhost"
assert "dry_run" not in base
print("Тест пройден!")
```

**Подсказка:**
> `result = dict(base)` — копия первого уровня. Для вложенных: `if isinstance(base[key], dict) and isinstance(value, dict): result[key] = merge_dicts(base[key], value)`. Это рекурсия — функция вызывает сама себя.

---

### Эталонные решения блока 2

<details>
<summary>Нажми чтобы раскрыть решения</summary>

**2.1. Подсчёт по статусу:**
```python
def count_by_status(interfaces):
    counts = {}
    for intf in interfaces:
        status = intf["status"]
        counts[status] = counts.get(status, 0) + 1
    return counts
```

**2.2. Группировка по типу:**
```python
def group_by_type(interfaces):
    groups = {}
    for intf in interfaces:
        t = intf["type"]
        if t not in groups:
            groups[t] = []
        groups[t].append(intf["name"])
    return groups
```

**2.3. Извлечение с fallback:**
```python
def get_first_value(data, field_names, default=""):
    for field in field_names:
        value = data.get(field)
        if value:
            return value
    return default
```

**2.4. Маппинг ключей:**
```python
def remap_keys(data, key_mapping):
    result = {}
    for key, value in data.items():
        new_key = key_mapping.get(key, key)
        result[new_key] = value
    return result
```

**2.5. Построение индекса:**
```python
def build_index(items, key_field):
    return {item[key_field]: item for item in items}
```

**2.6. Рекурсивное слияние:**
```python
def merge_dicts(base, override):
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_dicts(result[key], value)
        else:
            result[key] = value
    return result
```

</details>

---

## Блок 3. Списки и comprehensions — фильтрация и трансформация

Списки в Python — рабочая лошадка для хранения коллекций. Comprehensions (генераторы списков) позволяют создавать, фильтровать и трансформировать списки в одну строку. В проекте они используются повсеместно.

### Теория-напоминание

```python
# List comprehension — создание списка в одну строку
names = [intf["name"] for intf in interfaces]

# С фильтром
up_names = [intf["name"] for intf in interfaces if intf["status"] == "up"]

# С трансформацией
lower_names = [name.lower() for name in names]

# Dict comprehension
{key: value for key, value in data.items() if value}

# sorted() с ключом
sorted(items, key=lambda x: x["name"])

# any() / all() — проверка условий
any(intf["status"] == "up" for intf in interfaces)  # хотя бы один up?
all(intf["status"] == "up" for intf in interfaces)  # все up?

# enumerate() — индекс + значение
for i, item in enumerate(items):
    print(f"{i}: {item}")

# zip() — параллельная итерация
for name, status in zip(names, statuses):
    print(f"{name}: {status}")
```

---

### Задача 3.1. Фильтрация trunk-портов

**Контекст:** При сборе MAC-адресов нужно исключить trunk-порты. В проекте (файл `collectors/mac.py`) trunk-порты фильтруются через set.

**Задание:** Напиши функцию `filter_access_ports(interfaces)` — возвращает только access-порты (mode != "trunk"). Используй list comprehension.

```python
def filter_access_ports(interfaces):
    # Твой код здесь — одна строка с list comprehension
    pass

# Тест
interfaces = [
    {"name": "Gi0/1", "mode": "access", "vlan": 10},
    {"name": "Gi0/2", "mode": "trunk", "vlan": 0},
    {"name": "Gi0/3", "mode": "access", "vlan": 20},
    {"name": "Gi0/4", "mode": "trunk", "vlan": 0},
    {"name": "Gi0/5", "mode": "access", "vlan": 10},
]

result = filter_access_ports(interfaces)
assert len(result) == 3
assert all(intf["mode"] == "access" for intf in result)
assert [intf["name"] for intf in result] == ["Gi0/1", "Gi0/3", "Gi0/5"]
print("Тест пройден!")
```

---

### Задача 3.2. Извлечение имён и трансформация

**Задание:** Напиши три функции, каждая — одна строка с list comprehension:

```python
def get_names(interfaces):
    """Вернуть список имён интерфейсов"""
    pass

def get_names_lower(interfaces):
    """Вернуть список имён в нижнем регистре"""
    pass

def get_up_names(interfaces):
    """Вернуть имена только тех интерфейсов, которые up"""
    pass

# Тесты
interfaces = [
    {"name": "Gi0/1", "status": "up"},
    {"name": "Gi0/2", "status": "down"},
    {"name": "Te1/0/1", "status": "up"},
]

assert get_names(interfaces) == ["Gi0/1", "Gi0/2", "Te1/0/1"]
assert get_names_lower(interfaces) == ["gi0/1", "gi0/2", "te1/0/1"]
assert get_up_names(interfaces) == ["Gi0/1", "Te1/0/1"]
print("Все тесты пройдены!")
```

---

### Задача 3.3. Парсинг VLAN range

**Контекст:** Коммутаторы показывают trunk VLANs в сжатом виде: `"1,10-15,20,100-102"`. Нужно развернуть range в полный список.

**Задание:** Напиши функцию `parse_vlan_range(vlan_string)`:
1. Разбивает строку по запятым
2. Если элемент содержит `-` — разворачивает диапазон
3. Если просто число — добавляет как есть
4. Возвращает отсортированный список int

```python
def parse_vlan_range(vlan_string):
    # Твой код здесь
    pass

# Тесты
assert parse_vlan_range("10") == [10]
assert parse_vlan_range("1,10,20") == [1, 10, 20]
assert parse_vlan_range("10-15") == [10, 11, 12, 13, 14, 15]
assert parse_vlan_range("1,10-13,20,100-102") == [1, 10, 11, 12, 13, 20, 100, 101, 102]
assert parse_vlan_range("") == []
print("Все тесты пройдены!")
```

**Подсказка:**
> `for part in vlan_string.split(","):` → `if "-" in part:` → `start, end = part.split("-")` → `range(int(start), int(end) + 1)`. Используй `.extend()`.

---

### Задача 3.4. Сортировка интерфейсов по приоритету типа

**Контекст:** При создании интерфейсов в NetBox: сначала LAG, потом физические, потом виртуальные.

```python
TYPE_PRIORITY = {"lag": 0, "physical": 1, "virtual": 2}

def sort_by_type_priority(interfaces):
    # Твой код — используй sorted() с key=lambda
    pass

# Тест
interfaces = [
    {"name": "Vlan100", "type": "virtual"},
    {"name": "Gi0/1", "type": "physical"},
    {"name": "Po1", "type": "lag"},
    {"name": "Gi0/2", "type": "physical"},
    {"name": "Po2", "type": "lag"},
    {"name": "Vlan200", "type": "virtual"},
]

result = sort_by_type_priority(interfaces)
names = [intf["name"] for intf in result]
assert names == ["Po1", "Po2", "Gi0/1", "Gi0/2", "Vlan100", "Vlan200"]
print("Тест пройден!")
```

---

### Задача 3.5. Поиск первого совпадения с next()

**Контекст:** `next((i for i in items if i.name == name), None)` — из `netbox/sync/interfaces.py`.

```python
def find_interface(interfaces, name):
    # Твой код — используй next() с generator expression
    pass

# Тесты
interfaces = [
    {"name": "Gi0/1", "status": "up"},
    {"name": "Gi0/2", "status": "down"},
    {"name": "Po1", "status": "up"},
]

assert find_interface(interfaces, "Gi0/2") == {"name": "Gi0/2", "status": "down"}
assert find_interface(interfaces, "Gi0/99") is None
print("Все тесты пройдены!")
```

---

### Задача 3.6. Параллельные списки и zip()

**Контекст:** Batch-операции в `netbox/sync/base.py` используют `zip()` для параллельных списков.

```python
def create_report(names, statuses, speeds):
    # Твой код — используй zip() и list comprehension
    pass

# Тест
names = ["Gi0/1", "Gi0/2", "Gi0/3"]
statuses = ["up", "down", "up"]
speeds = [1000, 1000, 10000]

result = create_report(names, statuses, speeds)
assert result == [
    {"name": "Gi0/1", "status": "up", "speed": 1000},
    {"name": "Gi0/2", "status": "down", "speed": 1000},
    {"name": "Gi0/3", "status": "up", "speed": 10000},
]
print("Тест пройден!")
```

---

### Эталонные решения блока 3

<details>
<summary>Нажми чтобы раскрыть решения</summary>

**3.1:** `return [intf for intf in interfaces if intf["mode"] != "trunk"]`

**3.2:**
```python
def get_names(interfaces):
    return [intf["name"] for intf in interfaces]

def get_names_lower(interfaces):
    return [intf["name"].lower() for intf in interfaces]

def get_up_names(interfaces):
    return [intf["name"] for intf in interfaces if intf["status"] == "up"]
```

**3.3:**
```python
def parse_vlan_range(vlan_string):
    if not vlan_string:
        return []
    result = []
    for part in vlan_string.strip().split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-")
            result.extend(range(int(start), int(end) + 1))
        else:
            result.append(int(part))
    return sorted(result)
```

**3.4:** `return sorted(interfaces, key=lambda intf: TYPE_PRIORITY.get(intf["type"], 99))`

**3.5:** `return next((intf for intf in interfaces if intf["name"] == name), None)`

**3.6:** `return [{"name": n, "status": s, "speed": sp} for n, s, sp in zip(names, statuses, speeds)]`

</details>

---

## Блок 4. Функции — декомпозиция и паттерны

Хорошие функции — маленькие, делают одно дело и имеют понятное имя. В проекте каждый нормализатор состоит из десятков мелких функций: одна определяет тип порта, другая проверяет статус, третья строит имя.

### Теория-напоминание

```python
# Базовая функция
def normalize(value):
    return value.lower().strip()

# С default-аргументом
def truncate(name, max_length=64):
    if len(name) > max_length:
        return name[:max_length - 3] + "..."
    return name

# *args — произвольное число аргументов
def log(*messages):
    print(" ".join(str(m) for m in messages))

# **kwargs — произвольные именованные аргументы
def create_device(**fields):
    return fields  # словарь

# Lambda — анонимная функция
key_fn = lambda x: x["name"]
sorted(items, key=lambda x: x["name"])

# Функция как аргумент (higher-order)
def apply_to_all(items, fn):
    return [fn(item) for item in items]
```

---

### Задача 4.1. Функция с несколькими уровнями fallback

**Контекст:** В `core/domain/interface.py` метод `detect_port_type()` проверяет несколько источников: сначала media_type, потом hardware_type, потом имя. Каждый уровень — отдельная функция.

**Задание:** Напиши набор функций для определения скорости интерфейса с приоритетами:
1. Если есть поле `speed` — использовать его
2. Если есть `media_type` с подстрокой скорости — определить по ней
3. Если есть имя интерфейса — определить по префиксу
4. Иначе — `0`

```python
def detect_speed_from_field(data):
    """Уровень 1: прямое значение скорости"""
    # Твой код
    pass

def detect_speed_from_media(data):
    """Уровень 2: скорость из media_type"""
    # Подсказка: "10GBase" → 10000, "1000Base" → 1000, "100Base" → 100
    pass

def detect_speed_from_name(data):
    """Уровень 3: скорость из имени интерфейса"""
    # Подсказка: "Te" → 10000, "Gi" → 1000, "Fa" → 100
    pass

def detect_speed(data):
    """Главная функция: пробует уровни по приоритету"""
    # Твой код — вызывай функции выше по очереди
    pass

# Тесты
assert detect_speed({"name": "Gi0/1", "speed": 1000}) == 1000
assert detect_speed({"name": "Gi0/1", "media_type": "10GBase-SR"}) == 10000
assert detect_speed({"name": "Te1/0/1"}) == 10000
assert detect_speed({"name": "Gi0/1"}) == 1000
assert detect_speed({"name": "Fa0/1"}) == 100
assert detect_speed({"name": "Vlan100"}) == 0
assert detect_speed({}) == 0
print("Все тесты пройдены!")
```

**Подсказка:**
> В `detect_speed`: `speed = detect_speed_from_field(data)` → `if speed: return speed` → следующий уровень.

---

### Задача 4.2. Функция-валидатор с несколькими проверками

**Контекст:** Перед синхронизацией нужно проверить данные. Невалидные записи пропускаются с предупреждением.

**Задание:** Напиши функцию `validate_interface(data)`, которая возвращает `(is_valid, errors)`:

```python
def validate_interface(data):
    """
    Проверяет данные интерфейса. Возвращает (True, []) или (False, ["ошибка1", ...])

    Правила:
    - name обязательно и не пустое
    - status должен быть "up" или "down" (если есть)
    - speed должен быть положительным числом (если есть)
    - description не длиннее 200 символов (если есть)
    """
    # Твой код здесь
    pass

# Тесты
valid, errors = validate_interface({"name": "Gi0/1", "status": "up", "speed": 1000})
assert valid is True and errors == []

valid, errors = validate_interface({"status": "up"})
assert valid is False and "name" in errors[0].lower()

valid, errors = validate_interface({"name": "Gi0/1", "status": "maybe"})
assert valid is False and len(errors) == 1

valid, errors = validate_interface({"name": "Gi0/1", "speed": -100})
assert valid is False

valid, errors = validate_interface({"name": "Gi0/1", "description": "A" * 201})
assert valid is False

valid, errors = validate_interface({"name": ""})
assert valid is False

# Несколько ошибок сразу
valid, errors = validate_interface({"status": "maybe", "speed": -1})
assert valid is False and len(errors) >= 2
print("Все тесты пройдены!")
```

---

### Задача 4.3. Функция-обработчик списка с callback

**Контекст:** В `collectors/base.py` метод `collect_dicts()` принимает `progress_callback` — функцию, которая вызывается после обработки каждого устройства. Это паттерн callback.

**Задание:** Напиши функцию `process_devices(devices, processor, on_progress=None)`:
1. Для каждого device вызвать `processor(device)` и собрать результаты
2. После каждого device вызвать `on_progress(current, total, device_name)` если callback передан
3. Вернуть список результатов

```python
def process_devices(devices, processor, on_progress=None):
    # Твой код здесь
    pass

# Тест
devices = [
    {"name": "sw1", "ip": "10.0.0.1"},
    {"name": "sw2", "ip": "10.0.0.2"},
    {"name": "sw3", "ip": "10.0.0.3"},
]

# Простой процессор
def get_name(device):
    return device["name"].upper()

# Трекер прогресса
progress_log = []
def track_progress(current, total, name):
    progress_log.append(f"{current}/{total}: {name}")

result = process_devices(devices, get_name, on_progress=track_progress)
assert result == ["SW1", "SW2", "SW3"]
assert progress_log == ["1/3: sw1", "2/3: sw2", "3/3: sw3"]

# Без callback — тоже должно работать
result2 = process_devices(devices, get_name)
assert result2 == ["SW1", "SW2", "SW3"]
print("Все тесты пройдены!")
```

---

### Задача 4.4. Функция с *args и **kwargs

**Контекст:** В `netbox/sync/base.py` функция `_safe_netbox_call(operation, fn, *args, default=None, **kwargs)` оборачивает любой API-вызов в try/except.

**Задание:** Напиши функцию `safe_call(operation_name, fn, *args, default=None, **kwargs)`:
1. Вызывает `fn(*args, **kwargs)`
2. Если успех — возвращает результат
3. Если исключение — печатает предупреждение и возвращает `default`

```python
def safe_call(operation_name, fn, *args, default=None, **kwargs):
    # Твой код здесь
    pass

# Тесты
def divide(a, b):
    return a / b

assert safe_call("деление", divide, 10, 2) == 5.0
assert safe_call("деление", divide, 10, 0, default=-1) == -1  # ZeroDivisionError

def greet(name, prefix="Hello"):
    return f"{prefix}, {name}!"

assert safe_call("приветствие", greet, "World") == "Hello, World!"
assert safe_call("приветствие", greet, "World", prefix="Hi") == "Hi, World!"
print("Все тесты пройдены!")
```

---

### Задача 4.5. Декоратор для логирования

**Контекст:** Декораторы — функции, которые оборачивают другие функции. В проекте не так много декораторов, но это важная концепция Python.

**Задание:** Напиши декоратор `log_call`, который печатает имя функции, аргументы и результат.

```python
def log_call(fn):
    # Твой код здесь — верни обёртку
    pass

@log_call
def add(a, b):
    return a + b

@log_call
def normalize_mac(mac):
    return mac.replace(":", "").lower()

# Вызовы должны печатать логи и возвращать правильный результат
result1 = add(3, 5)
# Должно напечатать: Вызов add(3, 5) → 8
assert result1 == 8

result2 = normalize_mac("AA:BB:CC:DD:EE:FF")
# Должно напечатать: Вызов normalize_mac('AA:BB:CC:DD:EE:FF') → aabbccddeeff
assert result2 == "aabbccddeeff"
print("Все тесты пройдены!")
```

**Подсказка:**
> ```python
> def log_call(fn):
>     def wrapper(*args, **kwargs):
>         result = fn(*args, **kwargs)
>         args_str = ", ".join([repr(a) for a in args])
>         print(f"Вызов {fn.__name__}({args_str}) → {result}")
>         return result
>     return wrapper
> ```

---

### Эталонные решения блока 4

<details>
<summary>Нажми чтобы раскрыть решения</summary>

**4.1. Каскадное определение скорости:**
```python
def detect_speed_from_field(data):
    speed = data.get("speed")
    if speed and isinstance(speed, (int, float)) and speed > 0:
        return int(speed)
    return 0

def detect_speed_from_media(data):
    media = data.get("media_type", "")
    if not media:
        return 0
    media_lower = media.lower()
    if "10gbase" in media_lower or "10g" in media_lower:
        return 10000
    if "1000base" in media_lower:
        return 1000
    if "100base" in media_lower:
        return 100
    return 0

def detect_speed_from_name(data):
    name = data.get("name", "").lower()
    if not name:
        return 0
    if name.startswith(("te", "tengigabit")):
        return 10000
    if name.startswith(("gi", "gigabit")):
        return 1000
    if name.startswith(("fa", "fastethernet")):
        return 100
    return 0

def detect_speed(data):
    speed = detect_speed_from_field(data)
    if speed:
        return speed
    speed = detect_speed_from_media(data)
    if speed:
        return speed
    return detect_speed_from_name(data)
```

**4.2. Валидатор:**
```python
def validate_interface(data):
    errors = []
    name = data.get("name")
    if not name:
        errors.append("name обязательно и не может быть пустым")
    status = data.get("status")
    if status and status not in ("up", "down"):
        errors.append(f"status должен быть 'up' или 'down', получено: '{status}'")
    speed = data.get("speed")
    if speed is not None and (not isinstance(speed, (int, float)) or speed <= 0):
        errors.append(f"speed должен быть положительным числом, получено: {speed}")
    description = data.get("description")
    if description and len(description) > 200:
        errors.append(f"description слишком длинное: {len(description)} > 200")
    return (len(errors) == 0, errors)
```

**4.3. Обработка с callback:**
```python
def process_devices(devices, processor, on_progress=None):
    results = []
    total = len(devices)
    for i, device in enumerate(devices, 1):
        result = processor(device)
        results.append(result)
        if on_progress:
            on_progress(i, total, device["name"])
    return results
```

**4.4. safe_call:**
```python
def safe_call(operation_name, fn, *args, default=None, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        print(f"Предупреждение: {operation_name} — {e}")
        return default
```

**4.5. Декоратор:**
```python
def log_call(fn):
    def wrapper(*args, **kwargs):
        result = fn(*args, **kwargs)
        args_str = ", ".join([repr(a) for a in args])
        print(f"Вызов {fn.__name__}({args_str}) → {result}")
        return result
    return wrapper
```

</details>

---

## Блок 5. Множества (set) и регулярные выражения (re)

Множества — для быстрой проверки "есть ли элемент" и операций разности/пересечения. В проекте set используется для фильтрации trunk-портов, поиска новых/удалённых интерфейсов, дедупликации алиасов. Регулярные выражения — для парсинга вывода устройств.

### Теория-напоминание: set

```python
# Создание
s = {1, 2, 3}
s = set()           # пустое множество (не {}  — это dict!)

# Операции
s.add(4)            # добавить элемент
s.update([5, 6])    # добавить несколько
s.discard(3)        # удалить (без ошибки если нет)

# Проверка
4 in s              # True — O(1) скорость

# Операции множеств
a = {"Gi0/1", "Gi0/2", "Gi0/3"}
b = {"Gi0/2", "Gi0/3", "Gi0/4"}
a - b    # {"Gi0/1"}       — в a, но не в b (разность)
a & b    # {"Gi0/2", "Gi0/3"} — в обоих (пересечение)
a | b    # все четыре       — объединение

# Set comprehension
{name.lower() for name in names}
```

### Теория-напоминание: re

```python
import re

# re.match() — совпадение с НАЧАЛА строки
re.match(r"Gi\d+", "Gi0/1")      # Match object
re.match(r"Gi\d+", "Port Gi0/1")  # None (не с начала)

# re.search() — совпадение ГДЕ УГОДНО в строке
re.search(r"Gi\d+", "Port Gi0/1") # Match object

# re.findall() — все совпадения
re.findall(r"\d+", "Gi0/1/2")    # ["0", "1", "2"]

# re.sub() — замена
re.sub(r"\s+", " ", "hello   world")  # "hello world"

# Основные паттерны:
# \d   — цифра       \d+ — одна или более цифр
# \w   — буква/цифра \w+ — слово
# \s   — пробел      \s+ — один или более пробелов
# .    — любой символ .+  — один или более любых
# ^    — начало строки
# $    — конец строки
# [A-Za-z] — диапазон букв
# (...)  — группа захвата
```

---

### Задача 5.1. Поиск новых и удалённых интерфейсов через set

**Контекст:** В `core/domain/sync.py` метод `compare_cables()` использует операции множеств: `local_set - remote_set` = новые кабели, `remote_set - local_set` = удалённые.

**Задание:** Напиши функцию `find_changes(local_names, remote_names)`, которая возвращает словарь с тремя множествами:

```python
def find_changes(local_names, remote_names):
    """
    local_names: список имён интерфейсов, собранных с устройства
    remote_names: список имён интерфейсов в NetBox
    Возвращает: {"to_create": set, "to_delete": set, "unchanged": set}
    """
    # Твой код здесь
    pass

# Тест
local = ["Gi0/1", "Gi0/2", "Gi0/3", "Gi0/4"]
remote = ["Gi0/1", "Gi0/2", "Gi0/5"]

result = find_changes(local, remote)
assert result["to_create"] == {"Gi0/3", "Gi0/4"}   # есть локально, нет в NetBox
assert result["to_delete"] == {"Gi0/5"}              # нет локально, есть в NetBox
assert result["unchanged"] == {"Gi0/1", "Gi0/2"}    # есть в обоих
print("Тест пройден!")
```

---

### Задача 5.2. Фильтрация trunk-портов через set алиасов

**Контекст:** В `collectors/mac.py` trunk-порты хранятся в `set`. Для каждого порта генерируются все алиасы (Gi0/1, GigabitEthernet0/1 и т.д.), чтобы совпадение находилось независимо от формата.

**Задание:** Напиши функцию `is_trunk_port(interface_name, trunk_ports)`:

```python
# Упрощённая версия get_interface_aliases
# Маппинг: полное имя (в нижнем регистре) → (сокращение, полное имя в правильном регистре)
ALIAS_MAP = {
    "gigabitethernet": ("Gi", "GigabitEthernet"),
    "fastethernet": ("Fa", "FastEthernet"),
    "tengigabitethernet": ("Te", "TenGigabitEthernet"),
}

def get_aliases(name):
    """Возвращает set из имени и его вариантов"""
    aliases = {name, name.lower()}
    name_lower = name.lower()
    for full_lower, (short, full_proper) in ALIAS_MAP.items():
        if name_lower.startswith(full_lower):
            # Полное имя → добавить сокращённое
            suffix = name[len(full_lower):]
            aliases.add(short + suffix)
        elif name_lower.startswith(short.lower()):
            # Сокращённое имя → добавить полное
            suffix = name[len(short):]
            aliases.add(full_proper + suffix)
    return aliases

def is_trunk_port(interface_name, trunk_ports):
    """Проверяет, является ли интерфейс trunk (с учётом алиасов)"""
    # Твой код здесь
    pass

# Тесты
trunks = {"GigabitEthernet0/24", "GigabitEthernet0/48"}
assert is_trunk_port("Gi0/24", trunks) == True     # короткое имя
assert is_trunk_port("GigabitEthernet0/24", trunks) == True  # полное имя
assert is_trunk_port("Gi0/1", trunks) == False
print("Все тесты пройдены!")
```

**Подсказка:**
> Получи алиасы для `interface_name`, и проверь пересечение с `trunk_ports`: `if aliases & trunk_ports:`.

---

### Задача 5.3. Парсинг MAC-адреса из строки регулярным выражением

**Контекст:** В `core/domain/lldp.py` используется `re.match()` для определения, является ли строка MAC-адресом.

**Задание:** Напиши функцию `extract_macs(text)`, которая находит все MAC-адреса в тексте.

```python
import re

def extract_macs(text):
    """Находит все MAC-адреса формата XX:XX:XX:XX:XX:XX или XXXX.XXXX.XXXX"""
    # Твой код здесь
    pass

# Тесты
text1 = "Interface Gi0/1, MAC 00:1a:2b:3c:4d:5e, status up"
assert extract_macs(text1) == ["00:1a:2b:3c:4d:5e"]

text2 = "No MAC here"
assert extract_macs(text2) == []

text3 = """
Gi0/1   00:1a:2b:3c:4d:5e   DYNAMIC
Gi0/2   aa:bb:cc:dd:ee:ff   STATIC
Gi0/3   0011.2233.4455      DYNAMIC
"""
result = extract_macs(text3)
assert "00:1a:2b:3c:4d:5e" in result
assert "aa:bb:cc:dd:ee:ff" in result
assert "0011.2233.4455" in result
assert len(result) == 3
print("Все тесты пройдены!")
```

**Подсказка:**
> Два паттерна: `[0-9a-fA-F]{2}(:[0-9a-fA-F]{2}){5}` для формата с двоеточиями и `[0-9a-fA-F]{4}\.[0-9a-fA-F]{4}\.[0-9a-fA-F]{4}` для Cisco. Используй `re.findall()`.

---

### Задача 5.4. Парсинг таблицы MAC-адресов регулярным выражением

**Контекст:** В `collectors/mac.py` используется `re.compile()` с `finditer()` для парсинга вывода `show mac address-table`.

**Задание:** Напиши функцию `parse_mac_table(output)`:

```python
import re

def parse_mac_table(output):
    """
    Парсит вывод show mac address-table.
    Формат строки: VLAN  MAC  TYPE  INTERFACE
    Возвращает список словарей.
    """
    # Твой код здесь
    pass

# Тест
output = """
Mac Address Table
-------------------------------------------

Vlan    Mac Address       Type        Ports
----    -----------       --------    -----
   1    0011.2233.4455    DYNAMIC     Gi0/1
  10    aabb.ccdd.eeff    STATIC      Gi0/2
  20    1122.3344.5566    DYNAMIC     Gi0/3
Total Mac Addresses for this criterion: 3
"""

result = parse_mac_table(output)
assert len(result) == 3
assert result[0] == {"vlan": 1, "mac": "0011.2233.4455", "type": "DYNAMIC", "interface": "Gi0/1"}
assert result[1]["vlan"] == 10
assert result[2]["interface"] == "Gi0/3"
print("Тест пройден!")
```

**Подсказка:**
> `pattern = re.compile(r"^\s*(\d+)\s+([0-9a-fA-F.]+)\s+(\w+)\s+(\S+)", re.MULTILINE)`. Потом `for match in pattern.finditer(output): vlan, mac, mac_type, port = match.groups()`.

---

### Задача 5.5. Исключение интерфейсов по паттернам

**Контекст:** В `fields.yaml` есть настройка `exclude_interfaces` — список regex-паттернов для исключения. В `core/domain/sync.py` используется `re.match()`.

**Задание:** Напиши функцию `filter_interfaces(names, exclude_patterns)`:

```python
import re

def filter_interfaces(names, exclude_patterns):
    """
    Убирает интерфейсы, подходящие под любой из exclude_patterns.
    Паттерны — регулярные выражения (case-insensitive).
    """
    # Твой код здесь
    pass

# Тест
names = ["Gi0/1", "Gi0/2", "Vlan1", "Vlan100", "Null0", "Loopback0", "Po1"]
patterns = [r"^Vlan1$", r"^Null\d+", r"^Loopback\d+"]

result = filter_interfaces(names, patterns)
assert result == ["Gi0/1", "Gi0/2", "Vlan100", "Po1"]
# Vlan1 исключён (точное совпадение), Vlan100 — нет
# Null0 и Loopback0 исключены
print("Тест пройден!")
```

**Подсказка:**
> Для каждого имени проверяй: `any(re.match(pattern, name, re.IGNORECASE) for pattern in exclude_patterns)`. Если совпало — пропускаем.

---

### Эталонные решения блока 5

<details>
<summary>Нажми чтобы раскрыть решения</summary>

**5.1. Set-операции:**
```python
def find_changes(local_names, remote_names):
    local_set = set(local_names)
    remote_set = set(remote_names)
    return {
        "to_create": local_set - remote_set,
        "to_delete": remote_set - local_set,
        "unchanged": local_set & remote_set,
    }
```

**5.2. Trunk через алиасы:**
```python
def is_trunk_port(interface_name, trunk_ports):
    aliases = get_aliases(interface_name)
    return bool(aliases & trunk_ports)
```

**5.3. Извлечение MAC:**
```python
def extract_macs(text):
    pattern_colon = r"[0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5}"
    pattern_dot = r"[0-9a-fA-F]{4}\.[0-9a-fA-F]{4}\.[0-9a-fA-F]{4}"
    combined = f"({pattern_colon}|{pattern_dot})"
    return re.findall(combined, text)
```

**5.4. Парсинг MAC-таблицы:**
```python
def parse_mac_table(output):
    pattern = re.compile(r"^\s*(\d+)\s+([0-9a-fA-F.]+)\s+(\w+)\s+(\S+)", re.MULTILINE)
    results = []
    for match in pattern.finditer(output):
        vlan, mac, mac_type, port = match.groups()
        results.append({
            "vlan": int(vlan),
            "mac": mac,
            "type": mac_type,
            "interface": port,
        })
    return results
```

**5.5. Фильтрация по паттернам:**
```python
def filter_interfaces(names, exclude_patterns):
    result = []
    for name in names:
        excluded = any(re.match(p, name, re.IGNORECASE) for p in exclude_patterns)
        if not excluded:
            result.append(name)
    return result
```

</details>

---

## Блок 6. Работа с файлами — JSON, CSV, YAML

В проекте данные читаются из файлов (devices.json, config.yaml, fields.yaml) и записываются в файлы (Excel, CSV, JSON). Умение работать с файлами — обязательный навык.

### Теория-напоминание

```python
import json
import csv

# JSON — чтение
with open("data.json", "r") as f:
    data = json.load(f)        # файл → dict/list

# JSON — запись
with open("data.json", "w") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

# CSV — чтение как словари
with open("data.csv", "r") as f:
    reader = csv.DictReader(f)
    for row in reader:         # каждая строка — dict
        print(row["name"])

# CSV — запись
with open("data.csv", "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["name", "ip"])
    writer.writeheader()
    writer.writerow({"name": "sw1", "ip": "10.0.0.1"})

# with — автоматически закрывает файл, даже при ошибке
```

---

### Задача 6.1. Чтение и фильтрация JSON-файла

**Контекст:** В проекте файл `data/devices.json` хранит список устройств. При сборе данных этот список читается и фильтруется по сайту или платформе.

**Задание:** Напиши функцию `load_devices(filepath, site=None, platform=None)`:
1. Читает JSON-файл (список словарей)
2. Если указан `site` — фильтрует по полю `site`
3. Если указан `platform` — фильтрует по полю `platform`
4. Можно передать оба фильтра одновременно

```python
import json

def load_devices(filepath, site=None, platform=None):
    # Твой код здесь
    pass

# Для тестирования создадим временный файл
import tempfile, os

test_devices = [
    {"name": "sw1", "ip": "10.0.0.1", "site": "Office", "platform": "cisco_ios"},
    {"name": "sw2", "ip": "10.0.0.2", "site": "Office", "platform": "cisco_ios"},
    {"name": "sw3", "ip": "10.0.0.3", "site": "DC", "platform": "arista_eos"},
    {"name": "sw4", "ip": "10.0.0.4", "site": "DC", "platform": "cisco_ios"},
]

# Создаём временный файл
tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
json.dump(test_devices, tmp, indent=2)
tmp.close()

# Тесты
all_devices = load_devices(tmp.name)
assert len(all_devices) == 4

office = load_devices(tmp.name, site="Office")
assert len(office) == 2
assert all(d["site"] == "Office" for d in office)

arista = load_devices(tmp.name, platform="arista_eos")
assert len(arista) == 1
assert arista[0]["name"] == "sw3"

dc_cisco = load_devices(tmp.name, site="DC", platform="cisco_ios")
assert len(dc_cisco) == 1
assert dc_cisco[0]["name"] == "sw4"

os.unlink(tmp.name)  # удаляем временный файл
print("Все тесты пройдены!")
```

---

### Задача 6.2. Сохранение результатов в JSON

**Контекст:** Результаты синхронизации сохраняются в `data/history.json`.

**Задание:** Напиши функцию `save_results(filepath, results, max_records=100)`:
1. Если файл уже существует — прочитать его (список)
2. Добавить новые результаты в начало
3. Обрезать до `max_records`
4. Записать обратно

```python
import json, os

def save_results(filepath, results, max_records=100):
    # Твой код здесь
    pass

# Тест
import tempfile

tmp_path = tempfile.mktemp(suffix=".json")

# Первая запись — файла ещё нет
save_results(tmp_path, [{"operation": "sync", "created": 5}])
with open(tmp_path) as f:
    data = json.load(f)
assert len(data) == 1
assert data[0]["created"] == 5

# Вторая запись — файл уже есть
save_results(tmp_path, [{"operation": "sync", "created": 3}])
with open(tmp_path) as f:
    data = json.load(f)
assert len(data) == 2
assert data[0]["created"] == 3  # новый — в начале

# Тест ограничения
save_results(tmp_path, [{"n": i} for i in range(200)], max_records=10)
with open(tmp_path) as f:
    data = json.load(f)
assert len(data) == 10

os.unlink(tmp_path)
print("Все тесты пройдены!")
```

---

### Задача 6.3. Экспорт интерфейсов в CSV

**Контекст:** Команда `python -m network_collector devices --format csv` экспортирует данные.

**Задание:** Напиши функцию `export_to_csv(filepath, interfaces, fields)`:

```python
import csv

def export_to_csv(filepath, interfaces, fields):
    """
    Записывает список словарей в CSV.
    fields — список полей (колонок) для экспорта.
    Если поля нет в словаре — пустая строка.
    """
    # Твой код здесь
    pass

# Тест
import tempfile, os

interfaces = [
    {"name": "Gi0/1", "status": "up", "speed": 1000, "description": "Server"},
    {"name": "Gi0/2", "status": "down", "speed": 1000},  # нет description
    {"name": "Po1", "status": "up", "speed": 10000, "description": "Uplink"},
]

tmp = tempfile.mktemp(suffix=".csv")
export_to_csv(tmp, interfaces, ["name", "status", "speed", "description"])

# Проверяем
with open(tmp, "r") as f:
    reader = csv.DictReader(f)
    rows = list(reader)

assert len(rows) == 3
assert rows[0]["name"] == "Gi0/1"
assert rows[0]["description"] == "Server"
assert rows[1]["description"] == ""  # поля не было — пустая строка
assert rows[2]["speed"] == "10000"   # CSV читает всё как строки

os.unlink(tmp)
print("Тест пройден!")
```

**Подсказка:**
> `writer = csv.DictWriter(f, fieldnames=fields)`. Для каждой строки: `row = {field: str(intf.get(field, "")) for field in fields}`.

---

### Задача 6.4. Чтение YAML-конфигурации

**Контекст:** В проекте `config.py` читает `config.yaml` через `yaml.safe_load()`.

**Задание:** Напиши функцию `load_config(filepath, defaults)`:
1. Читает YAML-файл
2. Сливает с defaults (defaults как base, YAML как override)
3. Возвращает итоговый словарь
4. Если файл не найден — возвращает defaults без ошибки

```python
import json, os, tempfile

def load_config(filepath, defaults):
    # Твой код — используй merge_dicts из задачи 2.6
    # Для чтения: json.load(f) (или yaml.safe_load(f) если YAML)
    # Если файл не найден — вернуть defaults без ошибки
    pass

# Для тестирования используем JSON (аналог YAML, но без зависимостей)
tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
json.dump({"timeout": 60, "netbox": {"url": "http://netbox.local"}}, tmp)
tmp.close()

defaults = {
    "timeout": 30,
    "netbox": {"url": "http://localhost", "verify_ssl": True},
    "logging": {"level": "INFO"},
}

# Тест 1: файл есть — слияние
result = load_config(tmp.name, defaults)
assert result["timeout"] == 60               # override из файла
assert result["netbox"]["url"] == "http://netbox.local"  # override
assert result["netbox"]["verify_ssl"] is True # осталось из defaults
assert result["logging"]["level"] == "INFO"   # осталось из defaults

# Тест 2: файл не найден — вернуть defaults
result2 = load_config("/nonexistent/config.json", defaults)
assert result2["timeout"] == 30
assert result2["logging"]["level"] == "INFO"

os.unlink(tmp.name)
print("Все тесты пройдены!")
```

**Подсказка:**
> `try: with open(filepath) as f: file_data = json.load(f)` → `except FileNotFoundError: return dict(defaults)` → `return merge_dicts(defaults, file_data)`.

---

### Эталонные решения блока 6

<details>
<summary>Нажми чтобы раскрыть решения</summary>

**6.1. Чтение JSON:**
```python
def load_devices(filepath, site=None, platform=None):
    with open(filepath, "r") as f:
        devices = json.load(f)
    if site:
        devices = [d for d in devices if d.get("site") == site]
    if platform:
        devices = [d for d in devices if d.get("platform") == platform]
    return devices
```

**6.2. Сохранение с ограничением:**
```python
def save_results(filepath, results, max_records=100):
    existing = []
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            existing = json.load(f)
    combined = results + existing
    combined = combined[:max_records]
    with open(filepath, "w") as f:
        json.dump(combined, f, indent=2, ensure_ascii=False)
```

**6.3. Экспорт CSV:**
```python
def export_to_csv(filepath, interfaces, fields):
    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for intf in interfaces:
            row = {field: str(intf.get(field, "")) for field in fields}
            writer.writerow(row)
```

**6.4. Загрузка конфига:**
```python
def load_config(filepath, defaults):
    try:
        with open(filepath, "r") as f:
            file_data = json.load(f) or {}
    except FileNotFoundError:
        return dict(defaults)
    return merge_dicts(defaults, file_data)
```

</details>

---

## Блок 7. Классы — модели данных и наследование

В проекте классы используются для моделей данных (Interface, DeviceInfo, LLDPNeighbor), нормализаторов (InterfaceNormalizer), коллекторов (BaseCollector → DeviceCollector) и dataclass для простых структур (SyncItem, FieldChange).

### Теория-напоминание

```python
# Простой класс
class Device:
    def __init__(self, name, ip):
        self.name = name
        self.ip = ip

    def __str__(self):
        return f"{self.name} ({self.ip})"

# Наследование
class Switch(Device):
    def __init__(self, name, ip, vlan_count):
        super().__init__(name, ip)
        self.vlan_count = vlan_count

# @dataclass — автоматический __init__, __repr__, __eq__
from dataclasses import dataclass, field

@dataclass
class Interface:
    name: str
    status: str = "down"
    speed: int = 0
    tags: list = field(default_factory=list)  # для мутабельных!

# Классовые методы
class Interface:
    @classmethod
    def from_dict(cls, data):
        return cls(name=data["name"], status=data.get("status", "down"))

    def to_dict(self):
        return {"name": self.name, "status": self.status}
```

---

### Задача 7.1. Модель данных Interface

**Контекст:** В проекте модели данных имеют паттерн: `__init__`, `from_dict()`, `to_dict()`, `__str__()`. См. примеры в `core/domain/`.

**Задание:** Напиши класс `Interface` с полями и методами:

```python
class Interface:
    """
    Модель интерфейса.
    Поля: name, status, speed, description, mode, tagged_vlans
    """
    def __init__(self, name, status="down", speed=0, description="",
                 mode="", tagged_vlans=None):
        # Твой код
        pass

    @classmethod
    def from_dict(cls, data):
        """Создать Interface из словаря"""
        # Твой код
        pass

    def to_dict(self):
        """Конвертировать в словарь"""
        # Твой код
        pass

    def __str__(self):
        """Строковое представление: 'Gi0/1 (up, 1000 Mbps)'"""
        # Твой код
        pass

    def is_up(self):
        """Проверка: интерфейс поднят?"""
        # Твой код
        pass

# Тесты
intf = Interface("Gi0/1", status="up", speed=1000, description="Server")
assert intf.name == "Gi0/1"
assert intf.status == "up"
assert intf.is_up() is True
assert str(intf) == "Gi0/1 (up, 1000 Mbps)"

# from_dict
data = {"name": "Gi0/2", "status": "down", "speed": 100}
intf2 = Interface.from_dict(data)
assert intf2.name == "Gi0/2"
assert intf2.is_up() is False
assert intf2.description == ""  # default

# to_dict
d = intf.to_dict()
assert d["name"] == "Gi0/1"
assert d["speed"] == 1000

# tagged_vlans default — пустой список, но РАЗНЫЙ для каждого объекта
intf3 = Interface("Gi0/3")
intf4 = Interface("Gi0/4")
intf3.tagged_vlans.append(10)
assert intf4.tagged_vlans == []  # не должен измениться!
print("Все тесты пройдены!")
```

**Подсказка:**
> Для `tagged_vlans` НЕ пиши `tagged_vlans=[]` в `__init__`! Это ловушка мутабельного default. Пиши `tagged_vlans=None` и внутри: `self.tagged_vlans = tagged_vlans if tagged_vlans is not None else []`.

---

### Задача 7.2. Dataclass SyncResult

**Контекст:** В `core/domain/sync.py` используются dataclass для SyncItem, FieldChange, SyncDiff — лёгкие структуры данных.

**Задание:** Напиши dataclass `SyncResult` и `FieldChange`:

```python
from dataclasses import dataclass, field
from typing import List

@dataclass
class FieldChange:
    """Изменение одного поля"""
    field_name: str
    old_value: str
    new_value: str

    def __str__(self):
        # Формат: "status: down → up"
        # Твой код
        pass

@dataclass
class SyncResult:
    """Результат синхронизации одного интерфейса"""
    name: str
    action: str  # "create", "update", "delete", "skip"
    changes: List[FieldChange] = field(default_factory=list)

    def __str__(self):
        # Формат зависит от action:
        # create: "+ Gi0/1"
        # update: "~ Gi0/1: status: down → up, speed: 100 → 1000"
        # delete: "- Gi0/1"
        # skip:   "= Gi0/1"
        # Твой код
        pass

    @property
    def has_changes(self):
        """Есть ли реальные изменения (не skip)"""
        # Твой код
        pass

# Тесты
fc = FieldChange("status", "down", "up")
assert str(fc) == "status: down → up"

sr_create = SyncResult("Gi0/1", "create")
assert str(sr_create) == "+ Gi0/1"
assert sr_create.has_changes is True

sr_update = SyncResult("Gi0/2", "update", [
    FieldChange("status", "down", "up"),
    FieldChange("speed", "100", "1000"),
])
assert str(sr_update) == "~ Gi0/2: status: down → up, speed: 100 → 1000"

sr_skip = SyncResult("Gi0/3", "skip")
assert str(sr_skip) == "= Gi0/3"
assert sr_skip.has_changes is False

sr_delete = SyncResult("Gi0/4", "delete")
assert str(sr_delete) == "- Gi0/4"
print("Все тесты пройдены!")
```

---

### Задача 7.3. Наследование — BaseNormalizer и потомки

**Контекст:** В проекте нормализаторы (InterfaceNormalizer, MACNormalizer, LLDPNormalizer, InventoryNormalizer) имеют общий паттерн: `normalize()` вызывает `_normalize_row()` для каждой строки.

**Задание:** Напиши базовый класс и двух потомков:

```python
class BaseNormalizer:
    """Базовый нормализатор: normalize() вызывает _normalize_row() для каждого элемента"""

    def normalize(self, data):
        """Нормализовать список данных"""
        # Твой код — вызывает _normalize_row для каждого элемента
        pass

    def _normalize_row(self, row):
        """Нормализовать одну запись. Переопределяется в потомках."""
        raise NotImplementedError("Потомок должен реализовать _normalize_row()")


class MACNormalizer(BaseNormalizer):
    """Нормализует MAC-адреса"""

    def _normalize_row(self, row):
        # Копия словаря + нормализация mac
        # Твой код
        pass


class StatusNormalizer(BaseNormalizer):
    """Нормализует статусы"""

    STATUS_MAP = {
        "connected": "up",
        "notconnect": "down",
        "disabled": "down",
        "err-disabled": "down",
    }

    def _normalize_row(self, row):
        # Копия словаря + нормализация status через STATUS_MAP
        # Твой код
        pass

# Тесты
mac_norm = MACNormalizer()
mac_data = [
    {"name": "Gi0/1", "mac": "AA:BB:CC:DD:EE:FF"},
    {"name": "Gi0/2", "mac": "0011.2233.4455"},
]
result = mac_norm.normalize(mac_data)
assert result[0]["mac"] == "aabbccddeeff"
assert result[1]["mac"] == "001122334455"
assert result[0]["name"] == "Gi0/1"  # остальные поля не тронуты

status_norm = StatusNormalizer()
status_data = [
    {"name": "Gi0/1", "status": "connected"},
    {"name": "Gi0/2", "status": "disabled"},
    {"name": "Gi0/3", "status": "up"},  # не в маппинге — оставить
]
result = status_norm.normalize(status_data)
assert result[0]["status"] == "up"
assert result[1]["status"] == "down"
assert result[2]["status"] == "up"
print("Все тесты пройдены!")
```

---

### Задача 7.4. Класс-кэш с паттерном cache-aside

**Контекст:** В `netbox/sync/base.py` SyncBase использует кэши `_device_cache`, `_interface_cache` — чтобы не делать повторных API-запросов.

**Задание:** Напиши класс `SimpleCache`:

```python
class SimpleCache:
    """
    Простой кэш: сохраняет результаты дорогих операций.
    При повторном запросе — возвращает из кэша без вычисления.
    """
    def __init__(self):
        # Твой код
        pass

    def get_or_compute(self, key, compute_fn):
        """
        Если key в кэше — вернуть из кэша.
        Иначе — вызвать compute_fn(), сохранить результат и вернуть.
        """
        # Твой код
        pass

    def invalidate(self, key):
        """Удалить ключ из кэша"""
        # Твой код
        pass

    def clear(self):
        """Очистить весь кэш"""
        # Твой код
        pass

    @property
    def size(self):
        """Количество записей в кэше"""
        # Твой код
        pass

# Тесты
cache = SimpleCache()
call_count = 0

def expensive_lookup(name):
    """Имитация дорогого API-вызова"""
    global call_count
    call_count += 1
    return {"name": name, "id": call_count}

# Первый вызов — compute_fn вызывается
result1 = cache.get_or_compute("sw1", lambda: expensive_lookup("sw1"))
assert result1["name"] == "sw1"
assert call_count == 1

# Второй вызов с тем же ключом — из кэша
result2 = cache.get_or_compute("sw1", lambda: expensive_lookup("sw1"))
assert result2["name"] == "sw1"
assert call_count == 1  # НЕ увеличился!

# Другой ключ
result3 = cache.get_or_compute("sw2", lambda: expensive_lookup("sw2"))
assert call_count == 2
assert cache.size == 2

# Инвалидация
cache.invalidate("sw1")
assert cache.size == 1
result4 = cache.get_or_compute("sw1", lambda: expensive_lookup("sw1"))
assert call_count == 3  # вычислено заново

cache.clear()
assert cache.size == 0
print("Все тесты пройдены!")
```

---

### Эталонные решения блока 7

<details>
<summary>Нажми чтобы раскрыть решения</summary>

**7.1. Interface:**
```python
class Interface:
    def __init__(self, name, status="down", speed=0, description="",
                 mode="", tagged_vlans=None):
        self.name = name
        self.status = status
        self.speed = speed
        self.description = description
        self.mode = mode
        self.tagged_vlans = tagged_vlans if tagged_vlans is not None else []

    @classmethod
    def from_dict(cls, data):
        return cls(
            name=data["name"],
            status=data.get("status", "down"),
            speed=data.get("speed", 0),
            description=data.get("description", ""),
            mode=data.get("mode", ""),
            tagged_vlans=data.get("tagged_vlans"),
        )

    def to_dict(self):
        return {
            "name": self.name,
            "status": self.status,
            "speed": self.speed,
            "description": self.description,
            "mode": self.mode,
            "tagged_vlans": self.tagged_vlans,
        }

    def __str__(self):
        return f"{self.name} ({self.status}, {self.speed} Mbps)"

    def is_up(self):
        return self.status == "up"
```

**7.2. SyncResult dataclass:**
```python
@dataclass
class FieldChange:
    field_name: str
    old_value: str
    new_value: str

    def __str__(self):
        return f"{self.field_name}: {self.old_value} → {self.new_value}"

@dataclass
class SyncResult:
    name: str
    action: str
    changes: List[FieldChange] = field(default_factory=list)

    def __str__(self):
        prefix = {"create": "+", "update": "~", "delete": "-", "skip": "="}
        symbol = prefix.get(self.action, "?")
        if self.action == "update" and self.changes:
            changes_str = ", ".join(str(c) for c in self.changes)
            return f"{symbol} {self.name}: {changes_str}"
        return f"{symbol} {self.name}"

    @property
    def has_changes(self):
        return self.action != "skip"
```

**7.3. Наследование нормализаторов:**
```python
class BaseNormalizer:
    def normalize(self, data):
        return [self._normalize_row(row) for row in data]

    def _normalize_row(self, row):
        raise NotImplementedError

class MACNormalizer(BaseNormalizer):
    def _normalize_row(self, row):
        result = dict(row)
        mac = result.get("mac", "")
        result["mac"] = mac.replace(":", "").replace("-", "").replace(".", "").lower()
        return result

class StatusNormalizer(BaseNormalizer):
    STATUS_MAP = {"connected": "up", "notconnect": "down",
                  "disabled": "down", "err-disabled": "down"}

    def _normalize_row(self, row):
        result = dict(row)
        status = result.get("status", "").lower().strip()
        result["status"] = self.STATUS_MAP.get(status, status)
        return result
```

**7.4. SimpleCache:**
```python
class SimpleCache:
    def __init__(self):
        self._cache = {}

    def get_or_compute(self, key, compute_fn):
        if key not in self._cache:
            self._cache[key] = compute_fn()
        return self._cache[key]

    def invalidate(self, key):
        self._cache.pop(key, None)

    def clear(self):
        self._cache.clear()

    @property
    def size(self):
        return len(self._cache)
```

</details>

---

## Блок 8. Обработка ошибок и context managers

Сетевое оборудование ненадёжно: подключение рвётся, таймауты, неожиданный вывод. В проекте повсюду `try/except` с разными стратегиями: retry, fallback, пропуск с логированием.

### Теория-напоминание

```python
# Базовый try/except
try:
    result = connect(device)
except ConnectionError as e:
    print(f"Ошибка: {e}")

# Несколько типов исключений
except (ConnectionError, TimeoutError) as e:
    handle_error(e)

# finally — выполнится всегда
try:
    conn = connect()
    data = conn.send("show version")
finally:
    conn.close()

# Свои исключения
class DeviceError(Exception):
    pass

class ConnectionFailed(DeviceError):
    def __init__(self, device, reason):
        self.device = device
        super().__init__(f"Не удалось подключиться к {device}: {reason}")

# Context manager (with statement)
class Timer:
    def __enter__(self):
        self.start = time.time()
        return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.elapsed = time.time() - self.start
        return False  # не подавлять исключения
```

---

### Задача 8.1. Иерархия исключений проекта

**Контекст:** В проекте есть иерархия: `NetworkCollectorError` → `ConnectionError` / `ParseError` / `SyncError`. Каждый тип несёт дополнительный контекст.

**Задание:** Напиши иерархию исключений:

```python
class CollectorError(Exception):
    """Базовая ошибка коллектора"""
    pass

class ConnectionFailed(CollectorError):
    """Ошибка подключения к устройству"""
    def __init__(self, device_name, ip, reason=""):
        self.device_name = device_name
        self.ip = ip
        self.reason = reason
        # Твой код — вызови super().__init__() с понятным сообщением
        pass

class ParseError(CollectorError):
    """Ошибка парсинга вывода"""
    def __init__(self, device_name, command, raw_output=""):
        # Твой код
        pass

class SyncError(CollectorError):
    """Ошибка синхронизации с NetBox"""
    def __init__(self, entity_type, entity_name, operation, reason=""):
        # Твой код
        pass

# Тесты
try:
    raise ConnectionFailed("sw1", "10.0.0.1", "timeout")
except CollectorError as e:  # ловится базовым типом
    assert "sw1" in str(e)
    assert "10.0.0.1" in str(e)

try:
    raise ParseError("sw1", "show version", "garbage output")
except ParseError as e:
    assert e.device_name == "sw1"
    assert e.command == "show version"

try:
    raise SyncError("interface", "Gi0/1", "create", "API 500")
except SyncError as e:
    assert "Gi0/1" in str(e)
    assert "create" in str(e)

# Проверка иерархии
assert issubclass(ConnectionFailed, CollectorError)
assert issubclass(ParseError, CollectorError)
assert issubclass(SyncError, CollectorError)
print("Все тесты пройдены!")
```

---

### Задача 8.2. Collect-and-continue паттерн

**Контекст:** В `collectors/base.py` ошибка одного устройства не останавливает сбор с остальных. Ошибки собираются в список.

**Задание:** Напиши функцию `collect_from_all(devices, collector_fn)`:

```python
def collect_from_all(devices, collector_fn):
    """
    Вызывает collector_fn(device) для каждого устройства.
    Если ошибка — запоминает её и продолжает.
    Возвращает (results, errors).
    """
    # Твой код
    pass

# Тест
def flaky_collector(device):
    """Имитация: sw2 всегда падает"""
    if device["name"] == "sw2":
        raise ConnectionError(f"Timeout connecting to sw2 ({device['ip']})")
    return {"name": device["name"], "interfaces": 24}

devices = [
    {"name": "sw1", "ip": "10.0.0.1"},
    {"name": "sw2", "ip": "10.0.0.2"},
    {"name": "sw3", "ip": "10.0.0.3"},
]

results, errors = collect_from_all(devices, flaky_collector)
assert len(results) == 2
assert len(errors) == 1
assert results[0]["name"] == "sw1"
assert results[1]["name"] == "sw3"
assert "sw2" in str(errors[0])
print("Тест пройден!")
```

---

### Задача 8.3. Retry с backoff

**Контекст:** В `core/connection.py` при разрыве соединения делается retry с увеличивающейся паузой.

**Задание:** Напиши функцию `retry(fn, max_attempts=3, delay=1.0)`:

```python
import time

def retry(fn, max_attempts=3, delay=1.0):
    """
    Вызывает fn(). Если ошибка — ждёт delay секунд и пробует снова.
    Задержка удваивается после каждой попытки (exponential backoff).
    После max_attempts попыток — бросает последнее исключение.
    Возвращает результат fn() при успехе.
    """
    # Твой код
    pass

# Тест (без реальных задержек — замокаем time.sleep)
attempt = 0
def unstable_fn():
    global attempt
    attempt += 1
    if attempt < 3:
        raise ConnectionError(f"Попытка {attempt} не удалась")
    return "success"

# Для теста без ожидания подменим sleep
original_sleep = time.sleep
time.sleep = lambda x: None  # мгновенный "сон"

attempt = 0
result = retry(unstable_fn, max_attempts=5, delay=0.1)
assert result == "success"
assert attempt == 3

# Тест когда все попытки неудачны
attempt = 0
def always_fails():
    global attempt
    attempt += 1
    raise ConnectionError("fail")

try:
    retry(always_fails, max_attempts=3, delay=0.1)
    assert False, "Должно было бросить исключение"
except ConnectionError:
    assert attempt == 3

time.sleep = original_sleep
print("Все тесты пройдены!")
```

---

### Задача 8.4. Context manager для таймера

**Контекст:** Полезно замерять время операций: сбор данных, синхронизация.

**Задание:** Напиши context manager `Timer`:

```python
import time

class Timer:
    """
    Замеряет время выполнения блока кода.
    Использование: with Timer("sync") as t: ...
    После блока: t.elapsed содержит время в секундах.
    """
    def __init__(self, label=""):
        # Твой код
        pass

    def __enter__(self):
        # Твой код
        pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Твой код
        pass

    def __str__(self):
        # Формат: "sync: 1.23 сек" или "0.45 сек" (без label)
        # Твой код
        pass

# Тесты
with Timer("тестовая операция") as t:
    time.sleep(0.1)

assert t.elapsed >= 0.1
assert t.elapsed < 0.5
assert "тестовая операция" in str(t)

with Timer() as t2:
    x = sum(range(1000))

assert t2.elapsed >= 0
assert "сек" in str(t2)
print("Все тесты пройдены!")
```

---

### Эталонные решения блока 8

<details>
<summary>Нажми чтобы раскрыть решения</summary>

**8.1. Иерархия исключений:**
```python
class CollectorError(Exception):
    pass

class ConnectionFailed(CollectorError):
    def __init__(self, device_name, ip, reason=""):
        self.device_name = device_name
        self.ip = ip
        self.reason = reason
        super().__init__(f"Не удалось подключиться к {device_name} ({ip}): {reason}")

class ParseError(CollectorError):
    def __init__(self, device_name, command, raw_output=""):
        self.device_name = device_name
        self.command = command
        self.raw_output = raw_output
        super().__init__(f"Ошибка парсинга '{command}' на {device_name}")

class SyncError(CollectorError):
    def __init__(self, entity_type, entity_name, operation, reason=""):
        self.entity_type = entity_type
        self.entity_name = entity_name
        self.operation = operation
        self.reason = reason
        super().__init__(f"Ошибка {operation} {entity_type} '{entity_name}': {reason}")
```

**8.2. Collect-and-continue:**
```python
def collect_from_all(devices, collector_fn):
    results = []
    errors = []
    for device in devices:
        try:
            result = collector_fn(device)
            results.append(result)
        except Exception as e:
            errors.append(e)
    return results, errors
```

**8.3. Retry:**
```python
def retry(fn, max_attempts=3, delay=1.0):
    last_error = None
    current_delay = delay
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception as e:
            last_error = e
            if attempt < max_attempts - 1:
                time.sleep(current_delay)
                current_delay *= 2
    raise last_error
```

**8.4. Timer:**
```python
class Timer:
    def __init__(self, label=""):
        self.label = label
        self.elapsed = 0.0

    def __enter__(self):
        self._start = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.elapsed = time.time() - self._start
        return False

    def __str__(self):
        if self.label:
            return f"{self.label}: {self.elapsed:.2f} сек"
        return f"{self.elapsed:.2f} сек"
```

</details>

---

## Блок 9. Сравнение данных — SyncComparator

Это ключевой паттерн проекта: сравнить локальные данные (с устройства) с удалёнными (из NetBox), определить что создать, обновить, удалить. Этот блок тренирует именно эту логику.

### Задача 9.1. Простое сравнение двух списков

**Задание:** Напиши функцию `compare_simple(local, remote)`, где оба аргумента — списки словарей с полем `name`. Возвращает `{"to_create": [...], "to_update": [...], "to_delete": [...]}`.

Правила:
- Если имя есть только в local → to_create
- Если имя есть только в remote → to_delete
- Если имя есть в обоих — сравнить поля, если различаются → to_update

```python
def compare_simple(local, remote):
    # Твой код здесь
    pass

# Тест
local = [
    {"name": "Gi0/1", "status": "up", "description": "Server1"},
    {"name": "Gi0/2", "status": "down", "description": ""},
    {"name": "Gi0/3", "status": "up", "description": "New port"},
]
remote = [
    {"name": "Gi0/1", "status": "up", "description": "Server1"},
    {"name": "Gi0/2", "status": "up", "description": "Old desc"},
    {"name": "Gi0/4", "status": "up", "description": "Removed"},
]

result = compare_simple(local, remote)

# Gi0/3 — только в local
assert len(result["to_create"]) == 1
assert result["to_create"][0]["name"] == "Gi0/3"

# Gi0/2 — в обоих, но status и description различаются
assert len(result["to_update"]) == 1
assert result["to_update"][0]["name"] == "Gi0/2"

# Gi0/4 — только в remote
assert len(result["to_delete"]) == 1
assert result["to_delete"][0]["name"] == "Gi0/4"

# Gi0/1 — одинаковый, не попадает никуда
print("Тест пройден!")
```

**Подсказка:**
> Построй индексы: `local_index = {item["name"]: item for item in local}` и `remote_index = {item["name"]: item for item in remote}`. Потом используй set-операции на ключах.

---

### Задача 9.2. Сравнение с определением изменённых полей

**Контекст:** В `core/domain/sync.py` при update определяются конкретные изменённые поля (FieldChange).

**Задание:** Напиши функцию `find_field_changes(local_item, remote_item, fields)`:

```python
def find_field_changes(local_item, remote_item, fields):
    """
    Сравнивает два словаря по указанным полям.
    Возвращает список кортежей (field, old_value, new_value) для различающихся полей.
    """
    # Твой код
    pass

# Тесты
local = {"name": "Gi0/1", "status": "down", "description": "Server", "speed": 1000}
remote = {"name": "Gi0/1", "status": "up", "description": "Server", "speed": 100}

changes = find_field_changes(local, remote, ["status", "description", "speed"])
assert len(changes) == 2
assert ("status", "up", "down") in changes      # old=remote, new=local
assert ("speed", 100, 1000) in changes
# description одинаковый — не включён

no_changes = find_field_changes(local, local, ["status", "description"])
assert no_changes == []
print("Все тесты пройдены!")
```

---

### Задача 9.3. Полный SyncComparator

**Задание:** Собери всё вместе — напиши класс `SimpleSyncComparator`:

```python
class SimpleSyncComparator:
    """
    Сравнивает локальные и удалённые данные.
    compare() возвращает словарь с to_create, to_update, to_delete, unchanged.
    """

    def __init__(self, compare_fields):
        """compare_fields — список полей для сравнения (кроме name)"""
        # Твой код
        pass

    def compare(self, local, remote, exclude_names=None):
        """
        local, remote — списки словарей с полем 'name'.
        exclude_names — set имён для исключения.
        Возвращает dict с 4 ключами.
        """
        # Твой код
        pass

    def _find_changes(self, local_item, remote_item):
        """Находит изменённые поля"""
        # Твой код
        pass

# Тест
comp = SimpleSyncComparator(compare_fields=["status", "description", "speed"])

local = [
    {"name": "Gi0/1", "status": "up", "description": "Server", "speed": 1000},
    {"name": "Gi0/2", "status": "down", "description": "", "speed": 1000},
    {"name": "Gi0/3", "status": "up", "description": "New", "speed": 10000},
    {"name": "Vlan1", "status": "up", "description": "", "speed": 0},
]
remote = [
    {"name": "Gi0/1", "status": "up", "description": "Server", "speed": 1000},
    {"name": "Gi0/2", "status": "up", "description": "Old", "speed": 100},
    {"name": "Gi0/4", "status": "up", "description": "Removed", "speed": 1000},
]

result = comp.compare(local, remote, exclude_names={"Vlan1"})

assert len(result["to_create"]) == 1   # Gi0/3
assert result["to_create"][0]["name"] == "Gi0/3"

assert len(result["to_update"]) == 1   # Gi0/2
update = result["to_update"][0]
assert update["name"] == "Gi0/2"
assert len(update["changes"]) == 3     # status, description, speed

assert len(result["to_delete"]) == 1   # Gi0/4

assert len(result["unchanged"]) == 1   # Gi0/1

# Vlan1 исключён — нигде не фигурирует
all_names = set()
for key in result:
    for item in result[key]:
        all_names.add(item["name"])
assert "Vlan1" not in all_names
print("Тест пройден!")
```

---

### Эталонные решения блока 9

<details>
<summary>Нажми чтобы раскрыть решения</summary>

**9.1. Простое сравнение:**
```python
def compare_simple(local, remote):
    local_index = {item["name"]: item for item in local}
    remote_index = {item["name"]: item for item in remote}
    local_names = set(local_index.keys())
    remote_names = set(remote_index.keys())

    to_create = [local_index[n] for n in local_names - remote_names]
    to_delete = [remote_index[n] for n in remote_names - local_names]
    to_update = []
    for name in local_names & remote_names:
        if local_index[name] != remote_index[name]:
            to_update.append(local_index[name])

    return {"to_create": to_create, "to_update": to_update, "to_delete": to_delete}
```

**9.2. Изменённые поля:**
```python
def find_field_changes(local_item, remote_item, fields):
    changes = []
    for field in fields:
        local_val = local_item.get(field)
        remote_val = remote_item.get(field)
        if local_val != remote_val:
            changes.append((field, remote_val, local_val))
    return changes
```

**9.3. SimpleSyncComparator:**
```python
class SimpleSyncComparator:
    def __init__(self, compare_fields):
        self.compare_fields = compare_fields

    def compare(self, local, remote, exclude_names=None):
        exclude = exclude_names or set()
        local_index = {item["name"]: item for item in local if item["name"] not in exclude}
        remote_index = {item["name"]: item for item in remote}
        local_names = set(local_index.keys())
        remote_names = set(remote_index.keys())

        to_create = [local_index[n] for n in local_names - remote_names]
        to_delete = [{"name": n} for n in remote_names - local_names]
        to_update = []
        unchanged = []

        for name in local_names & remote_names:
            changes = self._find_changes(local_index[name], remote_index[name])
            if changes:
                to_update.append({"name": name, "changes": changes})
            else:
                unchanged.append({"name": name})

        return {
            "to_create": to_create,
            "to_update": to_update,
            "to_delete": to_delete,
            "unchanged": unchanged,
        }

    def _find_changes(self, local_item, remote_item):
        changes = []
        for field in self.compare_fields:
            local_val = local_item.get(field)
            remote_val = remote_item.get(field)
            if local_val != remote_val:
                changes.append((field, remote_val, local_val))
        return changes
```

</details>

---

## Блок 10. Продвинутые паттерны — Enum, property, __getattr__

Этот блок — паттерны, которые ты встретишь в реальном коде проекта. Они не сложнее предыдущих, но менее очевидны.

### Задача 10.1. Enum для типов действий

**Контекст:** В `core/domain/sync.py` используется `class ChangeType(str, Enum)` — можно сравнивать как строку и использовать как enum.

```python
from enum import Enum

class PortType(str, Enum):
    PHYSICAL = "physical"
    LAG = "lag"
    VIRTUAL = "virtual"
    MANAGEMENT = "management"
    UNKNOWN = "unknown"

    @classmethod
    def from_name(cls, interface_name):
        """Определить тип по имени интерфейса"""
        # Твой код:
        # "Gi", "Fa", "Te", "Eth" → PHYSICAL
        # "Po", "Port-channel", "AggregatePort" → LAG
        # "Vlan", "Loopback", "Tunnel" → VIRTUAL
        # "Mgmt", "Management" → MANAGEMENT
        # Всё остальное → UNKNOWN
        pass

# Тесты
assert PortType.from_name("Gi0/1") == PortType.PHYSICAL
assert PortType.from_name("Port-channel1") == PortType.LAG
assert PortType.from_name("Vlan100") == PortType.VIRTUAL
assert PortType.from_name("Mgmt0") == PortType.MANAGEMENT
assert PortType.from_name("UnknownType0") == PortType.UNKNOWN

# str(Enum) — строковое значение
assert PortType.PHYSICAL == "physical"
assert PortType.PHYSICAL.value == "physical"
assert PortType.PHYSICAL.name == "PHYSICAL"
print("Все тесты пройдены!")
```

---

### Задача 10.2. Property — вычисляемые атрибуты

**Контекст:** В `core/domain/sync.py` SyncDiff имеет `@property total_changes` и `has_changes`.

```python
class SyncSummary:
    """Итоги синхронизации с вычисляемыми свойствами"""

    def __init__(self, created=0, updated=0, deleted=0, skipped=0):
        self.created = created
        self.updated = updated
        self.deleted = deleted
        self.skipped = skipped

    @property
    def total_changes(self):
        """Общее количество изменений (без skipped)"""
        # Твой код
        pass

    @property
    def has_changes(self):
        """Есть ли хотя бы одно изменение?"""
        # Твой код
        pass

    @property
    def total_processed(self):
        """Общее количество обработанных (включая skipped)"""
        # Твой код
        pass

    def __str__(self):
        """Формат: 'Создано: 5, Обновлено: 3, Удалено: 1 (пропущено: 12)'"""
        # Твой код
        pass

# Тесты
s1 = SyncSummary(created=5, updated=3, deleted=1, skipped=12)
assert s1.total_changes == 9
assert s1.has_changes is True
assert s1.total_processed == 21

s2 = SyncSummary(skipped=10)
assert s2.total_changes == 0
assert s2.has_changes is False

assert "5" in str(s1) and "3" in str(s1)
print("Все тесты пройдены!")
```

---

### Задача 10.3. __getattr__ — доступ к настройкам через точку

**Контекст:** В `config.py` класс `ConfigSection` позволяет обращаться к настройкам как `config.netbox.url` вместо `config["netbox"]["url"]`.

```python
class DotDict:
    """
    Словарь с доступом через точку.
    d = DotDict({"a": 1, "b": {"c": 2}})
    d.a  → 1
    d.b.c → 2  (вложенные тоже оборачиваются)
    d.missing → None (не KeyError!)
    """
    def __init__(self, data=None):
        # Важно: используй super().__setattr__() для _data
        # иначе попадёшь в рекурсию
        # Твой код
        pass

    def __getattr__(self, name):
        # Твой код
        pass

    def __setattr__(self, name, value):
        # Твой код
        pass

    def to_dict(self):
        """Вернуть обычный dict"""
        # Твой код
        pass

# Тесты
d = DotDict({"name": "sw1", "netbox": {"url": "http://localhost", "timeout": 30}})
assert d.name == "sw1"
assert d.netbox.url == "http://localhost"
assert d.netbox.timeout == 30
assert d.missing is None  # несуществующий ключ → None

d.name = "sw2"
assert d.name == "sw2"

d.new_field = "value"
assert d.new_field == "value"

assert d.to_dict()["name"] == "sw2"
print("Все тесты пройдены!")
```

**Подсказка:**
> В `__init__`: `super().__setattr__("_data", data or {})`. В `__getattr__`: `value = self._data.get(name)`, если value — dict, верни `DotDict(value)`, иначе value.

---

### Эталонные решения блока 10

<details>
<summary>Нажми чтобы раскрыть решения</summary>

**10.1. PortType Enum:**
```python
class PortType(str, Enum):
    PHYSICAL = "physical"
    LAG = "lag"
    VIRTUAL = "virtual"
    MANAGEMENT = "management"
    UNKNOWN = "unknown"

    @classmethod
    def from_name(cls, interface_name):
        name_lower = interface_name.lower()
        physical = ("gi", "fa", "te", "eth", "twentyfive", "hundred")
        lag = ("po", "port-channel", "aggregateport", "ag")
        virtual = ("vlan", "loopback", "lo", "tunnel", "nve")
        mgmt = ("mgmt", "management")

        for prefix in lag:
            if name_lower.startswith(prefix):
                return cls.LAG
        for prefix in virtual:
            if name_lower.startswith(prefix):
                return cls.VIRTUAL
        for prefix in mgmt:
            if name_lower.startswith(prefix):
                return cls.MANAGEMENT
        for prefix in physical:
            if name_lower.startswith(prefix):
                return cls.PHYSICAL
        return cls.UNKNOWN
```

**10.2. SyncSummary:**
```python
class SyncSummary:
    def __init__(self, created=0, updated=0, deleted=0, skipped=0):
        self.created = created
        self.updated = updated
        self.deleted = deleted
        self.skipped = skipped

    @property
    def total_changes(self):
        return self.created + self.updated + self.deleted

    @property
    def has_changes(self):
        return self.total_changes > 0

    @property
    def total_processed(self):
        return self.total_changes + self.skipped

    def __str__(self):
        return (f"Создано: {self.created}, Обновлено: {self.updated}, "
                f"Удалено: {self.deleted} (пропущено: {self.skipped})")
```

**10.3. DotDict:**
```python
class DotDict:
    def __init__(self, data=None):
        super().__setattr__("_data", data or {})

    def __getattr__(self, name):
        value = self._data.get(name)
        if isinstance(value, dict):
            return DotDict(value)
        return value

    def __setattr__(self, name, value):
        self._data[name] = value

    def to_dict(self):
        return dict(self._data)
```

</details>

---

## Блок 11. Batch-операции и статистика

В проекте данные обрабатываются пачками (batch). Вместо создания интерфейсов по одному — отправляется один API-запрос на 50 штук. Это быстрее в 10-50 раз.

### Задача 11.1. Batch-обработка с fallback

**Контекст:** В `netbox/sync/base.py` метод `_batch_with_fallback()` — сначала пробует отправить пачку, при ошибке — по одному.

```python
def batch_process(items, batch_fn, single_fn):
    """
    1. Попробовать обработать все items через batch_fn(items)
    2. Если batch_fn бросил исключение — обработать по одному через single_fn(item)
    3. Вернуть (results, errors)
    """
    # Твой код
    pass

# Тест
def batch_create(items):
    """Имитация: пачка падает если больше 2 элементов"""
    if len(items) > 2:
        raise Exception("Batch too large")
    return [f"created:{item}" for item in items]

def single_create(item):
    """Имитация: поштучно всегда работает, кроме 'bad'"""
    if item == "bad":
        raise ValueError(f"Invalid item: {item}")
    return f"created:{item}"

# Маленькая пачка — batch работает
results, errors = batch_process(["a", "b"], batch_create, single_create)
assert results == ["created:a", "created:b"]
assert errors == []

# Большая пачка — fallback на поштучно
results, errors = batch_process(["a", "b", "c"], batch_create, single_create)
assert results == ["created:a", "created:b", "created:c"]
assert errors == []

# С ошибочным элементом
results, errors = batch_process(["a", "bad", "c"], batch_create, single_create)
assert len(results) == 2  # a и c
assert len(errors) == 1   # bad
print("Все тесты пройдены!")
```

---

### Задача 11.2. Класс SyncStats — накопление статистики

**Контекст:** `SyncStats` в `netbox/sync/base.py` — удобный счётчик с подробностями.

```python
class SyncStats:
    """
    Счётчик операций синхронизации.
    Создаётся с именами операций: SyncStats("created", "updated", "deleted")
    """
    def __init__(self, *operations):
        # stats: {"created": 0, "updated": 0, ...}
        # details: {"created": [], "updated": [], ...}
        # Твой код
        pass

    def record(self, operation, item_name, **extra):
        """
        Записать операцию.
        Увеличивает счётчик и добавляет в details.
        """
        # Твой код
        pass

    def summary(self):
        """Строка: 'created: 5, updated: 3, deleted: 0'"""
        # Твой код
        pass

    @property
    def total(self):
        # Твой код
        pass

# Тесты
ss = SyncStats("created", "updated", "deleted", "skipped")

ss.record("created", "Gi0/1")
ss.record("created", "Gi0/2")
ss.record("updated", "Gi0/3", changes=["status", "speed"])
ss.record("skipped", "Gi0/4")

assert ss.stats["created"] == 2
assert ss.stats["updated"] == 1
assert ss.stats["skipped"] == 1
assert ss.stats["deleted"] == 0
assert ss.total == 4
assert len(ss.details["created"]) == 2
assert ss.details["updated"][0]["name"] == "Gi0/3"
assert "created: 2" in ss.summary()
print("Тест пройден!")
```

---

### Задача 11.3. Dry-run режим

**Контекст:** `--dry-run` — показать что будет сделано, но не делать. В проекте: `if not dry_run: api.create(...)`.

```python
class SyncEngine:
    """
    Простой движок синхронизации с dry_run.
    """
    def __init__(self, dry_run=False):
        self.dry_run = dry_run
        self.log = []  # запись всех операций

    def create(self, name, data):
        """Создать объект. В dry_run — только записать в лог."""
        # Твой код
        pass

    def update(self, name, changes):
        """Обновить объект."""
        # Твой код
        pass

    def delete(self, name):
        """Удалить объект."""
        # Твой код
        pass

    def get_summary(self):
        """Вернуть словарь-счётчик по операциям"""
        # Твой код
        pass

# Тест dry_run=True
engine = SyncEngine(dry_run=True)
engine.create("Gi0/1", {"status": "up"})
engine.update("Gi0/2", {"status": "down"})
engine.delete("Gi0/3")

summary = engine.get_summary()
assert summary["create"] == 1
assert summary["update"] == 1
assert summary["delete"] == 1
# В dry_run никаких реальных вызовов — только логи
assert len(engine.log) == 3
assert engine.log[0]["dry_run"] is True

# Тест dry_run=False
engine2 = SyncEngine(dry_run=False)
engine2.create("Gi0/1", {"status": "up"})
assert engine2.log[0]["dry_run"] is False
print("Все тесты пройдены!")
```

---

### Эталонные решения блока 11

<details>
<summary>Нажми чтобы раскрыть решения</summary>

**11.1. Batch с fallback:**
```python
def batch_process(items, batch_fn, single_fn):
    try:
        results = batch_fn(items)
        return results, []
    except Exception:
        results = []
        errors = []
        for item in items:
            try:
                result = single_fn(item)
                results.append(result)
            except Exception as e:
                errors.append(e)
        return results, errors
```

**11.2. SyncStats:**
```python
class SyncStats:
    def __init__(self, *operations):
        self.stats = {op: 0 for op in operations}
        self.details = {op: [] for op in operations}

    def record(self, operation, item_name, **extra):
        self.stats[operation] = self.stats.get(operation, 0) + 1
        detail = {"name": item_name}
        detail.update(extra)
        if operation not in self.details:
            self.details[operation] = []
        self.details[operation].append(detail)

    def summary(self):
        parts = [f"{op}: {count}" for op, count in self.stats.items()]
        return ", ".join(parts)

    @property
    def total(self):
        return sum(self.stats.values())
```

**11.3. SyncEngine:**
```python
class SyncEngine:
    def __init__(self, dry_run=False):
        self.dry_run = dry_run
        self.log = []

    def create(self, name, data):
        self.log.append({
            "operation": "create", "name": name,
            "data": data, "dry_run": self.dry_run,
        })
        if not self.dry_run:
            pass  # реальный API-вызов

    def update(self, name, changes):
        self.log.append({
            "operation": "update", "name": name,
            "changes": changes, "dry_run": self.dry_run,
        })
        if not self.dry_run:
            pass

    def delete(self, name):
        self.log.append({
            "operation": "delete", "name": name,
            "dry_run": self.dry_run,
        })
        if not self.dry_run:
            pass

    def get_summary(self):
        summary = {}
        for entry in self.log:
            op = entry["operation"]
            summary[op] = summary.get(op, 0) + 1
        return summary
```

</details>

---

## Блок 12. Argparse и CLI

В проекте CLI построен на `argparse`. Это стандартная библиотека Python для парсинга аргументов командной строки.

### Задача 12.1. Простой CLI для сетевых утилит

**Задание:** Напиши CLI-парсер для утилиты с тремя командами:

```python
import argparse

def build_parser():
    """
    Создай парсер с тремя подкомандами:

    1. collect — сбор данных
       --site SITE        фильтр по сайту (опционально)
       --platform PLAT    фильтр по платформе (опционально)
       --format FMT       формат вывода: csv, json, excel (default: csv)

    2. sync — синхронизация
       --dry-run          только показать изменения (флаг)
       --interfaces       синхронизировать интерфейсы (флаг)
       --devices          синхронизировать устройства (флаг)

    3. check — проверка устройств
       --timeout SEC      таймаут в секундах (default: 10, тип int)
       device             позиционный аргумент: имя устройства
    """
    # Твой код здесь
    pass

# Тесты
parser = build_parser()

args = parser.parse_args(["collect", "--site", "Office", "--format", "json"])
assert args.command == "collect"
assert args.site == "Office"
assert args.format == "json"

args = parser.parse_args(["collect"])
assert args.format == "csv"  # default
assert args.site is None

args = parser.parse_args(["sync", "--dry-run", "--interfaces"])
assert args.command == "sync"
assert args.dry_run is True
assert args.interfaces is True
assert args.devices is False

args = parser.parse_args(["check", "sw1", "--timeout", "30"])
assert args.command == "check"
assert args.device == "sw1"
assert args.timeout == 30

args = parser.parse_args(["check", "sw1"])
assert args.timeout == 10  # default
print("Все тесты пройдены!")
```

---

### Задача 12.2. Диспетчер команд

**Контекст:** В `cli/__init__.py` после парсинга идёт `if args.command == "devices": cmd_devices(args)`.

**Задание:** Напиши диспетчер, который вместо цепочки if/elif использует словарь:

```python
def cmd_collect(args):
    return f"Collecting from {args.site or 'all'} as {args.format}"

def cmd_sync(args):
    mode = "dry-run" if args.dry_run else "apply"
    return f"Sync mode: {mode}"

def cmd_check(args):
    return f"Checking {args.device} with timeout {args.timeout}s"

def dispatch(args):
    """
    Вызывает нужный обработчик по args.command.
    Используй словарь вместо if/elif.
    Если команда неизвестна — верни "Unknown command: ..."
    """
    # Твой код
    pass

# Тесты (используй parser из 12.1)
parser = build_parser()

args = parser.parse_args(["collect", "--format", "json"])
assert dispatch(args) == "Collecting from all as json"

args = parser.parse_args(["sync", "--dry-run"])
assert dispatch(args) == "Sync mode: dry-run"

args = parser.parse_args(["check", "sw1"])
assert dispatch(args) == "Checking sw1 with timeout 10s"
print("Все тесты пройдены!")
```

---

### Эталонные решения блока 12

<details>
<summary>Нажми чтобы раскрыть решения</summary>

**12.1. CLI парсер:**
```python
def build_parser():
    parser = argparse.ArgumentParser(description="Network Collector CLI")
    subparsers = parser.add_subparsers(dest="command")

    collect_p = subparsers.add_parser("collect", help="Сбор данных")
    collect_p.add_argument("--site", default=None)
    collect_p.add_argument("--platform", default=None)
    collect_p.add_argument("--format", default="csv", choices=["csv", "json", "excel"])

    sync_p = subparsers.add_parser("sync", help="Синхронизация")
    sync_p.add_argument("--dry-run", action="store_true", default=False)
    sync_p.add_argument("--interfaces", action="store_true", default=False)
    sync_p.add_argument("--devices", action="store_true", default=False)

    check_p = subparsers.add_parser("check", help="Проверка")
    check_p.add_argument("device")
    check_p.add_argument("--timeout", type=int, default=10)

    return parser
```

**12.2. Диспетчер:**
```python
def dispatch(args):
    handlers = {
        "collect": cmd_collect,
        "sync": cmd_sync,
        "check": cmd_check,
    }
    handler = handlers.get(args.command)
    if handler:
        return handler(args)
    return f"Unknown command: {args.command}"
```

</details>

---

## Блок 13. Мини-проект: Нормализатор интерфейсов

Этот блок — написание реального модуля с нуля. Ты соберёшь все навыки из предыдущих блоков.

### Задание

Напиши модуль `interface_normalizer.py`, который делает следующее:

1. Читает JSON-файл со списком "сырых" интерфейсов (как после TextFSM-парсинга)
2. Нормализует каждый интерфейс: имя, статус, MAC, скорость, тип порта
3. Фильтрует по exclude-паттернам
4. Сортирует: LAG первыми, потом физические, потом виртуальные
5. Выводит отчёт в консоль и (опционально) сохраняет в JSON

**Входные данные (создай файл `test_raw_interfaces.json`):**

```json
[
    {"interface": "GigabitEthernet0/1", "link_status": "up", "hardware_address": "AA:BB:CC:DD:EE:01", "bandwidth": "1000000 Kbit", "media_type": "10/100/1000BaseTX"},
    {"interface": "GigabitEthernet0/2", "link_status": "administratively down", "hardware_address": "AA:BB:CC:DD:EE:02", "bandwidth": "100000 Kbit", "media_type": ""},
    {"interface": "GigabitEthernet0/3", "link_status": "connected", "hardware_address": "AA:BB:CC:DD:EE:03", "bandwidth": "1000000 Kbit", "media_type": "1000BaseSX"},
    {"interface": "Port-channel1", "link_status": "up", "hardware_address": "AA:BB:CC:DD:EE:10", "bandwidth": "2000000 Kbit", "media_type": ""},
    {"interface": "Vlan1", "link_status": "up", "hardware_address": "", "bandwidth": "1000000 Kbit", "media_type": ""},
    {"interface": "Vlan100", "link_status": "up", "hardware_address": "", "bandwidth": "1000000 Kbit", "media_type": ""},
    {"interface": "Loopback0", "link_status": "up", "hardware_address": "", "bandwidth": "8000000 Kbit", "media_type": ""},
    {"interface": "Null0", "link_status": "up", "hardware_address": "", "bandwidth": "0 Kbit", "media_type": ""},
    {"interface": "TenGigabitEthernet1/0/1", "link_status": "up", "hardware_address": "AA:BB:CC:DD:EE:20", "bandwidth": "10000000 Kbit", "media_type": "10GBase-SR"}
]
```

**Что должен делать твой код:**

```python
import json
import re

# --- Константы ---
STATUS_MAP = {
    # ... из задачи 1.3
}

INTERFACE_SHORT_MAP = [
    # ... из задачи 1.4
]

TYPE_PRIORITY = {"lag": 0, "physical": 1, "virtual": 2}

EXCLUDE_PATTERNS = [r"^Null\d+", r"^Vlan1$"]

# --- Функции (переиспользуй из предыдущих блоков) ---

def normalize_mac(mac):
    """Из блока 1.1"""
    pass

def normalize_status(raw_status):
    """Из блока 1.3"""
    pass

def shorten_interface(name):
    """Из блока 1.4"""
    pass

def detect_port_type(name):
    """Определить тип порта: lag, physical, virtual"""
    pass

def parse_speed(bandwidth_str):
    """
    '1000000 Kbit' → 1000 (Mbps)
    '10000000 Kbit' → 10000 (Mbps)
    '0 Kbit' → 0
    """
    pass

def is_excluded(name, patterns):
    """Из блока 5.5"""
    pass

# --- Главная функция ---

def normalize_interfaces(raw_data, exclude_patterns=None):
    """
    Принимает список сырых словарей.
    Возвращает список нормализованных и отсортированных словарей.

    Каждый выходной словарь:
    {
        "name": "Gi0/1",           # сокращённое имя
        "full_name": "GigabitEthernet0/1",  # оригинальное
        "status": "up",            # нормализованный
        "mac": "aabbccddee01",     # нормализованный
        "speed": 1000,             # в Mbps
        "port_type": "physical",   # lag/physical/virtual
        "media_type": "10/100/1000BaseTX",
    }
    """
    pass

# --- Отчёт ---

def print_report(interfaces):
    """
    Красивый вывод:
    === Отчёт по интерфейсам (7 шт.) ===
    [LAG]      Po1         up    2000 Mbps
    [physical] Gi0/1       up    1000 Mbps  10/100/1000BaseTX
    [physical] Gi0/2       down   100 Mbps
    ...
    Итого: up=5, down=2
    """
    pass

# --- Точка входа ---
if __name__ == "__main__":
    with open("test_raw_interfaces.json") as f:
        raw = json.load(f)

    result = normalize_interfaces(raw, EXCLUDE_PATTERNS)
    print_report(result)

    # Сохранить результат
    with open("normalized_interfaces.json", "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\nСохранено в normalized_interfaces.json ({len(result)} интерфейсов)")
```

**Критерии готовности:**
- [ ] Null0 и Vlan1 исключены
- [ ] Vlan100 и Loopback0 остались (не попадают под паттерн `^Vlan1$`)
- [ ] Port-channel1 идёт первым (LAG)
- [ ] Имена сокращены (Gi0/1, Te1/0/1, Po1)
- [ ] Статусы нормализованы (connected → up, administratively down → down)
- [ ] MAC нормализованы (нижний регистр, без разделителей)
- [ ] Скорость в Mbps
- [ ] Отчёт выводится красиво

---

## Блок 14. Мини-проект: Детектор изменений (diff)

### Задание

Напиши скрипт `interface_diff.py`, который:
1. Читает два JSON-файла: `before.json` и `after.json` (списки интерфейсов)
2. Находит: новые, удалённые, изменённые, неизменённые
3. Для изменённых показывает конкретные поля
4. Выводит красивый отчёт

**Входные данные:**

```json
// before.json — состояние до
[
    {"name": "Gi0/1", "status": "up", "description": "Server-1", "speed": 1000, "mode": "access", "vlan": 10},
    {"name": "Gi0/2", "status": "up", "description": "Server-2", "speed": 1000, "mode": "access", "vlan": 20},
    {"name": "Gi0/3", "status": "down", "description": "", "speed": 1000, "mode": "access", "vlan": 1},
    {"name": "Gi0/4", "status": "up", "description": "Printer", "speed": 100, "mode": "access", "vlan": 30},
    {"name": "Po1", "status": "up", "description": "Uplink", "speed": 2000, "mode": "trunk", "vlan": 0}
]

// after.json — состояние после
[
    {"name": "Gi0/1", "status": "up", "description": "Server-1", "speed": 1000, "mode": "access", "vlan": 10},
    {"name": "Gi0/2", "status": "down", "description": "Server-2 (maint)", "speed": 1000, "mode": "access", "vlan": 20},
    {"name": "Gi0/3", "status": "up", "description": "New-Server", "speed": 1000, "mode": "trunk", "vlan": 0},
    {"name": "Gi0/5", "status": "up", "description": "WiFi-AP", "speed": 1000, "mode": "access", "vlan": 50},
    {"name": "Po1", "status": "up", "description": "Uplink", "speed": 4000, "mode": "trunk", "vlan": 0}
]
```

**Ожидаемый вывод:**

```
=== Отчёт изменений интерфейсов ===

Новые (1):
  + Gi0/5: WiFi-AP (access, vlan 50)

Удалённые (1):
  - Gi0/4: Printer

Изменённые (3):
  ~ Gi0/2:
      status: up → down
      description: Server-2 → Server-2 (maint)
  ~ Gi0/3:
      status: down → up
      description:  → New-Server
      mode: access → trunk
      vlan: 1 → 0
  ~ Po1:
      speed: 2000 → 4000

Без изменений (1):
  = Gi0/1

Итого: +1 -1 ~3 =1
```

**Что нужно написать:**

```python
import json

def load_json(filepath):
    pass

def compare_interfaces(before, after, compare_fields):
    """
    Используй знания из блока 9.
    Возвращает dict с ключами: created, deleted, updated, unchanged.
    Для updated — включи список изменённых полей.
    """
    pass

def format_report(diff):
    """Формирует строку отчёта"""
    pass

if __name__ == "__main__":
    before = load_json("before.json")
    after = load_json("after.json")
    compare_fields = ["status", "description", "speed", "mode", "vlan"]

    diff = compare_interfaces(before, after, compare_fields)
    print(format_report(diff))
```

**Критерии готовности:**
- [ ] Gi0/5 определён как новый
- [ ] Gi0/4 определён как удалённый
- [ ] Gi0/2, Gi0/3, Po1 — изменённые, с конкретными полями
- [ ] Gi0/1 — без изменений
- [ ] Отчёт читаемый и понятный
- [ ] Итоговая строка с подсчётом

---

## Блок 15. Мини-проект: Анализатор конфигурации устройств

### Задание

Напиши скрипт `config_analyzer.py`, который:
1. Читает файл с конфигурацией устройства (текстовый, формат Cisco IOS)
2. Извлекает: hostname, интерфейсы с описаниями и VLAN, ACL, маршруты
3. Проверяет на типичные проблемы (security audit)
4. Выводит структурированный отчёт

**Входной файл `sample_config.txt`:**

```
hostname SW-OFFICE-01
!
interface GigabitEthernet0/1
 description Server-Web-01
 switchport mode access
 switchport access vlan 10
 spanning-tree portfast
!
interface GigabitEthernet0/2
 description Server-DB-01
 switchport mode access
 switchport access vlan 20
 no shutdown
!
interface GigabitEthernet0/3
 shutdown
!
interface GigabitEthernet0/24
 description Uplink-to-Core
 switchport mode trunk
 switchport trunk allowed vlan 10,20,30,100-110
!
interface Vlan10
 description Management
 ip address 10.0.10.1 255.255.255.0
!
interface Vlan20
 description Servers
 ip address 10.0.20.1 255.255.255.0
!
ip route 0.0.0.0 0.0.0.0 10.0.10.254
ip route 192.168.0.0 255.255.0.0 10.0.20.254
!
line vty 0 4
 password cisco123
 login
 transport input telnet ssh
!
enable secret 5 $1$abcd$xyz
!
snmp-server community public RO
snmp-server community private RW
```

**Что нужно извлечь и проверить:**

```python
import re

class ConfigAnalyzer:
    def __init__(self, config_text):
        self.config = config_text
        self.lines = config_text.splitlines()

    def get_hostname(self):
        """Извлечь hostname"""
        pass

    def get_interfaces(self):
        """
        Извлечь все интерфейсы с их настройками.
        Возвращает список словарей:
        [{"name": "Gi0/1", "description": "...", "mode": "access",
          "vlan": 10, "shutdown": False, "ip": None}, ...]
        """
        pass

    def get_routes(self):
        """
        Извлечь маршруты.
        [{"network": "0.0.0.0", "mask": "0.0.0.0", "gateway": "10.0.10.254"}, ...]
        """
        pass

    def get_vlans_in_use(self):
        """Вернуть set всех VLAN, используемых на интерфейсах"""
        pass

    def security_audit(self):
        """
        Проверить на проблемы:
        - telnet разрешён → предупреждение
        - SNMP community 'public' или 'private' → предупреждение
        - Простые пароли (password без secret) → предупреждение
        - Интерфейсы без description → информация
        Возвращает список строк-предупреждений.
        """
        pass

    def report(self):
        """Собрать полный отчёт"""
        pass

# Точка входа
if __name__ == "__main__":
    with open("sample_config.txt") as f:
        config_text = f.read()

    analyzer = ConfigAnalyzer(config_text)
    print(analyzer.report())
```

**Ожидаемый результат:**

```
=== Анализ конфигурации: SW-OFFICE-01 ===

Интерфейсы (6):
  Gi0/1       access  vlan 10   Server-Web-01
  Gi0/2       access  vlan 20   Server-DB-01
  Gi0/3       (shutdown)
  Gi0/24      trunk             Uplink-to-Core
  Vlan10      L3      10.0.10.1/24  Management
  Vlan20      L3      10.0.20.1/24  Servers

VLANs в использовании: 10, 20, 30, 100-110

Маршруты (2):
  0.0.0.0/0 → 10.0.10.254 (default)
  192.168.0.0/16 → 10.0.20.254

Проблемы безопасности (4):
  [WARN] Telnet разрешён на VTY-линиях
  [WARN] SNMP community 'public' — слишком предсказуемое
  [WARN] SNMP community 'private' RW — опасно!
  [WARN] Пароль на VTY задан через 'password' (не secret)
  [INFO] Интерфейс Gi0/3 без description
```

**Критерии готовности:**
- [ ] Hostname извлечён
- [ ] Все интерфейсы с правильными параметрами
- [ ] VLAN list включает trunk allowed vlans (с разворотом range)
- [ ] Маршруты извлечены
- [ ] Security audit находит минимум 4 проблемы
- [ ] Отчёт читаемый

---

## Как продолжать после этого Workbook

Ты прошёл 15 блоков и написал:
- ~40 мелких функций на строки, словари, списки
- Классы с наследованием, property, enum
- Обработку ошибок и context managers
- SyncComparator — ключевой паттерн проекта
- 3 мини-проекта на 50-150 строк каждый

**Что дальше:**

1. **Перепиши реальные функции проекта.** Открой `core/domain/interface.py`, прочитай `detect_port_type()` — и напиши свою версию с нуля. Потом сравни.

2. **Напиши тесты.** Открой `tests/test_collectors/` — посмотри как написаны тесты. Попробуй написать тест для своей функции из блока 13.

3. **Добавь фичу в проект.** Например:
   - Новый формат экспорта (Markdown-таблица)
   - Фильтрация MAC по вендору (OUI lookup)
   - Команда `check-connectivity` — пинг всех устройств из devices.json

4. **Читай код.** Каждый день 15-20 минут читай один файл проекта. Не весь — одну функцию. Разбирай строку за строкой.

**Главное правило:** лучше 30 минут в день каждый день, чем 5 часов раз в неделю.
