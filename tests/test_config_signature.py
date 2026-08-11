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


def test_signature_changes_when_tts_max_speed_changes():
    """E2 rung ② cap is part of cache identity."""
    from dub.config import TTSConfig

    cfg1 = make_config()
    cfg2 = make_config()
    cfg2.tts = TTSConfig(max_speed=1.3)
    assert _config_signature(cfg1, "nature") != _config_signature(cfg2, "nature")


def test_signature_changes_when_remediate_config_changes():
    """E2 remediation tuning must invalidate the cache."""
    from dub.config import RemediateConfig

    cfg1 = make_config()
    cfg2 = make_config()
    cfg2.remediate = RemediateConfig(max_atempo=1.4)
    assert _config_signature(cfg1, "nature") != _config_signature(cfg2, "nature")


def test_signature_changes_when_separate_config_changes():
    """Separation params affect the mix bed -> must invalidate the cache."""
    from dub.config import SeparateConfig

    cfg1 = make_config()
    cfg2 = make_config()
    cfg2.separate = SeparateConfig(model="htdemucs")
    assert _config_signature(cfg1, "nature") != _config_signature(cfg2, "nature")


def test_signature_changes_when_duck_db_changes():
    """Mix ducking depth changes the output -> must invalidate the cache."""
    from dub.config import MixConfig

    cfg1 = make_config()
    cfg2 = make_config()
    cfg2.mix = MixConfig(duck_db=-8.0)
    assert _config_signature(cfg1, "nature") != _config_signature(cfg2, "nature")


def test_signature_changes_when_voice_language_boost_changes():
    cfg_on = make_config(voices={"nature": make_voice(language_boost="Chinese")})
    cfg_off = make_config(voices={"nature": make_voice(language_boost=None)})
    assert _config_signature(cfg_on, "nature") != _config_signature(cfg_off, "nature")


def test_work_dir_differs_for_sample_vs_full(tmp_path):
    """A --sample run must not share/poison a full run's cache directory."""
    from dub.pipeline import work_dir_for

    cfg = make_config()
    cfg.pipeline.cache_dir = tmp_path  # contain created dirs
    src = tmp_path / "a.mkv"
    src.write_bytes(b"x" * 100)

    full = work_dir_for(src, cfg, "nature")
    samp = work_dir_for(src, cfg, "nature", sample_seconds=30)
    assert full != samp
