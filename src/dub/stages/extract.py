"""Stage: extract audio from video/audio container."""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Optional

from ..config import ExtractConfig
from ..models import AudioTrack

log = logging.getLogger(__name__)


def _probe_audio_streams(input_path: Path) -> list[dict]:
    """Return list of {index, language} for every audio stream in input."""
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "a",
        "-show_entries", "stream=index:stream_tags=language",
        "-of", "json",
        str(input_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(result.stdout).get("streams", [])


def _pick_audio_stream(streams: list[dict], input_path: Path, preferred_lang: str = "eng") -> int:
    """Pick the audio stream index. Prefer preferred_lang; else first."""
    for s in streams:
        if s.get("tags", {}).get("language") == preferred_lang:
            return int(s["index"])
    if streams:
        log.warning(
            "no '%s' audio stream found, falling back to first audio (langs: %s)",
            preferred_lang,
            [s.get("tags", {}).get("language") for s in streams],
        )
        return int(streams[0]["index"])
    raise RuntimeError(f"no audio streams in {input_path}")


def extract_audio(
    input_path: Path,
    cfg: ExtractConfig,
    work_dir: Path,
    preferred_lang: Optional[str] = "eng",
) -> AudioTrack:
    """Extract audio as 16-bit PCM wav at the configured sample rate."""
    out_path = work_dir / "audio.wav"
    if not out_path.exists():
        streams = _probe_audio_streams(input_path)
        if preferred_lang:
            stream_idx = _pick_audio_stream(streams, input_path, preferred_lang)
            log.info("using audio stream index %d (lang=%s)",
                     stream_idx,
                     streams[[i for i, s in enumerate(streams) if int(s['index']) == stream_idx][0]]
                     .get("tags", {}).get("language"))
            map_arg = f"0:{stream_idx}"
        else:
            map_arg = "0:a:0"

        channels = "1" if cfg.mono else "2"
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(input_path),
            "-map", map_arg,
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", str(cfg.sample_rate),
            "-ac", channels,
            str(out_path),
        ]
        subprocess.run(cmd, check=True)

    return AudioTrack(
        path=out_path,
        sample_rate=cfg.sample_rate,
        channels=1 if cfg.mono else 2,
    )
