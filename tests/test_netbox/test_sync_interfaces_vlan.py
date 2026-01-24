"""
Тесты синхронизации VLAN на интерфейсы.

Покрывает:
- Access port → untagged_vlan = access_vlan
- Trunk port → untagged_vlan = native_vlan
- VLAN не найден → пропуск без ошибки
- sync_vlans=false → не синхронизировать
- Очистка untagged_vlan если VLAN удалён с порта
"""

import pytest
from unittest.mock import MagicMock, patch
from dataclasses import dataclass
from typing import Optional


@dataclass
class MockInterface:
    """Mock Interface model."""
    name: str = "Gi0/1"
    description: str = ""
    status: str = "up"
    mode: str = ""
    access_vlan: str = ""
    native_vlan: str = ""
    mac: str = ""
    mtu: int = 0
    speed: str = ""
    duplex: str = ""
    ip_address: str = ""
    lag: str = ""
    tagged_vlans: str = ""


class MockNBInterface:
    """Mock NetBox interface."""
    def __init__(
        self,
        id: int = 1,
        name: str = "Gi0/1",
        description: str = "",
        enabled: bool = True,
        mode: Optional[str] = None,
        untagged_vlan: Optional[MagicMock] = None,
        device: Optional[MagicMock] = None,
    ):
        self.id = id
        self.name = name
        self.description = description
        self.enabled = enabled
        self.mtu = None
        self.speed = None
        self.duplex = None
        self.type = None
        self.lag = None

        # Mode как объект с value
        if mode:
            self.mode = MagicMock()
            self.mode.value = mode
        else:
            self.mode = None

        self.untagged_vlan = untagged_vlan
        self.device = device


class MockVLAN:
    """Mock VLAN object."""
    def __init__(self, id: int, vid: int, name: str = ""):
        self.id = id
        self.vid = vid
        self.name = name or f"VLAN{vid}"


class TestInterfaceVlanSync:
    """Тесты sync untagged_vlan."""

    @pytest.fixture
    def mock_sync_cfg_vlans_enabled(self):
        """Config с включенным sync_vlans."""
        cfg = MagicMock()
        cfg.is_field_enabled.return_value = True
        cfg.get_option.side_effect = lambda key, default=None: {
            "sync_vlans": True,
            "auto_detect_type": False,
            "sync_mac_only_with_ip": False,
            "enabled_mode": "admin",
        }.get(key, default)
        return cfg

    @pytest.fixture
    def mock_sync_cfg_vlans_disabled(self):
        """Config с выключенным sync_vlans."""
        cfg = MagicMock()
        cfg.is_field_enabled.return_value = True
        cfg.get_option.side_effect = lambda key, default=None: {
            "sync_vlans": False,
            "auto_detect_type": False,
            "sync_mac_only_with_ip": False,
            "enabled_mode": "admin",
        }.get(key, default)
        return cfg

    def test_access_port_syncs_untagged_vlan(self, mock_sync_cfg_vlans_enabled):
        """Access port с access_vlan=10 синхронизирует untagged_vlan."""
        from network_collector.netbox.sync.interfaces import InterfacesSyncMixin

        # Создаём mock sync object
        sync = MagicMock(spec=InterfacesSyncMixin)
        sync.dry_run = False
        sync.client = MagicMock()

        # VLAN 10 существует в NetBox с id=100
        mock_vlan = MockVLAN(id=100, vid=10, name="Users")
        sync._get_vlan_by_vid = MagicMock(return_value=mock_vlan)

        # Интерфейс access port в VLAN 10
        intf = MockInterface(
            name="Gi0/1",
            mode="access",
            access_vlan="10",
        )

        # Device с site
        mock_device = MagicMock()
        mock_device.site = MagicMock()
        mock_device.site.name = "Office"

        # NetBox interface без VLAN
        nb_interface = MockNBInterface(
            id=1,
            name="Gi0/1",
            mode="access",
            untagged_vlan=None,
            device=mock_device,
        )

        with patch("network_collector.netbox.sync.interfaces.get_sync_config", return_value=mock_sync_cfg_vlans_enabled):
            result = InterfacesSyncMixin._update_interface(sync, nb_interface, intf)

        # Проверяем что update_interface был вызван с untagged_vlan=100
        sync.client.update_interface.assert_called_once()
        call_kwargs = sync.client.update_interface.call_args[1]
        assert "untagged_vlan" in call_kwargs
        assert call_kwargs["untagged_vlan"] == 100

    def test_trunk_port_syncs_native_vlan(self, mock_sync_cfg_vlans_enabled):
        """Trunk port с native_vlan=1 синхронизирует untagged_vlan."""
        from network_collector.netbox.sync.interfaces import InterfacesSyncMixin

        sync = MagicMock(spec=InterfacesSyncMixin)
        sync.dry_run = False
        sync.client = MagicMock()

        # VLAN 1 (native) существует
        mock_vlan = MockVLAN(id=50, vid=1, name="default")
        sync._get_vlan_by_vid = MagicMock(return_value=mock_vlan)

        # Trunk интерфейс с native_vlan=1
        intf = MockInterface(
            name="Gi0/24",
            mode="tagged",
            native_vlan="1",
        )

        mock_device = MagicMock()
        mock_device.site = MagicMock()
        mock_device.site.name = "DC"

        nb_interface = MockNBInterface(
            id=2,
            name="Gi0/24",
            mode="tagged",
            untagged_vlan=None,
            device=mock_device,
        )

        with patch("network_collector.netbox.sync.interfaces.get_sync_config", return_value=mock_sync_cfg_vlans_enabled):
            result = InterfacesSyncMixin._update_interface(sync, nb_interface, intf)

        sync.client.update_interface.assert_called_once()
        call_kwargs = sync.client.update_interface.call_args[1]
        assert call_kwargs["untagged_vlan"] == 50

    def test_vlan_not_found_skips_sync(self, mock_sync_cfg_vlans_enabled):
        """Если VLAN не найден в NetBox, пропускаем без ошибки."""
        from network_collector.netbox.sync.interfaces import InterfacesSyncMixin

        sync = MagicMock(spec=InterfacesSyncMixin)
        sync.dry_run = False
        sync.client = MagicMock()

        # VLAN не найден
        sync._get_vlan_by_vid = MagicMock(return_value=None)

        intf = MockInterface(
            name="Gi0/1",
            mode="access",
            access_vlan="999",  # Не существует в NetBox
        )

        mock_device = MagicMock()
        mock_device.site = MagicMock()
        mock_device.site.name = "Office"

        nb_interface = MockNBInterface(
            id=1,
            name="Gi0/1",
            mode="access",
            device=mock_device,
        )

        with patch("network_collector.netbox.sync.interfaces.get_sync_config", return_value=mock_sync_cfg_vlans_enabled):
            # Не должно быть исключения
            result = InterfacesSyncMixin._update_interface(sync, nb_interface, intf)

        # update_interface не должен быть вызван с untagged_vlan
        if sync.client.update_interface.called:
            call_kwargs = sync.client.update_interface.call_args[1]
            assert "untagged_vlan" not in call_kwargs

    def test_sync_vlans_disabled_skips(self, mock_sync_cfg_vlans_disabled):
        """Если sync_vlans=false, не синхронизируем VLAN."""
        from network_collector.netbox.sync.interfaces import InterfacesSyncMixin

        sync = MagicMock(spec=InterfacesSyncMixin)
        sync.dry_run = False
        sync.client = MagicMock()

        # VLAN существует
        mock_vlan = MockVLAN(id=100, vid=10)
        sync._get_vlan_by_vid = MagicMock(return_value=mock_vlan)

        intf = MockInterface(
            name="Gi0/1",
            mode="access",
            access_vlan="10",
        )

        mock_device = MagicMock()
        mock_device.site = None

        nb_interface = MockNBInterface(
            id=1,
            name="Gi0/1",
            mode="access",
            device=mock_device,
        )

        with patch("network_collector.netbox.sync.interfaces.get_sync_config", return_value=mock_sync_cfg_vlans_disabled):
            result = InterfacesSyncMixin._update_interface(sync, nb_interface, intf)

        # _get_vlan_by_vid НЕ должен вызываться
        sync._get_vlan_by_vid.assert_not_called()

    def test_clears_untagged_if_no_vlan(self, mock_sync_cfg_vlans_enabled):
        """Очищает untagged_vlan если на порте нет VLAN."""
        from network_collector.netbox.sync.interfaces import InterfacesSyncMixin

        sync = MagicMock(spec=InterfacesSyncMixin)
        sync.dry_run = False
        sync.client = MagicMock()

        # Интерфейс без VLAN (нет mode или access_vlan)
        intf = MockInterface(
            name="Gi0/1",
            mode="",  # Нет mode
            access_vlan="",
        )

        # В NetBox есть untagged_vlan
        existing_vlan = MagicMock()
        existing_vlan.id = 100

        mock_device = MagicMock()
        mock_device.site = None

        nb_interface = MockNBInterface(
            id=1,
            name="Gi0/1",
            untagged_vlan=existing_vlan,
            device=mock_device,
        )

        with patch("network_collector.netbox.sync.interfaces.get_sync_config", return_value=mock_sync_cfg_vlans_enabled):
            result = InterfacesSyncMixin._update_interface(sync, nb_interface, intf)

        sync.client.update_interface.assert_called_once()
        call_kwargs = sync.client.update_interface.call_args[1]
        assert "untagged_vlan" in call_kwargs
        assert call_kwargs["untagged_vlan"] is None

    def test_no_change_if_vlan_same(self, mock_sync_cfg_vlans_enabled):
        """Не обновляем если VLAN уже правильный."""
        from network_collector.netbox.sync.interfaces import InterfacesSyncMixin

        sync = MagicMock(spec=InterfacesSyncMixin)
        sync.dry_run = False
        sync.client = MagicMock()

        # VLAN 10 с id=100
        mock_vlan = MockVLAN(id=100, vid=10)
        sync._get_vlan_by_vid = MagicMock(return_value=mock_vlan)

        intf = MockInterface(
            name="Gi0/1",
            mode="access",
            access_vlan="10",
        )

        # В NetBox уже правильный VLAN
        existing_vlan = MagicMock()
        existing_vlan.id = 100  # Тот же ID

        mock_device = MagicMock()
        mock_device.site = MagicMock()
        mock_device.site.name = "Office"

        nb_interface = MockNBInterface(
            id=1,
            name="Gi0/1",
            mode="access",
            untagged_vlan=existing_vlan,
            device=mock_device,
        )

        with patch("network_collector.netbox.sync.interfaces.get_sync_config", return_value=mock_sync_cfg_vlans_enabled):
            result = InterfacesSyncMixin._update_interface(sync, nb_interface, intf)

        # Не должно быть вызова update_interface (нет изменений)
        # Но может быть вызван если другие поля изменились
        if sync.client.update_interface.called:
            call_kwargs = sync.client.update_interface.call_args[1]
            # untagged_vlan не должен быть в updates
            assert "untagged_vlan" not in call_kwargs


class TestVlanCache:
    """Тесты кэширования VLAN."""

    def test_vlan_cache_reuses_result(self):
        """Кэш возвращает тот же объект без повторного API вызова."""
        from network_collector.netbox.sync.base import SyncBase

        mock_client = MagicMock()
        mock_vlan = MockVLAN(id=100, vid=10)
        mock_client.get_vlan_by_vid.return_value = mock_vlan

        sync = SyncBase(client=mock_client, dry_run=False)

        # Первый вызов - API
        result1 = sync._get_vlan_by_vid(10, "Office")
        assert result1 == mock_vlan
        assert mock_client.get_vlan_by_vid.call_count == 1

        # Второй вызов - из кэша
        result2 = sync._get_vlan_by_vid(10, "Office")
        assert result2 == mock_vlan
        assert mock_client.get_vlan_by_vid.call_count == 1  # Не изменился

        # Другой сайт - новый вызов
        sync._get_vlan_by_vid(10, "DC")
        assert mock_client.get_vlan_by_vid.call_count == 2

    def test_vlan_cache_different_vids(self):
        """Разные VID кэшируются отдельно."""
        from network_collector.netbox.sync.base import SyncBase

        mock_client = MagicMock()
        mock_client.get_vlan_by_vid.side_effect = lambda vid, site: MockVLAN(id=vid*10, vid=vid)

        sync = SyncBase(client=mock_client, dry_run=False)

        vlan10 = sync._get_vlan_by_vid(10, "Office")
        vlan20 = sync._get_vlan_by_vid(20, "Office")

        assert vlan10.vid == 10
        assert vlan20.vid == 20
        assert mock_client.get_vlan_by_vid.call_count == 2
