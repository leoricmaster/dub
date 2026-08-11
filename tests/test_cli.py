from typer.testing import CliRunner

from dub.cli import app
from dub.voice_preview import PreviewResult

runner = CliRunner()


def test_preview_voices_runs_sweep_and_prints_table(monkeypatch):
    seen = {}

    def fake_synth(matrix, text, speed, cfg, env, out_dir):
        seen["matrix"] = matrix
        seen["text"] = text
        return [PreviewResult(v, e, "ok", None, f"{v}__{e}.wav") for v, e in matrix]

    monkeypatch.setattr("dub.cli.voice_preview.synthesize_previews", fake_synth)
    result = runner.invoke(app, ["preview-voices", "--voices", "a,b", "--emotions", "calm"])

    assert result.exit_code == 0, result.stdout
    assert ("a", "calm") in seen["matrix"]
    assert ("b", "calm") in seen["matrix"]
    # baseline anchor auto-appended
    assert ("presenter_male", "neutral") in seen["matrix"]
    assert "Voice Preview Results" in result.stdout
    assert "voice_id: <your-pick>" in result.stdout
