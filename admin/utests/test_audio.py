"""Group: Audio Submodules

Tests for STT/TTS backends (with mocked inference), Re.audio (transcribe),
and Mo.audio (synthesize) submodules. No actual model loading.
"""

from __future__ import annotations

import base64
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from interface.audio import (
    APISTT,
    APITTS,
    HuggingFaceSTT,
    HuggingFaceTTS,
    STTConfig,
    TTSConfig,
    create_stt_backend,
    create_tts_backend,
)
from interface.bus import BusMessage, CognitionPath, FamilyPrefix, MessageBus
from interface.capabilities import Capability
from interface.llm import LLMConfig
from interface.logging import ModuleLogger
from interface.modules import MainModule
from interface.permissions import PermissionManager
from motion.mo_submodules.mo_audio import AudioActionSubmodule
from reaction.re_submodules.re_audio import AudioSubmodule


# ── Helpers ──


class _StubMainModule(MainModule):
    def __init__(self, prefix, bus, logger, llm_config, permissions):
        super().__init__(prefix, bus, logger, llm_config, permissions)

    async def _message_loop(self):
        pass

    async def get_resources(self):
        return {}

    async def get_limits(self):
        return {}

    async def pause_and_answer(self, question, requester):
        return ""


def _make_module(prefix_str: str):
    logger = ModuleLogger("SYS", "test")
    bus = MessageBus(logger)
    permissions = PermissionManager(logger)
    llm_config = LLMConfig()
    prefix = FamilyPrefix(prefix_str)
    mod_logger = ModuleLogger(prefix_str, "main")
    module = _StubMainModule(prefix, bus, mod_logger, llm_config, permissions)
    for p in ("Re", "Pr", "Ev", "Me", "Mo"):
        qname = f"{p}.main"
        if qname not in bus._queues:
            bus.register(qname)
    return bus, module


def _fake_audio(text: str = "hello") -> bytes:
    """Create fake PCM 16-bit audio bytes."""
    import struct
    samples = [int(32767 * 0.5)] * 1600  # 0.1s at 16kHz
    return struct.pack(f"<{len(samples)}h", *samples)


# ── STT Backend Tests ──


class TestHuggingFaceSTT:
    @pytest.mark.asyncio
    async def test_with_injected_fn(self):
        mock_fn = AsyncMock(return_value="hello world")
        config = STTConfig(model_id="test/model")
        backend = HuggingFaceSTT(config, transcribe_fn=mock_fn)
        await backend.load()
        assert backend.is_loaded

        result = await backend.transcribe(b"\x00\x00", sample_rate=16000)
        assert result == "hello world"
        mock_fn.assert_awaited_once_with(b"\x00\x00", 16000)

    @pytest.mark.asyncio
    async def test_not_loaded_raises(self):
        config = STTConfig(model_id="test/model")
        backend = HuggingFaceSTT(config, transcribe_fn=AsyncMock())
        # Don't call load()
        assert not backend.is_loaded
        with pytest.raises(RuntimeError, match="not loaded"):
            await backend.transcribe(b"\x00")

    @pytest.mark.asyncio
    async def test_unload(self):
        mock_fn = AsyncMock(return_value="text")
        config = STTConfig()
        backend = HuggingFaceSTT(config, transcribe_fn=mock_fn)
        await backend.load()
        assert backend.is_loaded
        await backend.unload()
        assert not backend.is_loaded


class TestHuggingFaceTTS:
    @pytest.mark.asyncio
    async def test_with_injected_fn(self):
        fake_audio = b"\x00\x01" * 100
        mock_fn = AsyncMock(return_value=(fake_audio, 24000))
        config = TTSConfig(model_id="test/model")
        backend = HuggingFaceTTS(config, synthesize_fn=mock_fn)
        await backend.load()
        assert backend.is_loaded

        audio, sr = await backend.synthesize("hello")
        assert audio == fake_audio
        assert sr == 24000
        mock_fn.assert_awaited_once_with("hello")

    @pytest.mark.asyncio
    async def test_not_loaded_raises(self):
        config = TTSConfig(model_id="test/model")
        backend = HuggingFaceTTS(config, synthesize_fn=AsyncMock())
        assert not backend.is_loaded
        with pytest.raises(RuntimeError, match="not loaded"):
            await backend.synthesize("hi")

    @pytest.mark.asyncio
    async def test_unload(self):
        mock_fn = AsyncMock(return_value=(b"", 24000))
        config = TTSConfig()
        backend = HuggingFaceTTS(config, synthesize_fn=mock_fn)
        await backend.load()
        await backend.unload()
        assert not backend.is_loaded


class TestAPIBackends:
    @pytest.mark.asyncio
    async def test_api_stt_placeholder(self):
        config = STTConfig(backend="api")
        backend = APISTT(config)
        await backend.load()
        assert backend.is_loaded
        with pytest.raises(NotImplementedError):
            await backend.transcribe(b"\x00")

    @pytest.mark.asyncio
    async def test_api_tts_placeholder(self):
        config = TTSConfig(backend="api")
        backend = APITTS(config)
        await backend.load()
        assert backend.is_loaded
        with pytest.raises(NotImplementedError):
            await backend.synthesize("hi")


class TestFactoryFunctions:
    def test_create_stt_huggingface(self):
        backend = create_stt_backend(STTConfig(backend="huggingface"))
        assert isinstance(backend, HuggingFaceSTT)

    def test_create_stt_api(self):
        backend = create_stt_backend(STTConfig(backend="api"))
        assert isinstance(backend, APISTT)

    def test_create_tts_huggingface(self):
        backend = create_tts_backend(TTSConfig(backend="huggingface"))
        assert isinstance(backend, HuggingFaceTTS)

    def test_create_tts_api(self):
        backend = create_tts_backend(TTSConfig(backend="api"))
        assert isinstance(backend, APITTS)


# ── Re.audio submodule tests ──


class TestReAudio:
    @pytest.mark.asyncio
    async def test_transcribe_capability(self):
        _, re_module = _make_module("Re")
        mock_fn = AsyncMock(return_value="transcribed text")
        backend = HuggingFaceSTT(STTConfig(), transcribe_fn=mock_fn)

        sub = AudioSubmodule(parent=re_module, stt_backend=backend)
        await sub.start()

        audio = _fake_audio()
        audio_b64 = base64.b64encode(audio).decode()
        result = await sub.invoke("transcribe", {"audio_b64": audio_b64})

        assert result["status"] == "ok"
        assert result["text"] == "transcribed text"

    @pytest.mark.asyncio
    async def test_transcribe_missing_audio(self):
        _, re_module = _make_module("Re")
        mock_fn = AsyncMock(return_value="")
        backend = HuggingFaceSTT(STTConfig(), transcribe_fn=mock_fn)

        sub = AudioSubmodule(parent=re_module, stt_backend=backend)
        await sub.start()

        result = await sub.invoke("transcribe", {})
        assert result["status"] == "error"
        assert "Missing" in result["reason"]

    @pytest.mark.asyncio
    async def test_transcribe_invalid_base64(self):
        _, re_module = _make_module("Re")
        mock_fn = AsyncMock(return_value="")
        backend = HuggingFaceSTT(STTConfig(), transcribe_fn=mock_fn)

        sub = AudioSubmodule(parent=re_module, stt_backend=backend)
        await sub.start()

        result = await sub.invoke("transcribe", {"audio_b64": "not-valid-b64!!!"})
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_transcribe_backend_not_loaded(self):
        _, re_module = _make_module("Re")
        mock_fn = AsyncMock(return_value="")
        backend = HuggingFaceSTT(STTConfig(), transcribe_fn=mock_fn)
        # Don't call start() — backend not loaded

        sub = AudioSubmodule(parent=re_module, stt_backend=backend)

        audio_b64 = base64.b64encode(b"\x00\x00").decode()
        result = await sub.invoke("transcribe", {"audio_b64": audio_b64})
        assert result["status"] == "error"
        assert "not loaded" in result["reason"]

    @pytest.mark.asyncio
    async def test_capabilities_declared(self):
        _, re_module = _make_module("Re")
        backend = HuggingFaceSTT(STTConfig(), transcribe_fn=AsyncMock())
        sub = AudioSubmodule(parent=re_module, stt_backend=backend)

        caps = sub.capabilities()
        assert len(caps) == 1
        assert caps[0].name == "transcribe"

    @pytest.mark.asyncio
    async def test_registered_with_parent(self):
        _, re_module = _make_module("Re")
        backend = HuggingFaceSTT(STTConfig(), transcribe_fn=AsyncMock())
        sub = AudioSubmodule(parent=re_module, stt_backend=backend)

        assert "audio" in re_module._submodules
        assert re_module.find_capability("transcribe") is sub

    @pytest.mark.asyncio
    async def test_announce(self):
        _, re_module = _make_module("Re")
        backend = HuggingFaceSTT(STTConfig(), transcribe_fn=AsyncMock())
        sub = AudioSubmodule(parent=re_module, stt_backend=backend)

        ann = sub.announce()
        assert ann["name"] == "audio"
        assert ann["family"] == "Re"
        assert len(ann["capabilities"]) == 1
        assert ann["capabilities"][0]["name"] == "transcribe"

    @pytest.mark.asyncio
    async def test_handle_message_capability_style(self):
        _, re_module = _make_module("Re")
        mock_fn = AsyncMock(return_value="hello from audio")
        backend = HuggingFaceSTT(STTConfig(), transcribe_fn=mock_fn)
        sub = AudioSubmodule(parent=re_module, stt_backend=backend)
        await sub.start()

        audio_b64 = base64.b64encode(_fake_audio()).decode()
        msg = BusMessage(
            message_id="Pr00000001D",
            timecode=MessageBus.now(),
            context="test",
            body={"capability": "transcribe", "params": {"audio_b64": audio_b64}},
            sender=FamilyPrefix.Pr,
            receiver=FamilyPrefix.Re,
        )
        await sub.handle_message(msg)
        # Should have invoked the transcribe fn
        mock_fn.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_handle_message_legacy_style(self):
        _, re_module = _make_module("Re")
        mock_fn = AsyncMock(return_value="legacy result")
        backend = HuggingFaceSTT(STTConfig(), transcribe_fn=mock_fn)
        sub = AudioSubmodule(parent=re_module, stt_backend=backend)
        await sub.start()

        audio_b64 = base64.b64encode(_fake_audio()).decode()
        msg = BusMessage(
            message_id="Pr00000001D",
            timecode=MessageBus.now(),
            context="test",
            body={"action": "transcribe", "audio_b64": audio_b64},
            sender=FamilyPrefix.Pr,
            receiver=FamilyPrefix.Re,
        )
        await sub.handle_message(msg)
        mock_fn.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stop_unloads_backend(self):
        _, re_module = _make_module("Re")
        mock_fn = AsyncMock(return_value="")
        backend = HuggingFaceSTT(STTConfig(), transcribe_fn=mock_fn)
        sub = AudioSubmodule(parent=re_module, stt_backend=backend)
        await sub.start()
        assert backend.is_loaded
        await sub.stop()
        assert not backend.is_loaded


# ── Mo.audio submodule tests ──


class TestMoAudio:
    @pytest.mark.asyncio
    async def test_synthesize_capability(self):
        _, mo_module = _make_module("Mo")
        fake_audio = b"\x00\x01" * 2400  # 0.1s at 24kHz
        mock_fn = AsyncMock(return_value=(fake_audio, 24000))
        backend = HuggingFaceTTS(TTSConfig(), synthesize_fn=mock_fn)

        sub = AudioActionSubmodule(parent=mo_module, tts_backend=backend)
        await sub.start()

        result = await sub.invoke("synthesize", {"text": "hello world"})

        assert result["status"] == "ok"
        assert "audio_b64" in result
        assert result["sample_rate"] == 24000
        assert result["duration_ms"] > 0

        # Verify the base64 decodes back
        decoded = base64.b64decode(result["audio_b64"])
        assert decoded == fake_audio

    @pytest.mark.asyncio
    async def test_synthesize_missing_text(self):
        _, mo_module = _make_module("Mo")
        mock_fn = AsyncMock(return_value=(b"", 24000))
        backend = HuggingFaceTTS(TTSConfig(), synthesize_fn=mock_fn)
        sub = AudioActionSubmodule(parent=mo_module, tts_backend=backend)
        await sub.start()

        result = await sub.invoke("synthesize", {})
        assert result["status"] == "error"
        assert "Missing" in result["reason"]

    @pytest.mark.asyncio
    async def test_synthesize_backend_not_loaded(self):
        _, mo_module = _make_module("Mo")
        mock_fn = AsyncMock(return_value=(b"", 24000))
        backend = HuggingFaceTTS(TTSConfig(), synthesize_fn=mock_fn)
        sub = AudioActionSubmodule(parent=mo_module, tts_backend=backend)
        # Don't call start()

        result = await sub.invoke("synthesize", {"text": "hi"})
        assert result["status"] == "error"
        assert "not loaded" in result["reason"]

    @pytest.mark.asyncio
    async def test_capabilities_declared(self):
        _, mo_module = _make_module("Mo")
        backend = HuggingFaceTTS(TTSConfig(), synthesize_fn=AsyncMock())
        sub = AudioActionSubmodule(parent=mo_module, tts_backend=backend)

        caps = sub.capabilities()
        assert len(caps) == 1
        assert caps[0].name == "synthesize"

    @pytest.mark.asyncio
    async def test_registered_with_parent(self):
        _, mo_module = _make_module("Mo")
        backend = HuggingFaceTTS(TTSConfig(), synthesize_fn=AsyncMock())
        sub = AudioActionSubmodule(parent=mo_module, tts_backend=backend)

        assert "audio" in mo_module._submodules
        assert mo_module.find_capability("synthesize") is sub

    @pytest.mark.asyncio
    async def test_announce(self):
        _, mo_module = _make_module("Mo")
        backend = HuggingFaceTTS(TTSConfig(), synthesize_fn=AsyncMock())
        sub = AudioActionSubmodule(parent=mo_module, tts_backend=backend)

        ann = sub.announce()
        assert ann["name"] == "audio"
        assert ann["family"] == "Mo"
        assert ann["capabilities"][0]["name"] == "synthesize"

    @pytest.mark.asyncio
    async def test_handle_message_capability_style(self):
        _, mo_module = _make_module("Mo")
        fake_audio = b"\x00\x01" * 100
        mock_fn = AsyncMock(return_value=(fake_audio, 24000))
        backend = HuggingFaceTTS(TTSConfig(), synthesize_fn=mock_fn)
        sub = AudioActionSubmodule(parent=mo_module, tts_backend=backend)
        await sub.start()

        msg = BusMessage(
            message_id="Pr00000001D",
            timecode=MessageBus.now(),
            context="test",
            body={"capability": "synthesize", "params": {"text": "hey"}},
            sender=FamilyPrefix.Pr,
            receiver=FamilyPrefix.Mo,
        )
        await sub.handle_message(msg)
        mock_fn.assert_awaited_once_with("hey")

    @pytest.mark.asyncio
    async def test_handle_message_legacy_style(self):
        _, mo_module = _make_module("Mo")
        fake_audio = b"\x00\x01" * 100
        mock_fn = AsyncMock(return_value=(fake_audio, 24000))
        backend = HuggingFaceTTS(TTSConfig(), synthesize_fn=mock_fn)
        sub = AudioActionSubmodule(parent=mo_module, tts_backend=backend)
        await sub.start()

        msg = BusMessage(
            message_id="Pr00000001D",
            timecode=MessageBus.now(),
            context="test",
            body={"action": "synthesize", "text": "hey"},
            sender=FamilyPrefix.Pr,
            receiver=FamilyPrefix.Mo,
        )
        await sub.handle_message(msg)
        mock_fn.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stop_unloads_backend(self):
        _, mo_module = _make_module("Mo")
        mock_fn = AsyncMock(return_value=(b"", 24000))
        backend = HuggingFaceTTS(TTSConfig(), synthesize_fn=mock_fn)
        sub = AudioActionSubmodule(parent=mo_module, tts_backend=backend)
        await sub.start()
        assert backend.is_loaded
        await sub.stop()
        assert not backend.is_loaded
