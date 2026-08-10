"""Regression tests for cache.Cache (the per-input scratch directory)."""
from __future__ import annotations

from dub.cache import Cache


def test_work_dir_creates_directory(tmp_path):
    c = Cache(tmp_path / "root")
    d = c.work_dir("abc123")
    assert d.exists() and d.is_dir()
    assert d == tmp_path / "root" / "abc123"


def test_work_dir_is_idempotent(tmp_path):
    """Re-asking the same work dir must not error on the second call."""
    c = Cache(tmp_path / "root")
    d1 = c.work_dir("abc123")
    d2 = c.work_dir("abc123")
    assert d1 == d2


def test_cache_constructor_creates_root(tmp_path):
    root = tmp_path / "cache_root"
    assert not root.exists()
    Cache(root)
    assert root.exists()
