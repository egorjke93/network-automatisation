# Безопасность и конфиденциальность

Данный документ описывает безопасные способы хранения учётных данных и работы с SSL сертификатами.

## Содержание

1. [Хранение NetBox API токена](#хранение-netbox-api-токена)
2. [SSL сертификаты (корпоративные CA)](#ssl-сертификаты-корпоративные-ca)
3. [Приоритет источников credentials](#приоритет-источников-credentials)
4. [Troubleshooting](#troubleshooting)

---

## Хранение NetBox API токена

### Проблема

**ПЛОХО — plaintext в config.yaml:**
```yaml
# config.yaml
netbox:
  token: "4dd51a78084a1c18c7dc95f56a5355c692811c02"  # ❌ НЕ БЕЗОПАСНО!
```

Файл может попасть в git, логи, screen sharing.

### Решение: Windows Credential Manager

**ХОРОШО — системное хранилище:**
- Windows: Credential Manager (зашифровано)
- Linux: Secret Service / Gnome Keyring
- macOS: Keychain

---

## Настройка на Windows

### Шаг 1: Установить зависимости

```bash
pip install keyring python-certifi-win32
```

### Шаг 2: Добавить токен в Credential Manager

#### Способ A: Через GUI (рекомендуется)

1. **Открыть Credential Manager:**
   ```
   Win + R → введите "Credential Manager" → Enter
   ```
   Или: `Панель управления → Учётные записи пользователей → Диспетчер учётных данных`

2. **Добавить Generic Credential:**
   - Нажмите **"Windows Credentials"** (Учётные данные Windows)
   - Нажмите **"Add a generic credential"** (Добавить универсальные учётные данные)

3. **Заполните форму ТОЧНО как указано:**
   ```
   Internet or network address: network_collector
   User name:                   netbox_token
   Password:                    <ваш NetBox API токен>
   ```

   **ВАЖНО:** Названия должны быть ТОЧНО такими (`network_collector`, `netbox_token`)

4. **Сохранить:** Нажмите "OK"

#### Способ B: Через командную строку (PowerShell)

```powershell
# Запустите PowerShell от имени администратора
cmdkey /generic:network_collector /user:netbox_token /pass:ваш-токен-здесь
```

### Шаг 3: Удалить токен из config.yaml

```yaml
# config.yaml
netbox:
  url: "https://netbox.example.com"
  token: ""  # Оставить пустым или удалить строку
```

### Шаг 4: Проверить что работает

```bash
python -m network_collector sync-netbox --interfaces --dry-run
```

Если токен найден, вы увидите в логах:
```
DEBUG: NetBox токен получен из системного хранилища (Credential Manager)
```

---

## Настройка на Linux

### Установка

```bash
# Ubuntu/Debian
sudo apt-get install gnome-keyring libsecret-1-0
pip install keyring python-certifi-win32

# Fedora/RHEL
sudo dnf install gnome-keyring libsecret
pip install keyring python-certifi-win32
```

### Добавить токен

```bash
# Интерактивно (скрытый ввод)
python3 -c "
import keyring
from getpass import getpass
token = getpass('Enter NetBox token: ')
keyring.set_password('network_collector', 'netbox_token', token)
print('Token saved!')
"
```

---

## SSL сертификаты (корпоративные CA)

### Проблема

При использовании корпоративного NetBox с самоподписанным или корпоративным CA:

```
SSLError: [SSL: CERTIFICATE_VERIFY_FAILED]
```

### Решение: python-certifi-win32

**Автоматическое подключение Windows Certificate Store:**

1. **Установить (уже сделали выше):**
   ```bash
   pip install python-certifi-win32
   ```

2. **Готово!** Утилита автоматически использует системные сертификаты.

Network Collector автоматически подключает `certifi_win32` при запуске (см. `__main__.py`).

### Как это работает

```python
# __main__.py (автоматически)
import certifi_win32
certifi_win32.wincerts.where()  # Патчит certifi

# Теперь все requests/pynetbox используют Windows Certificate Store
```

### Альтернатива: отключить проверку (НЕ рекомендуется)

```yaml
# config.yaml
netbox:
  verify_ssl: false  # ⚠️ ТОЛЬКО ДЛЯ ТЕСТОВ!
```

---

## Приоритет источников credentials

### NetBox API токен

```
1. Переменная окружения NETBOX_TOKEN     (высший приоритет, для CI/CD)
   ↓
2. Системное хранилище (Credential Manager)  (рекомендуется для продакшена)
   ↓
3. config.yaml → netbox.token             (fallback, не рекомендуется)
```

**Код:**
```python
# core/credentials.py
def get_netbox_token(config_token=None):
    # 1. Env var
    if os.getenv("NETBOX_TOKEN"):
        return os.getenv("NETBOX_TOKEN")

    # 2. Keyring
    import keyring
    if keyring.get_password("network_collector", "netbox_token"):
        return keyring.get_password("network_collector", "netbox_token")

    # 3. Config
    return config_token
```

### SSH учётные данные (для устройств)

```
1. Переменные окружения NET_USERNAME, NET_PASSWORD
   ↓
2. Интерактивный ввод (getpass)
```

**Пример:**
```bash
# Windows CMD
set NET_USERNAME=admin
set NET_PASSWORD=cisco

# Windows PowerShell
$env:NET_USERNAME="admin"
$env:NET_PASSWORD="cisco"

# Linux/macOS
export NET_USERNAME=admin
export NET_PASSWORD=cisco
```

---

## Примеры использования

### Вариант 1: Credential Manager (продакшен)

```bash
# 1. Добавить токен в Credential Manager (один раз)
#    Internet address: network_collector
#    User name:        netbox_token
#    Password:         <ваш токен>

# 2. Убрать из config.yaml
# config.yaml:
# netbox:
#   token: ""

# 3. Запускать как обычно
python -m network_collector sync-netbox --interfaces
```

### Вариант 2: Переменная окружения (CI/CD, тесты)

```bash
# Windows CMD
set NETBOX_TOKEN=4dd51a78084a1c18c7dc95f56a5355c692811c02
python -m network_collector sync-netbox --interfaces

# Linux/macOS
export NETBOX_TOKEN=4dd51a78084a1c18c7dc95f56a5355c692811c02
python -m network_collector sync-netbox --interfaces
```

### Вариант 3: Config.yaml (разработка, fallback)

```yaml
# config.yaml (НЕ коммитить в git!)
netbox:
  token: "4dd51a78084a1c18c7dc95f56a5355c692811c02"
```

---

## Troubleshooting

### Токен не найден

**Ошибка:**
```
ValueError: NetBox токен не указан. Добавьте токен в Windows Credential Manager
```

**Решение:**
1. Проверить Credential Manager: `Win+R → Credential Manager`
2. Найти **"network_collector"** в Generic Credentials
3. Если нет — добавить (см. [Шаг 2](#шаг-2-добавить-токен-в-credential-manager))
4. Проверить что User name = **"netbox_token"** (ТОЧНО)

### Keyring не установлен

**Ошибка (в логах):**
```
DEBUG: Библиотека keyring не установлена, пропускаем системное хранилище
```

**Решение:**
```bash
pip install keyring
```

### SSL сертификат не принимается

**Ошибка:**
```
SSLError: [SSL: CERTIFICATE_VERIFY_FAILED]
```

**Решение:**
1. Проверить что `python-certifi-win32` установлен:
   ```bash
   pip install python-certifi-win32
   ```

2. Убедиться что корпоративный CA добавлен в Windows Certificate Store:
   ```
   Win+R → certmgr.msc → Trusted Root Certification Authorities
   ```

3. Перезапустить утилиту

### Проверить откуда берётся токен

```bash
# Включить debug логирование
python -m network_collector sync-netbox --interfaces --dry-run 2>&1 | grep -i "netbox токен"

# Вывод покажет источник:
# DEBUG: NetBox токен получен из переменной окружения NETBOX_TOKEN
# или
# DEBUG: NetBox токен получен из системного хранилища (Credential Manager)
# или
# DEBUG: NetBox токен получен из config.yaml
```

---

## Best Practices

### ✅ Рекомендуется

- **Продакшен:** Credential Manager
- **CI/CD:** Переменные окружения (NETBOX_TOKEN)
- **SSL:** Использовать `python-certifi-win32`
- **Git:** Добавить `.gitignore`:
  ```
  config.yaml
  .env
  ```

### ❌ Не рекомендуется

- Хранить токены в config.yaml в продакшене
- Коммитить config.yaml с токенами в git
- Отключать verify_ssl в продакшене
- Передавать токены в аргументах командной строки

---

## Дополнительная информация

### Где хранятся credentials в Windows

```
Credential Manager → Generic Credentials
Физически: C:\Users\<user>\AppData\Local\Microsoft\Credentials\
Зашифровано: DPAPI (Data Protection API)
```

### Проверка через Python

```python
# Проверить что токен доступен
import keyring
token = keyring.get_password("network_collector", "netbox_token")
print(f"Token found: {token[:10]}..." if token else "Token not found")

# Добавить токен
keyring.set_password("network_collector", "netbox_token", "your-token-here")

# Удалить токен
keyring.delete_password("network_collector", "netbox_token")
```

---

## Контакты

Если возникли проблемы с настройкой безопасности, создайте issue в репозитории.
