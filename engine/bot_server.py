#!/usr/bin/env python3
"""
Luna GTA Shorts Telegram Interactive AI Command Center
High-Performance Architecture with Live Video Render Progress Tracker
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
PROGRESS_FILE = BASE_DIR / ".render_progress.txt"
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

HTTP_SESSION = requests.Session()
adapter = requests.adapters.HTTPAdapter(pool_connections=10, pool_maxsize=20, max_retries=2)
HTTP_SESSION.mount("https://", adapter)

def api_post(method, data=None, files=None):
    try:
        url = f"{API_URL}/{method}"
        if files:
            r = HTTP_SESSION.post(url, data=data, files=files, timeout=60)
        else:
            r = HTTP_SESSION.post(url, json=data, timeout=30)
        return r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}

def send_typing(chat_id):
    try:
        HTTP_SESSION.post(f"{API_URL}/sendChatAction", json={"chat_id": chat_id, "action": "typing"}, timeout=2)
    except:
        pass

def register_bot_commands():
    commands = [
        {"command": "help", "description": "Panduan & fitur lengkap Luna AI"},
        {"command": "progress", "description": "Pantau proses render video yang sedang berjalan"},
        {"command": "status", "description": "Status auto-watcher & server"},
        {"command": "watch_on", "description": "Nyalakan pemantau live 24/7"},
        {"command": "watch_off", "description": "Matikan pemantau live"},
        {"command": "clips", "description": "Lihat daftar klip terbaru"},
        {"command": "clip", "description": "Potong manual: /clip <url> <range> <title>"}
    ]
    api_post("setMyCommands", {"commands": commands})

def is_render_active():
    """Cek apakah ada proses ffmpeg / clipper yang sedang rendering."""
    try:
        out = subprocess.check_output(["pgrep", "-f", "clipper.py|ffmpeg.*libx264"], text=True)
        return bool(out.strip())
    except subprocess.CalledProcessError:
        return False

def get_render_progress_info():
    if not is_render_active():
        return None
        
    info = {"frame": 0, "fps": "0", "speed": "0x", "out_time": "00:00:00", "percent": 0}
    if PROGRESS_FILE.exists():
        try:
            content = PROGRESS_FILE.read_text()
            data = {}
            for line in content.splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    data[k.strip()] = v.strip()
                    
            frame = int(data.get("frame", 0))
            fps = data.get("fps", "0")
            speed = data.get("speed", "1x")
            out_time = data.get("out_time", "00:00:00").split(".")[0]
            
            # Asumsi standar video shorts 50s @ 60fps = 3000 frames
            total_frames = 3000
            percent = min(99, int((frame / total_frames) * 100))
            
            info.update({
                "frame": frame,
                "fps": fps,
                "speed": speed,
                "out_time": out_time,
                "percent": percent
            })
        except Exception:
            pass
    return info

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
    send_typing(chat_id)
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
                    {"text": "⏳ Cek Progress", "callback_data": "cmd:progress"},
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
            "text": f"⏳ *Memulai Produksi Video*\n• Gaya: *{style.upper()}*\n• Timestamp: `{t_point}`\n\nKetik `/progress` atau klik tombol di bawah untuk pantau render:",
            "parse_mode": "Markdown",
            "reply_markup": {
                "inline_keyboard": [[{"text": "⏳ Cek Progress Live", "callback_data": "cmd:progress"}]]
            }
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
        
        # Bersihkan file progress lama
        PROGRESS_FILE.unlink(missing_ok=True)
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
    elif data == "cmd:progress":
        handle_command(chat_id, "/progress")
    elif data == "cmd:clips":
        handle_command(chat_id, "/clips")
    elif data == "cmd:watch_on":
        handle_command(chat_id, "/watch_on")
    elif data == "cmd:watch_off":
        handle_command(chat_id, "/watch_off")

def handle_command(chat_id, text):
    send_typing(chat_id)
    parts = text.strip().split()
    cmd = parts[0].lower().split('@')[0]
    args = parts[1:]

    if cmd == "/progress":
        prog = get_render_progress_info()
        if not prog:
            msg = (
                "☕ *STATUS RENDER: IDLE*\n\n"
                "Saat ini tidak ada video yang sedang diproses.\n"
                "Semua antrian render selesai!"
            )
            keyboard = {
                "inline_keyboard": [
                    [{"text": "🎬 Lihat Klip Terbaru", "callback_data": "cmd:clips"},
                     {"text": "🌐 Buka Portal", "url": "https://8080-agq23kqdsijuyyvfkrqpswhfru.instabox.tech/clips/"}]
                ]
            }
        else:
            pct = prog["percent"]
            bar_len = 10
            filled = int((pct / 100) * bar_len)
            bar = "█" * filled + "░" * (bar_len - filled)
            
            msg = (
                "⚙️ *PROGRES RENDER VIDEO LIVE:*\n\n"
                f"Status: `Rendering 1080x1920 @ 60fps`\n"
                f"`[{bar}]` *{pct}%*\n\n"
                f"• Frame: `{prog['frame']} / 3000`\n"
                f"• Kecepatan: `{prog['fps']} fps ({prog['speed']})`\n"
                f"• Waktu Terproses: `{prog['out_time']}`\n\n"
                "_(Klik tombol Refresh untuk update status)_"
            )
            keyboard = {
                "inline_keyboard": [
                    [{"text": "🔄 Refresh Progress", "callback_data": "cmd:progress"}]
                ]
            }
        api_post("sendMessage", {"chat_id": chat_id, "text": msg, "parse_mode": "Markdown", "reply_markup": keyboard})

    elif cmd in ("/start", "/help"):
        msg = (
            "🤖 *LUNA AI CONTENT STUDIO - COMMAND CENTER*\n\n"
            "✨ *Fitur Chat Bahasa Alami*\n"
            "Ketik instruksi santai apa saja:\n"
            "• _\"Cariin momen pas Windah ngaku Jason\"_\n"
            "• _\"Potongin bagian parasut dong\"_\n"
            "• _\"Bikinin caption buat konten mandi\"_\n\n"
            "⚡ *Perintah Cepat:* \n"
            "• `/progress` - Cek proses render video saat ini\n"
            "• `/status` - Cek status watcher & server\n"
            "• `/watch_on` - Aktifkan auto-watcher live\n"
            "• `/watch_off` - Matikan auto-watcher\n"
            "• `/clips` - Lihat 5 klip terbaru di portal\n"
            "• `/clip <url> <range> <title>` - Potong manual cepat"
        )
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "⏳ Cek Progress", "callback_data": "cmd:progress"},
                    {"text": "📊 Status Server", "callback_data": "cmd:status"}
                ],
                [
                    {"text": "🔴 Watcher ON", "callback_data": "cmd:watch_on"},
                    {"text": "🎬 Klip Terbaru", "callback_data": "cmd:clips"}
                ],
                [
                    {"text": "🌐 Buka Web Portal", "url": "https://8080-agq23kqdsijuyyvfkrqpswhfru.instabox.tech/clips/"}
                ]
            ]
        }
        api_post("sendMessage", {"chat_id": chat_id, "text": msg, "parse_mode": "Markdown", "reply_markup": keyboard})

    elif cmd == "/status":
        running, pid = is_watcher_running()
        status_text = f"🟢 *AKTIF* (PID: `{pid}`)" if running else "🔴 *NONAKTIF*"
        render_text = "⚙️ *Sedang Render Video...*" if is_render_active() else "☕ *IDLE (Siap)*"
        
        total_clips = 0
        if (WEB_DIR / "files").exists():
            total_clips = len(list((WEB_DIR / "files").glob("*")))
            
        msg = (
            "📊 *STATUS SISTEM LUNA AI*\n\n"
            f"• Engine Render: {render_text}\n"
            f"• Auto-Watcher: {status_text}\n"
            f"• Target Default: `Windah Basudara`\n"
            f"• Total Klip di Portal: `{total_clips} klip`\n"
            f"• Output Format: `1080x1920 60 FPS (Faststart)`\n\n"
            "Gunakan tombol di bawah untuk kontrol cepat:"
        )
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "⏳ Cek Progress Video", "callback_data": "cmd:progress"},
                    {"text": "🔴 Watcher ON" if not running else "🛑 Watcher OFF", 
                     "callback_data": "cmd:watch_on" if not running else "cmd:watch_off"}
                ],
                [
                    {"text": "🌐 Buka Portal Web", "url": "https://8080-agq23kqdsijuyyvfkrqpswhfru.instabox.tech/clips/"}
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
        
        PROGRESS_FILE.unlink(missing_ok=True)
        api_post("sendMessage", {
            "chat_id": chat_id, 
            "text": f"⏳ Memproses klip *{title}*...\nKetik `/progress` untuk cek status render.",
            "parse_mode": "Markdown",
            "reply_markup": {"inline_keyboard": [[{"text": "⏳ Cek Progress", "callback_data": "cmd:progress"}]]}
        })
        subprocess.Popen([
            sys.executable, str(ENGINE_DIR / "clipper.py"),
            "--id", slug, "--url", url, "--range", rng, "--title", title, "--streamer", "windah", "--duration", "55.0"
        ])

def run_bot_server():
    print("=== Luna AI Telegram Command Center (Live Progress Tracking) Started ===")
    register_bot_commands()
    
    last_update_id = 0
    while True:
        try:
            url = f"{API_URL}/getUpdates?offset={last_update_id + 1}&timeout=30"
            res = HTTP_SESSION.get(url, timeout=40).json()
            if res.get("ok"):
                for item in res.get("result", []):
                    last_update_id = item["update_id"]
                    
                    if "callback_query" in item:
                        handle_callback_query(item["callback_query"])
                        continue
                        
                    msg = item.get("message")
                    if not msg:
                        continue
                        
                    chat_id = msg["chat"]["id"]
                    
                    if "text" in msg:
                        text = msg["text"]
                        print(f"[*] Message from {chat_id}: {text}")
                        if text.startswith("/"):
                            handle_command(chat_id, text)
                        else:
                            handle_text_prompt(chat_id, text)
                            
        except Exception as e:
            time.sleep(2)

if __name__ == "__main__":
    run_bot_server()
