# 08. Web-интерфейс -- FastAPI backend и Vue.js frontend

> **Время чтения:** ~30 минут
>
> **Предыдущий документ:** [07. Pipeline -- автоматизация](07_PIPELINE.md)
>
> **Связанная документация:** [WEB_API.md](../WEB_API.md) -- полная документация REST API

---

До этого момента мы работали с Network Collector через командную строку (CLI).
Но есть и второй способ -- **веб-интерфейс**. Он позволяет делать всё то же самое,
но через браузер: нажимать кнопки, видеть прогресс-бар, просматривать историю операций.

В этом документе разберём, как устроено веб-приложение: что такое backend и frontend,
как они общаются, и как всё это работает вместе.

---

## 1. Что такое веб-приложение

### Аналогия с рестораном

Представь ресторан:

```
Ты (клиент)          Официант          Кухня            Меню
──────────           ────────          ─────            ────
Сидишь за            Принимает         Готовит           Список
столиком,            заказ,            еду,              всех блюд,
смотришь             передаёт          отдаёт            которые
меню,                на кухню,         результат         можно
делаешь              приносит                            заказать
заказ                результат
```

В веб-приложении всё устроено так же:

| Ресторан | Веб-приложение | В нашем проекте |
|----------|----------------|-----------------|
| Ты (клиент) | Браузер | Chrome, Firefox |
| Меню | Frontend (интерфейс) | Vue.js -- красивые страницы с кнопками |
| Официант | HTTP-запросы | `fetch` / `axios` -- отправка запросов |
| Кухня | Backend (сервер) | FastAPI -- обрабатывает запросы, выполняет логику |
| Список блюд | API документация | Swagger UI на `/docs` |

### Клиент-серверная архитектура

```
┌──────────────────────┐         HTTP          ┌──────────────────────┐
│      БРАУЗЕР         │  ─────────────────►   │       СЕРВЕР         │
│   (Frontend)         │  ◄─────────────────   │     (Backend)        │
│                      │     запрос/ответ      │                      │
│  - Показывает кнопки │                       │  - Подключается к    │
│  - Рисует таблицы    │                       │    сетевому железу   │
│  - Отправляет формы  │                       │  - Общается с NetBox │
│                      │                       │  - Возвращает данные │
└──────────────────────┘                       └──────────────────────┘
     Vue.js (порт 5173)                          FastAPI (порт 8080)
```

**Frontend** (фронтенд) -- это то, что видит пользователь в браузере.
Кнопки, формы, таблицы, прогресс-бары. Написан на JavaScript (Vue.js).

**Backend** (бэкенд) -- это серверная часть, которая выполняет реальную работу.
Подключается к коммутаторам по SSH, общается с NetBox через API.
Написан на Python (FastAPI).

**HTTP** -- протокол общения между ними. Frontend отправляет запрос
("хочу собрать данные с таких-то устройств"), backend выполняет работу
и возвращает результат ("вот данные с 10 коммутаторов").

---

## 2. FastAPI backend

### Что такое FastAPI

**FastAPI** -- это Python-фреймворк для создания web API. Слово "Fast" в названии
не случайное -- он действительно быстрый и при этом очень простой в использовании.

Почему выбрали FastAPI:

| Причина | Объяснение |
|---------|------------|
| Простой синтаксис | Один декоратор `@app.get()` -- и endpoint готов |
| Автодокументация | Автоматически генерирует Swagger UI на `/docs` |
| Валидация | Pydantic-модели проверяют входные данные за тебя |
| Async поддержка | Умеет работать асинхронно (нужно для прогресс-бара) |
| Python | Мы и так пишем на Python -- не надо учить новый язык |

### Точка входа -- main.py

Всё начинается с файла `api/main.py`. Вот его упрощённая структура:

```python
# api/main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Создаём приложение
app = FastAPI(
    title="Network Collector API",
    description="REST API для сбора данных и синхронизации с NetBox",
    version="0.1.0",
    docs_url="/docs",       # Swagger UI будет тут
)

# Разрешаем запросы с фронтенда (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],    # Из любого источника
    allow_methods=["*"],    # Любые HTTP-методы
    allow_headers=["*"],    # Любые заголовки
)

# Простейший endpoint -- проверка здоровья
@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "0.1.0"}

# Подключаем роутеры (группы endpoints)
app.include_router(devices_router, prefix="/api/devices")
app.include_router(sync_router,    prefix="/api/sync")
app.include_router(pipelines_router, prefix="/api/pipelines")
app.include_router(history_router, prefix="/api/history")
# ... и другие
```

Что тут происходит:
1. `FastAPI()` -- создаёт приложение, аналогично `argparse.ArgumentParser()` в CLI
2. `CORSMiddleware` -- разрешает фронтенду (порт 5173) общаться с бэкендом (порт 8080)
3. `@app.get("/health")` -- определяет endpoint (URL, на который можно послать запрос)
4. `include_router()` -- подключает группы endpoints из отдельных файлов

**Что такое CORS?** Браузер по умолчанию запрещает странице с одного адреса
(localhost:5173) обращаться к другому адресу (localhost:8080). CORS-middleware
разрешает это, добавляя специальные заголовки в ответы сервера.

### Routes (маршруты) -- как обрабатываются запросы

Роутеры -- это файлы в `api/routes/`, каждый отвечает за свою группу операций.
Аналогия: в CLI есть команды (`devices`, `mac`, `sync-netbox`), а в API --
endpoints (`/api/devices`, `/api/mac`, `/api/sync`).

```
CLI                                 Web API
───                                 ───────
python -m network_collector devices  →  POST /api/devices/collect
python -m network_collector mac      →  POST /api/mac/collect
python -m network_collector sync-netbox  →  POST /api/sync/netbox
python -m network_collector pipeline run  →  POST /api/pipelines/{id}/run
```

Вот пример route для сбора устройств:

```python
# api/routes/devices.py

from fastapi import APIRouter, Request
from ..services.collector_service import CollectorService

router = APIRouter()

@router.post("/collect", response_model=DevicesResponse)
async def collect_devices(request: Request, body: DevicesRequest):
    """Собирает информацию об устройствах (show version)."""

    # 1. Извлекаем SSH credentials из заголовков запроса
    credentials = get_credentials_from_headers(request)

    # 2. Создаём сервис
    service = CollectorService(credentials)

    # 3. Выполняем сбор и возвращаем результат
    return await service.collect_devices(body)
```

Разберём построчно:

- `@router.post("/collect")` -- этот endpoint принимает POST-запросы на `/collect`
- `body: DevicesRequest` -- FastAPI автоматически парсит JSON из тела запроса
  в Pydantic-модель `DevicesRequest` (проверяет типы, обязательные поля и т.д.)
- `get_credentials_from_headers(request)` -- извлекает логин/пароль из HTTP-заголовков
- `CollectorService` -- сервисный класс, который делает реальную работу
- `return` -- FastAPI автоматически конвертирует результат в JSON

### Откуда берутся credentials

Логин и пароль для SSH передаются через HTTP-заголовки (headers) в каждом запросе.
Сервер **не хранит** пароли -- они живут только в браузере.

```python
# api/routes/auth.py

def get_credentials_from_headers(request: Request) -> Credentials:
    """Извлекает SSH credentials из HTTP headers."""
    username = request.headers.get("X-SSH-Username")
    password = request.headers.get("X-SSH-Password")

    if not username or not password:
        raise HTTPException(
            status_code=401,
            detail="SSH credentials required",
        )

    return Credentials(username=username, password=password)
```

Это похоже на то, как в ресторане ты показываешь членскую карту при каждом заказе.
Ресторан не хранит копию карты -- просто проверяет при каждом визите.

### Services (сервисы) -- бизнес-логика

Routes -- это "дверь" в API. Они принимают запрос и отдают ответ.
Но реальная работа выполняется в **сервисах** (`api/services/`).

```
Запрос от браузера
     │
     ▼
api/routes/sync.py          ← "дверь" -- принимает запрос, проверяет credentials
     │
     ▼
api/services/sync_service.py  ← "кухня" -- выполняет синхронизацию
     │
     ▼
netbox/sync/                   ← "повара" -- непосредственно работают с NetBox API
collectors/                    ← "поставщики" -- собирают данные с устройств
```

Пример цепочки для синхронизации:

```python
# api/routes/sync.py  (Route -- принимает запрос)
@router.post("/netbox")
async def sync_netbox(request: Request, body: SyncRequest):
    credentials = get_credentials_from_headers(request)
    netbox = get_netbox_config_from_headers(request)
    service = SyncService(credentials, netbox)     # Создаём сервис
    return await service.sync(body)                 # Вызываем метод сервиса

# api/services/sync_service.py  (Service -- выполняет работу)
class SyncService:
    async def sync(self, request: SyncRequest) -> SyncResponse:
        devices = self._get_devices(request.devices)    # Список устройств
        steps = self._calculate_steps(request)           # Что синхронизировать

        # Создаём NetBox клиент и sync
        client = NetBoxClient(url=self.netbox_url, token=self.netbox_token)
        sync = NetBoxSync(client, dry_run=request.dry_run)

        # Выполняем синхронизацию...
        result = sync.sync_interfaces(hostname, interfaces)
        return SyncResponse(success=True, ...)
```

### Файлы сервисов

| Файл | Описание |
|------|----------|
| `api/services/collector_service.py` | Сбор данных (devices, mac, lldp, interfaces) |
| `api/services/sync_service.py` | Синхронизация с NetBox |
| `api/services/task_manager.py` | Отслеживание прогресса задач |
| `api/services/history_service.py` | Запись истории операций в `data/history.json` |
| `api/services/device_service.py` | CRUD для списка устройств |
| `api/services/match_service.py` | Сопоставление MAC-адресов с хостами |
| `api/services/push_service.py` | Push описаний на устройства |

### Async mode -- зачем нужен и как работает прогресс

Представь: ты запускаешь синхронизацию 50 коммутаторов. Это занимает 5 минут.
Без async mode браузер будет просто ждать 5 минут, показывая "Loading...".
Ты даже не знаешь -- работает ли что-то или всё зависло.

С **async mode** всё работает иначе:

```
БЕЗ async mode (плохо):
────────────────────────────────────────────────────────────
Браузер  ──POST──►  Backend  ──────работа 5 минут──────►  ◄──ответ──  Браузер
                                                              (ждёт 5 минут,
                                                               ничего не видит)


С async mode (хорошо):
────────────────────────────────────────────────────────────
Браузер  ──POST──►  Backend
                       │
                       ├─► создаёт Task (задачу)
                       └─► возвращает task_id (за 0.1 сек)

Браузер  ◄─task_id─┘

Браузер  ──GET /tasks/{id}──►  Backend ──► {status: "running",  progress: 10%}
Браузер  ──GET /tasks/{id}──►  Backend ──► {status: "running",  progress: 45%}
Браузер  ──GET /tasks/{id}──►  Backend ──► {status: "running",  progress: 80%}
Браузер  ──GET /tasks/{id}──►  Backend ──► {status: "completed", result: {...}}
```

Ключевая идея: backend **сразу** возвращает ответ с `task_id`, а реальная работа
продолжается в фоновом потоке. Фронтенд каждые 500мс спрашивает "как дела?"
(это называется **polling**) и обновляет прогресс-бар.

#### TaskManager -- менеджер задач

Класс `TaskManager` хранит все задачи в памяти. Каждая задача (`Task`) содержит:

```python
# api/services/task_manager.py

@dataclass
class Task:
    id: str                    # Уникальный ID ("a1b2c3d4")
    type: str                  # Тип: "sync", "collect", "pipeline"
    status: TaskStatus         # pending → running → completed / failed

    current_step: int          # Текущий шаг (0, 1, 2, ...)
    total_steps: int           # Всего шагов

    current_item: int          # Текущее устройство (3 из 10)
    total_items: int           # Всего устройств

    message: str               # "Обработка 10.0.0.3 (3/10)"
    result: Optional[Dict]     # Результат после завершения
```

Пример жизненного цикла задачи:

```python
# 1. Создаём задачу
task = task_manager.create_task(
    task_type="sync",
    total_steps=3,             # collect → sync_interfaces → sync_cables
    total_items=10,            # 10 устройств
)
# task.id = "a1b2c3d4", task.status = "pending"

# 2. Запускаем
task_manager.start_task(task.id, "Начинаем синхронизацию")
# task.status = "running"

# 3. В процессе работы обновляем прогресс
task_manager.update_task(task.id, current_step=1, message="Сбор интерфейсов...")
task_manager.update_item(task.id, current=5, name="10.0.0.5")
# task.message = "Обработка 10.0.0.5 (5/10)", task.progress_percent = 45

# 4. Завершаем
task_manager.complete_task(task.id, result={"created": 15, "updated": 3})
# task.status = "completed"
```

Каждый раз когда фронтенд делает `GET /api/tasks/{id}`, backend возвращает
текущее состояние задачи -- и фронтенд обновляет прогресс-бар.

---

## 3. Vue.js frontend (кратко)

### Что такое Vue.js

**Vue.js** -- это JavaScript-фреймворк для создания пользовательских интерфейсов
в браузере. Он позволяет создавать **SPA** (Single Page Application) --
одностраничное приложение.

**Что такое SPA?** Обычный сайт -- это набор HTML-страниц: ты нажимаешь ссылку,
браузер загружает новую страницу целиком. В SPA страница загружается **один раз**,
а дальше меняется только содержимое. Ты нажимаешь на "Sync" в меню --
и страница мгновенно меняется без перезагрузки (как в Gmail или Telegram Web).

### Основные страницы

| Страница | URL | Файл | Что делает |
|----------|-----|------|------------|
| Dashboard | `/` | `Home.vue` | Обзор: статус API, статистика, кол-во устройств |
| Credentials | `/credentials` | `Credentials.vue` | Ввод SSH логина/пароля и NetBox токена |
| Device Management | `/device-management` | `DeviceManagement.vue` | Управление списком устройств (CRUD) |
| Devices | `/devices` | `Devices.vue` | Сбор show version |
| MAC | `/mac` | `Mac.vue` | Сбор MAC-таблицы |
| LLDP/CDP | `/lldp` | `Lldp.vue` | Сбор соседей |
| Interfaces | `/interfaces` | `Interfaces.vue` | Сбор интерфейсов |
| Inventory | `/inventory` | `Inventory.vue` | Сбор модулей/SFP |
| Backup | `/backup` | `Backup.vue` | Бэкап конфигураций |
| **Sync** | `/sync` | `Sync.vue` | Синхронизация с NetBox |
| **Pipelines** | `/pipelines` | `Pipelines.vue` | Управление и запуск pipeline |
| **History** | `/history` | `History.vue` | Журнал операций |

### Как frontend общается с backend

Фронтенд использует библиотеку **axios** для отправки HTTP-запросов.
Это аналог `requests` в Python, только для JavaScript.

```javascript
// Python (requests)                    // JavaScript (axios)
import requests                         import axios

response = requests.post(               const response = await axios.post(
    "http://localhost:8080/api/sync",       "/api/sync/netbox",
    json={"dry_run": True},                 { dry_run: true },
    headers={"X-SSH-Username": "admin"}   )
)
data = response.json()                  const data = response.data
```

Важная деталь -- **axios interceptor**. Это функция, которая автоматически
добавляет credentials в каждый запрос:

```javascript
// frontend/src/main.js
// Interceptor -- выполняется ПЕРЕД каждым запросом
axios.interceptors.request.use((config) => {
    // Берём credentials из хранилища браузера
    const username = sessionStorage.getItem('ssh_username')
    const password = sessionStorage.getItem('ssh_password')

    // Добавляем в заголовки
    if (username) config.headers['X-SSH-Username'] = username
    if (password) config.headers['X-SSH-Password'] = password

    return config
})
```

Это значит, что разработчику не надо вручную добавлять credentials
в каждый запрос -- interceptor делает это автоматически.

### Пример: что происходит при нажатии "Sync"

Полная цепочка от клика мышкой до результата на экране:

```
1. Пользователь нажимает кнопку "Preview Changes"
   │
2. Vue.js собирает данные из формы (какие устройства, что синхронизировать)
   │
3. axios отправляет POST /api/sync/netbox с async_mode: true
   │   (interceptor автоматически добавляет SSH логин/пароль в headers)
   │
4. Vite dev server проксирует запрос: localhost:5173 → localhost:8080
   │
5. FastAPI route (api/routes/sync.py) принимает запрос
   │   - извлекает credentials из headers
   │   - создаёт SyncService
   │
6. SyncService создаёт Task в TaskManager и запускает фоновый поток
   │   - возвращает task_id браузеру (за 0.1 сек)
   │
7. ProgressBar.vue начинает polling: GET /api/tasks/{task_id} каждые 500мс
   │   - обновляет прогресс-бар (10%... 45%... 80%...)
   │
8. Когда status = "completed" -- polling останавливается
   │   - result содержит статистику: created=15, updated=3
   │
9. Результат отображается в таблице на странице
```

---

## 4. REST API

### Что такое REST

**REST** (Representational State Transfer) -- это набор правил, по которым
клиент и сервер общаются через HTTP.

Четыре основных HTTP-метода:

| Метод | Назначение | Аналогия | Пример |
|-------|------------|----------|--------|
| **GET** | Получить данные | "Покажи мне" | Получить список устройств |
| **POST** | Создать / выполнить | "Сделай" | Запустить сбор данных |
| **PUT** | Обновить | "Измени" | Обновить pipeline |
| **DELETE** | Удалить | "Удали" | Удалить pipeline |

В нашем проекте:

```
GET    /api/pipelines           -- получить список всех pipelines
POST   /api/pipelines           -- создать новый pipeline
GET    /api/pipelines/default   -- получить конкретный pipeline
PUT    /api/pipelines/default   -- обновить pipeline
DELETE /api/pipelines/default   -- удалить pipeline
POST   /api/pipelines/default/run  -- запустить pipeline
```

### Примеры с curl

**curl** -- утилита для отправки HTTP-запросов из терминала.
Полезна для тестирования API без браузера.

#### Проверить что API работает

```bash
curl http://localhost:8080/health
```

Ответ:
```json
{
  "status": "ok",
  "version": "0.1.0",
  "uptime": 123.45
}
```

#### Получить список устройств

```bash
curl http://localhost:8080/api/devices
```

#### Собрать информацию об устройствах

```bash
curl -X POST http://localhost:8080/api/devices/collect \
  -H "Content-Type: application/json" \
  -H "X-SSH-Username: admin" \
  -H "X-SSH-Password: secret" \
  -d '{
    "devices": [
      {"host": "192.168.1.1", "platform": "cisco_ios"}
    ]
  }'
```

Разберём флаги curl:
- `-X POST` -- метод POST (по умолчанию GET)
- `-H "..."` -- добавить HTTP-заголовок
- `-d '{...}'` -- тело запроса (JSON)

#### Запустить синхронизацию (dry-run)

```bash
curl -X POST http://localhost:8080/api/sync/netbox \
  -H "Content-Type: application/json" \
  -H "X-SSH-Username: admin" \
  -H "X-SSH-Password: secret" \
  -H "X-NetBox-URL: http://netbox:8000" \
  -H "X-NetBox-Token: abc123token" \
  -d '{
    "sync_all": true,
    "site": "Office",
    "dry_run": true
  }'
```

#### Получить историю операций

```bash
curl "http://localhost:8080/api/history/?limit=10&operation=sync&status=success"
```

#### Pipeline -- создать и запустить

```bash
# Список pipelines
curl http://localhost:8080/api/pipelines

# Запустить pipeline
curl -X POST http://localhost:8080/api/pipelines/default/run \
  -H "Content-Type: application/json" \
  -H "X-SSH-Username: admin" \
  -H "X-SSH-Password: secret" \
  -H "X-NetBox-URL: http://netbox:8000" \
  -H "X-NetBox-Token: abc123" \
  -d '{"dry_run": true, "async_mode": true}'
```

### Swagger UI -- автодокументация

FastAPI автоматически генерирует интерактивную документацию API.
Открой в браузере:

- **Swagger UI:** http://localhost:8080/docs
- **ReDoc:** http://localhost:8080/redoc

На Swagger UI ты можешь:
- Увидеть все доступные endpoints
- Посмотреть какие параметры принимает каждый endpoint
- Попробовать отправить запрос прямо из браузера (кнопка "Try it out")
- Увидеть формат ответа

Это как "меню ресторана" со всеми блюдами, ценами и описаниями.

### Основные endpoint-ы

| Группа | Endpoint | Метод | Описание |
|--------|----------|-------|----------|
| Health | `/health` | GET | Проверка состояния API |
| Auth | `/api/auth/credentials/status` | GET | Проверить наличие credentials |
| Devices | `/api/devices/collect` | POST | Собрать show version |
| MAC | `/api/mac/collect` | POST | Собрать MAC-таблицу |
| LLDP | `/api/lldp/collect` | POST | Собрать соседей |
| Interfaces | `/api/interfaces/collect` | POST | Собрать интерфейсы |
| Inventory | `/api/inventory/collect` | POST | Собрать модули/SFP |
| Backup | `/api/backup/run` | POST | Бэкап конфигураций |
| Sync | `/api/sync/netbox` | POST | Синхронизация с NetBox |
| Sync | `/api/sync/netbox/diff` | POST | Показать diff без применения |
| Pipelines | `/api/pipelines` | GET | Список pipelines |
| Pipelines | `/api/pipelines/{id}` | GET/PUT/DELETE | CRUD для pipeline |
| Pipelines | `/api/pipelines/{id}/run` | POST | Запустить pipeline |
| History | `/api/history/` | GET | История операций |
| History | `/api/history/stats` | GET | Статистика |
| Tasks | `/api/tasks/{id}` | GET | Статус задачи (для прогресс-бара) |
| Fields | `/api/fields` | GET | Конфигурация полей (fields.yaml) |
| Match | `/api/match` | POST | Сопоставление MAC-адресов с хостами |
| Push | `/api/push` | POST | Push описаний на устройства |
| Device Mgmt | `/api/device-management/` | GET/POST | Управление устройствами |

---

## 5. Как запустить

Для работы веб-интерфейса нужно запустить **два** процесса: backend и frontend.

### Backend (FastAPI)

```bash
# Терминал 1
cd /home/sa/project
source network_collector/myenv/bin/activate
uvicorn network_collector.api.main:app --host 0.0.0.0 --port 8080 --reload
```

Разберём команду:
- `uvicorn` -- ASGI-сервер (запускает FastAPI приложение)
- `network_collector.api.main:app` -- путь к объекту `app` в `api/main.py`
- `--host 0.0.0.0` -- слушать на всех интерфейсах (не только localhost)
- `--port 8080` -- порт для API
- `--reload` -- автоперезагрузка при изменении кода (для разработки)

После запуска:
- API доступен на http://localhost:8080
- Swagger документация: http://localhost:8080/docs

### Frontend (Vue.js)

```bash
# Терминал 2
cd /home/sa/project/network_collector/frontend
npm install    # первый раз -- установить зависимости
npm run dev    # запустить dev-сервер
```

После запуска:
- Web UI доступен на http://localhost:5173
- Запросы `/api/*` автоматически проксируются на backend (порт 8080)

### Проверка работоспособности

```bash
# Проверить что backend запущен
curl http://localhost:8080/health
# Ответ: {"status":"ok","version":"0.1.0","uptime":...}

# Открыть Web UI в браузере
# http://localhost:5173
```

### Порядок запуска

1. **Сначала backend** -- фронтенд будет проксировать запросы на него
2. **Потом frontend** -- он проверит подключение к backend на Dashboard

---

## 6. Ключевые файлы

### Backend (Python / FastAPI)

| Файл | Описание |
|------|----------|
| `api/main.py` | Точка входа: создание `app`, подключение роутеров, CORS |
| `api/routes/__init__.py` | Экспорт всех роутеров |
| `api/routes/sync.py` | Endpoints синхронизации с NetBox |
| `api/routes/devices.py` | Endpoints сбора устройств |
| `api/routes/pipelines.py` | CRUD и запуск pipeline-ов |
| `api/routes/history.py` | История операций |
| `api/routes/tasks.py` | Статус задач (для прогресс-бара) |
| `api/routes/auth.py` | Извлечение credentials из headers |
| `api/routes/device_management.py` | CRUD для списка устройств |
| `api/services/sync_service.py` | Бизнес-логика синхронизации |
| `api/services/collector_service.py` | Бизнес-логика сбора данных |
| `api/services/task_manager.py` | Менеджер задач (прогресс) |
| `api/services/history_service.py` | Сохранение истории в JSON |
| `api/schemas/` | Pydantic-модели (request/response) |

### Frontend (JavaScript / Vue.js)

| Файл | Описание |
|------|----------|
| `frontend/src/main.js` | Точка входа: настройка Vue, роутер, axios interceptor |
| `frontend/src/App.vue` | Главный компонент, навигация |
| `frontend/src/views/Sync.vue` | Страница синхронизации |
| `frontend/src/views/Pipelines.vue` | Страница pipeline-ов |
| `frontend/src/views/History.vue` | Страница истории |
| `frontend/src/views/DeviceManagement.vue` | Управление устройствами |
| `frontend/src/views/Credentials.vue` | Ввод логина/пароля |
| `frontend/src/components/ProgressBar.vue` | Компонент прогресс-бара (polling) |
| `frontend/src/components/DeviceSelector.vue` | Выбор устройств |
| `frontend/vite.config.js` | Proxy: /api/* -> localhost:8080 |

---

## Итоги

Что мы разобрали:

1. **Клиент-серверная архитектура** -- frontend (браузер) и backend (сервер)
   общаются через HTTP-запросы
2. **FastAPI backend** -- обрабатывает запросы, выполняет реальную работу
   (SSH к устройствам, API к NetBox)
3. **Routes** -- "двери" в API, каждый endpoint принимает запрос и вызывает сервис
4. **Services** -- бизнес-логика, аналог CLI-обработчиков команд
5. **Async mode + TaskManager** -- фоновое выполнение с отслеживанием прогресса
6. **Vue.js frontend** -- SPA для работы через браузер
7. **REST API** -- GET/POST/PUT/DELETE для всех операций
8. **Swagger UI** -- автоматическая документация API на /docs

### CLI vs Web API -- сравнение

| Аспект | CLI | Web API |
|--------|-----|---------|
| Запуск | `python -m network_collector` | `uvicorn` + `npm run dev` |
| Ввод | Командная строка | Формы в браузере |
| Credentials | `~/.ssh` или аргументы | HTTP headers |
| Прогресс | Текст в терминале | Прогресс-бар |
| Результат | Файл (Excel/JSON) | JSON в браузере |
| Автоматизация | Shell скрипты, cron | HTTP-запросы, curl |
| Документация | `--help` | Swagger UI `/docs` |

Оба способа (CLI и Web) используют одни и те же сервисы и библиотеки.
Разница только в том, как данные поступают и куда уходит результат.

---

## Серия обучающих документов

Ты прочитал все документы серии. Вот полный список:

| # | Документ | Что ты узнал |
|---|----------|--------------|
| 01 | [Python-концепции](01_PYTHON_BASICS.md) | Comprehensions, dataclass, type hints, mixin, контекстные менеджеры |
| 02 | [Обзор проекта](02_PROJECT_OVERVIEW.md) | Архитектура, слои, структура папок |
| 03 | [CLI изнутри](03_CLI_INTERNALS.md) | argparse, маршрутизация команд, путь запроса |
| 04 | [Сбор данных](04_DATA_COLLECTION.md) | SSH (Scrapli), TextFSM, нормализация, модели |
| 05 | [Синхронизация с NetBox](05_SYNC_NETBOX.md) | Client/Sync слои, batch операции, dry_run |
| 06 | Pipeline -- автоматизация | Цепочки: collect -> sync -> cleanup |
| 07 | CLI и Web API | Команды CLI и REST API |
| **08** | **Web-интерфейс (этот документ)** | **FastAPI, Vue.js, REST API, async mode** |

Теперь ты понимаешь проект от начала до конца: от Python-основ до веб-интерфейса.
Следующий шаг -- открой код и попробуй разобраться в конкретных файлах.
Начни с простого: прочитай `api/routes/history.py` -- он короткий и понятный.
Потом переходи к `api/routes/sync.py` и `api/services/sync_service.py`.

Удачи!
