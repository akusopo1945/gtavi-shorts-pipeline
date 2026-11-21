#!/usr/bin/env python3
"""
GTA Shorts Auto-Watcher & Real-time Spike Clipper Daemon
Memantau livestream YouTube -> Deteksi Chat Spike -> Auto-Clip -> Kirim Telegram
"""

import os
import sys
import time
import json
import re
import argparse
import subprocess
from datetime import datetime
from pathlib import Path
from collections import Counter

BASE_DIR = Path(__file__).resolve().parent.parent
ENGINE_DIR = BASE_DIR / "engine"
JOBS_DIR = BASE_DIR / "jobs"
COOKIES_PATH = Path("/data/home/Downloads/www.youtube.com_cookies.txt")

sys.path.insert(0, str(ENGINE_DIR))
from telegram_bot import send_message, send_video

# Kata kunci reaksi emosional penonton Indonesia & global
HYPE_PATTERN = re.compile(
    r"(?i:wkwk|ngakak|kocak|anjir|anjay|parah|mampus|rusuh|baper|bocil|mati|lmao|kekw|lol|omg|no way)|\bW+\b|[💀😂🤣😭🔥]"
)
NOISE_PATTERN = re.compile(
    r"(?i:giveaway|sponsor|subscribe|discord\.gg|https?://|promo code|follow me)"
)
WORD_PATTERN = re.compile(r"[\w']{2,}|[💀😂🤣😭🔥]")

CHANNELS = {
    "windah": {
        "name": "Windah Basudara",
        "url": "https://www.youtube.com/@windahbasudara/live",
        "streamer_id": "windah"
    },
    "tara": {
        "name": "Tara Arts Game Indonesia",
        "url": "https://www.youtube.com/@TaraArtsGame/live",
        "streamer_id": "tara"
    }
}

def check_live_status(channel_url):
    """Cek apakah channel sedang LIVE via yt-dlp secara non-intrusif."""
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--print", "%(is_live)s|%(id)s|%(title)s",
        "--skip-download",
        channel_url
    ]
    if COOKIES_PATH.exists():
        cmd.extend(["--cookies", str(COOKIES_PATH)])
    if os.path.exists("/usr/local/bin/node"):
        cmd.extend(["--js-runtimes", "node:/usr/local/bin/node"])

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
        out = res.stdout.strip().split('\n')[-1]
        if "|" in out:
            is_live, video_id, title = out.split("|", 2)
            if is_live.lower() in ("true", "1"):
                return True, video_id, title
    except Exception as e:
        pass
    return False, None, None

def extract_chat_text(renderer):
    out = []
    for r in (renderer.get("message") or {}).get("runs", []):
        if "text" in r:
            out.append(r["text"])
        elif "emoji" in r:
            e = r["emoji"]
            out.append(e.get("emojiId") or (e.get("shortcuts") or [""])[0])
    return "".join(out).strip()

class LiveMonitor:
    def __init__(self, streamer_key, video_id, title):
        self.streamer_key = streamer_key
        self.video_id = video_id
        self.title = title
        self.watch_url = f"https://www.youtube.com/watch?v={video_id}"
        self.job_dir = JOBS_DIR / f"live_{video_id}_{int(time.time())}"
        self.job_dir.mkdir(parents=True, exist_ok=True)
        
        self.chat_pos = 0
        self.chat_buf = b""
        self.seen_msg_ids = set()
        self.wgt_counter = Counter() # per unix second
        self.last_spike_time = 0
        self.cooldown_sec = 240 # jeda 4 menit antar klip
        self.clip_count = 0

    def start_chat_stream(self):
        """Menjalankan background process yt-dlp untuk mendengarkan live chat."""
        cmd = [
            sys.executable, "-m", "yt_dlp",
            "--skip-download",
            "--write-subs",
            "--sub-langs", "live_chat",
            "-o", str(self.job_dir / "chat"),
            self.watch_url
        ]
        if COOKIES_PATH.exists():
            cmd.extend(["--cookies", str(COOKIES_PATH)])
        if os.path.exists("/usr/local/bin/node"):
            cmd.extend(["--js-runtimes", "node:/usr/local/bin/node"])

        self.proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"[*] Chat stream listener started (PID: {self.proc.pid})")

    def poll_chat(self):
        chat_files = sorted(self.job_dir.glob("chat.live_chat.json*"))
        for cf in chat_files:
            try:
                with open(cf, "rb") as fh:
                    fh.seek(self.chat_pos)
                    data = fh.read()
            except OSError:
                continue
            if not data:
                continue
            self.chat_pos += len(data)
            self.chat_buf += data
            *lines, rest = self.chat_buf.split(b"\n")
            self.chat_buf = rest
            
            for ln in lines:
                try:
                    acts = json.loads(ln)["replayChatItemAction"]["actions"]
                except Exception:
                    continue
                for a in acts:
                    r = (((a.get("addChatItemAction") or {}).get("item")) or {}).get("liveChatTextMessageRenderer")
                    if not r or r.get("id") in self.seen_msg_ids:
                        continue
                    self.seen_msg_ids.add(r.get("id"))
                    txt = extract_chat_text(r)
                    if not txt or NOISE_PATTERN.search(txt):
                        continue
                    now_s = int(time.time())
                    # Hype words dapat bobot 3 poin, chat biasa 1 poin
                    weight = 3 if HYPE_PATTERN.search(txt) else 1
                    self.wgt_counter[now_s] += weight

    def check_spike(self):
        now_s = int(time.time())
        if now_s - self.last_spike_time < self.cooldown_sec:
            return False, 0
            
        # Analisis 10 detik terakhir vs baseline 60 detik sebelumnya
        recent_10s = sum(self.wgt_counter.get(s, 0) for s in range(now_s - 10, now_s))
        baseline_60s = sum(self.wgt_counter.get(s, 0) for s in range(now_s - 70, now_s - 10))
        avg_baseline_10s = (baseline_60s / 6) if baseline_60s > 0 else 5
        
        ratio = recent_10s / max(1.0, avg_baseline_10s)
        # Spike terdeteksi jika chat tawa melonjak 2.8x lipat dan minimal ada 15 poin hype
        if ratio >= 2.8 and recent_10s >= 15:
            self.last_spike_time = now_s
            return True, ratio
        return False, 0

    def trigger_auto_clip(self, ratio):
        self.clip_count += 1
        clip_id = f"{self.streamer_key}_live_clip_{self.clip_count}_{int(time.time())}"
        print(f"\n[🔥] SPIKE DETECTED! (Ratio: {ratio:.1f}x) Producing clip: {clip_id}")
        
        send_message(
            f"🔥 *[MOMEN VIRAL LIVE TERDETEKSI!]*\n"
            f"Streamer: *{self.title}*\n"
            f"Lonjakan Tawa: `{ratio:.1f}x dari baseline normal`\n"
            f"⏳ Merekam 55 detik stream & render 1080p 60fps..."
        )
        
        clip_work = self.job_dir / clip_id
        clip_work.mkdir(parents=True, exist_ok=True)
        raw_video = clip_work / "raw.mp4"
        
        clipper_cmd = [
            sys.executable, str(ENGINE_DIR / "clipper.py"),
            "--id", clip_id,
            "--streamer", self.streamer_key,
            "--title", f"MOMEN SPONTAN LIVE GTA 6 #{self.clip_count}",
            "--duration", "55.0",
            "--summary", f"Momen viral lonjakan chat ({ratio:.1f}x) saat live stream GTA 6.",
            "--copywriting", f"Momen spontan paling bikin ngakak pas live GTA 6! Chat langsung jebol spam wkwk 😂🔥 #gta6 #shorts #gamingindo",
            "--workdir", str(clip_work)
        ]
        
        try:
            # 1. Dapatkan live stream URL (HLS m3u8) langsung via yt-dlp
            print("[*] Resolving live stream HLS URL via yt-dlp...")
            get_url_cmd = [
                sys.executable, "-m", "yt_dlp",
                "-f", "301/300/best[ext=mp4]/best",
                "-g", self.watch_url
            ]
            if COOKIES_PATH.exists():
                get_url_cmd.extend(["--cookies", str(COOKIES_PATH)])
            if os.path.exists("/usr/local/bin/node"):
                get_url_cmd.extend(["--js-runtimes", "node:/usr/local/bin/node"])
                
            stream_url = subprocess.check_output(get_url_cmd, text=True, timeout=30).strip()
            
            # 2. Rekam 55 detik stream via FFmpeg copy
            print(f"[*] Recording 55 seconds live slice to {raw_video}...")
            ffmpeg_dl_cmd = [
                "ffmpeg", "-y",
                "-t", "55",
                "-i", stream_url,
                "-c", "copy",
                str(raw_video)
            ]
            subprocess.run(ffmpeg_dl_cmd, check=True, timeout=90)
            print("[+] Live slice successfully recorded!")
            
            # 3. Jalankan render engine clipper
            print("[*] Running declarative clipper pipeline...")
            subprocess.run(clipper_cmd, check=True, timeout=180)
            
            rendered_video = clip_work / f"{clip_id}_rendered.mp4"
            thumb_path = clip_work / "thumb.jpg"
            
            if rendered_video.exists():
                send_video(
                    str(rendered_video),
                    caption=f"🎬 *Momen Live #{self.clip_count} Berhasil Diproduksi!* 🔥\n\n"
                            f"📌 Title: MOMEN SPONTAN LIVE GTA 6 #{self.clip_count}\n"
                            f"⏱️ Resolusi: 1080x1920 (60 FPS)\n"
                            f"🔗 Web: https://8080-agq23kqdsijuyyvfkrqpswhfru.instabox.tech/clips/",
                    thumb_path=str(thumb_path) if thumb_path.exists() else None
                )
                print(f"[+] Klip #{self.clip_count} berhasil dikirim ke Telegram!")
        except Exception as e:
            print(f"[!] Error producing auto-clip: {e}")
            send_message(f"⚠️ Gagal render auto-clip #{self.clip_count}: `{e}`")

    def stop(self):
        if hasattr(self, 'proc') and self.proc:
            self.proc.terminate()
            self.proc.wait()

def run_watcher_loop(streamer_target="windah"):
    cfg = CHANNELS.get(streamer_target, CHANNELS["windah"])
    print(f"=== Auto-Watcher Daemon Active: {cfg['name']} ===")
    send_message(f"🤖 *Auto-Watcher Luna Aktif!*\\nMemantau livestream: *{cfg['name']}* secara real-time.")
    
    active_monitor = None
    try:
        while True:
            if not active_monitor:
                is_live, vid_id, title = check_live_status(cfg["url"])
                if is_live:
                    print(f"\n[🔴 LIVE FOUND] {title} ({vid_id})")
                    send_message(
                        f"🔴 *STREAMER SEDANG LIVE!* 🎮\n"
                        f"Judul: *{title}*\n"
                        f"🚀 Menjalankan detektor tawa real-time..."
                    )
                    active_monitor = LiveMonitor(streamer_target, vid_id, title)
                    active_monitor.start_chat_stream()
                else:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] {cfg['name']} is offline. Polling in 60s...", end="\r")
                    time.sleep(60)
            else:
                active_monitor.poll_chat()
                is_spike, ratio = active_monitor.check_spike()
                if is_spike:
                    active_monitor.trigger_auto_clip(ratio)
                    
                time.sleep(2)
    except KeyboardInterrupt:
        print("\nStopping watcher...")
        if active_monitor:
            active_monitor.stop()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--streamer", default="windah", choices=["windah", "tara"])
    args = parser.parse_args()
    run_watcher_loop(args.streamer)
