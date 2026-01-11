"""
Контекст выполнения для отслеживания запусков.

RunContext прокидывается через все слои приложения:
- CLI → Collectors → Exporters
- CLI → NetBox Sync

Предоставляет:
- run_id: уникальный идентификатор запуска
- started_at: время начала
- dry_run: режим симуляции
- triggered_by: источник запуска (cli/cron/api)
- output_dir: папка для отчётов данного запуска

Пример использования:
    ctx = RunContext.create(dry_run=True)
    collector = InterfaceCollector(context=ctx)
    data = collector.collect(devices)
    # Отчёты сохраняются в reports/run_2025-03-14T12-30-22/
"""

import uuid
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Literal

logger = logging.getLogger(__name__)

TriggerSource = Literal["cli", "cron", "api", "test"]


@dataclass
class RunContext:
    """
    Контекст выполнения операции.

    Создаётся один раз при запуске команды и прокидывается
    через все слои приложения.

    Attributes:
        run_id: Уникальный идентификатор запуска (UUID или timestamp)
        started_at: Время начала выполнения
        dry_run: Режим симуляции (без реальных изменений)
        triggered_by: Источник запуска (cli/cron/api/test)
        command: Команда CLI которая была вызвана
        output_dir: Папка для отчётов данного запуска
        extra: Дополнительные данные контекста
    """

    run_id: str
    started_at: datetime
    dry_run: bool = False
    triggered_by: TriggerSource = "cli"
    command: str = ""
    output_dir: Optional[Path] = None
    extra: dict = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        dry_run: bool = False,
        triggered_by: TriggerSource = "cli",
        command: str = "",
        base_output_dir: Optional[Path] = None,
        use_timestamp_id: bool = True,
    ) -> "RunContext":
        """
        Создаёт новый контекст выполнения.

        Args:
            dry_run: Режим симуляции
            triggered_by: Источник запуска
            command: Название команды CLI
            base_output_dir: Базовая папка для отчётов (default: reports/)
            use_timestamp_id: Использовать timestamp вместо UUID

        Returns:
            RunContext: Новый контекст
        """
        started_at = datetime.now()

        if use_timestamp_id:
            # Формат: 2025-03-14T12-30-22
            run_id = started_at.strftime("%Y-%m-%dT%H-%M-%S")
        else:
            # Короткий UUID
            run_id = str(uuid.uuid4())[:8]

        # Определяем папку для отчётов
        if base_output_dir is None:
            base_output_dir = Path("reports")

        output_dir = base_output_dir / f"run_{run_id}"

        ctx = cls(
            run_id=run_id,
            started_at=started_at,
            dry_run=dry_run,
            triggered_by=triggered_by,
            command=command,
            output_dir=output_dir,
        )

        logger.debug(f"Created RunContext: {ctx.run_id} (dry_run={dry_run})")
        return ctx

    def ensure_output_dir(self) -> Path:
        """
        Создаёт папку для отчётов если её нет.

        Returns:
            Path: Путь к папке отчётов
        """
        if self.output_dir:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            return self.output_dir
        raise ValueError("output_dir not set")

    def get_output_path(self, filename: str) -> Path:
        """
        Возвращает полный путь для файла отчёта.

        Args:
            filename: Имя файла (например, "interfaces.xlsx")

        Returns:
            Path: Полный путь (reports/run_xxx/interfaces.xlsx)
        """
        self.ensure_output_dir()
        return self.output_dir / filename

    @property
    def elapsed_seconds(self) -> float:
        """Время выполнения в секундах."""
        return (datetime.now() - self.started_at).total_seconds()

    @property
    def elapsed_human(self) -> str:
        """Время выполнения в человекочитаемом формате."""
        elapsed = self.elapsed_seconds
        if elapsed < 60:
            return f"{elapsed:.1f}s"
        elif elapsed < 3600:
            minutes = int(elapsed // 60)
            seconds = int(elapsed % 60)
            return f"{minutes}m {seconds}s"
        else:
            hours = int(elapsed // 3600)
            minutes = int((elapsed % 3600) // 60)
            return f"{hours}h {minutes}m"

    def log_prefix(self) -> str:
        """
        Возвращает префикс для логов.

        Returns:
            str: Префикс вида "[run_id][command]"
        """
        if self.command:
            return f"[{self.run_id}][{self.command}]"
        return f"[{self.run_id}]"

    def to_dict(self) -> dict:
        """
        Сериализует контекст в словарь для JSON/отчётов.

        Returns:
            dict: Данные контекста
        """
        return {
            "run_id": self.run_id,
            "started_at": self.started_at.isoformat(),
            "dry_run": self.dry_run,
            "triggered_by": self.triggered_by,
            "command": self.command,
            "output_dir": str(self.output_dir) if self.output_dir else None,
            "elapsed_seconds": self.elapsed_seconds,
            "extra": self.extra,
        }

    def save_summary(self, stats: Optional[dict] = None) -> Path:
        """
        Сохраняет summary.json в папку отчётов.

        Args:
            stats: Дополнительная статистика для сохранения

        Returns:
            Path: Путь к файлу summary.json
        """
        import json

        summary = self.to_dict()
        summary["completed_at"] = datetime.now().isoformat()

        if stats:
            summary["stats"] = stats

        summary_path = self.get_output_path("summary.json")
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

        logger.info(f"Summary saved: {summary_path}")
        return summary_path

    def __str__(self) -> str:
        dry = " [DRY-RUN]" if self.dry_run else ""
        return f"RunContext({self.run_id}{dry})"

    def __repr__(self) -> str:
        return (
            f"RunContext(run_id={self.run_id!r}, "
            f"dry_run={self.dry_run}, "
            f"triggered_by={self.triggered_by!r}, "
            f"command={self.command!r})"
        )


# Глобальный контекст для случаев когда нет явного прокидывания
_current_context: Optional[RunContext] = None


def get_current_context() -> Optional[RunContext]:
    """Возвращает текущий глобальный контекст."""
    return _current_context


def set_current_context(ctx: Optional[RunContext]) -> None:
    """Устанавливает текущий глобальный контекст."""
    global _current_context
    _current_context = ctx


class RunContextFilter(logging.Filter):
    """
    Logging filter для добавления run_id в каждое сообщение.

    Автоматически добавляет run_id из глобального контекста.

    Использование:
        # В CLI после создания контекста
        handler = logging.StreamHandler()
        handler.addFilter(RunContextFilter())
        logging.getLogger().addHandler(handler)

    Формат лога:
        [2025-12-26T19-34-22] INFO - Собрано 100 записей
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Добавляет run_id к записи лога.

        Args:
            record: Запись лога

        Returns:
            bool: True (всегда пропускаем запись)
        """
        ctx = get_current_context()
        if ctx:
            record.run_id = ctx.run_id
            # Добавляем префикс к сообщению если его ещё нет
            if not record.msg.startswith(f"[{ctx.run_id}]"):
                record.msg = f"[{ctx.run_id}] {record.msg}"
        else:
            record.run_id = "-"
        return True


def setup_logging_with_context(level: int = logging.INFO) -> None:
    """
    Настраивает логирование с автоматическим run_id.

    Args:
        level: Уровень логирования

    Пример:
        ctx = RunContext.create(command="sync-netbox")
        set_current_context(ctx)
        setup_logging_with_context()
        # Теперь все логи будут с [run_id]
    """
    # Удаляем существующие handlers
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Создаём новый handler с фильтром
    handler = logging.StreamHandler()
    handler.setLevel(level)

    # Формат без run_id (он добавляется через фильтр)
    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    handler.addFilter(RunContextFilter())

    root_logger.addHandler(handler)
    root_logger.setLevel(level)
