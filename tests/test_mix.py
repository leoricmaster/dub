"""Regression tests for stages.mix.

Covers the two mix modes:

- ``accompaniment``: the bed is dipped by ``duck_db`` only under each Chinese
  clip's window; the bed stays full-volume between clips. Cross-frame-rate
  overlay (24k MiniMax clip onto a 44.1k/48k bed) must still land at the right
  position without pitch shift — pydub's ``_sync`` handles it, but that
  correctness is non-obvious and is pinned here.
- ``attenuate`` (fallback): the whole bed is lowered uniformly by
  ``bg_attenuation_db`` and clips are overlaid.
"""
from __future__ import annotations

import array
import math
import struct
import wave

from dub.config import MixConfig
from dub.models import Segment
from dub.stages.mix import MODE_ACCOMPANIMENT, MODE_ATTENUATE, mix_audio


def _tone_wav(path, seconds, freq, framerate, amp=12000):
    """Write a pure-tone wav (stand-in for narration / bed). amp=0 -> silence."""
    n = int(seconds * framerate)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(framerate)
        w.writeframes(
            struct.pack(
                "<" + "h" * n,
                *[int(amp * math.sin(2 * math.pi * freq * i / framerate)) for i in range(n)],
            )
        )
    return path


def _power_at(samples, fr, freq):
    """Phase-independent spectral power at `freq` (Goertzel-style)."""
    cos_acc = sin_acc = 0.0
    w = 2 * math.pi * freq / fr
    for i, s in enumerate(samples):
        ph = w * i
        cos_acc += s * math.cos(ph)
        sin_acc += s * math.sin(ph)
    return math.hypot(cos_acc, sin_acc) / len(samples)


def _dominant(samples, fr, candidates):
    return max(candidates, key=lambda f: _power_at(samples, fr, f))


def _read_samples(path):
    with wave.open(str(path), "rb") as w:
        return w.getframerate(), array.array("h", w.readframes(w.getnframes()))


def _rms(samples):
    m = max(1, len(samples))
    return (sum(x * x for x in samples) / m) ** 0.5


# --------------------------------------------------------------------------- #
# accompaniment mode                                                          #
# --------------------------------------------------------------------------- #

def test_accompaniment_overlay_dominates_in_clip_window(tmp_path):
    """44.1k bed + 24k clip: clip dominates its window, bed intact after."""
    base = _tone_wav(tmp_path / "base.wav", 3.0, freq=220, framerate=44100, amp=12000)
    clip = _tone_wav(tmp_path / "clip.wav", 1.0, freq=880, framerate=24000, amp=24000)

    seg = Segment(id=0, text_src=".", start_ms=500, end_ms=1500)
    cfg = MixConfig(duck_db=-4, sample_rate=44100)

    out = mix_audio(base, [seg], {0: clip}, cfg, tmp_path, mode=MODE_ACCOMPANIMENT)
    fr, s = _read_samples(out)

    # Clip window [500,1500]ms: the 880Hz clip must dominate the ducked 220Hz bed.
    assert _dominant(s[int(0.6 * fr):int(1.4 * fr)], fr, [220, 880]) == 880
    # Bed-only window [1600,2400]ms: the 220Hz bed is intact (full volume here).
    assert _dominant(s[int(1.6 * fr):int(2.4 * fr)], fr, [220, 880]) == 220


def test_accompaniment_clip_lands_at_segment_start(tmp_path):
    """The overlaid clip must begin at seg.start_ms, not shifted by the rate gap."""
    base = _tone_wav(tmp_path / "base.wav", 3.0, freq=220, framerate=44100)
    clip = _tone_wav(tmp_path / "clip.wav", 0.5, freq=880, framerate=24000, amp=24000)

    seg = Segment(id=0, text_src=".", start_ms=1000, end_ms=1500)
    out = mix_audio(
        base, [seg], {0: clip}, MixConfig(duck_db=-4), tmp_path, mode=MODE_ACCOMPANIMENT
    )
    fr, s = _read_samples(out)

    assert _rms(s[int(0 * fr / 1000):int(900 * fr / 1000)]) < _rms(
        s[int(1000 * fr / 1000):int(1400 * fr / 1000)]
    )  # quiet before clip, loud during


def test_accompaniment_ducks_bed_by_duck_db(tmp_path):
    """Under a (silent) clip, the bed must drop by ~duck_db; outside, full volume."""
    amp = 16000
    base = _tone_wav(tmp_path / "base.wav", 3.0, freq=220, framerate=44100, amp=amp)
    silent = _tone_wav(tmp_path / "clip.wav", 1.0, freq=880, framerate=24000, amp=0)

    seg = Segment(id=0, text_src=".", start_ms=1000, end_ms=2000)
    duck_db = -6.0
    cfg = MixConfig(duck_db=duck_db, sample_rate=44100)

    out = mix_audio(base, [seg], {0: silent}, cfg, tmp_path, mode=MODE_ACCOMPANIMENT)
    fr, s = _read_samples(out)

    inside = _rms(s[int(1200 * fr / 1000):int(1800 * fr / 1000)])
    outside = _rms(s[int(2100 * fr / 1000):int(2700 * fr / 1000)])

    ratio = inside / outside
    expected = 10 ** (duck_db / 20.0)
    assert abs(ratio - expected) < 0.06  # bed dipped ~duck_db, nowhere else


# --------------------------------------------------------------------------- #
# attenuate mode (fallback)                                                   #
# --------------------------------------------------------------------------- #

def test_attenuate_lowers_whole_bed_uniformly(tmp_path):
    """Fallback: whole bed attenuated by bg_attenuation_db; no extra ducking."""
    amp = 16000
    base = _tone_wav(tmp_path / "base.wav", 3.0, freq=220, framerate=44100, amp=amp)
    silent = _tone_wav(tmp_path / "clip.wav", 1.0, freq=880, framerate=24000, amp=0)

    seg = Segment(id=0, text_src=".", start_ms=1000, end_ms=2000)
    bg_db = -12.0
    cfg = MixConfig(bg_attenuation_db=bg_db, sample_rate=44100)

    out = mix_audio(base, [seg], {0: silent}, cfg, tmp_path, mode=MODE_ATTENUATE)
    fr, s = _read_samples(out)

    inside = _rms(s[int(1200 * fr / 1000):int(1800 * fr / 1000)])
    outside = _rms(s[int(2100 * fr / 1000):int(2700 * fr / 1000)])
    raw = _rms(_read_samples(base)[1])  # unattenuated original

    assert abs(inside / outside - 1.0) < 0.05            # uniform, no ducking
    assert abs(inside / raw - 10 ** (bg_db / 20.0)) < 0.06  # lowered ~bg_attenuation_db
