#!/usr/bin/env python3
from __future__ import annotations

import os
import json
import re
import difflib
from datetime import datetime, UTC
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Tuple, Optional, List

import click

from noorlytics.settings import get_settings
from noorlytics.llm_interface import LLMClient, render_progress, render_markdown_cli
from noorlytics.analyze_dependencies import (
    analyze_dependencies_file,
    render_notes_cli,
    render_vulns_cli,
)
from noorlytics.add_tests import generate_unit_tests, render_tests_cli, _detect_language_from_extension
from noorlytics.refactor_executor import RefactorPlanParser, DependencyGraph
from noorlytics.file_rewriter import FileRewriter, BackupManager
from noorlytics.git_integration import GitIntegration

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


def _has_real_dependency(depends_on: Optional[str]) -> bool:
    """Return True when a dependency string points to an actual prior change."""
    return bool(depends_on and not depends_on.lower().startswith("none"))


def _save_and_print(text: str, out_path: Path, header: str | None = None):
    """Write UTF-8 file and render it in the terminal."""
    generated_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%SZ")
    stamped_text = f"Generated: {generated_at}\n\n{text.lstrip()}"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(stamped_text, encoding="utf-8")
    render_markdown_cli(header or out_path.name, stamped_text, out_path)


def _next_versioned_markdown_path(reports_dir: Path, stem: str) -> Path:
    """Return the next versioned Markdown report path for a logical report stem."""
    legacy_path = reports_dir / f"{stem}.md"
    pattern = re.compile(rf"^{re.escape(stem)}\.v(\d+)\.md$")
    max_version = 1 if legacy_path.exists() else 0

    for path in reports_dir.glob(f"{stem}.v*.md"):
        match = pattern.match(path.name)
        if match:
            max_version = max(max_version, int(match.group(1)))

    return reports_dir / f"{stem}.v{max_version + 1}.md"


def _ansi_strikethrough(text: str) -> str:
    """Render strikethrough using ANSI escape codes when supported."""
    return f"\x1b[9m{text}\x1b[0m"


def _render_change_code_block(change, indent: str = "         ") -> None:
    """Render a styled code-block diff for a refactor change in the terminal."""
    before_lines = change.before_code.splitlines()
    after_lines = change.after_code.splitlines()
    diff_lines = list(difflib.ndiff(before_lines, after_lines))
    visible_lines = [line[2:] for line in diff_lines if line[:2] != "? "]
    max_width = max((len(line) for line in visible_lines), default=0)

    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.text import Text

        console = Console(force_terminal=True, highlight=False)
        block = Text()

        for line in diff_lines:
            prefix = line[:2]
            content = line[2:]
            padded = content.ljust(max_width)

            if prefix == "- ":
                block.append("- ", style="bold red")
                block.append(padded, style="red strike")
            elif prefix == "+ ":
                block.append("+ ", style="bold #8BC34A")
                block.append(padded, style="black on #8BC34A")
            elif prefix == "? ":
                continue
            else:
                block.append("  ", style="dim")
                block.append(padded, style="white")

            block.append("\n")

        if block.plain.endswith("\n"):
            block = block[:-1]

        console.print(
            Panel(
                block,
                title="Code Change",
                title_align="left",
                border_style="bright_blue",
                padding=(0, 1),
            )
        )
    except Exception:
        click.echo(f"{indent}```python")
        for line in diff_lines:
            prefix = line[:2]
            content = line[2:]
            padded = content.ljust(max_width)

            if prefix == "- ":
                click.echo(f"{indent}{click.style('- ', fg='red')}{click.style(_ansi_strikethrough(padded), fg='red')}")
            elif prefix == "+ ":
                click.echo(f"{indent}{click.style('+ ', fg='bright_green')}{click.style(padded, fg='black', bg='#8BC34A')}")
            elif prefix == "  ":
                click.echo(f"{indent}  {padded}")

        click.echo(f"{indent}```")


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

    settings_ext = getattr(S, "allowed_ext", (".py",))
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
    """Analyze technical debt in a file or directory (package)."""
    client = state.ensure_client()

    files = (
        list(_iter_code_files(path, state.allowed_ext, state.max_file_bytes))
        if path.is_dir()
        else list(_single_file(path, state.allowed_ext, state.max_file_bytes))
    )

    if not files:
        click.echo(click.style("⚠️  No matching files found.", fg="yellow"))
        raise SystemExit(2)

    # Summary for package mode
    if path.is_dir() and len(files) > 1:
        click.echo(click.style(f"📦 Analyzing package: {path.name}", fg="cyan"))
        click.echo(click.style(f"   Found {len(files)} files to analyze", fg="blue"))
        click.echo()

    analyzed_count = 0
    failed_count = 0

    with render_progress("Analyzing code…") as prog:
        t = prog.add_task("run", total=len(files))
        for fpath, content in files:
            try:
                report_md = client.analyze_text(fpath.name, content)
                out = _next_versioned_markdown_path(state.reports_dir, f"{fpath.name}.analyze")
                
                # For single files, show full output; for packages, show summary
                if not (path.is_dir() and len(files) > 1):
                    _save_and_print(report_md, out, header=fpath.name)
                else:
                    # Just save without rendering full output in package mode
                    out.parent.mkdir(parents=True, exist_ok=True)
                    generated_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%SZ")
                    stamped_text = f"Generated: {generated_at}\n\n{report_md.lstrip()}"
                    out.write_text(stamped_text, encoding="utf-8")
                    
                    rel_path = fpath.relative_to(path)
                    click.echo(click.style(f"   ✅ {rel_path} → {out.name}", fg="green"))
                
                analyzed_count += 1
            except Exception as e:
                click.echo(click.style(f"   ❌ {fpath.relative_to(path)}: {e}", fg="red"))
                failed_count += 1
            finally:
                prog.advance(t)

    # Summary for package mode
    if path.is_dir() and len(files) > 1:
        click.echo()
        click.echo(click.style(f"✨ Analyzed {analyzed_count} file(s) in reports/ folder", fg="green"))
        if failed_count > 0:
            click.echo(click.style(f"   {failed_count} file(s) failed", fg="yellow"))


@cli.command("suggest")
@click.argument("path", required=True, type=click.Path(exists=True, path_type=Path))
@click.pass_obj
def suggest_cmd(state: CLIState, path: Path):
    """Generate improvement and refactoring suggestions for file or package."""
    client = state.ensure_client()

    files = (
        list(_iter_code_files(path, state.allowed_ext, state.max_file_bytes))
        if path.is_dir()
        else list(_single_file(path, state.allowed_ext, state.max_file_bytes))
    )

    if not files:
        click.echo(click.style("⚠️  No matching files found.", fg="yellow"))
        raise SystemExit(2)

    # Summary for package mode
    if path.is_dir() and len(files) > 1:
        click.echo(click.style(f"📦 Generating suggestions for: {path.name}", fg="cyan"))
        click.echo(click.style(f"   Found {len(files)} files to process", fg="blue"))
        click.echo()

    generated_count = 0
    failed_count = 0

    with render_progress("Generating suggestions…") as prog:
        t = prog.add_task("run", total=len(files))
        for fpath, content in files:
            try:
                md = client.suggest_refactors(fpath.name, content)
                out = _next_versioned_markdown_path(state.reports_dir, f"{fpath.name}.suggest")
                
                # For single files, show full output; for packages, show summary
                if not (path.is_dir() and len(files) > 1):
                    _save_and_print(md, out, header=fpath.name)
                else:
                    # Just save without rendering full output in package mode
                    out.parent.mkdir(parents=True, exist_ok=True)
                    generated_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%SZ")
                    stamped_text = f"Generated: {generated_at}\n\n{md.lstrip()}"
                    out.write_text(stamped_text, encoding="utf-8")
                    
                    rel_path = fpath.relative_to(path)
                    click.echo(click.style(f"   ✅ {rel_path} → {out.name}", fg="green"))
                
                generated_count += 1
            except Exception as e:
                click.echo(click.style(f"   ❌ {fpath.relative_to(path)}: {e}", fg="red"))
                failed_count += 1
            finally:
                prog.advance(t)

    # Summary for package mode
    if path.is_dir() and len(files) > 1:
        click.echo()
        click.echo(click.style(f"✨ Generated suggestions for {generated_count} file(s) in reports/ folder", fg="green"))
        if failed_count > 0:
            click.echo(click.style(f"   {failed_count} file(s) failed", fg="yellow"))


@cli.command("add-tests")
@click.argument("path", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--lang", "--language", "lang",
              type=click.Choice(["python", "js", "ts", "java", "go", "csharp", "ruby", "cpp", "c", "php"]),
              default=None,
              help="Programming language. If omitted, auto-detects from file extension.")
@click.pass_obj
def add_tests_cmd(state: CLIState, path: Path, lang: str):
    """Generate unit test stubs for a file or directory (package)."""
    # Collect all candidate files (handles both single files and entire packages)
    candidates = (
        sorted([p for p in path.rglob("*")
         if p.is_file() and p.suffix.lower() in state.allowed_ext and not any(part in DEFAULT_IGNORE_DIRS for part in p.parts)])
        if path.is_dir()
        else ([path] if (path.is_file() and path.suffix.lower() in state.allowed_ext) else [])
    )

    if not candidates:
        click.echo(click.style("⚠️  No matching files found.", fg="yellow"))
        raise SystemExit(2)

    # Summary for package mode
    if path.is_dir() and len(candidates) > 1:
        click.echo(click.style(f"📦 Processing package: {path.name}", fg="cyan"))
        click.echo(click.style(f"   Found {len(candidates)} files to generate tests for", fg="blue"))
        click.echo()

    generated_count = 0
    failed_count = 0

    with render_progress("Generating test stubs…") as prog:
        t = prog.add_task("run", total=len(candidates))
        for fpath in candidates:
            try:
                # Auto-detect language if not provided
                language_hint = lang or _detect_language_from_extension(fpath)
                out_path = generate_unit_tests(fpath, mode=state.mode, language_hint=language_hint)
                
                # For single files, show full output; for packages, show summary
                if not (path.is_dir() and len(candidates) > 1):
                    render_tests_cli(out_path)
                else:
                    # Just show a brief indication in package mode
                    rel_path = fpath.relative_to(path)
                    click.echo(click.style(f"   ✅ {rel_path} → {out_path.relative_to(out_path.parent.parent)}", fg="green"))
                
                generated_count += 1
            except Exception as e:
                click.echo(click.style(f"   ❌ {fpath.relative_to(path)}: {e}", fg="red"))
                failed_count += 1
            finally:
                prog.advance(t)

    # Summary for package mode
    if path.is_dir() and len(candidates) > 1:
        click.echo()
        click.echo(click.style(f"✨ Generated {generated_count} test files in tests/ folder", fg="green"))
        if failed_count > 0:
            click.echo(click.style(f"   {failed_count} file(s) failed", fg="yellow"))


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
        out_md = _next_versioned_markdown_path(state.reports_dir, f"{manifest.name}.deps")
        _save_and_print(notes_md, out_md, header=f"{manifest.name} – dependencies")



@cli.command("refactor")
@click.argument("path", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--apply", "-a", is_flag=True, help="Apply safe (LOW-priority) refactoring changes automatically. Short form: -a.")
@click.option("--dry-run", "-dr", is_flag=True, help="Show diffs without modifying files. Short form: -dr.")
@click.option("--interactive", "-i", is_flag=True, help="Prompt for confirmation on each change. Short form: -i.")
@click.option("--undo", "-u", is_flag=True, help="Restore last refactoring changes from backup. Short form: -u.")
@click.option("--git-commit", "-gc", is_flag=True, help="Stage and commit changes to git after applying. Short form: -gc.")
@click.pass_obj
def refactor_cmd(state: CLIState, path: Path, apply: bool, dry_run: bool, interactive: bool, undo: bool, git_commit: bool):
    """Create AI-assisted refactor plans for file or package.

        Short flags: `-a`, `-dr`, `-i`, `-u`, `-gc`.

        \b
        Examples:
            noor refactor file.py
            noor refactor file.py -dr
            noor refactor file.py -i
            noor refactor file.py -a
            noor refactor file.py -u
            noor refactor file.py -i -gc
    """
    
    # Handle --undo flag
    if undo:
        _undo_refactoring(path)
        return
    
    client = state.ensure_client()

    files = (
        list(_iter_code_files(path, state.allowed_ext, state.max_file_bytes))
        if path.is_dir()
        else list(_single_file(path, state.allowed_ext, state.max_file_bytes))
    )

    if not files:
        click.echo(click.style("⚠️  No matching files found.", fg="yellow"))
        raise SystemExit(2)

    # Summary
    if path.is_dir() and len(files) > 1:
        mode_str = "dry-run" if dry_run else "interactive" if interactive else "apply" if apply else "planning"
        click.echo(click.style(f"📦 Refactoring {path.name} ({mode_str} mode)...", fg="cyan"))
        click.echo(click.style(f"   Found {len(files)} files", fg="blue"))
        click.echo()

    applied_count = 0
    failed_count = 0

    with render_progress("Generating refactor plans…") as prog:
        t = prog.add_task("run", total=len(files))
        for fpath, content in files:
            try:
                # Generate plan
                md = client.refactor(fpath.name, content)
                
                # Parse changes
                parser = RefactorPlanParser(md)
                changes = parser.parse()
                
                if not changes:
                    click.echo(click.style(f"   ⚠️  {fpath.name}: No structured changes found", fg="yellow"))
                    prog.advance(t)
                    continue
                
                # Save plan markdown (sorted by priority)
                plan_out = _next_versioned_markdown_path(state.reports_dir, f"{fpath.name}.refactor")
                generated_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%SZ")
                plan_out.parent.mkdir(parents=True, exist_ok=True)
                # Use regenerated markdown (sorted HIGH → MEDIUM → LOW)
                sorted_markdown = parser.to_markdown()
                plan_out.write_text(f"Generated: {generated_at}\n\n{sorted_markdown}", encoding="utf-8")
                
                # Handle different modes
                if dry_run:
                    _show_dry_run(fpath, changes)
                    applied_count += 1
                elif interactive:
                    if _interactive_apply(fpath, changes, state.reports_dir, git_commit):
                        applied_count += 1
                elif apply:
                    if _auto_apply(fpath, changes, state.reports_dir, git_commit):
                        applied_count += 1
                else:
                    # Default: just show plan
                    if not (path.is_dir() and len(files) > 1):
                        _save_and_print(md, plan_out, header=fpath.name)
                    else:
                        click.echo(click.style(f"   ✅ {fpath.name} → {plan_out.name}", fg="green"))
                    applied_count += 1
                
            except Exception as e:
                click.echo(click.style(f"   ❌ {fpath.name}: {e}", fg="red"))
                failed_count += 1
            finally:
                prog.advance(t)

    # Summary
    if path.is_dir() and len(files) > 1:
        click.echo()
        if apply or interactive:
            click.echo(click.style(f"✨ Applied refactors to {applied_count} file(s)", fg="green"))
        elif dry_run:
            click.echo(click.style(f"📋 Showed diffs for {applied_count} file(s)", fg="blue"))
        else:
            click.echo(click.style(f"✨ Created refactor plans for {applied_count} file(s) in reports/", fg="green"))
        
        if failed_count > 0:
            click.echo(click.style(f"   {failed_count} file(s) failed", fg="yellow"))


# -------------------- Refactor Helper Functions --------------------

def _show_dry_run(fpath: Path, changes: List) -> None:
    """Display diffs without applying changes."""
    click.echo(click.style(f"\n🔍 Dry-run for {fpath.name}:", fg="cyan"))
    for i, change in enumerate(changes, 1):
        click.echo(f"  [{i}] {change.display_title()} ({change.priority.value})")
        if change.problem_statement:
            click.echo(f"      {change.problem_statement}")
        _render_change_code_block(change, indent="      ")
        click.echo()
    click.echo()


def _interactive_apply(fpath: Path, changes: List, reports_dir: Path, git_commit: bool = False) -> bool:
    """Prompt user for each change before applying with smart dependency handling.
    
    Groups changes by dependency chains. When a user approves a change,
    all dependent changes are automatically included and applied together.
    
    Args:
        fpath: Path to file to refactor
        changes: List of refactoring changes to apply
        reports_dir: Directory to save diff reports
        git_commit: If True, stage and commit changes to git after applying
    
    Returns:
        True if changes were applied, False otherwise
    """
    # Build dependency graph
    graph = DependencyGraph(changes)
    chains = graph.group_by_chains()
    
    # Preview state tracks approved changes so later validations reflect the
    # same staged content that final application will see.
    preview = FileRewriter(fpath)
    # Applicator: collects changes to apply
    applicator = FileRewriter(fpath)
    
    approved_changes = []
    processed_indices = set()
    
    for chain_idx, chain in enumerate(chains, 1):
        if all(idx in processed_indices for idx in chain):
            continue  # Already processed this chain
        
        # Show chain header if it's a multi-change chain
        if len(chain) > 1:
            click.echo(click.style(f"\n📦 Dependency Chain {chain_idx}:", fg="magenta"))
            click.echo(f"   {graph.get_chain_summary(chain)}\n")
        
        chain_approved = False
        
        for idx in chain:
            if idx in processed_indices:
                continue
            
            change = changes[idx]
            position = f"[{idx+1}/{len(changes)}]"
            
            click.echo(f"\n{position} [{change.priority.value}] {change.display_title()}")
            note = change.display_note()
            if note:
                click.echo(f"   {click.style(note, fg='blue')}")
            click.echo(f"   Problem: {change.problem_statement}")
            if _has_real_dependency(change.depends_on):
                click.echo(f"   📌 Depends on: {change.depends_on}")
            
            # Show a unified diff preview matching the final apply rendering.
            click.echo()
            _render_change_code_block(change, indent="   ")
            click.echo()
            
            # Check if code blocks are complete
            if not change.is_complete():
                click.echo(click.style("   ⚠️  Code snippet appears truncated or incomplete", fg="yellow"))
                click.echo(click.style("   (Contains '...' or unbalanced brackets/quotes)", fg="yellow"))
                response = click.confirm("   Try to apply anyway?", default=False)
                if not response:
                    click.echo(click.style("   ⏭️  Skipping (incomplete code)", fg="yellow"))
                    processed_indices.add(idx)
                    continue
            
            # Validate against the staged preview state so sequential approvals
            # can build on earlier approved changes.
            can_apply = False
            dry_run_content = preview._apply_change_with_flexible_match(
                change.before_code,
                change.after_code,
                preview.current_content,
            )
            if dry_run_content is not None and dry_run_content != preview.current_content:
                can_apply = True
            elif preview._find_rebased_before_code(change.before_code, change.after_code) is not None:
                can_apply = True
            elif preview._find_with_flexible_match(change.after_code, preview.current_content):
                can_apply = True
            if not can_apply:
                if _has_real_dependency(change.depends_on):
                    click.echo(click.style(f"   ⚠️  Code not found in current staged file state (depends on: {change.depends_on})", fg="yellow"))
                else:
                    click.echo(click.style("   ⚠️  Code not found in current staged file state (may conflict with earlier changes)", fg="yellow"))
            
            # Show chain implications
            dependents = graph.get_all_dependents(idx, include_self=False)
            if dependents:
                dependent_titles = [changes[d].display_title() for d in dependents]
                click.echo(click.style(f"   ⛓️  Approving this will also apply: {', '.join(dependent_titles[:2])}", fg="cyan"))
                if len(dependent_titles) > 2:
                    click.echo(click.style(f"      + {len(dependent_titles)-2} more", fg="cyan"))
            
            response = click.confirm("   Apply this change?", default=True)
            if response and can_apply:
                newly_approved = [change]
                # Add this change and all its dependents
                approved_changes.append(change)
                processed_indices.add(idx)
                
                # Add all dependents automatically
                for dep_idx in dependents:
                    if dep_idx not in processed_indices:
                        dep_change = changes[dep_idx]
                        approved_changes.append(dep_change)
                        newly_approved.append(dep_change)
                        processed_indices.add(dep_idx)
                        click.echo(click.style(f"   ⛓️  Auto-including dependent: {dep_change.display_title()}", fg="cyan"))

                preview.apply_all_changes(newly_approved)
                
                chain_approved = True
                click.echo(click.style("   ✅ Approved (including dependents)", fg="green"))
            elif response and not can_apply:
                click.echo(click.style("   ⏭️  Skipping (code not found)", fg="yellow"))
                processed_indices.add(idx)
            else:
                processed_indices.add(idx)
    
    if approved_changes:
        click.echo()
        if click.confirm(f"Write {len(approved_changes)} changes to {fpath.name}?", default=True):
            try:
                # Apply all approved changes atomically
                successful, failed, failure_details = applicator.apply_all_changes(approved_changes)
                
                if successful > 0:
                    applicator.write()
                    _save_diff_report(fpath, applicator, reports_dir)
                    click.echo(click.style(f"✨ Applied {successful}/{len(approved_changes)} changes to {fpath.name}", fg="green"))
                    
                    # Handle git integration if requested
                    if git_commit and GitIntegration.is_git_repo(fpath):
                        if GitIntegration.stage_file(fpath):
                            commit_msg = f"refactor: {fpath.name} - {successful} change(s) applied via noorlytics"
                            if GitIntegration.commit(commit_msg, fpath.parent):
                                click.echo(click.style(f"✅ Committed changes to git", fg="green"))
                            else:
                                click.echo(click.style(f"⚠️  Staged file but commit failed", fg="yellow"))
                        else:
                            click.echo(click.style(f"⚠️  Failed to stage file in git", fg="yellow"))
                    elif git_commit:
                        click.echo(click.style(f"⚠️  Not in a git repository - skipping commit", fg="yellow"))
                    
                    if failed > 0:
                        click.echo(click.style(f"\n   ⚠️  {failed} change(s) could not be applied:", fg="yellow"))
                        for idx, change in enumerate(approved_changes[successful:]):
                            reason = failure_details.get(successful + idx, "Code not found in file")
                            click.echo(f"      ❌ {change.display_title()}")
                            _render_change_code_block(change)
                            click.echo(f"         Reason: {reason}")
                    
                    return True
                else:
                    click.echo(click.style(f"❌ No changes could be applied", fg="red"))
                    return False
            except Exception as e:
                click.echo(click.style(f"❌ Failed to write changes: {e}", fg="red"))
                return False
    else:
        click.echo(click.style("   No changes applied", fg="yellow"))
        return False
    
    return False


def _auto_apply(fpath: Path, changes: List, reports_dir: Path, git_commit: bool = False) -> bool:
    """Automatically apply safe (LOW priority) changes with smart dependency grouping.
    
    Groups safe changes by dependency chains and applies them together.
    When a safe change is applied, all its dependents are automatically applied too.
    
    Args:
        fpath: Path to file to refactor
        changes: List of refactoring changes
        reports_dir: Directory to save diff reports
        git_commit: If True, stage and commit changes to git after applying
    
    Returns:
        True if changes were applied, False otherwise
    """
    # Build dependency graph
    graph = DependencyGraph(changes)
    
    rewriter = FileRewriter(fpath)
    
    # Separate changes by priority
    safe_changes = [c for c in changes if c.is_safe()]
    unsafe_changes = [c for c in changes if not c.is_safe()]
    
    if not changes:
        click.echo(click.style(f"   ℹ️  No refactors found for {fpath.name}", fg="blue"))
        return False
    
    # Print header with change summary
    click.echo(click.style(f"\n   📋 Refactoring Plan for {fpath.name}:", fg="cyan"))
    click.echo(click.style(f"      Total suggestions: {len(changes)} | Safe (LOW): {len(safe_changes)} | Review needed: {len(unsafe_changes)}", fg="blue"))
    click.echo()
    
    if not safe_changes:
        click.echo(click.style(f"   ℹ️  No LOW-priority (safe) changes to auto-apply", fg="blue"))
        if unsafe_changes:
            click.echo(click.style(f"      {len(unsafe_changes)} change(s) require review (use --interactive)", fg="yellow"))
        return False
    
    # Check for incomplete code blocks before applying
    incomplete_changes = [c for c in safe_changes if not c.is_complete()]
    complete_safe_changes = [c for c in safe_changes if c.is_complete()]
    
    # Group complete safe changes by dependency chains for display only.
    safe_chains = []
    for chain in graph.group_by_chains():
        safe_chain = [idx for idx in chain if changes[idx].is_safe() and changes[idx].is_complete()]
        if safe_chain:
            safe_chains.append(safe_chain)

    # Apply changes in their original plan order. Group-flattening can reorder
    # independent steps after later dependency chains, which breaks stale-snippet
    # rebasing when a later change expects an earlier rename from the same block.
    ordered_complete_safe_changes = complete_safe_changes

    # Try to apply only complete safe changes in chain order.
    successful, failed, failure_details = rewriter.apply_all_changes(ordered_complete_safe_changes)
    
    # Display changes with dependency grouping
    displayed = set()
    
    for chain_indices in safe_chains:
        # Show chain header for multi-change chains
        if len(chain_indices) > 1:
            click.echo(click.style(f"   📦 Dependency Chain:", fg="magenta"))
            click.echo(f"      {graph.get_chain_summary(chain_indices)}")
            click.echo()
    
    # Display all changes in organized manner
    for i, change in enumerate(changes, 1):
        if i-1 in displayed:
            continue
        
        is_safe = change.is_safe()
        status_icon = "✅" if is_safe else "⏭️"
        priority = change.priority.value if hasattr(change, 'priority') else "UNKNOWN"
        
        # Check if incomplete
        if change in incomplete_changes:
            click.echo(f"   ⏭️  [{i}] {change.display_title()} ({priority})")
            click.echo(f"      ⏭️  SKIPPED: Code snippet is truncated/incomplete")
            if _has_real_dependency(getattr(change, 'depends_on', None)):
                click.echo(f"      📌 Depends on: {change.depends_on}")
            click.echo()
        elif not is_safe:
            click.echo(f"   {status_icon} [{i}] {change.display_title()} ({priority})")
            click.echo(f"      ⏸️  SKIPPED: Not a safe change (use --interactive to review)")
            if _has_real_dependency(getattr(change, 'depends_on', None)):
                click.echo(f"      📌 Depends on: {change.depends_on}")
            click.echo()
        
        displayed.add(i-1)
    
    # Now report on applied vs failed
    if successful > 0:
        try:
            rewriter.write()
            _save_diff_report(fpath, rewriter, reports_dir)
            
            # Show applied changes
            click.echo(click.style(f"   ✨ Successfully applied {successful} change(s):", fg="green"))
            for change in complete_safe_changes[:successful]:
                click.echo(f"      ✅ {change.display_title()}")
                note = change.display_note()
                if note:
                    click.echo(f"         {click.style(note, fg='blue')}")
                _render_change_code_block(change)
                if _has_real_dependency(getattr(change, 'depends_on', None)):
                    click.echo(f"         📌 Depends on: {change.depends_on}")
            
            if incomplete_changes:
                click.echo(click.style(f"\n   ⚠️  {len(incomplete_changes)} change(s) skipped (incomplete/truncated):", fg="yellow"))
                for change in incomplete_changes:
                    click.echo(f"      ⏭️ {change.display_title()}")
                    click.echo(f"         Code snippet contains truncation markers ('...')")
            
            if failed > 0:
                click.echo(click.style(f"\n   ⚠️  {failed} change(s) could not be applied:", fg="yellow"))
                for idx, change in enumerate(complete_safe_changes[successful:]):
                    reason = failure_details.get(successful + idx, "Code not found in file")
                    click.echo(f"      ❌ {change.display_title()}")
                    note = change.display_note()
                    if note:
                        click.echo(f"         {click.style(note, fg='blue')}")
                    _render_change_code_block(change)
                    click.echo(f"         Reason: {reason}")
            
            # Handle git integration if requested
            if git_commit and GitIntegration.is_git_repo(fpath):
                if GitIntegration.stage_file(fpath):
                    commit_msg = f"refactor: {fpath.name} - {successful} change(s) applied via noorlytics"
                    if GitIntegration.commit(commit_msg, fpath.parent):
                        click.echo(click.style(f"✅ Committed changes to git", fg="green"))
                    else:
                        click.echo(click.style(f"⚠️  Staged file but commit failed", fg="yellow"))
                else:
                    click.echo(click.style(f"⚠️  Failed to stage file in git", fg="yellow"))
            elif git_commit:
                click.echo(click.style(f"⚠️  Not in a git repository - skipping commit", fg="yellow"))
            
            click.echo()
            return True
        except Exception as e:
            click.echo(click.style(f"   ❌ Failed to write changes: {e}", fg="red"))
            return False
    
    if failed > 0 or incomplete_changes:
        if incomplete_changes:
            click.echo(click.style(f"   ⚠️  {len(incomplete_changes)} change(s) skipped (incomplete/truncated)", fg="yellow"))
            for change in incomplete_changes:
                click.echo(f"      ⏭️ {change.display_title()}")
        
        if failed > 0:
            click.echo(click.style(f"   ⚠️  All {failed} complete safe change(s) failed to apply", fg="yellow"))
            for idx, change in enumerate(complete_safe_changes):
                if idx in failure_details:
                    reason = failure_details[idx]
                    click.echo(f"      ❌ {change.display_title()}")
                    note = change.display_note()
                    if note:
                        click.echo(f"         {click.style(note, fg='blue')}")
                    _render_change_code_block(change)
                    click.echo(f"         Reason: {reason}")
    
    return False



def _undo_refactoring(path: Path) -> None:
    """Restore from backup."""
    backup_dir = path.parent / ".noor_backups" if path.is_file() else path / ".noor_backups"
    
    if not backup_dir.exists():
        click.echo(click.style("❌ No backups found", fg="red"))
        return
    
    # Find most recent backup
    manager = BackupManager(backup_dir)
    latest_backup = manager.get_latest_backup(path.name)
    
    if not latest_backup:
        click.echo(click.style(f"❌ No backups found for {path.name}", fg="red"))
        return
    
    if manager.restore_from_backup(path, latest_backup):
        click.echo(click.style(f"✅ Restored {path.name} from {latest_backup.name}", fg="green"))
    else:
        click.echo(click.style(f"❌ Failed to restore {path.name}", fg="red"))


def _save_diff_report(fpath: Path, rewriter: FileRewriter, reports_dir: Path) -> None:
    """Save diff report for applied changes."""
    diff = rewriter.get_diff()
    diff_path = reports_dir / f"{fpath.name}.refactor.diff"
    diff_path.parent.mkdir(parents=True, exist_ok=True)
    diff_path.write_text(diff, encoding="utf-8")


# -------------------- Git Command (Standalone) --------------------

@cli.command("git")
@click.argument("file", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--commit", "-c", type=str, default=None, 
              help="Commit message. If provided, stages and commits the file.")
@click.option("--status", "-s", is_flag=True, help="Show git status for the repository.")
@click.option("--branch", "-b", is_flag=True, help="Show current branch name.")
def git_cmd(file: Path, commit: Optional[str], status: bool, branch: bool):
    """Manage git operations independently (no refactor needed).
    
    \b
    Examples:
        noor git myfile.py --status
        noor git myfile.py -s
        noor git myfile.py --branch
        noor git myfile.py -b
        noor git myfile.py --commit "my changes"
        noor git myfile.py -c "my changes"
    """
    
    # Check if in a git repo
    if not GitIntegration.is_git_repo(file):
        click.echo(click.style(f"❌ Not in a git repository: {file}", fg="red"))
        return
    
    work_dir = file.parent if file.is_file() else file
    
    # Show branch
    if branch:
        current_branch = GitIntegration.get_current_branch(work_dir)
        click.echo(click.style(f"📌 Current branch: {current_branch or 'unknown'}", fg="cyan"))
    
    # Show status
    if status:
        git_status = GitIntegration.get_status(work_dir)
        if git_status:
            click.echo(click.style("📊 Git status:", fg="cyan"))
            click.echo(git_status)
        else:
            click.echo(click.style("✅ Working directory is clean", fg="green"))
    
    # Stage and commit
    if commit:
        if file.is_file():
            if GitIntegration.stage_file(file, work_dir):
                click.echo(click.style(f"✅ Staged: {file.name}", fg="green"))
                
                if GitIntegration.commit(commit, work_dir):
                    click.echo(click.style(f"✅ Committed: {commit}", fg="green"))
                else:
                    click.echo(click.style(f"⚠️  Staged but commit failed", fg="yellow"))
            else:
                click.echo(click.style(f"❌ Failed to stage: {file.name}", fg="red"))
        else:
            click.echo(click.style(f"❌ File not found: {file}", fg="red"))


# -------------------- Entrypoint --------------------

if __name__ == "__main__":
    cli()