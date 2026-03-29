"""Group: Modules

Tests for interface/modules.py — ModuleState, BaseModule, MainModule,
and SubModule including message generation, state management, sub-module
registration, and permission-checked operations.
"""

from __future__ import annotations

import asyncio
from typing import Optional

import pytest

from interface.bus import (
    BusMessage,
    CognitionPath,
    FamilyPrefix,
    MessageBus,
)
from interface.llm import LLMConfig
from interface.modules import MainModule, ModuleState, SubModule
from interface.permissions import PermissionManager


# ── Concrete test implementations ──


class ConcreteMainModule(MainModule):
    """Concrete MainModule for testing (implements abstract methods)."""

    async def _message_loop(self) -> None:
        while self._running:
            await asyncio.sleep(0.01)


class ConcreteSubModule(SubModule):
    """Concrete SubModule for testing."""

    async def handle_message(self, message: BusMessage) -> Optional[BusMessage]:
        return None


# ── ModuleState ──


class TestModuleState:
    def test_enum_values(self):
        assert ModuleState.IDLE == "IDLE"
        assert ModuleState.THINKING == "THINKING"

    def test_has_exactly_two_members(self):
        assert len(ModuleState) == 2


# ── MainModule ──


class TestMainModuleQualifiedName:
    def test_returns_prefix_dot_main(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        module = ConcreteMainModule(
            FamilyPrefix.Re, mock_bus, mock_logger, mock_llm_config, mock_permissions
        )
        assert module.qualified_name == "Re.main"


class TestMainModuleMessageId:
    def test_next_message_id_increments(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        module = ConcreteMainModule(
            FamilyPrefix.Pr, mock_bus, mock_logger, mock_llm_config, mock_permissions
        )
        id1 = module.next_message_id(CognitionPath.P)
        id2 = module.next_message_id(CognitionPath.D)
        assert id1 == "Pr00000001P"
        assert id2 == "Pr00000002D"

    def test_generate_trace_id_length(self):
        trace_id = MainModule._generate_trace_id()
        assert len(trace_id) == 12
        # Should be valid hex
        int(trace_id, 16)

    def test_generate_trace_id_uniqueness(self):
        ids = {MainModule._generate_trace_id() for _ in range(100)}
        assert len(ids) == 100


class TestMainModuleSendMessage:
    @pytest.mark.asyncio
    async def test_send_message_creates_bus_message(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        # Register receiver
        mock_bus.register("Ev.main")
        module = ConcreteMainModule(
            FamilyPrefix.Pr, mock_bus, mock_logger, mock_llm_config, mock_permissions
        )
        msg_id = await module.send_message(
            FamilyPrefix.Ev, "plan result", CognitionPath.D, context="test"
        )
        assert msg_id == "Pr00000001D"

        # Verify message was delivered
        received = mock_bus._queues["Ev.main"].get_nowait()
        assert received.body == "plan result"
        assert received.sender == FamilyPrefix.Pr
        assert received.receiver == FamilyPrefix.Ev
        assert received.context == "test"

    @pytest.mark.asyncio
    async def test_send_message_generates_trace_id(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        mock_bus.register("Mo.main")
        module = ConcreteMainModule(
            FamilyPrefix.Pr, mock_bus, mock_logger, mock_llm_config, mock_permissions
        )
        await module.send_message(FamilyPrefix.Mo, "go", CognitionPath.D)
        received = mock_bus._queues["Mo.main"].get_nowait()
        assert len(received.trace_id) == 12

    @pytest.mark.asyncio
    async def test_send_message_preserves_provided_trace_id(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        mock_bus.register("Mo.main")
        module = ConcreteMainModule(
            FamilyPrefix.Pr, mock_bus, mock_logger, mock_llm_config, mock_permissions
        )
        await module.send_message(
            FamilyPrefix.Mo, "go", CognitionPath.D, trace_id="custom123456"
        )
        received = mock_bus._queues["Mo.main"].get_nowait()
        assert received.trace_id == "custom123456"

    @pytest.mark.asyncio
    async def test_send_message_returns_full_on_backpressure(self, mock_logger):
        small_bus = MessageBus(mock_logger, queue_limits={"Ev": 1})
        permissions = PermissionManager(mock_logger)
        llm_config = LLMConfig()
        small_bus.register("Ev.main")

        module = ConcreteMainModule(
            FamilyPrefix.Pr, small_bus, mock_logger, llm_config, permissions
        )

        # Fill the Ev queue
        await module.send_message(FamilyPrefix.Ev, "first", CognitionPath.D)
        # Second should trigger backpressure
        result = await module.send_message(FamilyPrefix.Ev, "second", CognitionPath.D)
        assert result.startswith("FULL:")


class TestMainModuleSendAck:
    @pytest.mark.asyncio
    async def test_send_ack_lowercase_prefix(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        mock_bus.register("Ev.main")
        module = ConcreteMainModule(
            FamilyPrefix.Pr, mock_bus, mock_logger, mock_llm_config, mock_permissions
        )
        original_msg = BusMessage(
            message_id="Ev00000001P",
            timecode=1.0,
            trace_id="trace123",
            sender=FamilyPrefix.Ev,
            receiver=FamilyPrefix.Pr,
        )
        await module.send_ack(original_msg)
        ack = mock_bus._queues["Ev.main"].get_nowait()
        # Ack ID should have lowercase prefix
        assert ack.message_id == "ev00000001P"
        assert ack.is_ack is True
        assert ack.parent_message_id == "Ev00000001P"
        assert ack.trace_id == "trace123"


class TestMainModuleSubmodules:
    def test_register_and_list(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        parent = ConcreteMainModule(
            FamilyPrefix.Re, mock_bus, mock_logger, mock_llm_config, mock_permissions
        )
        ConcreteSubModule(parent, "vision", "Visual perception", mock_llm_config)
        subs = parent.list_submodules()
        assert "vision" in subs
        assert subs["vision"]["name"] == "vision"
        assert subs["vision"]["description"] == "Visual perception"

    def test_unregister_submodule(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        parent = ConcreteMainModule(
            FamilyPrefix.Re, mock_bus, mock_logger, mock_llm_config, mock_permissions
        )
        ConcreteSubModule(parent, "audio", "Audio perception", mock_llm_config)
        assert "audio" in parent.list_submodules()
        parent.unregister_submodule("audio")
        assert "audio" not in parent.list_submodules()


class TestMainModuleState:
    def test_initial_state_is_idle(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        module = ConcreteMainModule(
            FamilyPrefix.Ev, mock_bus, mock_logger, mock_llm_config, mock_permissions
        )
        assert module.state == ModuleState.IDLE

    @pytest.mark.asyncio
    async def test_set_state(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        module = ConcreteMainModule(
            FamilyPrefix.Ev, mock_bus, mock_logger, mock_llm_config, mock_permissions
        )
        await module.set_state(ModuleState.THINKING)
        assert module.state == ModuleState.THINKING

    @pytest.mark.asyncio
    async def test_set_custom_state(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        module = ConcreteMainModule(
            FamilyPrefix.Ev, mock_bus, mock_logger, mock_llm_config, mock_permissions
        )
        await module.set_state("PROCESSING")
        assert module.state == "PROCESSING"
        assert "PROCESSING" in module._custom_states


class TestMainModuleQueueInfo:
    @pytest.mark.asyncio
    async def test_get_queue_info(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        module = ConcreteMainModule(
            FamilyPrefix.Me, mock_bus, mock_logger, mock_llm_config, mock_permissions
        )
        info = await module.get_queue_info()
        assert "length" in info
        assert "max_length" in info
        assert info["length"] == 0


class TestMainModulePermissionChecks:
    @pytest.mark.asyncio
    async def test_change_prompt_with_permission(self, mock_bus, mock_logger, mock_llm_config, mock_permissions, tmp_path):
        prompt_file = tmp_path / "new_prompt.md"
        prompt_file.write_text("new prompt", encoding="utf-8")

        module = ConcreteMainModule(
            FamilyPrefix.Re, mock_bus, mock_logger, mock_llm_config, mock_permissions
        )
        # Re can change its own prompt
        await module.change_prompt(str(prompt_file), requester=FamilyPrefix.Re)
        assert module._llm.config.system_prompt_path == str(prompt_file)

    @pytest.mark.asyncio
    async def test_change_prompt_denied(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        module = ConcreteMainModule(
            FamilyPrefix.Re, mock_bus, mock_logger, mock_llm_config, mock_permissions
        )
        with pytest.raises(PermissionError):
            await module.change_prompt("/some/path.md", requester=FamilyPrefix.Mo)

    @pytest.mark.asyncio
    async def test_change_model_with_permission(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        module = ConcreteMainModule(
            FamilyPrefix.Re, mock_bus, mock_logger, mock_llm_config, mock_permissions
        )
        await module.change_model("ollama/qwen2.5", requester=FamilyPrefix.Re)
        assert module._llm.config.model_name == "ollama/qwen2.5"

    @pytest.mark.asyncio
    async def test_change_model_denied(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        module = ConcreteMainModule(
            FamilyPrefix.Re, mock_bus, mock_logger, mock_llm_config, mock_permissions
        )
        with pytest.raises(PermissionError):
            await module.change_model("gpt-4", requester=FamilyPrefix.Mo)


class TestMainModuleStartStop:
    @pytest.mark.asyncio
    async def test_start_sets_running(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        module = ConcreteMainModule(
            FamilyPrefix.Pr, mock_bus, mock_logger, mock_llm_config, mock_permissions
        )
        assert not module._running
        await module.start()
        assert module._running

    @pytest.mark.asyncio
    async def test_stop_clears_running(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        module = ConcreteMainModule(
            FamilyPrefix.Pr, mock_bus, mock_logger, mock_llm_config, mock_permissions
        )
        await module.start()
        await module.stop()
        assert not module._running


# ── SubModule ──


class TestSubModule:
    def test_announce_returns_descriptor(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        parent = ConcreteMainModule(
            FamilyPrefix.Re, mock_bus, mock_logger, mock_llm_config, mock_permissions
        )
        sub = ConcreteSubModule(parent, "vision", "Processes images", mock_llm_config)
        descriptor = sub.announce()
        assert descriptor == {
            "name": "vision",
            "family": "Re",
            "description": "Processes images",
            "qualified_name": "Re.vision",
        }

    def test_auto_registers_with_parent(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        parent = ConcreteMainModule(
            FamilyPrefix.Re, mock_bus, mock_logger, mock_llm_config, mock_permissions
        )
        sub = ConcreteSubModule(parent, "audio", "Audio input", mock_llm_config)
        assert "audio" in parent._submodules
        assert parent._submodules["audio"] is sub
