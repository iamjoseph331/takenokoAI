"""Group: Capability System

Tests for the Capability dataclass, SubModule.capabilities()/invoke(),
and MainModule.find_capability()/list_capabilities().
"""

from __future__ import annotations

from typing import Any, Optional
from unittest.mock import MagicMock

import pytest

from interface.bus import BusMessage, CognitionPath, FamilyPrefix, MessageBus
from interface.capabilities import Capability
from interface.llm import LLMConfig
from interface.logging import ModuleLogger
from interface.modules import MainModule, SubModule
from interface.permissions import PermissionManager


# ── Test helpers ──


class _StubMainModule(MainModule):
    """Minimal MainModule for testing submodule registration."""

    def __init__(self, bus, logger, llm_config, permissions):
        super().__init__(FamilyPrefix.Re, bus, logger, llm_config, permissions)

    async def _message_loop(self) -> None:
        pass

    async def get_resources(self) -> dict[str, Any]:
        return {}

    async def get_limits(self) -> dict[str, Any]:
        return {}

    async def pause_and_answer(self, question: str, requester: FamilyPrefix) -> str:
        return ""


class _EchoSubmodule(SubModule):
    """Test submodule with two capabilities: echo and reverse."""

    def capabilities(self) -> list[Capability]:
        return [
            Capability(
                name="echo",
                description="Echo back the input text",
                input_schema={"text": "string to echo"},
                output_schema={"status": "ok", "text": "echoed text"},
            ),
            Capability(
                name="reverse",
                description="Reverse the input text",
                input_schema={"text": "string to reverse"},
                output_schema={"status": "ok", "text": "reversed text"},
            ),
        ]

    async def _invoke_echo(self, params: dict) -> dict:
        return {"status": "ok", "text": params.get("text", "")}

    async def _invoke_reverse(self, params: dict) -> dict:
        return {"status": "ok", "text": params.get("text", "")[::-1]}


class _FailingSubmodule(SubModule):
    """Submodule whose capability raises an exception."""

    def capabilities(self) -> list[Capability]:
        return [Capability(name="fail", description="Always fails")]

    async def _invoke_fail(self, params: dict) -> dict:
        raise ValueError("Intentional failure")


def _make_parent():
    logger = ModuleLogger("SYS", "test")
    bus = MessageBus(logger)
    permissions = PermissionManager(logger)
    llm_config = LLMConfig()
    parent = _StubMainModule(bus, logger, llm_config, permissions)
    return parent


# ── Capability dataclass ──


class TestCapability:
    def test_to_dict(self):
        cap = Capability(
            name="transcribe",
            description="Audio to text",
            input_schema={"audio": "bytes"},
            output_schema={"text": "string"},
        )
        d = cap.to_dict()
        assert d["name"] == "transcribe"
        assert d["description"] == "Audio to text"
        assert d["input_schema"]["audio"] == "bytes"

    def test_frozen(self):
        cap = Capability(name="x", description="y")
        with pytest.raises(AttributeError):
            cap.name = "z"  # type: ignore

    def test_default_schemas(self):
        cap = Capability(name="a", description="b")
        assert cap.input_schema == {}
        assert cap.output_schema == {}


# ── SubModule.capabilities() and invoke() ──


class TestSubModuleCapabilities:
    @pytest.mark.asyncio
    async def test_invoke_echo(self):
        parent = _make_parent()
        sub = _EchoSubmodule(parent, "echo_sub", "test", parent._llm.config)
        result = await sub.invoke("echo", {"text": "hello"})
        assert result == {"status": "ok", "text": "hello"}

    @pytest.mark.asyncio
    async def test_invoke_reverse(self):
        parent = _make_parent()
        sub = _EchoSubmodule(parent, "echo_sub", "test", parent._llm.config)
        result = await sub.invoke("reverse", {"text": "abc"})
        assert result == {"status": "ok", "text": "cba"}

    @pytest.mark.asyncio
    async def test_invoke_unknown_capability(self):
        parent = _make_parent()
        sub = _EchoSubmodule(parent, "echo_sub", "test", parent._llm.config)
        result = await sub.invoke("nonexistent", {})
        assert result["status"] == "error"
        assert "Unknown capability" in result["reason"]

    @pytest.mark.asyncio
    async def test_invoke_catches_exceptions(self):
        parent = _make_parent()
        sub = _FailingSubmodule(parent, "fail_sub", "test", parent._llm.config)
        result = await sub.invoke("fail", {})
        assert result["status"] == "error"
        assert "ValueError" in result["reason"]

    @pytest.mark.asyncio
    async def test_invoke_with_none_params(self):
        parent = _make_parent()
        sub = _EchoSubmodule(parent, "echo_sub", "test", parent._llm.config)
        result = await sub.invoke("echo", None)
        assert result == {"status": "ok", "text": ""}

    def test_capabilities_list(self):
        parent = _make_parent()
        sub = _EchoSubmodule(parent, "echo_sub", "test", parent._llm.config)
        caps = sub.capabilities()
        assert len(caps) == 2
        assert caps[0].name == "echo"
        assert caps[1].name == "reverse"

    def test_announce_includes_capabilities(self):
        parent = _make_parent()
        sub = _EchoSubmodule(parent, "echo_sub", "test", parent._llm.config)
        ann = sub.announce()
        assert "capabilities" in ann
        assert len(ann["capabilities"]) == 2
        assert ann["capabilities"][0]["name"] == "echo"


# ── SubModule.handle_message() capability dispatch ──


class TestSubModuleMessageDispatch:
    @pytest.mark.asyncio
    async def test_capability_message_dispatches(self):
        parent = _make_parent()
        sub = _EchoSubmodule(parent, "echo_sub", "test", parent._llm.config)

        msg = BusMessage(
            message_id="Re00000001E",
            timecode=MessageBus.now(),
            context="test",
            body={"capability": "echo", "params": {"text": "hi"}},
            sender=FamilyPrefix.Pr,
            receiver=FamilyPrefix.Re,
        )
        result = await sub.handle_message(msg)
        assert result is None  # fire-and-forget

    @pytest.mark.asyncio
    async def test_non_capability_message_returns_none(self):
        parent = _make_parent()
        sub = _EchoSubmodule(parent, "echo_sub", "test", parent._llm.config)

        msg = BusMessage(
            message_id="Re00000001E",
            timecode=MessageBus.now(),
            context="test",
            body={"some": "data"},
            sender=FamilyPrefix.Pr,
            receiver=FamilyPrefix.Re,
        )
        result = await sub.handle_message(msg)
        assert result is None


# ── MainModule.find_capability() and list_capabilities() ──


class TestMainModuleCapabilityDiscovery:
    def test_find_capability_found(self):
        parent = _make_parent()
        sub = _EchoSubmodule(parent, "echo_sub", "test", parent._llm.config)
        found = parent.find_capability("echo")
        assert found is sub

    def test_find_capability_not_found(self):
        parent = _make_parent()
        _EchoSubmodule(parent, "echo_sub", "test", parent._llm.config)
        found = parent.find_capability("nonexistent")
        assert found is None

    def test_find_capability_empty(self):
        parent = _make_parent()
        assert parent.find_capability("anything") is None

    def test_list_capabilities(self):
        parent = _make_parent()
        _EchoSubmodule(parent, "echo_sub", "test", parent._llm.config)
        caps = parent.list_capabilities()
        assert len(caps) == 2
        names = {c["name"] for c in caps}
        assert names == {"echo", "reverse"}
        assert all(c["submodule"] == "echo_sub" for c in caps)

    def test_list_capabilities_multiple_submodules(self):
        parent = _make_parent()
        _EchoSubmodule(parent, "sub1", "first", parent._llm.config)
        _FailingSubmodule(parent, "sub2", "second", parent._llm.config)
        caps = parent.list_capabilities()
        assert len(caps) == 3  # echo + reverse + fail
        submodules = {c["submodule"] for c in caps}
        assert submodules == {"sub1", "sub2"}
