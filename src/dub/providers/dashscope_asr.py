"""Aliyun DashScope Paraformer-v2 ASR.

Flow for long audio:
  1. Upload audio to OSS (signed URL, 1h expiry)
  2. Submit async transcription job
  3. Poll for completion (typically 1-3 min for 50 min audio)
  4. Fetch transcription JSON from result URL
  5. Clean up OSS object

Docs:
  https://help.aliyun.com/document_detail/90727.html  (Paraformer file ASR)
  https://help.aliyun.com/zh/oss/  (Python SDK)
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Callable

import httpx
import oss2
from tenacity import retry, stop_after_attempt, wait_exponential

from ..config import ASRConfig, EnvSettings
from ..models import Segment

log = logging.getLogger(__name__)

DASHSCOPE_BASE = "https://dashscope.aliyuncs.com/api/v1"
DEFAULT_POLL_INTERVAL_SEC = 5
DEFAULT_TIMEOUT_SEC = 1800  # 30 min, enough for 2-hour audio


def upload_audio_to_oss(
    file_path: Path,
    env: EnvSettings,
    expiry_seconds: int = 3600,
) -> tuple[str, Callable[[], None]]:
    """Upload to OSS, return (signed_url, cleanup_fn)."""
    auth = oss2.Auth(env.oss_access_key_id, env.oss_access_key_secret)
    bucket = oss2.Bucket(auth, env.oss_endpoint, env.oss_bucket_name)

    key = f"{env.oss_key_prefix.rstrip('/')}/{file_path.name}"
    log.info("uploading %s to oss://%s/%s", file_path.name, env.oss_bucket_name, key)
    bucket.put_object_from_file(key, str(file_path))
    signed = bucket.sign_url("GET", key, expiry_seconds)

    def cleanup() -> None:
        try:
            bucket.delete_object(key)
            log.info("cleaned oss://%s/%s", env.oss_bucket_name, key)
        except Exception as e:
            log.warning("oss cleanup failed: %s", e)

    return signed, cleanup


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=20))
def submit_transcription(file_url: str, cfg: ASRConfig, api_key: str) -> str:
    """Submit ASR job, return task_id."""
    resp = httpx.post(
        f"{DASHSCOPE_BASE}/services/audio/asr/transcription",
        headers={
            "Authorization": f"Bearer {api_key}",
            "X-DashScope-Async": "enable",
            "Content-Type": "application/json",
        },
        json={
            "model": cfg.model,
            "input": {"file_urls": [file_url]},
            "parameters": {
                "language_hints": cfg.language_hints,
                "disfluency_removal_enabled": True,
            },
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["output"]["task_id"]


def poll_transcription(
    task_id: str,
    api_key: str,
    poll_interval: int = DEFAULT_POLL_INTERVAL_SEC,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
) -> dict:
    """Poll until SUCCEEDED, return full task response."""
    deadline = time.time() + timeout_sec
    last_status = None
    while time.time() < deadline:
        resp = httpx.get(
            f"{DASHSCOPE_BASE}/tasks/{task_id}",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        status = data["output"]["task_status"]
        if status != last_status:
            log.info("asr task %s -> %s", task_id, status)
            last_status = status
        if status == "SUCCEEDED":
            return data
        if status == "FAILED":
            raise RuntimeError(f"ASR task failed: {data}")
        time.sleep(poll_interval)
    raise TimeoutError(f"ASR task {task_id} did not finish within {timeout_sec}s")


def fetch_transcription_result(result_url: str) -> dict:
    """Download the transcription JSON from the result URL."""
    resp = httpx.get(result_url, timeout=60)
    resp.raise_for_status()
    return resp.json()


def parse_sentences(transcription: dict) -> list[Segment]:
    """Convert Paraformer output to a flat list of Segments."""
    segments: list[Segment] = []
    seg_id = 0
    for transcript in transcription.get("transcripts", []):
        for sentence in transcript.get("sentences", []):
            segments.append(
                Segment(
                    id=seg_id,
                    text_src=sentence["text"].strip(),
                    start_ms=int(sentence["begin_time"]),
                    end_ms=int(sentence["end_time"]),
                )
            )
            seg_id += 1
    return segments


def transcribe(
    audio_path: Path,
    cfg: ASRConfig,
    env: EnvSettings,
    work_dir: Path | None = None,
) -> list[Segment]:
    """Full pipeline: upload -> submit -> poll -> fetch -> parse -> cleanup.

    If work_dir is provided, the raw transcription JSON is cached there as
    `asr_raw.json`. Re-runs reuse the cached raw result instead of paying
    for another ASR call (useful when parsing/processing bugs cause a crash
    after the API call but before persistence).
    """
    if not env.dashscope_api_key:
        raise ValueError("DASHSCOPE_API_KEY not set")
    if not env.oss_bucket_name:
        raise ValueError("OSS_BUCKET_NAME not set")

    raw_cache = work_dir / "asr_raw.json" if work_dir else None
    if raw_cache and raw_cache.exists():
        log.info("reusing cached ASR raw result from %s", raw_cache)
        import json

        transcription = json.loads(raw_cache.read_text("utf-8"))
        return parse_sentences(transcription)

    signed_url, cleanup = upload_audio_to_oss(audio_path, env)
    try:
        task_id = submit_transcription(signed_url, cfg, env.dashscope_api_key)
        result = poll_transcription(task_id, env.dashscope_api_key)
        results = result["output"].get("results", [])
        if not results or "transcription_url" not in results[0]:
            raise RuntimeError(f"ASR result missing transcription_url: {result}")
        transcription_url = results[0]["transcription_url"]
        transcription = fetch_transcription_result(transcription_url)
    finally:
        cleanup()

    if raw_cache:
        import json

        raw_cache.write_text(
            json.dumps(transcription, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        log.info("cached ASR raw result to %s", raw_cache)

    return parse_sentences(transcription)
