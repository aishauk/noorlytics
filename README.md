# Noorlytics CLI

Noorlytics is a local-first CLI for code analysis, refactor guidance, dependency review, test stub generation, and decision management.

## Privacy / data flow

Noorlytics is designed to run locally by default.

- `--mode ollama` uses a local Ollama endpoint
- `analyze-deps` is local-only by default
- `--network` enables remote dependency checks and OSV registry lookups only when you explicitly choose it
- `--mode openai` sends prompts to OpenAI, which is intended for teams that have already approved that workflow
- `noor gdpr <path>` scans source code for common GDPR/privacy risk patterns like PII logging and insecure data transfer

In short: local-first is the default, and remote calls are opt-in.

## GDPR/privacy scan

Use the built-in privacy check when you want a quick review for common GDPR issues in source code:

```bash
noor gdpr examples/legacyfile.py
noor gdpr examples/
```

This flags patterns such as:

- personal data being logged
- personal data sent over insecure HTTP
- personal data stored without a clear minimization/retention control

The findings are saved to `reports/gdpr_findings.json`.

## Security & Compliance Scan

Scan code for security issues and compliance violations in one unified report:

```bash
noor unified-scan examples/security_issues.py   # Single file
noor unified-scan examples/                     # Entire directory
noor unified-scan . -o my_report.json           # Custom output file
```

This combines:

- **Security checks**: encryption, hardcoded credentials, audit logging, authentication, error handling
- **Compliance checks**: HIPAA, PCI-DSS, SOC 2, ISO 27001, FedRAMP requirements
- **Correlation**: automatically links related issues (e.g., "HTTP without encryption" is also a "HIPAA violation")
- **Deduplication**: merges overlapping findings from multiple scanners

Results are saved to `reports/unified_scan_findings.json` with:

- All findings with their sources (security, compliance, or both)
- Severity levels (high, medium, low)
- Correlation metadata showing related issues

## When to use `--offline` vs `--network`

Use the simplest option that fits your goal:

- Use `noor analyze-deps --offline requirements.txt` when:
  - you want privacy-first checks
  - you are on a locked-down or air-gapped machine
  - you want fast local-only checks without external calls
  - you want a conservative result that only uses installed metadata and local info

- Use `noor analyze-deps --network requirements.txt` when:
  - you want live package metadata, registry data, or OSV vulnerability lookups
  - you are working in a trusted environment and accept remote queries
  - you need the most complete public metadata for packages that are not fully visible locally

Recommended default:

```bash
# safest default
noor analyze-deps --offline requirements.txt
```

Only add `--network` when you intentionally want remote lookups and are comfortable with the data leaving your machine.

## ✨ Features

- Local-first analysis with Ollama by default
- Optional OpenAI mode (`--mode=openai`)
- Dependency analysis (`requirements.txt`, `pyproject.toml`, `package.json`, etc.)
- Offline dependency checks by default
- Explicit network checks with `--network`
- Suggest and stub out refactoring ideas
- Generate refactor suggestions in Markdown
- Generate unit test stubs
- License audit (detect risky or deprecated licenses)
- Security checks for vulnerable dependencies
- Customer-context-aware decision assessment
- Decision persistence and versioning with SQLite
- Decision history tracking and version comparison
- Analytics dashboards and metrics reports
- Optional cost tracking for OpenAI usage
- Markdown reports to `reports/`

## Capability Status

Stable:

- `analyze` for supported source files
- `suggest` for refactoring guidance
- `analyze-deps` for dependency, license, and vulnerability checks
- `refactor` with automatic file rewriting (see File Rewriting section below)
- `assess` with customer context for prioritized decisions
- `decisions` for decision management and querying
- `history` for tracking assessment versions and changes
- `metrics` for analytics dashboards and reports
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
# Analyze one file locally
noor --mode=ollama analyze examples/legacyfile.py

# Analyze a directory of supported source files
noor --mode=ollama analyze examples/

# Generate refactor suggestions for one file
noor --mode=ollama suggest examples/legacyfile.py

# Generate refactor suggestions for an entire package
noor --mode=ollama suggest examples/

# Generate unit test stubs for one file
noor --mode=ollama add-tests examples/legacyfile.py

# Generate tests for all files in a package
noor --mode=ollama add-tests examples/

# Create a refactor plan for one file
noor --mode=ollama refactor examples/legacyfile.py

# Preview changes without modifying files
noor --mode=ollama refactor examples/legacyfile.py --dry-run

# Interactively apply changes (approve each one)
noor --mode=ollama refactor examples/legacyfile.py --interactive

# Automatically apply all complete refactor changes
noor --mode=ollama refactor examples/legacyfile.py --apply

# Restore from backup
noor --mode=ollama refactor examples/legacyfile.py --undo

# Dependency scan: local-only by default
noor analyze-deps requirements.txt

# Dependency scan: allow public registry / OSV lookups
noor analyze-deps --network requirements.txt

# Use OpenAI if you have approved that workflow
noor --mode=openai analyze examples/legacyfile.py
```

## Phase 3: Decision Management & Assessment

Noorlytics now goes beyond technical analysis to generate business-prioritized decisions based on your customer's unique context.

### Workflow: From Findings to Decisions

1. **Generate Findings** via `analyze-deps` (dependency manifest → technical findings)
   - Identifies vulnerabilities, risky licenses, unpinned dependencies
   - Generates verified findings schema with evidence traceability
   - Outputs JSON file for consumption by assessment engine

2. **Create Customer Context** (JSON file with risk preferences and constraints)
   - Define risk profile: security, business continuity, cost control, delivery speed
   - Specify constraints: upgrade windows, license compliance, legacy runtimes
   - Customer context is used to prioritize decisions

3. **Generate Decisions** via `assess` (findings + context → prioritized decisions)
   - Transforms generic findings into customer-specific decisions
   - Assigns Priority (P1-P4) based on customer risk preferences
   - Includes business impact, effort estimate, target timeframe
   - Can optionally enhance decisions with LLM-generated rationales

4. **Track History** via `history` (persist versions and compare changes)
   - Saves each assessment to persistent SQLite database
   - Tracks decision versions across multiple assessments
   - Enables version comparison and change auditing
   - Supports stakeholder reporting with comparison matrices

5. **Monitor Metrics** via `metrics` (analytics dashboards and reports)
   - Dashboard: overview of all decisions by priority and category
   - Customer: stakeholder-focused metrics with trends
   - By-Category: breakdown of decisions by type
   - Trend: decision velocity and effort estimation over time

### Key Features of Customer Context

Noorlytics includes ready-to-use customer context templates in `noorlytics/templates/`:

**Default Template (Recommended for most users)**:

- `customer_context_default.json` - Balanced profile suitable for general use (auto-used if no template specified)

**Industry-Specific Templates**:

- `customer_context_fintech.json` - FinTech startup (Speed + Cost focus)
- `customer_context_enterprise.json` - Enterprise deployment (Comprehensive)
- `customer_context_healthcare.json` - Healthcare industry (Security + Compliance)
- `customer_context_startup.json` - Growth-focused startup

**Quick Start - Use the Default Template (no flag needed)**:

```bash
noor assess requirements.txt
```

**To use an industry-specific template**:

```bash
noor assess requirements.txt -c noorlytics/templates/customer_context_enterprise.json
```

**To customize for your needs**:

```bash
cp noorlytics/templates/customer_context_default.json my_context.json
# Edit my_context.json, then:
noor assess requirements.txt -c my_context.json
```

**Risk Preferences** (high/medium/low) control decision prioritization:

- `security`: Impact of vulnerability exposure on priority
- `business_continuity`: Impact of operational risk on priority
- `cost_control`: Emphasis on cost of remediation vs benefit
- `delivery_speed`: Trade-off between quick fixes vs comprehensive solutions

**Constraints** enforce business rules:

- `upgrade_window_days`: Days available for updates before deadline
- `requires_oss_license_review`: Whether OSS license review blocks deployment
- `legacy_runtime`: Maintained legacy runtime (e.g., Python 3.8) for compatibility
- `min_security_score`: Minimum acceptable security score (0-100)

### Database & Persistence

Decisions are stored in SQLite with:

- Composite key: (manifest_path, decision_id, assessment_version)
- Full audit trail: created_at, updated_at, rationale_version
- JSON export: decisions can be exported with complete metadata
- CSV export: flattened format for spreadsheet analysis
- Markdown export: human-readable format for reports

### LLM-Enhanced Decisions

When `--llm-model` flag is specified during `assess`:

```bash
noor assess requirements.txt -c noorlytics/templates/customer_context_default.json --llm-model=ollama:mistral
```

Noorlytics generates LLM-enhanced rationales for each decision:

- Model: Ollama (local) or OpenAI (cloud)
- Caching: LRU cache prevents redundant LLM calls
- Timeout: 5-second timeout with graceful fallback to static rationale
- Batch processing: Multiple decisions processed efficiently

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
- supports automatic file rewriting with `--apply`/`-a` for all complete refactor blocks, `--interactive`/`-i`, `--dry-run`/`-dr`, `--undo`/`-u`, `--git-commit`/`-gc`
- see File Rewriting section below for details

`git`

- standalone git operations (does NOT require refactor)
- stage files with `--commit` option
- show git status with `--status`
- show current branch with `--branch`
- works independently from any refactoring workflow

`assess`

- takes dependency findings and customer context, generates prioritized decisions
- transforms generic technical findings into business-focused recommendations
- considers customer risk preferences, constraints, and deployment model
- optional `--context` / `-c` flag: defaults to `noorlytics/templates/customer_context_default.json` if not specified
- supports LLM-enhanced rationales with fallback to static explanations
- optionally saves decisions to persistent history for tracking
- can compare decisions with previous assessment versions
- exports decisions in JSON, CSV, or Markdown formats
- generates metrics reports for customer stakeholder reports

`decisions`

- manages and queries stored decisions
- `list`: list all decisions with optional filtering by priority, category, or manifest
- `show`: display detailed information about a specific decision including rationale
- `export`: export decision set in JSON, CSV, or Markdown with audit trail

`history`

- tracks decision versions across multiple assessments
- `show`: timeline of all assessments for a dependency manifest
- `diff`: compare decisions between two assessment versions, show what changed
- `compare`: generate comparison matrix across multiple assessment versions for stakeholder reports

`metrics`

- analytics dashboards and reports for decision insights
- `dashboard`: shows key metrics including total decisions by priority, average effort, business impact
- `customer`: generates customer-specific metrics report with trends
- `by-category`: breakdown of decisions by category (Security, Performance, Refactoring, etc.)
- `trend`: generates trend analysis showing decision velocity and effort tracking over time

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
