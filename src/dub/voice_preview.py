"""Voice preview sweep for the `dub preview-voices` command.

Synthesises one fixed narration line across a matrix of candidate
voice_id x emotion combos so the user can A/B by ear. This is the low-cost
"judgement experiment" deciding whether MiniMax presets hold an acceptable
documentary voice before committing to a local-TTS route. See
docs/superpowers/specs/2026-08-11-documentary-voice-design.md.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rich.table import Table

from .config import EnvSettings, TTSConfig, VoicePreset
from .providers.minimax_tts import VoiceIdInvalid, synthesize_one

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
