"""Tests for stages.extract — in particular the --sample truncation.

Uses real ffmpeg on a tiny generated source (fast), to confirm sample_seconds
limits the extracted audio so the whole pipeline processes a short slice.
"""
from __future__ import annotations

import subprocess
import wave

from dub.config import ExtractConfig
from dub.stages.extract import extract_audio


def _gen_wav(path, seconds=5, rate=44100, channels=2):
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", f"sine=frequency=440:sample_rate={rate}",
            "-t", str(seconds), "-ac", str(channels), str(path),
        ],
        check=True,
    )


def _duration(path):
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / w.getframerate()


def test_extract_truncates_to_sample_seconds(tmp_path):
    src = tmp_path / "src.wav"
    _gen_wav(src, seconds=5)
    extract_audio(src, ExtractConfig(), tmp_path, preferred_lang=None, sample_seconds=2)
    dur = _duration(tmp_path / "audio.wav")
    assert 1.8 < dur < 2.2  # ~2s, not the full 5s


def test_extract_full_when_no_sample(tmp_path):
    src = tmp_path / "src.wav"
    _gen_wav(src, seconds=5)
    extract_audio(src, ExtractConfig(), tmp_path, preferred_lang=None)
    dur = _duration(tmp_path / "audio.wav")
    assert 4.8 < dur < 5.2  # full 5s
