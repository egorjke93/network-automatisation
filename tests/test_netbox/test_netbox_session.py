"""
Тесты NetBoxSession: timeout и retry 429.
"""

import time
from unittest.mock import patch, MagicMock, PropertyMock

import pytest
import requests

from network_collector.netbox.client.base import (
    NetBoxSession,
    MAX_RETRIES_429,
    DEFAULT_RETRY_DELAY,
)


class TestNetBoxSessionTimeout:
    """Тесты таймаута."""

    def test_default_timeout(self):
        """Сессия создаётся с таймаутом по умолчанию."""
        session = NetBoxSession()
        assert session.timeout == 30

    def test_custom_timeout(self):
        """Сессия принимает кастомный таймаут."""
        session = NetBoxSession(timeout=60)
        assert session.timeout == 60

    def test_timeout_applied_to_requests(self):
        """Таймаут передаётся в kwargs запроса."""
        session = NetBoxSession(timeout=15)
        with patch.object(requests.Session, "request") as mock_req:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_req.return_value = mock_response

            session.request("GET", "http://localhost/api/")

            # Проверяем что timeout передан
            _, kwargs = mock_req.call_args
            assert kwargs.get("timeout") == 15

    def test_explicit_timeout_not_overridden(self):
        """Явный timeout в kwargs не перезаписывается."""
        session = NetBoxSession(timeout=15)
        with patch.object(requests.Session, "request") as mock_req:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_req.return_value = mock_response

            session.request("GET", "http://localhost/api/", timeout=60)

            _, kwargs = mock_req.call_args
            assert kwargs.get("timeout") == 60

    def test_ssl_verify_setting(self):
        """SSL verify устанавливается при создании."""
        session = NetBoxSession(verify=False)
        assert session.verify is False

        session2 = NetBoxSession(verify=True)
        assert session2.verify is True


class TestNetBoxSessionRetry429:
    """Тесты retry при HTTP 429."""

    def test_no_retry_on_200(self):
        """Нет retry при успешном ответе."""
        session = NetBoxSession()
        with patch.object(requests.Session, "request") as mock_req:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_req.return_value = mock_response

            result = session.request("GET", "http://localhost/api/")

            assert result.status_code == 200
            assert mock_req.call_count == 1

    def test_no_retry_on_500(self):
        """Нет retry при серверной ошибке (не 429)."""
        session = NetBoxSession()
        with patch.object(requests.Session, "request") as mock_req:
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_req.return_value = mock_response

            result = session.request("GET", "http://localhost/api/")

            assert result.status_code == 500
            assert mock_req.call_count == 1

    @patch("network_collector.netbox.client.base.time.sleep")
    def test_retry_on_429_then_success(self, mock_sleep):
        """Retry при 429, затем успех."""
        session = NetBoxSession()

        response_429 = MagicMock()
        response_429.status_code = 429
        response_429.headers = {}

        response_200 = MagicMock()
        response_200.status_code = 200

        with patch.object(
            requests.Session, "request", side_effect=[response_429, response_200]
        ) as mock_req:
            result = session.request("GET", "http://localhost/api/")

            assert result.status_code == 200
            assert mock_req.call_count == 2
            mock_sleep.assert_called_once()

    @patch("network_collector.netbox.client.base.time.sleep")
    def test_retry_respects_retry_after_header(self, mock_sleep):
        """Используется Retry-After header для задержки."""
        session = NetBoxSession()

        response_429 = MagicMock()
        response_429.status_code = 429
        response_429.headers = {"Retry-After": "5"}

        response_200 = MagicMock()
        response_200.status_code = 200

        with patch.object(
            requests.Session, "request", side_effect=[response_429, response_200]
        ):
            session.request("GET", "http://localhost/api/")

            mock_sleep.assert_called_once_with(5)

    @patch("network_collector.netbox.client.base.time.sleep")
    def test_exponential_backoff_without_retry_after(self, mock_sleep):
        """Экспоненциальный backoff без Retry-After."""
        session = NetBoxSession()

        response_429 = MagicMock()
        response_429.status_code = 429
        response_429.headers = {}

        response_200 = MagicMock()
        response_200.status_code = 200

        with patch.object(
            requests.Session,
            "request",
            side_effect=[response_429, response_429, response_200],
        ):
            session.request("GET", "http://localhost/api/")

            # attempt=1: delay=2*1=2, attempt=2: delay=2*2=4
            assert mock_sleep.call_count == 2
            mock_sleep.assert_any_call(DEFAULT_RETRY_DELAY * 1)
            mock_sleep.assert_any_call(DEFAULT_RETRY_DELAY * 2)

    @patch("network_collector.netbox.client.base.time.sleep")
    def test_max_retries_exhausted(self, mock_sleep):
        """Возвращает 429 после исчерпания попыток."""
        session = NetBoxSession()

        response_429 = MagicMock()
        response_429.status_code = 429
        response_429.headers = {}

        with patch.object(
            requests.Session,
            "request",
            return_value=response_429,
        ) as mock_req:
            result = session.request("GET", "http://localhost/api/")

            assert result.status_code == 429
            assert mock_req.call_count == MAX_RETRIES_429
            assert mock_sleep.call_count == MAX_RETRIES_429


class TestNetBoxClientBaseTimeout:
    """Тесты что NetBoxClientBase использует timeout из конфига."""

    @patch("network_collector.netbox.client.base.pynetbox")
    @patch("network_collector.core.credentials.get_netbox_token", return_value="test-token")
    def test_timeout_from_config(self, mock_token, mock_pynetbox):
        """Timeout берётся из config.netbox.timeout."""
        mock_api = MagicMock()
        mock_pynetbox.api.return_value = mock_api

        with patch("network_collector.netbox.client.base.os.environ", {"NETBOX_URL": "http://test"}):
            with patch("network_collector.config.config") as mock_config:
                mock_config.netbox = MagicMock()
                mock_config.netbox.timeout = 45

                from network_collector.netbox.client.base import NetBoxClientBase
                client = NetBoxClientBase(url="http://test", token="test-token")

                # Проверяем что сессия получила timeout из конфига
                session = mock_api.http_session
                assert isinstance(session, NetBoxSession)
                assert session.timeout == 45

    @patch("network_collector.netbox.client.base.pynetbox")
    @patch("network_collector.core.credentials.get_netbox_token", return_value="test-token")
    def test_explicit_timeout_overrides_config(self, mock_token, mock_pynetbox):
        """Явный timeout перезаписывает конфиг."""
        mock_api = MagicMock()
        mock_pynetbox.api.return_value = mock_api

        from network_collector.netbox.client.base import NetBoxClientBase
        client = NetBoxClientBase(url="http://test", token="test-token", timeout=90)

        session = mock_api.http_session
        assert isinstance(session, NetBoxSession)
        assert session.timeout == 90
