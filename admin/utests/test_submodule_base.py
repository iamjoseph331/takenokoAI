"""Group: SubModule Base

Tests for the decoupled SubModule base class: constructor without MainModule,
send_message with QueueFullPolicy, bus-based registration, capability system.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest

from interface.bus import (
    BusMessage,
    CognitionPath,
    FamilyPrefix,
    MessageBus,
    QueueFullPolicy,
    QueueFullSignal,
)
from interface.capabilities import Capability
from interface.llm import LLMConfig
from interface.logging import ModuleLogger
from interface.modules import MainModule, SubModule
from interface.permissions import PermissionManager


# ── Concrete test submodule ──


class _StubSubModule(SubModule):
    """Minimal concrete SubModule for testing."""

    def capabilities(self) -> list[Capability]:
        return [
            Capability(
                name="greet",
                description="Say hello",
                input_schema={"name": "who to greet"},
                output_schema={"status": "ok", "greeting": "text"},
            ),
        ]

    async def _invoke_greet(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name", "world")
        return {"status": "ok", "greeting": f"Hello, {name}!"}


class _StubMainModule(MainModule):
    """Minimal MainModule for testing registration interception."""

    async def _handle_message(self, message: BusMessage) -> None:
        pass

    async def get_resources(self):
        return {}

    async def get_limits(self):
        return {}

    async def pause_and_answer(self, question, requester):
        return ""


def _make_sub(
    bus: MessageBus,
    permissions: PermissionManager,
    policy: QueueFullPolicy = QueueFullPolicy.DROP,
    family: FamilyPrefix = FamilyPrefix.Re,
) -> _StubSubModule:
    logger = ModuleLogger(family.value, "greet_sub")
    return _StubSubModule(
        family_prefix=family,
        name="greet_sub",
        description="Test submodule",
        bus=bus,
        logger=logger,
        llm_config=LLMConfig(),
        permissions=permissions,
        policy=policy,
    )


def _make_main(
    bus: MessageBus,
    permissions: PermissionManager,
    family: FamilyPrefix = FamilyPrefix.Re,
) -> _StubMainModule:
    logger = ModuleLogger(family.value, "main")
    return _StubMainModule(
        family_prefix=family,
        bus=bus,
        logger=logger,
        llm_config=LLMConfig(),
        permissions=permissions,
    )


# ── Constructor tests ──


class TestSubModuleConstructor:
    def test_no_parent_parameter(self, mock_bus, mock_permissions):
        """SubModule can be created without a MainModule reference."""
        sub = _make_sub(mock_bus, mock_permissions)
        assert sub.family_prefix == FamilyPrefix.Re
        assert sub.name == "greet_sub"
        assert sub.qualified_name == "Re.greet_sub"

    def test_policy_stored(self, mock_bus, mock_permissions):
        sub = _make_sub(mock_bus, mock_permissions, policy=QueueFullPolicy.RETRY)
        assert sub._policy == QueueFullPolicy.RETRY

    def test_registers_on_bus(self, mock_bus, mock_permissions):
        sub = _make_sub(mock_bus, mock_permissions)
        assert "Re.greet_sub" in mock_bus._queues


# ── Capability system tests ──


class TestCapabilities:
    def test_capabilities_declared(self, mock_bus, mock_permissions):
        sub = _make_sub(mock_bus, mock_permissions)
        caps = sub.capabilities()
        assert len(caps) == 1
        assert caps[0].name == "greet"

    @pytest.mark.asyncio
    async def test_invoke_known_capability(self, mock_bus, mock_permissions):
        sub = _make_sub(mock_bus, mock_permissions)
        result = await sub.invoke("greet", {"name": "Alice"})
        assert result == {"status": "ok", "greeting": "Hello, Alice!"}

    @pytest.mark.asyncio
    async def test_invoke_unknown_capability(self, mock_bus, mock_permissions):
        sub = _make_sub(mock_bus, mock_permissions)
        result = await sub.invoke("nonexistent", {})
        assert result["status"] == "error"
        assert "Unknown capability" in result["reason"]

    @pytest.mark.asyncio
    async def test_invoke_with_no_params(self, mock_bus, mock_permissions):
        sub = _make_sub(mock_bus, mock_permissions)
        result = await sub.invoke("greet")
        assert result == {"status": "ok", "greeting": "Hello, world!"}


class TestAnnounce:
    def test_announce_includes_capabilities(self, mock_bus, mock_permissions):
        sub = _make_sub(mock_bus, mock_permissions)
        ann = sub.announce()
        assert ann["name"] == "greet_sub"
        assert ann["family"] == "Re"
        assert len(ann["capabilities"]) == 1
        assert ann["capabilities"][0]["name"] == "greet"


# ── Message handling tests ──


class TestHandleMessage:
    @pytest.mark.asyncio
    async def test_capability_style_routing(self, mock_bus, mock_permissions):
        sub = _make_sub(mock_bus, mock_permissions)
        msg = BusMessage(
            message_id="Pr00000001D",
            timecode=MessageBus.now(),
            context="test",
            body={"capability": "greet", "params": {"name": "Bob"}},
            sender=FamilyPrefix.Pr,
            receiver=FamilyPrefix.Re,
        )
        result = await sub.handle_message(msg)
        assert result == {"status": "ok", "greeting": "Hello, Bob!"}

    @pytest.mark.asyncio
    async def test_action_style_routing(self, mock_bus, mock_permissions):
        sub = _make_sub(mock_bus, mock_permissions)
        msg = BusMessage(
            message_id="Pr00000001D",
            timecode=MessageBus.now(),
            context="test",
            body={"action": "greet", "name": "Charlie"},
            sender=FamilyPrefix.Pr,
            receiver=FamilyPrefix.Re,
        )
        result = await sub.handle_message(msg)
        assert result == {"status": "ok", "greeting": "Hello, Charlie!"}

    @pytest.mark.asyncio
    async def test_no_matching_body_returns_none(self, mock_bus, mock_permissions):
        sub = _make_sub(mock_bus, mock_permissions)
        msg = BusMessage(
            message_id="Pr00000001D",
            timecode=MessageBus.now(),
            context="test",
            body="just a string",
            sender=FamilyPrefix.Pr,
            receiver=FamilyPrefix.Re,
        )
        result = await sub.handle_message(msg)
        assert result is None


# ── send_message + QueueFullPolicy tests ──


class TestSendMessage:
    @pytest.mark.asyncio
    async def test_send_message_success(self, mock_bus, mock_permissions):
        # Register the receiver
        mock_bus.register("Mo.main")
        sub = _make_sub(mock_bus, mock_permissions)
        msg_id = await sub.send_message(
            receiver=FamilyPrefix.Mo,
            body={"test": True},
            path=CognitionPath.R,
        )
        assert msg_id.startswith("Re")
        assert msg_id.endswith("R")

    @pytest.mark.asyncio
    async def test_shared_counter_with_main(self, mock_bus, mock_permissions):
        """MainModule and SubModule share the bus counter — no ID collisions."""
        main = _make_main(mock_bus, mock_permissions)
        sub = _make_sub(mock_bus, mock_permissions)
        mock_bus.register("Mo.main")

        id1 = main.next_message_id(CognitionPath.S)
        id2 = await sub.send_message(
            receiver=FamilyPrefix.Mo,
            body={},
            path=CognitionPath.R,
        )
        # Both use the Re family counter via the bus
        # id1 should be Re00000001S, id2 should be Re00000002R
        assert id1 == "Re00000001S"
        assert id2 == "Re00000002R"


class TestQueueFullPolicyDrop:
    @pytest.mark.asyncio
    async def test_drop_returns_immediately(self, mock_bus, mock_permissions):
        # Create a queue with maxsize 1 and fill it
        mock_bus.register("Mo.main")
        mock_bus._queues["Mo.main"] = asyncio.Queue(maxsize=1)
        mock_bus._queues["Mo.main"].put_nowait(
            BusMessage(
                message_id="Mo00000001S",
                timecode=0,
                sender=FamilyPrefix.Mo,
                receiver=FamilyPrefix.Mo,
                body="filler",
            )
        )

        sub = _make_sub(mock_bus, mock_permissions, policy=QueueFullPolicy.DROP)
        result = await sub.send_message(
            receiver=FamilyPrefix.Mo,
            body={"test": True},
            path=CognitionPath.R,
        )
        assert result.startswith("DROPPED:")


class TestQueueFullPolicyRetry:
    @pytest.mark.asyncio
    async def test_retry_gives_up_after_max(self, mock_bus, mock_permissions):
        mock_bus.register("Mo.main")
        mock_bus._queues["Mo.main"] = asyncio.Queue(maxsize=1)
        mock_bus._queues["Mo.main"].put_nowait(
            BusMessage(
                message_id="Mo00000001S",
                timecode=0,
                sender=FamilyPrefix.Mo,
                receiver=FamilyPrefix.Mo,
                body="filler",
            )
        )

        sub = _make_sub(mock_bus, mock_permissions, policy=QueueFullPolicy.RETRY)
        sub._max_retries = 2
        result = await sub.send_message(
            receiver=FamilyPrefix.Mo,
            body={"test": True},
            path=CognitionPath.R,
        )
        assert result.startswith("DROPPED:")

    @pytest.mark.asyncio
    async def test_retry_succeeds_when_space_opens(self, mock_bus, mock_permissions):
        mock_bus.register("Mo.main")
        mock_bus._queues["Mo.main"] = asyncio.Queue(maxsize=1)
        mock_bus._queues["Mo.main"].put_nowait(
            BusMessage(
                message_id="Mo00000001S",
                timecode=0,
                sender=FamilyPrefix.Mo,
                receiver=FamilyPrefix.Mo,
                body="filler",
            )
        )

        sub = _make_sub(mock_bus, mock_permissions, policy=QueueFullPolicy.RETRY)
        sub._max_retries = 3

        # Drain the queue after a short delay
        async def drain():
            await asyncio.sleep(0.05)
            mock_bus._queues["Mo.main"].get_nowait()

        asyncio.get_event_loop().create_task(drain())
        result = await sub.send_message(
            receiver=FamilyPrefix.Mo,
            body={"test": True},
            path=CognitionPath.R,
        )
        assert not result.startswith("DROPPED:")


# ── Bus-based registration tests ──


class TestBusRegistration:
    @pytest.mark.asyncio
    async def test_start_sends_registration_message(self, mock_bus, mock_permissions):
        """SubModule.start() sends a _sub_register message to parent's queue."""
        # Register the parent's queue first
        mock_bus.register("Re.main")
        sub = _make_sub(mock_bus, mock_permissions)
        await sub.start()

        # Check the parent's queue for the registration message
        msg = mock_bus._queues["Re.main"].get_nowait()
        assert isinstance(msg.body, dict)
        assert msg.body["_sub_register"] is True
        assert msg.body["name"] == "greet_sub"
        assert len(msg.body["capabilities"]) == 1

    @pytest.mark.asyncio
    async def test_mainmodule_intercepts_registration(self, mock_bus, mock_permissions):
        """MainModule._message_loop intercepts _sub_register messages."""
        main = _make_main(mock_bus, mock_permissions)

        # Simulate a registration message arriving
        reg_body = {
            "_sub_register": True,
            "name": "greet_sub",
            "description": "Test submodule",
            "qualified_name": "Re.greet_sub",
            "capabilities": [{"name": "greet", "description": "Say hello"}],
        }
        main._handle_sub_registration(reg_body)

        assert "greet_sub" in main._submodule_registry
        assert main._submodule_registry["greet_sub"]["qualified_name"] == "Re.greet_sub"


# ── MainModule capability discovery tests ──


class TestMainModuleCapabilityDiscovery:
    def test_find_capability_in_registry(self, mock_bus, mock_permissions):
        main = _make_main(mock_bus, mock_permissions)
        main._submodule_registry["greet_sub"] = {
            "qualified_name": "Re.greet_sub",
            "description": "Test",
            "capabilities": [{"name": "greet", "description": "Say hello"}],
        }
        assert main.find_capability("greet") == "Re.greet_sub"
        assert main.find_capability("nonexistent") is None

    def test_list_capabilities_from_registry(self, mock_bus, mock_permissions):
        main = _make_main(mock_bus, mock_permissions)
        main._submodule_registry["greet_sub"] = {
            "qualified_name": "Re.greet_sub",
            "description": "Test",
            "capabilities": [{"name": "greet", "description": "Say hello"}],
        }
        caps = main.list_capabilities()
        assert len(caps) == 1
        assert caps[0]["name"] == "greet"
        assert caps[0]["submodule"] == "greet_sub"

    def test_list_submodules_includes_registry(self, mock_bus, mock_permissions):
        main = _make_main(mock_bus, mock_permissions)
        main._submodule_registry["greet_sub"] = {
            "qualified_name": "Re.greet_sub",
            "description": "Test",
            "capabilities": [],
        }
        subs = main.list_submodules()
        assert "greet_sub" in subs


# ── Bus shared counter tests ──


class TestBusSharedCounter:
    def test_counter_increments(self, mock_bus):
        id1 = mock_bus.next_message_id(FamilyPrefix.Re, CognitionPath.S)
        id2 = mock_bus.next_message_id(FamilyPrefix.Re, CognitionPath.S)
        assert id1 == "Re00000001S"
        assert id2 == "Re00000002S"

    def test_counter_per_family(self, mock_bus):
        id_re = mock_bus.next_message_id(FamilyPrefix.Re, CognitionPath.S)
        id_mo = mock_bus.next_message_id(FamilyPrefix.Mo, CognitionPath.S)
        assert id_re == "Re00000001S"
        assert id_mo == "Mo00000001S"
