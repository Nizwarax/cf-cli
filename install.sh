#!/bin/bash

# --- ANSI Color Codes ---
RESET="\033[0m"
RED="\033[31m"
GREEN="\033[32m"
YELLOW="\033[33m"
BLUE="\033[34m"
MAGENTA="\033[35m"
CYAN="\033[36m"

# --- Deteksi Lingkungan ---
IS_TERMUX=false
if [[ -n "$PREFIX" ]] && [[ "$PREFIX" == *com.termux* ]]; then
    IS_TERMUX=true
fi

# --- Fungsi Logging Berwarna ---
log() { echo -e "${CYAN}[*]${RESET} $1"; }
success() { echo -e "${GREEN}[✓]${RESET} $1"; }
warn() { echo -e "${YELLOW}[!]${RESET} $1"; }
error() { echo -e "${RED}[✗]${RESET} $1" >&2; exit 1; }

# --- Cek dependensi ---
log "Checking required tools..."
for cmd in python3 curl; do
    if ! command -v "$cmd" &> /dev/null; then
        if [[ "$IS_TERMUX" == true ]]; then
            error "$cmd not found. Run: pkg install python curl"
        else
            error "$cmd not found. Install with your package manager (e.g., apt)."
        fi
    fi
done

# --- Instal pip & requests ---
if ! python3 -m pip --version &> /dev/null; then
    log "Installing pip..."
    python3 -m ensurepip --user --upgrade > /dev/null 2>&1
fi
log "Installing 'requests'..."
python3 -m pip install --user --quiet requests || error "Failed to install requests"

# --- Tentukan lokasi instalasi ---
if [[ "$IS_TERMUX" == true ]]; then
    INSTALL_DIR="$PREFIX/bin"
    log "Termux detected → installing to $INSTALL_DIR"
else
    INSTALL_DIR="$HOME/.local/bin"
    log "Standard Linux/VPS → installing to $INSTALL_DIR"
fi
mkdir -p "$INSTALL_DIR"

# --- Download cf.py ---
SCRIPT_PATH="$INSTALL_DIR/cf"
REPO_URL="https://raw.githubusercontent.com/Nizwarax/cf-cli/main/cf.py"

log "Downloading cf.py..."
if ! curl -sSL "$REPO_URL" -o "$SCRIPT_PATH"; then
    error "Download failed. Check your connection."
fi

# --- Tambahkan shebang & jadikan executable ---
if ! head -n1 "$SCRIPT_PATH" | grep -q "^#!"; then
    sed -i '1i#!/usr/bin/env python3' "$SCRIPT_PATH"
fi
chmod +x "$SCRIPT_PATH"

# --- Selesai ---
echo
success "Installation complete!"

if [[ "$IS_TERMUX" == true ]]; then
    echo
    echo -e "${GREEN}You can now run:${RESET} ${MAGENTA}cf${RESET}"
else
    echo
    echo -e "${GREEN}Run the tool using:${RESET}"
    echo
    echo -e "    ${MAGENTA}$INSTALL_DIR/cf${RESET}"
    echo
    warn "Optional: Add $INSTALL_DIR to your PATH manually if you want to use 'cf' directly."
fi
