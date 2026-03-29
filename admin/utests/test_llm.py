"""Group: LLMClient

Tests for interface/llm.py — LLMConfig defaults and custom values,
LLMClient prompt loading/caching, update_config, and cache invalidation.
Real API calls (complete/complete_stream) are not tested here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interface.llm import LLMClient, LLMConfig
from interface.logging import ModuleLogger


# ── LLMConfig ──


class TestLLMConfig:
    def test_defaults(self):
        config = LLMConfig()
        assert config.model_name == "gpt-4o"
        assert config.temperature == 0.7
        assert config.max_tokens == 4096
        assert config.system_prompt_path is None
        assert config.extra_params == {}

    def test_custom_values(self):
        config = LLMConfig(
            model_name="anthropic/claude-sonnet-4-20250514",
            temperature=0.3,
            max_tokens=8192,
            system_prompt_path="/tmp/prompt.md",
            extra_params={"top_p": 0.9},
        )
        assert config.model_name == "anthropic/claude-sonnet-4-20250514"
        assert config.temperature == 0.3
        assert config.max_tokens == 8192
        assert config.system_prompt_path == "/tmp/prompt.md"
        assert config.extra_params == {"top_p": 0.9}


# ── LLMClient ──


class TestLLMClientPromptLoading:
    @pytest.mark.asyncio
    async def test_load_system_prompt_missing_file_returns_empty(self, mock_logger: ModuleLogger):
        config = LLMConfig(system_prompt_path="/nonexistent/path/prompt.md")
        client = LLMClient(config, mock_logger)
        result = await client.load_system_prompt()
        assert result == ""

    @pytest.mark.asyncio
    async def test_load_system_prompt_no_path_returns_empty(self, mock_logger: ModuleLogger):
        config = LLMConfig(system_prompt_path=None)
        client = LLMClient(config, mock_logger)
        result = await client.load_system_prompt()
        assert result == ""

    @pytest.mark.asyncio
    async def test_load_system_prompt_reads_file(self, mock_logger: ModuleLogger, tmp_path: Path):
        prompt_file = tmp_path / "test_prompt.md"
        prompt_file.write_text("You are a helpful assistant.", encoding="utf-8")

        config = LLMConfig(system_prompt_path=str(prompt_file))
        client = LLMClient(config, mock_logger)
        result = await client.load_system_prompt()
        assert result == "You are a helpful assistant."

    @pytest.mark.asyncio
    async def test_load_system_prompt_caches(self, mock_logger: ModuleLogger, tmp_path: Path):
        prompt_file = tmp_path / "cached_prompt.md"
        prompt_file.write_text("Original prompt.", encoding="utf-8")

        config = LLMConfig(system_prompt_path=str(prompt_file))
        client = LLMClient(config, mock_logger)

        first = await client.load_system_prompt()
        assert first == "Original prompt."

        # Modify the file — cached value should still be returned
        prompt_file.write_text("Modified prompt.", encoding="utf-8")
        second = await client.load_system_prompt()
        assert second == "Original prompt."

    @pytest.mark.asyncio
    async def test_reload_system_prompt_clears_cache(self, mock_logger: ModuleLogger, tmp_path: Path):
        prompt_file = tmp_path / "reload_prompt.md"
        prompt_file.write_text("Original.", encoding="utf-8")

        config = LLMConfig(system_prompt_path=str(prompt_file))
        client = LLMClient(config, mock_logger)

        first = await client.load_system_prompt()
        assert first == "Original."

        prompt_file.write_text("Updated.", encoding="utf-8")
        reloaded = await client.reload_system_prompt()
        assert reloaded == "Updated."


class TestLLMClientUpdateConfig:
    def test_update_known_keys(self, mock_logger: ModuleLogger):
        config = LLMConfig()
        client = LLMClient(config, mock_logger)
        client.update_config(model_name="ollama/qwen2.5", temperature=0.1)
        assert client.config.model_name == "ollama/qwen2.5"
        assert client.config.temperature == 0.1

    def test_update_raises_for_unknown_key(self, mock_logger: ModuleLogger):
        config = LLMConfig()
        client = LLMClient(config, mock_logger)
        with pytest.raises(ValueError, match="Unknown LLM config key"):
            client.update_config(nonexistent_key="value")

    def test_update_invalidates_cache_on_path_change(self, mock_logger: ModuleLogger, tmp_path: Path):
        prompt_file = tmp_path / "old_prompt.md"
        prompt_file.write_text("old", encoding="utf-8")

        config = LLMConfig(system_prompt_path=str(prompt_file))
        client = LLMClient(config, mock_logger)

        # Manually set cache
        client._system_prompt_cache = "cached value"

        new_prompt = tmp_path / "new_prompt.md"
        new_prompt.write_text("new", encoding="utf-8")
        client.update_config(system_prompt_path=str(new_prompt))

        # Cache should be invalidated
        assert client._system_prompt_cache is None
