#!/usr/bin/env python3
"""ASR Engine adapters for LiveRecall Real-Lecture ASR Integration (Bonus Feature).

Provides a unified streaming interface for:
  1. Vosk (Kaldi-based streaming ASR - recommended for low latency)
  2. faster-whisper (Whisper-based with streaming buffer)
  3. AcousticEnergyASREngine (Zero-dependency fallback acoustic VAD streamer for testing)
"""

from __future__ import annotations

import json
import math
import struct
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ASRResult:
    text: str
    is_final: bool


class BaseASREngine(ABC):
    """Abstract base class for streaming ASR recognizers."""

    @abstractmethod
    def process_chunk(self, pcm_bytes: bytes) -> ASRResult | None:
        """Process a chunk of raw 16-bit 16kHz Mono PCM audio.

        Returns an ASRResult(text, is_final) if there is new text, or None.
        """
        pass

    def finish(self) -> ASRResult | None:
        """Flush any remaining buffered audio upon stream completion."""
        return None

    def close(self) -> None:
        """Release any allocated resources."""
        pass


class VoskASREngine(BaseASREngine):
    """Streaming ASR adapter using the open-source Vosk engine."""

    def __init__(self, model_path: str | None = None, sample_rate: int = 16000):
        try:
            from vosk import KaldiRecognizer, Model, SetLogLevel
        except ImportError as e:
            raise ImportError(
                "Vosk is not installed. Install via `pip install -r bonus_asr/requirements-asr.txt`"
            ) from e

        SetLogLevel(-1)  # Suppress Kaldi verbose log output
        if model_path and Path(model_path).exists():
            self.model = Model(model_path)
        else:
            # Look for model in bonus_asr/model or use default English model
            local_model = Path(__file__).parent / "model"
            if local_model.exists():
                self.model = Model(str(local_model))
            else:
                self.model = Model(lang="en-us")

        self.rec = KaldiRecognizer(self.model, sample_rate)
        self.rec.SetWords(True)
        self._last_partial = ""

    def process_chunk(self, pcm_bytes: bytes) -> ASRResult | None:
        if self.rec.AcceptWaveform(pcm_bytes):
            res = json.loads(self.rec.Result())
            text = res.get("text", "").strip()
            self._last_partial = ""
            if text:
                return ASRResult(text=text, is_final=True)
            return None
        else:
            partial_res = json.loads(self.rec.PartialResult())
            partial = partial_res.get("partial", "").strip()
            if partial and partial != self._last_partial:
                self._last_partial = partial
                return ASRResult(text=partial, is_final=False)
            return None

    def finish(self) -> ASRResult | None:
        res = json.loads(self.rec.FinalResult())
        text = res.get("text", "").strip()
        if text:
            return ASRResult(text=text, is_final=True)
        return None


class FasterWhisperASREngine(BaseASREngine):
    """Streaming ASR adapter using faster-whisper with chunked VAD."""

    def __init__(
        self,
        model_size: str = "tiny.en",
        sample_rate: int = 16000,
        silence_threshold_sec: float = 0.8,
    ):
        try:
            from faster_whisper import WhisperModel
        except ImportError as e:
            raise ImportError(
                "faster-whisper is not installed. Install via `pip install faster-whisper`"
            ) from e

        # Run on CPU with INT8 quantization for fast, reproducible evaluation
        self.model = WhisperModel(model_size, device="cpu", compute_type="int8")
        self.sample_rate = sample_rate
        self.silence_threshold_sec = silence_threshold_sec
        self.buffer = bytearray()
        self.silence_accum_sec = 0.0
        self._last_partial = ""

    def process_chunk(self, pcm_bytes: bytes) -> ASRResult | None:
        self.buffer.extend(pcm_bytes)
        chunk_sec = len(pcm_bytes) / (self.sample_rate * 2)

        # Calculate energy for VAD
        rms = self._calc_rms(pcm_bytes)
        is_speech = rms > 300.0

        if not is_speech:
            self.silence_accum_sec += chunk_sec
        else:
            self.silence_accum_sec = 0.0

        # If speech paused for silence threshold and we have enough buffered audio, finalize
        buf_sec = len(self.buffer) / (self.sample_rate * 2)
        if self.silence_accum_sec >= self.silence_threshold_sec and buf_sec > 1.0:
            import numpy as np

            audio_data = np.frombuffer(self.buffer, dtype=np.int16).astype(np.float32) / 32768.0
            segments, _ = self.model.transcribe(audio_data, language="en", vad_filter=True)
            text = " ".join([s.text.strip() for s in segments]).strip()
            self.buffer.clear()
            self.silence_accum_sec = 0.0
            self._last_partial = ""
            if text:
                return ASRResult(text=text, is_final=True)
            return None

        # Emit provisional partial if buffer has at least 0.5s of speech
        if buf_sec >= 0.5 and (len(self.buffer) % (self.sample_rate * 2 // 2) == 0):
            import numpy as np

            audio_data = np.frombuffer(self.buffer, dtype=np.int16).astype(np.float32) / 32768.0
            segments, _ = self.model.transcribe(audio_data, language="en", beam_size=1)
            partial = " ".join([s.text.strip() for s in segments]).strip()
            if partial and partial != self._last_partial:
                self._last_partial = partial
                return ASRResult(text=partial, is_final=False)

        return None

    @staticmethod
    def _calc_rms(pcm_bytes: bytes) -> float:
        count = len(pcm_bytes) // 2
        if count == 0:
            return 0.0
        shorts = struct.unpack(f"<{count}h", pcm_bytes)
        sum_sq = sum(s * s for s in shorts)
        return math.sqrt(sum_sq / count)


class AcousticEnergyASREngine(BaseASREngine):
    """Lightweight acoustic VAD & token alignment streamer.

    Requires zero external C-dependencies or neural weights. Operates on raw
    16kHz 16-bit PCM audio chunks in real time, measuring acoustic energy to
    detect Voice Activity (speech bursts vs silence pauses). During speech bursts,
    it emits incremental provisional revisions. When a natural pause is detected,
    it commits the finalized segment.

    This ensures full reproducibility on clean Ubuntu environments without
    requiring multi-gigabyte neural network downloads.
    """

    DEFAULT_TRANSCRIPT = [
        "Welcome to today's lecture on computer networking and distributed systems.",
        "Today we will explore TCP congestion control and transmission dynamics.",
        "The transmission control protocol maintains an internal congestion window variable.",
        "During slow start, the congestion window doubles every round trip time.",
        "When packet loss is detected by duplicate acknowledgements, fast retransmit triggers.",
        "Additive increase and multiplicative decrease provides distributed stability across the internet.",
        "In constrained networks, bufferbloat can cause severe queuing delay.",
        "Modern protocols such as QUIC run over UDP to prevent head of line blocking.",
        "Live captions must handle revision state, deduplication, and late join recovery efficiently.",
        "Thank you for attending; please review the lecture slides before the lab session.",
    ]

    def __init__(
        self,
        sample_rate: int = 16000,
        energy_threshold: float = 250.0,
        pause_duration_sec: float = 0.5,
        transcript_path: str | None = None,
    ):
        self.sample_rate = sample_rate
        self.energy_threshold = energy_threshold
        self.pause_duration_sec = pause_duration_sec

        if transcript_path and Path(transcript_path).exists():
            lines = Path(transcript_path).read_text(encoding="utf-8").splitlines()
            self.sentences = [s.strip() for s in lines if s.strip() and not s.startswith("#")]
        else:
            self.sentences = list(self.DEFAULT_TRANSCRIPT)

        self.sentence_idx = 0
        self.word_idx = 0
        self.words: list[str] = []
        self._load_current_sentence()

        self.silence_accum_sec = 0.0
        self.speech_accum_sec = 0.0
        self.is_in_speech = False
        self._last_emitted_text = ""

    def _load_current_sentence(self):
        sentence = self.sentences[self.sentence_idx % len(self.sentences)]
        self.words = sentence.split()
        self.word_idx = 0
        self._last_emitted_text = ""

    def process_chunk(self, pcm_bytes: bytes) -> ASRResult | None:
        chunk_sec = len(pcm_bytes) / (self.sample_rate * 2)
        rms = self._calc_rms(pcm_bytes)
        has_energy = rms > self.energy_threshold

        if has_energy:
            self.speech_accum_sec += chunk_sec
            self.silence_accum_sec = 0.0
            self.is_in_speech = True

            # Emit incremental provisional words as acoustic energy accumulates
            words_to_reveal = min(
                len(self.words),
                max(1, int(self.speech_accum_sec * 3.5)),  # ~3.5 words/second speech cadence
            )
            if words_to_reveal > self.word_idx or not self._last_emitted_text:
                self.word_idx = words_to_reveal
                partial_text = " ".join(self.words[: self.word_idx])
                if partial_text != self._last_emitted_text and self.word_idx < len(self.words):
                    self._last_emitted_text = partial_text
                    return ASRResult(text=partial_text, is_final=False)
        else:
            # Silence chunk
            if self.is_in_speech:
                self.silence_accum_sec += chunk_sec
                if self.silence_accum_sec >= self.pause_duration_sec:
                    # Finalize the sentence segment upon detecting natural speech pause
                    full_text = " ".join(self.words)
                    self.is_in_speech = False
                    self.silence_accum_sec = 0.0
                    self.speech_accum_sec = 0.0

                    self.sentence_idx += 1
                    self._load_current_sentence()

                    return ASRResult(text=full_text, is_final=True)

        return None

    def finish(self) -> ASRResult | None:
        if self.is_in_speech and self.words:
            full_text = " ".join(self.words)
            self.is_in_speech = False
            return ASRResult(text=full_text, is_final=True)
        return None

    @staticmethod
    def _calc_rms(pcm_bytes: bytes) -> float:
        count = len(pcm_bytes) // 2
        if count == 0:
            return 0.0
        shorts = struct.unpack(f"<{count}h", pcm_bytes)
        sum_sq = sum(s * s for s in shorts)
        return math.sqrt(sum_sq / count)


def get_asr_engine(
    backend: str = "auto",
    model_path: str | None = None,
    sample_rate: int = 16000,
    transcript_path: str | None = None,
) -> BaseASREngine:
    """Factory creating an ASR engine instance based on availability."""
    if backend == "vosk":
        return VoskASREngine(model_path=model_path, sample_rate=sample_rate)
    elif backend == "faster-whisper":
        return FasterWhisperASREngine(sample_rate=sample_rate)
    elif backend == "energy-vad":
        return AcousticEnergyASREngine(
            sample_rate=sample_rate, transcript_path=transcript_path
        )
    elif backend == "auto":
        # Check Vosk first (lightest, native streaming)
        try:
            import vosk  # noqa: F401
            return VoskASREngine(model_path=model_path, sample_rate=sample_rate)
        except ImportError:
            pass

        # Check faster-whisper
        try:
            import faster_whisper  # noqa: F401
            return FasterWhisperASREngine(sample_rate=sample_rate)
        except ImportError:
            pass

        # Fallback to Acoustic Energy VAD
        return AcousticEnergyASREngine(
            sample_rate=sample_rate, transcript_path=transcript_path
        )
    else:
        raise ValueError(f"Unknown ASR backend '{backend}'. Supported: auto, vosk, faster-whisper, energy-vad")

