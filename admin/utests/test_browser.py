"""Group: Browser Submodules

Tests for BrowserSession, Re.browser, Mo.browser submodules, Mo.main
dispatch, and Me.rules placeholder. All Playwright interactions are mocked.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from interface.browser_session import BrowserSession
from interface.bus import BusMessage, CognitionPath, FamilyPrefix, MessageBus
from interface.llm import LLMConfig
from interface.logging import ModuleLogger
from interface.permissions import PermissionManager
from memorization.me_main_module import MemorizationModule
from motion.mo_main_module import MotionModule
from reaction.re_main_module import ReactionModule


# ── Helpers ──


def _make_llm_response(content: str) -> MagicMock:
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def _mock_completion_fn(text: str = '{"body":"test","path":"E","receiver":"Ev","summary":"test"}') -> AsyncMock:
    return AsyncMock(return_value=_make_llm_response(text))


def _make_bus_and_module(cls, prefix_str):
    """Create a bus, logger, and module for testing."""
    logger = ModuleLogger("SYS", "test")
    bus = MessageBus(logger)
    permissions = PermissionManager(logger)
    llm_config = LLMConfig(model_name="test-model")
    mod_logger = ModuleLogger(prefix_str, "main")
    module = cls(
        bus=bus, logger=mod_logger, llm_config=llm_config,
        permissions=permissions, completion_fn=_mock_completion_fn(),
    )
    for p in ("Re", "Pr", "Ev", "Me", "Mo"):
        qname = f"{p}.main"
        if qname not in bus._queues:
            bus.register(qname)
    return bus, module


def _mock_page() -> MagicMock:
    """Create a mock Playwright Page."""
    page = AsyncMock()
    page.goto = AsyncMock()
    page.screenshot = AsyncMock(return_value=b"\x89PNG fake")
    page.evaluate = AsyncMock(return_value={
        "title": "Some Game",
        "url": "http://localhost:8080",
        "body": {"tag": "body", "children": []},
    })
    page.click = AsyncMock()
    page.fill = AsyncMock()
    page.keyboard = MagicMock()
    page.keyboard.press = AsyncMock()
    page.mouse = MagicMock()
    page.mouse.click = AsyncMock()
    page.wait_for_selector = AsyncMock()
    return page


def _mock_browser_session(page: MagicMock | None = None) -> BrowserSession:
    """Create a BrowserSession with a mocked page."""
    session = BrowserSession.__new__(BrowserSession)
    session._headless = True
    session._logger = ModuleLogger("SYS", "browser")
    session._playwright = MagicMock()
    session._browser = MagicMock()
    session._page = page or _mock_page()
    return session


# ── BrowserSession ──


class TestBrowserSession:
    def test_is_running(self):
        session = _mock_browser_session()
        assert session.is_running is True

    def test_not_running_when_no_page(self):
        session = BrowserSession.__new__(BrowserSession)
        session._page = None
        assert session.is_running is False

    def test_page_property_raises_when_not_started(self):
        session = BrowserSession.__new__(BrowserSession)
        session._page = None
        with pytest.raises(RuntimeError, match="not started"):
            _ = session.page

    @pytest.mark.asyncio
    async def test_screenshot(self):
        session = _mock_browser_session()
        data = await session.screenshot()
        assert data == b"\x89PNG fake"

    @pytest.mark.asyncio
    async def test_screenshot_base64(self):
        session = _mock_browser_session()
        b64 = await session.screenshot_base64()
        assert isinstance(b64, str)
        assert len(b64) > 0

    @pytest.mark.asyncio
    async def test_click(self):
        session = _mock_browser_session()
        await session.click("#btn")
        session._page.click.assert_awaited_once_with("#btn")

    @pytest.mark.asyncio
    async def test_click_xy(self):
        session = _mock_browser_session()
        await session.click_xy(100, 200)
        session._page.mouse.click.assert_awaited_once_with(100, 200)

    @pytest.mark.asyncio
    async def test_type_text(self):
        session = _mock_browser_session()
        await session.type_text("#input", "hello")
        session._page.fill.assert_awaited_once_with("#input", "hello")

    @pytest.mark.asyncio
    async def test_get_dom_snapshot(self):
        session = _mock_browser_session()
        result = await session.get_dom_snapshot()
        assert result["title"] == "Some Game"

    @pytest.mark.asyncio
    async def test_evaluate_js(self):
        session = _mock_browser_session()
        session._page.evaluate = AsyncMock(return_value=42)
        result = await session.evaluate_js("1+1")
        assert result == 42

    @pytest.mark.asyncio
    async def test_press_key(self):
        session = _mock_browser_session()
        await session.press_key("Enter")
        session._page.keyboard.press.assert_awaited_once_with("Enter")


# ── Re.browser submodule ──


class TestReBrowser:
    @pytest.mark.asyncio
    async def test_observe_returns_dom_state(self):
        from reaction.re_submodules.re_browser import BrowserSubmodule

        _, re_module = _make_bus_and_module(ReactionModule, "Re")
        session = _mock_browser_session()

        sub = BrowserSubmodule(parent=re_module, session=session)
        await sub.start()

        state = await sub.observe()
        assert state["source"] == "browser"
        assert state["title"] == "Some Game"
        assert state["url"] == "http://localhost:8080"
        assert "dom" in state

    @pytest.mark.asyncio
    async def test_observe_with_screenshot(self):
        from reaction.re_submodules.re_browser import BrowserSubmodule

        _, re_module = _make_bus_and_module(ReactionModule, "Re")
        session = _mock_browser_session()

        sub = BrowserSubmodule(parent=re_module, session=session)
        state = await sub.observe_with_screenshot()
        assert "screenshot_b64" in state
        assert isinstance(state["screenshot_b64"], str)

    @pytest.mark.asyncio
    async def test_observe_when_session_not_running(self):
        from reaction.re_submodules.re_browser import BrowserSubmodule

        _, re_module = _make_bus_and_module(ReactionModule, "Re")
        session = BrowserSession.__new__(BrowserSession)
        session._page = None
        session._logger = ModuleLogger("SYS", "browser")

        sub = BrowserSubmodule(parent=re_module, session=session)
        state = await sub.observe()
        assert state["error"] == "Browser session not running"

    @pytest.mark.asyncio
    async def test_submodule_registered_with_parent(self):
        from reaction.re_submodules.re_browser import BrowserSubmodule

        _, re_module = _make_bus_and_module(ReactionModule, "Re")
        session = _mock_browser_session()

        sub = BrowserSubmodule(parent=re_module, session=session)
        assert "browser" in re_module._submodules
        assert re_module._submodules["browser"] is sub

    @pytest.mark.asyncio
    async def test_announce(self):
        from reaction.re_submodules.re_browser import BrowserSubmodule

        _, re_module = _make_bus_and_module(ReactionModule, "Re")
        session = _mock_browser_session()

        sub = BrowserSubmodule(parent=re_module, session=session)
        info = sub.announce()
        assert info["name"] == "browser"
        assert info["family"] == "Re"
        assert "perception" in info["description"].lower()


# ── Mo.browser submodule ──


class TestMoBrowser:
    @pytest.mark.asyncio
    async def test_execute_click_selector(self):
        from motion.mo_submodules.mo_browser import BrowserActionSubmodule

        _, mo_module = _make_bus_and_module(MotionModule, "Mo")
        session = _mock_browser_session()

        sub = BrowserActionSubmodule(parent=mo_module, session=session)
        result = await sub.execute_action({"action": "click", "selector": "#btn"})
        assert result["status"] == "ok"
        session._page.click.assert_awaited_once_with("#btn")

    @pytest.mark.asyncio
    async def test_execute_click_xy(self):
        from motion.mo_submodules.mo_browser import BrowserActionSubmodule

        _, mo_module = _make_bus_and_module(MotionModule, "Mo")
        session = _mock_browser_session()

        sub = BrowserActionSubmodule(parent=mo_module, session=session)
        result = await sub.execute_action({"action": "click", "x": 100, "y": 200})
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_execute_type(self):
        from motion.mo_submodules.mo_browser import BrowserActionSubmodule

        _, mo_module = _make_bus_and_module(MotionModule, "Mo")
        session = _mock_browser_session()

        sub = BrowserActionSubmodule(parent=mo_module, session=session)
        result = await sub.execute_action({"action": "type", "selector": "#in", "text": "hi"})
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_execute_press(self):
        from motion.mo_submodules.mo_browser import BrowserActionSubmodule

        _, mo_module = _make_bus_and_module(MotionModule, "Mo")
        session = _mock_browser_session()

        sub = BrowserActionSubmodule(parent=mo_module, session=session)
        result = await sub.execute_action({"action": "press", "key": "Enter"})
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_execute_navigate(self):
        from motion.mo_submodules.mo_browser import BrowserActionSubmodule

        _, mo_module = _make_bus_and_module(MotionModule, "Mo")
        session = _mock_browser_session()

        sub = BrowserActionSubmodule(parent=mo_module, session=session)
        result = await sub.execute_action({"action": "navigate", "url": "http://test.com"})
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_execute_js(self):
        from motion.mo_submodules.mo_browser import BrowserActionSubmodule

        _, mo_module = _make_bus_and_module(MotionModule, "Mo")
        session = _mock_browser_session()
        session._page.evaluate = AsyncMock(return_value="hello")

        sub = BrowserActionSubmodule(parent=mo_module, session=session)
        result = await sub.execute_action({"action": "js", "script": "document.title"})
        assert result["status"] == "ok"
        assert result["result"] == "hello"

    @pytest.mark.asyncio
    async def test_execute_when_session_not_running(self):
        from motion.mo_submodules.mo_browser import BrowserActionSubmodule

        _, mo_module = _make_bus_and_module(MotionModule, "Mo")
        session = BrowserSession.__new__(BrowserSession)
        session._page = None
        session._logger = ModuleLogger("SYS", "browser")

        sub = BrowserActionSubmodule(parent=mo_module, session=session)
        result = await sub.execute_action({"action": "click", "selector": "#x"})
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_unknown_action(self):
        from motion.mo_submodules.mo_browser import BrowserActionSubmodule

        _, mo_module = _make_bus_and_module(MotionModule, "Mo")
        session = _mock_browser_session()

        sub = BrowserActionSubmodule(parent=mo_module, session=session)
        result = await sub.execute_action({"action": "fly"})
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_submodule_registered_with_parent(self):
        from motion.mo_submodules.mo_browser import BrowserActionSubmodule

        _, mo_module = _make_bus_and_module(MotionModule, "Mo")
        session = _mock_browser_session()

        sub = BrowserActionSubmodule(parent=mo_module, session=session)
        assert "browser" in mo_module._submodules


# ── Me.rules submodule ──


class TestMeRules:
    @pytest.mark.asyncio
    async def test_add_and_get_rules(self):
        from memorization.me_submodules.me_rules import RulesSubmodule

        _, me_module = _make_bus_and_module(MemorizationModule, "Me")
        sub = RulesSubmodule(parent=me_module)
        await sub.start()

        rule_id = await sub.add_rule("tictactoe", "Players take turns placing X or O")
        assert rule_id.startswith("rule-tictactoe-")

        rules = await sub.get_rules("tictactoe")
        assert len(rules) == 1
        assert rules[0]["text"] == "Players take turns placing X or O"
        assert rules[0]["source"] == "user"

    @pytest.mark.asyncio
    async def test_multiple_rules(self):
        from memorization.me_submodules.me_rules import RulesSubmodule

        _, me_module = _make_bus_and_module(MemorizationModule, "Me")
        sub = RulesSubmodule(parent=me_module)

        await sub.add_rule("chess", "Pawns move forward one square")
        await sub.add_rule("chess", "Knights move in an L shape")
        await sub.add_rule("tictactoe", "Three in a row wins")

        assert len(await sub.get_rules("chess")) == 2
        assert len(await sub.get_rules("tictactoe")) == 1
        assert len(await sub.get_rules("unknown")) == 0

    @pytest.mark.asyncio
    async def test_clear_rules(self):
        from memorization.me_submodules.me_rules import RulesSubmodule

        _, me_module = _make_bus_and_module(MemorizationModule, "Me")
        sub = RulesSubmodule(parent=me_module)

        await sub.add_rule("tictactoe", "Rule 1")
        await sub.add_rule("tictactoe", "Rule 2")
        count = await sub.clear_rules("tictactoe")
        assert count == 2
        assert len(await sub.get_rules("tictactoe")) == 0

    @pytest.mark.asyncio
    async def test_query_rules_returns_all(self):
        """Placeholder query returns all rules (no semantic filtering yet)."""
        from memorization.me_submodules.me_rules import RulesSubmodule

        _, me_module = _make_bus_and_module(MemorizationModule, "Me")
        sub = RulesSubmodule(parent=me_module)

        await sub.add_rule("go", "Black plays first")
        await sub.add_rule("go", "Surrounded stones are captured")

        results = await sub.query_rules("go", "Who goes first?")
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_submodule_registered(self):
        from memorization.me_submodules.me_rules import RulesSubmodule

        _, me_module = _make_bus_and_module(MemorizationModule, "Me")
        sub = RulesSubmodule(parent=me_module)
        assert "rules" in me_module._submodules

    @pytest.mark.asyncio
    async def test_announce(self):
        from memorization.me_submodules.me_rules import RulesSubmodule

        _, me_module = _make_bus_and_module(MemorizationModule, "Me")
        sub = RulesSubmodule(parent=me_module)
        info = sub.announce()
        assert info["name"] == "rules"
        assert info["family"] == "Me"
        assert "rule" in info["description"].lower()


# ── Mo.main dispatch to Mo.browser ──


class TestMoMainBrowserDispatch:
    @pytest.mark.asyncio
    async def test_browser_action_dispatched_to_submodule(self):
        from motion.mo_submodules.mo_browser import BrowserActionSubmodule

        bus, mo_module = _make_bus_and_module(MotionModule, "Mo")
        session = _mock_browser_session()

        sub = BrowserActionSubmodule(parent=mo_module, session=session)
        sub.handle_message = AsyncMock(return_value=None)

        msg = BusMessage(
            message_id="Pr00000001D",
            timecode=MessageBus.now(),
            context="test",
            body={"action": "click", "target": "browser", "selector": "#cell"},
            sender=FamilyPrefix.Pr,
            receiver=FamilyPrefix.Mo,
        )
        await mo_module._handle_message(msg)
        sub.handle_message.assert_awaited_once_with(msg)

    @pytest.mark.asyncio
    async def test_non_browser_action_not_dispatched(self):
        """Regular actions still go through do() when no target=browser."""
        bus, mo_module = _make_bus_and_module(MotionModule, "Mo")

        msg = BusMessage(
            message_id="Pr00000001D",
            timecode=MessageBus.now(),
            context="test",
            body={"action": "jump", "height": 3},
            sender=FamilyPrefix.Pr,
            receiver=FamilyPrefix.Mo,
        )
        await mo_module._handle_message(msg)
        output = await asyncio.wait_for(mo_module._output_queue.get(), timeout=1.0)
        assert "jump" in output
