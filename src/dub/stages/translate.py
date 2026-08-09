"""Stage: translate source-language segments to Chinese."""
from __future__ import annotations

from ..config import EnvSettings, TranslateConfig
from ..models import Segment
from ..providers import deepseek_translate


def translate(
    segments: list[Segment],
    cfg: TranslateConfig,
    env: EnvSettings,
) -> list[Segment]:
    if cfg.provider == "deepseek":
        return deepseek_translate.translate(segments, cfg, env)
    raise ValueError(f"unknown translate provider: {cfg.provider}")
