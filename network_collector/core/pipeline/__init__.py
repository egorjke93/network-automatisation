"""
Pipeline module - настраиваемые конвейеры синхронизации.

Позволяет определять последовательность шагов:
- collect (сбор данных с устройств)
- sync (синхронизация с NetBox)
- export (экспорт в файл)

Example:
    from core.pipeline import Pipeline, PipelineExecutor

    pipeline = Pipeline.from_yaml("pipelines/default.yaml")
    executor = PipelineExecutor(pipeline)
    result = executor.run(devices, credentials)
"""

from .models import Pipeline, PipelineStep, StepType, StepStatus
from .executor import PipelineExecutor

__all__ = [
    "Pipeline",
    "PipelineStep",
    "StepType",
    "StepStatus",
    "PipelineExecutor",
]
