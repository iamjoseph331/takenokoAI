"""Motion family main module — executes output actions."""

from __future__ import annotations

import asyncio
from typing import Any

from interface.bus import BusMessage, FamilyPrefix, MessageBus
from interface.llm import CompletionFn, LLMConfig
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
        completion_fn: CompletionFn | None = None,
    ) -> None:
        super().__init__(
            FamilyPrefix.Mo, bus, logger, llm_config, permissions,
            prompt_assembler=prompt_assembler,
            completion_fn=completion_fn,
        )
        self._output_queue: asyncio.Queue[str] = asyncio.Queue()

    async def speak(
        self, content: str, *, channel: str = "default"
    ) -> dict[str, Any]:
        """Produce speech/text output on a channel.

        Puts the content into the output queue for the chat loop to collect.
        """
        self._logger.action(
            f"speak [{channel}]: {content[:100]}",
            data={"channel": channel, "length": len(content)},
        )
        await self._output_queue.put(content)
        return {"status": "delivered", "channel": channel, "length": len(content)}

    async def do(
        self, action: str, *, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Execute a game/physical action.

        Stage 1: log the action and put a description in the output queue.
        """
        result_text = f"[Action: {action}]"
        if params:
            result_text += f" params={params}"
        self._logger.action(
            f"do: {action}",
            data={"params": params},
        )
        await self._output_queue.put(result_text)
        return {"status": "executed", "action": action, "params": params}

    async def get_output(self, *, timeout: float = 30.0) -> str:
        """Wait for and return the next output produced by this module.

        Used by the chat loop in run_agent.py to collect responses.
        """
        return await asyncio.wait_for(self._output_queue.get(), timeout=timeout)

    async def _handle_message(self, message: BusMessage) -> None:
        """Handle action directives from Re, Ev, and Pr.

        If the action targets the browser and Mo.browser is registered,
        delegates to the browser submodule.
        """
        body = message.body or {}

        if isinstance(body, dict):
            # Delegate browser actions to Mo.browser submodule
            if (
                body.get("action") in ("move", "click", "type", "navigate", "wait")
                and body.get("target") == "browser"
                and "browser" in self._submodules
            ):
                await self._submodules["browser"].handle_message(message)
                return

            # Check for explicit action
            action = body.get("action")
            if action and action not in ("store",):
                params = {k: v for k, v in body.items() if k != "action"}
                await self.do(action, params=params)
                return

            # Check for plan text to speak
            plan = body.get("plan")
            if plan:
                await self.speak(str(plan))
                return

            # Check for plain text
            text = body.get("text")
            if text:
                await self.speak(str(text))
                return

        # Fallback: convert entire body to text and speak it
        await self.speak(str(body))
