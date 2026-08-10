"""Regression tests for stages.mix.

Locks the cross-frame-rate overlay behavior: extract outputs 16k mono while
MiniMax TTS outputs 24k, so mix_audio overlays 24k clips onto a 16k base.
pydub's overlay handles this via internal _sync (resamples to max frame_rate),
but that correctness is not obvious from the code and relies on pydub behavior.
These tests pin it so a refactor or pydub upgrade that breaks it is caught.
"""
from __future__ import annotations

import array
import math
import struct
import wave

from dub.config import MixConfig
from dub.models import AudioTrack, Segment
from dub.stages.mix import mix_audio


def _tone_wav(path, seconds, freq, framerate, amp=12000):
    """Write a pure-tone wav (used as a stand-in for narration / background)."""
    n = int(seconds * framerate)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(framerate)
        w.writeframes(
            struct_pack_tone(n, freq, framerate, amp)
        )
    return path


def struct_pack_tone(n, freq, framerate, amp):
    return struct.pack(
        "<" + "h" * n,
        *[int(amp * math.sin(2 * math.pi * freq * i / framerate)) for i in range(n)],
    )


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


def test_mix_preserves_pitch_across_mismatched_frame_rates(tmp_path):
    """16k base + 24k clip: neither the clip nor the base must change pitch."""
    base = _tone_wav(tmp_path / "base.wav", 3.0, freq=220, framerate=16000)
    clip = _tone_wav(tmp_path / "clip.wav", 1.0, freq=880, framerate=24000)

    audio = AudioTrack(path=base, sample_rate=16000, channels=1)
    seg = Segment(id=0, text_src=".", start_ms=500, end_ms=1500)
    cfg = MixConfig(bg_attenuation_db=-12, sample_rate=48000)

    out = mix_audio(audio, [seg], {0: clip}, cfg, tmp_path)
    fr, s = _read_samples(out)

    # Clip window [500,1500]ms: the 880Hz clip must dominate (louder than the
    # -12dB-attenuated 220Hz base underneath).
    assert _dominant(s[int(0.6 * fr):int(1.4 * fr)], fr, [220, 880]) == 880
    # Base-only window [1600,2400]ms: the 220Hz base must be intact, uncorrupted.
    assert _dominant(s[int(1.6 * fr):int(2.4 * fr)], fr, [220, 880]) == 220


def test_mix_clip_lands_at_segment_start(tmp_path):
    """The overlaid clip must begin at seg.start_ms, not be shifted by the rate gap."""
    base = _tone_wav(tmp_path / "base.wav", 3.0, freq=220, framerate=16000)
    clip = _tone_wav(tmp_path / "clip.wav", 0.5, freq=880, framerate=24000)

    audio = AudioTrack(path=base, sample_rate=16000, channels=1)
    seg = Segment(id=0, text_src=".", start_ms=1000, end_ms=1500)
    out = mix_audio(audio, [seg], {0: clip}, MixConfig(bg_attenuation_db=-12), tmp_path)
    fr, s = _read_samples(out)

    def rms(a, b):
        w = s[int(a * fr / 1000):int(b * fr / 1000)]
        return int((sum(x * x for x in w) / max(1, len(w))) ** 0.5)

    assert rms(0, 900) < rms(1000, 1400)   # silent before clip, loud during
    assert rms(1600, 2500) < rms(1000, 1400)  # silent after clip
