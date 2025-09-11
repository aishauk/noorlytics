import os

from noorlytics.analyze_dependencies import analyze_dependencies
from noorlytics.analyze_requirements import analyze_requirements
from noorlytics.license_audit import audit_licenses
from noorlytics.llm_interface import suggest_refactorings_realtime, apply_suggestion_to_code


def run_analysis(path: str, mode: str = "ollama"):
    """
    Run the overall analysis. Optimized version:
    - Passes through 'mode' to analyze_dependencies (previously defaulted).
    - Can skip secondary dependency analysis if NOOR_SKIP_SECONDARY_DEPS=1.
    """
    print("🔍 Starting Noorlytics analysis...")

    # Try to locate requirements.txt in the given path or current directory
    req_path = os.path.join(path, "requirements.txt") if os.path.isdir(path) else "requirements.txt"
    if os.path.isfile(req_path):
        with open(req_path, "r", encoding="utf-8") as f:
            content = f.read()
        analyze_dependencies(content, filename=req_path, mode=mode)
    else:
        print(f"⚠️  requirements.txt not found at {req_path}")

    skip_secondary = os.getenv("NOOR_SKIP_SECONDARY_DEPS", "0") == "1"
    if not skip_secondary:
        analyze_requirements(path)
    else:
        print("⏭️  Skipping secondary dependency analysis (NOOR_SKIP_SECONDARY_DEPS=1)")

    print("📜 Running license audit...")
    audit_licenses()
    print("✅ License audit complete.")