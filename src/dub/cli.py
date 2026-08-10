"""dub CLI entry point."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

from . import __version__, pipeline
from .config import load_config

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
    out = pipeline.run_pipeline(
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

    Useful for checking translation quality before paying for TTS. Reuses the
    same cache as `dub zh`, so repeat previews are free.
    """
    cfg = load_config(config)
    if voice not in cfg.voices:
        raise typer.BadParameter(
            f"unknown voice '{voice}'. available: {list(cfg.voices)}"
        )

    work_dir = pipeline.work_dir_for(input, cfg, voice)
    audio = pipeline.ensure_audio(input, cfg, work_dir, resume=True)
    segments = pipeline.ensure_transcript(audio, cfg, work_dir, resume=True)
    segments = pipeline.ensure_translation(segments, cfg, work_dir, resume=True)

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
