# Поток данных: match-mac (Сопоставление MAC-адресов)

Подробное описание всей цепочки обработки данных при сопоставлении MAC-адресов с хостами.

## Общая схема

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ПОТОК ДАННЫХ match-mac                            │
└─────────────────────────────────────────────────────────────────────────────┘

1. СБОР MAC-АДРЕСОВ (команда: mac)
   ┌──────────────┐    ┌─────────────────┐    ┌──────────────────┐
   │   Устройство │───>│  MACCollector   │───>│ Модель MACEntry  │
   │  (коммутатор)│    │  collect()      │    │ (поля модели)    │
   └──────────────┘    └─────────────────┘    └────────┬─────────┘
                                                       │
   Поля модели:                                        │
   - mac: "aa:bb:cc:00:10:00"                          │
   - interface: "Ethernet0/0"                          │
   - hostname: "switch1"                               │
   - vlan: "1"                                         │
                                                       ▼
2. ЭКСПОРТ В EXCEL                          ┌──────────────────────┐
   ┌─────────────────┐                      │   fields.yaml        │
   │ apply_fields_   │<─────────────────────│   секция "mac"       │
   │ config()        │                      └──────────────────────┘
   └────────┬────────┘
            │  Переименование полей:
            │  mac → "MAC Address"
            │  interface → "Port"
            │  hostname → "Device"
            ▼
   ┌──────────────────┐
   │  Excel файл      │
   │  mac_addresses   │
   │  .xlsx           │
   └────────┬─────────┘
            │
            │  Колонки в Excel:
            │  "DEVICE", "PORT", "MAC ADDRESS", "VLAN", ...
            │
            ▼
3. ЗАГРУЗКА В match-mac + REVERSE MAPPING
   ┌──────────────────┐
   │  pd.read_excel() │
   │  (pandas)        │
   └────────┬─────────┘
            │
            │  DataFrame с колонками:
            │  "DEVICE", "PORT", "MAC ADDRESS", "VLAN"
            │
            ▼
   ┌──────────────────────────────────────────────────────────────┐
   │  get_reverse_mapping("mac")                                  │
   │                                                              │
   │  Возвращает: {"device": "hostname", "port": "interface",    │
   │               "mac address": "mac", "vlan": "vlan", ...}     │
   └────────┬─────────────────────────────────────────────────────┘
            │
            ▼
4. ПЕРЕИМЕНОВАНИЕ КОЛОНОК (обратный маппинг)
   ┌──────────────────────────────────────────────────────────────┐
   │  mac_df.columns = [                                          │
   │      reverse_map.get(col.lower(), col.lower())               │
   │      for col in mac_df.columns                               │
   │  ]                                                           │
   └────────┬─────────────────────────────────────────────────────┘
            │
            │  Преобразование через reverse_map:
            │  "DEVICE" → "hostname"     (через "device")
            │  "PORT" → "interface"      (через "port")
            │  "MAC ADDRESS" → "mac"     (через "mac address")
            │  "VLAN" → "vlan"
            │
            ▼
   ┌──────────────────┐
   │  mac_df.to_dict  │
   │  ("records")     │
   └────────┬─────────┘
            │
            │  Список словарей с ОРИГИНАЛЬНЫМИ именами полей:
            │  [{"mac": "aa:bb:cc...", "interface": "Et0/0", ...}, ...]
            │
            ▼
5. СОПОСТАВЛЕНИЕ
   ┌─────────────────────────────────────────────────────────────┐
   │  matcher.match_mac_data(                                    │
   │      mac_data,                                              │
   │      mac_field="mac",           # ← оригинальное имя поля!  │
   │      hostname_field="hostname", # ← оригинальное имя поля!  │
   │      interface_field="interface", # ← оригинальное имя поля!│
   │      vlan_field="vlan",                                     │
   │  )                                                          │
   └─────────────────────────────────────────────────────────────┘
```

---

## Детальное описание каждого этапа

### Этап 1: Сбор MAC-адресов

**Файл:** `collectors/mac.py`
**Класс:** `MACCollector`
**Метод:** `collect(devices)`

```python
class MACCollector(BaseCollector):
    """Коллектор MAC-адресов с сетевых устройств."""

    def collect(self, devices: List[Device]) -> List[MACEntry]:
        """
        Собирает MAC-адреса с устройств.

        Выполняет команды:
        - Cisco: "show mac address-table"
        - Arista: "show mac address-table"
        - Juniper: "show ethernet-switching table"

        Returns:
            List[MACEntry]: Список объектов с полями:
                - mac: str - MAC-адрес (aa:bb:cc:dd:ee:ff)
                - interface: str - Интерфейс (Ethernet0/0)
                - hostname: str - Имя коммутатора (switch1)
                - vlan: str - Номер VLAN (1)
                - type: str - Тип записи (dynamic/static)
        """
```

**Модель данных:** `core/models.py`

```python
@dataclass
class MACEntry:
    """Модель записи MAC-адреса."""
    mac: str = ""           # Исходное имя поля
    interface: str = ""     # Исходное имя поля
    vlan: str = ""          # Исходное имя поля
    mac_type: str = "dynamic"
    hostname: str = ""      # Исходное имя поля
```

---

### Этап 2: Экспорт в Excel

**Файл:** `fields_config.py`
**Функция:** `apply_fields_config(data, data_type)`

```python
def apply_fields_config(data: List[Dict], data_type: str) -> List[Dict]:
    """
    Применяет конфигурацию полей к данным.

    Что делает:
    1. Читает fields.yaml секцию для data_type
    2. Оставляет только enabled поля
    3. ПЕРЕИМЕНОВЫВАЕТ поля в display names
    4. Сортирует по order

    Пример для mac:
        Вход:  {"mac": "aa:bb:cc...", "interface": "Et0/0", ...}
        Выход: {"MAC Address": "aa:bb:cc...", "Port": "Et0/0", ...}
    """
```

**Конфигурация:** `fields.yaml`

```yaml
mac:
  hostname:
    enabled: true
    name: "Device"        # ← display name в Excel
    order: 1
  interface:
    enabled: true
    name: "Port"          # ← display name в Excel
    order: 3
  mac:
    enabled: true
    name: "MAC Address"   # ← display name в Excel
    order: 4
  vlan:
    enabled: true
    name: "VLAN"
    order: 5
```

**Результат в Excel:**

| DEVICE | DEVICE IP | PORT | MAC ADDRESS | VLAN | TYPE |
|--------|-----------|------|-------------|------|------|
| switch1 | 192.168.3.35 | Et0/0 | aa:bb:cc:00:10:00 | 1 | dynamic |

---

### Этап 3: Загрузка Excel в match-mac

**Файл:** `cli/commands/match.py`
**Строки:** 18-20

```python
def cmd_match_mac(args, ctx=None):
    # Загружаем Excel файл
    mac_df = pd.read_excel(args.mac_file)

    # DataFrame имеет колонки как в Excel:
    # "DEVICE", "DEVICE IP", "PORT", "MAC ADDRESS", ...
```

**Что возвращает pandas:**

```python
mac_df.columns
# Index(['DEVICE', 'DEVICE IP', 'PORT', 'MAC ADDRESS', 'VLAN', 'TYPE', 'STATUS'])
```

---

### Этап 4: Обратный маппинг (reverse mapping)

**Файл:** `fields_config.py`
**Функция:** `get_reverse_mapping(data_type)`

```python
def get_reverse_mapping(data_type: str) -> Dict[str, str]:
    """
    Возвращает обратный маппинг: display_name → field_name.

    Используется для преобразования колонок Excel обратно в имена полей модели.
    Маппинг НЕчувствителен к регистру (ключи приводятся к lowercase).

    Args:
        data_type: Тип данных (lldp, mac, devices, interfaces, inventory)

    Returns:
        Dict[str, str]: {display_name.lower(): field_name}

    Пример для mac:
        {"device": "hostname", "port": "interface", "mac address": "mac", ...}
    """
```

**Файл:** `cli/commands/match.py`
**Строки:** 22-30

```python
# Получаем обратный маппинг из fields.yaml: display_name → field_name
reverse_map = get_reverse_mapping("mac")

# Переименовываем колонки: "MAC Address" → "mac", "Port" → "interface", etc.
mac_df.columns = [
    reverse_map.get(col.lower(), col.lower())
    for col in mac_df.columns
]
```

**Преобразование:**

| До (Excel) | col.lower() | reverse_map.get() | Результат |
|------------|-------------|-------------------|-----------|
| `DEVICE` | `device` | `hostname` | `hostname` |
| `DEVICE IP` | `device ip` | `device_ip` | `device_ip` |
| `PORT` | `port` | `interface` | `interface` |
| `MAC ADDRESS` | `mac address` | `mac` | `mac` |
| `VLAN` | `vlan` | `vlan` | `vlan` |
| `TYPE` | `type` | `type` | `type` |

**Зачем нужен reverse mapping:**
- **Единый источник правды** — вся информация о маппинге хранится в `fields.yaml`
- **Консистентность** — экспорт и импорт используют одну и ту же конфигурацию
- **Независимость от регистра** — работает с любым регистром колонок в Excel
- **Легкость изменений** — достаточно изменить `fields.yaml`, код не нужно трогать

---

### Этап 5: Конвертация в словари

**Файл:** `cli/commands/match.py`
**Строка:** 31

```python
mac_data = mac_df.to_dict("records")
```

**Результат:**

```python
[
    {
        "hostname": "switch1",       # ← ОРИГИНАЛЬНОЕ имя поля модели
        "device_ip": "192.168.3.35",
        "interface": "Et0/0",        # ← ОРИГИНАЛЬНОЕ имя поля модели
        "mac": "aa:bb:cc:00:10:00",  # ← ОРИГИНАЛЬНОЕ имя поля модели
        "vlan": "1",
        "type": "dynamic",
    },
    # ...
]
```

---

### Этап 6: Вызов match_mac_data()

**Файл:** `cli/commands/match.py`
**Строки:** 53-60

```python
matched = matcher.match_mac_data(
    mac_data,
    mac_field="mac",           # ← Оригинальное имя поля в модели MACEntry
    hostname_field="hostname", # ← Оригинальное имя поля в модели MACEntry
    interface_field="interface",  # ← Оригинальное имя поля в модели MACEntry
    vlan_field="vlan",
    description_field="description",
)
```

**Важно:** Параметры соответствуют **оригинальным именам полей модели**, а не display names из Excel!

---

### Этап 7: Внутренняя работа match_mac_data()

**Файл:** `configurator/description.py`
**Метод:** `DescriptionMatcher.match_mac_data()`

```python
def match_mac_data(
    self,
    mac_data: List[Dict[str, Any]],
    mac_field: str = "mac",           # Имя поля с MAC в входных данных
    hostname_field: str = "hostname", # Имя поля с hostname устройства
    interface_field: str = "interface",
    vlan_field: str = "vlan",
    description_field: str = "description",
) -> List[MatchedEntry]:
    """
    Сопоставляет данные MAC со справочником хостов.

    Алгоритм:
    1. Для каждой записи берёт MAC из поля mac_field
    2. Нормализует MAC (убирает разделители, lowercase)
    3. Ищет в self.reference_data по нормализованному MAC
    4. Если найден — заполняет host_name, matched=True
    """

    for row in mac_data:
        # Берём MAC из поля с именем mac_field
        mac = row.get(mac_field, "")  # ← Вот почему важно правильное имя!
        normalized_mac = normalize_mac(mac)

        # Создаём запись
        entry = MatchedEntry(
            hostname=row.get(hostname_field, ""),
            interface=row.get(interface_field, ""),
            mac=mac,
            vlan=str(row.get(vlan_field, "")),
        )

        # Ищем в справочнике
        if normalized_mac in self.reference_data:
            ref = self.reference_data[normalized_mac]
            entry.host_name = ref.get("name", "")
            entry.matched = True
```

---

## Таблица соответствия имён полей

| Этап | hostname | interface | mac | vlan |
|------|----------|-----------|-----|------|
| **1. Модель (MACEntry)** | `hostname` | `interface` | `mac` | `vlan` |
| **2. fields.yaml** | `name: "Device"` | `name: "Port"` | `name: "MAC Address"` | `name: "VLAN"` |
| **3. Excel колонки** | `DEVICE` | `PORT` | `MAC ADDRESS` | `VLAN` |
| **4. reverse_map ключ** | `device` | `port` | `mac address` | `vlan` |
| **5. После reverse mapping** | `hostname` | `interface` | `mac` | `vlan` |
| **6. Параметры match_mac_data()** | `hostname_field="hostname"` | `interface_field="interface"` | `mac_field="mac"` | `vlan_field="vlan"` |

---

## Архитектурное решение: Single Source of Truth

### Проблема (старая реализация)

В старой реализации нормализация была жёстко закодирована в CLI:

```python
# СТАРЫЙ КОД (плохо)
mac_df.columns = [col.lower().replace(" ", "_") for col in mac_df.columns]
# "MAC ADDRESS" → "mac_address" (НЕ соответствует модели!)

matched = matcher.match_mac_data(
    mac_data,
    mac_field="mac_address",  # Неконсистентно с моделью
    hostname_field="device",   # Неконсистентно с моделью
    interface_field="port",    # Неконсистентно с моделью
)
```

**Проблемы:**
- Жёсткая связь между CLI и форматом Excel
- Изменение в `fields.yaml` ломает match-mac
- Несоответствие именам полей модели

### Решение (текущая реализация)

Используем `get_reverse_mapping()` из `fields_config.py`:

```python
# НОВЫЙ КОД (правильно)
from ...fields_config import get_reverse_mapping

# Получаем маппинг из fields.yaml
reverse_map = get_reverse_mapping("mac")

# Преобразуем колонки обратно в имена модели
mac_df.columns = [
    reverse_map.get(col.lower(), col.lower())
    for col in mac_df.columns
]

matched = matcher.match_mac_data(
    mac_data,
    mac_field="mac",           # Консистентно с моделью
    hostname_field="hostname", # Консистентно с моделью
    interface_field="interface", # Консистентно с моделью
)
```

**Преимущества:**
- **Single Source of Truth** — все маппинги в `fields.yaml`
- **Консистентность** — экспорт и импорт используют один источник
- **Гибкость** — изменение display names не ломает код
- **Соответствие моделям** — используем оригинальные имена полей

---

## Диаграмма преобразования имени поля MAC

```
Модель MACEntry
     │
     │ поле: mac
     │
     ▼
fields.yaml (секция mac)
     │
     │ mac:
     │   name: "MAC Address"
     │
     ▼
apply_fields_config() [ЭКСПОРТ]
     │
     │ {"mac": "aa:bb"} → {"MAC Address": "aa:bb"}
     │
     ▼
Excel файл
     │
     │ колонка: "MAC ADDRESS" (uppercase от Excel)
     │
     ▼
pandas read_excel() [ИМПОРТ]
     │
     │ DataFrame column: "MAC ADDRESS"
     │
     ▼
get_reverse_mapping("mac")
     │
     │ {"mac address": "mac", ...}
     │
     ▼
reverse_map.get(col.lower(), col.lower())
     │
     │ "MAC ADDRESS".lower() = "mac address"
     │ reverse_map.get("mac address") = "mac"
     │
     ▼
to_dict("records")
     │
     │ dict key: "mac"  ← ОРИГИНАЛЬНОЕ ИМЯ!
     │
     ▼
match_mac_data(mac_field="mac")
     │
     │ row.get("mac")
     │
     ▼
Найден MAC для сопоставления!
```

---

## Файлы задействованные в процессе

| Файл | Роль |
|------|------|
| `collectors/mac.py` | Сбор MAC с устройств |
| `core/models.py` | Модель MACEntry с полями |
| `fields.yaml` | Маппинг field → display name |
| `fields_config.py` | `apply_fields_config()` и `get_reverse_mapping()` |
| `exporters/excel.py` | Экспорт в Excel |
| `cli/commands/match.py` | CLI команда match-mac |
| `configurator/description.py` | DescriptionMatcher - сопоставление |
| `core/constants.py` | normalize_mac_raw() |

---

## Тестирование

Проверено на реальных устройствах EVE-NG (192.168.3.35-37):

```bash
# 1. Сбор MAC-адресов
NET_USERNAME=admin NET_PASSWORD=admin \
python -m network_collector mac --format excel -o /tmp/test

# Результат: 45 MAC-адресов с 3 коммутаторов

# 2. Создание справочника хостов
# hosts.xlsx с колонками: MAC, Name

# 3. Сопоставление
python -m network_collector match-mac \
    --mac-file /tmp/test/mac_addresses.xlsx \
    --hosts-file /tmp/test/hosts.xlsx \
    --output /tmp/test/matched.xlsx

# Результат: 9 из 45 записей сопоставлено (20%)
```
