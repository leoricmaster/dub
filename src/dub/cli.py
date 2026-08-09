"""dub CLI entry point."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

from . import __version__
from .cache import Cache, input_hash
from .config import load_config
from .models import Segment
from .pipeline import _config_signature, run_pipeline
from .stages import extract as extract_stage
from .stages import transcribe as tr_stage
from .stages import translate as tl_stage

app = typer.Typer(
    no_args_is_help=True,
    help="Chinese AI dubbing pipeline for documentaries.",
    context_settings={"help_option_names": ["-h", "--help"]},
)
console = Console()


def _setup_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, show_path=False)],
    )


@app.callback()
def _root(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging"),
) -> None:
    _setup_logging(verbose)


@app.command()
def zh(
    input: Path = typer.Argument(..., exists=True, dir_okay=False, help="Input video/audio file"),
    voice: str = typer.Option("nature", help="Voice preset name (see `dub voices`)"),
    no_resume: bool = typer.Option(
        False, "--no-resume", help="Ignore cache, reprocess every stage from scratch"
    ),
    keep_original_audio: bool = typer.Option(
        False, "--keep-original-audio",
        help="Keep original audio tracks in output (larger file). Default: drop originals.",
    ),
    sample: Optional[float] = typer.Option(
        None, "--sample",
        help="Produce a sample clip of N seconds (for quick preview/acceptance).",
    ),
    config: Optional[Path] = typer.Option(None, "--config", help="Override YAML config path"),
) -> None:
    """Run the full pipeline and add a Chinese audio track to <input>."""
    cfg = load_config(config)
    if voice not in cfg.voices:
        raise typer.BadParameter(
            f"unknown voice '{voice}'. available: {list(cfg.voices)}"
        )
    out = run_pipeline(
        input,
        voice,
        cfg,
        resume=not no_resume,
        keep_original_audio=keep_original_audio,
        sample_seconds=sample,
    )
    console.print(f"\n[bold green]done[/bold green] -> {out}")


@app.command()
def translate(
    input: Path = typer.Argument(..., exists=True, dir_okay=False, help="Input video/audio file"),
    voice: str = typer.Option("nature", help="Voice preset (affects cache namespace only)"),
    config: Optional[Path] = typer.Option(None, "--config", help="Override YAML config path"),
) -> None:
    """Transcribe + translate only. Prints EN/ZH per segment, no audio output.

    Useful for checking translation quality before paying for TTS.
    """
    cfg = load_config(config)
    file_hash = input_hash(input, extra=voice)
    sig = _config_signature(cfg, voice)
    cache = Cache(cfg.pipeline.cache_dir)
    work_dir = cache.work_dir(f"{file_hash}-{sig}")

    audio = extract_stage.extract_audio(input, cfg.extract, work_dir)

    en_path = work_dir / "segments_en.json"
    if en_path.exists():
        segments = [Segment.from_dict(d) for d in json.loads(en_path.read_text("utf-8"))]
    else:
        segments = tr_stage.transcribe(audio, cfg.asr, cfg.env, work_dir)
        en_path.write_text(
            json.dumps([s.to_dict() for s in segments], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    segments = tl_stage.translate(segments, cfg.translate, cfg.env)
    zh_path = work_dir / "segments_zh.json"
    zh_path.write_text(
        json.dumps([s.to_dict() for s in segments], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    for seg in segments:
        console.print(
            f"[dim][{seg.start_ms / 1000:6.1f} – {seg.end_ms / 1000:6.1f}s][/dim]"
        )
        console.print(f"  EN: {seg.text_src}")
        console.print(f"  [bold]ZH: {seg.text_zh}[/bold]")


@app.command()
def voices(
    config: Optional[Path] = typer.Option(None, "--config", help="Override YAML config path"),
) -> None:
    """List configured voice presets."""
    cfg = load_config(config)
    table = Table(title="Voice Presets")
    table.add_column("Name", style="bold")
    table.add_column("Provider")
    table.add_column("Voice ID")
    table.add_column("Speed", justify="right")
    for name, v in cfg.voices.items():
        table.add_row(name, v.provider, v.voice_id, f"{v.speed:.2f}")
    console.print(table)


@app.command()
def version() -> None:
    """Print version."""
    console.print(f"dub {__version__}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
