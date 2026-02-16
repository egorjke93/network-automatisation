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

## Улучшение 5: LAG not found → ERROR logging

**Дата:** Февраль 2026
**Категория:** Наблюдаемость (observability)

### Проблема

В 3 местах `netbox/sync/interfaces.py` при `get_interface_by_name()` возвращающем None для LAG интерфейса — логировался `WARNING`. Интерфейс создавался/обновлялся без привязки к LAG, но из-за уровня WARNING это легко пропускалось в логах при массовом запуске (десятки WARNING от других операций).

### Решение

Заменены 3 вызова `logger.warning` → `logger.error` с более информативными сообщениями:

```python
# Было (3 места):
logger.warning(f"LAG интерфейс {intf.lag} не найден для {intf.name}")

# Стало:
logger.error(f"LAG интерфейс {intf.lag} не найден для {intf.name} — member не будет привязан")
```

### Преимущества

- **Видимость в логах:** ERROR выделяется в логах при массовом sync (20+ устройств × 48 портов)
- **Информативность:** Сообщение явно указывает последствие ("member не будет привязан")
- **Мониторинг:** Уровень ERROR проще фильтровать в системах мониторинга (Grafana, ELK)

### Файлы изменены

| Файл | Строки | Что изменено |
|------|--------|-------------|
| `netbox/sync/interfaces.py` | ~445, ~724, ~832 | `logger.warning` → `logger.error` + расширенные сообщения |

---

## Улучшение 6: Batch MAC assignment (bulk_assign_macs)

**Дата:** Февраль 2026
**Категория:** Производительность

### Проблема

`assign_mac_to_interface()` вызывался в цикле для каждого интерфейса. Каждый вызов — 1 API запрос (NetBox `dcim.mac_addresses.create`). При sync устройства с 48 портами = 48 отдельных HTTP запросов только для MAC-адресов.

**Пример масштаба:**
- Pipeline 22 устройства × ~48 портов = ~1056 API запросов
- При latency ~100ms/запрос = ~105 секунд только на MAC

### Решение

Добавлен метод `bulk_assign_macs()` в `netbox/client/dcim.py` — один bulk-вызов вместо цикла. С fallback на поштучные вызовы при ошибке batch.

```python
# Было: цикл по одному в _batch_create_interfaces
for idx, mac in create_mac_queue:
    self.client.assign_mac_to_interface(created[idx].id, mac)

# Стало: один batch вызов
mac_assignments = [(created[idx].id, mac) for idx, mac in create_mac_queue]
self.client.bulk_assign_macs(mac_assignments)
```

Аналогичная замена в `_batch_update_interfaces`.

### Преимущества

- **Скорость:** 48 API запросов → 1 запрос на устройство. Ускорение MAC-фазы в ~40-50x
- **Pipeline 22 устройства:** ~105с MAC → ~2с (22 bulk-запроса вместо 1056 поштучных)
- **Надёжность:** Встроенный fallback — если bulk упал, автоматически переключается на поштучное
- **Сетевая нагрузка:** Меньше TCP соединений, меньше HTTP overhead

### Файлы изменены

| Файл | Что изменено |
|------|-------------|
| `netbox/client/dcim.py` | Новый метод `bulk_assign_macs()` (~35 строк) |
| `netbox/sync/interfaces.py` | `_batch_create_interfaces` и `_batch_update_interfaces` — замена циклов на `bulk_assign_macs()` |

---

## Улучшение 7: Exponential backoff с jitter в retry

**Дата:** Февраль 2026
**Категория:** Производительность, надёжность

### Проблема

`ConnectionManager.connect()` использовал фиксированную задержку `time.sleep(self.retry_delay)` между retry. При параллельном сборе с 100 устройств (ThreadPoolExecutor) все retry приходили одновременно — thundering herd problem.

**Пример:**
```
t=0: 100 устройств подключаются
t=0: 20 получают timeout
t=5: все 20 retry одновременно → снова timeout (сервер перегружен)
t=10: все 20 снова одновременно → fail
```

### Решение

Добавлен метод `_get_retry_delay()` с экспоненциальным backoff и случайным jitter:

```python
def _get_retry_delay(self, attempt: int) -> float:
    """Вычисляет задержку с экспоненциальным backoff и jitter."""
    base_delay = self.retry_delay * (2 ** (attempt - 1))  # 5, 10, 20, 40...
    capped_delay = min(base_delay, 60)  # Макс 60с
    jitter = random.uniform(0, capped_delay * 0.5)  # +0..50%
    return capped_delay + jitter
```

**Пример с retry_delay=5:**
- Попытка 1: 5.0 + random(0..2.5) = 5.0..7.5с
- Попытка 2: 10.0 + random(0..5.0) = 10.0..15.0с
- Попытка 3: 20.0 + random(0..10.0) = 20.0..30.0с

### Преимущества

- **Нет thundering herd:** Retry распределяются равномерно по времени благодаря jitter
- **Exponential backoff:** Увеличивающиеся интервалы дают серверу время на восстановление
- **Cap 60с:** Защита от слишком больших задержек при высоком max_retries
- **Стандартный паттерн:** Тот же подход используется в AWS SDK, gRPC, и Google Cloud Client

### Файлы изменены

| Файл | Что изменено |
|------|-------------|
| `core/connection.py` | `import random`, метод `_get_retry_delay()`, замена 3 вызовов `time.sleep` |
| `tests/test_core/test_connection_retry.py` | Обновлён `test_retry_delay_is_applied` для проверки jitter |

---

## Улучшение 8: Unit-тесты cables sync (21 тест)

**Дата:** Февраль 2026
**Категория:** Тестовое покрытие

### Проблема

`netbox/sync/cables.py` (CablesSyncMixin) не имел unit-тестов. Были только 2 интеграционных теста, которые не покрывали edge cases: dedup A↔B/B↔A, LAG skip, unknown neighbors, cleanup.

### Решение

Создан `tests/test_netbox/test_cables_sync.py` с 21 тестом в 6 классах:

| Класс | Тестов | Покрытие |
|-------|--------|----------|
| `TestCablesSyncBasic` | 4 | Создание, already exists, пустой список, dry_run |
| `TestCablesSyncDeviceLookup` | 4 | Устройство/интерфейс не найден (local + remote) |
| `TestCablesSyncFiltering` | 4 | Skip unknown, allow unknown, skip LAG (local + remote) |
| `TestCablesSyncDedup` | 1 | A↔B и B↔A → 1 кабель |
| `TestFindNeighborDevice` | 6 | Поиск по hostname, IP, MAC, fallback, unknown type |
| `TestCablesCleanup` | 2 | Удаление stale, сохранение валидных |

### Преимущества

- **Regression protection:** Любое изменение в `cables.py` проверяется 21 тестом
- **Edge cases покрыты:** Dedup (частая проблема при LLDP), LAG filtering, neighbor types
- **Рефакторинг безопасен:** Можно менять внутреннюю реализацию при стабильном API
- **Документация кодом:** Тесты описывают ожидаемое поведение для каждого сценария

### Файлы

| Файл | Статус |
|------|--------|
| `tests/test_netbox/test_cables_sync.py` | НОВЫЙ (~280 строк, 21 тест) |

---

## Улучшение 9: Unit-тесты ip_addresses sync (17 тестов)

**Дата:** Февраль 2026
**Категория:** Тестовое покрытие

### Проблема

`netbox/sync/ip_addresses.py` (IPAddressesSyncMixin) не имел unit-тестов. Был только 1 базовый интеграционный тест. Не покрыты: batch create с fallback, mask change recreate, primary IP логика, dry_run.

### Решение

Создан `tests/test_netbox/test_ip_addresses_sync.py` с 17 тестами в 5 классах:

| Класс | Тестов | Покрытие |
|-------|--------|----------|
| `TestIPAddressesSyncBasic` | 4 | Device not found, пустой список, dry_run, create |
| `TestIPAddressBatchCreate` | 3 | Корректные данные, interface not found, batch fallback |
| `TestIPAddressUpdate` | 4 | Mask change (recreate), interface change, no changes, dry_run |
| `TestIPAddressDelete` | 1 | Batch delete dry_run |
| `TestPrimaryIP` | 5 | Already set, set from existing, create if not exists, dry_run, empty string |

### Преимущества

- **Критичный код:** IP-адреса — одна из самых важных сущностей в NetBox
- **Mask change recreate:** Покрыт сложный edge case (NetBox не позволяет менять маску → delete + create)
- **Primary IP:** 5 тестов на установку management IP — ключевая функция для мониторинга
- **Batch + fallback:** Проверка graceful degradation при ошибке bulk API

### Файлы

| Файл | Статус |
|------|--------|
| `tests/test_netbox/test_ip_addresses_sync.py` | НОВЫЙ (~330 строк, 17 тест) |

---

## Баг 5: QTech — пробелы в именах интерфейсов ломали LAG и transceiver

**Дата:** Февраль 2026
**Симптом:** QTech LAG member не привязывался: `LAG интерфейс Ag39 не найден для TFGigabitEthernet 0/39`. Типы интерфейсов (SFP+) из transceiver не подтягивались.

### Причина

QTech TextFSM шаблоны возвращают имена с пробелом: `TFGigabitEthernet 0/39`. Это ломало:
1. **LAG binding:** Имя `TFGigabitEthernet 0/39` не находилось при поиске LAG member
2. **Transceiver matching:** Ключи media_types содержали пробел, нормализованные имена — нет

### Исправление

**Файл:** `core/domain/interface.py` — метод `_normalize_row()`

Добавлена нормализация пробелов на раннем этапе:

```python
# Убираем пробелы в имени интерфейса (QTech: "TFGigabitEthernet 0/39" → "TFGigabitEthernet0/39")
iface_name = row.get("interface", "")
if iface_name:
    result["interface"] = iface_name.replace(" ", "")
```

### Цепочка transceiver → interface type (полная)

Для QTech определение типа интерфейса (SFP+, RJ45) работает через цепочку transceiver:

```
1. SSH → "show interface transceiver"
     ↓
2. TextFSM (qtech_show_interface_transceiver.textfsm)
   Regex: INTERFACE = (\S+\s+\d+/\d+)  ← С ПРОБЕЛОМ!
   Результат: {"INTERFACE": "TFGigabitEthernet 0/1", "TYPE": "10GBASE-SR-SFP+"}
     ↓
3. _parse_media_types() [collectors/interfaces.py:580]
   port = "TFGigabitEthernet 0/1"  (с пробелом)
     ↓
4. get_interface_aliases(port) [core/constants/interfaces.py:148]
   Генерирует ВСЕ варианты имени:
   - "TFGigabitEthernet 0/1"  (оригинал с пробелом)
   - "TFGigabitEthernet0/1"   (без пробела) ← КЛЮЧ для матчинга!
   - "TF0/1"                   (короткая форма)
     ↓
5. media_types = {
     "TFGigabitEthernet 0/1": "10GBASE-SR-SFP+",
     "TFGigabitEthernet0/1": "10GBASE-SR-SFP+",   ← без пробела
     "TF0/1": "10GBASE-SR-SFP+",
   }
     ↓
6. _normalize_row() [core/domain/interface.py]
   "TFGigabitEthernet 0/1" → "TFGigabitEthernet0/1"  (пробел убран)
     ↓
7. enrich_with_media_type() [core/domain/interface.py:482]
   Ищет: "TFGigabitEthernet0/1" in media_types → НАЙДЕНО!
   Устанавливает: media_type = "10GBASE-SR-SFP+"
     ↓
8. detect_port_type() [core/domain/interface.py]
   media_type "10GBASE-SR-SFP+" содержит "sfp" → port_type = "10g-sfp+"
     ↓
9. get_netbox_interface_type() [core/constants/netbox.py]
   "10g-sfp+" → "10gbase-x-sfpp"  (значение для NetBox API)
     ↓
10. NetBox API: interface.type = "10gbase-x-sfpp" (SFP+ 10G)
```

### Порядок операций в _collect_from_device()

```
Line 229: normalize_dicts()           → пробелы УБРАНЫ из interface names
Line 282: _parse_media_types()        → ключи через get_interface_aliases() (оба варианта)
Line 300: enrich_with_media_type()    → матчинг нормализованных имён → НАЙДЕНО
```

Критически важно: `get_interface_aliases()` на строке 171 делает `clean = interface.replace(" ", "")` — это гарантирует что media_types dict содержит ключ БЕЗ пробела, который совпадёт с нормализованным именем.

### Файлы изменены

| Файл | Что изменено |
|------|-------------|
| `core/domain/interface.py` | `_normalize_row()` — добавлен `replace(" ", "")` |
| `tests/test_core/test_domain/test_interface_normalizer.py` | 3 теста: пробелы, transceiver match, aliases |

---

## Баг 6: QTech IP-адреса не парсились из show interfaces

**Дата:** Февраль 2026
**Симптом:** VLAN SVI интерфейсы QTech не получали IP-адреса при sync в NetBox.

### Причина: два дефекта

#### 6a. TextFSM шаблон без IP-полей

**Файл:** `templates/qtech_show_interface.textfsm`

Шаблон не содержал полей `IP_ADDRESS` и `PREFIX_LENGTH`. Формат QTech:
```
Interface address is: 10.0.10.1/24
```

#### 6b. Regex fallback только для Cisco

**Файл:** `collectors/interfaces.py`

Regex fallback для прямого парсинга IP использовал паттерн Cisco:
```python
# Было:
ip_pattern = re.compile(r"Internet address is\s+(\d+\.\d+\.\d+\.\d+)/(\d+)")
```

QTech использует `"Interface address is:"` (с двоеточием), Cisco — `"Internet address is"` (без).

### Исправление

**TextFSM:** Добавлены поля и правило парсинга:
```
Value IP_ADDRESS (\d+\.\d+\.\d+\.\d+)
Value PREFIX_LENGTH (\d+)
...
^\s+Interface\s+address\s+is:\s+${IP_ADDRESS}/${PREFIX_LENGTH}
```

**Regex fallback:** Универсальный паттерн для обеих платформ:
```python
# Стало:
ip_pattern = re.compile(r"(?:Internet|Interface)\s+address\s+is:?\s+(\d+\.\d+\.\d+\.\d+)/(\d+)")
```

### Файлы изменены

| Файл | Что изменено |
|------|-------------|
| `templates/qtech_show_interface.textfsm` | Добавлены IP_ADDRESS, PREFIX_LENGTH + правило парсинга |
| `collectors/interfaces.py` | Regex: `Internet` → `(?:Internet\|Interface)`, добавлена `?` после `:` |
| `tests/test_qtech_templates.py` | 2 теста: IP из Vlan, пустой IP у физических портов |

---

## Баг 7: QTech show version не парсился

**Дата:** Февраль 2026
**Симптом:** Hostname, model, serial, version не заполнялись для QTech устройств.

### Причина

**Файл:** `collectors/device.py`

Коллектор использовал `ntc_templates.parse.parse_output()` напрямую. NTC Templates **не содержит** шаблона для QTech. Кастомный шаблон `qtech_show_version.textfsm` зарегистрирован в `CUSTOM_TEXTFSM_TEMPLATES`, но `parse_output()` не проверяет кастомные шаблоны.

```python
# Было:
from ntc_templates.parse import parse_output
parsed_data = parse_output(platform=ntc_platform, command="show version", data=output)

# Стало:
parsed_data = self._parser.parse(
    output=output,
    platform=device.platform,
    command="show version",
)
```

`NTCParser.parse()` проверяет кастомные шаблоны первым (`CUSTOM_TEXTFSM_TEMPLATES`), затем NTC Templates как fallback.

### Файлы изменены

| Файл | Что изменено |
|------|-------------|
| `collectors/device.py` | Заменён `parse_output()` на `self._parser.parse()`, убраны неиспользуемые imports |

---

## Баг 8: QTech media_types = 0 записей (lowercase ключи TextFSM)

**Дата:** Февраль 2026
**Симптом:** На проде `media_types содержит 0 записей` при 56 распарсенных transceiver записях. Типы интерфейсов (10gbase-sr) не применялись.

### Причина

**Файл:** `parsers/textfsm_parser.py` строка 247

Метод `_parse_with_textfsm()` **всегда** приводит заголовки к lowercase:

```python
headers = [h.lower() for h in fsm.header]
# TextFSM шаблон: INTERFACE, TYPE → dict: {'interface': ..., 'type': ...}
```

А `_parse_media_types()` искал ключи в **UPPERCASE**:

```python
port = row.get("port") or row.get("INTERFACE", "")  # ← "INTERFACE" не найден!
```

`row.get("port")` → None (NTC-ключ, нет в TextFSM), `row.get("INTERFACE")` → None (ключ `interface` lowercase) → `port = ""` → `continue` → все 56 записей пропущены.

### Почему затронут только QTech

| Платформа | Источник media_type | Парсер | Ключи | Статус |
|-----------|-------------------|--------|-------|--------|
| NX-OS | `show interface status` | NTC Templates | `port`, `type` (lowercase) | ✅ Работало |
| QTech | `show interface transceiver` | Кастомный TextFSM | `interface`, `type` (lowercase) | ❌ `"INTERFACE"` не найден |

NTC Templates (`parse_output()`) возвращает ключи в lowercase (`port`). Кастомный TextFSM тоже возвращает lowercase (из-за строки 247), но `_parse_media_types()` искал `"INTERFACE"` в uppercase.

### Исправление

**Файл:** `collectors/interfaces.py` — `_parse_media_types()`

```python
# Было:
port = row.get("port") or row.get("INTERFACE", "")

# Стало:
port = row.get("port") or row.get("interface") or row.get("INTERFACE", "")
```

Добавлен `row.get("interface")` — покрывает lowercase от `_parse_with_textfsm()`.

### Файлы изменены

| Файл | Что изменено |
|------|-------------|
| `collectors/interfaces.py` | Добавлен `row.get("interface")` в цепочку поиска |

---

## Баг 9: QTech show version — MODEL содержал закрывающую скобку

**Дата:** Февраль 2026
**Симптом:** Модель устройства `QSW-6900-56F)` с лишней `)` — не совпадала с моделью в NetBox `QSW-6900-56F`.

### Причина

**Файл:** `templates/qtech_show_version.textfsm`

Regex для MODEL: `(\S+\))` — "непробельные символы + закрывающая скобка". Из строки:
```
System description : Qtech Full 25G Routing Switch(QSW-6900-56F)
```
Захватывал `QSW-6900-56F)` **с `)` на конце**.

Тест использовал `assert "QSW-6900-56F" in entry.get("MODEL")` (substring) → проходил несмотря на лишнюю скобку.

### Исправление

```
# Было:
Value MODEL (\S+\))    → "QSW-6900-56F)"

# Стало:
Value MODEL ([^()]+)   → "QSW-6900-56F"
```

Тест обновлён на точное совпадение: `assert entry.get("MODEL") == "QSW-6900-56F"`.

### Файлы изменены

| Файл | Что изменено |
|------|-------------|
| `templates/qtech_show_version.textfsm` | Regex: `(\S+\))` → `([^()]+)` |
| `tests/test_qtech_templates.py` | `in` → `==` для точной проверки |

---

## Баг 10: --update-devices не работал без --create-devices

**Дата:** Февраль 2026
**Симптом:** `sync-netbox --update-devices` пропускал все устройства — обновления не применялись.

### Причина

**Файл:** `cli/commands/sync.py` строка 83

Весь блок синхронизации устройств был за условием `if create_devices`:

```python
if getattr(args, "create_devices", False):  # ← без --create-devices блок пропускался!
    update_devices = getattr(args, "update_devices", False)
    sync.sync_devices_from_inventory(..., update_existing=update_devices)
```

`--update-devices` устанавливал флаг `update_devices=True`, но без `--create-devices` код даже не доходил до этой строки.

### Исправление

```python
# Было:
if getattr(args, "create_devices", False):

# Стало:
if getattr(args, "create_devices", False) or getattr(args, "update_devices", False):
```

### Файлы изменены

| Файл | Что изменено |
|------|-------------|
| `cli/commands/sync.py` | Условие блока: добавлен `or update_devices` |

---

## Общие уроки

1. **При добавлении платформы — проверять ВСЕ места**, где есть хардкод имён (не только парсинг, но и сортировку, поиск, case-insensitive сравнение)
2. **Не дублировать логику** — один источник правды для алиасов, один для определения LAG. Определение типа интерфейса — ответственность domain layer (`detect_port_type()`), остальные слои используют готовый `port_type`
3. **WARNING, не DEBUG** — для ошибок которые влияют на результат пользователя. ERROR — для ошибок с потерей данных (LAG не привязан)
4. **Порядок elif имеет значение** — при duck typing новая ветка может "украсть" данные у чужой платформы
5. **Двухфазное создание** — если есть зависимости между объектами, всегда проверять что порядок создания правильный для ВСЕХ платформ
6. **Тесты должны отражать реальный data flow** — если нормализатор заполняет `port_type`, тестовые данные тоже должны его содержать
7. **Batch API вместо циклов** — один bulk-запрос вместо N поштучных. Fallback на поштучные при ошибке batch обеспечивает надёжность
8. **Jitter в retry** — стандартный паттерн exponential backoff + random jitter предотвращает thundering herd при параллельном сборе
9. **Unit-тесты для каждого sync mixin** — покрытие edge cases (dedup, fallback, recreate) защищает от регрессий при рефакторинге
10. **Пробелы в именах интерфейсов** — QTech возвращает `TFGigabitEthernet 0/1` с пробелом. Нормализация (`replace(" ", "")`) должна быть на раннем этапе в `_normalize_row()`, а `get_interface_aliases()` — в каждом месте где строится dict по имени интерфейса
11. **Кастомные TextFSM шаблоны** — использовать `NTCParser.parse()` вместо `ntc_templates.parse.parse_output()`. NTCParser проверяет `CUSTOM_TEXTFSM_TEMPLATES` первым
12. **Regex для разных платформ** — один паттерн `(?:Internet|Interface)\s+address\s+is:?\s+` покрывает и Cisco и QTech. При добавлении платформы проверять формат вывода каждой команды
13. **`_parse_with_textfsm()` приводит ключи к lowercase** — при обращении к полям TextFSM использовать lowercase: `row.get("interface")`, не `row.get("INTERFACE")`. Для совместимости проверять оба варианта
14. **TextFSM regex: проверять точное значение** — `(\S+\))` захватывает лишнюю скобку. Тесты с `in` (substring) маскируют проблему — использовать `==` (exact match)
15. **CLI флаги: проверять что каждый работает самостоятельно** — `--update-devices` зависел от `--create-devices`. Каждый флаг должен активировать нужный блок независимо
16. **Тестировать на проде** — unit-тесты с фикстурами не ловят проблемы формата реального вывода. Debug-логирование на каждом шаге цепочки критически важно для отладки
