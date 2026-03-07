#!/usr/bin/env bash
#
# cclaw installer
# Usage: curl -sSL https://raw.githubusercontent.com/heg-wtf/cclaw/main/install.sh | bash
#
set -euo pipefail

REPO="https://github.com/heg-wtf/cclaw.git"
MIN_PYTHON_MAJOR=3
MIN_PYTHON_MINOR=11

# ─── Colors ───────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

info()  { printf "${CYAN}▸${RESET} %s\n" "$*"; }
ok()    { printf "${GREEN}✔${RESET} %s\n" "$*"; }
warn()  { printf "${YELLOW}⚠${RESET} %s\n" "$*"; }
fail()  { printf "${RED}✖${RESET} %s\n" "$*"; exit 1; }

# ─── Banner ───────────────────────────────────────────────────────────
printf "${BOLD}${CYAN}"
cat << 'BANNER'

   ██████╗ ██████╗██╗      █████╗ ██╗    ██╗
  ██╔════╝██╔════╝██║     ██╔══██╗██║    ██║
  ██║     ██║     ██║     ███████║██║ █╗ ██║
  ██║     ██║     ██║     ██╔══██║██║███╗██║
  ╚██████╗╚██████╗███████╗██║  ██║╚███╔███╔╝
   ╚═════╝ ╚═════╝╚══════╝╚═╝  ╚═╝ ╚══╝╚══╝

BANNER
printf "${RESET}"
echo "  Telegram + Claude Code personal AI assistant"
echo ""

# ─── Detect Python ────────────────────────────────────────────────────
info "Checking Python..."

PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        version=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || true)
        if [ -n "$version" ]; then
            major=$(echo "$version" | cut -d. -f1)
            minor=$(echo "$version" | cut -d. -f2)
            if [ "$major" -ge "$MIN_PYTHON_MAJOR" ] && [ "$minor" -ge "$MIN_PYTHON_MINOR" ]; then
                PYTHON="$cmd"
                break
            fi
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    fail "Python ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR}+ is required but not found. Install it first:
    macOS:   brew install python@3.11
    Ubuntu:  sudo apt install python3.11
    https://www.python.org/downloads/"
fi

ok "Python $(${PYTHON} --version 2>&1 | awk '{print $2}') found ($(command -v "$PYTHON"))"

# ─── Check Claude Code CLI ───────────────────────────────────────────
info "Checking Claude Code CLI..."

if command -v claude &>/dev/null; then
    ok "Claude Code CLI found ($(command -v claude))"
else
    warn "Claude Code CLI not found."
    echo "   cclaw requires Claude Code CLI to function."
    echo "   Install it: npm install -g @anthropic-ai/claude-code"
    echo ""
fi

# ─── Choose install method ────────────────────────────────────────────
info "Choosing install method..."

USE_PIPX=false
USE_UV=false

if command -v uv &>/dev/null; then
    USE_UV=true
    ok "uv found — will use uv tool install"
elif command -v pipx &>/dev/null; then
    USE_PIPX=true
    ok "pipx found — will use pipx install"
else
    warn "Neither uv nor pipx found — will use pip install"
    echo "   For a cleaner install, consider installing uv or pipx first:"
    echo "   uv:   curl -LsSf https://astral.sh/uv/install.sh | sh"
    echo "   pipx: ${PYTHON} -m pip install --user pipx"
    echo ""
fi

# ─── Install ──────────────────────────────────────────────────────────
info "Installing cclaw..."

if [ "$USE_UV" = true ]; then
    uv tool install "cclaw @ git+${REPO}" --force
elif [ "$USE_PIPX" = true ]; then
    pipx install "git+${REPO}" --force --python "$PYTHON"
else
    "$PYTHON" -m pip install "git+${REPO}"
fi

# ─── Verify ───────────────────────────────────────────────────────────
echo ""
if command -v cclaw &>/dev/null; then
    ok "cclaw installed successfully!"
    echo ""
    info "Getting started:"
    echo ""
    echo "   ${BOLD}cclaw init${RESET}       — initial setup (timezone, language)"
    echo "   ${BOLD}cclaw bot add${RESET}    — create your first bot"
    echo "   ${BOLD}cclaw start${RESET}      — run bots"
    echo ""
else
    warn "cclaw was installed but is not in your PATH."
    echo ""
    if [ "$USE_UV" = true ]; then
        echo "   Try: uv tool update-shell"
    elif [ "$USE_PIPX" = true ]; then
        echo "   Try: pipx ensurepath"
    else
        echo "   Make sure your Python scripts directory is in PATH."
    fi
    echo "   Then restart your terminal and try: cclaw --help"
    echo ""
fi
