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
- `refactor` with automatic file rewriting (see File Rewriting section below)
- Versioned Markdown reports with `Generated:` timestamps

Partial:

- `add-tests` is strongest for Python and less predictable for other languages
- Dependency analysis works across multiple ecosystems, but unusual manifests may need manual review

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

# Generate refactor suggestions for one file
noor --mode=ollama suggest examples/legacyfile.py

# Generate refactor suggestions for entire package
noor --mode=ollama suggest examples/

# Generate unit test stubs for one file
noor --mode=ollama add-tests examples/legacyfile.py

# Generate tests for all files in a package
noor --mode=ollama add-tests examples/

# Create refactor plan for one file
noor --mode=ollama refactor examples/legacyfile.py

# Create refactor plans for entire package
noor --mode=ollama refactor examples/

# Preview changes without modifying files
noor --mode=ollama refactor examples/legacyfile.py --dry-run
noor --mode=ollama refactor examples/legacyfile.py -dr

# Interactively apply changes (approve each one)
noor --mode=ollama refactor examples/legacyfile.py --interactive
noor --mode=ollama refactor examples/legacyfile.py -i

# Automatically apply safe (LOW-priority) changes
noor --mode=ollama refactor examples/legacyfile.py --apply
noor --mode=ollama refactor examples/legacyfile.py -a

# Restore from backup
noor --mode=ollama refactor examples/legacyfile.py --undo
noor --mode=ollama refactor examples/legacyfile.py -u

# Apply changes and commit to git
noor --mode=ollama refactor examples/legacyfile.py --interactive --git-commit
noor --mode=ollama refactor examples/legacyfile.py -i -gc

# Auto-apply safe changes and commit to git
noor --mode=ollama refactor examples/legacyfile.py --apply --git-commit
noor --mode=ollama refactor examples/legacyfile.py -a -gc

# Standalone git operations (no refactor needed)
noor git myfile.py --status
noor git myfile.py -s
noor git myfile.py --branch
noor git myfile.py -b
noor git myfile.py --commit "my changes"
noor git myfile.py -c "my changes"
```

## Command Reference

`analyze`

- analyzes a single file or entire package/directory
- recursively finds all supported files when given a directory
- writes versioned Markdown reports to `reports/`
- for packages, shows progress and summary of analyzed files

`suggest`

- generates improvement and refactoring suggestions for a file or package
- recursively finds all supported files when given a directory
- writes versioned Markdown reports to `reports/`
- for packages, shows progress and summary of generated suggestions

`add-tests`

- generates test stubs for a single file or entire package/directory
- recursively finds all supported files when given a directory
- saves test files to `tests/` folder
- most reliable for Python inputs
- output pattern: `tests/{source_stem}.tests.py`
- for packages, shows progress and summary of generated tests

`analyze-deps`

- analyzes a single dependency manifest for license risk and known vulnerabilities
- supports: `requirements.txt`, `pyproject.toml`, `package.json`, `packages.config`
- writes a JSON report and a versioned Markdown summary to `reports/`

`refactor`

- creates AI-assisted refactor plans for a file or package
- recursively finds all supported files when given a directory
- writes versioned Markdown reports to `reports/`
- for packages, shows progress and summary of generated refactor plans
- supports automatic file rewriting with `--apply`/`-a`, `--interactive`/`-i`, `--dry-run`/`-dr`, `--undo`/`-u`, `--git-commit`/`-gc`
- see File Rewriting section below for details

`git`

- standalone git operations (does NOT require refactor)
- stage files with `--commit` option
- show git status with `--status`
- show current branch with `--branch`
- works independently from any refactoring workflow

## File Rewriting (Stable)

The `refactor` command now supports automatic application of refactoring suggestions:

### Workflow

1. **Generate refactor plan** (default):

   ```bash
   noor refactor myfile.py
   ```

   Creates a markdown plan with structured, prioritized changes in `reports/myfile.py.refactor.v1.md`

2. **Preview changes without modifying** (dry-run):

   ```bash
   noor refactor myfile.py --dry-run
   noor refactor myfile.py -dr
   ```

   Shows a summary of proposed changes in the terminal (no file modifications).

3. **Interactive: Approve changes one-by-one**:

   ```bash
   noor refactor myfile.py --interactive
   noor refactor myfile.py -i
   ```

   Prompts you before each change. Atomic: all-or-nothing application.

4. **Auto-apply safe changes**:

   ```bash
   noor refactor myfile.py --apply
   noor refactor myfile.py -a
   ```

   Automatically applies only LOW-priority, low-risk changes. MEDIUM and HIGH priority changes require `--interactive`.

5. **Undo last refactoring**:

   ```bash
   noor refactor myfile.py --undo
   noor refactor myfile.py -u
   ```

   Restores from the most recent backup in `.noor_backups/`.

6. **Auto-commit to git** (optional):

   ```bash
   noor refactor myfile.py --interactive --git-commit
   noor refactor myfile.py -i -gc

   noor refactor myfile.py --apply --git-commit
   noor refactor myfile.py -a -gc
   ```

   Automatically stages and commits refactored files to git after changes are applied (only if in a git repository).
   Can be combined with `--interactive` or `--apply`. Does nothing on `--dry-run` or `--undo`.
   Commit message: `refactor: myfile.py - N change(s) applied via noorlytics`

### Safety Features

- **Atomic changes**: All changes apply or none do. Partial refactoring is not allowed.
- **Automatic backups**: Original file is backed up to `.noor_backups/` before modification.
- **Git-compatible diffs**: Changes are saved to `reports/{file}.refactor.diff` for integration with git workflows.
- **Priority-based execution**: HIGH and MEDIUM priority changes require explicit approval; LOW priority are auto-safe.
- **Full rollback**: `--undo` can restore any previous state.

### Example Workflow

```bash
# 1. Generate and review plan
noor refactor legacy_code.py

# 2. See what would change without modifying
noor refactor legacy_code.py --dry-run
noor refactor legacy_code.py -dr

# 3. Interactively approve high-impact changes
noor refactor legacy_code.py --interactive
noor refactor legacy_code.py -i

# 4. If something breaks, restore:
noor refactor legacy_code.py --undo
noor refactor legacy_code.py -u

# 5. (Optionally) auto-apply only low-risk refactors to clean up:
noor refactor legacy_code.py --apply
noor refactor legacy_code.py -a
```

## Configuration

Main configuration lives in `.env`. The default template is in `.env.sample`.

Most useful settings:

- `NOOR_MODE`: default backend, usually `ollama`
- `NOOR_MODEL`: model name, default `mistral:latest`
- `OLLAMA_BASE`: Ollama base URL
- `OLLAMA_API_URL`: Ollama chat endpoint
- `NOOR_HTTP_TIMEOUT`: request timeout in seconds
- `NOOR_KEEP_ALIVE`: how long Ollama should keep the model warm
- `NOOR_REPORTS_DIR`: where analysis reports are written
- `NOOR_TESTS_DIR`: where generated test stubs are written
- `NOOR_ALLOWED_EXT`: supported source file extensions for code analysis
- `NOOR_MAX_FILE_BYTES`: size limit for source files scanned by the CLI
- `COMPLIANCE_MODE`: disables file-based debug logging when `true`

## Output

- Analysis reports are saved to `reports/`
- Unit test stubs are saved to `tests/`
- Re-running the same command creates a new versioned report instead of overwriting the old one
- Each Markdown report starts with a `Generated:` timestamp
- Dependency analysis also saves JSON output to `reports/`

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
