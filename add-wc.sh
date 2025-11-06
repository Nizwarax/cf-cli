#!/bin/bash
clear
TELEGRAM_USER_ID=$1
ZONE_ID=$2
SUBDOMAIN_CHOICE_LABEL=$3

DOMAIN_LIST_FILE="/root/botcf/domain.txt"

log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [LOG] $1" >&2
}

USER_DATA_FILE="/root/botcf/user_data/${TELEGRAM_USER_ID}.json"

if [ ! -f "$USER_DATA_FILE" ]; then
    echo "Error: File data pengguna ($USER_DATA_FILE) tidak ditemukan. Pastikan Anda sudah login melalui bot." >&2
    exit 1
fi

AUTH_EMAIL=$(jq -r '.email' "$USER_DATA_FILE")
AUTH_KEY=$(jq -r '.api_key' "$USER_DATA_FILE")
ACCOUNT_ID=$(jq -r '.account_id' "$USER_DATA_FILE")
DOMAIN_UTAMA=$(jq -r '.domains[] | select(.zone_id == "'"$ZONE_ID"'") | .name' "$USER_DATA_FILE" | head -n 1) 

if [ -z "$AUTH_EMAIL" ] || [ -z "$AUTH_KEY" ] || [ -z "$ACCOUNT_ID" ] || [ -z "$ZONE_ID" ] || [ -z "$DOMAIN_UTAMA" ]; then
    echo "Error: Kredensial Cloudflare tidak lengkap atau domain utama tidak ditemukan di data Anda. Coba login ulang." >&2
    exit 1
fi

FULL_SUBDOMAIN="${SUBDOMAIN_CHOICE_LABEL}.${DOMAIN_UTAMA}"

WORKER_NAME="${SUBDOMAIN_CHOICE_LABEL//./-}-${DOMAIN_UTAMA//./-}-worker-${TELEGRAM_USER_ID}" 

WILDCARD_CNAME_NAME="*.${FULL_SUBDOMAIN}" 

log_message "Mulai proses konfigurasi untuk subdomain: ${FULL_SUBDOMAIN}"
log_message "Worker Name: ${WORKER_NAME}"
log_message "Wildcard CNAME Name: ${WILDCARD_CNAME_NAME}"
log_message "ZONE_ID yang digunakan: ${ZONE_ID}"
log_message "Account ID yang digunakan: ${ACCOUNT_ID}"
log_message "Domain Utama: ${DOMAIN_UTAMA}"


call_cf_api() {
    local method=$1
    local url=$2
    local data=$3
    local content_type=${4:-application/json}
    local output_file="/tmp/api_response_$(uuidgen | head -c 8).json"
    local attempt=1
    local max_attempts=3
    local sleep_time=5

    while [ $attempt -le $max_attempts ]; do
        local http_code=$(curl -s -w "%{http_code}" -o "$output_file" -X "$method" "$url" \
            -H "X-Auth-Email: $AUTH_EMAIL" \
            -H "X-Auth-Key: $AUTH_KEY" \
            -H "Content-Type: $content_type" \
            ${data:+-d "$data"})

        if [ "$http_code" -eq 200 ] && jq -e '.success == true' "$output_file" >/dev/null 2>&1; then
            cat "$output_file"
            rm -f "$output_file"
            return 0
        elif [ "$http_code" -eq 429 ]; then
            log_message "Rate limit tercapai (429) untuk $url. Menunggu ${sleep_time}s... (percobaan $attempt/$max_attempts)"
            sleep "$sleep_time"
            attempt=$((attempt + 1))
            sleep_time=$((sleep_time * 2))
        else
            local error_msg=$(jq -r '.errors[]?.message // "Unknown API error"' "$output_file")
            log_message "Cloudflare API Error (HTTP $http_code) for $url: $error_msg. Full response: $(cat "$output_file" 2>/dev/null)"
            echo "❌ Cloudflare API Error (HTTP $http_code): $error_msg" >&2
            rm -f "$output_file"
            return 1
        fi
    done

    log_message "Gagal setelah $max_attempts percobaan akibat rate limit untuk $url."
    echo "❌ Gagal karena rate limit berulang. Harap tunggu sebentar lalu coba lagi." >&2
    return 1
}

get_dns_record_id() {
    local record_name=$1
    local record_type=$2
    local response=$(call_cf_api "GET" "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/dns_records?name=${record_name}&type=${record_type}")
    if [ $? -eq 0 ]; then
        echo "$response" | jq -r '.result[0].id'
    else
        echo ""
    fi
}

get_worker_custom_domain_id() {
    local hostname=$1
    local response=$(call_cf_api "GET" "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/workers/domains?hostname=${hostname}")
    if [ $? -eq 0 ]; then
        echo "$response" | jq -r '.result[]? | select(.hostname == "'"$hostname"'" and .service == "'"$WORKER_NAME"'") | .id'
    else
        echo ""
    fi
}

disable_worker_dev_domain() {
    log_message "Mencoba menonaktifkan domain bawaan *.workers.dev untuk worker: ${WORKER_NAME}"
    local response=$(call_cf_api "GET" "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/workers/domains?worker_name=${WORKER_NAME}")
    if [ $? -eq 0 ]; then
        local worker_dev_domain_id=$(echo "$response" | jq -r '.result[]? | select(.hostname | endswith(".workers.dev")) | .id')
        if [ -n "$worker_dev_domain_id" ]; then
            log_message "Menemukan domain *.workers.dev with ID: ${worker_dev_domain_id}. Mencoba menghapus..."
            if call_cf_api "DELETE" "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/workers/domains/${worker_dev_domain_id}"; then
                echo "✅ Workers.dev dinonaktifkan."
            else
                echo "❌ Gagal menonaktifkan Workers.dev. Cek log." >&2
            fi
        else
            echo "ℹ️ Tidak ada domain *.workers.dev yang ditemukan untuk worker '${WORKER_NAME}'. Mungkin sudah dinonaktifkan."
        fi
    else
        echo "❌ Gagal mendapatkan daftar Workers.dev untuk dinonaktifkan." >&2
    fi
}


check_worker_exists() {
    local worker_check_url="https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/workers/scripts/${WORKER_NAME}"
    local response=$(curl -s -o /dev/null -w "%{http_code}" -H "X-Auth-Email: $AUTH_EMAIL" -H "X-Auth-Key: $AUTH_KEY" "$worker_check_url")
    if [ "$response" -eq 200 ]; then
        return 0
    else
        return 1
    fi
}

get_any_worker_custom_domain_id() {
    local hostname=$1
    local response=$(call_cf_api "GET" "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/workers/domains?hostname=${hostname}")
    if [ $? -eq 0 ]; then
        echo "$response" | jq -r '.result[]? | select(.hostname == "'"$hostname"'") | .id'
    else
        echo ""
    fi
}

delete_all_worker_custom_domains() {
    log_message "Mulai menghapus semua custom domain yang terhubung ke worker '${WORKER_NAME}'."
    local worker_domains_url="https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/workers/domains?worker_name=$WORKER_NAME"
    local response=$(call_cf_api "GET" "$worker_domains_url")

    if [ $? -eq 0 ]; then
        local domain_ids=$(echo "$response" | jq -r '.result[] | .id')
        if [ -z "$domain_ids" ]; then
            echo "ℹ️ Tidak ada custom domain yang terhubung ke worker '${WORKER_NAME}' untuk dihapus."
            log_message "Tidak ada custom domain terhubung ke worker ${WORKER_NAME} untuk dihapus."
            return 0
        fi

        local delete_count=0
        local failed_count=0
        echo "⚠️ Menghapus custom domain yang sudah ada untuk worker '${WORKER_NAME}'..."
        while IFS= read -r domain_id; do
            if [ -z "$domain_id" ]; then continue; fi 
            log_message "Mencoba menghapus custom domain ID: ${domain_id}"
            if call_cf_api "DELETE" "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/workers/domains/${domain_id}"; then
                delete_count=$((delete_count + 1))
            else
                failed_count=$((failed_count + 1))
            fi 
            sleep 1
        done <<< "$domain_ids"
        echo "✅ Berhasil menghapus ${delete_count} custom domain lama. Gagal: ${failed_count}."
        log_message "Selesai menghapus custom domain for worker ${WORKER_NAME}. Berhasil: ${delete_count}, Gagal: ${failed_count}."
    else
        echo "❌ Gagal mendapatkan daftar custom domain for worker '${WORKER_NAME}' untuk dihapus. Cek log." >&2
    fi 
}


check_dependencies() {
    local deps=("curl" "jq")
    for dep in "${deps[@]}"; do
        if ! command -v "$dep" &> /dev/null; then
            echo "Error: $dep tidak ditemukan. Menginstal..." >&2
            sudo apt-get update && sudo apt-get install -y "$dep"
            log_message "Menginstal dependensi: $dep"
        fi
    done
}

# backup_config() dan cleanup_temp_files() dihapus karena lebih cocok di skrip interaktif atau jika diperlukan logging file
# secara ekstensif, atau bisa ditambahkan jika Anda mau. Untuk bot non-interaktif, ini jarang langsung diperlukan.


# --- UTAMA: Jalankan Proses Konfigurasi Sesuai Urutan Yang Diminta ---

check_dependencies

# Langkah 1: Buat worker sesuai nama yang diinginkan.
echo "Mulai Langkah 1: Worker konfigurasi."
log_message "Langkah 1: Membuat/Memverifikasi Worker '${WORKER_NAME}'."

if ! check_worker_exists; then
    echo "⚠️ Worker tidak ditemukan. Membuat..."
    log_message "Worker '${WORKER_NAME}' tidak ditemukan. Mencoba membuatnya."

WORKER_SCRIPT_CONTENT=$(cat <<EOF
addEventListener('fetch', event => {
  event.respondWith(handleRequest(event.request))
})

async function handleRequest(request) {
  let url = new URL(request.url);
  url.hostname = "${FULL_SUBDOMAIN}";
  let newRequest = new Request(url, request);
  return fetch(newRequest);
}
EOF
)
log_message "Menggunakan hardcoded worker script."

    WORKER_URL="https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/workers/scripts/${WORKER_NAME}"
    if call_cf_api "PUT" "$WORKER_URL" "$WORKER_SCRIPT_CONTENT" "application/javascript"; then
        echo "✅ Worker dikonfigurasi."
        log_message "Worker '${WORKER_NAME}' berhasil dibuat/diperbarui."
    else
        echo "❌ Gagal konfigurasi Worker. Proses dibatalkan." >&2
        exit 1
    fi
    sleep 1
else
    echo "ℹ️ Worker sudah ada. Melanjutkan."
    log_message "Worker '${WORKER_NAME}' sudah ada. Melanjutkan konfigurasi."
fi

disable_worker_dev_domain
sleep 1

# Langkah 2: Pointing custom domain worker 'sg.awokawok.biz.id' (FULL_SUBDOMAIN)
#           dan kemudian tambahkan domain dari file (domain.txt)
echo "Mulai Langkah 2: Custom domain worker konfigurasi."
log_message "Langkah 2: Menambahkan Custom Domain Worker untuk ${FULL_SUBDOMAIN} dan domain.txt."

log_message "Mencoba menambahkan custom domain worker: ${FULL_SUBDOMAIN}"

WORKER_ROOT_DOMAIN_DATA=$(cat <<EOF
{
    "hostname": "${FULL_SUBDOMAIN}",
    "zone_id": "${ZONE_ID}",
    "service": "${WORKER_NAME}",
    "environment": "production"
}
EOF
)
WORKER_DOMAINS_API_URL="https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/workers/domains/records"

EXISTING_FULL_SUBDOMAIN_WORKER_ID=$(get_worker_custom_domain_id "${FULL_SUBDOMAIN}")
ANY_EXISTING_FULL_SUBDOMAIN_ID=$(get_any_worker_custom_domain_id "${FULL_SUBDOMAIN}")

if [ -n "$EXISTING_FULL_SUBDOMAIN_WORKER_ID" ]; then
    echo "ℹ️ Custom domain '${FULL_SUBDOMAIN}' sudah terhubung."
else
    if [ -n "$ANY_EXISTING_FULL_SUBDOMAIN_ID" ]; then
        echo "⚠️ Custom domain '${FULL_SUBDOMAIN}' ada, pindah." >&2
        log_message "Custom domain '${FULL_SUBDOMAIN}' ada (ID: ${ANY_EXISTING_FULL_SUBDOMAIN_ID}), mencoba menghapus untuk dipindahkan."
        if call_cf_api "DELETE" "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/workers/domains/${ANY_EXISTING_FULL_SUBDOMAIN_ID}"; then
            echo "✅ Lama dihapus. Menambahkan ulang..."
            sleep 1
            log_message "Payload JSON untuk custom domain '${FULL_SUBDOMAIN}' (setelah hapus): ${WORKER_ROOT_DOMAIN_DATA}"
            if call_cf_api "PUT" "$WORKER_DOMAINS_API_URL" "$WORKER_ROOT_DOMAIN_DATA"; then
                echo "✅ Custom domain '${FULL_SUBDOMAIN}' dikonfigurasi."
            else
                echo "❌ Gagal konfigurasi setelah hapus. Cek log." >&2
            fi
        else
            echo "❌ Gagal hapus lama. Cek log." >&2
        fi
    else
        log_message "Payload JSON untuk custom domain '${FULL_SUBDOMAIN}': ${WORKER_ROOT_DOMAIN_DATA}"
        if call_cf_api "PUT" "$WORKER_DOMAINS_API_URL" "$WORKER_ROOT_DOMAIN_DATA"; then
            echo "✅ Custom domain '${FULL_SUBDOMAIN}' dikonfigurasi."
        else
            echo "❌ Gagal konfigurasi. Cek log." >&2
        fi
    fi
fi
sleep 1

if [ -f "$DOMAIN_LIST_FILE" ]; then
    log_message "Mulai menambahkan custom domain worker dari ${DOMAIN_LIST_FILE}."
    echo "--- Menambahkan Custom Domain Worker dari file ---"

    while IFS= read -r host_entry; do
        host_entry=$(echo "$host_entry" | sed 's/\r$//')
        if [ -z "$host_entry" ] || [[ "$host_entry" =~ ^# ]]; then
            continue
        fi

        if [[ "$host_entry" == http* ]]; then
            echo "Peringatan: '${host_entry}' di file adalah URL, dilewati." >&2
            log_message "Peringatan: '${host_entry}' di ${DOMAIN_LIST_FILE} adalah URL bukan hostname, dilewati."
            continue
        fi

        CURRENT_CUSTOM_DOMAIN="${host_entry}.${SUBDOMAIN_CHOICE_LABEL}.${DOMAIN_UTAMA}"
        
        if [[ "$CURRENT_CUSTOM_DOMAIN" =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]]; then
            echo "Peringatan: '${CURRENT_CUSTOM_DOMAIN}' (gabungan) adalah IP, dilewati." >&2
            log_message "Peringatan: '${CURRENT_CUSTOM_DOMAIN}' (setelah digabungkan) adalah IP, dilewati."
            continue
        fi

        log_message "Memproses custom domain yang digabungkan: ${CURRENT_CUSTOM_DOMAIN}"

        TARGET_ZONE_ID_FOR_MERGED_DOMAIN="${ZONE_ID}"

        CUSTOM_DOMAIN_DATA=$(cat <<EOF
{
    "hostname": "${CURRENT_CUSTOM_DOMAIN}",
    "zone_id": "${TARGET_ZONE_ID_FOR_MERGED_DOMAIN}",
    "service": "${WORKER_NAME}",
    "environment": "production"
}
EOF
)
        
        EXISTING_CUSTOM_DOMAIN_ID=$(get_worker_custom_domain_id "${CURRENT_CUSTOM_DOMAIN}")
        ANY_EXISTING_CUSTOM_DOMAIN_ID=$(get_any_worker_custom_domain_id "${CURRENT_CUSTOM_DOMAIN}")

        if [ -n "$EXISTING_CUSTOM_DOMAIN_ID" ]; then
            echo "ℹ️ Custom domain '${CURRENT_CUSTOM_DOMAIN}' sudah terhubung."
            log_message "Custom domain worker '${CURRENT_CUSTOM_DOMAIN}' sudah terhubung."
        else
            if [ -n "$ANY_EXISTING_CUSTOM_DOMAIN_ID" ]; then
                echo "⚠️ Custom domain '${CURRENT_CUSTOM_DOMAIN}' ada, pindah." >&2
                log_message "Custom domain worker '${CURRENT_CUSTOM_DOMAIN}' sudah ada (ID: ${ANY_EXISTING_CUSTOM_DOMAIN_ID}), mencoba menghapus untuk dipindahkan."
                if call_cf_api "DELETE" "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/workers/domains/${ANY_EXISTING_CUSTOM_DOMAIN_ID}"; then
                    echo "✅ Lama dihapus. Menambahkan ulang..."
                    sleep 1
                    log_message "Payload JSON untuk custom domain '${CURRENT_CUSTOM_DOMAIN}' (setelah hapus): ${CUSTOM_DOMAIN_DATA}"
                    if call_cf_api "PUT" "$WORKER_DOMAINS_API_URL" "$CUSTOM_DOMAIN_DATA"; then
                        echo "✅ Custom domain '${CURRENT_CUSTOM_DOMAIN}' dikonfigurasi."
                    else
                        echo "❌ Gagal konfigurasi setelah hapus. Cek log." >&2
                    fi
                else
                    echo "❌ Gagal hapus lama. Cek log." >&2
                fi
            else
                log_message "Payload JSON untuk custom domain '${CURRENT_CUSTOM_DOMAIN}': ${CUSTOM_DOMAIN_DATA}"
                if call_cf_api "PUT" "$WORKER_DOMAINS_API_URL" "$CUSTOM_DOMAIN_DATA"; then
                    echo "✅ Custom domain '${CURRENT_CUSTOM_DOMAIN}' dikonfigurasi."
                else
                    echo "❌ Gagal konfigurasi. Cek log." >&2
                fi
            fi
        fi
        sleep 1
    done < "$DOMAIN_LIST_FILE"
    echo "--- Penambahan Custom Domain Worker dari file selesai. ---"
else
    echo "Peringatan: File domain.txt tidak ditemukan. Tidak ada custom domain worker massal ditambahkan." >&2
    log_message "Peringatan: File ${DOMAIN_LIST_FILE} tidak ditemukan. Tidak ada custom domain worker massal yang ditambahkan."
fi


echo "Mulai Langkah 3: Menghapus Custom Domain Worker."
log_message "Langkah 3: Menghapus Custom Domain Worker."
delete_all_worker_custom_domains
sleep 1

echo "Mulai Langkah 4: Menambahkan DNS CNAME Record '${WILDCARD_CNAME_NAME}'."
log_message "Langkah 4: Menambahkan DNS CNAME Record '${WILDCARD_CNAME_NAME}'."
CNAME_RECORD_ID=$(get_dns_record_id "${WILDCARD_CNAME_NAME}" "CNAME")
if [ -n "$CNAME_RECORD_ID" ]; then
    echo "ℹ️ CNAME '${WILDCARD_CNAME_NAME}' sudah ada. (Langkah 4)"
else
    CNAME_RECORD_DATA='{"type":"CNAME","name":"'${WILDCARD_CNAME_NAME}'","content":"'${FULL_SUBDOMAIN}'","ttl":1,"proxied":true}'
    CNAME_RECORD_URL="https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/dns_records"
    if call_cf_api "POST" "$CNAME_RECORD_URL" "$CNAME_RECORD_DATA"; then
        echo "✅ CNAME '${WILDCARD_CNAME_NAME}' dikonfigurasi. (Langkah 4)"
    else
        echo "❌ Gagal konfigurasi CNAME. Cek log. (Langkah 4)" >&2
    fi
fi
sleep 1


echo "🎉 Proses konfigurasi selesai!"
log_message "Proses konfigurasi selesai."