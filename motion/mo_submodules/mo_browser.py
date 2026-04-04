"""Mo.browser — general browser action submodule.

Executes browser actions (click, type, navigate, etc.) via Playwright.
No game-specific logic — the agent's reasoning modules decide what to
click and where, using game rules learned and stored in Me.

Usage:
    browser_sub = BrowserActionSubmodule(parent=mo_module, session=session)
    await browser_sub.start()
    result = await browser_sub.execute_action({"action": "click", "selector": "#btn"})
"""

from __future__ import annotations

from typing import Any, Optional

from interface.browser_session import BrowserSession
from interface.bus import BusMessage, CognitionPath, FamilyPrefix
from interface.modules import MainModule, SubModule


class BrowserActionSubmodule(SubModule):
    """Browser action submodule for the Motion family.

    Executes generic browser actions. The agent's reasoning modules
    (Pr, Ev) decide what actions to take based on learned game rules.
    """

    def __init__(
        self,
        parent: MainModule,
        session: BrowserSession,
    ) -> None:
        super().__init__(
            parent=parent,
            name="browser",
            description=(
                "Browser action: executes clicks, typing, navigation, "
                "and other Playwright commands in the browser"
            ),
            llm_config=parent._llm.config,
        )
        self._session = session

    async def execute_action(self, action: dict[str, Any]) -> dict[str, Any]:
        """Execute a browser action.

        Supported action types:
          - "click": click by CSS selector or (x, y) coordinates
          - "type": type text into an element
          - "press": press a keyboard key
          - "navigate": go to a URL
          - "wait": wait for a selector or a delay
          - "js": evaluate JavaScript in page context

        Returns {"status": "ok", ...} or {"status": "error", "reason": ...}.
        """
        if not self._session.is_running:
            return {"status": "error", "reason": "Browser session not running"}

        action_type = action.get("action", "")

        if action_type == "click":
            selector = action.get("selector")
            if selector:
                await self._session.click(selector)
                return {"status": "ok", "clicked": selector}
            x, y = action.get("x"), action.get("y")
            if x is not None and y is not None:
                await self._session.click_xy(float(x), float(y))
                return {"status": "ok", "clicked": f"({x},{y})"}
            return {"status": "error", "reason": "click requires 'selector' or 'x'+'y'"}

        if action_type == "type":
            selector = action.get("selector", "")
            text = action.get("text", "")
            await self._session.type_text(selector, text)
            return {"status": "ok", "typed": text[:50]}

        if action_type == "press":
            key = action.get("key", "")
            await self._session.press_key(key)
            return {"status": "ok", "pressed": key}

        if action_type == "navigate":
            url = action.get("url", "")
            await self._session.navigate(url)
            return {"status": "ok", "navigated": url}

        if action_type == "wait":
            selector = action.get("selector")
            if selector:
                timeout = action.get("timeout", 5000)
                await self._session.wait_for_selector(selector, timeout=timeout)
                return {"status": "ok", "waited_for": selector}
            delay = action.get("delay", 0.3)
            await self._session.wait_for_stable(delay=delay)
            return {"status": "ok", "waited": delay}

        if action_type == "js":
            script = action.get("script", "")
            result = await self._session.evaluate_js(script)
            return {"status": "ok", "result": result}

        return {"status": "error", "reason": f"Unknown action type: {action_type}"}

    async def handle_message(self, message: BusMessage) -> Optional[BusMessage]:
        """Handle incoming action messages.

        Executes the action, then requests Re to observe the updated
        page state so the agent sees the result.
        """
        body = message.body or {}
        if not isinstance(body, dict):
            self._logger.action(f"Ignoring non-dict body: {str(body)[:100]}")
            return None

        action_type = body.get("action")
        if not action_type:
            self._logger.action("No action specified in message body")
            return None

        result = await self.execute_action(body)

        self._logger.action(
            f"Browser action: {action_type}",
            data={"result": result.get("status")},
        )

        # After any successful action, trigger re-observation
        if result.get("status") == "ok":
            await self._session.wait_for_stable()
            await self._parent.send_message(
                receiver=FamilyPrefix.Re,
                body={
                    "source": "browser",
                    "action": "observe",
                    "after_action": body,
                    "action_result": result,
                },
                path=CognitionPath.D,
                context="Post-action observation request",
                summary=f"<Mo.browser> action done ({action_type}), requesting Re to observe",
            )

        return None

    async def start(self) -> None:
        await super().start()
        self._logger.action("Browser action ready")

    async def stop(self) -> None:
        await super().stop()
