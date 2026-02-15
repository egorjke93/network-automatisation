# Журнал багов и исправлений

Этот документ описывает найденные баги, их причины и способы устранения.
Цель — понимать историю проблем и избегать похожих ошибок.

---

## Баг 1: QTech LAG интерфейсы не привязывались к member-портам

**Дата:** Февраль 2026
**Симптом:** На проде при добавлении QTech не добавились интерфейсы в LAG. В логах: `"LAG интерфейс Ag10 не найден для <interface>"`.

### Причина: три ошибки в цепочке

#### 1a. Двухфазное создание не распознавало QTech LAG

**Файл:** `netbox/sync/interfaces.py`

При создании интерфейсов в NetBox используется двухфазная стратегия:
1. **Фаза 1:** Создать LAG-интерфейсы (Port-channel, AggregatePort)
2. **Фаза 2:** Создать member-интерфейсы с привязкой к LAG

Это нужно, потому что при создании member-интерфейса с полем `lag` нужен ID LAG-интерфейса, который уже должен существовать в NetBox.

**Старый код:**

```python
# Сортировка (строка 92):
def is_lag(intf):
    return 0 if intf.name.lower().startswith(("port-channel", "po")) else 1

# Разделение на фазы (строка 205):
if intf.name.lower().startswith(("port-channel", "po")):
    lag_items.append(...)
else:
    member_items.append(...)
```

**Проблема:** Проверка только `"port-channel"` и `"po"`. QTech LAG интерфейсы называются `AggregatePort1` или `Ag1` — они НЕ распознавались как LAG и создавались во **второй фазе** вместе с member-интерфейсами.

**Результат:** Member-интерфейсы пытались привязаться к LAG, который ещё не создан в NetBox → `"LAG интерфейс Ag10 не найден"`.

**Первое исправление (v1):** добавлена функция `_is_lag_interface()` с проверкой QTech префиксов.

**Проблема v1:** дублирование — те же самые префиксы уже проверялись в `detect_port_type()` (domain layer). При добавлении новой платформы нужно было обновлять оба места.

**Финальное исправление (v2):** удалена `_is_lag_interface()`, используется `port_type == "lag"` — универсальный механизм через поле модели:

```python
# InterfaceNormalizer.detect_port_type() (domain layer) — единый источник:
if iface_lower.startswith(("port-channel", "po", "aggregateport")):
    return "lag"
if len(iface_lower) >= 3 and iface_lower[:2] == "ag" and iface_lower[2].isdigit():
    return "lag"

# Interface.port_type = "lag" — заполняется нормализатором

# Сортировка (sync) — через port_type, не по имени:
sorted_interfaces = sorted(
    interface_models,
    key=lambda intf: 0 if intf.port_type == "lag" else 1,
)

# Разделение на фазы — через port_type:
if intf.port_type == "lag":
    lag_items.append(...)
```

**Архитектурный урок:** не дублировать логику определения типа. Определение LAG — ответственность domain layer (`detect_port_type()`), sync layer должен только использовать результат (`port_type == "lag"`).

#### 1b. Регистронезависимый поиск не включал QTech LAG

**Файл:** `netbox/client/interfaces.py`

Метод `get_interface_by_name()` ищет LAG-интерфейс в NetBox по имени. Поиск идёт в 3 шага:
1. Точное совпадение: `filter(name="Ag1")`
2. Нормализованное имя: `Ag1` → `AggregatePort1`, затем `filter(name="AggregatePort1")`
3. Регистронезависимый поиск (для случаев типа `port-channel1` vs `Port-channel1`)

**Старый код (шаг 3):**

```python
if interface_name.lower().startswith(("po", "port-channel")):
    # case-insensitive search...
```

**Проблема:** Шаг 3 работал только для `po`/`port-channel`. Если в NetBox LAG назван `aggregateport1` (нижний регистр), а ищем `AggregatePort1` — шаги 1 и 2 не найдут, а шаг 3 пропустит.

**Исправление:**

```python
if interface_name.lower().startswith(("po", "port-channel", "ag", "aggregateport")):
    # case-insensitive search...
```

#### 1c. Тихая ошибка при обновлении LAG

**Файл:** `netbox/sync/interfaces.py`

**Старый код:**

```python
# При создании (видно в логах):
logger.warning(f"LAG интерфейс {intf.lag} не найден для {intf.name}")

# При обновлении (НЕ видно в логах!):
logger.debug(f"LAG интерфейс {intf.lag} не найден в NetBox")
```

**Проблема:** При обновлении ошибка логировалась на уровне `DEBUG`, который по умолчанию не выводится. Пользователь не видел что LAG не привязывается.

**Исправление:**

```python
logger.warning(f"LAG интерфейс {intf.lag} не найден в NetBox для {intf.name}")
```

### Полная цепочка: где именно ломалось

```
TextFSM: "Ag10" (из show aggregatePort summary)
  ↓
Collector: lag_membership = {"Hu0/55": "Ag10", ...}
  ↓
Domain: interface.lag = "Ag10"
  ↓
Sync: _batch_create_interfaces()
  ↓
is_lag("Ag10") → False!  ← БАГ 1a: не распознан как LAG
  ↓
Ag10 создаётся во ВТОРОЙ фазе (вместе с members)
  ↓
Member "Hu0/55" пытается найти LAG Ag10 в NetBox → НЕТ (ещё не создан)
  ↓
get_interface_by_name("Ag10") → ищет exact "Ag10" → нет
  ↓
normalize: "Ag10" → "AggregatePort10" → ищет → нет (может быть в другом регистре)
  ↓
case-insensitive: startswith("po", "port-channel") → False  ← БАГ 1b
  ↓
return None → logger.warning("LAG интерфейс Ag10 не найден")
  ↓
Интерфейс создан БЕЗ привязки к LAG
```

### Файлы изменены

| Файл | Что изменено |
|------|-------------|
| `netbox/sync/interfaces.py` | Удалена `_is_lag_interface()`, сортировка и фазы через `port_type == "lag"`, WARNING вместо DEBUG |
| `netbox/client/interfaces.py` | Добавлены `"ag"`, `"aggregateport"` в case-insensitive поиск |

---

## Баг 2: NX-OS switchport mode: tagged вместо tagged-all

**Дата:** Февраль 2026
**Симптом:** Trunk-порты NX-OS с `trunking_vlans: "1-4094"` получали mode `tagged` вместо `tagged-all`.

### Причина

При добавлении QTech ветки в `_normalize_switchport_data()` (тогда ещё в коллекторе) было только два условия:

```python
if admin_mode:           # ← Cisco IOS/Arista
    ...
elif switchport == "enabled":   # ← QTech
    ...
```

NX-OS **не имеет** поля `admin_mode`, но имеет `switchport: "Enabled"` → попадал в QTech ветку. QTech ветка искала `vlan_lists` (которого у NX-OS нет) → mode получался неправильный.

### Исправление

Добавлена отдельная ветка для NX-OS **между** IOS и QTech:

```python
if admin_mode:                                              # Cisco IOS/Arista
    ...
elif row.get("trunking_vlans") is not None and row.get("mode"):  # NX-OS
    ...
elif switchport == "enabled":                               # QTech
    ...
```

NX-OS определяется по наличию `trunking_vlans` + `mode` при отсутствии `admin_mode`.

### Файлы изменены

| Файл | Что изменено |
|------|-------------|
| `core/domain/interface.py` | Добавлена NX-OS ветка в `normalize_switchport_data()` |

---

## Баг 3: QTech кастомный шаблон switchport не применялся

**Дата:** Февраль 2026
**Симптом:** QTech switchport парсился пустым — кастомный TextFSM шаблон не находился.

### Причина

Коллектор вызывал парсер с неправильной платформой или команда не совпадала с ключом в `CUSTOM_TEXTFSM_TEMPLATES`. Ключ `("qtech", "show interface switchport")` требовал точного совпадения, а в коде платформа или команда передавалась иначе.

### Исправление

Выверены все ключи в `CUSTOM_TEXTFSM_TEMPLATES` и передача платформы в парсер `as-is` (без маппинга на `cisco_ios`).

---

## Баг 4: Тройное дублирование алиасов интерфейсов

**Дата:** Февраль 2026
**Симптом:** Не баг в работе, но архитектурная проблема — три копии одной логики.

### Причина

Генерация алиасов имён интерфейсов (`Gi0/1` ↔ `GigabitEthernet0/1`) дублировалась в трёх местах:

1. `collectors/interfaces.py` — `_add_switchport_aliases()` (ручная генерация)
2. `core/domain/interface.py` — `_get_interface_name_variants()` (другая ручная генерация)
3. `collectors/interfaces.py` — `_parse_media_types()` (inline генерация `Eth` → `Ethernet`)

Каждая реализация генерировала **разный** набор алиасов. Если одна обновлялась — другие отставали. Это приводило к тому, что switchport_modes находили интерфейс по одному имени, а enrich_with_switchport не мог найти его по другому.

### Исправление

Все три замены одной функцией `get_interface_aliases()` из `core/constants/interfaces.py`:

| Было | Стало |
|------|-------|
| `_add_switchport_aliases()` (collector) | Удалён |
| `_get_interface_name_variants()` (domain) | Удалён |
| inline `Eth→Ethernet` (collector) | Заменён на `get_interface_aliases()` |

Switchport нормализация (`_normalize_switchport_data()`) перенесена из коллектора в `InterfaceNormalizer` (domain layer) — вся нормализация в одном месте.

### Файлы изменены

| Файл | Что изменено |
|------|-------------|
| `core/domain/interface.py` | Добавлен `normalize_switchport_data()`, удалён `_get_interface_name_variants()` |
| `collectors/interfaces.py` | Удалены `_normalize_switchport_data()`, `_add_switchport_aliases()`, обновлён `_parse_media_types()` |

---

## Общие уроки

1. **При добавлении платформы — проверять ВСЕ места**, где есть хардкод имён (не только парсинг, но и сортировку, поиск, case-insensitive сравнение)
2. **Не дублировать логику** — один источник правды для алиасов, один для определения LAG. Определение типа интерфейса — ответственность domain layer (`detect_port_type()`), остальные слои используют готовый `port_type`
3. **WARNING, не DEBUG** — для ошибок которые влияют на результат пользователя
4. **Порядок elif имеет значение** — при duck typing новая ветка может "украсть" данные у чужой платформы
5. **Двухфазное создание** — если есть зависимости между объектами, всегда проверять что порядок создания правильный для ВСЕХ платформ
6. **Тесты должны отражать реальный data flow** — если нормализатор заполняет `port_type`, тестовые данные тоже должны его содержать
