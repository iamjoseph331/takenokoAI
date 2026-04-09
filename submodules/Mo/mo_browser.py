"""Mo.browser — general browser action submodule.

Executes browser actions (click, type, navigate, etc.) via Playwright.
No game-specific logic — the agent's reasoning modules decide what to
click and where, using game rules learned and stored in Me.

Capabilities:
  - click: Click by CSS selector or (x, y) coordinates
  - type: Type text into an element
  - press: Press a keyboard key
  - navigate: Go to a URL
  - wait: Wait for a selector or a delay
  - js: Evaluate JavaScript in page context

Usage:
    browser_sub = BrowserActionSubmodule(
        bus=bus, logger=logger, llm_config=llm_config,
        permissions=permissions, session=session,
    )
    await browser_sub.start()
    result = await browser_sub.invoke("click", {"selector": "#btn"})
"""

from __future__ import annotations

from typing import Any

from interface.browser_session import BrowserSession
from interface.bus import (
    BusMessage,
    CognitionPath,
    FamilyPrefix,
    MessageBus,
    QueueFullPolicy,
)
from interface.capabilities import Capability
from interface.llm import LLMConfig
from interface.logging import ModuleLogger
from interface.modules import SubModule
from interface.permissions import PermissionManager


class BrowserActionSubmodule(SubModule):
    """Browser action submodule for the Motion family.

    Executes generic browser actions. The agent's reasoning modules
    (Pr, Ev) decide what actions to take based on learned game rules.
    """

    def __init__(
        self,
        *,
        family_prefix: FamilyPrefix = FamilyPrefix.Mo,
        bus: MessageBus,
        logger: ModuleLogger,
        llm_config: LLMConfig,
        permissions: PermissionManager,
        session: BrowserSession,
        policy: QueueFullPolicy = QueueFullPolicy.WAIT,
        max_retries: int = 3,
    ) -> None:
        super().__init__(
            family_prefix=family_prefix,
            name="browser",
            description=(
                "Browser action: executes clicks, typing, navigation, "
                "and other Playwright commands in the browser"
            ),
            bus=bus,
            logger=logger,
            llm_config=llm_config,
            permissions=permissions,
            policy=policy,
            max_retries=max_retries,
        )
        self._session = session

    def capabilities(self) -> list[Capability]:
        return [
            Capability(
                name="click",
                description="Click by CSS selector or (x, y) coordinates",
                input_schema={"selector": "CSS selector (or x+y)", "x": "x coord", "y": "y coord"},
                output_schema={"status": "ok | error", "clicked": "what was clicked"},
            ),
            Capability(
                name="type",
                description="Type text into an element",
                input_schema={"selector": "CSS selector", "text": "text to type"},
                output_schema={"status": "ok | error", "typed": "text typed"},
            ),
            Capability(
                name="press",
                description="Press a keyboard key",
                input_schema={"key": "key name (e.g. Enter, Tab)"},
                output_schema={"status": "ok | error", "pressed": "key pressed"},
            ),
            Capability(
                name="navigate",
                description="Navigate to a URL",
                input_schema={"url": "target URL"},
                output_schema={"status": "ok | error", "navigated": "URL"},
            ),
            Capability(
                name="wait",
                description="Wait for a selector or a delay",
                input_schema={"selector": "CSS selector (optional)", "delay": "seconds (optional)", "timeout": "ms (optional)"},
                output_schema={"status": "ok | error"},
            ),
            Capability(
                name="js",
                description="Evaluate JavaScript in page context",
                input_schema={"script": "JavaScript code"},
                output_schema={"status": "ok | error", "result": "JS return value"},
            ),
        ]

    async def _invoke_click(self, params: dict[str, Any]) -> dict[str, Any]:
        if not self._session.is_running:
            return {"status": "error", "reason": "Browser session not running"}
        selector = params.get("selector")
        if selector:
            await self._session.click(selector)
            return {"status": "ok", "clicked": selector}
        x, y = params.get("x"), params.get("y")
        if x is not None and y is not None:
            await self._session.click_xy(float(x), float(y))
            return {"status": "ok", "clicked": f"({x},{y})"}
        return {"status": "error", "reason": "click requires 'selector' or 'x'+'y'"}

    async def _invoke_type(self, params: dict[str, Any]) -> dict[str, Any]:
        if not self._session.is_running:
            return {"status": "error", "reason": "Browser session not running"}
        selector = params.get("selector", "")
        text = params.get("text", "")
        await self._session.type_text(selector, text)
        return {"status": "ok", "typed": text[:50]}

    async def _invoke_press(self, params: dict[str, Any]) -> dict[str, Any]:
        if not self._session.is_running:
            return {"status": "error", "reason": "Browser session not running"}
        key = params.get("key", "")
        await self._session.press_key(key)
        return {"status": "ok", "pressed": key}

    async def _invoke_navigate(self, params: dict[str, Any]) -> dict[str, Any]:
        if not self._session.is_running:
            return {"status": "error", "reason": "Browser session not running"}
        url = params.get("url", "")
        await self._session.navigate(url)
        return {"status": "ok", "navigated": url}

    async def _invoke_wait(self, params: dict[str, Any]) -> dict[str, Any]:
        if not self._session.is_running:
            return {"status": "error", "reason": "Browser session not running"}
        selector = params.get("selector")
        if selector:
            timeout = params.get("timeout", 5000)
            await self._session.wait_for_selector(selector, timeout=timeout)
            return {"status": "ok", "waited_for": selector}
        delay = params.get("delay", 0.3)
        await self._session.wait_for_stable(delay=delay)
        return {"status": "ok", "waited": delay}

    async def _invoke_js(self, params: dict[str, Any]) -> dict[str, Any]:
        if not self._session.is_running:
            return {"status": "error", "reason": "Browser session not running"}
        script = params.get("script", "")
        result = await self._session.evaluate_js(script)
        return {"status": "ok", "result": result}

    async def handle_message(self, message: BusMessage) -> dict[str, Any] | None:
        """Handle incoming action messages.

        After a successful action, requests Re to observe the updated page.
        """
        result = await super().handle_message(message)

        # After any successful action, trigger re-observation
        if isinstance(result, dict) and result.get("status") == "ok":
            await self._session.wait_for_stable()
            body = message.body if isinstance(message.body, dict) else {}
            await self.send_message(
                receiver=FamilyPrefix.Re,
                body={
                    "source": "browser",
                    "action": "observe",
                    "after_action": body,
                    "action_result": result,
                },
                path=CognitionPath.D,
                context="Post-action observation request",
                summary=f"<Mo.browser> action done, requesting Re to observe",
            )

        return result

    async def start(self) -> None:
        await super().start()
        self._logger.action("Browser action ready")

    async def stop(self) -> None:
        await super().stop()
