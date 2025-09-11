from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional

from .settings import get_settings
from . import net
from .llm_interface import LLMClient


# ----- Ecosystem detection -----

def detect_ecosystem(filename: str, content: str) -> str:
    """Very simple heuristic. Extend as needed."""
    name = filename.lower()
    if "requirements" in name or name.endswith(".txt"):
        return "python"
    if name.endswith("pyproject.toml"):
        return "python"
    if name.endswith("package.json"):
        return "node"
    if name.endswith("pom.xml") or name.endswith(".gradle"):
        return "java"
    return "unknown"


# ----- Parsers -----

def parse_requirements_txt(text: str) -> List[Tuple[str, Optional[str]]]:
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"([A-Za-z0-9_.\-]+)\s*(?:==|>=|<=|~=|>|<)?\s*([A-Za-z0-9_.\-]+)?", line)
        if m:
            out.append((m.group(1), m.group(2)))
    return out


def parse_package_json(text: str) -> Dict[str, str]:
    try:
        data = json.loads(text)
    except Exception:
        return {}
    deps = {}
    for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        if key in data and isinstance(data[key], dict):
            deps.update(data[key])
    return deps


def parse_pyproject(text: str) -> List[Tuple[str, Optional[str]]]:
    pkgs: List[Tuple[str, Optional[str]]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if re.match(r"[A-Za-z0-9_.\-]+", line) and any(op in line for op in ("=", ">", "<", "~")):
            name = re.split(r"[><=~! ]+", line)[0]
            version = None
            m = re.search(r"([0-9]+\.[0-9]+(?:\.[0-9]+)?)", line)
            if m:
                version = m.group(1)
            pkgs.append((name, version))
    return pkgs


# ----- License screening (simple baseline) -----

RISKY_LICENSES = {
    "GPL", "GPL-2.0", "GPL-3.0",
    "AGPL", "AGPL-3.0",
    "LGPL", "LGPL-2.1", "LGPL-3.0",
    "UNKNOWN", "NONE", None,
}


# ----- API helpers -----

def _ollama_models() -> List[str]:
    """Return list of locally available Ollama models (best-effort)."""
    S = get_settings()
    try:
        resp = net.session().get(f"{S.ollama_base}/api/tags", timeout=3.0)
        resp.raise_for_status()
        data = resp.json()
        models = [m.get("model") for m in data.get("models", []) if isinstance(m, dict)]
        return [m for m in models if m]
    except Exception:
        return []


# ----- Main dependency analysis -----

def analyze_dependencies_file(path: Path, client: LLMClient) -> Dict[str, Any]:
    """
    Parse a dependency file and return a normalized summary:
    {
      "ecosystem": "python|node|java|unknown",
      "dependencies": [{"name":..., "version":...}, ...],
      "license_risk": [{"name":..., "license":..., "risk": "high|medium|low"}],
      "notes": "...",
    }
    """
    text = path.read_text(encoding="utf-8", errors="ignore")
    eco = detect_ecosystem(path.name, text)

    deps: List[Dict[str, Any]] = []
    if eco == "python":
        if path.name.endswith("requirements.txt") or path.suffix == ".txt":
            pairs = parse_requirements_txt(text)
        else:
            pairs = parse_pyproject(text)
        deps = [{"name": n, "version": v} for (n, v) in pairs]
    elif eco == "node":
        m = parse_package_json(text)
        deps = [{"name": k, "version": v} for k, v in m.items()]
    else:
        deps = []

    # License screening (placeholder – could be extended with SPDX or OSV data)
    license_risk: List[Dict[str, Any]] = []
    for d in deps:
        lic = "UNKNOWN"
        risk = "high" if lic in RISKY_LICENSES else "low"
        license_risk.append({"name": d["name"], "license": lic, "risk": risk})

    # LLM-based summary for risks and suggestions
    summary = ""
    if deps:
        prompt = (
            "Given this dependency list, identify potential risks:\n"
            "- deprecated libs\n- known high-profile vulnerabilities (if any)\n"
            "- risky licenses (GPL/AGPL/LGPL/Unknown)\n"
            "Suggest safer alternatives if applicable.\n"
            "Answer concisely in Markdown with sections: Risks, Suggestions."
        )
        user = f"File: {path.name}\nDependencies JSON:\n```json\n{json.dumps(deps, indent=2)}\n```"
        summary = client.chat(
            [{"role": "system", "content": prompt}, {"role": "user", "content": user}],
            temperature=0.0,
            max_tokens=get_settings().analyze_num_predict,
        )

    return {
        "file": str(path),
        "ecosystem": eco,
        "dependencies": deps,
        "license_risk": license_risk,
        "notes": summary,
        "ollama_models": _ollama_models(),
    }