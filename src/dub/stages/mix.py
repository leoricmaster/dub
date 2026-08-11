"""Stage: mix Chinese TTS clips over the original bed.

Two modes:

- ``accompaniment`` (default, after the separate stage): the bed is Demucs's
  no-vocals accompaniment — music/SFX with the English narration already
  removed. Each Chinese clip's window is dipped by ``duck_db`` so the bed
  recedes under the narration and swells between lines (documentary feel).
- ``attenuate`` (fallback when separation is unavailable): the whole original
  is lowered by ``bg_attenuation_db`` and clips are overlaid. The English
  remains faintly audible — the documented P1 trade-off.

In both modes the bed is the high-quality ``audio_hq.wav`` / accompaniment
rather than the 16k mono ASR extract, so music/SFX stay crisp.
"""
from __future__ import annotations

from pathlib import Path

from pydub import AudioSegment

from ..config import MixConfig
from ..models import Segment

# mode: which bed to expect and how to treat clip windows
MODE_ACCOMPANIMENT = "accompaniment"
MODE_ATTENUATE = "attenuate"


def mix_audio(
    base_path: Path,
    segments: list[Segment],
    tts_clips: dict[int, Path],
    cfg: MixConfig,
    work_dir: Path,
    *,
    mode: str = MODE_ACCOMPANIMENT,
) -> Path:
    """Overlay Chinese TTS clips over the bed; returns the mixed wav path."""
    base = AudioSegment.from_wav(base_path)

    if mode == MODE_ATTENUATE:
        base = base + cfg.bg_attenuation_db
        extra_duck_db = 0.0  # whole track already attenuated uniformly
    else:
        extra_duck_db = cfg.duck_db  # dip the bed under each clip only

    for seg in segments:
        clip_path = tts_clips.get(seg.id)
        if clip_path is None or not clip_path.exists():
            continue
        clip = AudioSegment.from_wav(clip_path)
        start = seg.start_ms
        end = min(start + len(clip), len(base))
        if end <= start:
            continue

        # Mix the clip onto just its small window (cheap), then splice back.
        # Cross-frame-rate overlay (24k clip onto 44.1k/48k bed) is handled by
        # pydub's internal _sync — pinned by tests/test_mix.py.
        window = base[start:end] + extra_duck_db
        window = window.overlay(clip, position=0)
        base = base[:start] + window + base[end:]

    base = base.set_frame_rate(cfg.sample_rate)
    out_path = work_dir / "zh_audio.wav"
    base.export(out_path, format="wav")
    return out_path
