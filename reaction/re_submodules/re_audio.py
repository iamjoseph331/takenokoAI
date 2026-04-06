"""Re.audio — speech-to-text perception submodule.

Transcribes audio input into text using an injectable STT backend,
then feeds the transcription into Re.main for classification and
routing through cognition paths.

Capabilities:
  - transcribe: Convert audio bytes (base64) to text

Usage:
    stt_backend = HuggingFaceSTT(config, transcribe_fn=mock_fn)
    audio_sub = AudioSubmodule(parent=re_module, stt_backend=stt_backend)
    await audio_sub.start()
    result = await audio_sub.invoke("transcribe", {"audio_b64": "..."})
"""

from __future__ import annotations

import base64
from typing import Any, Optional

from interface.audio import STTBackend
from interface.bus import BusMessage
from interface.capabilities import Capability
from interface.modules import MainModule, SubModule


class AudioSubmodule(SubModule):
    """Speech-to-text perception submodule for the Reaction family.

    Transcribes audio into text. The STT backend is injectable:
    use HuggingFaceSTT for local models, APISTT for cloud APIs,
    or inject a transcribe_fn for testing.
    """

    def __init__(
        self,
        parent: MainModule,
        stt_backend: STTBackend,
    ) -> None:
        super().__init__(
            parent=parent,
            name="audio",
            description=(
                "Speech-to-text: transcribes audio input into text "
                "for the agent to process"
            ),
            llm_config=parent._llm.config,
        )
        self._stt = stt_backend

    def capabilities(self) -> list[Capability]:
        return [
            Capability(
                name="transcribe",
                description="Transcribe audio to text",
                input_schema={
                    "audio_b64": "base64-encoded audio bytes (PCM 16-bit)",
                    "sample_rate": "(optional) sample rate, default 16000",
                },
                output_schema={
                    "status": "ok | error",
                    "text": "transcribed text",
                },
            ),
        ]

    async def _invoke_transcribe(self, params: dict[str, Any]) -> dict[str, Any]:
        """Transcribe base64-encoded audio to text."""
        audio_b64 = params.get("audio_b64", "")
        if not audio_b64:
            return {"status": "error", "reason": "Missing audio_b64 parameter"}

        sample_rate = int(params.get("sample_rate", 16000))

        try:
            audio_data = base64.b64decode(audio_b64)
        except Exception as e:
            return {"status": "error", "reason": f"Invalid base64: {e}"}

        if not self._stt.is_loaded:
            return {"status": "error", "reason": "STT backend not loaded"}

        text = await self._stt.transcribe(audio_data, sample_rate=sample_rate)

        self._logger.action(
            f"Transcribed {len(audio_data)} bytes -> {len(text)} chars",
            data={"sample_rate": sample_rate, "text_preview": text[:100]},
        )

        return {"status": "ok", "text": text}

    async def handle_message(self, message: BusMessage) -> Optional[BusMessage]:
        """Handle incoming messages.

        Routes capability invocations via the base class, and also
        handles legacy format: {"action": "transcribe", "audio_b64": "..."}.
        """
        body = message.body
        if isinstance(body, dict):
            # Capability-style invocation
            if "capability" in body:
                return await super().handle_message(message)

            # Legacy action-style
            if body.get("action") == "transcribe":
                result = await self._invoke_transcribe(body)
                self._logger.action(f"Transcription result: {result.get('status')}")
                return None

        return await super().handle_message(message)

    async def start(self) -> None:
        await self._stt.load()
        await super().start()
        self._logger.action("Audio perception ready (STT loaded)")

    async def stop(self) -> None:
        await self._stt.unload()
        await super().stop()
