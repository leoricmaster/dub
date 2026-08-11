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
