#!/usr/bin/env python3
"""
Telegram Bot Helper untuk Auto-Clipper Notification
"""

import os
import sys
import json
import requests
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"

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

def save_env_key(key, val):
    lines = []
    found = False
    if ENV_FILE.exists():
        with open(ENV_FILE) as f:
            lines = f.readlines()
    new_lines = []
    for l in lines:
        if l.strip().startswith(f"{key}="):
            new_lines.append(f'{key}="{val}"\n')
            found = True
        else:
            new_lines.append(l)
    if not found:
        new_lines.append(f'{key}="{val}"\n')
    with open(ENV_FILE, 'w') as f:
        f.writelines(new_lines)

def get_latest_chat_id():
    env = load_env()
    token = env.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set in .env")
    
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    res = requests.get(url).json()
    if res.get("ok") and res.get("result"):
        # get latest message
        for update in reversed(res["result"]):
            msg = update.get("message") or update.get("channel_post")
            if msg and "chat" in msg:
                chat_id = str(msg["chat"]["id"])
                save_env_key("TELEGRAM_CHAT_ID", chat_id)
                return chat_id
    return None

def send_message(text):
    env = load_env()
    token = env.get("TELEGRAM_BOT_TOKEN")
    chat_id = env.get("TELEGRAM_CHAT_ID")
    if not chat_id:
        chat_id = get_latest_chat_id()
    if not chat_id:
        print("[!] No CHAT_ID found. Please send a message to the bot first.")
        return False
        
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    r = requests.post(url, json=payload).json()
    return r.get("ok", False)

def send_video(video_path, caption, thumb_path=None):
    env = load_env()
    token = env.get("TELEGRAM_BOT_TOKEN")
    chat_id = env.get("TELEGRAM_CHAT_ID")
    if not chat_id:
        chat_id = get_latest_chat_id()
    if not chat_id:
        print("[!] No CHAT_ID found. Please send a message to the bot first.")
        return False
        
    url = f"https://api.telegram.org/bot{token}/sendVideo"
    data = {
        "chat_id": chat_id,
        "caption": caption[:1024],
        "supports_streaming": True
    }
    files = {}
    with open(video_path, 'rb') as f_vid:
        files["video"] = f_vid
        if thumb_path and os.path.exists(thumb_path):
            with open(thumb_path, 'rb') as f_thumb:
                files["thumbnail"] = f_thumb
                r = requests.post(url, data=data, files=files).json()
        else:
            r = requests.post(url, data=data, files=files).json()
            
    return r.get("ok", False)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "check":
        cid = get_latest_chat_id()
        if cid:
            print(f"[+] Detected CHAT_ID: {cid}")
            send_message("🚀 *Koneksi Bot Luna Berhasil!*\nSistem Auto-Clipper siap mengirim klip otomatis ke sini.")
        else:
            print("[-] Belum ada pesan. Buka t.me/luna_akuncilik_bot dan klik Start.")
