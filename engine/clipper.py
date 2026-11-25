#!/usr/bin/env python3
"""
GTA Shorts Clipper Engine - Universal Declarative Golden Formula Pipeline
Supports Auto-FX (Snap Zoom 1.5x, Micro Shake, White Impact Flash, SFX Mix,
Perfect Cut 1.0s Black Screen + FAAH, Styled ASS, and Art-Director Cutout Thumbnails).
"""

import os
import re
import sys
import json
import time
import shutil
import argparse
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ENGINE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"
PROFILES_FILE = ENGINE_DIR / "profiles.json"
WEB_DIR = Path("/data/html/clips")
STAGE_FILE = BASE_DIR / ".job_stage.json"

sys.path.insert(0, str(ENGINE_DIR))


def update_stage(stage, percent, detail, slug=None):
    data = {}
    if STAGE_FILE.exists():
        try:
            data = json.loads(STAGE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    if slug:
        data["slug"] = slug
    data.update({"stage": stage, "percent": percent, "detail": detail, "updated_at": time.time()})
    try:
        STAGE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


def parse_time_to_seconds(t_str):
    parts = list(map(float, t_str.split(":")))
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    elif len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return float(parts[0])


def load_profiles():
    if not PROFILES_FILE.exists():
        return {}
    return json.loads(PROFILES_FILE.read_text(encoding="utf-8"))


def run_download(url, time_range, output_path, cookies_path=None):
    print(f"[*] Downloading slice {time_range} from {url}...")
    start_s, end_s = [parse_time_to_seconds(x) for x in time_range.split("-")]
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--download-sections", f"*{int(start_s)}-{int(end_s)}",
        "--force-keyframes-at-cuts",
        "-f", "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]",
        "-o", str(output_path),
        url
    ]
    for c in [cookies_path, str(BASE_DIR / "cookies.txt"), "/data/home/Downloads/www.youtube.com_cookies.txt"]:
        if c and os.path.exists(c):
            cmd.extend(["--cookies", str(c)])
            break
    if os.path.exists("/usr/local/bin/node"):
        cmd.extend(["--js-runtimes", "node:/usr/local/bin/node"])
    subprocess.run(cmd, check=True)
    print(f"[+] Download complete: {output_path}")


def build_render_cmd(raw_video, ass_file, streamer, title, out_video, clip_duration, work_dir,
                     zoom_expr="0", shake_expr="0", flash_expr="0", sfx_list=None, perfect_cut=True):
    profiles = load_profiles()
    prof = profiles.get(streamer, profiles.get("default"))

    title_file = work_dir / "title.txt"
    title_file.write_text(title.upper(), encoding="utf-8")

    total_duration = round(clip_duration + (1.0 if perfect_cut else 0.0), 2)

    # Safe calibrated facecam crop + 1.5x zoom derived cleanly from top_normal
    face_norm = prof.get("facecam_normal", "crop=iw*0.29:ih*0.32:iw*0.71:ih*0.68,scale=1080:820:flags=lanczos,unsharp=5:5:0.8:5:5:0.0")
    face_norm = face_norm.replace("crop=356:270:1595:615", "crop=356:270:1564:615")

    filter_parts = [
        f"[0:v]trim=duration={clip_duration},scale=1920:1080:flags=lanczos,fps=60,setpts=PTS-STARTPTS,split=2[cam_in][game_in];",
        f"[cam_in]{face_norm},split=2[top_normal][top_z_src];",
        f"[top_z_src]crop=720:546:240:90,scale=1080:820:flags=lanczos,unsharp=5:5:1.0:5:5:0.0[top_zoom];",
        f"[game_in]{prof['gameplay']}[bottom_game];",
        f"color=c=black:s=1080x1920:r=60:d={clip_duration}[canvas];",
        f"[canvas][top_normal]overlay=0:0[c1];",
        f"[c1][top_zoom]overlay=0:0:enable='{zoom_expr}'[c2];",
        f"[c2][bottom_game]overlay=0:940[c3];",
    ]

    # Micro screen shake on impact
    if shake_expr and shake_expr != "0":
        filter_parts.append(
            f"color=c=black:s=1080x1920:r=60:d={clip_duration}[sbg];"
            f"[sbg][c3]overlay=x='if({shake_expr},sin(2*PI*t*30)*18,0)':y='if({shake_expr},cos(2*PI*t*30)*12,0)'[shaken];"
        )
        v_stage = "shaken"
    else:
        v_stage = "c3"

    # Seam divider (y=820..940)
    filter_parts.append(
        f"[{v_stage}]drawbox=y=820:w=1080:h=120:color={prof['seam_color_bg']}@1.0:t=fill,"
        f"drawbox=y=820:w=1080:h=5:color={prof['seam_color_top']}@1.0:t=fill,"
        f"drawbox=y=935:w=1080:h=5:color={prof['seam_color_bottom']}@1.0:t=fill,"
        f"drawtext=font='{prof['font_title']}':textfile='{title_file}':fontcolor=white:fontsize=54:"
        f"bordercolor=black:borderw=3:shadowcolor=black@0.9:shadowx=4:shadowy=4:"
        f"x=(w-text_w)/2:y=820+(120-text_h)/2[base_vid];"
    )

    logo_path = BASE_DIR / "docs" / "logo.png"
    current_v = "base_vid"
    inputs = ["-i", str(raw_video)]

    if logo_path.exists():
        inputs.extend(["-i", str(logo_path)])
        filter_parts.append(f"[1:v]scale=180:-1[logo];[{current_v}][logo]overlay=W-w-40:40[with_logo];")
        current_v = "with_logo"

    # 1-frame white impact flash
    if flash_expr and flash_expr != "0":
        filter_parts.append(
            f"[{current_v}]drawbox=x=0:y=0:w=1080:h=1920:color=white@0.32:t=fill:enable='{flash_expr}'[flashed];"
        )
        current_v = "flashed"

    if ass_file and os.path.exists(ass_file) and os.path.getsize(ass_file) > 0:
        filter_parts.append(f"[{current_v}]ass='{ass_file}'[v_main];")
    else:
        filter_parts.append(f"[{current_v}]null[v_main];")

    # Perfect Cut 1.0s Black Screen Outro
    if perfect_cut:
        filter_parts.append(
            f"color=c=black:s=1080x1920:r=60:d=1.0[black_end];"
            f"[v_main][black_end]concat=n=2:v=1:a=0[v];"
        )
    else:
        filter_parts.append("[v_main]null[v];")

    # Audio stream + SFX mix + loudnorm -14 LUFS
    filter_parts.append(f"[0:a]atrim=duration={clip_duration},asetpts=PTS-STARTPTS,aresample=async=1000:osr=48000[a_stream];")
    audio_inputs = ["[a_stream]"]

    if sfx_list:
        for idx, item in enumerate(sfx_list.split(",")):
            if "@" not in item:
                continue
            name, t_sec = item.strip().split("@")
            t_ms = int(float(t_sec) * 1000)
            sfx_file = ASSETS_DIR / "sfx" / f"{name}.mp3"
            if not sfx_file.exists():
                sfx_file = ASSETS_DIR / "sfx" / f"{name.capitalize()}.mp3"
            if sfx_file.exists():
                sfx_idx = len(inputs) // 2
                inputs.extend(["-i", str(sfx_file)])
                tag = f"sfx_{idx}"
                vol = "1.15" if name in ("vine_boom", "boom", "faah") else "1.0"
                filter_parts.append(f"[{sfx_idx}:a]adelay={t_ms}|{t_ms},volume={vol}[{tag}];")
                audio_inputs.append(f"[{tag}]")

    if len(audio_inputs) > 1:
        mix_inputs = "".join(audio_inputs)
        filter_parts.append(
            f"{mix_inputs}amix=inputs={len(audio_inputs)}:duration=longest:dropout_transition=0,"
            f"atrim=end={total_duration},aresample=async=1000:osr=48000,loudnorm=I=-14:LRA=11:TP=-1.5[a]"
        )
    else:
        filter_parts.append(
            f"[a_stream]atrim=end={total_duration},aresample=async=1000:osr=48000,loudnorm=I=-14:LRA=11:TP=-1.5[a]"
        )

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", "".join(filter_parts),
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-r", "60",
        "-pix_fmt", "yuv420p", "-maxrate", "6M", "-bufsize", "12M",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-movflags", "+faststart",
        "-progress", str(BASE_DIR / ".render_progress.txt"),
        "-t", str(total_duration),
        str(out_video)
    ]
    return cmd


def deploy_to_portal(clip_id, out_video, title, summary, copy_text, duration_str, size_str,
                     streamer="windah", hook_top=None, hook_main=None, badge="DILUAR NALAR!", sfx_tags=None):
    dest_dir = WEB_DIR / "files" / clip_id
    dest_dir.mkdir(parents=True, exist_ok=True)

    final_mp4 = dest_dir / f"{clip_id}_1080p.mp4"
    shutil.copyfile(out_video, final_mp4)

    # Generate Art-Director Cutout Thumbnail + lightweight thumb_sm.jpg
    out_cutout = dest_dir / "thumb_cutout.jpg"
    try:
        from PIL import Image
        from thumb_cutout import generate_cutout_thumbnail
        words = title.upper().split()
        ht = hook_top or (" ".join(words[:2]) if len(words) >= 3 else "MOMEN KOCAK")
        hm = hook_main or (" ".join(words[2:4]) + "?!" if len(words) >= 3 else title.upper())
        generate_cutout_thumbnail(str(final_mp4), str(out_cutout), ht, hm, badge)
        shutil.copyfile(out_cutout, dest_dir / "thumb_v1.jpg")
        shutil.copyfile(out_cutout, dest_dir / "thumb.jpg")
        sm = Image.open(out_cutout).convert("RGB")
        sm.thumbnail((270, 480), Image.Resampling.LANCZOS)
        sm.save(dest_dir / "thumb_sm.jpg", "JPEG", quality=80, optimize=True)
        # Inject 0.12s Intro Cover Flash for YouTube Shorts / TikTok / Reels frame picker
        from inject_cover_intro import inject_cover_intro
        if inject_cover_intro(final_mp4, out_cutout):
            (dest_dir / ".cover_intro_v1").write_text("ok", encoding="utf-8")
            size_str = f"{final_mp4.stat().st_size / (1024*1024):.1f} MB"
    except Exception as e:
        print(f"[!] Cutout thumbnail fallback ({e})")
        subprocess.run(
            ["ffmpeg", "-y", "-ss", "10", "-i", str(final_mp4), "-vframes", "1", "-q:v", "2", str(dest_dir / "thumb.jpg")],
            check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

    (dest_dir / "copywriting.txt").write_text(copy_text, encoding="utf-8")

    html_path = WEB_DIR / "index.html"
    if html_path.exists():
        content = html_path.read_text(encoding="utf-8")
        match = re.search(r"const CLIPS = (\[.*?\]);", content, re.DOTALL)
        if match:
            clips = json.loads(match.group(1))
            clips = [c for c in clips if c.get("id") != clip_id]
            profiles = load_profiles()
            prof = profiles.get(streamer, profiles.get("default"))

            new_clip = {
                "id": clip_id,
                "streamer": prof["name"].upper(),
                "streamer_color": prof["badge_color"],
                "is_new": True,
                "title": title,
                "duration": duration_str,
                "size": size_str,
                "sfx": sfx_tags or ["Snap Zoom 1.5x", "Micro Shake & Flash", "Auto SFX Mix", "FAAH Perfect Cut"],
                "video_url": f"files/{clip_id}/{final_mp4.name}",
                "copy_url": f"files/{clip_id}/copywriting.txt",
                "summary": summary,
                "desc": summary,
                "copywriting": copy_text,
                "copy_text": copy_text
            }
            clips.insert(0, new_clip)
            new_json = json.dumps(clips, ensure_ascii=False)
            content = content[:match.start()] + f"const CLIPS = {new_json};" + content[match.end():]
            content = re.sub(r'let currentClipId = "[^"]+";', f'let currentClipId = "{clip_id}";', content)
            html_path.write_text(content, encoding="utf-8")
            print(f"[+] Portal index.html updated with {clip_id}!")

    # 5. Auto-sync to Google Drive (Rolling Cache: keep 3 newest locally)
    try:
        sync_script = Path(__file__).resolve().parent / "gdrive_sync.py"
        if sync_script.exists():
            subprocess.run([sys.executable, str(sync_script), "--keep", "3"], check=False)
    except Exception as e:
        print(f"[!] Warning: GDrive auto-sync skipped: {e}")



def main():
    parser = argparse.ArgumentParser(description="GTA Shorts Golden Formula Clipper Pipeline")
    parser.add_argument("--url")
    parser.add_argument("--range")
    parser.add_argument("--streamer", default="windah")
    parser.add_argument("--title", default="")
    parser.add_argument("--duration", type=float, default=50.0)
    parser.add_argument("--zoom", default="0")
    parser.add_argument("--shake", default="0")
    parser.add_argument("--flash", default="0")
    parser.add_argument("--sfx", default="")
    parser.add_argument("--perfect-cut", action="store_true", default=True)
    parser.add_argument("--no-perfect-cut", action="store_false", dest="perfect_cut")
    parser.add_argument("--auto-fx", action="store_true", help="Run context_analyzer for auto-title, subs, zoom, shake, sfx")
    parser.add_argument("--chat-json", help="Optional JSON file of livechat messages for context")
    parser.add_argument("--hook-top")
    parser.add_argument("--hook-main")
    parser.add_argument("--badge", default="DILUAR NALAR!")
    parser.add_argument("--id", required=True)
    parser.add_argument("--summary", default="")
    parser.add_argument("--copywriting", default="")
    parser.add_argument("--cookies", default="/data/home/Downloads/www.youtube.com_cookies.txt")
    parser.add_argument("--workdir")
    parser.add_argument("--no-deploy", action="store_true")
    args = parser.parse_args()

    work_dir = Path(args.workdir) if args.workdir else BASE_DIR / "jobs" / args.id
    work_dir.mkdir(parents=True, exist_ok=True)

    try:
        raw_video = work_dir / "raw.mp4"
        if args.url and args.range and not raw_video.exists():
            update_stage("downloading", 15, f"Mengunduh video stream ({args.range})...", slug=args.id)
            run_download(args.url, args.range, raw_video, args.cookies)

        ass_file = work_dir / "subs.ass"
        title = args.title
        summary = args.summary
        copywriting = args.copywriting
        clip_dur = args.duration
        zoom_expr = args.zoom
        shake_expr = args.shake
        flash_expr = args.flash
        sfx_list = args.sfx
        hook_top = args.hook_top
        hook_main = args.hook_main
        badge = args.badge

        if args.auto_fx or not ass_file.exists():
            update_stage("transcribing", 30, "AI analisis konteks, transkrip, & auto-FX...", slug=args.id)
            from context_analyzer import analyze_clip
            chats = json.loads(Path(args.chat_json).read_text(encoding="utf-8")) if args.chat_json and Path(args.chat_json).exists() else []
            profiles = load_profiles()
            s_name = profiles.get(args.streamer, {}).get("name", args.streamer)
            analysis = analyze_clip(str(raw_video), str(ass_file), chats, s_name)
            (work_dir / "analysis.json").write_text(json.dumps(analysis, indent=2, ensure_ascii=False), encoding="utf-8")

            if args.auto_fx:
                if not analysis["worth_clipping"]:
                    print(f"[SKIP] Quality gate rejected clip: {analysis['reason']}")
                    sys.exit(2)
                if not title:
                    title = analysis["title"]
                if not summary:
                    summary = analysis["summary"]
                if not copywriting:
                    copywriting = analysis["copywriting"]
                clip_dur = min(args.duration, analysis["clip_duration"])
                if zoom_expr == "0":
                    zoom_expr = analysis["zoom_expr"]
                if shake_expr == "0":
                    shake_expr = analysis["shake_expr"]
                if flash_expr == "0":
                    flash_expr = analysis["flash_expr"]
                if not sfx_list:
                    sfx_list = re.sub(r"faah@[0-9.]+", f"faah@{clip_dur:.2f}", analysis["sfx_list"])
                hook_top = hook_top or analysis["hook_top"]
                hook_main = hook_main or analysis["hook_main"]
                badge = analysis["badge"]

        title = title or "MOMEN KOCAK GTA 6!"
        out_video = work_dir / f"{args.id}_rendered.mp4"
        cmd = build_render_cmd(
            raw_video=raw_video,
            ass_file=ass_file,
            streamer=args.streamer,
            title=title,
            out_video=out_video,
            clip_duration=clip_dur,
            work_dir=work_dir,
            zoom_expr=zoom_expr,
            shake_expr=shake_expr,
            flash_expr=flash_expr,
            sfx_list=sfx_list,
            perfect_cut=args.perfect_cut
        )

        update_stage("rendering", 55, "Rendering Golden Formula 1080x1920 @ 60fps...", slug=args.id)
        subprocess.run(cmd, check=True)

        total_dur = round(clip_dur + (1.0 if args.perfect_cut else 0.0), 1)
        size_mb = os.stat(out_video).st_size / (1024 * 1024)
        print(f"[+] Render complete: {out_video} ({size_mb:.1f} MB, {total_dur}s)")

        if not args.no_deploy:
            update_stage("deploying", 90, "Generate cutout thumbnail & publish ke portal...", slug=args.id)
            sfx_tags = ["Snap Zoom 1.5x", "Micro Shake & Flash", "Styled Subs", "FAAH Perfect Cut"]
            if "delfin@" in (sfx_list or ""):
                sfx_tags.insert(2, "Auto Dolphin Censor")
            if "vine_boom@" in (sfx_list or ""):
                sfx_tags.insert(2, "Vine Boom")
            deploy_to_portal(
                clip_id=args.id,
                out_video=out_video,
                title=title,
                summary=summary or title,
                copy_text=copywriting or title,
                duration_str=f"{total_dur:.1f}s",
                size_str=f"{size_mb:.1f} MB",
                streamer=args.streamer,
                hook_top=hook_top,
                hook_main=hook_main,
                badge=badge,
                sfx_tags=sfx_tags
            )
            if raw_video.exists():
                pass  # Keep raw.mp4 for clean future revisions

        update_stage("done", 100, f"Klip selesai! ({size_mb:.1f} MB)", slug=args.id)
    except SystemExit:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        update_stage("error", 0, f"Error pipeline: {str(e)}", slug=args.id)
        sys.exit(1)


if __name__ == "__main__":
    main()
