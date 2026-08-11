"""MiniMax T2A-01 text-to-speech provider.

MiniMax T2A v2 returns audio as a hex-encoded string in `data.audio`
for non-streaming requests. Group ID is passed as a URL query param.

Docs: https://platform.minimaxi.com/document/T2A%20V2
"""
from __future__ import annotations

import logging
from pathlib import Path

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from ..config import EnvSettings, TTSConfig, VoicePreset
from ..models import Segment

log = logging.getLogger(__name__)

MINIMAX_T2A_URL = "https://api.minimaxi.com/v1/t2a_v2"


@retry(stop=stop_after_attempt(6), wait=wait_exponential(min=2, max=30))
def synthesize_one(
    text: str,
    voice: VoicePreset,
    cfg: TTSConfig,
    env: EnvSettings,
    out_path: Path,
) -> Path:
    if not env.minimax_api_key:
        raise ValueError("MINIMAX_API_KEY not set")
    if not env.minimax_group_id:
        raise ValueError("MINIMAX_GROUP_ID not set")

    voice_setting = {
        "voice_id": voice.voice_id,
        "speed": voice.speed,
        "vol": voice.vol,
        "pitch": voice.pitch,
    }
    if voice.emotion is not None:
        voice_setting["emotion"] = voice.emotion

    payload: dict = {
        "model": cfg.model,
        "text": text,
        "stream": False,
        "voice_setting": voice_setting,
        "audio_setting": {
            "sample_rate": cfg.sample_rate,
            "format": cfg.audio_format,
        },
    }
    if voice.language_boost is not None:
        # Top-level param (sibling of voice_setting), biases a target language.
        payload["language_boost"] = voice.language_boost

    resp = httpx.post(
        f"{MINIMAX_T2A_URL}?GroupId={env.minimax_group_id}",
        headers={
            "Authorization": f"Bearer {env.minimax_api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()

    audio_field = data.get("data", {}).get("audio")
    if not audio_field:
        raise RuntimeError(f"MiniMax T2A returned no audio: {data}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(bytes.fromhex(audio_field))
    return out_path


def synthesize(
    segments: list[Segment],
    voice: VoicePreset,
    cfg: TTSConfig,
    env: EnvSettings,
    work_dir: Path,
) -> dict[int, Path]:
    """Synthesize each segment with Chinese text. Returns {segment_id: clip_path}."""
    clips_dir = work_dir / "tts_clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    paths: dict[int, Path] = {}
    for seg in segments:
        if not seg.text_zh:
            log.warning("segment %d has no Chinese text, skipping TTS", seg.id)
            continue
        clip_path = clips_dir / f"{seg.id:05d}.wav"
        if clip_path.exists():
            log.info("tts clip %d cached", seg.id)
        else:
            preview = seg.text_zh[:30].replace("\n", " ")
            log.info("synthesizing segment %d: %s", seg.id, preview)
            synthesize_one(seg.text_zh, voice, cfg, env, clip_path)
        paths[seg.id] = clip_path

    return paths
