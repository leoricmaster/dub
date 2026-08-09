"""Stage: speech-to-text transcription."""
from __future__ import annotations

from pathlib import Path

from ..config import ASRConfig, EnvSettings
from ..models import AudioTrack, Segment
from ..providers import dashscope_asr


def transcribe(
    audio: AudioTrack,
    cfg: ASRConfig,
    env: EnvSettings,
    work_dir: Path,
) -> list[Segment]:
    if cfg.provider == "dashscope":
        return dashscope_asr.transcribe(audio.path, cfg, env, work_dir)
    raise ValueError(f"unknown ASR provider: {cfg.provider}")
