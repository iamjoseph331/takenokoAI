"""Group: Family Modules

Tests for each family main module: ReactionModule, PredictionModule,
EvaluationModule, MemorizationModule, and MotionModule — verifying
inheritance, family_prefix, implemented methods, and the message loop template.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from interface.bus import BusMessage, CognitionPath, FamilyPrefix, MessageBus
from interface.logging import ModuleLogger
from interface.modules import MainModule
from evaluation.ev_main_module import EvaluationModule
from memorization.me_main_module import MemorizationModule
from motion.mo_main_module import MotionModule
from prediction.pr_main_module import PredictionModule
from reaction.re_main_module import ReactionModule


# ── Helpers ──


def _make_llm_response(content: str) -> MagicMock:
    """Build a fake litellm response object."""
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def _mock_completion_fn(response_text: str = '{"body":"test","path":"E","receiver":"Ev","summary":"test"}') -> AsyncMock:
    """Create an AsyncMock that returns a fake LLM response."""
    return AsyncMock(return_value=_make_llm_response(response_text))


def _make_module(cls, prefix_str, mock_bus, mock_logger, mock_llm_config, mock_permissions, completion_fn=None):
    """Instantiate a family module with test fixtures.

    Also registers dummy queues for all other families so send_message
    can resolve receivers.
    """
    logger = ModuleLogger(prefix_str, "main")
    module = cls(
        bus=mock_bus,
        logger=logger,
        llm_config=mock_llm_config,
        permissions=mock_permissions,
        completion_fn=completion_fn or _mock_completion_fn(),
    )
    # Register dummy queues for other families (the module under test
    # registered itself in __init__)
    for prefix in ("Re", "Pr", "Ev", "Me", "Mo"):
        qname = f"{prefix}.main"
        if qname not in mock_bus._queues:
            mock_bus.register(qname)
    return module


def _make_bus_message(sender: FamilyPrefix = FamilyPrefix.Re, receiver: FamilyPrefix = FamilyPrefix.Ev) -> BusMessage:
    """Create a test BusMessage."""
    return BusMessage(
        message_id=MessageBus.make_message_id(sender, 1, CognitionPath.E),
        timecode=MessageBus.now(),
        context="test",
        body={"text": "hello"},
        sender=sender,
        receiver=receiver,
    )


# ── ReactionModule ──


class TestReactionModule:
    def test_inherits_main_module(self):
        assert issubclass(ReactionModule, MainModule)

    def test_family_prefix(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        module = _make_module(ReactionModule, "Re", mock_bus, mock_logger, mock_llm_config, mock_permissions)
        assert module.family_prefix == FamilyPrefix.Re

    @pytest.mark.asyncio
    async def test_classify_input_returns_path(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        fn = _mock_completion_fn('{"body":"routing","path":"E","receiver":"Ev","summary":"test"}')
        module = _make_module(ReactionModule, "Re", mock_bus, mock_logger, mock_llm_config, mock_permissions, fn)
        path = await module.classify_input({"type": "text", "content": "hello"})
        assert path in (CognitionPath.R, CognitionPath.E, CognitionPath.U)

    @pytest.mark.asyncio
    async def test_perceive_sends_message(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        fn = _mock_completion_fn('{"body":"routing","path":"U","receiver":"Pr","summary":"test"}')
        module = _make_module(ReactionModule, "Re", mock_bus, mock_logger, mock_llm_config, mock_permissions, fn)
        msg_id = await module.perceive({"text": "hello"})
        assert isinstance(msg_id, str)
        assert len(msg_id) > 0

    @pytest.mark.asyncio
    async def test_handle_message_processes_text(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        fn = _mock_completion_fn('{"body":"test","path":"E","receiver":"Ev","summary":"test"}')
        module = _make_module(ReactionModule, "Re", mock_bus, mock_logger, mock_llm_config, mock_permissions, fn)
        msg = _make_bus_message(FamilyPrefix.Pr, FamilyPrefix.Re)
        await module._handle_message(msg)
        assert fn.call_count >= 1


# ── PredictionModule ──


class TestPredictionModule:
    def test_inherits_main_module(self):
        assert issubclass(PredictionModule, MainModule)

    def test_family_prefix(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        module = _make_module(PredictionModule, "Pr", mock_bus, mock_logger, mock_llm_config, mock_permissions)
        assert module.family_prefix == FamilyPrefix.Pr

    @pytest.mark.asyncio
    async def test_reason_returns_string(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        fn = _mock_completion_fn('{"body":"plan to win","path":"P","receiver":"Ev","summary":"planning"}')
        module = _make_module(PredictionModule, "Pr", mock_bus, mock_logger, mock_llm_config, mock_permissions, fn)
        result = await module.reason("board state", "evaluation: losing")
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_dispatch_sends_d_path(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        module = _make_module(PredictionModule, "Pr", mock_bus, mock_logger, mock_llm_config, mock_permissions)
        msg_id = await module.dispatch("do something", FamilyPrefix.Mo)
        assert isinstance(msg_id, str)

    @pytest.mark.asyncio
    async def test_handle_message_reasons_and_responds(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        fn = _mock_completion_fn('{"body":"my plan","path":"P","receiver":"Ev","summary":"planning"}')
        module = _make_module(PredictionModule, "Pr", mock_bus, mock_logger, mock_llm_config, mock_permissions, fn)
        msg = _make_bus_message(FamilyPrefix.Re, FamilyPrefix.Pr)
        await module._handle_message(msg)
        assert fn.call_count >= 1


# ── EvaluationModule ──


class TestEvaluationModule:
    def test_inherits_main_module(self):
        assert issubclass(EvaluationModule, MainModule)

    def test_family_prefix(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        module = _make_module(EvaluationModule, "Ev", mock_bus, mock_logger, mock_llm_config, mock_permissions)
        assert module.family_prefix == FamilyPrefix.Ev

    @pytest.mark.asyncio
    async def test_evaluate_returns_dict(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        fn = _mock_completion_fn('{"body":"looks good, confidence: 0.8","path":"P","receiver":"Mo","summary":"approved"}')
        module = _make_module(EvaluationModule, "Ev", mock_bus, mock_logger, mock_llm_config, mock_permissions, fn)
        result = await module.evaluate("self", "game context")
        assert isinstance(result, dict)
        assert "assessment" in result
        assert "confidence" in result

    @pytest.mark.asyncio
    async def test_generate_affordances_returns_list(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        fn = _mock_completion_fn('{"body":"1. move left 2. move right","path":"S","receiver":"Ev","summary":"brainstorming"}')
        module = _make_module(EvaluationModule, "Ev", mock_bus, mock_logger, mock_llm_config, mock_permissions, fn)
        result = await module.generate_affordances("current situation")
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_update_weights_logs_without_error(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        module = _make_module(EvaluationModule, "Ev", mock_bus, mock_logger, mock_llm_config, mock_permissions)
        await module.update_weights({"result": "win", "score": 1.0})

    @pytest.mark.asyncio
    async def test_message_loop_runs_without_error(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        module = _make_module(EvaluationModule, "Ev", mock_bus, mock_logger, mock_llm_config, mock_permissions)
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


# ── MemorizationModule ──


class TestMemorizationModule:
    def test_inherits_main_module(self):
        assert issubclass(MemorizationModule, MainModule)

    def test_family_prefix(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        module = _make_module(MemorizationModule, "Me", mock_bus, mock_logger, mock_llm_config, mock_permissions)
        assert module.family_prefix == FamilyPrefix.Me

    @pytest.mark.asyncio
    async def test_store_returns_memory_id(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        module = _make_module(MemorizationModule, "Me", mock_bus, mock_logger, mock_llm_config, mock_permissions)
        memory_id = await module.store("some data", tags=["test"])
        assert memory_id.startswith("mem_")

    @pytest.mark.asyncio
    async def test_search_returns_list(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        module = _make_module(MemorizationModule, "Me", mock_bus, mock_logger, mock_llm_config, mock_permissions)
        await module.store("hello world", tags=["greeting"])
        results = await module.search("hello")
        assert isinstance(results, list)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_recall_returns_record(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        module = _make_module(MemorizationModule, "Me", mock_bus, mock_logger, mock_llm_config, mock_permissions)
        mem_id = await module.store("test data")
        record = await module.recall(mem_id)
        assert record is not None
        assert record["content"] == "test data"

    @pytest.mark.asyncio
    async def test_recall_missing_returns_none(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        module = _make_module(MemorizationModule, "Me", mock_bus, mock_logger, mock_llm_config, mock_permissions)
        record = await module.recall("nonexistent")
        assert record is None

    @pytest.mark.asyncio
    async def test_message_loop_runs_without_error(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
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
    async def test_speak_queues_output(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        module = _make_module(MotionModule, "Mo", mock_bus, mock_logger, mock_llm_config, mock_permissions)
        result = await module.speak("Hello world")
        assert result["status"] == "delivered"
        output = await module.get_output(timeout=1.0)
        assert output == "Hello world"

    @pytest.mark.asyncio
    async def test_do_queues_output(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        module = _make_module(MotionModule, "Mo", mock_bus, mock_logger, mock_llm_config, mock_permissions)
        result = await module.do("play_card", params={"card": "ace"})
        assert result["status"] == "executed"
        output = await module.get_output(timeout=1.0)
        assert "play_card" in output

    @pytest.mark.asyncio
    async def test_get_output_times_out(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        module = _make_module(MotionModule, "Mo", mock_bus, mock_logger, mock_llm_config, mock_permissions)
        with pytest.raises((TimeoutError, asyncio.TimeoutError)):
            await module.get_output(timeout=0.05)

    @pytest.mark.asyncio
    async def test_handle_message_speaks_plan(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        module = _make_module(MotionModule, "Mo", mock_bus, mock_logger, mock_llm_config, mock_permissions)
        msg = BusMessage(
            message_id=MessageBus.make_message_id(FamilyPrefix.Pr, 1, CognitionPath.D),
            timecode=MessageBus.now(),
            context="test",
            body={"plan": "Say hello to the user"},
            sender=FamilyPrefix.Pr,
            receiver=FamilyPrefix.Mo,
        )
        await module._handle_message(msg)
        output = await module.get_output(timeout=1.0)
        assert "hello" in output.lower()


# ── MessageCodec ──


class TestMessageCodec:
    def test_parse_valid_json(self):
        from interface.message_codec import parse_llm_output
        raw = '{"body": "hello", "path": "E", "receiver": "Ev", "summary": "test"}'
        result = parse_llm_output(raw, FamilyPrefix.Re, ModuleLogger("TEST", "codec"))
        assert result.body == "hello"
        assert result.path == CognitionPath.E
        assert result.receiver == FamilyPrefix.Ev
        assert result.summary == "test"
        assert result.parse_error is None

    def test_parse_invalid_json_falls_back(self):
        from interface.message_codec import parse_llm_output
        raw = "Just some plain text response"
        result = parse_llm_output(raw, FamilyPrefix.Re, ModuleLogger("TEST", "codec"))
        assert result.body == raw
        assert result.path is None
        assert result.receiver is None
        assert result.parse_error is not None

    def test_parse_json_in_markdown_block(self):
        from interface.message_codec import parse_llm_output
        raw = '```json\n{"body": "hi", "path": "U", "receiver": "Pr", "summary": "s"}\n```'
        result = parse_llm_output(raw, FamilyPrefix.Re, ModuleLogger("TEST", "codec"))
        assert result.body == "hi"
        assert result.path == CognitionPath.U

    def test_parse_invalid_path_returns_none(self):
        from interface.message_codec import parse_llm_output
        raw = '{"body": "hi", "path": "X", "receiver": "Pr", "summary": "s"}'
        result = parse_llm_output(raw, FamilyPrefix.Re, ModuleLogger("TEST", "codec"))
        assert result.body == "hi"
        assert result.path is None


# ── Broadcast buffer ──


class TestBroadcastBuffer:
    def test_broadcast_buffer_stores_and_retrieves(self, mock_bus):
        from interface.bus import Broadcast
        for i in range(5):
            mock_bus.add_broadcast(Broadcast(
                summary=f"msg {i}", sender=FamilyPrefix.Re, timecode=float(i)
            ))
        recent = mock_bus.get_recent_broadcasts(3)
        assert len(recent) == 3
        assert recent[-1].summary == "msg 4"

    def test_broadcast_buffer_respects_maxsize(self, mock_logger):
        bus = MessageBus(mock_logger, broadcast_buffer_size=3)
        from interface.bus import Broadcast
        for i in range(10):
            bus.add_broadcast(Broadcast(
                summary=f"msg {i}", sender=FamilyPrefix.Pr, timecode=float(i)
            ))
        all_broadcasts = bus.get_recent_broadcasts(10)
        assert len(all_broadcasts) == 3


# ── S-path ──


class TestSPath:
    def test_s_path_in_enum(self):
        assert CognitionPath.S == "S"

    def test_s_path_valid_routes(self):
        for prefix in FamilyPrefix:
            assert MessageBus.validate_route(prefix, prefix, CognitionPath.S)

    def test_s_path_message_id_format(self):
        msg_id = MessageBus.make_message_id(FamilyPrefix.Pr, 1, CognitionPath.S)
        assert msg_id == "Pr00000001S"


# ── Idle detection ──


class TestIdleDetection:
    def test_idle_fields_initialized(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        module = _make_module(EvaluationModule, "Ev", mock_bus, mock_logger, mock_llm_config, mock_permissions)
        assert module._idle_streak == 0
        assert module._self_message_count == 0
        assert module._sleep_until == 0.0
        assert module._idle_nudge_threshold == 5.0
        assert module._max_idle_streak == 5
        assert module._self_message_budget == 3

    @pytest.mark.asyncio
    async def test_idle_tick_skips_below_threshold(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        import time
        module = _make_module(EvaluationModule, "Ev", mock_bus, mock_logger, mock_llm_config, mock_permissions)
        module._last_activity_time = time.monotonic()  # just now
        await module._handle_idle_tick()
        assert module._idle_streak == 0  # no nudge fired

    @pytest.mark.asyncio
    async def test_idle_tick_increments_streak(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        import time
        module = _make_module(EvaluationModule, "Ev", mock_bus, mock_logger, mock_llm_config, mock_permissions)
        module._last_activity_time = time.monotonic() - 10.0  # idle for 10s
        module._budget_window_start = time.monotonic()
        await module._handle_idle_tick()
        assert module._idle_streak == 1
        assert module._self_message_count == 1

    @pytest.mark.asyncio
    async def test_idle_tick_forced_sleep_after_max_streak(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        import time
        module = _make_module(EvaluationModule, "Ev", mock_bus, mock_logger, mock_llm_config, mock_permissions)
        module._last_activity_time = time.monotonic() - 10.0
        module._budget_window_start = time.monotonic()
        module._idle_streak = 5  # at max
        await module._handle_idle_tick()
        assert module._idle_streak == 0  # reset
        assert module._sleep_until > time.monotonic()  # sleeping

    @pytest.mark.asyncio
    async def test_idle_tick_skips_when_sleeping(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        import time
        module = _make_module(EvaluationModule, "Ev", mock_bus, mock_logger, mock_llm_config, mock_permissions)
        module._last_activity_time = time.monotonic() - 10.0
        module._sleep_until = time.monotonic() + 100.0  # sleeping
        await module._handle_idle_tick()
        assert module._idle_streak == 0  # no nudge while sleeping

    @pytest.mark.asyncio
    async def test_idle_tick_respects_budget(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        import time
        module = _make_module(EvaluationModule, "Ev", mock_bus, mock_logger, mock_llm_config, mock_permissions)
        module._last_activity_time = time.monotonic() - 10.0
        module._budget_window_start = time.monotonic()
        module._self_message_count = 3  # budget exhausted
        await module._handle_idle_tick()
        assert module._idle_streak == 0  # no nudge


# ── Fallback routes ──


class TestFallbackRoutes:
    def test_u_path_to_pr_falls_back_to_d_mo(self):
        from interface.message_codec import infer_fallback_route
        msg = BusMessage(
            message_id="Re00000001U",
            timecode=1.0,
            sender=FamilyPrefix.Re,
            receiver=FamilyPrefix.Pr,
        )
        path, receiver = infer_fallback_route(msg, FamilyPrefix.Pr)
        assert path == CognitionPath.D
        assert receiver == FamilyPrefix.Mo

    def test_p_path_to_pr_falls_back_to_p_ev(self):
        from interface.message_codec import infer_fallback_route
        msg = BusMessage(
            message_id="Ev00000001P",
            timecode=1.0,
            sender=FamilyPrefix.Ev,
            receiver=FamilyPrefix.Pr,
        )
        path, receiver = infer_fallback_route(msg, FamilyPrefix.Pr)
        assert path == CognitionPath.P
        assert receiver == FamilyPrefix.Ev

    def test_p_path_to_ev_falls_back_to_p_pr(self):
        from interface.message_codec import infer_fallback_route
        msg = BusMessage(
            message_id="Pr00000001P",
            timecode=1.0,
            sender=FamilyPrefix.Pr,
            receiver=FamilyPrefix.Ev,
        )
        path, receiver = infer_fallback_route(msg, FamilyPrefix.Ev)
        assert path == CognitionPath.P
        assert receiver == FamilyPrefix.Pr

    def test_unknown_route_falls_back_to_s_self(self):
        from interface.message_codec import infer_fallback_route
        msg = BusMessage(
            message_id="Me00000001D",
            timecode=1.0,
            sender=FamilyPrefix.Pr,
            receiver=FamilyPrefix.Me,
        )
        path, receiver = infer_fallback_route(msg, FamilyPrefix.Me)
        assert path == CognitionPath.S
        assert receiver == FamilyPrefix.Me


# ── Family state query ──


class TestFamilyStates:
    def test_get_family_states_without_callback(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        module = _make_module(EvaluationModule, "Ev", mock_bus, mock_logger, mock_llm_config, mock_permissions)
        states = module._get_family_states()
        assert states == {"Ev": "IDLE"}

    def test_get_family_states_with_callback(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        module = _make_module(EvaluationModule, "Ev", mock_bus, mock_logger, mock_llm_config, mock_permissions)
        module._family_state_fn = lambda: {"Re": "IDLE", "Pr": "THINKING", "Ev": "IDLE", "Me": "IDLE", "Mo": "IDLE"}
        states = module._get_family_states()
        assert len(states) == 5
        assert states["Pr"] == "THINKING"

    def test_broadcast_context_includes_states(self, mock_bus, mock_logger, mock_llm_config, mock_permissions):
        module = _make_module(EvaluationModule, "Ev", mock_bus, mock_logger, mock_llm_config, mock_permissions)
        module._family_state_fn = lambda: {"Re": "IDLE", "Pr": "IDLE"}
        ctx = module._build_broadcast_context()
        assert "Family states:" in ctx
        assert "Re=IDLE" in ctx
