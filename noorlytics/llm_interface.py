# noorlytics/llm_interface.py
# Unified interface for LLM interactions (OpenAI and Ollama).
# - Configured via settings.py (model choice, temps, timeouts).
# - Provides high-level methods for analysis, refactoring suggestions, and test generation.
# - Includes a simple CLI Markdown renderer with section headers.
from __future__ import annotations

import json
import requests
from pathlib import Path
from typing import List, Dict, Any, Optional

try:
    import openai
except ImportError:
    openai = None
from rich.progress import Progress, SpinnerColumn, TextColumn

from .settings import get_settings
from . import net


def _summarize_ollama_http_error(error: requests.exceptions.HTTPError) -> str:
    """Build a user-facing Ollama HTTP error message with response details."""
    response = error.response
    body_text = ""

    if response is not None:
        try:
            payload = response.json()
        except ValueError:
            payload = None

        if isinstance(payload, dict):
            body_text = str(payload.get("error") or payload.get("message") or "").strip()

        if not body_text:
            try:
                body_text = response.text.strip()
            except Exception:
                body_text = ""

    if len(body_text) > 400:
        body_text = body_text[:397] + "..."

    details = [
        "Ollama returned an HTTP error.",
        "",
        f"URL: {response.url if response is not None else 'unknown'}",
        f"Error: {error}",
    ]

    if response is not None:
        details.append(f"Status: {response.status_code}")
    if body_text:
        details.append(f"Response body: {body_text}")

    return "\n".join(details)


def check_ollama_available(timeout: float = 2.0) -> bool:
    """Quick health check against the Ollama base endpoint."""
    s = get_settings()
    try:
        r = net.session().get(s.ollama_base, timeout=timeout)
        return r.status_code == 200
    except Exception:
        return False


class LLMClient:
    """
    Unified client for OpenAI and Ollama backends with a shared chat interface.
    All configuration comes from settings.py; no direct env lookups.
    """

    def __init__(self, mode: Optional[str] = None, model: Optional[str] = None):
        S = get_settings()
        self.mode = (mode or ("openai" if S.openai_api_key else "ollama")).lower()
        self.model = model or S.model

        # OpenAI setup
        if self.mode == "openai":
            if openai is None:
                raise RuntimeError(
                    "OpenAI support is not installed. Install it with: python -m pip install 'noorlytics[openai]'"
                )
            if not S.openai_api_key:
                raise RuntimeError("OPENAI_API_KEY is missing but mode=openai was chosen.")
            openai.api_key = S.openai_api_key

        # Shared defaults
        self.http_timeout = S.http_timeout
        self.temp_analyze = S.temp_analyze
        self.temp_refactor = S.temp_refactor
        self.analyze_num_predict = S.analyze_num_predict
        self.refactor_num_predict = S.refactor_num_predict

        # Ollama endpoints
        self.ollama_api_url = S.ollama_api_url
        self.ollama_base = S.ollama_base
        self.keep_alive = S.keep_alive

    def warmup(self) -> None:
        """Optional warmup call to reduce first-call latency."""
        if self.mode == "ollama":
            try:
                # Fetch tags to wake the daemon, then send a short keepalive message.
                net.session().get(f"{self.ollama_base}/api/tags", timeout=3.0)
                payload = {
                    "model": self.model,
                    "messages": [{"role": "system", "content": "warmup"}],
                    "stream": False,
                    "keep_alive": self.keep_alive,
                    "options": {"temperature": 0.0, "num_predict": 1},
                }
                net.session().post(self.ollama_api_url, json=payload, timeout=5.0)
            except Exception:
                pass
        else:
            return

    def chat(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Shared chat interface returning plain text."""
        if self.mode == "ollama":
            payload = {
                "model": self.model,
                "messages": messages,
                "stream": False,
                "keep_alive": self.keep_alive,
                "options": {
                    "temperature": temperature,
                    **({"num_predict": max_tokens} if max_tokens else {}),
                },
            }

            try:
                r = net.session().post(self.ollama_api_url, json=payload, timeout=self.http_timeout)
                r.raise_for_status()
            except requests.exceptions.ConnectionError:
                raise RuntimeError(
                    "Could not connect to Ollama.\n\n"
                    f"Noorlytics tried to reach: {self.ollama_api_url}\n\n"
                    "Start Ollama with:\n"
                    "  ollama serve\n\n"
                    "Then make sure your model is installed:\n"
                    f"  ollama pull {self.model}\n\n"
                    "Or use OpenAI mode:\n"
                    "  noor --mode openai analyze <path>"
                )
            except requests.exceptions.Timeout:
                raise RuntimeError(
                    "Ollama did not respond in time.\n\n"
                    f"Current timeout: {self.http_timeout}s\n\n"
                    "Try increasing it:\n"
                    "  export NOOR_HTTP_TIMEOUT=300\n\n"
                    "Or reduce output size:\n"
                    "  export NOOR_ANALYZE_NUM_PREDICT=160"
                )
            except requests.exceptions.HTTPError as e:
                raise RuntimeError(_summarize_ollama_http_error(e))

            data = r.json()
            if "message" in data and isinstance(data["message"], dict):
                return data["message"].get("content", "")
            return data.get("response", "")

        if openai is None:
            raise RuntimeError(
                "OpenAI support is not installed. Install it with: python -m pip install 'noorlytics[openai]'"
            )
        completion = openai.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return completion.choices[0].message.content or ""

    # ----- High-level helpers -----

    def analyze_text(self, filename: str, content: str) -> str:
        # Slightly opinionated prompt to keep headings stable for the CLI renderer.
        sys = (
            "You are Noorlytics, a senior engineering risk analyst.\n"
            "Your job is to identify what matters most and what should be fixed first.\n\n"

            "Analyze the code for production bugs, data correctness, security/privacy risks, performance, reliability, and maintainability.\n\n"

            "Return concise Markdown with EXACTLY these H2 headings in this order:\n"
            "## Executive Summary\n"
            "## Top Risks\n"
            "## Impact & Risk\n"
            "## Highest-ROI Recommendations\n\n"

            "CRITICAL ANALYSIS RULES:\n"
            "1. BE SPECIFIC: Reference actual code patterns, function names, logic flows. Never generic advice.\n"
            "2. IDENTIFY ROOT CAUSE: Not just symptoms. Why does this code pattern create risk?\n"
            "3. QUANTIFY IMPACT: Describe concrete user/system/developer impact (data loss, security exposure, performance degradation).\n"
            "4. SCORE SEVERITY: Combine likelihood (High/Med/Low) × Impact (Critical/High/Med/Low) → Priority.\n"
            "5. PROVIDE EVIDENCE: Point to specific lines, patterns, or assumptions visible in the code.\n"
            "6. ACTIONABLE FIX: Each risk must have a clear remediation (not just 'review code').\n\n"

            "In ## Top Risks:\n"
            "- List up to 5 risks, ordered by priority (severity × likelihood).\n"
            "- Use this format:\n"
            "  - [P1 Critical] Short title (specific, not generic)\n"
            "    - Category: Security/Performance/Reliability/DataCorrectness/Maintainability\n"
            "    - Severity: Critical/High/Medium/Low\n"
            "    - Likelihood: High/Medium/Low\n"
            "    - Evidence: Point to specific code pattern or function\n"
            "    - Why it matters: Concrete consequence (data loss, security breach, performance drop)\n"
            "    - Suggested fix: What to change and how\n\n"

            "In ## Impact & Risk:\n"
            "- Quantify real-world impact:\n"
            "  - USER IMPACT: Data loss, security exposure, availability issues\n"
            "  - SYSTEM IMPACT: Performance degradation, resource exhaustion, cascading failures\n"
            "  - DEVELOPER IMPACT: Technical debt, testing difficulty, debugging complexity\n\n"

            "In ## Highest-ROI Recommendations:\n"
            "- Rank by effort-to-impact ratio (highest ROI first).\n"
            "- For each recommendation include:\n"
            "  - What: Specific change or refactoring\n"
            "  - Why: How it reduces risk\n"
            "  - Effort: Small (< 1 hour) / Medium (1-4 hours) / Large (> 4 hours)\n"
            "  - Impact: Risk reduction, performance gain, maintainability improvement\n"
            "  - Validation: How to test the fix works\n\n"

            "Rules:\n"
            "- Be specific to the provided code; avoid generic advice.\n"
            "- Prefer fewer, higher-value findings over long lists.\n"
            "- Do not invent behavior not visible in the code. If uncertain, state assumptions.\n"
        )
        
        user = f"File: {filename}\n\n```text\n{content}\n```"
        return self.chat(
            [
                {"role": "system", "content": sys},
                {"role": "user", "content": user},
            ],
            temperature=self.temp_analyze,
            max_tokens=self.analyze_num_predict,
        )

    def suggest_refactors(self, filename: str, content: str) -> str:
        sys = (
            "You are a pragmatic senior engineer specializing in refactoring. "
            "Analyze code for maintainability, performance, and design improvements.\n\n"
            "CRITICAL REFACTORING RULES:\n"
            "1. Propose only SAFE, TESTED refactorings that preserve behavior\n"
            "2. Provide CONCRETE BEFORE/AFTER code examples, not abstract descriptions\n"
            "3. Explain the BENEFIT of each refactoring (e.g., reduced complexity, better testability, performance gain)\n"
            "4. List SPECIFIC RISKS or edge cases to watch for during implementation\n"
            "5. Organize by PRIORITY: quick wins first, then architectural improvements\n"
            "6. Include VALIDATION STRATEGY: how to test each refactoring doesn't break functionality\n\n"
            "Output format:\n"
            "- Use Markdown with clear headers (##) for each refactoring\n"
            "- Include code blocks marked with ```python or appropriate language\n"
            "- Add a checklist (- [ ]) of implementation steps\n"
            "- Prioritize: [HIGH] quick improvements, [MEDIUM] structural, [LOW] style"
        )
        user = f"File: {filename}\n\n```text\n{content}\n```"
        return self.chat(
            [
                {"role": "system", "content": sys},
                {"role": "user", "content": user},
            ],
            temperature=self.temp_refactor,
            max_tokens=self.refactor_num_predict,
        )

    def refactor(self, filename: str, content: str) -> str:
        """Generate detailed refactoring implementation plan with step-by-step guidance."""
        sys = (
            "You are an expert code refactoring architect. Your goal is to create a detailed, "
            "ACTIONABLE refactoring implementation plan that a developer can execute with confidence.\n\n"
            "CRITICAL REFACTORING IMPLEMENTATION RULES:\n"
            "1. START WITH ASSESSMENT: Identify code smells, complexity issues, and design problems\n"
            "2. PROPOSE INCREMENTAL STEPS: Break large refactorings into small, testable changes\n"
            "3. PROVIDE COMPLETE CODE: Show full BEFORE and AFTER code blocks for each change\n"
            "4. EXPLAIN EACH CHANGE: Why this change matters + specific benefits (performance/readability/maintainability)\n"
            "5. BACKWARDS COMPATIBILITY: Address API compatibility, deprecation paths, and migration needs\n"
            "6. DETAILED TESTING PLAN: Specify exactly what to test and how to validate each step\n"
            "7. ROLLBACK STRATEGY: If something breaks, how to safely revert with minimal impact\n\n"
            "IMPLEMENTATION CHECKLIST FORMAT:\n"
            "For EACH refactoring, provide:\n"
            "- [HIGH/MEDIUM/LOW] priority tag\n"
            "- Problem statement (1-2 sentences of current issue)\n"
            "- Solution (concrete change with BEFORE/AFTER code blocks)\n"
            "- Implementation steps as nested checklist (- [ ])\n"
            "- Validation instructions (how to test this specific change)\n"
            "- Estimated impact on: readability, performance, maintainability\n"
            "- Potential breakage points or edge cases\n\n"
            "QUALITY CRITERIA FOR REFACTORING:\n"
            "✓ Every suggested change must be implementable by a mid-level developer\n"
            "✓ Code examples must be copy-paste ready (no pseudocode)\n"
            "✓ Testing strategy must be specific to the change (not generic)\n"
            "✓ Prioritize quick wins (under 1 hour) before major refactors\n"
            "✓ Never suggest refactoring without showing impact"
        )
        user = f"File: {filename}\n\nImplement detailed refactoring plan:\n\n```text\n{content}\n```"
        return self.chat(
            [
                {"role": "system", "content": sys},
                {"role": "user", "content": user},
            ],
            temperature=self.temp_refactor,
            max_tokens=self.refactor_num_predict,
        )

    def generate_tests(self, filename: str, content: str, language_hint: str = "python") -> str:
        sys = (
            "You generate minimal, robust unit test skeletons with clear Arrange-Act-Assert. "
            "Prefer deterministic seams and fake data. Avoid over-mocking."
        )
        user = f"Language: {language_hint}\nTarget file: {filename}\n\n```text\n{content}\n```"
        return self.chat(
            [
                {"role": "system", "content": sys},
                {"role": "user", "content": user},
            ],
            temperature=self.temp_analyze,
            max_tokens=self.analyze_num_predict,
        )


def render_progress(description: str):
    """Small progress spinner renderer used by CLI commands."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[bold]" + description + "[/bold]"),
        transient=True,
    )


def pretty_json(obj: Any) -> str:
    """Deterministic pretty JSON (UTF-8, two spaces)."""
    return json.dumps(obj, indent=2, ensure_ascii=False)

# --- Minimal pretty CLI renderer for Markdown output (analyze/suggest/refactor) ---

def render_markdown_cli(title: str, md_text: str, saved_path: Optional[Path] = None) -> None:
    """
    Pretty-print a Markdown report with colored section headers.
    No big box header, just clean dividers per section.
    """
    try:
        import os
        from rich.console import Console
        from rich.rule import Rule
        from rich.markdown import Markdown

        if os.environ.get("NO_COLOR"):
            raise RuntimeError("NO_COLOR set")

        console = Console(highlight=False, force_terminal=True)

        # Split on H2 headings ("## ")
        sections = []
        current_title = None
        current_lines = []
        for line in md_text.splitlines():
            if line.startswith("## "):
                if current_title is not None:
                    sections.append((current_title, "\n".join(current_lines).strip()))
                current_title = line[3:].strip()
                current_lines = []
            else:
                current_lines.append(line)
        if current_title is not None:
            sections.append((current_title, "\n".join(current_lines).strip()))
        else:
            sections = [("Report", md_text.strip())]

        # Color per section
        colors = {
            "summary": "bright_cyan",
            "findings": "magenta",
            "impact": "yellow",
            "suggested actions": "green",
            "suggestions": "green",
        }

        # Print each section with a colored rule
        console.print(f"[bold underline]{title}[/bold underline]\n", style="bright_green")
        for sec_title, body in sections:
            key = sec_title.lower()
            color = colors.get(key, "bright_cyan")
            console.print(Rule(f"[bold]{sec_title}[/bold]", style=color))
            console.print(Markdown(body or "_(empty)_", code_theme="ansi_dark"))
            console.print()

        if saved_path:
            demo_path = _relpath_for_demo(saved_path, base=saved_path.parent.parent)  # show "reports/…"
            console.print(f"[bold green]Saved →[/bold green] [italic]{demo_path}[/]")

    except Exception:
        # Plain fallback (no Rich / NO_COLOR)
        print(md_text)
        if saved_path:
            demo_path = _relpath_for_demo(saved_path, base=saved_path.parent.parent)
            print(f"\nSaved → {demo_path}")


def _relpath_for_demo(p: Path, base: Optional[Path] = None) -> str:
    """
    Return a shortened path for demo display.
    If base is given (e.g., project root or reports dir), return relative to that.
    Otherwise just the last two path parts.
    """
    try:
        if base and p.is_absolute():
            return str(p.relative_to(base))
    except Exception:
        pass
    # Fallback: keep only the tail
    parts = p.parts
    return str(Path(*parts[-2:]))