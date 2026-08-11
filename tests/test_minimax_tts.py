"""Tests for the MiniMax T2A provider request shape.

Mocks httpx so no network/key is needed. Pins that language_boost / emotion are
sent only when set on the voice preset, and that an invalid/missing response
raises clearly.
"""
from __future__ import annotations

import pytest

from dub.config import EnvSettings, TTSConfig, VoicePreset
from dub.providers import minimax_tts


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _capture_post(monkeypatch, payload=None):
    payload = payload if payload is not None else {"data": {"audio": "00"}}
    captured: dict = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["json"] = json
        return _FakeResp(payload)

    monkeypatch.setattr(minimax_tts.httpx, "post", fake_post)
    return captured


def _env():
    return EnvSettings(minimax_api_key="k", minimax_group_id="g")


def test_payload_includes_language_boost_and_emotion(monkeypatch, tmp_path):
    captured = _capture_post(monkeypatch)
    voice = VoicePreset(
        provider="minimax", voice_id="male-qn-yuanbo", language_boost="Chinese", emotion="neutral"
    )
    minimax_tts.synthesize_one("你好", voice, TTSConfig(), _env(), tmp_path / "a.wav")

    p = captured["json"]
    assert p["language_boost"] == "Chinese"
    assert p["voice_setting"]["emotion"] == "neutral"
    assert p["voice_setting"]["voice_id"] == "male-qn-yuanbo"


def test_payload_omits_optional_fields_when_unset(monkeypatch, tmp_path):
    captured = _capture_post(monkeypatch)
    voice = VoicePreset(provider="minimax", voice_id="male-qn-yuanbo")  # no boost/emotion
    minimax_tts.synthesize_one("你好", voice, TTSConfig(), _env(), tmp_path / "a.wav")

    p = captured["json"]
    assert "language_boost" not in p
    assert "emotion" not in p["voice_setting"]
    # core voice_setting fields still present
    assert {"voice_id", "speed", "vol", "pitch"} <= set(p["voice_setting"])


def test_raises_voice_id_invalid_on_2054(monkeypatch, tmp_path):
    payload = {
        "base_resp": {"status_code": 2054, "status_msg": "voice id not exist"},
        "data": {},
    }
    _capture_post(monkeypatch, payload=payload)
    voice = VoicePreset(provider="minimax", voice_id="bogus-id")
    with pytest.raises(minimax_tts.VoiceIdInvalid):
        minimax_tts.synthesize_one("你好", voice, TTSConfig(), _env(), tmp_path / "a.wav")
