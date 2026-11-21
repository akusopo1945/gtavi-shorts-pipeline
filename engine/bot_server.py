#!/usr/bin/env python3
"""
Luna GTA Shorts Telegram Interactive AI Command Center
Ringan & Cepat (Tanpa dependensi Voice Note / Audio Loading di Bot Loop)
Mendukung:
- Natural Language AI Assistant
- Interactive Inline Keyboard Buttons
- Watcher Daemon On/Off via Chat
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

sys.path.insert(0, str(ENGINE_DIR))
import ai_brain

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
    commands = [
        {"command": "help", "description": "Panduan & fitur lengkap Luna AI"},
        {"command": "status", "description": "Status auto-watcher & server"},
        {"command": "watch_on", "description": "Nyalakan pemantau live 24/7"},
        {"command": "watch_off", "description": "Matikan pemantau live"},
        {"command": "clips", "description": "Lihat daftar klip terbaru"},
        {"command": "clip", "description": "Potong manual: /clip <url> <range> <title>"}
    ]
    api_post("setMyCommands", {"commands": commands})

def is_watcher_running():
    if not PID_FILE.exists():
        return False, None
    try:
        pid = int(PID_FILE.read_text().strip())
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
    cmd = [sys.executable, str(ENGINE_DIR / "watcher.py"), "--streamer", streamer]
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

def handle_text_prompt(chat_id, user_text):
    intent_data = ai_brain.parse_user_intent(user_text)
    reply_text, target_time = ai_brain.format_ai_response(intent_data)
    
    keyboard = None
    if intent_data["intent"] == "create_clip" and target_time:
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "🎬 Render Gaya Live Chat", "callback_data": f"render:livechat:{target_time}"},
                    {"text": "⚡ Render Gaya Clean", "callback_data": f"render:clean:{target_time}"}
                ],
                [
                    {"text": "📊 Cek Status Server", "callback_data": "cmd:status"},
                    {"text": "🌐 Buka Portal Web", "url": "https://8080-agq23kqdsijuyyvfkrqpswhfru.instabox.tech/clips/"}
                ]
            ]
        }
        
    payload = {
        "chat_id": chat_id,
        "text": reply_text,
        "parse_mode": "Markdown"
    }
    if keyboard:
        payload["reply_markup"] = keyboard
        
    api_post("sendMessage", payload)

def handle_callback_query(cq):
    cq_id = cq["id"]
    chat_id = cq["message"]["chat"]["id"]
    data = cq["data"]
    
    api_post("answerCallbackQuery", {"callback_query_id": cq_id, "text": "Perintah diterima!"})
    
    if data.startswith("render:"):
        _, style, t_point = data.split(":")
        api_post("sendMessage", {
            "chat_id": chat_id,
            "text": f"⏳ *Memulai Produksi AI Clipper*\n• Gaya: *{style.upper()}*\n• Timestamp: `{t_point}`\n\nSedang memotong dan merender 1080p 60fps...",
            "parse_mode": "Markdown"
        })
        
        slug = f"ai_{style}_{int(time.time())}"
        p = t_point.split(":")
        if len(p) == 2:
            s_start = int(p[0]) * 60 + int(float(p[1]))
        else:
            s_start = int(p[0]) * 3600 + int(p[1]) * 60 + int(float(p[2]))
        s_end = s_start + 50
        
        m_s, sec_s = divmod(s_start, 60)
        h_s, m_s = divmod(m_s, 60)
        m_e, sec_e = divmod(s_end, 60)
        h_e, m_e = divmod(m_e, 60)
        range_str = f"{h_s:02d}:{m_s:02d}:{sec_s:02d}-{h_e:02d}:{m_e:02d}:{sec_e:02d}"
        
        subprocess.Popen([
            sys.executable, str(ENGINE_DIR / "clipper.py"),
            "--id", slug,
            "--url", "https://www.youtube.com/watch?v=03qhcshfeMY",
            "--range", range_str,
            "--title", f"MOMEN SPONTAN GTA 6 ({t_point})",
            "--streamer", "windah",
            "--duration", "50.0"
        ])
    elif data == "cmd:status":
        handle_command(chat_id, "/status")
    elif data == "cmd:clips":
        handle_command(chat_id, "/clips")
    elif data == "cmd:watch_on":
        handle_command(chat_id, "/watch_on")
    elif data == "cmd:watch_off":
        handle_command(chat_id, "/watch_off")

def handle_command(chat_id, text):
    parts = text.strip().split()
    cmd = parts[0].lower().split('@')[0]
    args = parts[1:]

    if cmd in ("/start", "/help"):
        msg = (
            "🤖 *LUNA AI CONTENT STUDIO - COMMAND CENTER*\n\n"
            "✨ *Fitur Chat Bahasa Alami*\n"
            "Ketik instruksi santai apa saja:\n"
            "• _\"Cariin momen pas Windah ngaku Jason\"_\n"
            "• _\"Potongin bagian parasut dong\"_\n"
            "• _\"Bikinin caption buat konten mandi\"_\n\n"
            "⚡ *Perintah Cepat:* \n"
            "• `/status` - Cek watcher & storage server\n"
            "• `/watch_on` - Aktifkan auto-watcher live\n"
            "• `/watch_off` - Matikan auto-watcher\n"
            "• `/clips` - Lihat 5 klip terbaru di portal\n"
            "• `/clip <url> <range> <title>` - Potong manual cepat"
        )
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "📊 Status Server", "callback_data": "cmd:status"},
                    {"text": "🎬 Klip Terbaru", "callback_data": "cmd:clips"}
                ],
                [
                    {"text": "🔴 Nyalakan Watcher", "callback_data": "cmd:watch_on"},
                    {"text": "🌐 Buka Web Portal", "url": "https://8080-agq23kqdsijuyyvfkrqpswhfru.instabox.tech/clips/"}
                ]
            ]
        }
        api_post("sendMessage", {"chat_id": chat_id, "text": msg, "parse_mode": "Markdown", "reply_markup": keyboard})

    elif cmd == "/status":
        running, pid = is_watcher_running()
        status_text = f"🟢 *AKTIF* (PID: `{pid}`)" if running else "🔴 *NONAKTIF*"
        
        total_clips = 0
        if (WEB_DIR / "files").exists():
            total_clips = len(list((WEB_DIR / "files").glob("*")))
            
        msg = (
            "📊 *STATUS SISTEM LUNA AI*\n\n"
            f"• Auto-Watcher: {status_text}\n"
            f"• AI Brain: 🟢 *Active (Lightweight NLP Matcher)*\n"
            f"• Target Default: `Windah Basudara`\n"
            f"• Total Klip di Portal: `{total_clips} klip`\n"
            f"• Output Format: `1080x1920 60 FPS (Faststart)`\n\n"
            "Gunakan tombol di bawah untuk kontrol cepat:"
        )
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "🔴 Nyalakan Watcher" if not running else "🛑 Matikan Watcher", 
                     "callback_data": "cmd:watch_on" if not running else "cmd:watch_off"},
                    {"text": "🌐 Lihat Portal", "url": "https://8080-agq23kqdsijuyyvfkrqpswhfru.instabox.tech/clips/"}
                ]
            ]
        }
        api_post("sendMessage", {"chat_id": chat_id, "text": msg, "parse_mode": "Markdown", "reply_markup": keyboard})

    elif cmd == "/watch_on":
        streamer = args[0] if args else "windah"
        success, info = start_watcher(streamer)
        msg = f"🚀 *Watcher Aktif!* (Target: {streamer.upper()})" if success else f"⚠️ {info}"
        api_post("sendMessage", {"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"})

    elif cmd == "/watch_off":
        success, info = stop_watcher()
        api_post("sendMessage", {"chat_id": chat_id, "text": f"🛑 {info}", "parse_mode": "Markdown"})

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
            msg = "⚠️ Format: `/clip <url> <range> <title>`"
            api_post("sendMessage", {"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"})
            return

        url, rng = args[0], args[1]
        title = " ".join(args[2:])
        slug = f"manual_{int(time.time())}"
        api_post("sendMessage", {"chat_id": chat_id, "text": f"⏳ Memproses klip *{title}*...", "parse_mode": "Markdown"})
        subprocess.Popen([
            sys.executable, str(ENGINE_DIR / "clipper.py"),
            "--id", slug, "--url", url, "--range", rng, "--title", title, "--streamer", "windah", "--duration", "55.0"
        ])

def run_bot_server():
    print("=== Luna AI Telegram Command Center (Lightweight) Started ===")
    register_bot_commands()
    
    last_update_id = 0
    while True:
        try:
            url = f"{API_URL}/getUpdates?offset={last_update_id + 1}&timeout=30"
            res = requests.get(url, timeout=40).json()
            if res.get("ok"):
                for item in res.get("result", []):
                    last_update_id = item["update_id"]
                    
                    # 1. Handle tombol inline (Callback Query)
                    if "callback_query" in item:
                        handle_callback_query(item["callback_query"])
                        continue
                        
                    msg = item.get("message")
                    if not msg:
                        continue
                        
                    chat_id = msg["chat"]["id"]
                    
                    # 2. Abaikan voice / audio jika dikirim
                    if "voice" in msg or "audio" in msg:
                        api_post("sendMessage", {
                            "chat_id": chat_id, 
                            "text": "ℹ️ *Fitur voice note dinonaktifkan*. Silakan ketik perintah langsung lewat teks chat santai atau slash command.",
                            "parse_mode": "Markdown"
                        })
                        continue
                        
                    # 3. Handle Teks
                    if "text" in msg:
                        text = msg["text"]
                        print(f"[*] Message from {chat_id}: {text}")
                        if text.startswith("/"):
                            handle_command(chat_id, text)
                        else:
                            handle_text_prompt(chat_id, text)
                            
        except Exception as e:
            time.sleep(3)

if __name__ == "__main__":
    run_bot_server()
