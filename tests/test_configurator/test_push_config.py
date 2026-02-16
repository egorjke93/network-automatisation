"""Тесты команды push-config: загрузка YAML, маппинг команд по платформам, exec-команды."""

import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import patch, MagicMock, call

from network_collector.cli.commands.push import (
    _load_commands_yaml,
    _build_device_commands,
    cmd_push_config,
)
from network_collector.core.device import Device


# =============================================================================
# Fixtures — унифицированный формат (config/exec внутри платформы)
# =============================================================================

@pytest.fixture
def yaml_file(tmp_path):
    """YAML с config-командами (унифицированный формат)."""
    content = """
_common:
  config:
    - logging buffered 16384
    - no ip domain-lookup

cisco_iosxe:
  config:
    - interface range GigabitEthernet0/1 - 48
    - spanning-tree portfast
    - no shutdown

cisco_nxos:
  config:
    - interface Ethernet1/1-48
    - spanning-tree port type edge

arista_eos:
  config:
    - interface Ethernet1
    - spanning-tree portfast
"""
    filepath = tmp_path / "test_commands.yaml"
    filepath.write_text(content, encoding="utf-8")
    return str(filepath)


@pytest.fixture
def yaml_file_no_common(tmp_path):
    """YAML без секции _common."""
    content = """
cisco_iosxe:
  config:
    - interface GigabitEthernet0/1
    - shutdown
"""
    filepath = tmp_path / "no_common.yaml"
    filepath.write_text(content, encoding="utf-8")
    return str(filepath)


@pytest.fixture
def yaml_file_only_common(tmp_path):
    """YAML только с _common."""
    content = """
_common:
  config:
    - logging buffered 16384
"""
    filepath = tmp_path / "only_common.yaml"
    filepath.write_text(content, encoding="utf-8")
    return str(filepath)


@pytest.fixture
def yaml_file_with_exec(tmp_path):
    """YAML с config и exec командами (унифицированный формат)."""
    content = """
_common:
  config:
    - logging buffered 16384
  exec:
    - show running-config | include logging

cisco_iosxe:
  config:
    - spanning-tree portfast
  exec:
    - show spanning-tree summary
"""
    filepath = tmp_path / "with_exec.yaml"
    filepath.write_text(content, encoding="utf-8")
    return str(filepath)


@pytest.fixture
def yaml_file_only_exec(tmp_path):
    """YAML только с exec-командами (без config)."""
    content = """
_common:
  exec:
    - show version

qtech:
  exec:
    - copy running-config startup-config
"""
    filepath = tmp_path / "only_exec.yaml"
    filepath.write_text(content, encoding="utf-8")
    return str(filepath)


@pytest.fixture
def yaml_file_platform_exec_only(tmp_path):
    """YAML: config для одной платформы, exec для другой."""
    content = """
cisco_iosxe:
  config:
    - spanning-tree portfast

qtech:
  exec:
    - copy running-config startup-config
"""
    filepath = tmp_path / "platform_exec.yaml"
    filepath.write_text(content, encoding="utf-8")
    return str(filepath)


@pytest.fixture
def yaml_file_full(tmp_path):
    """YAML с полным набором: _common + несколько платформ с config и exec."""
    content = """
_common:
  config:
    - logging buffered 16384
  exec:
    - show clock

cisco_iosxe:
  config:
    - spanning-tree portfast
  exec:
    - show spanning-tree summary

cisco_nxos:
  config:
    - spanning-tree port type edge

qtech:
  exec:
    - copy running-config startup-config
"""
    filepath = tmp_path / "full.yaml"
    filepath.write_text(content, encoding="utf-8")
    return str(filepath)


# --- Device fixtures ---

@pytest.fixture
def device_cisco_iosxe():
    """Устройство cisco_iosxe (новый формат)."""
    return Device(host="192.168.1.1", platform="cisco_iosxe")


@pytest.fixture
def device_cisco_iosxe_old_format():
    """Устройство cisco_iosxe (старый формат через device_type)."""
    return Device(host="192.168.1.2", device_type="cisco_iosxe")


@pytest.fixture
def device_nxos():
    """Устройство cisco_nxos."""
    return Device(host="192.168.2.1", platform="cisco_nxos")


@pytest.fixture
def device_qtech():
    """Устройство qtech."""
    return Device(host="192.168.4.1", platform="qtech")


@pytest.fixture
def device_unknown():
    """Устройство с платформой без команд."""
    return Device(host="192.168.3.1", platform="juniper_junos")


# =============================================================================
# Тесты _load_commands_yaml — унифицированный формат
# =============================================================================

class TestLoadCommandsYaml:
    """Тесты загрузки YAML-файла с командами."""

    def test_load_valid_yaml(self, yaml_file):
        """Загрузка корректного YAML."""
        data = _load_commands_yaml(yaml_file)
        assert "_common" in data
        assert "cisco_iosxe" in data
        assert "cisco_nxos" in data
        assert "arista_eos" in data

    def test_load_common_config(self, yaml_file):
        """Проверка _common.config."""
        data = _load_commands_yaml(yaml_file)
        assert data["_common"]["config"] == ["logging buffered 16384", "no ip domain-lookup"]

    def test_load_platform_config(self, yaml_file):
        """Проверка платформенных config-команд."""
        data = _load_commands_yaml(yaml_file)
        assert len(data["cisco_iosxe"]["config"]) == 3
        assert "spanning-tree portfast" in data["cisco_iosxe"]["config"]

    def test_load_with_exec(self, yaml_file_with_exec):
        """Загрузка YAML с exec-секциями."""
        data = _load_commands_yaml(yaml_file_with_exec)
        assert data["_common"]["exec"] == ["show running-config | include logging"]
        assert data["cisco_iosxe"]["exec"] == ["show spanning-tree summary"]

    def test_file_not_found(self):
        """Несуществующий файл → SystemExit."""
        with pytest.raises(SystemExit):
            _load_commands_yaml("/nonexistent/path/commands.yaml")

    def test_invalid_yaml_syntax(self, tmp_path):
        """Некорректный YAML → SystemExit."""
        bad_file = tmp_path / "bad.yaml"
        bad_file.write_text("{ invalid: yaml: [", encoding="utf-8")
        with pytest.raises(SystemExit):
            _load_commands_yaml(str(bad_file))

    def test_empty_yaml(self, tmp_path):
        """Пустой YAML → SystemExit."""
        empty_file = tmp_path / "empty.yaml"
        empty_file.write_text("", encoding="utf-8")
        with pytest.raises(SystemExit):
            _load_commands_yaml(str(empty_file))

    def test_non_dict_yaml(self, tmp_path):
        """YAML со списком вместо dict → SystemExit."""
        list_file = tmp_path / "list.yaml"
        list_file.write_text("- item1\n- item2\n", encoding="utf-8")
        with pytest.raises(SystemExit):
            _load_commands_yaml(str(list_file))

    def test_non_list_config(self, tmp_path):
        """config не список → SystemExit."""
        bad_file = tmp_path / "bad_cmds.yaml"
        bad_file.write_text("cisco_ios:\n  config: not_a_list\n", encoding="utf-8")
        with pytest.raises(SystemExit):
            _load_commands_yaml(str(bad_file))

    def test_unknown_section_key(self, tmp_path):
        """Неизвестный ключ в секции → SystemExit."""
        bad_file = tmp_path / "bad_keys.yaml"
        bad_file.write_text("cisco_ios:\n  config:\n    - cmd1\n  something:\n    - cmd2\n", encoding="utf-8")
        with pytest.raises(SystemExit):
            _load_commands_yaml(str(bad_file))

    def test_empty_section(self, tmp_path):
        """Пустая секция (без config и exec) → SystemExit."""
        bad_file = tmp_path / "empty_section.yaml"
        bad_file.write_text("cisco_ios: {}\n", encoding="utf-8")
        with pytest.raises(SystemExit):
            _load_commands_yaml(str(bad_file))

    def test_commands_converted_to_strings(self, tmp_path):
        """Числовые значения конвертируются в строки."""
        num_file = tmp_path / "nums.yaml"
        num_file.write_text("cisco_ios:\n  config:\n    - 123\n    - true\n", encoding="utf-8")
        data = _load_commands_yaml(str(num_file))
        assert data["cisco_ios"]["config"] == ["123", "True"]

    def test_non_list_non_dict_value(self, tmp_path):
        """Значение секции — не список и не dict → SystemExit."""
        bad_file = tmp_path / "bad_value.yaml"
        bad_file.write_text("cisco_ios: not_a_list\n", encoding="utf-8")
        with pytest.raises(SystemExit):
            _load_commands_yaml(str(bad_file))


# =============================================================================
# Тесты _build_device_commands
# =============================================================================

class TestBuildDeviceCommands:
    """Тесты сборки команд для устройства."""

    def test_common_plus_platform(self, yaml_file):
        """Общие + платформенные config-команды."""
        data = _load_commands_yaml(yaml_file)
        config_cmds, exec_cmds = _build_device_commands(data, "cisco_iosxe")
        # 2 common + 3 platform = 5
        assert len(config_cmds) == 5
        # _common идут первыми
        assert config_cmds[0] == "logging buffered 16384"
        assert config_cmds[1] == "no ip domain-lookup"
        # Потом платформенные
        assert config_cmds[2] == "interface range GigabitEthernet0/1 - 48"
        # Нет exec-команд
        assert exec_cmds == []

    def test_only_platform_no_common(self, yaml_file_no_common):
        """Только платформенные команды (без _common)."""
        data = _load_commands_yaml(yaml_file_no_common)
        config_cmds, exec_cmds = _build_device_commands(data, "cisco_iosxe")
        assert len(config_cmds) == 2
        assert config_cmds[0] == "interface GigabitEthernet0/1"

    def test_only_common(self, yaml_file_only_common):
        """Только _common (платформа без секции)."""
        data = _load_commands_yaml(yaml_file_only_common)
        config_cmds, exec_cmds = _build_device_commands(data, "cisco_iosxe")
        assert len(config_cmds) == 1
        assert config_cmds[0] == "logging buffered 16384"

    def test_unknown_platform_with_common(self, yaml_file):
        """Неизвестная платформа → только _common."""
        data = _load_commands_yaml(yaml_file)
        config_cmds, exec_cmds = _build_device_commands(data, "unknown_platform")
        assert len(config_cmds) == 2  # Только _common
        assert config_cmds[0] == "logging buffered 16384"

    def test_unknown_platform_no_common(self, yaml_file_no_common):
        """Неизвестная платформа без _common → пустой список."""
        data = _load_commands_yaml(yaml_file_no_common)
        config_cmds, exec_cmds = _build_device_commands(data, "unknown_platform")
        assert config_cmds == []
        assert exec_cmds == []

    def test_nxos_commands(self, yaml_file):
        """Команды для NX-OS."""
        data = _load_commands_yaml(yaml_file)
        config_cmds, exec_cmds = _build_device_commands(data, "cisco_nxos")
        assert len(config_cmds) == 4  # 2 common + 2 nxos
        assert "spanning-tree port type edge" in config_cmds

    def test_config_and_exec_together(self, yaml_file_with_exec):
        """Config + exec из _common и платформы."""
        data = _load_commands_yaml(yaml_file_with_exec)
        config_cmds, exec_cmds = _build_device_commands(data, "cisco_iosxe")
        # Config: _common.config(1) + cisco_iosxe.config(1) = 2
        assert len(config_cmds) == 2
        assert config_cmds[0] == "logging buffered 16384"
        assert config_cmds[1] == "spanning-tree portfast"
        # Exec: _common.exec(1) + cisco_iosxe.exec(1) = 2
        assert len(exec_cmds) == 2
        assert exec_cmds[0] == "show running-config | include logging"
        assert exec_cmds[1] == "show spanning-tree summary"

    def test_exec_only_common(self, yaml_file_with_exec):
        """Платформа без exec → только _common.exec."""
        data = _load_commands_yaml(yaml_file_with_exec)
        config_cmds, exec_cmds = _build_device_commands(data, "cisco_nxos")
        # Exec: только _common.exec(1), нет cisco_nxos.exec
        assert len(exec_cmds) == 1
        assert exec_cmds[0] == "show running-config | include logging"

    def test_exec_only_platform(self, yaml_file_platform_exec_only):
        """Exec-команды только для конкретной платформы (без _common)."""
        data = _load_commands_yaml(yaml_file_platform_exec_only)
        config_cmds, exec_cmds = _build_device_commands(data, "qtech")
        # Config: нет _common и нет qtech.config
        assert config_cmds == []
        # Exec: qtech.exec(1)
        assert len(exec_cmds) == 1
        assert exec_cmds[0] == "copy running-config startup-config"

    def test_only_exec_no_config(self, yaml_file_only_exec):
        """YAML только с exec-командами."""
        data = _load_commands_yaml(yaml_file_only_exec)
        config_cmds, exec_cmds = _build_device_commands(data, "qtech")
        assert config_cmds == []
        assert len(exec_cmds) == 2  # _common.exec(1) + qtech.exec(1)
        assert "show version" in exec_cmds
        assert "copy running-config startup-config" in exec_cmds

    def test_full_yaml_all_platforms(self, yaml_file_full):
        """Полный YAML: проверяем команды для каждой платформы."""
        data = _load_commands_yaml(yaml_file_full)

        # cisco_iosxe: config(_common + platform) + exec(_common + platform)
        cfg, exc = _build_device_commands(data, "cisco_iosxe")
        assert cfg == ["logging buffered 16384", "spanning-tree portfast"]
        assert exc == ["show clock", "show spanning-tree summary"]

        # cisco_nxos: config(_common + platform) + exec(только _common)
        cfg, exc = _build_device_commands(data, "cisco_nxos")
        assert cfg == ["logging buffered 16384", "spanning-tree port type edge"]
        assert exc == ["show clock"]

        # qtech: config(только _common) + exec(_common + platform)
        cfg, exc = _build_device_commands(data, "qtech")
        assert cfg == ["logging buffered 16384"]
        assert exc == ["show clock", "copy running-config startup-config"]

        # unknown: только _common
        cfg, exc = _build_device_commands(data, "unknown")
        assert cfg == ["logging buffered 16384"]
        assert exc == ["show clock"]


# =============================================================================
# Тесты backward compatibility (device_type → platform)
# =============================================================================

class TestBackwardCompatibility:
    """Тесты обратной совместимости device_type → platform."""

    def test_old_format_device_type_as_platform(self):
        """Старый формат: device_type='cisco_iosxe' → platform='cisco_iosxe'."""
        device = Device(host="10.0.0.1", device_type="cisco_iosxe")
        assert device.platform == "cisco_iosxe"

    def test_old_format_device_type_cisco_ios(self):
        """Старый формат: device_type='cisco_ios' → platform='cisco_ios'."""
        device = Device(host="10.0.0.1", device_type="cisco_ios")
        assert device.platform == "cisco_ios"

    def test_new_format_both_fields(self):
        """Новый формат: platform + device_type как модель."""
        device = Device(host="10.0.0.1", platform="cisco_iosxe", device_type="C9200L-24P")
        assert device.platform == "cisco_iosxe"
        assert device.device_type == "C9200L-24P"

    def test_commands_match_regardless_of_format(self, yaml_file):
        """Команды одинаковы для старого и нового формата."""
        data = _load_commands_yaml(yaml_file)

        # Новый формат
        device_new = Device(host="10.0.0.1", platform="cisco_iosxe")
        cmds_new = _build_device_commands(data, device_new.platform)

        # Старый формат
        device_old = Device(host="10.0.0.2", device_type="cisco_iosxe")
        cmds_old = _build_device_commands(data, device_old.platform)

        assert cmds_new == cmds_old


# =============================================================================
# Тесты cmd_push_config (интеграция)
# =============================================================================

class TestCmdPushConfig:
    """Интеграционные тесты cmd_push_config."""

    def _make_args(self, commands_file, apply=False, no_save=False, platform=None, devices="devices_ips.py"):
        """Создаёт mock args."""
        args = MagicMock()
        args.commands = commands_file
        args.apply = apply
        args.no_save = no_save
        args.platform = platform
        args.devices = devices
        return args

    @patch("network_collector.cli.commands.push.load_devices")
    def test_dry_run_shows_commands(self, mock_load, yaml_file, device_cisco_iosxe):
        """Dry-run показывает команды без применения."""
        mock_load.return_value = [device_cisco_iosxe]

        args = self._make_args(yaml_file, apply=False)
        # Не должен вызвать ошибку
        cmd_push_config(args)

    @patch("network_collector.cli.commands.push.load_devices")
    def test_platform_filter(self, mock_load, yaml_file, device_cisco_iosxe, device_nxos):
        """Фильтр по платформе — только cisco_iosxe."""
        mock_load.return_value = [device_cisco_iosxe, device_nxos]

        args = self._make_args(yaml_file, apply=False, platform="cisco_iosxe")
        cmd_push_config(args)
        # Тест проходит без ошибок — фильтр работает

    @patch("network_collector.cli.commands.push.get_credentials")
    @patch("network_collector.configurator.base.ConnectHandler")
    @patch("network_collector.cli.commands.push.load_devices")
    def test_apply_calls_pusher(self, mock_load, mock_conn, mock_creds, yaml_file, device_cisco_iosxe):
        """--apply вызывает ConfigPusher."""
        from network_collector.core.credentials import Credentials

        mock_load.return_value = [device_cisco_iosxe]
        mock_creds.return_value = Credentials(username="admin", password="pass")

        # Мокаем Netmiko connection
        mock_connection = MagicMock()
        mock_connection.send_config_set.return_value = "OK"
        mock_connection.save_config.return_value = "Saved"
        mock_connection.__enter__ = MagicMock(return_value=mock_connection)
        mock_connection.__exit__ = MagicMock(return_value=False)
        mock_conn.return_value = mock_connection

        args = self._make_args(yaml_file, apply=True)
        cmd_push_config(args)

        # Проверяем что send_config_set вызван
        mock_connection.send_config_set.assert_called_once()
        # Проверяем что save_config вызван (по умолчанию save=True)
        mock_connection.save_config.assert_called_once()

    @patch("network_collector.cli.commands.push.get_credentials")
    @patch("network_collector.configurator.base.ConnectHandler")
    @patch("network_collector.cli.commands.push.load_devices")
    def test_apply_no_save(self, mock_load, mock_conn, mock_creds, yaml_file, device_cisco_iosxe):
        """--apply --no-save: конфигурация не сохраняется."""
        from network_collector.core.credentials import Credentials

        mock_load.return_value = [device_cisco_iosxe]
        mock_creds.return_value = Credentials(username="admin", password="pass")

        mock_connection = MagicMock()
        mock_connection.send_config_set.return_value = "OK"
        mock_connection.__enter__ = MagicMock(return_value=mock_connection)
        mock_connection.__exit__ = MagicMock(return_value=False)
        mock_conn.return_value = mock_connection

        args = self._make_args(yaml_file, apply=True, no_save=True)
        cmd_push_config(args)

        mock_connection.send_config_set.assert_called_once()
        # save_config НЕ вызван
        mock_connection.save_config.assert_not_called()

    @patch("network_collector.cli.commands.push.load_devices")
    def test_no_commands_for_platform(self, mock_load, yaml_file, device_unknown):
        """Устройство без команд для платформы — пропускается."""
        mock_load.return_value = [device_unknown]

        # YAML не содержит juniper_junos, но есть _common
        args = self._make_args(yaml_file, apply=False)
        # Не падает, juniper_junos получит только _common команды
        cmd_push_config(args)

    @patch("network_collector.cli.commands.push.load_devices")
    def test_no_commands_at_all(self, mock_load, yaml_file_no_common, device_unknown):
        """Устройство без каких-либо команд (нет _common, нет платформы)."""
        mock_load.return_value = [device_unknown]

        args = self._make_args(yaml_file_no_common, apply=False)
        # Не падает — просто warning
        cmd_push_config(args)

    @patch("network_collector.cli.commands.push.get_credentials")
    @patch("network_collector.configurator.base.ConnectHandler")
    @patch("network_collector.cli.commands.push.load_devices")
    def test_apply_with_exec_commands(self, mock_load, mock_conn, mock_creds, yaml_file_with_exec, device_cisco_iosxe):
        """--apply с exec-командами: send_config_set + send_command."""
        from network_collector.core.credentials import Credentials

        mock_load.return_value = [device_cisco_iosxe]
        mock_creds.return_value = Credentials(username="admin", password="pass")

        mock_connection = MagicMock()
        mock_connection.send_config_set.return_value = "OK"
        mock_connection.send_command.return_value = "exec output"
        mock_connection.save_config.return_value = "Saved"
        mock_connection.__enter__ = MagicMock(return_value=mock_connection)
        mock_connection.__exit__ = MagicMock(return_value=False)
        mock_conn.return_value = mock_connection

        args = self._make_args(yaml_file_with_exec, apply=True)
        cmd_push_config(args)

        # Config-команды через send_config_set
        mock_connection.send_config_set.assert_called_once()
        # Exec-команды через send_command (2: _common.exec + cisco_iosxe.exec)
        assert mock_connection.send_command.call_count == 2

    @patch("network_collector.cli.commands.push.get_credentials")
    @patch("network_collector.configurator.base.ConnectHandler")
    @patch("network_collector.cli.commands.push.load_devices")
    def test_apply_only_exec_no_config(self, mock_load, mock_conn, mock_creds, yaml_file_only_exec, device_qtech):
        """--apply только exec-команды (без config)."""
        from network_collector.core.credentials import Credentials

        mock_load.return_value = [device_qtech]
        mock_creds.return_value = Credentials(username="admin", password="pass")

        mock_connection = MagicMock()
        mock_connection.send_command.return_value = "OK"
        mock_connection.save_config.return_value = "Saved"
        mock_connection.__enter__ = MagicMock(return_value=mock_connection)
        mock_connection.__exit__ = MagicMock(return_value=False)
        mock_conn.return_value = mock_connection

        args = self._make_args(yaml_file_only_exec, apply=True)
        cmd_push_config(args)

        # send_config_set НЕ вызван (нет config-команд)
        mock_connection.send_config_set.assert_not_called()
        # Exec-команды через send_command (2: _common.exec + qtech.exec)
        assert mock_connection.send_command.call_count == 2

    @patch("network_collector.cli.commands.push.load_devices")
    def test_dry_run_shows_exec_separately(self, mock_load, yaml_file_with_exec, device_cisco_iosxe):
        """Dry-run показывает exec-команды отдельно от config."""
        mock_load.return_value = [device_cisco_iosxe]

        args = self._make_args(yaml_file_with_exec, apply=False)
        # Не падает — exec-команды отображаются в превью
        cmd_push_config(args)
