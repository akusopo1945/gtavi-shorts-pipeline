#!/usr/bin/env python3
"""
Luna GTA Shorts Telegram Interactive Command Center
Mendengarkan perintah user via Telegram Bot (Start/Stop Watcher, Manual Clip, Status, Help)
"""

import os
import sys
import time
import json
import signal
import subprocess
import requests
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ENGINE_DIR = BASE_DIR / "engine"
PID_FILE = BASE_DIR / ".watcher.pid"
ENV_FILE = BASE_DIR / ".env"
WEB_DIR = Path("/data/html/clips")

def load_env():
    env = {}
    if ENV_FILE.exists():
        with open(ENV_FILE) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    env[k.strip()] = v.strip().strip('"').strip("'")
    return env

ENV = load_env()
TOKEN = ENV.get("TELEGRAM_BOT_TOKEN")
OWNER_ID = ENV.get("TELEGRAM_CHAT_ID")
API_URL = f"https://api.telegram.org/bot{TOKEN}"

def api_post(method, data=None, files=None):
    try:
        url = f"{API_URL}/{method}"
        if files:
            r = requests.post(url, data=data, files=files, timeout=60)
        else:
            r = requests.post(url, json=data, timeout=30)
        return r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}

def register_bot_commands():
    """Daftarkan menu tombol slash commands di aplikasi Telegram."""
    commands = [
        {"command": "help", "description": "Buka daftar perintah & panduan tools"},
        {"command": "status", "description": "Cek status Auto-Watcher & server"},
        {"command": "watch_on", "description": "Nyalakan pemantau live otomatis (Windah/Tara)"},
        {"command": "watch_off", "description": "Matikan pemantau live otomatis"},
        {"command": "clips", "description": "Lihat 5 klip Shorts terbaru di portal"},
        {"command": "clip", "description": "Potong manual: /clip <url> <range> <title>"}
    ]
    api_post("setMyCommands", {"commands": commands})

def is_watcher_running():
    if not PID_FILE.exists():
        return False, None
    try:
        pid = int(PID_FILE.read_text().strip())
        # Cek apakah proses masih hidup
        os.kill(pid, 0)
        return True, pid
    except (OSError, ValueError):
        PID_FILE.unlink(missing_ok=True)
        return False, None

def start_watcher(streamer="windah"):
    running, pid = is_watcher_running()
    if running:
        return False, f"Watcher sudah aktif (PID: {pid})."

    log_file = open(BASE_DIR / "watcher.log", "a")
    cmd = [
        sys.executable, str(ENGINE_DIR / "watcher.py"),
        "--streamer", streamer
    ]
    proc = subprocess.Popen(cmd, stdout=log_file, stderr=log_file, cwd=str(BASE_DIR))
    PID_FILE.write_text(str(proc.pid))
    return True, proc.pid

def stop_watcher():
    running, pid = is_watcher_running()
    if not running:
        return False, "Watcher sedang tidak aktif."
    try:
        os.kill(pid, signal.SIGTERM)
        time.sleep(1)
        if is_watcher_running()[0]:
            os.kill(pid, signal.SIGKILL)
        PID_FILE.unlink(missing_ok=True)
        return True, f"Watcher (PID: {pid}) berhasil dimatikan."
    except Exception as e:
        PID_FILE.unlink(missing_ok=True)
        return False, f"Error mematikan watcher: {e}"

def handle_command(chat_id, text):
    parts = text.strip().split()
    cmd = parts[0].lower().split('@')[0]
    args = parts[1:]

    if cmd in ("/start", "/help"):
        msg = (
            "🤖 *LUNA GTA SHORTS - COMMAND CENTER*\n\n"
            "Daftar perintah yang bisa kamu gunakan:\n"
            "• `/status` - Cek apakah pemantau live aktif / offline\n"
            "• `/watch_on [windah|tara]` - Aktifkan auto-watcher 24/7\n"
            "• `/watch_off` - Nonaktifkan auto-watcher\n"
            "• `/clips` - Lihat 5 klip terbaru yang sudah diproduksi\n"
            "• `/clip <url> <range> <title>` - Potong manual video apapun\n\n"
            "🌐 *Web Portal*: https://8080-agq23kqdsijuyyvfkrqpswhfru.instabox.tech/clips/"
        )
        api_post("sendMessage", {"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"})

    elif cmd == "/status":
        running, pid = is_watcher_running()
        status_text = f"🟢 *AKTIF* (PID: `{pid}`)" if running else "🔴 *NONAKTIF*"
        
        # Cek storage clips
        total_clips = 0
        if (WEB_DIR / "files").exists():
            total_clips = len(list((WEB_DIR / "files").glob("*")))
            
        msg = (
            "📊 *STATUS SISTEM LUNA CLIPPER*\n\n"
            f"• Auto-Watcher: {status_text}\n"
            f"• Target Default: `Windah Basudara`\n"
            f"• Total Klip di Portal: `{total_clips} klip`\n"
            f"• Output Format: `1080x1920 60 FPS (Faststart)`\n\n"
            "Gunakan `/watch_on` untuk menyalakan atau `/watch_off` untuk mematikan."
        )
        api_post("sendMessage", {"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"})

    elif cmd == "/watch_on":
        streamer = args[0] if args else "windah"
        success, info = start_watcher(streamer)
        if success:
            msg = (
                f"🚀 *Auto-Watcher Berhasil Dinyalakan!*\n\n"
                f"• Target: *{streamer.upper()}*\n"
                f"• PID Server: `{info}`\n"
                f"• Mode: *Background 24/7*\n\n"
                f"Bot akan mendeteksi tawa otomatis saat streamer LIVE dan langsung mengirim video ke sini!"
            )
        else:
            msg = f"⚠️ *Info*: {info}"
        api_post("sendMessage", {"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"})

    elif cmd == "/watch_off":
        success, info = stop_watcher()
        msg = f"🛑 {info}"
        api_post("sendMessage", {"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"})

    elif cmd == "/clips":
        html_file = WEB_DIR / "index.html"
        if html_file.exists():
            import re
            content = html_file.read_text(encoding="utf-8")
            match = re.search(r'const CLIPS = (\[.*?\]);', content, re.DOTALL)
            if match:
                clips = json.loads(match.group(1))[:5]
                lines = ["🎬 *5 KLIP TERBARU DI PORTAL:*\n"]
                for i, c in enumerate(clips, 1):
                    lines.append(f"{i}. *{c['title']}*")
                    lines.append(f"   ⏱️ `{c['duration']}` | 💾 `{c['size']}`")
                lines.append("\n🔗 *Nonton di Portal*:\nhttps://8080-agq23kqdsijuyyvfkrqpswhfru.instabox.tech/clips/")
                msg = "\n".join(lines)
            else:
                msg = "Belum ada daftar klip."
        else:
            msg = "Portal index.html tidak ditemukan."
        api_post("sendMessage", {"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"})

    elif cmd == "/clip":
        if len(args) < 3:
            msg = (
                "⚠️ *Format salah!*\n"
                "Gunakan:\n`/clip <url> <range> <title>`\n\n"
                "Contoh:\n`/clip https://youtube.com/watch?v=... 01:20:00-01:20:55 Windah Kena Prank`"
            )
            api_post("sendMessage", {"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"})
            return

        url = args[0]
        rng = args[1]
        title = " ".join(args[2:])
        slug = f"manual_{int(time.time())}"
        
        api_post("sendMessage", {
            "chat_id": chat_id,
            "text": f"⏳ *Memproses Klip Manual...*\n• Title: *{title}*\n• Range: `{rng}`\nHarap tunggu ~1 menit...",
            "parse_mode": "Markdown"
        })
        
        # Trigger background execution clipper
        subprocess.Popen([
            sys.executable, str(ENGINE_DIR / "clipper.py"),
            "--id", slug,
            "--url", url,
            "--range", rng,
            "--title", title,
            "--streamer", "windah",
            "--duration", "55.0"
        ])

def run_bot_server():
    print("=== Luna Telegram Bot Command Center Started ===")
    register_bot_commands()
    
    last_update_id = 0
    while True:
        try:
            url = f"{API_URL}/getUpdates?offset={last_update_id + 1}&timeout=30"
            res = requests.get(url, timeout=40).json()
            if res.get("ok"):
                for item in res.get("result", []):
                    last_update_id = item["update_id"]
                    msg = item.get("message")
                    if msg and "text" in msg:
                        chat_id = msg["chat"]["id"]
                        text = msg["text"]
                        print(f"[*] Received from {chat_id}: {text}")
                        handle_command(chat_id, text)
        except Exception as e:
            time.sleep(3)

if __name__ == "__main__":
    run_bot_server()
