from noorlytics.config import COMPLIANCE_MODE

def log_to_console(message):
    if not COMPLIANCE_MODE:
        print(message)

def write_to_file(filepath, content):
    if not COMPLIANCE_MODE:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

def append_to_file(filepath, content):
    if not COMPLIANCE_MODE:
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(content + "\n")