
import os

from noorlytics.analyze_dependencies_enhanced import analyze_dependencies
from noorlytics.analyze_requirements import analyze_requirements
from noorlytics.license_audit import audit_licenses
from noorlytics.llm_interface import suggest_refactorings, auto_refactor, generate_test_stubs

def run_analysis(path, mode):
    print("🔍 Starting Noorlytics analysis...")

    # Try to read requirements.txt from path or parent folder
    req_path = os.path.join(path, "requirements.txt") if os.path.isdir(path) else "requirements.txt"
    if not os.path.isfile(req_path):
        print(f"⚠️  requirements.txt not found at {req_path}")
    else:
        with open(req_path, "r") as f:
            content = f.read()
        analyze_dependencies(content, filename=req_path)

    analyze_requirements(path)
    audit_licenses()
