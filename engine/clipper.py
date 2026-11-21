#!/usr/bin/env python3
"""
GTA Shorts Clipper Engine - Universal Declarative Pipeline
Portabel untuk Linux VPS / DevContainer / Sandbox.
"""

import os
import sys
import json
import time
import argparse
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = BASE_DIR / "assets"
PROFILES_FILE = Path(__file__).resolve().parent / "profiles.json"
WEB_DIR = Path("/data/html/clips")
STAGE_FILE = BASE_DIR / ".job_stage.json"

def update_stage(stage, percent, detail, slug=None):
    data = {}
    if STAGE_FILE.exists():
        try:
            data = json.loads(STAGE_FILE.read_text(encoding="utf-8"))
        except:
            pass
    if slug:
        data["slug"] = slug
    data.update({
        "stage": stage,
        "percent": percent,
        "detail": detail,
        "updated_at": time.time()
    })
    try:
        STAGE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except:
        pass

def parse_time_to_seconds(t_str):
    parts = list(map(float, t_str.split(':')))
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    elif len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return float(parts[0])

def load_profiles():
    if not PROFILES_FILE.exists():
        return {}
    with open(PROFILES_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def run_download(url, time_range, output_path, cookies_path=None):
    print(f"[*] Downloading slice {time_range} from {url}...")
    start_s, end_s = [parse_time_to_seconds(x) for x in time_range.split('-')]
    
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--download-sections", f"*{int(start_s)}-{int(end_s)}",
        "--force-keyframes-at-cuts",
        "-f", "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]",
        "-o", str(output_path),
        url
    ]
    
    # Check cookies
    possible_cookies = [
        cookies_path,
        str(BASE_DIR / "cookies.txt"),
        "/data/home/Downloads/www.youtube.com_cookies.txt"
    ]
    for c in possible_cookies:
        if c and os.path.exists(c):
            cmd.extend(["--cookies", str(c)])
            break
            
    # Check node for js runtimes
    if os.path.exists("/usr/local/bin/node"):
        cmd.extend(["--js-runtimes", "node:/usr/local/bin/node"])
        
    subprocess.run(cmd, check=True)
    print(f"[+] Download complete: {output_path}")

def run_transcribe(input_video, output_ass):
    print("[*] Transcribing audio with faster-whisper...")
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel('base', device='cpu', compute_type='int8')
        segments, info = model.transcribe(str(input_video), language='id', beam_size=5)
        
        ass_header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Bebas Neue,58,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,1.5,0,1,4.5,3.0,2,40,40,1110,1
Style: Highlight,Bebas Neue,60,&H0000FFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,1.5,0,1,5.0,3.5,2,40,40,1110,1
Style: Magenta,Bebas Neue,62,&H003333FF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,1.5,0,1,5.0,3.5,2,40,40,1110,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        lines = [ass_header]
        count = 0
        for s in segments:
            def fmt_time(sec):
                m, sec = divmod(sec, 60)
                h, m = divmod(m, 60)
                cs = int((sec % 1) * 100)
                return f"{int(h)}:{int(m):02d}:{int(sec):02d}.{cs:02d}"
            
            clean_text = s.text.strip().upper()
            if clean_text:
                lines.append(f"Dialogue: 0,{fmt_time(s.start)},{fmt_time(s.end)},Default,,0,0,0,,{clean_text}\n")
                count += 1
            
        with open(output_ass, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        print(f"[+] Subtitle ASS generated: {output_ass} ({count} dialogue lines)")
    except Exception as e:
        print(f"[!] Warning: faster-whisper failed: {e}. Skipping auto-transcribe.")

def build_render_cmd(raw_video, ass_file, streamer, title, out_video, duration, work_dir, zoom_expr="0", sfx_list=None):
    profiles = load_profiles()
    prof = profiles.get(streamer, profiles.get("default"))
    
    # Save title to textfile to avoid ANY FFmpeg escaping bugs (colons, quotes, etc)
    title_file = work_dir / "title.txt"
    title_file.write_text(title, encoding="utf-8")
    
    filter_parts = [
        f"[0:v]scale=1920:1080:flags=lanczos,fps=60,setpts=PTS-STARTPTS,split=3[cam_normal_in][cam_zoom_in][game_in];",
        f"[cam_normal_in]{prof['facecam_normal']}[top_normal];",
        f"[cam_zoom_in]{prof['facecam_zoom']}[top_zoom];",
        f"[game_in]{prof['gameplay']}[bottom_game];",
        f"color=c=black:s=1080x1920:r=60:d={duration}[canvas];",
        f"[canvas][top_normal]overlay=0:0:enable='not({zoom_expr})'[canvas1];",
        f"[canvas1][top_zoom]overlay=0:0:enable='{zoom_expr}'[canvas2];",
        f"[canvas2][bottom_game]overlay=0:940[tmp2];",
        f"[tmp2]drawbox=y=820:w=1080:h=120:color={prof['seam_color_bg']}@1.0:t=fill,",
        f"drawbox=y=820:w=1080:h=5:color={prof['seam_color_top']}@1.0:t=fill,",
        f"drawbox=y=935:w=1080:h=5:color={prof['seam_color_bottom']}@1.0:t=fill,",
        f"drawtext=font='{prof['font_title']}':textfile='{title_file}':fontcolor=white:fontsize={prof['font_size']}:",
        f"bordercolor=black:borderw=3:shadowcolor=black@0.9:shadowx=4:shadowy=4:",
        f"x=(w-text_w)/2:y=820+(120-text_h)/2[base_vid];"
    ]
    
    logo_path = BASE_DIR / "docs" / "logo.png"
    has_logo = logo_path.exists()
    
    current_v = "base_vid"
    inputs = ["-i", str(raw_video)]
    
    if has_logo:
        inputs.extend(["-i", str(logo_path)])
        filter_parts.append(f"[1:v]scale=180:-1[logo];[{current_v}][logo]overlay=W-w-40:40[with_logo];")
        current_v = "with_logo"
        
    if ass_file and os.path.exists(ass_file) and os.path.getsize(ass_file) > 0:
        filter_parts.append(f"[{current_v}]ass='{ass_file}'[v];")
    else:
        filter_parts.append(f"[{current_v}]null[v];")
    
    # Audio setup
    filter_parts.append("[0:a]asetpts=PTS-STARTPTS[a_stream];")
    audio_inputs = ["[a_stream]"]
    
    if sfx_list:
        items = sfx_list.split(',')
        for idx, item in enumerate(items):
            if '@' not in item:
                continue
            name, t_sec = item.strip().split('@')
            t_ms = int(float(t_sec) * 1000)
            
            sfx_file = ASSETS_DIR / "sfx" / f"{name}.mp3"
            if not sfx_file.exists():
                sfx_file = ASSETS_DIR / "sfx" / f"{name.capitalize()}.mp3"
                
            if sfx_file.exists():
                sfx_idx = len(inputs) // 2
                inputs.extend(["-i", str(sfx_file)])
                tag = f"sfx_{idx}"
                filter_parts.append(f"[{sfx_idx}:a]adelay={t_ms}|{t_ms},volume=1.1[{tag}];")
                audio_inputs.append(f"[{tag}]")
                
    if len(audio_inputs) > 1:
        mix_inputs = "".join(audio_inputs)
        filter_parts.append(
            f"{mix_inputs}amix=inputs={len(audio_inputs)}:duration=longest:dropout_transition=0,"
            f"atrim=end={duration},aresample=async=1000:osr=48000,loudnorm=I=-14:LRA=11:TP=-1.5[a]"
        )
    else:
        filter_parts.append(f"[a_stream]atrim=end={duration},aresample=async=1000:osr=48000,loudnorm=I=-14:LRA=11:TP=-1.5[a]")
        
    filter_complex = "".join(filter_parts)
    
    cmd = [
        "ffmpeg", "-y",
        "-t", str(duration),
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-map", "[a]",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "19",
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "48000",
        "-movflags", "+faststart",
        "-progress", str(BASE_DIR / ".render_progress.txt"),
        "-t", str(duration),
        str(out_video)
    ]
    return cmd

def deploy_to_portal(clip_id, out_video, title, summary, copy_text, duration_str, size_str, streamer="windah"):
    dest_dir = WEB_DIR / "files" / clip_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Copy video
    final_mp4 = dest_dir / f"{clip_id}_1080p.mp4"
    subprocess.run(["cp", str(out_video), str(final_mp4)], check=True)
    
    # 2. Extract thumbnail
    thumb_path = dest_dir / "thumb.jpg"
    subprocess.run([
        "ffmpeg", "-y", "-ss", "10",
        "-i", str(final_mp4),
        "-vframes", "1", "-q:v", "2",
        str(thumb_path)
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # 3. Write copywriting
    copy_path = dest_dir / "copywriting.txt"
    with open(copy_path, 'w', encoding='utf-8') as f:
        f.write(copy_text)
        
    # 4. Update index.html
    html_path = WEB_DIR / "index.html"
    if html_path.exists():
        with open(html_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        import re
        match = re.search(r'const CLIPS = (\[.*?\]);', content, re.DOTALL)
        if match:
            clips = json.loads(match.group(1))
            clips = [c for c in clips if c.get('id') != clip_id]
            
            profiles = load_profiles()
            prof = profiles.get(streamer, profiles.get("default"))
            
            new_clip = {
                'id': clip_id,
                'streamer': prof['name'].upper(),
                'streamer_color': prof['badge_color'],
                'is_new': True,
                'title': title,
                'duration': duration_str,
                'size': size_str,
                'sfx': ["Standard Unified Sound Mix", "Faststart Streaming"],
                'video_url': f"files/{clip_id}/{final_mp4.name}",
                'copy_url': f"files/{clip_id}/copywriting.txt",
                'summary': summary,
                'desc': summary,
                'copywriting': copy_text,
                'copy_text': copy_text
            }
            clips.insert(0, new_clip)
            new_json = json.dumps(clips, ensure_ascii=False)
            content = content[:match.start()] + f'const CLIPS = {new_json};' + content[match.end():]
            content = re.sub(r'let currentClipId = \"[^\"]+\";', f'let currentClipId = "{clip_id}";', content)
            
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"[+] Portal index.html updated with {clip_id}!")

def main():
    parser = argparse.ArgumentParser(description="GTA Shorts Declarative Clipper Pipeline")
    parser.add_argument("--url", help="YouTube video stream URL")
    parser.add_argument("--range", help="Time range e.g. 02:14:10-02:15:05")
    parser.add_argument("--streamer", default="windah", help="Streamer key in profiles.json")
    parser.add_argument("--title", required=True, help="Seam bar main title")
    parser.add_argument("--duration", type=float, default=50.0, help="Target duration in seconds")
    parser.add_argument("--zoom", default="0", help="Zoom expression for FFmpeg enable")
    parser.add_argument("--sfx", help="Comma-separated sfx@seconds e.g. whoosh@10,boom@35,faah@53")
    parser.add_argument("--id", required=True, help="Clip unique ID slug")
    parser.add_argument("--summary", default="", help="Short clip summary")
    parser.add_argument("--copywriting", default="", help="Full caption copywriting")
    parser.add_argument("--cookies", default="/data/home/Downloads/www.youtube.com_cookies.txt", help="Path to YouTube cookies")
    parser.add_argument("--workdir", help="Working directory for intermediate files")
    
    args = parser.parse_args()
    
    work_dir = Path(args.workdir) if args.workdir else BASE_DIR / "jobs" / args.id
    work_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        raw_video = work_dir / "raw.mp4"
        if args.url and args.range and not raw_video.exists():
            update_stage("downloading", 15, f"Mengunduh video stream ({args.range}) via yt-dlp...", slug=args.id)
            run_download(args.url, args.range, raw_video, args.cookies)
            
        ass_file = work_dir / "subs.ass"
        if not ass_file.exists() and raw_video.exists():
            update_stage("transcribing", 35, "AI transkripsi audio ke subtitle ASS...", slug=args.id)
            run_transcribe(raw_video, ass_file)
            
        out_video = work_dir / f"{args.id}_rendered.mp4"
        cmd = build_render_cmd(
            raw_video=raw_video,
            ass_file=ass_file,
            streamer=args.streamer,
            title=args.title,
            out_video=out_video,
            duration=args.duration,
            work_dir=work_dir,
            zoom_expr=args.zoom,
            sfx_list=args.sfx
        )
        
        update_stage("rendering", 50, "Rendering 1080x1920 @ 60fps dengan FFmpeg...", slug=args.id)
        print("[*] Rendering with unified FFmpeg pipeline...")
        subprocess.run(cmd, check=True)
        
        st = os.stat(out_video)
        size_mb = st.st_size / (1024 * 1024)
        print(f"[+] Render complete: {out_video} ({size_mb:.1f} MB)")
        
        update_stage("deploying", 95, "Menyimpan ke portal dan patching faststart streaming...", slug=args.id)
        deploy_to_portal(
            clip_id=args.id,
            out_video=out_video,
            title=args.title,
            summary=args.summary or args.title,
            copy_text=args.copywriting or args.title,
            duration_str=f"{args.duration:.1f}s",
            size_str=f"{size_mb:.1f} MB",
            streamer=args.streamer
        )
        
        update_stage("done", 100, f"Klip selesai diproduksi! ({size_mb:.1f} MB)", slug=args.id)
        print("[+] All pipeline tasks completed successfully!")
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        update_stage("error", 0, f"Error pipeline: {str(e)}", slug=args.id)
        sys.exit(1)

if __name__ == "__main__":
    main()
