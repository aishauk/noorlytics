import pkg_resources
import os

from .constants import RISKY_LICENSES

def audit_licenses(output_dir: str | None = None):
    """
    Inspect installed package licenses and flag risky ones.
    Returns a list of results and optionally writes a JSON/Markdown report.
    """
    report = []
    for dist in pkg_resources.working_set:
        name = dist.project_name
        version = dist.version

        # Try to extract license info
        license_type = "Unknown"
        meta = ""
        if dist.has_metadata("METADATA"):
            meta = dist.get_metadata("METADATA")
        elif dist.has_metadata("PKG-INFO"):
            meta = dist.get_metadata("PKG-INFO")

        for line in meta.splitlines():
            if line.startswith("License:"):
                license_type = line.split(":", 1)[-1].strip()
                break
            if line.startswith("Classifier:") and "License" in line:
                license_type = line.split("::")[-1].strip()
                break

        risk = "HIGH ❌" if license_type in RISKY_LICENSES else "Low ✅"
        report.append({
            "package": name,
            "version": version,
            "license": license_type,
            "risk": risk,
        })

    # Optional: write to file
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        import json
        path = os.path.join(output_dir, "license_audit.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

    return report