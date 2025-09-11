# noorlytics/logger.py
from pathlib import Path
from .settings import get_settings

def log_to_console(message: str):
    if not get_settings().compliance_mode:
        print(message)

def write_to_file(filepath: str | Path, content: str):
    if not get_settings().compliance_mode:
        p = Path(filepath)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

def append_to_file(filepath: str | Path, content: str):
    if not get_settings().compliance_mode:
        p = Path(filepath)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(content + "\n")
