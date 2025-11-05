#!/bin/bash

# --- Deteksi Lingkungan ---
IS_TERMUX=false
if [[ -n "$PREFIX" ]] && [[ "$PREFIX" == *com.termux* ]]; then
    IS_TERMUX=true
fi

# --- Fungsi Logging ---
log() {
    echo "[*] $1"
}
error() {
    echo "[!] $1" >&2
    exit 1
}

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

# --- Pastikan pip tersedia ---
if ! python3 -m pip --version &> /dev/null; then
    log "Installing pip..."
    if [[ "$IS_TERMUX" == true ]]; then
        python3 -m ensurepip --user
    else
        python3 -m ensurepip --user --upgrade
    fi
fi

# --- Instal library Python ---
log "Installing Python dependencies..."
python3 -m pip install --user --quiet requests

# --- Tentukan direktori instalasi ---
if [[ "$IS_TERMUX" == true ]]; then
    INSTALL_DIR="$PREFIX/bin"
    log "Detected Termux. Installing to $INSTALL_DIR"
else
    INSTALL_DIR="$HOME/.local/bin"
    log "Detected standard Linux/VPS. Installing to $INSTALL_DIR"
fi

mkdir -p "$INSTALL_DIR"

# --- Download script utama ---
SCRIPT_PATH="$INSTALL_DIR/cf"
REPO_URL="https://raw.githubusercontent.com/Nizwarax/cf-cli/main/cf.py"

log "Downloading cf.py..."
if ! curl -sSL "$REPO_URL" -o "$SCRIPT_PATH"; then
    error "Failed to download cf.py. Check your internet or URL."
fi

# --- Tambahkan shebang jika belum ada ---
if ! head -n1 "$SCRIPT_PATH" | grep -q "^#!"; then
    sed -i '1i#!/usr/bin/env python3' "$SCRIPT_PATH"
fi

# --- Jadikan executable ---
chmod +x "$SCRIPT_PATH"

# --- Setup PATH (jika diperlukan) ---
if [[ "$IS_TERMUX" == false ]]; then
    # Di VPS/Linux non-Termux
    if [[ ":$PATH:" != *":$INSTALL_DIR:"* ]]; then
        log "Adding $INSTALL_DIR to PATH in ~/.bashrc"
        echo "export PATH=\"\$PATH:$INSTALL_DIR\"" >> ~/.bashrc
        export PATH="$PATH:$INSTALL_DIR"
    fi
else
    # Termux: $PREFIX/bin sudah otomatis di PATH
    log "Termux: $INSTALL_DIR is already in PATH"
fi

# --- Selesai ---
log "Installation complete!"
echo
echo "You can now run the tool by typing:"
echo
echo "    cf"
echo
if [[ "$IS_TERMUX" == false ]]; then
    echo "If 'cf' is not found, restart your shell or run: source ~/.bashrc"
fi
