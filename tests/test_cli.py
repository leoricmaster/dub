from typer.testing import CliRunner

from dub.cli import app
from dub.voice_preview import PreviewResult

runner = CliRunner()


def _mock_synth(monkeypatch, capture=None):
    """Mock the sweep; optionally capture args into `capture`."""
    def fake_synth(matrix, text, speed, cfg, env, out_dir):
        if capture is not None:
            capture["matrix"] = matrix
        # a real-ish path so render_html has a path.name to reference
        return [PreviewResult(v, e, "ok", out_dir / f"{v}__{e}.wav", f"{v}__{e}.wav")
                for v, e in matrix]

    monkeypatch.setattr("dub.cli.voice_preview.synthesize_previews", fake_synth)


def _mock_browser(monkeypatch):
    opened = []
    monkeypatch.setattr("dub.cli.webbrowser.open", lambda url: opened.append(url))
    return opened


def test_preview_voices_runs_sweep_and_prints_table(monkeypatch):
    seen = {}
    _mock_synth(monkeypatch, seen)
    _mock_browser(monkeypatch)
    result = runner.invoke(app, ["preview-voices", "--voices", "a,b", "--emotions", "calm"])

    assert result.exit_code == 0, result.stdout
    assert ("a", "calm") in seen["matrix"]
    assert ("b", "calm") in seen["matrix"]
    # baseline anchor auto-appended
    assert ("presenter_male", "neutral") in seen["matrix"]
    assert "Voice Preview Results" in result.stdout
    assert "voice_id: <your-pick>" in result.stdout


def test_preview_voices_writes_html_and_opens_browser(monkeypatch):
    _mock_synth(monkeypatch)
    opened = _mock_browser(monkeypatch)
    result = runner.invoke(app, ["preview-voices", "--voices", "a"])

    assert result.exit_code == 0, result.stdout
    assert len(opened) == 1
    assert opened[0].startswith("file://")
    assert opened[0].endswith("index.html")


def test_preview_voices_no_open_skips_browser(monkeypatch):
    _mock_synth(monkeypatch)
    opened = _mock_browser(monkeypatch)
    result = runner.invoke(app, ["preview-voices", "--voices", "a", "--no-open"])

    assert result.exit_code == 0, result.stdout
    assert opened == []
