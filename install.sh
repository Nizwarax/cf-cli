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

# --- Bersihkan virtual environment jika aktif ---
if [[ -n "$VIRTUAL_ENV" ]]; then
    unset VIRTUAL_ENV
    export PATH=$(echo "$PATH" | sed 's|/.*/\.cf-venv/bin:||g; s|/.*/\.cf-venv/bin||g')
fi

# --- Cek dependensi dasar ---
log "Memeriksa alat yang dibutuhkan..."
for cmd in python3 curl; do
    if ! command -v "$cmd" &> /dev/null; then
        if [[ "$IS_TERMUX" == true ]]; then
            error "$cmd tidak ditemukan. Jalankan: pkg install python curl"
        else
            error "$cmd tidak ditemukan. Silakan instal (misal: apt install python3 curl)."
        fi
    fi
done

# --- Instal/pastikan pip tersedia ---
if ! python3 -m pip --version &> /dev/null; then
    log "Menginstal pip..."
    python3 -m ensurepip --user --upgrade > /dev/null 2>&1
fi

# --- Instal dependensi Python dengan fallback ---
log "Menginstal dependensi Python..."
if command -v pip3 &> /dev/null; then
    pip3 install --user --quiet requests
elif python3 -m pip --version &> /dev/null; then
    python3 -m pip install --user --quiet requests
else
    error "Gagal menginstal 'requests'. Pastikan pip tersedia."
fi

# --- Tentukan lokasi instalasi ---
if [[ "$IS_TERMUX" == true ]]; then
    INSTALL_DIR="$PREFIX/bin"
    log "Terdeteksi Termux. Menginstal ke: ${INSTALL_DIR}"
else
    INSTALL_DIR="$HOME/.local/bin"
    log "Terdeteksi VPS/Linux. Menginstal ke: ${INSTALL_DIR}"
fi

mkdir -p "$INSTALL_DIR"

# --- Unduh cf.py dari GitHub ---
SCRIPT_PATH="$INSTALL_DIR/cf"
REPO_URL="https://raw.githubusercontent.com/Nizwarax/cf-cli/main/cf.py"

log "Mengunduh cf.py dari GitHub..."
if ! curl -sSL "$REPO_URL" -o "$SCRIPT_PATH"; then
    error "Gagal mengunduh cf.py. Periksa koneksi internet Anda."
fi

# --- Tambahkan shebang jika belum ada ---
if ! head -n1 "$SCRIPT_PATH" | grep -q "^#!"; then
    sed -i '1i#!/usr/bin/env python3' "$SCRIPT_PATH"
fi

# --- Jadikan executable ---
chmod +x "$SCRIPT_PATH"

# --- Tambahkan ke PATH (hanya di VPS, via ~/.bashrc) ---
if [[ "$IS_TERMUX" == false ]]; then
    if [[ ":$PATH:" != *":$INSTALL_DIR:"* ]]; then
        if ! grep -q "$INSTALL_DIR" ~/.bashrc 2>/dev/null; then
            echo "export PATH=\"\$PATH:$INSTALL_DIR\"" >> ~/.bashrc
        fi
        export PATH="$PATH:$INSTALL_DIR"
        log "Menambahkan $INSTALL_DIR ke PATH di ~/.bashrc"
    fi
else
    log "Termux: $INSTALL_DIR sudah otomatis di PATH"
fi

# --- Selesai ---
echo
success "Instalasi berhasil!"
echo
echo -e "${GREEN}Anda sekarang dapat menjalankan tool ini dengan mengetik:${RESET}"
echo
echo -e "    ${MAGENTA}cf${RESET}"
echo
if [[ "$IS_TERMUX" == true ]]; then
    echo -e "${CYAN}ℹ️  Di Termux, perintah 'cf' langsung tersedia.${RESET}"
else
    echo -e "${YELLOW}[!]${RESET} Jika 'cf' tidak ditemukan, restart terminal atau jalankan: ${CYAN}source ~/.bashrc${RESET}"
    echo -e "${CYAN}ℹ️  File disimpan di: ${MAGENTA}$SCRIPT_PATH${RESET}"
fi
