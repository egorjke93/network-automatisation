"""
Модели Pipeline - шаги и конвейеры синхронизации.

Архитектура:
- Pipeline: набор шагов с именем и описанием
- PipelineStep: один шаг (collect, sync, export) — match убран, это отдельная операция
- StepType: тип шага
- StepStatus: статус выполнения
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Any, Optional
from pathlib import Path

import yaml


class StepType(str, Enum):
    """Тип шага pipeline."""
    COLLECT = "collect"      # Сбор данных с устройств
    SYNC = "sync"            # Синхронизация с NetBox
    EXPORT = "export"        # Экспорт в файл


class StepStatus(str, Enum):
    """Статус выполнения шага."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


# Доступные collectors
AVAILABLE_COLLECTORS = {
    "devices", "interfaces", "mac", "lldp", "cdp", "inventory", "backup"
}

# Доступные sync targets
AVAILABLE_SYNC_TARGETS = {
    "devices", "interfaces", "cables", "inventory", "vlans", "ip_addresses"
}

# Маппинг sync target -> какой collect нужен (если отличается от target)
SYNC_COLLECT_MAPPING = {
    "cables": ["lldp", "cdp"],           # cables sync требует lldp или cdp collect
    "ip_addresses": ["interfaces"],       # ip_addresses sync требует interfaces collect
}

# Зависимости: target -> requires (какой sync должен быть выполнен до)
SYNC_DEPENDENCIES = {
    "interfaces": ["devices"],      # Интерфейсы требуют устройства
    "cables": ["interfaces"],       # Кабели требуют интерфейсы
    "inventory": ["devices"],       # Inventory требует устройства
    "vlans": ["devices"],           # VLAN требует устройства
    "ip_addresses": ["interfaces"], # IP адреса требуют интерфейсы
}


@dataclass
class PipelineStep:
    """
    Один шаг pipeline.

    Attributes:
        id: Уникальный идентификатор шага
        type: Тип шага (collect, sync, export)
        target: Цель (devices, interfaces, etc.)
        enabled: Включён ли шаг
        options: Дополнительные опции
        depends_on: Зависимости от других шагов
    """
    id: str
    type: StepType
    target: str
    enabled: bool = True
    options: Dict[str, Any] = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)

    # Runtime статус
    status: StepStatus = StepStatus.PENDING
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    def __post_init__(self):
        """Валидация после создания."""
        if isinstance(self.type, str):
            self.type = StepType(self.type)
        if isinstance(self.status, str):
            self.status = StepStatus(self.status)

    def validate(self) -> List[str]:
        """
        Валидирует шаг.

        Returns:
            List[str]: Список ошибок (пустой если всё OK)
        """
        errors = []

        if not self.id:
            errors.append("Step id is required")

        if self.type == StepType.COLLECT:
            if self.target not in AVAILABLE_COLLECTORS:
                errors.append(
                    f"Unknown collector '{self.target}'. "
                    f"Available: {AVAILABLE_COLLECTORS}"
                )

        elif self.type == StepType.SYNC:
            if self.target not in AVAILABLE_SYNC_TARGETS:
                errors.append(
                    f"Unknown sync target '{self.target}'. "
                    f"Available: {AVAILABLE_SYNC_TARGETS}"
                )

        return errors

    def to_dict(self) -> Dict[str, Any]:
        """Конвертирует в словарь."""
        return {
            "id": self.id,
            "type": self.type.value,
            "target": self.target,
            "enabled": self.enabled,
            "options": self.options,
            "depends_on": self.depends_on,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PipelineStep":
        """Создаёт из словаря."""
        return cls(
            id=data.get("id", ""),
            type=StepType(data.get("type", "collect")),
            target=data.get("target", ""),
            enabled=data.get("enabled", True),
            options=data.get("options", {}),
            depends_on=data.get("depends_on", []),
        )


@dataclass
class Pipeline:
    """
    Pipeline - набор шагов синхронизации.

    Attributes:
        id: Уникальный идентификатор
        name: Человекочитаемое имя
        description: Описание
        steps: Список шагов
        enabled: Включён ли pipeline
    """
    id: str
    name: str
    description: str = ""
    steps: List[PipelineStep] = field(default_factory=list)
    enabled: bool = True

    # Runtime
    status: StepStatus = StepStatus.PENDING
    current_step: Optional[str] = None

    def validate(self) -> List[str]:
        """
        Валидирует pipeline.

        Returns:
            List[str]: Список ошибок
        """
        errors = []

        if not self.id:
            errors.append("Pipeline id is required")

        if not self.name:
            errors.append("Pipeline name is required")

        if not self.steps:
            errors.append("Pipeline must have at least one step")

        # Валидируем каждый шаг
        step_ids = set()
        for step in self.steps:
            step_errors = step.validate()
            for err in step_errors:
                errors.append(f"Step '{step.id}': {err}")

            # Проверяем уникальность id
            if step.id in step_ids:
                errors.append(f"Duplicate step id: {step.id}")
            step_ids.add(step.id)

            # Проверяем зависимости
            for dep in step.depends_on:
                if dep not in step_ids:
                    # Зависимость должна быть определена ДО текущего шага
                    if not any(s.id == dep for s in self.steps):
                        errors.append(
                            f"Step '{step.id}' depends on unknown step '{dep}'"
                        )

        # Собираем информацию о collect шагах (для предупреждений)
        # Sync автоматически делает collect если данных нет, но явный collect
        # перед sync позволяет переиспользовать данные и избежать повторных сборов
        collected_targets = set()
        for step in self.steps:
            if step.type == StepType.COLLECT and step.enabled:
                collected_targets.add(step.target)

        # Проверяем sync зависимости между targets
        sync_steps = [s for s in self.steps if s.type == StepType.SYNC]
        synced_targets = set()
        for step in sync_steps:
            required = SYNC_DEPENDENCIES.get(step.target, [])
            for req in required:
                if req not in synced_targets:
                    # Проверяем есть ли sync для required
                    has_sync = any(
                        s.target == req and s.type == StepType.SYNC
                        for s in self.steps
                        if self.steps.index(s) < self.steps.index(step)
                    )
                    if not has_sync:
                        errors.append(
                            f"Sync '{step.target}' requires sync '{req}' first"
                        )
            synced_targets.add(step.target)

        return errors

    def get_enabled_steps(self) -> List[PipelineStep]:
        """Возвращает только включённые шаги."""
        return [s for s in self.steps if s.enabled]

    def get_step_by_id(self, step_id: str) -> Optional[PipelineStep]:
        """Находит шаг по id."""
        for step in self.steps:
            if step.id == step_id:
                return step
        return None

    def reset_status(self):
        """Сбрасывает статусы всех шагов."""
        self.status = StepStatus.PENDING
        self.current_step = None
        for step in self.steps:
            step.status = StepStatus.PENDING
            step.result = None
            step.error = None

    def to_dict(self) -> Dict[str, Any]:
        """Конвертирует в словарь."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "steps": [s.to_dict() for s in self.steps],
            "enabled": self.enabled,
            "status": self.status.value,
            "current_step": self.current_step,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Pipeline":
        """Создаёт из словаря."""
        steps = [
            PipelineStep.from_dict(s)
            for s in data.get("steps", [])
        ]
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            steps=steps,
            enabled=data.get("enabled", True),
        )

    @classmethod
    def from_yaml(cls, path: str) -> "Pipeline":
        """
        Загружает pipeline из YAML файла.

        Args:
            path: Путь к YAML файлу

        Returns:
            Pipeline: Загруженный pipeline
        """
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls.from_dict(data)

    def to_yaml(self, path: str):
        """
        Сохраняет pipeline в YAML файл.

        Args:
            path: Путь к файлу
        """
        data = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "enabled": self.enabled,
            "steps": [
                {
                    "id": s.id,
                    "type": s.type.value,
                    "target": s.target,
                    "enabled": s.enabled,
                    "options": s.options,
                    "depends_on": s.depends_on,
                }
                for s in self.steps
            ],
        }
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
