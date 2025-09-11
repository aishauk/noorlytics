"""
add_tests.py

Provides functionality to generate unit test stubs for a given source file
using the configured LLM backend (Ollama or OpenAI).

The generated tests are saved in the reports directory as <filename>.tests.py
"""

from pathlib import Path
from noorlytics.settings import get_settings
from noorlytics.llm_interface import LLMClient


def generate_unit_tests(path: Path, mode: str | None = None, language_hint: str = "python") -> Path:
    """
    Generate unit test stubs for the given file.

    Args:
        path (Path): Path to the source file to analyze.
        mode (str|None): LLM backend ("ollama" or "openai"). If None, defaults to settings.
        language_hint (str): Programming language (default: "python").

    Returns:
        Path: The path to the generated test file.
    """
    S = get_settings()
    client = LLMClient(mode=mode)
    client.warmup()

    # Read source code
    code = path.read_text(encoding="utf-8", errors="ignore")

    # Ask LLM to generate tests
    tests = client.generate_tests(filename=path.name, content=code, language_hint=language_hint)

    # Write output to reports/<filename>.tests.py
    out_file = S.reports_dir / f"{path.stem}.tests.py"
    out_file.write_text(tests, encoding="utf-8")

    return out_file