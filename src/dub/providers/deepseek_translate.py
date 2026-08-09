"""DeepSeek translation provider.

DeepSeek exposes an OpenAI-compatible chat API, so we use the openai SDK
pointed at api.deepseek.com. This makes swapping to Qwen-Max or GLM-4
(which also expose OpenAI-compatible endpoints) trivial.
"""
from __future__ import annotations

import json
import logging

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from ..config import EnvSettings, TranslateConfig
from ..models import Segment

log = logging.getLogger(__name__)

DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"

SYSTEM_PROMPT = """You are a professional documentary narrator translator. Translate English narration into natural, fluent Mandarin Chinese suitable for voiceover.

Style guidelines:
- Documentary tone: evocative, measured, slightly formal, never colloquial
- Prefer concise Chinese that fits the original timing budget
- Preserve technical terms (species names, place names); transliterate sensibly
- Each input segment produces exactly one output segment

You receive segments with target durations. Aim for ≤{chars_per_sec} Chinese chars per second of the original duration so the TTS engine can read it without rushing."""


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=20))
def translate_batch(
    segments: list[Segment],
    cfg: TranslateConfig,
    env: EnvSettings,
) -> list[str]:
    """Translate a batch of segments, return Chinese strings in input order."""
    if not env.deepseek_api_key:
        raise ValueError("DEEPSEEK_API_KEY not set")

    client = OpenAI(api_key=env.deepseek_api_key, base_url=DEEPSEEK_BASE_URL)

    input_data = [
        {"id": s.id, "en": s.text_src, "duration_sec": round(s.duration_sec, 1)}
        for s in segments
    ]

    user_msg = (
        f"Translate the following {len(segments)} English narration segments to "
        f"Mandarin Chinese. Each segment has a target duration; produce Chinese "
        f"that fits within {cfg.max_chars_per_second} chars/sec of that duration.\n\n"
        f'Output JSON: {{"translations":[{{"id":0,"zh":"中文"}}]}}\n\n'
        f"Input:\n{json.dumps(input_data, ensure_ascii=False, indent=2)}"
    )

    response = client.chat.completions.create(
        model=cfg.model,
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT.format(chars_per_sec=cfg.max_chars_per_second),
            },
            {"role": "user", "content": user_msg},
        ],
        temperature=cfg.temperature,
        response_format={"type": "json_object"},
    )

    text = response.choices[0].message.content or ""
    data = json.loads(text)
    by_id = {item["id"]: item["zh"] for item in data.get("translations", [])}
    return [by_id.get(s.id, "") for s in segments]


def translate(
    segments: list[Segment],
    cfg: TranslateConfig,
    env: EnvSettings,
) -> list[Segment]:
    """Translate in context-windowed batches; mutates segments in place."""
    if not segments:
        return segments

    window = max(1, cfg.context_window)
    for start in range(0, len(segments), window):
        batch = segments[start : start + window]
        log.info("translating segments %d-%d", batch[0].id, batch[-1].id)
        zh_texts = translate_batch(batch, cfg, env)
        for seg, zh in zip(batch, zh_texts):
            seg.text_zh = zh

    return segments
