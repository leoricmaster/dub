"""Hash-based stage cache.

Each input gets a scratch work directory under the cache root, keyed by the
input file identity (path + size + mtime) plus a hash of the full stage
configuration. Stage outputs land in this directory by convention
(audio.wav, segments_en.json, tts_clips/, ...); the presence of the expected
file means the stage can be skipped on resume.
"""
from __future__ import annotations

import hashlib
from pathlib import Path


def input_hash(input_path: Path, extra: str = "") -> str:
    """Stable identity hash for an input file.

    Uses path + size + mtime rather than reading file contents —
    important for multi-GB mkv files.
    """
    stat = input_path.stat()
    payload = f"{input_path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}|{extra}"
    return hashlib.sha1(payload.encode()).hexdigest()[:16]


class Cache:
    """Filesystem-backed scratch area for one input's stage outputs."""

    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def work_dir(self, name: str) -> Path:
        """A scratch directory for one input's stage files (audio, json, clips)."""
        d = self.root / name
        d.mkdir(parents=True, exist_ok=True)
        return d
