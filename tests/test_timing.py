"""Tests for dub.timing: TTS-clip vs segment-window alignment.

A clip longer than its segment window spills into the next segment →
overlapping Chinese narration, the #1 intelligibility bug. These checks
turn that silent failure into a measurable, reportable one.
"""
from __future__ import annotations

from dub.models import Segment
from dub.timing import (
    Overflow,
    check_alignment,
    clip_duration_ms,
    fits_segment_window,
    summarize,
)

from .helpers import make_wav

# ----- clip_duration_ms: stdlib-wave measurement, exact lengths -----


def test_clip_duration_ms_one_second(tmp_path):
    p = make_wav(tmp_path / "c.wav", seconds=1.0, framerate=24000)
    assert clip_duration_ms(p) == 1000


def test_clip_duration_ms_half_second(tmp_path):
    p = make_wav(tmp_path / "c.wav", seconds=0.5, framerate=16000)
    assert clip_duration_ms(p) == 500


def test_clip_duration_ms_independent_of_framerate(tmp_path):
    """1s is 1000ms whether the file is 16k or 24k."""
    a = make_wav(tmp_path / "a.wav", seconds=1.0, framerate=16000)
    b = make_wav(tmp_path / "b.wav", seconds=1.0, framerate=24000)
    assert clip_duration_ms(a) == clip_duration_ms(b) == 1000


# ----- fits_segment_window: the core budget assertion -----


def test_fits_segment_window_shorter_clip_ok():
    seg = Segment(id=0, text_src="x", start_ms=0, end_ms=2000)
    assert fits_segment_window(seg, 1800) is True


def test_fits_segment_window_exact_fit_ok():
    seg = Segment(id=0, text_src="x", start_ms=0, end_ms=2000)
    assert fits_segment_window(seg, 2000) is True


def test_fits_segment_window_one_ms_overflow_rejected():
    seg = Segment(id=0, text_src="x", start_ms=0, end_ms=2000)
    assert fits_segment_window(seg, 2001) is False


def test_fits_segment_window_zero_duration_segment():
    """A degenerate segment (start==end) fits only a zero-length clip."""
    seg = Segment(id=0, text_src="x", start_ms=500, end_ms=500)
    assert fits_segment_window(seg, 0) is True
    assert fits_segment_window(seg, 1) is False


# ----- check_alignment: end-to-end over many segments/clips -----


def test_check_alignment_reports_only_overflowing(tmp_path):
    segs = [
        Segment(id=0, text_src="a", start_ms=0, end_ms=2000),
        Segment(id=1, text_src="b", start_ms=2000, end_ms=4000),
    ]
    clips = {
        0: make_wav(tmp_path / "0.wav", seconds=1.5),  # fits
        1: make_wav(tmp_path / "1.wav", seconds=2.5),  # overflows by 0.5s
    }
    overflows = check_alignment(segs, clips)
    assert [o.id for o in overflows] == [1]
    assert overflows[0] == Overflow(id=1, clip_ms=2500, segment_ms=2000, overflow_ms=500)


def test_check_alignment_ignores_missing_clips(tmp_path):
    segs = [Segment(id=0, text_src="a", start_ms=0, end_ms=1000)]
    assert check_alignment(segs, {}) == []


def test_check_alignment_ignores_nonexistent_clip_path(tmp_path):
    segs = [Segment(id=0, text_src="a", start_ms=0, end_ms=500)]
    clips = {0: tmp_path / "missing.wav"}
    assert check_alignment(segs, clips) == []


def test_check_alignment_all_clean_returns_empty(tmp_path):
    segs = [Segment(id=0, text_src="a", start_ms=0, end_ms=2000)]
    clips = {0: make_wav(tmp_path / "0.wav", seconds=1.0)}
    assert check_alignment(segs, clips) == []


# ----- summarize: the report formatter the pipeline logs -----


def test_summarize_clean_says_ok():
    assert "OK" in summarize([])


def test_summarize_reports_count_and_worst():
    ovs = [
        Overflow(id=1, clip_ms=2500, segment_ms=2000, overflow_ms=500),
        Overflow(id=3, clip_ms=3000, segment_ms=2000, overflow_ms=1000),
    ]
    msg = summarize(ovs)
    assert "2" in msg          # count of overflowing clips
    assert "+1000" in msg      # worst overflow


def test_summarize_truncates_after_ten_overflows():
    """More than 10 overflows collapses the tail to '... and N more'."""
    ovs = [
        Overflow(id=i, clip_ms=2001, segment_ms=2000, overflow_ms=1)
        for i in range(12)
    ]
    msg = summarize(ovs)
    assert "... and 2 more" in msg
    # only the first 10 get an individual line (seg 0..9)
    assert msg.count("seg ") == 10
