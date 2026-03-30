"""Group: Family Modules

Tests for each family main module: ReactionModule, PredictionModule,
EvaluationModule, MemorizationModule, and MotionModule — verifying
inheritance, family_prefix, abstract stubs, and concrete methods.
"""

from __future__ import annotations

import asyncio

import pytest

from interface.bus import FamilyPrefix
from interface.logging import ModuleLogger
from interface.modules import MainModule
from evaluation.ev_main_module import EvaluationModule
from memorization.me_main_module import MemorizationModule
from motion.mo_main_module import MotionModule
from prediction.pr_main_module import PredictionModule
from reaction.re_main_module import ReactionModule


# ── Helpers ──


def _make_module(cls, prefix_str, mock_bus, mock_logger, mock_llm_config, mock_permissions):
    """Instantiate a family module with test fixtures."""
    logger = ModuleLogger(prefix_str, "main")
    return cls(
        bus=mock_bus,
        logger=logger,
        llm_config=mock_llm_config,
        permissions=mock_permissions,
    )


# ── ReactionModule ──


class TestReactionModule:
    def test_inherits_main_module(self):
        assert issubclass(ReactionModule, MainModule)

    def test_family_prefix(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        module = _make_module(ReactionModule, "Re", mock_bus, mock_logger, mock_llm_config, mock_permissions)
        assert module.family_prefix == FamilyPrefix.Re

    @pytest.mark.asyncio
    async def test_perceive_raises_not_implemented(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        module = _make_module(ReactionModule, "Re", mock_bus, mock_logger, mock_llm_config, mock_permissions)
        with pytest.raises(NotImplementedError):
            await module.perceive({"type": "text", "content": "hello"})

    @pytest.mark.asyncio
    async def test_classify_input_raises_not_implemented(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        module = _make_module(ReactionModule, "Re", mock_bus, mock_logger, mock_llm_config, mock_permissions)
        with pytest.raises(NotImplementedError):
            await module.classify_input({"type": "text"})

    @pytest.mark.asyncio
    async def test_message_loop_raises_not_implemented(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        module = _make_module(ReactionModule, "Re", mock_bus, mock_logger, mock_llm_config, mock_permissions)
        with pytest.raises(NotImplementedError):
            await module._message_loop()


# ── PredictionModule ──


class TestPredictionModule:
    def test_inherits_main_module(self):
        assert issubclass(PredictionModule, MainModule)

    def test_family_prefix(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        module = _make_module(PredictionModule, "Pr", mock_bus, mock_logger, mock_llm_config, mock_permissions)
        assert module.family_prefix == FamilyPrefix.Pr

    @pytest.mark.asyncio
    async def test_reason_raises_not_implemented(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        module = _make_module(PredictionModule, "Pr", mock_bus, mock_logger, mock_llm_config, mock_permissions)
        with pytest.raises(NotImplementedError):
            await module.reason("context", "evaluation")

    @pytest.mark.asyncio
    async def test_dispatch_raises_not_implemented(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        module = _make_module(PredictionModule, "Pr", mock_bus, mock_logger, mock_llm_config, mock_permissions)
        with pytest.raises(NotImplementedError):
            await module.dispatch("plan", FamilyPrefix.Mo)

    @pytest.mark.asyncio
    async def test_message_loop_raises_not_implemented(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        module = _make_module(PredictionModule, "Pr", mock_bus, mock_logger, mock_llm_config, mock_permissions)
        with pytest.raises(NotImplementedError):
            await module._message_loop()


# ── EvaluationModule ──


class TestEvaluationModule:
    def test_inherits_main_module(self):
        assert issubclass(EvaluationModule, MainModule)

    def test_family_prefix(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        module = _make_module(EvaluationModule, "Ev", mock_bus, mock_logger, mock_llm_config, mock_permissions)
        assert module.family_prefix == FamilyPrefix.Ev

    @pytest.mark.asyncio
    async def test_evaluate_raises_not_implemented(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        module = _make_module(EvaluationModule, "Ev", mock_bus, mock_logger, mock_llm_config, mock_permissions)
        with pytest.raises(NotImplementedError):
            await module.evaluate("self", "game context")

    @pytest.mark.asyncio
    async def test_generate_affordances_raises_not_implemented(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        module = _make_module(EvaluationModule, "Ev", mock_bus, mock_logger, mock_llm_config, mock_permissions)
        with pytest.raises(NotImplementedError):
            await module.generate_affordances("current situation")

    @pytest.mark.asyncio
    async def test_update_weights_logs_without_error(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        module = _make_module(EvaluationModule, "Ev", mock_bus, mock_logger, mock_llm_config, mock_permissions)
        # Should not raise — it's the one non-stub method
        await module.update_weights({"result": "win", "score": 1.0})

    @pytest.mark.asyncio
    async def test_message_loop_idles_without_error(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        module = _make_module(EvaluationModule, "Ev", mock_bus, mock_logger, mock_llm_config, mock_permissions)
        module._running = True
        # Should not raise — runs idle loop that times out on empty queue
        task = asyncio.create_task(module._message_loop())
        await asyncio.sleep(0.05)
        module._running = False
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


# ── MemorizationModule ──


class TestMemorizationModule:
    def test_inherits_main_module(self):
        assert issubclass(MemorizationModule, MainModule)

    def test_family_prefix(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        module = _make_module(MemorizationModule, "Me", mock_bus, mock_logger, mock_llm_config, mock_permissions)
        assert module.family_prefix == FamilyPrefix.Me

    @pytest.mark.asyncio
    async def test_store_raises_not_implemented(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        module = _make_module(MemorizationModule, "Me", mock_bus, mock_logger, mock_llm_config, mock_permissions)
        with pytest.raises(NotImplementedError):
            await module.store("some data", tags=["test"])

    @pytest.mark.asyncio
    async def test_search_raises_not_implemented(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        module = _make_module(MemorizationModule, "Me", mock_bus, mock_logger, mock_llm_config, mock_permissions)
        with pytest.raises(NotImplementedError):
            await module.search("query")

    @pytest.mark.asyncio
    async def test_recall_raises_not_implemented(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        module = _make_module(MemorizationModule, "Me", mock_bus, mock_logger, mock_llm_config, mock_permissions)
        with pytest.raises(NotImplementedError):
            await module.recall("mem_001")

    @pytest.mark.asyncio
    async def test_message_loop_idles_without_error(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        module = _make_module(MemorizationModule, "Me", mock_bus, mock_logger, mock_llm_config, mock_permissions)
        module._running = True
        task = asyncio.create_task(module._message_loop())
        await asyncio.sleep(0.05)
        module._running = False
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


# ── MotionModule ──


class TestMotionModule:
    def test_inherits_main_module(self):
        assert issubclass(MotionModule, MainModule)

    def test_family_prefix(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        module = _make_module(MotionModule, "Mo", mock_bus, mock_logger, mock_llm_config, mock_permissions)
        assert module.family_prefix == FamilyPrefix.Mo

    @pytest.mark.asyncio
    async def test_speak_raises_not_implemented(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        module = _make_module(MotionModule, "Mo", mock_bus, mock_logger, mock_llm_config, mock_permissions)
        with pytest.raises(NotImplementedError):
            await module.speak("Hello world")

    @pytest.mark.asyncio
    async def test_do_raises_not_implemented(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        module = _make_module(MotionModule, "Mo", mock_bus, mock_logger, mock_llm_config, mock_permissions)
        with pytest.raises(NotImplementedError):
            await module.do("play_card", params={"card": "ace"})

    @pytest.mark.asyncio
    async def test_message_loop_raises_not_implemented(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        module = _make_module(MotionModule, "Mo", mock_bus, mock_logger, mock_llm_config, mock_permissions)
        with pytest.raises(NotImplementedError):
            await module._message_loop()
