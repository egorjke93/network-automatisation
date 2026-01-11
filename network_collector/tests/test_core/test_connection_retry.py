"""Тесты retry логики для ConnectionManager."""

import pytest
from unittest.mock import patch, MagicMock, call
import time

from scrapli.exceptions import (
    ScrapliTimeout,
    ScrapliAuthenticationFailed,
    ScrapliConnectionError,
)

from network_collector.core.connection import ConnectionManager
from network_collector.core.device import Device
from network_collector.core.credentials import Credentials
from network_collector.core.exceptions import (
    ConnectionError as CollectorConnectionError,
    AuthenticationError,
    TimeoutError as CollectorTimeoutError,
)


@pytest.fixture
def credentials():
    """Тестовые учётные данные."""
    return Credentials(username="admin", password="admin123")


@pytest.fixture
def device():
    """Тестовое устройство."""
    return Device(host="192.168.1.1", device_type="cisco_ios")


@pytest.fixture
def conn_manager():
    """ConnectionManager с быстрыми retry для тестов."""
    return ConnectionManager(
        max_retries=2,
        retry_delay=0.1,  # Быстрый retry для тестов
    )


class TestConnectionManagerRetry:
    """Тесты retry логики ConnectionManager."""

    @patch("network_collector.core.connection.Scrapli")
    def test_successful_connection_no_retry(self, mock_scrapli, conn_manager, device, credentials):
        """Успешное подключение с первой попытки - retry не нужен."""
        mock_conn = MagicMock()
        mock_scrapli.return_value = mock_conn

        with conn_manager.connect(device, credentials) as conn:
            assert conn == mock_conn

        # Scrapli вызван только 1 раз
        assert mock_scrapli.call_count == 1
        mock_conn.open.assert_called_once()
        # close вызывается в finally блоке (может быть несколько раз)
        assert mock_conn.close.called

    @patch("network_collector.core.connection.Scrapli")
    def test_timeout_triggers_retry(self, mock_scrapli, conn_manager, device, credentials):
        """Timeout вызывает retry."""
        mock_conn = MagicMock()
        # Первые 2 попытки - timeout, третья успешна
        mock_scrapli.return_value = mock_conn
        mock_conn.open.side_effect = [
            ScrapliTimeout("Connection timed out"),
            ScrapliTimeout("Connection timed out"),
            None,  # Успех на 3-й попытке
        ]

        with conn_manager.connect(device, credentials) as conn:
            assert conn == mock_conn

        # 3 попытки (1 + 2 retry)
        assert mock_conn.open.call_count == 3

    @patch("network_collector.core.connection.Scrapli")
    def test_connection_error_triggers_retry(self, mock_scrapli, conn_manager, device, credentials):
        """Connection error вызывает retry."""
        mock_conn = MagicMock()
        mock_scrapli.return_value = mock_conn
        # Первая попытка - ошибка, вторая успешна
        mock_conn.open.side_effect = [
            ScrapliConnectionError("Connection refused"),
            None,
        ]

        with conn_manager.connect(device, credentials) as conn:
            assert conn == mock_conn

        assert mock_conn.open.call_count == 2

    @patch("network_collector.core.connection.Scrapli")
    def test_auth_error_no_retry(self, mock_scrapli, conn_manager, device, credentials):
        """AuthenticationError НЕ вызывает retry."""
        mock_conn = MagicMock()
        mock_scrapli.return_value = mock_conn
        mock_conn.open.side_effect = ScrapliAuthenticationFailed("Bad credentials")

        with pytest.raises(AuthenticationError):
            with conn_manager.connect(device, credentials):
                pass

        # Только 1 попытка - без retry
        assert mock_conn.open.call_count == 1

    @patch("network_collector.core.connection.Scrapli")
    def test_all_retries_exhausted_raises_timeout(self, mock_scrapli, conn_manager, device, credentials):
        """После исчерпания всех попыток выбрасывается TimeoutError."""
        mock_conn = MagicMock()
        mock_scrapli.return_value = mock_conn
        # Все попытки - timeout
        mock_conn.open.side_effect = ScrapliTimeout("Connection timed out")

        with pytest.raises(CollectorTimeoutError) as exc_info:
            with conn_manager.connect(device, credentials):
                pass

        assert "Таймаут подключения" in str(exc_info.value)
        # 3 попытки (1 + 2 retry)
        assert mock_conn.open.call_count == 3

    @patch("network_collector.core.connection.Scrapli")
    def test_all_retries_exhausted_raises_connection_error(self, mock_scrapli, conn_manager, device, credentials):
        """После исчерпания всех попыток выбрасывается ConnectionError."""
        mock_conn = MagicMock()
        mock_scrapli.return_value = mock_conn
        mock_conn.open.side_effect = ScrapliConnectionError("Connection refused")

        with pytest.raises(CollectorConnectionError) as exc_info:
            with conn_manager.connect(device, credentials):
                pass

        assert "Ошибка подключения" in str(exc_info.value)
        assert mock_conn.open.call_count == 3

    @patch("network_collector.core.connection.time.sleep")
    @patch("network_collector.core.connection.Scrapli")
    def test_retry_delay_is_applied(self, mock_scrapli, mock_sleep, device, credentials):
        """Между retry применяется задержка."""
        conn_manager = ConnectionManager(max_retries=2, retry_delay=5)

        mock_conn = MagicMock()
        mock_scrapli.return_value = mock_conn
        mock_conn.open.side_effect = [
            ScrapliTimeout("timeout"),
            ScrapliTimeout("timeout"),
            None,
        ]

        with conn_manager.connect(device, credentials):
            pass

        # sleep вызван 2 раза (перед 2-й и 3-й попыткой)
        assert mock_sleep.call_count == 2
        mock_sleep.assert_called_with(5)

    @patch("network_collector.core.connection.Scrapli")
    def test_zero_retries_no_retry(self, mock_scrapli, device, credentials):
        """max_retries=0 означает только одну попытку."""
        conn_manager = ConnectionManager(max_retries=0, retry_delay=0.1)

        mock_conn = MagicMock()
        mock_scrapli.return_value = mock_conn
        mock_conn.open.side_effect = ScrapliTimeout("timeout")

        with pytest.raises(CollectorTimeoutError):
            with conn_manager.connect(device, credentials):
                pass

        # Только 1 попытка
        assert mock_conn.open.call_count == 1

    @patch("network_collector.core.connection.Scrapli")
    def test_device_status_updated_on_success(self, mock_scrapli, conn_manager, device, credentials):
        """Статус устройства обновляется при успехе."""
        from network_collector.core.device import DeviceStatus

        mock_conn = MagicMock()
        mock_scrapli.return_value = mock_conn

        with conn_manager.connect(device, credentials):
            pass

        assert device.status == DeviceStatus.ONLINE

    @patch("network_collector.core.connection.Scrapli")
    def test_device_status_updated_on_failure(self, mock_scrapli, conn_manager, device, credentials):
        """Статус устройства обновляется при неудаче."""
        from network_collector.core.device import DeviceStatus

        mock_conn = MagicMock()
        mock_scrapli.return_value = mock_conn
        mock_conn.open.side_effect = ScrapliTimeout("timeout")

        with pytest.raises(CollectorTimeoutError):
            with conn_manager.connect(device, credentials):
                pass

        assert device.status == DeviceStatus.OFFLINE

    @patch("network_collector.core.connection.Scrapli")
    def test_connection_closed_on_partial_failure(self, mock_scrapli, conn_manager, device, credentials):
        """Соединение закрывается даже при частичной ошибке."""
        mock_conn = MagicMock()
        mock_scrapli.return_value = mock_conn
        # open успешен, но потом ошибка
        mock_conn.open.side_effect = [None, ScrapliTimeout("timeout"), None]

        # Симулируем что первое соединение было открыто но потом закрыто
        with conn_manager.connect(device, credentials):
            pass

        mock_conn.close.assert_called()
