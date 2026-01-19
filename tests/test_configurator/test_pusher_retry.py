"""Тесты retry логики для ConfigPusher."""

import pytest
from unittest.mock import patch, MagicMock

from netmiko.exceptions import (
    NetmikoTimeoutException,
    NetmikoAuthenticationException,
)

from network_collector.configurator.base import ConfigPusher, ConfigResult
from network_collector.core.device import Device
from network_collector.core.credentials import Credentials


@pytest.fixture
def credentials():
    """Тестовые учётные данные."""
    return Credentials(username="admin", password="admin123")


@pytest.fixture
def device():
    """Тестовое устройство."""
    return Device(host="192.168.1.1", device_type="cisco_ios")


@pytest.fixture
def pusher(credentials):
    """ConfigPusher с быстрыми retry для тестов."""
    return ConfigPusher(
        credentials=credentials,
        max_retries=2,
        retry_delay=0.1,  # Быстрый retry для тестов
    )


@pytest.fixture
def commands():
    """Тестовые команды."""
    return [
        "interface Gi0/1",
        "description Test-Server",
    ]


class TestConfigPusherRetry:
    """Тесты retry логики ConfigPusher."""

    def test_dry_run_no_connection(self, pusher, device, commands):
        """Dry-run не выполняет подключение."""
        result = pusher.push_config(device, commands, dry_run=True)

        assert result.success is True
        assert result.commands_sent == 2
        assert "[DRY RUN]" in result.output

    @patch("network_collector.configurator.base.ConnectHandler")
    def test_successful_push_no_retry(self, mock_handler, pusher, device, commands):
        """Успешное применение с первой попытки."""
        mock_conn = MagicMock()
        mock_handler.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_handler.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.send_config_set.return_value = "config applied"
        mock_conn.save_config.return_value = "config saved"

        result = pusher.push_config(device, commands, dry_run=False)

        assert result.success is True
        assert result.commands_sent == 2
        # ConnectHandler вызван только 1 раз
        assert mock_handler.call_count == 1

    @patch("network_collector.configurator.base.ConnectHandler")
    def test_timeout_triggers_retry(self, mock_handler, pusher, device, commands):
        """Timeout вызывает retry."""
        mock_conn = MagicMock()
        mock_conn.send_config_set.return_value = "config applied"
        mock_conn.save_config.return_value = "config saved"

        # Первые 2 попытки - timeout, третья успешна
        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] <= 2:
                raise NetmikoTimeoutException("Connection timed out")
            # Возвращаем context manager
            cm = MagicMock()
            cm.__enter__ = MagicMock(return_value=mock_conn)
            cm.__exit__ = MagicMock(return_value=False)
            return cm

        mock_handler.side_effect = side_effect

        result = pusher.push_config(device, commands, dry_run=False)

        assert result.success is True
        # 3 попытки
        assert call_count[0] == 3

    @patch("network_collector.configurator.base.ConnectHandler")
    def test_auth_error_no_retry(self, mock_handler, pusher, device, commands):
        """AuthenticationError НЕ вызывает retry."""
        mock_handler.side_effect = NetmikoAuthenticationException("Bad credentials")

        result = pusher.push_config(device, commands, dry_run=False)

        assert result.success is False
        assert "аутентификации" in result.error.lower()
        # Только 1 попытка
        assert mock_handler.call_count == 1

    @patch("network_collector.configurator.base.ConnectHandler")
    def test_all_retries_exhausted(self, mock_handler, pusher, device, commands):
        """После исчерпания всех попыток возвращается ошибка."""
        mock_handler.side_effect = NetmikoTimeoutException("Connection timed out")

        result = pusher.push_config(device, commands, dry_run=False)

        assert result.success is False
        assert "Таймаут" in result.error
        # 3 попытки (1 + 2 retry)
        assert mock_handler.call_count == 3

    @patch("network_collector.configurator.base.time.sleep")
    @patch("network_collector.configurator.base.ConnectHandler")
    def test_retry_delay_is_applied(self, mock_handler, mock_sleep, credentials, device, commands):
        """Между retry применяется задержка."""
        pusher = ConfigPusher(credentials=credentials, max_retries=2, retry_delay=5)

        mock_conn = MagicMock()
        mock_conn.send_config_set.return_value = "ok"
        mock_conn.save_config.return_value = "ok"

        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] <= 2:
                raise NetmikoTimeoutException("timeout")
            cm = MagicMock()
            cm.__enter__ = MagicMock(return_value=mock_conn)
            cm.__exit__ = MagicMock(return_value=False)
            return cm

        mock_handler.side_effect = side_effect

        pusher.push_config(device, commands, dry_run=False)

        # sleep вызван 2 раза
        assert mock_sleep.call_count == 2
        mock_sleep.assert_called_with(5)

    @patch("network_collector.configurator.base.ConnectHandler")
    def test_zero_retries(self, mock_handler, credentials, device, commands):
        """max_retries=0 означает только одну попытку."""
        pusher = ConfigPusher(credentials=credentials, max_retries=0, retry_delay=0.1)
        mock_handler.side_effect = NetmikoTimeoutException("timeout")

        result = pusher.push_config(device, commands, dry_run=False)

        assert result.success is False
        # Только 1 попытка
        assert mock_handler.call_count == 1

    @patch("network_collector.configurator.base.ConnectHandler")
    def test_generic_exception_triggers_retry(self, mock_handler, pusher, device, commands):
        """Общие исключения тоже вызывают retry."""
        mock_conn = MagicMock()
        mock_conn.send_config_set.return_value = "ok"
        mock_conn.save_config.return_value = "ok"

        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("Network unreachable")
            cm = MagicMock()
            cm.__enter__ = MagicMock(return_value=mock_conn)
            cm.__exit__ = MagicMock(return_value=False)
            return cm

        mock_handler.side_effect = side_effect

        result = pusher.push_config(device, commands, dry_run=False)

        assert result.success is True
        assert call_count[0] == 2

    def test_empty_commands_no_connection(self, pusher, device):
        """Пустой список команд не вызывает подключение."""
        result = pusher.push_config(device, [], dry_run=False)

        assert result.success is True
        assert result.commands_sent == 0

    @patch("network_collector.configurator.base.ConnectHandler")
    def test_enable_mode_called_with_secret(self, mock_handler, device, commands):
        """Enable mode вызывается если есть secret."""
        creds = Credentials(username="admin", password="pass", secret="enable123")
        pusher = ConfigPusher(credentials=creds, max_retries=0)

        mock_conn = MagicMock()
        mock_conn.send_config_set.return_value = "ok"
        mock_conn.save_config.return_value = "ok"

        mock_handler.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_handler.return_value.__exit__ = MagicMock(return_value=False)

        pusher.push_config(device, commands, dry_run=False)

        mock_conn.enable.assert_called_once()

    @patch("network_collector.configurator.base.ConnectHandler")
    def test_config_saved_by_default(self, mock_handler, pusher, device, commands):
        """Конфигурация сохраняется по умолчанию."""
        mock_conn = MagicMock()
        mock_conn.send_config_set.return_value = "ok"
        mock_conn.save_config.return_value = "saved"

        mock_handler.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_handler.return_value.__exit__ = MagicMock(return_value=False)

        pusher.push_config(device, commands, dry_run=False)

        mock_conn.save_config.assert_called_once()

    @patch("network_collector.configurator.base.ConnectHandler")
    def test_config_not_saved_when_disabled(self, mock_handler, credentials, device, commands):
        """Конфигурация не сохраняется если save_config=False."""
        pusher = ConfigPusher(credentials=credentials, save_config=False, max_retries=0)

        mock_conn = MagicMock()
        mock_conn.send_config_set.return_value = "ok"

        mock_handler.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_handler.return_value.__exit__ = MagicMock(return_value=False)

        pusher.push_config(device, commands, dry_run=False)

        mock_conn.save_config.assert_not_called()
