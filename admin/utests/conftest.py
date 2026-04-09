"""Shared pytest fixtures for TakenokoAI unit tests."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from interface.bus import MessageBus
from interface.llm import LLMConfig
from interface.logging import ModuleLogger
from interface.permissions import PermissionManager


@pytest.fixture
def mock_logger() -> ModuleLogger:
    return ModuleLogger("TEST", "fixture")


@pytest.fixture
def mock_bus(mock_logger: ModuleLogger) -> MessageBus:
    return MessageBus(mock_logger)


@pytest.fixture
def mock_llm_config() -> LLMConfig:
    return LLMConfig(model_name="test-model", temperature=0.0, max_tokens=100)


@pytest.fixture
def mock_permissions(mock_logger: ModuleLogger) -> PermissionManager:
    return PermissionManager(mock_logger)
