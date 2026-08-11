"""Shared test helpers: config builders and synthetic-audio generation.

Pure functions (not fixtures) so tests can pass parameters directly.
"""
from __future__ import annotations

import struct
import wave
from pathlib import Path

from dub.config import AppConfig, VoicePreset


def make_voice(
    voice_id: str = "male-qn-qingse",
    speed: float = 0.95,
    vol: float = 1.0,
    pitch: int = 0,
    language_boost: str | None = None,
    emotion: str | None = None,
) -> VoicePreset:
    return VoicePreset(
        provider="minimax",
        voice_id=voice_id,
        speed=speed,
        vol=vol,
        pitch=pitch,
        language_boost=language_boost,
        emotion=emotion,
    )


def make_config(voices: dict[str, VoicePreset] | None = None) -> AppConfig:
    """An AppConfig with sane defaults; caller overrides voices for the test."""
    voices = voices or {"nature": make_voice()}
    return AppConfig(voices=voices)


def make_wav(
    path: Path, *, seconds: float, framerate: int = 24000, channels: int = 1
) -> Path:
    """Write a silent wav of an exact duration; returns its path.

    Used to test clip-duration measurement with known lengths, without pydub.
    """
    nframes = int(round(seconds * framerate))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)  # 16-bit PCM
        w.setframerate(framerate)
        w.writeframes(struct.pack("<" + "h" * (nframes * channels),
                                  *([0] * (nframes * channels))))
    return path
