"""dub CLI entry point."""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

from . import __version__, pipeline, voice_preview
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
    sample: float | None = typer.Option(
        None, "--sample",
        help="Produce a sample clip of N seconds (for quick preview/acceptance).",
    ),
    config: Path | None = typer.Option(None, "--config", help="Override YAML config path"),
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
    config: Path | None = typer.Option(None, "--config", help="Override YAML config path"),
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
    config: Path | None = typer.Option(None, "--config", help="Override YAML config path"),
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


@app.command(name="preview-voices")
def preview_voices(
    voices: str = typer.Option(
        ",".join(voice_preview.DEFAULT_PREVIEW_VOICES), "--voices",
        help="Comma-separated candidate voice_ids.",
    ),
    emotions: str = typer.Option(
        ",".join(voice_preview.DEFAULT_PREVIEW_EMOTIONS), "--emotions",
        help="Comma-separated emotions, e.g. calm,fluent.",
    ),
    speed: float = typer.Option(
        0.92, "--speed",
        help="Speech rate applied to every sample (keep equal for fair A/B).",
    ),
    text: str | None = typer.Option(
        None, "--text", help="Override the built-in preview narration line.",
    ),
    config: Path | None = typer.Option(None, "--config", help="Override YAML config path"),
) -> None:
    """Synthesise a fixed narration across voice x emotion candidates for A/B by ear.

    Low-cost judgement experiment: writes one wav per combo under
    output/voice-previews/<timestamp>/ and prints a table. Invalid voice_ids
    are skipped. After listening, pin the winner into config/voices.yaml.
    """
    cfg = load_config(config)
    voice_ids = [v.strip() for v in voices.split(",") if v.strip()]
    emo_list = [e.strip() for e in emotions.split(",") if e.strip()]
    matrix = voice_preview.expand_matrix(voice_ids, emo_list)

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = cfg.pipeline.output_dir / "voice-previews" / ts
    console.print(f"[dim]synthesising {len(matrix)} samples -> {out_dir}[/dim]")

    results = voice_preview.synthesize_previews(
        matrix, text or voice_preview.PREVIEW_TEXT, speed, cfg.tts, cfg.env, out_dir
    )
    console.print(results and voice_preview.results_table(results))

    ok = [r for r in results if r.status == "ok"]
    console.print(
        f"\n[bold]next:[/bold] listen to the {len(ok)} ok sample(s) under {out_dir}, "
        "pick the one that sounds most like a BBC Chinese documentary, and "
        "edit config/voices.yaml -> nature."
    )
    console.print("\n[dim]# paste into config/voices.yaml -> nature:[/dim]")
    console.print(voice_preview.nature_yaml_template(speed))


@app.command()
def version() -> None:
    """Print version."""
    console.print(f"dub {__version__}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
