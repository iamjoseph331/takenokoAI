"""Prediction family main module — central intelligence, planning, and reasoning."""

from __future__ import annotations


from interface.bus import BusMessage, CognitionPath, FamilyPrefix, MessageBus
from interface.llm import CompletionFn, LLMConfig
from interface.logging import ModuleLogger
from interface.message_codec import infer_fallback_route, parse_llm_outputs
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
        completion_fn: CompletionFn | None = None,
    ) -> None:
        super().__init__(
            FamilyPrefix.Pr, bus, logger, llm_config, permissions,
            prompt_assembler=prompt_assembler,
            completion_fn=completion_fn,
        )

    async def reason(self, context: str, evaluation: str) -> str:
        """Core reasoning — use the LLM to analyze context and evaluation.

        Task framing, routing rules, and output format come from the
        assembled system prompt (identity + rulebook + character + lessons
        + output-format). This method only supplies the per-call data.

        Returns the raw reasoning result as a string.
        """
        broadcast_ctx = self._build_broadcast_context()
        parts = []
        if broadcast_ctx:
            parts.append(broadcast_ctx)
        parts.append(f"Context:\n{context}")
        if evaluation:
            parts.append(f"Evaluation:\n{evaluation}")
        user_content = "\n\n".join(parts)

        messages = [{"role": "user", "content": user_content}]
        return await self.think(messages)

    async def dispatch(
        self, plan: str, target: FamilyPrefix, *, trace_id: str = "",
        parent_message_id: str | None = None,
    ) -> str:
        """Send a directive to a target family via the D cognition path.

        Returns the sent message ID.
        """
        return await self.send_message(
            receiver=target,
            body={"plan": plan},
            path=CognitionPath.D,
            context=f"Pr dispatching plan to {target.value}",
            trace_id=trace_id,
            parent_message_id=parent_message_id,
            summary=f"<Pr> dispatching to <{target.value}>: {plan[:60]}",
        )

    def grant_permission(
        self,
        grantee: FamilyPrefix,
        action: PermissionAction,
        target: str,
    ) -> None:
        """Grant a permission to another family (Pr has universal grant authority)."""
        self._permissions.grant(grantee, action, target, granted_by=FamilyPrefix.Pr)

    async def _handle_message(self, message: BusMessage) -> None:
        """Handle messages from Re (U path) and Ev (P path)."""
        body = message.body or {}
        context_str = message.context or ""
        body_str = str(body)

        raw = await self.reason(
            context=f"From {message.sender.value} via {context_str}:\n{body_str}",
            evaluation=body_str if message.sender == FamilyPrefix.Ev else "",
        )
        outputs = parse_llm_outputs(raw, FamilyPrefix.Pr, self._logger)

        for parsed in outputs:
            if parsed.path and parsed.receiver:
                await self.send_message(
                    receiver=parsed.receiver,
                    body={"plan": parsed.body},
                    path=parsed.path,
                    context=f"Pr response to {message.message_id}",
                    parent_message_id=message.message_id,
                    trace_id=message.trace_id,
                    summary=parsed.summary or f"<Pr> responding to <{message.sender.value}>",
                )
            elif parsed.body:
                fallback_path, fallback_receiver = infer_fallback_route(
                    message, FamilyPrefix.Pr
                )
                await self.send_message(
                    receiver=fallback_receiver,
                    body={"plan": parsed.body},
                    path=fallback_path,
                    context=f"Pr response (fallback route from {message.message_id})",
                    parent_message_id=message.message_id,
                    trace_id=message.trace_id,
                    summary=parsed.summary or f"<Pr> sending plan to <{fallback_receiver.value}>",
                )
