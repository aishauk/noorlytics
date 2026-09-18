#!/usr/bin/env bash
# Source from the repository root: source setup_noorlytics.sh

_noor_setup() {
    _noor_install_target="."
    case "${1:-}" in
        "") ;;
        --openai) _noor_install_target=".[openai]" ;;
        *)
            echo "Usage: source setup_noorlytics.sh [--openai]"
            return 2
            ;;
    esac

    if [[ ! -f "pyproject.toml" ]]; then
        echo "Run this script from the Noorlytics repository root."
        return 1
    fi

    _noor_python=""
    for _noor_candidate in python3.14 python3.13 python3.12 python3.11 python3.10 python3; do
        if command -v "$_noor_candidate" >/dev/null 2>&1 && "$_noor_candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then
            _noor_python="$_noor_candidate"
            break
        fi
    done

    if [[ -z "$_noor_python" ]]; then
        echo "Python 3.10 or newer is required. Install it, then run: source setup_noorlytics.sh"
        return 1
    fi

    if [[ ! -d ".venv" ]]; then
        "$_noor_python" -m venv .venv || return 1
    fi

    source .venv/bin/activate || return 1
    _noor_venv_python=".venv/bin/python"
    if [[ ! -x "$_noor_venv_python" ]]; then
        _noor_venv_python=".venv/bin/python3"
    fi
    if [[ ! -x "$_noor_venv_python" ]]; then
        echo "The virtual environment does not contain a Python executable. Remove .venv and run the setup script again."
        return 1
    fi

    "$_noor_venv_python" -m pip install --upgrade pip || return 1
    "$_noor_venv_python" -m pip install -e "$_noor_install_target" || return 1

    if [[ ! -f ".env" && -f ".env.sample" ]]; then
        cp .env.sample .env || return 1
        echo "Created .env from .env.sample. Add OPENAI_API_KEY only for OpenAI mode."
    fi

    if [[ -f ".env" ]]; then
        set -a
        source .env
        set +a
    fi

    printf 'Noorlytics is ready: %s\n' "$(noor --version)"
    printf 'Using noor from: %s\n' "$(command -v noor)"

    if [[ "$_noor_install_target" == ".[openai]" ]]; then
        if [[ -z "${OPENAI_API_KEY:-}" ]]; then
            echo "OpenAI mode enabled. Next step: export OPENAI_API_KEY before running 'noor --mode=openai ...'"
        else
            echo "OpenAI mode enabled and OPENAI_API_KEY is present in the current shell."
        fi
    else
        if command -v ollama >/dev/null 2>&1; then
            echo "Ollama detected. Next steps: run 'ollama pull ${NOOR_MODEL:-mistral:latest}' once, then 'ollama serve' if the service is not already running."
        else
            echo "Ollama is not installed or not on PATH. Install Ollama, then run 'ollama pull ${NOOR_MODEL:-mistral:latest}'."
        fi
    fi
}

_noor_setup
_noor_exit_code=$?
unset -f _noor_setup
unset _noor_candidate _noor_install_target _noor_python _noor_venv_python
return "$_noor_exit_code" 2>/dev/null || exit "$_noor_exit_code"
