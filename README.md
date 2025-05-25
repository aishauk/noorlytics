# Noorlytics CLI

Noorlytics is a local-first CLI tool for analyzing technical debt, dependencies, licenses, and structure in your codebase — powered by AI (OpenAI or Ollama).

## ✨ Features
- Local and cloud-based LLM support (Ollama + OpenAI)
- Analyze dependencies (`requirements.txt`)
- Suggest and stub out refactoring ideas
- License audit
- Optional cost tracking for OpenAI usage

## ⚙️ Requirements
- Python 3.9+
- [Ollama](https://ollama.com/) installed and running (if using `--mode=ollama`)
- OpenAI API key (if using `--mode=openai`)

## 📦 Setup

```bash
# Clone the repo
cd noorlytics

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## 🧪 Example usage

```bash
# Start Ollama (Mistral must be running)
ollama run mistral  # in a separate terminal

# Analyze a file using Ollama
python run.py analyze examples/legacyfile.py --mode=ollama

# Analyze using OpenAI
export OPENAI_API_KEY=your-key
python run.py analyze examples/legacyfile.py --mode=openai

# Suggest refactorings
python run.py suggest examples/legacyfile.py --mode=ollama

# Generate unit test stubs
python run.py add-tests examples/legacyfile.py --mode=ollama

# Refactor code (TODO: not implemented yet)
python run.py refactor examples/legacyfile.py --mode=ollama

```

## 🧰 CLI Overview

```bash
python run.py [COMMAND] [PATH] --mode=[ollama|openai]

Commands:
  analyze       Run full code and license analysis
  suggest       Suggest AI-powered refactorings
  add-tests     Generate unit test stubs from source code
  refactor      Apply automatic refactor suggestions (WIP)
```

## 📁 Output
- Reports are saved to `reports/` as markdown files.
- Suggestions are printed to console.

## 🛡 Compliance
- When running with `--mode=ollama`, all inference runs locally and complies with security-restricted environments.
- Enable `.env` support to manage keys and config.

## 🧠 Coming soon
- Before/after refactor trace logging
- Fine-tuning support (LoRA, QLoRA)
- VS Code integration

---

Built with ❤️ by Aisha Ugljanin