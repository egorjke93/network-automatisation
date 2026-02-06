# 06. Pipeline -- автоматизация

> **Время чтения:** ~25 минут
>
> **Предыдущий документ:** [05. Синхронизация с NetBox](05_SYNC_NETBOX.md)
>
> **Связанная документация:** [MANUAL.md](../MANUAL.md) -- руководство по использованию, [SYNC_PIPELINE_INTERNALS.md](../SYNC_PIPELINE_INTERNALS.md) -- внутренности sync и pipeline

Как объединить несколько операций (сбор данных, синхронизация, экспорт)
в одну цепочку и запускать её одной командой.

---

## 1. Что такое Pipeline

### Аналогия: конвейер на заводе

Представь автомобильный завод. На конвейере машина проходит через станции:

```
Станция 1        Станция 2         Станция 3        Станция 4
Сварка кузова → Покраска        → Установка       → Проверка
                                   двигателя          качества
```

Каждая станция:
- Делает одну конкретную работу
- Получает результат от предыдущей станции
- Передаёт свой результат дальше
- Если станция сломалась -- конвейер останавливается

Pipeline в нашем проекте -- это такой же конвейер, только для сетевых данных:

```
Шаг 1               Шаг 2              Шаг 3             Шаг 4
Синхронизация    →   Синхронизация   →  Синхронизация  →  Синхронизация
устройств            интерфейсов        IP-адресов         кабелей
(devices)            (interfaces)       (ip_addresses)     (cables)
```

### Зачем нужен Pipeline

Без Pipeline тебе пришлось бы вводить несколько команд вручную:

```bash
# Без Pipeline: 5 отдельных команд
python -m network_collector sync-netbox --devices --apply
python -m network_collector sync-netbox --interfaces --cleanup --apply
python -m network_collector sync-netbox --ip-addresses --cleanup --apply
python -m network_collector sync-netbox --inventory --cleanup --apply
python -m network_collector sync-netbox --cables --cleanup --apply
```

С Pipeline -- одна команда:

```bash
# С Pipeline: 1 команда делает всё
python -m network_collector pipeline run default --apply
```

Pipeline гарантирует правильный **порядок** (сначала устройства, потом интерфейсы)
и **зависимости** (если шаг "devices" упал, то "interfaces" не запустится).

---

## 2. YAML формат -- как описать Pipeline

Pipeline описывается в файле YAML. YAML -- это формат для записи структурированных данных,
похожий на словари и списки Python, но записанный отступами вместо фигурных скобок.

### Реальный файл из проекта

**Файл:** `pipelines/default.yaml`

```yaml
id: default
name: Full Sync
description: 'Полная синхронизация: devices -> interfaces -> IP -> inventory -> cables'
enabled: true
steps:
- id: sync_devices
  type: sync
  target: devices
  enabled: true
  options: {}
  depends_on: []

- id: sync_interfaces
  type: sync
  target: interfaces
  enabled: true
  options:
    cleanup: true
  depends_on:
  - sync_devices

- id: sync_ip_addresses
  type: sync
  target: ip_addresses
  enabled: true
  options:
    cleanup: true
    update_existing: true
  depends_on:
  - sync_interfaces

- id: sync_inventory
  type: sync
  target: inventory
  enabled: true
  options:
    cleanup: true
  depends_on:
  - sync_devices

- id: sync_cables
  type: sync
  target: cables
  enabled: true
  options:
    cleanup: true
  depends_on:
  - sync_interfaces
```

### Разбираем по частям

**Шапка** -- описание самого pipeline:

```yaml
id: default              # Уникальный идентификатор (имя файла)
name: Full Sync          # Человекочитаемое имя
description: '...'       # Описание что делает pipeline
enabled: true            # Включён ли pipeline
```

**Шаг** -- одна операция внутри pipeline:

```yaml
- id: sync_interfaces        # Уникальный ID шага
  type: sync                  # Тип: collect / sync / export
  target: interfaces          # Цель: devices, interfaces, ip_addresses, cables, ...
  enabled: true               # Включён ли шаг (можно временно отключить)
  options:                    # Дополнительные настройки
    cleanup: true             #   cleanup: удалять лишнее из NetBox
  depends_on:                 # Зависимости: какие шаги должны завершиться перед этим
  - sync_devices              #   Этот шаг запустится только после sync_devices
```

### Три типа шагов

| Тип | Что делает | Пример target |
|-----|-----------|---------------|
| `collect` | Собирает данные с устройств по SSH | devices, interfaces, mac, lldp, inventory, backup |
| `sync` | Синхронизирует данные с NetBox | devices, interfaces, cables, inventory, ip_addresses |
| `export` | Экспортирует данные в файл | devices, interfaces, mac (формат: excel, csv, json) |

### Зависимости -- порядок выполнения

`depends_on` определяет, какие шаги должны успешно завершиться **до** текущего шага.
Это как зависимости между станциями конвейера:

```
sync_devices (нет зависимостей -- запускается первым)
     │
     ├── sync_interfaces (ждёт sync_devices)
     │       │
     │       ├── sync_ip_addresses (ждёт sync_interfaces)
     │       │
     │       └── sync_cables (ждёт sync_interfaces)
     │
     └── sync_inventory (ждёт sync_devices)
```

Заметь: `sync_inventory` и `sync_interfaces` оба зависят от `sync_devices`,
но не зависят друг от друга. Если бы проект поддерживал параллельное выполнение,
они могли бы работать одновременно. Сейчас они выполняются последовательно,
в том порядке, в котором записаны в YAML.

### Как YAML соответствует Python

Для понимания -- вот как YAML-структура выглядела бы в Python:

```python
# Это то, что pipeline.from_yaml() создаёт из YAML файла
pipeline = Pipeline(
    id="default",
    name="Full Sync",
    description="Полная синхронизация: devices -> interfaces -> IP -> inventory -> cables",
    enabled=True,
    steps=[
        PipelineStep(
            id="sync_devices",
            type=StepType.SYNC,
            target="devices",
            enabled=True,
            options={},
            depends_on=[],
        ),
        PipelineStep(
            id="sync_interfaces",
            type=StepType.SYNC,
            target="interfaces",
            enabled=True,
            options={"cleanup": True},
            depends_on=["sync_devices"],
        ),
        # ... остальные шаги
    ],
)
```

---

## 3. Модели Pipeline -- PipelineStep и Pipeline

**Файл:** `core/pipeline/models.py`

Модели -- это Python-классы, которые описывают структуру данных Pipeline.
Здесь используются два механизма Python: **Enum** и **dataclass**.

### StepType -- Enum (перечисление)

```python
from enum import Enum

class StepType(str, Enum):
    """Тип шага pipeline."""
    COLLECT = "collect"      # Сбор данных с устройств
    SYNC = "sync"            # Синхронизация с NetBox
    EXPORT = "export"        # Экспорт в файл
```

**Что такое Enum?** Это способ ограничить набор допустимых значений.
Вместо обычной строки `"collect"`, которую легко опечатать (`"colect"`),
мы используем `StepType.COLLECT` -- IDE подскажет и не даст ошибиться.

```python
# Без Enum -- легко ошибиться, никто не проверит
step_type = "colect"  # Опечатка! Но Python не ругнётся

# С Enum -- ошибка сразу видна
step_type = StepType.COLECT  # AttributeError: COLECT -- нет такого!
step_type = StepType.COLLECT  # Правильно
```

`str, Enum` означает что значения Enum -- строки. Это позволяет сравнивать
`StepType.COLLECT == "collect"` (удобно при загрузке из YAML).

### StepStatus -- статус выполнения

```python
class StepStatus(str, Enum):
    """Статус выполнения шага."""
    PENDING = "pending"        # Ожидает выполнения
    RUNNING = "running"        # Выполняется прямо сейчас
    COMPLETED = "completed"    # Завершён успешно
    FAILED = "failed"          # Завершён с ошибкой
    SKIPPED = "skipped"        # Пропущен (зависимость не выполнена)
```

Это как светофор для каждого шага: ожидает, работает, готово, ошибка, пропущен.

### PipelineStep -- один шаг

```python
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

@dataclass
class PipelineStep:
    """Один шаг pipeline."""
    id: str                                          # Уникальный ID ("sync_devices")
    type: StepType                                   # Тип (COLLECT / SYNC / EXPORT)
    target: str                                      # Цель ("devices", "interfaces", ...)
    enabled: bool = True                             # Включён ли шаг
    options: Dict[str, Any] = field(default_factory=dict)   # Настройки {"cleanup": True}
    depends_on: List[str] = field(default_factory=list)     # Зависимости ["sync_devices"]

    # Runtime статус (заполняется при выполнении)
    status: StepStatus = StepStatus.PENDING
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
```

**Что такое `@dataclass`?** Это декоратор, который автоматически создаёт `__init__`
и другие методы. Вместо того чтобы писать:

```python
# Без dataclass -- много повторяющегося кода
class PipelineStep:
    def __init__(self, id, type, target, enabled=True, options=None, depends_on=None):
        self.id = id
        self.type = type
        self.target = target
        self.enabled = enabled
        self.options = options or {}
        self.depends_on = depends_on or []
```

Ты просто перечисляешь поля -- Python сделает `__init__` сам.

**`field(default_factory=dict)`** -- это способ сказать: "по умолчанию создай новый
пустой словарь для каждого экземпляра". Нельзя просто написать `options: dict = {}`,
потому что тогда все экземпляры будут делить один и тот же словарь (ловушка Python
с мутабельными аргументами по умолчанию).

### `__post_init__` -- конвертация после создания

```python
def __post_init__(self):
    """Валидация после создания."""
    if isinstance(self.type, str):
        self.type = StepType(self.type)
    if isinstance(self.status, str):
        self.status = StepStatus(self.status)
```

`__post_init__` -- специальный метод dataclass, который вызывается **после** `__init__`.
Здесь он конвертирует строки в Enum. Это нужно потому что из YAML приходят строки
(`"sync"`), а нам нужны объекты Enum (`StepType.SYNC`).

### Pipeline -- набор шагов

```python
@dataclass
class Pipeline:
    """Pipeline -- набор шагов синхронизации."""
    id: str                                              # Уникальный ID ("default")
    name: str                                            # Имя ("Full Sync")
    description: str = ""                                # Описание
    steps: List[PipelineStep] = field(default_factory=list)  # Список шагов
    enabled: bool = True                                 # Включён ли

    # Runtime
    status: StepStatus = StepStatus.PENDING              # Текущий статус
    current_step: Optional[str] = None                   # Какой шаг выполняется
```

### Загрузка из YAML

Pipeline умеет загружать себя из YAML файла:

```python
@classmethod
def from_yaml(cls, path: str) -> "Pipeline":
    """Загружает pipeline из YAML файла."""
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)    # YAML -> Python dict
    return cls.from_dict(data)      # dict -> Pipeline object
```

`@classmethod` -- это метод, который вызывается на классе, а не на экземпляре:

```python
# classmethod: вызываем на классе Pipeline (не на объекте)
pipeline = Pipeline.from_yaml("pipelines/default.yaml")

# Обычный метод: вызываем на объекте
pipeline.validate()
```

### Валидация -- проверка что pipeline корректный

```python
def validate(self) -> List[str]:
    """Возвращает список ошибок (пустой если всё OK)."""
    errors = []

    if not self.id:
        errors.append("Pipeline id is required")
    if not self.steps:
        errors.append("Pipeline must have at least one step")

    # Проверяем каждый шаг
    for step in self.steps:
        step_errors = step.validate()
        # ...

    # Проверяем зависимости между sync-шагами
    # Например: interfaces требует devices перед собой
    # ...

    return errors
```

Валидация вызывается перед запуском pipeline. Если есть ошибки -- pipeline
не запустится, а покажет список проблем.

### Маппинги зависимостей

В файле моделей определены словари, описывающие связи между шагами:

```python
# Какой collect нужен для какого sync
SYNC_COLLECT_MAPPING = {
    "cables": ["lldp", "cdp"],           # Кабели требуют LLDP или CDP данные
    "ip_addresses": ["interfaces"],       # IP-адреса требуют интерфейсы
}

# Какой sync должен быть выполнен перед каким
SYNC_DEPENDENCIES = {
    "interfaces": ["devices"],      # Интерфейсы требуют устройства
    "cables": ["interfaces"],       # Кабели требуют интерфейсы
    "inventory": ["devices"],       # Inventory требует устройства
    "ip_addresses": ["interfaces"], # IP-адреса требуют интерфейсы
}
```

Эти маппинги используются при валидации (проверить что pipeline описан правильно)
и при автоматическом сборе данных (если sync шагу нужны данные, которых ещё нет).

---

## 4. PipelineExecutor -- как шаги выполняются

**Файл:** `core/pipeline/executor.py`

PipelineExecutor -- это "мотор" конвейера. Он берёт Pipeline (описание шагов)
и выполняет каждый шаг по порядку.

### Создание и запуск

```python
from network_collector.core.pipeline.executor import PipelineExecutor
from network_collector.core.pipeline.models import Pipeline

# Загружаем pipeline из YAML
pipeline = Pipeline.from_yaml("pipelines/default.yaml")

# Создаём executor
executor = PipelineExecutor(
    pipeline,
    dry_run=True,           # Режим "посмотреть что будет"
    on_step_start=...,      # Callback при начале шага
    on_step_complete=...,   # Callback при завершении шага
)

# Запускаем
result = executor.run(
    devices=devices,             # Список устройств
    credentials=creds_dict,      # SSH логин/пароль
    netbox_config=netbox_config, # URL и токен NetBox
)
```

### Контекст -- передача данных между шагами

Ключевая идея: шаги обмениваются данными через **контекст** -- общий словарь,
который живёт на время выполнения pipeline.

```python
class PipelineExecutor:
    def __init__(self, pipeline, dry_run=False, ...):
        self._context: Dict[str, Any] = {}    # Хранилище данных между шагами

    def run(self, devices, credentials=None, netbox_config=None):
        # Инициализация контекста
        self._context = {
            "devices": devices,
            "credentials": credentials or {},
            "netbox_config": netbox_config or {},
            "dry_run": self.dry_run,
            "collected_data": {},  # Сюда collect-шаги складывают результаты
        }
```

Когда collect-шаг собирает данные, он сохраняет их в `self._context["collected_data"]`.
Когда sync-шаг запускается, он берёт нужные данные оттуда:

```
collect interfaces → _context["collected_data"]["interfaces"] = {...}
                                   │
                                   ▼
sync interfaces   ← _context["collected_data"]["interfaces"]
```

### Главный цикл выполнения

```python
def run(self, devices, credentials=None, netbox_config=None):
    # ... инициализация ...

    # Проходим по каждому включённому шагу
    for step in self.pipeline.get_enabled_steps():
        self.pipeline.current_step = step.id

        # 1. Проверяем зависимости
        deps_ok = self._check_dependencies(step, results)
        if not deps_ok:
            # Зависимость не выполнена -- пропускаем шаг
            step_result = StepResult(
                step_id=step.id,
                status=StepStatus.SKIPPED,
                error="Dependencies not met",
            )
            results.append(step_result)
            continue

        # 2. Выполняем шаг
        step.status = StepStatus.RUNNING
        step_result = self._execute_step(step)
        step.status = step_result.status
        results.append(step_result)

        # 3. Если шаг упал -- останавливаем конвейер
        if step_result.status == StepStatus.FAILED:
            self.pipeline.status = StepStatus.FAILED
            break                # Выход из цикла!
```

Три ключевых момента:
1. **Проверка зависимостей** -- шаг запускается только если все его зависимости
   завершились успешно
2. **Выполнение шага** -- вызов нужного метода (collect, sync или export)
3. **Остановка при ошибке** -- если шаг упал, весь pipeline останавливается

### Проверка зависимостей

```python
def _check_dependencies(self, step, results):
    """Проверяет что все зависимости выполнены успешно."""
    # Собираем ID успешно завершённых шагов
    completed_steps = {r.step_id for r in results if r.status == StepStatus.COMPLETED}

    # Каждая зависимость должна быть в completed_steps
    for dep_id in step.depends_on:
        if dep_id not in completed_steps:
            return False

    return True
```

Пример: если `sync_devices` завершился с ошибкой, а `sync_interfaces`
зависит от него, то `_check_dependencies` вернёт `False` и шаг будет пропущен.

### Выполнение шага -- диспетчеризация по типу

```python
def _execute_step(self, step):
    """Выполняет один шаг."""
    try:
        if step.type == StepType.COLLECT:
            data = self._execute_collect(step)     # Сбор с устройств
        elif step.type == StepType.SYNC:
            data = self._execute_sync(step)        # Синхронизация с NetBox
        elif step.type == StepType.EXPORT:
            data = self._execute_export(step)      # Экспорт в файл
        else:
            raise ValueError(f"Unknown step type: {step.type}")

        return StepResult(step_id=step.id, status=StepStatus.COMPLETED, data=data)

    except Exception as e:
        return StepResult(step_id=step.id, status=StepStatus.FAILED, error=str(e))
```

В зависимости от `step.type` вызывается один из трёх методов:
`_execute_collect`, `_execute_sync`, `_execute_export`.

### Как работает _execute_collect

```python
def _execute_collect(self, step):
    """Выполняет collect шаг."""
    target = step.target    # Например "interfaces"
    devices = self._context["devices"]

    # Маппинг target -> класс коллектора
    COLLECTOR_MAPPING = {
        "devices": "DeviceCollector",
        "interfaces": "InterfaceCollector",
        "mac": "MACCollector",
        "lldp": "LLDPCollector",
        "inventory": "InventoryCollector",
        "backup": "ConfigBackupCollector",
    }

    # Получаем нужный коллектор
    collector_class = ...  # По маппингу
    collector = collector_class(**options)

    # Собираем данные
    data = collector.collect_dicts(devices)

    # Сохраняем в контекст для следующих шагов
    self._context["collected_data"][target] = {
        "target": target,
        "data": data,
        "count": len(data),
    }

    return {"target": target, "data": data, "count": len(data)}
```

### Как работает _execute_sync

Sync-шаг умнее простого collect. Он:
1. Проверяет, есть ли нужные данные в контексте
2. Если данных нет -- **автоматически запускает collect**
3. Выполняет синхронизацию

```python
def _execute_sync(self, step):
    """Выполняет sync шаг. Автоматически делает collect если данных нет."""
    target = step.target
    dry_run = self._context["dry_run"]

    # Определяем какой collect нужен для этого sync
    required_collects = SYNC_COLLECT_MAPPING.get(target, [target])
    # Например: для "cables" нужен collect "lldp" или "cdp"
    # Для "interfaces" нужен collect "interfaces"

    # Ищем данные в контексте
    data = []
    for collect_target in required_collects:
        collected = self._context["collected_data"].get(collect_target, {})
        data = collected.get("data", [])
        if data:
            break

    # Если данных нет -- автоматически собираем
    if not data:
        logger.info(f"No {collect_target} data found, auto-collecting...")
        # Создаём временный collect шаг и выполняем
        auto_collect_step = PipelineStep(
            id=f"auto_collect_{collect_target}",
            type=StepType.COLLECT,
            target=collect_target,
        )
        self._execute_collect(auto_collect_step)
        # Теперь данные есть в контексте
        data = self._context["collected_data"].get(collect_target, {}).get("data", [])

    # Выполняем синхронизацию
    # (создаёт NetBoxClient, NetBoxSync и вызывает нужный sync метод)
    # ...
```

Это важная фича: **Pipeline "default" не содержит collect-шагов**. Каждый sync-шаг
автоматически собирает нужные данные, если их ещё нет. Это упрощает YAML файл.

### Результаты: StepResult и PipelineResult

```python
@dataclass
class StepResult:
    """Результат одного шага."""
    step_id: str              # ID шага ("sync_interfaces")
    status: StepStatus        # COMPLETED / FAILED / SKIPPED
    data: Any = None          # Данные (created=5, updated=3, ...)
    error: Optional[str] = None   # Текст ошибки (если FAILED)
    duration_ms: int = 0      # Время выполнения в миллисекундах

@dataclass
class PipelineResult:
    """Результат всего pipeline."""
    pipeline_id: str          # ID pipeline ("default")
    status: StepStatus        # Общий статус
    steps: List[StepResult]   # Результаты каждого шага
    total_duration_ms: int    # Общее время выполнения
```

### Callbacks -- отслеживание прогресса

PipelineExecutor принимает два callback-а (функции обратного вызова):

```python
executor = PipelineExecutor(
    pipeline,
    on_step_start=lambda step: print(f"  Начинаю: {step.id}..."),
    on_step_complete=lambda step, result: print(f"  Готово: {step.id} ({result.duration_ms}ms)"),
)
```

Это позволяет CLI и Web UI показывать прогресс выполнения.
В CLI это выглядит так:

```python
# cli/commands/pipeline.py
def on_step_start(step):
    print(f"  >>> {step.id}...")

def on_step_complete(step, result):
    icon = "OK" if result.status == StepStatus.COMPLETED else "FAIL"
    print(f"  {icon} {step.id} ({result.duration_ms}ms)")
```

---

## 5. Cleanup шаги -- удаление лишнего

### Что такое cleanup

Cleanup -- это удаление из NetBox объектов, которых больше нет на устройстве.
Это включается опцией `cleanup: true` в YAML.

```yaml
- id: sync_interfaces
  type: sync
  target: interfaces
  options:
    cleanup: true        # Удалять интерфейсы из NetBox, которых нет на устройстве
```

### Пример: зачем нужен cleanup

```
Устройство switch-01           NetBox
─────────────────────           ──────
GigabitEthernet0/1              GigabitEthernet0/1      → OK, совпадает
GigabitEthernet0/2              GigabitEthernet0/2      → OK, совпадает
(нет)                           GigabitEthernet0/99     → cleanup: УДАЛИТЬ

Интерфейс GigabitEthernet0/99 есть в NetBox, но нет на устройстве.
Возможно, его переименовали или удалили. cleanup уберёт устаревшую запись.
```

### Для каких типов работает cleanup

В Pipeline cleanup поддерживается для:

| Target | Cleanup | Что удаляется |
|--------|---------|---------------|
| `interfaces` | Да | Интерфейсы, которых нет на устройстве |
| `cables` | Да | Кабели, которых нет в LLDP/CDP данных |
| `inventory` | Да | Модули/трансиверы, которых нет на устройстве |
| `ip_addresses` | Да | IP-адреса, которых нет на интерфейсах устройства |
| `devices` | Нет | Устройства не удаляются через pipeline (опасно) |

### Предупреждение

Cleanup -- мощная опция. Всегда проверяйте что будет удалено через `--dry-run`
перед реальным запуском:

```bash
# Сначала: смотрим что будет
python -m network_collector pipeline run default
# (по умолчанию dry_run=True)

# Убедились что всё правильно -- применяем
python -m network_collector pipeline run default --apply
```

---

## 6. CLI команды для Pipeline

### pipeline list -- показать все pipeline

```bash
python -m network_collector pipeline list
```

Вывод:

```
ID                   Name                      Steps   Enabled  Description
--------------------------------------------------------------------------------
default              Full Sync                 5       OK       Полная синхронизация: devic...
full-no-vlans        Full Sync (no VLANs)      5       OK       Полная синхронизация без VL...

Total: 2 pipeline(s)
```

Команда сканирует папку `pipelines/`, загружает все `.yaml` файлы и показывает таблицу.

### pipeline show -- детали pipeline

```bash
python -m network_collector pipeline show default
```

Вывод:

```
============================================================
Pipeline: Full Sync
============================================================
ID:          default
Description: Полная синхронизация: devices -> interfaces -> IP -> inventory -> cables
Enabled:     Yes
Steps:       5

Steps:
------------------------------------------------------------
  1. [OK] sync_devices
      Type: sync, Target: devices
  2. [OK] sync_interfaces
      Type: sync, Target: interfaces (depends: sync_devices)
      Options: cleanup=True
  3. [OK] sync_ip_addresses
      Type: sync, Target: ip_addresses (depends: sync_interfaces)
      Options: cleanup=True, update_existing=True
  4. [OK] sync_inventory
      Type: sync, Target: inventory (depends: sync_devices)
      Options: cleanup=True
  5. [OK] sync_cables
      Type: sync, Target: cables (depends: sync_interfaces)
      Options: cleanup=True
============================================================
```

### pipeline run -- запуск

```bash
# Dry-run (по умолчанию) -- ничего не меняет
python -m network_collector pipeline run default

# Применить изменения
python -m network_collector pipeline run default --apply
```

Вывод при запуске:

```
Running pipeline: Full Sync
Devices: 22
Dry-run: False
----------------------------------------
  >>> sync_devices...
  OK sync_devices (4521ms)
  >>> sync_interfaces...
  OK sync_interfaces (12340ms)
  >>> sync_ip_addresses...
  OK sync_ip_addresses (3210ms)
  >>> sync_inventory...
  OK sync_inventory (5430ms)
  >>> sync_cables...
  OK sync_cables (2100ms)

============================================================
Pipeline Run Result: default
============================================================
Status: OK COMPLETED
Duration: 27601ms

Steps:
------------------------------------------------------------
  OK sync_devices                       4521ms (+3, ~2)
  OK sync_interfaces                   12340ms (+12, ~8, -2)
  OK sync_ip_addresses                  3210ms (+5, ~1)
  OK sync_inventory                     5430ms (+8, ~3)
  OK sync_cables                        2100ms (+4, ~1)
============================================================
```

`+3` = создано 3, `~2` = обновлено 2, `-2` = удалено 2.

### pipeline validate -- проверка корректности

```bash
python -m network_collector pipeline validate default
```

Если всё OK:
```
OK Pipeline 'default' is valid (5 steps)
```

Если ошибки:
```
FAIL Pipeline 'default' has 1 error(s):
  - Sync 'cables' requires sync 'interfaces' first
```

### Как устроен CLI обработчик

**Файл:** `cli/commands/pipeline.py`

```python
def cmd_pipeline(args, ctx=None):
    """Обработчик команды pipeline."""
    subcommand = getattr(args, "pipeline_command", None)

    if subcommand == "list":
        _cmd_list(args)
    elif subcommand == "show":
        _cmd_show(args)
    elif subcommand == "run":
        _cmd_run(args, ctx)
    elif subcommand == "validate":
        _cmd_validate(args)
    elif subcommand == "create":
        _cmd_create(args)
    elif subcommand == "delete":
        _cmd_delete(args)
```

Pipeline CLI использует **subparsers** из argparse -- подкоманды внутри команды:

```
python -m network_collector pipeline run default --apply
                            ~~~~~~~~ ~~~ ~~~~~~~  ~~~~~~~
                            команда  подкоманда  аргументы
```

Это как команды Git: `git commit -m "..."`, `git push origin main` --
одна программа, много подкоманд.

---

## 7. Web UI интеграция

Pipeline доступен не только через CLI, но и через Web-интерфейс.

### REST API endpoints

**Файл:** `api/routes/pipelines.py`

| Метод | URL | Описание |
|-------|-----|----------|
| GET | `/api/pipelines` | Список всех pipeline |
| GET | `/api/pipelines/{id}` | Детали pipeline |
| POST | `/api/pipelines` | Создать pipeline |
| PUT | `/api/pipelines/{id}` | Обновить pipeline |
| DELETE | `/api/pipelines/{id}` | Удалить pipeline |
| POST | `/api/pipelines/{id}/run` | Запустить pipeline |
| POST | `/api/pipelines/{id}/validate` | Валидировать pipeline |

### Асинхронный запуск

В Web UI pipeline запускается **асинхронно** -- в фоновом потоке:

```python
# api/routes/pipelines.py
if body.async_mode:
    # Создаём задачу
    task = task_manager.create_task(
        task_type=f"pipeline_{pipeline_id}",
        total_steps=len(enabled_steps),
        total_items=len(devices),
    )

    # Запускаем в отдельном потоке
    thread = threading.Thread(
        target=_run_pipeline_background,
        args=(task.id, pipeline, devices, creds, netbox_config, body.dry_run),
        daemon=True,
    )
    thread.start()

    # Сразу возвращаем task_id клиенту
    return PipelineRunResponse(status="running", task_id=task.id)
```

Клиент (Vue.js frontend) получает `task_id` и периодически спрашивает
"как дела?" через отдельный endpoint. Это позволяет показывать прогресс
в реальном времени.

### Web UI страница

Страница `/pipelines` в Web UI позволяет:
- Просмотреть список pipeline
- Посмотреть шаги и их зависимости
- Запустить pipeline (dry-run или apply)
- Следить за прогрессом в реальном времени
- Посмотреть результаты в истории (`/history`)

---

## 8. Создание своего Pipeline

### Шаг 1: Создать YAML файл

Создай файл `pipelines/my-pipeline.yaml`:

```yaml
id: my-pipeline
name: My Custom Pipeline
description: Сбор интерфейсов и экспорт в Excel
enabled: true
steps:
- id: collect_interfaces
  type: collect
  target: interfaces
  enabled: true
  options: {}
  depends_on: []

- id: export_interfaces
  type: export
  target: interfaces
  enabled: true
  options:
    format: excel
    output_dir: output
  depends_on:
  - collect_interfaces
```

### Шаг 2: Проверить

```bash
python -m network_collector pipeline validate my-pipeline
```

### Шаг 3: Запустить

```bash
python -m network_collector pipeline run my-pipeline --apply
```

### Доступные targets для collect

```python
AVAILABLE_COLLECTORS = {
    "devices", "interfaces", "mac", "lldp", "cdp", "inventory", "backup"
}
```

### Доступные targets для sync

```python
AVAILABLE_SYNC_TARGETS = {
    "devices", "interfaces", "cables", "inventory", "vlans", "ip_addresses"
}
```

---

## Ключевые файлы

| Файл | Описание |
|------|----------|
| `core/pipeline/models.py` | PipelineStep, Pipeline, StepType, StepStatus -- модели данных |
| `core/pipeline/executor.py` | PipelineExecutor -- выполнение шагов, контекст, зависимости |
| `cli/commands/pipeline.py` | CLI: list, show, run, validate, create, delete |
| `api/routes/pipelines.py` | REST API: endpoints для Web UI |
| `pipelines/default.yaml` | Pipeline по умолчанию: полная синхронизация |
| `pipelines/full-no-vlans.yaml` | Pipeline без VLAN синхронизации |

---

## Итоги

| Концепция | Суть |
|-----------|------|
| Pipeline | Цепочка шагов (collect, sync, export), описанная в YAML |
| PipelineStep | Один шаг: тип, цель, опции, зависимости |
| PipelineExecutor | Выполняет шаги последовательно, проверяет зависимости |
| Контекст (`_context`) | Общий словарь для передачи данных между шагами |
| `depends_on` | Список шагов, которые должны завершиться до текущего |
| cleanup | Удаление из NetBox объектов, которых нет на устройстве |
| dry_run | Режим "посмотреть что будет" без изменений |
| Автоматический collect | Sync-шаг сам запускает collect, если данных ещё нет |
| Callbacks | Функции для отслеживания прогресса (CLI и Web UI) |

### Что читать дальше

| # | Документ | Что узнаешь |
|---|----------|-------------|
| 07 | CLI и Web API | Как работают REST API endpoints, FastAPI, связь CLI и Web UI |
| 08 | Тестирование | Как писать и запускать тесты, pytest, моки |

Также полезно:
- [MANUAL.md](../MANUAL.md) -- руководство пользователя (все команды и примеры)
- [SYNC_PIPELINE_INTERNALS.md](../SYNC_PIPELINE_INTERNALS.md) -- техническое описание pipeline и sync
