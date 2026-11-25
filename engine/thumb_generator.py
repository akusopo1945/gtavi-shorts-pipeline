#!/usr/bin/env python3
"""
Auto-Thumbnail Hook FYP Generator for GTA VI Shorts
Supports Multi-Style Presets (V1: Neon Seam, V2: Clickbait Arrow, V3: Breaking News)
and instant revision via CLI or API.
"""

import os
import sys
import math
import shutil
import argparse
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter

FONTS_DIR = Path('/data/gtavi-claudecode/assets/fonts')
FONT_BEBAS = str(FONTS_DIR / 'BebasNeue-Bold.otf')
FONT_MONTSERRAT = str(FONTS_DIR / 'Montserrat-ExtraBold.otf')

def get_video_duration(video_path):
    try:
        cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', str(video_path)]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(res.stdout.strip())
    except:
        return 50.0

def extract_frame(video_path, timestamp, tmp_frame):
    cmd = [
        'ffmpeg', '-y', '-ss', f'{timestamp:.2f}',
        '-i', str(video_path),
        '-vframes', '1', '-q:v', '2',
        str(tmp_frame)
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    img = Image.open(tmp_frame).convert('RGBA')
    # Boost colors for vertical screens
    enh_col = ImageEnhance.Color(img)
    img = enh_col.enhance(1.18)
    enh_con = ImageEnhance.Contrast(img)
    img = enh_con.enhance(1.12)
    enh_shp = ImageEnhance.Sharpness(img)
    img = enh_shp.enhance(1.10)
    return img

def format_hook_text(title, hook_text=None):
    if not hook_text:
        t_clean = title.replace('?!', '').replace('!', '').replace('?', '').strip()
        words = t_clean.split()
        if len(words) > 4:
            hook_text = ' '.join(words[:4]) + '?!'
        else:
            hook_text = t_clean + '?!'
    return hook_text.upper()

def draw_arrow(draw, start, end, color=(239, 68, 68, 255), width=12, head_size=42):
    draw.line([start, end], fill=color, width=width)
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    angle = math.atan2(dy, dx)
    p1 = (end[0] - head_size * math.cos(angle - math.pi / 6),
          end[1] - head_size * math.sin(angle - math.pi / 6))
    p2 = (end[0] - head_size * math.cos(angle + math.pi / 6),
          end[1] - head_size * math.sin(angle + math.pi / 6))
    draw.polygon([end, p1, p2], fill=color)

# ==========================================
# PRESET 1: NEON SEAM (Current Default)
# ==========================================
def render_style_v1(img, title, hook_text, streamer):
    W, H = img.size
    overlay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    
    banner_y1 = 845
    banner_y2 = 1075
    draw.rectangle([(0, banner_y1), (W, banner_y2)], fill=(9, 13, 24, 235))
    draw.line([(0, banner_y1), (W, banner_y1)], fill=(255, 230, 0, 255), width=6)
    draw.line([(0, banner_y2), (W, banner_y2)], fill=(236, 72, 153, 255), width=6)
    
    s_name = 'WINDAH BASUDARA' if streamer.lower() == 'windah' else 'TARA ARTS' if streamer.lower() == 'tara' else streamer.upper()
    pill_color = (37, 99, 235, 255) if streamer.lower() == 'windah' else (236, 72, 153, 255)
    f_pill = ImageFont.truetype(FONT_MONTSERRAT, 24)
    pill_text = f'  {s_name}  '
    pill_bbox = draw.textbbox((0, 0), pill_text, font=f_pill)
    pill_w = pill_bbox[2] - pill_bbox[0]
    draw.rectangle([(50, banner_y1 - 22), (50 + pill_w + 10, banner_y1 + 18)], fill=pill_color)
    draw.text((55, banner_y1 - 18), pill_text, fill=(255, 255, 255, 255), font=f_pill)
    
    f_tag = ImageFont.truetype(FONT_MONTSERRAT, 22)
    tag_text = '  KLIMAKS SHORTS  '
    tag_bbox = draw.textbbox((0, 0), tag_text, font=f_tag)
    tag_w = tag_bbox[2] - tag_bbox[0]
    draw.rectangle([(W - tag_w - 60, banner_y1 - 22), (W - 50, banner_y1 + 18)], fill=(239, 68, 68, 255))
    draw.text((W - tag_w - 55, banner_y1 - 18), tag_text, fill=(255, 255, 255, 255), font=f_tag)
    
    font_size = 94
    f_hook = ImageFont.truetype(FONT_BEBAS, font_size)
    bbox = draw.textbbox((0, 0), hook_text, font=f_hook)
    text_w = bbox[2] - bbox[0]
    while text_w > (W - 100) and font_size > 54:
        font_size -= 4
        f_hook = ImageFont.truetype(FONT_BEBAS, font_size)
        bbox = draw.textbbox((0, 0), hook_text, font=f_hook)
        text_w = bbox[2] - bbox[0]
        
    text_x = (W - text_w) // 2
    text_y = banner_y1 + 42
    
    stroke_w = 8
    draw.text((text_x + 6, text_y + 6), hook_text, font=f_hook, fill=(0, 0, 0, 255), stroke_width=stroke_w, stroke_fill=(0, 0, 0, 255))
    draw.text((text_x, text_y), hook_text, font=f_hook, fill=(255, 230, 0, 255), stroke_width=stroke_w, stroke_fill=(0, 0, 0, 255))
    
    f_sub = ImageFont.truetype(FONT_MONTSERRAT, 26)
    sub_text = 'DETIK-DETIK PALING DILUAR NALAR!'
    sub_bbox = draw.textbbox((0, 0), sub_text, font=f_sub)
    sub_w = sub_bbox[2] - sub_bbox[0]
    sub_x = (W - sub_w) // 2
    draw.text((sub_x, banner_y1 + 158), sub_text, font=f_sub, fill=(226, 232, 240, 255), stroke_width=3, stroke_fill=(0, 0, 0, 220))
    
    draw.rectangle([(14, 14), (W - 14, H - 14)], outline=(236, 72, 153, 200), width=6)
    return Image.alpha_composite(img, overlay).convert('RGB')

# ==========================================
# PRESET 2: CLICKBAIT ARROW & CIRCLE (CTR King)
# ==========================================
def render_style_v2(img, title, hook_text, streamer):
    W, H = img.size
    overlay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    
    # 1. Top Slanted Card for Hook Text (y: 110 - 320)
    card_y1 = 120
    card_y2 = 330
    draw.rectangle([(30, card_y1), (W - 30, card_y2)], fill=(15, 23, 42, 240))
    draw.line([(30, card_y1), (W - 30, card_y1)], fill=(239, 68, 68, 255), width=8)
    draw.line([(30, card_y2), (W - 30, card_y2)], fill=(255, 230, 0, 255), width=8)
    
    # Tag
    f_tag = ImageFont.truetype(FONT_MONTSERRAT, 22)
    draw.rectangle([(60, card_y1 - 18), (360, card_y1 + 18)], fill=(239, 68, 68, 255))
    draw.text((75, card_y1 - 15), 'VIRAL TIKTOK • KOCAK PARAH', fill=(255, 255, 255, 255), font=f_tag)
    
    # Large Hook Bebas Neue
    font_size = 90
    f_hook = ImageFont.truetype(FONT_BEBAS, font_size)
    bbox = draw.textbbox((0, 0), hook_text, font=f_hook)
    text_w = bbox[2] - bbox[0]
    while text_w > (W - 120) and font_size > 50:
        font_size -= 4
        f_hook = ImageFont.truetype(FONT_BEBAS, font_size)
        bbox = draw.textbbox((0, 0), hook_text, font=f_hook)
        text_w = bbox[2] - bbox[0]
        
    text_x = (W - text_w) // 2
    draw.text((text_x + 5, card_y1 + 45), hook_text, font=f_hook, fill=(0, 0, 0, 255), stroke_width=10, stroke_fill=(0, 0, 0, 255))
    draw.text((text_x, card_y1 + 40), hook_text, font=f_hook, fill=(255, 230, 0, 255), stroke_width=8, stroke_fill=(0, 0, 0, 255))
    
    f_sub = ImageFont.truetype(FONT_MONTSERRAT, 24)
    sub = f'{streamer.upper()} • DETIK INI BIKIN NGAKAK'
    sub_bbox = draw.textbbox((0, 0), sub, font=f_sub)
    draw.text(((W - (sub_bbox[2]-sub_bbox[0])) // 2, card_y1 + 150), sub, fill=(255, 255, 255, 255), font=f_sub)
    
    # 2. Glowing Clickbait Circle in Gameplay (y: 1350 - 1650)
    c_x1, c_y1, c_x2, c_y2 = 520, 1320, 840, 1640
    # Outer glow
    draw.ellipse([(c_x1-6, c_y1-6), (c_x2+6, c_y2+6)], outline=(239, 68, 68, 160), width=6)
    # Inner bright yellow neon
    draw.ellipse([(c_x1, c_y1), (c_x2, c_y2)], outline=(255, 230, 0, 255), width=10)
    
    # 3. Big Red 3D Arrow pointing towards circle
    draw_arrow(draw, start=(280, 1200), end=(530, 1360), color=(239, 68, 68, 255), width=16, head_size=50)
    
    # Text badge near arrow
    f_arr = ImageFont.truetype(FONT_MONTSERRAT, 24)
    draw.rectangle([(190, 1150), (370, 1200)], fill=(239, 68, 68, 255))
    draw.text((205, 1160), 'LIAT INI ANJIR!', fill=(255, 255, 255, 255), font=f_arr)
    
    # Vignette border
    draw.rectangle([(10, 10), (W - 10, H - 10)], outline=(239, 68, 68, 220), width=8)
    return Image.alpha_composite(img, overlay).convert('RGB')

# ==========================================
# PRESET 3: BREAKING NEWS (Live Report)
# ==========================================
def render_style_v3(img, title, hook_text, streamer):
    W, H = img.size
    overlay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    
    # 1. Top Red Breaking Header (y: 0 - 130)
    draw.rectangle([(0, 0), (W, 125)], fill=(220, 38, 38, 245))
    draw.line([(0, 125), (W, 125)], fill=(255, 255, 255, 255), width=5)
    
    # Blinking Live Dot
    draw.ellipse([(45, 42), (75, 72)], fill=(255, 255, 255, 255))
    draw.ellipse([(52, 49), (68, 65)], fill=(220, 38, 38, 255))
    
    f_top = ImageFont.truetype(FONT_BEBAS, 56)
    draw.text((95, 34), 'BREAKING NEWS • SIARAN LANGSUNG GTA VI', fill=(255, 255, 255, 255), font=f_top)
    
    # 2. Lower Third News Box (y: 1540 - 1860)
    box_y1 = 1540
    box_y2 = 1860
    # Background
    draw.rectangle([(0, box_y1), (W, box_y2)], fill=(11, 15, 25, 245))
    draw.line([(0, box_y1), (W, box_y1)], fill=(220, 38, 38, 255), width=8)
    
    # Subtag
    draw.rectangle([(0, box_y1), (460, box_y1 + 50)], fill=(220, 38, 38, 255))
    f_report = ImageFont.truetype(FONT_MONTSERRAT, 24)
    draw.text((25, box_y1 + 10), f'LUNA REPORT: {streamer.upper()}', fill=(255, 255, 255, 255), font=f_report)
    
    # Headline Bebas Neue
    font_size = 84
    f_head = ImageFont.truetype(FONT_BEBAS, font_size)
    bbox = draw.textbbox((0, 0), hook_text, font=f_head)
    text_w = bbox[2] - bbox[0]
    while text_w > (W - 80) and font_size > 48:
        font_size -= 4
        f_head = ImageFont.truetype(FONT_BEBAS, font_size)
        bbox = draw.textbbox((0, 0), hook_text, font=f_head)
        text_w = bbox[2] - bbox[0]
        
    draw.text((40, box_y1 + 65), hook_text, fill=(255, 230, 0, 255), font=f_head, stroke_width=6, stroke_fill=(0, 0, 0, 255))
    
    # Bottom ticker strip
    draw.rectangle([(0, box_y2 - 60), (W, box_y2)], fill=(255, 230, 0, 255))
    f_ticker = ImageFont.truetype(FONT_MONTSERRAT, 22)
    ticker_text = '🔴 LIVE UPDATE: KEJADIAN DILUAR PREDIKSI BMKG • WARGA VICE CITY GEMPAR'
    draw.text((30, box_y2 - 45), ticker_text, fill=(0, 0, 0, 255), font=f_ticker)
    
    draw.rectangle([(10, 10), (W - 10, H - 10)], outline=(220, 38, 38, 200), width=6)
    return Image.alpha_composite(img, overlay).convert('RGB')

# ==========================================
# MULTI GENERATOR & REVISION HANDLER
# ==========================================
def generate_all_versions(video_path, dest_dir, title, hook_text=None, timestamp=None, streamer='windah'):
    video_path = Path(video_path)
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    
    duration = get_video_duration(video_path)
    if timestamp is None:
        timestamp = min(max(duration * 0.5, 5.0), max(duration - 5.0, 5.0))
        
    tmp_frame = dest_dir / f'_tmp_frame_{timestamp:.0f}.jpg'
    raw_img = extract_frame(video_path, timestamp, tmp_frame)
    hook = format_hook_text(title, hook_text)
    
    # 1. Generate V1 (Neon Seam)
    v1_img = render_style_v1(raw_img.copy(), title, hook, streamer)
    v1_path = dest_dir / 'thumb_v1.jpg'
    v1_img.save(v1_path, 'JPEG', quality=95)
    
    # 2. Generate V2 (Clickbait Arrow)
    v2_img = render_style_v2(raw_img.copy(), title, hook, streamer)
    v2_path = dest_dir / 'thumb_v2.jpg'
    v2_img.save(v2_path, 'JPEG', quality=95)
    
    # 3. Generate V3 (Breaking News)
    v3_img = render_style_v3(raw_img.copy(), title, hook, streamer)
    v3_path = dest_dir / 'thumb_v3.jpg'
    v3_img.save(v3_path, 'JPEG', quality=95)
    
    # Default thumb.jpg points to v1
    default_thumb = dest_dir / 'thumb.jpg'
    shutil.copyfile(v1_path, default_thumb)
    
    if tmp_frame.exists():
        tmp_frame.unlink()
        
    print(f'[+] All 3 thumbnail versions generated in {dest_dir}:')
    print(f'    - V1 Neon Seam: {v1_path.stat().st_size / 1024:.1f} KB')
    print(f'    - V2 Clickbait Arrow: {v2_path.stat().st_size / 1024:.1f} KB')
    print(f'    - V3 Breaking News: {v3_path.stat().st_size / 1024:.1f} KB')
    return {'v1': v1_path, 'v2': v2_path, 'v3': v3_path, 'default': default_thumb}

def generate_single_version(video_path, out_path, title, hook_text=None, timestamp=None, streamer='windah', style='v1'):
    video_path = Path(video_path)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    duration = get_video_duration(video_path)
    if timestamp is None:
        timestamp = min(max(duration * 0.5, 5.0), max(duration - 5.0, 5.0))
        
    tmp_frame = out_path.parent / f'_tmp_single_{timestamp:.0f}.jpg'
    raw_img = extract_frame(video_path, timestamp, tmp_frame)
    hook = format_hook_text(title, hook_text)
    
    if style.lower() in ('v2', 'arrow', 'clickbait'):
        res_img = render_style_v2(raw_img, title, hook, streamer)
    elif style.lower() in ('v3', 'news', 'breaking'):
        res_img = render_style_v3(raw_img, title, hook, streamer)
    else:
        res_img = render_style_v1(raw_img, title, hook, streamer)
        
    res_img.save(out_path, 'JPEG', quality=95)
    if tmp_frame.exists():
        tmp_frame.unlink()
    print(f'[+] Single thumbnail ({style}) saved: {out_path} ({out_path.stat().st_size / 1024:.1f} KB)')
    return out_path

# Compatibility alias for clipper.py
def generate_fyp_thumbnail(video_path, out_path, title, hook_text=None, timestamp=None, streamer='windah'):
    dest_dir = Path(out_path).parent
    return generate_all_versions(video_path, dest_dir, title, hook_text, timestamp, streamer)['default']

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Multi-Style FYP Thumbnail Generator')
    parser.add_argument('--video', required=True, help='Path to 1080x1920 MP4')
    parser.add_argument('--dest-dir', help='Destination directory for multi-versions')
    parser.add_argument('--out', help='Output single thumbnail path')
    parser.add_argument('--title', required=True, help='Video title')
    parser.add_argument('--hook', help='Custom punchy hook text')
    parser.add_argument('--time', type=float, help='Timestamp in seconds')
    parser.add_argument('--streamer', default='windah', help='windah or tara')
    parser.add_argument('--style', default='all', choices=['all', 'v1', 'v2', 'v3'], help='Style preset')
    args = parser.parse_args()
    
    if args.style == 'all' or args.dest_dir:
        d = args.dest_dir or (Path(args.out).parent if args.out else '.')
        generate_all_versions(args.video, d, args.title, args.hook, args.time, args.streamer)
    else:
        generate_single_version(args.video, args.out, args.title, args.hook, args.time, args.streamer, args.style)
