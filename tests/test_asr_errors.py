"""Tests for dashscope ASR failure handling.

Pins that a no-speech outcome (SUCCESS_WITH_NO_VALID_FRAGMENT) raises a clear,
actionable error instead of dumping the raw API response, while other failures
still report the full payload for debugging.
"""
from __future__ import annotations

import pytest

from dub.providers import dashscope_asr


class _Resp:
    def __init__(self, payload):
        self._p = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._p


def _mock_get(monkeypatch, payload):
    monkeypatch.setattr(dashscope_asr.httpx, "get", lambda *a, **k: _Resp(payload))


def test_no_speech_fragment_raises_clear_error(monkeypatch):
    _mock_get(
        monkeypatch,
        {
            "output": {
                "task_status": "FAILED",
                "code": "SUCCESS_WITH_NO_VALID_FRAGMENT",
                "message": "SUCCESS_WITH_NO_VALID_FRAGMENT",
            }
        },
    )
    with pytest.raises(RuntimeError) as exc:
        dashscope_asr.poll_transcription("tid", "key", poll_interval=0, timeout_sec=2)
    assert "no speech" in str(exc.value).lower()
    # the raw dump should NOT dominate the message
    assert "SUCCESS_WITH_NO_VALID_FRAGMENT" not in str(exc.value)


def test_generic_failure_still_reports_dump(monkeypatch):
    _mock_get(monkeypatch, {"output": {"task_status": "FAILED", "code": "SOME_OTHER_ERROR"}})
    with pytest.raises(RuntimeError) as exc:
        dashscope_asr.poll_transcription("tid", "key", poll_interval=0, timeout_sec=2)
    assert "ASR task failed" in str(exc.value)
