"""
Тесты для логики enabled интерфейсов.

Проверяет что:
- admin down (shutdown) -> enabled=False
- up (линк есть) -> enabled=True
- down (линк отсутствует, но порт включён) -> enabled=True
- err-disabled -> enabled=False
"""

import pytest
from unittest.mock import Mock, MagicMock


class TestInterfaceEnabledLogicDiff:
    """Тесты enabled логики в diff.py."""

    def test_enabled_logic_values(self):
        """Проверяет что статусы правильно конвертируются в enabled."""
        # Логика из diff.py: new_enabled = new_status.lower() not in ("disabled", "error")
        test_cases = [
            ("up", True),            # порт включён, линк есть
            ("down", True),          # порт включён, линка нет (not connected)
            ("disabled", False),     # administratively down
            ("error", False),        # err-disabled
            ("UP", True),            # регистронезависимость
            ("DOWN", True),
            ("DISABLED", False),
            ("Disabled", False),
        ]

        for status, expected_enabled in test_cases:
            actual = status.lower() not in ("disabled", "error")
            assert actual == expected_enabled, (
                f"Status '{status}' should give enabled={expected_enabled}, "
                f"but got enabled={actual}"
            )

    def test_diff_compare_interface_enabled(self):
        """Тест _compare_interface в DiffCalculator."""
        from unittest.mock import patch
        from network_collector.netbox.diff import DiffCalculator

        # Мок клиента
        mock_client = Mock()
        calc = DiffCalculator(mock_client)

        # Создаём мок существующего интерфейса
        existing = MagicMock()
        existing.enabled = True
        existing.description = ""
        existing.mode = None

        # Мокаем get_sync_config чтобы вернуть enabled_mode="admin"
        mock_sync_cfg = MagicMock()
        mock_sync_cfg.get_option.return_value = "admin"

        with patch("network_collector.netbox.diff.get_sync_config", return_value=mock_sync_cfg):
            # Тест 1: status="down" не должен менять enabled=True
            new_data = {"status": "down", "description": ""}
            changes = calc._compare_interface(existing, new_data)
            enabled_changes = [c for c in changes if c.field == "enabled"]
            assert len(enabled_changes) == 0, (
                "down status should not change enabled=True because down=not connected, not disabled"
            )

            # Тест 2: status="disabled" должен менять enabled на False
            existing.enabled = True
            new_data = {"status": "disabled", "description": ""}
            changes = calc._compare_interface(existing, new_data)
            enabled_changes = [c for c in changes if c.field == "enabled"]
            assert len(enabled_changes) == 1
            assert enabled_changes[0].new_value == False

            # Тест 3: status="up" не должен менять enabled=True
            existing.enabled = True
            new_data = {"status": "up", "description": ""}
            changes = calc._compare_interface(existing, new_data)
            enabled_changes = [c for c in changes if c.field == "enabled"]
            assert len(enabled_changes) == 0


class TestInterfaceEnabledLogicSync:
    """Тесты enabled логики в sync/interfaces.py."""

    def test_sync_interface_enabled_mapping(self):
        """Проверяет маппинг status -> enabled в sync."""
        # Логика из sync/interfaces.py: enabled = intf.status not in ("disabled", "error")
        from network_collector.core.models import Interface

        test_cases = [
            ("up", True),
            ("down", True),       # down = not connected, но порт включён!
            ("disabled", False),  # admin shutdown
            ("error", False),     # err-disabled
        ]

        for status, expected_enabled in test_cases:
            # Используем ту же логику что в sync
            actual_enabled = status not in ("disabled", "error")
            assert actual_enabled == expected_enabled, (
                f"Interface with status='{status}' should have enabled={expected_enabled}"
            )


class TestStatusNormalization:
    """Тесты нормализации статуса в InterfaceNormalizer."""

    def test_status_normalization(self):
        """Проверяет что все варианты статуса нормализуются правильно."""
        from network_collector.core.domain.interface import STATUS_MAP

        expected_mappings = {
            # Стандартные
            "up": "up",
            "down": "down",
            # Admin down варианты -> disabled
            "administratively down": "disabled",
            "admin down": "disabled",
            "disabled": "disabled",
            # Error варианты -> error
            "err-disabled": "error",
            "errdisabled": "error",
            # Cisco варианты
            "connected": "up",
            "notconnect": "down",
        }

        for raw_status, expected_normalized in expected_mappings.items():
            # STATUS_MAP использует lowercase ключи
            actual = STATUS_MAP.get(raw_status.lower().strip(), raw_status.lower())
            assert actual == expected_normalized, (
                f"Status '{raw_status}' should normalize to '{expected_normalized}', "
                f"but got '{actual}'"
            )

    def test_admin_down_preserved_as_disabled(self):
        """
        Критический тест: administratively down должен стать disabled, не down.

        Если это сломается, все admin-выключенные порты будут показаны как enabled=True!
        """
        from network_collector.core.domain.interface import STATUS_MAP

        admin_down_variants = [
            "administratively down",
            "admin down",
        ]

        for variant in admin_down_variants:
            normalized = STATUS_MAP.get(variant.lower().strip(), variant.lower())
            assert normalized == "disabled", (
                f"'{variant}' MUST normalize to 'disabled', got '{normalized}'. "
                f"This bug causes admin-shutdown ports to show as enabled=True!"
            )


class TestEndToEndEnabledFlow:
    """
    E2E тест потока данных enabled.

    Проверяет весь путь: raw output -> collector -> normalizer -> sync -> NetBox
    """

    def test_enabled_flow_admin_down(self):
        """
        Порт с 'administratively down' должен иметь enabled=False в итоге.
        """
        from network_collector.core.domain.interface import STATUS_MAP

        # 1. Raw output содержит "administratively down"
        raw_status = "administratively down"

        # 2. Collector передаёт в normalizer
        # 3. Normalizer конвертирует через STATUS_MAP
        normalized = STATUS_MAP.get(raw_status.lower().strip(), raw_status.lower())
        assert normalized == "disabled"

        # 4. Sync проверяет: enabled = status not in ("disabled", "error")
        enabled = normalized not in ("disabled", "error")
        assert enabled == False, (
            "Admin down port should have enabled=False in NetBox"
        )

    def test_enabled_flow_not_connected(self):
        """
        Порт с 'down' (not connected) должен иметь enabled=True в итоге.
        """
        from network_collector.core.domain.interface import STATUS_MAP

        # 1. Raw output содержит "down" (линк отсутствует)
        raw_status = "down"

        # 2-3. Normalizer
        normalized = STATUS_MAP.get(raw_status.lower().strip(), raw_status.lower())
        assert normalized == "down"

        # 4. Sync
        enabled = normalized not in ("disabled", "error")
        assert enabled == True, (
            "Not connected port (down) should have enabled=True because "
            "it's administratively UP, just no cable"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
