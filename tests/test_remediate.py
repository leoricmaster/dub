"""Tests for dub.remediate orchestrators (rung ①②③ decision logic).

Provider calls are injected (retranslate_fn / resynth_fn / fit_fn), so the full
escalation ladder is testable with no real API and no ffmpeg timing dependence.
"""
from __future__ import annotations

import math

from dub.models import Segment
from dub.remediate import remediate_clips, remediate_translation
from dub.timing import clip_duration_ms

from .helpers import make_wav


def _should_not_call(*a, **k):
    raise AssertionError("provider call not expected here")


def _clip(tmp_path, seg_id, ms, framerate=24000):
    return make_wav(tmp_path / f"{seg_id}.wav", seconds=ms / 1000, framerate=framerate)


# ----- remediate_translation (rung ①) -----


def test_translation_retranslates_over_budget_segment():
    # 1s window, max_cps 3.5 -> budget 4; 6-char text is over
    segs = [Segment(id=0, text_src=".", text_zh="你好你好你好", start_ms=0, end_ms=1000)]
    calls = []

    def retrans(seg, budget):
        calls.append((seg.id, budget))
        return "短"  # 1 char, fits

    rep = remediate_translation(segs, max_chars_per_second=3.5, retranslate_fn=retrans)
    assert segs[0].text_zh == "短"
    assert rep.retranslated == 1
    assert calls == [(0, 4)]  # budget passed correctly


def test_translation_leaves_fitting_segments_alone():
    segs = [Segment(id=0, text_src=".", text_zh="你好", start_ms=0, end_ms=1000)]  # 2 <= 4
    rep = remediate_translation(segs, 3.5, _should_not_call)
    assert segs[0].text_zh == "你好"
    assert rep.retranslated == 0


def test_translation_continues_past_failure():
    segs = [
        Segment(id=0, text_src=".", text_zh="你好你好你好", start_ms=0, end_ms=1000),
        Segment(id=1, text_src=".", text_zh="你好你好你好", start_ms=1000, end_ms=2000),
    ]

    def retrans(seg, budget):
        if seg.id == 0:
            raise RuntimeError("api down")
        return "短"

    rep = remediate_translation(segs, 3.5, retrans)
    assert rep.retranslated == 1
    assert rep.failed == 1
    assert segs[1].text_zh == "短"


# ----- remediate_clips (rung ②③) -----


def _run_clips(tmp_path, seg, clip_ms, *, voice_speed, resynth_fn, fit_fn,
               max_speed=1.2, tolerance_ms=50, min_window_ms=200, max_atempo=1.5):
    clips = {seg.id: _clip(tmp_path, seg.id, clip_ms)}
    rep = remediate_clips(
        [seg], clips, voice_speed,
        max_speed=max_speed, tolerance_ms=tolerance_ms,
        min_window_ms=min_window_ms, max_atempo=max_atempo,
        resynth_fn=resynth_fn, fit_fn=fit_fn,
    )
    return rep, clips


def test_clips_noop_when_fits(tmp_path):
    seg = Segment(id=0, text_src=".", text_zh="你好", start_ms=0, end_ms=2000)
    rep, _ = _run_clips(tmp_path, seg, 1500, voice_speed=1.0,
                        resynth_fn=_should_not_call, fit_fn=_should_not_call)
    assert rep.resynthed == rep.atempoed == rep.truncated == 0


def test_clips_resynth_when_required_speed_within_cap(tmp_path):
    # 1.6s clip in 1.5s window: required = 1.0*1600/1500 = 1.0667 <= 1.2
    seg = Segment(id=0, text_src=".", text_zh="你好", start_ms=0, end_ms=1500)
    seen = {}

    def resynth(seg_id, text, speed, out):
        seen["speed"] = speed
        return make_wav(out, seconds=1.4)  # fits now

    rep, _ = _run_clips(tmp_path, seg, 1600, voice_speed=1.0,
                        resynth_fn=resynth, fit_fn=_should_not_call)
    assert rep.resynthed == 1 and rep.atempoed == 0
    assert math.isclose(seen["speed"], 1600 / 1500, rel_tol=1e-6)


def test_clips_atempo_for_residual_after_cap_resynth(tmp_path):
    # 2s clip in 1s window: required=2.0 > cap 1.2 -> resynth at 1.2, still over -> atempo
    seg = Segment(id=0, text_src=".", text_zh="你好", start_ms=0, end_ms=1000)
    fit_targets = []

    def resynth(seg_id, text, speed, out):
        return make_wav(out, seconds=1.5)  # still over 1s window

    def fit(path, target, out):
        fit_targets.append(target)
        return make_wav(out, seconds=1.0)

    rep, _ = _run_clips(tmp_path, seg, 2000, voice_speed=1.0,
                        resynth_fn=resynth, fit_fn=fit)
    assert rep.resynthed == 1 and rep.atempoed == 1
    assert fit_targets == [1000]


def test_clips_truncate_degenerate_window(tmp_path):
    # 100ms window < min_window 200 -> truncate (after a resynth attempt)
    seg = Segment(id=0, text_src=".", text_zh="你好", start_ms=0, end_ms=100)
    rep, clips = _run_clips(
        tmp_path, seg, 1000, voice_speed=1.0,
        resynth_fn=lambda i, t, s, out: make_wav(out, seconds=0.9),
        fit_fn=_should_not_call,
    )
    assert rep.truncated == 1
    assert clip_duration_ms(clips[0]) == 100


def test_clips_truncate_when_atempo_factor_exceeds_max(tmp_path):
    # 1s window (>= min_window), resynth at cap still leaves atempo factor 1.8 > 1.5
    seg = Segment(id=0, text_src=".", text_zh="你好", start_ms=0, end_ms=1000)
    rep, clips = _run_clips(
        tmp_path, seg, 2000, voice_speed=1.0,
        resynth_fn=lambda i, t, s, out: make_wav(out, seconds=1.8),
        fit_fn=_should_not_call,
    )
    assert rep.truncated == 1
    assert clip_duration_ms(clips[0]) == 1000


def test_clips_resynth_failure_falls_through_to_atempo(tmp_path):
    seg = Segment(id=0, text_src=".", text_zh="你好", start_ms=0, end_ms=1000)

    def resynth(*a):
        raise RuntimeError("api")

    def fit(path, target, out):
        return make_wav(out, seconds=1.0)

    rep, _ = _run_clips(tmp_path, seg, 1500, voice_speed=1.0,
                        resynth_fn=resynth, fit_fn=fit)
    assert rep.failed == 1 and rep.atempoed == 1


def test_clips_skips_segment_without_clip(tmp_path):
    seg = Segment(id=0, text_src=".", text_zh="你好", start_ms=0, end_ms=1000)
    rep = remediate_clips(
        [seg], {}, 1.0, max_speed=1.2, tolerance_ms=50,
        min_window_ms=200, max_atempo=1.5,
        resynth_fn=_should_not_call, fit_fn=_should_not_call,
    )
    assert rep.resynthed == rep.atempoed == rep.truncated == 0
