"""
PipelineExecutor - выполнение pipeline.

Выполняет шаги pipeline последовательно с учётом зависимостей.
"""

from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field

from .models import Pipeline, PipelineStep, StepType, StepStatus
from ..logging import get_logger

logger = get_logger(__name__)


# Маппинг target -> collector class
COLLECTOR_MAPPING = {
    "devices": "DeviceCollector",
    "mac": "MACCollector",
    "lldp": "LLDPCollector",
    "cdp": "LLDPCollector",
    "interfaces": "InterfaceCollector",
    "inventory": "InventoryCollector",
    "backup": "ConfigBackupCollector",
}


@dataclass
class StepResult:
    """Результат выполнения шага."""
    step_id: str
    status: StepStatus
    data: Any = None
    error: Optional[str] = None
    duration_ms: int = 0


@dataclass
class PipelineResult:
    """Результат выполнения pipeline."""
    pipeline_id: str
    status: StepStatus
    steps: List[StepResult] = field(default_factory=list)
    total_duration_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Конвертирует в словарь."""
        return {
            "pipeline_id": self.pipeline_id,
            "status": self.status.value,
            "steps": [
                {
                    "step_id": s.step_id,
                    "status": s.status.value,
                    "error": s.error,
                    "duration_ms": s.duration_ms,
                }
                for s in self.steps
            ],
            "total_duration_ms": self.total_duration_ms,
        }


class PipelineExecutor:
    """
    Выполняет pipeline.

    Поддерживает:
    - Последовательное выполнение шагов
    - Зависимости между шагами
    - Dry-run режим
    - Callbacks для прогресса

    Example:
        executor = PipelineExecutor(pipeline)
        result = executor.run(devices, credentials)
    """

    def __init__(
        self,
        pipeline: Pipeline,
        dry_run: bool = False,
        on_step_start: Optional[Callable[[PipelineStep], None]] = None,
        on_step_complete: Optional[Callable[[PipelineStep, StepResult], None]] = None,
    ):
        """
        Инициализация executor.

        Args:
            pipeline: Pipeline для выполнения
            dry_run: Режим dry-run (не применять изменения)
            on_step_start: Callback при начале шага
            on_step_complete: Callback при завершении шага
        """
        self.pipeline = pipeline
        self.dry_run = dry_run
        self.on_step_start = on_step_start
        self.on_step_complete = on_step_complete

        # Хранилище данных между шагами
        self._context: Dict[str, Any] = {}

    def run(
        self,
        devices: List[Any],
        credentials: Optional[Dict[str, str]] = None,
        netbox_config: Optional[Dict[str, str]] = None,
    ) -> PipelineResult:
        """
        Выполняет pipeline.

        Args:
            devices: Список устройств
            credentials: Учётные данные SSH
            netbox_config: Конфигурация NetBox

        Returns:
            PipelineResult: Результат выполнения
        """
        import time

        start_time = time.time()

        # Валидация
        errors = self.pipeline.validate()
        if errors:
            return PipelineResult(
                pipeline_id=self.pipeline.id,
                status=StepStatus.FAILED,
                steps=[
                    StepResult(
                        step_id="validation",
                        status=StepStatus.FAILED,
                        error="; ".join(errors),
                    )
                ],
            )

        # Инициализация контекста
        self._context = {
            "devices": devices,
            "credentials": credentials or {},
            "netbox_config": netbox_config or {},
            "dry_run": self.dry_run,
            "collected_data": {},  # Данные от collect шагов
        }

        self.pipeline.status = StepStatus.RUNNING
        results: List[StepResult] = []

        # Выполняем шаги
        for step in self.pipeline.get_enabled_steps():
            self.pipeline.current_step = step.id

            # Проверяем зависимости
            deps_ok = self._check_dependencies(step, results)
            if not deps_ok:
                step_result = StepResult(
                    step_id=step.id,
                    status=StepStatus.SKIPPED,
                    error="Dependencies not met",
                )
                results.append(step_result)
                continue

            # Callback начала
            if self.on_step_start:
                self.on_step_start(step)

            # Выполняем шаг
            step.status = StepStatus.RUNNING
            step_result = self._execute_step(step)
            step.status = step_result.status
            step.error = step_result.error
            results.append(step_result)

            # Callback завершения
            if self.on_step_complete:
                self.on_step_complete(step, step_result)

            # Если шаг failed - прерываем
            if step_result.status == StepStatus.FAILED:
                self.pipeline.status = StepStatus.FAILED
                break

        # Определяем итоговый статус
        if self.pipeline.status != StepStatus.FAILED:
            if all(r.status == StepStatus.COMPLETED for r in results):
                self.pipeline.status = StepStatus.COMPLETED
            elif any(r.status == StepStatus.FAILED for r in results):
                self.pipeline.status = StepStatus.FAILED
            else:
                self.pipeline.status = StepStatus.COMPLETED

        total_time = int((time.time() - start_time) * 1000)

        return PipelineResult(
            pipeline_id=self.pipeline.id,
            status=self.pipeline.status,
            steps=results,
            total_duration_ms=total_time,
        )

    def _check_dependencies(
        self,
        step: PipelineStep,
        results: List[StepResult],
    ) -> bool:
        """Проверяет что все зависимости выполнены успешно."""
        completed_steps = {r.step_id for r in results if r.status == StepStatus.COMPLETED}

        for dep_id in step.depends_on:
            if dep_id not in completed_steps:
                return False

        return True

    def _execute_step(self, step: PipelineStep) -> StepResult:
        """
        Выполняет один шаг.

        Args:
            step: Шаг для выполнения

        Returns:
            StepResult: Результат
        """
        import time

        start_time = time.time()

        try:
            if step.type == StepType.COLLECT:
                data = self._execute_collect(step)
            elif step.type == StepType.SYNC:
                data = self._execute_sync(step)
            elif step.type == StepType.EXPORT:
                data = self._execute_export(step)
            else:
                raise ValueError(f"Unknown step type: {step.type}")

            duration = int((time.time() - start_time) * 1000)

            return StepResult(
                step_id=step.id,
                status=StepStatus.COMPLETED,
                data=data,
                duration_ms=duration,
            )

        except Exception as e:
            duration = int((time.time() - start_time) * 1000)
            logger.error(f"Step {step.id} failed: {e}")

            return StepResult(
                step_id=step.id,
                status=StepStatus.FAILED,
                error=str(e),
                duration_ms=duration,
            )

    def _execute_collect(self, step: PipelineStep) -> Dict[str, Any]:
        """Выполняет collect шаг."""
        target = step.target
        devices = self._context["devices"]
        credentials = self._context["credentials"]

        logger.info(f"Collecting {target} from {len(devices)} devices...")

        if not devices:
            logger.warning(f"No devices to collect {target} from")
            collected = {"target": target, "data": [], "count": 0}
            self._context["collected_data"][target] = collected
            return collected

        # Импортируем collectors
        from ...collectors import (
            DeviceCollector,
            MACCollector,
            LLDPCollector,
            InterfaceCollector,
            InventoryCollector,
            ConfigBackupCollector,
        )

        # Получаем соответствующий collector
        collector_class_name = COLLECTOR_MAPPING.get(target)
        if not collector_class_name:
            raise ValueError(f"Unknown collector target: {target}")

        collector_classes = {
            "DeviceCollector": DeviceCollector,
            "MACCollector": MACCollector,
            "LLDPCollector": LLDPCollector,
            "InterfaceCollector": InterfaceCollector,
            "InventoryCollector": InventoryCollector,
            "ConfigBackupCollector": ConfigBackupCollector,
        }

        collector_class = collector_classes[collector_class_name]

        # Создаём collector с нужными параметрами
        options = step.options.copy()
        options["credentials"] = credentials

        # LLDP/CDP имеет параметр protocol
        if target == "lldp":
            options.setdefault("protocol", "lldp")
        elif target == "cdp":
            options["protocol"] = "cdp"
            collector_class = LLDPCollector

        # Backup имеет output_dir
        if target == "backup":
            options.setdefault("output_dir", "backups")

        try:
            collector = collector_class(**options)
            data = collector.collect(devices)
            logger.info(f"Collected {len(data)} {target} entries")
        except Exception as e:
            logger.error(f"Collector error for {target}: {e}")
            raise

        # Сохраняем в контекст для последующих шагов
        collected = {"target": target, "data": data, "count": len(data)}
        self._context["collected_data"][target] = collected

        return collected

    def _execute_sync(self, step: PipelineStep) -> Dict[str, Any]:
        """Выполняет sync шаг."""
        target = step.target
        options = step.options
        dry_run = self._context["dry_run"]
        netbox_config = self._context.get("netbox_config", {})

        logger.info(f"Syncing {target} to NetBox (dry_run={dry_run})...")

        # Проверяем NetBox config
        netbox_url = netbox_config.get("url")
        netbox_token = netbox_config.get("token")

        if not netbox_url or not netbox_token:
            raise ValueError("NetBox URL and token are required for sync")

        # Получаем данные из collected_data
        collected = self._context["collected_data"].get(target, {})
        data = collected.get("data", [])

        if not data:
            logger.warning(f"No {target} data to sync")
            return {"target": target, "dry_run": dry_run, "skipped": True, "reason": "No data"}

        # Импортируем NetBox
        from ...netbox.client import NetBoxClient
        from ...netbox.sync import NetBoxSync

        client = NetBoxClient(url=netbox_url, token=netbox_token)
        sync = NetBoxSync(client, dry_run=dry_run)

        # Выполняем соответствующий sync
        result = {}

        if target == "devices":
            site = options.get("site")
            role = options.get("role")
            result = sync.sync_devices_from_inventory(data, site=site, role=role)

        elif target == "interfaces":
            # Group by device
            by_device = {}
            for intf in data:
                hostname = intf.get("hostname", "")
                if hostname not in by_device:
                    by_device[hostname] = []
                by_device[hostname].append(intf)

            total_created = 0
            total_updated = 0
            total_skipped = 0
            total_failed = 0

            for hostname, interfaces in by_device.items():
                sync_result = sync.sync_interfaces(hostname, interfaces)
                total_created += sync_result.get("created", 0)
                total_updated += sync_result.get("updated", 0)
                total_skipped += sync_result.get("skipped", 0)
                total_failed += sync_result.get("failed", 0)

            result = {
                "created": total_created,
                "updated": total_updated,
                "skipped": total_skipped,
                "failed": total_failed,
            }

        elif target == "cables":
            # Используем LLDP данные
            lldp_data = self._context["collected_data"].get("lldp", {}).get("data", [])
            if not lldp_data:
                # Пробуем cdp
                lldp_data = self._context["collected_data"].get("cdp", {}).get("data", [])
            result = sync.sync_cables_from_lldp(lldp_data)

        elif target == "inventory":
            # Group by device
            by_device = {}
            for item in data:
                hostname = item.get("hostname", "")
                if hostname not in by_device:
                    by_device[hostname] = []
                by_device[hostname].append(item)

            total_created = 0
            total_updated = 0
            total_skipped = 0

            for hostname, items in by_device.items():
                sync_result = sync.sync_inventory(hostname, items)
                total_created += sync_result.get("created", 0)
                total_updated += sync_result.get("updated", 0)
                total_skipped += sync_result.get("skipped", 0)

            result = {
                "created": total_created,
                "updated": total_updated,
                "skipped": total_skipped,
            }

        elif target == "vlans":
            # TODO: Implement VLAN sync
            result = {"skipped": True, "reason": "VLAN sync not implemented yet"}

        else:
            raise ValueError(f"Unknown sync target: {target}")

        result["target"] = target
        result["dry_run"] = dry_run

        logger.info(f"Sync {target} result: {result}")
        return result

    def _execute_export(self, step: PipelineStep) -> Dict[str, Any]:
        """Выполняет export шаг."""
        target = step.target
        options = step.options
        format_ = options.get("format", "excel")
        output_dir = options.get("output_dir", "output")

        logger.info(f"Exporting {target} to {format_}...")

        # Получаем данные из collected_data
        collected = self._context["collected_data"].get(target, {})
        data = collected.get("data", [])

        if not data:
            logger.warning(f"No {target} data to export")
            return {"target": target, "format": format_, "skipped": True, "reason": "No data"}

        # Импортируем exporters
        from ...exporters.excel import ExcelExporter
        from ...exporters.csv_exporter import CSVExporter

        import os
        os.makedirs(output_dir, exist_ok=True)

        filename_base = f"{target}"
        result = {}

        if format_ == "excel":
            filepath = os.path.join(output_dir, f"{filename_base}.xlsx")
            exporter = ExcelExporter()
            exporter.export(data, filepath)
            result = {"target": target, "format": format_, "file": filepath, "count": len(data)}

        elif format_ == "csv":
            filepath = os.path.join(output_dir, f"{filename_base}.csv")
            exporter = CSVExporter()
            exporter.export(data, filepath)
            result = {"target": target, "format": format_, "file": filepath, "count": len(data)}

        elif format_ == "json":
            import json
            filepath = os.path.join(output_dir, f"{filename_base}.json")
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            result = {"target": target, "format": format_, "file": filepath, "count": len(data)}

        else:
            raise ValueError(f"Unknown export format: {format_}")

        logger.info(f"Exported {len(data)} {target} entries to {result.get('file')}")
        return result
