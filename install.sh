#!/usr/bin/env bash

set -e  # Hentikan jika ada error

BOLD="\033[1m"
GREEN="\033[0;32m"
BLUE="\033[0;34m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
NC="\033[0m"  # No Color

info()  { echo -e "${BLUE}[*]${NC} $1"; }
warn()  { echo -e "${YELLOW}[!]${NC} $1"; }
good()  { echo -e "${GREEN}[✓]${NC} $1"; }
error() { echo -e "${RED}[✗]${NC} $1"; }

# === Deteksi lingkungan ===
if [ -n "$TERMUX_VERSION" ]; then
    IS_TERMUX=true
    BIN_DIR="$HOME/bin"
    VENV_DIR="$HOME/.cf-venv"
else
    IS_TERMUX=false
    BIN_DIR="$HOME/.local/bin"
    VENV_DIR="$HOME/.cf-venv"
fi

# === Pastikan direktori tujuan ada ===
mkdir -p "$BIN_DIR"

# === Cek dependensi dasar ===
info "Checking required tools..."
for cmd in curl python3; do
    if ! command -v "$cmd" &> /dev/null; then
        error "Required command '$cmd' not found. Please install it first."
        exit 1
    fi
done

# === Cek atau buat virtual environment ===
if [ ! -d "$VENV_DIR" ]; then
    info "Creating virtual environment at $VENV_DIR..."
    python3 -m venv "$VENV_DIR" || {
        error "Failed to create virtual environment. Make sure 'python3-venv' is installed."
        if [ "$IS_TERMUX" = false ]; then
            warn "On Debian/Ubuntu, run: sudo apt install python3-venv"
            warn "On CentOS/RHEL, run: sudo yum install python3-pip && python3 -m ensurepip"
        fi
        exit 1
    }
fi

# === Aktifkan venv secara sementara untuk instalasi ===
info "Installing/upgrading Python dependencies..."
"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/python" -m pip install requests

# === Unduh cf.py ===
info "Downloading cf.py from GitHub..."
CF_SCRIPT_URL="https://raw.githubusercontent.com/Nizwarax/cf-cli/main/cf.py"
CF_LOCAL="$BIN_DIR/cf"

curl -sSL "$CF_SCRIPT_URL" -o "$CF_LOCAL" || {
    error "Failed to download cf.py"
    exit 1
}

chmod +x "$CF_LOCAL"

# === Buat wrapper shell (opsional tapi lebih bersih) ===
cat > "$BIN_DIR/cf" << EOF
#!/usr/bin/env bash
exec "$VENV_DIR/bin/python" "$BIN_DIR/cf.py" "\$@"
EOF
chmod +x "$BIN_DIR/cf"

# === Tambahkan ke PATH (jika belum) ===
PROFILE=""
if [ "$IS_TERMUX" = true ]; then
    PROFILE="$HOME/.bashrc"
else
    if [ -f "$HOME/.bashrc" ]; then
        PROFILE="$HOME/.bashrc"
    elif [ -f "$HOME/.profile" ]; then
        PROFILE="$HOME/.profile"
    else
        PROFILE="$HOME/.bashrc"
        touch "$PROFILE"
    fi
fi

# Tambahkan ke PATH hanya jika belum ada
if ! grep -q "$BIN_DIR" "$PROFILE" 2>/dev/null; then
    info "Adding $BIN_DIR to PATH in $PROFILE"
    echo "export PATH=\"\$PATH:$BIN_DIR\"" >> "$PROFILE"
fi

# === Selesai ===
good "Installation complete!"

if [[ ":$PATH:" == *":$BIN_DIR:"* ]]; then
    good "You can now run: cf"
else
    warn "To use 'cf' immediately, run:"
    echo "    source \"$PROFILE\""
    echo ""
    warn "Or restart your shell."
fi

good "Note: This tool runs in an isolated virtual environment for safety."
