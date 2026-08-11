# `dub preview-voices` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `dub preview-voices` command that synthesises a fixed narration line across a matrix of candidate MiniMax voice_id × emotion combos, so the user can A/B by ear and decide whether presets hold an acceptable documentary voice.

**Architecture:** A new `voice_preview` module holds all pure logic (matrix expansion, synthesis sweep with per-combo fault tolerance, result table, YAML template). The MiniMax provider gains a `VoiceIdInvalid` exception so the sweep can skip rejected voice_ids without aborting. A thin typer command in `cli.py` wires it together. Preview output is intentionally kept out of `.dub-cache` (it is exploratory, not a pipeline stage).

**Tech Stack:** Python ≥ 3.10, typer, rich, pydantic, pytest (monkeypatch-based, `@pytest.mark.live` gating), existing `dub.providers.minimax_tts.synthesize_one`.

## Global Constraints

- Python ≥ 3.10; `from __future__ import annotations` at top of new modules (matches existing style).
- Fast-lane tests must not hit the network or need real API keys — mock `httpx` / `synthesize_one`.
- Live API calls gated by `@pytest.mark.live`, skipped unless `--run-live` (see `tests/conftest.py`).
- MiniMax model is `speech-2.8-hd`; request shape pinned by `tests/test_minimax_tts.py` must stay green.
- Preview output never enters `.dub-cache`; write under `output/voice-previews/<timestamp>/`.
- No new runtime dependencies (typer/rich/pydantic already present).
- Commit after each task; messages prefixed `feat:` / `docs:` / `test:`.

---

## File Structure

- **Modify** `src/dub/providers/minimax_tts.py` — add `VoiceIdInvalid` exception; detect status `2054` in `synthesize_one`.
- **Modify** `tests/test_minimax_tts.py` — test the new `2054` → `VoiceIdInvalid` path.
- **Create** `src/dub/voice_preview.py` — constants (`PREVIEW_TEXT`, defaults, anchor), `expand_matrix`, `synthesize_previews`, `PreviewResult`, `results_table`, `nature_yaml_template`. One responsibility: the preview sweep.
- **Create** `tests/test_voice_preview.py` — unit tests for the preview module.
- **Modify** `src/dub/cli.py` — add `preview_voices` typer command; import `voice_preview`.
- **Create** `tests/test_cli.py` — CLI smoke test for `preview-voices` (mocks the sweep).
- **Modify** `README.md` — correct the stale §音色 (`male-qn-yuanbo` → current reality + `preview-voices`).

---

### Task 1: `VoiceIdInvalid` exception + status 2054 detection in the MiniMax provider

**Files:**
- Modify: `src/dub/providers/minimax_tts.py`
- Test: `tests/test_minimax_tts.py`

**Interfaces:**
- Produces: `class VoiceIdInvalid(RuntimeError)` in `dub.providers.minimax_tts`. `synthesize_one` raises it when the JSON response has `base_resp.status_code == 2054`. Other "no audio" failures keep raising `RuntimeError`. Consumed by Task 3.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_minimax_tts.py`:

```python
import pytest


def test_raises_voice_id_invalid_on_2054(monkeypatch, tmp_path):
    payload = {
        "base_resp": {"status_code": 2054, "status_msg": "voice id not exist"},
        "data": {},
    }
    _capture_post(monkeypatch, payload=payload)
    voice = VoicePreset(provider="minimax", voice_id="bogus-id")
    with pytest.raises(minimax_tts.VoiceIdInvalid):
        minimax_tts.synthesize_one("你好", voice, TTSConfig(), _env(), tmp_path / "a.wav")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_minimax_tts.py::test_raises_voice_id_invalid_on_2054 -v`
Expected: FAIL — `AttributeError: module 'dub.providers.minimax_tts' has no attribute 'VoiceIdInvalid'`

- [ ] **Step 3: Implement the exception and the 2054 check**

In `src/dub/providers/minimax_tys.py`, add the exception class just below the `log = logging.getLogger(__name__)` line (after the `MINIMAX_T2A_URL` constant):

```python
class VoiceIdInvalid(RuntimeError):
    """MiniMax rejected the voice_id (status 2054 'voice id not exist').

    Distinct from other failures so callers (e.g. preview-voices) can skip the
    offending voice and continue with the next candidate instead of aborting.
    """
```

Then in `synthesize_one`, replace the block:

```python
    data = resp.json()

    audio_field = data.get("data", {}).get("audio")
    if not audio_field:
        raise RuntimeError(f"MiniMax T2A returned no audio: {data}")
```

with:

```python
    data = resp.json()

    # MiniMax returns HTTP 200 even for API-level errors; voice_id problems
    # surface as base_resp.status_code == 2054 ("voice id not exist").
    base_resp = data.get("base_resp", {})
    if base_resp.get("status_code") == 2054:
        raise VoiceIdInvalid(
            f"voice_id not accepted by MiniMax (status 2054): "
            f"{base_resp.get('status_msg', '')}"
        )

    audio_field = data.get("data", {}).get("audio")
    if not audio_field:
        raise RuntimeError(f"MiniMax T2A returned no audio: {data}")
```

- [ ] **Step 4: Run the full provider test file to verify pass + no regressions**

Run: `pytest tests/test_minimax_tts.py -v`
Expected: PASS (3 tests: the two existing payload-shape tests still pass because their fake response has no `base_resp` → status_code treated as not-2054; the new test passes).

- [ ] **Step 5: Commit**

```bash
git add src/dub/providers/minimax_tts.py tests/test_minimax_tts.py
git commit -m "feat(tts): raise VoiceIdInvalid on MiniMax status 2054"
```

---

### Task 2: Preview module — constants + matrix expansion

**Files:**
- Create: `src/dub/voice_preview.py`
- Create: `tests/test_voice_preview.py`

**Interfaces:**
- Produces:
  - `PREVIEW_TEXT: str` — built-in narration line.
  - `DEFAULT_PREVIEW_VOICES: list[str]`, `DEFAULT_PREVIEW_EMOTIONS: list[str]`.
  - `ANCHOR_VOICE = "presenter_male"`, `ANCHOR_EMOTION = "neutral"`.
  - `expand_matrix(voices: list[str], emotions: list[str]) -> list[tuple[str, str | None]]` — cartesian product, with the baseline anchor appended exactly once if missing.
- Consumes: nothing from other tasks.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_voice_preview.py`:

```python
from dub.voice_preview import (
    DEFAULT_PREVIEW_EMOTIONS,
    DEFAULT_PREVIEW_VOICES,
    expand_matrix,
)


def test_expand_matrix_is_cartesian_product():
    assert expand_matrix(["a", "b"], ["calm"]) == [("a", "calm"), ("b", "calm")]


def test_expand_matrix_multiple_emotions():
    assert expand_matrix(["a"], ["calm", "fluent"]) == [("a", "calm"), ("a", "fluent")]


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_voice_preview.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'dub.voice_preview'`

- [ ] **Step 3: Create the module with constants and `expand_matrix`**

Create `src/dub/voice_preview.py`:

```python
"""Voice preview sweep for the `dub preview-voices` command.

Synthesises one fixed narration line across a matrix of candidate
voice_id x emotion combos so the user can A/B by ear. This is the low-cost
"judgement experiment" deciding whether MiniMax presets hold an acceptable
documentary voice before committing to a local-TTS route. See
docs/superpowers/specs/2026-08-11-documentary-voice-design.md.
"""
from __future__ import annotations

# A representative BBC-nature-style Mandarin narration: has scene, rhythm and a
# small emotional arc (not flat declarative). ~80 chars / a few seconds — enough
# to judge timbre and cadence, cheap to synthesise.
PREVIEW_TEXT = (
    "在非洲草原的尽头，雨季的云层正在聚集。"
    "一群角马已经在这里等待了数周——它们能嗅到远方的水汽。"
    "当第一场雨落下，漫长的迁徙就将开始。"
    "这片土地上的每一个生命，都在等待这一刻。"
)

# Candidates aimed at "steady / narrator / deep" timbres, from MiniMax's voice
# library descriptions + the project's prior probes. Validity under
# speech-2.8-hd is NOT guaranteed — invalid ids are skipped at synth time.
DEFAULT_PREVIEW_VOICES: list[str] = [
    "presenter_male",     # current baseline (broadcast male)
    "male-qn-jingying",   # elite / steady
    "male-qn-yuanbo",     # narrator / documentary (turbo-invalid; hd TBD)
    "male-qn-badao",      # deep / forceful
]

DEFAULT_PREVIEW_EMOTIONS: list[str] = ["calm"]

# Always also render the real-world baseline so the user has a reference point.
ANCHOR_VOICE = "presenter_male"
ANCHOR_EMOTION = "neutral"


def expand_matrix(
    voices: list[str],
    emotions: list[str],
) -> list[tuple[str, str | None]]:
    """Cartesian product of voices x emotions, with the baseline anchor ensured.

    The anchor (presenter_male x neutral) is appended exactly once if not already
    present, so the table always includes the user's current real-world voice as
    a comparison reference. Candidates come first, anchor last.
    """
    matrix: list[tuple[str, str | None]] = [
        (v, e) for v in voices for e in emotions
    ]
    anchor = (ANCHOR_VOICE, ANCHOR_EMOTION)
    if anchor not in matrix:
        matrix.append(anchor)
    return matrix
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_voice_preview.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/dub/voice_preview.py tests/test_voice_preview.py
git commit -m "feat(preview): voice_preview module skeleton + matrix expansion"
```

---

### Task 3: Preview module — synthesis sweep with per-combo fault tolerance

**Files:**
- Modify: `src/dub/voice_preview.py`
- Modify: `tests/test_voice_preview.py`

**Interfaces:**
- Produces:
  - `@dataclass PreviewResult(voice_id: str, emotion: str | None, status: str, path: Path | None, note: str)` — `status` is `"ok" | "skipped" | "error"`.
  - `synthesize_previews(matrix, text, speed, cfg: TTSConfig, env: EnvSettings, out_dir: Path) -> list[PreviewResult]` — never raises; `VoiceIdInvalid` → `"skipped"`, other exceptions → `"error"`, success → `"ok"` with the wav path.
  - `_filename_for(voice_id, emotion) -> str` — e.g. `"presenter_male__calm.wav"`, `"presenter_male__none.wav"`.
- Consumes: `VoiceIdInvalid`, `synthesize_one` from `dub.providers.minimax_tts` (Task 1); `VoicePreset`, `TTSConfig`, `EnvSettings` from `dub.config`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_voice_preview.py`:

```python
from pathlib import Path

from dub.config import EnvSettings, TTSConfig
from dub.providers.minimax_tts import VoiceIdInvalid
from dub.voice_preview import PreviewResult, _filename_for, synthesize_previews


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_voice_preview.py -v`
Expected: FAIL — `ImportError: cannot import name 'PreviewResult'` (and `_filename_for`, `synthesize_previews`).

- [ ] **Step 3: Add the dataclass, helpers, and sweep**

Append to `src/dub/voice_preview.py`:

```python
from dataclasses import dataclass
from pathlib import Path

from rich.table import Table

from .config import EnvSettings, TTSConfig, VoicePreset
from .providers.minimax_tts import VoiceIdInvalid, synthesize_one


@dataclass
class PreviewResult:
    voice_id: str
    emotion: str | None
    status: str        # "ok" | "skipped" | "error"
    path: Path | None
    note: str          # filename on ok, error message otherwise


def _filename_for(voice_id: str, emotion: str | None) -> str:
    return f"{voice_id}__{emotion or 'none'}.wav"


def _voice_for(voice_id: str, emotion: str | None, speed: float) -> VoicePreset:
    return VoicePreset(
        provider="minimax",
        voice_id=voice_id,
        speed=speed,
        emotion=emotion,
        language_boost="Chinese",
    )


def synthesize_previews(
    matrix: list[tuple[str, str | None]],
    text: str,
    speed: float,
    cfg: TTSConfig,
    env: EnvSettings,
    out_dir: Path,
) -> list[PreviewResult]:
    """Synthesise one clip per (voice_id, emotion) combo into out_dir.

    Each combo is independent and never aborts the sweep: VoiceIdInvalid ->
    "skipped", any other exception -> "error", success -> "ok".
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    results: list[PreviewResult] = []
    for voice_id, emotion in matrix:
        out_path = out_dir / _filename_for(voice_id, emotion)
        try:
            synthesize_one(text, _voice_for(voice_id, emotion, speed), cfg, env, out_path)
            results.append(PreviewResult(voice_id, emotion, "ok", out_path, out_path.name))
        except VoiceIdInvalid as e:
            results.append(PreviewResult(voice_id, emotion, "skipped", None, str(e)))
        except Exception as e:  # noqa: BLE001 - a preview sweep must survive any failure
            results.append(
                PreviewResult(voice_id, emotion, "error", None, f"{type(e).__name__}: {e}")
            )
    return results
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_voice_preview.py -v`
Expected: PASS (all tests, incl. the 5 from Task 2).

- [ ] **Step 5: Commit**

```bash
git add src/dub/voice_preview.py tests/test_voice_preview.py
git commit -m "feat(preview): synthesis sweep with per-combo fault tolerance"
```

---

### Task 4: Preview module — results table + YAML template

**Files:**
- Modify: `src/dub/voice_preview.py`
- Modify: `tests/test_voice_preview.py`

**Interfaces:**
- Produces:
  - `results_table(results: list[PreviewResult]) -> rich.table.Table` — columns: voice_id, emotion, status, file / note.
  - `nature_yaml_template(speed: float) -> str` — a fill-in-the-blank YAML snippet for pinning the winner into `config/voices.yaml` -> `nature`.
- Consumes: `PreviewResult` (Task 3).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_voice_preview.py`:

```python
from dub.voice_preview import nature_yaml_template, results_table


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_voice_preview.py -v`
Expected: FAIL — `ImportError: cannot import name 'nature_yaml_template'` (and `results_table`).

- [ ] **Step 3: Implement the table and template**

Append to `src/dub/voice_preview.py`:

```python
def results_table(results: list[PreviewResult]) -> Table:
    """Build the rich table printed after a sweep."""
    table = Table(title="Voice Preview Results")
    table.add_column("voice_id", style="bold")
    table.add_column("emotion")
    table.add_column("status")
    table.add_column("file / note")
    for r in results:
        table.add_row(r.voice_id, r.emotion or "-", r.status, r.note)
    return table


def nature_yaml_template(speed: float) -> str:
    """Fill-in-the-blank YAML snippet for pinning the winner into voices.yaml."""
    return (
        "nature:\n"
        "  provider: minimax\n"
        "  voice_id: <your-pick>\n"
        "  emotion: calm          # calm | fluent | neutral\n"
        f"  speed: {speed}\n"
        "  vol: 1.0\n"
        "  pitch: 0\n"
        "  language_boost: Chinese\n"
    )
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_voice_preview.py -v`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add src/dub/voice_preview.py tests/test_voice_preview.py
git commit -m "feat(preview): results table + nature yaml template"
```

---

### Task 5: `dub preview-voices` CLI command

**Files:**
- Modify: `src/dub/cli.py`
- Create: `tests/test_cli.py`

**Interfaces:**
- Produces: typer command `preview-voices` registered on the app. Options: `--voices` (csv), `--emotions` (csv), `--speed` (float, default 0.92), `--text` (str, optional), `--config` (path, optional). Writes wav files under `output/voice-previews/<YYYYmmdd-HHMMSS>/` and prints the results table + YAML template.
- Consumes: `expand_matrix`, `synthesize_previews`, `results_table`, `nature_yaml_template`, `PREVIEW_TEXT` from `dub.voice_preview` (Tasks 2–4); `load_config` from `dub.config`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_cli.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py -v`
Expected: FAIL — `Error: No such command 'preview-voices'` (exit code != 0).

- [ ] **Step 3: Add the command to `cli.py`**

In `src/dub/cli.py`:

(a) Update the top import line (currently `from . import __version__, pipeline`) to also import the preview module and `datetime`:

```python
from datetime import datetime

from . import __version__, pipeline, voice_preview
```

(b) Add the new command after the existing `voices` command (before `version`):

```python
@app.command(name="preview-voices")
def preview_voices(
    voices: str = typer.Option(
        ",".join(voice_preview.DEFAULT_PREVIEW_VOICES), "--voices",
        help="Comma-separated candidate voice_ids.",
    ),
    emotions: str = typer.Option(
        ",".join(voice_preview.DEFAULT_PREVIEW_EMOTIONS), "--emotions",
        help="Comma-separated emotions, e.g. calm,fluent.",
    ),
    speed: float = typer.Option(
        0.92, "--speed",
        help="Speech rate applied to every sample (keep equal for fair A/B).",
    ),
    text: Optional[str] = typer.Option(
        None, "--text", help="Override the built-in preview narration line.",
    ),
    config: Optional[Path] = typer.Option(None, "--config", help="Override YAML config path"),
) -> None:
    """Synthesise a fixed narration across voice x emotion candidates for A/B by ear.

    Low-cost judgement experiment: writes one wav per combo under
    output/voice-previews/<timestamp>/ and prints a table. Invalid voice_ids
    are skipped. After listening, pin the winner into config/voices.yaml.
    """
    cfg = load_config(config)
    voice_ids = [v.strip() for v in voices.split(",") if v.strip()]
    emo_list = [e.strip() for e in emotions.split(",") if e.strip()]
    matrix = voice_preview.expand_matrix(voice_ids, emo_list)

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = cfg.pipeline.output_dir / "voice-previews" / ts
    console.print(f"[dim]synthesising {len(matrix)} samples -> {out_dir}[/dim]")

    results = voice_preview.synthesize_previews(
        matrix, text or voice_preview.PREVIEW_TEXT, speed, cfg.tts, cfg.env, out_dir
    )
    console.print(results and voice_preview.results_table(results))

    ok = [r for r in results if r.status == "ok"]
    console.print(
        f"\n[bold]next:[/bold] listen to the {len(ok)} ok sample(s) under {out_dir}, "
        "pick the one that sounds most like a BBC Chinese documentary, and "
        "edit config/voices.yaml -> nature."
    )
    console.print("\n[dim]# paste into config/voices.yaml -> nature:[/dim]")
    console.print(voice_preview.nature_yaml_template(speed))
```

- [ ] **Step 4: Run the CLI test to verify pass**

Run: `pytest tests/test_cli.py -v`
Expected: PASS.

- [ ] **Step 5: Run the whole fast suite to check for regressions**

Run: `pytest -q`
Expected: PASS (all fast-lane tests).

- [ ] **Step 6: Commit**

```bash
git add src/dub/cli.py tests/test_cli.py
git commit -m "feat(cli): add dub preview-voices command"
```

---

### Task 6: Correct the stale README §音色

**Files:**
- Modify: `README.md`

**Interfaces:** None (docs only).

- [ ] **Step 1: Replace the stale §音色 paragraph**

In `README.md`, replace:

```markdown
`config/voices.yaml`：`nature` 已固化为 `male-qn-yuanbo`（渊博男声，纪录片旁白）。其余预设（food/science/history）的 voice_id 仍为候选，到 [MiniMax 控制台](https://platform.minimaxi.com/platform/tts) 试听后更新即可。音色按预设缓存，换 voice_id 只重花 TTS 的钱。
```

with:

```markdown
`config/voices.yaml`：`nature` 当前用 `presenter_male`（播音男声），仍在调优——用 `dub preview-voices` 跨候选音色×情感盲听对比，再把满意的固化进预设（设计见 [docs/superpowers/specs/2026-08-11-documentary-voice-design.md](docs/superpowers/specs/2026-08-11-documentary-voice-design.md)）。其余预设（food/science/history）的 voice_id 仍为候选。音色按预设缓存，换 voice_id 只重花 TTS 的钱。
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: fix stale README voice section (yuanbo -> presenter_male + preview-voices)"
```

---

## Notes for execution

- The full `pytest -q` run happens in Task 5 Step 5; later tasks are docs-only.
- A real end-to-end smoke (`dub preview-voices` with real keys) belongs behind `@pytest.mark.live` and is intentionally NOT added here — it costs real money and is something the user runs manually once the winner-picking is wanted. The spec calls this the "judgement experiment".
- After Task 6, the user runs `dub preview-voices`, listens, and (per spec) manually pins the winner into `config/voices.yaml` -> `nature`. If no preset satisfies, trigger BACKLOG E8 (local TTS route).
