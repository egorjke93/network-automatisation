# Network Collector — Web API

> REST API и веб-интерфейс для сбора данных с сетевого оборудования и синхронизации с NetBox

## Содержание

1. [Запуск](#запуск)
2. [Архитектура Frontend ↔ Backend](#архитектура-frontend--backend)
3. [Полная цепочка: от клика до результата](#полная-цепочка-от-клика-до-результата)
4. [Credentials и авторизация](#credentials-и-авторизация)
5. [Async Mode и Progress Bar](#async-mode-и-progress-bar)
6. [REST API Endpoints](#rest-api-endpoints)
7. [Web UI Страницы](#web-ui-страницы)

---

## Запуск

### Backend (FastAPI)

```bash
cd /home/sa/project
source network_collector/myenv/bin/activate
uvicorn network_collector.api.main:app --reload --host 0.0.0.0 --port 8080
```

### Frontend (Vue.js)

```bash
cd /home/sa/project/network_collector/frontend
npm install        # первый раз
npm run dev        # development сервер (http://localhost:5173)
```

**Production сборка:**
```bash
npm run build      # сборка в dist/
npm run preview    # превью собранной версии
```

### Запуск обоих сервисов

```bash
# Терминал 1: Backend
cd /home/sa/project && source network_collector/myenv/bin/activate
uvicorn network_collector.api.main:app --host 0.0.0.0 --port 8080

# Терминал 2: Frontend
cd /home/sa/project/network_collector/frontend && npm run dev
```

**Доступ:**
- **Web UI:** http://localhost:5173
- **API:** http://localhost:8080

### Безопасность (HTTPS)

Для локальной разработки (`localhost`) HTTPS не требуется — трафик не покидает машину.

Для доступа из сети используйте:
- **nginx + SSL** (рекомендуется для production)
- **self-signed сертификат** (для внутренней сети)

```bash
# Self-signed сертификат
openssl req -x509 -newkey rsa:4096 -nodes \
  -keyout key.pem -out cert.pem -days 365 \
  -subj "/CN=localhost"

# Запуск с SSL
uvicorn network_collector.api.main:app \
  --host 0.0.0.0 --port 8443 \
  --ssl-keyfile key.pem --ssl-certfile cert.pem
```

## Документация API

- **Swagger UI:** http://localhost:8080/docs
- **ReDoc:** http://localhost:8080/redoc

---

## Архитектура Frontend ↔ Backend

### Общая схема

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              BROWSER                                          │
│                                                                               │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │                     Vue.js 3 (SPA)                                       │ │
│  │                     http://localhost:5173                                │ │
│  │                                                                          │ │
│  │  ┌────────────┐   ┌────────────┐   ┌────────────┐   ┌────────────┐     │ │
│  │  │ App.vue    │   │ Sync.vue   │   │Pipelines.vue│  │History.vue │     │ │
│  │  │ (навигация)│   │ (sync)     │   │ (pipeline) │   │ (журнал)   │     │ │
│  │  └────────────┘   └────────────┘   └────────────┘   └────────────┘     │ │
│  │                          │                                               │ │
│  │                          ▼                                               │ │
│  │  ┌───────────────────────────────────────────────────────────────────┐  │ │
│  │  │                      axios (HTTP Client)                           │  │ │
│  │  │                                                                    │  │ │
│  │  │  interceptor: добавляет X-SSH-Username, X-SSH-Password,           │  │ │
│  │  │               X-NetBox-URL, X-NetBox-Token из sessionStorage      │  │ │
│  │  └───────────────────────────────────────────────────────────────────┘  │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                    │                                          │
│                          HTTP POST/GET (JSON)                                 │
│                                    │                                          │
└────────────────────────────────────┼──────────────────────────────────────────┘
                                     │
                          ┌──────────┴──────────┐
                          │  vite proxy         │
                          │  /api/* → :8080     │
                          └──────────┬──────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           BACKEND (FastAPI)                                   │
│                           http://localhost:8080                               │
│                                                                               │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │                         api/routes/*.py                                  │ │
│  │                                                                          │ │
│  │  /api/sync/netbox    → sync.py     → SyncService                        │ │
│  │  /api/pipelines      → pipelines.py → PipelineExecutor                  │ │
│  │  /api/tasks/{id}     → tasks.py    → TaskManager                        │ │
│  │  /api/history        → history.py  → HistoryService                     │ │
│  │  /api/devices/collect → devices.py → CollectorService                   │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                    │                                          │
│                                    ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │                        api/services/*.py                                 │ │
│  │                                                                          │ │
│  │  SyncService      → создаёт Task, запускает sync, обновляет progress    │ │
│  │  TaskManager      → хранит задачи in-memory, отдаёт статус              │ │
│  │  HistoryService   → сохраняет результаты в data/history.json            │ │
│  │  CollectorService → собирает данные с устройств                         │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                    │                                          │
│                                    ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │                         CORE LAYER                                       │ │
│  │                                                                          │ │
│  │  collectors/*.py    → SSH подключение, парсинг                          │ │
│  │  netbox/sync/*.py   → API вызовы к NetBox                               │ │
│  │  core/pipeline/*    → оркестрация шагов                                 │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                    │                                          │
│                    ┌───────────────┴───────────────┐                          │
│                    ▼                               ▼                          │
│           ┌──────────────┐               ┌──────────────┐                     │
│           │ SSH (Scrapli)│               │ NetBox API   │                     │
│           │ → устройства │               │ (pynetbox)   │                     │
│           └──────────────┘               └──────────────┘                     │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Ключевые файлы

| Слой | Файл | Описание |
|------|------|----------|
| **Frontend** | `frontend/src/main.js` | Настройка Vue, роутер, axios interceptor |
| | `frontend/src/App.vue` | Главный компонент, навигация |
| | `frontend/src/views/*.vue` | Страницы (Sync, Pipelines, History) |
| | `frontend/src/components/*.vue` | Переиспользуемые компоненты |
| | `frontend/vite.config.js` | Proxy настройка `/api → :8080` |
| **Backend** | `api/main.py` | FastAPI app, подключение роутеров |
| | `api/routes/*.py` | HTTP endpoints |
| | `api/services/*.py` | Бизнес-логика |
| | `api/schemas/*.py` | Pydantic модели (request/response) |

---

## Полная цепочка: от клика до результата

### Пример: Sync NetBox (пошагово)

Разберём что происходит когда пользователь нажимает "Preview Changes" на странице Sync.

#### Шаг 1: Пользователь заполняет форму и нажимает кнопку

**Файл:** `frontend/src/views/Sync.vue`

```vue
<template>
  <form @submit.prevent="runSync">
    <DeviceSelector v-model="selectedDevices" />
    <input v-model="site" type="text" />
    <label><input type="checkbox" v-model="interfaces" /> Interfaces</label>
    <button type="submit">Preview Changes</button>
  </form>
</template>
```

**Что происходит:**
1. Пользователь выбирает устройства через `DeviceSelector`
2. Отмечает галочки (interfaces, cables, etc.)
3. Нажимает кнопку — срабатывает `@submit.prevent="runSync"`

#### Шаг 2: Vue компонент формирует и отправляет запрос

**Файл:** `frontend/src/views/Sync.vue`

```javascript
methods: {
  buildRequest() {
    return {
      devices: this.selectedDevices,        // ["10.0.0.1", "10.0.0.2"]
      site: this.site || null,              // "Office"
      interfaces: this.interfaces,           // true
      cables: this.cables,                   // false
      dry_run: true,                         // только предпросмотр
      async_mode: true,                      // async режим
    }
  },

  async runSync() {
    this.loading = true
    this.taskId = null

    const res = await axios.post('/api/sync/netbox', {
      ...this.buildRequest(),
      dry_run: true,
      async_mode: true,
    })

    // Получаем task_id для отслеживания прогресса
    this.taskId = res.data.task_id   // "a1b2c3d4"
  }
}
```

**Что происходит:**
1. `buildRequest()` собирает данные из формы в объект
2. `axios.post()` отправляет POST запрос на `/api/sync/netbox`
3. Благодаря axios interceptor, автоматически добавляются headers с credentials

#### Шаг 3: Axios interceptor добавляет credentials

**Файл:** `frontend/src/main.js`

```javascript
// Axios interceptor — выполняется ПЕРЕД каждым запросом
axios.interceptors.request.use((config) => {
  // Берём credentials из sessionStorage
  const sshUsername = sessionStorage.getItem('ssh_username')
  const sshPassword = sessionStorage.getItem('ssh_password')
  const netboxUrl = sessionStorage.getItem('netbox_url')
  const netboxToken = sessionStorage.getItem('netbox_token')

  // Добавляем в headers
  if (sshUsername) config.headers['X-SSH-Username'] = sshUsername
  if (sshPassword) config.headers['X-SSH-Password'] = sshPassword
  if (netboxUrl) config.headers['X-NetBox-URL'] = netboxUrl
  if (netboxToken) config.headers['X-NetBox-Token'] = netboxToken

  return config
})
```

**Что происходит:**
1. Перед отправкой запроса срабатывает interceptor
2. Достаёт credentials из sessionStorage браузера
3. Добавляет их в HTTP headers запроса

**Итоговый HTTP запрос:**
```http
POST /api/sync/netbox HTTP/1.1
Host: localhost:8080
Content-Type: application/json
X-SSH-Username: admin
X-SSH-Password: secret123
X-NetBox-URL: http://netbox:8000
X-NetBox-Token: abc123token

{
  "devices": ["10.0.0.1", "10.0.0.2"],
  "site": "Office",
  "interfaces": true,
  "dry_run": true,
  "async_mode": true
}
```

#### Шаг 4: Vite proxy перенаправляет запрос на backend

**Файл:** `frontend/vite.config.js`

```javascript
export default defineConfig({
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8080',  // Backend
        changeOrigin: true,
      },
    },
  },
})
```

**Что происходит:**
1. Браузер отправляет запрос на `localhost:5173/api/sync/netbox`
2. Vite dev server видит путь `/api/*`
3. Проксирует запрос на `localhost:8080/api/sync/netbox`

#### Шаг 5: FastAPI route принимает запрос

**Файл:** `api/routes/sync.py`

```python
@router.post("/netbox", response_model=SyncResponse)
async def sync_netbox(request: Request, body: SyncRequest):
    # Извлекаем credentials из headers
    credentials = get_credentials_from_headers(request)
    # credentials = Credentials(username="admin", password="secret123")

    netbox = get_netbox_config_from_headers(request)
    # netbox = NetBoxConfig(url="http://netbox:8000", token="abc123")

    # Создаём сервис
    service = SyncService(credentials, netbox)

    # Запускаем синхронизацию
    return await service.sync(body)
```

**Что происходит:**
1. FastAPI парсит JSON body в `SyncRequest` (Pydantic модель)
2. `get_credentials_from_headers()` достаёт credentials из headers
3. Создаётся `SyncService` с credentials
4. Вызывается `service.sync(body)`

#### Шаг 6: SyncService создаёт Task и запускает синхронизацию

**Файл:** `api/services/sync_service.py`

```python
class SyncService:
    async def sync(self, request: SyncRequest) -> SyncResponse:
        devices = self._get_devices(request.devices)
        steps = self._calculate_steps(request)  # ["collect", "sync_interfaces", ...]

        if request.async_mode:
            # Создаём задачу для отслеживания прогресса
            task = task_manager.create_task(
                task_type="sync",
                total_steps=len(steps),
                total_items=len(devices),
                steps=steps,
            )

            # Сразу возвращаем task_id клиенту
            # Синхронизация продолжится в фоне
            asyncio.create_task(self._run_sync_async(request, devices, task))

            return SyncResponse(
                success=True,
                task_id=task.id,  # "a1b2c3d4"
                dry_run=request.dry_run,
            )
```

**Что происходит:**
1. Получаем список устройств для синхронизации
2. Вычисляем шаги (collect, sync_interfaces, sync_cables, ...)
3. В async_mode создаём Task для отслеживания
4. Сразу возвращаем response с `task_id`
5. Синхронизация продолжается в background через `asyncio.create_task()`

#### Шаг 7: Frontend получает task_id и начинает polling

**Файл:** `frontend/src/views/Sync.vue`

```javascript
async runSync() {
  const res = await axios.post('/api/sync/netbox', {...})

  // Получаем task_id
  this.taskId = res.data.task_id  // "a1b2c3d4"

  // ProgressBar автоматически начинает polling
  // (см. watch на taskId)
}
```

**Файл:** `frontend/src/components/ProgressBar.vue`

```javascript
watch: {
  taskId: {
    immediate: true,
    handler(newId) {
      if (newId) {
        this.startPolling()  // Начинаем опрашивать статус
      }
    },
  },
},

methods: {
  async startPolling() {
    this.visible = true
    await this.fetchTaskStatus()

    // Опрашиваем каждые 500ms
    this.pollTimer = setInterval(this.fetchTaskStatus, 500)
  },

  async fetchTaskStatus() {
    const res = await axios.get(`/api/tasks/${this.taskId}`)
    const task = res.data

    this.status = task.status           // "running"
    this.progress = task.progress_percent  // 45
    this.message = task.message         // "Обработка 10.0.0.1 (2/5)"
    this.steps = task.steps             // [{name: "collect", status: "completed"}, ...]

    // Если завершено — останавливаем polling
    if (task.status === 'completed' || task.status === 'failed') {
      this.stopPolling()
      this.$emit('complete', task)  // Уведомляем родителя
    }
  }
}
```

**Что происходит:**
1. Vue компонент получает `task_id`
2. ProgressBar.vue видит изменение taskId через `watch`
3. Начинает опрашивать `/api/tasks/{task_id}` каждые 500ms
4. Обновляет progress bar на основе ответа
5. Когда status='completed' — останавливает polling и emit'ит событие

#### Шаг 8: TaskManager обновляется в процессе синхронизации

**Файл:** `api/services/sync_service.py`

```python
def _do_sync(self, request, devices, task_id, steps):
    # Шаг 1: Collect interfaces
    task_manager.start_step(task_id, step_index=0, total_items=len(devices))
    task_manager.update_task(task_id, message="Collecting interfaces...")

    for i, device in enumerate(devices):
        task_manager.update_item(task_id, current=i+1, name=device.host)
        # ... сбор данных ...

    task_manager.complete_step(task_id, step_index=0)

    # Шаг 2: Sync interfaces
    task_manager.start_step(task_id, step_index=1, total_items=len(interfaces))
    task_manager.update_task(task_id, message="Syncing interfaces...")

    for i, intf in enumerate(interfaces):
        task_manager.update_item(task_id, current=i+1, name=intf.name)
        # ... синхронизация ...

    task_manager.complete_step(task_id, step_index=1)

    # Завершение
    task_manager.complete_task(task_id, result={...}, message="Sync completed")
```

**Что происходит:**
1. В процессе работы SyncService постоянно обновляет TaskManager
2. `start_step()` — начинает новый шаг
3. `update_item()` — обновляет прогресс внутри шага
4. `complete_step()` — завершает шаг
5. `complete_task()` — завершает всю задачу с результатом

#### Шаг 9: Frontend получает результат

**Файл:** `frontend/src/views/Sync.vue`

```javascript
// ProgressBar emit'ит событие когда задача завершена
<ProgressBar :task-id="taskId" @complete="onTaskComplete" />

methods: {
  onTaskComplete(task) {
    this.loading = false

    // Получаем результат из task.result
    this.result = {
      success: task.result.success,
      dry_run: task.result.dry_run,
      devices: task.result.stats?.devices,     // {created: 2, updated: 0}
      interfaces: task.result.stats?.interfaces, // {created: 15, updated: 3}
      diff: task.result.diff,                  // [{action: "create", ...}]
      errors: task.result.errors,
    }

    // Теперь result отображается в template
  }
}
```

**Что происходит:**
1. ProgressBar завершает polling и emit'ит событие `complete`
2. Sync.vue получает task с результатом в `onTaskComplete()`
3. Извлекает данные из `task.result`
4. Vue реактивно обновляет template с результатами

#### Шаг 10: Результат записывается в историю

**Файл:** `api/services/sync_service.py`

```python
# После завершения sync (не dry_run)
if not result["dry_run"]:
    history_service.add_entry(
        operation="sync",
        status="success",
        devices=[d.host for d in devices],
        stats={
            "devices": result["stats"]["devices"],
            "interfaces": result["stats"]["interfaces"],
            ...
        },
        details=diff_list,  # Полный diff изменений
        duration_ms=duration_ms,
    )
```

**Файл:** `api/services/history_service.py`

```python
def add_entry(self, operation, status, devices, stats, details, duration_ms):
    entry = {
        "id": str(uuid.uuid4())[:8],
        "operation": operation,
        "status": status,
        "timestamp": datetime.now().isoformat(),
        "devices": devices,
        "stats": stats,
        "details": details,
        "duration_ms": duration_ms,
    }

    # Добавляем в начало списка
    self._history.insert(0, entry)

    # Ограничиваем до 1000 записей
    if len(self._history) > 1000:
        self._history = self._history[:1000]

    # Сохраняем в файл
    self._save()  # → data/history.json
```

**Что происходит:**
1. После успешной синхронизации (не preview)
2. `history_service.add_entry()` создаёт запись
3. Сохраняет в `data/history.json`
4. Ограничивает историю 1000 записями

---

## Credentials и авторизация

### Где хранятся credentials?

```
┌─────────────────────────────────────────────────────────────────────┐
│                         BROWSER                                       │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │                    sessionStorage                                │ │
│  │                                                                  │ │
│  │  ssh_username: "admin"                                           │ │
│  │  ssh_password: "secret123"                                       │ │
│  │  netbox_url: "http://netbox:8000"                               │ │
│  │  netbox_token: "abc123token"                                    │ │
│  │                                                                  │ │
│  │  (Удаляются при закрытии вкладки)                               │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│                                                                       │
│  ИЛИ                                                                  │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │                    localStorage                                  │ │
│  │                                                                  │ │
│  │  (То же, но сохраняется между сессиями)                         │ │
│  └─────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

### Как credentials попадают в запрос?

**Страница Credentials (`/credentials`):**

```javascript
// frontend/src/views/Credentials.vue
saveCredentials() {
  // Сохраняем в sessionStorage (или localStorage если "Remember me")
  sessionStorage.setItem('ssh_username', this.sshUsername)
  sessionStorage.setItem('ssh_password', this.sshPassword)
  sessionStorage.setItem('netbox_url', this.netboxUrl)
  sessionStorage.setItem('netbox_token', this.netboxToken)
}
```

**Axios interceptor (автоматически):**

```javascript
// frontend/src/main.js
axios.interceptors.request.use((config) => {
  const username = sessionStorage.getItem('ssh_username')
  if (username) config.headers['X-SSH-Username'] = username
  // ... остальные
  return config
})
```

**Backend извлекает из headers:**

```python
# api/routes/auth.py
def get_credentials_from_headers(request: Request) -> Credentials:
    username = request.headers.get("X-SSH-Username")
    password = request.headers.get("X-SSH-Password")

    if not username or not password:
        raise HTTPException(401, "SSH credentials required")

    return Credentials(username=username, password=password)
```

### Важно: Сервер НЕ хранит пароли!

- Пароли хранятся только в браузере (sessionStorage)
- Передаются в каждом запросе через headers
- Backend использует их только для текущего запроса
- После ответа — забывает

---

## Async Mode и Progress Bar

### Зачем async mode?

Синхронизация может занять несколько минут:
- SSH подключения к устройствам
- Парсинг данных
- API вызовы к NetBox

Без async mode браузер бы ждал ответа минутами — плохой UX.

### Как работает async mode

```
Sync Mode (без async):
─────────────────────────────────────────────────────────────────
Browser ──POST──▶ Backend ─────работа─────▶ ◀──Response── Browser
                            (5 минут)
         (браузер ждёт 5 минут)


Async Mode (с async):
─────────────────────────────────────────────────────────────────
Browser ──POST──▶ Backend
                    │
                    ├──▶ создаёт Task
                    ├──▶ возвращает task_id (100ms)
                    │
Browser ◀─task_id──┘

Browser ──GET /tasks/{id}──▶ Backend ──▶ {status: "running", progress: 10%}
Browser ──GET /tasks/{id}──▶ Backend ──▶ {status: "running", progress: 45%}
Browser ──GET /tasks/{id}──▶ Backend ──▶ {status: "running", progress: 80%}
Browser ──GET /tasks/{id}──▶ Backend ──▶ {status: "completed", result: {...}}
```

### Компоненты async mode

| Компонент | Файл | Описание |
|-----------|------|----------|
| `TaskManager` | `api/services/task_manager.py` | Хранит задачи in-memory |
| `Task` | там же | Dataclass с прогрессом |
| `ProgressBar` | `frontend/src/components/ProgressBar.vue` | Polling и отображение |
| `/api/tasks/{id}` | `api/routes/tasks.py` | Endpoint для статуса |

### TaskManager API

```python
# Создание задачи
task = task_manager.create_task(
    task_type="sync",
    total_steps=4,
    total_items=10,
    steps=["collect", "sync_interfaces", "sync_cables", "sync_inventory"],
)

# Начало шага
task_manager.start_step(task.id, step_index=0, total_items=10)

# Обновление прогресса
task_manager.update_item(task.id, current=5, name="10.0.0.5")

# Завершение шага
task_manager.complete_step(task.id, step_index=0)

# Завершение задачи
task_manager.complete_task(task.id, result={...}, message="Done")
```

### ProgressBar props

```vue
<ProgressBar
  :task-id="taskId"           <!-- ID задачи для polling -->
  :poll-interval="500"        <!-- Интервал polling (ms) -->
  :auto-hide="true"           <!-- Скрыть после завершения -->
  :hide-delay="3000"          <!-- Через сколько скрыть (ms) -->
  @complete="onTaskComplete"  <!-- Событие завершения -->
/>
```

---

## Аутентификация

Credentials передаются через **HTTP headers** в каждом запросе:

| Header | Описание | Пример |
|--------|----------|--------|
| `X-SSH-Username` | SSH логин | `admin` |
| `X-SSH-Password` | SSH пароль | `secret` |
| `X-NetBox-URL` | URL NetBox API | `http://netbox:8000` |
| `X-NetBox-Token` | API токен NetBox | `0123456789abcdef` |

**Важно:** Сервер НЕ хранит пароли — они остаются только в браузере (sessionStorage).

---

## Endpoints

### Health Check

| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/` | Информация об API |
| GET | `/health` | Проверка состояния |

**Пример:**
```bash
curl http://localhost:8080/health
```

**Ответ:**
```json
{
  "status": "ok",
  "version": "0.1.0",
  "uptime": 123.45
}
```

---

### Auth — Управление Credentials

| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/api/auth/credentials/status` | Проверить наличие SSH credentials |
| GET | `/api/auth/netbox/status` | Проверить наличие NetBox config |

**Пример:**
```bash
curl -H "X-SSH-Username: admin" http://localhost:8080/api/auth/credentials/status
```

---

### Devices — Инвентаризация

| Метод | Endpoint | Описание |
|-------|----------|----------|
| POST | `/api/devices/collect` | Собрать информацию об устройствах |

**Запрос:**
```bash
curl -X POST http://localhost:8080/api/devices/collect \
  -H "Content-Type: application/json" \
  -H "X-SSH-Username: admin" \
  -H "X-SSH-Password: secret" \
  -d '{
    "devices": [
      {"host": "192.168.1.1", "platform": "cisco_ios"},
      {"host": "192.168.1.2", "platform": "cisco_nxos"}
    ]
  }'
```

---

### MAC — Таблица MAC-адресов

| Метод | Endpoint | Описание |
|-------|----------|----------|
| POST | `/api/mac/collect` | Собрать MAC-таблицу |

**Запрос:**
```bash
curl -X POST http://localhost:8080/api/mac/collect \
  -H "Content-Type: application/json" \
  -H "X-SSH-Username: admin" \
  -H "X-SSH-Password: secret" \
  -d '{
    "devices": [{"host": "192.168.1.1", "platform": "cisco_ios"}],
    "exclude_trunks": true
  }'
```

---

### LLDP/CDP — Соседи

| Метод | Endpoint | Описание |
|-------|----------|----------|
| POST | `/api/lldp/collect` | Собрать LLDP/CDP соседей |

**Запрос:**
```bash
curl -X POST http://localhost:8080/api/lldp/collect \
  -H "Content-Type: application/json" \
  -H "X-SSH-Username: admin" \
  -H "X-SSH-Password: secret" \
  -d '{
    "devices": [{"host": "192.168.1.1", "platform": "cisco_ios"}],
    "protocol": "both"
  }'
```

**Параметры:**
- `protocol`: `lldp`, `cdp`, `both` (по умолчанию `both`)

---

### Interfaces — Интерфейсы

| Метод | Endpoint | Описание |
|-------|----------|----------|
| POST | `/api/interfaces/collect` | Собрать информацию об интерфейсах |

**Запрос:**
```bash
curl -X POST http://localhost:8080/api/interfaces/collect \
  -H "Content-Type: application/json" \
  -H "X-SSH-Username: admin" \
  -H "X-SSH-Password: secret" \
  -d '{
    "devices": [{"host": "192.168.1.1", "platform": "cisco_ios"}]
  }'
```

---

### Inventory — Модули/SFP

| Метод | Endpoint | Описание |
|-------|----------|----------|
| POST | `/api/inventory/collect` | Собрать инвентарь |

---

### Backup — Резервное копирование

| Метод | Endpoint | Описание |
|-------|----------|----------|
| POST | `/api/backup/run` | Создать backup конфигураций |

**Запрос:**
```bash
curl -X POST http://localhost:8080/api/backup/run \
  -H "Content-Type: application/json" \
  -H "X-SSH-Username: admin" \
  -H "X-SSH-Password: secret" \
  -d '{
    "devices": [{"host": "192.168.1.1", "platform": "cisco_ios"}],
    "config_type": "running"
  }'
```

**Параметры:**
- `config_type`: `running` (по умолчанию), `startup`

---

### Sync NetBox — Синхронизация

| Метод | Endpoint | Описание |
|-------|----------|----------|
| POST | `/api/sync/netbox` | Синхронизировать с NetBox |
| POST | `/api/sync/netbox/diff` | Показать diff без применения |

**Запрос:**
```bash
curl -X POST http://localhost:8080/api/sync/netbox \
  -H "Content-Type: application/json" \
  -H "X-SSH-Username: admin" \
  -H "X-SSH-Password: secret" \
  -H "X-NetBox-URL: http://netbox:8000" \
  -H "X-NetBox-Token: abc123" \
  -d '{
    "devices": [{"host": "192.168.1.1", "platform": "cisco_ios"}],
    "sync_all": true,
    "site": "Office",
    "dry_run": true
  }'
```

**Параметры:**
- `sync_all`: синхронизировать всё
- `create_devices`: создавать устройства
- `update_devices`: обновлять устройства
- `interfaces`: синхронизировать интерфейсы
- `ip_addresses`: синхронизировать IP
- `cables`: создавать кабели из LLDP/CDP
- `inventory`: синхронизировать модули
- `dry_run`: режим предпросмотра (по умолчанию `true`)
- `site`: фильтр по сайту NetBox

---

### Match — Сопоставление MAC

| Метод | Endpoint | Описание |
|-------|----------|----------|
| POST | `/api/match/mac` | Сопоставить MAC с хостами |

**Запрос:**
```bash
curl -X POST http://localhost:8080/api/match/mac \
  -H "Content-Type: application/json" \
  -d '{
    "mac_file": "output/mac_table.xlsx",
    "hosts_file": "hosts.xlsx"
  }'
```

---

### Push Descriptions — Применение описаний

| Метод | Endpoint | Описание |
|-------|----------|----------|
| POST | `/api/push/descriptions` | Применить описания на устройства |

**Запрос:**
```bash
curl -X POST http://localhost:8080/api/push/descriptions \
  -H "Content-Type: application/json" \
  -H "X-SSH-Username: admin" \
  -H "X-SSH-Password: secret" \
  -d '{
    "matches_file": "output/matched.xlsx",
    "dry_run": true
  }'
```

---

### Device Management — Управление устройствами

| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/api/device-management/` | Список устройств |
| GET | `/api/device-management/stats` | Статистика |
| GET | `/api/device-management/types` | Типы устройств |
| GET | `/api/device-management/roles` | Роли устройств |
| GET | `/api/device-management/hosts/list` | Список IP для сбора |
| GET | `/api/device-management/{id}` | Получить устройство |
| POST | `/api/device-management/` | Создать устройство |
| PUT | `/api/device-management/{id}` | Обновить устройство |
| DELETE | `/api/device-management/{id}` | Удалить устройство |
| POST | `/api/device-management/{id}/toggle` | Включить/выключить |
| POST | `/api/device-management/bulk` | Массовый импорт |
| POST | `/api/device-management/migrate` | Миграция из devices_ips.py |
| POST | `/api/device-management/import-from-netbox` | Импорт из NetBox |

#### Создание устройства

```bash
curl -X POST http://localhost:8080/api/device-management/ \
  -H "Content-Type: application/json" \
  -d '{
    "host": "192.168.1.100",
    "device_type": "cisco_ios",
    "name": "switch-01",
    "site": "Office",
    "role": "switch",
    "enabled": true
  }'
```

#### Импорт из NetBox

```bash
curl -X POST http://localhost:8080/api/device-management/import-from-netbox \
  -H "Content-Type: application/json" \
  -d '{
    "netbox_url": "http://netbox:8000",
    "netbox_token": "abc123",
    "site": "Office",
    "status": "active",
    "replace": false
  }'
```

**Параметры:**
- `netbox_url`: URL NetBox API (обязательно)
- `netbox_token`: API токен (обязательно)
- `site`: фильтр по сайту
- `role`: фильтр по роли
- `status`: фильтр по статусу (`active` по умолчанию)
- `replace`: заменить все существующие устройства

**Ответ:**
```json
{
  "success": true,
  "fetched": 10,
  "added": 8,
  "skipped": 2,
  "errors": 0,
  "message": "Successfully imported 8 devices from NetBox"
}
```

**Маппинг платформ NetBox → Scrapli:**

| NetBox Platform | Scrapli Platform |
|-----------------|------------------|
| cisco-ios | cisco_ios |
| cisco-ios-xe | cisco_ios |
| cisco-nxos | cisco_nxos |
| cisco-iosxr | cisco_iosxr |
| arista-eos | arista_eos |
| juniper-junos | juniper_junos |
| qtech | cisco_ios |

---

### Pipelines — Конвейеры

| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/api/pipelines` | Список pipelines |
| GET | `/api/pipelines/{id}` | Получить pipeline |
| POST | `/api/pipelines` | Создать pipeline |
| PUT | `/api/pipelines/{id}` | Обновить pipeline |
| DELETE | `/api/pipelines/{id}` | Удалить pipeline |
| POST | `/api/pipelines/{id}/validate` | Валидировать |
| POST | `/api/pipelines/{id}/run` | Запустить |

#### Создание pipeline

```bash
curl -X POST http://localhost:8080/api/pipelines \
  -H "Content-Type: application/json" \
  -d '{
    "name": "full_sync",
    "description": "Полная синхронизация",
    "steps": [
      {"id": "collect_devices", "type": "collect", "target": "devices"},
      {"id": "sync_devices", "type": "sync", "target": "devices", "depends_on": ["collect_devices"]},
      {"id": "collect_interfaces", "type": "collect", "target": "interfaces", "depends_on": ["sync_devices"]},
      {"id": "sync_interfaces", "type": "sync", "target": "interfaces", "depends_on": ["collect_interfaces"]}
    ]
  }'
```

#### Запуск pipeline

```bash
curl -X POST http://localhost:8080/api/pipelines/full_sync/run \
  -H "Content-Type: application/json" \
  -H "X-SSH-Username: admin" \
  -H "X-SSH-Password: secret" \
  -H "X-NetBox-URL: http://netbox:8000" \
  -H "X-NetBox-Token: abc123" \
  -d '{
    "devices": [{"host": "192.168.1.1", "platform": "cisco_ios"}],
    "dry_run": true
  }'
```

---

### History — История операций

| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/api/history/` | История операций (с пагинацией и фильтрами) |
| GET | `/api/history/stats` | Статистика (всего, за 24ч, по статусам) |
| DELETE | `/api/history/` | Очистить всю историю |

**Параметры GET `/api/history/`:**
- `limit` — количество записей (по умолчанию 50)
- `offset` — смещение для пагинации
- `operation` — фильтр: `devices`, `mac`, `lldp`, `sync`, `pipeline:default`
- `status` — фильтр: `success`, `error`, `partial`

**Пример запроса:**
```bash
curl "http://localhost:8080/api/history/?limit=10&operation=sync&status=success"
```

**Пример ответа:**
```json
{
  "entries": [
    {
      "id": "abc123",
      "operation": "sync",
      "status": "success",
      "timestamp": "2025-01-18T22:30:00",
      "devices": ["10.0.0.1", "10.0.0.2"],
      "device_count": 2,
      "duration_ms": 5430,
      "stats": {
        "devices": {"created": 0, "updated": 2, "skipped": 0},
        "interfaces": {"created": 15, "updated": 3, "deleted": 0}
      },
      "details": [
        {"entity_type": "interface", "entity_name": "Gi0/1", "action": "create", "device": "switch-01"},
        {"entity_type": "ip_address", "entity_name": "10.0.0.1/24", "action": "create", "device": "switch-01"}
      ]
    }
  ],
  "total": 156
}
```

**Детали (details):**

Для **sync** операций `details` содержит полный diff:
```json
{
  "entity_type": "interface",  // interface, ip_address, cable, device, inventory
  "entity_name": "Gi0/1",
  "action": "create",          // create, update, delete
  "device": "switch-01",
  "field": "description",      // для update — какое поле изменилось
  "old_value": "",
  "new_value": "Server-01"
}
```

Для **pipeline** операций `stats` содержит детали по каждому шагу:
```json
{
  "sync_interfaces": {
    "created": 15,
    "updated": 3,
    "skipped": 10,
    "details": {
      "create": [{"name": "Gi0/1", "device": "switch-01"}],
      "update": [{"name": "Gi0/2", "device": "switch-01", "changes": {"description": "new"}}]
    }
  }
}
```

**Хранение:**
- Файл: `data/history.json`
- Максимум: 1000 записей (старые удаляются автоматически)
- Записывается только для реальных операций (не dry-run)

---

### Tasks — Отслеживание прогресса

| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/api/tasks` | Список последних задач |
| GET | `/api/tasks/{id}` | Статус задачи по ID |
| DELETE | `/api/tasks/{id}` | Отмена задачи |

Каждый endpoint сбора данных возвращает `task_id` в ответе. Frontend использует этот ID для polling статуса.

**Пример ответа `/api/tasks/{id}`:**
```json
{
  "id": "abc12345",
  "type": "collect_devices",
  "status": "running",
  "current_step": 1,
  "total_steps": 1,
  "current_item": 3,
  "total_items": 10,
  "current_item_name": "10.0.0.3",
  "message": "Сбор информации с 10 устройств",
  "progress_percent": 30,
  "elapsed_ms": 5432,
  "steps": [],
  "created_at": "2025-01-17T10:30:00",
  "started_at": "2025-01-17T10:30:01"
}
```

**Статусы задачи:**
- `pending` - ожидание запуска
- `running` - выполняется
- `completed` - успешно завершена
- `failed` - ошибка
- `cancelled` - отменена

**Пример использования (JavaScript):**
```javascript
// Запускаем сбор
const response = await axios.post('/api/devices/collect', { devices: [] });
const taskId = response.data.task_id;

// Polling статуса каждые 500ms
const pollInterval = setInterval(async () => {
  const status = await axios.get(`/api/tasks/${taskId}`);

  updateProgressBar(status.data.progress_percent);

  if (status.data.status === 'completed' || status.data.status === 'failed') {
    clearInterval(pollInterval);
  }
}, 500);
```

---

## Async Mode — Режим реального прогресса

По умолчанию API endpoints работают синхронно: запрос блокируется до завершения сбора данных. Для отображения **real-time прогресса** используйте параметр `async_mode: true`.

### Как это работает

1. **Sync Mode (по умолчанию):**
   - Запрос блокируется
   - Ответ приходит когда всё готово
   - `task_id` в ответе указывает на уже завершённую задачу

2. **Async Mode:**
   - Запрос возвращается **сразу** с `task_id`
   - Сбор выполняется в фоновом потоке
   - Клиент поллит `/api/tasks/{id}` для получения прогресса
   - Результаты доступны в `task.result.data` после завершения

### Пример использования

**Запрос (async mode):**
```bash
curl -X POST http://localhost:8080/api/devices/collect \
  -H "Content-Type: application/json" \
  -H "X-SSH-Username: admin" \
  -H "X-SSH-Password: secret" \
  -d '{
    "devices": [],
    "async_mode": true
  }'
```

**Немедленный ответ:**
```json
{
  "success": true,
  "devices": [],
  "task_id": "abc12345"
}
```

**Polling прогресса:**
```javascript
// 1. Отправляем запрос с async_mode
const response = await axios.post('/api/devices/collect', {
  devices: [],
  async_mode: true
});
const taskId = response.data.task_id;

// 2. Начинаем polling каждые 500ms
const poll = setInterval(async () => {
  const status = await axios.get(`/api/tasks/${taskId}`);
  const task = status.data;

  // Обновляем progress bar
  console.log(`${task.progress_percent}% - ${task.message}`);
  // Пример: "30% - Обработка 10.0.0.3 (3/10)"

  if (task.status === 'completed') {
    clearInterval(poll);
    // Результаты в task.result.data
    console.log('Results:', task.result.data);
  } else if (task.status === 'failed') {
    clearInterval(poll);
    console.error('Error:', task.error);
  }
}, 500);
```

### Поддерживаемые endpoints

| Endpoint | Параметр |
|----------|----------|
| POST `/api/devices/collect` | `async_mode: true` |
| POST `/api/mac/collect` | `async_mode: true` |
| POST `/api/lldp/collect` | `async_mode: true` |
| POST `/api/interfaces/collect` | `async_mode: true` |
| POST `/api/inventory/collect` | `async_mode: true` |
| POST `/api/backup/run` | `async_mode: true` |

### Результаты в async mode

После завершения задачи (`status: completed`), данные доступны в `task.result`:

```json
{
  "id": "abc12345",
  "status": "completed",
  "result": {
    "total": 10,
    "data": [
      {"hostname": "switch-01", "device_ip": "10.0.0.1", ...},
      {"hostname": "switch-02", "device_ip": "10.0.0.2", ...}
    ]
  },
  "message": "Завершено: 10 записей"
}
```

### Когда использовать async_mode

| Сценарий | Рекомендация |
|----------|--------------|
| Web UI с progress bar | `async_mode: true` |
| API клиенты, скрипты | `async_mode: false` (по умолчанию) |
| Много устройств (10+) | `async_mode: true` |
| Быстрые операции (1-3 устройства) | `async_mode: false` |

---

## Коды ошибок

| Код | Описание |
|-----|----------|
| 200 | OK |
| 201 | Created |
| 204 | No Content (успешное удаление) |
| 400 | Bad Request (невалидные данные) |
| 401 | Unauthorized (нет credentials) |
| 404 | Not Found |
| 409 | Conflict (дубликат) |
| 422 | Validation Error |
| 500 | Internal Server Error |

---

## Примеры использования

### Python (requests)

```python
import requests

BASE_URL = "http://localhost:8080"
HEADERS = {
    "Content-Type": "application/json",
    "X-SSH-Username": "admin",
    "X-SSH-Password": "secret",
}

# Сбор устройств
response = requests.post(
    f"{BASE_URL}/api/devices/collect",
    headers=HEADERS,
    json={
        "devices": [
            {"host": "192.168.1.1", "platform": "cisco_ios"},
        ]
    },
)
print(response.json())
```

### JavaScript (axios)

```javascript
import axios from 'axios';

const api = axios.create({
  baseURL: 'http://localhost:8080',
  headers: {
    'X-SSH-Username': 'admin',
    'X-SSH-Password': 'secret',
  },
});

// Сбор устройств
const response = await api.post('/api/devices/collect', {
  devices: [
    { host: '192.168.1.1', platform: 'cisco_ios' },
  ],
});
console.log(response.data);
```

---

## Web UI — Страницы

| Страница | URL | Описание |
|----------|-----|----------|
| Home | `/` | Главная страница |
| Credentials | `/credentials` | Настройка SSH и NetBox credentials |
| Device Management | `/device-management` | CRUD устройств, импорт из NetBox |
| Devices | `/devices` | Сбор информации об устройствах |
| MAC Table | `/mac` | Сбор MAC-адресов |
| LLDP/CDP | `/lldp` | Сбор соседей |
| Interfaces | `/interfaces` | Сбор интерфейсов |
| Inventory | `/inventory` | Сбор модулей/SFP |
| Backup | `/backup` | Резервное копирование конфигураций |
| Sync NetBox | `/sync` | Синхронизация с NetBox |
| Pipelines | `/pipelines` | Управление и запуск pipelines |
| **History** | `/history` | **Журнал операций** |

### Страница History (Журнал)

Показывает историю всех операций с **полными деталями**:

**Функции:**
- **Статистика:** всего операций, за 24 часа, успешных, ошибок
- **Фильтры:** по типу операции (включая pipeline), по статусу
- **Пагинация:** навигация по истории
- **Очистка:** удаление всей истории

**Детали операций:**

| Тип | Что показывается |
|-----|------------------|
| **Sync** | Полный diff: все create/update/delete с указанием устройства |
| **Pipeline** | Статистика по каждому шагу + детали изменений |
| **Collect** | Количество записей, список устройств |

**Особенности:**
- **Без лимитов:** показываются ВСЕ изменения, не только первые N
- **IP с PRIMARY:** IP адреса помечаются `[PRIMARY]` если это primary IP устройства
- **Изменённые поля:** для update показывается какие поля изменились

**Пример отображения sync:**
```
Изменения (26):
  [create] interface Gi0/10 @ switch-01
  [create] ip_address 10.0.0.1/24 (Vlan10) [PRIMARY] @ switch-01
  [update] interface Gi0/1 description @ switch-02
```

**Пример отображения pipeline:**
```
sync_interfaces: +15 ~3 =10
  Создано: Gi0/1, Gi0/2, Gi0/3...
  Обновлено: Gi0/5 [description, enabled]

sync_ip_addresses: +5 ~0 =20
  Создано: 10.0.0.1/24 (Vlan10) [PRIMARY]
```

---

## Связанная документация

- [MANUAL.md](MANUAL.md) — Полное руководство
- [ARCHITECTURE.md](ARCHITECTURE.md) — Архитектура проекта
- [DEVELOPMENT.md](DEVELOPMENT.md) — Разработка
- [TODO.md](TODO.md) — План развития
