"""Stage: translate source-language segments to Chinese."""
from __future__ import annotations

import logging

from .. import remediate
from ..config import EnvSettings, TranslateConfig
from ..models import Segment
from ..providers import deepseek_translate

log = logging.getLogger(__name__)


def translate(
    segments: list[Segment],
    cfg: TranslateConfig,
    env: EnvSettings,
) -> list[Segment]:
    if cfg.provider != "deepseek":
        raise ValueError(f"unknown translate provider: {cfg.provider}")

    segments = deepseek_translate.translate(segments, cfg, env)

    # E2 rung ①: re-translate segments whose Chinese exceeds the char budget,
    # before any TTS spend. Runs only when translation is fresh (not cached),
    # so the shortened text persists to segments_zh.json.
    if cfg.refit:
        report = remediate.remediate_translation(
            segments,
            cfg.max_chars_per_second,
            retranslate_fn=lambda seg, budget: deepseek_translate.retranslate_strict(
                seg, budget, cfg, env
            ),
        )
        if report.retranslated or report.failed:
            log.info("translate refit (rung ①): %s", report)

    return segments
