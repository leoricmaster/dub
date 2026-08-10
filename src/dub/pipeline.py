"""Pipeline orchestrator.

Runs the six stages in sequence against one input file:
  extract -> transcribe -> translate -> tts -> mix -> mux

Per-input scratch/cache directory is keyed by input file identity AND the
full stage configuration. Any config change (sample rate, voice, model
version, etc.) creates a fresh work dir, so resume is always safe.

JSON intermediate files (segments_en.json, segments_zh.json) are written
into the work dir for inspection and resume. The final mkv goes to
pipeline.output_dir.
"""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Optional

from .cache import Cache, input_hash
from .config import AppConfig, VoicePreset, load_config
from .models import AudioTrack, JobContext, Segment
from .stages import extract, mix, mux, transcribe, translate, tts

log = logging.getLogger(__name__)


def _config_signature(config: AppConfig, voice: str) -> str:
    """Hash of all stage configs + voice. Changes here invalidate cache."""
    payload = {
        "extract": config.extract.model_dump(),
        "asr": config.asr.model_dump(),
        "translate": config.translate.model_dump(),
        "tts": config.tts.model_dump(),
        "mix": config.mix.model_dump(),
        "mux": config.mux.model_dump(),
        "voice": voice,
    }
    return hashlib.sha1(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:12]


def work_dir_for(input_path: Path, config: AppConfig, voice: str) -> Path:
    """Per-input cache dir, keyed by file identity + full stage config + voice."""
    file_hash = input_hash(input_path, extra=voice)
    sig = _config_signature(config, voice)
    return Cache(config.pipeline.cache_dir).work_dir(f"{file_hash}-{sig}")


def ensure_audio(
    input_path: Path, config: AppConfig, work_dir: Path, resume: bool
) -> AudioTrack:
    """Stage 1: extract audio (cached by audio.wav presence)."""
    audio_path = work_dir / "audio.wav"
    if audio_path.exists() and resume:
        log.info("[1/6] extract (cached)")
    else:
        log.info("[1/6] extract")
        extract.extract_audio(input_path, config.extract, work_dir)
    return AudioTrack(
        path=audio_path,
        sample_rate=config.extract.sample_rate,
        channels=1 if config.extract.mono else 2,
    )


def ensure_transcript(
    audio: AudioTrack, config: AppConfig, work_dir: Path, resume: bool
) -> list[Segment]:
    """Stage 2: transcribe (cached by segments_en.json presence)."""
    en_path = work_dir / "segments_en.json"
    if en_path.exists() and resume:
        log.info("[2/6] transcribe (cached)")
        segments = [Segment.from_dict(d) for d in json.loads(en_path.read_text("utf-8"))]
    else:
        log.info("[2/6] transcribe")
        segments = transcribe.transcribe(audio, config.asr, config.env, work_dir)
        en_path.write_text(
            json.dumps([s.to_dict() for s in segments], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    log.info(
        "      %d segments, total %.1fs narrated",
        len(segments),
        sum(s.duration_sec for s in segments),
    )
    return segments


def ensure_translation(
    segments: list[Segment], config: AppConfig, work_dir: Path, resume: bool
) -> list[Segment]:
    """Stage 3: translate (cached by segments_zh.json presence)."""
    zh_path = work_dir / "segments_zh.json"
    if zh_path.exists() and resume:
        log.info("[3/6] translate (cached)")
        return [Segment.from_dict(d) for d in json.loads(zh_path.read_text("utf-8"))]
    log.info("[3/6] translate")
    segments = translate.translate(segments, config.translate, config.env)
    zh_path.write_text(
        json.dumps([s.to_dict() for s in segments], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return segments


def run_pipeline(
    input_path: Path,
    voice: str,
    config: Optional[AppConfig] = None,
    resume: bool = True,
    keep_original_audio: bool = False,
    sample_seconds: Optional[float] = None,
) -> Path:
    """Run the full pipeline; returns the output mkv path."""
    config = config or load_config()
    input_path = input_path.resolve()

    if voice not in config.voices:
        raise ValueError(
            f"unknown voice preset '{voice}'. available: {list(config.voices)}"
        )
    voice_preset: VoicePreset = config.voices[voice]

    work_dir = work_dir_for(input_path, config, voice)
    ctx = JobContext(input_path=input_path, work_dir=work_dir, voice=voice)
    log.info("processing %s (work_dir: %s)", input_path.name, work_dir.name)

    # ---- Stage 1: extract ----
    ctx.audio = ensure_audio(input_path, config, work_dir, resume)

    # ---- Stage 2: transcribe ----
    ctx.segments = ensure_transcript(ctx.audio, config, work_dir, resume)

    # ---- Stage 3: translate ----
    ctx.segments = ensure_translation(ctx.segments, config, work_dir, resume)

    # ---- Stage 4: tts ----
    clips_dir = work_dir / "tts_clips"
    expected = sum(1 for s in ctx.segments if s.text_zh)
    existing = list(clips_dir.glob("*.wav")) if clips_dir.exists() else []
    if len(existing) >= expected and expected > 0 and resume:
        log.info("[4/6] tts (cached %d clips)", len(existing))
        ctx.tts_clips = {int(p.stem): p for p in existing}
    else:
        log.info("[4/6] tts (%d clips)", expected)
        ctx.tts_clips = tts.tts(
            ctx.segments, voice_preset, config.tts, config.env, work_dir
        )

    # ---- Stage 5: mix ----
    mixed_path = work_dir / "zh_audio.wav"
    if mixed_path.exists() and resume:
        log.info("[5/6] mix (cached)")
    else:
        log.info("[5/6] mix")
        mix.mix_audio(ctx.audio, ctx.segments, ctx.tts_clips, config.mix, work_dir)
    ctx.mixed_audio = mixed_path

    # ---- Stage 6: mux ----
    output_suffix = ".sample.mkv" if sample_seconds else ".zh.mkv"
    output_path = config.pipeline.output_dir / f"{input_path.stem}{output_suffix}"
    if output_path.exists() and resume:
        log.info("[6/6] mux (cached)")
    else:
        log.info("[6/6] mux")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        mux.mux_track(
            input_path,
            ctx.mixed_audio,
            config.mux,
            output_path,
            keep_original_audio=keep_original_audio,
            sample_seconds=sample_seconds,
        )
    ctx.output_path = output_path

    log.info("done: %s", output_path)
    return output_path
