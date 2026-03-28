"""LLM abstraction layer using litellm.

Provides a unified interface for OpenAI, Anthropic, Ollama, and other
LLM providers via litellm's model string routing:
  - OpenAI:    "gpt-4o"
  - Anthropic: "anthropic/claude-sonnet-4-20250514"
  - Ollama:    "ollama/qwen2.5"
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator

import litellm

from interface.logging import ModuleLogger


@dataclass
class LLMConfig:
    """Configuration for an LLM client instance."""

    model_name: str = "gpt-4o"
    temperature: float = 0.7
    max_tokens: int = 4096
    system_prompt_path: str | None = None
    extra_params: dict[str, Any] = field(default_factory=dict)


class LLMClient:
    """Async LLM client wrapping litellm for provider-agnostic completions.

    Each module gets its own LLMClient with independently configurable
    model, temperature, and system prompt.
    """

    # SUGGESTION (Test seams):
    # Accept an optional `completion_fn` parameter in __init__ that defaults to
    # litellm.acompletion. In tests, inject a mock:
    #   mock_fn = AsyncMock(return_value=fake_response)
    #   client = LLMClient(config, logger, completion_fn=mock_fn)
    # This avoids burning API tokens during development and testing.

    def __init__(self, config: LLMConfig, logger: ModuleLogger) -> None:
        self._config = config
        self._logger = logger
        self._system_prompt_cache: str | None = None

    @property
    def config(self) -> LLMConfig:
        return self._config

    async def load_system_prompt(self) -> str:
        """Read the system prompt from the configured .md file path. Caches result."""
        if self._system_prompt_cache is not None:
            return self._system_prompt_cache

        if self._config.system_prompt_path is None:
            self._system_prompt_cache = ""
            return ""

        path = Path(self._config.system_prompt_path)
        if not path.exists():
            self._logger.action(
                f"System prompt file not found: {path}, using empty prompt"
            )
            self._system_prompt_cache = ""
            return ""

        self._system_prompt_cache = path.read_text(encoding="utf-8")
        self._logger.action(f"Loaded system prompt from {path}")
        return self._system_prompt_cache

    async def reload_system_prompt(self) -> str:
        """Force-reload the system prompt from disk."""
        self._system_prompt_cache = None
        return await self.load_system_prompt()

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        system_prompt_override: str | None = None,
    ) -> str:
        """Send messages to the LLM and return the completion text.

        Args:
            messages: List of {"role": ..., "content": ...} dicts.
            system_prompt_override: If set, replaces the configured system prompt.

        Returns:
            The assistant's response text.
        """
        system_prompt = system_prompt_override or await self.load_system_prompt()

        full_messages: list[dict[str, str]] = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        self._logger.thought(
            f"LLM request: model={self._config.model_name}, "
            f"messages={len(full_messages)}"
        )

        response = await litellm.acompletion(
            model=self._config.model_name,
            messages=full_messages,
            temperature=self._config.temperature,
            max_tokens=self._config.max_tokens,
            **self._config.extra_params,
        )

        content = response.choices[0].message.content or ""
        self._logger.thought(f"LLM response: {len(content)} chars")
        return content

    async def complete_stream(
        self,
        messages: list[dict[str, str]],
        *,
        system_prompt_override: str | None = None,
    ) -> AsyncIterator[str]:
        """Stream completion tokens from the LLM.

        Yields individual text chunks as they arrive.
        """
        system_prompt = system_prompt_override or await self.load_system_prompt()

        full_messages: list[dict[str, str]] = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        self._logger.thought(
            f"LLM stream request: model={self._config.model_name}, "
            f"messages={len(full_messages)}"
        )

        response = await litellm.acompletion(
            model=self._config.model_name,
            messages=full_messages,
            temperature=self._config.temperature,
            max_tokens=self._config.max_tokens,
            stream=True,
            **self._config.extra_params,
        )

        async for chunk in response:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    def update_config(self, **kwargs: Any) -> None:
        """Hot-swap configuration values (model, temperature, etc.)."""
        for key, value in kwargs.items():
            if hasattr(self._config, key):
                setattr(self._config, key, value)
                self._logger.action(f"LLM config updated: {key}={value}")
            else:
                raise ValueError(f"Unknown LLM config key: {key!r}")
        # Invalidate prompt cache if path changed
        if "system_prompt_path" in kwargs:
            self._system_prompt_cache = None
