"""Re.browser — general browser perception submodule.

Captures raw browser state (DOM snapshot, screenshots) and feeds it
into Re.main for classification. No game-specific logic — the agent
learns to interpret what it sees through Pr/Ev reasoning and Me rule
memory.

Usage:
    browser_sub = BrowserSubmodule(parent=re_module, session=session)
    await browser_sub.start()
    state = await browser_sub.observe()  # returns raw DOM/screenshot data
"""

from __future__ import annotations

from typing import Any, Optional

from interface.browser_session import BrowserSession
from interface.bus import BusMessage, CognitionPath, FamilyPrefix
from interface.modules import MainModule, SubModule


class BrowserSubmodule(SubModule):
    """Browser perception submodule for the Reaction family.

    Captures raw browser state and feeds it to Re.main. The agent's
    reasoning modules (Pr, Ev) interpret what the page means, using
    game rules stored in Me.
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
                "Browser perception: captures page DOM snapshots and "
                "screenshots, feeding raw observations to Re.main"
            ),
            llm_config=parent._llm.config,
        )
        self._session = session

    async def observe(self) -> dict[str, Any]:
        """Capture the current browser state.

        Returns a dict with DOM snapshot and page metadata.
        The agent's reasoning modules interpret the content.
        """
        if not self._session.is_running:
            return {"source": "browser", "error": "Browser session not running"}

        dom = await self._session.get_dom_snapshot()
        state: dict[str, Any] = {
            "source": "browser",
            "title": dom.get("title", ""),
            "url": dom.get("url", ""),
            "dom": dom.get("body"),
        }

        self._logger.action(
            "Browser observation captured",
            data={"title": state["title"], "url": state["url"]},
        )
        return state

    async def observe_with_screenshot(self) -> dict[str, Any]:
        """Capture DOM snapshot plus a base64 screenshot."""
        state = await self.observe()
        if "error" not in state and self._session.is_running:
            state["screenshot_b64"] = await self._session.screenshot_base64()
        return state

    async def observe_and_send(self) -> str:
        """Observe browser state and send it to Re.main for classification."""
        state = await self.observe()
        msg_id = await self._parent.send_message(
            receiver=FamilyPrefix.Re,
            body=state,
            path=CognitionPath.S,
            context="Browser observation",
            summary=f"<Re.browser> observed page: {state.get('title', '?')}",
        )
        return msg_id

    async def handle_message(self, message: BusMessage) -> Optional[BusMessage]:
        """Handle incoming messages requesting browser observation.

        Responds to:
          - {"action": "observe"} — capture DOM and send to Re.main
          - {"action": "screenshot"} — capture DOM + screenshot
        """
        body = message.body or {}
        action = body.get("action", "observe") if isinstance(body, dict) else "observe"

        if action == "screenshot":
            state = await self.observe_with_screenshot()
        else:
            state = await self.observe()

        await self._parent.send_message(
            receiver=FamilyPrefix.Re,
            body=state,
            path=CognitionPath.S,
            context=f"Browser observation ({action})",
            summary=f"<Re.browser> captured: {state.get('title', '?')}",
        )
        return None

    async def start(self) -> None:
        await super().start()
        self._logger.action("Browser perception ready")

    async def stop(self) -> None:
        await super().stop()
