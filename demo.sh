#!/usr/bin/env bash
# demo.sh – cinema mode för Noorlytics demo
# Grön pil, cyan kommando, vit output

# 1. Spara originalprompt
export OLD_PS1="$PS1"

# 2. Prompt (grön pil) + inmatning (cyan)
# Trick: readline färgar input i cyan via bind
export PS1=$'\033[1;32m❯ \033[0;36m'
bind 'set colored-stats on'
bind 'set completion-prefix-display-length 2'

# 3. Forcerad outputfärg: vit (ANSI 37)
# alias som wrapp: varje gång du kör noor => pipe till sed som lägger vit
alias noor='NO_COLOR=1 command noor | sed "s/^/\x1b[37m/; s/$/\x1b[0m/"'
export VIRTUAL_ENV_DISABLE_PROMPT=1

# 4. Aktivera venv (ändra sökväg om din venv heter något annat)
source venv/bin/activate

# 5. Rensa terminalen
clear

echo "🎬 Demo mode ON – grön pil, cyan kommandon, vit output"
echo "👉 Testa: noor --help"
echo