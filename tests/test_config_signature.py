"""Tests for pipeline cache-key correctness.

The work dir is keyed by input identity + _config_signature(config, voice).
If the signature misses any input that affects output, resume silently serves
stale artifacts. The riskiest gap historically: the voice preset *contents*
(speed/voice_id/vol/pitch) were not in the signature, only the preset name.
"""
from __future__ import annotations

from dub.pipeline import _config_signature

from .helpers import make_config, make_voice


def test_signature_stable_for_identical_config():
    cfg = make_config()
    assert _config_signature(cfg, "nature") == _config_signature(cfg, "nature")


def test_signature_changes_with_voice_name():
    cfg = make_config(
        voices={
            "nature": make_voice(voice_id="male-qn-qingse"),
            "food": make_voice(voice_id="male-qn-badao"),
        }
    )
    assert _config_signature(cfg, "nature") != _config_signature(cfg, "food")


def test_signature_changes_when_voice_preset_speed_changes():
    """THE BUG: editing voices.yaml speed must invalidate the cache."""
    cfg_fast = make_config(voices={"nature": make_voice(speed=0.95)})
    cfg_slow = make_config(voices={"nature": make_voice(speed=0.85)})
    assert _config_signature(cfg_fast, "nature") != _config_signature(
        cfg_slow, "nature"
    )


def test_signature_changes_when_voice_id_changes():
    cfg_a = make_config(voices={"nature": make_voice(voice_id="male-qn-qingse")})
    cfg_b = make_config(voices={"nature": make_voice(voice_id="male-qn-yuanbo")})
    assert _config_signature(cfg_a, "nature") != _config_signature(cfg_b, "nature")


def test_signature_changes_when_stage_config_changes():
    """Translating with a different model must invalidate the cache."""
    from dub.config import TranslateConfig

    cfg1 = make_config()
    cfg2 = make_config()
    cfg2.translate = TranslateConfig(model="deepseek-reasoner")
    assert _config_signature(cfg1, "nature") != _config_signature(cfg2, "nature")
