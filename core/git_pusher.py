"""
Модуль для отправки бэкапов конфигураций в Git (Gitea/GitLab/GitHub).

Использует REST API для создания/обновления файлов в репозитории.
Каждое устройство — отдельная папка, конфиг обновляется коммитом.

Структура репозитория:
    network-backups/
    ├── switch-core-01/
    │   └── running-config.cfg
    ├── switch-access-02/
    │   └── running-config.cfg
    └── ...

Поддерживаемые серверы: Gitea, GitLab, GitHub (через REST API).

Пример использования:
    pusher = GitBackupPusher(
        url="http://localhost:3001",
        token="your-api-token",
        repo="backup-bot/network-backups",
    )
    results = pusher.push_backups(backup_folder="backups")
"""

import base64
import hashlib
import re
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field

import requests

from .logging import get_logger

logger = get_logger(__name__)


@dataclass
class GitPushResult:
    """Результат пуша одного файла в Git."""
    hostname: str
    file_path: str
    success: bool
    action: str = ""  # "created", "updated", "unchanged"
    commit_sha: Optional[str] = None
    web_url: Optional[str] = None
    error: Optional[str] = None


class GitBackupPusher:
    """
    Отправляет бэкапы конфигураций в Git-репозиторий через REST API.

    Поддерживает Gitea API v1. Для каждого .cfg файла:
    1. Проверяет есть ли файл в репо (GET)
    2. Если нет — создаёт (POST)
    3. Если есть и содержимое изменилось — обновляет (PUT)
    4. Если содержимое не изменилось — пропускает

    Attributes:
        url: URL Git-сервера (например http://localhost:3001)
        token: API-токен для аутентификации
        repo: Репозиторий в формате "owner/repo"
        branch: Ветка для коммитов (по умолчанию "main")
        verify_ssl: Проверять SSL сертификат
    """

    def __init__(
        self,
        url: str,
        token: str,
        repo: str,
        branch: str = "main",
        verify_ssl: any = True,
        timeout: int = 30,
    ):
        """
        Args:
            verify_ssl: True — проверять системный CA,
                        False — не проверять (небезопасно),
                        "/path/to/cert.pem" — путь к self-signed сертификату.
        """
        self.url = url.rstrip("/")
        self.token = token
        self.repo = repo
        self.branch = branch
        self.timeout = timeout

        # verify_ssl: bool или путь к сертификату
        # requests принимает: True, False, "/path/to/ca-bundle.crt"
        if isinstance(verify_ssl, str) and verify_ssl.lower() in ("true", "false"):
            self.verify_ssl = verify_ssl.lower() == "true"
        else:
            self.verify_ssl = verify_ssl

        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"token {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
        self._session.verify = self.verify_ssl

        # Подавляем предупреждения при verify_ssl=False (self-signed без сертификата)
        if self.verify_ssl is False:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def _api_url(self, path: str) -> str:
        """Формирует полный URL для API-запроса."""
        return f"{self.url}/api/v1/repos/{self.repo}/{path}"

    def _get_file(self, file_path: str) -> Optional[dict]:
        """
        Получает информацию о файле из репозитория.

        Returns:
            dict с полями content, sha если файл существует, None если нет.
        """
        url = self._api_url(f"contents/{file_path}")
        params = {"ref": self.branch}

        try:
            resp = self._session.get(url, params=params, timeout=self.timeout)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"Ошибка получения файла {file_path}: {e}")
            raise

        return None

    def _create_file(self, file_path: str, content: str, message: str) -> dict:
        """Создаёт новый файл в репозитории."""
        url = self._api_url(f"contents/{file_path}")
        data = {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "branch": self.branch,
        }

        resp = self._session.post(url, json=data, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def _update_file(self, file_path: str, content: str, sha: str, message: str) -> dict:
        """Обновляет существующий файл в репозитории."""
        url = self._api_url(f"contents/{file_path}")
        data = {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "sha": sha,
            "branch": self.branch,
        }

        resp = self._session.put(url, json=data, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def _content_changed(self, existing: dict, new_content: str) -> bool:
        """Проверяет изменилось ли содержимое файла."""
        # Gitea возвращает content в base64
        existing_content = base64.b64decode(existing.get("content", "")).decode("utf-8")
        return existing_content.strip() != new_content.strip()

    def get_device_url(self, hostname: str, site: Optional[str] = None) -> str:
        """
        Формирует Web URL для папки устройства в Gitea.

        Можно вставить в NetBox custom field (тип URL) для быстрого
        перехода к конфигам устройства прямо из NetBox.

        Args:
            hostname: Имя устройства
            site: Сайт (если используется группировка по сайтам)

        Returns:
            str: URL вида http://gitea:3001/owner/repo/src/branch/main/site/hostname
        """
        if site:
            safe_site = re.sub(r'[^\w\-.]', '_', site)
            path = f"{safe_site}/{hostname}"
        else:
            path = hostname
        return f"{self.url}/{self.repo}/src/branch/{self.branch}/{path}"

    def push_file(
        self, hostname: str, config_content: str, site: Optional[str] = None
    ) -> GitPushResult:
        """
        Пушит конфигурацию одного устройства в Git.

        Args:
            hostname: Имя устройства (будет именем папки)
            config_content: Содержимое конфигурации
            site: Сайт устройства (для группировки: site/hostname/)

        Returns:
            GitPushResult: Результат операции
        """
        # Путь в репо: {site}/{hostname}/running-config.cfg или {hostname}/running-config.cfg
        if site:
            safe_site = re.sub(r'[^\w\-.]', '_', site)
            repo_path = f"{safe_site}/{hostname}/running-config.cfg"
        else:
            repo_path = f"{hostname}/running-config.cfg"

        result = GitPushResult(
            hostname=hostname,
            file_path=repo_path,
            success=False,
            web_url=self.get_device_url(hostname, site),
        )

        try:
            existing = self._get_file(repo_path)

            if existing is None:
                # Файл не существует — создаём
                message = f"backup: добавлен конфиг {hostname}"
                resp = self._create_file(repo_path, config_content, message)
                result.action = "created"
                result.commit_sha = resp.get("commit", {}).get("sha", "")
                result.success = True
                logger.info(f"[CREATE] {hostname}: конфиг добавлен в Git")

            elif self._content_changed(existing, config_content):
                # Файл изменился — обновляем
                sha = existing.get("sha", "")
                message = f"backup: обновлён конфиг {hostname}"
                resp = self._update_file(repo_path, config_content, sha, message)
                result.action = "updated"
                result.commit_sha = resp.get("commit", {}).get("sha", "")
                result.success = True
                logger.info(f"[UPDATE] {hostname}: конфиг обновлён в Git")

            else:
                # Файл не изменился
                result.action = "unchanged"
                result.success = True
                logger.info(f"[SKIP] {hostname}: конфиг не изменился")

        except requests.RequestException as e:
            result.error = str(e)
            logger.error(f"[ERROR] {hostname}: ошибка Git push: {e}")
        except Exception as e:
            result.error = str(e)
            logger.error(f"[ERROR] {hostname}: неизвестная ошибка: {e}")

        return result

    def push_backups(
        self,
        backup_folder: str = "backups",
        site_map: Optional[Dict[str, str]] = None,
        default_site: Optional[str] = None,
    ) -> List[GitPushResult]:
        """
        Пушит все .cfg файлы из папки бэкапов в Git.

        Структура:
        - С site_map: {site}/{hostname}/running-config.cfg
        - Без site_map: {hostname}/running-config.cfg

        Args:
            backup_folder: Папка с бэкапами
            site_map: Маппинг hostname → site (из devices_ips.py).
                      Если передан, файлы группируются по сайтам.
            default_site: Дефолтный site для устройств без записи в site_map.

        Returns:
            List[GitPushResult]: Результаты для каждого файла
        """
        folder = Path(backup_folder)
        results = []

        if not folder.exists():
            logger.error(f"Папка бэкапов не найдена: {folder}")
            return results

        cfg_files = sorted(folder.glob("*.cfg"))
        if not cfg_files:
            logger.warning(f"Нет .cfg файлов в {folder}")
            return results

        logger.info(f"Пушим {len(cfg_files)} бэкапов в Git ({self.repo})...")

        for cfg_file in cfg_files:
            hostname = cfg_file.stem  # имя файла без .cfg
            config_content = cfg_file.read_text(encoding="utf-8")
            # Приоритет: per-device site из site_map → default_site
            site = None
            if site_map:
                site = site_map.get(hostname)
            if not site and default_site:
                site = default_site
            result = self.push_file(hostname, config_content, site=site)
            results.append(result)

        # Статистика
        created = sum(1 for r in results if r.action == "created")
        updated = sum(1 for r in results if r.action == "updated")
        unchanged = sum(1 for r in results if r.action == "unchanged")
        failed = sum(1 for r in results if not r.success)

        logger.info(
            f"Git push завершён: "
            f"создано={created}, обновлено={updated}, "
            f"без изменений={unchanged}, ошибки={failed}"
        )

        return results

    def test_connection(self) -> bool:
        """Проверяет доступность репозитория."""
        try:
            url = self._api_url("")
            resp = self._session.get(url, timeout=self.timeout)
            if resp.status_code == 200:
                repo_info = resp.json()
                logger.info(
                    f"Git подключение OK: {repo_info.get('full_name', self.repo)}"
                )
                return True
            else:
                logger.error(f"Git: HTTP {resp.status_code} — {resp.text[:200]}")
                return False
        except requests.RequestException as e:
            logger.error(f"Git: ошибка подключения: {e}")
            return False
