"""Data models shared across pipeline stages."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Segment:
    """One ASR / translation / TTS unit, anchored to a time range."""

    id: int
    text_src: str                       # original-language transcript
    text_zh: Optional[str] = None       # Chinese translation
    start_ms: int = 0
    end_ms: int = 0

    @property
    def duration_ms(self) -> int:
        return max(0, self.end_ms - self.start_ms)

    @property
    def duration_sec(self) -> float:
        return self.duration_ms / 1000.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "text_src": self.text_src,
            "text_zh": self.text_zh,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Segment:
        return cls(
            id=d["id"],
            text_src=d["text_src"],
            text_zh=d.get("text_zh"),
            start_ms=d.get("start_ms", 0),
            end_ms=d.get("end_ms", 0),
        )


@dataclass
class AudioTrack:
    """An audio file with basic metadata."""

    path: Path
    sample_rate: int = 48000
    channels: int = 2


@dataclass
class JobContext:
    """Mutable state passed through the pipeline for one input file."""

    input_path: Path
    work_dir: Path                       # per-input cache directory
    voice: str = "nature"

    audio: Optional[AudioTrack] = None   # extracted from container
    segments: list[Segment] = field(default_factory=list)
    tts_clips: dict[int, Path] = field(default_factory=dict)
    mixed_audio: Optional[Path] = None
    output_path: Optional[Path] = None
