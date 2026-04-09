"""Evaluation family main module — judges outcomes and generates affordances."""

from __future__ import annotations

from typing import Any

from interface.bus import BusMessage, CognitionPath, FamilyPrefix, MessageBus
from interface.llm import CompletionFn, LLMConfig
from interface.logging import ModuleLogger
from interface.message_codec import FORMAT_INSTRUCTIONS, parse_llm_output
from interface.modules import MainModule
from interface.permissions import PermissionManager
from interface.prompt_assembler import PromptAssembler


_EVALUATE_PROMPT = """Evaluate the given situation or plan. Your assessment must include:

1. **assessment**: What is happening? Is this good, bad, or neutral?
2. **confidence**: A score from 0.0 to 1.0 indicating how certain you are.
3. **affordances**: A list of possible actions available from this state.

If evaluating a plan from Pr:
- confidence >= 0.7: Approve and route to Mo for execution.
- confidence < 0.5: Reject with specific objections, send back to Pr.
- Between 0.5 and 0.7: Approve with caveats.

""" + FORMAT_INSTRUCTIONS

_AFFORDANCE_PROMPT = """Generate possible actions (affordances) for the given situation.

List 2-5 possible actions. For each, include:
- What the action is
- Expected outcome
- Risk level (low/medium/high)

Be creative but realistic. Include at least one safe option and one ambitious option.

""" + FORMAT_INSTRUCTIONS

AFFORDANCE_TEMPERATURE = 0.8


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
        prompt_assembler: PromptAssembler | None = None,
        completion_fn: CompletionFn | None = None,
    ) -> None:
        super().__init__(
            FamilyPrefix.Ev, bus, logger, llm_config, permissions,
            prompt_assembler=prompt_assembler,
            completion_fn=completion_fn,
        )

    async def evaluate(self, target: str, context: str) -> dict[str, Any]:
        """Assess a target (self, environment, or goal) in the given context.

        Returns a dict with keys: assessment, confidence, affordances, raw.
        """
        broadcast_ctx = self._build_broadcast_context()
        user_content = f"Target: {target}\nContext:\n{context}"
        if broadcast_ctx:
            user_content = f"{broadcast_ctx}\n\n{user_content}"

        messages = [
            {"role": "system", "content": _EVALUATE_PROMPT},
            {"role": "user", "content": user_content},
        ]
        raw = await self.think(messages)
        parsed = parse_llm_output(raw, FamilyPrefix.Ev, self._logger)

        return {
            "assessment": parsed.body,
            "confidence": self._extract_confidence(parsed.body),
            "affordances": [],
            "raw": raw,
            "path": parsed.path,
            "receiver": parsed.receiver,
            "summary": parsed.summary,
        }

    async def generate_affordances(self, situation: str) -> list[str]:
        """Brainstorm possible actions using a higher temperature for creativity."""
        broadcast_ctx = self._build_broadcast_context()
        user_content = f"Situation:\n{situation}"
        if broadcast_ctx:
            user_content = f"{broadcast_ctx}\n\n{user_content}"

        messages = [
            {"role": "system", "content": _AFFORDANCE_PROMPT},
            {"role": "user", "content": user_content},
        ]
        raw = await self.think(messages, temperature_override=AFFORDANCE_TEMPERATURE)
        parsed = parse_llm_output(raw, FamilyPrefix.Ev, self._logger)

        # The body should contain the affordances as text
        return [parsed.body] if parsed.body else []

    async def update_weights(self, outcome: dict[str, Any]) -> None:
        """Update internal evaluation weights based on an outcome.

        Stage 1: log the outcome only (no actual weight adjustment).
        """
        self._logger.action(
            "update_weights called (Stage 1: log only)",
            data={"outcome": outcome},
        )

    async def _handle_message(self, message: BusMessage) -> None:
        """Handle messages from Re (E path) and Pr (P path)."""
        body = message.body or {}
        body_str = str(body)

        # If this is a plan from Pr, validate it
        if message.sender == FamilyPrefix.Pr:
            plan_text = body.get("plan", body_str) if isinstance(body, dict) else body_str
            result = await self.evaluate("plan", f"Plan from Pr:\n{plan_text}")

            confidence = result.get("confidence", 0.5)
            parsed_path = result.get("path")
            parsed_receiver = result.get("receiver")

            if confidence >= 0.7:
                target = FamilyPrefix(parsed_receiver) if parsed_receiver else FamilyPrefix.Mo
                path = CognitionPath(parsed_path) if parsed_path else CognitionPath.P
                await self.send_message(
                    receiver=target,
                    body={"action": plan_text, "confidence": confidence, "assessment": result["assessment"]},
                    path=path,
                    context=f"Ev approved plan (confidence={confidence:.2f})",
                    parent_message_id=message.message_id,
                    trace_id=message.trace_id,
                    summary=result.get("summary", f"<Ev> approved plan, routing to <{target.value}>"),
                )
            else:
                await self.send_message(
                    receiver=FamilyPrefix.Pr,
                    body={"feedback": result["assessment"], "confidence": confidence},
                    path=CognitionPath.P,
                    context=f"Ev rejected plan (confidence={confidence:.2f}), requesting revision",
                    parent_message_id=message.message_id,
                    trace_id=message.trace_id,
                    summary=f"<Ev> rejected plan (conf={confidence:.2f}), asking <Pr> to revise",
                )
        else:
            # Input from Re (E path) — evaluate and send to Pr
            result = await self.evaluate("input", f"Perception from Re:\n{body_str}")
            await self.send_message(
                receiver=FamilyPrefix.Pr,
                body={
                    "assessment": result["assessment"],
                    "confidence": result.get("confidence", 0.5),
                    "original_input": body,
                },
                path=CognitionPath.P,
                context=f"Ev appraisal of input from {message.sender.value}",
                parent_message_id=message.message_id,
                trace_id=message.trace_id,
                summary=result.get("summary", f"<Ev> evaluated input from <{message.sender.value}>"),
            )

    @staticmethod
    def _extract_confidence(text: str) -> float:
        """Try to extract a confidence score from evaluation text."""
        import re
        patterns = [
            r'"confidence"\s*:\s*([\d.]+)',
            r'confidence[:\s]+([\d.]+)',
            r'(\d\.\d+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    val = float(match.group(1))
                    if 0.0 <= val <= 1.0:
                        return val
                except ValueError:
                    continue
        return 0.5
