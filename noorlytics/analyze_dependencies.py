from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional

from .settings import get_settings
from . import net
from .llm_interface import LLMClient


# ---------------- Ecosystem detection ----------------

def detect_ecosystem(filename: str, content: str) -> str:
    name = filename.lower()

    if name == "packages.config":
        return "dotnet"

    if "requirements" in name or name.endswith(".txt"):
        return "python"
    if name.endswith("pyproject.toml"):
        return "python"
    if name.endswith("package.json"):
        return "node"
    if name.endswith("pom.xml") or name.endswith(".gradle"):
        return "java"

    return "unknown"


# ---------------- Parsers ----------------

def parse_requirements_txt(text: str) -> List[Tuple[str, Optional[str]]]:
    out = []

    for line in text.splitlines():
        line = line.strip()

        if not line or line.startswith("#"):
            continue

        m = re.match(
            r"([A-Za-z0-9_.\-]+)\s*(?:==|>=|<=|~=|>|<)?\s*([A-Za-z0-9_.\-]+)?",
            line
        )

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


def parse_packages_config(text: str) -> List[Tuple[str, Optional[str]]]:
    packages: List[Tuple[str, Optional[str]]] = []

    for match in re.finditer(
        r'<package\s+[^>]*id="([^"]+)"[^>]*version="([^"]+)"',
        text,
        re.IGNORECASE
    ):
        packages.append((match.group(1), match.group(2)))

    return packages


# ---------------- License helpers ----------------

RISKY_LICENSES = {
    "GPL",
    "GPL-2.0",
    "GPL-3.0",
    "AGPL",
    "AGPL-3.0",
    "LGPL",
    "LGPL-2.1",
    "LGPL-3.0",
    "UNKNOWN",
    "NONE",
    None
}

PERMISSIVE_HINTS = {
    "MIT",
    "APACHE",
    "APACHE-2.0",
    "BSD",
    "BSD-3-CLAUSE",
    "ISC",
    "MPL",
    "MPL-2.0"
}


def _normalize_license_name(lic_raw: Optional[str]) -> str:
    if not lic_raw:
        return "UNKNOWN"

    lic = str(lic_raw).strip().strip('"').strip("'")
    u = lic.upper().replace(" LICENSE", "").replace("LICENCE", "").strip()

    if "APACHE" in u and "2" in u:
        return "Apache-2.0"
    if u in {"APACHE", "APACHE2", "APACHE-2"}:
        return "Apache-2.0"
    if "MIT" in u:
        return "MIT"
    if "BSD-3" in u or ("BSD" in u and "3" in u):
        return "BSD-3-Clause"
    if u == "BSD":
        return "BSD"
    if "ISC" in u:
        return "ISC"
    if "MPL" in u and "2" in u:
        return "MPL-2.0"
    if "GPL-3" in u or ("GPL" in u and "3" in u):
        return "GPL-3.0"
    if "GPL-2" in u or ("GPL" in u and "2" in u):
        return "GPL-2.0"
    if "AGPL" in u:
        return "AGPL-3.0"
    if "LGPL-3" in u or ("LGPL" in u and "3" in u):
        return "LGPL-3.0"
    if "LGPL-2" in u or ("LGPL" in u and "2" in u):
        return "LGPL-2.1"
    if u in {"UNKNOWN", "NONE", ""}:
        return "UNKNOWN"

    return lic


def _risk_from_license(lic: str) -> str:
    up = lic.upper()

    if any(bad in up for bad in ("AGPL", "GPL", "LGPL")) or up in {"UNKNOWN", "NONE"}:
        return "high"

    if any(ok in up for ok in PERMISSIVE_HINTS):
        return "low"

    return "medium"


# ---------------- Rendering helpers ----------------

def _split_md_sections(md: str) -> Dict[str, List[str]]:
    sections: Dict[str, List[str]] = {
        "Risks": [],
        "Suggestions": []
    }

    current = None

    for line in md.splitlines():
        hdr = line.strip().lstrip("# ").lower()

        if hdr.startswith("risks"):
            current = "Risks"
            continue

        if hdr.startswith("suggestions"):
            current = "Suggestions"
            continue

        if current and line.strip():
            sections[current].append(line.rstrip())

    return sections


def _format_risk_chip(risk: str) -> str:
    try:
        from rich.text import Text

        chip = Text(f" {risk.upper()} ")

        if risk == "high":
            chip.stylize("bold white on red")
        elif risk == "medium":
            chip.stylize("bold black on yellow")
        else:
            chip.stylize("bold white on green")

        return chip.__rich__()

    except Exception:
        return f"[{risk.upper()}]"


def render_vulns_cli(vulns: List[Dict[str, Optional[str]]]) -> None:
    if not vulns:
        return

    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        tbl = Table(title="Known vulnerabilities (HIGH/CRITICAL)")

        tbl.add_column("Package", style="cyan", no_wrap=True)
        tbl.add_column("ID", style="magenta")
        tbl.add_column("Severity", style="bold")
        tbl.add_column("Fix", style="")
        tbl.add_column("Version", style="dim")

        for v in vulns:
            tbl.add_row(
                v.get("name") or "?",
                v.get("id") or "-",
                (v.get("severity") or "").upper(),
                v.get("fix_version") or "-",
                v.get("version") or "-"
            )

        console.print(tbl)

    except Exception:
        import click

        click.echo(click.style("\nKnown vulnerabilities (HIGH/CRITICAL)", fg="cyan", bold=True))

        for v in vulns:
            click.echo(
                f"  - {v.get('name')}@{v.get('version') or '-'}  "
                f"{v.get('id') or '-'}  "
                f"{v.get('severity') or ''}  "
                f"fix: {v.get('fix_version') or '-'}"
            )


def render_notes_cli(notes_sections: Dict[str, List[str]], license_risk: List[Dict[str, Any]]) -> None:
    try:
        from rich.console import Console
        from rich.table import Table
        from rich.markdown import Markdown

        console = Console()

        table = Table(title="License / Risk overview", show_lines=False)
        table.add_column("Dependency", style="cyan", no_wrap=True)
        table.add_column("License", style="magenta")
        table.add_column("Risk", style="bold")

        for item in license_risk:
            chip = _format_risk_chip(item.get("risk", "low"))
            table.add_row(
                item["name"],
                str(item.get("license", "UNKNOWN")),
                chip
            )

        console.print(table)

        for title in ("Risks", "Suggestions"):
            body = "\n".join(notes_sections.get(title, [])) or "_(none)_"
            console.rule(f"[bold cyan]{title}")
            console.print(Markdown(body))

    except Exception:
        import click

        click.echo(click.style("\nLicense / Risk overview", fg="cyan", bold=True))

        for item in license_risk:
            risk = item.get("risk", "low")
            color = {"high": "red", "medium": "yellow"}.get(risk, "green")
            chip = f"[{risk.upper()}]"

            click.echo(
                f"  - {item['name']:<24} "
                f"lic={item.get('license','UNKNOWN'):<10} "
                f"{click.style(chip, fg=color, bold=True)}"
            )

        for title in ("Risks", "Suggestions"):
            click.echo(click.style(f"\n## {title}", fg="cyan", bold=True))

            for line in notes_sections.get(title, []):
                click.echo(line)


# ---------------- Transitives lockfiles ----------------

def _collect_node_transitives(lock_path: Path) -> Tuple[List[Dict[str, Optional[str]]], List[Dict[str, str]]]:
    try:
        data = json.loads(lock_path.read_text(encoding="utf-8"))
    except Exception:
        return [], []

    collected: Dict[str, Dict[str, Optional[str]]] = {}

    def walk(node: Dict[str, Any]):
        deps = node.get("dependencies", {}) or {}

        for name, meta in deps.items():
            ver = meta.get("version")
            key = f"{name}@{ver}" if ver else name

            if key in collected:
                continue

            collected[key] = {
                "name": name,
                "version": ver
            }

            walk(meta)

    if "packages" in data and isinstance(data["packages"], dict):
        root = {
            "dependencies": data.get("dependencies", {})
        }
        walk(root)
    else:
        walk(data)

    src = [{
        "type": "node-lockfile",
        "path": str(lock_path)
    }]

    return list(collected.values()), src


def _collect_poetry_transitives(lock_path: Path) -> Tuple[List[Dict[str, Optional[str]]], List[Dict[str, str]]]:
    text = lock_path.read_text(encoding="utf-8", errors="ignore")
    pkgs: List[Dict[str, Optional[str]]] = []
    current = None

    for line in text.splitlines():
        s = line.strip()

        if s.startswith("[[package]]"):
            if current:
                pkgs.append(current)

            current = {
                "name": None,
                "version": None
            }

        elif s.startswith("name =") and current is not None:
            current["name"] = s.split("=", 1)[1].strip().strip('"\'')

        elif s.startswith("version =") and current is not None:
            current["version"] = s.split("=", 1)[1].strip().strip('"\'')

    if current:
        pkgs.append(current)

    seen = set()
    out = []

    for p in pkgs:
        key = f"{p.get('name')}@{p.get('version')}"

        if key not in seen and p.get("name"):
            out.append({
                "name": p.get("name"),
                "version": p.get("version")
            })
            seen.add(key)

    src = [{
        "type": "python-poetry-lock",
        "path": str(lock_path)
    }]

    return out, src


def _expand_from_lockfiles(project_root: Path, eco: str) -> Tuple[List[Dict[str, Optional[str]]], List[Dict[str, str]]]:
    if eco == "node":
        p = project_root / "package-lock.json"

        if p.exists():
            return _collect_node_transitives(p)

        return [], []

    if eco == "python":
        for lock in ("poetry.lock", "Pipfile.lock"):
            p = project_root / lock

            if p.exists():
                return _collect_poetry_transitives(p)

        return [], []

    return [], []


# ---------------- Offline license detection ----------------

def _detect_license_python(pkg: str) -> Tuple[str, str]:
    try:
        out = subprocess.check_output(
            [sys.executable, "-m", "pip", "show", pkg],
            stderr=subprocess.DEVNULL,
            text=True
        )

        lic_raw = None

        for line in out.splitlines():
            if line.lower().startswith("license:"):
                lic_raw = line.split(":", 1)[1].strip()
                break

        lic = _normalize_license_name(lic_raw)

        if lic != "UNKNOWN":
            return lic, "pip-show"

    except Exception:
        pass

    try:
        r = net.session().get(f"https://pypi.org/pypi/{pkg}/json", timeout=5)

        if r.ok:
            info = r.json().get("info", {})
            lic_raw = info.get("license")

            if not lic_raw:
                for c in info.get("classifiers", []):
                    if c.startswith("License ::"):
                        lic_raw = c.split("::")[-1].strip()
                        break

            lic = _normalize_license_name(lic_raw)
            return lic, "pypi"

    except Exception:
        pass

    return "UNKNOWN", "unknown"


def _detect_license_node(pkg: str, project_root: Path, version_hint: Optional[str]) -> Tuple[str, str]:
    try:
        pkg_json = project_root / "node_modules" / pkg / "package.json"

        if pkg_json.exists():
            data = json.loads(pkg_json.read_text(encoding="utf-8", errors="ignore"))
            lic_raw = data.get("license")

            if not lic_raw and isinstance(data.get("licenses"), list) and data["licenses"]:
                lic_raw = data["licenses"][0].get("type")

            lic = _normalize_license_name(lic_raw)

            if lic != "UNKNOWN":
                return lic, "node_modules"

    except Exception:
        pass

    try:
        ver = None

        if version_hint:
            m = re.search(r"\d+(\.\d+){0,2}", version_hint)

            if m:
                ver = m.group(0)

        url = f"https://registry.npmjs.org/{pkg}/" + (ver or "latest")
        r = net.session().get(url, timeout=5)

        if r.ok:
            data = r.json()
            lic_raw = data.get("license")

            if not lic_raw and isinstance(data.get("licenses"), list) and data["licenses"]:
                lic_raw = data["licenses"][0].get("type")

            lic = _normalize_license_name(lic_raw)
            return lic, "npm-registry"

    except Exception:
        pass

    return "UNKNOWN", "unknown"


def _detect_license_nuget(pkg: str, version_hint: Optional[str]) -> Tuple[str, str]:
    try:
        registration_url = f"https://api.nuget.org/v3/registration5-semver1/{pkg.lower()}/index.json"
        r = net.session().get(registration_url, timeout=6)

        if not r.ok:
            return "UNKNOWN", "nuget"

        data = r.json()
        items = data.get("items", [])
        target_version = version_hint.lower() if version_hint else None

        for page in items:
            page_items = page.get("items")

            if page_items is None and page.get("@id"):
                page_response = net.session().get(page["@id"], timeout=6)

                if page_response.ok:
                    page_items = page_response.json().get("items", [])

            if not page_items:
                continue

            for item in page_items:
                catalog_entry = item.get("catalogEntry", {})
                version = str(catalog_entry.get("version", "")).lower()

                if target_version and version != target_version:
                    continue

                lic_raw = (
                    catalog_entry.get("licenseExpression")
                    or catalog_entry.get("licenseUrl")
                    or catalog_entry.get("license")
                )

                lic = _normalize_license_name(lic_raw)

                if lic != "UNKNOWN":
                    return lic, "nuget"

                if target_version:
                    return "UNKNOWN", "nuget"

        return "UNKNOWN", "nuget"

    except Exception:
        return "UNKNOWN", "nuget"


# ---------------- Vulnerability scanning OSV plus fallbacks ----------------

def _severity_from_osv_vuln(v: Dict[str, Any]) -> str:
    sev_label = None

    for s in v.get("severity") or []:
        try:
            score_raw = str(s.get("score", ""))

            m = re.search(r"(\d+\.\d+)", score_raw)

            if not m:
                continue

            score = float(m.group(1))

            if score >= 9.0:
                sev_label = "CRITICAL"
            elif score >= 7.0:
                sev_label = "HIGH"
            elif score >= 4.0:
                sev_label = "MEDIUM"
            else:
                sev_label = "LOW"

        except Exception:
            continue

    if not sev_label:
        db_sev = (
            v.get("database_specific", {}).get("severity")
            or ""
        )

        db_sev = str(db_sev).upper()

        if "CRITICAL" in db_sev:
            sev_label = "CRITICAL"
        elif "HIGH" in db_sev:
            sev_label = "HIGH"
        elif "MODERATE" in db_sev or "MEDIUM" in db_sev:
            sev_label = "MEDIUM"
        elif "LOW" in db_sev:
            sev_label = "LOW"

    return sev_label or "UNKNOWN"


def _osv_querybatch(ecosystem: str, pkgs: List[Tuple[str, Optional[str]]]) -> List[Dict[str, Optional[str]]]:
    queries = []
    names: List[str] = []
    versions: List[str] = []

    for name, ver in pkgs:
        if not ver:
            continue

        if ecosystem == "npm":
            m = re.search(r"\d+(\.\d+){0,2}", ver)

            if not m:
                continue

            ver = m.group(0)

        osv_ecosystem = (
            "PyPI" if ecosystem == "pypi"
            else "npm" if ecosystem == "npm"
            else "NuGet"
        )

        queries.append({
            "package": {
                "name": name,
                "ecosystem": osv_ecosystem
            },
            "version": ver
        })

        names.append(name)
        versions.append(ver)

    if not queries:
        return []

    try:
        r = net.session().post(
            "https://api.osv.dev/v1/querybatch",
            json={"queries": queries},
            timeout=10
        )

        r.raise_for_status()
        data = r.json()

    except Exception:
        return []

    out: List[Dict[str, Optional[str]]] = []

    for idx, res in enumerate(data.get("results", [])):
        vulns = res.get("vulns") or []

        for v in vulns:
            vid = v.get("id") or (v.get("aliases") or [None])[0]
            sev_label = _severity_from_osv_vuln(v)

            fix = None

            for aff in v.get("affected") or []:
                for rng in aff.get("ranges") or []:
                    for ev in rng.get("events") or []:
                        if "fixed" in ev:
                            fix = ev["fixed"]
                            break

                    if fix:
                        break

                if fix:
                    break

            out.append({
                "name": names[idx],
                "version": versions[idx],
                "id": vid,
                "severity": sev_label,
                "fix_version": fix,
                "title": v.get("summary") or v.get("details"),
            })

    return [
        v for v in out
        if (v.get("severity") or "").upper() in {"HIGH", "CRITICAL"}
    ]


def _version_tuple(version: Optional[str]) -> Tuple[int, ...]:
    if not version:
        return ()

    numbers = re.findall(r"\d+", str(version))

    return tuple(int(n) for n in numbers[:4])


def _version_lt(version: Optional[str], target: str) -> bool:
    current = _version_tuple(version)
    expected = _version_tuple(target)

    if not current or not expected:
        return False

    max_len = max(len(current), len(expected))
    current = current + (0,) * (max_len - len(current))
    expected = expected + (0,) * (max_len - len(expected))

    return current < expected


def _dotnet_fallback_vulns(deps: List[Dict[str, Any]]) -> List[Dict[str, Optional[str]]]:
    """
    Small deterministic fallback for well known NuGet demo findings.
    This is useful because OSV/NuGet matching can be incomplete or inconsistent.
    Keep this list small and conservative.
    """
    fallback_rules = {
        "newtonsoft.json": {
            "affected_below": "13.0.1",
            "id": "GHSA-5crp-9r3c-p9vr",
            "severity": "HIGH",
            "fix_version": "13.0.1",
            "title": "Improper handling of exceptional conditions in Newtonsoft.Json"
        },
        "system.text.encodings.web": {
            "affected_below": "4.5.1",
            "id": "GHSA-ghhp-997w-qr28",
            "severity": "HIGH",
            "fix_version": "4.5.1",
            "title": "System.Text.Encodings.Web vulnerability in older versions"
        }
    }

    out: List[Dict[str, Optional[str]]] = []

    for d in deps:
        name = str(d.get("name", ""))
        key = name.lower()
        version = d.get("version")

        rule = fallback_rules.get(key)

        if not rule:
            continue

        if _version_lt(version, rule["affected_below"]):
            out.append({
                "name": name,
                "version": version,
                "id": rule["id"],
                "severity": rule["severity"],
                "fix_version": rule["fix_version"],
                "title": rule["title"],
            })

    return out


def _dedupe_vulns(vulns: List[Dict[str, Optional[str]]]) -> List[Dict[str, Optional[str]]]:
    seen = set()
    out = []

    for v in vulns:
        key = (
            str(v.get("name", "")).lower(),
            str(v.get("version", "")),
            str(v.get("id", ""))
        )

        if key in seen:
            continue

        seen.add(key)
        out.append(v)

    return out


def _collect_known_vulns(path: Path, eco: str, deps: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Optional[str]]], Dict[str, str]]:
    sources: Dict[str, str] = {}
    vulns: List[Dict[str, Optional[str]]] = []

    if eco == "node":
        osv = _osv_querybatch("npm", [(d["name"], d.get("version")) for d in deps])

        if osv:
            vulns.extend(osv)
            sources["node"] = "osv"

    elif eco == "python":
        osv = _osv_querybatch("pypi", [(d["name"], d.get("version")) for d in deps])

        if osv:
            vulns.extend(osv)
            sources["python"] = "osv"

    elif eco == "dotnet":
        osv = _osv_querybatch("nuget", [(d["name"], d.get("version")) for d in deps])
        fallback = _dotnet_fallback_vulns(deps)

        if osv:
            vulns.extend(osv)
            sources["dotnet"] = "osv"

        if fallback:
            vulns.extend(fallback)
            sources["dotnet_fallback"] = "curated-known-nuget-findings"

        if not osv and not fallback:
            sources["dotnet"] = "osv-no-high-critical-found"

    return _dedupe_vulns(vulns), sources


# ---------------- Main dependency analysis ----------------

def analyze_dependencies_file(path: Path, client: LLMClient) -> Dict[str, Any]:
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

    elif eco == "dotnet":
        pairs = parse_packages_config(text)
        deps = [{"name": n, "version": v} for (n, v) in pairs]

    transitive, _ = _expand_from_lockfiles(path.parent, eco)

    if transitive:
        existing = {(d["name"], d.get("version")) for d in deps}

        for td in transitive:
            if (td["name"], td.get("version")) not in existing:
                deps.append(td)

    license_risk: List[Dict[str, Any]] = []
    license_sources: Dict[str, str] = {}

    for d in deps:
        name = d["name"]
        ver_hint = d.get("version")

        if eco == "python":
            lic, src = _detect_license_python(name)
        elif eco == "node":
            lic, src = _detect_license_node(name, path.parent, ver_hint)
        elif eco == "dotnet":
            lic, src = _detect_license_nuget(name, ver_hint)
        else:
            lic, src = "UNKNOWN", "unknown"

        lic_norm = _normalize_license_name(lic)
        risk = _risk_from_license(lic_norm)

        license_risk.append({
            "name": name,
            "license": lic_norm,
            "risk": risk
        })

        license_sources[name] = src

    known_vulns, vuln_sources = _collect_known_vulns(path, eco, deps)

    risk_lines: List[str] = []
    risk_lines.append("**Known high-profile vulnerabilities:**")

    if known_vulns:
        for v in known_vulns:
            pkg = v.get("name")
            ver = v.get("version") or "unknown"
            vid = v.get("id") or "Advisory"
            sev = (v.get("severity") or "").upper()
            fix = v.get("fix_version")
            fix_txt = f", fix: {fix}" if fix else ""

            risk_lines.append(f"- {pkg}@{ver} — {vid} ({sev}){fix_txt}")
    else:
        unpinned = [d["name"] for d in deps if not d.get("version")]

        if unpinned:
            risk_lines.append("- No high or critical vulnerabilities found because some packages are unpinned and cannot be audited precisely.")
        else:
            risk_lines.append("- No high or critical vulnerabilities found via OSV for the specified versions.")
            risk_lines.append("- This does not mean the dependencies are risk free.")

    risk_lines.append("")

    risky = [
        r for r in license_risk
        if r["risk"] == "high" and r["license"].upper() != "UNKNOWN"
    ]

    unknowns = [
        r for r in license_risk
        if r["license"].upper() == "UNKNOWN"
    ]

    risk_lines.append("**Risky licenses:**")

    if risky:
        for r in risky:
            risk_lines.append(f"- {r['name']}: {r['license']}")
    else:
        risk_lines.append("- None flagged as high risk based on license.")

    if unknowns:
        risk_lines.append("")
        show = unknowns[:10]
        risk_lines.append("**Unknown licenses top 10:**")

        for r in show:
            risk_lines.append(f"- {r['name']}: UNKNOWN")

        if len(unknowns) > 10:
            risk_lines.append(f"- … and {len(unknowns) - 10} more")

    risk_lines.append("")

    unpinned = [d["name"] for d in deps if not d.get("version")]

    if unpinned:
        risk_lines.append("**Unpinned packages:**")

        for n in unpinned[:20]:
            risk_lines.append(f"- {n}")

        if len(unpinned) > 20:
            risk_lines.append(f"- … and {len(unpinned) - 20} more")

        risk_lines.append("")

    if eco == "dotnet":
        legacy_candidates = [
            d for d in deps
            if d.get("version") and re.match(r"^[0-3]\.", str(d.get("version")))
        ]

        if legacy_candidates:
            risk_lines.append("**Legacy dependency signals:**")

            for d in legacy_candidates[:15]:
                risk_lines.append(
                    f"- {d['name']}@{d.get('version')} appears very old and should be reviewed."
                )

            if len(legacy_candidates) > 15:
                risk_lines.append(f"- … and {len(legacy_candidates) - 15} more")

            risk_lines.append("")

        risk_lines.append("**Dependency management model:**")
        risk_lines.append("- This project uses packages.config, which is common in older .NET Framework projects.")
        risk_lines.append("- Consider migrating to PackageReference if the project structure allows it.")
        risk_lines.append("")

    sug_lines: List[str] = []

    sug_lines.append("1. **Upgrade vulnerable packages**: apply the fixed versions listed above as soon as possible.")
    sug_lines.append("2. **Pin and update regularly**: keep versions pinned and schedule routine updates.")
    sug_lines.append("3. **Verify licenses**: ensure each dependency has a clear SPDX license compatible with your project.")

    if eco == "node":
        sug_lines.append("4. **Automate in CI**: run Noorlytics dependency scan and OSV checks on every PR.")

    elif eco == "python":
        sug_lines.append("4. **Automate in CI**: run Noorlytics dependency scan and OSV checks on every PR and pin versions in requirements.")

    elif eco == "dotnet":
        sug_lines.append("4. **Modernize dependency management**: consider migrating from packages.config to PackageReference.")
        sug_lines.append("5. **Review old NuGet packages**: prioritize upgrades for legacy packages that are several major versions behind.")
        sug_lines.append("6. **Check .NET Framework compatibility**: verify whether the project can move to a newer .NET Framework version or modern .NET.")

    else:
        sug_lines.append("4. **Automate in CI**: run Noorlytics dependency scan and OSV checks on every PR.")

    notes_sections = {
        "Risks": risk_lines,
        "Suggestions": sug_lines
    }

    notes_md = (
        "## Risks\n"
        + "\n".join(risk_lines)
        + "\n## Suggestions\n"
        + "\n".join(sug_lines)
    )

    return {
        "file": str(path),
        "ecosystem": eco,
        "dependencies": deps,
        "license_risk": license_risk,
        "license_sources": license_sources,
        "vulnerability_sources": vuln_sources,
        "known_vulns": known_vulns,
        "notes_md": notes_md,
        "notes_sections": notes_sections,
    }