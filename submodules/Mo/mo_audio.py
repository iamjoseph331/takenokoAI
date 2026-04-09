"""Mo.audio — text-to-speech action submodule.

Synthesizes text into audio using an injectable TTS backend,
enabling the agent to speak aloud.

Capabilities:
  - synthesize: Convert text to audio bytes (base64)

Usage:
    from interface.audio import HuggingFaceTTS, TTSConfig
    tts_backend = HuggingFaceTTS(TTSConfig(), synthesize_fn=mock_fn)
    audio_sub = AudioActionSubmodule(
        bus=bus, logger=logger, llm_config=llm_config,
        permissions=permissions, tts_backend=tts_backend,
    )
    await audio_sub.start()
    result = await audio_sub.invoke("synthesize", {"text": "Hello world"})
"""

from __future__ import annotations

import base64
from typing import Any

from interface.audio import TTSBackend
from interface.bus import (
    FamilyPrefix,
    MessageBus,
    QueueFullPolicy,
)
from interface.capabilities import Capability
from interface.llm import LLMConfig
from interface.logging import ModuleLogger
from interface.modules import SubModule
from interface.permissions import PermissionManager


class AudioActionSubmodule(SubModule):
    """Text-to-speech action submodule for the Motion family.

    Synthesizes text into audio. The TTS backend is injectable:
    use HuggingFaceTTS for local models, APITTS for cloud APIs,
    or inject a synthesize_fn for testing.
    """

    def __init__(
        self,
        *,
        family_prefix: FamilyPrefix = FamilyPrefix.Mo,
        bus: MessageBus,
        logger: ModuleLogger,
        llm_config: LLMConfig,
        permissions: PermissionManager,
        tts_backend: TTSBackend,
        policy: QueueFullPolicy = QueueFullPolicy.WAIT,
        max_retries: int = 3,
    ) -> None:
        super().__init__(
            family_prefix=family_prefix,
            name="audio",
            description=(
                "Text-to-speech: synthesizes text into audio output "
                "so the agent can speak"
            ),
            bus=bus,
            logger=logger,
            llm_config=llm_config,
            permissions=permissions,
            policy=policy,
            max_retries=max_retries,
        )
        self._tts = tts_backend

    def capabilities(self) -> list[Capability]:
        return [
            Capability(
                name="synthesize",
                description="Synthesize text into speech audio",
                input_schema={
                    "text": "text to synthesize",
                },
                output_schema={
                    "status": "ok | error",
                    "audio_b64": "base64-encoded audio bytes (PCM 16-bit)",
                    "sample_rate": "audio sample rate",
                    "duration_ms": "approximate duration in milliseconds",
                },
            ),
        ]

    async def _invoke_synthesize(self, params: dict[str, Any]) -> dict[str, Any]:
        """Synthesize text to base64-encoded audio."""
        text = params.get("text", "")
        if not text:
            return {"status": "error", "reason": "Missing text parameter"}

        if not self._tts.is_loaded:
            return {"status": "error", "reason": "TTS backend not loaded"}

        audio_data, sample_rate = await self._tts.synthesize(text)
        audio_b64 = base64.b64encode(audio_data).decode("ascii")

        # Estimate duration: PCM 16-bit = 2 bytes per sample
        num_samples = len(audio_data) // 2
        duration_ms = int(num_samples / sample_rate * 1000) if sample_rate > 0 else 0

        self._logger.action(
            f"Synthesized {len(text)} chars -> {len(audio_data)} bytes ({duration_ms}ms)",
            data={"sample_rate": sample_rate, "text_preview": text[:100]},
        )

        return {
            "status": "ok",
            "audio_b64": audio_b64,
            "sample_rate": sample_rate,
            "duration_ms": duration_ms,
        }

    async def start(self) -> None:
        await self._tts.load()
        await super().start()
        self._logger.action("Audio action ready (TTS loaded)")

    async def stop(self) -> None:
        await self._tts.unload()
        await super().stop()
