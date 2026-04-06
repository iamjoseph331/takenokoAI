"""Mo.audio — text-to-speech action submodule.

Synthesizes text into audio using an injectable TTS backend,
enabling the agent to speak aloud.

Capabilities:
  - synthesize: Convert text to audio bytes (base64)

Usage:
    tts_backend = HuggingFaceTTS(config, synthesize_fn=mock_fn)
    audio_sub = AudioActionSubmodule(parent=mo_module, tts_backend=tts_backend)
    await audio_sub.start()
    result = await audio_sub.invoke("synthesize", {"text": "Hello world"})
"""

from __future__ import annotations

import base64
from typing import Any, Optional

from interface.audio import TTSBackend
from interface.bus import BusMessage
from interface.capabilities import Capability
from interface.modules import MainModule, SubModule


class AudioActionSubmodule(SubModule):
    """Text-to-speech action submodule for the Motion family.

    Synthesizes text into audio. The TTS backend is injectable:
    use HuggingFaceTTS for local models, APITTS for cloud APIs,
    or inject a synthesize_fn for testing.
    """

    def __init__(
        self,
        parent: MainModule,
        tts_backend: TTSBackend,
    ) -> None:
        super().__init__(
            parent=parent,
            name="audio",
            description=(
                "Text-to-speech: synthesizes text into audio output "
                "so the agent can speak"
            ),
            llm_config=parent._llm.config,
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

    async def handle_message(self, message: BusMessage) -> Optional[BusMessage]:
        """Handle incoming messages.

        Routes capability invocations via the base class, and also
        handles legacy format: {"action": "synthesize", "text": "..."}.
        """
        body = message.body
        if isinstance(body, dict):
            if "capability" in body:
                return await super().handle_message(message)

            if body.get("action") == "synthesize":
                result = await self._invoke_synthesize(body)
                self._logger.action(f"Synthesis result: {result.get('status')}")
                return None

        return await super().handle_message(message)

    async def start(self) -> None:
        await self._tts.load()
        await super().start()
        self._logger.action("Audio action ready (TTS loaded)")

    async def stop(self) -> None:
        await self._tts.unload()
        await super().stop()
