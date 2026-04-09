"""Audio backend abstraction for speech-to-text and text-to-speech.

Mirrors the LLMClient/CompletionFn pattern: backends are injectable so
tests can mock them and production can swap between local HuggingFace
models and cloud APIs.

Supported backends:
  STT (speech-to-text):
    - HuggingFaceSTT: local models (Qwen3-ASR-0.6B, Granite-4.0-1b-speech)
    - APISTT: placeholder for cloud APIs (OpenAI Whisper, etc.)

  TTS (text-to-speech):
    - HuggingFaceTTS: local models (Supertonic, MioTTS-0.6B)
    - APITTS: placeholder for cloud APIs (ElevenLabs, etc.)

Usage:
    stt = HuggingFaceSTT(model_id="Qwen/Qwen3-ASR-0.6B")
    await stt.load()
    text = await stt.transcribe(audio_bytes)

    tts = HuggingFaceTTS(model_id="Supertone/supertonic")
    await tts.load()
    audio, sr = await tts.synthesize("Hello world")
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

from interface.logging import ModuleLogger


# ── Type aliases for injectable functions ──

TranscribeFn = Callable[[bytes, int], Coroutine[Any, Any, str]]
"""(audio_data, sample_rate) -> transcribed text"""

SynthesizeFn = Callable[[str], Coroutine[Any, Any, tuple[bytes, int]]]
"""(text) -> (audio_data, sample_rate)"""


# ── Configuration ──


@dataclass
class STTConfig:
    """Configuration for a speech-to-text backend."""

    backend: str = "huggingface"  # "huggingface" | "api"
    model_id: str = "Qwen/Qwen3-ASR-0.6B"
    sample_rate: int = 16000
    device: str = "cpu"  # "cpu" | "cuda" | "mps"
    extra_params: dict[str, Any] = field(default_factory=dict)


@dataclass
class TTSConfig:
    """Configuration for a text-to-speech backend."""

    backend: str = "huggingface"  # "huggingface" | "api"
    model_id: str = "Supertone/supertonic"
    sample_rate: int = 24000
    device: str = "cpu"
    voice: str = "default"
    extra_params: dict[str, Any] = field(default_factory=dict)


# ── Abstract backends ──


class STTBackend(ABC):
    """Abstract speech-to-text backend."""

    @abstractmethod
    async def load(self) -> None:
        """Load the model / initialize the client. Call once before transcribe()."""
        ...

    @abstractmethod
    async def transcribe(self, audio_data: bytes, *, sample_rate: int = 16000) -> str:
        """Transcribe audio bytes to text.

        Args:
            audio_data: Raw audio bytes (PCM/WAV).
            sample_rate: Sample rate of the audio.

        Returns:
            Transcribed text.
        """
        ...

    @abstractmethod
    async def unload(self) -> None:
        """Release model resources."""
        ...

    @property
    @abstractmethod
    def is_loaded(self) -> bool:
        ...


class TTSBackend(ABC):
    """Abstract text-to-speech backend."""

    @abstractmethod
    async def load(self) -> None:
        """Load the model / initialize the client."""
        ...

    @abstractmethod
    async def synthesize(self, text: str) -> tuple[bytes, int]:
        """Synthesize text to audio.

        Args:
            text: Text to synthesize.

        Returns:
            Tuple of (audio_data bytes, sample_rate).
        """
        ...

    @abstractmethod
    async def unload(self) -> None:
        """Release model resources."""
        ...

    @property
    @abstractmethod
    def is_loaded(self) -> bool:
        ...


# ── HuggingFace STT backend ──


class HuggingFaceSTT(STTBackend):
    """Local speech-to-text using HuggingFace models.

    Supported models:
      - Qwen/Qwen3-ASR-0.6B (via qwen-asr or transformers)
      - ibm-granite/granite-4.0-1b-speech (via transformers)

    The actual model loading is deferred to load() and runs in a thread
    pool to avoid blocking the event loop.
    """

    def __init__(
        self,
        config: STTConfig,
        logger: ModuleLogger | None = None,
        *,
        transcribe_fn: TranscribeFn | None = None,
    ) -> None:
        self._config = config
        self._logger = logger or ModuleLogger("SYS", "stt")
        self._transcribe_fn = transcribe_fn
        self._model: Any = None
        self._processor: Any = None
        self._loaded = False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    async def load(self) -> None:
        if self._transcribe_fn:
            self._loaded = True
            self._logger.action(f"STT using injected transcribe_fn")
            return

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._load_model_sync)
        self._loaded = True
        self._logger.action(f"STT model loaded: {self._config.model_id}")

    def _load_model_sync(self) -> None:
        """Load the HuggingFace model (runs in thread pool)."""
        model_id = self._config.model_id

        if "qwen" in model_id.lower() and "asr" in model_id.lower():
            self._load_qwen_asr(model_id)
        elif "granite" in model_id.lower():
            self._load_granite(model_id)
        else:
            self._load_generic_pipeline(model_id)

    def _load_qwen_asr(self, model_id: str) -> None:
        try:
            from qwen_asr import Qwen3ASRModel
            self._model = Qwen3ASRModel.from_pretrained(
                model_id, device=self._config.device
            )
        except ImportError:
            self._load_generic_pipeline(model_id)

    def _load_granite(self, model_id: str) -> None:
        from transformers import AutoProcessor, AutoModelForSpeechSeq2Seq
        self._processor = AutoProcessor.from_pretrained(model_id)
        self._model = AutoModelForSpeechSeq2Seq.from_pretrained(model_id)
        if self._config.device != "cpu":
            self._model = self._model.to(self._config.device)

    def _load_generic_pipeline(self, model_id: str) -> None:
        from transformers import pipeline
        self._model = pipeline(
            "automatic-speech-recognition",
            model=model_id,
            device=self._config.device if self._config.device != "cpu" else -1,
        )

    async def transcribe(self, audio_data: bytes, *, sample_rate: int = 16000) -> str:
        if not self._loaded:
            raise RuntimeError("STT model not loaded. Call load() first.")

        if self._transcribe_fn:
            return await self._transcribe_fn(audio_data, sample_rate)

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._transcribe_sync, audio_data, sample_rate
        )

    def _transcribe_sync(self, audio_data: bytes, sample_rate: int) -> str:
        """Synchronous transcription (runs in thread pool)."""
        import numpy as np

        # Convert bytes to float32 numpy array
        audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0

        if hasattr(self._model, "transcribe"):
            # Qwen-ASR style
            return self._model.transcribe(audio_np, sr=sample_rate)

        if self._processor is not None:
            # Granite style
            inputs = self._processor(
                audio_np, sampling_rate=sample_rate, return_tensors="pt"
            )
            if self._config.device != "cpu":
                inputs = {k: v.to(self._config.device) for k, v in inputs.items()}
            generated = self._model.generate(**inputs)
            return self._processor.batch_decode(generated, skip_special_tokens=True)[0]

        # Pipeline style
        result = self._model({"raw": audio_np, "sampling_rate": sample_rate})
        return result.get("text", "")

    async def unload(self) -> None:
        self._model = None
        self._processor = None
        self._loaded = False
        self._logger.action("STT model unloaded")


# ── HuggingFace TTS backend ──


class HuggingFaceTTS(TTSBackend):
    """Local text-to-speech using HuggingFace models.

    Supported models:
      - Supertone/supertonic (via supertonic package, ONNX)
      - Aratako/MioTTS-0.6B (via transformers)

    The actual model loading is deferred to load() and runs in a thread
    pool to avoid blocking the event loop.
    """

    def __init__(
        self,
        config: TTSConfig,
        logger: ModuleLogger | None = None,
        *,
        synthesize_fn: SynthesizeFn | None = None,
    ) -> None:
        self._config = config
        self._logger = logger or ModuleLogger("SYS", "tts")
        self._synthesize_fn = synthesize_fn
        self._model: Any = None
        self._loaded = False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    async def load(self) -> None:
        if self._synthesize_fn:
            self._loaded = True
            self._logger.action("TTS using injected synthesize_fn")
            return

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._load_model_sync)
        self._loaded = True
        self._logger.action(f"TTS model loaded: {self._config.model_id}")

    def _load_model_sync(self) -> None:
        model_id = self._config.model_id

        if "supertonic" in model_id.lower():
            self._load_supertonic()
        elif "miotts" in model_id.lower():
            self._load_miotts(model_id)
        else:
            self._load_generic(model_id)

    def _load_supertonic(self) -> None:
        from supertonic import TTS
        self._model = TTS(auto_download=True)

    def _load_miotts(self, model_id: str) -> None:
        from transformers import AutoTokenizer, AutoModelForCausalLM
        self._model = {
            "tokenizer": AutoTokenizer.from_pretrained(model_id),
            "model": AutoModelForCausalLM.from_pretrained(model_id),
        }

    def _load_generic(self, model_id: str) -> None:
        from transformers import pipeline
        self._model = pipeline("text-to-speech", model=model_id)

    async def synthesize(self, text: str) -> tuple[bytes, int]:
        if not self._loaded:
            raise RuntimeError("TTS model not loaded. Call load() first.")

        if self._synthesize_fn:
            return await self._synthesize_fn(text)

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._synthesize_sync, text)

    def _synthesize_sync(self, text: str) -> tuple[bytes, int]:
        """Synchronous synthesis (runs in thread pool)."""
        import numpy as np

        if hasattr(self._model, "synthesize"):
            # Supertonic style
            voice_style = self._model.get_voice_style(
                voice_name=self._config.voice
                if self._config.voice != "default" else "M1"
            )
            wav, _duration = self._model.synthesize(text, voice_style=voice_style)
            audio_bytes = (np.array(wav) * 32768).astype(np.int16).tobytes()
            return audio_bytes, self._config.sample_rate

        if isinstance(self._model, dict) and "tokenizer" in self._model:
            # MioTTS style — placeholder, actual codec integration needed
            raise NotImplementedError(
                "MioTTS inference requires MioCodec; use synthesize_fn injection"
            )

        # Pipeline style
        result = self._model(text)
        audio = result.get("audio", result.get("waveform", []))
        sr = result.get("sampling_rate", self._config.sample_rate)
        audio_bytes = (np.array(audio) * 32768).astype(np.int16).tobytes()
        return audio_bytes, sr

    async def unload(self) -> None:
        self._model = None
        self._loaded = False
        self._logger.action("TTS model unloaded")


# ── API backends (placeholders for future cloud API integration) ──


class APISTT(STTBackend):
    """Placeholder for cloud-based STT APIs (OpenAI Whisper, Google, etc.).

    Configure via STTConfig with backend="api" and extra_params for
    API-specific settings (api_key, endpoint, etc.).
    """

    def __init__(
        self,
        config: STTConfig,
        logger: ModuleLogger | None = None,
    ) -> None:
        self._config = config
        self._logger = logger or ModuleLogger("SYS", "stt-api")
        self._loaded = False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    async def load(self) -> None:
        self._loaded = True
        self._logger.action(f"API STT ready (endpoint: {self._config.extra_params.get('endpoint', 'not set')})")

    async def transcribe(self, audio_data: bytes, *, sample_rate: int = 16000) -> str:
        raise NotImplementedError(
            "API STT not yet implemented. Configure a specific API provider "
            "in extra_params or use HuggingFaceSTT for local inference."
        )

    async def unload(self) -> None:
        self._loaded = False


class APITTS(TTSBackend):
    """Placeholder for cloud-based TTS APIs (ElevenLabs, Google, etc.)."""

    def __init__(
        self,
        config: TTSConfig,
        logger: ModuleLogger | None = None,
    ) -> None:
        self._config = config
        self._logger = logger or ModuleLogger("SYS", "tts-api")
        self._loaded = False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    async def load(self) -> None:
        self._loaded = True
        self._logger.action(f"API TTS ready (endpoint: {self._config.extra_params.get('endpoint', 'not set')})")

    async def synthesize(self, text: str) -> tuple[bytes, int]:
        raise NotImplementedError(
            "API TTS not yet implemented. Configure a specific API provider "
            "in extra_params or use HuggingFaceTTS for local inference."
        )

    async def unload(self) -> None:
        self._loaded = False


# ── Factory ──


def create_stt_backend(config: STTConfig, logger: ModuleLogger | None = None) -> STTBackend:
    """Create an STT backend from config."""
    if config.backend == "api":
        return APISTT(config, logger)
    return HuggingFaceSTT(config, logger)


def create_tts_backend(config: TTSConfig, logger: ModuleLogger | None = None) -> TTSBackend:
    """Create a TTS backend from config."""
    if config.backend == "api":
        return APITTS(config, logger)
    return HuggingFaceTTS(config, logger)
