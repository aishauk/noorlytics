# Noorlytics CLI

Noorlytics is a local-first CLI for code analysis, refactor guidance, dependency review, and test stub generation. It runs with either a local Ollama model or OpenAI.

## ✨ Features

- Local and cloud-based LLM support (`--mode=ollama` or `--mode=openai`)
- Dependency analysis (`requirements.txt`, `pyproject.toml`, `package.json`, etc.)
- Suggest and stub out refactoring ideas
- Generate refactor suggestions in Markdown
- Generate unit test stubs
- License audit (detect risky or deprecated licenses)
- Security checks for vulnerable dependencies
- Optional cost tracking for OpenAI usage
- Markdown reports to `reports/`

## Capability Status

Stable:

- `analyze` for supported source files
- `suggest` for refactoring guidance
- `analyze-deps` for dependency, license, and vulnerability checks
- Versioned Markdown reports with `Generated:` timestamps

Partial:

- `add-tests` is strongest for Python and less predictable for other languages
- Dependency analysis works across multiple ecosystems, but unusual manifests may need manual review

Experimental:

- `refactor` currently generates a refactor plan in Markdown; it does not rewrite source files

## Requirements

- Python 3.10 or newer
- Bash or Zsh for the setup script
- One backend:
  - Ollama installed locally for `--mode=ollama`
  - OpenAI API key for `--mode=openai`

## Quick Start

```bash
# Clone the repo
git clone https://github.com/aishauk/noorlytics.git
cd noorlytics

# Create .venv, install the CLI and required Python packages, and create .env.
source setup_noorlytics.sh

# Confirm the CLI is available.
noor --help
```

The setup script:

- creates `.venv` if needed
- installs Noorlytics in editable mode
- upgrades `pip`
- creates `.env` from `.env.sample` if missing
- activates the virtual environment in the current shell
- prints which `noor` executable is active

## Setup Paths

### Ollama setup

```bash
source setup_noorlytics.sh
ollama --version
ollama pull mistral:latest
ollama serve
```

If Ollama is already running as a service on your machine, you do not need to start `ollama serve` manually.

### OpenAI setup

```bash
source setup_noorlytics.sh --openai
export OPENAI_API_KEY="your-key"
```

## First Run Check

Before debugging anything else, verify the runtime path and backend:

```bash
source .venv/bin/activate
command -v noor
ollama list
noor --mode=ollama analyze examples/legacyfile.py
```

Expected results:

- `command -v noor` points to `.venv/bin/noor`
- `ollama list` includes the configured model, usually `mistral:latest`
- Noorlytics prints an analysis summary and saves a new report under `reports/`

If `command -v noor` points somewhere else, run `.venv/bin/noor` explicitly or reactivate the virtual environment.

## Supported Inputs

Source analysis uses the extensions in `NOOR_ALLOWED_EXT`.

Default source extensions:

- `.py`
- `.cs`

Dependency analysis supports:

- `requirements.txt`
- `pyproject.toml`
- `package.json`
- `packages.config`

## Common Commands

```bash
# Analyze one file
noor --mode=ollama analyze examples/legacyfile.py

# Analyze a directory of supported source files
noor --mode=ollama analyze examples/

# Generate refactor suggestions
noor --mode=ollama suggest examples/legacyfile.py

# Generate unit test stubs
noor --mode=ollama add-tests examples/legacyfile.py

# Analyze dependencies
noor --mode=ollama analyze-deps examples/requirements.txt

# Generate a refactor plan
noor --mode=ollama refactor examples/legacyfile.py
```

## Command Reference

`analyze`

- analyzes one file or a directory of supported source files
- writes versioned Markdown reports to `reports/`

`suggest`

- generates refactor suggestions in Markdown
- does not modify source code

`add-tests`

- generates test stubs
- most reliable for Python inputs

`analyze-deps`

- analyzes a manifest for license risk and known vulnerabilities
- writes a JSON report and a versioned Markdown summary

`refactor`

- generates a refactor plan in Markdown
- does not automatically apply code changes

## Configuration

Main configuration lives in `.env`. The default template is in `.env.sample`.

Most useful settings:

- `NOOR_MODE`: default backend, usually `ollama`
- `NOOR_MODEL`: model name, default `mistral:latest`
- `OLLAMA_BASE`: Ollama base URL
- `OLLAMA_API_URL`: Ollama chat endpoint
- `NOOR_HTTP_TIMEOUT`: request timeout in seconds
- `NOOR_KEEP_ALIVE`: how long Ollama should keep the model warm
- `NOOR_REPORTS_DIR`: where reports are written
- `NOOR_ALLOWED_EXT`: supported source file extensions for code analysis
- `NOOR_MAX_FILE_BYTES`: size limit for source files scanned by the CLI
- `COMPLIANCE_MODE`: disables file-based debug logging when `true`

## Output

- Markdown reports are saved to `reports/`
- Re-running the same command creates a new versioned report instead of overwriting the old one
- Each Markdown report starts with a `Generated:` timestamp
- Dependency analysis also saves JSON output

## Troubleshooting

`noor` points to the wrong executable:
Run `command -v noor`. If it does not point to `.venv/bin/noor`, reactivate the virtual environment or run `.venv/bin/noor` directly.

Ollama is installed but requests fail:
Check `ollama list`, confirm `NOOR_MODEL` matches an installed model, and increase `NOOR_HTTP_TIMEOUT` if the model is slow to respond.

Ollama returns an HTTP error:
Noorlytics now shows the HTTP status code and response body when available. Use that message to decide whether the issue is a missing model, server crash, or invalid request.

No files were analyzed:
Check `NOOR_ALLOWED_EXT` and `NOOR_MAX_FILE_BYTES` in `.env`. The CLI only analyzes supported extensions and skips oversized files.

Generated tests are weak for non-Python code:
That is expected today. Review generated test files before treating them as executable output.

## Compliance Behavior

- `--mode=ollama` keeps inference local to your machine
- `COMPLIANCE_MODE=true` disables file-based debug logging
- operational status messages still print to the terminal

## Notes On setup_noorlytics.sh

The setup script already covers the essential Python-side setup correctly:

- virtual environment creation
- editable install
- dependency installation
- `.env` bootstrap
- shell activation
- active CLI path confirmation

The missing piece was backend guidance after install. The script now tells the user what to do next for either Ollama or OpenAI.

## Roadmap

- stronger test validation for non-Python `add-tests`
- more CLI feedback for skipped files
- broader automated test coverage for parsing and command behavior
- optional CI integration patterns
