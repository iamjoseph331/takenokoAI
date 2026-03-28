"""Evaluation family main module — judges outcomes and generates affordances."""

from __future__ import annotations

from typing import Any

from interface.bus import FamilyPrefix, MessageBus
from interface.llm import LLMConfig
from interface.logging import ModuleLogger
from interface.modules import MainModule
from interface.permissions import PermissionManager


class EvaluationModule(MainModule):
    """Judges outcomes, assesses situations, and generates possible actions.

    Message flows:
      - E path: receives input appraisals from Re
      - P path: exchanges with Pr (evaluate -> plan -> evaluate -> act)
    """

    def __init__(
        self,
        bus: MessageBus,
        logger: ModuleLogger,
        llm_config: LLMConfig,
        permissions: PermissionManager,
    ) -> None:
        super().__init__(FamilyPrefix.Ev, bus, logger, llm_config, permissions)

    async def evaluate(self, target: str, context: str) -> dict[str, Any]:
        """Assess a target (self, environment, or goal) in the given context.

        Returns a dict with keys: assessment, confidence, affordances.
        """
        raise NotImplementedError(
            "evaluate: LLM-based assessment returning "
            "{assessment, confidence, affordances}"
        )

    async def generate_affordances(self, situation: str) -> list[str]:
        """Brainstorm possible actions given the current situation.

        Returns a list of action descriptions the agent could take.
        """
        raise NotImplementedError(
            "generate_affordances: LLM brainstorms possible actions"
        )

    # TODO: Design feedback structure for update_weights() — define outcome
    # schema, feedback flow from Mo back to Ev, and weight storage format
    # before Stage 2.

    async def update_weights(self, outcome: dict[str, Any]) -> None:
        """Update internal evaluation weights based on an outcome.

        Stage 1: log the outcome only (no actual weight adjustment).
        """
        self._logger.action(
            "update_weights called (Stage 1: log only)",
            data={"outcome": outcome},
        )

    async def _message_loop(self) -> None:
        """Listen for messages from Re (E path) and Pr (P path)."""
        raise NotImplementedError("EvaluationModule._message_loop")

    async def get_resources(self) -> dict[str, Any]:
        raise NotImplementedError("EvaluationModule.get_resources")

    async def get_limits(self) -> dict[str, Any]:
        raise NotImplementedError("EvaluationModule.get_limits")

    async def pause_and_answer(
        self, question: str, requester: FamilyPrefix
    ) -> str:
        raise NotImplementedError("EvaluationModule.pause_and_answer")
