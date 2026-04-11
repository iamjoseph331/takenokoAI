"""Reaction family main module — sensory input and perception."""

from __future__ import annotations

from typing import Any

from interface.bus import BusMessage, CognitionPath, FamilyPrefix, MessageBus
from interface.llm import CompletionFn, LLMConfig
from interface.logging import ModuleLogger
from interface.message_codec import parse_llm_output
from interface.modules import MainModule
from interface.permissions import PermissionManager
from interface.prompt_assembler import PromptAssembler


class ReactionModule(MainModule):
    """Perceives the environment and routes input to the appropriate cognition path.

    Input flows:
      - R path (Reflex):    Re -> Mo  (immediate reaction)
      - E path (Appraisal): Re -> Ev  (evaluate input)
      - U path (Uptake):    Re -> Pr  (feed to planning)
    """

    def __init__(
        self,
        bus: MessageBus,
        logger: ModuleLogger,
        llm_config: LLMConfig,
        permissions: PermissionManager,
        prompt_assembler: PromptAssembler | None = None,
        completion_fn: CompletionFn | None = None,
    ) -> None:
        super().__init__(
            FamilyPrefix.Re, bus, logger, llm_config, permissions,
            prompt_assembler=prompt_assembler,
            completion_fn=completion_fn,
        )

    async def perceive(self, input_data: dict[str, Any]) -> str:
        """Process raw input and route it along the appropriate cognition path.

        Uses the LLM to classify the input, then sends a message to the
        target family determined by the cognition path. Returns the message ID.
        """
        self._logger.action(
            "perceive called",
            data={"input_preview": str(input_data)[:200]},
        )

        path = await self.classify_input(input_data)

        target_map = {
            CognitionPath.R: FamilyPrefix.Mo,
            CognitionPath.E: FamilyPrefix.Ev,
            CognitionPath.U: FamilyPrefix.Pr,
        }
        receiver = target_map.get(path, FamilyPrefix.Ev)

        msg_id = await self.send_message(
            receiver=receiver,
            body=input_data,
            path=path,
            context=f"Perceived input classified as {path.value} path",
            summary=f"<Re> received input, routing to <{receiver.value}> via {path.value} path",
        )
        return msg_id

    async def classify_input(self, input_data: dict[str, Any]) -> CognitionPath:
        """Use the LLM to decide which cognition path this input should follow.

        Classification rules (R / E / U / N and tie-breakers) live in the
        assembled system prompt (re_rulebook.md).
        """
        broadcast_ctx = self._build_broadcast_context()
        parts = []
        if broadcast_ctx:
            parts.append(broadcast_ctx)
        parts.append(f"Task: classify input\nInput:\n{input_data}")
        user_content = "\n\n".join(parts)

        messages = [{"role": "user", "content": user_content}]
        raw = await self.think(messages)
        parsed = parse_llm_output(raw, FamilyPrefix.Re, self._logger)

        if parsed.path and parsed.path in (CognitionPath.R, CognitionPath.E, CognitionPath.U):
            return parsed.path

        self._logger.action(
            f"classify_input: LLM returned invalid path {parsed.path}, defaulting to E"
        )
        return CognitionPath.E

    async def _handle_message(self, message: BusMessage) -> None:
        """Handle incoming messages (D-path directives from Pr)."""
        body = message.body or {}

        # Route capability invocations to submodules
        if isinstance(body, dict) and "capability" in body:
            cap_name = body["capability"]
            target_qn = self.find_capability(cap_name)
            if target_qn:
                await self._bus.send(message.model_copy(update={}))
                self._logger.action(f"Routed capability '{cap_name}' to {target_qn}")
                return

        if isinstance(body, dict) and "text" in body:
            await self.perceive(body)
        elif isinstance(body, dict) and body.get("action") == "re-observe":
            self._logger.action("Re-observing as directed by Pr")
            await self.perceive(body.get("data", {}))
        else:
            self._logger.action(
                "Re received unrecognized message",
                data={"body_preview": str(body)[:200]},
            )
