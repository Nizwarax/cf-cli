#!/bin/bash

# Pastikan script dijalankan dengan hak akses root (sudo)
if [[ $EUID -ne 0 ]]; then
   echo "This script must be run as root"
   exit 1
fi



# 1. Cek dependensi: python3 dan pip3
echo "Checking dependencies..."
if ! command -v python3 &> /dev/null; then
    echo "python3 could not be found, please install it first."
    exit 1
fi

if ! command -v pip3 &> /dev/null; then
    echo "pip3 could not be found, please install it first."
    exit 1
fi

# 2. Install library 'requests' menggunakan pip3
echo "Installing required Python libraries..."
pip3 install requests

# 3. Download the main script from GitHub
REPO_URL="https://raw.githubusercontent.com/username/repo/main/cf.py"
INSTALL_DIR="/usr/local/bin"
SCRIPT_PATH="$INSTALL_DIR/cf"

echo "Downloading the main script to $SCRIPT_PATH..."
curl -sSL "$REPO_URL" -o "$SCRIPT_PATH"

# 4. Jadikan cf executable
echo "Making the script executable..."
chmod +x "$SCRIPT_PATH"

echo "Installation complete!"
echo "You can now run the script by typing 'cf' in your terminal."
