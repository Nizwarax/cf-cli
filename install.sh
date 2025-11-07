#!/bin/bash

# --- ANSI Color Codes ---
RESET="\033[0m"
RED="\033[31m"
GREEN="\033[32m"
YELLOW="\033[33m"
BLUE="\033[34m"
MAGENTA="\033[35m"
CYAN="\033[36m"
BOLD="\033[1m"

# --- Deteksi Lingkungan ---
IS_TERMUX=false
if [[ -n "$PREFIX" ]] && [[ "$PREFIX" == *com.termux* ]]; then
    IS_TERMUX=true
fi

# --- Fungsi Logging Berwarna ---
log() {
    echo -e "${CYAN}[*]${RESET} $1"
}

success() {
    echo -e "${GREEN}[✓]${RESET} $1"
}

warn() {
    echo -e "${YELLOW}[!]${RESET} $1"
}

error() {
    echo -e "${RED}[✗]${RESET} $1" >&2
    exit 1
}

# --- Cek dependensi dasar ---
log "Checking required tools..."
for cmd in python3 curl; do
    if ! command -v "$cmd" &> /dev/null; then
        if [[ "$IS_TERMUX" == true ]]; then
            error "$cmd not found. Please run: ${YELLOW}pkg install python curl${RESET}"
        else
            error "$cmd not found. Please install it first (e.g., ${YELLOW}apt install python3 curl${RESET})."
        fi
    fi
done

# --- Pastikan pip tersedia ---
if ! python3 -m pip --version &> /dev/null; then
    log "Installing pip..."
    python3 -m ensurepip --user --upgrade > /dev/null 2>&1
fi

# --- Instal library Python ---
log "Installing Python dependencies..."
if command -v pip3 &> /dev/null; then
    pip3 install --user --quiet requests
elif python3 -m pip --version &> /dev/null; then
    python3 -m pip install --user --quiet requests
else
    error "pip not available and could not be auto-installed."
fi

# --- Tentukan direktori instalasi ---
if [[ "$IS_TERMUX" == true ]]; then
    INSTALL_DIR="$PREFIX/bin"
    log "Detected Termux. Installing to ${INSTALL_DIR}"
else
    INSTALL_DIR="$HOME/.local/bin"
    log "Detected standard Linux/VPS. Installing to ${INSTALL_DIR}"
fi

mkdir -p "$INSTALL_DIR"

# --- Download script utama ---
SCRIPT_PATH="$INSTALL_DIR/cf"
REPO_URL="https://raw.githubusercontent.com/Nizwarax/cf-cli/main/cf.py"

log "Downloading cf.py from GitHub..."
if ! curl -sSL "$REPO_URL" -o "$SCRIPT_PATH"; then
    error "Failed to download cf.py. Please check your internet connection."
fi

# --- Tambahkan shebang jika belum ada ---
if ! head -n1 "$SCRIPT_PATH" | grep -q "^#!"; then
    sed -i '1i#!/usr/bin/env python3' "$SCRIPT_PATH"
fi

# --- Jadikan executable ---
chmod +x "$SCRIPT_PATH"

# --- Selesai (tanpa modifikasi PATH otomatis) ---
echo
success "Installation complete!"
echo

if [[ "$IS_TERMUX" == true ]]; then
    echo -e "${GREEN}You can now run the tool by typing:${RESET}"
    echo
    echo -e "    ${MAGENTA}cf${RESET}"
else
    echo -e "${GREEN}Run the tool using its full path:${RESET}"
    echo
    echo -e "    ${MAGENTA}$SCRIPT_PATH${RESET}"
    echo
    warn "Optional: Add $INSTALL_DIR to your PATH manually if you want to use 'cf' directly."
fi
