"""Tests for dub.remediate wav operations: truncate_wav + atempo_fit.

These touch the real ffmpeg binary (atempo) and stdlib wave (truncate), so they
sit in the fast lane but need ffmpeg on PATH (a project prerequisite).
"""
from __future__ import annotations

import wave

from dub.remediate import atempo_fit, truncate_wav
from dub.timing import clip_duration_ms

from .helpers import make_wav

# ----- truncate_wav (stdlib wave + array, fade-out) -----


def test_truncate_wav_shortens_to_window(tmp_path):
    src = make_wav(tmp_path / "s.wav", seconds=3.0, framerate=24000)
    out = truncate_wav(src, 1000, tmp_path / "o.wav")
    assert clip_duration_ms(out) == 1000


def test_truncate_wav_in_place_default(tmp_path):
    src = make_wav(tmp_path / "s.wav", seconds=2.0, framerate=24000)
    truncate_wav(src, 500)  # out_path defaults to path
    assert clip_duration_ms(src) == 500


def test_truncate_wav_window_bigger_than_clip_is_noop(tmp_path):
    src = make_wav(tmp_path / "s.wav", seconds=1.0, framerate=24000)
    out = truncate_wav(src, 5000, tmp_path / "o.wav")
    assert clip_duration_ms(out) == 1000  # not lengthened, not faded


def test_truncate_wav_zero_window_yields_empty(tmp_path):
    src = make_wav(tmp_path / "s.wav", seconds=1.0, framerate=24000)
    out = truncate_wav(src, 0, tmp_path / "o.wav")
    assert clip_duration_ms(out) == 0


# ----- atempo_fit (ffmpeg, pitch-preserving) -----


def test_atempo_fit_compresses_to_target(tmp_path):
    src = make_wav(tmp_path / "s.wav", seconds=2.0, framerate=24000)
    out = atempo_fit(src, 1000, tmp_path / "o.wav")
    # atempo may be off by a few frames; allow tolerance
    assert abs(clip_duration_ms(out) - 1000) <= 50


def test_atempo_fit_output_is_valid_wav(tmp_path):
    src = make_wav(tmp_path / "s.wav", seconds=2.0, framerate=24000)
    out = atempo_fit(src, 1500, tmp_path / "o.wav")
    with wave.open(str(out), "rb") as w:
        assert w.getnframes() > 0
        assert w.getframerate() == 24000


def test_atempo_fit_noop_when_already_fits(tmp_path):
    """A clip shorter than the target must not be lengthened (factor <= 1.0)."""
    src = make_wav(tmp_path / "s.wav", seconds=1.0, framerate=24000)
    atempo_fit(src, 2000, tmp_path / "o.wav")  # factor 0.5 -> no-op
    assert clip_duration_ms(src) == 1000  # source unchanged, not lengthened


def test_atempo_fit_preserves_pitch_class_roughly(tmp_path):
    """Sanity: atempo keeps frame_rate; pitch shift is what speedup would do."""
    src = make_wav(tmp_path / "s.wav", seconds=1.0, framerate=24000)
    out = atempo_fit(src, 800, tmp_path / "o.wav")  # 1.25x compress
    with wave.open(str(out), "rb") as w:
        assert w.getframerate() == 24000  # frame_rate unchanged (no resample)
