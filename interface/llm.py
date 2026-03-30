"""LLM abstraction layer using litellm.

Provides a unified interface for OpenAI, Anthropic, Ollama, and other
LLM providers via litellm's model string routing:
  - OpenAI:    "gpt-4o"
  - Anthropic: "anthropic/claude-sonnet-4-20250514"
  - Ollama:    "ollama/qwen2.5"
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, TYPE_CHECKING

import litellm

from interface.logging import ModuleLogger

if TYPE_CHECKING:
    from interface.prompt_assembler import PromptAssembler


_DEFAULT_API_ENV_MAP = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "ollama": "OLLAMA_API_KEY",
}


def configure_api_keys(
    api_key_envs: dict[str, str],
    *,
    logger: ModuleLogger | None = None,
) -> None:
    """Map configured env vars to provider API key envs for litellm."""
    if not api_key_envs:
        return

    for provider, source_env in api_key_envs.items():
        if not source_env:
            continue
        target_env = _DEFAULT_API_ENV_MAP.get(provider.lower())
        if not target_env:
            if logger:
                logger.action(
                    f"Unknown LLM provider for API key mapping: {provider}",
                    data={"source_env": source_env},
                )
            continue

        source_value = os.getenv(source_env)
        if not source_value:
            if logger:
                logger.action(
                    f"API key not found in env: {source_env}",
                    data={"provider": provider, "target_env": target_env},
                )
            continue

        if os.getenv(target_env):
            if logger:
                logger.action(
                    f"API key already set for {provider}",
                    data={"target_env": target_env},
                )
            continue

        os.environ[target_env] = source_value
        if logger:
            logger.action(
                f"API key wired for {provider}",
                data={"source_env": source_env, "target_env": target_env},
            )


@dataclass
class LLMConfig:
    """Configuration for an LLM client instance."""

    model_name: str = "gpt-4o"
    temperature: float = 0.7
    max_tokens: int = 4096
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

    def __init__(
        self,
        config: LLMConfig,
        logger: ModuleLogger,
        prompt_assembler: PromptAssembler | None = None,
    ) -> None:
        self._config = config
        self._logger = logger
        self._prompt_assembler = prompt_assembler
        self._system_prompt_cache: str | None = None

    @property
    def config(self) -> LLMConfig:
        return self._config

    async def load_system_prompt(self) -> str:
        """Build the system prompt via the PromptAssembler. Caches result."""
        if self._system_prompt_cache is not None:
            return self._system_prompt_cache

        if self._prompt_assembler is None:
            self._system_prompt_cache = ""
            return ""

        self._system_prompt_cache = await self._prompt_assembler.assemble()
        return self._system_prompt_cache

    async def reload_system_prompt(self) -> str:
        """Force-reload the system prompt (re-reads all sources from disk)."""
        self._system_prompt_cache = None
        if self._prompt_assembler is not None:
            self._prompt_assembler.invalidate_cache()
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
