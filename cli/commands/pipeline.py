"""
Команда pipeline.

Управление и запуск pipelines (конвейеров синхронизации).

Примеры:
    python -m network_collector pipeline list
    python -m network_collector pipeline show default
    python -m network_collector pipeline run default --dry-run
    python -m network_collector pipeline validate default
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional

from ...core.pipeline.models import Pipeline, StepStatus
from ...core.pipeline.executor import PipelineExecutor, PipelineResult

logger = logging.getLogger(__name__)

# Директория с pipeline файлами
PIPELINES_DIR = Path(__file__).parent.parent.parent / "pipelines"


def _get_pipeline_files() -> list[Path]:
    """Возвращает список всех YAML файлов в директории pipelines."""
    if not PIPELINES_DIR.exists():
        return []
    return list(PIPELINES_DIR.glob("*.yaml")) + list(PIPELINES_DIR.glob("*.yml"))


def _load_pipeline(name_or_path: str) -> Optional[Pipeline]:
    """
    Загружает pipeline по имени или пути.

    Args:
        name_or_path: Имя pipeline (без .yaml) или путь к файлу

    Returns:
        Pipeline или None если не найден
    """
    # Если это путь к файлу
    if os.path.exists(name_or_path):
        return Pipeline.from_yaml(name_or_path)

    # Ищем в директории pipelines
    for ext in [".yaml", ".yml"]:
        path = PIPELINES_DIR / f"{name_or_path}{ext}"
        if path.exists():
            return Pipeline.from_yaml(str(path))

    return None


def _print_pipeline_list(pipelines: list[Pipeline], format_: str = "table") -> None:
    """Выводит список pipelines."""
    if format_ == "json":
        data = [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "enabled": p.enabled,
                "steps_count": len(p.steps),
            }
            for p in pipelines
        ]
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return

    # Табличный вывод
    print(f"\n{'ID':<20} {'Name':<25} {'Steps':<7} {'Enabled':<8} Description")
    print("-" * 80)

    for p in pipelines:
        enabled = "✓" if p.enabled else "✗"
        desc = p.description[:30] + "..." if len(p.description) > 30 else p.description
        print(f"{p.id:<20} {p.name:<25} {len(p.steps):<7} {enabled:<8} {desc}")

    print(f"\nTotal: {len(pipelines)} pipeline(s)")


def _print_pipeline_details(pipeline: Pipeline, format_: str = "table") -> None:
    """Выводит детали pipeline."""
    if format_ == "json":
        print(json.dumps(pipeline.to_dict(), indent=2, ensure_ascii=False))
        return

    print(f"\n{'='*60}")
    print(f"Pipeline: {pipeline.name}")
    print(f"{'='*60}")
    print(f"ID:          {pipeline.id}")
    print(f"Description: {pipeline.description}")
    print(f"Enabled:     {'Yes' if pipeline.enabled else 'No'}")
    print(f"Steps:       {len(pipeline.steps)}")
    print()

    print("Steps:")
    print("-" * 60)
    for i, step in enumerate(pipeline.steps, 1):
        enabled = "✓" if step.enabled else "✗"
        deps = f" (depends: {', '.join(step.depends_on)})" if step.depends_on else ""
        print(f"  {i}. [{enabled}] {step.id}")
        print(f"      Type: {step.type.value}, Target: {step.target}{deps}")
        if step.options:
            opts_str = ", ".join(f"{k}={v}" for k, v in step.options.items())
            print(f"      Options: {opts_str}")

    print(f"{'='*60}\n")


def _print_validation_result(pipeline: Pipeline, errors: list[str]) -> None:
    """Выводит результат валидации."""
    if errors:
        print(f"\n✗ Pipeline '{pipeline.id}' has {len(errors)} error(s):")
        for err in errors:
            print(f"  - {err}")
    else:
        print(f"\n✓ Pipeline '{pipeline.id}' is valid ({len(pipeline.steps)} steps)")


def _print_run_result(result: PipelineResult, format_: str = "table") -> None:
    """Выводит результат выполнения pipeline."""
    if format_ == "json":
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
        return

    status_icons = {
        StepStatus.COMPLETED: "✓",
        StepStatus.FAILED: "✗",
        StepStatus.SKIPPED: "○",
        StepStatus.RUNNING: "►",
        StepStatus.PENDING: "·",
    }

    action_icons = {"create": "+", "update": "~", "delete": "-"}

    # Сначала выводим детали изменений
    _print_run_changes(result, action_icons)

    # Затем сводку
    print(f"\n{'='*60}")
    print(f"Pipeline Run Result: {result.pipeline_id}")
    print(f"{'='*60}")

    overall = status_icons.get(result.status, "?")
    print(f"Status: {overall} {result.status.value.upper()}")
    print(f"Duration: {result.total_duration_ms}ms")
    print()

    print("Steps:")
    print("-" * 60)
    for step in result.steps:
        icon = status_icons.get(step.status, "?")
        # Добавляем счётчики к каждому шагу
        stats_str = ""
        if step.data and isinstance(step.data, dict):
            parts = []
            if step.data.get("created", 0) > 0:
                parts.append(f"+{step.data['created']}")
            if step.data.get("updated", 0) > 0:
                parts.append(f"~{step.data['updated']}")
            if step.data.get("deleted", 0) > 0:
                parts.append(f"-{step.data['deleted']}")
            if parts:
                stats_str = f" ({', '.join(parts)})"

        print(f"  {icon} {step.step_id:<30} {step.duration_ms:>6}ms{stats_str}")
        if step.error:
            print(f"      Error: {step.error}")

    print(f"{'='*60}\n")


def _print_run_changes(result: PipelineResult, action_icons: dict) -> None:
    """Выводит детали изменений из результатов pipeline."""
    # Собираем все детали из шагов
    has_details = False
    for step in result.steps:
        if step.data and isinstance(step.data, dict) and step.data.get("details"):
            has_details = True
            break

    if not has_details:
        return

    print(f"\n{'='*60}")
    print("ДЕТАЛИ ИЗМЕНЕНИЙ")
    print(f"{'='*60}")

    for step in result.steps:
        if not step.data or not isinstance(step.data, dict):
            continue

        details = step.data.get("details", {})
        if not details or not any(details.values()):
            continue

        print(f"\n{step.step_id.upper()}:")

        for action in ("create", "update", "delete"):
            items = details.get(action, [])
            if not items:
                continue

            icon = action_icons.get(action, "•")

            for item in items:
                if isinstance(item, dict):
                    name = item.get("name", "")
                    device = item.get("device", "")
                    changes = item.get("changes", [])

                    if device:
                        if changes:
                            print(f"  {icon} {device}: {name} ({', '.join(changes)})")
                        else:
                            print(f"  {icon} {device}: {name}")
                    else:
                        if changes:
                            print(f"  {icon} {name} ({', '.join(changes)})")
                        else:
                            print(f"  {icon} {name}")
                else:
                    print(f"  {icon} {item}")


def cmd_pipeline(args, ctx=None) -> None:
    """
    Обработчик команды pipeline.

    Subcommands:
        list     - Показать все pipelines
        show     - Показать детали pipeline
        run      - Запустить pipeline
        validate - Валидировать pipeline
        create   - Создать pipeline из YAML
        delete   - Удалить pipeline
    """
    subcommand = getattr(args, "pipeline_command", None)

    if subcommand == "list":
        _cmd_list(args)
    elif subcommand == "show":
        _cmd_show(args)
    elif subcommand == "run":
        _cmd_run(args, ctx)
    elif subcommand == "validate":
        _cmd_validate(args)
    elif subcommand == "create":
        _cmd_create(args)
    elif subcommand == "delete":
        _cmd_delete(args)
    else:
        print("Usage: pipeline {list|show|run|validate|create|delete}")
        print("\nUse 'pipeline <subcommand> --help' for details")


def _cmd_list(args) -> None:
    """Показать список pipelines."""
    files = _get_pipeline_files()

    if not files:
        print(f"\nNo pipelines found in {PIPELINES_DIR}")
        print("Create a pipeline YAML file in the pipelines/ directory")
        return

    pipelines = []
    for f in files:
        try:
            p = Pipeline.from_yaml(str(f))
            pipelines.append(p)
        except Exception as e:
            logger.warning(f"Failed to load {f}: {e}")

    format_ = getattr(args, "format", "table")
    _print_pipeline_list(pipelines, format_)


def _cmd_show(args) -> None:
    """Показать детали pipeline."""
    name = getattr(args, "name", None)
    if not name:
        print("Error: pipeline name required")
        return

    pipeline = _load_pipeline(name)
    if not pipeline:
        print(f"Error: pipeline '{name}' not found")
        return

    format_ = getattr(args, "format", "table")
    _print_pipeline_details(pipeline, format_)


def _cmd_run(args, ctx=None) -> None:
    """Запустить pipeline."""
    from ..utils import load_devices, get_credentials
    from ...config import config
    from ...core.credentials import get_netbox_token

    name = getattr(args, "name", None)
    if not name:
        print("Error: pipeline name required")
        return

    pipeline = _load_pipeline(name)
    if not pipeline:
        print(f"Error: pipeline '{name}' not found")
        return

    # Валидация
    errors = pipeline.validate()
    if errors:
        _print_validation_result(pipeline, errors)
        return

    # Загружаем устройства
    devices_file = getattr(args, "devices", "devices_ips.py")
    try:
        devices = load_devices(devices_file)
    except Exception as e:
        print(f"Error loading devices: {e}")
        return

    if not devices:
        print("No devices to process")
        return

    # Получаем credentials
    credentials = get_credentials()

    # NetBox config - используем get_netbox_token для поддержки keyring/Credential Manager
    netbox_config = {}
    if config.netbox:
        netbox_config["url"] = config.netbox.url
        # get_netbox_token проверяет: env NETBOX_TOKEN → keyring → config.yaml
        netbox_config["token"] = get_netbox_token(config.netbox.token)

    # Переопределение из аргументов (приоритет выше)
    if getattr(args, "netbox_url", None):
        netbox_config["url"] = args.netbox_url
    if getattr(args, "netbox_token", None):
        netbox_config["token"] = args.netbox_token

    # Dry-run режим
    dry_run = getattr(args, "dry_run", True)
    if getattr(args, "apply", False):
        dry_run = False

    print(f"\nRunning pipeline: {pipeline.name}")
    print(f"Devices: {len(devices)}")
    print(f"Dry-run: {dry_run}")
    print("-" * 40)

    # Callback для прогресса
    def on_step_start(step):
        print(f"  ► {step.id}...")

    def on_step_complete(step, result):
        icon = "✓" if result.status == StepStatus.COMPLETED else "✗"
        print(f"  {icon} {step.id} ({result.duration_ms}ms)")
        if result.error:
            print(f"    Error: {result.error}")

    # Выполнение
    executor = PipelineExecutor(
        pipeline,
        dry_run=dry_run,
        on_step_start=on_step_start,
        on_step_complete=on_step_complete,
    )

    # Подготовка credentials как dict
    creds_dict = {}
    if credentials:
        creds_dict = {
            "username": credentials.username,
            "password": credentials.password,
            "secret": credentials.secret,
        }

    result = executor.run(
        devices=devices,
        credentials=creds_dict,
        netbox_config=netbox_config,
    )

    format_ = getattr(args, "format", "table")
    _print_run_result(result, format_)


def _cmd_validate(args) -> None:
    """Валидировать pipeline."""
    name = getattr(args, "name", None)
    if not name:
        print("Error: pipeline name required")
        return

    pipeline = _load_pipeline(name)
    if not pipeline:
        print(f"Error: pipeline '{name}' not found")
        return

    errors = pipeline.validate()
    _print_validation_result(pipeline, errors)


def _cmd_create(args) -> None:
    """Создать pipeline из YAML файла."""
    source = getattr(args, "source", None)
    if not source:
        print("Error: source YAML file required")
        return

    if not os.path.exists(source):
        print(f"Error: file '{source}' not found")
        return

    try:
        pipeline = Pipeline.from_yaml(source)
    except Exception as e:
        print(f"Error parsing YAML: {e}")
        return

    # Валидация
    errors = pipeline.validate()
    if errors:
        print(f"\n✗ Pipeline has {len(errors)} error(s):")
        for err in errors:
            print(f"  - {err}")
        return

    # Сохраняем в директорию pipelines
    PIPELINES_DIR.mkdir(exist_ok=True)
    dest = PIPELINES_DIR / f"{pipeline.id}.yaml"

    if dest.exists() and not getattr(args, "force", False):
        print(f"Error: pipeline '{pipeline.id}' already exists")
        print("Use --force to overwrite")
        return

    pipeline.to_yaml(str(dest))
    print(f"✓ Pipeline '{pipeline.id}' created: {dest}")


def _cmd_delete(args) -> None:
    """Удалить pipeline."""
    name = getattr(args, "name", None)
    if not name:
        print("Error: pipeline name required")
        return

    # Ищем файл
    target = None
    for ext in [".yaml", ".yml"]:
        path = PIPELINES_DIR / f"{name}{ext}"
        if path.exists():
            target = path
            break

    if not target:
        print(f"Error: pipeline '{name}' not found")
        return

    # Подтверждение
    if not getattr(args, "force", False):
        confirm = input(f"Delete pipeline '{name}'? [y/N]: ")
        if confirm.lower() != "y":
            print("Cancelled")
            return

    target.unlink()
    print(f"✓ Pipeline '{name}' deleted")
