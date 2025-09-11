#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, List, Tuple

import click

from noorlytics.settings import get_settings
from noorlytics.llm_interface import LLMClient, render_progress
from noorlytics.analyze_dependencies import analyze_dependencies_file


IGNORE_DIRS = {
    ".git", ".hg", ".svn", "__pycache__", "node_modules", "dist", "build",
    ".venv", "venv", ".mypy_cache", ".pytest_cache", ".idea", ".vscode",
}


def _save_and_print(text: str, out_path: Path, header: str | None = None):
    """Save results to file (UTF-8) and also print them to the terminal."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")
    if header:
        click.echo(click.style(f"\n=== {header} ===", fg="cyan", bold=True))
        click.echo(click.style(f"→ saved to {out_path}", fg="green", dim=True))
    click.echo(click.style(text, fg="white"))


def _iter_code_files(root: Path, allowed_ext: set[str], max_bytes: int) -> Iterable[Tuple[Path, str]]:
    """Yield code files from a directory tree, skipping ignored dirs and oversized files."""
    for path in root.rglob("*"):
        if path.is_dir():
            if path.name in IGNORE_DIRS:
                continue
            if any(ignored in path.parts for ignored in IGNORE_DIRS):
                continue
            continue
        if path.suffix.lower() not in allowed_ext:
            continue
        try:
            if path.stat().st_size > max_bytes:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            yield path, text
        except Exception:
            continue


def _single_file(path: Path, allowed_ext: set[str], max_bytes: int) -> Iterable[Tuple[Path, str]]:
    """Return a single file’s content if it matches extension and size limits."""
    if path.suffix.lower() not in allowed_ext:
        return []
    if path.stat().st_size > max_bytes:
        return []
    text = path.read_text(encoding="utf-8", errors="ignore")
    return [(path, text)]


@click.group()
def cli():
    """Noorlytics CLI — Analyze tech debt, suggest refactors, generate tests, and audit dependencies."""
    pass


@cli.command("analyze")
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option("--mode", type=click.Choice(["ollama", "openai"]), default=None, help="Which LLM backend to use.")
def analyze_cmd(path: Path, mode: str | None):
    """Analyze technical debt in code files (Markdown reports in reports/)."""
    S = get_settings()
    client = LLMClient(mode=mode)
    client.warmup()

    files: List[Tuple[Path, str]]
    if path.is_dir():
        click.echo(click.style(f"📁 Collecting files in: {path}", fg="blue"))
        files = list(_iter_code_files(path, set(S.allowed_ext), S.max_file_bytes))
    else:
        click.echo(click.style(f"📄 Analyzing file: {path}", fg="blue"))
        files = list(_single_file(path, set(S.allowed_ext), S.max_file_bytes))

    if not files:
        click.echo(click.style("⚠️ No files matched your filters (.env → NOOR_ALLOWED_EXT and NOOR_MAX_FILE_BYTES).", fg="yellow"))
        return

    with render_progress("Analyzing…") as prog:
        t = prog.add_task("run", total=len(files))
        for fpath, content in files:
            report_md = client.analyze_text(fpath.name, content)
            out = S.reports_dir / f"{fpath.name}.analyze.md"
            _save_and_print(report_md, out, header=fpath.name)
            prog.advance(t)

    click.echo(click.style(f"📝 Reports saved to {S.reports_dir.resolve()}", fg="green", bold=True))


@cli.command("suggest")
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option("--mode", type=click.Choice(["ollama", "openai"]), default=None)
def suggest_cmd(path: Path, mode: str | None):
    """Suggest refactorings for file(s)."""
    S = get_settings()
    client = LLMClient(mode=mode)
    client.warmup()

    files: List[Tuple[Path, str]]
    if path.is_dir():
        click.echo(click.style(f"📁 Collecting files in: {path}", fg="blue"))
        files = list(_iter_code_files(path, set(S.allowed_ext), S.max_file_bytes))
    else:
        click.echo(click.style(f"📄 Suggestions for: {path}", fg="blue"))
        files = list(_single_file(path, set(S.allowed_ext), S.max_file_bytes))

    if not files:
        click.echo(click.style("⚠️ No files matched your filters.", fg="yellow"))
        return

    with render_progress("Suggesting refactors…") as prog:
        t = prog.add_task("run", total=len(files))
        for fpath, content in files:
            md = client.suggest_refactors(fpath.name, content)
            out = S.reports_dir / f"{fpath.name}.refactor.md"
            _save_and_print(md, out, header=fpath.name)
            prog.advance(t)

    click.echo(click.style(f"📝 Suggestions saved to {S.reports_dir.resolve()}", fg="green", bold=True))


@cli.command("add-tests")
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option("--mode", type=click.Choice(["ollama", "openai"]), default=None)
@click.option("--lang", default="python", help="Language hint for the test generator (e.g., python, js, ts, java).")
def add_tests_cmd(path: Path, mode: str | None, lang: str):
    """Generate unit test stubs for file(s)."""
    S = get_settings()
    client = LLMClient(mode=mode)
    client.warmup()

    # Collect files
    if path.is_dir():
        click.echo(click.style(f"📁 Collecting files in: {path}", fg="blue"))
        files = list(_iter_code_files(path, set(S.allowed_ext), S.max_file_bytes))
    else:
        click.echo(click.style(f"📄 Generating tests for: {path}", fg="blue"))
        files = list(_single_file(path, set(S.allowed_ext), S.max_file_bytes))

    if not files:
        click.echo(click.style("⚠️ No files matched your filters.", fg="yellow"))
        return

    with render_progress("Generating unit tests…") as prog:
        t = prog.add_task("run", total=len(files))
        for fpath, content in files:
            # Ask LLM to create tests
            tests_code = client.generate_tests(fpath.name, content, language_hint=lang)

            # Save to reports/<filename>.tests.py (so you can actually run them with pytest/unittest)
            out = S.reports_dir / f"{fpath.stem}.tests.py"
            _save_and_print(tests_code, out, header=f"{fpath.name}")

            prog.advance(t)

    click.echo(click.style(f"🧪 Unit test stubs saved to {S.reports_dir.resolve()}", fg="green", bold=True))


@cli.command("analyze-deps")
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option("--mode", type=click.Choice(["ollama", "openai"]), default=None)
def analyze_deps_cmd(path: Path, mode: str | None):
    """Analyze dependency files (requirements.txt, package.json, pyproject.toml)."""
    S = get_settings()
    client = LLMClient(mode=mode)
    client.warmup()

    if path.is_dir():
        candidates = []
        for name in ("requirements.txt", "pyproject.toml", "package.json"):
            candidates.extend(Path(path).rglob(name))
        if not candidates:
            click.echo(click.style("⚠️ No dependency files found.", fg="yellow"))
            return
        targets = candidates
    else:
        targets = [path]

    with render_progress("Analyzing dependencies…") as prog:
        t = prog.add_task("run", total=len(targets))
        for p in targets:
            res = analyze_dependencies_file(p, client)
            out = S.reports_dir / f"{p.name}.deps.json"
            _save_and_print(json.dumps(res, indent=2, ensure_ascii=False), out, header=p.name)
            prog.advance(t)

    click.echo(click.style(f"📦 Dependency analyses saved to {S.reports_dir.resolve()}", fg="green", bold=True))


@cli.command("refactor")
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option("--mode", type=click.Choice(["ollama", "openai"]), default=None)
def refactor_cmd(path: Path, mode: str | None):
    """
    WIP: Same output format as 'suggest' (Markdown).
    Next step is to generate actual patch files, but for now it's safe text only.
    """
    S = get_settings()
    client = LLMClient(mode=mode)
    client.warmup()

    files: List[Tuple[Path, str]]
    if path.is_dir():
        click.echo(click.style(f"📁 Collecting files in: {path}", fg="blue"))
        files = list(_iter_code_files(path, set(S.allowed_ext), S.max_file_bytes))
    else:
        click.echo(click.style(f"📄 Refactor for: {path}", fg="blue"))
        files = list(_single_file(path, set(S.allowed_ext), S.max_file_bytes))

    if not files:
        click.echo(click.style("⚠️ No files matched your filters.", fg="yellow"))
        return

    with render_progress("Drafting refactor plan…") as prog:
        t = prog.add_task("run", total=len(files))
        for fpath, content in files:
            md = client.suggest_refactors(fpath.name, content)
            out = S.reports_dir / f"{fpath.name}.refactor.md"
            _save_and_print(md, out, header=fpath.name)
            prog.advance(t)

    click.echo(click.style(f"🛠️ Refactor plan saved to {S.reports_dir.resolve()}", fg="green", bold=True))


if __name__ == "__main__":
    cli()