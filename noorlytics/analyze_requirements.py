import os

def analyze_requirements(path="."):
    """
    Analyze the requirements.txt file at the given path.
    Currently a placeholder – extend with actual analysis logic.

    Args:
        path (str): Path to the directory containing requirements.txt
    """
    req_path = os.path.join(path, "requirements.txt") if os.path.isdir(path) else path

    if not os.path.isfile(req_path):
        print(f"⚠️  No requirements.txt found at {req_path}")
        return

    print(f"🔍 Found requirements.txt at {req_path}")
    with open(req_path, "r") as f:
        lines = f.readlines()

    print("📄 Dependencies listed:")
    for line in lines:
        print(f"  • {line.strip()}")