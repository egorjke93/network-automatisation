"""
Тесты для GitBackupPusher.

Тестирует логику push_file (create/update/unchanged)
без реальных HTTP-запросов (мокаем requests).
"""

import base64
from unittest.mock import patch, MagicMock
from pathlib import Path

import pytest

from network_collector.core.git_pusher import GitBackupPusher, GitPushResult


@pytest.fixture
def pusher():
    """Создаёт GitBackupPusher с тестовыми параметрами."""
    return GitBackupPusher(
        url="http://localhost:3001",
        token="test-token",
        repo="backup-bot/network-backups",
        verify_ssl=False,
    )


class TestGitPushFile:
    """Тесты push_file: create, update, unchanged."""

    def test_create_new_file(self, pusher):
        """Новый файл → action='created'."""
        config = "hostname switch-01\n!\nend\n"

        with patch.object(pusher, "_get_file", return_value=None), \
             patch.object(pusher, "_create_file", return_value={
                 "commit": {"sha": "abc123"}
             }):
            result = pusher.push_file("switch-01", config)

        assert result.success is True
        assert result.action == "created"
        assert result.hostname == "switch-01"
        assert result.commit_sha == "abc123"

    def test_update_changed_file(self, pusher):
        """Изменённый файл → action='updated'."""
        old_content = "hostname switch-01\nvlan 100\n"
        new_content = "hostname switch-01\nvlan 200\n"
        existing = {
            "content": base64.b64encode(old_content.encode()).decode(),
            "sha": "old_sha",
        }

        with patch.object(pusher, "_get_file", return_value=existing), \
             patch.object(pusher, "_update_file", return_value={
                 "commit": {"sha": "def456"}
             }):
            result = pusher.push_file("switch-01", new_content)

        assert result.success is True
        assert result.action == "updated"
        assert result.commit_sha == "def456"

    def test_unchanged_file(self, pusher):
        """Неизменённый файл → action='unchanged'."""
        content = "hostname switch-01\nvlan 100\n"
        existing = {
            "content": base64.b64encode(content.encode()).decode(),
            "sha": "existing_sha",
        }

        with patch.object(pusher, "_get_file", return_value=existing):
            result = pusher.push_file("switch-01", content)

        assert result.success is True
        assert result.action == "unchanged"
        assert result.commit_sha is None

    def test_file_path_format(self, pusher):
        """Проверяет формат пути: {hostname}/running-config.cfg."""
        with patch.object(pusher, "_get_file", return_value=None), \
             patch.object(pusher, "_create_file", return_value={"commit": {"sha": "x"}}):
            result = pusher.push_file("router-gw-01", "config data")

        assert result.file_path == "router-gw-01/running-config.cfg"

    def test_file_path_with_site(self, pusher):
        """С site: {site}/{hostname}/running-config.cfg."""
        with patch.object(pusher, "_get_file", return_value=None), \
             patch.object(pusher, "_create_file", return_value={"commit": {"sha": "x"}}):
            result = pusher.push_file("switch-01", "config", site="msk-office")

        assert result.file_path == "msk-office/switch-01/running-config.cfg"
        assert "msk-office/switch-01" in result.web_url

    def test_web_url_without_site(self, pusher):
        """web_url без site: .../hostname."""
        with patch.object(pusher, "_get_file", return_value=None), \
             patch.object(pusher, "_create_file", return_value={"commit": {"sha": "x"}}):
            result = pusher.push_file("switch-01", "config")

        assert result.web_url == "http://localhost:3001/backup-bot/network-backups/src/branch/main/switch-01"

    def test_web_url_with_site(self, pusher):
        """web_url с site: .../site/hostname."""
        with patch.object(pusher, "_get_file", return_value=None), \
             patch.object(pusher, "_create_file", return_value={"commit": {"sha": "x"}}):
            result = pusher.push_file("switch-01", "config", site="spb-dc")

        assert result.web_url == "http://localhost:3001/backup-bot/network-backups/src/branch/main/spb-dc/switch-01"

    def test_api_error_handled(self, pusher):
        """Ошибка API → success=False, error заполнен."""
        import requests
        with patch.object(pusher, "_get_file",
                          side_effect=requests.RequestException("Connection refused")):
            result = pusher.push_file("switch-01", "config")

        assert result.success is False
        assert "Connection refused" in result.error


class TestGitPushBackups:
    """Тесты push_backups: работа с папкой файлов."""

    def test_push_backups_from_folder(self, pusher, tmp_path):
        """Пушит все .cfg файлы из папки."""
        # Создаём тестовые файлы
        (tmp_path / "sw1.cfg").write_text("config sw1")
        (tmp_path / "sw2.cfg").write_text("config sw2")
        (tmp_path / "readme.txt").write_text("not a config")  # не .cfg

        with patch.object(pusher, "push_file", return_value=GitPushResult(
            hostname="test", file_path="test/running-config.cfg",
            success=True, action="created",
        )) as mock_push:
            results = pusher.push_backups(str(tmp_path))

        # Только .cfg файлы (2, не 3)
        assert len(results) == 2
        assert mock_push.call_count == 2

        # Проверяем что hostname = имя файла без .cfg
        hostnames = [call.args[0] for call in mock_push.call_args_list]
        assert "sw1" in hostnames
        assert "sw2" in hostnames

    def test_push_backups_empty_folder(self, pusher, tmp_path):
        """Пустая папка → пустой результат."""
        results = pusher.push_backups(str(tmp_path))
        assert results == []

    def test_push_backups_missing_folder(self, pusher):
        """Несуществующая папка → пустой результат."""
        results = pusher.push_backups("/nonexistent/path")
        assert results == []

    def test_push_backups_with_site_map(self, pusher, tmp_path):
        """site_map передаёт site для каждого hostname."""
        (tmp_path / "sw1.cfg").write_text("config sw1")
        (tmp_path / "sw2.cfg").write_text("config sw2")

        site_map = {"sw1": "msk-office", "sw2": "spb-dc"}

        with patch.object(pusher, "push_file", return_value=GitPushResult(
            hostname="test", file_path="test/running-config.cfg",
            success=True, action="created",
        )) as mock_push:
            pusher.push_backups(str(tmp_path), site_map=site_map)

        # Проверяем что site передан правильно
        calls = mock_push.call_args_list
        assert calls[0].kwargs.get("site") == "msk-office"  # sw1
        assert calls[1].kwargs.get("site") == "spb-dc"  # sw2

    def test_push_backups_with_default_site(self, pusher, tmp_path):
        """default_site используется если hostname нет в site_map."""
        (tmp_path / "sw1.cfg").write_text("config sw1")
        (tmp_path / "sw2.cfg").write_text("config sw2")

        site_map = {"sw1": "msk-office"}  # sw2 нет в site_map

        with patch.object(pusher, "push_file", return_value=GitPushResult(
            hostname="test", file_path="test/running-config.cfg",
            success=True, action="created",
        )) as mock_push:
            pusher.push_backups(str(tmp_path), site_map=site_map, default_site="fallback-site")

        calls = mock_push.call_args_list
        assert calls[0].kwargs.get("site") == "msk-office"  # sw1 — из site_map
        assert calls[1].kwargs.get("site") == "fallback-site"  # sw2 — из default_site


class TestGitContentChanged:
    """Тесты _content_changed."""

    def test_same_content(self, pusher):
        """Одинаковое содержимое → False."""
        content = "hostname test\n"
        existing = {
            "content": base64.b64encode(content.encode()).decode(),
        }
        assert pusher._content_changed(existing, content) is False

    def test_different_content(self, pusher):
        """Разное содержимое → True."""
        existing = {
            "content": base64.b64encode(b"old config").decode(),
        }
        assert pusher._content_changed(existing, "new config") is True

    def test_whitespace_ignored(self, pusher):
        """Trailing whitespace игнорируется."""
        existing = {
            "content": base64.b64encode(b"config\n  \n").decode(),
        }
        assert pusher._content_changed(existing, "config") is False


class TestGitTestConnection:
    """Тесты test_connection."""

    def test_connection_ok(self, pusher):
        """Успешное подключение."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"full_name": "backup-bot/network-backups"}

        with patch.object(pusher._session, "get", return_value=mock_resp):
            assert pusher.test_connection() is True

    def test_connection_failed(self, pusher):
        """Ошибка подключения."""
        import requests
        with patch.object(pusher._session, "get",
                          side_effect=requests.RequestException("timeout")):
            assert pusher.test_connection() is False

    def test_connection_404(self, pusher):
        """Репо не найден → False."""
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.text = "Not Found"

        with patch.object(pusher._session, "get", return_value=mock_resp):
            assert pusher.test_connection() is False


class TestGitConfigSchema:
    """Тесты валидации GitConfig в config_schema."""

    def test_git_config_defaults(self):
        """GitConfig с дефолтами."""
        from network_collector.core.config_schema import GitConfig
        cfg = GitConfig()
        assert cfg.url == ""
        assert cfg.token == ""
        assert cfg.repo == ""
        assert cfg.branch == "main"
        assert cfg.verify_ssl is True
        assert cfg.timeout == 30

    def test_git_config_url_validation(self):
        """GitConfig валидирует URL."""
        from network_collector.core.config_schema import GitConfig

        # Валидный URL
        cfg = GitConfig(url="http://localhost:3001")
        assert cfg.url == "http://localhost:3001"

        # HTTPS
        cfg = GitConfig(url="https://gitea.example.com/")
        assert cfg.url == "https://gitea.example.com"  # trailing slash убирается

    def test_git_config_invalid_url(self):
        """GitConfig отклоняет невалидный URL."""
        from network_collector.core.config_schema import GitConfig
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            GitConfig(url="ftp://bad-url")

    def test_app_config_has_git(self):
        """AppConfig содержит git секцию."""
        from network_collector.core.config_schema import AppConfig
        app = AppConfig()
        assert hasattr(app, "git")
        assert app.git.branch == "main"

    def test_git_config_verify_ssl_as_path(self):
        """verify_ssl принимает путь к сертификату."""
        from network_collector.core.config_schema import GitConfig
        cfg = GitConfig(verify_ssl="/path/to/cert.pem")
        assert cfg.verify_ssl == "/path/to/cert.pem"

    def test_git_config_verify_ssl_bool(self):
        """verify_ssl принимает bool."""
        from network_collector.core.config_schema import GitConfig
        cfg = GitConfig(verify_ssl=False)
        assert cfg.verify_ssl is False


class TestGitVerifySSL:
    """Тесты verify_ssl: bool, строка, путь к сертификату."""

    def test_verify_ssl_true(self):
        """verify_ssl=True → session.verify=True."""
        p = GitBackupPusher(url="http://x", token="t", repo="o/r", verify_ssl=True)
        assert p._session.verify is True

    def test_verify_ssl_false(self):
        """verify_ssl=False → session.verify=False."""
        p = GitBackupPusher(url="http://x", token="t", repo="o/r", verify_ssl=False)
        assert p._session.verify is False

    def test_verify_ssl_cert_path(self):
        """verify_ssl='/path/to/cert.pem' → session.verify='/path/to/cert.pem'."""
        p = GitBackupPusher(url="http://x", token="t", repo="o/r", verify_ssl="/certs/ca.pem")
        assert p._session.verify == "/certs/ca.pem"

    def test_verify_ssl_string_true(self):
        """verify_ssl='true' (строка из YAML) → session.verify=True."""
        p = GitBackupPusher(url="http://x", token="t", repo="o/r", verify_ssl="true")
        assert p._session.verify is True

    def test_verify_ssl_string_false(self):
        """verify_ssl='false' (строка из YAML) → session.verify=False."""
        p = GitBackupPusher(url="http://x", token="t", repo="o/r", verify_ssl="false")
        assert p._session.verify is False
