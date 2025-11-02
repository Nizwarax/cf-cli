#!/usr/bin/env python3

import os
import json
import subprocess
import requests
import time

# =========================
# Warna ANSI & Formatting
# =========================
C = {
    "HITAM": "\033[30m",
    "MERAH": "\033[31m",
    "HIJAU": "\033[32m",
    "KUNING": "\033[33m",
    "BIRU": "\033[34m",
    "UNGU": "\033[35m",
    "CYAN": "\033[36m",
    "PUTIH": "\033[37m",
    "BOLD": "\033[1m",
    "UNDERLINE": "\033[4m",
    "RESET": "\033[0m"
}

def c(text, color):
    text = str(text) if not isinstance(text, str) else text
    if not color:
        return text
    colors = color.split('+')
    ansi_codes = []
    for c_name in colors:
        if c_name in C:
            ansi_codes.append(C[c_name])
        else:
            print(f"{C['MERAH']}⚠️ Warna '{c_name}' tidak dikenal.{C['RESET']}")
    return ''.join(ansi_codes) + text + C['RESET']

# =========================
# Animasi Loading
# =========================
def loading(msg, duration=0.5):
    for char in ['|', '/', '-', '\\']:
        print(f"\r{msg} {char}  ", end="", flush=True)
        time.sleep(duration / 4)
    print(f"\r{msg} {c('✅', 'HIJAU')}", end="", flush=True)
    time.sleep(0.5)
    print()

# =========================
# ASCII Logo
# =========================
def format_date(date_str):
    if not date_str:
        return "N/A"
    try:
        from datetime import datetime
        # API dapat mengembalikan format dengan atau tanpa mikrodetik
        # Coba format dengan mikrodetik terlebih dahulu
        try:
            dt_obj = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S.%fZ")
        except ValueError:
            # Jika gagal, coba format tanpa mikrodetik
            dt_obj = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ")
        return dt_obj.strftime("%d %B %Y")
    except (ValueError, ImportError):
        # Jika kedua upaya parsing gagal, kembalikan string asli
        return date_str

def show_logo():
    logo = (
        f"{c('╔══════════════════════════════════╗', 'BIRU')}\n"
        f"{c('║', 'BIRU')}{' ' * 4}{c('🔐 CLOUDFLARE MANAGER CLI', 'BOLD+CYAN')}{' ' * 5}{c('║', 'BIRU')}\n"
        f"{c('║', 'BIRU')}{' ' * 7}{c('Author: Deki_niswara', 'UNGU')}{' ' * 7}{c('║', 'BIRU')}\n"
        f"{c('╚══════════════════════════════════╝', 'BIRU')}"
    )
    print(logo)

def clear_screen():
    """Membersihkan layar terminal."""
    os.system('cls' if os.name == 'nt' else 'clear')

# =========================
# Konfigurasi
# =========================
API_BASE = "https://api.cloudflare.com/client/v4"
CONFIG_FILE = os.path.expanduser("~/.cloudflare-manager-cli.json")

# =========================
# Manajemen Akun
# =========================
def load_accounts():
    if os.path.isfile(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}

def save_accounts(accounts):
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, 'w') as f:
        json.dump(accounts, f, indent=2)

# =========================
# Penanganan Error API
# =========================
def handle_api_error(response):
    if not response.get("success"):
        errors = response.get("errors", [])
        for error in errors:
            if error.get("code") == 6003:
                print(f"{c('❌ Gagal:', 'MERAH')} {c('Header permintaan tidak valid.', 'KUNING')}")
                print(f"{c('   Pastikan API Token atau API Key Anda benar dan memiliki izin yang diperlukan.', 'KUNING')}")
                return
        # Fallback for other errors
        print(f"{c('❌ Gagal:', 'MERAH')} {response.get('raw', 'Respons tidak diketahui')[:100]}...")

# =========================
# Cloudflare API Wrapper
# =========================
class CloudflareAPI:
    def __init__(self, email=None, api_key=None, api_token=None):
        self.email = email
        self.api_key = api_key
        self.api_token = api_token

    def _headers(self):
        h = {"Content-Type": "application/json"}
        if self.api_token:
            h["Authorization"] = f"Bearer {self.api_token}"
        else:
            h["X-Auth-Email"] = self.email or ""
            h["X-Auth-Key"] = self.api_key or ""
        return h

    def _req(self, method, path, **kwargs):
        url = f"{API_BASE}{path}"
        try:
            r = requests.request(method, url, headers=self._headers(), timeout=60, **kwargs)
        except requests.RequestException as e:
            data = {"success": False, "errors": [{"message": f"HTTP error: {e}"}], "status_code": None, "raw": None}
            handle_api_error(data)
            return data
        try:
            data = r.json()
        except Exception:
            data = {"success": False, "errors": [{"message": "Non-JSON response"}]}
        data["status_code"] = r.status_code
        data["raw"] = r.text
        if not data.get("success"):
            handle_api_error(data)
        return data

    def list_zones(self): return self._req("GET", "/zones")
    def add_domain(self, domain): return self._req("POST", "/zones", json={"name": domain, "jump_start": True})
    def get_zone_id(self, domain):
        zones = self.list_zones()
        for z in zones.get("result", []) if zones.get("result") else []:
            if z.get("name") == domain:
                return z.get("id")
        return None
    def delete_zone(self, zone_id): return self._req("DELETE", f"/zones/{zone_id}")
    def list_dns_records(self, zone_id): return self._req("GET", f"/zones/{zone_id}/dns_records")
    def add_dns_record(self, zone_id, record_type, name, content, ttl=120, proxied=False):
        payload = {"type": record_type, "name": name, "content": content, "ttl": ttl, "proxied": proxied}
        return self._req("POST", f"/zones/{zone_id}/dns_records", json=payload)
    def delete_dns_record(self, zone_id, record_id): return self._req("DELETE", f"/zones/{zone_id}/dns_records/{record_id}")
    def update_dns_record(self, zone_id, record_id, record_type, name, content, ttl=120, proxied=False):
        payload = {"type": record_type, "name": name, "content": content, "ttl": ttl, "proxied": proxied}
        return self._req("PUT", f"/zones/{zone_id}/dns_records/{record_id}", json=payload)
    def get_edge_certificates(self, zone_id): return self._req("GET", f"/zones/{zone_id}/ssl/certificate_packs")
    def get_total_tls(self, zone_id): return self._req("GET", f"/zones/{zone_id}/acm/total_tls")
    def set_total_tls(self, zone_id, enabled=True, certificate_authority="google", validity_period=None):
        payload = {"enabled": bool(enabled), "certificate_authority": certificate_authority}
        if validity_period is not None:
            payload["validity_period"] = int(validity_period)
        return self._req("POST", f"/zones/{zone_id}/acm/total_tls", data=json.dumps(payload))
    def list_origin_ca_certs(self, zone_id, page=1, per_page=50):
        params = {"zone_id": zone_id, "page": page, "per_page": per_page}
        return self._req("GET", "/certificates", params=params)
    def get_origin_ca_cert(self, certificate_id): return self._req("GET", f"/certificates/{certificate_id}")

# =========================
# Cek Total TLS
# =========================
def total_tls_available(cf: CloudflareAPI, zone_id: str):
    resp = cf.get_total_tls(zone_id)
    if resp.get("success"):
        return True, resp
    errs = resp.get("errors") or []
    if resp.get("status_code") == 401 and any(e.get("code") == 1450 for e in errs):
        return False, resp
    return True, resp

# =========================
# Zone Manager (Lengkap)
# =========================
def manage_zone(cf: CloudflareAPI, zone: dict):
    zone_id = zone["id"]
    zone_name = zone["name"]
    ttl_available, _ = total_tls_available(cf, zone_id)

    while True:
        clear_screen()
        show_logo()
        print(f"\n{c('⚙️  ZONE MANAGER:', 'BIRU')} {c(zone_name.upper(), 'BOLD+PUTIH')}")
        print(f"{c('─' * 50, 'BIRU')}")
        print(f"{c('1', 'HIJAU')}. 🔍 Lihat DNS Record")
        print(f"{c('2', 'HIJAU')}. ➕ Tambah DNS Record")
        print(f"{c('3', 'HIJAU')}. ❌ Hapus DNS Record")
        print(f"{c('4', 'HIJAU')}. ✏️  Update DNS Record")
        print(f"{c('5', 'CYAN')}. 🛡️  Lihat Semua Edge Certificates")
        print(f"{c('6', 'CYAN')}. ✅ Lihat Edge Certificates (AKTIF)")
        if ttl_available:
            print(f"{c('7', 'MERAH')}. 🔐 Total TLS - Lihat Status")
            print(f"{c('8', 'MERAH')}. 🔐 Total TLS - Enable (pilih CA)")
            print(f"{c('9', 'MERAH')}. 🔐 Total TLS - Disable")
            next_base = 10
        else:
            print(f"{c('7', 'MERAH')} ⚠️  (Total TLS tidak tersedia — butuh ACM)")
            next_base = 8
        print(f"{c(next_base, 'KUNING')}. 🪪 Origin CA - Daftar Sertifikat")
        print(f"{c(next_base+1, 'KUNING')}. 💾 Origin CA - Ambil & Simpan Sertifikat (PEM)")
        print(f"{c('0', 'MERAH')}. 🔙 Kembali")
        p = input(f"\n{c('→ Pilih: ', 'CYAN')}").strip()

        if p == "1":
            clear_screen()
            show_logo()
            resp = cf.list_dns_records(zone_id)
            if resp.get("success"):
                print(f"\n{c('=== DNS RECORDS ===', 'BOLD+HIJAU')}")
                for r in resp.get("result", []):
                    proxied = "cloudflare" if r.get("proxied", False) else "dns only"
                    color = "MERAH" if proxied == "cloudflare" else "HIJAU"
                    print(f"  {c(r['type'], 'KUNING')} {c(r['name'], 'PUTIH')} → {c(r['content'], 'CYAN')} [{c(proxied, color)}]")
                input(f"\n{c('Tekan ENTER untuk kembali...', 'KUNING')}")

        elif p == "2":
            rtype = input(f"{c('→ Tipe (A/CNAME/TXT): ', 'HIJAU')}").strip().upper()
            name = input(f"{c('→ Nama (www): ', 'HIJAU')}").strip()
            content = input(f"{c('→ Konten (IP): ', 'HIJAU')}").strip()
            proxied = input(f"{c('→ Aktifkan proxy (y/n)? ', 'KUNING')}").strip().lower() == "y"
            res = cf.add_dns_record(zone_id, rtype, name, content, proxied=proxied)
            if res.get("success"):
                print(f"{c('✅ Berhasil ditambahkan!', 'HIJAU')}")

        elif p == "3":
            rid = input(f"{c('→ ID record: ', 'MERAH')}").strip()
            res = cf.delete_dns_record(zone_id, rid)
            if res.get("success"):
                print(f"{c('🗑️ Record dihapus.', 'HIJAU')}")

        elif p == "4":
            rid = input(f"{c('→ ID record: ', 'HIJAU')}").strip()
            rtype = input(f"{c('→ Tipe baru: ', 'HIJAU')}").strip().upper()
            name = input(f"{c('→ Nama baru: ', 'HIJAU')}").strip()
            content = input(f"{c('→ Konten baru: ', 'HIJAU')}").strip()
            proxied = input(f"{c('→ Aktifkan proxy (y/n)? ', 'KUNING')}").strip().lower() == "y"
            res = cf.update_dns_record(zone_id, rid, rtype, name, content, proxied=proxied)
            if res.get("success"):
                print(f"{c('✏️ Diperbarui!', 'HIJAU')}")

        elif p == "5":
            clear_screen()
            show_logo()
            packs = cf.get_edge_certificates(zone_id)
            if packs.get("success"):
                print(f"\n{c('=== EDGE CERTIFICATES ===', 'BOLD+CYAN')}")
                for cert in packs.get("result", []):
                    print(f"Type   : {cert.get('type', 'N/A')}")
                    print(f"Status : {cert.get('status', 'N/A')}")
                    print(f"Hosts  : {', '.join(cert.get('hosts', []))}")
                    print(f"Issued : {format_date(cert.get('issued_on'))}")
                    print(f"Expire : {format_date(cert.get('expires_on'))}")
                    print(f"{'─' * 40}")
                input(f"\n{c('Tekan ENTER untuk kembali...', 'KUNING')}")

        elif p == "6":
            clear_screen()
            show_logo()
            packs = cf.get_edge_certificates(zone_id)
            if packs.get("success"):
                print(f"\n{c('=== EDGE CERTIFICATES (AKTIF) ===', 'BOLD+CYAN')}")
                found = False
                for cert in packs.get("result", []):
                    if cert.get("status") == "active":
                        found = True
                        print(f"Type   : {cert.get('type', 'N/A')}")
                        print(f"Hosts  : {', '.join(cert.get('hosts', []))}")
                        print(f"Expire : {format_date(cert.get('expires_on'))}")
                        print(f"{'─' * 40}")
                if not found:
                    print(f"{c('Belum ada sertifikat aktif.', 'KUNING')}")
                input(f"\n{c('Tekan ENTER untuk kembali...', 'KUNING')}")

        elif ttl_available and p == "7":
            clear_screen()
            show_logo()
            data = cf.get_total_tls(zone_id)
            if data.get("success"):
                result = data.get("result", {})
                enabled = result.get("enabled", False)
                status = result.get("status", "N/A")
                status_text = c("AKTIF", "HIJAU") if enabled else c("NONAKTIF", "MERAH")
                print(f"\n{c('=== STATUS TOTAL TLS ===', 'BOLD+CYAN')}")
                print(f"  {c('Status:', 'PUTIH')} {status_text}")
                print(f"  {c('Detail:', 'PUTIH')} {status if status else 'Tidak ada detail status'}")
            else:
                print(f"{c('Gagal mengambil status Total TLS.', 'MERAH')}")
            input(f"\n{c('Tekan ENTER untuk kembali...', 'KUNING')}")

        elif ttl_available and p == "8":
            ca = input(f"{c('→ CA (google/lets_encrypt/ssl_com) [google]: ', 'HIJAU')}").strip() or "google"
            vp = input(f"{c('→ Masa aktif (hari, kosong=90): ', 'KUNING')}").strip()
            vp_int = int(vp) if vp.isdigit() else None
            resp = cf.set_total_tls(zone_id, enabled=True, certificate_authority=ca, validity_period=vp_int)
            print(f"{c('Status:', 'CYAN')} {resp.get('status_code')}")
            print(json.dumps(resp, indent=2))
            if any(e.get("code") == 1450 for e in (resp.get("errors") or [])):
                print(f"\n{c('⚠️ Total TLS butuh Advanced Certificate Manager (ACM)', 'MERAH')}")

        elif ttl_available and p == "9":
            resp = cf.set_total_tls(zone_id, enabled=False)
            print(f"{c('Status:', 'CYAN')} {resp.get('status_code')}")
            print(json.dumps(resp, indent=2))

        elif p == str(next_base):
            clear_screen()
            show_logo()
            resp = cf.list_origin_ca_certs(zone_id)
            if resp.get("success"):
                result = resp.get("result", [])
                print(f"\n{c('=== ORIGIN CA CERTIFICATES ===', 'BOLD+KUNING')}")
                if not result:
                    print(f"{c('(Kosong) — belum ada sertifikat.', 'KUNING')}")
                else:
                    for cert in result:
                        print(f"- {c('ID:', 'CYAN')} {cert.get('id', 'N/A')}")
                        print(f"  {c('Hosts:', 'HIJAU')} {', '.join(cert.get('hostnames', []))}")
                        print(f"  {c('Validity:', 'KUNING')} {cert.get('requested_validity')} hari")
                        print(f"  {c('Expire:', 'MERAH')} {format_date(cert.get('expires_on', 'N/A'))}")
                input(f"\n{c('Tekan ENTER untuk kembali...', 'KUNING')}")

        elif p == str(next_base + 1):
            cert_id = input(f"{c('→ Masukkan certificate_id: ', 'KUNING')}").strip()
            if not cert_id:
                print(f"{c('❌ ID tidak boleh kosong.', 'MERAH')}")
                continue
            out_dir = os.path.join("origin_ca", zone_name)
            os.makedirs(out_dir, exist_ok=True)
            pem_path = os.path.join(out_dir, f"{cert_id}.pem")
            resp = cf.get_origin_ca_cert(cert_id)
            if resp.get("success"):
                cert_pem = (resp.get("result") or {}).get("certificate")
            if not cert_pem:
                print(f"{c('❌ Tidak ada sertifikat dalam respons.', 'MERAH')}")
            else:
                with open(pem_path, "w") as f:
                    f.write(cert_pem)
                print(f"\n{c('✅ Tersimpan:', 'HIJAU')} {pem_path}")
                print(f"{c('ℹ️ Private key tidak bisa diambil ulang.', 'KUNING')}")

        elif p == "0":
            break
        else:
            print(f"{c('⚠️ Pilihan tidak valid.', 'KUNING')}")

# =========================
# Main Menu
# =========================
def main_menu(cf: CloudflareAPI):
    while True:
        clear_screen()
        show_logo()
        print(f"\n{c('≡', 'BIRU')} {c('MENU UTAMA', 'BOLD+BIRU')}")
        print(f"{c('────────────────────────────', 'BIRU')}")
        print(f"{c('1', 'HIJAU')}. 🌐 Daftar Domain")
        print(f"{c('2', 'HIJAU')}. ➕ Tambah Domain")
        print(f"{c('3', 'HIJAU')}. ❌ Hapus Domain")
        print(f"{c('4', 'KUNING')}. 🔐 Ganti Akun")
        print(f"{c('0', 'MERAH')}. 🚪 Keluar")
        p = input(f"\n{c('→ Pilih opsi (0-4): ', 'CYAN')}").strip()

        if p == "1":
            print(f"\n{c('↻ Mengambil daftar domain...', 'KUNING')}")
            loading("Menghubungkan ke Cloudflare", 0.8)
            zones_resp = cf.list_zones()
            if zones_resp.get("success"):
                zones = zones_resp.get("result", [])
            if not zones:
                print(f"{c('📭 Tidak ada domain.', 'KUNING')}")
                continue
            print(f"\n{c('=== DAFTAR DOMAIN ===', 'BOLD+HIJAU')}")
            for i, z in enumerate(zones, 1):
                name = z.get("name")
                status = (z.get("status") or "UNKNOWN").upper()
                plan = (z.get("plan") or {}).get("name", "Free")
                icon = "🟢" if status == "ACTIVE" else "🟠"
                print(f" {c(str(i), 'CYAN')}. {icon} {c(name, 'BOLD')} | {c(plan, 'KUNING')}")
            idx = input(f"\n{c('→ Pilih domain (0=batal): ', 'CYAN')}").strip()
            if idx.isdigit() and 1 <= int(idx) <= len(zones):
                manage_zone(cf, zones[int(idx)-1])

        elif p == "2":
            domain = input(f"{c('→ Nama domain: ', 'HIJAU')}").strip()
            res = cf.add_domain(domain)
            if res.get("success"):
                print(f"{c('✅ Berhasil ditambahkan!', 'HIJAU')}")
                result = res.get("result", {})
                name_servers = result.get("name_servers", [])
                if name_servers:
                    print(f"\n{c('ℹ️ Silakan ganti nameserver domain Anda ke:', 'KUNING')}")
                    for ns in name_servers:
                        print(f"  - {c(ns, 'CYAN')}")
                    input(f"\n{c('Tekan ENTER untuk melanjutkan...', 'KUNING')}")

        elif p == "3":
            domain = input(f"{c('→ Nama domain: ', 'MERAH')}").strip()
            zid = cf.get_zone_id(domain)
            if not zid:
                print(f"{c('❌ Tidak ditemukan.', 'MERAH')}")
                continue
            if input(f"{c('⚠️ Ketik HAPUS untuk konfirmasi: ', 'KUNING')}").strip() == "HAPUS":
                res = cf.delete_zone(zid)
                if res.get("success"):
                    print(f"{c('🗑️ Dihapus.', 'HIJAU')}")

        elif p == "4":
            return

        elif p == "0":
            print(f"\n{c('👋 Sampai jumpa!', 'HIJAU')}")
            break
        else:
            print(f"{c('⚠️ Tidak valid.', 'KUNING')}")

def main():
    show_logo()
    total_accounts = 0
    total_domains = 0

    accounts = load_accounts()
    if accounts:
        total_accounts = len(accounts)
        print(f"{c('Mengambil statistik global...', 'KUNING')}")
        for acc_name, acc_data in accounts.items():
            print(f"  {c(f'Menghitung domain di akun {acc_name}...', 'KUNING')}")
            cf = CloudflareAPI(email=acc_data.get("email"), api_key=acc_data.get("api_key"), api_token=acc_data.get("api_token"))
            zones_resp = cf.list_zones()
            if zones_resp.get("success"):
                total_domains += len(zones_resp.get("result", []))
            else:
                print(f"  {c(f'Tidak dapat mengambil domain untuk akun {acc_name}.', 'MERAH')}")

    print(f"\n✨ {c('Selamat Datang!', 'BOLD+KUNING')} ✨\n")
    print(f"{c('Statistik Global (Semua Akun):', 'BOLD+HIJAU')}")
    print(f"  - 🔑 {c('Total Akun Tersimpan', 'CYAN')}\t: {total_accounts}")
    print(f"  - 🌐 {c('Total Domain Terkelola', 'CYAN')}\t: {total_domains}")

    input(f"\n{c('? Tekan ENTER untuk memulai...', 'KUNING')}")

    while True:
        accounts = load_accounts()
        clear_screen()
        show_logo()
        print(f"\n{c('👥', 'CYAN')} {c('PILIH AKUN CLOUDFLARE', 'BOLD+CYAN')}")
        print(f"{c('──────────────────────────', 'BIRU')}")

        if not accounts:
            print(f"{c('📭 Belum ada akun tersimpan.', 'KUNING')}")
        else:
            acc_list = list(accounts.keys())
            for i, name in enumerate(acc_list, 1):
                print(f"{c(i, 'HIJAU')}. {c(name, 'BOLD')}")

        print(f"\n{c('a', 'HIJAU')}. ➕ Tambah Akun Baru")
        if accounts:
            print(f"{c('d', 'MERAH')}. ❌ Hapus Akun")
        print(f"{c('0', 'MERAH')}. 🚪 Keluar")

        choice = input(f"\n{c('→ Pilih (0, a, d, atau nomor): ', 'CYAN')}").strip().lower()

        if choice.isdigit() and 1 <= int(choice) <= len(accounts):
            acc_name = acc_list[int(choice) - 1]
            acc_data = accounts[acc_name]
            cf = CloudflareAPI(email=acc_data.get("email"), api_key=acc_data.get("api_key"), api_token=acc_data.get("api_token"))
            main_menu(cf)
        elif choice == 'a':
            add_account()
        elif choice == 'd' and accounts:
            delete_account()
        elif choice == '0':
            print(f"\n{c('👋 Sampai jumpa!', 'HIJAU')}")
            break
        else:
            print(f"{c('⚠️ Pilihan tidak valid.', 'KUNING')}")

def add_account():
    accounts = load_accounts()
    name = input(f"{c('→ Nama unik untuk akun ini: ', 'KUNING')}").strip()
    if not name:
        print(f"{c('❌ Nama tidak boleh kosong.', 'MERAH')}")
        return
    if name in accounts:
        print(f"{c('❌ Akun dengan nama ini sudah ada.', 'MERAH')}")
        return

    mode = input(f"{c('→ Pakai API Token? (y/n) [y]: ', 'HIJAU')}").strip().lower() or "y"
    new_acc = {}
    if mode == 'y':
        token = input(f"{c('→ Masukkan API Token: ', 'HIJAU')}").strip()
        if not token:
            print(f"{c('❌ Token tidak boleh kosong.', 'MERAH')}")
            return
        new_acc = {"api_token": token}
    else:
        email = input(f"{c('→ Email: ', 'HIJAU')}").strip()
        key = input(f"{c('→ API Key: ', 'HIJAU')}").strip()
        if not email or not key:
            print(f"{c('❌ Email dan API Key wajib.', 'MERAH')}")
            return
        new_acc = {"email": email, "api_key": key}

    accounts[name] = new_acc
    save_accounts(accounts)
    print(f"\n{c('✅ Akun', 'HIJAU')} {c(name, 'BOLD')} {c('berhasil ditambahkan!', 'HIJAU')}")

def delete_account():
    accounts = load_accounts()
    acc_list = list(accounts.keys())

    for i, name in enumerate(acc_list, 1):
        print(f"{c(i, 'HIJAU')}. {c(name, 'BOLD')}")

    idx_str = input(f"\n{c('→ Pilih nomor akun yang akan dihapus (0=batal): ', 'MERAH')}").strip()

    if idx_str.isdigit():
        idx = int(idx_str)
        if 1 <= idx <= len(acc_list):
            acc_name = acc_list[idx - 1]
            confirm = input(f"{c(f'⚠️ Ketik HAPUS untuk menghapus akun {acc_name}: ', 'KUNING')}").strip()
            if confirm == "HAPUS":
                del accounts[acc_name]
                save_accounts(accounts)
                print(f"\n{c('🗑️ Akun', 'HIJAU')} {c(acc_name, 'BOLD')} {c('telah dihapus.', 'HIJAU')}")
            else:
                print(f"{c(' Dibatalkan.', 'KUNING')}")
        elif idx != 0:
            print(f"{c('⚠️ Nomor tidak valid.', 'KUNING')}")
    else:
        print(f"{c('⚠️ Masukkan harus berupa nomor.', 'KUNING')}")

if __name__ == "__main__":
    main()
