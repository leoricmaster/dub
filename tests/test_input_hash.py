"""Regression tests for cache.input_hash.

input_hash anchors the entire resume cache: a wrong hash means either stale
artifacts or needless re-runs. It intentionally keys on path+size+mtime (not
file contents) so multi-GB mkv files are cheap to identify.
"""
from __future__ import annotations

from dub.cache import input_hash


def test_stable_for_same_file(tmp_path):
    f = tmp_path / "a.mkv"
    f.write_bytes(b"x" * 100)
    assert input_hash(f) == input_hash(f)


def test_differs_on_extra(tmp_path):
    """The voice name is mixed into the hash → different voices get distinct caches."""
    f = tmp_path / "a.mkv"
    f.write_bytes(b"x")
    assert input_hash(f, extra="nature") != input_hash(f, extra="food")


def test_differs_on_file_size(tmp_path):
    small = tmp_path / "small.mkv"
    big = tmp_path / "big.mkv"
    small.write_bytes(b"x" * 100)
    big.write_bytes(b"x" * 200)
    assert input_hash(small) != input_hash(big)


def test_differs_on_path(tmp_path):
    """Same size, different path → different identity."""
    a = tmp_path / "a.mkv"
    b = tmp_path / "b.mkv"
    a.write_bytes(b"x" * 100)
    b.write_bytes(b"x" * 100)
    assert input_hash(a) != input_hash(b)


def test_returns_short_hex(tmp_path):
    f = tmp_path / "a.mkv"
    f.write_bytes(b"x")
    h = input_hash(f)
    assert len(h) == 16
    int(h, 16)  # raises if not hex
