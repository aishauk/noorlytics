#!/usr/bin/env python3
from __future__ import annotations

import os
import json
import re
import difflib
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    transform_analysis_to_findings,
)
from noorlytics.findings import FindingsCollection
from noorlytics.assessment import (
    AssessmentEngine,
    CustomerContext,
)
from noorlytics.add_tests import generate_unit_tests, render_tests_cli, _detect_language_from_extension
from noorlytics.gdpr import scan_gdpr_violations
from noorlytics.audit_security import scan_audit_security
from noorlytics.scan_standards import scan_standards, check_dependency_standards
from noorlytics.unified_scan import UnifiedScanner, FindingCategory
from noorlytics.refactor_executor import RefactorPlanParser, DependencyGraph
from noorlytics.file_rewriter import FileRewriter, BackupManager
from noorlytics.git_integration import GitIntegration

# Import new CLI modules for Phase 3
from noorlytics.cli.decisions import decisions
from noorlytics.cli.history import history
from noorlytics.cli.metrics import metrics

# -------------------- Constants --------------------

DEFAULT_IGNORE_DIRS = {
    ".git", ".hg", ".svn", "__pycache__", "node_modules", "dist", "build",
    ".venv", "venv", ".mypy_cache", ".pytest_cache", ".idea", ".vscode",
}

CONTEXT_SETTINGS = dict(help_option_names=["-h", "--help"], max_content_width=100)

# Default template path (relative to noorlytics package)
_PACKAGE_DIR = Path(__file__).parent.parent  # noorlytics/cli/ -> noorlytics/
DEFAULT_TEMPLATE_PATH = _PACKAGE_DIR / "templates" / "customer_context_default.json"


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


def _extract_defined_symbol_name(code: str) -> Optional[str]:
    """Return the primary function/class name defined by a code snippet, if any."""
    match = re.search(r"^\s*(?:def|class)\s+([A-Za-z_][A-Za-z0-9_]*)\b", code, re.MULTILINE)
    return match.group(1) if match else None


def _find_conflicting_symbol_changes(changes: List) -> List[Tuple[int, int, str]]:
    """Return pairs of changes that rewrite the same original symbol incompatibly.

    Auto-apply should stop when two independent refactor blocks both target the
    same function/class in different directions (for example, main -> main(args)
    and main -> run) without a declared dependency between them.
    """
    conflicts: List[Tuple[int, int, str]] = []

    for i in range(len(changes)):
        left = changes[i]
        left_before = _extract_defined_symbol_name(left.before_code)
        left_after = _extract_defined_symbol_name(left.after_code)

        if not left_before:
            continue

        for j in range(i + 1, len(changes)):
            right = changes[j]
            right_before = _extract_defined_symbol_name(right.before_code)
            right_after = _extract_defined_symbol_name(right.after_code)

            if not right_before:
                continue

            if left_before != right_before:
                continue

            if _has_real_dependency(getattr(left, 'depends_on', None)) or _has_real_dependency(getattr(right, 'depends_on', None)):
                continue

            if left_after and right_after and left_after != right_after:
                conflicts.append((i, j, left_before))
                continue

            if left_after and left_after != left_before and right_after and right_after != right_before:
                if left_after != right_after:
                    conflicts.append((i, j, left_before))

    return conflicts


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
@click.option("--mode", type=click.Choice(["ollama", "openai"]), 
              default=os.getenv("NOOR_MODE", "ollama"),
              help="Choose LLM backend. Default: ollama (from NOOR_MODE env var).")
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
@click.argument("path", required=True, type=click.Path(exists=True, path_type=Path), help="File or directory path to analyze")
@click.pass_obj
def analyze_cmd(state: CLIState, path: Path):
    """Analyze source code for technical debt, quality issues, and anti-patterns.
    
    PURPOSE:
    Scans code for potential improvements including:
    - Code quality issues
    - Performance problems
    - Security concerns
    - Maintainability issues
    
    PARAMETERS:
    - path (required): File or directory to analyze
      * Single file: analyzes that file
      * Directory: recursively analyzes all supported files
    
    OUTPUTS:
    - Saves versioned Markdown report to reports/
    - Shows progress and summary in terminal
    
    EXAMPLES:
    - noor analyze examples/legacyfile.py          # Analyze single file
    - noor analyze examples/                        # Analyze entire directory
    - noor --mode=openai analyze myfile.py         # Use OpenAI backend
    """
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
@click.argument("path", required=True, type=click.Path(exists=True, path_type=Path), help="File or directory to suggest improvements for")
@click.pass_obj
def suggest_cmd(state: CLIState, path: Path):
    """Generate specific refactoring suggestions to improve code.
    
    PURPOSE:
    Creates actionable refactor recommendations including:
    - Code simplification ideas
    - Design pattern suggestions
    - Performance optimization opportunities
    - Best practice recommendations
    
    PARAMETERS:
    - path (required): File or directory for suggestions
      * Single file: generates suggestions for that file
      * Directory: recursively suggests for all supported files
    
    OUTPUTS:
    - Saves versioned Markdown report to reports/
    - Displays suggested changes with rationale
    
    EXAMPLES:
    - noor suggest examples/legacyfile.py          # Suggestions for one file
    - noor suggest examples/                        # Suggestions for package
    - noor --mode=ollama suggest mycode.py         # Use local Ollama
    """
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
    """Generate comprehensive unit test stubs for improved code coverage.
    
    PURPOSE:
    Create test skeleton files with test cases for:
    - All public functions and methods
    - Edge cases and error conditions
    - Integration points
    - Performance scenarios
    
    PARAMETERS:
    - path (required): File or directory to generate tests for
      * Single file: generates tests for that file
      * Directory: generates tests for all files in package
    - --lang: Programming language (python, js, ts, java, go, etc.)
      * Auto-detects from file extension if omitted
      * Useful if extension doesn't match language
    
    OUTPUTS:
    - New test files in tests/ directory (or alongside source)
    - One test file per source file
    - Framework-appropriate test structure
    
    EXAMPLES:
    - noor add-tests examples/legacyfile.py         # Generate tests
    - noor add-tests src/                           # Tests for package
    - noor add-tests file.js --lang javascript      # Specify language
    """
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
@click.option(
    "--offline",
    "allow_network",
    flag_value=False,
    default=False,
    help="Use only local metadata and local lockfiles. No registry or OSV calls are made.",
)
@click.option(
    "--network",
    "allow_network",
    flag_value=True,
    help="Allow live registry and OSV lookups for package metadata and advisories.",
)
@click.pass_obj
def analyze_deps_cmd(state: CLIState, manifest: Path, allow_network: bool):
    """Analyze dependencies for security vulnerabilities and license risks.
    
    PURPOSE:
    Scan package manifests for:
    - Known security vulnerabilities in dependencies
    - License compatibility issues
    - Outdated package versions
    - Dependency conflicts
    - Supply chain risks
    
    PARAMETERS:
    - manifest (required): Dependency file to analyze
      * requirements.txt: Python pip dependencies
      * pyproject.toml: Modern Python packaging
      * package.json: JavaScript/Node.js packages
      * pom.xml: Java Maven dependencies
      * Gemfile: Ruby dependencies
      * go.mod: Go modules
    - --offline: Use only local data (no registry lookups)
    - --network: Allow live registry and security advisory lookups
    
    OUTPUTS:
    - Vulnerability list with severity levels
    - License risk assessment
    - Findings JSON file (reports/)
    - Remediation recommendations
    
    EXAMPLES:
    - noor analyze-deps requirements.txt             # Analyze Python
    - noor analyze-deps package.json                 # Analyze Node.js
    - noor analyze-deps requirements.txt --network   # With live lookups
    - noor analyze-deps pyproject.toml --offline     # Offline mode
    """
    result = analyze_dependencies_file(manifest, allow_network=allow_network)

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

    # 4) Transform to normalized verified findings
    findings_collection = transform_analysis_to_findings(result)
    out_findings_json = state.reports_dir / f"{manifest.name}.findings.json"
    findings_collection.to_json_file(str(out_findings_json))
    
    # Show findings statistics
    stats = findings_collection.stats()
    click.echo(click.style(f"\n✓ Verified Findings Generated:", fg="cyan", bold=True))
    click.echo(f"  Total findings: {stats['total']}")
    if stats['by_type']:
        for ftype, count in stats['by_type'].items():
            click.echo(f"    - {ftype}: {count}")
    click.echo(click.style(f"📋  Findings JSON saved → {out_findings_json}", fg="green", bold=True))

    # 5) (Valfritt men nice) – spara en Markdown-rapport också
    notes_md = result.get("notes_md")
    if notes_md:
        out_md = _next_versioned_markdown_path(state.reports_dir, f"{manifest.name}.deps")
        _save_and_print(notes_md, out_md, header=f"{manifest.name} – dependencies")

    # 6) ---- Standards Compliance Check ----
    standards_compliance = result.get("standards_compliance") or []
    if standards_compliance:
        click.echo("")
        click.echo(click.style("⚠️  Standards Compliance Issues Detected:", fg="yellow", bold=True))
        
        by_standard = {}
        for issue in standards_compliance:
            std = issue["standard"]
            if std not in by_standard:
                by_standard[std] = []
            by_standard[std].append(issue)
        
        for std in sorted(by_standard.keys()):
            issues = by_standard[std]
            click.echo(click.style(f"\n  {std.upper()} ({len(issues)} issue(s)):", fg="yellow"))
            for issue in issues:
                click.echo(
                    f"    - {issue['package']} "
                    f"[{issue['severity'].upper()}]: {issue['message']}"
                )
                click.echo(f"      Remediation: {issue['remediation']}")
        
        # Save compliance findings
        out_compliance_json = state.reports_dir / f"{manifest.name}.compliance.json"
        out_compliance_json.write_text(json.dumps(standards_compliance, indent=2, ensure_ascii=False), encoding="utf-8")
        click.echo(click.style(f"\n📝 Compliance findings saved → {out_compliance_json}", fg="green", bold=True))
    else:
        click.echo(click.style("\n✓ No standards compliance issues detected for dependencies.", fg="green"))


@cli.command("gdpr")
@click.argument("path", required=True, type=click.Path(exists=True, path_type=Path), help="File or directory to scan for privacy risks")
@click.pass_obj
def gdpr_cmd(state: CLIState, path: Path):
    """Scan code for GDPR/privacy compliance issues and PII handling risks.
    
    PURPOSE:
    Detects privacy violations including:
    - Personal data being logged unsafely
    - Insecure data transmission (HTTP instead of HTTPS)
    - Missing data minimization/retention controls
    - Unencrypted sensitive data storage
    - Unauthorized data collection patterns
    
    PARAMETERS:
    - path (required): File or directory to scan
      * Single file: scans that file
      * Directory: recursively scans all supported files
    
    OUTPUTS:
    - JSON findings file: reports/gdpr_findings.json
    - Shows privacy issues with line numbers
    - Provides remediation suggestions
    
    EXAMPLES:
    - noor gdpr examples/legacyfile.py              # Scan single file
    - noor gdpr src/                                # Scan entire codebase
    """
    files = (
        list(_iter_code_files(path, state.allowed_ext, state.max_file_bytes))
        if path.is_dir()
        else list(_single_file(path, state.allowed_ext, state.max_file_bytes))
    )

    if not files:
        click.echo(click.style("⚠️  No matching files found.", fg="yellow"))
        raise SystemExit(2)

    all_findings = []
    for fpath, content in files:
        for item in scan_gdpr_violations(content, str(fpath)):
            all_findings.append(item)

    if not all_findings:
        click.echo(click.style("✅ No GDPR/privacy-risk patterns detected.", fg="green"))
        return

    click.echo(click.style("\n⚠️  GDPR/privacy-risk findings detected:", fg="red", bold=True))
    for item in all_findings:
        click.echo(
            f"  - [{item['severity'].upper()}] {item['rule']} "
            f"({item['filename']}:{item['line']}): {item['message']}"
        )

    out_json = state.reports_dir / "gdpr_findings.json"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(all_findings, indent=2, ensure_ascii=False), encoding="utf-8")
    click.echo(click.style(f"\n📝 GDPR findings saved → {out_json}", fg="green", bold=True))


@cli.command("audit-security")
@click.argument("path", required=True, type=click.Path(exists=True, path_type=Path), help="File or directory to scan for security issues")
@click.option("--check", "-c", type=click.Choice(["encryption", "audit_logging", "authentication", "secrets", "error_handling", "all"]), 
              default="all", help="Which security checks to run (default: all)")
@click.option("--remediate", "-r", is_flag=True, help="Generate AI-powered remediation suggestions using LLM")
@click.pass_obj
def audit_security_cmd(state: CLIState, path: Path, check: str, remediate: bool):
    """Audit code for security hardening: encryption, logging, authentication, secrets handling.
    
    PURPOSE:
    Scans code for security best practices including:
    - Encryption at-rest (hardcoded credentials, plaintext storage)
    - Encryption in-transit (HTTP vs HTTPS usage)
    - Audit logging for sensitive operations
    - Authentication patterns (weak passwords, hardcoded creds)
    - Secrets/credentials management
    - Error handling for security operations
    
    PARAMETERS:
    - path (required): File or directory to scan
      * Single file: scans that file
      * Directory: recursively scans all supported files
    - --check / -c: Specific security check to run
      * encryption: hardcoded creds, plaintext storage, HTTP usage
      * audit_logging: missing logs for sensitive operations
      * authentication: weak auth patterns, hardcoded usernames
      * secrets: credentials in logs/urls/config
      * error_handling: missing try-except around security ops
      * all: run all checks (default)
    - --remediate / -r: Generate LLM-powered remediation suggestions (requires Ollama/OpenAI)
    
    OUTPUTS:
    - JSON findings file: reports/audit_security_findings.json
    - Shows security issues with line numbers and severity
    - Provides remediation suggestions
    - With --remediate: detailed LLM-generated remediation plans
    
    EXAMPLES:
    - noor audit-security examples/legacyfile.py              # All checks
    - noor audit-security src/ --check encryption             # Encryption only
    - noor audit-security . -c secrets                        # Secrets only
    - noor audit-security . --remediate                       # With AI suggestions
    """
    from noorlytics.audit_security import scan_audit_security
    
    files = (
        list(_iter_code_files(path, state.allowed_ext, state.max_file_bytes))
        if path.is_dir()
        else list(_single_file(path, state.allowed_ext, state.max_file_bytes))
    )

    if not files:
        click.echo(click.style("⚠️  No matching files found.", fg="yellow"))
        raise SystemExit(2)

    # Determine which checks to run
    checks_to_run = None if check == "all" else [check]

    all_findings = []
    for fpath, content in files:
        for item in scan_audit_security(content, str(fpath), checks=checks_to_run):
            all_findings.append(item)

    if not all_findings:
        click.echo(click.style("✅ No security issues detected.", fg="green"))
        return

    click.echo(click.style("\n⚠️  Security audit findings detected:", fg="red", bold=True))
    by_check = {}
    for item in all_findings:
        check_type = item["check_type"]
        if check_type not in by_check:
            by_check[check_type] = []
        by_check[check_type].append(item)

    for check_type in sorted(by_check.keys()):
        items = by_check[check_type]
        click.echo(click.style(f"\n  {check_type.upper()} ({len(items)} issues):", fg="yellow"))
        # Group by filename for better readability
        by_file = {}
        for item in items:
            fname = item['filename']
            if fname not in by_file:
                by_file[fname] = []
            by_file[fname].append(item)
        
        for fname in sorted(by_file.keys()):
            file_items = by_file[fname]
            click.echo(click.style(f"    📄 {fname}", fg="cyan"))
            for item in file_items:
                click.echo(
                    f"      - [{item['severity'].upper()}] "
                    f"(line {item['line']}): {item['message']}"
                )

    state.reports_dir.mkdir(parents=True, exist_ok=True)
    out_json = state.reports_dir / "audit_security_findings.json"
    out_json.write_text(json.dumps(all_findings, indent=2, ensure_ascii=False), encoding="utf-8")
    click.echo(click.style(f"\n📝 Security findings saved → {out_json}", fg="green", bold=True))

    # Generate LLM-powered remediation if requested
    if remediate:
        click.echo(click.style("\n🤖 Generating AI-powered remediation suggestions...", fg="cyan", bold=True))
        client = state.ensure_client()
        
        remediation_results = []
        for finding in all_findings[:5]:  # Limit to first 5 for performance
            prompt = f"""
            A security issue was detected:
            
            Type: {finding['check_type'].upper()}
            Severity: {finding['severity'].upper()}
            Issue: {finding['message']}
            Location: {finding['filename']}:{finding['line']}
            Code: {finding['evidence']}
            
            Provide a detailed, actionable remediation plan with code examples.
            Focus on best practices for secure coding.
            Keep response concise but comprehensive.
            """
            
            try:
                response = client.generate(prompt)
                remediation_results.append({
                    "finding_type": finding['check_type'],
                    "severity": finding['severity'],
                    "issue": finding['message'],
                    "ai_remediation": response,
                })
                click.echo(click.style(f"  ✓ {finding['check_type'].upper()} - {finding['message'][:50]}...", fg="green"))
            except Exception as e:
                if state.verbose:
                    click.echo(click.style(f"  ✗ Error generating remediation: {e}", fg="red"))

        if remediation_results:
            remediation_json = state.reports_dir / "audit_security_remediation_ai.json"
            remediation_json.write_text(json.dumps(remediation_results, indent=2, ensure_ascii=False), encoding="utf-8")
            click.echo(click.style(f"✓ AI-powered remediation saved → {remediation_json}", fg="green", bold=True))


@cli.command("scan-standards")
@click.argument("path", required=True, type=click.Path(exists=True, path_type=Path), help="File or directory to scan for compliance")
@click.option("--standard", "-s", type=click.Choice(["hipaa", "pci-dss", "soc2", "iso27001", "fedramp", "all"]), 
              default="all", help="Which compliance standard to check (default: all)")
@click.option("--remediate", "-r", is_flag=True, help="Generate AI-powered remediation suggestions using LLM")
@click.pass_obj
def scan_standards_cmd(state: CLIState, path: Path, standard: str, remediate: bool):
    """Scan code for compliance with industry standards: HIPAA, PCI-DSS, SOC 2, ISO 27001, FedRAMP.
    
    PURPOSE:
    Detects compliance violations for regulated industries and standards:
    - HIPAA: Healthcare data (PHI) protection, encryption, access controls, audit logging
    - PCI-DSS: Payment card data protection, tokenization, network security
    - SOC 2: Service organization controls (availability, integrity, confidentiality)
    - ISO 27001: Information security management, asset management, access control, cryptography
    - FedRAMP: Federal cloud authorization, data classification, FIPS 140-2 encryption, MFA
    
    PARAMETERS:
    - path (required): File or directory to scan
      * Single file: scans that file
      * Directory: recursively scans all supported files
    - --standard / -s: Specific compliance standard to check
      * hipaa: Healthcare Protected Health Information rules
      * pci-dss: Payment Card Industry Data Security Standard
      * soc2: Service Organization Controls
      * iso27001: Information Security Management System
      * fedramp: Federal Risk and Authorization Management Program
      * all: check all standards (default)
    - --remediate / -r: Generate LLM-powered remediation suggestions (requires Ollama/OpenAI)
    
    OUTPUTS:
    - JSON findings file: reports/compliance_findings.json
    - Shows compliance violations with requirement IDs
    - Provides remediation guidance per standard
    - With --remediate: detailed LLM-generated remediation plans
    
    EXAMPLES:
    - noor scan-standards examples/payment.py           # All standards
    - noor scan-standards src/ --standard hipaa         # HIPAA only
    - noor scan-standards . -s iso27001                 # ISO 27001 only
    - noor scan-standards . -s fedramp --remediate      # FedRAMP + AI suggestions
    """
    from noorlytics.scan_standards import scan_standards
    
    files = (
        list(_iter_code_files(path, state.allowed_ext, state.max_file_bytes))
        if path.is_dir()
        else list(_single_file(path, state.allowed_ext, state.max_file_bytes))
    )

    if not files:
        click.echo(click.style("⚠️  No matching files found.", fg="yellow"))
        raise SystemExit(2)

    # Determine which standards to check
    standards_to_check = None if standard == "all" else [standard]

    all_findings = []
    for fpath, content in files:
        for item in scan_standards(content, str(fpath), standards=standards_to_check):
            all_findings.append(item)

    if not all_findings:
        click.echo(click.style("✅ No compliance violations detected.", fg="green"))
        return

    click.echo(click.style("\n⚠️  Compliance findings detected:", fg="red", bold=True))
    by_standard = {}
    for item in all_findings:
        std = item["standard"]
        if std not in by_standard:
            by_standard[std] = []
        by_standard[std].append(item)

    for std in sorted(by_standard.keys()):
        items = by_standard[std]
        click.echo(click.style(f"\n  {std.upper()} ({len(items)} issues):", fg="yellow"))
        # Group by filename for better readability
        by_file = {}
        for item in items:
            fname = item.get('filename', 'unknown')
            if fname not in by_file:
                by_file[fname] = []
            by_file[fname].append(item)
        
        for fname in sorted(by_file.keys()):
            file_items = by_file[fname]
            click.echo(click.style(f"    📄 {fname}", fg="cyan"))
            for item in file_items:
                line_info = f":{item['line']}" if item.get('line') else ""
                click.echo(
                    f"      - [{item['severity'].upper()}] Req {item['requirement']}: {item['message']}{line_info}"
                )
                click.echo(f"        → {item['remediation']}")

    # Save findings
    state.reports_dir.mkdir(parents=True, exist_ok=True)
    out_json = state.reports_dir / "compliance_findings.json"
    out_json.write_text(json.dumps(all_findings, indent=2, ensure_ascii=False), encoding="utf-8")
    click.echo(click.style(f"\n📝 Compliance findings saved → {out_json}", fg="green", bold=True))

    # Generate LLM-powered remediation if requested
    if remediate:
        click.echo(click.style("\n🤖 Generating AI-powered remediation suggestions...", fg="cyan", bold=True))
        client = state.ensure_client()
        
        remediation_results = []
        for finding in all_findings[:5]:  # Limit to first 5 for performance
            prompt = f"""
            A compliance violation was detected:
            
            Standard: {finding['standard'].upper()}
            Requirement: {finding['requirement']}
            Issue: {finding['message']}
            Code: {finding['evidence']}
            
            Provide a detailed, actionable remediation plan with code examples where applicable.
            Keep response concise but comprehensive.
            """
            
            try:
                response = client.generate(prompt)
                remediation_results.append({
                    "finding_id": f"{finding['standard']}-{finding['requirement']}",
                    "issue": finding['message'],
                    "ai_remediation": response,
                })
                click.echo(click.style(f"  ✓ {finding['standard'].upper()} {finding['requirement']}", fg="green"))
            except Exception as e:
                if state.verbose:
                    click.echo(click.style(f"  ✗ Error generating remediation: {e}", fg="red"))

        if remediation_results:
            remediation_json = state.reports_dir / "compliance_remediation_ai.json"
            remediation_json.write_text(json.dumps(remediation_results, indent=2, ensure_ascii=False), encoding="utf-8")
            click.echo(click.style(f"✓ AI-powered remediation saved → {remediation_json}", fg="green", bold=True))


@cli.command("unified-scan")
@click.argument("path", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--output", "-o", required=False, type=click.Path(path_type=Path), default=None, help="Output JSON file for unified findings")
@click.option("--json-only", is_flag=True, help="Only output JSON, no progress/summary display")
@click.pass_obj
def unified_scan_cmd(state: CLIState, path: Path, output: Optional[Path], json_only: bool):
    """Combine security and compliance findings into unified report.
    
    PURPOSE:
    Merges audit-security (security violations) with scan-standards (compliance issues)
    to create a unified view where overlapping issues are correlated and deduplicated.
    
    KEY FEATURES:
    - Merge: Combines findings from both security and compliance scanners
    - Deduplicate: Removes duplicate issues detected by multiple scanners
    - Correlate: Links related findings across scanners (e.g., HTTP → HIPAA violation)
    - Categorize: Labels findings as security-only, compliance-only, or both
    - Severity: Calculates unified severity when issue affects both aspects
    
    WORKFLOW:
    1. Scan file(s) with audit-security
    2. Scan file(s) with scan-standards
    3. Merge and correlate findings
    4. Save unified report with correlation metadata
    
    OUTPUT:
    Unified findings JSON with:
    - Individual findings with merged context
    - Correlation links showing related issues
    - Category (security_only, compliance_only, or both)
    - Remediation guidance combining both perspectives
    
    EXAMPLES:
    - noor unified-scan file.py                              # Scan single file
    - noor unified-scan . --json-only                        # Scan directory, JSON output
    - noor unified-scan file.py -o report.json               # Save to specific file
    """
    try:
        # state is now passed via @click.pass_obj
        
        # Determine files to scan
        if path.is_file():
            files_to_scan = [path]
        else:
            files_to_scan = list(path.rglob("*.py"))
        
        if not files_to_scan:
            click.echo(click.style("✗ No Python files found", fg="red"))
            return
        
        scanner = UnifiedScanner()
        results = []
        
        if not json_only:
            click.echo(click.style("\n🔗 Running Unified Security & Compliance Scan...\n", fg="cyan", bold=True))
        
        with click.progressbar(files_to_scan, label="Scanning files", show_pos=True) as bar:
            for file_path in bar:
                try:
                    # Skip vendor, test, and config files
                    if any(
                        skip in file_path.parts
                        for skip in {"__pycache__", ".venv", "venv", "node_modules", ".git", "tests", "test"}
                    ):
                        continue
                    
                    content = file_path.read_text(encoding="utf-8", errors="ignore")
                    
                    # Get security findings (content first, then filename)
                    security_findings = scan_audit_security(content, str(file_path))
                    
                    # Get compliance findings (also expects content first)
                    compliance_findings = scan_standards(content, str(file_path))
                    
                    # Merge and correlate
                    result = scanner.scan(
                        str(file_path),
                        security_findings,
                        compliance_findings,
                    )
                    
                    if result.findings:
                        results.append(result)
                
                except Exception as e:
                    if not json_only:
                        click.echo(click.style(f"  ✗ Error scanning {file_path}: {e}", fg="yellow"))
        
        # Merge all results
        merged_summary = scanner.merge_results(results)
        
        # Prepare output
        output_data = {
            "summary": merged_summary,
            "by_file": [r.to_dict() for r in results],
        }
        
        # Determine output file
        if output is None:
            output = state.reports_dir / "unified_scan_findings.json"
        
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(output_data, indent=2, ensure_ascii=False), encoding="utf-8")
        
        if not json_only:
            # Display summary
            click.echo(click.style("\n✓ Unified Scan Complete\n", fg="green", bold=True))
            click.echo(f"📁 Files scanned: {merged_summary['files_scanned']}")
            click.echo(f"⚠️  Files with issues: {merged_summary['files_with_issues']}")
            click.echo(f"📊 Total findings: {merged_summary['total_findings']}")
            
            # Severity breakdown
            click.echo("\nBy Severity:")
            click.echo(f"  🔴 High: {merged_summary['by_severity']['high']}")
            click.echo(f"  🟠 Medium: {merged_summary['by_severity']['medium']}")
            click.echo(f"  🟡 Low: {merged_summary['by_severity']['low']}")
            
            # Category breakdown
            click.echo("\nBy Category:")
            click.echo(f"  🔒 Security-only: {merged_summary['by_category']['security_only']}")
            click.echo(f"  📋 Compliance-only: {merged_summary['by_category']['compliance_only']}")
            click.echo(f"  ⚠️  Both (overlapping): {merged_summary['by_category']['both']}")
            
            # Show sample correlations
            if any(r.correlations for r in results):
                click.echo("\n🔗 Correlation Examples:")
                correlation_count = 0
                for result in results:
                    for finding_id, correlated_ids in result.correlations.items():
                        if correlation_count < 3:
                            finding = result.findings.get(finding_id)
                            if finding:
                                click.echo(f"  • {finding.title}")
                                for corr_id in correlated_ids[:1]:
                                    corr_finding = result.findings.get(corr_id)
                                    if corr_finding:
                                        click.echo(f"    ↔️  {corr_finding.title}")
                                correlation_count += 1
            
            click.echo(click.style(f"\n✓ Findings saved → {output}\n", fg="green", bold=True))
        else:
            # Just output JSON
            click.echo(json.dumps(output_data, indent=2, ensure_ascii=False))
    
    except Exception as e:
        click.echo(click.style(f"✗ Error: {e}", fg="red"), err=True)
        raise click.ClickException(str(e))


@cli.command("assess")
@click.argument("manifest_or_findings", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--context", "-c", required=False, type=click.Path(exists=True, path_type=Path), default=None, help="Customer context JSON file (default: noorlytics/templates/customer_context_default.json)")
@click.option("--llm-model", type=str, help="LLM model (ollama:mistral|openai:gpt-4)")
@click.option("--save-history", is_flag=True, help="Save assessment to history tracking")
@click.option("--compare-versions", is_flag=True, help="Compare with previous assessment version")
@click.option("--export-format", type=click.Choice(["json", "csv", "markdown"]), help="Auto-export decision format")
@click.option("--export-output", type=click.Path(), help="Where to save export file")
@click.option("--metrics-report", is_flag=True, help="Generate metrics dashboard after assessment")
@click.option("--create-report", type=click.Path(), help="Generate markdown report with decisions + metrics")
@click.pass_obj
def assess_cmd(
    state: CLIState,
    manifest_or_findings: Path,
    context: Path,
    llm_model: str,
    save_history: bool,
    compare_versions: bool,
    export_format: str,
    export_output: str,
    metrics_report: bool,
    create_report: str,
):
    """Convert technical findings into prioritized business decisions.
    
    PURPOSE:
    Transforms technical issues into business-critical decisions by:
    - Assessing impact using customer context
    - Ranking by priority (P1=Critical, P4=Enhancement)
    - Generating rationale and recommendations
    - Optionally storing for trend analysis
    
    WORKFLOW:
    1. Provide manifest or findings: noor assess requirements.txt
    2. (Optional) Use custom context: --context my_context.json
    3. (Optional) Save for tracking: --save-history
    4. (Optional) Generate reports: --create-report decision_report.md
    
    PARAMETERS:
    - manifest_or_findings (required): 
      * requirements.txt, package.json, pyproject.toml (manifests)
      * requirements.txt.findings.json (pre-analyzed findings)
    - --context: Custom decision context JSON
      * Default: built-in template with standard risk weights
      * Customize: security, cost_control, delivery_speed, maintainability
    - --llm-model: Enhance with AI rationales (e.g., ollama:mistral)
    - --save-history: Store in database for change tracking
    - --compare-versions: Show what changed since last assessment
    - --export-format: Export decisions (json/csv/markdown)
    - --export-output: Save exports to file
    - --metrics-report: Generate metrics dashboard
    - --create-report: Save combined report with metrics
    
    OUTPUTS:
    - Displays decisions grouped by priority (P1-P4)
    - Saves assessment JSON and Markdown
    - (Optional) Stores in database: noorlytics/decisions.db
    - (Optional) Generates metrics and comparison reports
    
    EXAMPLES:
    - noor assess requirements.txt                            # Basic assessment
    - noor assess requirements.txt --save-history            # With database tracking
    - noor assess requirements.txt --context custom.json      # Custom priorities
    - noor assess requirements.txt --create-report report.md  # Full report
    """
    try:
        # Use default template if no context specified
        if context is None:
            if not DEFAULT_TEMPLATE_PATH.exists():
                click.echo(
                    click.style(
                        f"❌ Default template not found: {DEFAULT_TEMPLATE_PATH}",
                        fg="red",
                        bold=True,
                    )
                )
                raise click.ClickException(
                    f"Default template missing. Please provide a template via --context or install the default at {DEFAULT_TEMPLATE_PATH}"
                )
            context = DEFAULT_TEMPLATE_PATH
            click.echo(
                click.style(
                    f"ℹ️  Using default template: {DEFAULT_TEMPLATE_PATH}",
                    fg="cyan",
                    bold=True,
                )
            )
        
        # Load customer context
        customer_context = CustomerContext.from_json_file(str(context))
        click.echo(
            click.style(
                f"✓ Loaded customer context: {customer_context.customer_name}",
                fg="cyan",
                bold=True,
            )
        )

        # Load or generate findings
        if manifest_or_findings.name.endswith(".findings.json"):
            # Load findings from JSON
            findings = FindingsCollection.from_json_file(str(manifest_or_findings))
            click.echo(
                click.style(
                    f"✓ Loaded findings: {len(findings.findings)} total",
                    fg="cyan",
                    bold=True,
                )
            )
            findings_source = str(manifest_or_findings)
        else:
            # Analyze manifest and generate findings
            analysis = analyze_dependencies_file(manifest_or_findings)
            findings = transform_analysis_to_findings(analysis)
            click.echo(
                click.style(
                    f"✓ Analyzed manifest: {len(findings.findings)} findings generated",
                    fg="cyan",
                    bold=True,
                )
            )
            findings_source = str(manifest_or_findings)

        # Display customer context
        click.echo("")
        click.echo(click.style("Customer Risk Profile:", fg="cyan", bold=True))
        prefs = customer_context.risk_preferences
        click.echo(f"  - Security: {prefs.security.upper()}")
        click.echo(f"  - Business Continuity: {prefs.business_continuity.upper()}")
        click.echo(f"  - Cost Control: {prefs.cost_control.upper()}")
        click.echo(f"  - Delivery Speed: {prefs.delivery_speed.upper()}")

        # Generate assessment
        engine = AssessmentEngine(customer_context)
        assessment = engine.assess(findings, findings_source)

        # Display decision summary
        click.echo("")
        click.echo(click.style("Generated Decisions:", fg="cyan", bold=True))
        by_priority = {}
        for decision in assessment.decisions:
            if decision.priority not in by_priority:
                by_priority[decision.priority] = []
            by_priority[decision.priority].append(decision)

        for priority in ["P1", "P2", "P3", "P4"]:
            decisions_at_priority = by_priority.get(priority, [])
            if decisions_at_priority:
                click.echo(f"  {priority}: {len(decisions_at_priority)} decision(s)")

        # Save assessment results
        state.reports_dir.mkdir(parents=True, exist_ok=True)

        # Determine output filenames
        if manifest_or_findings.name.endswith(".findings.json"):
            base_name = manifest_or_findings.stem.replace(".findings", "")
        else:
            base_name = manifest_or_findings.name

        # Save JSON assessment
        out_assess_json = state.reports_dir / f"{base_name}.assess.json"
        assessment.to_json_file(str(out_assess_json))
        click.echo(
            click.style(f"\n📋 Assessment JSON saved → {out_assess_json}", fg="green", bold=True)
        )

        # Save Markdown assessment
        out_assess_md = _next_versioned_markdown_path(state.reports_dir, f"{base_name}.assess")
        assessment_md = assessment.to_markdown()
        _save_and_print(assessment_md, out_assess_md, header=f"{base_name} – assessment")

        # ---- Phase 3 Enhancements: Decision Store, History, Analytics ----
        
        # Optionally enhance decisions with LLM
        if llm_model:
            click.echo("")
            click.echo(click.style("🤖 Enhancing decisions with LLM...", fg="cyan", bold=True))
            try:
                from noorlytics.llm_decision_engine import LLMDecisionEnhancer
                from noorlytics.llm_interface import LLMClient

                backend, model = llm_model.split(":", 1)
                llm_client = LLMClient(mode=backend, model=model)
                enhancer = LLMDecisionEnhancer(llm_client=llm_client, model=f"{backend}:{model}")

                for decision in assessment.decisions:
                    enhanced = enhancer.enhance_decision(decision, customer_context, findings)
                    if enhanced.rationale:
                        decision.rationale = enhanced.rationale
                click.echo(click.style(f"✅ Enhanced {len(assessment.decisions)} decisions with LLM", fg="green"))
            except Exception as e:
                click.echo(click.style(f"⚠️  LLM enhancement failed: {e}", fg="yellow"))
        
        # Optionally store decisions for history tracking
        if save_history:
            click.echo("")
            click.echo(click.style("💾 Storing decisions to history...", fg="cyan", bold=True))
            try:
                from noorlytics.decision_store import DecisionStore
                
                store = DecisionStore()
                manifest_path = str(manifest_or_findings)
                for decision in assessment.decisions:
                    store.store_decision(decision, customer_context, manifest_path, assessment_version=1)
                
                click.echo(click.style(f"✅ Stored {len(assessment.decisions)} decisions", fg="green"))
            except Exception as e:
                click.echo(click.style(f"⚠️  History storage failed: {e}", fg="yellow"))
        
        # Optionally compare with previous version
        if compare_versions:
            click.echo("")
            click.echo(click.style("📊 Comparing with previous assessment...", fg="cyan", bold=True))
            try:
                from noorlytics.decision_history import DecisionHistory
                from noorlytics.decision_store import DecisionStore
                
                store = DecisionStore()
                history = DecisionHistory(store)
                manifest_path = str(manifest_or_findings)
                timeline = history.get_assessment_timeline(manifest_path)
                if len(timeline) > 1:
                    diff = history.get_assessment_diff(manifest_path, 1, 2)
                    click.echo(click.style(f"Changes detected:", fg="blue"))
                    click.echo(f"  Added: {len(diff.added)}")
                    click.echo(f"  Removed: {len(diff.removed)}")
                    click.echo(f"  Modified: {len(diff.modified)}")
                else:
                    click.echo(click.style("No previous assessment found", fg="yellow"))
            except Exception as e:
                click.echo(click.style(f"⚠️  Version comparison failed: {e}", fg="yellow"))
        
        # Optionally export decisions in requested format
        if export_format and export_output:
            click.echo("")
            click.echo(click.style(f"📤 Exporting decisions as {export_format}...", fg="cyan", bold=True))
            try:
                from noorlytics.decision_store import DecisionStore
                
                store = DecisionStore()
                manifest_path = str(manifest_or_findings)
                decisions = store.query_decisions(manifest_path=manifest_path)
                
                export_path = Path(export_output)
                export_path.parent.mkdir(parents=True, exist_ok=True)
                
                if export_format == "json":
                    import json
                    with open(export_path, "w") as f:
                        json.dump([d.to_dict() for d in decisions], f, indent=2)
                elif export_format == "csv":
                    import csv
                    if decisions:
                        with open(export_path, "w", newline="") as f:
                            writer = csv.DictWriter(f, fieldnames=decisions[0].to_dict().keys())
                            writer.writeheader()
                            for d in decisions:
                                writer.writerow(d.to_dict())
                elif export_format == "markdown":
                    from noorlytics.decision_store import DecisionStore
                    export_data = store.export_decisions(manifest_path, format=export_format)
                    with open(export_path, "w") as f:
                        f.write(export_data)
                
                click.echo(click.style(f"✅ Exported to {export_path}", fg="green"))
            except Exception as e:
                click.echo(click.style(f"⚠️  Export failed: {e}", fg="yellow"))
        
        # Optionally generate metrics report
        if metrics_report:
            click.echo("")
            click.echo(click.style("📈 Generating metrics dashboard...", fg="cyan", bold=True))
            try:
                from noorlytics.decision_analytics import DecisionAnalytics
                from noorlytics.decision_store import DecisionStore
                
                store = DecisionStore()
                analytics = DecisionAnalytics(store)
                dashboard = analytics.generate_metrics_dashboard()
                metrics_output = state.reports_dir / f"{base_name}.metrics.txt"
                with open(metrics_output, "w") as f:
                    f.write(dashboard)
                click.echo(click.style(f"✅ Metrics saved to {metrics_output}", fg="green"))
            except Exception as e:
                click.echo(click.style(f"⚠️  Metrics generation failed: {e}", fg="yellow"))
        
        # Optionally create combined report
        if create_report:
            click.echo("")
            click.echo(click.style("📑 Creating combined report...", fg="cyan", bold=True))
            try:
                from noorlytics.decision_store import DecisionStore
                from noorlytics.decision_analytics import DecisionAnalytics
                
                report_path = Path(create_report)
                report_path.parent.mkdir(parents=True, exist_ok=True)
                
                with open(report_path, "w") as f:
                    f.write(f"# Assessment Report: {base_name}\n\n")
                    f.write("## Assessment Summary\n\n")
                    f.write(assessment_md)
                    f.write("\n\n## Metrics Dashboard\n\n")
                    
                    try:
                        store = DecisionStore()
                        analytics = DecisionAnalytics(store)
                        dashboard = analytics.generate_metrics_dashboard()
                        f.write(dashboard)
                    except Exception:
                        f.write("(Metrics generation not available)\n")
                
                click.echo(click.style(f"✅ Report saved to {report_path}", fg="green"))
            except Exception as e:
                click.echo(click.style(f"⚠️  Report generation failed: {e}", fg="yellow"))

    except FileNotFoundError as e:
        click.echo(click.style(f"❌ Error: File not found: {e}", fg="red", bold=True), err=True)
    except json.JSONDecodeError as e:
        click.echo(
            click.style(
                f"❌ Error: Invalid JSON in customer context: {e}", fg="red", bold=True
            ),
            err=True,
        )
    except Exception as e:
        click.echo(
            click.style(f"❌ Error during assessment: {e}", fg="red", bold=True), err=True
        )
        if state.verbose:
            import traceback
            traceback.print_exc()


@cli.command("refactor")
@click.argument("path", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--apply", "-a", is_flag=True, help="Apply all complete refactoring changes automatically. Short form: -a.")
@click.option("--dry-run", "-dr", is_flag=True, help="Show diffs without modifying files. Short form: -dr.")
@click.option("--interactive", "-i", is_flag=True, help="Prompt for confirmation on each change. Short form: -i.")
@click.option("--undo", "-u", is_flag=True, help="Restore last refactoring changes from backup. Short form: -u.")
@click.option("--git-commit", "-gc", is_flag=True, help="Stage and commit changes to git after applying. Short form: -gc.")
@click.pass_obj
def refactor_cmd(state: CLIState, path: Path, apply: bool, dry_run: bool, interactive: bool, undo: bool, git_commit: bool):
    """Create AI-assisted refactoring plans with flexible execution modes.
    
    PURPOSE:
    Generate and execute code refactoring recommendations for:
    - Code simplification and clarity
    - Performance improvements
    - Pattern adoption and consistency
    - Maintainability enhancements
    - Technical debt reduction
    
    PARAMETERS:
    - path (required): File or directory to refactor
    - --apply (-a): Apply changes automatically (non-interactive)
    - --dry-run (-dr): Show changes without modifying files
    - --interactive (-i): Prompt for confirmation on each change
    - --undo (-u): Restore previous refactoring from backup
    - --git-commit (-gc): Auto-commit changes to git
    
    MODES:
    - Planning (default): Generate refactor plan only
    - Dry-run: Show proposed changes
    - Interactive: Review and approve each change
    - Auto-apply: Apply all changes without prompting
    
    OUTPUTS:
    - Refactor plan with detailed changes (Markdown)
    - Backups of modified files (if applied)
    - Git commits (if --git-commit enabled)
    
    EXAMPLES:
    - noor refactor file.py                        # Plan only
    - noor refactor file.py --dry-run              # Show changes
    - noor refactor file.py --interactive          # Review each change
    - noor refactor file.py --apply                # Auto-apply all
    - noor refactor file.py --apply --git-commit   # Apply and commit
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
    
    # Issue 3: Warmup Ollama with progress feedback (only once at the start)
    if client.mode == "ollama" and len(files) > 0:
        click.echo(click.style("🔄 Preparing LLM model...", fg="cyan"))
        if not client.warmup():
            click.echo(click.style("   ⚠️  Model warmup failed (will retry on first use)", fg="yellow"))
        else:
            click.echo(click.style("   ✓ Model ready", fg="green"))

    applied_count = 0
    failed_count = 0
    
    # Issue 1: Parallel processing with ThreadPoolExecutor (4-8x speedup for multi-file dirs)
    # Issue 2: Uses cached_refactor to skip redundant LLM calls
    def _process_file_for_refactor(fpath: Path, content: str) -> Tuple[Path, Optional[str], Optional[str], bool]:
        """Process a single file for refactoring.
        
        Returns:
            Tuple of (fpath, markdown_plan, error_msg, success)
        """
        try:
            # Issue 2: Use cached_refactor to check cache first, saving 20-50s per re-run
            md = client.cached_refactor(fpath.name, content)
            return (fpath, md, None, True)
        except Exception as e:
            return (fpath, None, str(e), False)
    
    # Determine number of parallel workers (4 is a safe default to avoid overwhelming Ollama)
    max_workers = min(4, len(files)) if len(files) > 1 else 1
    
    with render_progress("Generating refactor plans…") as prog:
        t = prog.add_task("run", total=len(files))
        
        # Use ThreadPoolExecutor for parallel processing (Issue 1)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures_to_files = {
                executor.submit(_process_file_for_refactor, fpath, content): (fpath, content)
                for fpath, content in files
            }
            
            for future in as_completed(futures_to_files):
                fpath, original_content = futures_to_files[future]
                
                try:
                    fpath_result, md, error_msg, success = future.result()
                    
                    if not success or md is None:
                        click.echo(click.style(f"   ❌ {fpath.name}: {error_msg}", fg="red"))
                        failed_count += 1
                        prog.advance(t)
                        continue
                    
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
            _render_change_code_block(change, indent="   ")
            click.echo()
            note = change.display_note()
            if note:
                click.echo(f"   {click.style(note, fg='blue')}")
            click.echo(f"   Problem: {change.problem_statement}")
            if _has_real_dependency(change.depends_on):
                click.echo(f"   📌 Depends on: {change.depends_on}")
            
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
                # Apply all approved changes atomically for the chosen set.
                successful, failed, failure_details = applicator.apply_all_changes(approved_changes)

                if failed > 0:
                    applicator.rollback()
                    click.echo(click.style(f"\n   ⚠️  {failed} change(s) could not be applied; rolling back the entire selection.", fg="yellow"))
                    for idx, change in enumerate(approved_changes):
                        if idx in failure_details:
                            reason = failure_details.get(idx, "Code not found in file")
                            click.echo(f"      ❌ {change.display_title()}")
                            _render_change_code_block(change)
                            click.echo(f"         Reason: {reason}")
                    click.echo(click.style("   No file changes were written because the refactor set was not fully successful.", fg="yellow"))
                    return False

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
    """Automatically apply all complete refactoring changes with dependency grouping.

    The apply-all path intentionally applies every complete refactor block in the
    plan, regardless of priority, while still skipping incomplete/truncated code
    snippets that are not safe to patch automatically.

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

    if not changes:
        click.echo(click.style(f"   ℹ️  No refactors found for {fpath.name}", fg="blue"))
        return False

    complete_changes = [c for c in changes if c.is_complete()]
    incomplete_changes = [c for c in changes if not c.is_complete()]

    # Print header with change summary
    click.echo(click.style(f"\n   📋 Refactoring Plan for {fpath.name}:", fg="cyan"))
    click.echo(click.style(f"      Total suggestions: {len(changes)} | Complete: {len(complete_changes)} | Incomplete: {len(incomplete_changes)}", fg="blue"))
    click.echo()

    if not complete_changes:
        click.echo(click.style(f"   ℹ️  No complete refactor blocks to auto-apply", fg="blue"))
        if incomplete_changes:
            click.echo(click.style(f"      {len(incomplete_changes)} change(s) are truncated or incomplete and were skipped", fg="yellow"))
        return False

    # Group complete changes by dependency chains for display only.
    complete_chains = []
    for chain in graph.group_by_chains():
        complete_chain = [idx for idx in chain if changes[idx].is_complete()]
        if complete_chain:
            complete_chains.append(complete_chain)

    # Reject incompatible refactors that edit the same original symbol without an
    # explicit dependency chain. This is the root cause behind corrupted output
    # like main -> main(args) and main -> run being auto-applied together.
    conflict_pairs = _find_conflicting_symbol_changes(complete_changes)
    if conflict_pairs:
        click.echo(click.style("\n   ⚠️  Incompatible auto-apply detected:", fg="yellow"))
        for i, j, symbol in conflict_pairs:
            left = complete_changes[i]
            right = complete_changes[j]
            click.echo(
                f"      {left.display_title()} and {right.display_title()} both modify `{symbol}` "
                "without a valid dependency chain"
            )
            _render_change_code_block(left, indent="      ")
            _render_change_code_block(right, indent="      ")
        click.echo(click.style("   Skipping auto-apply for this refactor set to avoid corrupting the file.", fg="yellow"))
        return False

    # Apply changes in their original plan order. Group-flattening can reorder
    # independent steps after later dependency chains, which breaks stale-snippet
    # rebasing when a later change expects an earlier rename from the same block.
    ordered_complete_changes = complete_changes

    # Try to apply all complete changes in chain order.
    successful, failed, failure_details = rewriter.apply_all_changes(ordered_complete_changes)

    # Display changes with dependency grouping
    displayed = set()

    for chain_indices in complete_chains:
        if len(chain_indices) > 1:
            click.echo(click.style(f"   📦 Dependency Chain:", fg="magenta"))
            click.echo(f"      {graph.get_chain_summary(chain_indices)}")
            click.echo()

    for i, change in enumerate(changes, 1):
        if i - 1 in displayed:
            continue

        priority = change.priority.value if hasattr(change, 'priority') else "UNKNOWN"

        if change in incomplete_changes:
            click.echo(f"   ⏭️  [{i}] {change.display_title()} ({priority})")
            click.echo(f"      ⏭️  SKIPPED: Code snippet is truncated/incomplete")
            if _has_real_dependency(getattr(change, 'depends_on', None)):
                click.echo(f"      📌 Depends on: {change.depends_on}")
            click.echo()
        else:
            click.echo(f"   ✅ [{i}] {change.display_title()} ({priority})")
            click.echo(f"      ✅ AUTO-APPLYING: complete refactor block")
            if _has_real_dependency(getattr(change, 'depends_on', None)):
                click.echo(f"      📌 Depends on: {change.depends_on}")
            _render_change_code_block(change)
            click.echo()

        displayed.add(i - 1)

    if failed > 0:
        rewriter.rollback()
        click.echo(click.style(f"\n   ⚠️  {failed} change(s) could not be applied; rolling back the entire selection.", fg="yellow"))
        for idx, change in enumerate(complete_changes):
            if idx in failure_details:
                reason = failure_details.get(idx, "Code not found in file")
                click.echo(f"      ❌ {change.display_title()}")
                note = change.display_note()
                if note:
                    click.echo(f"         {click.style(note, fg='blue')}")
                _render_change_code_block(change)
                click.echo(f"         Reason: {reason}")
        click.echo(click.style("   No file changes were written because the refactor set was not fully successful.", fg="yellow"))
        return False

    if successful > 0:
        try:
            rewriter.write()
            _save_diff_report(fpath, rewriter, reports_dir)

            click.echo(click.style(f"   ✨ Successfully applied {successful} change(s):", fg="green"))
            for change in complete_changes[:successful]:
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

    if incomplete_changes:
        if incomplete_changes:
            click.echo(click.style(f"   ⚠️  {len(incomplete_changes)} change(s) skipped (incomplete/truncated)", fg="yellow"))
            for change in incomplete_changes:
                click.echo(f"      ⏭️ {change.display_title()}")

        if failed > 0:
            click.echo(click.style(f"   ⚠️  All {failed} complete change(s) failed to apply", fg="yellow"))
            for idx, change in enumerate(complete_changes):
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
    """Manage git operations for versioning and committing changes.
    
    PURPOSE:
    Interact with git repository for:
    - Staging and committing analysis/refactor results
    - Checking current branch and repository status
    - Managing version control integration
    - Recording decision history in git
    
    PARAMETERS:
    - file (required): File or directory path in git repo
    - --commit (-c): Commit message to stage and commit the file
    - --status (-s): Show git status for repository
    - --branch (-b): Display current branch name
    
    OUTPUTS:
    - Current branch information
    - Repository status (staged, unstaged, untracked files)
    - Confirmation of successful commits
    - Git integration status
    
    EXAMPLES:
    - noor git myfile.py --status                   # Show status
    - noor git myfile.py -s                         # Short form
    - noor git myfile.py --branch                   # Current branch
    - noor git myfile.py -b                         # Short form
    - noor git myfile.py --commit "Initial analysis" # Stage and commit
    - noor git myfile.py -c "Fixed security issues" # Short form
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


# -------------------- Phase 3: Decision Intelligence CLI Groups --------------------

# Add decision management commands
cli.add_command(decisions, name="decisions")

# Add decision history commands  
cli.add_command(history, name="history")

# Add analytics and metrics commands
cli.add_command(metrics, name="metrics")


# -------------------- Entrypoint --------------------

if __name__ == "__main__":
    cli()