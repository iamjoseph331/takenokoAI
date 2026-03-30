"""Motion family main module — executes output actions."""

from __future__ import annotations

import asyncio
from typing import Any

from interface.bus import FamilyPrefix, MessageBus
from interface.llm import LLMConfig
from interface.logging import ModuleLogger
from interface.modules import MainModule
from interface.permissions import PermissionManager
from interface.prompt_assembler import PromptAssembler


class MotionModule(MainModule):
    """Executes actions in the external world — speaking and doing.

    Receives directives via:
      - R path (Reflex): from Re (immediate reaction)
      - P path (Deliberate): from Ev (after evaluation)
      - D path (Dispatch): from Pr (direct command)
    """

    def __init__(
        self,
        bus: MessageBus,
        logger: ModuleLogger,
        llm_config: LLMConfig,
        permissions: PermissionManager,
        prompt_assembler: PromptAssembler | None = None,
    ) -> None:
        super().__init__(
            FamilyPrefix.Mo, bus, logger, llm_config, permissions,
            prompt_assembler=prompt_assembler,
        )
        self._output_queue: asyncio.Queue[str] = asyncio.Queue()

    async def get_output(self, *, timeout: float = 30.0) -> str:
        """Wait for the next output produced by this module.

        Used by external runners (e.g. chat loop) to receive Mo's output
        after a cognition cycle completes.

        Raises asyncio.TimeoutError if no output arrives within *timeout* seconds.
        """
        return await asyncio.wait_for(self._output_queue.get(), timeout=timeout)

    async def speak(
        self, content: str, *, channel: str = "default"
    ) -> dict[str, Any]:
        """Produce speech/text output on a channel.

        Args:
            content: What to say.
            channel: Output channel identifier.

        Returns:
            Result dict with delivery status.
        """
        raise NotImplementedError(
            "speak: output content to the specified channel"
        )

    async def do(
        self, action: str, *, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Execute a physical/game action.

        Args:
            action: Action identifier (e.g. "play_card", "place_mark").
            params: Action-specific parameters.

        Returns:
            Result dict with action outcome.
        """
        raise NotImplementedError(
            "do: execute action with params, return outcome"
        )

    async def _message_loop(self) -> None:
        """Listen for action directives from Re, Ev, and Pr.

        Stage 1: idle loop — receives and acks messages (not yet implemented).
        """
        self._logger.action("_message_loop started (Stage 1: idle)")
        while self._running:
            try:
                message = await self._bus.receive(self.qualified_name, timeout=1.0)
            except (TimeoutError, asyncio.TimeoutError):
                continue
            await self.send_ack(message)

    async def get_resources(self) -> dict[str, Any]:
        raise NotImplementedError("MotionModule.get_resources")

    async def get_limits(self) -> dict[str, Any]:
        raise NotImplementedError("MotionModule.get_limits")

    async def pause_and_answer(
        self, question: str, requester: FamilyPrefix
    ) -> str:
        raise NotImplementedError("MotionModule.pause_and_answer")
