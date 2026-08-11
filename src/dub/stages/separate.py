"""Stage: separate vocals from accompaniment (E7).

Splits the original soundtrack into vocals (the English narration) and
accompaniment (music/SFX). The mix stage uses the accompaniment as its bed so
no English speech bleeds through under the Chinese dub.

Implementation runs Demucs locally via ``python -m demucs --two-stems=vocals``
(mirroring how ``extract`` drives ffmpeg via subprocess). Demucs is an optional
dependency (``pip install -e '.[sep]'``); if it is missing or the run fails,
this stage returns ``None`` and ``mix`` falls back to whole-track attenuation.
"""
from __future__ import annotations

import importlib.util
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

from ..config import SeparateConfig
from .extract import _pick_audio_stream, _probe_audio_streams

log = logging.getLogger(__name__)


def _extract_hq(
    input_path: Path, cfg: SeparateConfig, out_path: Path, sample_seconds: float | None = None
) -> None:
    """Extract a high-quality stereo wav for separation.

    Distinct from the 16k mono ``audio.wav`` used for ASR — Demucs wants the
    full-bandwidth original. Reuses extract's stream-picking so the same audio
    track (preferred English) is separated as was transcribed.
    """
    streams = _probe_audio_streams(input_path)
    stream_idx = _pick_audio_stream(streams, input_path)
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(input_path),
        "-map", f"0:{stream_idx}",
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", str(cfg.sample_rate),
        "-ac", str(cfg.channels),
    ]
    if sample_seconds is not None:
        cmd += ["-t", str(sample_seconds)]
    cmd.append(str(out_path))
    subprocess.run(cmd, check=True)


def _demucs_available() -> bool:
    return importlib.util.find_spec("demucs") is not None


def separate(
    input_path: Path, cfg: SeparateConfig, work_dir: Path, sample_seconds: float | None = None
) -> Path | None:
    """Run two-stems separation; return the accompaniment path, or None on fallback.

    None means "no accompaniment available" — mix then attenuates the whole HQ
    track instead. The HQ extract (``audio_hq.wav``) is always produced so the
    fallback bed is still full-bandwidth.
    """
    accompaniment = work_dir / "accompaniment.wav"
    if accompaniment.exists():
        log.info("[5/7] separate (cached)")
        return accompaniment

    work_dir.mkdir(parents=True, exist_ok=True)

    # HQ bed is useful even on fallback, so extract it regardless.
    hq_path = work_dir / "audio_hq.wav"
    if not hq_path.exists():
        log.info("[5/7] extract HQ audio for separation")
        _extract_hq(input_path, cfg, hq_path, sample_seconds)

    if not cfg.enabled:
        log.info("[5/7] separate disabled -> mix will attenuate the HQ track")
        return None

    if not _demucs_available():
        log.warning(
            "[5/7] demucs not installed (pip install -e '.[sep]') -> "
            "falling back to whole-track attenuation"
        )
        return None

    out_dir = work_dir / "demucs"
    log.info(
        "[5/7] demucs %s (two_stems=%s, device=%s)",
        cfg.model, cfg.two_stems, cfg.device,
    )
    cmd = [
        sys.executable, "-m", "demucs",
        "--two-stems", cfg.two_stems,
        "-n", cfg.model,
        "--device", cfg.device,
        "-o", str(out_dir),
        str(hq_path),
    ]
    # Route HuggingFace model downloads through a reachable mirror (China-friendly).
    env = dict(os.environ)
    if cfg.hf_endpoint:
        env["HF_ENDPOINT"] = cfg.hf_endpoint
    try:
        subprocess.run(cmd, check=True, env=env)
    except subprocess.CalledProcessError as e:
        log.warning(
            "[5/7] demucs failed (rc=%d); falling back to attenuation. "
            "Tip: verify the CUDA/torch install or set separate.device=cpu.",
            e.returncode,
        )
        return None

    # Demucs writes <out_dir>/<model>/<trackstem>/no_vocals.wav
    candidates = list(out_dir.rglob("no_vocals.wav"))
    if not candidates:
        log.warning("[5/7] demucs produced no no_vocals.wav -> falling back")
        return None
    shutil.move(str(candidates[0]), str(accompaniment))
    shutil.rmtree(out_dir, ignore_errors=True)  # drop bulky intermediate stems
    return accompaniment
