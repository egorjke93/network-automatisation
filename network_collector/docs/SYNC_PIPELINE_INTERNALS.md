# Sync и Pipeline — Подробное руководство для начинающих

Этот документ объясняет внутреннее устройство синхронизации с NetBox и системы Pipeline.
Написан максимально подробно для тех, кто только изучает Python.

---

## Содержание

1. [Введение](#введение)
2. [Общая архитектура](#общая-архитектура)
3. [Pipeline — Конвейер выполнения](#pipeline--конвейер-выполнения)
   - [Модели Pipeline](#модели-pipeline)
   - [PipelineExecutor](#pipelineexecutor)
   - [Полная цепочка вызовов Pipeline](#полная-цепочка-вызовов-pipeline)
4. [Sync — Синхронизация с NetBox](#sync--синхронизация-с-netbox)
   - [Архитектура Sync модулей](#архитектура-sync-модулей)
   - [SyncBase — Базовый класс](#syncbase--базовый-класс)
   - [Mixin классы](#mixin-классы)
   - [NetBoxSync — Главный класс](#netboxsync--главный-класс)
5. [API SyncService](#api-syncservice)
   - [Полная цепочка: от клика до результата](#полная-цепочка-от-клика-до-результата)
6. [Collectors — Сбор данных](#collectors--сбор-данных)
7. [Сравнение данных (SyncComparator)](#сравнение-данных-synccomparator)
8. [Как работает to_dict() и очистка полей](#как-работает-to_dict-и-очистка-полей)
9. [Примеры кода с объяснениями](#примеры-кода-с-объяснениями)
10. [Batch API — Оптимизация производительности](#batch-api--оптимизация-производительности)

---

## Введение

### Что делает система?

**Sync** — это процесс синхронизации данных с сетевых устройств в NetBox:
1. Собираем данные с устройств (SSH)
2. Сравниваем с тем, что уже есть в NetBox
3. Создаём/обновляем/удаляем записи в NetBox

**Pipeline** — это способ автоматизировать несколько операций в одну цепочку:
1. Сначала собрать devices
2. Потом собрать interfaces
3. Синхронизировать devices в NetBox
4. Синхронизировать interfaces в NetBox
5. Экспортировать результат в Excel

### Зачем это нужно?

Без Pipeline пришлось бы каждый раз вручную запускать команды:
```bash
python -m network_collector devices --format excel
python -m network_collector sync-netbox --create-devices
python -m network_collector sync-netbox --interfaces
```

С Pipeline — один клик:
```bash
python -m network_collector pipeline run full-sync
```

---

## Общая архитектура

```
┌─────────────────────────────────────────────────────────────────┐
│                         Frontend (Vue.js)                        │
│  [Sync.vue] → axios.post('/api/sync') → отображает результат    │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                       API (FastAPI)                              │
│  api/routes/sync.py → SyncService → NetBoxSync                  │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Sync Layer (netbox/sync/)                   │
│                                                                  │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐        │
│  │  NetBoxSync  │ ← │   Mixins     │ ← │  SyncBase    │        │
│  │  (главный)   │   │ (интерфейсы, │   │ (базовый)    │        │
│  │              │   │  кабели...)  │   │              │        │
│  └──────────────┘   └──────────────┘   └──────────────┘        │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    NetBox Client (netbox/client/)                │
│  Обёртка над pynetbox для работы с NetBox API                   │
│  Поштучные + bulk методы (batch create/update/delete)           │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                         NetBox Server                            │
│  REST API: GET/POST/PATCH/DELETE                                │
└─────────────────────────────────────────────────────────────────┘
```

---

## Pipeline — Конвейер выполнения

### Что такое Pipeline?

Pipeline — это **последовательность шагов**, которые выполняются один за другим.
Каждый шаг может быть:
- **collect** — сбор данных с устройств
- **sync** — синхронизация с NetBox
- **export** — экспорт в файл (Excel, CSV, JSON)

### Модели Pipeline

**Файл:** `core/pipeline/models.py`

#### StepType — Тип шага

```python
class StepType(str, Enum):
    """Тип шага pipeline."""
    COLLECT = "collect"      # Сбор данных с устройств
    SYNC = "sync"            # Синхронизация с NetBox
    EXPORT = "export"        # Экспорт в файл
```

**Что это?**
- `Enum` — это перечисление, набор констант
- `str, Enum` — значит каждая константа одновременно строка и Enum
- Это ограничивает возможные типы шагов только тремя вариантами

#### StepStatus — Статус выполнения

```python
class StepStatus(str, Enum):
    """Статус выполнения шага."""
    PENDING = "pending"       # Ожидает выполнения
    RUNNING = "running"       # Выполняется
    COMPLETED = "completed"   # Завершён успешно
    FAILED = "failed"         # Ошибка
    SKIPPED = "skipped"       # Пропущен (зависимости не выполнены)
```

#### PipelineStep — Один шаг

```python
@dataclass
class PipelineStep:
    """
    Один шаг pipeline.

    @dataclass — это декоратор Python, который автоматически
    создаёт __init__, __repr__ и другие методы.
    Вместо:
        def __init__(self, id, type, target, ...):
            self.id = id
            self.type = type
            ...
    Достаточно просто указать поля.
    """
    id: str                    # Уникальный ID шага, например "collect_devices"
    type: StepType             # Тип: collect, sync или export
    target: str                # Цель: devices, interfaces, cables, etc.
    enabled: bool = True       # Включён ли шаг (можно временно отключить)
    options: Dict = field(default_factory=dict)  # Дополнительные опции
    depends_on: List[str] = field(default_factory=list)  # Зависимости

    # Runtime поля (заполняются во время выполнения)
    status: StepStatus = StepStatus.PENDING
    result: Optional[Dict] = None
    error: Optional[str] = None
```

**Пример шага:**
```python
step = PipelineStep(
    id="collect_interfaces",
    type=StepType.COLLECT,
    target="interfaces",
    depends_on=["collect_devices"],  # Сначала нужно собрать devices
)
```

#### Pipeline — Набор шагов

```python
@dataclass
class Pipeline:
    """
    Pipeline — это контейнер для шагов.
    """
    id: str                           # Уникальный ID, например "full-sync"
    name: str                         # Человекочитаемое имя
    description: str = ""             # Описание
    steps: List[PipelineStep] = field(default_factory=list)
    enabled: bool = True

    # Runtime
    status: StepStatus = StepStatus.PENDING
    current_step: Optional[str] = None  # ID текущего шага
```

**Пример Pipeline в YAML:**
```yaml
id: full-sync
name: Полная синхронизация
description: Собирает все данные и синхронизирует с NetBox
steps:
  - id: collect_devices
    type: collect
    target: devices

  - id: collect_interfaces
    type: collect
    target: interfaces
    depends_on: [collect_devices]

  - id: sync_devices
    type: sync
    target: devices
    depends_on: [collect_devices]
    options:
      site: Office
      role: switch

  - id: sync_interfaces
    type: sync
    target: interfaces
    depends_on: [sync_devices, collect_interfaces]
```

### PipelineExecutor

**Файл:** `core/pipeline/executor.py`

Executor — это класс, который **выполняет** Pipeline.

```python
class PipelineExecutor:
    """
    Выполняет pipeline.

    Attributes:
        pipeline: Pipeline для выполнения
        dry_run: Режим симуляции (не применять изменения)
        on_step_start: Callback при начале шага
        on_step_complete: Callback при завершении шага
        _context: Внутренний контекст (данные между шагами)
    """

    def __init__(
        self,
        pipeline: Pipeline,
        dry_run: bool = False,
        on_step_start: Optional[Callable] = None,
        on_step_complete: Optional[Callable] = None,
    ):
        self.pipeline = pipeline
        self.dry_run = dry_run
        self.on_step_start = on_step_start
        self.on_step_complete = on_step_complete
        self._context: Dict[str, Any] = {}
```

#### Метод run() — Главная точка входа

```python
def run(
    self,
    devices: List[Any],           # Список устройств для работы
    credentials: Optional[Dict],   # SSH учётные данные
    netbox_config: Optional[Dict], # URL и токен NetBox
) -> PipelineResult:
    """
    Выполняет pipeline.

    Возвращает PipelineResult с информацией о каждом шаге.
    """
    import time
    start_time = time.time()

    # 1. ВАЛИДАЦИЯ
    # Проверяем что pipeline корректен
    errors = self.pipeline.validate()
    if errors:
        # Если есть ошибки — возвращаем сразу
        return PipelineResult(
            pipeline_id=self.pipeline.id,
            status=StepStatus.FAILED,
            steps=[StepResult(
                step_id="validation",
                status=StepStatus.FAILED,
                error="; ".join(errors),
            )],
        )

    # 2. ИНИЦИАЛИЗАЦИЯ КОНТЕКСТА
    # Контекст — это словарь, который передаётся между шагами
    self._context = {
        "devices": devices,
        "credentials": credentials or {},
        "netbox_config": netbox_config or {},
        "dry_run": self.dry_run,
        "collected_data": {},  # Сюда складываются данные от collect шагов
    }

    self.pipeline.status = StepStatus.RUNNING
    results: List[StepResult] = []

    # 3. ВЫПОЛНЕНИЕ ШАГОВ
    # Перебираем только включённые шаги
    for step in self.pipeline.get_enabled_steps():
        self.pipeline.current_step = step.id

        # 3.1 Проверяем зависимости
        deps_ok = self._check_dependencies(step, results)
        if not deps_ok:
            # Зависимости не выполнены — пропускаем шаг
            step_result = StepResult(
                step_id=step.id,
                status=StepStatus.SKIPPED,
                error="Dependencies not met",
            )
            results.append(step_result)
            continue

        # 3.2 Callback начала (для UI прогресс-бара)
        if self.on_step_start:
            self.on_step_start(step)

        # 3.3 Выполняем шаг
        step.status = StepStatus.RUNNING
        step_result = self._execute_step(step)
        step.status = step_result.status
        step.error = step_result.error
        results.append(step_result)

        # 3.4 Callback завершения
        if self.on_step_complete:
            self.on_step_complete(step, step_result)

        # 3.5 Если шаг failed — прерываем pipeline
        if step_result.status == StepStatus.FAILED:
            self.pipeline.status = StepStatus.FAILED
            break

    # 4. ОПРЕДЕЛЯЕМ ИТОГОВЫЙ СТАТУС
    if self.pipeline.status != StepStatus.FAILED:
        if all(r.status == StepStatus.COMPLETED for r in results):
            self.pipeline.status = StepStatus.COMPLETED
        elif any(r.status == StepStatus.FAILED for r in results):
            self.pipeline.status = StepStatus.FAILED
        else:
            self.pipeline.status = StepStatus.COMPLETED

    total_time = int((time.time() - start_time) * 1000)

    return PipelineResult(
        pipeline_id=self.pipeline.id,
        status=self.pipeline.status,
        steps=results,
        total_duration_ms=total_time,
    )
```

#### Метод _execute_step() — Выполнение одного шага

```python
def _execute_step(self, step: PipelineStep) -> StepResult:
    """
    Выполняет один шаг.

    Определяет тип шага и вызывает соответствующий метод.
    """
    import time
    start_time = time.time()

    try:
        # Выбираем метод по типу шага
        if step.type == StepType.COLLECT:
            data = self._execute_collect(step)
        elif step.type == StepType.SYNC:
            data = self._execute_sync(step)
        elif step.type == StepType.EXPORT:
            data = self._execute_export(step)
        else:
            raise ValueError(f"Unknown step type: {step.type}")

        duration = int((time.time() - start_time) * 1000)

        return StepResult(
            step_id=step.id,
            status=StepStatus.COMPLETED,
            data=data,
            duration_ms=duration,
        )

    except Exception as e:
        # Ловим любую ошибку и возвращаем FAILED
        duration = int((time.time() - start_time) * 1000)
        logger.error(f"Step {step.id} failed: {e}")

        return StepResult(
            step_id=step.id,
            status=StepStatus.FAILED,
            error=str(e),
            duration_ms=duration,
        )
```

#### Метод _execute_collect() — Сбор данных

```python
def _execute_collect(self, step: PipelineStep) -> Dict[str, Any]:
    """
    Выполняет collect шаг — сбор данных с устройств.
    """
    from ...core.credentials import Credentials

    target = step.target  # Например: "devices", "interfaces"
    devices = self._context["devices"]
    creds_dict = self._context["credentials"]

    # 1. Конвертируем credentials из dict в объект Credentials
    # Зачем? Collectors ожидают объект Credentials, а не словарь
    credentials = None
    if creds_dict and creds_dict.get("username"):
        credentials = Credentials(
            username=creds_dict.get("username", ""),
            password=creds_dict.get("password", ""),
        )

    logger.info(f"Collecting {target} from {len(devices)} devices...")

    # 2. Проверяем что есть устройства
    if not devices:
        logger.warning(f"No devices to collect {target} from")
        collected = {"target": target, "data": [], "count": 0}
        self._context["collected_data"][target] = collected
        return collected

    # 3. Импортируем collectors
    # Почему внутри функции? Чтобы избежать circular imports
    from ...collectors import (
        DeviceCollector,
        MACCollector,
        LLDPCollector,
        InterfaceCollector,
        InventoryCollector,
        ConfigBackupCollector,
    )

    # 4. Маппинг target -> класс collector
    COLLECTOR_MAPPING = {
        "devices": DeviceCollector,
        "mac": MACCollector,
        "lldp": LLDPCollector,
        "interfaces": InterfaceCollector,
        "inventory": InventoryCollector,
        "backup": ConfigBackupCollector,
    }

    collector_class = COLLECTOR_MAPPING.get(target)
    if not collector_class:
        raise ValueError(f"Unknown collector target: {target}")

    # 5. Создаём collector и собираем данные
    options = step.options.copy()
    options["credentials"] = credentials

    collector = collector_class(**options)

    # collect_dicts() возвращает список словарей
    # Это унифицированный метод для всех collectors
    data = collector.collect_dicts(devices)

    logger.info(f"Collected {len(data)} {target} entries")

    # 6. Сохраняем в контекст для последующих шагов
    # Это важно! Sync шаг возьмёт данные отсюда
    collected = {"target": target, "data": data, "count": len(data)}
    self._context["collected_data"][target] = collected

    return collected
```

#### Метод _execute_sync() — Синхронизация

```python
def _execute_sync(self, step: PipelineStep) -> Dict[str, Any]:
    """
    Выполняет sync шаг — синхронизацию с NetBox.

    Автоматически делает collect если данных нет!
    """
    target = step.target  # Например: "devices", "interfaces", "cables"
    options = step.options
    dry_run = self._context["dry_run"]
    netbox_config = self._context.get("netbox_config", {})

    logger.info(f"Syncing {target} to NetBox (dry_run={dry_run})...")

    # 1. Проверяем NetBox config
    netbox_url = netbox_config.get("url")
    netbox_token = netbox_config.get("token")

    if not netbox_url or not netbox_token:
        raise ValueError("NetBox URL and token are required for sync")

    # 2. Маппинг: какой collect нужен для какого sync
    # Например: cables sync требует lldp collect
    SYNC_COLLECT_MAPPING = {
        "cables": ["lldp", "cdp"],
        "ip_addresses": ["interfaces"],
    }

    required_collects = SYNC_COLLECT_MAPPING.get(target, [target])

    # 3. Получаем данные из контекста
    data = []
    for collect_target in required_collects:
        collected = self._context["collected_data"].get(collect_target, {})
        data = collected.get("data", [])
        if data:
            break

    # 4. Если данных нет — автоматически запускаем collect
    if not data:
        collect_target = required_collects[0]
        logger.info(f"No {collect_target} data found, auto-collecting...")

        # Создаём временный collect шаг
        auto_collect_step = PipelineStep(
            id=f"auto_collect_{collect_target}",
            type=StepType.COLLECT,
            target=collect_target,
        )

        self._execute_collect(auto_collect_step)

        # Теперь данные должны быть в контексте
        collected = self._context["collected_data"].get(collect_target, {})
        data = collected.get("data", [])

    if not data:
        logger.warning(f"No {target} data to sync after collect")
        return {"target": target, "dry_run": dry_run, "skipped": True}

    # 5. Создаём NetBox клиент и sync
    from ...netbox.client import NetBoxClient
    from ...netbox.sync import NetBoxSync

    client = NetBoxClient(url=netbox_url, token=netbox_token)
    sync = NetBoxSync(client, dry_run=dry_run)

    # 6. Выполняем sync по типу target
    result = {}

    if target == "devices":
        result = sync.sync_devices_from_inventory(
            data,
            site=options.get("site"),
            role=options.get("role"),
        )

    elif target == "interfaces":
        # Группируем по устройству
        by_device = {}
        for intf in data:
            hostname = intf.get("hostname", "")
            if hostname not in by_device:
                by_device[hostname] = []
            by_device[hostname].append(intf)

        total_created = 0
        total_updated = 0

        for hostname, interfaces in by_device.items():
            sync_result = sync.sync_interfaces(hostname, interfaces)
            total_created += sync_result.get("created", 0)
            total_updated += sync_result.get("updated", 0)

        result = {"created": total_created, "updated": total_updated}

    elif target == "cables":
        lldp_data = self._context["collected_data"].get("lldp", {}).get("data", [])
        result = sync.sync_cables_from_lldp(lldp_data)

    result["target"] = target
    result["dry_run"] = dry_run

    return result
```

### Полная цепочка вызовов Pipeline

```
1. Пользователь запускает pipeline:
   python -m network_collector pipeline run full-sync

2. CLI парсит команду и вызывает:
   pipeline_run_command(pipeline_id="full-sync", devices, credentials)

3. Загружается Pipeline из YAML:
   pipeline = Pipeline.from_yaml("pipelines/full-sync.yaml")

4. Создаётся Executor:
   executor = PipelineExecutor(pipeline, dry_run=False)

5. Запускается выполнение:
   result = executor.run(devices, credentials, netbox_config)

6. Внутри run() для каждого шага:
   ┌─────────────────────────────────────────┐
   │ Step: collect_devices                   │
   │                                         │
   │ 1. Проверка зависимостей: OK           │
   │ 2. _execute_step(step)                 │
   │    └─ _execute_collect(step)           │
   │       └─ DeviceCollector.collect_dicts │
   │ 3. Сохранение в контекст               │
   │ 4. status = COMPLETED                  │
   └─────────────────────────────────────────┘

   ┌─────────────────────────────────────────┐
   │ Step: sync_devices                      │
   │                                         │
   │ 1. Проверка зависимостей: OK           │
   │ 2. _execute_step(step)                 │
   │    └─ _execute_sync(step)              │
   │       └─ NetBoxSync.sync_devices_...   │
   │ 3. Возврат результата                  │
   │ 4. status = COMPLETED                  │
   └─────────────────────────────────────────┘

7. Возвращается PipelineResult:
   {
     "pipeline_id": "full-sync",
     "status": "completed",
     "steps": [
       {"step_id": "collect_devices", "status": "completed", ...},
       {"step_id": "sync_devices", "status": "completed", ...}
     ],
     "total_duration_ms": 12345
   }
```

---

## Sync — Синхронизация с NetBox

### Архитектура Sync модулей

```
netbox/sync/
├── __init__.py      # Экспорт NetBoxSync
├── base.py          # SyncBase — базовый класс с общими методами
├── main.py          # NetBoxSync — главный класс (собирает всё вместе)
├── devices.py       # DevicesSyncMixin — синхронизация устройств
├── interfaces.py    # InterfacesSyncMixin — синхронизация интерфейсов
├── cables.py        # CablesSyncMixin — синхронизация кабелей
├── ip_addresses.py  # IPAddressesSyncMixin — синхронизация IP
├── vlans.py         # VLANsSyncMixin — синхронизация VLAN
└── inventory.py     # InventorySyncMixin — синхронизация inventory
```

**Почему такая структура?**

Без разделения на файлы весь код был бы в одном огромном файле (1000+ строк).
С Mixin-ами:
- Каждый файл отвечает за один тип синхронизации
- Легко находить нужный код
- Можно тестировать независимо

### SyncBase — Базовый класс

**Файл:** `netbox/sync/base.py`

```python
class SyncBase:
    """
    Базовый класс для синхронизации с NetBox.

    Содержит общие атрибуты и вспомогательные методы,
    которые используются во всех sync-операциях.
    """

    def __init__(
        self,
        client: NetBoxClient,    # NetBox API клиент
        dry_run: bool = False,   # Режим симуляции
        create_only: bool = False,  # Только создавать
        update_only: bool = False,  # Только обновлять
        context: Optional[RunContext] = None,  # Контекст выполнения
    ):
        """
        Инициализация синхронизатора.

        dry_run=True — ничего не меняем в NetBox, только логируем
        create_only=True — создаём новое, но не обновляем существующее
        update_only=True — обновляем существующее, но не создаём новое
        """
        self.client = client
        self.ctx = context or get_current_context()
        self.dry_run = dry_run
        self.create_only = create_only
        self.update_only = update_only

        # Кэш для поиска устройств
        # Зачем? Чтобы не делать запрос в NetBox каждый раз
        self._device_cache: Dict[str, Any] = {}
        self._mac_cache: Dict[str, Any] = {}
```

#### Методы поиска и кэширования

```python
def _find_device(self, name: str) -> Optional[Any]:
    """
    Находит устройство в NetBox (с кэшированием).

    Кэширование важно! Без него:
    - 100 интерфейсов = 100 запросов к NetBox для поиска устройства

    С кэшированием:
    - 100 интерфейсов = 1 запрос (остальные из кэша)
    """
    # Проверяем кэш
    if name in self._device_cache:
        return self._device_cache[name]

    # Запрос к NetBox
    device = self.client.get_device_by_name(name)

    # Сохраняем в кэш
    if device:
        self._device_cache[name] = device

    return device

def _find_interface(self, device_id: int, interface_name: str) -> Optional[Any]:
    """
    Находит интерфейс устройства.

    Сначала ищет точное совпадение, потом нормализованное.
    Например: "Gi0/1" и "GigabitEthernet0/1" — это одно и то же.
    """
    interfaces = self.client.get_interfaces(device_id=device_id)

    # Точное совпадение
    for intf in interfaces:
        if intf.name == interface_name:
            return intf

    # Нормализованное имя
    normalized = self._normalize_interface_name(interface_name)
    for intf in interfaces:
        if self._normalize_interface_name(intf.name) == normalized:
            return intf

    return None
```

#### Методы get-or-create

```python
def _get_or_create(
    self,
    endpoint,              # NetBox API endpoint (например, api.dcim.manufacturers)
    name: str,             # Имя для поиска/создания
    extra_data: Optional[Dict] = None,  # Дополнительные поля
    get_field: str = "name",  # Поле для поиска
) -> Optional[Any]:
    """
    Generic get-or-create для NetBox объектов.

    Логика:
    1. Ищем объект по name
    2. Если нашли — возвращаем
    3. Если не нашли — создаём

    Это паттерн "Получить или создать", очень часто используется.
    """
    try:
        # Пробуем найти
        obj = endpoint.get(**{get_field: name})
        if obj:
            return obj

        # Не нашли — создаём
        # slug — это URL-friendly версия имени: "Cisco Systems" → "cisco-systems"
        slug = slugify(name)
        create_data = {get_field: name, "slug": slug}
        if extra_data:
            create_data.update(extra_data)

        return endpoint.create(create_data)

    except Exception as e:
        logger.error(f"Ошибка NetBox ({get_field}={name}): {e}")
        return None

# Конкретные реализации для разных типов объектов
def _get_or_create_manufacturer(self, name: str):
    """Получает или создаёт производителя."""
    return self._get_or_create(self.client.api.dcim.manufacturers, name)

def _get_or_create_device_type(self, model: str, manufacturer_id: int):
    """Получает или создаёт тип устройства."""
    return self._get_or_create(
        self.client.api.dcim.device_types,
        model,
        extra_data={"manufacturer": manufacturer_id},
        get_field="model",
    )

def _get_or_create_site(self, name: str):
    """Получает или создаёт сайт."""
    return self._get_or_create(
        self.client.api.dcim.sites,
        name,
        extra_data={"status": "active"},
    )
```

### Mixin классы

**Что такое Mixin?**

Mixin — это класс, который добавляет функциональность другому классу через множественное наследование.

```python
# Без Mixin — всё в одном классе
class NetBoxSync:
    def sync_devices(self): ...
    def sync_interfaces(self): ...
    def sync_cables(self): ...
    # 1000+ строк кода...

# С Mixin — разделено по файлам
class DevicesSyncMixin:
    def sync_devices(self): ...

class InterfacesSyncMixin:
    def sync_interfaces(self): ...

class CablesSyncMixin:
    def sync_cables(self): ...

# Главный класс наследует все Mixin
class NetBoxSync(
    DevicesSyncMixin,
    InterfacesSyncMixin,
    CablesSyncMixin,
    SyncBase,  # Базовый класс в конце!
):
    pass
```

#### InterfacesSyncMixin — Синхронизация интерфейсов

**Файл:** `netbox/sync/interfaces.py`

> **Оптимизация (Февраль 2026):** Метод `sync_interfaces` использует **Batch API** —
> все создания, обновления и удаления интерфейсов выполняются пакетно (один API-вызов
> на каждую операцию), а не поштучно. Это даёт ускорение в **3-5x** для фазы sync.
> Подробнее: [Batch API — Оптимизация производительности](#batch-api--оптимизация-производительности).

```python
class InterfacesSyncMixin:
    """Mixin для синхронизации интерфейсов."""

    def sync_interfaces(
        self: SyncBase,           # Type hint для IDE
        device_name: str,         # Имя устройства в NetBox
        interfaces: List[Interface],  # Список интерфейсов с устройства
        create_missing: Optional[bool] = None,  # Создавать отсутствующие
        update_existing: Optional[bool] = None, # Обновлять существующие
        cleanup: bool = False,    # Удалять лишние
    ) -> Dict[str, Any]:
        """
        Синхронизирует интерфейсы устройства.

        Использует batch API для create/update/delete (один вызов на операцию).
        При ошибке batch — fallback на поштучные операции.

        Возвращает статистику: {created, updated, deleted, skipped, details}
        """
        # 1. ИНИЦИАЛИЗАЦИЯ
        stats = {"created": 0, "updated": 0, "deleted": 0, "skipped": 0}
        details = {"create": [], "update": [], "delete": [], "skip": []}

        # Получаем настройки из fields.yaml
        sync_cfg = get_sync_config("interfaces")

        # Если не указано явно — берём из config
        if create_missing is None:
            create_missing = sync_cfg.get_option("create_missing", True)
        if update_existing is None:
            update_existing = sync_cfg.get_option("update_existing", True)

        # 2. НАХОДИМ УСТРОЙСТВО В NETBOX
        device = self.client.get_device_by_name(device_name)
        if not device:
            # Fallback: поиск по IP если device_name похоже на IP
            ...
            logger.error(f"Устройство не найдено в NetBox: {device_name}")
            stats["failed"] = 1
            return stats

        # 3. ПОЛУЧАЕМ СУЩЕСТВУЮЩИЕ ИНТЕРФЕЙСЫ
        existing = list(self.client.get_interfaces(device_id=device.id))

        # 4. СРАВНИВАЕМ через SyncComparator (domain layer)
        comparator = SyncComparator()
        local_data = [intf.to_dict() for intf in interfaces if intf.name]
        diff = comparator.compare_interfaces(local, remote, ...)

        # 5. ПРИМЕНЯЕМ ИЗМЕНЕНИЯ (Batch API)
        #    Каждая операция — один вызов к NetBox API

        # 5.1 Batch create
        self._batch_create_interfaces(device.id, diff.to_create, interfaces, stats, details)

        # 5.2 Batch update
        self._batch_update_interfaces(diff.to_update, interfaces, stats, details)

        # 5.3 Batch delete
        self._batch_delete_interfaces(diff.to_delete, stats, details)

        stats["skipped"] += len(diff.to_skip)
        stats["details"] = details
        return stats
```

**Ключевое отличие от старого подхода:**

| Операция | Раньше (поштучно) | Сейчас (Batch API) |
|----------|-------------------|---------------------|
| Создание 10 интерфейсов | 10 POST запросов | 1 POST запрос |
| Обновление 48 интерфейсов | 48 PATCH запросов | 1 PATCH запрос |
| Удаление 5 интерфейсов | 5 DELETE запросов | 1 DELETE запрос |
| **Итого на устройство (~48 портов)** | **~100 запросов** | **~3 запроса** |

#### Архитектура Batch операций

Batch API разделяет подготовку данных и отправку в NetBox:

```
┌──────────────────────────────────────────────────────────────────────┐
│  sync_interfaces()                                                    │
│                                                                       │
│  1. SyncComparator.compare() → diff (to_create, to_update, to_delete)│
│                                                                       │
│  2. _batch_create_interfaces()                                        │
│     ├── for each item: _build_create_data() → (dict, mac)            │
│     ├── collect all dicts into create_batch[]                         │
│     ├── ONE call: client.bulk_create_interfaces(create_batch)         │
│     ├── post-create: assign_mac_to_interface() (по одному)            │
│     └── fallback: _create_interface() поштучно при ошибке             │
│                                                                       │
│  3. _batch_update_interfaces()                                        │
│     ├── for each item: _build_update_data() → (updates, changes, mac)│
│     ├── collect all updates into update_batch[]                       │
│     ├── ONE call: client.bulk_update_interfaces(update_batch)         │
│     ├── post-update: assign_mac_to_interface() (по одному)            │
│     └── fallback: _update_interface() поштучно при ошибке             │
│                                                                       │
│  4. _batch_delete_interfaces()                                        │
│     ├── collect all IDs into delete_ids[]                             │
│     ├── ONE call: client.bulk_delete_interfaces(delete_ids)           │
│     └── fallback: _delete_interface() поштучно при ошибке             │
└──────────────────────────────────────────────────────────────────────┘
```

#### _build_create_data() — Подготовка данных для создания

Выделен из `_create_interface()`. Чистая функция — **без API-вызовов** (кроме LAG lookup):

```python
def _build_create_data(
    self: SyncBase,
    device_id: int,
    intf: Interface,
) -> Tuple[Optional[Dict], Optional[str]]:
    """
    Подготавливает данные для создания интерфейса (без API-вызовов).

    Returns:
        Tuple: (data_dict для API, mac_to_assign или None)
    """
    sync_cfg = get_sync_config("interfaces")

    data = {
        "device": device_id,
        "name": intf.name,
        "type": get_netbox_interface_type(interface=intf),
    }

    # Добавляем поля согласно fields.yaml
    if sync_cfg.is_field_enabled("description"):
        data["description"] = intf.description
    if sync_cfg.is_field_enabled("enabled"):
        data["enabled"] = intf.status not in ("disabled", "error")
    if sync_cfg.is_field_enabled("mtu") and intf.mtu:
        data["mtu"] = intf.mtu
    if sync_cfg.is_field_enabled("speed") and intf.speed:
        data["speed"] = self._parse_speed(intf.speed)
    if sync_cfg.is_field_enabled("duplex") and intf.duplex:
        data["duplex"] = self._parse_duplex(intf.duplex)
    if sync_cfg.is_field_enabled("mode") and intf.mode:
        data["mode"] = intf.mode

    # MAC назначается через отдельный endpoint (не в bulk)
    mac_to_assign = None
    if sync_cfg.is_field_enabled("mac_address") and intf.mac:
        mac_to_assign = normalize_mac_netbox(intf.mac)

    return data, mac_to_assign
```

#### _build_update_data() — Подготовка данных для обновления

Выделен из `_update_interface()`. Сравнивает поля **без API-вызовов**:

```python
def _build_update_data(
    self: SyncBase,
    nb_interface,      # Существующий интерфейс в NetBox
    intf: Interface,   # Новые данные с устройства
) -> Tuple[Dict, List[str], Optional[str]]:
    """
    Подготавливает данные для обновления (без API-вызовов, кроме MAC check).

    Returns:
        Tuple: (updates_dict, actual_changes_list, mac_to_assign или None)
    """
    updates = {}
    actual_changes = []
    sync_cfg = get_sync_config("interfaces")

    # Проверяем каждое поле на изменения
    if sync_cfg.is_field_enabled("description"):
        if intf.description != nb_interface.description:
            updates["description"] = intf.description
            actual_changes.append(f"description: {nb_interface.description!r} → {intf.description!r}")

    if sync_cfg.is_field_enabled("enabled"):
        enabled = intf.status not in ("disabled", "error")
        if enabled != nb_interface.enabled:
            updates["enabled"] = enabled
            actual_changes.append(f"enabled: {nb_interface.enabled} → {enabled}")

    # ... аналогично для mtu, speed, duplex, mode, vlans, lag

    mac_to_assign = None
    if sync_cfg.is_field_enabled("mac_address") and intf.mac:
        new_mac = normalize_mac_netbox(intf.mac)
        current_mac = self.client.get_interface_mac(nb_interface.id)
        if new_mac.upper() != (current_mac or "").upper():
            mac_to_assign = new_mac
            actual_changes.append(f"mac: {current_mac} → {new_mac}")

    return updates, actual_changes, mac_to_assign
```

**Почему MAC назначается отдельно?**

NetBox не позволяет назначить MAC-адрес в bulk create/update запросе.
MAC назначается через отдельный endpoint `assign_mac_to_interface()`.
Поэтому после batch create/update мы проходим по очереди MAC:

```python
# Post-create: назначаем MAC (отдельный endpoint, по одному)
for idx, mac in create_mac_queue:
    if idx < len(created):
        self.client.assign_mac_to_interface(created[idx].id, mac)
```

#### Fallback — страховка от ошибок

Если batch-вызов падает (например, один из 48 интерфейсов имеет невалидные данные),
система переключается на поштучные операции. Так мы не теряем все 47 корректных интерфейсов:

```python
try:
    # Пробуем batch (один запрос на все 48 интерфейсов)
    created = self.client.bulk_create_interfaces(create_batch)
    for name in create_names:
        stats["created"] += 1
except Exception as e:
    # Batch упал — fallback на поштучное создание
    logger.warning(f"Batch create не удался ({e}), fallback на поштучное создание")
    for data in create_batch:
        try:
            self._create_interface(device_id, intf)
            stats["created"] += 1
        except Exception as exc:
            logger.error(f"Ошибка создания интерфейса {name}: {exc}")
```

#### Legacy-методы _create_interface и _update_interface

Старые методы `_create_interface()` и `_update_interface()` **сохранены** как fallback.
Они используются только если batch-вызов упал с ошибкой.

```python
def _create_interface(self: SyncBase, device_id: int, intf: Interface) -> None:
    """Создаёт интерфейс в NetBox (поштучно, для fallback)."""
    # Та же логика что раньше — один запрос на один интерфейс
    interface = self.client.create_interface(device_id=device_id, name=intf.name, ...)
    if mac_to_assign and interface:
        self.client.assign_mac_to_interface(interface.id, mac_to_assign)

def _update_interface(self: SyncBase, nb_interface, intf: Interface) -> tuple:
    """Обновляет интерфейс в NetBox (поштучно, для fallback)."""
    updates, actual_changes, mac_to_assign = self._build_update_data(nb_interface, intf)
    if updates:
        self.client.update_interface(nb_interface.id, **updates)
    if mac_to_assign:
        self.client.assign_mac_to_interface(nb_interface.id, mac_to_assign)
    return True, actual_changes
```

### NetBoxSync — Главный класс

**Файл:** `netbox/sync/main.py`

```python
class NetBoxSync(
    InterfacesSyncMixin,    # sync_interfaces
    CablesSyncMixin,        # sync_cables_from_lldp
    IPAddressesSyncMixin,   # sync_ip_addresses
    DevicesSyncMixin,       # create_device, sync_devices_from_inventory
    VLANsSyncMixin,         # sync_vlans_from_interfaces
    InventorySyncMixin,     # sync_inventory
    SyncBase,               # Базовый класс (должен быть последним!)
):
    """
    Синхронизация данных с NetBox.

    ВАЖНО: Мы ТОЛЬКО ЧИТАЕМ с устройств и ЗАПИСЫВАЕМ в NetBox!
    Никаких изменений на сетевых устройствах.

    Пример использования:
        # Проверить что будет изменено (dry-run)
        sync = NetBoxSync(client, dry_run=True)
        sync.sync_interfaces("switch-01", interfaces)

        # Реальная синхронизация
        sync = NetBoxSync(client, dry_run=False)
        sync.sync_cables_from_lldp(lldp_data)

    Доступные методы:
        - sync_interfaces(device_name, interfaces, ...)
        - sync_cables_from_lldp(lldp_data, ...)
        - sync_ip_addresses(device_name, ip_data, ...)
        - create_device(name, device_type, ...)
        - sync_devices_from_inventory(inventory_data, ...)
        - sync_vlans_from_interfaces(device_name, interfaces, ...)
        - sync_inventory(device_name, inventory_data)
    """

    def __init__(
        self,
        client: NetBoxClient,
        dry_run: bool = False,
        create_only: bool = False,
        update_only: bool = False,
        context: Optional[RunContext] = None,
    ):
        # Вызываем конструктор базового класса
        # super() автоматически вызывает __init__ всех родителей
        super().__init__(
            client=client,
            dry_run=dry_run,
            create_only=create_only,
            update_only=update_only,
            context=context,
        )
```

**Порядок наследования важен!**

```python
# Правильно: SyncBase в конце
class NetBoxSync(
    InterfacesSyncMixin,
    CablesSyncMixin,
    SyncBase,  # ← Базовый класс в конце
):
    pass

# Python ищет методы слева направо:
# 1. InterfacesSyncMixin.sync_interfaces
# 2. CablesSyncMixin.sync_cables_from_lldp
# 3. SyncBase._find_device, _get_or_create, etc.
```

---

## API SyncService

**Файл:** `api/services/sync_service.py`

SyncService — это обёртка для использования Sync из Web API.

```python
class SyncService:
    """Сервис синхронизации с NetBox."""

    def __init__(self, credentials: Credentials, netbox: NetBoxConfig):
        # Конвертируем API схемы в core объекты
        from network_collector.core.credentials import Credentials as CoreCredentials
        self.credentials = CoreCredentials(
            username=credentials.username,
            password=credentials.password,
            secret=credentials.secret,
        )
        self.netbox_url = netbox.url
        self.netbox_token = netbox.token

        # ThreadPoolExecutor для параллельного выполнения
        self._max_workers = config.connection.max_workers or 5
        self._executor = ThreadPoolExecutor(max_workers=self._max_workers)
```

### Полная цепочка: от клика до результата

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. ФРОНТЕНД: Sync.vue                                           │
│                                                                 │
│    <button @click="startSync">Синхронизировать</button>        │
│                                                                 │
│    async startSync() {                                          │
│      const response = await axios.post('/api/sync', {          │
│        sync_all: true,                                          │
│        dry_run: false,                                          │
│        async_mode: true,  // ← Асинхронный режим               │
│      });                                                        │
│      this.taskId = response.data.task_id;                      │
│      this.pollStatus();  // Начинаем опрашивать статус         │
│    }                                                            │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. РОУТЕР: api/routes/sync.py                                   │
│                                                                 │
│    @router.post("/sync")                                        │
│    async def sync_to_netbox(                                    │
│        request: SyncRequest,                                    │
│        credentials: Credentials = Depends(get_credentials),    │
│        netbox: NetBoxConfig = Depends(get_netbox_config),      │
│    ):                                                           │
│        service = SyncService(credentials, netbox)              │
│        return await service.sync(request)                      │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. СЕРВИС: api/services/sync_service.py                         │
│                                                                 │
│    async def sync(self, request: SyncRequest) -> SyncResponse: │
│        devices = self._get_devices(request.devices)            │
│        steps = self._calculate_steps(request)                  │
│                                                                 │
│        # Создаём задачу для отслеживания                       │
│        task = task_manager.create_task(                        │
│            task_type="sync_netbox",                            │
│            total_steps=len(steps),                             │
│        )                                                        │
│                                                                 │
│        if request.async_mode:                                  │
│            # Запускаем в фоновом потоке                        │
│            thread = threading.Thread(                          │
│                target=self._run_sync_background,               │
│                args=(task.id, request, devices),               │
│            )                                                    │
│            thread.start()                                       │
│            return SyncResponse(task_id=task.id)  # Сразу       │
│        else:                                                    │
│            # Ждём результат                                     │
│            result = await self._run_in_executor(...)           │
│            return SyncResponse(...)                             │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. ФОНОВЫЙ ПОТОК: _run_sync_background()                        │
│                                                                 │
│    def _run_sync_background(self, task_id, request, devices):  │
│        try:                                                     │
│            result = self._do_sync(request, devices, task_id)   │
│            task_manager.complete_task(task_id, result=result)  │
│        except Exception as e:                                   │
│            task_manager.fail_task(task_id, str(e))             │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│ 5. ФАКТИЧЕСКАЯ СИНХРОНИЗАЦИЯ: _do_sync()                        │
│                                                                 │
│    def _do_sync(self, request, devices, task_id, steps):       │
│        # Создаём NetBox клиент                                  │
│        client = NetBoxClient(url=..., token=...)               │
│        sync = NetBoxSync(client, dry_run=request.dry_run)      │
│                                                                 │
│        # Devices                                                │
│        if request.sync_all or request.create_devices:          │
│            update_step("Devices")                               │
│            collector = DeviceCollector(credentials=...)        │
│            device_data = collector.collect_dicts(devices)      │
│            result = sync.sync_devices_from_inventory(...)      │
│            stats["devices"] = SyncStats(...)                   │
│                                                                 │
│        # Interfaces                                             │
│        if request.sync_all or request.interfaces:              │
│            update_step("Interfaces")                            │
│            collector = InterfaceCollector(credentials=...)     │
│            interface_data = collector.collect_dicts(devices)   │
│            for hostname, interfaces in by_device.items():      │
│                result = sync.sync_interfaces(hostname, ...)    │
│                                                                 │
│        # ... и так далее для IP, VLANs, Cables                 │
│                                                                 │
│        return {"success": True, "stats": stats, "diff": ...}   │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│ 6. SYNC МОДУЛЬ: netbox/sync/ (Batch API)                        │
│                                                                 │
│    # sync_devices_from_inventory()                              │
│    for entry in devices:                                        │
│        existing = client.get_device_by_name(name)              │
│        if existing: self._update_device(existing, ...)         │
│        else: self.create_device(name, device_type, ...)        │
│                                                                 │
│    # sync_interfaces() — BATCH API                              │
│    device = self.client.get_device_by_name(device_name)        │
│    existing = client.get_interfaces(device_id=device.id)       │
│    diff = comparator.compare_interfaces(local, remote)         │
│                                                                 │
│    # Batch create (один запрос на все новые интерфейсы)         │
│    create_batch = [_build_create_data(intf) for intf in create]│
│    client.bulk_create_interfaces(create_batch)  # 1 POST       │
│                                                                 │
│    # Batch update (один запрос на все обновления)               │
│    update_batch = [_build_update_data(nb, intf) for ...]       │
│    client.bulk_update_interfaces(update_batch)  # 1 PATCH      │
│                                                                 │
│    # Batch delete (один запрос на все удаления)                 │
│    delete_ids = [item.remote_data.id for item in delete]       │
│    client.bulk_delete_interfaces(delete_ids)    # 1 DELETE     │
│                                                                 │
│    # Post: MAC назначение (отдельный endpoint, по одному)       │
│    for mac in mac_queue:                                        │
│        client.assign_mac_to_interface(intf_id, mac)            │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│ 7. NETBOX CLIENT: netbox/client/ (mixin архитектура)            │
│                                                                 │
│    # Обёртка над pynetbox с bulk-методами                       │
│    class NetBoxClient(InterfacesMixin, InventoryMixin, ...):   │
│        def __init__(self, url, token):                         │
│            self.api = pynetbox.api(url, token=token)           │
│                                                                 │
│    # --- Поштучные методы (для fallback) ---                    │
│    def create_interface(device_id, name, **kwargs)             │
│    def update_interface(interface_id, **updates)               │
│                                                                 │
│    # --- Bulk методы (основной путь) ---                        │
│    def bulk_create_interfaces(data: List[dict])                │
│    def bulk_update_interfaces(updates: List[dict])             │
│    def bulk_delete_interfaces(ids: List[int])                  │
│                                                                 │
│    # Аналогично для inventory и IP:                             │
│    def bulk_create_inventory_items(data)                        │
│    def bulk_create_ip_addresses(data)                           │
│    # ...и bulk_update/delete                                    │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│ 8. NETBOX API (HTTP) — Batch запрос                             │
│                                                                 │
│    POST /api/dcim/interfaces/ (список = batch create)           │
│    [                                                            │
│      {"device": 123, "name": "Gi0/1", "type": "1000base-t"},  │
│      {"device": 123, "name": "Gi0/2", "type": "1000base-t"},  │
│      {"device": 123, "name": "Gi0/3", "type": "1000base-t"},  │
│      ... (до 48 интерфейсов в одном запросе)                   │
│    ]                                                            │
│                                                                 │
│    Response: 201 Created                                        │
│    [                                                            │
│      {"id": 456, "name": "Gi0/1", ...},                       │
│      {"id": 457, "name": "Gi0/2", ...},                       │
│      ...                                                        │
│    ]                                                            │
│                                                                 │
│    Раньше: 48 отдельных POST запросов                           │
│    Сейчас: 1 POST запрос с массивом                             │
└─────────────────────────────────────────────────────────────────┘
```

---

## Collectors — Сбор данных

**Что такое Collector?**

Collector — это класс, который собирает данные с устройств по SSH.

```
collectors/
├── __init__.py         # Экспорт всех collectors
├── base.py             # BaseCollector — базовый класс
├── device.py           # DeviceCollector — сбор инфо об устройстве
├── interfaces.py       # InterfaceCollector — сбор интерфейсов
├── mac.py              # MACCollector — сбор MAC таблицы
├── lldp.py             # LLDPCollector — сбор LLDP/CDP соседей
├── inventory.py        # InventoryCollector — сбор inventory
└── config_backup.py    # ConfigBackupCollector — бэкап конфигов
```

### BaseCollector — Базовый класс

```python
class BaseCollector:
    """
    Базовый класс для всех collectors.

    Содержит общую логику:
    - Параллельный сбор с нескольких устройств
    - Обработка ошибок подключения
    - Конвертация результатов
    """

    def __init__(
        self,
        credentials: Credentials = None,
        max_workers: int = 5,
    ):
        self.credentials = credentials
        self.max_workers = max_workers

    def collect(self, devices: List[Device]) -> List[Any]:
        """
        Собирает данные с устройств.

        Использует ThreadPoolExecutor для параллельного сбора.
        """
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # executor.map выполняет _collect_one для каждого устройства
            results = list(executor.map(self._collect_one, devices))

        # Фильтруем None (ошибки)
        return [r for r in results if r is not None]

    def collect_dicts(self, devices: List[Device]) -> List[Dict]:
        """
        Собирает данные и возвращает как список словарей.

        Унифицированный метод для Pipeline.
        """
        results = self.collect(devices)
        return [self._to_dict(r) for r in results]

    def _collect_one(self, device: Device) -> Optional[Any]:
        """
        Собирает данные с одного устройства.

        Переопределяется в дочерних классах.
        """
        raise NotImplementedError
```

### Пример: InterfaceCollector

```python
class InterfaceCollector(BaseCollector):
    """Сбор интерфейсов с устройств."""

    def _collect_one(self, device: Device) -> List[Interface]:
        """
        Собирает интерфейсы с одного устройства.
        """
        # 1. Подключаемся
        connection = Connection(
            device=device,
            credentials=self.credentials,
        )

        try:
            connection.connect()

            # 2. Выполняем команды
            # Команды зависят от платформы (cisco_ios, cisco_nxos, ...)
            output = connection.send_command("show interfaces")

            # 3. Парсим вывод
            # ntc-templates автоматически определяет формат
            parsed = parse_output(
                platform=device.device_type,
                command="show interfaces",
                data=output,
            )

            # 4. Конвертируем в Interface модели
            interfaces = []
            for entry in parsed:
                intf = Interface(
                    name=entry.get("interface"),
                    description=entry.get("description", ""),
                    status=entry.get("link_status", ""),
                    speed=entry.get("speed", ""),
                    # ...
                )
                interfaces.append(intf)

            return interfaces

        except Exception as e:
            logger.error(f"Ошибка сбора с {device.host}: {e}")
            return []
        finally:
            connection.disconnect()
```

---

## Сравнение данных (SyncComparator)

**Файл:** `core/domain/sync.py`

SyncComparator — это класс для сравнения локальных данных (с устройства) с удалёнными (в NetBox).

```python
class SyncComparator:
    """
    Сравнивает данные для синхронизации.

    Результат — SyncDiff:
    - to_create: что нужно создать
    - to_update: что нужно обновить
    - to_delete: что нужно удалить
    - to_skip: что оставить как есть
    """

    def compare_interfaces(
        self,
        local: List[Dict],           # Данные с устройства
        remote: List[Any],           # Данные из NetBox
        exclude_patterns: List[str], # Исключить (regex)
        create_missing: bool,        # Создавать отсутствующие
        update_existing: bool,       # Обновлять существующие
        cleanup: bool,               # Удалять лишние
        compare_fields: List[str],   # Какие поля сравнивать
    ) -> SyncDiff:
        """
        Сравнивает интерфейсы.
        """
        diff = SyncDiff()

        # Индексируем по имени для быстрого поиска
        local_by_name = {self._normalize_name(d["name"]): d for d in local}
        remote_by_name = {self._normalize_name(r.name): r for r in remote}

        # 1. Ищем что создать и обновить
        for name, local_data in local_by_name.items():
            # Исключаем по паттерну
            if self._should_exclude(name, exclude_patterns):
                continue

            remote_data = remote_by_name.get(name)

            if remote_data is None:
                # Нет в NetBox → создать
                if create_missing:
                    diff.to_create.append(DiffItem(
                        name=local_data["name"],
                        local_data=local_data,
                        change_type=ChangeType.CREATE,
                    ))
            else:
                # Есть в NetBox → проверить изменения
                if update_existing:
                    changes = self._compare_fields(
                        local_data, remote_data, compare_fields
                    )
                    if changes:
                        diff.to_update.append(DiffItem(
                            name=local_data["name"],
                            local_data=local_data,
                            remote_data=remote_data,
                            changes=changes,
                            change_type=ChangeType.UPDATE,
                        ))
                    else:
                        diff.to_skip.append(DiffItem(
                            name=local_data["name"],
                            change_type=ChangeType.SKIP,
                        ))

        # 2. Ищем что удалить
        if cleanup:
            for name, remote_data in remote_by_name.items():
                if name not in local_by_name:
                    # Есть в NetBox, но нет на устройстве → удалить
                    diff.to_delete.append(DiffItem(
                        name=remote_data.name,
                        remote_data=remote_data,
                        change_type=ChangeType.DELETE,
                    ))

        return diff

    def _compare_fields(
        self,
        local: Dict,
        remote: Any,
        fields: List[str],
    ) -> List[FieldChange]:
        """
        Сравнивает отдельные поля.
        """
        changes = []

        for field in fields:
            local_value = local.get(field)
            remote_value = getattr(remote, field, None)

            # Нормализуем значения для сравнения
            if isinstance(remote_value, object) and hasattr(remote_value, 'value'):
                remote_value = remote_value.value  # Enum в pynetbox

            if local_value != remote_value:
                changes.append(FieldChange(
                    field=field,
                    old_value=remote_value,
                    new_value=local_value,
                ))

        return changes
```

---

## Как работает to_dict() и очистка полей

### Проблема: пустые значения при синхронизации

Когда мы синхронизируем интерфейсы, нужно понять: "поле пустое" — это **отсутствие данных** или **намеренная очистка**?

**Пример:** порт был trunk (tagged-all), а потом его просто выключили (shutdown). Теперь mode пустой. Нужно ли очистить mode в NetBox?

**Ответ:** Да! Пустой mode = "очистить", а отсутствие поля = "не трогать".

### Как работает to_dict()

`to_dict()` превращает объект Interface в словарь для сравнения:

```python
# Файл: core/models.py

def to_dict(self) -> Dict[str, Any]:
    # Шаг 1: берём все поля, убираем пустые
    result = {k: v for k, v in asdict(self).items() if v is not None and v != ""}
    # Шаг 2: но description и mode ВСЕГДА включаем (пустая строка = очистка)
    result["description"] = self.description
    result["mode"] = self.mode
    return result
```

**Разберём `{k: v for k, v in ... if ...}` по шагам:**

```python
# Это dict comprehension — создание словаря в одну строку

# Шаг 1: asdict(self) — dataclass → обычный словарь
asdict(self) = {
    "name": "Gi0/1",
    "status": "disabled",
    "mode": "",          # пустой — порт shutdown
    "description": "",   # пустой — нет описания
    "speed": "",         # пустой — нет данных
    "mtu": None,         # нет данных
}

# Шаг 2: .items() — пары (ключ, значение)
# ("name", "Gi0/1"), ("status", "disabled"), ("mode", ""), ...

# Шаг 3: for k, v in ... — проходим по каждой паре
# k = "name",   v = "Gi0/1"
# k = "status", v = "disabled"
# k = "mode",   v = ""
# ...

# Шаг 4: if v is not None and v != "" — фильтр
# "Gi0/1"    → не None ✓, не "" ✓ → БЕРЁМ
# "disabled" → не None ✓, не "" ✓ → БЕРЁМ
# ""         → не None ✓, но "" ✗  → ВЫКИДЫВАЕМ
# None       → None ✗              → ВЫКИДЫВАЕМ

# Результат:
result = {"name": "Gi0/1", "status": "disabled"}
```

**Это то же самое что обычный цикл:**

```python
result = {}
for k, v in asdict(self).items():
    if v is not None and v != "":
        result[k] = v
# result = {"name": "Gi0/1", "status": "disabled"}
```

### Зачем description и mode добавляются отдельно

Проблема: mode="" выкидывается фильтром → comparator не видит что mode изменился → не обновляет.

Решение: **всегда включаем** mode и description в словарь:

```python
result["description"] = self.description  # "" = очистить описание
result["mode"] = self.mode                # "" = очистить mode (shutdown порт)
```

### Как comparator использует это

```python
# Файл: core/domain/sync.py

def _get_local_field(self, data, field_name):
    if field_name == "mode":
        if "mode" in data:
            return data["mode"]   # "" = очистить, "access"/"tagged" = установить
        return None               # ключа нет = пропустить сравнение

    if field_name == "description":
        if "description" in data:
            return data["description"]  # "" = очистить, "текст" = установить
        return None                     # пропустить
```

**Логика:**

| `data` содержит | `_get_local_field` вернёт | Действие |
|------------------|---------------------------|----------|
| `{"mode": "access"}` | `"access"` | Установить mode=access |
| `{"mode": ""}` | `""` | Очистить mode (shutdown порт) |
| `{}` (нет ключа mode) | `None` | Не трогать mode |

### Полная цепочка для shutdown порта

```
1. Устройство: interface Gi0/1 → shutdown (mode пустой)

2. Коллектор: Interface(name="Gi0/1", mode="")

3. to_dict(): {"name": "Gi0/1", "mode": "", "status": "disabled", ...}
              ↑ mode="" включён в словарь

4. _get_local_field("mode"): "mode" in data → True → return ""

5. _compare_fields: local="" vs remote="tagged-all" → РАЗНЫЕ → to_update

6. _update_interface: not intf.mode and current_mode → updates["mode"] = ""

7. NetBox API: interface.update(mode="") → mode очищён ✓
```

---

## Примеры кода с объяснениями

### Пример 1: Простая синхронизация интерфейсов

```python
from network_collector.netbox.client import NetBoxClient
from network_collector.netbox.sync import NetBoxSync
from network_collector.collectors import InterfaceCollector
from network_collector.core.credentials import Credentials
from network_collector.core.device import Device

# 1. Настройки
device = Device(host="192.168.1.1", device_type="cisco_ios")
credentials = Credentials(username="admin", password="secret")

# 2. Собираем интерфейсы с устройства
collector = InterfaceCollector(credentials=credentials)
interfaces = collector.collect([device])
# interfaces = [
#   Interface(name="Gi0/1", status="up", description="Uplink"),
#   Interface(name="Gi0/2", status="down", description=""),
#   ...
# ]

# 3. Создаём NetBox клиент и синхронизатор
client = NetBoxClient(
    url="http://netbox.local",
    token="your_token_here",
)
sync = NetBoxSync(client, dry_run=True)  # dry_run=True для проверки

# 4. Синхронизируем
result = sync.sync_interfaces("switch-01", interfaces)

# result = {
#   "created": 2,
#   "updated": 3,
#   "deleted": 0,
#   "skipped": 10,
#   "details": {
#     "create": [{"name": "Gi0/5"}, {"name": "Gi0/6"}],
#     "update": [{"name": "Gi0/1", "changes": ["description"]}],
#   }
# }

print(f"Создано: {result['created']}, Обновлено: {result['updated']}")
```

### Пример 2: Pipeline из YAML

**pipelines/full-sync.yaml:**
```yaml
id: full-sync
name: Полная синхронизация
description: Собирает все данные и синхронизирует с NetBox

steps:
  - id: collect_devices
    type: collect
    target: devices

  - id: sync_devices
    type: sync
    target: devices
    depends_on: [collect_devices]
    options:
      site: Office
      role: switch

  - id: collect_interfaces
    type: collect
    target: interfaces
    depends_on: [collect_devices]

  - id: sync_interfaces
    type: sync
    target: interfaces
    depends_on: [sync_devices, collect_interfaces]
```

**Запуск:**
```python
from network_collector.core.pipeline import Pipeline, PipelineExecutor

# 1. Загружаем pipeline
pipeline = Pipeline.from_yaml("pipelines/full-sync.yaml")

# 2. Валидируем
errors = pipeline.validate()
if errors:
    print(f"Ошибки: {errors}")
    exit(1)

# 3. Создаём executor
executor = PipelineExecutor(
    pipeline,
    dry_run=False,
    on_step_start=lambda step: print(f"Начат: {step.id}"),
    on_step_complete=lambda step, result: print(f"Завершён: {step.id} ({result.status.value})"),
)

# 4. Запускаем
result = executor.run(
    devices=[Device(host="192.168.1.1", device_type="cisco_ios")],
    credentials={"username": "admin", "password": "secret"},
    netbox_config={"url": "http://netbox.local", "token": "token"},
)

# 5. Проверяем результат
print(f"Pipeline {result.pipeline_id}: {result.status.value}")
for step in result.steps:
    print(f"  {step.step_id}: {step.status.value} ({step.duration_ms}ms)")
```

### Пример 3: API запрос (curl)

```bash
# Синхронизация через API
curl -X POST http://localhost:8080/api/sync \
  -H "Content-Type: application/json" \
  -H "X-Credentials: $(echo -n 'admin:secret' | base64)" \
  -H "X-NetBox-URL: http://netbox.local" \
  -H "X-NetBox-Token: your_token" \
  -d '{
    "sync_all": true,
    "dry_run": true,
    "async_mode": true
  }'

# Ответ:
# {
#   "success": true,
#   "task_id": "abc-123-def"
# }

# Проверка статуса
curl http://localhost:8080/api/tasks/abc-123-def

# Ответ:
# {
#   "id": "abc-123-def",
#   "status": "running",
#   "progress": 50,
#   "current_step": 2,
#   "message": "Синхронизация: Interfaces"
# }
```

---

## Batch API — Оптимизация производительности

> **Добавлено:** Февраль 2026
> **Причина:** Pipeline на 22 устройства выполнялся ~30 минут, основное время — sync фаза
> **Результат:** Ускорение sync фазы в 3-5 раз

### Проблема

До оптимизации каждая операция синхронизации выполнялась **поштучно**:

```
# Пример: sync_interfaces для 1 устройства с 48 портами

get_device_by_name()              # 1 запрос
get_interfaces(device_id)         # 1 запрос
for each interface to update:
    get(id) + update()            # 2 запроса × 48 = 96 запросов
                                  # Итого: ~100 API запросов на устройство
```

При 22 устройствах: **~2200 API-вызовов** только для интерфейсов.
Добавим inventory (~50 на устройство) и IP (~30 на устройство) — получаем **~5000+ вызовов**.

### Решение: Batch API через pynetbox

NetBox API поддерживает bulk-операции:
- **POST** с массивом = создать несколько объектов одним запросом
- **PATCH** с массивом (каждый элемент содержит `id`) = обновить несколько объектов
- **DELETE** с массивом ID = удалить несколько объектов

pynetbox это поддерживает из коробки:

```python
# Bulk create — передаём список словарей вместо одного
api.dcim.interfaces.create([
    {"device": 1, "name": "Gi0/1", "type": "1000base-t"},
    {"device": 1, "name": "Gi0/2", "type": "1000base-t"},
    {"device": 1, "name": "Gi0/3", "type": "1000base-t"},
])
# → 1 HTTP POST вместо 3

# Bulk update — каждый dict содержит 'id'
api.dcim.interfaces.update([
    {"id": 101, "description": "Uplink"},
    {"id": 102, "description": "Server"},
    {"id": 103, "enabled": False},
])
# → 1 HTTP PATCH вместо 3

# Bulk delete — список объектов с id
api.dcim.interfaces.delete([{"id": 101}, {"id": 102}])
# → 1 HTTP DELETE вместо 2
```

### Архитектура изменений

#### Слой 1: NetBox Client (netbox/client/)

Добавлены **bulk-методы** в mixin-классы клиента:

| Файл | Методы |
|------|--------|
| `client/interfaces.py` | `bulk_create_interfaces()`, `bulk_update_interfaces()`, `bulk_delete_interfaces()` |
| `client/inventory.py` | `bulk_create_inventory_items()`, `bulk_update_inventory_items()`, `bulk_delete_inventory_items()` |
| `client/ip_addresses.py` | `bulk_create_ip_addresses()`, `bulk_delete_ip_addresses()` |

Пример реализации (все аналогичны):

```python
def bulk_create_interfaces(self, interfaces_data: List[dict]) -> List[Any]:
    """Создаёт несколько интерфейсов одним API-вызовом."""
    if not interfaces_data:
        return []
    result = self.api.dcim.interfaces.create(interfaces_data)
    return result if isinstance(result, list) else [result]

def bulk_update_interfaces(self, updates: List[dict]) -> List[Any]:
    """Обновляет несколько интерфейсов одним API-вызовом.
    Каждый dict должен содержать 'id'."""
    if not updates:
        return []
    result = self.api.dcim.interfaces.update(updates)
    return result if isinstance(result, list) else [result]

def bulk_delete_interfaces(self, ids: List[int]) -> bool:
    """Удаляет интерфейсы по списку ID."""
    if not ids:
        return True
    objects = [{"id": id_} for id_ in ids]
    self.api.dcim.interfaces.delete(objects)
    return True
```

Старые поштучные методы (`create_interface`, `update_interface`) **сохранены** для fallback.

#### Слой 2: Sync Mixins (netbox/sync/)

Рефакторинг sync-методов для пакетных операций:

**Interfaces (sync/interfaces.py):**
| Метод | Назначение |
|-------|-----------|
| `_build_create_data(device_id, intf)` | Подготовка dict для create (без API) |
| `_build_update_data(nb_interface, intf)` | Подготовка dict для update (без API) |
| `_batch_create_interfaces(...)` | Bulk create + MAC post-assign + fallback |
| `_batch_update_interfaces(...)` | Bulk update + MAC post-assign + fallback |
| `_batch_delete_interfaces(...)` | Bulk delete + fallback |
| `_create_interface()` | Старый метод (только для fallback) |
| `_update_interface()` | Старый метод (только для fallback) |

**Inventory (sync/inventory.py):**
- `sync_inventory()` — собирает `create_batch`, `update_batch`, `delete_ids`
- Один `bulk_create_inventory_items()` вместо цикла `create_inventory_item()`
- Один `bulk_update_inventory_items()` вместо цикла `update_inventory_item()`
- Один `bulk_delete_inventory_items()` вместо цикла `delete_inventory_item()`

**IP Addresses (sync/ip_addresses.py):**
- `_batch_create_ip_addresses()` — bulk create IP
- `_batch_delete_ip_addresses()` — bulk delete IP
- Update остаётся поштучным (может требовать пересоздание IP при смене маски)

### Паттерн: подготовка данных → batch → fallback

Все batch-операции следуют одному паттерну:

```python
def _batch_create_interfaces(self, device_id, to_create, interfaces, stats, details):
    """Batch создание интерфейсов."""

    # ШАГ 1: Подготовка данных (без API-вызовов)
    create_batch = []
    create_mac_queue = []
    for item in to_create:
        intf = find_interface(item.name)
        data, mac = self._build_create_data(device_id, intf)  # чистая функция
        create_batch.append(data)
        if mac:
            create_mac_queue.append((len(create_batch) - 1, mac))

    # ШАГ 2: dry_run — только логирование
    if self.dry_run:
        for name in create_names:
            logger.info(f"[DRY-RUN] Создание интерфейса: {name}")
            stats["created"] += 1
        return

    # ШАГ 3: Batch запрос (1 HTTP вызов на все интерфейсы)
    try:
        created = self.client.bulk_create_interfaces(create_batch)
        for name in create_names:
            stats["created"] += 1

        # Post-create: MAC (отдельный endpoint)
        for idx, mac in create_mac_queue:
            self.client.assign_mac_to_interface(created[idx].id, mac)

    # ШАГ 4: Fallback на поштучные операции при ошибке
    except Exception as e:
        logger.warning(f"Batch create не удался ({e}), fallback")
        for data in create_batch:
            try:
                self._create_interface(device_id, intf)
                stats["created"] += 1
            except Exception as exc:
                logger.error(f"Ошибка создания {name}: {exc}")
```

### Что не изменилось

- **Domain layer** (`core/domain/sync.py`): SyncComparator работает как раньше
- **dry_run режим**: пропускает API-вызовы, считает статистику
- **Формат результата**: `{created, updated, deleted, skipped, details}` — тот же
- **Pipeline и CLI**: используют тот же `sync.sync_interfaces()` — без изменений
- **Поштучные методы**: `_create_interface()`, `_update_interface()` — сохранены для fallback

### Количественный эффект

| Метрика | До | После |
|---------|------|---------|
| API вызовов на 1 устройство (interfaces) | ~100 | ~3 + MAC |
| API вызовов на 1 устройство (inventory) | ~50 | ~3 |
| API вызовов на 1 устройство (IP) | ~30 | ~2 |
| Общее время sync (22 устройства) | ~10 мин | ~2-3 мин |
| **Ожидаемое ускорение sync фазы** | | **3-5x** |

### Тестирование

Тесты для batch операций: `tests/test_netbox/test_bulk_operations.py` (32 теста)

Покрытие:
- Batch create/update/delete для interfaces, inventory, IP
- dry_run режим
- Fallback при ошибке batch (переключение на поштучные операции)
- Пустые данные (edge case)
- Device not found
- Update с реальным diff

---

## Резюме

### Ключевые концепции

1. **Pipeline** — последовательность шагов (collect → sync → export)
2. **PipelineExecutor** — выполняет pipeline, управляет контекстом
3. **SyncBase** — базовый класс с общими методами (кэширование, get-or-create)
4. **Mixin** — классы с отдельной функциональностью (interfaces, cables, ...)
5. **NetBoxSync** — главный класс, объединяющий все Mixin
6. **SyncService** — обёртка для API (async, task tracking)
7. **Collector** — сбор данных с устройств по SSH
8. **SyncComparator** — сравнение local vs remote данных
9. **Batch API** — пакетные операции для ускорения sync (bulk create/update/delete)

### Поток данных

```
Устройство (SSH) → Collector → Models → Comparator → Sync (Batch API) → NetBox API
```

### Файлы для изучения

| Файл | Что изучить |
|------|-------------|
| `core/pipeline/models.py` | Pipeline, PipelineStep, StepType |
| `core/pipeline/executor.py` | PipelineExecutor, run(), _execute_* |
| `netbox/sync/base.py` | SyncBase, _find_*, _get_or_create_* |
| `netbox/sync/interfaces.py` | InterfacesSyncMixin, batch create/update/delete, _build_*_data |
| `netbox/sync/inventory.py` | InventorySyncMixin, batch create/update/delete |
| `netbox/sync/ip_addresses.py` | IPAddressesSyncMixin, batch create/delete |
| `netbox/sync/main.py` | NetBoxSync (множественное наследование) |
| `netbox/client/interfaces.py` | InterfacesMixin, bulk_create/update/delete_interfaces |
| `netbox/client/inventory.py` | InventoryMixin, bulk_create/update/delete_inventory_items |
| `netbox/client/ip_addresses.py` | IPAddressesMixin, bulk_create/delete_ip_addresses |
| `api/services/sync_service.py` | SyncService, _do_sync, async handling |
| `core/domain/sync.py` | SyncComparator, SyncDiff, compare_* |
