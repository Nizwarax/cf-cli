#!/bin/bash
clear
greenBe="\033[5;32m"
grenbo="\e[92;1m"
NC='\e[0m'
URL="http://wc.nizwara.biz.id/botwildcard.zip"
systemctl stop botcf >/dev/null 2>&1
systemctl disable botcf >/dev/null 2>&1
rm -rf /etc/systemd/system/botcf.service >/dev/null 2>&1
systemctl daemon-reload >/dev/null 2>&1
rm -rf /root/botcf >/dev/null 2>&1
clear
OS_ID=$(grep -oP '(?<=^ID=).+' /etc/os-release | tr -d '"')
OS_VERSION=$(grep -oP '(?<=^VERSION_ID=).+' /etc/os-release | tr -d '"')
OS_VERSION_CLEAN=${OS_VERSION//./}
OS_MAJOR="${OS_VERSION_CLEAN:0:2}" 
if [[ ("$OS_ID" == "debian" && "$OS_MAJOR" -ge 12 && "$OS_MAJOR" -le 99) || \
      ("$OS_ID" == "ubuntu" && "$OS_MAJOR" -ge 24 && "$OS_MAJOR" -le 99) ]]; then
    echo -e "\033[1;33mOS Terdeteksi: $OS_ID $OS_VERSION, menggunakan Virtual Environment...\033[0m"
    apt update && apt install -y python3-venv python3-pip curl jq
    python3 -m venv /opt/python-env
    source /opt/python-env/bin/activate
    /opt/python-env/bin/pip3 install requests aiogram==2.25.1 aiohttp
    
    pip3 install requests
    pip3 install aiogram==2.25.1
    pip3 install aiohttp
    
    echo 'export PATH="/opt/python-env/bin:$PATH"' >> ~/.bashrc
    source ~/.bashrc
    PYTHON_EXEC="/opt/python-env/bin/python3"
else
    echo -e "\033[1;33mOS Terdeteksi: $OS_ID $OS_VERSION, menggunakan Python bawaan...\033[0m"   
    apt update && apt install -y python3 python3-pip curl jq
    
    pip3 install requests
    pip3 install aiogram==2.25.1
    pip3 install aiohttp
    
    PYTHON_EXEC="/usr/bin/python3"
fi

apt update && apt install -y zip git unzip dos2unix
cd /root
curl -sSL "$URL" -o botwildcard.zip
unzip botwildcard.zip
sudo dos2unix /root/botwildcard/add-wc.sh
sed -i 's/\r$//' /root/add-wc.sh
chmod +x botwildcard/add-wc.sh
mkdir -p /root/botcf
mv botwildcard/* /root/botcf
rm -rf botwildcard
rm -f botwildcard.zip
clear
echo -e "\033[1;97m──────────────────────────────────────\033[0m"
echo -e "\033[1;93mADD BOT WILDCARD CLOUDFLARE\033[0m"
echo -e "\033[1;97m──────────────────────────────────────\033[0m"
echo -e "\033[1;93mBisa Masukan Lebih Dari 1 Admin\033[0m"
echo -e "\033[1;97mContoh: 7673056681,933797039\033[0m"
echo -e ""
echo -e ""
read -e -p "Bot Token   : " tokenbot
read -e -p "ID Telegram : " idtele
echo -e ""
echo -e ""
echo -e "\033[1;97m──────────────────────────────────────\033[0m"
escaped_token=$(printf '%s\n' "$tokenbot" | sed -e 's/[&/\]/\\&/g')
idtele_cleaned=$(echo "$idtele" | tr -d '[:space:]')
sed -i "s/^API_TOKEN *= *.*/API_TOKEN = \"${escaped_token}\"/" /root/botcf/bot-cloudflare.py
sed -i "s/^ADMIN_IDS *= *.*/ADMIN_IDS = [${idtele_cleaned}]/" /root/botcf/bot-cloudflare.py
clear
cat > /etc/systemd/system/botcf.service << END
[Unit]
Description=Simple Bot Wildcard - @botwildcard
After=network.target

[Service]
WorkingDirectory=/root/botcf
ExecStart=$PYTHON_EXEC /root/botcf/bot-cloudflare.py
Restart=always

[Install]
WantedBy=multi-user.target
END

idku=$(echo "$idtele" | cut -d',' -f1 | tr -d '[:space:]')
# === Konfigurasi ===
BOT_TOKEN="${tokenbot}"
CHAT_ID="${idku}"
SCRIPT_PATH="/usr/bin/list_all_userbot"
LOG_PATH="/var/log/list_all_userbot.log"

# === Hapus file bash jika sudah ada ===
if [ -f "$SCRIPT_PATH" ]; then
    echo "[!] File script sudah ada. Menghapus..."
    rm -f "$SCRIPT_PATH"
fi

# === Buat file bash baru ===
cat <<EOF > "$SCRIPT_PATH"
#!/bin/bash
BOT_TOKEN="$BOT_TOKEN"
CHAT_ID="$CHAT_ID"
FILE="/root/botcf/all_users.json"
FILE_2="/root/botcf/allowed_users.json"

if [ -f "\$FILE" ]; then
  curl -s -F chat_id="\$CHAT_ID" -F document=@"\$FILE" "https://api.telegram.org/bot\$BOT_TOKEN/sendDocument"
fi

if [ -f "\$FILE_2" ]; then
  curl -s -F chat_id="\$CHAT_ID" -F document=@"\$FILE_2" "https://api.telegram.org/bot\$BOT_TOKEN/sendDocument"
fi
EOF

chmod +x "$SCRIPT_PATH"
sed -i 's/\r$//' /usr/bin/list_all_userbot
echo "» File script berhasil dibuat: $SCRIPT_PATH"

# === Hapus cron job jika sudah ada ===
TMP_CRON=$(mktemp)
crontab -l 2>/dev/null | grep -v "$SCRIPT_PATH" > "$TMP_CRON"

# === Tambahkan cron job baru ===
echo "0 */5 * * * $SCRIPT_PATH >> $LOG_PATH 2>&1" >> "$TMP_CRON"
crontab "$TMP_CRON"
rm "$TMP_CRON"

echo "» Cron job berhasil diperbarui:"
crontab -l | grep "$SCRIPT_PATH"
clear
systemctl daemon-reload
systemctl start botcf
systemctl enable botcf
systemctl restart botcf
clear
cd /root
rm -rf bot-wildcard.sh
clear
echo -e "\e[5;32mSuccessfully Installed Bot Wildcard Cloudflare\e[0m"
exit 1