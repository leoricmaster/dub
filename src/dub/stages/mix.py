"""Stage: mix Chinese TTS clips over attenuated original audio.

P1 strategy: attenuate the full original track by a fixed dB and overlay
Chinese clips at their segment start times. The original English remains
faintly audible underneath — acceptable for validation. P2 will replace
this with proper BGM ducking after Demucs separation (vocals removed,
only music/SFX remain as background).
"""
from __future__ import annotations

from pathlib import Path

from pydub import AudioSegment

from ..config import MixConfig
from ..models import AudioTrack, Segment


def mix_audio(
    original: AudioTrack,
    segments: list[Segment],
    tts_clips: dict[int, Path],
    cfg: MixConfig,
    work_dir: Path,
) -> Path:
    """Overlay Chinese TTS clips over the attenuated original track."""
    base = AudioSegment.from_wav(original.path)
    base = base + cfg.bg_attenuation_db

    for seg in segments:
        clip_path = tts_clips.get(seg.id)
        if clip_path is None or not clip_path.exists():
            continue
        clip = AudioSegment.from_wav(clip_path)
        base = base.overlay(clip, position=seg.start_ms)

    base = base.set_frame_rate(cfg.sample_rate)
    out_path = work_dir / "zh_audio.wav"
    base.export(out_path, format="wav")
    return out_path
