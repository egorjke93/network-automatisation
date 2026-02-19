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

## Баг 8: QTech transceiver типы не применялись (media_types = 0 записей)

**Дата:** Февраль 2026
**Симптом:** На проде QTech интерфейсы получали generic тип (`10gbase-x-sfpp`) вместо точного (`10gbase-sr`). Debug-лог показал: `media_types содержит 0 записей` — при том что TextFSM распарсил 56 transceiver записей.

### Полная цепочка: как устроено определение типа интерфейса

Тип интерфейса в NetBox (например `10gbase-sr` для SFP+ модуля) определяется через цепочку transceiver. Вот как она работает:

```
_collect_from_device() [collectors/interfaces.py]
  │
  ├─ 1. SSH → "show interface transceiver" (QTech)
  │      Вывод: "========Interface TFGigabitEthernet 0/1========
  │              Transceiver Type    :  10GBASE-SR-SFP+"
  │
  ├─ 2. NTCParser.parse(output, "qtech", "show interface transceiver")
  │      │
  │      ├─ Проверяет CUSTOM_TEXTFSM_TEMPLATES[("qtech", "show interface transceiver")]
  │      │  → находит шаблон "qtech_show_interface_transceiver.textfsm"
  │      │
  │      └─ _parse_with_textfsm(output, template_path)
  │           TextFSM шаблон содержит: Value Required INTERFACE (\S+\s+\d+/\d+)
  │                                    Value TYPE (.+)
  │           │
  │           │  ВАЖНО: строка 247 в parsers/textfsm_parser.py:
  │           │  headers = [h.lower() for h in fsm.header]
  │           │  Заголовки ВСЕГДА приводятся к LOWERCASE!
  │           │
  │           └─ Результат: [{"interface": "TFGigabitEthernet 0/1", "type": "10GBASE-SR-SFP+"}, ...]
  │                            ^^^^^^^^^ lowercase!                   ^^^^ lowercase!
  │
  ├─ 3. _parse_media_types(output, platform, command)
  │      │  Получает parsed = [{"interface": ..., "type": ...}, ...]
  │      │
  │      │  Для каждой записи:
  │      │    port = row.get("port") or row.get("interface") or row.get("INTERFACE", "")
  │      │           │                   │                       │
  │      │           │                   │                       └─ UPPERCASE — fallback
  │      │           │                   └─ lowercase — для кастомных TextFSM шаблонов
  │      │           └─ NTC Templates (show interface status, NX-OS) — ключ "port"
  │      │
  │      │    media_type = row.get("type") or row.get("TYPE", "")
  │      │
  │      │  Затем для каждого port вызывает get_interface_aliases(port):
  │      │    "TFGigabitEthernet 0/1" → ["TFGigabitEthernet 0/1",     ← с пробелом
  │      │                                "TFGigabitEthernet0/1",      ← без пробела
  │      │                                "TF0/1"]                     ← короткая форма
  │      │
  │      └─ Результат: media_types = {
  │           "TFGigabitEthernet 0/1": "10GBASE-SR-SFP+",
  │           "TFGigabitEthernet0/1":  "10GBASE-SR-SFP+",   ← для матчинга!
  │           "TF0/1":                 "10GBASE-SR-SFP+",
  │           ...  (все 56 портов × 3 варианта = ~168 ключей)
  │         }
  │
  ├─ 4. normalizer.enrich_with_media_type(data, media_types)
  │      │  Интерфейсы уже нормализованы (_normalize_row убрал пробелы):
  │      │    interface = "TFGigabitEthernet0/1" (без пробела)
  │      │
  │      │  Ищет: "TFGigabitEthernet0/1" in media_types → НАЙДЕНО!
  │      │  Устанавливает: iface["media_type"] = "10GBASE-SR-SFP+"
  │      │
  │      └─ detect_port_type() → "10g-sfp+" (содержит "sfp")
  │
  └─ 5. Позже при sync → get_netbox_interface_type()
         media_type = "10GBASE-SR-SFP+" → lowercase → "10gbase-sr-sfp+"
         Ищет в NETBOX_INTERFACE_TYPE_MAP: "10gbase-sr" in "10gbase-sr-sfp+" → True!
         Результат: "10gbase-sr" (точный тип для NetBox API)
```

### Где была проблема (баг)

Баг был на **шаге 3** — в `_parse_media_types()`:

```python
# БЫЛО (баг):
port = row.get("port") or row.get("INTERFACE", "")
#                                  ^^^^^^^^^ UPPERCASE!
#
# row = {"interface": "TFGigabitEthernet 0/1", "type": "10GBASE-SR-SFP+"}
#
# row.get("port")      → None (нет такого ключа)
# row.get("INTERFACE")  → None (ключ "interface" в LOWERCASE, а ищем "INTERFACE")
# port = ""
# if not port: continue   ← ВСЕ 56 ЗАПИСЕЙ ПРОПУЩЕНЫ!
#
# Результат: media_types = {} (пустой dict)
```

**Почему ключи в lowercase?**

Файл `parsers/textfsm_parser.py`, метод `_parse_with_textfsm()`, строка 247:

```python
headers = [h.lower() for h in fsm.header]
#           ^^^^^^^^^ ВСЕГДА lowercase!
```

TextFSM шаблон определяет поля как `INTERFACE`, `TYPE` (uppercase). Но `_parse_with_textfsm()` приводит все заголовки к lowercase **перед** созданием словаря. Это сделано для унификации — чтобы разные шаблоны возвращали одинаковый формат. Но `_parse_media_types()` об этом не знал и искал `"INTERFACE"` в uppercase.

### Почему баг затронул только QTech

Два пути парсинга media_type:

| Путь | Платформа | Парсер | Как ключи попадают в dict | Какой ключ ищет `_parse_media_types()` | Результат |
|------|-----------|--------|--------------------------|--------------------------------------|-----------|
| NTC Templates | NX-OS | `parse_output()` (библиотека ntc-templates) | Возвращает lowercase: `{"port": ..., "type": ...}` | `row.get("port")` → найден! | ✅ Работало |
| Кастомный TextFSM | QTech | `_parse_with_textfsm()` (наш код) | `h.lower()` → lowercase: `{"interface": ..., "type": ...}` | `row.get("port")` → None, `row.get("INTERFACE")` → None | ❌ Не работало |

**NX-OS** использует NTC Templates (внешняя библиотека), которая возвращает ключ `"port"` — первый вариант в `row.get("port") or ...` находит его сразу.

**QTech** использует кастомный TextFSM шаблон (наш), где поле называется `INTERFACE`. После `h.lower()` ключ становится `"interface"`, а код искал `"INTERFACE"` (uppercase) — не находил.

### Как debug-лог помог найти проблему

Без debug-логирования баг был невидим — `_parse_media_types()` просто возвращал пустой dict, и всё тихо работало без transceiver типов (fallback на generic тип по имени интерфейса).

Debug-логи которые помогли:

```
# Шаг 1: Команда отправлена ✅
collect_media_type=True, platform=qtech_qsw, mt_cmd=show interface transceiver

# Шаг 2: TextFSM распарсил 56 записей ✅
_parse_media_types: parsed 56 записей из transceiver

# Шаг 3: Первая запись — ключи в lowercase ✅ (но это подсказка!)
_parse_media_types: первая запись: {'interface': 'TFGigabitEthernet 0/1', 'type': '10GBASE-SR-SFP+'}

# Шаг 4: ПРОБЛЕМА — 0 записей в dict! ❌
media_types содержит 0 записей
```

Между шагом 2 (56 записей распарсено) и шагом 4 (0 в dict) — теряются все записи. Шаг 3 показывает что ключи lowercase (`interface`). Но код искал uppercase (`INTERFACE`).

### Исправление

**Файл:** `collectors/interfaces.py` — `_parse_media_types()`

```python
# СТАЛО (исправлено):
port = row.get("port") or row.get("interface") or row.get("INTERFACE", "")
#                          ^^^^^^^^^^^^^^^^^^^^
#                          Добавлен lowercase вариант!
```

Теперь цепочка поиска покрывает все варианты:
1. `"port"` — NTC Templates (NX-OS show interface status)
2. `"interface"` — кастомный TextFSM после `h.lower()` (QTech show interface transceiver)
3. `"INTERFACE"` — fallback на случай если TextFSM не приводит к lowercase

### Файлы изменены

| Файл | Что изменено |
|------|-------------|
| `collectors/interfaces.py` | Добавлен `row.get("interface")` в цепочку поиска ключа порта |

### Урок

При работе с двумя путями парсинга (NTC Templates и кастомный TextFSM) нужно учитывать что они возвращают **разные форматы ключей**:
- NTC Templates: свои ключи (`port`, `type`, `name`) — всегда lowercase
- Кастомный TextFSM: ключи из шаблона (`INTERFACE`, `TYPE`) — но `_parse_with_textfsm()` приводит к lowercase

Код который читает результат должен проверять **все возможные варианты** названия ключа, либо нормализовать ключи заранее

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

## Баг 11: QTech — три проблемы: кабели, MAC, administratively down

**Дата:** Февраль 2026
**Симптом:** Три связанные проблемы при работе с QTech:
1. Кабели (LLDP) не создаются — `"Интерфейс не найден: SU-QSW-6900-56F-02:TFGigabitEthernet 0/48"`
2. MAC не назначаются на интерфейсы с IP при повторном sync
3. `administratively down` не парсится TextFSM шаблоном

### 11a. Кабели: пробелы в normalize_interface_full()

**Файл:** `core/constants/interfaces.py`

LLDP возвращает имена с пробелом (`TFGigabitEthernet 0/48`), в NetBox интерфейсы без пробела (`TFGigabitEthernet0/48`). При поиске в `_find_interface()` вызывается `normalize_interface_full()`, но эта функция **не убирала пробелы** (в отличие от `normalize_interface_short()`, где `.replace(" ", "")` уже был).

```python
# Было:
def normalize_interface_full(interface: str) -> str:
    for short_name, full_name in INTERFACE_FULL_MAP.items():
        ...

# Стало:
def normalize_interface_full(interface: str) -> str:
    # Убираем пробелы (QTech: "TFGigabitEthernet 0/48" → "TFGigabitEthernet0/48")
    interface = interface.replace(" ", "").strip()
    for short_name, full_name in INTERFACE_FULL_MAP.items():
        ...
```

### 11b. MAC не назначается на пропущенные интерфейсы

**Файл:** `netbox/sync/interfaces.py`

MAC не входит в `compare_fields` компаратора (description, enabled, mode, mtu, duplex, speed). Если все эти поля совпадают — интерфейс попадает в `to_skip`. Метод `_check_mac()` вызывается только для `to_update`.

**Цепочка:**
```
1. Интерфейс создан без MAC (IP ещё не было → sync_mac_only_with_ip заблокировал)
2. Позже IP появился, повторный sync
3. compare_interfaces() — все поля совпали → to_skip
4. _batch_update_interfaces() обрабатывает только to_update
5. _check_mac() НИКОГДА не вызывается для to_skip
6. MAC не назначается — навсегда
```

**Исправление:** Добавлен метод `_post_sync_mac_check()` — пост-обработка MAC для пропущенных интерфейсов. Вызывается в `sync_interfaces()` после `_batch_update_interfaces()`:

```python
def _post_sync_mac_check(self, to_skip, sorted_interfaces, stats, details) -> int:
    """Проверяет и назначает MAC для пропущенных интерфейсов."""
    # Для каждого skipped интерфейса:
    # 1. Проверяет mac_address enabled, intf.mac, sync_mac_only_with_ip
    # 2. Сравнивает с текущим MAC в NetBox (get_interface_mac)
    # 3. Если отличается — добавляет в очередь
    # Batch назначение через bulk_assign_macs()
```

### 11c. TextFSM: administratively down

**Файл:** `templates/qtech_show_interface.textfsm`

Паттерн LINK_STATUS `(UP|DOWN)` не матчил строку:
```
TFGigabitEthernet 0/3 is administratively down  , line protocol is DOWN
```

```
# Было:
Value LINK_STATUS (UP|DOWN)

# Стало:
Value LINK_STATUS ((?:administratively\s+)?(?:UP|DOWN|up|down))
```

Нормализатор `STATUS_MAP` уже содержал `"administratively down": "disabled"` — нужно было только донести значение из TextFSM.

### Файлы изменены

| Файл | Что изменено |
|------|-------------|
| `core/constants/interfaces.py` | `normalize_interface_full()` — добавлен `.replace(" ", "")` |
| `netbox/sync/interfaces.py` | Новый метод `_post_sync_mac_check()`, вызов в `sync_interfaces()` |
| `templates/qtech_show_interface.textfsm` | LINK_STATUS расширен на `administratively down` |
| `tests/fixtures/qtech/show_interface.txt` | Фикстура: `DOWN` → `administratively down` для TFGi 0/3 |
| `tests/test_qtech_templates.py` | Тест: проверка парсинга `administratively down` |

---

## Баг 12: QTech LLDP — потеря remote_port (NEIGHBOR PORT = None)

**Дата:** Февраль 2026
**Симптом:** В Excel экспорте LLDP столбец NEIGHBOR PORT = None для всех QTech записей. В parsed JSON — заполнен. Кабели не создаются (1 из 10).

### Причина: цепочка потери данных в TextFSM → нормализатор

**Файл 1:** `templates/qtech_show_lldp_neighbors_detail.textfsm`

TextFSM шаблон QTech называл поле Port ID как `NEIGHBOR_INTERFACE`. В нормализаторе `KEY_MAPPING` маппит `neighbor_interface` → `port_description` (так задумано для NTC Templates, где `neighbor_interface` = Port Description).

**Файл 2:** `core/domain/lldp.py` — `KEY_MAPPING`

```
Цепочка потери:
TextFSM: NEIGHBOR_INTERFACE = "TFGigabitEthernet 0/48"  (реальный Port ID)
→ KEY_MAPPING: neighbor_interface → port_description = "TFGigabitEthernet 0/48"
→ PORT_DESCRIPTION → port_description = "peer-keepalive" (ПЕРЕЗАПИСЫВАЕТ!)
→ port_id_value = None (нет поля port_id/neighbor_port_id)
→ remote_port = "" (пусто!)
```

### Исправление

Переименование в TextFSM шаблоне:
```
# Было:
Value NEIGHBOR_INTERFACE (.+)
  ^\s+Port ID\s+:\s+${NEIGHBOR_INTERFACE}

# Стало:
Value NEIGHBOR_PORT_ID (.+)
  ^\s+Port ID\s+:\s+${NEIGHBOR_PORT_ID}
```

`NEIGHBOR_PORT_ID` → lowercased → `neighbor_port_id` → попадает в обработку `port_id_value` в нормализаторе → `_is_interface_name()` → True → `remote_port = "TFGigabitEthernet 0/48"`.

### Файлы изменены

| Файл | Что изменено |
|------|-------------|
| `templates/qtech_show_lldp_neighbors_detail.textfsm` | `NEIGHBOR_INTERFACE` → `NEIGHBOR_PORT_ID` (строки 8, 23) |

---

## Баг 13: QTech LLDP — два соседа на одном порту (двойные TLV)

**Дата:** Февраль 2026
**Симптом:** На порту HundredGigabitEthernet 0/51 QTech — два LLDP объявления от одного Cisco 9500. TextFSM парсил только первое (второе игнорировалось). После исправления бага 12 — оба парсятся, но создаются дубли.

### Причина 1: TextFSM шаблон не поддерживал множественных соседей на порту

Шаблон использовал `Required LOCAL_INTERFACE` без `Filldown`. При переходе `802.1 organizationally -> Record Start` значение LOCAL_INTERFACE очищалось, и в состоянии Start строка `Neighbor index : 2` не матчилась — второй сосед терялся.

### Причина 2: Cisco 9500 отправляет два LLDP TLV

Один и тот же сосед отправляет:
- TLV 1: chassis_id_type="MAC address", Port ID="Hu2/0/52", IP=10.177.30.54
- TLV 2: chassis_id_type="Locally assigned", Port ID="HundredGigE2/0/52", IP=10.195.227.1

Это одно физическое соединение.

### Исправление

**TextFSM:** `Filldown` для LOCAL_INTERFACE + переход `Neighbor index -> NeighborBlock` в Start:
```
Value Filldown,Required LOCAL_INTERFACE (...)

Start
  ^LLDP neighbor-information of port \[${LOCAL_INTERFACE}\] -> NeighborBlock
  ^\s+Neighbor index -> NeighborBlock
```

**Нормализатор:** Метод `_deduplicate_neighbors()` — дедупликация по ключу `(local_interface, remote_hostname_short)`. При дупликатах оставляет запись с remote_port, дополняет remote_mac из другой записи.

### Файлы изменены

| Файл | Что изменено |
|------|-------------|
| `templates/qtech_show_lldp_neighbors_detail.textfsm` | `Filldown` + `Neighbor index` переход + фикс Record target |
| `core/domain/lldp.py` | Метод `_deduplicate_neighbors()`, вызов в `normalize_dicts()` |

---

## Баг 14: Кабели — нормализация имён (удаление/пересоздание)

**Дата:** Февраль 2026
**Симптом:** Кабели ошибочно удаляются и пересоздаются при каждом sync. В логах: удаление `Mgmt0` кабеля → создание `Mgmt 0` кабеля (тот же физический кабель).

### Причина: три места с несогласованными именами

LLDP возвращает "сырые" имена из устройства, NetBox хранит нормализованные:

| LLDP (сырой) | NetBox (нормализованный) |
|---|---|
| `Mgmt 0` | `Mgmt0` |
| `Gi1/0/4` | `GigabitEthernet1/0/4` |
| `HundredGigabitEthernet 0/51` | `HundredGigabitEthernet0/51` |

**Место 1:** `sync_cables_from_lldp()` строка 115 — cable_key использовал сырые LLDP имена.
**Место 2:** `_cleanup_cables()` строка 174 — valid_endpoints из сырых LLDP имён.
**Место 3:** `compare_cables()` строка 482 — endpoint ключи из сырых LLDP данных.

Все три сравнивались с `get_cable_endpoints()`, который возвращал нормализованные имена из NetBox → ключи не совпадали → кабели ошибочно помечались для удаления/создания.

### Исправление

**cables.py:**
```python
# cable_key — из NetBox объектов (нормализованные)
cable_key = tuple(sorted([
    f"{a_name}:{local_intf_obj.name}",
    f"{b_name}:{remote_intf_obj.name}",
]))

# _cleanup_cables — нормализация интерфейсов через SHORT form
local_intf_norm = normalize_interface_short(entry.local_interface, lowercase=True)
remote_port_norm = normalize_interface_short(entry.remote_port, lowercase=True)
```

**sync.py (compare_cables):**
```python
local_dev = _normalize_hostname(item.get("hostname", ""))
local_port = normalize_interface_short(item.get("local_interface", ""), lowercase=True)
```

**base.py (_normalize_interface_name):**
```python
# Было: normalize_interface_full(name.strip()).lower()
# Стало:
return normalize_interface_short(name.strip(), lowercase=True)
```

### Как сопоставляются имена интерфейсов

#### Три формы имён интерфейсов

Для каждого типа интерфейса существуют три формы записи:

| Тип | Short (сокращённая) | Full Cisco | Full QTech |
|-----|---------------------|------------|------------|
| 100G | `Hu0/51` | `HundredGigE0/51` | `HundredGigabitEthernet0/51` |
| 10G | `Te1/0/1` или `TF0/1` | `TenGigabitEthernet1/0/1` | `TFGigabitEthernet0/1` |
| 1G | `Gi0/1` | `GigabitEthernet0/1` | `GigabitEthernet0/1` |
| 25G | `Twe1/0/17` | `TwentyFiveGigE1/0/17` | — |

**Ключевая проблема:** у 100G портов **два разных полных имени** (`HundredGigE` vs `HundredGigabitEthernet`), но **одна сокращённая форма** (`Hu`).

#### Две функции нормализации

| Функция | Направление | Пример |
|---------|------------|--------|
| `normalize_interface_short()` | Full → Short | `HundredGigabitEthernet0/51` → `Hu0/51` |
| `normalize_interface_full()` | Short → Full | `Hu0/51` → `HundredGigE0/51` |

- `normalize_interface_short()` **всегда** приводит к одной короткой форме (и Cisco и QTech):
  - `HundredGigE0/51` → `Hu0/51`
  - `HundredGigabitEthernet0/51` → `Hu0/51`
  - `Hu0/51` → `Hu0/51`

- `normalize_interface_full()` расширяет ТОЛЬКО сокращённые формы и **не знает** какой вендор:
  - `Hu0/51` → `HundredGigE0/51` (всегда Cisco-стиль)
  - `HundredGigabitEthernet0/51` → `HundredGigabitEthernet0/51` (не трогает)

**Вывод:** Для **сравнения** всегда используем `normalize_interface_short(name, lowercase=True)`. Это единственный надёжный способ сопоставить интерфейсы разных вендоров.

#### Где используется нормализация

| Место | Функция | Зачем |
|-------|---------|-------|
| `_find_interface()` | `normalize_interface_short()` | Поиск интерфейса в NetBox по LLDP имени |
| `_cleanup_cables()` | `normalize_interface_short()` | Сравнение LLDP endpoints с NetBox кабелями |
| `compare_cables()` | `normalize_interface_short()` | Diff: какие кабели создать/удалить |
| `cable_key` в sync | Имена из NetBox объектов | Дедупликация A-B = B-A |

Обе функции также **убирают пробелы** (`"Mgmt 0"` → `"Mgmt0"`), что критично для QTech.

### Что иметь в виду при добавлении нового устройства

1. **Проверить TextFSM шаблон** — поле Port ID должно называться `NEIGHBOR_PORT_ID` (не `NEIGHBOR_INTERFACE`)
2. **Проверить пробелы** — если платформа возвращает имена с пробелами, оба normalizer-а уберут их
3. **Проверить INTERFACE_SHORT_MAP** — добавить полное имя → короткое сокращение (`core/constants/interfaces.py`). Это обеспечит правильную нормализацию для сравнений
4. **Проверить INTERFACE_FULL_MAP** — добавить короткое → полное (`core/constants/interfaces.py`). Это обеспечит расширение для отображения
5. **Проверить кабели** — запустить с `--dry-run` и убедиться что нет ложных удалений/созданий
6. **Debug-лог** — `logger.warning` покажет если интерфейс не найден (с указанием raw LLDP имени)

### Файлы изменены

| Файл | Что изменено |
|------|-------------|
| `netbox/sync/cables.py` | cable_key из NetBox объектов, normalize_interface_short в cleanup |
| `core/domain/sync.py` | compare_cables: normalize hostname + interface names через short form |
| `netbox/sync/base.py` | `_normalize_interface_name()`: short form вместо full form |

---

## Баг 15: Устройства создаются в площадке "Main" вместо "SU"

**Дата:** Февраль 2026
**Симптом:** При создании устройства через API оно попадает в сайт "Main", хотя в `fields.yaml` настроен default `site: "SU"`.

### Причина: хардкод "Main" в сигнатурах методов

Два метода имели хардкод `site="Main"` в параметрах по умолчанию:

```python
# netbox/sync/devices.py:139
def sync_devices_from_inventory(self, ..., site: str = "Main"):

# collectors/device.py:416
def __init__(self, ..., site: str = "Main"):
```

Когда вызывающий код не передавал `site`, использовался хардкод "Main" вместо значения из конфига.

### Исправление

Сигнатуры изменены на `site: Optional[str] = None`, внутри метода — чтение из конфига:

```python
def sync_devices_from_inventory(self, ..., site: Optional[str] = None):
    sync_cfg = get_sync_config("devices")
    if site is None:
        site = sync_cfg.get_default("site", "Main")
```

Цепочка приоритетов для site: `CLI --site` > `fields.yaml defaults.site` > `"Main"` (fallback).

### Файлы изменены

| Файл | Что изменено |
|------|-------------|
| `netbox/sync/devices.py` | `sync_devices_from_inventory`: `site: str = "Main"` → `Optional[str] = None` + чтение из конфига |
| `collectors/device.py` | `__init__`: `site: str = "Main"` → `Optional[str] = None` + чтение из конфига |

---

## Баг 16: Дублирование маппингов INTERFACE_NAME_PREFIX_MAP и INTERFACE_NAME_PORT_TYPE_MAP

**Дата:** Февраль 2026
**Симптом:** Два почти идентичных словаря в разных файлах — при добавлении нового типа порта нужно обновлять оба, иначе рассинхрон.

### Дублирование

В проекте было два маппинга с **одинаковыми ключами**, но разными форматами значений:

| Файл | Маппинг | Значения | Пример |
|------|---------|----------|--------|
| `core/constants/interfaces.py` | `INTERFACE_NAME_PORT_TYPE_MAP` | port_type (domain) | `"hundredgig": "100g-qsfp28"` |
| `core/constants/netbox.py` | `INTERFACE_NAME_PREFIX_MAP` | NetBox тип | `"hundredgig": "100gbase-x-qsfp28"` |

А мост между ними — `PORT_TYPE_MAP`: `"100g-qsfp28"` → `"100gbase-x-qsfp28"`.

Также дублировались наборы коротких префиксов:
- `_SHORT_PORT_TYPE_PREFIXES` (interfaces.py) = `_SHORT_PREFIXES` (netbox.py) = `{"hu", "fo", "twe", "tf", "te", "gi", "fa"}`

### Исправление

Удалён `INTERFACE_NAME_PREFIX_MAP` и `_SHORT_PREFIXES` из `netbox.py`. Функция `_detect_type_by_name_prefix()` переписана: использует `INTERFACE_NAME_PORT_TYPE_MAP` (единый источник из interfaces.py) и конвертирует port_type → NetBox тип через `PORT_TYPE_MAP`.

```python
# БЫЛО (netbox.py): два отдельных маппинга
INTERFACE_NAME_PREFIX_MAP = {"hundredgig": "100gbase-x-qsfp28", ...}  # дубль!
for prefix, netbox_type in INTERFACE_NAME_PREFIX_MAP.items():
    return netbox_type

# СТАЛО: единый источник + конвертация
from .interfaces import INTERFACE_NAME_PORT_TYPE_MAP, _SHORT_PORT_TYPE_PREFIXES
for prefix, port_type in INTERFACE_NAME_PORT_TYPE_MAP.items():
    return PORT_TYPE_MAP.get(port_type, port_type)  # port_type → NetBox тип
```

### При добавлении нового типа порта (например 400G)

Теперь нужно обновить **2 места** вместо 3:

1. `core/constants/interfaces.py` → `INTERFACE_NAME_PORT_TYPE_MAP`: `"fourhundredgig": "400g-qsfp-dd"`
2. `core/constants/netbox.py` → `PORT_TYPE_MAP`: `"400g-qsfp-dd": "400gbase-x-qsfp-dd"`

Функция `_detect_type_by_name_prefix()` автоматически подхватит через цепочку.

### Файлы изменены

| Файл | Что изменено |
|------|-------------|
| `core/constants/netbox.py` | Удалён `INTERFACE_NAME_PREFIX_MAP`, `_SHORT_PREFIXES`; импорт из interfaces.py |
| `core/constants/__init__.py` | Убран реэкспорт `INTERFACE_NAME_PREFIX_MAP` |
| `docs/DEVELOPMENT.md` | Обновлены инструкции добавления нового типа |
| `docs/PLATFORM_GUIDE.md` | Обновлен чеклист |
| `docs/learning/12_INTERNALS_AND_TESTING.md` | Обновлены описания маппингов |

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
17. **Пробелы в обеих normalize-функциях** — `normalize_interface_short()` убирал пробелы, `normalize_interface_full()` — нет. При добавлении нормализации проверять симметричность обеих функций
18. **MAC не в compare_fields** — поля, назначаемые через отдельный endpoint (не через bulk update), не участвуют в сравнении компаратора. Нужна пост-обработка для таких полей
19. **TextFSM Value regex ≠ line regex** — паттерн `Value LINK_STATUS (UP|DOWN)` слишком узкий для `administratively down`. При описании Value проверять ВСЕ варианты реального вывода, включая admin-статусы
20. **Data-driven dispatch вместо if/elif** — LAG_PARSERS dict + getattr() заменяет if/elif dispatch по платформе. Добавление новой платформы = одна строка в dict вместо новой ветки
21. **Shared маппинги между слоями** — detect_port_type() (domain) и get_netbox_interface_type() (constants) дублировали speed-паттерны. Решение: общие маппинги в constants/interfaces.py, domain итерирует по ним. constants/netbox.py сохраняет свои более специфичные маппинги (media_type → конкретный NetBox type)
22. **Порядок ключей в dict — контракт** — HARDWARE_TYPE_PORT_TYPE_MAP: "10000" перед "1000", "100/1000/10000" первым. Нарушение порядка = ложное совпадение. Python 3.7+ гарантирует insertion order, но при редактировании dict порядок — не случайность, а архитектурное решение
23. **TextFSM поля — именовать по конвенции NTC Templates** — `NEIGHBOR_PORT_ID` (не `NEIGHBOR_INTERFACE`). Нормализатор LLDP использует `KEY_MAPPING` где `neighbor_interface` → `port_description`. Если назвать поле Port ID как `NEIGHBOR_INTERFACE`, оно попадёт в `port_description` и будет перезаписано реальным Port Description
24. **Дедупликация LLDP TLV** — один и тот же сосед может отправлять несколько LLDP объявлений (разные chassis_id_type: MAC address и Locally assigned). Дедупликация по ключу `(local_interface_short, remote_hostname_short)` гарантирует один сосед на один порт
25. **Short form для сравнения интерфейсов** — `normalize_interface_short()` приводит ВСЕ варианты к одной форме (`HundredGigE`, `HundredGigabitEthernet`, `Hu` → `Hu`). `normalize_interface_full()` расширяет только в один вариант (Cisco) и НЕ подходит для сравнения кросс-вендорных имён
26. **Конфиг вместо хардкода в сигнатурах** — `site: str = "Main"` в параметрах метода = хардкод, который игнорирует `fields.yaml`. Правильно: `site: Optional[str] = None` + `get_sync_config("devices").get_default("site", "Main")` внутри метода
27. **TextFSM Filldown для multi-neighbor** — на одном порту может быть несколько соседей (разные Neighbor index). `Filldown` на `LOCAL_INTERFACE` гарантирует что имя порта наследуется от первого блока к последующим
28. **Один маппинг — один источник** — `INTERFACE_NAME_PREFIX_MAP` (netbox.py) дублировал `INTERFACE_NAME_PORT_TYPE_MAP` (interfaces.py) с другим форматом значений. Решение: убрать дубль, конвертировать через `PORT_TYPE_MAP`. При добавлении нового типа — обновлять только `INTERFACE_NAME_PORT_TYPE_MAP` + `PORT_TYPE_MAP`
29. **Централизация констант** — виртуальные/management/LAG префиксы были захардкожены в нескольких местах с расхождениями. Решение: единые источники `VIRTUAL_INTERFACE_PREFIXES`, `MGMT_INTERFACE_PATTERNS`, `LAG_PREFIXES` из constants, импорт в domain layer. `is_lag_name()` использует `_LAG_LONG_PREFIXES`/`_LAG_SHORT_PREFIXES` вместо хардкода
30. **normalize_hostname — утилита, не локальная функция** — `normalize_hostname()` (strip domain) дублировалась в `cables.py` и inline в `_find_neighbor_device()`. Теперь в `core/constants/utils.py` как единый источник
31. **_is_same_lag() через normalize_interface_short** — вместо 25 строк ручного сравнения `Port-channel1 == Po1 == po1`, одна строка через `normalize_interface_short(name, lowercase=True)`. Надёжнее и автоматически поддерживает новые платформы
32. **HARDWARE_TYPE_PORT_TYPE_MAP неполный** — отсутствовали "tengig" (без пробела), "twentyfive", "twenty-five". NETBOX_HARDWARE_TYPE_MAP имел все варианты, а domain layer — нет. Порты с такими hardware_type получали неверный тип
33. **exclude_interfaces без QTech LAG** — дефолтные `exclude_interfaces` не содержали `AggregatePort`/`Ag\d+`. При сборе MAC с QTech LAG-интерфейсы не фильтровались
