"""Timing-fit remediation (BACKLOG E2).

Three-rung escalation to guarantee each Chinese clip fits its segment window:
  ① char-budget re-translate  (translate-time, in stages/translate.py)
  ② TTS speed re-synth        (orchestrator below, wired in pipeline.py)
  ③ ffmpeg atempo exact fit   (orchestrator below)
Truncation is reserved for degenerate windows only.

This module holds the audio primitives now; the orchestrators are added next.
"""
from __future__ import annotations

import array
import logging
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path

from .models import Segment
from .timing import (
    atempo_factor,
    char_budget,
    clip_duration_ms,
    over_budget_segments,
    required_speed,
)

log = logging.getLogger(__name__)

FADE_OUT_MS = 30
_ATEMPO_MIN, _ATEMPO_MAX = 0.5, 2.0  # ffmpeg atempo per-filter practical range


@dataclass
class Report:
    """Counts of remediation actions across one pass."""

    retranslated: int = 0
    resynthed: int = 0
    atempoed: int = 0
    truncated: int = 0
    failed: int = 0

    def __str__(self) -> str:
        parts = []
        for name in ("retranslated", "resynthed", "atempoed", "truncated", "failed"):
            n = getattr(self, name)
            if n:
                parts.append(f"{name}={n}")
        return ", ".join(parts) or "no-op"


def truncate_wav(path: Path, window_ms: int, out_path: Path | None = None) -> Path:
    """Truncate a 16-bit wav to ``window_ms`` with a short linear fade-out.

    A window larger than the clip is a no-op (no fade applied). A non-positive
    window yields an empty clip. ``out_path`` defaults to ``path`` (in place).
    """
    out_path = out_path or path
    with wave.open(str(path), "rb") as w:
        params = w.getparams()
        framerate = w.getframerate()
        n_channels = w.getnchannels()
        total_frames = w.getnframes()
        frames = w.readframes(total_frames)
    samples = array.array("h", frames)

    target_frames = max(0, min(int(window_ms * framerate / 1000), total_frames))
    keep_samples = target_frames * n_channels
    truncated = samples[:keep_samples]

    # Fade the tail only when we actually shortened the clip.
    if 0 < target_frames < total_frames:
        fade = min(int(FADE_OUT_MS * framerate / 1000), target_frames)
        for i in range(fade):
            frac = 1.0 - (i / fade)
            base = (target_frames - fade + i) * n_channels
            for c in range(n_channels):
                truncated[base + c] = int(truncated[base + c] * frac)

    with wave.open(str(out_path), "wb") as w:
        w.setparams(params)
        w.writeframes(truncated.tobytes())
    return out_path


def _atempo_chain(factor: float) -> list[float]:
    """Split a tempo factor into ffmpeg-safe pieces (each within 0.5..2.0)."""
    pieces: list[float] = []
    f = factor
    while f > _ATEMPO_MAX:
        pieces.append(_ATEMPO_MAX)
        f /= _ATEMPO_MAX
    while f < _ATEMPO_MIN:
        pieces.append(_ATEMPO_MIN)
        f /= _ATEMPO_MIN
    pieces.append(f)
    return pieces


def atempo_fit(path: Path, target_ms: int, out_path: Path | None = None) -> Path:
    """Pitch-preserving time-compress a wav to ``target_ms`` via ffmpeg ``atempo``.

    ``out_path`` defaults to ``path`` (in place). If the clip already fits or is
    empty, it is returned unchanged.
    """
    out_path = out_path or path
    clip_ms = clip_duration_ms(path)
    if clip_ms <= 0 or target_ms <= 0:
        return out_path
    factor = clip_ms / target_ms
    if factor <= 1.0:
        return out_path  # already fits; not our job to lengthen

    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(path)]
    for piece in _atempo_chain(factor):
        cmd += ["-af", f"atempo={piece}"]
    cmd.append(str(out_path))
    subprocess.run(cmd, check=True)
    return out_path


# ----- Orchestrators -----


def remediate_translation(
    segments: list[Segment],
    max_chars_per_second: float,
    retranslate_fn,
) -> Report:
    """Rung ①: re-translate segments whose text_zh exceeds the char budget.

    Mutates ``text_zh`` in place. A failing retranslate for one segment is
    counted and skipped (rung ②③ will handle the residual at TTS time).
    """
    report = Report()
    for seg in over_budget_segments(segments, max_chars_per_second):
        budget = char_budget(seg.duration_sec, max_chars_per_second)
        try:
            new_text = retranslate_fn(seg, budget)
        except Exception as e:  # one bad segment must not abort the batch
            log.warning("retranslate seg %d failed: %s", seg.id, e)
            report.failed += 1
            continue
        seg.text_zh = new_text
        report.retranslated += 1
    return report


def remediate_clips(
    segments: list[Segment],
    tts_clips: dict[int, Path],
    current_speed: float,
    *,
    max_speed: float,
    tolerance_ms: int,
    min_window_ms: int,
    max_atempo: float,
    resynth_fn,
    fit_fn,
) -> Report:
    """Rung ②③: fit each clip into its segment window.

      ② if over the window, re-synth at min(required, max_speed); one attempt.
      ③ any residual overflow -> atempo exact fit, or truncate if the window is
        degenerate or the needed atempo factor exceeds ``max_atempo``.

    Guarantees: after this pass, every clip that existed fits its window (+tol),
    was truncated to it, or is reported as failed.
    """
    report = Report()
    for seg in segments:
        clip = tts_clips.get(seg.id)
        if clip is None or not clip.exists():
            continue
        window = seg.duration_ms
        clip_ms = clip_duration_ms(clip)
        if clip_ms <= window + tolerance_ms:
            continue  # already fits

        # ② speed re-synth (one attempt, capped)
        need = required_speed(current_speed, clip_ms, window)
        target_speed = min(need, max_speed)
        if target_speed > current_speed and seg.text_zh:
            try:
                resynth_fn(seg.id, seg.text_zh, target_speed, clip)
                report.resynthed += 1
                clip_ms = clip_duration_ms(clip)
            except Exception as e:
                log.warning("resynth seg %d failed: %s", seg.id, e)
                report.failed += 1

        # ③ exact fit of any residual
        if clip_ms > window + tolerance_ms:
            if window < min_window_ms or atempo_factor(clip_ms, window) > max_atempo:
                truncate_wav(clip, window, clip)
                report.truncated += 1
            else:
                fit_fn(clip, window, clip)
                report.atempoed += 1
    return report
