"""Tests for dub.timing budget/speed math (rung ①②③ of E2).

Pure functions only — no audio, no API. These underpin:
  ① char_budget      — translate-time length gate
  ② required_speed   — TTS speed to fit a clip into its window
  ③ atempo_factor    — ffmpeg compression factor for exact fit
"""
from __future__ import annotations

import math

from dub.models import Segment
from dub.timing import (
    atempo_factor,
    char_budget,
    fits_char_budget,
    over_budget_segments,
    required_speed,
)

# ----- char_budget / fits_char_budget (rung ①) -----


def test_char_budget_rounds_up():
    assert char_budget(1.0, 3.5) == 4      # ceil(3.5)
    assert char_budget(2.0, 3.5) == 7      # ceil(7.0)
    assert char_budget(0.3, 3.5) == 2      # ceil(1.05)
    assert char_budget(0.0, 3.5) == 0


def test_fits_char_budget():
    assert fits_char_budget("你好", 1.0, 3.5) is True          # 2 ≤ 4
    assert fits_char_budget("你好你好你好", 1.0, 3.5) is False   # 6 > 4
    assert fits_char_budget("", 1.0, 3.5) is True


def test_over_budget_segments_returns_only_offenders():
    segs = [
        Segment(id=0, text_src=".", text_zh="你好", start_ms=0, end_ms=1000),         # 2 ≤ 4 ok
        Segment(id=1, text_src=".", text_zh="你好你好你好你好", start_ms=1000, end_ms=2000),  # 8 > 4 over
        Segment(id=2, text_src=".", text_zh=None, start_ms=2000, end_ms=3000),       # no text, skipped
        Segment(id=3, text_src=".", text_zh="", start_ms=3000, end_ms=4000),         # empty, skipped
    ]
    over = over_budget_segments(segs, 3.5)
    assert [s.id for s in over] == [1]


# ----- required_speed (rung ②) -----


def test_required_speed_proportional():
    assert required_speed(1.0, 2000, 1000) == 2.0
    assert math.isclose(required_speed(0.95, 2000, 1500), 0.95 * 2000 / 1500)
    assert required_speed(1.0, 1000, 1000) == 1.0   # exact fit


def test_required_speed_zero_window_is_inf():
    """A zero-length window can never be fit by speeding up."""
    assert math.isinf(required_speed(1.0, 1000, 0))


# ----- atempo_factor (rung ③) -----


def test_atempo_factor():
    assert atempo_factor(2000, 1000) == 2.0   # compress 2s into 1s
    assert atempo_factor(1000, 1000) == 1.0   # no change


def test_atempo_factor_zero_window_is_inf():
    assert math.isinf(atempo_factor(1000, 0))
