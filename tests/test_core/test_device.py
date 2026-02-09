"""
Тесты для Device model — поле site.

Проверяет: per-device site из devices_ips.py, fallback на default.
"""

import pytest
from network_collector.core.device import Device


class TestDeviceSite:
    """Тесты поля site в Device."""

    def test_device_has_site_field(self):
        """Device имеет поле site."""
        device = Device(host="10.0.0.1", platform="cisco_ios")
        assert hasattr(device, "site")
        assert device.site is None

    def test_device_with_site(self):
        """Device с указанным site."""
        device = Device(host="10.0.0.1", platform="cisco_ios", site="DC-1")
        assert device.site == "DC-1"

    def test_device_from_dict_with_site(self):
        """Device.from_dict() читает site."""
        data = {
            "host": "10.0.0.1",
            "platform": "cisco_ios",
            "site": "Office",
        }
        device = Device.from_dict(data)
        assert device.site == "Office"

    def test_device_from_dict_without_site(self):
        """Device.from_dict() без site — site=None."""
        data = {
            "host": "10.0.0.1",
            "platform": "cisco_ios",
        }
        device = Device.from_dict(data)
        assert device.site is None

    def test_device_site_preserved_in_attrs(self):
        """Site сохраняется после __post_init__."""
        device = Device(
            host="10.0.0.1",
            platform="cisco_iosxe",
            device_type="C9200L",
            role="Switch",
            site="Branch-1",
        )
        assert device.site == "Branch-1"
        assert device.platform == "cisco_iosxe"
        assert device.role == "Switch"


class TestDeviceSyncPerDevice:
    """Тесты per-device site в sync_devices_from_inventory."""

    def test_device_site_overrides_default(self):
        """entry.site перезаписывает default site."""
        from unittest.mock import MagicMock
        from network_collector.netbox.sync.devices import DevicesSyncMixin

        sync = MagicMock(spec=DevicesSyncMixin)
        sync.dry_run = False
        sync.client = MagicMock()
        sync.client.get_device_by_name.return_value = None
        sync.client.get_device_by_ip.return_value = None

        # Привязываем реальные методы
        sync.create_device = MagicMock(return_value=MagicMock(id=1))
        sync.sync_devices_from_inventory = lambda *a, **kw: DevicesSyncMixin.sync_devices_from_inventory(sync, *a, **kw)

        # DeviceInfo с site="DC-2"
        device_data = [{
            "hostname": "switch-01",
            "name": "switch-01",
            "ip_address": "10.0.0.1",
            "model": "C9200L",
            "serial": "ABC123",
            "manufacturer": "Cisco",
            "platform": "cisco_iosxe",
            "site": "DC-2",
        }]

        sync.sync_devices_from_inventory(device_data, site="Main")

        # create_device вызван с site="DC-2" (из устройства), а не "Main"
        sync.create_device.assert_called_once()
        call_kwargs = sync.create_device.call_args[1]
        assert call_kwargs["site"] == "DC-2"

    def test_default_site_used_when_no_device_site(self):
        """Если у устройства нет site — используется default."""
        from unittest.mock import MagicMock
        from network_collector.netbox.sync.devices import DevicesSyncMixin

        sync = MagicMock(spec=DevicesSyncMixin)
        sync.dry_run = False
        sync.client = MagicMock()
        sync.client.get_device_by_name.return_value = None
        sync.client.get_device_by_ip.return_value = None

        sync.create_device = MagicMock(return_value=MagicMock(id=1))
        sync.sync_devices_from_inventory = lambda *a, **kw: DevicesSyncMixin.sync_devices_from_inventory(sync, *a, **kw)

        # DeviceInfo БЕЗ site
        device_data = [{
            "hostname": "switch-01",
            "name": "switch-01",
            "ip_address": "10.0.0.1",
            "model": "C9200L",
            "serial": "ABC123",
            "manufacturer": "Cisco",
            "platform": "cisco_iosxe",
        }]

        sync.sync_devices_from_inventory(device_data, site="Office")

        # create_device вызван с site="Office" (default)
        sync.create_device.assert_called_once()
        call_kwargs = sync.create_device.call_args[1]
        assert call_kwargs["site"] == "Office"
