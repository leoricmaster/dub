"""Stage: text-to-speech synthesis."""
from __future__ import annotations

from pathlib import Path

from ..config import EnvSettings, TTSConfig, VoicePreset
from ..models import Segment
from ..providers import minimax_tts


def tts(
    segments: list[Segment],
    voice: VoicePreset,
    cfg: TTSConfig,
    env: EnvSettings,
    work_dir: Path,
) -> dict[int, Path]:
    if voice.provider == "minimax":
        return minimax_tts.synthesize(segments, voice, cfg, env, work_dir)
    raise ValueError(f"unknown TTS provider: {voice.provider}")
