"""Prediction family main module — central intelligence, planning, and reasoning."""

from __future__ import annotations

from typing import Any

from interface.bus import BusMessage, FamilyPrefix, MessageBus
from interface.llm import LLMConfig
from interface.logging import ModuleLogger
from interface.modules import MainModule
from interface.permissions import PermissionAction, PermissionManager
from interface.prompt_assembler import PromptAssembler


class PredictionModule(MainModule):
    """Central intelligence module — plans, reasons, and dispatches directives.

    Pr holds default authority to write to any part of the project and
    can grant permissions to other families.

    Message flows:
      - P path: receives from Ev, reasons, sends back to Ev
      - U path: receives input from Re
      - D path: dispatches directives to any family
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
            FamilyPrefix.Pr, bus, logger, llm_config, permissions,
            prompt_assembler=prompt_assembler,
        )

    async def reason(self, context: str, evaluation: str) -> str:
        """Core reasoning — use the LLM to analyze context and evaluation.

        Args:
            context: Current situation/state description.
            evaluation: Assessment from the Evaluation module.

        Returns:
            The reasoning result / plan as a string.
        """
        raise NotImplementedError(
            "reason: LLM-based reasoning over context + evaluation"
        )

    async def dispatch(
        self, plan: str, target: FamilyPrefix
    ) -> BusMessage:
        """Send a directive to a target family via the D cognition path.

        Args:
            plan: The plan/instruction to dispatch.
            target: Which family should receive the directive.

        Returns:
            The sent BusMessage.
        """
        raise NotImplementedError(
            "dispatch: send directive via D path to target family"
        )

    def grant_permission(
        self,
        grantee: FamilyPrefix,
        action: PermissionAction,
        target: str,
    ) -> None:
        """Grant a permission to another family (Pr has universal grant authority)."""
        self._permissions.grant(grantee, action, target, granted_by=FamilyPrefix.Pr)

    async def _message_loop(self) -> None:
        """Listen for messages from Re (U path), Ev (P path) and process them."""
        raise NotImplementedError("PredictionModule._message_loop")

    async def get_resources(self) -> dict[str, Any]:
        raise NotImplementedError("PredictionModule.get_resources")

    async def get_limits(self) -> dict[str, Any]:
        raise NotImplementedError("PredictionModule.get_limits")

    async def pause_and_answer(
        self, question: str, requester: FamilyPrefix
    ) -> str:
        raise NotImplementedError("PredictionModule.pause_and_answer")
