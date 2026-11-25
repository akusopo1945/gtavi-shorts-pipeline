#!/usr/bin/env python3
"""
Google Drive Rolling Cache Sync for GTA Shorts / Markas Klip / Filmingo ID Portal.
- Resumable & incremental: saves index.html after every clip!
- Keeps the newest --keep N (default 3) MP4 files locally for instant HTML5 playback.
- Uploads all clips to gdrive:ClipsArchive/<Channel>/<clip_id>/, shares public link,
  verifies remote size, then deletes local MP4 for clips beyond --keep.
"""

import os
import re
import sys
import json
import shutil
import argparse
import threading
import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

WEB_DIR = Path("/data/html/clips")
HTML_PATH = WEB_DIR / "index.html"
REMOTE = "gdrive:ClipsArchive"
LOCK = threading.Lock()


def get_channel_folder(clip):
    streamer = (clip.get("streamer") or "").upper()
    if "FILMINGO" in streamer or "MARVEL" in streamer:
        return "FilmingoID"
    return "MarkasKlip"


def run_cmd(cmd, timeout=300):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def save_clips_to_html(clips_list):
    with LOCK:
        content = HTML_PATH.read_text(encoding="utf-8")
        m = re.search(r'const CLIPS = (\[.*?\]);', content, re.DOTALL)
        if not m:
            return
        new_json = json.dumps(clips_list, ensure_ascii=False)
        new_content = content[:m.start()] + f"const CLIPS = {new_json};" + content[m.end():]
        tmp_path = HTML_PATH.with_suffix(".html.tmp")
        tmp_path.write_text(new_content, encoding="utf-8")
        tmp_path.replace(HTML_PATH)


def sync_one_clip(idx, clip, keep_count):
    clip_id = clip["id"]
    video_url = clip.get("video_url", "")
    rel_path = re.sub(r"^/?clips/", "", video_url.split("?")[0]).lstrip("/")
    local_mp4 = WEB_DIR / rel_path if rel_path else None
    channel = get_channel_folder(clip)
    filename = local_mp4.name if local_mp4 else f"{clip_id}_1080p.mp4"
    remote_dir = f"{REMOTE}/{channel}/{clip_id}"
    remote_file = f"{remote_dir}/{filename}"

    keep_local = idx < keep_count
    gdrive_id = clip.get("gdrive_id")
    local_exists = bool(local_mp4 and local_mp4.exists() and local_mp4.stat().st_size > 0)
    local_size = local_mp4.stat().st_size if local_exists else 0

    # Fast-path: already synced and in desired storage state
    if gdrive_id and clip.get("gdrive_shared"):
        if keep_local and clip.get("storage") == "local+gdrive":
            return idx, clip, f"OK     #{idx:02d} {clip_id} (cached local+gdrive)", 0
        if not keep_local and not local_exists and clip.get("storage") == "gdrive":
            return idx, clip, f"OK     #{idx:02d} {clip_id} (already gdrive)", 0

    # 1. Upload if local file exists and not yet confirmed on GDrive
    if local_exists and not gdrive_id:
        r = run_cmd(["rclone", "copy", str(local_mp4), remote_dir, "-L", "--transfers", "1", "--retries", "3"], timeout=240)
        if r.returncode != 0:
            return idx, clip, f"ERR    #{idx:02d} {clip_id}: {r.stderr.strip()[:100]}", 0

    # 2. Verify remote file & get ID via lsjson
    remote_size = 0
    if not gdrive_id or (not keep_local and local_exists):
        r = run_cmd(["rclone", "lsjson", remote_file], timeout=60)
        if r.returncode == 0 and r.stdout.strip():
            try:
                items = json.loads(r.stdout)
                if items:
                    gdrive_id = items[0].get("ID") or gdrive_id
                    remote_size = int(items[0].get("Size", 0))
            except Exception:
                pass

    # 3. Ensure public share link ("anyone with link can view")
    if gdrive_id and not clip.get("gdrive_shared"):
        r = run_cmd(["rclone", "link", remote_file], timeout=60)
        if r.returncode == 0:
            url = r.stdout.strip()
            m = re.search(r'(?:id=|/d/)([a-zA-Z0-9_-]{20,})', url)
            if m:
                gdrive_id = m.group(1)
            clip["gdrive_shared"] = True

    if gdrive_id:
        clip["gdrive_id"] = gdrive_id
        clip["gdrive_preview"] = f"https://drive.google.com/file/d/{gdrive_id}/preview"
        clip["gdrive_download"] = f"https://drive.google.com/uc?export=download&id={gdrive_id}"

    # 4. Rolling cache policy
    freed_bytes = 0
    if keep_local:
        clip["storage"] = "local+gdrive" if gdrive_id else "local"
        status = f"KEEP   #{idx:02d} {clip_id} (gdrive={'ok' if gdrive_id else 'no'})"
    else:
        if gdrive_id and local_exists:
            if remote_size == 0 or remote_size == local_size:
                local_mp4.unlink()
                freed_bytes += local_size
                for extra in local_mp4.parent.glob("*.mp4"):
                    freed_bytes += extra.stat().st_size
                    extra.unlink()
                clip["storage"] = "gdrive"
                status = f"OFFLOAD #{idx:02d} {clip_id} (freed {freed_bytes/1e6:.1f} MB)"
            else:
                clip["storage"] = "local+gdrive"
                status = f"SKIP   #{idx:02d} {clip_id} (size mismatch)"
        elif gdrive_id and not local_exists:
            clip["storage"] = "gdrive"
            status = f"GDRIVE #{idx:02d} {clip_id} (already offloaded)"
        else:
            clip["storage"] = "local"
            status = f"WARN   #{idx:02d} {clip_id} (no gdrive_id)"

    return idx, clip, status, freed_bytes


def main():
    parser = argparse.ArgumentParser(description="Sync portal clips to Google Drive with rolling local cache")
    parser.add_argument("--keep", type=int, default=3, help="Number of newest clips to keep locally (default: 3)")
    parser.add_argument("--workers", type=int, default=6, help="Parallel rclone workers (default: 6)")
    args = parser.parse_args()

    content = HTML_PATH.read_text(encoding="utf-8")
    m = re.search(r'const CLIPS = (\[.*?\]);', content, re.DOTALL)
    if not m:
        print("[!] Could not find CLIPS array in index.html")
        sys.exit(1)

    clips = json.loads(m.group(1))
    shutil.copy2(HTML_PATH, WEB_DIR / "index.html.bak")
    print(f"[*] Starting incremental GDrive sync: {len(clips)} clips (keep={args.keep}, workers={args.workers})", flush=True)

    total_freed = 0
    done = 0

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(sync_one_clip, i, dict(c), args.keep) for i, c in enumerate(clips)]
        for f in as_completed(futs):
            idx, new_clip, status, freed = f.result()
            clips[idx] = new_clip
            total_freed += freed
            done += 1
            save_clips_to_html(clips)
            print(f"  [{done:02d}/{len(clips)}] {status}", flush=True)

    print(f"[+] Sync complete! Freed {total_freed/1e6:.1f} MB local disk. Portal updated.", flush=True)


if __name__ == "__main__":
    main()
