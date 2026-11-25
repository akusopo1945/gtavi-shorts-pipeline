#!/usr/bin/env python3
"""
Art-Director Cutout Thumbnail Generator for GTA VI Shorts.
Zero-clutter, high-CTR mobile-first poster composition using rembg + OpenCV + Chromium.
Supports single video CLI and batch generation for all clips in /data/html/clips/.
"""

import re
import json
import shutil
import base64
import argparse
import subprocess
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageEnhance
from rembg import remove, new_session

ASSETS_DIR = Path('/data/gtavi-claudecode/assets')
FONTS_DIR = ASSETS_DIR / 'fonts'
JASON_ART = ASSETS_DIR / 'jason_official.jpg'
BG_ART = ASSETS_DIR / 'vice_bg_official.jpg'


def get_video_duration(video_path: Path) -> float:
    try:
        r = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', str(video_path)],
            capture_output=True, text=True, check=True
        )
        return float(r.stdout.strip())
    except Exception:
        return 45.0


def find_peak_timestamp(video_path: Path, duration: float) -> float:
    """Find loudest audio RMS peak between 12% and 82% of clip duration."""
    try:
        r = subprocess.run(
            ['ffmpeg', '-i', str(video_path), '-af',
             'astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.RMS_level:file=-',
             '-f', 'null', '-'],
            capture_output=True, text=True, timeout=25
        )
        cur_t, best_v, best_t = 0.0, -999.0, duration * 0.45
        t_min, t_max = max(2.0, duration * 0.12), min(duration - 3.0, duration * 0.82)
        for line in r.stdout.splitlines():
            if 'pts_time:' in line:
                cur_t = float(line.split('pts_time:')[1].split()[0])
            elif 'RMS_level=' in line and t_min <= cur_t <= t_max:
                try:
                    v = float(line.split('RMS_level=')[1].strip())
                    if v > best_v:
                        best_v, best_t = v, cur_t
                except ValueError:
                    pass
        return best_t
    except Exception:
        return max(3.0, duration * 0.45)


def add_sticker_outline(rgba_img: Image.Image, border_px: int = 10, color=(255, 255, 255, 255)) -> Image.Image:
    """Add a smooth morphological sticker border around an RGBA cutout using OpenCV."""
    arr = np.array(rgba_img)
    alpha = arr[:, :, 3]
    alpha_bin = np.where(alpha > 45, 255, 0).astype(np.uint8)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (border_px * 2 + 1, border_px * 2 + 1))
    dilated = cv2.dilate(alpha_bin, kernel, iterations=1)
    dilated = cv2.GaussianBlur(dilated, (5, 5), 0)

    outline = np.zeros_like(arr)
    outline[:, :, 0] = color[0]
    outline[:, :, 1] = color[1]
    outline[:, :, 2] = color[2]
    outline[:, :, 3] = dilated
    return Image.alpha_composite(Image.fromarray(outline, 'RGBA'), rgba_img)


def enhance_subject(rgba_img: Image.Image, sat: float = 1.22, con: float = 1.16) -> Image.Image:
    """Boost color, contrast, and sharpness for mobile screen pop."""
    r, g, b, a = rgba_img.split()
    rgb = Image.merge('RGB', (r, g, b))
    rgb = ImageEnhance.Color(rgb).enhance(sat)
    rgb = ImageEnhance.Contrast(rgb).enhance(con)
    rgb = ImageEnhance.Sharpness(rgb).enhance(1.18)
    r2, g2, b2 = rgb.split()
    return Image.merge('RGBA', (r2, g2, b2, a))


def img_to_data_uri(path: Path) -> str:
    ext = path.suffix.lower().lstrip('.')
    mime = 'image/png' if ext == 'png' else 'image/jpeg'
    b64 = base64.b64encode(path.read_bytes()).decode('ascii')
    return f'data:{mime};base64,{b64}'


def extract_assets_from_video(video_path: Path, timestamp: float, work_dir: Path, session):
    """Extract facecam cutout (or fallback) and gameplay background from video frame."""
    tmp_raw = work_dir / '_raw_frame.png'
    subprocess.run(
        ['ffmpeg', '-y', '-ss', f'{timestamp:.2f}', '-i', str(video_path), '-vframes', '1', '-q:v', '2', str(tmp_raw)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    img = Image.open(tmp_raw).convert('RGBA')
    W, H = img.size

    # Gameplay background (bottom 980px if 1080x1920, else full)
    bg_crop = img.crop((0, int(H * 0.49), W, H)) if H >= 1600 else img
    bg_path = work_dir / 'bg.jpg'
    bg_crop.convert('RGB').save(bg_path, 'JPEG', quality=90)

    # Try top facecam cutout (standard split layout y=0..815, x=0..860)
    top_crop = img.crop((0, 0, min(880, W), min(815, int(H * 0.45))))
    cutout = remove(top_crop, session=session)
    alpha = np.array(cutout)[:, :, 3]
    fg_ratio = float(np.mean(alpha > 128))

    # Fallback if top facecam is empty (e.g. full-screen gameplay with bottom overlay)
    if fg_ratio < 0.05 or fg_ratio > 0.90:
        bot_crop = img.crop((0, int(H * 0.48), W, H))
        cutout_b = remove(bot_crop, session=session)
        fg_b = float(np.mean(np.array(cutout_b)[:, :, 3] > 128))
        if 0.05 <= fg_b <= 0.85:
            cutout = cutout_b
            fg_ratio = fg_b

    subject_png = work_dir / 'subject.png'
    if 0.04 <= fg_ratio <= 0.90:
        cutout = enhance_subject(cutout)
        cutout = add_sticker_outline(cutout, border_px=10, color=(255, 255, 255, 255))
        cutout.save(subject_png, 'PNG')
        has_cutout = True
    else:
        # Clean zoom fallback of top region
        enhance_subject(top_crop).save(subject_png, 'PNG')
        has_cutout = False

    if tmp_raw.exists():
        tmp_raw.unlink()
    return bg_path, subject_png, has_cutout


def build_html(bg_uri: str, subject_uri: str, hook_top: str, hook_main: str,
               badge_text: str, inset_uri: str = None, has_cutout: bool = True) -> str:
    font_bebas = (FONTS_DIR / 'BebasNeue-Bold.otf').as_uri()
    font_mont = (FONTS_DIR / 'Montserrat-ExtraBold.otf').as_uri()

    inset_html = f'<img class="inset-cutout" src="{inset_uri}" />' if inset_uri else ''
    subj_class = 'subject-cutout' if has_cutout else 'subject-card'
    arrow_html = """
  <svg class="arrow-svg" viewBox="0 0 280 240" fill="none">
    <path d="M18 45 Q 140 8 232 152" stroke="#ffffff" stroke-width="28" stroke-linecap="round"/>
    <path d="M18 45 Q 140 8 232 152" stroke="#ef4444" stroke-width="18" stroke-linecap="round"/>
    <polygon points="258,190 182,166 238,112" fill="#ef4444" stroke="#ffffff" stroke-width="7"/>
  </svg>"""

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
@font-face {{
  font-family: 'BebasNeue';
  src: url('{font_bebas}') format('opentype');
}}
@font-face {{
  font-family: 'MontserratExtra';
  src: url('{font_mont}') format('opentype');
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  width: 1080px;
  height: 1920px;
  overflow: hidden;
  position: relative;
  background: #070a14;
  font-family: 'MontserratExtra', sans-serif;
}}
.bg {{
  position: absolute;
  inset: 0;
  background: url('{bg_uri}') center/cover no-repeat;
  filter: saturate(1.45) contrast(1.18) brightness(0.55) blur(3px);
  transform: scale(1.08);
}}
.cinematic-overlay {{
  position: absolute;
  inset: 0;
  background:
    radial-gradient(circle at 22% 48%, rgba(6, 182, 212, 0.48), transparent 48%),
    radial-gradient(circle at 75% 72%, rgba(236, 72, 153, 0.56), transparent 54%),
    radial-gradient(circle at 50% 18%, rgba(255, 230, 0, 0.16), transparent 45%),
    linear-gradient(180deg, rgba(7,10,20,0.88) 0%, rgba(7,10,20,0.16) 38%, rgba(7,10,20,0.25) 72%, rgba(7,10,20,0.88) 100%);
}}
.burst {{
  position: absolute;
  inset: 0;
  opacity: 0.16;
  background: repeating-conic-gradient(from 0deg at 60% 68%, rgba(255,255,255,0.28) 0deg 2deg, transparent 2deg 11deg);
}}
.slash-line {{
  position: absolute;
  left: -120px;
  top: 790px;
  width: 1400px;
  height: 14px;
  background: linear-gradient(90deg, #06b6d4, #ffe600, #ec4899);
  transform: rotate(-16deg);
  box-shadow: 0 0 35px rgba(255, 230, 0, 0.85);
  z-index: 12;
  opacity: 0.92;
}}
.headline-wrap {{
  position: absolute;
  top: 84px;
  left: 0;
  right: 0;
  text-align: center;
  z-index: 25;
  transform: rotate(-2.5deg);
  padding: 0 28px;
}}
.hook-top {{
  font-family: 'BebasNeue', sans-serif;
  font-size: 146px;
  line-height: 0.90;
  color: #ffffff;
  letter-spacing: 4px;
  -webkit-text-stroke: 16px #000000;
  paint-order: stroke fill;
  text-shadow: 0 12px 0 #ec4899, 0 24px 45px rgba(0,0,0,0.95);
}}
.hook-main {{
  font-family: 'BebasNeue', sans-serif;
  font-size: 235px;
  line-height: 0.86;
  color: #ffe600;
  letter-spacing: 5px;
  -webkit-text-stroke: 20px #000000;
  paint-order: stroke fill;
  text-shadow: 0 15px 0 #ef4444, 0 28px 52px rgba(0,0,0,0.98);
  margin-top: 8px;
}}
.inset-cutout {{
  position: absolute;
  left: -25px;
  top: 470px;
  width: 670px;
  z-index: 20;
  filter: drop-shadow(0 0 34px rgba(6, 182, 212, 0.85)) drop-shadow(0 20px 35px rgba(0,0,0,0.9));
}}
.subject-cutout {{
  position: absolute;
  right: -35px;
  bottom: 0px;
  width: 1020px;
  max-height: 1120px;
  object-fit: contain;
  object-position: bottom right;
  z-index: 30;
  filter: drop-shadow(0 0 42px rgba(236, 72, 153, 0.9)) drop-shadow(0 22px 45px rgba(0,0,0,0.95));
}}
.subject-card {{
  position: absolute;
  left: 70px;
  right: 70px;
  bottom: 120px;
  height: 820px;
  object-fit: cover;
  border-radius: 36px;
  border: 10px solid #ffffff;
  z-index: 30;
  box-shadow: 0 0 45px rgba(236, 72, 153, 0.85), 0 24px 50px rgba(0,0,0,0.95);
}}
.curiosity-badge {{
  position: absolute;
  right: 52px;
  top: 710px;
  background: #ef4444;
  color: #ffffff;
  font-family: 'BebasNeue', sans-serif;
  font-size: 68px;
  letter-spacing: 3px;
  padding: 10px 30px;
  border-radius: 16px;
  border: 6px solid #ffe600;
  transform: rotate(7deg);
  z-index: 40;
  box-shadow: 0 14px 35px rgba(0,0,0,0.85);
}}
.arrow-svg {{
  position: absolute;
  left: 240px;
  top: 640px;
  width: 280px;
  height: 240px;
  z-index: 38;
  filter: drop-shadow(0 10px 18px rgba(0,0,0,0.9));
}}
</style>
</head>
<body>
  <div class="bg"></div>
  <div class="cinematic-overlay"></div>
  <div class="burst"></div>
  <div class="slash-line"></div>

  <div class="headline-wrap">
    <div class="hook-top">{hook_top}</div>
    <div class="hook-main">{hook_main}</div>
  </div>

  {inset_html}
  {arrow_html}

  <img class="{subj_class}" src="{subject_uri}" />
  <div class="curiosity-badge">{badge_text}</div>
</body>
</html>"""


def generate_cutout_thumbnail(video_path: str, out_path: str, hook_top: str, hook_main: str,
                              badge_text: str = 'KOK BISA?!', timestamp: float = None,
                              session=None) -> Path:
    video_p = Path(video_path)
    out_p = Path(out_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    work_dir = out_p.parent / '_tmp_cutout'
    work_dir.mkdir(exist_ok=True)

    if session is None:
        session = new_session('u2net_human_seg')

    if timestamp is None:
        dur = get_video_duration(video_p)
        timestamp = find_peak_timestamp(video_p, dur)

    bg_path, subject_png, has_cutout = extract_assets_from_video(video_p, timestamp, work_dir, session)

    html = build_html(
        bg_uri=img_to_data_uri(bg_path),
        subject_uri=img_to_data_uri(subject_png),
        hook_top=hook_top.upper(),
        hook_main=hook_main.upper(),
        badge_text=badge_text.upper(),
        has_cutout=has_cutout
    )

    html_file = work_dir / 'thumb.html'
    png_file = work_dir / 'thumb.png'
    html_file.write_text(html, encoding='utf-8')

    subprocess.run([
        '/usr/bin/chromium', '--headless', '--no-sandbox', '--disable-gpu',
        '--hide-scrollbars', '--window-size=1080,1920',
        f'--screenshot={png_file}', html_file.as_uri()
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    im = Image.open(png_file).convert('RGB')
    im.save(out_p, 'JPEG', quality=94, optimize=True)

    for f in work_dir.iterdir():
        f.unlink()
    work_dir.rmdir()

    print(f'[+] {out_p.parent.name}: {out_p.name} ({out_p.stat().st_size / 1024:.1f} KB) @ t={timestamp:.1f}s cutout={has_cutout}')
    return out_p


HOOK_MAP = {
    'ai_agent_1795395563': ('JOGET JASON', 'MERESAHKAN?!', 'GAJE PARAH!'),
    'ai_agent_1795372640': ('KITA NABRAK', 'KITA MENTAL?!', 'KOK BISA?!'),
    'ai_agent_maling_kualat': ('MALING MOTOR', 'KUALAT?!', 'KARMA INSTAN!'),
    'windah_live_clip_1_1795280844': ('CHAT JEBOL', 'NGAKAK?!', '4.8X SPIKE!'),
    'ai_agent_1795253581': ('DISIKSA ABIS', 'PASRAH?!', 'KENA MENTAL!'),
    'ai_livechat_1795250778': ('MOMEN GILA', 'GTA 6?!', 'LIVE CHAOS!'),
    'windah_parasut_landing': ('PAKE PARASUT', 'KENA MENTAL!', 'PLOT TWIST!'),
    'windah_jason_mandi': ('MANDI SENDIRI', 'DI MOTEL?!', 'SUS PARAH!'),
    'windah_prank_livechat': ('NYEBUR LAUT', 'KENA PRANK!', 'ZONK TOTAL!'),
    'windah_prank_senjata': ('SENJATA EMAS', 'DIBAWA?!', 'PRANK BOCIL!'),
    'windah_curhat_floating': ('1 VS 17.000', 'TROLL!', 'PICK ME?!'),
    'windah_curhat_17k': ('MATEMATIKA', 'BOCIL TROLL!', 'EMOSI JIWA!'),
    'windah_maling_nenek': ('KEJAR NENEK', 'KUALAT!', 'PANIK PARAH!'),
    'windah_pesawat_bocil': ('DISURUH LOMPAT', 'PESAWAT!', 'SCAM BOCIL!'),
    'windah_bagasi': ('MOBIL NYEBUR', 'TAS DI BAGASI!', 'TELAT BILANG!'),
    'tara_debat': ('DEBAT GPS', 'KE PENJARA!', 'NYASAR PARAH!'),
    'tara_nikah': ('UNTUNG GUA', 'UDAH KAWIN!', 'NO JOMBLO!'),
    'tara_tampar': ('SAMA GTA 5?', 'GUA TAMPAR!', '1 : 1000!'),
    'tara_airport': ('MAU TERBANG', 'BINTANG 4?!', 'PANIK PARAH!'),
    'windah_bkt': ('TEORI JALUR', 'BKT GTA 6?!', 'SKAKMAT!'),
    'windah_pesawat': ('PESAWAT', 'MELEDAK?!', 'EASTER EGG!'),
    'windah_explicit': ('TEMPAT SEPATU', 'DOLAR?!', 'MISTERI!'),
    'windah_club': ('SEPATU JOGET', 'HENING?!', 'SUS BANGET!'),
    'windah_bigfoot': ('KETEMU', 'BIGFOOT?!', 'REALITA GOFOOD!'),
    'windah_perfect_cut': ('SAMPAI PIPIS', 'TUMPE!', 'PERFECT CUT!'),
    'windah_rage': ('NGAMUK', 'DIATUR BOCIL!', 'KENA MENTAL!'),
}


def run_batch():
    html = Path('/data/html/clips/index.html').read_text(encoding='utf-8')
    m = re.search(r'const CLIPS = (\[.*?\]);\s*\n', html, re.S)
    clips = json.loads(m.group(1))
    session = new_session('u2net_human_seg')

    for c in clips:
        cid = c['id']
        if cid == 'ai_agent_1795395040':
            print(f'[=] Skipping {cid} (already custom Jason vs Windah cutout)')
            continue

        vurl = c['video_url'].lstrip('/')
        vpath = Path('/data/html/' + vurl) if vurl.startswith('clips/') else Path('/data/html/clips/' + vurl)
        if not vpath.exists():
            print(f'[!] Missing video: {vpath}')
            continue

        dest_dir = Path('/data/html/clips/files') / cid
        out_cutout = dest_dir / 'thumb_cutout.jpg'
        hook_top, hook_main, badge = HOOK_MAP.get(cid, ('MOMEN KOCAK', 'GTA 6?!', 'NGAKAK!'))
        generate_cutout_thumbnail(str(vpath), str(out_cutout), hook_top, hook_main, badge, session=session)
        shutil.copyfile(out_cutout, dest_dir / 'thumb_v1.jpg')
        shutil.copyfile(out_cutout, dest_dir / 'thumb.jpg')
        sm = Image.open(out_cutout).convert('RGB')
        sm.thumbnail((270, 480), Image.Resampling.LANCZOS)
        sm.save(dest_dir / 'thumb_sm.jpg', 'JPEG', quality=80, optimize=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--batch-all', action='store_true')
    p.add_argument('--video')
    p.add_argument('--out')
    p.add_argument('--hook-top', default='BRO PIKIR DIA')
    p.add_argument('--hook-main', default='JASON?!')
    p.add_argument('--badge', default='MIRIP GAK?!')
    p.add_argument('--time', type=float)
    args = p.parse_args()

    if args.batch_all:
        run_batch()
    elif args.video and args.out:
        generate_cutout_thumbnail(args.video, args.out, args.hook_top, args.hook_main, args.badge, args.time)
    else:
        p.print_help()
