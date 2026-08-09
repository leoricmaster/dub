"""Stage: mux the mixed Chinese audio back into the container.

Strategies:
  - "lean"   : drop original audio tracks; output = video + subtitles + chinese.
               Smallest output. Use when disk is tight or you only need Chinese.
  - "all"    : keep all original streams + add chinese track. Largest output.
               Use when you want to compare/switch tracks in the same file.

Optional sample mode: stop after N seconds. Good for quick acceptance or when
full output is too large for the disk.
"""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

from ..config import MuxConfig

log = logging.getLogger(__name__)


def _probe_streams(input_path: Path) -> list[dict]:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "stream=index,codec_type:stream_tags=language",
        "-of", "json",
        str(input_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(result.stdout).get("streams", [])


def mux_track(
    input_path: Path,
    mixed_audio: Path,
    cfg: MuxConfig,
    output_path: Path,
    *,
    keep_original_audio: bool = False,
    sample_seconds: float | None = None,
) -> Path:
    """Mux mixed audio into the original container.

    Args:
        keep_original_audio: if True, keep all original audio streams (larger output).
            If False (default), drop original audio — output has video + subtitles
            + the new Chinese track only.
        sample_seconds: if set, stop after this many seconds of video (sample mode).
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    streams = _probe_streams(input_path)

    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(input_path),
        "-i", str(mixed_audio),
    ]

    # Map: video + subtitles (skip audio if not keeping original)
    new_audio_idx = 0  # stream index within output audio numbering
    for s in streams:
        ctype = s.get("codec_type")
        if ctype == "audio":
            if keep_original_audio:
                cmd.extend(["-map", f"0:{s['index']}"])
                new_audio_idx += 1
            # else: skip
        elif ctype in ("video", "subtitle", "data", "attachment"):
            cmd.extend(["-map", f"0:{s['index']}"])

    # Map the new Chinese audio
    cmd.extend(["-map", "1:a:0"])

    if sample_seconds is not None:
        cmd.extend(["-t", str(sample_seconds)])

    cmd.extend([
        "-c", "copy",                              # copy originals
        f"-c:a:{new_audio_idx}", "aac",            # encode new audio
        f"-b:a:{new_audio_idx}", "192k",
        f"-metadata:s:a:{new_audio_idx}", f"language={cfg.language}",
        f"-metadata:s:a:{new_audio_idx}", f"title={cfg.title}",
    ])

    if cfg.set_default:
        cmd.extend([f"-disposition:a:{new_audio_idx}", "default"])

    cmd.append(str(output_path))

    log.info(
        "mux: keep_original_audio=%s, sample=%ss, new audio at index %d",
        keep_original_audio, sample_seconds, new_audio_idx,
    )
    subprocess.run(cmd, check=True)
    return output_path
