from pathlib import Path

from dub.config import EnvSettings, TTSConfig
from dub.providers.minimax_tts import VoiceIdInvalid
from dub.voice_preview import (
    DEFAULT_PREVIEW_EMOTIONS,
    DEFAULT_PREVIEW_VOICES,
    PreviewResult,
    _filename_for,
    expand_matrix,
    nature_yaml_template,
    render_html,
    results_table,
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


def test_results_table_has_one_row_per_result():
    rs = [
        PreviewResult("a", "calm", "ok", Path("a__calm.wav"), "a__calm.wav"),
        PreviewResult("b", None, "skipped", None, "status 2054"),
    ]
    table = results_table(rs)
    assert table.row_count == 2
    assert [c.header for c in table.columns] == ["voice_id", "emotion", "status", "file / note"]


def test_nature_yaml_template_contains_fields():
    out = nature_yaml_template(0.92)
    assert out.startswith("nature:")
    assert "voice_id: <your-pick>" in out
    assert "emotion: calm" in out
    assert "speed: 0.92" in out
    assert "language_boost: Chinese" in out


def test_render_html_writes_file_with_every_result(tmp_path):
    results = [
        PreviewResult("presenter_male", "calm", "ok",
                      tmp_path / "presenter_male__calm.wav", "presenter_male__calm.wav"),
        PreviewResult("male-qn-yuanbo", "calm", "skipped", None, "status 2054 voice id not exist"),
    ]
    out = render_html(results, tmp_path)
    assert out == tmp_path / "index.html"
    assert out.exists()
    html = out.read_text(encoding="utf-8")
    assert "presenter_male" in html
    assert "male-qn-yuanbo" in html
    assert "calm" in html


def test_render_html_ok_rows_have_audio_player_with_relative_src(tmp_path):
    results = [
        PreviewResult("presenter_male", "calm", "ok",
                      tmp_path / "presenter_male__calm.wav", "presenter_male__calm.wav"),
    ]
    html = render_html(results, tmp_path).read_text(encoding="utf-8")
    assert "<audio" in html
    assert "presenter_male__calm.wav" in html
    assert str(tmp_path) not in html  # relative path, not absolute


def test_render_html_failed_rows_show_reason_without_player(tmp_path):
    results = [
        PreviewResult("bogus", "calm", "skipped", None, "status 2054 voice id not exist"),
    ]
    html = render_html(results, tmp_path).read_text(encoding="utf-8")
    assert "voice id not exist" in html
    assert "<audio" not in html
