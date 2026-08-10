"""Regression tests for models.Segment.

Segment crosses the cache boundary (written to segments_en/zh.json and read
back on resume), so its serialization and duration math must be rock-solid.
"""
from __future__ import annotations

from dub.models import Segment


def test_duration_properties():
    s = Segment(id=0, text_src="x", start_ms=1000, end_ms=2500)
    assert s.duration_ms == 1500
    assert s.duration_sec == 1.5


def test_negative_duration_clamped_to_zero():
    """end < start must not produce a negative window (guard against bad timestamps)."""
    s = Segment(id=0, text_src="x", start_ms=2000, end_ms=1000)
    assert s.duration_ms == 0
    assert s.duration_sec == 0.0


def test_round_trip_preserves_all_fields():
    s = Segment(id=3, text_src="hello", text_zh="你好", start_ms=100, end_ms=900)
    assert Segment.from_dict(s.to_dict()) == s


def test_round_trip_preserves_none_zh():
    s = Segment(id=1, text_src="hello", text_zh=None, start_ms=0, end_ms=500)
    assert Segment.from_dict(s.to_dict()) == s


def test_from_dict_without_zh_defaults_none():
    d = {"id": 0, "text_src": "x", "start_ms": 0, "end_ms": 10}
    assert Segment.from_dict(d).text_zh is None


def test_from_dict_without_timestamps_defaults_zero():
    d = {"id": 0, "text_src": "x"}
    s = Segment.from_dict(d)
    assert s.start_ms == 0 and s.end_ms == 0
    assert s.duration_ms == 0
