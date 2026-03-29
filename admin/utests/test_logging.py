"""Group: Logging

Tests for interface/logging.py — LogCategory enum, ModuleLogger construction
and methods, and setup_logging() configuration.
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock

from interface.logging import LogCategory, ModuleLogger, setup_logging


# ── LogCategory ──


class TestLogCategory:
    def test_has_expected_values(self):
        expected = {"MESSAGE", "THOUGHT", "ACTION", "SYSTEM", "PERMISSION"}
        actual = {member.value for member in LogCategory}
        assert actual == expected

    def test_members_are_strings(self):
        for member in LogCategory:
            assert isinstance(member, str)


# ── ModuleLogger ──


class TestModuleLogger:
    def test_construction(self):
        logger = ModuleLogger("Re", "vision")
        assert logger.family_prefix == "Re"
        assert logger.module_name == "vision"

    def test_qualified_name(self):
        logger = ModuleLogger("Pr", "main")
        assert logger.qualified_name == "Pr.main"

    def test_log_calls_underlying_logger(self):
        logger = ModuleLogger("Ev", "test")
        logger._logger = MagicMock()
        logger.log(logging.INFO, LogCategory.ACTION, "test message", data={"key": "val"})
        logger._logger.log.assert_called_once()
        args, kwargs = logger._logger.log.call_args
        assert args[0] == logging.INFO
        assert args[1] == "test message"
        assert kwargs["extra"]["category"] == "ACTION"
        assert kwargs["extra"]["family"] == "Ev"
        assert kwargs["extra"]["data"] == {"key": "val"}

    def test_log_default_data_is_empty_dict(self):
        logger = ModuleLogger("Mo", "test")
        logger._logger = MagicMock()
        logger.log(logging.DEBUG, LogCategory.THOUGHT, "no data")
        _, kwargs = logger._logger.log.call_args
        assert kwargs["extra"]["data"] == {}

    def test_thought_convenience_method(self):
        logger = ModuleLogger("Pr", "main")
        logger._logger = MagicMock()
        logger.thought("thinking hard")
        logger._logger.log.assert_called_once()
        args, kwargs = logger._logger.log.call_args
        assert args[0] == logging.DEBUG
        assert kwargs["extra"]["category"] == "THOUGHT"

    def test_action_convenience_method(self):
        logger = ModuleLogger("Re", "main")
        logger._logger = MagicMock()
        logger.action("doing something")
        logger._logger.log.assert_called_once()
        args, kwargs = logger._logger.log.call_args
        assert args[0] == logging.INFO
        assert kwargs["extra"]["category"] == "ACTION"

    def test_bus_message_convenience_method(self):
        logger = ModuleLogger("Me", "main")
        logger._logger = MagicMock()
        logger.bus_message("Re -> Mo [msg001]", data={"body_preview": "hi"})
        logger._logger.log.assert_called_once()
        args, kwargs = logger._logger.log.call_args
        assert args[0] == logging.DEBUG
        assert kwargs["extra"]["category"] == "MESSAGE"
        assert kwargs["extra"]["data"] == {"body_preview": "hi"}


# ── setup_logging ──


class TestSetupLogging:
    def test_creates_log_directory(self, tmp_path: Path):
        log_dir = tmp_path / "test_logs"
        assert not log_dir.exists()
        setup_logging(log_dir=str(log_dir))
        assert log_dir.exists()
        assert log_dir.is_dir()

    def test_configures_handlers(self, tmp_path: Path):
        log_dir = tmp_path / "handler_logs"
        # Remove any existing handlers first
        root = logging.getLogger("takenoko")
        original_handlers = root.handlers[:]

        setup_logging(log_dir=str(log_dir), level=logging.DEBUG)

        # Should have added at least 2 handlers (file + console)
        new_handlers = [h for h in root.handlers if h not in original_handlers]
        assert len(new_handlers) >= 2

        # Verify log file was created
        log_file = log_dir / "takenoko.log"
        assert log_file.exists()

        # Clean up added handlers to avoid polluting other tests
        for h in new_handlers:
            root.removeHandler(h)
            h.close()
