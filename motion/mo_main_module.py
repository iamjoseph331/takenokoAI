"""Motion family main module — executes output actions."""

from __future__ import annotations

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
        """Listen for action directives from Re, Ev, and Pr."""
        raise NotImplementedError("MotionModule._message_loop")

    async def get_resources(self) -> dict[str, Any]:
        raise NotImplementedError("MotionModule.get_resources")

    async def get_limits(self) -> dict[str, Any]:
        raise NotImplementedError("MotionModule.get_limits")

    async def pause_and_answer(
        self, question: str, requester: FamilyPrefix
    ) -> str:
        raise NotImplementedError("MotionModule.pause_and_answer")
