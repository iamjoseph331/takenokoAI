"""Reaction family main module — sensory input and perception."""

from __future__ import annotations

from typing import Any

from interface.bus import BusMessage, CognitionPath, FamilyPrefix, MessageBus
from interface.llm import LLMConfig
from interface.logging import ModuleLogger
from interface.modules import MainModule
from interface.permissions import PermissionManager
from interface.prompt_assembler import PromptAssembler


class ReactionModule(MainModule):
    """Perceives the environment and routes input to the appropriate cognition path.

    Input flows:
      - R path (Reflex):   Re -> Mo  (immediate reaction)
      - E path (Appraisal): Re -> Ev  (evaluate input)
      - U path (Uptake):   Re -> Pr  (feed to planning)
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
            FamilyPrefix.Re, bus, logger, llm_config, permissions,
            prompt_assembler=prompt_assembler,
        )

    async def perceive(self, input_data: dict[str, Any]) -> BusMessage:
        """Process raw input and route it along the appropriate cognition path.

        Uses the LLM to classify the input, then sends a message to the
        target family determined by the cognition path.
        """
        raise NotImplementedError(
            "perceive: classify input and route to R/E/U path"
        )

    async def classify_input(self, input_data: dict[str, Any]) -> CognitionPath:
        """Use the LLM to decide which cognition path this input should follow.

        Returns one of: CognitionPath.R (reflex), E (appraisal), U (uptake).
        """
        raise NotImplementedError(
            "classify_input: LLM decides R/E/U path for input"
        )

    async def _message_loop(self) -> None:
        """Listen for incoming messages and dispatch to sub-modules or self."""
        raise NotImplementedError("ReactionModule._message_loop")

    async def get_resources(self) -> dict[str, Any]:
        raise NotImplementedError("ReactionModule.get_resources")

    async def get_limits(self) -> dict[str, Any]:
        raise NotImplementedError("ReactionModule.get_limits")

    async def pause_and_answer(
        self, question: str, requester: FamilyPrefix
    ) -> str:
        raise NotImplementedError("ReactionModule.pause_and_answer")
