"""Configuration loading.

Three sources merged into AppConfig:
  - YAML files in ./config/ (defaults + voice presets)
  - .env file (API keys & secrets)
  - Optional override YAML via --config flag
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# ----- Stage configs (from YAML) -----


class PipelineConfig(BaseModel):
    cache_dir: Path = Path(".dub-cache")
    output_dir: Path = Path("./output")


class ExtractConfig(BaseModel):
    sample_rate: int = 16000
    mono: bool = True


class ASRConfig(BaseModel):
    provider: str = "dashscope"
    model: str = "paraformer-v2"
    language_hints: list[str] = Field(default_factory=lambda: ["en"])


class TranslateConfig(BaseModel):
    provider: str = "deepseek"
    model: str = "deepseek-chat"
    temperature: float = 0.3
    max_chars_per_second: float = 3.5
    context_window: int = 8


class TTSConfig(BaseModel):
    provider: str = "minimax"
    model: str = "speech-01-turbo"
    audio_format: str = "wav"
    sample_rate: int = 24000


class MixConfig(BaseModel):
    bg_attenuation_db: float = -12.0
    sample_rate: int = 48000


class MuxConfig(BaseModel):
    language: str = "chi"
    title: str = "Chinese (AI Dubbed)"
    set_default: bool = False


class VoicePreset(BaseModel):
    provider: str
    voice_id: str
    speed: float = 1.0
    vol: float = 1.0
    pitch: int = 0


# ----- Env-sourced secrets -----


class EnvSettings(BaseSettings):
    """Loaded from .env or process environment."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    deepseek_api_key: str = ""

    dashscope_api_key: str = ""
    oss_access_key_id: str = ""
    oss_access_key_secret: str = ""
    oss_bucket_name: str = ""
    oss_region: str = "oss-cn-hangzhou"
    oss_endpoint: str = "oss-cn-hangzhou.aliyuncs.com"
    oss_key_prefix: str = "dub-cache/"

    minimax_api_key: str = ""
    minimax_group_id: str = ""


# ----- Combined config -----


@dataclass
class AppConfig:
    pipeline: PipelineConfig = field(default_factory=PipelineConfig)
    extract: ExtractConfig = field(default_factory=ExtractConfig)
    asr: ASRConfig = field(default_factory=ASRConfig)
    translate: TranslateConfig = field(default_factory=TranslateConfig)
    tts: TTSConfig = field(default_factory=TTSConfig)
    mix: MixConfig = field(default_factory=MixConfig)
    mux: MuxConfig = field(default_factory=MuxConfig)
    voices: dict[str, VoicePreset] = field(default_factory=dict)
    env: EnvSettings = field(default_factory=EnvSettings)


def config_dir() -> Path:
    """Resolve the YAML config directory.

    Override with DUB_CONFIG_DIR env var; otherwise ./config relative to CWD.
    """
    env = os.environ.get("DUB_CONFIG_DIR")
    if env:
        return Path(env).expanduser().resolve()
    return Path.cwd() / "config"


def load_config(override: Optional[Path] = None) -> AppConfig:
    """Load defaults, voices, optional override YAML, and env secrets."""

    def _load_yaml(path: Path) -> dict:
        if not path.exists():
            return {}
        with open(path) as f:
            return yaml.safe_load(f) or {}

    cdir = config_dir()
    merged: dict = {}
    merged.update(_load_yaml(cdir / "default.yaml"))
    if override:
        merged.update(_load_yaml(override))

    voices_raw = _load_yaml(cdir / "voices.yaml")
    voices = {name: VoicePreset(**vc) for name, vc in voices_raw.items()}

    return AppConfig(
        pipeline=PipelineConfig(**merged.get("pipeline", {})),
        extract=ExtractConfig(**merged.get("extract", {})),
        asr=ASRConfig(**merged.get("asr", {})),
        translate=TranslateConfig(**merged.get("translate", {})),
        tts=TTSConfig(**merged.get("tts", {})),
        mix=MixConfig(**merged.get("mix", {})),
        mux=MuxConfig(**merged.get("mux", {})),
        voices=voices,
        env=EnvSettings(),
    )
