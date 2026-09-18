"""Manual smoke test for the configured Noorlytics LLM backend."""

from .llm_interface import LLMClient


def main() -> None:
    client = LLMClient()
    print(client.suggest_refactors("example.py", "def add(a, b): return a + b"))


if __name__ == "__main__":
    main()
