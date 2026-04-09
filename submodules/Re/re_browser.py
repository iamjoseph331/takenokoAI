"""Re.browser — general browser perception submodule.

Captures raw browser state (DOM snapshot, screenshots) and feeds it
into Re.main for classification. No game-specific logic — the agent
learns to interpret what it sees through Pr/Ev reasoning and Me rule
memory.

Capabilities:
  - observe: Capture DOM snapshot of the current page
  - screenshot: Capture DOM snapshot plus a base64 screenshot

Usage:
    browser_sub = BrowserSubmodule(
        bus=bus, logger=logger, llm_config=llm_config,
        permissions=permissions, session=session,
    )
    await browser_sub.start()
    result = await browser_sub.invoke("observe", {})
"""

from __future__ import annotations

from typing import Any

from interface.browser_session import BrowserSession
from interface.bus import (
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


class BrowserSubmodule(SubModule):
    """Browser perception submodule for the Reaction family.

    Captures raw browser state and sends it to Re.main. The agent's
    reasoning modules (Pr, Ev) interpret what the page means, using
    game rules stored in Me.
    """

    def __init__(
        self,
        *,
        family_prefix: FamilyPrefix = FamilyPrefix.Re,
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
                "Browser perception: captures page DOM snapshots and "
                "screenshots, feeding raw observations to Re.main"
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
                name="observe",
                description="Capture browser DOM snapshot",
                input_schema={},
                output_schema={
                    "status": "ok | error",
                    "source": "browser",
                    "title": "page title",
                    "url": "page URL",
                    "dom": "DOM body content",
                },
            ),
            Capability(
                name="screenshot",
                description="Capture DOM snapshot plus base64 screenshot",
                input_schema={},
                output_schema={
                    "status": "ok | error",
                    "source": "browser",
                    "title": "page title",
                    "url": "page URL",
                    "dom": "DOM body content",
                    "screenshot_b64": "base64-encoded PNG screenshot",
                },
            ),
        ]

    async def _invoke_observe(self, params: dict[str, Any]) -> dict[str, Any]:
        """Capture the current browser state."""
        if not self._session.is_running:
            return {"status": "error", "reason": "Browser session not running"}

        dom = await self._session.get_dom_snapshot()
        result = {
            "status": "ok",
            "source": "browser",
            "title": dom.get("title", ""),
            "url": dom.get("url", ""),
            "dom": dom.get("body"),
        }
        self._logger.action(
            "Browser observation captured",
            data={"title": result["title"], "url": result["url"]},
        )
        return result

    async def _invoke_screenshot(self, params: dict[str, Any]) -> dict[str, Any]:
        """Capture DOM snapshot plus a base64 screenshot."""
        result = await self._invoke_observe(params)
        if result["status"] == "ok" and self._session.is_running:
            result["screenshot_b64"] = await self._session.screenshot_base64()
        return result

    async def observe_and_send(self) -> str:
        """Observe browser state and send it to Re.main for classification."""
        result = await self._invoke_observe({})
        msg_id = await self.send_message(
            receiver=FamilyPrefix.Re,
            body=result,
            path=CognitionPath.S,
            context="Browser observation",
            summary=f"<Re.browser> observed page: {result.get('title', '?')}",
        )
        return msg_id

    async def start(self) -> None:
        await super().start()
        self._logger.action("Browser perception ready")

    async def stop(self) -> None:
        await super().stop()
