"""Group: MessageBus

Tests for interface/bus.py — FamilyPrefix, CognitionPath, MESSAGE_ID_PATTERN,
BusMessage, QueueFullSignal, MessageBus methods, and VALID_PATH_ROUTES.
"""

from __future__ import annotations

import asyncio

import pytest

from interface.bus import (
    VALID_PATH_ROUTES,
    BusMessage,
    CognitionPath,
    FamilyPrefix,
    MESSAGE_ID_PATTERN,
    MessageBus,
    QueueFullSignal,
)
from interface.logging import ModuleLogger


# ── Enums ──


class TestFamilyPrefix:
    def test_values(self):
        assert set(FamilyPrefix) == {
            FamilyPrefix.Re,
            FamilyPrefix.Pr,
            FamilyPrefix.Ev,
            FamilyPrefix.Me,
            FamilyPrefix.Mo,
        }

    def test_string_values(self):
        assert FamilyPrefix.Re.value == "Re"
        assert FamilyPrefix.Pr.value == "Pr"
        assert FamilyPrefix.Ev.value == "Ev"
        assert FamilyPrefix.Me.value == "Me"
        assert FamilyPrefix.Mo.value == "Mo"


class TestCognitionPath:
    def test_values(self):
        assert set(CognitionPath) == {
            CognitionPath.P,
            CognitionPath.R,
            CognitionPath.E,
            CognitionPath.U,
            CognitionPath.D,
            CognitionPath.S,
            CognitionPath.N,
        }


# ── MESSAGE_ID_PATTERN ──


class TestMessageIdPattern:
    @pytest.mark.parametrize(
        "valid_id",
        [
            "Pr00000001P",
            "Re00000012R",
            "Ev99999999E",
            "Me00000001U",
            "Mo00000100D",
            "Pr00000001S",
            "Re00000001N",
            # Lowercase prefix (ack format)
            "pr00000001P",
            "re00000012R",
            "ev99999999E",
            "me00000001U",
            "mo00000100D",
            "pr00000001N",
        ],
    )
    def test_valid_ids(self, valid_id: str):
        assert MESSAGE_ID_PATTERN.match(valid_id) is not None

    @pytest.mark.parametrize(
        "invalid_id",
        [
            "",
            "XX00000001P",       # invalid prefix
            "Pr0000001P",        # 7 digits
            "Pr000000001P",      # 9 digits
            "Pr00000001X",       # invalid path letter
            "Pr00000001p",       # lowercase path letter
            "pr00000001p",       # lowercase path letter
            "P00000001P",        # 1-letter prefix
            "Pre00000001P",      # 3-letter prefix
        ],
    )
    def test_invalid_ids(self, invalid_id: str):
        assert MESSAGE_ID_PATTERN.match(invalid_id) is None


# ── BusMessage ──


class TestBusMessage:
    def test_construction(self):
        msg = BusMessage(
            message_id="Pr00000001P",
            timecode=1.0,
            body="hello",
            sender=FamilyPrefix.Pr,
            receiver=FamilyPrefix.Ev,
        )
        assert msg.message_id == "Pr00000001P"
        assert msg.body == "hello"
        assert msg.sender == FamilyPrefix.Pr
        assert msg.receiver == FamilyPrefix.Ev
        assert msg.parent_message_id is None
        assert msg.context == ""
        assert msg.resources is None

    def test_validation_rejects_bad_id(self):
        with pytest.raises(ValueError, match="Invalid message_id format"):
            BusMessage(
                message_id="BADID",
                timecode=1.0,
                sender=FamilyPrefix.Pr,
                receiver=FamilyPrefix.Ev,
            )

    def test_trace_id_field(self):
        msg = BusMessage(
            message_id="Ev00000001E",
            timecode=1.0,
            trace_id="abc123def456",
            sender=FamilyPrefix.Re,
            receiver=FamilyPrefix.Ev,
        )
        assert msg.trace_id == "abc123def456"

    def test_trace_id_defaults_empty(self):
        msg = BusMessage(
            message_id="Re00000001R",
            timecode=1.0,
            sender=FamilyPrefix.Re,
            receiver=FamilyPrefix.Mo,
        )
        assert msg.trace_id == ""

    def test_is_ack_field(self):
        msg = BusMessage(
            message_id="pr00000001P",
            timecode=1.0,
            sender=FamilyPrefix.Pr,
            receiver=FamilyPrefix.Ev,
            is_ack=True,
        )
        assert msg.is_ack is True

    def test_is_ack_defaults_false(self):
        msg = BusMessage(
            message_id="Pr00000001P",
            timecode=1.0,
            sender=FamilyPrefix.Pr,
            receiver=FamilyPrefix.Ev,
        )
        assert msg.is_ack is False


# ── MessageBus ──


class TestMessageBusRegister:
    def test_register_creates_bounded_queue(self, mock_bus: MessageBus):
        queue = mock_bus.register("Pr.main")
        assert isinstance(queue, asyncio.Queue)
        assert queue.maxsize == 10  # from queue_limits fixture

    def test_register_uses_family_prefix_limit(self, mock_bus: MessageBus):
        queue = mock_bus.register("Re.main")
        assert queue.maxsize == 5

    def test_register_raises_on_duplicate(self, mock_bus: MessageBus):
        mock_bus.register("Pr.main")
        with pytest.raises(ValueError, match="already registered"):
            mock_bus.register("Pr.main")

    def test_unregister_removes_module(self, mock_bus: MessageBus):
        mock_bus.register("Ev.main")
        mock_bus.unregister("Ev.main")
        # Should be able to register again after unregister
        queue = mock_bus.register("Ev.main")
        assert isinstance(queue, asyncio.Queue)


class TestMessageBusSend:
    @pytest.mark.asyncio
    async def test_send_delivers_message(self, mock_bus: MessageBus):
        queue = mock_bus.register("Mo.main")
        msg = BusMessage(
            message_id="Re00000001R",
            timecode=1.0,
            body="act now",
            sender=FamilyPrefix.Re,
            receiver=FamilyPrefix.Mo,
        )
        result = await mock_bus.send(msg)
        assert result is None
        assert queue.qsize() == 1
        received = queue.get_nowait()
        assert received.body == "act now"

    @pytest.mark.asyncio
    async def test_send_returns_queue_full_signal(self, mock_logger: ModuleLogger):
        bus = MessageBus(mock_logger, queue_limits={"Te": 1})
        bus.register("Te.main")
        BusMessage(
            message_id="Pr00000001D",
            timecode=1.0,
            sender=FamilyPrefix.Pr,
            receiver=FamilyPrefix.Pr,  # doesn't matter for routing
        )
        BusMessage(
            message_id="Pr00000002D",
            timecode=2.0,
            sender=FamilyPrefix.Pr,
            receiver=FamilyPrefix.Pr,
        )
        # Register under a name that resolves for "Pr"
        bus2 = MessageBus(mock_logger, queue_limits={"Tx": 1})
        bus2.register("Tx.main")

        # Fill the queue (maxsize=1)
        BusMessage(
            message_id="Pr00000001D",
            timecode=1.0,
            sender=FamilyPrefix.Pr,
            receiver=FamilyPrefix.Pr,
        )
        # We need a bus where "Pr" resolves. Use mock_bus approach:
        small_bus = MessageBus(mock_logger, queue_limits={"Pr": 1})
        small_bus.register("Pr.main")

        msg_a = BusMessage(
            message_id="Ev00000001P",
            timecode=1.0,
            body="first",
            sender=FamilyPrefix.Ev,
            receiver=FamilyPrefix.Pr,
        )
        msg_b = BusMessage(
            message_id="Ev00000002P",
            timecode=2.0,
            body="second",
            sender=FamilyPrefix.Ev,
            receiver=FamilyPrefix.Pr,
        )
        result_a = await small_bus.send(msg_a)
        assert result_a is None

        result_b = await small_bus.send(msg_b)
        assert isinstance(result_b, QueueFullSignal)
        assert result_b.receiver == "Pr.main"
        assert result_b.message_id == "Ev00000002P"


class TestMessageBusReceive:
    @pytest.mark.asyncio
    async def test_receive_gets_message(self, mock_bus: MessageBus):
        mock_bus.register("Ev.main")
        msg = BusMessage(
            message_id="Pr00000001D",
            timecode=1.0,
            body="evaluate this",
            sender=FamilyPrefix.Pr,
            receiver=FamilyPrefix.Ev,
        )
        await mock_bus.send(msg)
        received = await mock_bus.receive("Ev.main", timeout=1.0)
        assert received.body == "evaluate this"

    @pytest.mark.asyncio
    async def test_receive_timeout(self, mock_bus: MessageBus):
        mock_bus.register("Me.main")
        with pytest.raises(asyncio.TimeoutError):
            await mock_bus.receive("Me.main", timeout=0.01)

    @pytest.mark.asyncio
    async def test_receive_unregistered_raises(self, mock_bus: MessageBus):
        with pytest.raises(ValueError, match="not registered"):
            await mock_bus.receive("nonexistent")


class TestMessageBusSubscribe:
    @pytest.mark.asyncio
    async def test_subscribe_fires_callback(self, mock_bus: MessageBus):
        mock_bus.register("Mo.main")
        received_messages = []

        async def callback(msg: BusMessage) -> None:
            received_messages.append(msg)

        mock_bus.subscribe("Mo.main", callback)
        msg = BusMessage(
            message_id="Re00000001R",
            timecode=1.0,
            body="reflex",
            sender=FamilyPrefix.Re,
            receiver=FamilyPrefix.Mo,
        )
        await mock_bus.send(msg)
        assert len(received_messages) == 1
        assert received_messages[0].body == "reflex"


class TestMessageBusStaticMethods:
    def test_make_message_id_format(self):
        mid = MessageBus.make_message_id(FamilyPrefix.Pr, 42, CognitionPath.P)
        assert mid == "Pr00000042P"

    def test_make_message_id_with_large_counter(self):
        mid = MessageBus.make_message_id(FamilyPrefix.Re, 12345678, CognitionPath.R)
        assert mid == "Re12345678R"

    def test_make_ack_id_lowercases_prefix(self):
        ack = MessageBus.make_ack_id("Pr00000012P")
        assert ack == "pr00000012P"

    def test_make_ack_id_already_lowercase(self):
        ack = MessageBus.make_ack_id("pr00000012P")
        assert ack == "pr00000012P"

    def test_validate_route_valid_p_path(self):
        assert MessageBus.validate_route(FamilyPrefix.Ev, FamilyPrefix.Pr, CognitionPath.P)
        assert MessageBus.validate_route(FamilyPrefix.Pr, FamilyPrefix.Ev, CognitionPath.P)
        assert MessageBus.validate_route(FamilyPrefix.Ev, FamilyPrefix.Mo, CognitionPath.P)
        assert MessageBus.validate_route(FamilyPrefix.Ev, FamilyPrefix.Me, CognitionPath.P)

    def test_validate_route_valid_r_path(self):
        assert MessageBus.validate_route(FamilyPrefix.Re, FamilyPrefix.Mo, CognitionPath.R)

    def test_validate_route_valid_e_path(self):
        assert MessageBus.validate_route(FamilyPrefix.Re, FamilyPrefix.Ev, CognitionPath.E)

    def test_validate_route_valid_u_path(self):
        assert MessageBus.validate_route(FamilyPrefix.Re, FamilyPrefix.Pr, CognitionPath.U)

    def test_validate_route_valid_d_path(self):
        assert MessageBus.validate_route(FamilyPrefix.Pr, FamilyPrefix.Re, CognitionPath.D)
        assert MessageBus.validate_route(FamilyPrefix.Pr, FamilyPrefix.Ev, CognitionPath.D)
        assert MessageBus.validate_route(FamilyPrefix.Pr, FamilyPrefix.Mo, CognitionPath.D)
        assert MessageBus.validate_route(FamilyPrefix.Pr, FamilyPrefix.Me, CognitionPath.D)

    def test_validate_route_invalid(self):
        assert not MessageBus.validate_route(FamilyPrefix.Mo, FamilyPrefix.Re, CognitionPath.R)
        assert not MessageBus.validate_route(FamilyPrefix.Ev, FamilyPrefix.Re, CognitionPath.P)


class TestMessageBusResolveReceiver:
    def test_resolve_plain_name(self, mock_bus: MessageBus):
        mock_bus.register("Pr.main")
        resolved = mock_bus._resolve_receiver("Pr")
        assert resolved == "Pr.main"

    def test_resolve_qualified_name(self, mock_bus: MessageBus):
        mock_bus.register("Pr.main")
        resolved = mock_bus._resolve_receiver("Pr.main")
        assert resolved == "Pr.main"

    def test_resolve_unknown_raises(self, mock_bus: MessageBus):
        with pytest.raises(ValueError, match="not registered"):
            mock_bus._resolve_receiver("Unknown")


class TestValidPathRoutes:
    def test_all_cognition_paths_have_routes(self):
        for path in CognitionPath:
            assert path in VALID_PATH_ROUTES, f"Missing routes for path {path}"

    def test_no_extra_paths(self):
        for key in VALID_PATH_ROUTES:
            assert key in CognitionPath
