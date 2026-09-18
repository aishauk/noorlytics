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


# ---------- general test prompt ----------

GENERAL_TEST_PROMPT = """You generate executable unit tests ONLY.
Requirements:
- Output: **code only**. No markdown, no comments outside the code.
- Do NOT repeat the source code. Do not explain.
- Detect the language and use the idiomatic testing framework for that language:
  * Python: pytest (use `uut` import harness if provided)
  * JavaScript/TypeScript: Jest or Vitest
  * Java: JUnit
  * C#: NUnit or xUnit
  * Go: Go testing package
  * Ruby: RSpec or Minitest
- Write fast, deterministic tests (no I/O, no network, no sleeps, no infinite loops).
- Use idiomatic test naming (test_*, describe/it, TestXxx, etc. depending on language).
- Prefer AAA pattern and focused assertions.

Critical quality rules:
- **Test behavior, not just existence**: Don't just check hasattr() or that a function exists. Call the function and verify it returns correct output.
- **Test both success and failure paths**: Include tests for error cases, exceptions, edge cases, empty inputs.
- **Use mocking for external dependencies**: Mock network calls, file I/O, database queries using unittest.mock (Python), jest.mock (JS), etc.
- **Use specific assertions**: Assert exact values, not just truthiness. Example: `self.assertEqual(result, expected)` not `self.assertTrue(result)`.
- **Create fixtures/helpers for complex setup**: Build helper functions or classes (like fake objects) to simulate external dependencies.
- **Identify and test private methods that are critical**: If a private method (_func) handles important logic (parsing, error handling), test it directly.
- **If functionality is hard to exercise safely** (e.g., async/GUI/main loops), write focused smoke tests that verify key behavior works.

Produce ONLY code in the detected language below.
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


def _detect_language_from_extension(path: Path) -> str:
    """Auto-detect language from file extension."""
    ext_map = {
        ".py": "python",
        ".js": "js",
        ".ts": "ts",
        ".jsx": "js",
        ".tsx": "ts",
        ".java": "java",
        ".cs": "csharp",
        ".go": "go",
        ".rb": "ruby",
        ".cpp": "cpp",
        ".c": "c",
        ".h": "c",
        ".php": "php",
    }
    return ext_map.get(path.suffix.lower(), "python")


def _fallback_pytest_skeleton(pub_funcs: List[str]) -> str:
    lines = [
        "import unittest",
        "from unittest.mock import patch, MagicMock",
        "",
        "class TestModule(unittest.TestCase):",
        "    def test_module_imports(self):",
        "        \"\"\"Verify the module loads without errors.\"\"\"",
        "        self.assertTrue(hasattr(uut, '__dict__'))",
        "        self.assertGreater(len(dir(uut)), 0)",
        "",
    ]
    
    # For each public function, create a placeholder test with better structure
    for fn in pub_funcs[:8]:  # limit to avoid bloat
        lines += [
            f"    def test_{fn}_exists_and_callable(self):",
            f"        \"\"\"Verify {fn}() exists and is callable.\"\"\"",
            f"        self.assertTrue(hasattr(uut, '{fn}'))",
            f"        self.assertTrue(callable(getattr(uut, '{fn}')))",
            "",
        ]
    
    lines.append("")
    lines.append("if __name__ == '__main__':")
    lines.append("    unittest.main()")
    
    return "\n".join(lines) + "\n"


def _detect_test_style(tests_code: str) -> str:
    if re.search(r"^def\s+test_", tests_code, re.MULTILINE):
        return "pytest"
    if "unittest.TestCase" in tests_code:
        return "unittest"
    return "pytest"


def _assess_test_quality(code: str) -> int:
    """Score test quality 0-100. Lower scores indicate weak/generic tests."""
    score = 0
    
    # Check for behavior testing (not just existence checks)
    has_assertEqual = "assertEqual" in code or "assert" in code.lower()
    if has_assertEqual:
        score += 20
    
    # Check for error/edge case testing
    has_error_tests = "assertRaises" in code or "raises" in code or "Exception" in code
    if has_error_tests:
        score += 15
    
    # Check for mocking (external dependency isolation)
    has_mocking = "@patch" in code or "MagicMock" in code or "mock" in code.lower()
    if has_mocking:
        score += 20
    
    # Check for meaningful test names (not just "test_1")
    test_count = len(re.findall(r"def test_[a-zA-Z_]", code))
    if test_count > 0:
        score += 10
    
    # Check for docstrings/comments (indicates understanding)
    has_docs = '"""' in code or "'''" in code or re.search(r"#.*test", code, re.IGNORECASE)
    if has_docs:
        score += 10
    
    # Check for helper classes/fixtures (indicates sophistication)
    has_helpers = "class " in code and "Test" not in code.split("class")[1].split(":")[ 0]
    if has_helpers:
        score += 25
    
    return min(score, 100)





# ---------- public API ----------

def generate_unit_tests(path: Path, mode: str | None = None, language_hint: str = "python") -> Path:
    """
    Generate unit test stubs for the given file and write to tests/<stem>.tests.py.
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
    tests_dir = S.tests_dir
    out_file = tests_dir / f"{path.stem}.tests.py"
    out_file.parent.mkdir(parents=True, exist_ok=True)

    # --- compute path from tests/ to the source file (for the import harness) ---
    # Minimal fix: use os.path.relpath against the tests dir; fallback to absolute.
    # This avoids ValueError: "is not in the subpath of '/.../tests'".
    import os
    try:
        rel_from_tests = os.path.relpath(path.resolve(), tests_dir.resolve())
    except Exception:
        rel_from_tests = str(path.resolve())

    # Determine if this is Python for the import harness
    is_python = path.suffix.lower() == ".py"
    
    # LLM: general prompt → code only
    if is_python:
        # Python gets the special import harness + enhanced guidance
        system = GENERAL_TEST_PROMPT + f"""

For Python files specifically:

1. The import harness is already at the top of the file:
    import importlib.util, pathlib
    _SRC = (pathlib.Path(__file__).resolve().parent / r"{rel_from_tests}")
    _SPEC = importlib.util.spec_from_file_location("{path.stem}", _SRC)
    uut = importlib.util.module_from_spec(_SPEC)
    _SPEC.loader.exec_module(uut)

   Reference module functions as uut.function_name()

2. Use unittest.mock.patch for external dependencies (HTTP, files, APIs).
   Example: from unittest.mock import patch
            @patch('requests.get')
            def test_my_function(self, mock_get): ...

3. Test both success AND failure cases:
   - Happy path (normal inputs)
   - Error paths (exceptions, bad data)
   - Edge cases (empty inputs, None, large values)

4. Create helper classes/functions for complex mocking:
   class FakeResponse:
       def __init__(self, status_code, json_data):
           self.status_code = status_code
           self._json = json_data
       def json(self):
           return self._json

5. Use specific assertions:
   - self.assertEqual(actual, expected) for exact matches
   - self.assertIn(substring, text) for string checks
   - self.assertRaises(ExceptionType) for error cases
   - self.assertIsNone(), self.assertTrue(), etc. for specific checks

6. Keep tests focused: one test per behavior, not one test per function.

Do not use: @patch decorators require careful mocking; build fake objects instead if simpler.
"""
    else:
        system = GENERAL_TEST_PROMPT
    
    user = f"Source file: {path.name}\n\n```\n{src_text}\n```"

    raw = client.chat(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.0,
        max_tokens=get_settings().analyze_num_predict,
    )

    body = _extract_code_block(raw)

    # Build final test module
    header = _make_header_banner(path, language_hint, getattr(client, "mode", None))
    harness = _import_harness(rel_from_tests, path.stem) if is_python else ""
    tests_code = header + harness + body.strip() + "\n"

    # Validate; fallback only for Python files
    used_fallback = False
    quality_score = 0
    
    if is_python:
        quality_score = _assess_test_quality(tests_code)
        
        # Use fallback if: (1) doesn't look like tests, (2) doesn't compile, or (3) very low quality
        if not _looks_like_tests(tests_code) or not _compiles(tests_code) or quality_score < 25:
            pub = _public_functions_from_source(src_text)
            skeleton = _fallback_pytest_skeleton(pub)
            tests_code = header + harness + skeleton
            used_fallback = True
            quality_score = _assess_test_quality(tests_code)

    # Write tests and meta
    out_file.write_text(tests_code, encoding="utf-8")
    try:
        meta = {
            "source": str(path),
            "out_file": str(out_file),
            "backend": getattr(client, "mode", None),
            "style": _detect_test_style(tests_code),
            "has_tests": _looks_like_tests(tests_code),
            "quality_score": quality_score,
            "used_fallback": used_fallback,
            "notes": "Quality score 0-100: 0-30=weak (placeholder), 30-60=acceptable, 60-100=strong" if is_python else None,
        }
        (S.tests_dir / f"{path.stem}.tests.meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
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
        console.print()  # blank line

    except Exception:
        print(f"\n[Unit tests generated] {out_path}")
        print("Run: pytest -q", out_path)