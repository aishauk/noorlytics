#!/usr/bin/env bash
# restore.sh – återställ prompt & färger

# Ta bort custom alias
unalias noor 2>/dev/null || true

# Återställ prompt
export PS1="$OLD_PS1"

# Avaktivera venv
deactivate 2>/dev/null || true

clear
echo "✅ Demo mode OFF – prompt, färger och miljö återställda"