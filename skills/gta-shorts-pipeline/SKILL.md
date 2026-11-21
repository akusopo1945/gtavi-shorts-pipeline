---
name: gta-shorts-pipeline
description: Pipeline otomatisasi produksi video vertikal Shorts/Reels/TikTok (1080x1920 60fps) gameplay GTA 6 dari live streaming kreator (Windah Basudara, Tara Arts, dll). Mendukung auto-transcribe faster-whisper, facecam calibrated zoom, seam neon divider, ASS typography, SFX mix, dan faststart streaming.
---

# GTA Shorts Pipeline Guide

## Standar Output
- **Resolusi**: 1080x1920 (Vertical 9:16) @ 60 FPS
- **Durasi**: Strictly 30 - 60 detik (target optimal 45s - 55s)
- **Struktur Layout**:
  - `y = 0..820`: Streamer Facecam (Crop calibrated + Snap Zoom 1.5x di klimaks/punchline)
  - `y = 820..940`: Seam Divider 120px dengan border neon & judul Bebas Neue Bold
  - `y = 940..1920`: Gameplay 1080x980 (Crop 1440:1080:0:0)
- **Subtitles**: Bebas Neue Bold (ukuran 58-62) di posisi MarginV 1110 (area atas gameplay)
- **Audio**: Stream audio + Sound Effects (whoosh, anime wow, vine boom, undertaker, faah) + `loudnorm=I=-14:LRA=11:TP=-1.5`
- **Container**: MP4 wajib memakai `-movflags +faststart` untuk streaming & instant download.

---

## Struktur File Proyek
```
gtavi-claudecode/
├── assets/
│   ├── fonts/           # Bebas Neue Bold, Montserrat (OTF/TTF)
│   ├── sfx/             # Vine Boom, FAAH, Undertaker, Anime Wow, Whoosh
│   └── memes/           # Meme overlays & assets
├── engine/
│   ├── clipper.py       # Universal Declarative CLI
│   └── profiles.json    # Profil crop facecam & warna streamer
├── requirements.txt     # faster-whisper, yt-dlp, Pillow, numpy
├── setup.sh             # Script 1-klik deploy di VPS/mesin baru
└── skills/
    └── gta-shorts-pipeline/SKILL.md
```

---

## Cara Menjalankan Engine CLI

### Sintaks Dasar:
```bash
./venv/bin/python engine/clipper.py \
  --id "<unique_slug>" \
  --streamer "<windah|tara|default>" \
  --title "<JUDUL KONTEN DI SEAM BAR>" \
  --url "<YOUTUBE_STREAM_URL>" \
  --range "<HH:MM:SS-HH:MM:SS>" \
  --duration <detik> \
  --zoom "<ffmpeg_between_expression>" \
  --sfx "whoosh@10,wow@25,boom@35,bell@47,faah@53" \
  --summary "<deskripsi_singkat>" \
  --copywriting "<teks_caption_lengkap>"
```

### Parameter:
- `--streamer`: Mengambil konfigurasi crop facecam otomatis dari `engine/profiles.json`.
- `--zoom`: Ekspresi FFmpeg boolean, contoh: `(between(t,25.0,29.5)+between(t,34.8,46.5))`.
- `--sfx`: Pasangan nama SFX dan detik aktivasi, dipisahkan koma.
- `--range`: Rentang potong dari full video YouTube, misal: `02:14:05-02:15:00`.
