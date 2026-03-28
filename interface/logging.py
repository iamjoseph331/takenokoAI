"""Structured logging for TakenokoAI modules."""

from __future__ import annotations

import logging
import logging.handlers
from enum import StrEnum
from pathlib import Path
from typing import Any


class LogCategory(StrEnum):
    """Categories for structured log entries."""

    MESSAGE = "MESSAGE"
    THOUGHT = "THOUGHT"
    ACTION = "ACTION"
    SYSTEM = "SYSTEM"
    PERMISSION = "PERMISSION"


class ModuleLogger:
    """Structured logger scoped to a specific module within a family.

    Wraps stdlib logging with family_prefix and module_name context
    so every log line is traceable to its source module.
    """

    def __init__(self, family_prefix: str, module_name: str) -> None:
        self.family_prefix = family_prefix
        self.module_name = module_name
        self._logger = logging.getLogger(f"takenoko.{family_prefix}.{module_name}")

    @property
    def qualified_name(self) -> str:
        return f"{self.family_prefix}.{self.module_name}"

    def log(
        self,
        level: int,
        category: LogCategory,
        message: str,
        *,
        data: dict[str, Any] | None = None,
    ) -> None:
        """Emit a structured log entry."""
        extra = {
            "family": self.family_prefix,
            "module": self.module_name,
            "category": category.value,
            "data": data or {},
        }
        self._logger.log(level, message, extra=extra)

    def thought(self, message: str, *, data: dict[str, Any] | None = None) -> None:
        """Log a thought (LLM reasoning step)."""
        self.log(logging.DEBUG, LogCategory.THOUGHT, message, data=data)

    def action(self, message: str, *, data: dict[str, Any] | None = None) -> None:
        """Log an action taken by the module."""
        self.log(logging.INFO, LogCategory.ACTION, message, data=data)

    def bus_message(
        self, message: str, *, data: dict[str, Any] | None = None
    ) -> None:
        """Log a bus message sent or received."""
        self.log(logging.DEBUG, LogCategory.MESSAGE, message, data=data)


class _StructuredFormatter(logging.Formatter):
    """Formatter that includes structured fields from extra."""

    def format(self, record: logging.LogRecord) -> str:
        family = getattr(record, "family", "?")
        module = getattr(record, "module", "?")
        category = getattr(record, "category", "?")
        data = getattr(record, "data", {})
        base = super().format(record)
        data_str = f" | {data}" if data else ""
        return f"[{family}.{module}] [{category}] {base}{data_str}"


def setup_logging(
    log_dir: str = "logs",
    level: int = logging.DEBUG,
) -> None:
    """Configure rotating file + console logging for the agent.

    Args:
        log_dir: Directory for log files. Created if it doesn't exist.
        level: Minimum log level.
    """
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    formatter = _StructuredFormatter(
        "%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Rotating file handler — 10 MB per file, keep 5 backups
    file_handler = logging.handlers.RotatingFileHandler(
        log_path / "takenoko.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)

    root = logging.getLogger("takenoko")
    root.setLevel(level)
    root.addHandler(file_handler)
    root.addHandler(console_handler)
