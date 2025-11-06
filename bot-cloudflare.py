import logging
import requests
import asyncio
import os
import json
import uuid
import re
from aiogram import types
import subprocess 
from typing import Union
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.dispatcher import FSMContext
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils import executor
from aiogram.utils.callback_data import CallbackData


os.makedirs('user_data', exist_ok=True)
os.chmod('user_data', 0o777) 
os.makedirs('temp_actions', exist_ok=True)
os.chmod('temp_actions', 0o777) 

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

TEMP_DIR = "temp_actions"
DATA_DIR = "user_data" 
DOMAIN_FILE = "/root/botcf/domain.txt" # New constant for the domain file path

CREATE_WILDCARD_SCRIPT = "/root/botcf/add-wc.sh"

ALLOWED_USERS_FILE = "allowed_users.json"
ADMIN_IDS = [7588969672,6687478923,5092269467]

def get_total_users():
    path = "all_users.json"
    if os.path.exists(path):
        try:
            users = json.load(open(path))
            return len(users)
        except:
            return 0
    return 0
    
def load_allowed_users():
    if os.path.exists(ALLOWED_USERS_FILE):
        try:
            with open(ALLOWED_USERS_FILE, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return []
    return []

def save_allowed_users(users):
    with open(ALLOWED_USERS_FILE, "w") as f:
        json.dump(users, f)

def is_user_allowed(user_id: int) -> bool:
    return user_id in load_allowed_users() or user_id in ADMIN_IDS

def save_user_once(user_id: int):
    path = "all_users.json"
    users = []
    if os.path.exists(path):
        try:
            users = json.load(open(path))
        except json.JSONDecodeError:
            pass
    if user_id not in users:
        users.append(user_id)
        json.dump(users, open(path, "w"))    
        
def save_temp_action(uid: int, data: dict) -> str:
    action_id = str(uuid.uuid4())[:6]
    user_dir = os.path.join(TEMP_DIR, str(uid))
    os.makedirs(user_dir, exist_ok=True)
    filepath = os.path.join(user_dir, f"{action_id}.json")
    with open(filepath, 'w') as f: json.dump(data, f)
    return action_id

def load_temp_action(uid: int, action_id: str) -> dict:
    filepath = os.path.join(TEMP_DIR, str(uid), f"{action_id}.json")
    if not os.path.exists(filepath): return None
    with open(filepath, 'r') as f: return json.load(f)

def delete_temp_action(uid: int, action_id: str):
    filepath = os.path.join(TEMP_DIR, str(uid), f"{action_id}.json")
    if os.path.exists(filepath): os.remove(filepath)

def escape_markdown_v2(text: str) -> str:
    reserved_chars = r'[_*[\]()~`>#+\-=|{}.!]'
    return ''.join(f'\\{char}' if char in reserved_chars else char for char in text)

API_TOKEN = "7269560569:AAFuj0XhC0nFihKQCtPM2ffDiij4q5bUHzs"


bot = Bot(token=API_TOKEN, parse_mode=types.ParseMode.MARKDOWN_V2)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

zone_cb = CallbackData("zone", "action", "zone_id", "domain_name")
dns_cb = CallbackData("dns", "action", "zone_id", "dns_id", "subdomain_name")

class MemberManage(StatesGroup):
    waiting_for_add_id = State()
    waiting_for_del_id = State()
    
class AddMember(StatesGroup):
    waiting_for_user_id = State()
    
class BroadcastState(StatesGroup):
    waiting_for_all = State()

class Login(StatesGroup):
    get_email = State()
    get_apikey = State()
    get_name = State() 

class AddSubdomain(StatesGroup):
    get_record_type = State()
    get_name = State()
    get_content = State()
    get_cname_target = State()
    get_cname_proxied_status = State()


class EditDnsRecord(StatesGroup):
    get_record_number = State()
    select_edit_option = State()
    get_new_content = State()
    get_new_proxied_status = State()
    get_new_record_type = State()
    get_new_record_content_for_type_change = State()
    get_new_proxied_status_for_type_change = State()

class CreateWildcard(StatesGroup):
    get_subdomain_choice = State()

class DeleteWildcard(StatesGroup):
    get_subdomain_choice_to_delete = State()

# --- New States for Subdomain File Management ---
class DomainFileManage(StatesGroup):
    waiting_for_subdomain_to_add = State()
    waiting_for_subdomain_to_delete = State()
    waiting_for_confirm_delete_all = State()

def init_storage():
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        os.makedirs(TEMP_DIR, exist_ok=True)
        logger.info(f"Direktori penyimpanan '{DATA_DIR}' dan '{TEMP_DIR}' siap")
    except OSError as e:
        logger.critical(f"Gagal membuat direktori penyimpanan. Pastikan izin benar: {e}")

def get_user_filepath(uid): return os.path.join(DATA_DIR, f"{uid}.json")
def get_user_data(uid):
    fpath = get_user_filepath(uid)
    if not os.path.exists(fpath): return None
    try:
        with open(fpath, 'r') as f: return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        logger.warning(f"File data pengguna {fpath} tidak ditemukan atau rusak")
        return None
    except IOError as e:
        logger.error(f"IOError saat membaca data pengguna {fpath}: {e}")
        return None

def save_user_data(uid, data):
    fpath = get_user_filepath(uid)
    try:
        with open(fpath, 'w') as f: json.dump(data, f, indent=4)
        logger.info(f"Data pengguna {uid} berhasil disimpan ke {fpath}")
    except IOError as e:
        logger.critical(f"CRITICAL ERROR: Gagal menulis data pengguna {uid} ke {fpath}. Pastikan izin direktori '{DATA_DIR}' benar: {e}")

def delete_user_data(uid):
    fpath = get_user_filepath(uid)
    if os.path.exists(fpath):
        try:
            os.remove(fpath)
            logger.info(f"Data pengguna {uid} berhasil dihapus dari {fpath}")
            return True
        except IOError as e:
            logger.critical(f"CRITICAL ERROR: Gagal menghapus data pengguna {uid} dari {fpath}. Pastikan izin benar: {e}")
            return False
    return False

def get_cf_accounts(email: str, api_key: str):
    url = "https://api.cloudflare.com/client/v4/accounts"
    headers = {"X-Auth-Email": email, "X-Auth-Key": api_key, "Content-Type": "application/json"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        return r.json().get("result", [])
    except requests.exceptions.RequestException as e:
        logger.error(f"Cloudflare API error (get_cf_accounts): {e}")
        return None

def get_cf_zones(email: str, api_key: str):
    url = "https://api.cloudflare.com/client/v4/zones"
    headers = {"X-Auth-Email": email, "X-Auth-Key": api_key, "Content-Type": "application/json"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        return r.json().get("result", [])
    except requests.exceptions.RequestException as e:
        logging.error(f"Cloudflare API error (get_cf_zones): {e}")
        return None

def get_cf_dns_records(email: str, api_key: str, zone_id: str):
    """Mengambil daftar DNS record untuk zona tertentu dari Cloudflare"""
    url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records"
    headers = {"X-Auth-Email": email, "X-Auth-Key": api_key, "Content-Type": "application/json"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        return r.json().get("result", [])
    except requests.exceptions.RequestException as e:
        logging.error(f"Cloudflare API error (get_cf_dns_records): {e}")
        return None

def add_cf_dns_record(email: str, api_key: str, zone_id: str, name: str, content: str, record_type="A", proxied=False):
    url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records"
    headers = {"X-Auth-Email": email, "X-Auth-Key": api_key, "Content-Type": "application/json"}
    data = {
        "type": record_type,
        "name": name,
        "content": content,
        "proxied": proxied
    }
    try:
        r = requests.post(url, headers=headers, json=data, timeout=10)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.RequestException as e:
        logging.error(f"Cloudflare API error (add_cf_dns_record): {e}")
        return None

def update_cf_dns_record(email: str, api_key: str, zone_id: str, dns_id: str, name: str, content: str, record_type: str, proxied: bool):
    """Memperbarui DNS record di Cloudflare"""
    url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records/{dns_id}"
    headers = {"X-Auth-Email": email, "X-Auth-Key": api_key, "Content-Type": "application/json"}
    data = {
        "type": record_type,
        "name": name,
        "content": content,
        "proxied": proxied
    }
    try:
        r = requests.put(url, headers=headers, json=data, timeout=10)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.RequestException as e:
        logging.error(f"Cloudflare API error (update_cf_dns_record): {e}")
        return None

def delete_cf_dns_record(email: str, api_key: str, zone_id: str, dns_id: str):
    url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records/{dns_id}"
    headers = {"X-Auth-Email": email, "X-Auth-Key": api_key, "Content-Type": "application/json"}
    try:
        r = requests.delete(url, headers=headers, timeout=10)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.RequestException as e:
        logging.error(f"Cloudflare API error (delete_cf_dns_record): {e}")
        return None

# --- New Functions for Subdomain File Management ---
def read_subdomains():
    if not os.path.exists(DOMAIN_FILE):
        return []
    with open(DOMAIN_FILE, 'r') as f:
        return [line.strip() for line in f if line.strip()]

def write_subdomains(subdomains):
    with open(DOMAIN_FILE, 'w') as f:
        for sub in subdomains:
            f.write(f"{sub}\n")

def add_subdomain_to_file(subdomain: str):
    with open(DOMAIN_FILE, 'a') as f:
        f.write(f"{subdomain}\n")

@dp.callback_query_handler(lambda c: c.data == 'batalkan', state='*')
async def cancel_by_button(cb: types.CallbackQuery, state: FSMContext):
    await state.finish()
    
    await cb.message.delete_reply_markup() 
    await cb.message.answer("❌ Proses telah dibatalkan", reply_markup=create_main_reply_menu(cb.from_user.id))
    
    await cb.answer()

@dp.message_handler(commands=['ping'])
async def ping_command(message: types.Message):
    await message.reply(escape_markdown_v2("🏓 Pong \n✅ Bot aktif dan merespon"))

def create_main_reply_menu(user_id: int):
    is_logged_in = get_user_data(user_id) is not None
    is_admin = user_id in ADMIN_IDS

    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False, row_width=2)

    keyboard.row(KeyboardButton("🔄 Ganti Akun & Logout"), KeyboardButton("🌐 Kelola Domain"))

    if is_logged_in:
        keyboard.row(KeyboardButton("ℹ️ Info & bantuan"), KeyboardButton("📋 List Member"))
    else:
        keyboard.row(
            KeyboardButton("📋 List Member"),
            KeyboardButton("🔑 Login ke Akun"),
            KeyboardButton("ℹ️ Info & bantuan")
        )
        

    if is_admin:
        keyboard.row(
            KeyboardButton("❌ Hapus Member"),
            KeyboardButton("✏️ Tambah Member")
        )
        
        keyboard.row(KeyboardButton("📢 Broadcast"))
        
        # New row for Admin-only subdomain file management
        keyboard.row(KeyboardButton("📁 Kelola File Domain"))

    return keyboard

@dp.callback_query_handler(lambda c: c.data == "ping")
async def callback_ping(cb: types.CallbackQuery):
    await cb.answer()
    await cb.message.edit_text("🏓 Pong\n✅ Bot aktif Dan Merespon")


@dp.callback_query_handler(lambda c: c.data == "about")
async def callback_about(cb: types.CallbackQuery):
    await cb.answer()
    await cb.message.edit_text(
        "📒️ *Informasi Tentang Bot:*\n\n"
        "🤖 Bot Ini Membantu Mu Mengelola DNS Record Di Cloudflare Untuk Keperluan Tunneling Dll\\. 🚀\n\n"
        "📦 *Fitur Bot*:\n"
        "» *Bisa Membuat Wildcard*\\.\n"
        "» *Bisa Edit Type Records Sub Domain*\\.\n"
        "» *Bisa Buat Sub Domain Type CNAME*\\.\n"
        "» *Bisa Atur Status Awan Orange 🟠 ON Atau OFF*\\.\n"
        "» *Bisa Hapus Sub Domain Yang Di Pilih*\\.\n"
        "» *Otomatis Memindai Domain Utama Di Akun CF Kalian*\\.\n"
        "» *Ada Fitur Log Out Akun, Jadi Bisa Gonta Ganti Ke Akun Lain*\\.\n\n"
        "Untuk Sewa Bot Bisa Chat Admin Ganteng @Dark\\_System2x"
    )


@dp.callback_query_handler(lambda c: c.data == "list_member")
async def callback_list_member(cb: types.CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS:
        await cb.answer("❌ Hanya admin", show_alert=True)
        return

    allowed = load_allowed_users()
    if not allowed:
        await cb.message.edit_text("📭 Tidak ada user yang diizinkan")
        return

    result = "📋 Daftar User yang Diizinkan:\n\n"
    for uid in allowed:
        try:
            user = await bot.get_chat(uid)
            username = f"@{user.username}" if user.username else "tanpa username"
            name = escape_markdown_v2(user.first_name)
            uid_str = escape_markdown_v2(str(uid))
            username_escaped = escape_markdown_v2(username)
            result += f"» `{uid_str}` → {username_escaped} → {name}\n"
        except:
            uid_str = escape_markdown_v2(str(uid))
            result += f"» `{uid_str}` → tidak dapat mengambil info\n"

    await cb.message.edit_text(result, parse_mode="MarkdownV2")

@dp.callback_query_handler(lambda c: c.data == "broadcast_all")
async def callback_broadcast_trigger(cb: types.CallbackQuery, state: FSMContext):
    if cb.from_user.id not in ADMIN_IDS:
        await cb.answer("❌ Hanya admin", show_alert=True)
        return

    await cb.answer()
    await cb.message.edit_text("📝 Silakan kirim pesan teks, gambar, dll yang ingin dibroadcast ke semua user")
    await BroadcastState.waiting_for_all.set()    

@dp.message_handler(commands=['start', 'menu'], state='*')
async def start_menu(msg: types.Message, state: FSMContext):
    await state.finish()
    save_user_once(msg.from_user.id)
    total_users = get_total_users()

    user_data = get_user_data(msg.from_user.id)
    username = f"@{msg.from_user.username}" if msg.from_user.username else "(tanpa username)"
    display_name = escape_markdown_v2(
        user_data.get('name', msg.from_user.first_name)
    ) if user_data else escape_markdown_v2(msg.from_user.first_name)
    email = escape_markdown_v2(
        user_data.get('email', 'Belum login')
    ) if user_data else "Belum login"

    text = f"🏷️ Selamat datang {display_name}\n\n"
    text += f"👤 Nama: {display_name}\n"
    text += f"🆔 ID Telegram: `{msg.from_user.id}`\n"
    text += f"🔗 Username: {escape_markdown_v2(username)}\n"
    text += f"📧 Login: `{email}`\n"
    text += f"👥 Total Pengguna: `{total_users}`\n\n"
    text += "🏷️ Silahkan pilih opsi di bawah ini:"

    keyboard = create_main_reply_menu(msg.from_user.id)
    await msg.answer(text, reply_markup=keyboard, parse_mode="MarkdownV2")


@dp.callback_query_handler(lambda c: c.data == 'back_to_main_menu', state='*')
async def back_to_main_menu_cb(cb: types.CallbackQuery, state: FSMContext):
    await state.finish()
    total_users = get_total_users()

    user_data = get_user_data(cb.from_user.id)
    username = f"@{cb.from_user.username}" if cb.from_user.username else "(tanpa username)"
    display_name = escape_markdown_v2(
        user_data.get('name', cb.from_user.first_name)
    ) if user_data else escape_markdown_v2(cb.from_user.first_name)
    email = escape_markdown_v2(
        user_data.get('email', 'Belum login')
    ) if user_data else "Belum login"

    text = f"🏷️ Selamat datang kembali {display_name}\n\n"
    text += f"👤 Nama: {display_name}\n"
    text += f"🆔 ID Telegram: `{cb.from_user.id}`\n"
    text += f"🔗 Username: {escape_markdown_v2(username)}\n"
    text += f"📧 Login: `{email}`\n"
    text += f"👥 Total Pengguna: `{total_users}`\n\n"
    text += "🏷️ Silahkan pilih opsi di bawah ini:"

    keyboard = create_main_reply_menu(cb.from_user.id)
    await cb.message.edit_text(text, parse_mode="MarkdownV2")
    
    await bot.send_message(cb.from_user.id, "Menu Utama:", reply_markup=keyboard)
    await cb.answer()

@dp.callback_query_handler(lambda c: c.data == 'show_help')
async def show_help(cb: types.CallbackQuery):
    help_text = (
        "📒️ *Informasi Tentang Bot:*\n\n"
        "🤖 Bot Ini Membantu Mu Mengelola DNS Record Di Cloudflare Untuk Keperluan Tunneling Dll\\. 🚀\n\n"
        "📦 *Fitur Bot*:\n"
        "» *Bisa Membuat Wildcard*\\.\n"
        "» *Bisa Edit Type Records Sub Domain*\\.\n"
        "» *Bisa Buat Sub Domain Type CNAME*\\.\n"
        "» *Bisa Atur Status Awan Orange 🟠 ON Atau OFF*\\.\n"
        "» *Bisa Hapus Sub Domain Yang Di Pilih*\\.\n"
        "» *Otomatis Memindai Domain Utama Di Akun CF Kalian*\\.\n"
        "» *Ada Fitur Log Out Akun, Jadi Bisa Gonta Ganti Ke Akun Lain*\\.\n\n"
        "Untuk Sewa Bot Bisa Chat Admin Ganteng @Dark\\_System2x" # Dihapus bagian "Pastikan Telah Bergabung Di Channel Dan Grup Admin Terlebih Dahulu Untuk Menggunakan Bot Ini\\."
    )
    keyboard = InlineKeyboardMarkup().add(
        InlineKeyboardButton("⬅️ Kembali ke Menu", callback_data="back_to_main_menu")
    )
    await cb.message.edit_text(help_text, reply_markup=keyboard, parse_mode="MarkdownV2")
    await cb.answer()


@dp.callback_query_handler(lambda c: c.data == "go_to_login")
async def go_to_login(cb: types.CallbackQuery, state: FSMContext):
    if not is_user_allowed(cb.from_user.id):
        await cb.answer("❌ Anda belum diberi izin.", show_alert=True)
        return
        
    await state.finish()
    uid = cb.from_user.id


    if get_user_data(uid):
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(InlineKeyboardButton("🗑️ Ya, Hapus Data & Logout", callback_data="confirm_delete_account"))
        keyboard.add(InlineKeyboardButton("⬅️ Kembali ke Menu", callback_data="back_to_main_menu"))
        await cb.message.edit_text(escape_markdown_v2("⚠️ Silahkan Konfirmasi Penghapusan Data Akun Anda Seperti Email & Api Key Akan Di Hapus Dari Bot:"), reply_markup=keyboard)
    else:
        keyboard = InlineKeyboardMarkup().add(InlineKeyboardButton("❌ Batal", callback_data="back_to_main_menu"))
        await cb.message.edit_text(escape_markdown_v2("🔐 Kirim Email Akun Cloudflare Mu:"), reply_markup=keyboard)
        await Login.get_email.set()
    await cb.answer()

@dp.message_handler(state=Login.get_email)
async def process_email(msg: types.Message, state: FSMContext):
    if not is_user_allowed(msg.from_user.id):
        await msg.answer("❌ Anda belum diberi izin untuk menggunakan bot ini, Silahkan hubungi admin")
        # Tambahkan state.finish() di sini agar tidak melanjutkan ke state berikutnya jika tidak diizinkan
        await state.finish() 
        return
        

    await state.update_data(email=msg.text.strip())
    keyboard = InlineKeyboardMarkup().add(
        InlineKeyboardButton("❌ Batal", callback_data="batalkan")
    )
    await msg.answer(
        escape_markdown_v2("🔑 Kirim Global API Key Cloudflare Mu:"),
        reply_markup=keyboard,
        parse_mode="MarkdownV2"
    )
    await Login.get_apikey.set()

@dp.message_handler(state=Login.get_apikey)
async def process_apikey(msg: types.Message, state: FSMContext):    
    if not is_user_allowed(msg.from_user.id):
        await msg.answer("❌ Anda belum diberi izin untuk menggunakan bot ini")
        await state.finish()
        return
    
    api_key_input = msg.text.strip()
    user_data_state = await state.get_data()
    email = user_data_state['email']
    
    processing_msg = await msg.answer(
        escape_markdown_v2("⏳ Memverifikasi API Key"),
        parse_mode="MarkdownV2"
    )

    zones = get_cf_zones(email, api_key_input)

    if zones is None:
        await processing_msg.edit_text(
            escape_markdown_v2("❌ Gagal login » Cek kembali email & API key mu"),
            parse_mode="MarkdownV2"
        )
        await state.finish()
        await start_menu(msg, state)
    else:
        await state.update_data(api_key=api_key_input)
        keyboard = InlineKeyboardMarkup().add(
            InlineKeyboardButton("❌ Batal", callback_data="batalkan")
        )
        await processing_msg.edit_text(
            escape_markdown_v2("✨ Masukkan Nama Anda untuk bot ini (Contoh: LITE123):"),
            reply_markup=keyboard,
            parse_mode="MarkdownV2"
        )
        await Login.get_name.set()

@dp.message_handler(state=Login.get_name)
async def process_name_input(msg: types.Message, state: FSMContext):
    user_name = msg.text.strip()
    user_data_state = await state.get_data()
    email = user_data_state['email']
    api_key = user_data_state['api_key']

    processing_msg = await msg.answer(escape_markdown_v2("⏳ Mengambil data akun Cloudflare."))

    account_id = None
    zone_id = None
    login_successful = False

    try:
        accounts = get_cf_accounts(email, api_key) 
        if accounts:
            account_id = accounts[0]['id'] 
            logger.info(f"Account ID found: {account_id}")
        else:
            await processing_msg.edit_text(
                escape_markdown_v2("⚠️ Gagal mendapatkan Account ID\\. Pastikan API Key memiliki izin yang cukup\\.")
            )
            await state.finish()
            await start_menu(msg, state)
            return

        zones = get_cf_zones(email, api_key)
        if zones:
            zone_id = zones[0]['id']
            logger.info(f"Zone ID found: {zone_id}")
        else:
            await processing_msg.edit_text(
                escape_markdown_v2("⚠️ Gagal mendapatkan Zone ID\\. Pastikan Anda memiliki domain di Cloudflare\\.")
            )
            await state.finish()
            await start_menu(msg, state)
            return
        
        login_successful = True

    except Exception as e:
        logger.error(f"Terjadi kesalahan tak terduga saat memeriksa Cloudflare: {e}")
        await processing_msg.edit_text(
            f"❌ Login gagal\\. Terjadi kesalahan tak terduga: `{escape_markdown_v2(str(e))}`\n"
            f"Pastikan Email dan Global API Key Anda benar\\."
        )

    if login_successful:
        new_user_data = {
            "email": email,
            "api_key": api_key,
            "account_id": account_id,
            "zone_id": zone_id,
            "name": user_name, 
            "domains": [{"zone_id": z['id'], "name": z['name']} for z in zones] 
        }
        save_user_data(msg.from_user.id, new_user_data)
        
        await processing_msg.edit_text(f"❇️ Berhasil Login sebagai `{escape_markdown_v2(user_name)}`\\. Data akun Anda telah disimpan secara pribadi\\.")
    
    # Pindahkan state.finish() ke sini
    await state.finish()
    await start_menu(msg, state)

@dp.callback_query_handler(lambda c: c.data == 'confirm_delete_account')
async def delete_account(cb: types.CallbackQuery, state: FSMContext):
    delete_user_data(cb.from_user.id)
    await cb.answer(escape_markdown_v2("✅ Data Anda telah dihapus dari bot"), show_alert=True)
    await back_to_main_menu_cb(cb, state) # Perbaikan: panggil fungsi dengan _cb

@dp.callback_query_handler(lambda c: c.data == 'go_to_manage_domains', state='*')
async def go_to_manage_domains(cb: types.CallbackQuery):
    uid = cb.from_user.id

    user_data = get_user_data(uid)
    if not user_data:
        await cb.answer(escape_markdown_v2("❌ Anda belum login"), show_alert=True)
        await cb.message.edit_text(
            escape_markdown_v2("Silahkan login terlebih dahulu"),
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("🔐 Login ke Akun", callback_data="go_to_login"),
                InlineKeyboardButton("⬅️ Kembali ke Menu", callback_data="back_to_main_menu")
            )
        )
        return

    await cb.answer(escape_markdown_v2("⏳ Memindai Domain Utama"))
    
    zones = get_cf_zones(user_data['email'], user_data['api_key'])
    if zones is None:
        await cb.message.edit_text(
            escape_markdown_v2("❌ Gagal mengambil domain dari Cloudflare \\& Silahkan periksa API Key Anda atau coba lagi nanti"),
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("⬅️ Kembali ke Menu", callback_data="back_to_main_menu")
            )
        )
        return

    domain_list = [{"zone_id": z['id'], "name": z['name']} for z in zones]
    user_data['domains'] = domain_list
    save_user_data(uid, user_data)

    keyboard = InlineKeyboardMarkup(row_width=1)
    for domain in domain_list:
        try:
            temp_data = {
                "zone_id": domain['zone_id'],
                "domain_name": domain['name'],
                "action": "select_domain"
            }
            action_id = save_temp_action(uid, temp_data)
            button_text = domain['name']
            if len(button_text) > 58:
                button_text = button_text[:55] + "."
            keyboard.add(InlineKeyboardButton(escape_markdown_v2(button_text), callback_data=f"act:{action_id}"))
        except Exception as e:
            logging.error(f"❌ Gagal membuat tombol domain {domain['name']}: {e}")

    keyboard.add(InlineKeyboardButton("⬅️ Kembali ke Menu", callback_data="back_to_main_menu"))

    await cb.message.edit_text(
        escape_markdown_v2("✅ Silahkan pilih domain yang ingin Anda kelola dari akun Cloudflare Anda:"),
        reply_markup=keyboard
    )

# Bagian ini HARUS DIUBAH untuk menangani alur `AddSubdomain.get_record_type`
@dp.callback_query_handler(lambda c: c.data.startswith("act:"), state='*')
async def handle_temp_action(cb: types.CallbackQuery, state: FSMContext):
    uid = cb.from_user.id

    action_id = cb.data.split(":")[1]

    data = load_temp_action(uid, action_id)
    if not data:
        await cb.answer(escape_markdown_v2("⚠️ Data aksi tidak ditemukan"), show_alert=True)
        await cb.message.edit_text(
            escape_markdown_v2("⚠️ Terjadi kesalahan atau aksi tidak valid atau silahkan mulai dari awal"),
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("⬅️ Kembali ke Menu Utama", callback_data="back_to_main_menu")
            )
        )
        return

    # --- Bagian PENTING: Handle Aksi Wildcard yang Baru Ditambahkan ---
    # Periksa action yang spesifik terlebih dahulu
    if data.get('action') == "create_wildcard_for_sub":
        await create_wildcard_for_sub_handler(cb, state)
        # delete_temp_action sudah dipanggil di dalam handler itu sendiri
        return # Penting untuk return agar tidak jatuh ke else atau elif lainnya
    elif data.get('action') == "delete_wildcard_for_sub":
        # Untuk delete_wildcard_for_sub_handler, kita perlu memastikan datanya ada
        if "zone_id" not in data or "domain_name" not in data or "subdomain_choice" not in data:
            await cb.answer("⚠️ Data aksi wildcard tidak lengkap atau kadaluarsa", show_alert=True)
            await cb.message.edit_text(
                "⚠️ Terjadi kesalahan atau aksi tidak valid. Silahkan mulai dari awal",
                reply_markup=InlineKeyboardMarkup().add(
                    InlineKeyboardButton("⬅️ Kembali ke Menu Utama", callback_data="back_to_main_menu")
                ),
            )
            return
        await delete_wildcard_for_sub_handler(cb, state)
        # delete_temp_action sudah dipanggil di dalam handler itu sendiri
        return # Penting untuk return agar tidak jatuh ke else atau elif lainnya
    # --- AKHIR Bagian PENTING ---

    # Existing actions (akan dijalankan hanya jika action di atas tidak cocok)
    if data.get('action') == "delete_dns":
        user_data = get_user_data(uid)
        if not user_data:
            await cb.answer(escape_markdown_v2("❌ Anda perlu login ulang"), show_alert=True)
            await cb.message.edit_text(
                escape_markdown_v2("❌ Silahkan login terlebih dahulu"),
                reply_markup=InlineKeyboardMarkup().add(
                    InlineKeyboardButton("🔐 Login ke Akun", callback_data="go_to_login"),
                    InlineKeyboardButton("⬅️ Kembali ke Menu", callback_data="back_to_main_menu")
                )
            )
            return

        await cb.message.edit_text(escape_markdown_v2("⏳ Menghapus subdomain"))
        await cb.answer()

        res = delete_cf_dns_record(
            email=user_data.get("email"),
            api_key=user_data.get("api_key"),
            zone_id=data['zone_id'],
            dns_id=data['dns_id']
        )

        if res and res.get("success"):
            await cb.message.edit_text(escape_markdown_v2("✅ Subdomain berhasil dihapus"))
        else:
            error_message = "❌ Gagal menghapus subdomain"
            if res and res.get('errors'):
                first_error = res['errors'][0] if res['errors'] else {}
                error_message = escape_markdown_v2(first_error.get('message', 'error tidak diketahui'))
            elif res is None:
                error_message = escape_markdown_v2("Permintaan ke Cloudflare gagal Silahkan Coba lagi nanti")
            
            await cb.message.edit_text(f"❌ {error_message}")

        delete_temp_action(uid, action_id)
        
        temp_data_back_to_list = {
            "zone_id": data['zone_id'],
            "domain_name": data['domain_name'],
            "action": "list_subs"
        }
        back_to_list_action_id = save_temp_action(uid, temp_data_back_to_list)
        keyboard = InlineKeyboardMarkup().add(InlineKeyboardButton("⬅️ Kembali ke Daftar", callback_data=f"act:{back_to_list_action_id}"))
        await cb.message.edit_reply_markup(reply_markup=keyboard)
        return

    elif data.get('action') == "select_domain":
        await select_zone_action(cb, {"zone_id": data["zone_id"], "domain_name": data["domain_name"]}, state)
        delete_temp_action(uid, action_id)
        return

    elif data.get('action') == "list_subs":
        await list_subdomains(cb, state)
        delete_temp_action(uid, action_id)
        return

    elif data.get('action') == "add_sub_start":
        await choose_record_type(cb, state, data['zone_id'], data['domain_name']) # Memanggil fungsi baru
        delete_temp_action(uid, action_id)
        return

    elif data.get('action') == "edit_sub_start":
        await edit_subdomain_start(cb, state)
        delete_temp_action(uid, action_id)
        return

    elif data.get('action') == "edit_dns_item":
        await state.update_data(
            zone_id=data['zone_id'],
            domain_name=data['domain_name'],
            selected_dns_id=data['dns_id'],
            selected_dns_name=data['dns_name'],
            selected_dns_content=data['dns_content'],
            selected_dns_type=data['dns_type'],
            selected_dns_proxied=data['dns_proxied']
        )

        await show_edit_options_for_record(cb, state)
        await EditDnsRecord.select_edit_option.set() 
        delete_temp_action(uid, action_id)
        await cb.answer()
        return

    await cb.answer(escape_markdown_v2("⚠️ Aksi tidak dikenali"), show_alert=True)
    await cb.message.edit_text(
        escape_markdown_v2("⚠️ Terjadi kesalahan atau aksi tidak valid\\. Silahkan coba kembali"),
        reply_markup=InlineKeyboardMarkup().add(
            InlineKeyboardButton("⬅️ Kembali ke Menu Utama", callback_data="back_to_main_menu")
        )
    )


@dp.callback_query_handler(lambda c: c.data.startswith("act:") and load_temp_action(c.from_user.id, c.data.split(":")[1]) and load_temp_action(c.from_user.id, c.data.split(":")[1]).get('action') == 'select_domain', state='*')
@dp.callback_query_handler(zone_cb.filter(action="select"), state='*')
async def select_zone_action(cb: types.CallbackQuery, callback_data: dict, state: FSMContext):
    uid = cb.from_user.id

    await state.finish()
    
    zone_id = callback_data.get('zone_id')
    domain_name = callback_data.get('domain_name')

    if not zone_id or not domain_name:
        action_id_from_cb = cb.data.split(":")[1]
        data_from_temp = load_temp_action(cb.from_user.id, action_id_from_cb)
        if data_from_temp and data_from_temp.get('action') == 'select_domain':
            zone_id = data_from_temp['zone_id']
            domain_name = data_from_temp['domain_name']
            delete_temp_action(cb.from_user.id, action_id_from_cb)
        else:
            await cb.answer(escape_markdown_v2("⚠️ Kesalahan data domain"), show_alert=True)
            await cb.message.edit_text(escape_markdown_v2("Silahkan pilih opsi:"), reply_markup=create_main_reply_menu(cb.from_user.id))
            return

    keyboard = InlineKeyboardMarkup(row_width=2)
    
    temp_data_add = {
        "zone_id": zone_id,
        "domain_name": domain_name,
        "action": "add_sub_start"
    }
    action_id_add = save_temp_action(uid, temp_data_add)
    keyboard.add(InlineKeyboardButton(escape_markdown_v2("🏷️ Add Subdomain"), callback_data=f"act:{action_id_add}"))

    temp_data_list = {
        "zone_id": zone_id,
        "domain_name": domain_name,
        "action": "list_subs"
    }
    action_id_list = save_temp_action(uid, temp_data_list)
    keyboard.add(InlineKeyboardButton(escape_markdown_v2("✏️ Edit Subdomain"), callback_data=f"act:{action_id_list}"))
        
    keyboard.add(InlineKeyboardButton(escape_markdown_v2("⬅️ Kembali ke Daftar Domain"), callback_data="go_to_manage_domains"))
    
    await cb.message.edit_text(f"⚙️ Menu Pengaturan domain: `{escape_markdown_v2(domain_name)}`", reply_markup=keyboard)
    await cb.answer()

@dp.callback_query_handler(
    lambda c: c.data.startswith("act:")
    and load_temp_action(c.from_user.id, c.data.split(":")[1])
    and load_temp_action(c.from_user.id, c.data.split(":")[1]).get('action') == 'list_subs',
    state='*'
)
async def list_subdomains(cb: types.CallbackQuery, state: FSMContext):
    uid = cb.from_user.id
    
    action_id = cb.data.split(":")[1]
    data = load_temp_action(uid, action_id)
    
    if not data:
        await cb.answer(escape_markdown_v2("⚠️ Data aksi tidak ditemukan"), show_alert=True)
        await cb.message.edit_text(
            escape_markdown_v2("⚠️ Terjadi kesalahan atau aksi tidak valid\\. Silahkan coba lagi"),
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("⬅️ Kembali ke Menu Utama", callback_data="back_to_main_menu")
            )
        )
        return

    delete_temp_action(uid, action_id)

    zone_id = data['zone_id']
    domain_name = data['domain_name']
    user_data = get_user_data(uid)
    
    await cb.answer(escape_markdown_v2("⏳ Memindai Data DNS"))
    records = get_cf_dns_records(user_data['email'], user_data['api_key'], zone_id)
    
    if records is None:
        temp_data_back = {
            "zone_id": zone_id,
            "domain_name": domain_name,
            "action": "select_domain"
        }
        back_action_id = save_temp_action(uid, temp_data_back)
        keyboard = InlineKeyboardMarkup().add(
            InlineKeyboardButton("⬅️ Kembali", callback_data=f"act:{back_action_id}")
        )
        await cb.message.edit_text(
            f"❌ Gagal mengambil DNS record dari Cloudflare untuk `{escape_markdown_v2(domain_name)}`, Silahkan coba lagi nanti",
            reply_markup=keyboard
        )
        return

    keyboard = InlineKeyboardMarkup(row_width=2) # Default ke 2 kolom
    text = f"📄 *Daftar Subdomain Dari* `{escape_markdown_v2(domain_name)}`:\n\n"

    display_records = [r for r in records if r['type'] in ['A', 'AAAA', 'CNAME', 'NS']]

    if not display_records:
        temp_data_back = {
            "zone_id": zone_id,
            "domain_name": domain_name,
            "action": "select_domain"
        }
        back_action_id = save_temp_action(uid, temp_data_back)
        keyboard_empty = InlineKeyboardMarkup().add(
            InlineKeyboardButton("⬅️ Kembali", callback_data=f"act:{back_action_id}")
        )
        await cb.message.edit_text(
            f"ℹ️ Tidak ada DNS record tipe A, AAAA, CNAME, atau NS yang ditemukan untuk `{escape_markdown_v2(domain_name)}`\\.",
            reply_markup=keyboard_empty
        )
        return

    for idx, r in enumerate(display_records):
        proxy_status = ""
        if r['type'] != 'NS':
            proxy_status = "🟠" if r.get('proxied') else "⚪"

        status_text = f" {proxy_status}" if proxy_status else ""

        text += (
            f"`{idx + 1}`\\. `{escape_markdown_v2(r['name'])}`\n"
            f"  `{r['type']}` → `{escape_markdown_v2(r['content'])}`{status_text}\n"
        )

        # Tombol Edit dan Hapus yang sudah ada
        temp_data_edit_item = {
            "zone_id": zone_id,
            "dns_id": r['id'],
            "domain_name": domain_name,
            "dns_name": r['name'],
            "dns_content": r['content'],
            "dns_type": r['type'],
            "dns_proxied": r.get('proxied', False),
            "action": "edit_dns_item"
        }
        action_id_edit_item = save_temp_action(uid, temp_data_edit_item)

        temp_data_delete_item_action = {
            "zone_id": zone_id,
            "dns_id": r['id'],
            "domain_name": domain_name,
            "action": "delete_dns"
        }
        action_id_delete_item_action = save_temp_action(uid, temp_data_delete_item_action)
        
        # Logika penentuan subdomain untuk operasi wildcard
        subdomain_for_wc_ops = ""
        # Jika r['name'] sama dengan domain_name (root domain) atau sudah wildcard (*.sub.domain.com)
        if r['name'] == domain_name: 
            subdomain_for_wc_ops = "" 
        elif r['name'].startswith("*"): 
            subdomain_for_wc_ops = ""
        else: 
            # Jika r['name'] adalah subdomain yang relevan (misal 'vpn.example.com')
            # Ambil hanya bagian subdomain (misal 'vpn')
            subdomain_only = r['name'].replace(f".{domain_name}", "")
            # Validasi lagi, memastikan hanya karakter yang valid untuk subdomain (seperti yang di Bash)
            if re.match(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$", subdomain_only):
                subdomain_for_wc_ops = subdomain_only
            else:
                subdomain_for_wc_ops = "" # Jika tidak valid, jangan tampilkan tombol WC

        row_buttons = [
            InlineKeyboardButton(f"✏️ Edit {idx + 1}", callback_data=f"act:{action_id_edit_item}"),
            InlineKeyboardButton(f"🗑️ Hapus {idx + 1}", callback_data=f"act:{action_id_delete_item_action}")
        ]

        if subdomain_for_wc_ops: # Hanya tambahkan tombol WC jika ini adalah subdomain yang valid & bukan NS record
            temp_data_create_wc = {
                "zone_id": zone_id,
                "domain_name": domain_name,
                "subdomain_choice": subdomain_for_wc_ops,
                "action": "create_wildcard_for_sub"
            }
            action_id_create_wc = save_temp_action(uid, temp_data_create_wc)
            row_buttons.append(InlineKeyboardButton(f"🟠 WC {idx + 1}", callback_data=f"act:{action_id_create_wc}"))
        
        keyboard.row(*row_buttons)

    temp_data_back = {
        "zone_id": zone_id,
        "domain_name": domain_name,
        "action": "select_domain"
    }
    back_action_id = save_temp_action(uid, temp_data_back)
    keyboard.add(InlineKeyboardButton("⬅️ Kembali", callback_data=f"act:{back_action_id}"))

    await cb.message.edit_text(text, reply_markup=keyboard, disable_web_page_preview=True)
    await cb.answer()


@dp.callback_query_handler(
    lambda c: c.data.startswith("act:")
    and load_temp_action(c.from_user.id, c.data.split(":")[1])
    and load_temp_action(c.from_user.id, c.data.split(":")[1]).get("action") == "create_wildcard_for_sub",
    state="*",
)
async def create_wildcard_for_sub_handler(cb: types.CallbackQuery, state: FSMContext):
    async def animate_loading(msg: types.Message, stop_event: asyncio.Event):
        progress_frames = [
            "⏳ Sabar Om",
            "⏳ Om Jangan Om",
            "⏳ Woi Sabar Woi",
            "⏳ Sabarrr Ngentod",
            "⏳ Kenapa Hah Nggk Suka",
            "⏳ Bay Wan Dek",
            "⏳ Aoa Au Ah Ndak Jelas",
            "⏳ Emang Ndak Jelas We",
            "⏳ Sedikit Lagi Coy",
            "⏳ Tinggal Sebentar Lagi Kok",
            "⏳ sedikiiiiiiit Laaaagiiiii",
            "⌛ Tapi Bohong Hanyyuuuuk",
        ]
        i = 0
        while not stop_event.is_set():
            try:
                await msg.edit_text(escape_markdown_v2(progress_frames[i % len(progress_frames)]), parse_mode="MarkdownV2")
                i += 1
                await asyncio.sleep(1.5)
            except:
                break

    uid = cb.from_user.id

    action_id = cb.data.split(":")[1]
    data = load_temp_action(uid, action_id)
    delete_temp_action(uid, action_id)

    if not data or "zone_id" not in data or "domain_name" not in data or "subdomain_choice" not in data:
        await cb.answer("⚠️ Data aksi wildcard tidak lengkap atau kadaluarsa", show_alert=True)
        await cb.message.edit_text(
            "⚠️ Terjadi kesalahan atau aksi tidak valid. Silahkan mulai dari awal",
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("⬅️ Kembali ke Menu Utama", callback_data="back_to_main_menu")
            ),
        )
        return

    zone_id = data["zone_id"]
    domain_name = data["domain_name"]
    full_sub = data["subdomain_choice"]
    sub_label = full_sub[:-len(domain_name)-1] if full_sub.endswith("" + domain_name) else full_sub

    loading_msg = await cb.message.answer(escape_markdown_v2("⏳ Memulai Proses"), parse_mode="MarkdownV2")

    stop_flag = asyncio.Event()
    animation_task = asyncio.create_task(animate_loading(loading_msg, stop_flag))

    try:
        process = await asyncio.create_subprocess_exec(
            "bash",
            CREATE_WILDCARD_SCRIPT,
            str(uid),
            zone_id,
            sub_label,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        stop_flag.set()
        await animation_task

        output = stdout.decode().strip()
        error = stderr.decode().strip()

        if process.returncode == 0:
            text = f"✅ *Wildcard selesai untuk* `{escape_markdown_v2(full_sub)}`\\!\n"
            text += "📄 *Log Output:*\n"
            text += f"```\n{escape_markdown_v2(output)}\n```"
            if error:
                text += f"\n⚠️ *Log Tambahan:*\n```\n{escape_markdown_v2(error)}\n```"
        else:
            text = f"❌ *Gagal membuat wildcard untuk* `{escape_markdown_v2(full_sub)}`\\.\n"
            text += f"```\n{escape_markdown_v2(output)}\n```"
            if error:
                text += f"\n🚨 *Error:*\n```\n{escape_markdown_v2(error)}\n```"

        await loading_msg.edit_text(text, parse_mode="MarkdownV2")

    except Exception as e:
        stop_flag.set()
        await animation_task
        await loading_msg.edit_text(f"❇️ Proses Selesai, Silahkan Lanjut Untuk Buat DNS Record CNAME", parse_mode="MarkdownV2")

    await state.finish()
    back_action_id = save_temp_action(uid, {
        "zone_id": zone_id,
        "domain_name": domain_name,
        "action": "select_domain"
    })
    await cb.message.answer(
        "✅ Proses selesai",
        reply_markup=InlineKeyboardMarkup().add(
            InlineKeyboardButton("⬅️ Kembali ke Menu Domain", callback_data=f"act:{back_action_id}")
        )
    )
    await cb.answer()

# Tambahkan handler untuk delete_wildcard_for_sub
@dp.callback_query_handler(
    lambda c: c.data.startswith("act:")
    and load_temp_action(c.from_user.id, c.data.split(":")[1])
    and load_temp_action(c.from_user.id, c.data.split(":")[1]).get("action") == "delete_wildcard_for_sub",
    state="*",
)
async def delete_wildcard_for_sub_handler(cb: types.CallbackQuery, state: FSMContext):
    async def animate_loading(msg: types.Message, stop_event: asyncio.Event):
        progress_frames = [
            "⏳ Sedang menghapus",
            "⏳ Proses penghapusan...",
            "⏳ Hampir selesai...",
            "⏳ Menunggu konfirmasi...",
        ]
        i = 0
        while not stop_event.is_set():
            try:
                await msg.edit_text(escape_markdown_v2(progress_frames[i % len(progress_frames)]), parse_mode="MarkdownV2")
                i += 1
                await asyncio.sleep(1.5)
            except:
                break

    uid = cb.from_user.id

    action_id = cb.data.split(":")[1]
    data = load_temp_action(uid, action_id)
    delete_temp_action(uid, action_id)

    if not data or "zone_id" not in data or "domain_name" not in data or "subdomain_choice" not in data:
        await cb.answer("⚠️ Data aksi wildcard tidak lengkap atau kadaluarsa", show_alert=True)
        await cb.message.edit_text(
            "⚠️ Terjadi kesalahan atau aksi tidak valid. Silahkan mulai dari awal",
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("⬅️ Kembali ke Menu Utama", callback_data="back_to_main_menu")
            ),
        )
        return

    zone_id = data["zone_id"]
    domain_name = data["domain_name"]
    full_sub = data["subdomain_choice"]
    sub_label = full_sub[:-len(domain_name)-1] if full_sub.endswith("." + domain_name) else full_sub

    loading_msg = await cb.message.answer(escape_markdown_v2("⏳ Memulai Proses Penghapusan Wildcard"), parse_mode="MarkdownV2")

    stop_flag = asyncio.Event()
    animation_task = asyncio.create_task(animate_loading(loading_msg, stop_flag))

    try:
        # Panggil script bash untuk menghapus wildcard
        # Asumsi ada script "/root/botcf/del-wc.sh" untuk penghapusan
        # Jika tidak ada, Anda perlu membuat atau menyesuaikannya
        process = await asyncio.create_subprocess_exec(
            "bash",
            "/root/botcf/del-wc.sh", # Ganti dengan path script penghapusan wildcard Anda
            str(uid),
            zone_id,
            sub_label,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        stop_flag.set()
        await animation_task

        output = stdout.decode().strip()
        error = stderr.decode().strip()

        if process.returncode == 0:
            text = f"✅ *Wildcard berhasil dihapus untuk* `{escape_markdown_v2(full_sub)}`\\!\n"
            text += "📄 *Log Output:*\n"
            text += f"```\n{escape_markdown_v2(output)}\n```"
            if error:
                text += f"\n⚠️ *Log Tambahan:*\n```\n{escape_markdown_v2(error)}\n```"
        else:
            text = f"❌ *Gagal menghapus wildcard untuk* `{escape_markdown_v2(full_sub)}`\\.\n"
            text += f"```\n{escape_markdown_v2(output)}\n```"
            if error:
                text += f"\n🚨 *Error:*\n```\n{escape_markdown_v2(error)}\n```"

        await loading_msg.edit_text(text, parse_mode="MarkdownV2")

    except FileNotFoundError:
        stop_flag.set()
        await animation_task
        await loading_msg.edit_text(
            f"❌ Script penghapusan wildcard tidak ditemukan: `/root/botcf/del-wc.sh`\\. "
            f"Pastikan file tersebut ada dan memiliki izin eksekusi\\.",
            parse_mode="MarkdownV2"
        )
    except Exception as e:
        stop_flag.set()
        await animation_task
        await loading_msg.edit_text(f"❌ Terjadi kesalahan tak terduga saat menghapus wildcard: `{escape_markdown_v2(str(e))}`", parse_mode="MarkdownV2")

    await state.finish()
    back_action_id = save_temp_action(uid, {
        "zone_id": zone_id,
        "domain_name": domain_name,
        "action": "select_domain"
    })
    await cb.message.answer(
        "✅ Proses selesai",
        reply_markup=InlineKeyboardMarkup().add(
            InlineKeyboardButton("⬅️ Kembali ke Menu Domain", callback_data=f"act:{back_action_id}")
        )
    )
    await cb.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("act:") and load_temp_action(c.from_user.id, c.data.split(":")[1]) and load_temp_action(c.from_user.id, c.data.split(":")[1]).get('action') == 'add_sub_start', state='*')
async def add_subdomain_start(cb: types.CallbackQuery, state: FSMContext):
    # Ini adalah handler lama yang sekarang akan menjadi 'router' ke `choose_record_type`
    # Pastikan data yang diperlukan ada sebelum memanggil choose_record_type
    action_id = cb.data.split(":")[1]
    data = load_temp_action(cb.from_user.id, action_id)
    if not data or "zone_id" not in data or "domain_name" not in data:
        await cb.answer(escape_markdown_v2("⚠️ Data aksi tidak lengkap atau kadaluarsa"), show_alert=True)
        await cb.message.edit_text(
            escape_markdown_v2("⚠️ Terjadi kesalahan atau aksi tidak valid\\. Silahkan mulai dari awal"),
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("⬅️ Kembali ke Menu Utama", callback_data="back_to_main_menu")
            )
        )
        return
    await choose_record_type(cb, state, data['zone_id'], data['domain_name'])
    await cb.answer()

# --- Fungsi BARU untuk memilih Tipe Record ---
async def choose_record_type(cb: types.CallbackQuery, state: FSMContext, zone_id: str, domain_name: str):
    await state.update_data(zone_id=zone_id, domain_name=domain_name)

    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("Tipe A (IPv4)", callback_data="add_type_a"),
        InlineKeyboardButton("Tipe CNAME", callback_data="add_type_cname")
    )
    keyboard.add(InlineKeyboardButton("❌ Batal", callback_data="batalkan"))

    await cb.message.edit_text(
        f"📝 Menambahkan subdomain ke `{escape_markdown_v2(domain_name)}`\\.\n\n"
        f"Pilih tipe DNS record yang ingin Anda tambahkan:",
        reply_markup=keyboard,
        parse_mode="MarkdownV2"
    )
    await AddSubdomain.get_record_type.set()
    
# --- Handler untuk Tipe A (Sudah ada, modifikasi sedikit) ---
@dp.callback_query_handler(lambda c: c.data == "add_type_a", state=AddSubdomain.get_record_type)
async def process_add_type_a(cb: types.CallbackQuery, state: FSMContext):
    await state.update_data(record_type="A")
    keyboard = InlineKeyboardMarkup().add(InlineKeyboardButton("❌ Batal", callback_data="batalkan"))
    await cb.message.edit_text(
        f"📝 Anda memilih tipe A\\. Silahkan Input nama subdomain mu dengan contoh sebagai berikut: `sg1`",
        reply_markup=keyboard,
        parse_mode="MarkdownV2"
    )
    await AddSubdomain.get_name.set()
    await cb.answer()

@dp.message_handler(state=AddSubdomain.get_name)
async def process_subdomain_name(msg: types.Message, state: FSMContext):
    subdomain = msg.text.strip()
    await state.update_data(sub_name=subdomain)
    
    data = await state.get_data()
    record_type = data.get('record_type')
    
    keyboard = InlineKeyboardMarkup().add(
        InlineKeyboardButton("❌ Batal", callback_data="batalkan")
    )
    
    if record_type == "A":
        text = (
            f"✅ Nama subdomain: `{escape_markdown_v2(subdomain)}`\n\n"
            f"Silahkan Input IP Address \\(IPv4\\) untuk record A mu dengan contoh sebagai berikut: `8\\.8\\.8\\.8`"
        )
        await msg.answer(text, reply_markup=keyboard, parse_mode="MarkdownV2")
        await AddSubdomain.get_content.set()
    elif record_type == "CNAME":
        text = (
            f"✅ Nama subdomain: `{escape_markdown_v2(subdomain)}`\n\n"
            f"Silahkan Input Target Domain \\(Contoh: `www\\.example\\.com` atau `example\\.com`\\) untuk record CNAME mu:"
        )
        await msg.answer(text, reply_markup=keyboard, parse_mode="MarkdownV2")
        await AddSubdomain.get_cname_target.set() # Set state ke CNAME target
    else:
        await msg.answer(escape_markdown_v2("⚠️ Tipe record tidak valid\\. Silahkan ulangi proses dari awal\\."), parse_mode="MarkdownV2")
        await state.finish()
        await start_menu(msg, state)

# --- Handler untuk Konten Tipe A (sudah ada, perlu diintegrasikan) ---
@dp.message_handler(state=AddSubdomain.get_content)
async def process_add_subdomain_content(msg: types.Message, state: FSMContext):
    content = msg.text.strip()
    data = await state.get_data()
    zone_id = data['zone_id']
    domain_name = data['domain_name']
    sub_name = data['sub_name']
    record_type = data['record_type'] # Harusnya "A"
    
    full_domain_name = f"{sub_name}.{domain_name}" if sub_name != '@' else domain_name

    escaped_full_domain_name = escape_markdown_v2(full_domain_name)
    escaped_content = escape_markdown_v2(content)

    await msg.answer(
        f"⏳ Menambahkan `{escaped_full_domain_name}` \\({record_type}\\) \\-\\> `{escaped_content}`\\.",
        parse_mode="MarkdownV2"
    )

    uid = msg.from_user.id
    user_data = get_user_data(uid)
    
    # Untuk Tipe A, proxied defaultnya False (sesuai fungsi add_cf_dns_record)
    result = add_cf_dns_record(user_data['email'], user_data['api_key'], zone_id, full_domain_name, content, record_type=record_type, proxied=False) 

    await state.finish()

    temp_data_back_to_domain_menu = {
        "zone_id": zone_id,
        "domain_name": domain_name,
        "action": "select_domain"
    }
    back_action_id = save_temp_action(uid, temp_data_back_to_domain_menu)
    keyboard = InlineKeyboardMarkup().add(
        InlineKeyboardButton("⬅️ Kembali ke Menu Domain", callback_data=f"act:{back_action_id}")
    )

    if result and result.get("success"):
        await msg.answer(
            f"✅ Subdomain `{escaped_full_domain_name}` \\({record_type}\\) telah dibuat\\.",
            parse_mode="MarkdownV2",
            reply_markup=keyboard
        )
    else:
        if result and result.get('errors'):
            error_message_from_cf = result.get('errors', [{}])[0].get('message', 'Terjadi kesalahan tidak diketahui')
            error = escape_markdown_v2(error_message_from_cf)
        elif result is None:
            error = "Permintaan ke Cloudflare gagal atau timeout\\."
        else:
            error = "Gagal menambahkan subdomain\\."

        await msg.answer(
            f"❌ *Gagal\\!* Terjadi kesalahan: `{error}`",
            parse_mode="MarkdownV2",
            reply_markup=keyboard
        )

# --- Handler BARU untuk Tipe CNAME ---
@dp.callback_query_handler(lambda c: c.data == "add_type_cname", state=AddSubdomain.get_record_type)
async def process_add_type_cname(cb: types.CallbackQuery, state: FSMContext):
    await state.update_data(record_type="CNAME")
    keyboard = InlineKeyboardMarkup().add(InlineKeyboardButton("❌ Batal", callback_data="batalkan"))
    await cb.message.edit_text(
        f"📝 Anda memilih tipe CNAME\\. Silahkan Input nama subdomain mu dengan contoh sebagai berikut: `www`",
        reply_markup=keyboard,
        parse_mode="MarkdownV2"
    )
    await AddSubdomain.get_name.set() # Re-use get_name for CNAME subdomain name
    await cb.answer()

@dp.message_handler(state=AddSubdomain.get_cname_target)
async def process_cname_target(msg: types.Message, state: FSMContext):
    cname_target = msg.text.strip()
    await state.update_data(cname_target=cname_target)

    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("✅ Aktifkan Proxied", callback_data="cname_proxied_true"),
        InlineKeyboardButton("❌ Nonaktifkan Proxied", callback_data="cname_proxied_false")
    )
    keyboard.add(InlineKeyboardButton("❌ Batal", callback_data="batalkan"))

    await msg.answer(
        f"✅ Target CNAME: `{escape_markdown_v2(cname_target)}`\n\n"
        f"Apakah Anda ingin mengaktifkan proxy \\(Cloudflare CDN\\) untuk CNAME ini?",
        reply_markup=keyboard,
        parse_mode="MarkdownV2"
    )
    await AddSubdomain.get_cname_proxied_status.set()

@dp.callback_query_handler(lambda c: c.data.startswith("cname_proxied_"), state=AddSubdomain.get_cname_proxied_status)
async def process_cname_proxied_status(cb: types.CallbackQuery, state: FSMContext):
    proxied_status = True if cb.data == "cname_proxied_true" else False
    await state.update_data(proxied_status=proxied_status)

    data = await state.get_data()
    zone_id = data['zone_id']
    domain_name = data['domain_name']
    sub_name = data['sub_name']
    cname_target = data['cname_target']
    
    full_domain_name = f"{sub_name}.{domain_name}" if sub_name != '@' else domain_name

    escaped_full_domain_name = escape_markdown_v2(full_domain_name)
    escaped_cname_target = escape_markdown_v2(cname_target)
    proxied_text = "✅ Aktif" if proxied_status else "❌ Nonaktif"
    escaped_proxied_text = escape_markdown_v2(proxied_text)

    await cb.message.edit_text(
        f"⏳ Menambahkan `{escaped_full_domain_name}` \\(CNAME\\) \\-\\> `{escaped_cname_target}` \\(Proxied: {escaped_proxied_text}\\)\\.",
        parse_mode="MarkdownV2"
    )
    await cb.answer()

    uid = cb.from_user.id
    user_data = get_user_data(uid)
    
    result = add_cf_dns_record(user_data['email'], user_data['api_key'], zone_id, full_domain_name, cname_target, record_type="CNAME", proxied=proxied_status)

    await state.finish()

    temp_data_back_to_domain_menu = {
        "zone_id": zone_id,
        "domain_name": domain_name,
        "action": "select_domain"
    }
    back_action_id = save_temp_action(uid, temp_data_back_to_domain_menu)
    keyboard = InlineKeyboardMarkup().add(
        InlineKeyboardButton("⬅️ Kembali ke Menu Domain", callback_data=f"act:{back_action_id}")
    )

    if result and result.get("success"):
        await cb.message.edit_text(
            f"✅ Subdomain `{escaped_full_domain_name}` \\(CNAME\\) telah dibuat\\.",
            parse_mode="MarkdownV2",
            reply_markup=keyboard
        )
    else:
        if result and result.get('errors'):
            error_message_from_cf = result.get('errors', [{}])[0].get('message', 'Terjadi kesalahan tidak diketahui')
            error = escape_markdown_v2(error_message_from_cf)
        elif result is None:
            error = "Permintaan ke Cloudflare gagal atau timeout\\."
        else:
            error = "Gagal menambahkan subdomain\\."

        await cb.message.edit_text(
            f"❌ *Gagal\\!* Terjadi kesalahan: `{error}`",
            parse_mode="MarkdownV2",
            reply_markup=keyboard
        )


@dp.callback_query_handler(lambda c: c.data.startswith("act:") and load_temp_action(c.from_user.id, c.data.split(":")[1]) and load_temp_action(c.from_user.id, c.data.split(":")[1]).get('action') == 'edit_sub_start', state='*')
async def edit_subdomain_start(cb: types.CallbackQuery, state: FSMContext):
    uid = cb.from_user.id

    action_id = cb.data.split(":")[1]
    data = load_temp_action(uid, action_id)

    if not data:
        await cb.answer("⚠️ Data aksi tidak ditemukan", show_alert=True)
        return

    delete_temp_action(uid, action_id)

    zone_id = data['zone_id']
    domain_name = data['domain_name']
    user_data = get_user_data(uid)

    await cb.answer(escape_markdown_v2("⏳ Memindai Data DNS"))
    records = get_cf_dns_records(user_data['email'], user_data['api_key'], zone_id)

    if records is None:
        temp_data_back = {
            "zone_id": zone_id,
            "domain_name": domain_name,
            "action": "select_domain"
        }
        back_action_id = save_temp_action(uid, temp_data_back)
        keyboard = InlineKeyboardMarkup().add(
            InlineKeyboardButton("⬅️ Kembali", callback_data=f"act:{back_action_id}")
        )
        await cb.message.edit_text(
            f"❌ Gagal mengambil DNS record dari Cloudflare untuk `{escape_markdown_v2(domain_name)}`, Silahkan coba lagi nanti",
            reply_markup=keyboard
        )
        return

    display_records = [r for r in records if r['type'] in ['A', 'AAAA', 'CNAME', 'NS']]
    if not display_records:
        temp_data_back = {
            "zone_id": zone_id,
            "domain_name": domain_name,
            "action": "select_domain"
        }
        back_action_id = save_temp_action(uid, temp_data_back)
        keyboard_empty = InlineKeyboardMarkup().add(
            InlineKeyboardButton("⬅️ Kembali", callback_data=f"act:{back_action_id}")
        )
        await cb.message.edit_text(
            f"ℹ️ Tidak ada DNS record tipe A, AAAA, CNAME, atau NS yang dapat diedit untuk `{escape_markdown_v2(domain_name)}`\\.",
            reply_markup=keyboard_empty
        )
        return

    text = f"📄 *Daftar Subdomain Dari* `{escape_markdown_v2(domain_name)}` untuk diedit/dihapus:\n\n"
    keyboard = InlineKeyboardMarkup(row_width=2)

    for idx, r in enumerate(display_records):
        proxy_status = ""
        if r['type'] != 'NS':
            proxy_status = "🟠" if r.get('proxied') else "⚪"

        status_text = f" {proxy_status}" if proxy_status else ""

        text += (
            f"`{idx + 1}`\\. `{escape_markdown_v2(r['name'])}`\n"
            f"  `{r['type']}` → `{escape_markdown_v2(r['content'])}`{status_text}\n"
        )

        temp_data_edit_item = {
            "zone_id": zone_id,
            "dns_id": r['id'],
            "domain_name": domain_name,
            "dns_name": r['name'],
            "dns_content": r['content'],
            "dns_type": r['type'],
            "dns_proxied": r.get('proxied', False),
            "action": "edit_dns_item"
        }
        action_id_edit_item = save_temp_action(uid, temp_data_edit_item)

        temp_data_delete_item_action = {
            "zone_id": zone_id,
            "dns_id": r['id'],
            "domain_name": domain_name,
            "action": "delete_dns"
        }
        action_id_delete_item_action = save_temp_action(uid, temp_data_delete_item_action)

        keyboard.add(
            InlineKeyboardButton(f"✏️ Edit {idx + 1}", callback_data=f"act:{action_id_edit_item}"),
            InlineKeyboardButton(f"🗑️ Hapus {idx + 1}", callback_data=f"act:{action_id_delete_item_action}")
        )

    temp_data_back = {
        "zone_id": zone_id,
        "domain_name": domain_name,
        "action": "select_domain"
    }
    back_action_id = save_temp_action(uid, temp_data_back)
    keyboard.add(InlineKeyboardButton("⬅️ Kembali", callback_data=f"act:{back_action_id}"))

    await cb.message.edit_text(text, reply_markup=keyboard, parse_mode="MarkdownV2", disable_web_page_preview=True)
    await cb.answer()


async def show_edit_options_for_record(cb: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    dns_name = escape_markdown_v2(data['selected_dns_name'])
    dns_content = escape_markdown_v2(data['selected_dns_content'])
    dns_type = escape_markdown_v2(data['selected_dns_type'])
    proxied_status = "✅ Aktif" if data['selected_dns_proxied'] else "❌ Nonaktif"
    escaped_proxied_status = escape_markdown_v2(proxied_status)

    text = (
        f"⚙️ Anda akan mengedit record:\n"
        f"Nama: `{dns_name}`\n"
        f"Tipe: `{dns_type}`\n"
        f"Konten: `{dns_content}`\n"
        f"Proxied: `{escaped_proxied_status}`\n\n"
        f"Pilih apa yang ingin Anda edit:"
    )

    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("✏️ Edit IP Atau Hostname", callback_data="edit_content"),
        InlineKeyboardButton("🔄 Ganti Tipe Record", callback_data="change_record_type")
    )
    if dns_type != 'NS': # NS records cannot be proxied
        keyboard.add(
            InlineKeyboardButton("🟠 Ubah Status Proxied", callback_data="edit_proxied_status")
        )
    
    # Tombol Kembali ke daftar subdomain
    temp_data_back_to_list = {
        "zone_id": data['zone_id'],
        "domain_name": data['domain_name'],
        "action": "list_subs"
    }
    back_to_list_action_id = save_temp_action(cb.from_user.id, temp_data_back_to_list)
    keyboard.add(InlineKeyboardButton("⬅️ Kembali ke Daftar", callback_data=f"act:{back_to_list_action_id}"))
    
    keyboard.add(InlineKeyboardButton("❌ Batal", callback_data="batalkan"))

    await cb.message.edit_text(text, reply_markup=keyboard, parse_mode="MarkdownV2")

@dp.callback_query_handler(lambda c: c.data in ["edit_content", "edit_proxied_status", "change_record_type"], state=EditDnsRecord.select_edit_option)
async def process_edit_option_selection(cb: types.CallbackQuery, state: FSMContext):
    selected_option = cb.data
    await state.update_data(edit_option=selected_option)
    data = await state.get_data()

    keyboard = InlineKeyboardMarkup().add(InlineKeyboardButton("❌ Batal", callback_data="batalkan"))

    if selected_option == "edit_content":
        await cb.message.edit_text(
            f"⚙️ Anda memilih untuk mengedit konten record `{escape_markdown_v2(data['selected_dns_name'])}` \\({escape_markdown_v2(data['selected_dns_type'])}\\)\\.\n\n"
            f"Konten saat ini: `{escape_markdown_v2(data['selected_dns_content'])}`\n\n"
            f"Silahkan kirim IP Address Baru untuk tipe A, IPv6 untuk tipe AAA\n"
            f"Dan target domain baru untuk tipe CNAME Serta NS:",
            reply_markup=keyboard,
            parse_mode="MarkdownV2"
        )
        await EditDnsRecord.get_new_content.set()
    elif selected_option == "edit_proxied_status":
        current_proxied = data['selected_dns_proxied']
        new_status_text = "✅ Aktifkan" if not current_proxied else "❌ Nonaktifkan"
        callback_data_status = "set_proxied_true" if not current_proxied else "set_proxied_false"
        
        keyboard_proxied = InlineKeyboardMarkup(row_width=1)
        keyboard_proxied.add(InlineKeyboardButton(new_status_text, callback_data=callback_data_status))
        keyboard_proxied.add(InlineKeyboardButton("❌ Batal", callback_data="batalkan"))

        await cb.message.edit_text(
            f"⚙️ Anda memilih untuk mengubah status proxy record `{escape_markdown_v2(data['selected_dns_name'])}`\\.\n\n"
            f"Status saat ini: `{escape_markdown_v2('Aktif') if current_proxied else escape_markdown_v2('Nonaktif')}`\n\n"
            f"Pilih status baru:",
            reply_markup=keyboard_proxied,
            parse_mode="MarkdownV2"
        )
        await EditDnsRecord.get_new_proxied_status.set()
    elif selected_option == "change_record_type":
        keyboard_type = InlineKeyboardMarkup(row_width=2)
        
        # Opsi tipe record yang tersedia
        available_types = ['A', 'AAAA', 'CNAME', 'NS']
        current_type = data['selected_dns_type']
        
        for record_type in available_types:
            if record_type != current_type:
                keyboard_type.add(InlineKeyboardButton(record_type, callback_data=f"change_type_to_{record_type.lower()}"))
        
        keyboard_type.add(InlineKeyboardButton("❌ Batal", callback_data="batalkan"))
        
        await cb.message.edit_text(
            f"⚙️ Anda memilih untuk mengubah tipe record `{escape_markdown_v2(data['selected_dns_name'])}` dari `{escape_markdown_v2(current_type)}`\\.\n\n"
            f"Pilih tipe record baru:",
            reply_markup=keyboard_type,
            parse_mode="MarkdownV2"
        )
        await EditDnsRecord.get_new_record_type.set()
    
    await cb.answer()

@dp.message_handler(state=EditDnsRecord.get_new_content)
async def process_new_content(msg: types.Message, state: FSMContext):
    new_content = msg.text.strip()
    data = await state.get_data()
    
    uid = msg.from_user.id
    user_data = get_user_data(uid)

    await msg.answer(
        f"⏳ Memperbarui konten record `{escape_markdown_v2(data['selected_dns_name'])}` ke `{escape_markdown_v2(new_content)}`\\.",
        parse_mode="MarkdownV2"
    )

    res = update_cf_dns_record(
        email=user_data.get("email"),
        api_key=user_data.get("api_key"),
        zone_id=data['zone_id'],
        dns_id=data['selected_dns_id'],
        name=data['selected_dns_name'],
        content=new_content,
        record_type=data['selected_dns_type'],
        proxied=data['selected_dns_proxied']
    )

    await state.finish()
    
    temp_data_back_to_domain_menu = {
        "zone_id": data['zone_id'],
        "domain_name": data['domain_name'],
        "action": "select_domain"
    }
    back_action_id = save_temp_action(uid, temp_data_back_to_domain_menu)
    keyboard = InlineKeyboardMarkup().add(InlineKeyboardButton("⬅️ Kembali ke Menu Domain", callback_data=f"act:{back_action_id}"))

    if res and res.get("success"):
        await msg.answer(
            f"✅ Konten record `{escape_markdown_v2(data['selected_dns_name'])}` berhasil diperbarui\\.",
            reply_markup=keyboard,
            parse_mode="MarkdownV2"
        )
    else:
        error_message = "❌ Gagal memperbarui konten record\\."
        if res and res.get('errors'):
            first_error = res['errors'][0] if res['errors'] else {}
            error_message = escape_markdown_v2(first_error.get('message', 'error tidak diketahui'))
        elif res is None:
            error_message = escape_markdown_v2("Permintaan ke Cloudflare gagal Silahkan Coba lagi nanti")
        
        await msg.answer(
            f"❌ *Gagal\\!* Terjadi kesalahan: `{error_message}`",
            reply_markup=keyboard,
            parse_mode="MarkdownV2"
        )

@dp.callback_query_handler(lambda c: c.data.startswith("set_proxied_"), state=EditDnsRecord.get_new_proxied_status)
async def process_new_proxied_status(cb: types.CallbackQuery, state: FSMContext):
    new_proxied_status = True if cb.data == "set_proxied_true" else False
    data = await state.get_data()
    
    uid = cb.from_user.id
    user_data = get_user_data(uid)

    proxied_text = "mengaktifkan" if new_proxied_status else "menonaktifkan"
    escaped_proxied_text = escape_markdown_v2(proxied_text)

    await cb.message.edit_text(
        f"⏳ Sedang {escaped_proxied_text} proxy untuk record `{escape_markdown_v2(data['selected_dns_name'])}`\\.",
        parse_mode="MarkdownV2"
    )
    await cb.answer()

    res = update_cf_dns_record(
        email=user_data.get("email"),
        api_key=user_data.get("api_key"),
        zone_id=data['zone_id'],
        dns_id=data['selected_dns_id'],
        name=data['selected_dns_name'],
        content=data['selected_dns_content'],
        record_type=data['selected_dns_type'],
        proxied=new_proxied_status
    )

    await state.finish()

    temp_data_back_to_domain_menu = {
        "zone_id": data['zone_id'],
        "domain_name": data['domain_name'],
        "action": "select_domain"
    }
    back_action_id = save_temp_action(uid, temp_data_back_to_domain_menu)
    keyboard = InlineKeyboardMarkup().add(InlineKeyboardButton("⬅️ Kembali ke Menu Domain", callback_data=f"act:{back_action_id}"))

    if res and res.get("success"):
        await cb.message.edit_text(
            f"✅ Status proxy record `{escape_markdown_v2(data['selected_dns_name'])}` berhasil diperbarui menjadi `{escape_markdown_v2('Aktif') if new_proxied_status else escape_markdown_v2('Nonaktif')}`\\.",
            reply_markup=keyboard,
            parse_mode="MarkdownV2"
        )
    else:
        error_message = "❌ Gagal memperbarui status proxy record\\."
        if res and res.get('errors'):
            first_error = res['errors'][0] if res['errors'] else {}
            error_message = escape_markdown_v2(first_error.get('message', 'error tidak diketahui'))
        elif res is None:
            error_message = escape_markdown_v2("Permintaan ke Cloudflare gagal Silahkan Coba lagi nanti")
        
        await cb.message.edit_text(
            f"❌ *Gagal\\!* Terjadi kesalahan: `{error_message}`",
            reply_markup=keyboard,
            parse_mode="MarkdownV2"
        )

@dp.callback_query_handler(lambda c: c.data.startswith("change_type_to_"), state=EditDnsRecord.get_new_record_type)
async def process_new_record_type_selection(cb: types.CallbackQuery, state: FSMContext):
    new_type = cb.data.replace("change_type_to_", "").upper()
    await state.update_data(new_record_type=new_type)
    data = await state.get_data()

    keyboard = InlineKeyboardMarkup().add(InlineKeyboardButton("❌ Batal", callback_data="batalkan"))

    if new_type in ['A', 'AAAA', 'CNAME']:
        await cb.message.edit_text(
            f"⚙️ Anda memilih untuk mengubah tipe record `{escape_markdown_v2(data['selected_dns_name'])}` ke `{escape_markdown_v2(new_type)}`\\.\n\n"
            f"Silahkan kirim IP Address Baru untuk tipe A, IPv6 untuk tipe AAA\n"
            f"Dan target domain baru untuk tipe CNAME Serta NS:",
            reply_markup=keyboard,
            parse_mode="MarkdownV2"
        )
        await EditDnsRecord.get_new_record_content_for_type_change.set()
    elif new_type == 'NS':
        await cb.message.edit_text(
            f"⚙️ Anda memilih untuk mengubah tipe record `{escape_markdown_v2(data['selected_dns_name'])}` ke `{escape_markdown_v2(new_type)}`\\.\n\n"
            f"Silahkan kirim target domain baru untuk Nameserver\\.\n"
            f"contoh: `ns1\\.example\\.com`:",
            reply_markup=keyboard,
            parse_mode="MarkdownV2"
        )
        await EditDnsRecord.get_new_record_content_for_type_change.set()
    else:
        await cb.message.edit_text(
            escape_markdown_v2("⚠️ Tipe record yang dipilih tidak didukung\\. Silahkan pilih tipe lain\\."),
            reply_markup=keyboard,
            parse_mode="MarkdownV2"
        )
        # Kembali ke menu pemilihan tipe
        await show_edit_options_for_record(cb, state)
        await EditDnsRecord.select_edit_option.set()

    await cb.answer()

@dp.message_handler(state=EditDnsRecord.get_new_record_content_for_type_change)
async def process_new_content_for_type_change(msg: types.Message, state: FSMContext):
    new_content = msg.text.strip()
    data = await state.get_data()
    new_type = data['new_record_type']

    await state.update_data(new_content_for_type_change=new_content)

    if new_type in ['A', 'AAAA', 'CNAME']:
        keyboard_proxied = InlineKeyboardMarkup(row_width=2)
        keyboard_proxied.add(
            InlineKeyboardButton("✅ Aktifkan Proxied", callback_data="proxied_true_for_type_change"),
            InlineKeyboardButton("❌ Nonaktifkan Proxied", callback_data="proxied_false_for_type_change")
        )
        keyboard_proxied.add(InlineKeyboardButton("❌ Batal", callback_data="batalkan"))
        
        await msg.answer(
            f"⚙️ Konten baru `{escape_markdown_v2(new_content)}` untuk tipe `{escape_markdown_v2(new_type)}` telah diterima\\.\n\n"
            f"Apakah Anda ingin mengaktifkan proxy \\(Cloudflare CDN\\) untuk record ini?",
            reply_markup=keyboard_proxied,
            parse_mode="MarkdownV2"
        )
        await EditDnsRecord.get_new_proxied_status_for_type_change.set()
    elif new_type == 'NS':
        # NS records tidak bisa diproxied, langsung update
        uid = msg.from_user.id
        user_data = get_user_data(uid)

        await msg.answer(
            f"⏳ Memperbarui record `{escape_markdown_v2(data['selected_dns_name'])}` ke tipe `{escape_markdown_v2(new_type)}` dengan konten `{escape_markdown_v2(new_content)}`\\.",
            parse_mode="MarkdownV2"
        )

        res = update_cf_dns_record(
            email=user_data.get("email"),
            api_key=user_data.get("api_key"),
            zone_id=data['zone_id'],
            dns_id=data['selected_dns_id'],
            name=data['selected_dns_name'],
            content=new_content,
            record_type=new_type,
            proxied=False # NS cannot be proxied
        )

        await state.finish()

        temp_data_back_to_domain_menu = {
            "zone_id": data['zone_id'],
            "domain_name": data['domain_name'],
            "action": "select_domain"
        }
        back_action_id = save_temp_action(uid, temp_data_back_to_domain_menu)
        keyboard = InlineKeyboardMarkup().add(InlineKeyboardButton("⬅️ Kembali ke Menu Domain", callback_data=f"act:{back_action_id}"))

        if res and res.get("success"):
            await msg.answer(
                f"✅ Record `{escape_markdown_v2(data['selected_dns_name'])}` berhasil diperbarui ke tipe `{escape_markdown_v2(new_type)}`\\.",
                reply_markup=keyboard,
                parse_mode="MarkdownV2"
            )
        else:
            error_message = "❌ Gagal memperbarui tipe record\\."
            if res and res.get('errors'):
                first_error = res['errors'][0] if res['errors'] else {}
                error_message = escape_markdown_v2(first_error.get('message', 'error tidak diketahui'))
            elif res is None:
                error_message = escape_markdown_v2("Permintaan ke Cloudflare gagal Silahkan Coba lagi nanti")
            
            await msg.answer(
                f"❌ *Gagal\\!* Terjadi kesalahan: `{error_message}`",
                reply_markup=keyboard,
                parse_mode="MarkdownV2"
            )
    else:
        await msg.answer(
            escape_markdown_v2("⚠️ Tipe record yang dipilih tidak didukung\\. Silahkan pilih tipe lain\\."),
            parse_mode="MarkdownV2"
        )
        await show_edit_options_for_record(msg, state) # Kembali ke opsi edit
        await EditDnsRecord.select_edit_option.set()

@dp.callback_query_handler(lambda c: c.data.startswith("proxied_") and c.data.endswith("_for_type_change"), state=EditDnsRecord.get_new_proxied_status_for_type_change)
async def process_new_proxied_status_for_type_change(cb: types.CallbackQuery, state: FSMContext):
    new_proxied_status = True if "proxied_true" in cb.data else False
    data = await state.get_data()
    
    uid = cb.from_user.id
    user_data = get_user_data(uid)

    new_type = data['new_record_type']
    new_content = data['new_content_for_type_change']

    proxied_text = "mengaktifkan" if new_proxied_status else "menonaktifkan"
    escaped_proxied_text = escape_markdown_v2(proxied_text)

    await cb.message.edit_text(
        f"⏳ Memperbarui record `{escape_markdown_v2(data['selected_dns_name'])}` ke tipe `{escape_markdown_v2(new_type)}` dengan konten `{escape_markdown_v2(new_content)}` dan {escaped_proxied_text} proxy\\.",
        parse_mode="MarkdownV2"
    )
    await cb.answer()

    res = update_cf_dns_record(
        email=user_data.get("email"),
        api_key=user_data.get("api_key"),
        zone_id=data['zone_id'],
        dns_id=data['selected_dns_id'],
        name=data['selected_dns_name'],
        content=new_content,
        record_type=new_type,
        proxied=new_proxied_status
    )

    await state.finish()

    temp_data_back_to_domain_menu = {
        "zone_id": data['zone_id'],
        "domain_name": data['domain_name'],
        "action": "select_domain"
    }
    back_action_id = save_temp_action(uid, temp_data_back_to_domain_menu)
    keyboard = InlineKeyboardMarkup().add(InlineKeyboardButton("⬅️ Kembali ke Menu Domain", callback_data=f"act:{back_action_id}"))

    if res and res.get("success"):
        await cb.message.edit_text(
            f"✅ Record `{escape_markdown_v2(data['selected_dns_name'])}` berhasil diperbarui ke tipe `{escape_markdown_v2(new_type)}` dengan status proxy `{escape_markdown_v2('Aktif') if new_proxied_status else escape_markdown_v2('Nonaktif')}`\\.",
            reply_markup=keyboard,
            parse_mode="MarkdownV2"
        )
    else:
        error_message = "❌ Gagal memperbarui tipe record dan status proxy\\."
        if res and res.get('errors'):
            first_error = res['errors'][0] if res['errors'] else {}
            error_message = escape_markdown_v2(first_error.get('message', 'error tidak diketahui'))
        elif res is None:
            error_message = escape_markdown_v2("Permintaan ke Cloudflare gagal Silahkan Coba lagi nanti")
        
        await cb.message.edit_text(
            f"❌ *Gagal\\!* Terjadi kesalahan: `{error_message}`",
            reply_markup=keyboard,
            parse_mode="MarkdownV2"
        )

@dp.message_handler(commands=['add_member'])
async def add_member(msg: types.Message):
    if msg.from_user.id not in ADMIN_IDS:
        await msg.reply("❌ Anda bukan admin")
        return

    parts = msg.text.strip().split()
    if len(parts) != 2 or not parts[1].isdigit():
        await msg.reply("⚠️ Format: /add_member <id_telegram_user>")
        return

    target_id = int(parts[1])
    allowed = load_allowed_users()

    if target_id in allowed:
        await msg.reply("ℹ️ Pengguna sudah memiliki izin")
    else:
        allowed.append(target_id)
        save_allowed_users(allowed)
        await msg.reply(f"✅ ID {target_id} telah diberi izin menggunakan bot")

@dp.message_handler(commands=['del_member'])
async def del_member(msg: types.Message):
    if msg.from_user.id not in ADMIN_IDS:
        await msg.reply("❌ Anda bukan admin")
        return

    parts = msg.text.strip().split()
    if len(parts) != 2 or not parts[1].isdigit():
        await msg.reply("⚠️ Format: /del_member <id_telegram_user>")
        return

    target_id = int(parts[1])

    if target_id in ADMIN_IDS:
        await msg.reply("⚠️ Tidak dapat mencabut izin admin")
        return

    allowed = load_allowed_users()
    if target_id in allowed:
        allowed.remove(target_id)
        save_allowed_users(allowed)
        await msg.reply(f"❌ Akses ID {target_id} telah dicabut")
    else:
        await msg.reply("ℹ️ ID tersebut belum diizinkan sebelumnya")
        

@dp.message_handler(commands=['list_member'])
async def list_member(msg: types.Message):
    allowed = load_allowed_users()
    if not allowed:
        await msg.answer("📭 Belum ada user yang diizinkan", parse_mode="MarkdownV2")
        return

    result = "📋 Daftar User yang Diizinkan:\n\n"
    for uid in allowed:
        try:
            user = await bot.get_chat(uid)
            username = f"@{user.username}" if user.username else "(tanpa username)"
            name = escape_markdown_v2(user.first_name)
            uid_str = escape_markdown_v2(str(uid))
            username_escaped = escape_markdown_v2(username)
            result += f"» `{uid_str}` → {username_escaped} — {name}\n"
        except Exception:
            uid_str = escape_markdown_v2(str(uid))
            result += f"» `{uid_str}` → (tidak dapat mengambil info)\n"

    await msg.answer(result, parse_mode="MarkdownV2")
    
@dp.message_handler(commands=['about'])
async def about_handler(msg: types.Message):
    text = (
        "📒️ *Informasi Tentang Bot:*\n\n"
        "🤖 Bot Ini Membantu Mu Mengelola DNS Record Di Cloudflare Untuk Keperluan Tunneling Dll\\. 🚀\n\n"
        "📦 *Fitur Bot*:\n"
        "» *Bisa Membuat Wildcard*\\.\n"
        "» *Bisa Edit Type Records Sub Domain*\\.\n"
        "» *Bisa Buat Sub Domain Type CNAME*\\.\n"
        "» *Bisa Atur Status Awan Orange 🟠 ON Atau OFF*\\.\n"
        "» *Bisa Hapus Sub Domain Yang Di Pilih*\\.\n"
        "» *Otomatis Memindai Domain Utama Di Akun CF Kalian*\\.\n"
        "» *Ada Fitur Log Out Akun, Jadi Bisa Gonta Ganti Ke Akun Lain*\\.\n\n"
        "Untuk Sewa Bot Bisa Chat Admin Ganteng @Dark\\_System2x"
    )
    await msg.answer(text, parse_mode="MarkdownV2")
        
@dp.message_handler(state=BroadcastState.waiting_for_all, content_types=types.ContentTypes.ANY)
async def process_broadcast_all(msg: types.Message, state: FSMContext):
    if msg.from_user.id not in ADMIN_IDS:
        await msg.answer("❌ Anda bukan admin")
        await state.finish()
        return

    success, failed = 0, 0

    try:
        with open("all_users.json", "r") as f:
            users = json.load(f)
    except:
        users = []

    await msg.answer("🚀 Mengirim broadcast ke semua user")

    for uid in users:
        try:
            if msg.content_type == "text":
                await bot.send_message(uid, msg.text)
            elif msg.content_type == "photo":
                await bot.send_photo(uid, msg.photo[-1].file_id, caption=msg.caption or "")
            elif msg.content_type == "video":
                await bot.send_video(uid, msg.video.file_id, caption=msg.caption or "")
            elif msg.content_type == "document":
                await bot.send_document(uid, msg.document.file_id, caption=msg.caption or "")
            elif msg.content_type == "sticker":
                await bot.send_sticker(uid, msg.sticker.file_id)
            else:
                failed += 1
                continue

            success += 1
        except Exception:
            failed += 1

    await msg.answer(f"✅ Broadcast selesai\n\n🟢 Berhasil: {success}\n🔴 Gagal: {failed}")
    await state.finish()
    
@dp.message_handler(commands=['kirim_pesan'])
async def broadcast_all_start(msg: types.Message):
    if msg.from_user.id not in ADMIN_IDS:
        await msg.answer("❌ Anda bukan admin")
        return

    await msg.answer("📝 Silakan kirim pesan Teks, Gambar, Dokumen, video, dll yang ingin dibroadcast ke semua user yang pernah akses /start di bot")
    await BroadcastState.waiting_for_all.set()
    
@dp.message_handler(lambda msg: msg.text == "🔑 Login ke Akun")
async def handle_login_button(msg: types.Message, state: FSMContext):
    if not is_user_allowed(msg.from_user.id):
        await msg.answer("❌ Anda belum diberi izin")
        return

    user_data = get_user_data(msg.from_user.id)
    if user_data:
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(InlineKeyboardButton("🗑️ Ya, Hapus Data & Logout", callback_data="confirm_delete_account"))
        keyboard.add(InlineKeyboardButton("⬅️ Kembali ke Menu", callback_data="back_to_main_menu"))
        await msg.answer(escape_markdown_v2("⚠️ Anda sudah login. Ingin logout?"), reply_markup=keyboard)
    else:
        keyboard = InlineKeyboardMarkup().add(InlineKeyboardButton("❌ Batal", callback_data="back_to_main_menu"))
        await msg.answer(escape_markdown_v2("🔐 Kirim Email Akun Cloudflare mu:"), reply_markup=keyboard)
        await Login.get_email.set()


@dp.message_handler(lambda msg: msg.text == "🌐 Kelola Domain")
async def handle_manage_domains_button(msg: types.Message):
    uid = msg.from_user.id

    if not is_user_allowed(uid):
        await msg.answer("❌ Anda belum diberi izin")
        return

    user_data = get_user_data(uid)
    if not user_data:
        keyboard = InlineKeyboardMarkup().add(
            InlineKeyboardButton("🔐 Login ke Akun", callback_data="go_to_login"),
            InlineKeyboardButton("⬅️ Kembali ke Menu", callback_data="back_to_main_menu")
        )
        await msg.answer("❌ Silahkan login terlebih dahulu", reply_markup=keyboard)
        return

    zones = get_cf_zones(user_data['email'], user_data['api_key'])
    if not zones:
        await msg.answer("❌ Gagal mengambil domain, Silahkan cek API Key kamu")
        return

    domain_list = [{"zone_id": z['id'], "name": z['name']} for z in zones]
    user_data['domains'] = domain_list
    save_user_data(uid, user_data)

    keyboard = InlineKeyboardMarkup(row_width=1)
    for domain in domain_list:
        temp_data = {
            "zone_id": domain['zone_id'],
            "domain_name": domain['name'],
            "action": "select_domain"
        }
        action_id = save_temp_action(uid, temp_data)
        keyboard.add(InlineKeyboardButton(domain['name'], callback_data=f"act:{action_id}"))

    keyboard.add(InlineKeyboardButton("⬅️ Kembali ke Menu", callback_data="back_to_main_menu"))
    await msg.answer("✅ Pilih domain yang ingin kamu kelola:", reply_markup=keyboard)

@dp.message_handler(lambda msg: msg.text == "🔄 Ganti Akun & Logout")
async def handle_logout_button(msg: types.Message, state: FSMContext):
    if not is_user_allowed(msg.from_user.id):
        await msg.answer("❌ Anda belum diberi izin")
        return

    user_data = get_user_data(msg.from_user.id)
    if not user_data:
        await msg.answer("❌ Anda belum login")
        return

    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(InlineKeyboardButton("🗑️ Ya, Hapus Data & Logout", callback_data="confirm_delete_account"))
    keyboard.add(InlineKeyboardButton("⬅️ Batal", callback_data="back_to_main_menu"))

    await msg.answer(escape_markdown_v2("⚠️ Konfirmasi logout dan hapus data login Anda dari bot:"), reply_markup=keyboard, parse_mode="MarkdownV2")

@dp.message_handler(lambda msg: msg.text == "ℹ️ Info & bantuan")
async def handle_help_button(msg: types.Message):
    keyboard = InlineKeyboardMarkup().add(
        InlineKeyboardButton("⬅️ Kembali ke Menu", callback_data="back_to_main_menu")
    )
    await msg.answer(
        "📒️ *Informasi Tentang Bot:*\n\n"
        "🤖 Bot Ini Membantu Mu Mengelola DNS Record Di Cloudflare Untuk Keperluan Tunneling Dll\\. 🚀\n\n"
        "📦 *Fitur Bot*:\n"
        "» *Bisa Membuat Wildcard*\\.\n"
        "» *Bisa Edit Type Records Sub Domain*\\.\n"
        "» *Bisa Buat Sub Domain Tipe CNAME*\\.\n"
        "» *Bisa Atur Status Awan Orange 🟠 ON Atau OFF*\\.\n"
        "» *Bisa Hapus Sub Domain Yang Di Pilih*\\.\n"
        "» *Otomatis Memindai Domain Utama Di Akun CF Kalian*\\.\n"
        "» *Ada Fitur Log Out Akun, Jadi Bisa Gonta Ganti Ke Akun Lain*\\.\n\n"
        "Untuk Sewa Bot Bisa Chat Admin Ganteng @Dark\\_System2x",
        # Dihapus bagian "Pastikan Telah Bergabung Di Channel Dan Grup Admin Terlebih Dahulu Untuk Menggunakan Bot Ini\\."
        reply_markup=keyboard,
        parse_mode="MarkdownV2"
    )    

@dp.message_handler(lambda msg: msg.text == "📋 List Member")
async def handle_list_member_text(msg: types.Message):
    allowed = load_allowed_users()
    
    if not allowed:
        await msg.answer("📭 Belum ada member yang diizinkan")
        return

    result = f"📋 *Daftar Member yang Diizinkan:* {len(allowed)}\n\n"
    for uid in allowed:
        try:
            user = await bot.get_chat(uid)
            uname = f"@{user.username}" if user.username else "tanpa username"
            name = escape_markdown_v2(user.first_name)
            result += f"» `{uid}` → {escape_markdown_v2(uname)} — {name}\n"
        except:
            result += f"» `{uid}` → tidak ditemukan\n"

    await msg.answer(result, parse_mode="MarkdownV2")

@dp.message_handler(lambda msg: msg.text == "✏️ Tambah Member")
async def trigger_add_member(msg: types.Message, state: FSMContext):
    if msg.from_user.id not in ADMIN_IDS:
        await msg.reply("❌ Anda bukan admin")
        return

    await msg.answer("📝 Kirim ID Telegram user yang ingin kamu izinkan:")
    await MemberManage.waiting_for_add_id.set()


@dp.message_handler(state=MemberManage.waiting_for_add_id)
async def handle_add_member(msg: types.Message, state: FSMContext):
    if msg.from_user.id not in ADMIN_IDS:
        await state.finish()
        return

    if not msg.text.strip().isdigit():
        await msg.reply("⚠️ Harus berupa angka")
        return

    target_id = int(msg.text.strip())
    allowed = load_allowed_users()
    if target_id in allowed:
        await msg.reply("ℹ️ Sudah diizinkan")
    else:
        allowed.append(target_id)
        save_allowed_users(allowed)
        await msg.reply(f"✅ ID `{target_id}` ditambahkan", parse_mode="MarkdownV2")

    await state.finish()

@dp.message_handler(lambda msg: msg.text == "❌ Hapus Member")
async def trigger_delete_member(msg: types.Message, state: FSMContext):
    if msg.from_user.id not in ADMIN_IDS:
        await msg.reply("❌ Anda bukan admin")
        return

    await msg.answer("📤 Kirim ID Telegram user yang ingin kamu hapus:")
    await MemberManage.waiting_for_del_id.set()


@dp.message_handler(state=MemberManage.waiting_for_del_id)
async def handle_delete_member(msg: types.Message, state: FSMContext):
    if msg.from_user.id not in ADMIN_IDS:
        await state.finish()
        return

    if not msg.text.strip().isdigit():
        await msg.reply("⚠️ Harus berupa angka")
        return

    target_id = int(msg.text.strip())

    if target_id in ADMIN_IDS:
        await msg.reply("⚠️ Tidak bisa hapus admin")
        await state.finish()
        return

    allowed = load_allowed_users()
    if target_id in allowed:
        allowed.remove(target_id)
        save_allowed_users(allowed)
        await msg.reply(f"❌ Akses ID `{target_id}` dicabut", parse_mode="MarkdownV2")
    else:
        await msg.reply("ℹ️ ID belum diizinkan")

    await state.finish()

@dp.message_handler(lambda msg: msg.text == "📢 Broadcast")
async def start_broadcast(msg: types.Message, state: FSMContext):
    if msg.from_user.id not in ADMIN_IDS:
        await msg.reply("❌ Anda bukan admin")
        return

    await msg.answer("📢 Kirim pesan yang ingin dibroadcast ke semua member:")
    await BroadcastState.waiting_for_all.set()


@dp.message_handler(state=BroadcastState.waiting_for_all)
async def handle_broadcast(msg: types.Message, state: FSMContext):
    allowed = load_allowed_users()
    success = 0
    fail = 0

    for uid in allowed:
        try:
            await bot.send_message(uid, msg.text)
            success += 1
        except:
            fail += 1

    await msg.reply(f"✅ Terkirim ke {success} user\n❌ Gagal kirim ke {fail} user")
    await state.finish()

# --- New Handlers for Subdomain File Management ---
@dp.message_handler(lambda message: message.text == '🌐 Kelola Domain', state='*')
async def go_to_manage_domain(message: types.Message, state: FSMContext):
    await state.finish()
    await _send_manage_domain_file_menu(message)

# Fungsi untuk mengirim menu pengelolaan file domain
async def _send_manage_domain_file_menu(target_message: types.Message):
    """Fungsi internal untuk mengirim menu pengelolaan file domain."""
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("➕ Tambah Subdomain", callback_data="add_subdomain_file"),
        InlineKeyboardButton("🗑️ Hapus Subdomain", callback_data="delete_subdomain_file")
    )
    keyboard.add(InlineKeyboardButton("📋 Tampilkan Semua", callback_data="list_subdomain_file"))
    keyboard.add(InlineKeyboardButton("💣 Hapus Semua Subdomain", callback_data="confirm_delete_all_subdomains"))
    keyboard.add(InlineKeyboardButton("⬅️ Kembali ke Menu", callback_data="back_to_main_menu"))
    
    await target_message.answer("⚙️ Pilih aksi untuk mengelola file `domain.txt`:", reply_markup=keyboard)


@dp.message_handler(lambda msg: msg.text == "📁 Kelola File Domain")
async def manage_domain_file_menu(msg: types.Message):
    if msg.from_user.id not in ADMIN_IDS:
        await msg.reply("❌ Fitur ini hanya untuk admin")
        return
        
    await _send_manage_domain_file_menu(msg)


@dp.callback_query_handler(lambda c: c.data == "list_subdomain_file")
async def list_subdomain_file(cb: types.CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS:
        await cb.answer("❌ Fitur ini hanya untuk admin", show_alert=True)
        return
        
    subdomains = read_subdomains()
    
    if not subdomains:
        text = "📭 File `domain.txt` kosong atau tidak ada"
    else:
        text = "📄 *Daftar Subdomain dari* `domain.txt`:\n\n"
        text += "\n".join([f"`{escape_markdown_v2(s)}`" for s in subdomains])
        
    keyboard = InlineKeyboardMarkup().add(InlineKeyboardButton("⬅️ Kembali", callback_data="back_to_file_menu"))
    await cb.message.edit_text(text, reply_markup=keyboard, parse_mode="MarkdownV2")
    await cb.answer()


@dp.callback_query_handler(lambda c: c.data == "add_subdomain_file")
async def add_subdomain_file_start(cb: types.CallbackQuery, state: FSMContext):
    if cb.from_user.id not in ADMIN_IDS:
        await cb.answer("❌ Fitur ini hanya untuk admin", show_alert=True)
        return
        
    await cb.message.edit_text(escape_markdown_v2("📝 Kirim nama subdomain yang ingin ditambahkan (satu atau lebih, dipisahkan per baris):\n\nContoh:\n`vpn-1.domain.com`\n`vpn-2.domain.com`"))
    await DomainFileManage.waiting_for_subdomain_to_add.set()
    await cb.answer()


@dp.message_handler(state=DomainFileManage.waiting_for_subdomain_to_add)
async def add_subdomain_to_file_handler(msg: types.Message, state: FSMContext):
    if msg.from_user.id not in ADMIN_IDS:
        await state.finish()
        return
    
    # Memisahkan input menjadi daftar subdomain, mengabaikan baris kosong
    subdomains_to_add = [line.strip() for line in msg.text.split('\n') if line.strip()]
    
    if not subdomains_to_add:
        await msg.answer("⚠️ Tidak ada subdomain yang valid ditemukan Silahkan kirim daftar subdomain satu per baris")
        return

    existing_subdomains = read_subdomains()
    added_subdomains = []
    
    for sub in subdomains_to_add:
        # Pengecekan validasi yang mengizinkan:
        # 1. Hanya tanda '*'
        # 2. Subdomain normal (mengandung '.' dan tidak dimulai dengan '.')
        is_valid_entry = (sub == '*') or ('.' in sub and not sub.startswith('.'))
        
        if is_valid_entry:
            # Periksa apakah subdomain sudah ada untuk menghindari duplikasi
            if sub not in existing_subdomains:
                existing_subdomains.append(sub)
                added_subdomains.append(sub)
    
    if added_subdomains:
        write_subdomains(existing_subdomains)
        success_message = f"✅ Subdomain berhasil ditambahkan:\n\n" + "\n".join([f"`{escape_markdown_v2(s)}`" for s in added_subdomains])
        await msg.answer(success_message, parse_mode="MarkdownV2")
    else:
        # Jika tidak ada yang ditambahkan, berikan pesan error yang lebih spesifik
        await msg.answer("⚠️ Tidak ada subdomain baru yang valid untuk ditambahkan Pastikan formatnya benar (contoh: `vpn.domain.com` atau hanya `*`)")

    # Mengakhiri state dan kembali ke menu pengelolaan file
    await state.finish()


@dp.callback_query_handler(lambda c: c.data == "back_to_file_menu", state='*')
async def back_to_file_menu_cb(cb: types.CallbackQuery, state: FSMContext):
    await state.finish()
    await _send_manage_domain_file_menu(cb.message)
    await cb.answer()

# --- Handler untuk memulai proses Hapus Subdomain ---
@dp.callback_query_handler(lambda c: c.data == "delete_subdomain_file")
async def delete_subdomain_file_start(cb: types.CallbackQuery, state: FSMContext):
    if cb.from_user.id not in ADMIN_IDS:
        await cb.answer("❌ Fitur ini hanya untuk admin", show_alert=True)
        return
        
    subdomains = read_subdomains()
    
    if not subdomains:
        keyboard = InlineKeyboardMarkup().add(InlineKeyboardButton("⬅️ Kembali", callback_data="back_to_file_menu"))
        await cb.message.edit_text("📭 File `domain.txt` kosong atau tidak ada subdomain untuk dihapus", reply_markup=keyboard)
        await cb.answer()
        return
    
    text = "📝 Kirim nomor atau nama subdomain yang ingin kamu hapus:\n\n"
    for idx, sub in enumerate(subdomains):
        text += f"`{idx + 1}`\\. `{escape_markdown_v2(sub)}`\n"
    
    keyboard = InlineKeyboardMarkup().add(InlineKeyboardButton("⬅️ Kembali", callback_data="back_to_file_menu"))
    await cb.message.edit_text(text, reply_markup=keyboard, parse_mode="MarkdownV2")
    await DomainFileManage.waiting_for_subdomain_to_delete.set()
    await cb.answer()


@dp.message_handler(state=DomainFileManage.waiting_for_subdomain_to_delete)
async def delete_subdomain_from_file_handler(msg: types.Message, state: FSMContext):
    if msg.from_user.id not in ADMIN_IDS:
        await state.finish()
        return
    
    subdomains = read_subdomains()
    to_delete = msg.text.strip()
    deleted_subdomain = None
    
    try:
        idx = int(to_delete) - 1
        if 0 <= idx < len(subdomains):
            deleted_subdomain = subdomains.pop(idx)
        else:
            await msg.reply("⚠️ Nomor subdomain tidak valid Coba lagi")
            return
    except ValueError:
        if to_delete in subdomains:
            subdomains.remove(to_delete)
            deleted_subdomain = to_delete
        else:
            await msg.reply(f"⚠️ Subdomain `{escape_markdown_v2(to_delete)}` tidak ditemukan")
            return
            
    if deleted_subdomain:
        write_subdomains(subdomains)
        await msg.reply(f"✅ Subdomain `{escape_markdown_v2(deleted_subdomain)}` berhasil dihapus", parse_mode="MarkdownV2")
    else:
        await msg.reply("⚠️ Terjadi kesalahan saat menghapus")
        
    await state.finish()
    await _send_manage_domain_file_menu(msg)


@dp.callback_query_handler(lambda c: c.data == "confirm_delete_all_subdomains")
async def confirm_delete_all_subdomains(cb: types.CallbackQuery, state: FSMContext):
    if cb.from_user.id not in ADMIN_IDS:
        await cb.answer("❌ Fitur ini hanya untuk admin", show_alert=True)
        return
        
    keyboard = InlineKeyboardMarkup().add(
        InlineKeyboardButton("⚠️ Ya, Hapus Semua", callback_data="delete_all_subdomains_confirmed"),
        InlineKeyboardButton("❌ Batal", callback_data="back_to_file_menu")
    )
    
    await cb.message.edit_text(escape_markdown_v2("⚠️ *PERINGATAN*:\n\nIni akan menghapus semua subdomain dari file `domain.txt`. Apakah Anda yakin?"), reply_markup=keyboard, parse_mode="MarkdownV2")
    await cb.answer()


@dp.callback_query_handler(lambda c: c.data == "delete_all_subdomains_confirmed")
async def delete_all_subdomains(cb: types.CallbackQuery, state: FSMContext):
    if cb.from_user.id not in ADMIN_IDS:
        await cb.answer("❌ Fitur ini hanya untuk admin", show_alert=True)
        return
    
    with open(DOMAIN_FILE, 'w') as f:
        f.write("")
        
    await cb.message.edit_text("✅ Semua subdomain telah dihapus dari `domain.txt`")
    await state.finish()
    await cb.answer()
    
    await _send_manage_domain_file_menu(cb.message)


@dp.callback_query_handler(lambda c: c.data == "back_to_file_menu")
async def back_to_file_menu_cb(cb: types.CallbackQuery):
    await _send_manage_domain_file_menu(cb.message)
    await cb.answer()
    
def escape_subdomain(text: str) -> str:
    # A simplified version of escape_markdown_v2 for just the subdomain part
    reserved_chars = r'[\_*\(\)\[\]~`>#+\-=|{}.!]'
    return ''.join(f'\\{char}' if char in reserved_chars else char for char in text)


if __name__ == "__main__":
    init_storage() 
    logging.basicConfig(level=logging.INFO)
    executor.start_polling(dp, skip_updates=True)