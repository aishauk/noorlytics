#!/usr/bin/env python3
from __future__ import annotations

import os, click
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Tuple, Optional

import click

from noorlytics.settings import get_settings
from noorlytics.llm_interface import LLMClient, render_progress, render_markdown_cli
from noorlytics.analyze_dependencies import (
    analyze_dependencies_file,
    render_notes_cli,
    render_vulns_cli,
)
from noorlytics.add_tests import generate_unit_tests, render_tests_cli

# -------------------- Constants --------------------

DEFAULT_IGNORE_DIRS = {
    ".git", ".hg", ".svn", "__pycache__", "node_modules", "dist", "build",
    ".venv", "venv", ".mypy_cache", ".pytest_cache", ".idea", ".vscode",
}

CONTEXT_SETTINGS = dict(help_option_names=["-h", "--help"], max_content_width=100)


# -------------------- CLI State --------------------

@dataclass
class CLIState:
    mode: Optional[str]
    reports_dir: Path
    allowed_ext: set[str]
    max_file_bytes: int
    verbose: bool
    client: Optional[LLMClient] = None  # Lazy init

    def ensure_client(self) -> LLMClient:
        """Ensure an LLM client exists and is warmed up once per CLI session."""
        if self.client is None:
            self.client = LLMClient(mode=self.mode)
            try:
                self.client.warmup()
            except Exception as e:
                if self.verbose:
                    click.echo(click.style(f"⚠️  Model warmup warning: {e}", fg="yellow"))
        return self.client


# -------------------- Helper Functions --------------------

def _resolve_mode(cli_mode: Optional[str]) -> Optional[str]:
    """
    Resolve which LLM mode to use based on priority:
      1. CLI flag (--mode)
      2. Environment variable NOOR_MODE
      3. Settings.MODE or settings.mode
      4. None (let LLMClient decide default)
    """
    if cli_mode:
        return cli_mode
    env_mode = os.getenv("NOOR_MODE")
    if env_mode:
        return env_mode
    settings = get_settings()
    return getattr(settings, "MODE", None) or getattr(settings, "mode", None)


def _iter_code_files(root: Path, allowed_ext: set[str], max_bytes: int) -> Iterable[Tuple[Path, str]]:
    """Yield (path, text) for files in a directory tree that match filters."""
    for path in root.rglob("*"):
        if any(part in DEFAULT_IGNORE_DIRS for part in path.parts):
            continue
        if path.is_dir():
            continue
        if path.suffix.lower() not in allowed_ext:
            continue
        try:
            if path.stat().st_size > max_bytes:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            yield path, text
        except Exception:
            continue  # Skip unreadable files silently


def _single_file(path: Path, allowed_ext: set[str], max_bytes: int) -> Iterable[Tuple[Path, str]]:
    """Return a single (path, text) pair if valid, otherwise empty list."""
    if any(part in DEFAULT_IGNORE_DIRS for part in path.parts):
        return []
    if path.suffix.lower() not in allowed_ext:
        return []
    if path.stat().st_size > max_bytes:
        return []
    text = path.read_text(encoding="utf-8", errors="ignore")
    return [(path, text)]


def _save_and_print(text: str, out_path: Path, header: str | None = None):
    """Write UTF-8 file and render it in the terminal."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")
    render_markdown_cli(header or out_path.name, text, out_path)


# -------------------- CLI Root --------------------

@click.group(context_settings=CONTEXT_SETTINGS)
@click.option("--mode", type=click.Choice(["ollama", "openai"]), default=None,
              help="Choose LLM backend. If omitted, uses .env/settings value.")
@click.version_option(package_name="noorlytics", prog_name="noor")
@click.pass_context
def cli(ctx: click.Context, mode: Optional[str]):
    """
    Noorlytics CLI — AI-powered technical debt analysis, refactoring suggestions,
    unit test generation, and dependency audits.
    \f

    Examples:
      noor analyze project.py
      noor analyze .
      noor analyze-deps requirements.txt
    """
    S = get_settings()

    resolved_mode = _resolve_mode(mode)
    resolved_reports = getattr(S, "reports_dir", Path("reports"))
    if isinstance(resolved_reports, str):
        resolved_reports = Path(resolved_reports)

    settings_ext = getattr(S, "allowed_ext", [".py"])
    if isinstance(settings_ext, str):
        settings_ext = [settings_ext]
    resolved_ext = set(map(str.lower, settings_ext))

    resolved_max = getattr(S, "max_file_bytes", 400_000)

    ctx.obj = CLIState(
        mode=resolved_mode,
        reports_dir=resolved_reports,
        allowed_ext=resolved_ext,
        max_file_bytes=resolved_max,
        verbose=False,  # verbose tas bort som option → sätt default
    )

# -------------------- Commands --------------------

@cli.command("analyze")
@click.argument("path", required=True, type=click.Path(exists=True, path_type=Path))
@click.pass_obj
def analyze_cmd(state: CLIState, path: Path):
    """Analyze technical debt in a file or directory."""
    client = state.ensure_client()

    files = (
        list(_iter_code_files(path, state.allowed_ext, state.max_file_bytes))
        if path.is_dir()
        else list(_single_file(path, state.allowed_ext, state.max_file_bytes))
    )

    if not files:
        click.echo(click.style("⚠️  No matching files found.", fg="yellow"))
        raise SystemExit(2)

    with render_progress("Analyzing code…") as prog:
        t = prog.add_task("run", total=len(files))
        for fpath, content in files:
            report_md = client.analyze_text(fpath.name, content)
            out = state.reports_dir / f"{fpath.name}.analyze.md"
            _save_and_print(report_md, out, header=fpath.name)
            prog.advance(t)


@cli.command("suggest")
@click.argument("path", required=True, type=click.Path(exists=True, path_type=Path))
@click.pass_obj
def suggest_cmd(state: CLIState, path: Path):
    """Generate improvement and refactoring suggestions."""
    client = state.ensure_client()

    files = (
        list(_iter_code_files(path, state.allowed_ext, state.max_file_bytes))
        if path.is_dir()
        else list(_single_file(path, state.allowed_ext, state.max_file_bytes))
    )

    if not files:
        click.echo(click.style("⚠️  No matching files found.", fg="yellow"))
        raise SystemExit(2)

    with render_progress("Generating suggestions…") as prog:
        t = prog.add_task("run", total=len(files))
        for fpath, content in files:
            md = client.suggest_refactors(fpath.name, content)
            out = state.reports_dir / f"{fpath.name}.suggest.md"
            _save_and_print(md, out, header=fpath.name)
            prog.advance(t)


@cli.command("add-tests")
@click.argument("path", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--lang", "--language", "lang",
              type=click.Choice(["python", "js", "ts", "java", "go"]),
              default="python",
              help="Programming language hint for the test generator.")
@click.pass_obj
def add_tests_cmd(state: CLIState, path: Path, lang: str):
    """Generate unit test stubs for a file or directory."""
    candidates = (
        [p for p in path.rglob("*")
         if p.is_file() and p.suffix.lower() in state.allowed_ext and not any(part in DEFAULT_IGNORE_DIRS for part in p.parts)]
        if path.is_dir()
        else ([path] if (path.is_file() and path.suffix.lower() in state.allowed_ext) else [])
    )

    if not candidates:
        click.echo(click.style("⚠️  No matching files found.", fg="yellow"))
        raise SystemExit(2)

    with render_progress("Generating test stubs…") as prog:
        t = prog.add_task("run", total=len(candidates))
        for fpath in candidates:
            try:
                out_path = generate_unit_tests(fpath, mode=state.mode, language_hint=lang)
                render_tests_cli(out_path)
            except Exception as e:
                click.echo(click.style(f"❌  Failed to generate tests for {fpath}: {e}", fg="red"))
            finally:
                prog.advance(t)


@cli.command("analyze-deps")
@click.argument("manifest", required=True, type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.pass_obj
def analyze_deps_cmd(state: CLIState, manifest: Path):
    """Analyze a dependency manifest (requirements.txt, pyproject.toml, package.json)."""
    client = state.ensure_client()
    result = analyze_dependencies_file(manifest, client)

    # result är en dict med bl.a.:
    # - "notes_sections": {"Risks": [...], "Suggestions": [...]}
    # - "license_risk": [{"name": ..., "license": ..., "risk": ...}, ...]
    # - "known_vulns": [{...}, ...]
    # - "notes_md": "## Risks\n..."
    notes_sections = result.get("notes_sections") or {}
    license_risk = result.get("license_risk") or []
    known_vulns = result.get("known_vulns") or []

    # 1) Rendera licens- och risköversikt + text-notes i terminalen
    if notes_sections or license_risk:
        render_notes_cli(notes_sections, license_risk)

    # 2) Rendera kända sårbarheter i terminalen
    if known_vulns:
        render_vulns_cli(known_vulns)

    # 3) Spara JSON-rapport
    out_json = state.reports_dir / f"{manifest.name}.deps.json"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    click.echo(click.style(f"📝  Dependency JSON report saved → {out_json}", fg="green", bold=True))

    # 4) (Valfritt men nice) – spara en Markdown-rapport också
    notes_md = result.get("notes_md")
    if notes_md:
        out_md = state.reports_dir / f"{manifest.name}.deps.md"
        _save_and_print(notes_md, out_md, header=f"{manifest.name} – dependencies")



@cli.command("refactor")
@click.argument("path", required=True, type=click.Path(exists=True, path_type=Path))
@click.pass_obj
def refactor_cmd(state: CLIState, path: Path):
    """Create AI-assisted refactor plans in Markdown."""
    client = state.ensure_client()

    files = (
        list(_iter_code_files(path, state.allowed_ext, state.max_file_bytes))
        if path.is_dir()
        else list(_single_file(path, state.allowed_ext, state.max_file_bytes))
    )

    if not files:
        click.echo(click.style("⚠️  No matching files found.", fg="yellow"))
        raise SystemExit(2)

    with render_progress("Generating refactor plans…") as prog:
        t = prog.add_task("run", total=len(files))
        for fpath, content in files:
            md = client.suggest_refactors(fpath.name, content)
            out = state.reports_dir / f"{fpath.name}.refactor.md"
            _save_and_print(md, out, header=fpath.name)
            prog.advance(t)

# -------------------- Entrypoint --------------------

if __name__ == "__main__":
    cli()