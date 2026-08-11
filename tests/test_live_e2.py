"""Live tests for E2 assumptions that need real provider APIs.

Skipped by default (needs --run-live AND real keys in .env). These validate the
two core assumptions the remediation ladder rests on:
  - MiniMax `speed` shortens clip duration (rung ② lever actually works).
  - DeepSeek `retranslate_strict` respects a hard char budget (rung ① shortens text).
"""
from __future__ import annotations

import pytest

from dub.config import load_config
from dub.models import Segment
from dub.providers.deepseek_translate import retranslate_strict
from dub.providers.minimax_tts import synthesize_one
from dub.timing import char_budget, clip_duration_ms


@pytest.mark.live
def test_live_minimax_speed_shortens_clip(tmp_path):
    cfg = load_config()
    if not cfg.env.minimax_api_key or not cfg.env.minimax_group_id:
        pytest.skip("MiniMax keys not set")
    voice = cfg.voices.get("nature") or next(iter(cfg.voices.values()))
    text = "这是一段用于测试语速影响的中文纪录片旁白句子。"

    slow = synthesize_one(text, voice.model_copy(update={"speed": 1.0}), cfg.tts, cfg.env, tmp_path / "slow.wav")
    fast = synthesize_one(text, voice.model_copy(update={"speed": 1.3}), cfg.tts, cfg.env, tmp_path / "fast.wav")

    d_slow = clip_duration_ms(slow)
    d_fast = clip_duration_ms(fast)
    assert d_fast < d_slow, f"speed did not shorten clip: slow={d_slow}ms fast={d_fast}ms"
    # roughly inverse: 1.3x speed -> ~0.77x duration
    ratio = d_fast / d_slow
    assert ratio < 0.9, f"speed effect too weak: ratio={ratio:.2f}"


@pytest.mark.live
def test_live_deepseek_retranslate_respects_budget():
    cfg = load_config()
    if not cfg.env.deepseek_api_key:
        pytest.skip("DEEPSEEK_API_KEY not set")
    seg = Segment(
        id=0,
        text_src="The majestic humpback whale migrates thousands of miles across the ocean each year.",
        start_ms=0,
        end_ms=2000,
    )
    budget = char_budget(seg.duration_sec, cfg.translate.max_chars_per_second)  # ~7 chars
    zh = retranslate_strict(seg, budget, cfg.translate, cfg.env)
    assert zh, "empty retranslation"
    # LLMs don't hit exact budgets; allow a little slack but it must be short
    assert len(zh) <= budget + 3, f"over budget: {len(zh)} > {budget} (zh={zh!r})"
