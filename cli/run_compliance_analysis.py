
import sys
from logger import log_to_console
from llm_interface import get_analysis

def load_code(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Användning: python run_compliance_analysis.py <filnamn>")
        sys.exit(1)

    filepath = sys.argv[1]
    code = load_code(filepath)

    log_to_console("🔍 Analyserar kod med lokal LLM (Ollama)...")
    result = get_analysis(code)
    log_to_console("\n📄 AI-förslag:\n")
    print(result)
