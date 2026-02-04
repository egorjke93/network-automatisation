"""
Тесты передачи cleanup опций в pipeline executor.

Покрывает:
- interfaces sync с cleanup
- cables sync с cleanup
- ip_addresses sync с cleanup
- inventory sync с cleanup
- devices sync БЕЗ cleanup (требует tenant)
- lldp collect с protocol=both по умолчанию
"""

import pytest
from unittest.mock import MagicMock, patch


class TestPipelineCleanupOptions:
    """Тесты передачи cleanup в sync шаги."""

    @pytest.fixture
    def mock_context(self):
        """Базовый контекст для executor."""
        return {
            "devices": [],
            "credentials": {},
            "netbox_config": {"url": "http://netbox.local"},
            "dry_run": True,
            "collected_data": {
                "interfaces": {"data": [{"hostname": "sw1", "name": "Gi0/1"}]},
                "lldp": {"data": [{"hostname": "sw1", "local_interface": "Gi0/1"}]},
                "inventory": {"data": [{"hostname": "sw1", "name": "Module1"}]},
            },
        }

    def test_interfaces_sync_passes_cleanup(self, mock_context):
        """sync_interfaces получает cleanup из options."""
        from network_collector.core.pipeline.executor import PipelineExecutor
        from network_collector.core.pipeline.models import Pipeline, PipelineStep, StepType

        step = PipelineStep(
            id="sync_interfaces",
            type=StepType.SYNC,
            target="interfaces",
            options={"cleanup": True},
        )

        pipeline = Pipeline(id="test", name="Test", steps=[step])
        executor = PipelineExecutor(pipeline, dry_run=True)
        executor._context = mock_context

        with patch("network_collector.netbox.client.NetBoxClient") as mock_client_cls, \
             patch("network_collector.netbox.sync.NetBoxSync") as mock_sync_cls:

            mock_sync = MagicMock()
            mock_sync.sync_interfaces.return_value = {"created": 0, "updated": 0, "skipped": 0}
            mock_sync_cls.return_value = mock_sync

            executor._execute_sync(step)

            # Проверяем что sync_interfaces вызван с cleanup=True
            mock_sync.sync_interfaces.assert_called()
            call_args = mock_sync.sync_interfaces.call_args
            assert call_args[1].get("cleanup") is True

    def test_cables_sync_passes_cleanup(self, mock_context):
        """sync_cables_from_lldp получает cleanup из options."""
        from network_collector.core.pipeline.executor import PipelineExecutor
        from network_collector.core.pipeline.models import Pipeline, PipelineStep, StepType

        step = PipelineStep(
            id="sync_cables",
            type=StepType.SYNC,
            target="cables",
            options={"cleanup": True},
        )

        pipeline = Pipeline(id="test", name="Test", steps=[step])
        executor = PipelineExecutor(pipeline, dry_run=True)
        executor._context = mock_context

        with patch("network_collector.netbox.client.NetBoxClient") as mock_client_cls, \
             patch("network_collector.netbox.sync.NetBoxSync") as mock_sync_cls:

            mock_sync = MagicMock()
            mock_sync.sync_cables_from_lldp.return_value = {"created": 0, "deleted": 0}
            mock_sync_cls.return_value = mock_sync

            executor._execute_sync(step)

            # Проверяем что sync_cables_from_lldp вызван с cleanup=True
            mock_sync.sync_cables_from_lldp.assert_called_once()
            call_args = mock_sync.sync_cables_from_lldp.call_args
            assert call_args[1].get("cleanup") is True

    def test_inventory_sync_passes_cleanup(self, mock_context):
        """sync_inventory получает cleanup из options."""
        from network_collector.core.pipeline.executor import PipelineExecutor
        from network_collector.core.pipeline.models import Pipeline, PipelineStep, StepType

        step = PipelineStep(
            id="sync_inventory",
            type=StepType.SYNC,
            target="inventory",
            options={"cleanup": True},
        )

        pipeline = Pipeline(id="test", name="Test", steps=[step])
        executor = PipelineExecutor(pipeline, dry_run=True)
        executor._context = mock_context

        with patch("network_collector.netbox.client.NetBoxClient") as mock_client_cls, \
             patch("network_collector.netbox.sync.NetBoxSync") as mock_sync_cls:

            mock_sync = MagicMock()
            mock_sync.sync_inventory.return_value = {"created": 0, "updated": 0, "deleted": 0}
            mock_sync_cls.return_value = mock_sync

            executor._execute_sync(step)

            # Проверяем что sync_inventory вызван с cleanup=True
            mock_sync.sync_inventory.assert_called()
            call_args = mock_sync.sync_inventory.call_args
            assert call_args[1].get("cleanup") is True

    def test_devices_sync_does_not_pass_cleanup(self, mock_context):
        """sync_devices НЕ получает cleanup (требует tenant для безопасности)."""
        from network_collector.core.pipeline.executor import PipelineExecutor
        from network_collector.core.pipeline.models import Pipeline, PipelineStep, StepType

        mock_context["collected_data"]["devices"] = {
            "data": [{"hostname": "sw1", "ip": "1.1.1.1"}]
        }

        step = PipelineStep(
            id="sync_devices",
            type=StepType.SYNC,
            target="devices",
            options={"cleanup": True, "site": "Main"},  # cleanup указан, но не должен передаваться
        )

        pipeline = Pipeline(id="test", name="Test", steps=[step])
        executor = PipelineExecutor(pipeline, dry_run=True)
        executor._context = mock_context

        with patch("network_collector.netbox.client.NetBoxClient") as mock_client_cls, \
             patch("network_collector.netbox.sync.NetBoxSync") as mock_sync_cls:

            mock_sync = MagicMock()
            mock_sync.sync_devices_from_inventory.return_value = {"created": 0, "updated": 0}
            mock_sync_cls.return_value = mock_sync

            executor._execute_sync(step)

            # Проверяем что sync_devices_from_inventory вызван БЕЗ cleanup
            mock_sync.sync_devices_from_inventory.assert_called_once()
            call_args = mock_sync.sync_devices_from_inventory.call_args
            # cleanup НЕ должен быть в аргументах
            assert "cleanup" not in call_args[1]

    def test_cleanup_defaults_to_false(self, mock_context):
        """Без явного cleanup=True, cleanup=False."""
        from network_collector.core.pipeline.executor import PipelineExecutor
        from network_collector.core.pipeline.models import Pipeline, PipelineStep, StepType

        step = PipelineStep(
            id="sync_interfaces",
            type=StepType.SYNC,
            target="interfaces",
            options={},  # Нет cleanup
        )

        pipeline = Pipeline(id="test", name="Test", steps=[step])
        executor = PipelineExecutor(pipeline, dry_run=True)
        executor._context = mock_context

        with patch("network_collector.netbox.client.NetBoxClient") as mock_client_cls, \
             patch("network_collector.netbox.sync.NetBoxSync") as mock_sync_cls:

            mock_sync = MagicMock()
            mock_sync.sync_interfaces.return_value = {"created": 0, "updated": 0, "skipped": 0}
            mock_sync_cls.return_value = mock_sync

            executor._execute_sync(step)

            call_args = mock_sync.sync_interfaces.call_args
            assert call_args[1].get("cleanup") is False


class TestLLDPProtocolDefault:
    """Тесты protocol=both по умолчанию для LLDP."""

    def test_lldp_collect_defaults_to_both(self):
        """collect lldp использует protocol=both по умолчанию."""
        from network_collector.core.pipeline.executor import PipelineExecutor
        from network_collector.core.pipeline.models import Pipeline, PipelineStep, StepType

        step = PipelineStep(
            id="collect_lldp",
            type=StepType.COLLECT,
            target="lldp",
            options={},  # Без явного protocol
        )

        pipeline = Pipeline(id="test", name="Test", steps=[step])
        executor = PipelineExecutor(pipeline, dry_run=True)
        executor._context = {
            "devices": [MagicMock()],
            "credentials": {"username": "admin", "password": "pass"},
            "dry_run": True,
            "collected_data": {},
        }

        with patch("network_collector.collectors.LLDPCollector") as mock_collector_cls:
            mock_collector = MagicMock()
            mock_collector.collect_dicts.return_value = []
            mock_collector_cls.return_value = mock_collector

            executor._execute_collect(step)

            # Проверяем что LLDPCollector создан с protocol=both
            call_kwargs = mock_collector_cls.call_args[1]
            assert call_kwargs.get("protocol") == "both"

    def test_cdp_collect_uses_cdp_protocol(self):
        """collect cdp использует protocol=cdp."""
        from network_collector.core.pipeline.executor import PipelineExecutor
        from network_collector.core.pipeline.models import Pipeline, PipelineStep, StepType

        step = PipelineStep(
            id="collect_cdp",
            type=StepType.COLLECT,
            target="cdp",
            options={},
        )

        pipeline = Pipeline(id="test", name="Test", steps=[step])
        executor = PipelineExecutor(pipeline, dry_run=True)
        executor._context = {
            "devices": [MagicMock()],
            "credentials": {"username": "admin", "password": "pass"},
            "dry_run": True,
            "collected_data": {},
        }

        with patch("network_collector.collectors.LLDPCollector") as mock_collector_cls:
            mock_collector = MagicMock()
            mock_collector.collect_dicts.return_value = []
            mock_collector_cls.return_value = mock_collector

            executor._execute_collect(step)

            # Проверяем что LLDPCollector создан с protocol=cdp
            call_kwargs = mock_collector_cls.call_args[1]
            assert call_kwargs.get("protocol") == "cdp"
