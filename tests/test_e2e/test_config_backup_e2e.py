"""
E2E тесты для ConfigBackupCollector.

Проверяет полный цикл: подключение → получение конфига → сохранение.
Без реального SSH подключения.

Примечание: ConfigBackupCollector сохраняет конфигурации в файлы,
поэтому тесты проверяют создание файлов и их содержимое.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from typing import List
from unittest.mock import patch, MagicMock

from network_collector.collectors.config_backup import (
    ConfigBackupCollector,
    BackupResult,
    CONFIG_COMMANDS,
)
from network_collector.core.exceptions import ConnectionError, AuthenticationError

from .conftest import create_mock_device, SUPPORTED_PLATFORMS


@pytest.fixture
def temp_backup_dir():
    """Создаёт временную папку для бэкапов."""
    temp_dir = tempfile.mkdtemp(prefix="backup_test_")
    yield temp_dir
    # Очистка после теста
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def collector():
    """Создаёт ConfigBackupCollector для тестов."""
    credentials = MagicMock()
    credentials.username = "admin"
    credentials.password = "password"
    return ConfigBackupCollector(credentials=credentials)


class TestConfigBackupE2E:
    """E2E тесты ConfigBackupCollector — полный цикл без SSH."""

    def test_cisco_ios_backup_creates_file(
        self, collector, load_fixture, temp_backup_dir
    ):
        """Cisco IOS: бэкап создаёт файл с конфигом."""
        config = load_fixture("cisco_ios", "show_running_config.txt")
        device = create_mock_device("cisco_ios", "SW-CORE-01", "10.0.0.1")

        # Мокаем подключение
        mock_conn = MagicMock()
        mock_response = MagicMock()
        mock_response.result = config
        mock_conn.send_command.return_value = mock_response
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)

        with patch.object(
            collector._conn_manager, 'connect', return_value=mock_conn
        ):
            with patch.object(
                collector._conn_manager, 'get_hostname', return_value="SW-CORE-01"
            ):
                results = collector.backup([device], output_folder=temp_backup_dir)

        assert len(results) == 1
        result = results[0]

        assert result.success is True
        assert result.hostname == "SW-CORE-01"
        assert result.file_path is not None

        # Проверяем что файл создан
        backup_file = Path(result.file_path)
        assert backup_file.exists()
        assert backup_file.suffix == ".cfg"

        # Проверяем содержимое
        content = backup_file.read_text()
        assert "hostname SW-CORE-01" in content
        assert "interface GigabitEthernet0/1" in content

    def test_cisco_nxos_backup_creates_file(
        self, collector, load_fixture, temp_backup_dir
    ):
        """Cisco NX-OS: бэкап создаёт файл с конфигом."""
        config = load_fixture("cisco_nxos", "show_running_config.txt")
        device = create_mock_device("cisco_nxos", "NXOS-SPINE-01", "10.0.0.2")

        mock_conn = MagicMock()
        mock_response = MagicMock()
        mock_response.result = config
        mock_conn.send_command.return_value = mock_response
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)

        with patch.object(
            collector._conn_manager, 'connect', return_value=mock_conn
        ):
            with patch.object(
                collector._conn_manager, 'get_hostname', return_value="NXOS-SPINE-01"
            ):
                results = collector.backup([device], output_folder=temp_backup_dir)

        assert len(results) == 1
        result = results[0]

        assert result.success is True
        assert result.hostname == "NXOS-SPINE-01"

        backup_file = Path(result.file_path)
        assert backup_file.exists()

        content = backup_file.read_text()
        assert "hostname NXOS-SPINE-01" in content
        assert "interface Ethernet1/1" in content

    def test_qtech_backup_creates_file(
        self, collector, load_fixture, temp_backup_dir
    ):
        """QTech: бэкап создаёт файл с конфигом."""
        config = load_fixture("qtech", "show_running_config.txt")
        device = create_mock_device("qtech", "QTECH-DC-SW01", "10.0.0.3")

        mock_conn = MagicMock()
        mock_response = MagicMock()
        mock_response.result = config
        mock_conn.send_command.return_value = mock_response
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)

        with patch.object(
            collector._conn_manager, 'connect', return_value=mock_conn
        ):
            with patch.object(
                collector._conn_manager, 'get_hostname', return_value="QTECH-DC-SW01"
            ):
                results = collector.backup([device], output_folder=temp_backup_dir)

        assert len(results) == 1
        result = results[0]

        assert result.success is True
        assert result.hostname == "QTECH-DC-SW01"

        backup_file = Path(result.file_path)
        assert backup_file.exists()

        content = backup_file.read_text()
        assert "hostname QTECH-DC-SW01" in content

    @pytest.mark.parametrize("platform", SUPPORTED_PLATFORMS)
    def test_all_platforms_have_config_command(self, platform):
        """Все платформы имеют команду для получения конфига."""
        # Проверяем что платформа есть в CONFIG_COMMANDS
        # или есть fallback на show running-config
        command = CONFIG_COMMANDS.get(platform.lower(), "show running-config")
        assert "config" in command.lower() or "configuration" in command.lower()

    def test_multiple_devices_backup(
        self, collector, load_fixture, temp_backup_dir
    ):
        """Бэкап нескольких устройств создаёт отдельные файлы."""
        ios_config = load_fixture("cisco_ios", "show_running_config.txt")
        nxos_config = load_fixture("cisco_nxos", "show_running_config.txt")

        devices = [
            create_mock_device("cisco_ios", "SW1", "10.0.0.1"),
            create_mock_device("cisco_nxos", "SW2", "10.0.0.2"),
        ]

        # Настраиваем mock для разных устройств
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)

        configs = iter([ios_config, nxos_config])
        hostnames = iter(["SW1", "SW2"])

        def get_config(*args, **kwargs):
            response = MagicMock()
            response.result = next(configs)
            return response

        def get_hostname(*args, **kwargs):
            return next(hostnames)

        mock_conn.send_command.side_effect = get_config

        with patch.object(
            collector._conn_manager, 'connect', return_value=mock_conn
        ):
            with patch.object(
                collector._conn_manager, 'get_hostname', side_effect=get_hostname
            ):
                results = collector.backup(devices, output_folder=temp_backup_dir)

        assert len(results) == 2
        assert all(r.success for r in results)

        # Проверяем что созданы разные файлы
        files = list(Path(temp_backup_dir).glob("*.cfg"))
        assert len(files) == 2

        filenames = {f.stem for f in files}
        assert "SW1" in filenames
        assert "SW2" in filenames


class TestConfigBackupErrorHandling:
    """Тесты обработки ошибок."""

    @pytest.fixture
    def collector(self):
        credentials = MagicMock()
        return ConfigBackupCollector(credentials=credentials)

    def test_connection_error_handled(self, collector, temp_backup_dir):
        """Ошибка подключения обрабатывается."""
        device = create_mock_device("cisco_ios", "SW-FAIL", "10.0.0.99")

        with patch.object(
            collector._conn_manager, 'connect',
            side_effect=ConnectionError("Connection refused")
        ):
            results = collector.backup([device], output_folder=temp_backup_dir)

        assert len(results) == 1
        result = results[0]

        assert result.success is False
        assert result.error is not None
        assert "Connection" in result.error or "refused" in result.error

    def test_auth_error_handled(self, collector, temp_backup_dir):
        """Ошибка аутентификации обрабатывается."""
        device = create_mock_device("cisco_ios", "SW-AUTH-FAIL", "10.0.0.98")

        with patch.object(
            collector._conn_manager, 'connect',
            side_effect=AuthenticationError("Invalid credentials")
        ):
            results = collector.backup([device], output_folder=temp_backup_dir)

        assert len(results) == 1
        result = results[0]

        assert result.success is False
        assert result.error is not None

    def test_partial_failure(self, collector, load_fixture, temp_backup_dir):
        """Частичный сбой: одно устройство OK, другое FAIL."""
        config = load_fixture("cisco_ios", "show_running_config.txt")

        devices = [
            create_mock_device("cisco_ios", "SW-OK", "10.0.0.1"),
            create_mock_device("cisco_ios", "SW-FAIL", "10.0.0.2"),
        ]

        call_count = [0]

        def connect_side_effect(device, *args):
            call_count[0] += 1
            if call_count[0] == 1:
                mock_conn = MagicMock()
                mock_response = MagicMock()
                mock_response.result = config
                mock_conn.send_command.return_value = mock_response
                mock_conn.__enter__ = MagicMock(return_value=mock_conn)
                mock_conn.__exit__ = MagicMock(return_value=False)
                return mock_conn
            else:
                raise ConnectionError("Connection refused")

        with patch.object(
            collector._conn_manager, 'connect', side_effect=connect_side_effect
        ):
            with patch.object(
                collector._conn_manager, 'get_hostname', return_value="SW-OK"
            ):
                results = collector.backup(devices, output_folder=temp_backup_dir)

        assert len(results) == 2
        success_count = sum(1 for r in results if r.success)
        fail_count = sum(1 for r in results if not r.success)

        assert success_count == 1
        assert fail_count == 1


class TestConfigBackupFileNaming:
    """Тесты именования файлов."""

    @pytest.fixture
    def collector(self):
        credentials = MagicMock()
        return ConfigBackupCollector(credentials=credentials)

    def test_special_chars_in_hostname_sanitized(
        self, collector, load_fixture, temp_backup_dir
    ):
        """Специальные символы в hostname заменяются."""
        config = load_fixture("cisco_ios", "show_running_config.txt")
        device = create_mock_device("cisco_ios", "SW/CORE:01", "10.0.0.1")

        mock_conn = MagicMock()
        mock_response = MagicMock()
        mock_response.result = config
        mock_conn.send_command.return_value = mock_response
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)

        with patch.object(
            collector._conn_manager, 'connect', return_value=mock_conn
        ):
            with patch.object(
                collector._conn_manager, 'get_hostname', return_value="SW/CORE:01"
            ):
                results = collector.backup([device], output_folder=temp_backup_dir)

        assert len(results) == 1
        result = results[0]

        assert result.success is True
        # Файл должен быть создан с безопасным именем
        backup_file = Path(result.file_path)
        assert backup_file.exists()
        # Не должно быть "/" или ":" в имени файла
        assert "/" not in backup_file.name
        assert ":" not in backup_file.name

    def test_folder_created_if_not_exists(self, collector, load_fixture):
        """Папка создаётся если не существует."""
        config = load_fixture("cisco_ios", "show_running_config.txt")
        device = create_mock_device("cisco_ios", "SW1", "10.0.0.1")

        # Используем вложенную несуществующую папку
        with tempfile.TemporaryDirectory() as base_dir:
            nested_dir = Path(base_dir) / "level1" / "level2" / "backups"
            assert not nested_dir.exists()

            mock_conn = MagicMock()
            mock_response = MagicMock()
            mock_response.result = config
            mock_conn.send_command.return_value = mock_response
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)

            with patch.object(
                collector._conn_manager, 'connect', return_value=mock_conn
            ):
                with patch.object(
                    collector._conn_manager, 'get_hostname', return_value="SW1"
                ):
                    results = collector.backup([device], output_folder=str(nested_dir))

            assert nested_dir.exists()
            assert len(results) == 1
            assert results[0].success is True


class TestBackupResult:
    """Тесты структуры BackupResult."""

    def test_backup_result_fields(self):
        """BackupResult имеет все необходимые поля."""
        result = BackupResult(
            device_ip="10.0.0.1",
            hostname="SW1",
            success=True,
            file_path="/path/to/backup.cfg",
            error=None,
        )

        assert result.device_ip == "10.0.0.1"
        assert result.hostname == "SW1"
        assert result.success is True
        assert result.file_path == "/path/to/backup.cfg"
        assert result.error is None

    def test_backup_result_error_state(self):
        """BackupResult корректно хранит ошибку."""
        result = BackupResult(
            device_ip="10.0.0.1",
            hostname="SW1",
            success=False,
            file_path=None,
            error="Connection refused",
        )

        assert result.success is False
        assert result.file_path is None
        assert result.error == "Connection refused"
