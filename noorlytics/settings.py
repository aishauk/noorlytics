# noorlytics/settings.py
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
import os
from dotenv import load_dotenv, find_dotenv

def _as_bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}

@dataclass(frozen=True)
class Settings:
    # Compliance & keys
    compliance_mode: bool = field(default_factory=lambda: _as_bool("COMPLIANCE_MODE", "true"))
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")

    # Model selection
    model: str = os.getenv("NOOR_MODEL", "mistral:latest")
    num_ctx: int = int(os.getenv("NOOR_NUM_CTX", "4096"))

    # Ollama / server
    load_dotenv(find_dotenv(), override=True)
    ollama_api_url: str = os.getenv("OLLAMA_API_URL", "http://localhost:11434/api/chat")
    ollama_base: str = os.getenv("OLLAMA_BASE", "http://localhost:11434")
    http_timeout: float = float(os.getenv("NOOR_HTTP_TIMEOUT", "60"))
    keep_alive: str = os.getenv("NOOR_KEEP_ALIVE", "5m")

    # Generation params
    temp_analyze: float = float(os.getenv("NOOR_TEMP_ANALYZE", "0.0"))
    temp_refactor: float = float(os.getenv("NOOR_TEMP_REFACTOR", "0.0"))
    analyze_num_predict: int = int(os.getenv("NOOR_ANALYZE_NUM_PREDICT", "512"))
    refactor_num_predict: int = int(os.getenv("NOOR_REFACTOR_NUM_PREDICT", "1024"))

    # Chunking
    max_chunk_lines: int = int(os.getenv("NOOR_MAX_CHUNK_LINES", "120"))
    chunk_overlap: int = int(os.getenv("NOOR_CHUNK_OVERLAP", "20"))

    # IO / reports
    reports_dir: Path = Path(os.getenv("NOOR_REPORTS_DIR", "reports")).resolve()

    # CLI collection
    max_file_bytes: int = int(os.getenv("NOOR_MAX_FILE_BYTES", "100000"))
    allowed_ext: tuple[str, ...] = tuple(os.getenv("NOOR_ALLOWED_EXT", ".py").split(","))

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    s = Settings()
    s.reports_dir.mkdir(parents=True, exist_ok=True)
    return s