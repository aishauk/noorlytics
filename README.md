# Noorlytics CLI – Quick Start Guide

**Noorlytics** is a local-first CLI for analyzing code quality, dependencies, security, compliance, and generating AI-powered refactoring plans with business-priority decisions.

---

## 🔧 Setup Requirements

| Requirement          | Version                          |
| -------------------- | -------------------------------- |
| Python               | 3.10+                            |
| Backend (choose one) | Ollama (local) OR OpenAI API key |
| Shell                | Bash or Zsh                      |

---

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

## Setup Paths

### Ollama setup

Download ollama from https://ollama.com/ , and use a separate terminal to run the following.

```bash
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

---

## 📋 All noor CLI Commands

### Core Commands

| Command       | Purpose                                                                                                               | Usage                                                             |
| ------------- | --------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| **analyze**   | Scan code for technical debt, quality issues, performance problems (Phase 5: cache, parallel, incremental, benchmark) | `noor analyze file.py` or `noor analyze src/ --cache --benchmark` |
| **suggest**   | Generate specific refactoring suggestions with rationale                                                              | `noor suggest file.py`                                            |
| **refactor**  | Create and apply AI-assisted refactoring plans                                                                        | `noor refactor file.py --interactive`                             |
| **add-tests** | Generate unit test stubs for code coverage                                                                            | `noor add-tests file.py`                                          |

### Dependency & Security Scanning

| Command            | Purpose                                                                | Usage                                          |
| ------------------ | ---------------------------------------------------------------------- | ---------------------------------------------- |
| **analyze-deps**   | Check dependencies for vulnerabilities, licenses, compliance           | `noor analyze-deps requirements.txt --network` |
| **gdpr**           | Scan for GDPR/privacy violations (PII logging, insecure data transfer) | `noor gdpr src/`                               |
| **audit-security** | Audit code for encryption, logging, authentication, secrets handling   | `noor audit-security file.py --remediate`      |
| **scan-standards** | Check compliance with HIPAA, PCI-DSS, SOC2, ISO27001, FedRAMP          | `noor scan-standards src/ --standard hipaa`    |
| **unified-scan**   | Merge security and compliance findings into one report                 | `noor unified-scan .`                          |

### Cache Management (Phase 5)

| Command                | Purpose                                                   | Usage                                              |
| ---------------------- | --------------------------------------------------------- | -------------------------------------------------- |
| **cache stats**        | Show cache statistics and usage information               | `noor cache stats`                                 |
| **cache clear**        | Clear all cached findings (with optional --confirm flag)  | `noor cache clear` or `noor cache clear --confirm` |
| **cache info**         | Display detailed cache location and metrics               | `noor cache info`                                  |
| **cache reset-hashes** | Reset file hash tracking (forces re-hashing of all files) | `noor cache reset-hashes --confirm`                |

### Decision Management (Phase 3)

| Command       | Purpose                                                                         | Usage                                         |
| ------------- | ------------------------------------------------------------------------------- | --------------------------------------------- |
| **assess**    | Convert findings into business-priority decisions (P1=Critical, P4=Enhancement) | `noor assess requirements.txt --save-history` |
| **decisions** | Query stored decisions (list, show, export)                                     | `noor decisions list --priority P1`           |
| **history**   | Track and compare decision versions over time                                   | `noor history show requirements.txt`          |
| **metrics**   | View decision analytics dashboards and trends                                   | `noor metrics dashboard --period 30`          |

---

## 🎯 Common Workflows

### Workflow 1: Quick Code Review

```bash
noor analyze myfile.py
noor suggest myfile.py
noor audit-security myfile.py
```

### Workflow 2: Dependency Security Audit

```bash
noor analyze-deps requirements.txt --network # Default local mode if --network is not indicated
noor analyze-deps pyproject.toml
noor gdpr src/
```

#### When to use `--offline` vs `--network`

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

### Workflow 3: Compliance Check

```bash
noor scan-standards src/ --standard hipaa        # HIPAA only
noor scan-standards src/ --standard iso27001     # ISO 27001 only
noor scan-standards src/                         # All standards
```

### Workflow 4: Refactoring with Auto-Apply

```bash
noor refactor file.py --dry-run                  # Preview changes
noor refactor file.py --interactive              # Review each change
noor refactor file.py --apply --git-commit       # Apply + commit to git
```

### Workflow 5: Full Assessment & Decision Making

```bash
noor analyze-deps requirements.txt --network             # Find issues
noor assess requirements.txt --save-history             # Create decisions
noor decisions list --priority P1                       # View critical items
noor history show requirements.txt                      # Track changes over time
noor metrics dashboard --period 30                      # View trends
```

### Workflow 6: Performance Optimization (Phase 5)

```bash
# Default: all performance features enabled (cache, benchmark, incremental)
noor analyze src/

# Disable specific features if needed
noor analyze src/ --no-incremental           # Skip incremental analysis
noor analyze src/ --no-benchmark             # Skip performance metrics
noor analyze src/ --no-cache                 # Disable cache

# Customize performance
noor analyze src/ --parallel 8               # Use 8 threads
noor analyze src/ --no-cache --parallel 1   # Sequential, no cache

# Manage cache
noor cache stats      # Show cache statistics
noor cache clear      # Clear all cached findings
noor cache info       # Detailed cache information
```

---

## 📊 Command Options Reference

### Global Options

```bash
--mode ollama          # Use local Ollama (default)
--mode openai          # Use OpenAI API
--help                 # Show command help
--version              # Show CLI version
```

### Performance & Caching (Phase 5)

Add these flags to analyze, suggest, audit-security, gdpr, and scan-standards commands:

```bash
--cache/--no-cache         # Use cached results (default: enabled)
                          # Caches analysis findings in .noor/cache/
                          # 50x faster for repeated files (5ms vs 250ms)

--parallel N              # Number of worker threads (default: 4)
                          # 0 = auto-detect CPU cores
                          # 3-4x faster with parallel processing

--incremental/--no-incremental  # Only analyze changed files (default: enabled)
                                # 25-50x faster when only 1-2 files changed

--benchmark/--no-benchmark      # Measure and track performance metrics (default: enabled)
                                # Saves to reports/performance_benchmarks.json
                                # <5ms overhead
```

### Performance Impact

| Scenario                     | Without Phase 5 | With Phase 5   | Improvement    |
| ---------------------------- | --------------- | -------------- | -------------- |
| Cached results               | 250ms           | 5ms            | **50x** ⚡⚡⚡ |
| Parallel (4 threads)         | 1000ms          | 300ms          | **3-4x** ⚡    |
| Incremental (1 file changed) | 125s            | 2.5s           | **50x** ⚡⚡⚡ |
| First-time + cache build     | N/A             | +10ms overhead | **Negligible** |

### analyze

```bash
--cache/--no-cache                        # Use cached findings (default: enabled, Phase 5)
--parallel N                              # Number of worker threads (default: 4, Phase 5)
--incremental/--no-incremental            # Only changed files (default: enabled, Phase 5)
--benchmark/--no-benchmark                # Measure performance (default: enabled, Phase 5)
```

### refactor

```bash
--apply (-a)           # Auto-apply changes automatically (default: plan only)
--dry-run (-dr)        # Show changes without modifying files
--interactive (-i)     # Prompt for confirmation before each change
--undo (-u)            # Restore previous refactoring from backup
--git-commit (-gc)     # Auto-commit changes to git after applying
```

### add-tests

```bash
--lang python          # Specify language (auto-detects from extension if omitted)
```

### analyze-deps

```bash
--offline              # Use only local data (no network lookup)
--network              # Allow live registry & security checks
```

### audit-security

```bash
--check encryption           # Check only encryption issues
--check audit_logging        # Check only logging issues
--check authentication       # Check only auth issues
--check secrets              # Check only secrets/credentials
--check all                  # Check everything (default)
--remediate (-r)             # Generate LLM-powered remediation
--cache/--no-cache           # Use cached results (Phase 5, default: enabled)
--parallel N                 # Number of worker threads (Phase 5, default: 4)
--benchmark                  # Measure performance metrics (Phase 5)
```

### scan-standards

```bash
--standard hipaa             # HIPAA only
--standard pci-dss           # PCI-DSS only
--standard soc2              # SOC 2 only
--standard iso27001          # ISO 27001 only
--standard fedramp           # FedRAMP only
--standard all               # All standards (default)
--remediate (-r)             # Generate LLM-powered remediation
--cache/--no-cache           # Use cached results (default: enabled)
--parallel N                 # Number of worker threads (default: 4)
--incremental                # Only analyze changed files (Phase 5)
--benchmark                  # Measure performance metrics (Phase 5)
```

### assess

```bash
--context custom.json        # Use custom decision context
--save-history               # Store decisions in database for tracking
--compare-versions           # Show changes from last assessment
--create-report report.md    # Generate full report with metrics
--export-format json         # Export as JSON (or csv, markdown)
```

### decisions

```bash
noor decisions list                          # All decisions
noor decisions list --priority P1            # Only critical
noor decisions list --customer "Acme Corp"   # Customer-specific
noor decisions show DEC-ABC123               # Show one decision
noor decisions export --format json          # Export all
```

### history

```bash
noor history show requirements.txt           # Last 5 versions
noor history show requirements.txt --all-versions  # All versions
noor history diff requirements.txt           # Compare last two versions
```

### metrics

```bash
noor metrics dashboard                       # All-time overview
noor metrics dashboard --period 30           # Last 30 days
noor metrics customer --customer "Acme"      # Customer-specific
noor metrics by-category                     # Group by category
```

---

## 📁 Supported Input Files

### Code Analysis

- `.py` (Python)
- `.cs` (C#)
- _More languages can be configured_

### Dependency Manifests

- `requirements.txt` (Python pip)
- `pyproject.toml` (Modern Python)
- `package.json` (Node.js)
- `pom.xml` (Java Maven)
- `Gemfile` (Ruby)
- `go.mod` (Go)

---

## 📤 Outputs

All results are saved to `reports/` directory:

| Output                         | Description                   |
| ------------------------------ | ----------------------------- |
| `{filename}.analyze.v1.md`     | Code analysis findings        |
| `{filename}.suggest.v1.md`     | Refactoring suggestions       |
| `{filename}.refactor.v1.md`    | Detailed refactor plan        |
| `{filename}.v1.md`             | Unit tests generated          |
| `{filename}.deps.json`         | Dependency analysis (JSON)    |
| `gdpr_findings.json`           | GDPR violations               |
| `audit_security_findings.json` | Security audit results        |
| `compliance_findings.json`     | Standards compliance issues   |
| `{filename}.assess.json`       | Business decisions (JSON)     |
| `{filename}.assess.v1.md`      | Business decisions (Markdown) |
| `decisions.db`                 | Decision history database     |

---

## 🔐 Privacy & Data Flow

- **Default:** Fully local (Ollama runs on your machine)
- **Network:** Only enabled with `--network` flag (dependency lookups, OSV checks)
- **OpenAI:** Only with `--mode openai` (requires explicit API key)
- **GDPR scan:** Analyzes code locally, no external transmission

---

## 🤔 Troubleshooting

**"noor command not found"**

```bash
# Reactivate virtual environment
source .venv/bin/activate
command -v noor
```

**"Model not available"**

```bash
# Ensure Ollama is running
ollama list
ollama serve
```

**"OpenAI API key error"**

```bash
# Set API key before running
export OPENAI_API_KEY="sk-..."
noor --mode=openai analyze file.py
```

**"No matching files found"**

- Check file extension is supported (`.py`, `.cs` by default)
- Path must exist and be readable

---

## 📚 Learn More

| Topic              | Resource                                 |
| ------------------ | ---------------------------------------- |
| Full documentation | See original README.md                   |
| Examples           | `examples/` folder                       |
| Configuration      | `.env` file (created by setup script)    |
| Database           | `noorlytics/decisions.db` (auto-created) |

---

## 💡 Quick Tips

1. **Start simple:** `noor analyze file.py` before trying complex options
2. **Use dry-run first:** `noor refactor file.py --dry-run` before applying
3. **Save decisions:** `noor assess requirements.txt --save-history` for tracking
4. **Track progress:** `noor history show requirements.txt` to see improvement over time
5. **Export results:** Use `--export-format json` to integrate with other tools
6. **Git integration:** Add `--git-commit` to auto-commit refactoring changes

---

**Ready to analyze code? Start with:** `noor --help`
