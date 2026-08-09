"""Hash-based stage cache.

Each stage's output is keyed by:
  - input file identity (path + size + mtime)
  - stage name
  - relevant stage config

This lets us skip work on re-runs and resume partially completed jobs.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Optional


def input_hash(input_path: Path, extra: str = "") -> str:
    """Stable identity hash for an input file.

    Uses path + size + mtime rather than reading file contents —
    important for multi-GB mkv files.
    """
    stat = input_path.stat()
    payload = f"{input_path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}|{extra}"
    return hashlib.sha1(payload.encode()).hexdigest()[:16]


def stage_config_hash(stage_config: dict) -> str:
    cfg_str = json.dumps(stage_config, sort_keys=True, default=str)
    return hashlib.sha1(cfg_str.encode()).hexdigest()[:8]


class Cache:
    """Filesystem-backed cache for stage outputs."""

    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def key(self, input_file_hash: str, stage: str, stage_config: dict) -> str:
        return f"{input_file_hash}/{stage}-{stage_config_hash(stage_config)}"

    def has(self, key: str, suffix: str = "json") -> bool:
        return self.path(key, suffix).exists()

    def path(self, key: str, suffix: str = "json") -> Path:
        p = self.root / f"{key}.{suffix}"
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def read_json(self, key: str) -> Optional[Any]:
        p = self.path(key, "json")
        if not p.exists():
            return None
        with open(p) as f:
            return json.load(f)

    def write_json(self, key: str, data: Any) -> Path:
        p = self.path(key, "json")
        with open(p, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        return p

    def remove(self, key: str, suffix: str = "json") -> None:
        p = self.path(key, suffix)
        if p.exists():
            if p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink()

    def work_dir(self, name: str) -> Path:
        """A scratch directory for arbitrary stage files (e.g. per-segment wavs)."""
        d = self.root / name
        d.mkdir(parents=True, exist_ok=True)
        return d
