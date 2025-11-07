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

# --- Cek dependensi dasar ---
log "Checking required tools..."
for cmd in python3 curl; do
    if ! command -v "$cmd" &> /dev/null; then
        if [[ "$IS_TERMUX" == true ]]; then
            error "$cmd not found. Please run: pkg install python curl"
        else
            error "$cmd not found. Please install it first (e.g., apt install python3 curl)."
        fi
    fi
done

# --- Nonaktifkan virtual environment sementara (jika ada) ---
if [[ -n "$VIRTUAL_ENV" ]]; then
    unset VIRTUAL_ENV
    # Hapus path venv dari PATH
    export PATH=$(echo "$PATH" | sed 's|/.*/\.cf-venv/bin:||g; s|/.*/\.cf-venv/bin||g')
fi

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
    error "pip not available and could not be installed automatically."
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

# --- Setup PATH: hanya di VPS, dan hanya ke ~/.bashrc ---
if [[ "$IS_TERMUX" == false ]]; then
    if [[ ":$PATH:" != *":$INSTALL_DIR:"* ]]; then
        # Tambahkan ke ~/.bashrc jika belum ada
        if ! grep -q "$INSTALL_DIR" ~/.bashrc 2>/dev/null; then
            echo "export PATH=\"\$PATH:$INSTALL_DIR\"" >> ~/.bashrc
        fi
        export PATH="$PATH:$INSTALL_DIR"
        log "Added $INSTALL_DIR to PATH in ~/.bashrc"
    fi
else
    log "Termux: $INSTALL_DIR is already in PATH"
fi

# --- Selesai ---
echo
success "Installation complete!"
echo
echo -e "${GREEN}You can now run the tool by typing:${RESET}"
echo
echo -e "    ${MAGENTA}cf${RESET}"
echo
if [[ "$IS_TERMUX" == false ]]; then
    warn "If 'cf' is not found, restart your shell or run: ${CYAN}source ~/.bashrc${RESET}"
fi
