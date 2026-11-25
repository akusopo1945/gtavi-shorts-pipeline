#!/usr/bin/env python3
"""
Luna GTA Shorts Telegram Interactive AI Command Center
High-Performance Architecture with Live Multi-Stage Progress Tracker & Auto Notifications
"""

import os
import sys
import time
import json
import signal
import threading
import subprocess
import traceback
import requests
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ENGINE_DIR = BASE_DIR / "engine"
PID_FILE = BASE_DIR / ".watcher.pid"
ENV_FILE = BASE_DIR / ".env"
PROGRESS_FILE = BASE_DIR / ".render_progress.txt"
STAGE_FILE = BASE_DIR / ".job_stage.json"
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
PORTAL_URL = ENV.get("PORTAL_URL", "https://your-portal-host/clips/")

HTTP_SESSION = requests.Session()
adapter = requests.adapters.HTTPAdapter(pool_connections=10, pool_maxsize=20, max_retries=2)
HTTP_SESSION.mount("https://", adapter)

# Background Job Tracking
ACTIVE_JOB = {
    "proc": None,
    "slug": None,
    "title": None,
    "chat_id": None,
    "log_fp": None
}

def api_post(method, data=None, files=None):
    try:
        url = f"{API_URL}/{method}"
        if files:
            r = HTTP_SESSION.post(url, data=data, files=files, timeout=60)
        else:
            r = HTTP_SESSION.post(url, json=data, timeout=30)
        return r.json()
    except Exception as e:
        print(f"[!] api_post error ({method}): {e}")
        return {"ok": False, "error": str(e)}

def send_typing(chat_id):
    try:
        HTTP_SESSION.post(f"{API_URL}/sendChatAction", json={"chat_id": chat_id, "action": "typing"}, timeout=2)
    except:
        pass

def register_bot_commands():
    commands = [
        {"command": "help", "description": "Panduan & fitur lengkap Luna AI"},
        {"command": "progress", "description": "Pantau proses render video real-time"},
        {"command": "status", "description": "Status auto-watcher & server"},
        {"command": "watch_on", "description": "Nyalakan pemantau live 24/7"},
        {"command": "watch_off", "description": "Matikan pemantau live"},
        {"command": "clips", "description": "Lihat daftar klip terbaru"},
        {"command": "clip", "description": "Potong manual: /clip <url> <range> <title>"}
    ]
    api_post("setMyCommands", {"commands": commands})

def is_render_active():
    """Cek apakah proses render clipper / ffmpeg / yt_dlp sedang berjalan."""
    try:
        out = subprocess.check_output(["pgrep", "-f", "clipper.py|ffmpeg.*libx264|yt_dlp"], text=True)
        return bool(out.strip())
    except subprocess.CalledProcessError:
        return False

def get_render_progress_info():
    if not is_render_active():
        return None
        
    stage_data = {}
    if STAGE_FILE.exists():
        try:
            stage_data = json.loads(STAGE_FILE.read_text(encoding="utf-8"))
        except:
            pass

    stage = stage_data.get("stage", "starting")
    percent = stage_data.get("percent", 10)
    detail = stage_data.get("detail", "Sedang memproses video...")
    title = stage_data.get("title", "Klip GTA 6")

    info = {
        "title": title,
        "stage": stage,
        "detail": detail,
        "percent": percent,
        "frame": 0,
        "fps": "0",
        "speed": "0x",
        "out_time": "00:00:00"
    }

    if PROGRESS_FILE.exists():
        try:
            content = PROGRESS_FILE.read_text(encoding="utf-8")
            data = {}
            for line in content.splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    data[k.strip()] = v.strip()
                    
            frame = int(data.get("frame", 0))
            fps = data.get("fps", "0")
            speed = data.get("speed", "1x")
            out_time = data.get("out_time", "00:00:00").split(".")[0]
            
            # Asumsi video shorts 50 detik @ 60fps = 3000 frames
            total_frames = 3000
            calc_pct = min(95, max(45, int(45 + (frame / total_frames) * 50)))
            
            info.update({
                "frame": frame,
                "fps": fps,
                "speed": speed,
                "out_time": out_time,
                "percent": calc_pct,
                "stage": "rendering",
                "detail": f"Encoding frame {frame}/{total_frames} ({fps} fps, speed {speed})"
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

def job_monitor_thread():
    """Background monitor yang memeriksa status render dan kirim notifikasi Telegram saat selesai."""
    global ACTIVE_JOB
    while True:
        try:
            proc = ACTIVE_JOB.get("proc")
            if proc is not None:
                ret = proc.poll()
                if ret is not None:
                    # Process completed
                    slug = ACTIVE_JOB.get("slug")
                    title = ACTIVE_JOB.get("title")
                    chat_id = ACTIVE_JOB.get("chat_id")
                    
                    if ACTIVE_JOB.get("log_fp"):
                        try:
                            ACTIVE_JOB["log_fp"].close()
                        except:
                            pass
                            
                    ACTIVE_JOB = {"proc": None, "slug": None, "title": None, "chat_id": None, "log_fp": None}
                    
                    if ret == 0:
                        print(f"[+] Job {slug} finished successfully!")
                        msg = (
                            f"🎉 *KLIP BERHASIL DIRENDER & TAYANG!*\\n\\n"
                            f"🎬 *{title}*\\n"
                            f"⏱️ Resolusi: `1080x1920 (60 FPS)`\\n"
                            f"⚡ Faststart: `Instant Playback Ready`\\n\\n"
                            f"🔗 *Tonton di Web Portal:*\\n{PORTAL_URL}"
                        )
                        keyboard = {
                            "inline_keyboard": [
                                [{"text": "🌐 Nonton di Portal Web", "url": PORTAL_URL}],
                                [{"text": "🎬 Klip Terbaru", "callback_data": "cmd:clips"}]
                            ]
                        }
                    else:
                        print(f"[!] Job {slug} failed with exit code {ret}!")
                        # Read error from log
                        err_snippet = "Terjadi kesalahan pada pipeline."
                        log_file = BASE_DIR / "jobs" / f"{slug}_run.log"
                        if log_file.exists():
                            lines = log_file.read_text(encoding="utf-8", errors="ignore").splitlines()
                            err_snippet = "\n".join(lines[-6:]) if lines else err_snippet
                            
                        msg = (
                            f"⚠️ *Render Gagal (Exit Code: {ret})*\\n\\n"
                            f"🎬 *{title}*\\n\\n"
                            f"```\n{err_snippet[-400:]}\n```"
                        )
                        keyboard = {
                            "inline_keyboard": [[{"text": "📊 Status Server", "callback_data": "cmd:status"}]]
                        }
                        
                    if chat_id:
                        api_post("sendMessage", {
                            "chat_id": chat_id,
                            "text": msg,
                            "parse_mode": "Markdown",
                            "reply_markup": keyboard
                        })
                        
        except Exception as e:
            print(f"[!] Exception in job_monitor_thread: {e}")
            traceback.print_exc()
            
        time.sleep(3)

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
                    {"text": "🌐 Buka Portal Web", "url": PORTAL_URL}
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
    global ACTIVE_JOB
    cq_id = cq["id"]
    chat_id = cq["message"]["chat"]["id"]
    data = cq["data"]
    
    print(f"[*] CallbackQuery from {chat_id}: {data}")
    api_post("answerCallbackQuery", {"callback_query_id": cq_id, "text": "Perintah diterima!"})
    
    try:
        if data.startswith("render:"):
            # Format: render:<style>:<time_point>
            parts = data.split(":", 2)
            style = parts[1]
            t_point = parts[2] if len(parts) > 2 else "00:42:15"
            
            p = t_point.split(":")
            if len(p) == 1:
                s_start = int(float(p[0]))
            elif len(p) == 2:
                s_start = int(p[0]) * 60 + int(float(p[1]))
            elif len(p) == 3:
                s_start = int(p[0]) * 3600 + int(p[1]) * 60 + int(float(p[2]))
            else:
                s_start = 2535
                
            s_end = s_start + 50
            m_s, sec_s = divmod(s_start, 60)
            h_s, m_s = divmod(m_s, 60)
            m_e, sec_e = divmod(s_end, 60)
            h_e, m_e = divmod(m_e, 60)
            range_str = f"{h_s:02d}:{m_s:02d}:{sec_s:02d}-{h_e:02d}:{m_e:02d}:{sec_e:02d}"
            
            slug = f"ai_{style}_{int(time.time())}"
            title = f"MOMEN GTA 6 ({t_point})"
            
            # Initial stage info
            STAGE_FILE.write_text(json.dumps({
                "slug": slug,
                "title": title,
                "stage": "starting",
                "percent": 5,
                "detail": "Menyiapkan worker & dependensi...",
                "chat_id": chat_id,
                "started_at": time.time()
            }, indent=2), encoding="utf-8")
            
            PROGRESS_FILE.unlink(missing_ok=True)
            
            api_post("sendMessage", {
                "chat_id": chat_id,
                "text": (
                    f"🚀 *MEMULAI PRODUKSI KLIP*\\n\\n"
                    f"• Gaya: *{style.upper()}*\\n"
                    f"• Timestamp: `{t_point}` (`{range_str}`)\\n\\n"
                    f"⏳ *Tahapan Pipeline:*\\n"
                    f"1️⃣ Unduh Slice Video (yt-dlp)\\n"
                    f"2️⃣ AI Transkripsi Subtitle (Whisper)\\n"
                    f"3️⃣ Render 1080p 60fps (FFmpeg)\\n"
                    f"4️⃣ Auto-Publish ke Portal Web\\n\\n"
                    f"Bot akan otomatis mengirim notifikasi ketika selesai! Atau pantau langsung via tombol di bawah:"
                ),
                "parse_mode": "Markdown",
                "reply_markup": {
                    "inline_keyboard": [
                        [{"text": "⏳ Pantau Progress Real-Time", "callback_data": "cmd:progress"}],
                        [{"text": "🌐 Buka Portal Web", "url": PORTAL_URL}]
                    ]
                }
            })
            
            (BASE_DIR / "jobs").mkdir(parents=True, exist_ok=True)
            log_path = BASE_DIR / "jobs" / f"{slug}_run.log"
            log_fp = open(log_path, "w", encoding="utf-8")
            
            cmd = [
                sys.executable, "-u", str(ENGINE_DIR / "clipper.py"),
                "--id", slug,
                "--url", "https://www.youtube.com/watch?v=03qhcshfeMY",
                "--range", range_str,
                "--title", title,
                "--streamer", "windah",
                "--duration", "50.0"
            ]
            
            proc = subprocess.Popen(cmd, stdout=log_fp, stderr=log_fp, cwd=str(BASE_DIR))
            ACTIVE_JOB = {
                "proc": proc,
                "slug": slug,
                "title": title,
                "chat_id": chat_id,
                "log_fp": log_fp
            }
            print(f"[+] Clipper spawned (PID: {proc.pid}, slug: {slug})")
            
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
            
    except Exception as e:
        print(f"[!] Error in handle_callback_query: {e}")
        traceback.print_exc()
        api_post("sendMessage", {
            "chat_id": chat_id,
            "text": f"⚠️ Terjadi error saat mengeksekusi aksi: `{e}`",
            "parse_mode": "Markdown"
        })

def handle_command(chat_id, text):
    global ACTIVE_JOB
    send_typing(chat_id)
    parts = text.strip().split()
    cmd = parts[0].lower().split('@')[0]
    args = parts[1:]

    if cmd == "/progress":
        prog = get_render_progress_info()
        if not prog:
            msg = (
                "☕ *STATUS RENDER: IDLE*\n\n"
                "Saat ini tidak ada antrian video yang sedang diproses.\n"
                "Ketik instruksi santai untuk mencari momen baru!"
            )
            keyboard = {
                "inline_keyboard": [
                    [{"text": "🎬 Lihat Klip Terbaru", "callback_data": "cmd:clips"},
                     {"text": "🌐 Buka Portal", "url": PORTAL_URL}]
                ]
            }
        else:
            pct = prog["percent"]
            bar_len = 10
            filled = int((pct / 100) * bar_len)
            bar = "█" * filled + "░" * (bar_len - filled)
            
            stage_labels = {
                "starting": "1/4 Persiapan Environment",
                "downloading": "2/4 Unduh Slice YouTube (yt-dlp)",
                "transcribing": "3/4 AI Audio Transkripsi (Whisper)",
                "rendering": "4/4 FFmpeg Render 1080x1920 60fps",
                "deploying": "Publish ke Web Portal & Faststart"
            }
            stage_name = stage_labels.get(prog["stage"], prog["stage"].capitalize())
            
            msg = (
                "⚙️ *PROGRES RENDER VIDEO LIVE:*\n\n"
                f"• Target: *{prog['title']}*\n"
                f"• Tahap: `{stage_name}`\n"
                f"• Status: _{prog['detail']}_\n\n"
                f"`[{bar}]` *{pct}%*\n"
            )
            if prog["frame"] > 0:
                msg += f"• Encoding: `{prog['frame']}/3000 frames` (`{prog['fps']} fps`, `{prog['speed']}`)\n"
                msg += f"• Waktu Terproses: `{prog['out_time']}`\n"
                
            msg += "\n_(Klik tombol Refresh untuk melihat pergerakan live)_"
            keyboard = {
                "inline_keyboard": [
                    [{"text": "🔄 Refresh Progress", "callback_data": "cmd:progress"}],
                    [{"text": "🌐 Portal Web", "url": PORTAL_URL}]
                ]
            }
        api_post("sendMessage", {"chat_id": chat_id, "text": msg, "parse_mode": "Markdown", "reply_markup": keyboard})

    elif cmd in ("/start", "/help"):
        msg = (
            "🤖 *LUNA AI CONTENT STUDIO - COMMAND CENTER*\n\n"
            "✨ *Fitur Chat Bahasa Alami*\n"
            "Ketik perintah santai apa saja:\n"
            "• _\"Cariin momen pas Windah ngaku Jason\"_\n"
            "• _\"Potongin bagian pas parasut dong\"_\n"
            "• _\"Bikinin caption buat konten mandi\"_\n\n"
            "⚡ *Perintah Cepat:*\n"
            "• `/progress` - Pantau progres render video real-time\n"
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
                    {"text": "🌐 Buka Web Portal", "url": PORTAL_URL}
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
                    {"text": "🌐 Buka Portal Web", "url": PORTAL_URL}
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
                lines.append(f"\n🔗 *Nonton di Portal*:\n{PORTAL_URL}")
                msg = "\n".join(lines)
            else:
                msg = "Belum ada daftar klip."
        else:
            msg = "Portal index.html tidak ditemukan."
        api_post("sendMessage", {"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"})

    elif cmd == "/clip":
        if len(args) < 3:
            msg = "⚠️ Format: `/clip <url> <range> <title>`\nContoh: `/clip https://youtu.be/... 00:42:10-00:43:00 WINDAH KOCAK`"
            api_post("sendMessage", {"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"})
            return

        url, rng = args[0], args[1]
        title = " ".join(args[2:])
        slug = f"manual_{int(time.time())}"
        
        STAGE_FILE.write_text(json.dumps({
            "slug": slug,
            "title": title,
            "stage": "starting",
            "percent": 5,
            "detail": "Menyiapkan worker manual...",
            "chat_id": chat_id,
            "started_at": time.time()
        }, indent=2), encoding="utf-8")
        
        PROGRESS_FILE.unlink(missing_ok=True)
        
        api_post("sendMessage", {
            "chat_id": chat_id, 
            "text": f"⏳ Memproses klip *{title}*...\nKetik `/progress` atau klik tombol di bawah untuk pantau render.",
            "parse_mode": "Markdown",
            "reply_markup": {"inline_keyboard": [[{"text": "⏳ Cek Progress", "callback_data": "cmd:progress"}]]}
        })
        
        (BASE_DIR / "jobs").mkdir(parents=True, exist_ok=True)
        log_path = BASE_DIR / "jobs" / f"{slug}_run.log"
        log_fp = open(log_path, "w", encoding="utf-8")
        
        cmd_args = [
            sys.executable, "-u", str(ENGINE_DIR / "clipper.py"),
            "--id", slug,
            "--url", url,
            "--range", rng,
            "--title", title,
            "--streamer", "windah",
            "--duration", "50.0"
        ]
        proc = subprocess.Popen(cmd_args, stdout=log_fp, stderr=log_fp, cwd=str(BASE_DIR))
        ACTIVE_JOB = {
            "proc": proc,
            "slug": slug,
            "title": title,
            "chat_id": chat_id,
            "log_fp": log_fp
        }
        print(f"[+] Manual clip spawned (PID: {proc.pid}, slug: {slug})")

def run_bot_server():
    print("=== Luna AI Telegram Command Center (Live Progress Tracking) Started ===")
    register_bot_commands()
    
    # Start background job monitor thread
    monitor = threading.Thread(target=job_monitor_thread, daemon=True)
    monitor.start()
    
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
            print(f"[!] Top-level loop error: {e}")
            traceback.print_exc()
            time.sleep(2)

if __name__ == "__main__":
    run_bot_server()
