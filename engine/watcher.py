#!/usr/bin/env python3
"""
GTA Shorts Smart Auto-Watcher & Rolling Ring-Buffer Spike Clipper Daemon.
Live Stream -> Rolling 80s Ring Buffer + Live Chat Monitor -> Dual-Signal Spike + Context Rewind ->
Whisper + Audio Peak Auto-FX/Title/Cutout Thumbnail -> Telegram + Web Portal.
"""

import os
import sys
import time
import json
import re
import shutil
import argparse
import subprocess
from datetime import datetime
from pathlib import Path
from collections import Counter, deque

BASE_DIR = Path(__file__).resolve().parent.parent
ENGINE_DIR = BASE_DIR / "engine"
JOBS_DIR = BASE_DIR / "jobs"
COOKIES_PATH = Path("/data/home/Downloads/www.youtube.com_cookies.txt")

sys.path.insert(0, str(ENGINE_DIR))
from telegram_bot import load_env, send_message, send_video
PORTAL_URL = load_env().get("PORTAL_URL", os.getenv("PORTAL_URL", "https://your-portal-host/clips/"))

HYPE_PATTERN = re.compile(
    r"(?i:wkwk|ngakak|kocak|anjir|anjay|parah|mampus|rusuh|baper|bocil|mati|lmao|kekw|lol|omg|no way|jason|polisi|prank|scam|kualat|ngamuk)|\bW+\b|[💀😂🤣😭🔥]"
)
NOISE_PATTERN = re.compile(
    r"(?i:giveaway|sponsor|subscribe|discord\.gg|https?://|promo code|follow me)"
)

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


def yt_dlp_base_args():
    args = [sys.executable, "-m", "yt_dlp"]
    if COOKIES_PATH.exists():
        args.extend(["--cookies", str(COOKIES_PATH)])
    if os.path.exists("/usr/local/bin/node"):
        args.extend(["--js-runtimes", "node:/usr/local/bin/node"])
    return args


def check_live_status(channel_url):
    cmd = yt_dlp_base_args() + ["--print", "%(is_live)s|%(id)s|%(title)s", "--skip-download", channel_url]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
        out = res.stdout.strip().split("\n")[-1]
        if "|" in out:
            is_live, video_id, title = out.split("|", 2)
            if is_live.lower() in ("true", "1"):
                return True, video_id, title
    except Exception:
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
        self.buf_dir = self.job_dir / "ring_buffer"
        self.buf_dir.mkdir(parents=True, exist_ok=True)

        self.chat_pos = 0
        self.chat_buf = b""
        self.seen_msg_ids = set()
        self.wgt_counter = Counter()
        self.recent_messages = deque(maxlen=60)  # (unix_ts, text)
        self.last_spike_time = 0
        self.cooldown_sec = 240
        self.clip_count = 0
        self.chat_proc = None
        self.buf_proc = None
        self.last_buf_restart = 0

    def resolve_stream_url(self):
        cmd = yt_dlp_base_args() + ["-f", "301/300/best[ext=mp4]/best", "-g", self.watch_url]
        return subprocess.check_output(cmd, text=True, timeout=30).strip().splitlines()[0]

    def start_chat_stream(self):
        cmd = yt_dlp_base_args() + [
            "--skip-download", "--write-subs", "--sub-langs", "live_chat",
            "-o", str(self.job_dir / "chat"),
            self.watch_url
        ]
        self.chat_proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"[*] Chat stream listener started (PID: {self.chat_proc.pid})")

    def start_ring_buffer(self):
        """Continuously record rolling 10s .ts chunks (wrap=8 => last ~70-80s history) at ~0% CPU."""
        if self.buf_proc and self.buf_proc.poll() is None:
            return
        now = time.time()
        if now - self.last_buf_restart < 20:
            return
        self.last_buf_restart = now
        try:
            stream_url = self.resolve_stream_url()
            cmd = [
                "ffmpeg", "-y", "-loglevel", "error",
                "-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5",
                "-i", stream_url,
                "-c", "copy",
                "-f", "segment", "-segment_time", "10", "-segment_wrap", "8",
                "-reset_timestamps", "1",
                str(self.buf_dir / "seg_%02d.ts")
            ]
            self.buf_proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(f"[*] Rolling 80s ring-buffer recorder started (PID: {self.buf_proc.pid})")
        except Exception as e:
            print(f"[!] Ring-buffer start warning: {e}")

    def snapshot_ring_buffer(self, out_mp4: Path, num_segments: int = 5) -> bool:
        """Concatenate the last N completed .ts segments (gives ~35s context rewind + 15s aftermath)."""
        now = time.time()
        # Exclude segment written within last 1.2s (likely still being written)
        segs = sorted(
            [p for p in self.buf_dir.glob("seg_*.ts") if p.stat().st_size > 100_000 and (now - p.stat().st_mtime) > 1.2],
            key=lambda p: p.stat().st_mtime
        )
        if len(segs) < 3:
            return False

        chosen = segs[-num_segments:]
        concat_file = out_mp4.with_name("concat_list.txt")
        lines = []
        for s in chosen:
            # Copy snapshot so ring buffer cannot overwrite while we concat
            snap = out_mp4.with_name(f"snap_{s.name}")
            shutil.copyfile(s, snap)
            lines.append(f"file '{snap}'\n")
        concat_file.write_text("".join(lines), encoding="utf-8")

        try:
            subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                 "-i", str(concat_file), "-c", "copy", "-movflags", "+faststart", str(out_mp4)],
                check=True, timeout=45
            )
            return out_mp4.exists() and out_mp4.stat().st_size > 300_000
        finally:
            for f in out_mp4.parent.glob("snap_seg_*.ts"):
                f.unlink(missing_ok=True)
            concat_file.unlink(missing_ok=True)

    def poll_chat(self):
        # Keep ring buffer alive if stream HLS refreshed
        if not self.buf_proc or self.buf_proc.poll() is not None:
            self.start_ring_buffer()

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
                    weight = 3 if HYPE_PATTERN.search(txt) else 1
                    self.wgt_counter[now_s] += weight
                    self.recent_messages.append((now_s, txt))

    def check_spike(self):
        now_s = int(time.time())
        if now_s - self.last_spike_time < self.cooldown_sec:
            return False, 0

        recent_10s = sum(self.wgt_counter.get(s, 0) for s in range(now_s - 10, now_s))
        baseline_60s = sum(self.wgt_counter.get(s, 0) for s in range(now_s - 70, now_s - 10))
        avg_baseline_10s = (baseline_60s / 6) if baseline_60s > 0 else 5

        ratio = recent_10s / max(1.0, avg_baseline_10s)
        if ratio >= 2.8 and recent_10s >= 15:
            self.last_spike_time = now_s
            return True, ratio
        return False, 0

    def trigger_auto_clip(self, ratio):
        self.clip_count += 1
        clip_id = f"{self.streamer_key}_live_clip_{self.clip_count}_{int(time.time())}"
        print(f"\n[🔥] SPIKE DETECTED! (Ratio: {ratio:.1f}x) -> Capturing context rewind for {clip_id}")

        # Wait 12s so ring buffer finishes capturing reaction aftermath while keeping ~35s BEFORE spike
        time.sleep(12)
        self.poll_chat()

        clip_work = self.job_dir / clip_id
        clip_work.mkdir(parents=True, exist_ok=True)
        raw_video = clip_work / "raw.mp4"
        chat_json = clip_work / "chat_context.json"

        recent_texts = [t for _, t in list(self.recent_messages)[-40:]]
        chat_json.write_text(json.dumps(recent_texts, ensure_ascii=False), encoding="utf-8")

        try:
            got_buffer = self.snapshot_ring_buffer(raw_video, num_segments=5)
            if got_buffer:
                print(f"[+] Context-rewound slice extracted from ring buffer: {raw_video}")
            else:
                print("[*] Ring buffer warming up -> fallback direct 48s record...")
                stream_url = self.resolve_stream_url()
                subprocess.run(
                    ["ffmpeg", "-y", "-t", "48", "-i", stream_url, "-c", "copy", str(raw_video)],
                    check=True, timeout=90
                )

            clipper_cmd = [
                sys.executable, str(ENGINE_DIR / "clipper.py"),
                "--id", clip_id,
                "--streamer", self.streamer_key,
                "--duration", "50.0",
                "--auto-fx",
                "--chat-json", str(chat_json),
                "--workdir", str(clip_work)
            ]
            print("[*] Running Golden Formula Auto-FX + Quality Gate pipeline...")
            res = subprocess.run(clipper_cmd, timeout=240)

            if res.returncode == 2:
                print(f"[SKIP] Quality Gate filtered false-alarm chat spike #{self.clip_count} (streamer diam/monoton).")
                shutil.rmtree(clip_work, ignore_errors=True)
                return
            if res.returncode != 0:
                raise RuntimeError(f"clipper.py exited with code {res.returncode}")

            analysis = {}
            a_file = clip_work / "analysis.json"
            if a_file.exists():
                analysis = json.loads(a_file.read_text(encoding="utf-8"))

            final_title = analysis.get("title", f"MOMEN KOCAK GTA 6 #{self.clip_count}")
            transcript_prev = analysis.get("transcript_preview", "")
            sfx_str = analysis.get("sfx_list", "")
            rendered_video = clip_work / f"{clip_id}_rendered.mp4"
            portal_thumb = Path(f"/data/html/clips/files/{clip_id}/thumb_cutout.jpg")

            if rendered_video.exists():
                send_video(
                    str(rendered_video),
                    caption=(
                        f"🎬 *{final_title}* 🔥\n\n"
                        f"🗣️ _\"{transcript_prev[:140]}...\"_\n"
                        f"⚡ FX: Snap Zoom 1.5x, Shake/Flash, Auto SFX (`{sfx_str}`), Cutout Cover\n"
                        f"📊 Chat Spike: `{ratio:.1f}x` | Rewind Context: `✅`\n"
                        f"🔗 Portal: {PORTAL_URL}"
                    ),
                    thumb_path=str(portal_thumb) if portal_thumb.exists() else None
                )
                print(f"[+] Smart Auto-Clip '{final_title}' sent to Telegram!")
        except Exception as e:
            print(f"[!] Error producing auto-clip: {e}")
            send_message(f"⚠️ Gagal render auto-clip #{self.clip_count}: `{e}`")

    def stop(self):
        for p in (self.chat_proc, self.buf_proc):
            if p and p.poll() is None:
                p.terminate()
                try:
                    p.wait(timeout=5)
                except Exception:
                    p.kill()


def run_watcher_loop(streamer_target="windah"):
    cfg = CHANNELS.get(streamer_target, CHANNELS["windah"])
    print(f"=== Smart Auto-Watcher Daemon Active: {cfg['name']} ===")
    send_message(
        f"🤖 *Smart Auto-Watcher v2 Aktif!*\n"
        f"Memantau: *{cfg['name']}*\n"
        f"✅ 80s Rolling Ring-Buffer (Context Rewind)\n"
        f"✅ Dual-Signal Filter (Chat Spike + Audio Peak)\n"
        f"✅ Auto-Title, Styled Subs, Zoom/Shake/Flash, SFX & Cutout Cover"
    )

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
                        f"🚀 Menjalankan 80s Rolling Buffer + Dual-Signal Detector..."
                    )
                    active_monitor = LiveMonitor(streamer_target, vid_id, title)
                    active_monitor.start_chat_stream()
                    active_monitor.start_ring_buffer()
                else:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] {cfg['name']} offline. Poll 60s...", end="\r")
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
