# noorlytics/add_tests.py
"""
Generate unit test stubs with hard guardrails:
- Strict LLM prompt (code only, pytest by default)
- Import harness (uut) that loads the source file reliably from reports/
- Sanitize markdown fences
- Compile check; fallback to minimal pytest skeleton if needed
- Pretty CLI rendering (Rich), with next-step command
"""

from __future__ import annotations

import ast
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from noorlytics.settings import get_settings
from noorlytics.llm_interface import LLMClient


# ---------- strict prompt ----------

STRICT_TEST_PROMPT = """You generate executable unit tests ONLY.
Requirements:
- Framework: {framework} (default pytest).
- Output: ONE Python module, **code only**. No markdown, no comments outside Python.
- Do NOT repeat the source code. Do not explain.
- Import the module under test as `uut`; assume the following lines already exist at the top of the file:

    import importlib.util, pathlib
    _SRC = (pathlib.Path(__file__).resolve().parent / r"{rel_path}")
    _SPEC = importlib.util.spec_from_file_location("{module_name}", _SRC)
    uut = importlib.util.module_from_spec(_SPEC)
    _SPEC.loader.exec_module(uut)

- Write fast, deterministic tests (no I/O, no network, no sleeps, no infinite loops).
- Name tests `test_*`. Prefer AAA pattern and focused assertions.
- If functionality is hard to exercise safely (e.g., GUI/main loop), write smoke tests that import, create objects, and assert invariants without starting loops.

Produce ONLY Python code for tests below.
"""


# ---------- helpers ----------

def _extract_code_block(text: str) -> str:
    """If the LLM returned ```...``` fences, extract the first code block."""
    m = re.search(r"```(?:python)?\n(.*?)\n```", text, flags=re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else text.strip()


def _public_functions_from_source(src: str) -> List[str]:
    """Grab top-level public function names for fallback skeleton."""
    try:
        tree = ast.parse(src)
    except Exception:
        return []
    names: List[str] = []
    for n in tree.body:
        if isinstance(n, ast.FunctionDef) and not n.name.startswith("_"):
            names.append(n.name)
    return names


def _make_header_banner(src_path: Path, language: str, backend: str | None) -> str:
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%SZ")
    return (
        "# === Noorlytics Auto-Generated Tests ===\n"
        f"# Source:    {src_path}\n"
        f"# Generated: {ts}\n"
        f"# Language:  {language}\n"
        f"# Backend:   {backend or 'auto'}\n"
        "# --------------------------------------\n"
    )


def _import_harness(rel_path: str, module_name: str) -> str:
    return (
        "import importlib.util, pathlib\n"
        f"_SRC = (pathlib.Path(__file__).resolve().parent / r\"{rel_path}\")\n"
        f"_SPEC = importlib.util.spec_from_file_location(\"{module_name}\", _SRC)\n"
        "uut = importlib.util.module_from_spec(_SPEC)\n"
        "_SPEC.loader.exec_module(uut)\n\n"
    )


def _looks_like_tests(code: str) -> bool:
    return bool(re.search(r"^def\s+test_[A-Za-z0-9_]+\(", code, flags=re.MULTILINE))


def _compiles(code: str) -> bool:
    try:
        compile(code, "<tests>", "exec")
        return True
    except Exception:
        return False


def _fallback_pytest_skeleton(pub_funcs: List[str]) -> str:
    lines = [
        "def test_module_imports():",
        "    assert hasattr(uut, '__dict__')",
        "",
    ]
    # non-breaking sanity checks for public funcs
    for fn in pub_funcs[:10]:
        lines += [
            f"def test_has_function_{fn}():",
            f"    assert hasattr(uut, '{fn}')",
            "",
        ]
    return "\n".join(lines) + "\n"


def _detect_test_style(tests_code: str) -> str:
    if re.search(r"^def\s+test_", tests_code, re.MULTILINE):
        return "pytest"
    if "unittest.TestCase" in tests_code:
        return "unittest"
    return "pytest"


# ---------- public API ----------

def generate_unit_tests(path: Path, mode: str | None = None, language_hint: str = "python") -> Path:
    """
    Generate unit test stubs for the given file and write to reports/<stem>.tests.py.
    Returns the output path.
    """
    S = get_settings()
    client = LLMClient(mode=mode)
    try:
        client.warmup()
    except Exception:
        pass

    # Read source & derive paths
    src_text = path.read_text(encoding="utf-8", errors="ignore")
    out_file = S.reports_dir / f"{path.stem}.tests.py"
    out_file.parent.mkdir(parents=True, exist_ok=True)

    # --- compute path from reports/ to the source file (for the import harness) ---
    # Minimal fix: use os.path.relpath against the reports dir; fallback to absolute.
    # This avoids ValueError: "is not in the subpath of '/.../reports'".
    import os  # CHANGED
    try:  # CHANGED
        rel_from_reports = os.path.relpath(path.resolve(), S.reports_dir.resolve())  # CHANGED
    except Exception:  # CHANGED
        rel_from_reports = str(path.resolve())  # CHANGED

    # LLM: strict prompt → code only
    system = STRICT_TEST_PROMPT.format(
        framework="pytest" if language_hint.lower() == "python" else "pytest",
        rel_path=rel_from_reports,
        module_name=path.stem,
    )
    user = f"Source file: {path.name}\n\n```python\n{src_text}\n```"

    raw = client.chat(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.0,
        max_tokens=get_settings().analyze_num_predict,
    )

    body = _extract_code_block(raw)

    # Build final test module
    header = _make_header_banner(path, language_hint, getattr(client, "mode", None))
    harness = _import_harness(rel_from_reports, path.stem)
    tests_code = header + harness + body.strip() + "\n"

    # Validate; fallback if needed
    if not _looks_like_tests(tests_code) or not _compiles(tests_code):
        pub = _public_functions_from_source(src_text)
        skeleton = _fallback_pytest_skeleton(pub)
        tests_code = header + harness + skeleton

    # Write tests and meta
    out_file.write_text(tests_code, encoding="utf-8")
    try:
        meta = {
            "source": str(path),
            "out_file": str(out_file),
            "backend": getattr(client, "mode", None),
            "style": _detect_test_style(tests_code),
            "has_tests": _looks_like_tests(tests_code),
        }
        (S.reports_dir / f"{path.stem}.tests.meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    except Exception:
        pass

    return out_file


def render_tests_cli(out_path: Path) -> None:
    """Syntax-highlighted preview + next steps (Rich if available, else plain)."""
    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table
        from rich.syntax import Syntax
        from rich.rule import Rule
        import os

        S = get_settings()
        console = Console()
        tests_text = Path(out_path).read_text(encoding="utf-8", errors="ignore")

        # Demo-safe path
        try:
            base = getattr(S, "root_dir", None)
            if base:
                demo_path = os.path.relpath(Path(out_path).resolve(), Path(base).resolve())
            else:
                demo_path = os.path.relpath(Path(out_path).resolve(), S.reports_dir.resolve().parent)
        except Exception:
            demo_path = str(out_path)

        style = _detect_test_style(tests_text)
        has_tests = _looks_like_tests(tests_text)

        # --- Header ---
        console.print()  # blank line
        console.print(Rule("[bold cyan]Unit tests generated[/bold cyan]", style="green"))
        console.print()  # blank line

        tbl = Table.grid(padding=(0, 2))
        tbl.add_row("📄 File", demo_path)
        tbl.add_row("🧪 Style", style)
        tbl.add_row("✅ Contains tests", "yes" if has_tests else "fallback")
        console.print(tbl)
        console.print()  # blank line

        # --- Code preview ---
        lines = tests_text.splitlines()[:200]
        # Insert a blank line at the top so the banner starts on its own row
        if lines and lines[0].startswith("# === Noorlytics Auto-Generated Tests"):
            lines.insert(0, "")
        preview = "\n".join(lines)

        console.print(Rule(style="cyan"))
        console.print()
        console.print(Syntax(preview, "python", line_numbers=True, start_line=1))
        console.print(Rule(style="cyan"))


        # --- Next step box ---
        cmd = f"pytest -q {demo_path}" if style == "pytest" else f"python -m unittest {demo_path}"
        console.print(Panel.fit(f"Next step:\n[bold]{cmd}[/bold]", border_style="cyan"))
        console.print()  # blank line

    except Exception:
        print(f"\n[Unit tests generated] {out_path}")
        print("Run: pytest -q", out_path)