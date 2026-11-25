#!/usr/bin/env python3
"""
Smart Context, Auto-Title, Dynamic ASS Subtitle & Auto-FX Analyzer.
Combines Audio RMS Peak Analysis + Faster-Whisper Transcription + Livechat Topic Clustering
(+ optional Gemini/Groq API enrichment if key exists in .env) to produce Golden Formula clips.
"""

import os
import re
import json
import subprocess
from collections import Counter
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"

SWEAR_RE = re.compile(r"\b(anjing|anjir|anjay|babi|bangsat|kontol|memek|tolol|goblok|bajingan|cok|cuk|asu)\b", re.I)
HYPE_SPEECH_RE = re.compile(
    r"\b(ngamuk|kaget|parah|gila|kocak|kualat|sabar|scam|prank|ban|mati|meledak|polisi|penjara|jason|lucia|bocil|troll|pick me|mental|kabur|maling|lompat)\b",
    re.I
)
CHAT_STOPWORDS = {
    "wkwk", "wkwkwk", "wkwkwkwk", "haha", "hahaha", "anjir", "anjay", "bang", "windah",
    "brando", "yang", "dan", "ini", "itu", "nya", "ada", "apa", "gak", "ga", "gk",
    "iya", "ya", "yg", "di", "ke", "dari", "buat", "sama", "aja", "kok", "sih", "nih",
    "lah", "kan", "dong", "deh", "tuh", "bgt", "banget", "parah", "ngakak", "kocak",
    "lmao", "lol", "kekw", "omg", "bro", "cuy", "guys", "ges", "min", "halo", "hai",
    "live", "gta", "gtavi", "gta6", "stream"
}


def load_env():
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


DOMAIN_FIXES = [
    (r"\bbanget\s+arah\b", "Bang Tara"),
    (r"\bbang\s+arah\b", "Bang Tara"),
    (r"\bgetenam\b", "GTA 6"),
    (r"\bgt\s*enam\b", "GTA 6"),
    (r"\bjasin\b", "Jason"),
    (r"\bweb,?\s*bang,?\s*tara\b", "W Bang Tara"),
    (r"\bel\s+bocil\b", "L bocil"),
    (r"\bcoikin\b", "cuekin"),
    (r"\bngajem\b", "nge-gym"),
    (r"\bbocil\s+boset\b", "bocil bosen"),
    (r"\bbocil\s+nguruh\b", "bocil nyuruh"),
    (r"\bilam\b", "Ilham"),
    (r"\bdaruh\s+nih,?\s*gis\b", "darah nih guys"),
    (r"\bdinikmatik\b", "dinikmatin"),
    (r"\bbernanya\b", "biarin aja"),
    (r"\bcepet-epet\b", "cepet-cepet"),
]

def fix_domain_typos(text: str) -> str:
    for pat, rep in DOMAIN_FIXES:
        text = re.sub(pat, rep, text, flags=re.I)
    return text

def censor_text(text: str) -> str:
    def _rep(m):
        w = m.group(0)
        return w[:2] + "*" * max(2, len(w) - 2)
    return re.sub(r"\b(anjing|babi|bangsat|kontol|memek|bajingan)\b", _rep, text, flags=re.I)


def get_duration(video_path: Path) -> float:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
            capture_output=True, text=True, check=True
        )
        return float(r.stdout.strip())
    except Exception:
        return 45.0


def analyze_audio_peaks(video_path: Path, duration: float):
    """Extract 1-second RMS energy profile and return (max_rms, median_rms, peak_timestamps)."""
    cmd = [
        "ffmpeg", "-i", str(video_path), "-af",
        "astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.RMS_level:file=-",
        "-f", "null", "-"
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=35)
    cur_t = 0.0
    sec_peaks = {}
    for line in r.stdout.splitlines():
        if "pts_time:" in line:
            try:
                cur_t = float(line.split("pts_time:")[1].split()[0])
            except ValueError:
                pass
        elif "RMS_level=" in line:
            raw = line.split("RMS_level=")[1].strip()
            try:
                val = float(raw)
                if val > -90.0:
                    b = int(cur_t)
                    if b not in sec_peaks or val > sec_peaks[b][0]:
                        sec_peaks[b] = (val, cur_t)
            except ValueError:
                pass

    if not sec_peaks:
        return -30.0, -35.0, [max(8.0, duration * 0.45)]

    all_vals = sorted(v for v, _ in sec_peaks.values())
    max_rms = all_vals[-1]
    median_rms = all_vals[len(all_vals) // 2]

    # Pick up to 2 distinct peaks (at least 7s apart, after 6s context rewind & before last 3s)
    candidates = [
        (v, t) for v, t in sec_peaks.values()
        if 6.5 <= t <= max(8.0, duration - 3.5)
    ]
    candidates.sort(key=lambda x: x[0], reverse=True)
    chosen = []
    for v, t in candidates:
        if all(abs(t - ct) >= 7.5 for ct in chosen):
            chosen.append(round(t, 2))
            if len(chosen) >= 2:
                break
    chosen.sort()
    return round(max_rms, 1), round(median_rms, 1), chosen


def transcribe_segments(video_path: Path):
    """Run faster-whisper (Indonesian) and return list of dicts {start, end, text}."""
    from faster_whisper import WhisperModel
    model = WhisperModel("base", device="cpu", compute_type="int8")
    segments, _ = model.transcribe(str(video_path), language="id", beam_size=5, vad_filter=True, initial_prompt="Windah Basudara, Bang Tara, Tara Arts, GTA 6, GTA VI, Jason, Lucia, bocil kematian, nge-gym, cuekin, W Bang Tara, L bocil, Ilham, Vice City.")
    out = []
    for s in segments:
        txt = fix_domain_typos(s.text.strip())
        if txt and len(txt) >= 2:
            out.append({"start": round(s.start, 2), "end": round(s.end, 2), "text": txt})
    return out


def write_styled_ass(segments, peak_times, output_ass: Path):
    """Generate Golden Formula ASS subtitles with White / Yellow Highlight / Magenta emphasis."""
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Bebas Neue,58,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,1.5,0,1,5.0,3.0,2,45,45,180,1
Style: Highlight,Bebas Neue,62,&H0000FFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,1.5,0,1,5.5,3.5,2,45,45,180,1
Style: Magenta,Bebas Neue,66,&H00CC44FF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,1.5,0,1,6.0,4.0,2,45,45,180,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    def fmt(sec):
        m, s = divmod(max(0.0, sec), 60)
        h, m = divmod(m, 60)
        cs = int((s % 1) * 100)
        return f"{int(h)}:{int(m):02d}:{int(s):02d}.{cs:02d}"

    lines = [header]
    for seg in segments:
        raw_txt = seg["text"]
        clean = censor_text(raw_txt).upper()
        mid = (seg["start"] + seg["end"]) / 2.0
        near_peak = any(abs(mid - pt) <= 2.2 for pt in peak_times)

        if SWEAR_RE.search(raw_txt) or near_peak:
            style = "Magenta"
        elif HYPE_SPEECH_RE.search(raw_txt) or "?" in raw_txt or "!" in raw_txt:
            style = "Highlight"
        else:
            style = "Default"

        lines.append(f"Dialogue: 0,{fmt(seg['start'])},{fmt(seg['end'])},{style},,0,0,0,,{clean}\n")

    output_ass.write_text("".join(lines), encoding="utf-8")


def try_llm_metadata(transcript_text: str, chat_samples: list, streamer_name: str):
    """Optional LLM title/hook generator if GEMINI_API_KEY or GROQ_API_KEY is set in .env."""
    env = load_env()
    prompt = (
        f"Kamu Art Director konten YouTube Shorts gaming Indonesia untuk streamer {streamer_name} main GTA 6.\n"
        f"Transkrip ucapan:\n{transcript_text[:1200]}\n\n"
        f"Sampel livechat saat momen ini:\n{', '.join(chat_samples[:15])}\n\n"
        "Balas HANYA JSON valid dengan key:\n"
        '{"worth_clipping": true/false, "reason": "singkat", '
        '"title": "JUDUL SEAM BAR MAX 5 KATA KAPITAL", '
        '"hook_top": "2 KATA BARIS 1 THUMBNAIL", '
        '"hook_main": "1-2 KATA KUNCI THUMBNAIL?!", '
        '"badge": "2 KATA BADGE REAKSI!", '
        '"summary": "1 kalimat ringkasan lucu", '
        '"copywriting": "caption viral tiktok/shorts + hashtag #GTA6 #WindahBasudara"}'
    )
    try:
        import requests
        if env.get("GROQ_API_KEY"):
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {env['GROQ_API_KEY']}"},
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.7
                },
                timeout=15
            )
            if r.ok:
                return json.loads(r.json()["choices"][0]["message"]["content"])
        if env.get("GEMINI_API_KEY"):
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={env['GEMINI_API_KEY']}"
            r = requests.post(
                url,
                json={"contents": [{"parts": [{"text": prompt}]}],
                      "generationConfig": {"responseMimeType": "application/json"}},
                timeout=15
            )
            if r.ok:
                txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(txt)
    except Exception as e:
        print(f"[!] Optional LLM skipped: {e}")
    return None


def local_smart_metadata(segments, peak_times, chat_samples, streamer_name: str):
    """100% local zero-API context & title extractor from Whisper transcript + livechat topics."""
    # 1. Extract top topic keywords from livechat
    chat_words = Counter()
    for msg in chat_samples:
        for w in re.findall(r"[a-zA-Z0-9]{3,}", msg.lower()):
            if w not in CHAT_STOPWORDS and not w.isdigit():
                chat_words[w] += 1
    top_chat_topics = [w.upper() for w, c in chat_words.most_common(3) if c >= 2]

    # 2. Find punchline segment closest to main audio peak
    punch_seg = None
    if segments:
        if peak_times:
            main_peak = peak_times[0]
            punch_seg = min(segments, key=lambda s: abs(((s["start"] + s["end"]) / 2.0) - main_peak))
        else:
            punch_seg = max(segments, key=lambda s: len(s["text"]))

    punch_clean = censor_text(punch_seg["text"]).strip() if punch_seg else ""
    punch_words = [w for w in re.findall(r"[A-Za-z0-9*]+", punch_clean.upper()) if len(w) >= 2]

    short_name = "WINDAH" if "windah" in streamer_name.lower() else "TARA" if "tara" in streamer_name.lower() else streamer_name.upper().split()[0]

    # Build punchy title (never generic "MOMEN SPONTAN"!)
    if punch_words and len(punch_words) >= 3:
        snippet = " ".join(punch_words[:4])
        title = f"{short_name}: {snippet}!"
        hook_top = " ".join(punch_words[:2])
        hook_main = " ".join(punch_words[2:4]) + "?!"
    elif top_chat_topics:
        topic = " ".join(top_chat_topics[:2])
        title = f"{short_name} HEBOH SOAL {topic}!"
        hook_top = f"{short_name} HEBOH"
        hook_main = f"{topic}?!"
    else:
        title = f"{short_name} KENA MENTAL DI GTA 6!"
        hook_top = f"{short_name}"
        hook_main = "KENA MENTAL?!"

    # Choose dynamic badge based on emotion
    full_txt = " ".join(s["text"] for s in segments)
    if SWEAR_RE.search(full_txt):
        badge = "EMOSI MELEDAK!"
    elif re.search(r"prank|scam|bohong|tipu|bocil", full_txt, re.I):
        badge = "KENA PRANK!"
    elif re.search(r"polisi|bintang|penjara|kabur|maling", full_txt, re.I):
        badge = "PANIK PARAH!"
    else:
        badge = "DILUAR NALAR!"

    excerpt = " ".join(censor_text(s["text"]) for s in segments[:4])[:220]
    topic_tag = f" (Chat ramai bahas: {', '.join(top_chat_topics)})" if top_chat_topics else ""
    summary = f"Momen kocak {streamer_name} di GTA 6: \"{punch_clean or excerpt}\"{topic_tag}"
    copywriting = (
        f"{title}\n\n"
        f"Detik-detik kocak {streamer_name} pas live GTA VI: \"{punch_clean or excerpt}\"\n"
        f"Menurut kalian gimana momen ini? Tulis di komentar!\n\n"
        f"#GTA6 #GTAVI #{short_name.capitalize()} #WindahBasudara #GamingIndonesia #Shorts #FYP"
    )
    return {
        "worth_clipping": True,
        "reason": "Vocal reaction + chat spike verified",
        "title": title[:44],
        "hook_top": hook_top[:16],
        "hook_main": hook_main[:16],
        "badge": badge,
        "summary": summary,
        "copywriting": copywriting
    }


def analyze_clip(video_path: str, ass_out: str, chat_samples=None, streamer_name: str = "Windah Basudara"):
    """Full context + quality + FX director analysis for a raw clip."""
    video_p = Path(video_path)
    ass_p = Path(ass_out)
    chat_samples = chat_samples or []

    duration = get_duration(video_p)
    max_rms, median_rms, peak_times = analyze_audio_peaks(video_p, duration)
    segments = transcribe_segments(video_p)

    # Dual-Signal Quality Gate (anti random bocil chat spam when streamer is silent)
    speech_words = sum(len(s["text"].split()) for s in segments)
    dynamic_jump = max_rms - median_rms
    worth_clipping = True
    reject_reason = ""
    if speech_words < 5 and max_rms < -15.0:
        worth_clipping = False
        reject_reason = f"Streamer diam/minim dialog (words={speech_words}, max_rms={max_rms}dB)"
    elif max_rms < -22.0 and dynamic_jump < 4.0:
        worth_clipping = False
        reject_reason = f"Audio terlalu datar/monoton (max_rms={max_rms}dB, jump={dynamic_jump:.1f}dB)"

    # Trim dead tail for Perfect Cut Comedy right after last vocal segment (if within clip)
    perfect_cut_dur = min(duration, 48.0)
    if segments:
        last_speech_end = segments[-1]["end"]
        if 20.0 <= last_speech_end <= duration - 2.0:
            perfect_cut_dur = round(min(duration, last_speech_end + 0.35), 2)

    # Filter peaks within perfect_cut_dur
    valid_peaks = [t for t in peak_times if 5.0 <= t <= perfect_cut_dur - 2.0]
    if not valid_peaks:
        valid_peaks = [round(perfect_cut_dur * 0.55, 2)]

    write_styled_ass(segments, valid_peaks, ass_p)

    # Build FX expressions (Zoom 1.5x, Micro Shake, 1-Frame Flash, SFX)
    zoom_parts = [f"between(t,{t:.2f},{min(perfect_cut_dur, t + 2.6):.2f})" for t in valid_peaks]
    shake_parts = [f"between(t,{t:.2f},{t + 0.35:.2f})" for t in valid_peaks]
    flash_parts = [f"between(t,{t:.2f},{t + 0.06:.2f})" for t in valid_peaks]

    sfx_items = []
    # 1. Auto Dolphin censor on swear words (max 2 to stay tasteful)
    censor_count = 0
    for seg in segments:
        if seg["start"] < perfect_cut_dur - 1.0 and SWEAR_RE.search(seg["text"]):
            t_cen = round(seg["start"] + max(0.0, (seg["end"] - seg["start"]) * 0.5), 2)
            sfx_items.append(f"delfin@{t_cen}")
            censor_count += 1
            if censor_count >= 2:
                break

    # 2. Vine Boom on punchline peaks (max 2)
    for pt in valid_peaks[:2]:
        sfx_items.append(f"vine_boom@{pt:.2f}")

    # 3. FAAH on Perfect Cut black screen ending
    sfx_items.append(f"faah@{perfect_cut_dur:.2f}")

    # Metadata (LLM if configured, else local smart extractor)
    full_transcript = "\n".join(f"[{s['start']:.1f}s] {s['text']}" for s in segments)
    meta = try_llm_metadata(full_transcript, chat_samples, streamer_name)
    if not meta:
        meta = local_smart_metadata(segments, valid_peaks, chat_samples, streamer_name)
    if not worth_clipping:
        meta["worth_clipping"] = False
        meta["reason"] = reject_reason

    return {
        "worth_clipping": meta.get("worth_clipping", True),
        "reason": meta.get("reason", ""),
        "clip_duration": perfect_cut_dur,
        "total_duration": round(perfect_cut_dur + 1.0, 2),  # +1.0s Perfect Cut black screen
        "max_rms": max_rms,
        "peaks": valid_peaks,
        "zoom_expr": "+".join(zoom_parts) if zoom_parts else "0",
        "shake_expr": "+".join(shake_parts) if shake_parts else "0",
        "flash_expr": "+".join(flash_parts) if flash_parts else "0",
        "sfx_list": ",".join(sfx_items),
        "title": meta["title"],
        "hook_top": meta["hook_top"],
        "hook_main": meta["hook_main"],
        "badge": meta["badge"],
        "summary": meta["summary"],
        "copywriting": meta["copywriting"],
        "transcript_preview": " ".join(censor_text(s["text"]) for s in segments[:5])[:260]
    }


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--video", required=True)
    p.add_argument("--ass", required=True)
    p.add_argument("--streamer", default="Windah Basudara")
    p.add_argument("--chat-json", help="Optional JSON file with list of chat strings")
    args = p.parse_args()
    chats = json.loads(Path(args.chat_json).read_text()) if args.chat_json and Path(args.chat_json).exists() else []
    res = analyze_clip(args.video, args.ass, chats, args.streamer)
    print(json.dumps(res, indent=2, ensure_ascii=False))
