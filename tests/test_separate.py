"""Tests for stages.separate.

The separation stage drives Demucs via subprocess; these tests mock the
subprocess layer and the demucs-availability probe so they run in the fast
lane (no torch/Gpu needed). One @pytest.mark.live smoke test exercises the real
Demucs install end-to-end.
"""
from __future__ import annotations

import struct
import wave
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from dub.config import SeparateConfig
from dub.stages import separate as separate_stage


def _write_wav(path: Path, seconds: float = 0.1, framerate: int = 44100, channels: int = 2) -> None:
    n = int(seconds * framerate) * channels
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(framerate)
        w.writeframes(struct.pack("<" + "h" * n, *([0] * n)))


def _fake_demucs_run(cmd, check=False, **kw):
    """Pretend to be demucs: emit <out>/<model>/<trackstem>/no_vocals.wav."""
    model = cmd[cmd.index("-n") + 1]
    out_dir = Path(cmd[cmd.index("-o") + 1])
    trackstem = Path(cmd[-1]).stem
    target = out_dir / model / trackstem / "no_vocals.wav"
    target.parent.mkdir(parents=True, exist_ok=True)
    _write_wav(target)
    return MagicMock(returncode=0)


def test_returns_accompaniment_when_demucs_succeeds(tmp_path, monkeypatch):
    monkeypatch.setattr(separate_stage, "_demucs_available", lambda: True)
    _write_wav(tmp_path / "audio_hq.wav")  # pre-create so ffmpeg extract is skipped
    monkeypatch.setattr(separate_stage.subprocess, "run", _fake_demucs_run)

    acc = separate_stage.separate(Path("dummy.mkv"), SeparateConfig(), tmp_path)

    assert acc == tmp_path / "accompaniment.wav"
    assert acc.exists()
    assert not (tmp_path / "demucs").exists()  # intermediate tree cleaned up


def test_cached_when_accompaniment_exists(tmp_path, monkeypatch):
    _write_wav(tmp_path / "accompaniment.wav")
    calls: list = []
    monkeypatch.setattr(separate_stage.subprocess, "run", lambda *a, **k: calls.append(a))

    acc = separate_stage.separate(Path("dummy.mkv"), SeparateConfig(), tmp_path)

    assert acc == tmp_path / "accompaniment.wav"
    assert not calls  # nothing executed


def test_falls_back_when_demucs_not_installed(tmp_path, monkeypatch):
    monkeypatch.setattr(separate_stage, "_demucs_available", lambda: False)
    _write_wav(tmp_path / "audio_hq.wav")
    monkeypatch.setattr(separate_stage.subprocess, "run", lambda *a, **k: None)

    acc = separate_stage.separate(Path("dummy.mkv"), SeparateConfig(), tmp_path)

    assert acc is None
    assert not (tmp_path / "accompaniment.wav").exists()


def test_falls_back_when_demucs_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(separate_stage, "_demucs_available", lambda: True)
    _write_wav(tmp_path / "audio_hq.wav")

    def boom(cmd, check=False, **kw):
        if "demucs" in cmd:
            raise separate_stage.subprocess.CalledProcessError(1, cmd)
        return MagicMock(returncode=0)

    monkeypatch.setattr(separate_stage.subprocess, "run", boom)

    acc = separate_stage.separate(Path("dummy.mkv"), SeparateConfig(), tmp_path)

    assert acc is None  # graceful fallback, no raise


def test_disabled_returns_none_without_running_demucs(tmp_path, monkeypatch):
    _write_wav(tmp_path / "audio_hq.wav")
    calls: list = []
    monkeypatch.setattr(separate_stage.subprocess, "run", lambda *a, **k: calls.append(a))

    acc = separate_stage.separate(Path("dummy.mkv"), SeparateConfig(enabled=False), tmp_path)

    assert acc is None
    assert not calls


@pytest.mark.live
def test_live_separate_runs_real_demucs(tmp_path):
    """End-to-end Demucs run; needs `pip install -e '.[sep]'` + an audio file.

    Point DUB_LIVE_AUDIO at any wav/mp4 to exercise the real path.
    """
    import os

    src = os.environ.get("DUB_LIVE_AUDIO")
    if not src or not separate_stage._demucs_available():
        pytest.skip("set DUB_LIVE_AUDIO=<file> and pip install -e '.[sep]'")
    acc = separate_stage.separate(Path(src), SeparateConfig(device="cuda"), tmp_path)
    assert acc is not None and acc.exists()
