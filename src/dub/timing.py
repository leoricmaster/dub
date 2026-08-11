"""Timing-alignment checks: TTS clips must fit their segment windows.

A clip longer than its segment window spills into the next segment, producing
overlapping Chinese narration — the #1 intelligibility bug in the dub output.
These functions measure clip durations via the stdlib ``wave`` module (no pydub
dependency) and report overflows, so the pipeline can warn now (P1.5) and
auto-remediate later (BACKLOG E2: re-synth with higher speed, then re-prompt,
then stretch).
"""
from __future__ import annotations

import math
import wave
from dataclasses import dataclass
from pathlib import Path

from .models import Segment


def clip_duration_ms(path: Path) -> int:
    """Duration of a wav file in milliseconds (stdlib wave; no pydub)."""
    with wave.open(str(path), "rb") as w:
        return int(round(w.getnframes() / w.getframerate() * 1000))


def fits_segment_window(seg: Segment, clip_ms: int) -> bool:
    """True when a clip of ``clip_ms`` fits within the segment's time window."""
    return clip_ms <= seg.duration_ms


# ----- Budget / speed math for E2 timing-fit remediation -----


def char_budget(duration_sec: float, max_chars_per_second: float) -> int:
    """Max Chinese characters allowed for a segment of this duration."""
    return math.ceil(duration_sec * max_chars_per_second)


def fits_char_budget(
    text: str, duration_sec: float, max_chars_per_second: float
) -> bool:
    return len(text) <= char_budget(duration_sec, max_chars_per_second)


def over_budget_segments(
    segments: list[Segment], max_chars_per_second: float
) -> list[Segment]:
    """Segments whose ``text_zh`` exceeds the char budget (rung ① candidates)."""
    return [
        s
        for s in segments
        if s.text_zh and len(s.text_zh) > char_budget(s.duration_sec, max_chars_per_second)
    ]


def required_speed(current_speed: float, clip_ms: int, window_ms: int) -> float:
    """TTS speed so a clip of ``clip_ms`` fits ``window_ms`` (duration ~ 1/speed).

    Returns inf for a non-positive window (cannot be fit by speeding up).
    """
    if window_ms <= 0:
        return math.inf
    return current_speed * clip_ms / window_ms


def atempo_factor(clip_ms: int, window_ms: int) -> float:
    """ffmpeg ``atempo`` factor to compress ``clip_ms`` into ``window_ms`` (>1 = faster).

    Returns inf for a non-positive window.
    """
    if window_ms <= 0:
        return math.inf
    return clip_ms / window_ms


@dataclass
class Overflow:
    """A clip that exceeds its segment window."""

    id: int            # segment id
    clip_ms: int       # measured clip duration
    segment_ms: int    # segment window duration
    overflow_ms: int   # clip_ms - segment_ms


def check_alignment(
    segments: list[Segment], tts_clips: dict[int, Path]
) -> list[Overflow]:
    """Return one ``Overflow`` per segment whose TTS clip exceeds its window.

    Segments without an existing clip on disk are ignored (missing clips are a
    separate concern handled in the TTS stage).
    """
    overflows: list[Overflow] = []
    for seg in segments:
        clip = tts_clips.get(seg.id)
        if clip is None or not clip.exists():
            continue
        clip_ms = clip_duration_ms(clip)
        if clip_ms > seg.duration_ms:
            overflows.append(
                Overflow(seg.id, clip_ms, seg.duration_ms, clip_ms - seg.duration_ms)
            )
    return overflows


def summarize(overflows: list[Overflow]) -> str:
    """Human-readable alignment report for pipeline logging."""
    if not overflows:
        return "timing OK: all clips fit their segment windows"
    worst = max(o.overflow_ms for o in overflows)
    total = sum(o.overflow_ms for o in overflows)
    lines = [
        f"timing OVERFLOW: {len(overflows)} clip(s) exceed their segment window "
        f"(worst +{worst}ms, total +{total}ms) — Chinese will overlap adjacent segments"
    ]
    for o in overflows[:10]:
        lines.append(
            f"  seg {o.id}: clip {o.clip_ms}ms > window {o.segment_ms}ms (+{o.overflow_ms}ms)"
        )
    if len(overflows) > 10:
        lines.append(f"  ... and {len(overflows) - 10} more")
    return "\n".join(lines)
