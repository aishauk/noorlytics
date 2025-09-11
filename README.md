# Noorlytics CLI

Noorlytics is a local-first CLI tool for analyzing technical debt, dependencies, licenses, and structure in your codebase — powered by AI (OpenAI or Ollama).

## ✨ Features
- Local and cloud-based LLM support (`--mode=ollama` or `--mode=openai`)
- Dependency analysis (`requirements.txt`, `pyproject.toml`, `package.json`, etc.)
- Suggest and stub out refactoring ideas
- Generate unit test stubs
- License audit (detect risky or deprecated licenses)
- Security checks for vulnerable dependencies
- Optional cost tracking for OpenAI usage
- Markdown reports to `reports/`

## ⚙️ Requirements
- Python 3.10+
- [Ollama](https://ollama.com/) installed and running (if using `--mode=ollama`)
- OpenAI API key (if using `--mode=openai`)
- Bash/Zsh for setup script (`setup_noorlytics.sh`)

## 📦 Setup

```bash
# Clone the repo
git clone https://github.com/yourusername/noorlytics.git
cd noorlytics

# Run setup script (creates venv, installs deps, loads env vars)
source setup_noorlytics.sh
```

## 🧪 Example usage

```bash
# Start Ollama (Mistral or your preferred model must be available)
ollama run mistral   # in a separate terminal

# Analyze a file using Ollama
python run.py analyze examples/legacyfile.py --mode=ollama

# Analyze using OpenAI
export OPENAI_API_KEY=your-key
python run.py analyze examples/legacyfile.py --mode=openai

# Suggest refactorings
python run.py suggest examples/legacyfile.py --mode=ollama

# Generate unit test stubs
python run.py add-tests examples/legacyfile.py --mode=ollama

# Refactor code (work in progress)
python run.py refactor examples/legacyfile.py --mode=ollama
```

## 🧰 CLI Overview

```bash
python run.py [COMMAND] [PATH] --mode=[ollama|openai]

Commands:
  analyze       Run full code, dependency, and license analysis
  suggest       Suggest AI-powered refactorings
  add-tests     Generate unit test stubs from source code
  refactor      Apply automatic refactor suggestions (WIP, next release)
```

## 📁 Output
- Reports are saved to `reports/` as Markdown and JSON files.
- Suggestions and findings are also printed to the console.

## 🛡 Compliance
- With `--mode=ollama`, all inference runs locally, compliant with secure/restricted environments.
- `.env` support for managing API keys and configuration.

## 🧠 Roadmap
- Stable refactor feature
- Before/after refactor trace logging
- CI pipeline integration
- Team-level reporting and dashboards

## ⚠️ Latency warning

When running **Ollama locally** (`http://localhost:11434`), network latency is negligible.  
- Recommended: `NOOR_HTTP_TIMEOUT=30`, `NOOR_KEEP_ALIVE=5m`  
- Local models start quickly but consume more RAM if kept alive for too long.
- **Local models can be slow to generate results, depending on your CPU/GPU and RAM.**

When running **remote Ollama** (e.g. Runpod, cloud instance), you should increase values in `.env` file:  
- Recommended: `NOOR_HTTP_TIMEOUT=120`, `NOOR_KEEP_ALIVE=30m`  
- Remote models benefit from higher timeouts due to network latency and cold starts.

---

Built with ❤️ by Aisha Ugljanin