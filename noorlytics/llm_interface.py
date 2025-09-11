from __future__ import annotations

import json
from typing import List, Dict, Any, Optional

import openai
from rich.progress import Progress, SpinnerColumn, TextColumn

from .settings import get_settings
from . import net


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
            if not openai.api_key:
                raise RuntimeError("OPENAI_API_KEY is missing but mode=openai was chosen.")

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
            r = net.session().post(self.ollama_api_url, json=payload, timeout=self.http_timeout)
            r.raise_for_status()
            data = r.json()
            if "message" in data and isinstance(data["message"], dict):
                return data["message"].get("content", "")
            return data.get("response", "")
        else:
            completion = openai.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return completion.choices[0].message.content or ""

    # ----- High-level helpers -----

    def analyze_text(self, filename: str, content: str) -> str:
        sys = (
            "You analyze code for technical debt, risks, smells, and modernization opportunities. "
            "Return a concise Markdown report with sections: Summary, Findings, Impact, Suggested Actions."
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
            "You are a pragmatic senior engineer. Propose safe, incremental refactorings. "
            "Output: Markdown with a checklist of concrete steps and diff-style examples."
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
    return Progress(
        SpinnerColumn(),
        TextColumn("[bold]" + description + "[/bold]"),
        transient=True,
    )


def pretty_json(obj: Any) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False)