"""
E2E тесты для параллельного сбора с нескольких устройств.

Проверяет:
- Параллельный сбор: ThreadPoolExecutor, futures
- Частичный отказ: 1 из N устройств недоступен
- Timeout на одном устройстве не блокирует остальные
- Результат содержит данные только от успешных устройств

Без реального SSH подключения — мокаем BaseCollector._collect_from_device.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from concurrent.futures import ThreadPoolExecutor

from network_collector.collectors.interfaces import InterfaceCollector
from network_collector.collectors.inventory import InventoryCollector
from network_collector.core.device import Device
from network_collector.core.models import Interface, InventoryItem
from network_collector.core.exceptions import ConnectionError, TimeoutError

from .conftest import create_mock_device


# =============================================================================
# Parallel Collection
# =============================================================================


class TestParallelCollection:
    """Тесты параллельного сбора данных."""

    def test_multiple_devices_all_success(self):
        """Все устройства доступны — все данные собраны."""
        devices = [
            create_mock_device("cisco_ios", "ios-1", "10.0.0.1"),
            create_mock_device("cisco_ios", "ios-2", "10.0.0.2"),
            create_mock_device("cisco_nxos", "nxos-1", "10.0.0.3"),
        ]

        # Мокаем _collect_from_device для каждого устройства
        mock_data = {
            "10.0.0.1": [
                {"interface": "Gi0/1", "status": "up", "hostname": "ios-1", "device_ip": "10.0.0.1"},
                {"interface": "Gi0/2", "status": "down", "hostname": "ios-1", "device_ip": "10.0.0.1"},
            ],
            "10.0.0.2": [
                {"interface": "Gi0/1", "status": "up", "hostname": "ios-2", "device_ip": "10.0.0.2"},
            ],
            "10.0.0.3": [
                {"interface": "Eth1/1", "status": "up", "hostname": "nxos-1", "device_ip": "10.0.0.3"},
                {"interface": "Eth1/2", "status": "up", "hostname": "nxos-1", "device_ip": "10.0.0.3"},
            ],
        }

        collector = InterfaceCollector(
            credentials=None,
            collect_lag_info=False,
            collect_switchport=False,
            collect_media_type=False,
        )

        def fake_collect(device):
            return mock_data.get(device.host, [])

        with patch.object(collector, '_collect_from_device', side_effect=fake_collect):
            result = collector.collect_dicts(devices, parallel=True)

        # Все 5 записей собраны
        assert len(result) == 5

        # Данные от всех 3 устройств
        hostnames = {r["hostname"] for r in result}
        assert hostnames == {"ios-1", "ios-2", "nxos-1"}

    def test_multiple_devices_sequential(self):
        """Последовательный сбор (parallel=False) тоже работает."""
        devices = [
            create_mock_device("cisco_ios", "ios-1", "10.0.0.1"),
            create_mock_device("cisco_ios", "ios-2", "10.0.0.2"),
        ]

        mock_data = {
            "10.0.0.1": [{"interface": "Gi0/1", "status": "up", "hostname": "ios-1", "device_ip": "10.0.0.1"}],
            "10.0.0.2": [{"interface": "Gi0/1", "status": "up", "hostname": "ios-2", "device_ip": "10.0.0.2"}],
        }

        collector = InterfaceCollector(
            credentials=None,
            collect_lag_info=False,
            collect_switchport=False,
            collect_media_type=False,
        )

        def fake_collect(device):
            return mock_data.get(device.host, [])

        with patch.object(collector, '_collect_from_device', side_effect=fake_collect):
            result = collector.collect_dicts(devices, parallel=False)

        assert len(result) == 2


# =============================================================================
# Partial Failures
# =============================================================================


class TestPartialFailures:
    """Тесты частичного отказа устройств."""

    def test_one_device_fails_others_succeed(self):
        """1 из 3 устройств недоступен — остальные данные собраны."""
        devices = [
            create_mock_device("cisco_ios", "ios-1", "10.0.0.1"),
            create_mock_device("cisco_ios", "ios-2", "10.0.0.2"),
            create_mock_device("cisco_ios", "ios-3", "10.0.0.3"),
        ]

        def fake_collect(device):
            if device.host == "10.0.0.2":
                raise ConnectionError(f"Cannot connect to {device.host}")
            return [{"interface": "Gi0/1", "status": "up", "hostname": device.hostname, "device_ip": device.host}]

        collector = InterfaceCollector(
            credentials=None,
            collect_lag_info=False,
            collect_switchport=False,
            collect_media_type=False,
        )

        with patch.object(collector, '_collect_from_device', side_effect=fake_collect):
            result = collector.collect_dicts(devices, parallel=True)

        # 2 из 3 устройств успешны
        assert len(result) == 2
        hostnames = {r["hostname"] for r in result}
        assert "ios-2" not in hostnames
        assert "ios-1" in hostnames
        assert "ios-3" in hostnames

    def test_all_devices_fail(self):
        """Все устройства недоступны — пустой результат."""
        devices = [
            create_mock_device("cisco_ios", "ios-1", "10.0.0.1"),
            create_mock_device("cisco_ios", "ios-2", "10.0.0.2"),
        ]

        def fake_collect(device):
            raise ConnectionError(f"Cannot connect to {device.host}")

        collector = InterfaceCollector(
            credentials=None,
            collect_lag_info=False,
            collect_switchport=False,
            collect_media_type=False,
        )

        with patch.object(collector, '_collect_from_device', side_effect=fake_collect):
            result = collector.collect_dicts(devices, parallel=True)

        assert len(result) == 0

    def test_timeout_does_not_block_others(self):
        """Timeout на одном устройстве не блокирует остальные."""
        devices = [
            create_mock_device("cisco_ios", "ios-1", "10.0.0.1"),
            create_mock_device("cisco_ios", "ios-2", "10.0.0.2"),
        ]

        def fake_collect(device):
            if device.host == "10.0.0.1":
                raise TimeoutError(f"Connection timed out: {device.host}")
            return [{"interface": "Gi0/1", "status": "up", "hostname": device.hostname, "device_ip": device.host}]

        collector = InterfaceCollector(
            credentials=None,
            collect_lag_info=False,
            collect_switchport=False,
            collect_media_type=False,
        )

        with patch.object(collector, '_collect_from_device', side_effect=fake_collect):
            result = collector.collect_dicts(devices, parallel=True)

        # Только ios-2 успешен
        assert len(result) == 1
        assert result[0]["hostname"] == "ios-2"

    def test_empty_result_from_device(self):
        """Устройство возвращает пустой результат — не ошибка."""
        devices = [
            create_mock_device("cisco_ios", "ios-1", "10.0.0.1"),
            create_mock_device("cisco_ios", "ios-2", "10.0.0.2"),
        ]

        def fake_collect(device):
            if device.host == "10.0.0.1":
                return []  # Пустой результат (но не ошибка)
            return [{"interface": "Gi0/1", "status": "up", "hostname": device.hostname, "device_ip": device.host}]

        collector = InterfaceCollector(
            credentials=None,
            collect_lag_info=False,
            collect_switchport=False,
            collect_media_type=False,
        )

        with patch.object(collector, '_collect_from_device', side_effect=fake_collect):
            result = collector.collect_dicts(devices, parallel=True)

        assert len(result) == 1


# =============================================================================
# Progress Callback
# =============================================================================


class TestProgressCallback:
    """Тесты callback для отслеживания прогресса."""

    def test_progress_callback_called(self):
        """Progress callback вызывается для каждого устройства."""
        devices = [
            create_mock_device("cisco_ios", "ios-1", "10.0.0.1"),
            create_mock_device("cisco_ios", "ios-2", "10.0.0.2"),
        ]

        progress_calls = []

        def progress_cb(current, total, host, success):
            progress_calls.append((current, total, host, success))

        def fake_collect(device):
            return [{"interface": "Gi0/1", "status": "up", "hostname": device.hostname, "device_ip": device.host}]

        collector = InterfaceCollector(
            credentials=None,
            collect_lag_info=False,
            collect_switchport=False,
            collect_media_type=False,
        )

        with patch.object(collector, '_collect_from_device', side_effect=fake_collect):
            collector.collect_dicts(devices, parallel=True, progress_callback=progress_cb)

        # Callback вызван 2 раза (по одному на устройство)
        assert len(progress_calls) == 2
        # total всегда 2
        assert all(call[1] == 2 for call in progress_calls)

    def test_progress_callback_with_failure(self):
        """Progress callback отмечает неуспешные устройства."""
        devices = [
            create_mock_device("cisco_ios", "ios-1", "10.0.0.1"),
            create_mock_device("cisco_ios", "ios-2", "10.0.0.2"),
        ]

        progress_calls = []

        def progress_cb(current, total, host, success):
            progress_calls.append({"host": host, "success": success})

        def fake_collect(device):
            if device.host == "10.0.0.1":
                raise ConnectionError(f"Fail: {device.host}")
            return [{"interface": "Gi0/1", "status": "up", "hostname": device.hostname, "device_ip": device.host}]

        collector = InterfaceCollector(
            credentials=None,
            collect_lag_info=False,
            collect_switchport=False,
            collect_media_type=False,
        )

        with patch.object(collector, '_collect_from_device', side_effect=fake_collect):
            collector.collect_dicts(devices, parallel=True, progress_callback=progress_cb)

        assert len(progress_calls) == 2


# =============================================================================
# Inventory Multi-Device Collection
# =============================================================================


class TestInventoryMultiDevice:
    """Тесты параллельного сбора inventory с нескольких устройств."""

    def test_inventory_multiple_devices(self):
        """Inventory собирается с нескольких устройств."""
        devices = [
            create_mock_device("cisco_ios", "ios-1", "10.0.0.1"),
            create_mock_device("cisco_nxos", "nxos-1", "10.0.0.2"),
        ]

        mock_data = {
            "10.0.0.1": [
                {"name": "Switch 1", "pid": "WS-C3750", "serial": "SN1", "hostname": "ios-1", "device_ip": "10.0.0.1"},
            ],
            "10.0.0.2": [
                {"name": "Nexus Module", "pid": "N9K-X9736", "serial": "SN2", "hostname": "nxos-1", "device_ip": "10.0.0.2"},
                {"name": "PSU-1", "pid": "NXA-PAC-1100W", "serial": "SN3", "hostname": "nxos-1", "device_ip": "10.0.0.2"},
            ],
        }

        collector = InventoryCollector(
            credentials=None,
            collect_transceivers=False,
        )

        def fake_collect(device):
            return mock_data.get(device.host, [])

        with patch.object(collector, '_collect_from_device', side_effect=fake_collect):
            result = collector.collect_dicts(devices, parallel=True)

        # 3 записи суммарно
        assert len(result) == 3

        # Данные от обоих устройств
        hostnames = {r["hostname"] for r in result}
        assert hostnames == {"ios-1", "nxos-1"}

    def test_inventory_partial_failure(self):
        """Inventory: один из коллекторов падает — остальные работают."""
        devices = [
            create_mock_device("cisco_ios", "ios-1", "10.0.0.1"),
            create_mock_device("cisco_nxos", "nxos-1", "10.0.0.2"),
        ]

        def fake_collect(device):
            if device.host == "10.0.0.2":
                raise ConnectionError("NX-OS unreachable")
            return [{"name": "Switch 1", "pid": "WS-C3750", "serial": "SN1", "hostname": "ios-1", "device_ip": "10.0.0.1"}]

        collector = InventoryCollector(
            credentials=None,
            collect_transceivers=False,
        )

        with patch.object(collector, '_collect_from_device', side_effect=fake_collect):
            result = collector.collect_dicts(devices, parallel=True)

        # Только данные от ios-1
        assert len(result) == 1
        assert result[0]["hostname"] == "ios-1"


# =============================================================================
# Single Device Edge Cases
# =============================================================================


class TestSingleDeviceEdgeCases:
    """Edge cases для сбора с одного устройства."""

    def test_single_device_no_parallel(self):
        """Один устройство: parallel=True → последовательный сбор (оптимизация)."""
        devices = [
            create_mock_device("cisco_ios", "ios-1", "10.0.0.1"),
        ]

        def fake_collect(device):
            return [{"interface": "Gi0/1", "status": "up", "hostname": "ios-1", "device_ip": "10.0.0.1"}]

        collector = InterfaceCollector(
            credentials=None,
            collect_lag_info=False,
            collect_switchport=False,
            collect_media_type=False,
        )

        with patch.object(collector, '_collect_from_device', side_effect=fake_collect):
            result = collector.collect_dicts(devices, parallel=True)

        assert len(result) == 1

    def test_empty_device_list(self):
        """Пустой список устройств — пустой результат."""
        collector = InterfaceCollector(
            credentials=None,
            collect_lag_info=False,
            collect_switchport=False,
            collect_media_type=False,
        )

        with patch.object(collector, '_collect_from_device', return_value=[]):
            result = collector.collect_dicts([], parallel=True)

        assert len(result) == 0
