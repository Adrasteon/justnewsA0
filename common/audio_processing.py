"""
Audio Transcription Service (Faster-Whisper)

Provides enterprise-grade, GPU-accelerated audio transcription capabilities.
Designed to be traceable and integrate with the FactChecker/Investigator pipeline.

Implementation:
- Uses `faster-whisper` (CTranslate2 backend) for high performance.
- Supports CUDA acceleration with potential for Int8 quantization.
- Returns timestamped segments suitable for cross-referencing with video frames.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

import torch

try:
    from faster_whisper import WhisperModel
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False

logger = logging.getLogger(__name__)

@dataclass
class TranscriptionConfig:
    model_size: str = "distil-large-v3" # or "large-v3" for max accuracy
    device: str = "auto"
    compute_type: str = "float16" # or "int8"
    beam_size: int = 5
    language: str = "en" # Start with English, can be None for auto-detect

class AudioTranscriber:
    def __init__(self, config: TranscriptionConfig | None = None):
        self.config = config or TranscriptionConfig()
        if not WHISPER_AVAILABLE:
            logger.warning("faster-whisper not installed. AudioTranscriber will fail.")
            self.model = None
        else:
            self.model = None

    def _load_model(self):
        """Lazy load the Whisper model."""
        if self.model:
            return

        device = self.config.device
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"

        logger.info(f"🎤 Loading Whisper model ({self.config.model_size}) on {device}...")
        try:
            self.model = WhisperModel(
                self.config.model_size,
                device=device,
                compute_type=self.config.compute_type
            )
        except Exception as e:
            logger.error(f"Failed to load Whisper model: {e}")
            raise

    def transcribe(self, audio_path: str) -> dict[str, Any]:
        """
        Transcribe an audio file.
        
        Args:
            audio_path: Path to the audio file.
            
        Returns:
            Dict containing full text and segments.
        """
        if not WHISPER_AVAILABLE:
            return {"error": "Whisper not available"}

        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        self._load_model()

        logger.info(f"🎤 Transcribing: {audio_path}")
        segments, info = self.model.transcribe(
            audio_path,
            beam_size=self.config.beam_size,
            language=self.config.language
        )

        # Segments is a generator, consume it
        results = []
        full_text = []

        for segment in segments:
            results.append({
                "start": segment.start,
                "end": segment.end,
                "text": segment.text
            })
            full_text.append(segment.text)

        return {
            "text": " ".join(full_text),
            "segments": results,
            "language": info.language,
            "duration": info.duration
        }

    def unload(self):
        """Unload model to free VRAM."""
        if self.model:
            del self.model
            self.model = None
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
