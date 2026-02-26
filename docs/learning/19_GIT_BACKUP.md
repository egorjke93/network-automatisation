# 19. Резервное копирование конфигов в Git

Бэкап конфигураций устройств — одна из базовых задач сетевого инженера. Network Collector
умеет не просто сохранять конфиги в файлы, а автоматически пушить их в Git-репозиторий
(Gitea, GitLab, GitHub). Это даёт историю изменений, diff между версиями, и ссылки
на конфиг прямо из NetBox.

В этом документе разберём **всю цепочку**: от CLI-команды до HTTP-запроса в Gitea REST API.

**Предварительное чтение:** [03_CLI_INTERNALS.md](03_CLI_INTERNALS.md), [12_INTERNALS_AND_TESTING.md](12_INTERNALS_AND_TESTING.md)

**Время:** ~30 мин

---

## Содержание

1. [Зачем пушить конфиги в Git](#1-зачем-пушить-конфиги-в-git)
2. [Общая схема](#2-общая-схема)
3. [Конфигурация: config.yaml](#3-конфигурация-configyaml)
4. [CLI: аргументы backup](#4-cli-аргументы-backup)
5. [GitBackupPusher — главный класс](#5-gitbackuppusher--главный-класс)
6. [Алгоритм push_file: GET → POST/PUT](#6-алгоритм-push_file-get--postput)
7. [Обнаружение изменений: base64 + strip](#7-обнаружение-изменений-base64--strip)
8. [Группировка по сайтам: site_map](#8-группировка-по-сайтам-site_map)
9. [Обработка ошибок](#9-обработка-ошибок)
10. [SSL и безопасность](#10-ssl-и-безопасность)
11. [Тестирование](#11-тестирование)
12. [Полная диаграмма потока данных](#12-полная-диаграмма-потока-данных)
13. [Связь с официальной документацией](#13-связь-с-официальной-документацией)

---

## 1. Зачем пушить конфиги в Git

Локальные файлы бэкапов — это хорошо, но:

| Проблема | Решение с Git |
|----------|---------------|
| Нет истории изменений | Git хранит каждый коммит, можно посмотреть diff |
| Непонятно кто и когда менял | Каждый коммит = timestamp + автор |
| Файлы лежат на одной машине | Git-сервер — централизованное хранилище |
| Нет связи с NetBox | URL из Gitea можно вставить в custom field устройства |

**Структура в Git-репозитории:**

```
network-backups/          ← Git-репозиторий
├── DC-Moscow/            ← Сайт (из devices_ips.py)
│   ├── switch-core-01/   ← Hostname (из SSH)
│   │   └── running-config.cfg
│   └── switch-access-02/
│       └── running-config.cfg
└── DC-SPB/
    └── router-gw-01/
        └── running-config.cfg
```

---

## 2. Общая схема

```
┌─────────────────────────────────────────────────────────────┐
│                         CLI                                  │
│  python -m network_collector backup --push-git --site DC-1  │
└──────────────┬──────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────┐
│  cmd_backup() — backup.py    │
│  1. Собираем конфиги (SSH)   │
│  2. Сохраняем .cfg файлы     │
│  3. Строим site_map          │
│  4. Вызываем push_backups()  │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│  GitBackupPusher             │
│  (core/git_pusher.py)        │
│                              │
│  push_backups()              │
│  ├── Читаем *.cfg из папки   │
│  └── Для каждого файла:      │
│      push_file(hostname, cfg)│
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│  Gitea REST API v1           │
│                              │
│  GET  /contents/{path}       │
│  ├── 404 → POST (create)     │
│  ├── 200 + changed → PUT     │
│  └── 200 + same → skip       │
└──────────────────────────────┘
```

---

## 3. Конфигурация: config.yaml

Git-бэкапы настраиваются в секции `git` файла `config.yaml`:

```yaml
git:
  # URL Git-сервера (Gitea, GitLab, GitHub)
  url: "https://gitea.example.com"

  # API-токен для аутентификации
  # ВАЖНО: лучше через env: GIT_BACKUP_TOKEN
  token: ""

  # Репозиторий в формате "owner/repo"
  repo: "backup-bot/network-backups"

  # Ветка для коммитов
  branch: "main"

  # SSL: true / false / "/path/to/cert.pem"
  verify_ssl: true

  # Таймаут запросов (секунды)
  timeout: 30
```

### Что здесь происходит

Конфигурация валидируется через Pydantic-модель `GitConfig` в `core/config_schema.py`:

```python
class GitConfig(BaseModel):
    url: str = ""
    token: str = ""
    repo: str = ""
    branch: str = "main"
    verify_ssl: Union[bool, str] = True   # bool или путь к сертификату
    timeout: int = Field(default=30, ge=1, le=300)

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if v and not v.startswith(("http://", "https://")):
            raise PydanticCustomError("invalid_url", "Git URL должен начинаться с http:// или https://")
        return v.rstrip("/") if v else v
```

**Три способа задать токен (приоритет):**

1. Переменная окружения: `export GIT_BACKUP_TOKEN="..."`
2. `config.yaml`: `git.token: "..."`
3. (Не рекомендуется: хардкод в конфиге, попадёт в git)

Переменные окружения загружаются в `config.py → _load_env()`:

```python
def _load_env(self) -> None:
    if os.getenv("GIT_BACKUP_URL"):
        self._data.setdefault("git", {})["url"] = os.getenv("GIT_BACKUP_URL")
    if os.getenv("GIT_BACKUP_TOKEN"):
        self._data.setdefault("git", {})["token"] = os.getenv("GIT_BACKUP_TOKEN")
    if os.getenv("GIT_BACKUP_REPO"):
        self._data.setdefault("git", {})["repo"] = os.getenv("GIT_BACKUP_REPO")
```

---

## 4. CLI: аргументы backup

В `cli/__init__.py` определены флаги для команды `backup`:

```python
backup_parser = subparsers.add_parser("backup", help="Резервное копирование конфигураций")
backup_parser.add_argument("--output", "-o", default="backups")
backup_parser.add_argument("--push-git", action="store_true")   # Собрать + пушить
backup_parser.add_argument("--git-only", action="store_true")   # Только пушить (без SSH)
backup_parser.add_argument("--git-test", action="store_true")   # Проверить подключение
backup_parser.add_argument("--site", default=None)              # Дефолтный сайт
```

**Три режима работы:**

| Флаги | Что делает |
|-------|------------|
| `backup` | Только SSH → сохранить .cfg файлы |
| `backup --push-git` | SSH → .cfg файлы → push в Git |
| `backup --git-only` | Взять готовые .cfg → push в Git (без SSH) |
| `backup --git-test` | Проверить подключение к Git-серверу |

**Флаг `--site`:**

```bash
# Все устройства в сайт "DC-Moscow"
python -m network_collector backup --push-git --site "DC-Moscow"

# Site берётся из devices_ips.py (per-device)
python -m network_collector backup --push-git
```

---

## 5. GitBackupPusher — главный класс

**Файл:** `core/git_pusher.py` (~336 строк)

Это единственный класс, который общается с Git API. Всё общение через `requests.Session`:

```python
class GitBackupPusher:
    def __init__(self, url, token, repo, branch="main", verify_ssl=True, timeout=30):
        self.url = url.rstrip("/")
        self.token = token
        self.repo = repo
        self.branch = branch

        # SSL: True, False, или "/path/to/cert.pem"
        if isinstance(verify_ssl, str) and verify_ssl.lower() in ("true", "false"):
            self.verify_ssl = verify_ssl.lower() == "true"
        else:
            self.verify_ssl = verify_ssl

        # HTTP-сессия с авторизацией
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"token {self.token}",
            "Content-Type": "application/json",
        })
        self._session.verify = self.verify_ssl
```

### Что здесь происходит

1. **URL нормализуется** — убирается trailing slash (`https://gitea.example.com/` → `https://gitea.example.com`)
2. **verify_ssl обрабатывает три варианта:**
   - `True` / `False` — bool, передаётся как есть
   - `"true"` / `"false"` — строка из YAML, конвертируется в bool
   - `"/path/to/cert.pem"` — путь, передаётся как строка
3. **Session** — используется один раз, токен в заголовке `Authorization: token <...>`

### Результат операции: GitPushResult

```python
@dataclass
class GitPushResult:
    hostname: str                      # Имя устройства
    file_path: str                     # Путь в репо: "site/hostname/running-config.cfg"
    success: bool                      # True если операция прошла
    action: str = ""                   # "created", "updated", "unchanged"
    commit_sha: Optional[str] = None   # SHA коммита (если был)
    web_url: Optional[str] = None      # URL в Gitea Web UI
    error: Optional[str] = None        # Текст ошибки (если была)
```

Каждый push_file() возвращает `GitPushResult` — по нему можно понять что произошло.

---

## 6. Алгоритм push_file: GET → POST/PUT

Это самый важный метод. Для каждого устройства он определяет: создать файл, обновить, или пропустить.

```python
def push_file(self, hostname, config_content, site=None):
    # 1. Формируем путь в репо
    if site:
        safe_site = re.sub(r'[^\w\-.]', '_', site)  # безопасное имя папки
        repo_path = f"{safe_site}/{hostname}/running-config.cfg"
    else:
        repo_path = f"{hostname}/running-config.cfg"

    # 2. Проверяем — есть ли файл в репо? (GET)
    existing = self._get_file(repo_path)

    if existing is None:
        # 3a. Файл не существует → создаём (POST)
        self._create_file(repo_path, config_content, message)
        result.action = "created"

    elif self._content_changed(existing, config_content):
        # 3b. Файл есть, содержимое изменилось → обновляем (PUT)
        sha = existing.get("sha", "")
        self._update_file(repo_path, config_content, sha, message)
        result.action = "updated"

    else:
        # 3c. Файл есть, не изменился → пропускаем
        result.action = "unchanged"
```

### REST API вызовы

```
GET  /api/v1/repos/backup-bot/network-backups/contents/DC-1/switch-01/running-config.cfg
     → 404: файла нет
     → 200: {"content": "aG9zdG5hbWUg...", "sha": "abc123"}

POST /api/v1/repos/backup-bot/network-backups/contents/DC-1/switch-01/running-config.cfg
     Body: {"message": "backup: добавлен конфиг switch-01",
            "content": "<base64>", "branch": "main"}

PUT  /api/v1/repos/backup-bot/network-backups/contents/DC-1/switch-01/running-config.cfg
     Body: {"message": "backup: обновлён конфиг switch-01",
            "content": "<base64>", "sha": "abc123", "branch": "main"}
```

**Важно:** при обновлении (PUT) нужен `sha` текущего файла — это защита от перезаписи
(optimistic locking). Если кто-то изменил файл между GET и PUT, API вернёт ошибку.

### Путь `safe_site`

Имя сайта может содержать спецсимволы (пробелы, кириллица). Для безопасного использования
в пути файловой системы Git применяется санитизация:

```python
safe_site = re.sub(r'[^\w\-.]', '_', site)
# "DC Москва" → "DC___________"
# "DC-Moscow"  → "DC-Moscow"  (без изменений)
```

---

## 7. Обнаружение изменений: base64 + strip

Gitea API возвращает содержимое файла в **base64**. Чтобы определить, изменился ли конфиг,
нужно декодировать и сравнить:

```python
def _content_changed(self, existing, new_content):
    existing_content = base64.b64decode(existing.get("content", "")).decode("utf-8")
    return existing_content.strip() != new_content.strip()
```

### Что здесь происходит

1. **base64.b64decode** — декодируем содержимое из ответа API
2. **.decode("utf-8")** — из bytes в строку
3. **.strip()** — убираем пробелы/переводы строк в начале и конце
4. **Сравниваем** — если одинаково, возвращаем `False` (не изменилось)

**Зачем strip?** Разные устройства добавляют разное количество пустых строк в конце конфига.
Без strip каждый бэкап считался бы "изменённым".

**Пример:**

```python
# В Git:     "hostname switch-01\nvlan 100\n\n"
# Новый:     "hostname switch-01\nvlan 100\n"
# strip():   "hostname switch-01\nvlan 100" == "hostname switch-01\nvlan 100"
# Результат: unchanged (пропускаем)
```

---

## 8. Группировка по сайтам: site_map

Самая сложная часть — связать hostname устройства с его сайтом. Проблема в том,
что hostname узнаётся из SSH (после подключения), а site задаётся в `devices_ips.py`
(до подключения, по IP).

### Цепочка данных

```
devices_ips.py              BackupResult              site_map
┌─────────────┐            ┌─────────────┐          ┌─────────────────┐
│ host: 10.0.0.1 ──────┐  │ device_ip: 10.0.0.1 │  │ switch-01: DC-1 │
│ site: "DC-1" │       │  │ hostname: "switch-01"│  │ switch-02: DC-2 │
│              │       └──┤                      ├──┤                 │
│ host: 10.0.0.2 ──────┐  │ device_ip: 10.0.0.2 │  │                 │
│ site: "DC-2" │       │  │ hostname: "switch-02"│  │                 │
└─────────────┘       └──┤                      │  └─────────────────┘
                          └─────────────────────┘
```

### Код _build_site_map (backup.py)

```python
def _build_site_map(backup_results, devices, default_site=None):
    # Шаг 1: IP → site из devices_ips.py
    ip_to_site = {}
    for device in devices:
        site = getattr(device, "site", None) or default_site
        if site:
            ip_to_site[device.host] = site  # "10.0.0.1" → "DC-1"

    # Шаг 2: hostname → site через BackupResult.device_ip
    site_map = {}
    for result in backup_results:
        if result.success and result.hostname:
            site = ip_to_site.get(result.device_ip)
            if site:
                site_map[result.hostname] = site  # "switch-01" → "DC-1"

    return site_map if site_map else None
```

### Приоритет определения site

```
1. device.site (из devices_ips.py, per-device)    ← высший приоритет
2. default_site (из --site флага CLI)              ← fallback
3. None (без группировки, файл прямо в hostname/)  ← дефолт
```

### Пример devices_ips.py

```python
devices_list = [
    {"host": "10.0.0.1", "platform": "cisco_iosxe", "site": "DC-Moscow"},
    {"host": "10.0.0.2", "platform": "cisco_iosxe", "site": "DC-SPB"},
    {"host": "10.0.0.3", "platform": "arista_eos"},  # нет site → default_site
]
```

---

## 9. Обработка ошибок

Каждый push_file() обёрнут в try/except — ошибка одного устройства не останавливает обработку:

```python
def push_file(self, hostname, config_content, site=None):
    try:
        existing = self._get_file(repo_path)
        # ... create/update/skip ...
    except requests.RequestException as e:
        result.error = str(e)           # Записываем ошибку
        result.success = False
        logger.error(f"[ERROR] {hostname}: ошибка Git push: {e}")
    except Exception as e:
        result.error = str(e)
        result.success = False
    return result  # Всегда возвращаем результат
```

### Типичные ошибки

| Ошибка | Причина | Что в result |
|--------|---------|--------------|
| `ConnectionError` | Git-сервер недоступен | `success=False, error="Connection refused"` |
| `401 Unauthorized` | Неверный токен | `success=False, error="401..."` |
| `404 Not Found` | Неверный repo в config | `success=False, error="404..."` |
| `409 Conflict` | SHA устарел (файл изменён) | `success=False, error="409..."` |
| `SSLError` | Проблема с сертификатом | `success=False, error="SSL..."` |

### test_connection() — проверка перед работой

```python
def test_connection(self) -> bool:
    url = self._api_url("")  # GET /api/v1/repos/owner/repo/
    resp = self._session.get(url, timeout=self.timeout)
    if resp.status_code == 200:
        logger.info(f"Git подключение OK: {repo_info.get('full_name')}")
        return True
    else:
        logger.error(f"Git: HTTP {resp.status_code}")
        return False
```

Использование из CLI: `python -m network_collector backup --git-test`

---

## 10. SSL и безопасность

### Три режима verify_ssl

```yaml
# 1. Системный CA (рекомендуется)
verify_ssl: true
# requests проверяет сертификат через certifi (или truststore)

# 2. Без проверки (только для тестов!)
verify_ssl: false
# requests НЕ проверяет сертификат — MITM-атака возможна

# 3. Путь к CA-сертификату (self-signed / корп. CA)
verify_ssl: "/etc/ssl/certs/gitea-ca.pem"
# requests проверяет сертификат через указанный CA
```

### Как работает verify_ssl в коде

```python
# В __init__:
self._session.verify = self.verify_ssl

# requests.Session.verify принимает:
#   True  → certifi CA bundle (или truststore)
#   False → без проверки
#   str   → путь к CA-сертификату
```

### truststore — системные сертификаты

По умолчанию `requests` использует `certifi` bundle из virtualenv (НЕ системное хранилище).
Пакет `truststore` (Python 3.10+) переключает на системные сертификаты:

```python
# config.py — выполняется при старте
import truststore
truststore.inject_into_ssl()
```

| Платформа | Хранилище |
|-----------|-----------|
| Windows | Windows Certificate Store (`certmgr.msc`) |
| Linux | `/etc/ssl/certs/` (`update-ca-certificates`) |

### Токен передаётся в заголовке

```python
self._session.headers.update({
    "Authorization": f"token {self.token}",
})
```

Токен передаётся в каждом запросе через HTTP-заголовок. При HTTPS — шифруется.
При HTTP — передаётся открытым текстом (не использовать в продакшене!).

---

## 11. Тестирование

**Файл:** `tests/test_core/test_git_pusher.py` (~331 строк, 30 тестов)

Все тесты работают **без реальных HTTP-запросов** — через `unittest.mock.patch`.

### Паттерн: мокаем внутренние методы

```python
def test_create_new_file(self, pusher):
    """Новый файл → action='created'."""
    config = "hostname switch-01\n!\nend\n"

    # Мокаем: _get_file возвращает None (файла нет)
    #         _create_file возвращает {"commit": {"sha": "abc123"}}
    with patch.object(pusher, "_get_file", return_value=None), \
         patch.object(pusher, "_create_file", return_value={
             "commit": {"sha": "abc123"}
         }):
        result = pusher.push_file("switch-01", config)

    assert result.success is True
    assert result.action == "created"
    assert result.commit_sha == "abc123"
```

### Что здесь происходит

1. **`patch.object(pusher, "_get_file", return_value=None)`** — подменяем `_get_file`
   чтобы он возвращал `None` (как будто файла нет в репо)
2. **`patch.object(pusher, "_create_file", ...)`** — подменяем `_create_file`
   чтобы он возвращал фейковый ответ API
3. **Вызываем `push_file`** — он использует замоканные методы
4. **Проверяем результат** — action="created", success=True

### Группы тестов

| Класс | Что тестирует | Кол-во тестов |
|-------|---------------|---------------|
| `TestGitPushFile` | Создание, обновление, пропуск, пути, URL, ошибки | 8 |
| `TestGitPushBackups` | Сканирование папки, пустая папка, site_map | 5 |
| `TestGitContentChanged` | Сравнение контента: одинаковый, разный, whitespace | 3 |
| `TestGitTestConnection` | Подключение: OK, ошибка, 404 | 3 |
| `TestGitConfigSchema` | Pydantic валидация: дефолты, URL, verify_ssl | 6 |
| `TestGitVerifySSL` | SSL: true, false, путь к серту, строки "true"/"false" | 5 |

### Тест site_map

```python
def test_push_backups_with_site_map(self, pusher, tmp_path):
    (tmp_path / "sw1.cfg").write_text("config sw1")
    (tmp_path / "sw2.cfg").write_text("config sw2")
    site_map = {"sw1": "msk-office", "sw2": "spb-dc"}

    with patch.object(pusher, "push_file", return_value=GitPushResult(
        hostname="test", file_path="test/running-config.cfg",
        success=True, action="created",
    )) as mock_push:
        pusher.push_backups(str(tmp_path), site_map=site_map)

    calls = mock_push.call_args_list
    assert calls[0].kwargs.get("site") == "msk-office"  # sw1
    assert calls[1].kwargs.get("site") == "spb-dc"       # sw2
```

### Запуск тестов

```bash
cd /home/sa/project
python -m pytest network_collector/tests/test_core/test_git_pusher.py -v
```

---

## 12. Полная диаграмма потока данных

```
┌─────────────────────────────────────────────────────────────────────┐
│  1. CLI: python -m network_collector backup --push-git --site DC-1  │
└─────────────┬───────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────┐
│  2. cli/__init__.py                  │
│     → parse args                     │
│     → route → cmd_backup(args)       │
└─────────────┬───────────────────────┘
              │
              ▼
┌─────────────────────────────────────┐
│  3. cli/commands/backup.py           │
│     cmd_backup():                    │
│     ├── prepare_collection(args)     │
│     │   └── devices, credentials     │
│     ├── ConfigBackupCollector        │
│     │   └── SSH → running-config     │
│     │       → save .cfg files        │
│     └── if --push-git:               │
│         ├── _build_site_map()        │
│         └── pusher.push_backups()    │
└─────────────┬───────────────────────┘
              │
              ▼
┌─────────────────────────────────────┐    ┌──────────────────────┐
│  4. _build_site_map()                │    │  devices_ips.py      │
│     ├── Device.host → Device.site    │◄───│  host: 10.0.0.1     │
│     │   (IP → site mapping)          │    │  site: "DC-Moscow"   │
│     └── BackupResult.device_ip       │    └──────────────────────┘
│         → hostname → site            │
│     Result: {"switch-01": "DC-1"}    │
└─────────────┬───────────────────────┘
              │
              ▼
┌─────────────────────────────────────┐
│  5. GitBackupPusher.push_backups()   │
│     ├── glob("*.cfg") → файлы        │
│     └── for each .cfg:               │
│         ├── hostname = файл.stem     │
│         ├── site = site_map[hostname]│
│         └── push_file(hostname, cfg) │
└─────────────┬───────────────────────┘
              │
              ▼
┌─────────────────────────────────────┐
│  6. push_file()                      │
│     ├── repo_path = site/hostname/   │
│     │               running-config   │
│     ├── GET existing file            │───── 404 → POST (create)
│     ├── content_changed?             │───── Yes → PUT  (update)
│     └── unchanged                    │───── No  → skip
└─────────────┬───────────────────────┘
              │
              ▼
┌─────────────────────────────────────┐
│  7. Gitea REST API v1                │
│     ├── POST → 201: commit created   │
│     ├── PUT  → 200: commit updated   │
│     └── Ответ: {"commit": {"sha":...}}│
└─────────────────────────────────────┘
```

### Три режима CLI (сводка)

```
backup                    SSH → .cfg файлы (только локально)
backup --push-git         SSH → .cfg → push_backups(site_map)
backup --git-only         .cfg → push_backups(default_site)
backup --git-test         test_connection() → OK/FAIL
```

---

## 13. Связь с официальной документацией

| Тема | Где читать |
|------|------------|
| CLI команды backup | [MANUAL.md](../MANUAL.md) — секция 3 и 10.5 |
| SSL сертификаты | [MANUAL.md](../MANUAL.md) — секция 9.4 |
| Переменные окружения | [MANUAL.md](../MANUAL.md) — секция 9.3 и 9.5 |
| Архитектура слоёв | [ARCHITECTURE.md](../ARCHITECTURE.md) |
| devices_ips.py формат | [MANUAL.md](../MANUAL.md) — секция 1.3 |
| Тестирование | [TESTING.md](../TESTING.md) |
| План развития | [TODO.md](../TODO.md) — секция Backup-to-Git |
