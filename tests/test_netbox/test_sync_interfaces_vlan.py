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
        tagged_vlans: Optional[list] = None,
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
        self.tagged_vlans = tagged_vlans
        self.device = device


class MockVLAN:
    """Mock VLAN object."""
    def __init__(self, id: int, vid: int, name: str = ""):
        self.id = id
        self.vid = vid
        self.name = name or f"VLAN{vid}"


def bind_mixin_methods(mock_obj, mixin_class, method_names):
    """Привязывает реальные методы mixin к mock объекту."""
    for name in method_names:
        method = getattr(mixin_class, name)
        setattr(mock_obj, name, lambda *args, _m=method, **kw: _m(mock_obj, *args, **kw))
    # Инициализируем кэши SyncBase, которые используют _check_* хелперы
    if not hasattr(mock_obj, '_vlan_id_to_vid') or isinstance(getattr(mock_obj, '_vlan_id_to_vid', None), type(mock_obj)):
        mock_obj._vlan_id_to_vid = {}


# Все методы InterfacesSyncMixin, которые нужно привязать к mock
INTERFACE_SYNC_METHODS = [
    '_build_update_data', '_build_create_data',
    '_check_type', '_check_description', '_check_enabled', '_check_mac',
    '_check_mtu', '_check_speed', '_check_duplex', '_check_mode',
    '_check_untagged_vlan', '_check_tagged_vlans', '_check_lag',
]


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
        bind_mixin_methods(sync, InterfacesSyncMixin, INTERFACE_SYNC_METHODS)

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
        bind_mixin_methods(sync, InterfacesSyncMixin, INTERFACE_SYNC_METHODS)

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
        bind_mixin_methods(sync, InterfacesSyncMixin, INTERFACE_SYNC_METHODS)

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
        bind_mixin_methods(sync, InterfacesSyncMixin, INTERFACE_SYNC_METHODS)

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
        bind_mixin_methods(sync, InterfacesSyncMixin, INTERFACE_SYNC_METHODS)

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
        bind_mixin_methods(sync, InterfacesSyncMixin, INTERFACE_SYNC_METHODS)

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
        # get_vlans возвращает все VLAN сайта
        mock_client.get_vlans.return_value = [mock_vlan]

        sync = SyncBase(client=mock_client, dry_run=False)

        # Первый вызов - загружает все VLAN сайта
        result1 = sync._get_vlan_by_vid(10, "Office")
        assert result1 == mock_vlan
        assert mock_client.get_vlans.call_count == 1

        # Второй вызов - из кэша
        result2 = sync._get_vlan_by_vid(10, "Office")
        assert result2 == mock_vlan
        assert mock_client.get_vlans.call_count == 1  # Не изменился

        # Другой сайт - новый вызов get_vlans
        mock_client.get_vlans.return_value = [MockVLAN(id=200, vid=10)]
        sync._get_vlan_by_vid(10, "DC")
        assert mock_client.get_vlans.call_count == 2

    def test_vlan_cache_different_vids(self):
        """Разные VID кэшируются отдельно."""
        from network_collector.netbox.sync.base import SyncBase

        mock_client = MagicMock()
        # get_vlans возвращает несколько VLAN
        mock_client.get_vlans.return_value = [
            MockVLAN(id=100, vid=10),
            MockVLAN(id=200, vid=20),
        ]

        sync = SyncBase(client=mock_client, dry_run=False)

        vlan10 = sync._get_vlan_by_vid(10, "Office")
        vlan20 = sync._get_vlan_by_vid(20, "Office")

        assert vlan10.vid == 10
        assert vlan20.vid == 20
        # Только один вызов get_vlans для сайта
        assert mock_client.get_vlans.call_count == 1


class TestParseVlanRange:
    """Тесты парсинга диапазонов VLAN (проверяет domain layer)."""

    def test_parse_single_vlan(self):
        """Одиночный VLAN."""
        from network_collector.core.domain.vlan import parse_vlan_range

        result = parse_vlan_range("10")
        assert result == [10]

    def test_parse_multiple_vlans(self):
        """Несколько VLAN через запятую."""
        from network_collector.core.domain.vlan import parse_vlan_range

        result = parse_vlan_range("10,20,30")
        assert result == [10, 20, 30]

    def test_parse_vlan_range(self):
        """Диапазон VLAN."""
        from network_collector.core.domain.vlan import parse_vlan_range

        result = parse_vlan_range("10-15")
        assert result == [10, 11, 12, 13, 14, 15]

    def test_parse_mixed_vlans_and_ranges(self):
        """Комбинация VLAN и диапазонов."""
        from network_collector.core.domain.vlan import parse_vlan_range

        result = parse_vlan_range("10,20-25,30")
        assert result == [10, 20, 21, 22, 23, 24, 25, 30]

    def test_parse_all_returns_empty(self):
        """'all' возвращает пустой список."""
        from network_collector.core.domain.vlan import parse_vlan_range

        assert parse_vlan_range("all") == []
        assert parse_vlan_range("ALL") == []

    def test_parse_full_range_returns_empty(self):
        """Полный диапазон (1-4094) возвращает пустой список."""
        from network_collector.core.domain.vlan import parse_vlan_range

        assert parse_vlan_range("1-4094") == []
        assert parse_vlan_range("1-4093") == []

    def test_parse_empty_string(self):
        """Пустая строка возвращает пустой список."""
        from network_collector.core.domain.vlan import parse_vlan_range

        assert parse_vlan_range("") == []

    def test_parse_removes_duplicates(self):
        """Удаляет дубликаты."""
        from network_collector.core.domain.vlan import parse_vlan_range

        result = parse_vlan_range("10,10,20,10-12")
        assert result == [10, 11, 12, 20]


class TestTaggedVlansSync:
    """Тесты синхронизации tagged_vlans."""

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

    def test_trunk_port_syncs_tagged_vlans(self, mock_sync_cfg_vlans_enabled):
        """Trunk port с tagged_vlans синхронизирует список VLAN."""
        from network_collector.netbox.sync.interfaces import InterfacesSyncMixin

        sync = MagicMock(spec=InterfacesSyncMixin)
        sync.dry_run = False
        sync.client = MagicMock()
        bind_mixin_methods(sync, InterfacesSyncMixin, INTERFACE_SYNC_METHODS)

        # VLANs 10, 20, 30 существуют в NetBox
        def get_vlan(vid, site):
            return MockVLAN(id=vid * 10, vid=vid)

        sync._get_vlan_by_vid = MagicMock(side_effect=get_vlan)
        sync._parse_vlan_range = MagicMock(return_value=[10, 20, 30])

        # Trunk интерфейс с tagged_vlans
        intf = MockInterface(
            name="Gi0/24",
            mode="tagged",
            native_vlan="1",
            tagged_vlans="10,20,30",
        )

        mock_device = MagicMock()
        mock_device.site = MagicMock()
        mock_device.site.name = "Office"

        nb_interface = MockNBInterface(
            id=2,
            name="Gi0/24",
            mode="tagged",
            device=mock_device,
        )
        nb_interface.tagged_vlans = None  # Нет tagged_vlans

        with patch("network_collector.netbox.sync.interfaces.get_sync_config", return_value=mock_sync_cfg_vlans_enabled):
            result = InterfacesSyncMixin._update_interface(sync, nb_interface, intf)

        sync.client.update_interface.assert_called_once()
        call_kwargs = sync.client.update_interface.call_args[1]
        assert "tagged_vlans" in call_kwargs
        assert call_kwargs["tagged_vlans"] == [100, 200, 300]  # VID * 10

    def test_access_port_clears_tagged_vlans(self, mock_sync_cfg_vlans_enabled):
        """Access port очищает tagged_vlans если они были."""
        from network_collector.netbox.sync.interfaces import InterfacesSyncMixin

        sync = MagicMock(spec=InterfacesSyncMixin)
        sync.dry_run = False
        sync.client = MagicMock()
        bind_mixin_methods(sync, InterfacesSyncMixin, INTERFACE_SYNC_METHODS)
        sync._get_vlan_by_vid = MagicMock(return_value=MockVLAN(id=100, vid=10))

        # Access интерфейс
        intf = MockInterface(
            name="Gi0/1",
            mode="access",
            access_vlan="10",
        )

        mock_device = MagicMock()
        mock_device.site = MagicMock()
        mock_device.site.name = "Office"

        # В NetBox есть tagged_vlans (ошибка - access port не должен иметь tagged)
        mock_vlan_200 = MagicMock(id=200, vid=20)
        mock_vlan_300 = MagicMock(id=300, vid=30)
        existing_tagged = [mock_vlan_200, mock_vlan_300]

        nb_interface = MockNBInterface(
            id=1,
            name="Gi0/1",
            mode="access",
            device=mock_device,
        )
        nb_interface.tagged_vlans = existing_tagged

        with patch("network_collector.netbox.sync.interfaces.get_sync_config", return_value=mock_sync_cfg_vlans_enabled):
            result = InterfacesSyncMixin._update_interface(sync, nb_interface, intf)

        sync.client.update_interface.assert_called_once()
        call_kwargs = sync.client.update_interface.call_args[1]
        assert "tagged_vlans" in call_kwargs
        assert call_kwargs["tagged_vlans"] == []  # Очищено

    def test_tagged_all_does_not_sync_list(self, mock_sync_cfg_vlans_enabled):
        """tagged-all не синхронизирует список VLAN (пустой)."""
        from network_collector.netbox.sync.interfaces import InterfacesSyncMixin

        sync = MagicMock(spec=InterfacesSyncMixin)
        sync.dry_run = False
        sync.client = MagicMock()
        bind_mixin_methods(sync, InterfacesSyncMixin, INTERFACE_SYNC_METHODS)
        sync._get_vlan_by_vid = MagicMock(return_value=MockVLAN(id=10, vid=1))

        # tagged-all интерфейс
        intf = MockInterface(
            name="Gi0/24",
            mode="tagged-all",
            native_vlan="1",
            tagged_vlans="",  # Пусто для tagged-all
        )

        mock_device = MagicMock()
        mock_device.site = MagicMock()
        mock_device.site.name = "Office"

        nb_interface = MockNBInterface(
            id=2,
            name="Gi0/24",
            mode="tagged-all",
            device=mock_device,
        )
        nb_interface.tagged_vlans = None

        with patch("network_collector.netbox.sync.interfaces.get_sync_config", return_value=mock_sync_cfg_vlans_enabled):
            result = InterfacesSyncMixin._update_interface(sync, nb_interface, intf)

        # tagged_vlans не должен быть в updates
        if sync.client.update_interface.called:
            call_kwargs = sync.client.update_interface.call_args[1]
            assert "tagged_vlans" not in call_kwargs


class TestModeClearOnShutdown:
    """Тесты очищения mode для shutdown портов."""

    @pytest.fixture
    def mock_sync_cfg(self):
        """Config со всеми включёнными полями."""
        cfg = MagicMock()
        cfg.is_field_enabled.return_value = True
        cfg.get_option.side_effect = lambda key, default=None: {
            "sync_vlans": True,
            "auto_detect_type": False,
            "sync_mac_only_with_ip": False,
            "enabled_mode": "admin",
        }.get(key, default)
        return cfg

    def test_empty_mode_clears_netbox_mode(self, mock_sync_cfg):
        """Если mode на устройстве пустой, очищаем mode в NetBox."""
        from network_collector.netbox.sync.interfaces import InterfacesSyncMixin

        sync = MagicMock(spec=InterfacesSyncMixin)
        sync.dry_run = False
        sync.client = MagicMock()
        bind_mixin_methods(sync, InterfacesSyncMixin, INTERFACE_SYNC_METHODS)

        # Shutdown интерфейс — mode пустой
        intf = MockInterface(
            name="Gi0/1",
            status="disabled",
            mode="",  # Пустой mode для shutdown порта
        )

        mock_device = MagicMock()
        mock_device.site = None

        # В NetBox mode был tagged-all
        nb_interface = MockNBInterface(
            id=1,
            name="Gi0/1",
            mode="tagged-all",
            device=mock_device,
        )

        with patch("network_collector.netbox.sync.interfaces.get_sync_config", return_value=mock_sync_cfg):
            result = InterfacesSyncMixin._update_interface(sync, nb_interface, intf)

        # Должен очистить mode
        sync.client.update_interface.assert_called_once()
        call_kwargs = sync.client.update_interface.call_args[1]
        assert "mode" in call_kwargs
        assert call_kwargs["mode"] == ""

    def test_mode_not_cleared_if_same(self, mock_sync_cfg):
        """Если mode одинаковый — не обновляем."""
        from network_collector.netbox.sync.interfaces import InterfacesSyncMixin

        sync = MagicMock(spec=InterfacesSyncMixin)
        sync.dry_run = False
        sync.client = MagicMock()
        bind_mixin_methods(sync, InterfacesSyncMixin, INTERFACE_SYNC_METHODS)

        intf = MockInterface(
            name="Gi0/1",
            status="up",
            mode="access",
        )

        mock_device = MagicMock()
        mock_device.site = None

        nb_interface = MockNBInterface(
            id=1,
            name="Gi0/1",
            mode="access",  # Тот же mode
            device=mock_device,
        )

        with patch("network_collector.netbox.sync.interfaces.get_sync_config", return_value=mock_sync_cfg):
            result = InterfacesSyncMixin._update_interface(sync, nb_interface, intf)

        # mode не должен быть в updates
        if sync.client.update_interface.called:
            call_kwargs = sync.client.update_interface.call_args[1]
            assert "mode" not in call_kwargs

    def test_shutdown_port_clears_vlans_with_empty_mode(self, mock_sync_cfg):
        """Shutdown порт без mode очищает tagged_vlans."""
        from network_collector.netbox.sync.interfaces import InterfacesSyncMixin

        sync = MagicMock(spec=InterfacesSyncMixin)
        sync.dry_run = False
        sync.client = MagicMock()
        bind_mixin_methods(sync, InterfacesSyncMixin, INTERFACE_SYNC_METHODS)
        sync._get_vlan_by_vid = MagicMock(return_value=None)

        # Shutdown интерфейс — mode пустой
        intf = MockInterface(
            name="Gi0/1",
            status="disabled",
            mode="",  # Нет mode
            tagged_vlans="",  # Нет vlans
        )

        mock_device = MagicMock()
        mock_device.site = MagicMock()
        mock_device.site.name = "Office"

        # В NetBox были tagged_vlans
        mock_vlan_100 = MagicMock()
        mock_vlan_100.vid = 100
        existing_tagged = [mock_vlan_100]

        nb_interface = MockNBInterface(
            id=1,
            name="Gi0/1",
            mode="tagged-all",  # Был trunk
            device=mock_device,
        )
        nb_interface.tagged_vlans = existing_tagged

        with patch("network_collector.netbox.sync.interfaces.get_sync_config", return_value=mock_sync_cfg):
            result = InterfacesSyncMixin._update_interface(sync, nb_interface, intf)

        sync.client.update_interface.assert_called_once()
        call_kwargs = sync.client.update_interface.call_args[1]
        # Должен очистить mode и tagged_vlans
        assert "mode" in call_kwargs
        assert call_kwargs["mode"] == ""
        assert "tagged_vlans" in call_kwargs
        assert call_kwargs["tagged_vlans"] == []


class TestModeDiffDetection:
    """Тесты: diff comparator корректно обнаруживает изменение mode."""

    def test_to_dict_includes_empty_mode(self):
        """to_dict() должен включать mode даже если он пустой."""
        from network_collector.core.models import Interface

        intf = Interface(name="Gi0/1", status="disabled", mode="")
        data = intf.to_dict()
        assert "mode" in data
        assert data["mode"] == ""

    def test_to_dict_includes_set_mode(self):
        """to_dict() включает mode когда он задан."""
        from network_collector.core.models import Interface

        intf = Interface(name="Gi0/1", status="up", mode="access")
        data = intf.to_dict()
        assert data["mode"] == "access"

    def test_diff_detects_empty_mode_vs_tagged_all(self):
        """Comparator обнаруживает изменение tagged-all → пустой mode."""
        from network_collector.core.domain.sync import SyncComparator

        comparator = SyncComparator()

        # Локальный интерфейс — mode пустой (shutdown)
        local = [{"name": "Gi0/1", "status": "disabled", "mode": "", "description": ""}]

        # Remote интерфейс — mode tagged-all
        remote_intf = MagicMock()
        remote_intf.name = "Gi0/1"
        remote_intf.enabled = False
        remote_intf.description = ""
        remote_intf.mode = MagicMock()
        remote_intf.mode.value = "tagged-all"
        remote_intf.mtu = None
        remote_intf.duplex = None
        remote_intf.speed = None
        remote_intf.type = MagicMock()
        remote_intf.type.value = "1000base-t"

        diff = comparator.compare_interfaces(
            local=local,
            remote=[remote_intf],
            compare_fields=["mode"],
            update_existing=True,
        )

        assert len(diff.to_update) == 1
        assert len(diff.to_skip) == 0
        assert diff.to_update[0].changes[0].field == "mode"
        assert diff.to_update[0].changes[0].new_value == ""

    def test_diff_skips_both_empty_mode(self):
        """Comparator НЕ создаёт обновление когда оба mode пустые."""
        from network_collector.core.domain.sync import SyncComparator

        comparator = SyncComparator()

        local = [{"name": "Gi0/1", "status": "disabled", "mode": "", "description": ""}]

        remote_intf = MagicMock()
        remote_intf.name = "Gi0/1"
        remote_intf.enabled = False
        remote_intf.description = ""
        remote_intf.mode = None  # В NetBox тоже нет mode
        remote_intf.mtu = None
        remote_intf.duplex = None
        remote_intf.speed = None
        remote_intf.type = MagicMock()
        remote_intf.type.value = "1000base-t"

        diff = comparator.compare_interfaces(
            local=local,
            remote=[remote_intf],
            compare_fields=["mode"],
            update_existing=True,
        )

        assert len(diff.to_update) == 0
        assert len(diff.to_skip) == 1
