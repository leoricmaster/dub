from dub.config import EnvSettings, TTSConfig
from dub.providers.minimax_tts import VoiceIdInvalid
from dub.voice_preview import (
    DEFAULT_PREVIEW_EMOTIONS,
    DEFAULT_PREVIEW_VOICES,
    _filename_for,
    expand_matrix,
    synthesize_previews,
)


def test_expand_matrix_is_cartesian_product():
    # Candidates appear in voices-x-emotions order; the baseline anchor is
    # always appended last (see test_expand_matrix_appends_baseline_anchor_when_missing).
    assert expand_matrix(["a", "b"], ["calm"]) == [
        ("a", "calm"),
        ("b", "calm"),
        ("presenter_male", "neutral"),
    ]


def test_expand_matrix_multiple_emotions():
    assert expand_matrix(["a"], ["calm", "fluent"]) == [
        ("a", "calm"),
        ("a", "fluent"),
        ("presenter_male", "neutral"),
    ]


def test_expand_matrix_appends_baseline_anchor_when_missing():
    result = expand_matrix(["male-qn-jingying"], ["calm"])
    assert result[-1] == ("presenter_male", "neutral")
    assert ("presenter_male", "neutral") in result


def test_expand_matrix_does_not_duplicate_anchor_when_present():
    result = expand_matrix(["presenter_male"], ["neutral"])
    assert result.count(("presenter_male", "neutral")) == 1


def test_defaults_are_non_empty():
    assert "presenter_male" in DEFAULT_PREVIEW_VOICES
    assert DEFAULT_PREVIEW_EMOTIONS == ["calm"]


def _env():
    return EnvSettings(minimax_api_key="k", minimax_group_id="g")


def _fake_synth(monkeypatch, outcomes):
    """outcomes: dict[(voice_id, emotion)] -> 'ok' or an Exception to raise."""
    def fake(text, voice, cfg, env, out_path):
        outcome = outcomes.get((voice.voice_id, voice.emotion), "ok")
        if isinstance(outcome, Exception):
            raise outcome
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"fake")
        return out_path

    monkeypatch.setattr("dub.voice_preview.synthesize_one", fake)


def test_filename_for_encodes_voice_and_emotion():
    assert _filename_for("presenter_male", "calm") == "presenter_male__calm.wav"
    assert _filename_for("presenter_male", None) == "presenter_male__none.wav"


def test_synthesize_previews_marks_ok(tmp_path, monkeypatch):
    _fake_synth(monkeypatch, {})
    results = synthesize_previews(
        [("presenter_male", "calm")], "hi", 0.92, TTSConfig(), _env(), tmp_path
    )
    assert len(results) == 1
    assert results[0].status == "ok"
    assert results[0].path.exists()
    assert results[0].path.name == "presenter_male__calm.wav"


def test_synthesize_previews_skips_invalid_voice_id(tmp_path, monkeypatch):
    _fake_synth(monkeypatch, {("bogus", "calm"): VoiceIdInvalid("status 2054")})
    results = synthesize_previews(
        [("bogus", "calm")], "hi", 0.92, TTSConfig(), _env(), tmp_path
    )
    assert results[0].status == "skipped"
    assert "2054" in results[0].note
    assert results[0].path is None


def test_synthesize_previews_continues_after_error(tmp_path, monkeypatch):
    _fake_synth(
        monkeypatch,
        {("bad", "calm"): RuntimeError("network down"), ("good", "calm"): "ok"},
    )
    results = synthesize_previews(
        [("bad", "calm"), ("good", "calm")], "hi", 0.92, TTSConfig(), _env(), tmp_path
    )
    assert [r.status for r in results] == ["error", "ok"]
    assert "network down" in results[0].note
    assert results[1].status == "ok"
