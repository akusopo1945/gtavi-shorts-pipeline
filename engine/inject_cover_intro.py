#!/usr/bin/env python3
"""
Inject 0.12s Intro Cover Overlay (thumb_cutout.jpg at t=0..0.12s) into Shorts MP4s
without shifting audio or subtitles, for 1-tap YouTube Shorts / TikTok / Reels cover selection.
"""

import re
import sys
import json
import shutil
import argparse
import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

WEB_DIR = Path('/data/html/clips')
INDEX_HTML = WEB_DIR / 'index.html'
INTRO_DUR = 0.12


def inject_cover_intro(mp4_path: Path, thumb_path: Path, dur: float = INTRO_DUR) -> bool:
    if not mp4_path.exists() or not thumb_path.exists():
        return False
    tmp_out = mp4_path.with_name(f'_tmp_intro_{mp4_path.name}')
    cmd = [
        'ffmpeg', '-y', '-loglevel', 'error',
        '-i', str(mp4_path),
        '-loop', '1', '-t', f'{dur + 0.05:.2f}', '-i', str(thumb_path),
        '-filter_complex',
        f"[1:v]scale=1080:1920:flags=lanczos[cov];[0:v][cov]overlay=0:0:enable='between(t,0,{dur:.2f})'[v]",
        '-map', '[v]', '-map', '0:a?',
        '-c:v', 'libx264', '-preset', 'superfast', '-crf', '19', '-pix_fmt', 'yuv420p',
        '-threads', '2',
        '-c:a', 'copy',
        '-movflags', '+faststart',
        str(tmp_out)
    ]
    subprocess.run(cmd, check=True)
    if tmp_out.exists() and tmp_out.stat().st_size > 100_000:
        shutil.move(str(tmp_out), str(mp4_path))
        return True
    tmp_out.unlink(missing_ok=True)
    return False


def process_clip(clip, force=False):
    cid = clip['id']
    vurl = clip['video_url'].split('?')[0].lstrip('/')
    vpath = Path('/data/html/' + vurl) if vurl.startswith('clips/') else Path('/data/html/clips/' + vurl)
    dest_dir = WEB_DIR / 'files' / cid
    thumb = dest_dir / 'thumb_cutout.jpg'
    if not thumb.exists():
        thumb = dest_dir / 'thumb.jpg'
    marker = dest_dir / '.cover_intro_v1'

    if marker.exists() and not force:
        return cid, 'skipped', vpath.stat().st_size / (1024 * 1024) if vpath.exists() else 0

    if not vpath.exists() or not thumb.exists():
        return cid, 'missing', 0

    ok = inject_cover_intro(vpath, thumb)
    if ok:
        marker.write_text('ok\n', encoding='utf-8')
        return cid, 'done', vpath.stat().st_size / (1024 * 1024)
    return cid, 'failed', 0


def run_batch(start_idx=0, limit=None, force=False, workers=2):
    html = INDEX_HTML.read_text(encoding='utf-8')
    m = re.search(r'(const CLIPS = )(\[.*?\])(;\s*\n)', html, re.S)
    clips = json.loads(m.group(2))
    subset = clips[start_idx: start_idx + limit] if limit else clips[start_idx:]

    results = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(process_clip, c, force): c['id'] for c in subset}
        for f in as_completed(futs):
            cid, st, sz = f.result()
            results[cid] = (st, sz)
            print(f'[{st.upper()}] {cid} ({sz:.1f} MB)', flush=True)

    # Refresh index.html cache-busters & sizes for updated clips
    html = INDEX_HTML.read_text(encoding='utf-8')
    m = re.search(r'(const CLIPS = )(\[.*?\])(;\s*\n)', html, re.S)
    clips = json.loads(m.group(2))
    changed = False
    for c in clips:
        cid = c['id']
        if (WEB_DIR / "files" / cid / ".cover_intro_v1").exists():
            base_url = c['video_url'].split('?')[0]
            c['video_url'] = f'{base_url}?v=cov1'
            vurl_clean = c["video_url"].split("?")[0].lstrip("/"); vp = Path("/data/html/" + vurl_clean) if vurl_clean.startswith("clips/") else Path("/data/html/clips/" + vurl_clean); c["size"] = f"{vp.stat().st_size/(1024*1024):.1f} MB" if vp.exists() else c["size"]
            if '0.12s Cover Intro' not in c.get('sfx', []):
                c.setdefault('sfx', []).append('0.12s Cover Intro')
            changed = True
    if changed:
        INDEX_HTML.write_text(html[:m.start(2)] + json.dumps(clips, ensure_ascii=False) + html[m.end(2):], encoding='utf-8')
        print('[+] Updated index.html cache-busters & sizes!')


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--start', type=int, default=0)
    p.add_argument('--limit', type=int)
    p.add_argument('--force', action='store_true')
    p.add_argument('--workers', type=int, default=2)
    args = p.parse_args()
    run_batch(args.start, args.limit, args.force, args.workers)
