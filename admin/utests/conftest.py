"""Shared pytest fixtures for TakenokoAI unit tests."""

from __future__ import annotations

import pytest

from interface.bus import MessageBus
from interface.llm import LLMConfig
from interface.logging import ModuleLogger
from interface.permissions import PermissionManager


@pytest.fixture
def mock_logger() -> ModuleLogger:
    """A ModuleLogger instance scoped to the test-system family."""
    return ModuleLogger("TS", "test")


@pytest.fixture
def mock_bus(mock_logger: ModuleLogger) -> MessageBus:
    """A MessageBus with per-family queue limits matching default.yaml."""
    queue_limits = {"Pr": 10, "Re": 5, "Ev": 5, "Me": 5, "Mo": 5}
    return MessageBus(mock_logger, queue_limits=queue_limits)


@pytest.fixture
def mock_permissions(mock_logger: ModuleLogger) -> PermissionManager:
    """A PermissionManager with default grants."""
    return PermissionManager(mock_logger)


@pytest.fixture
def mock_llm_config() -> LLMConfig:
    """An LLMConfig with default values."""
    return LLMConfig()
