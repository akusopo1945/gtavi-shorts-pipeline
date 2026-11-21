#!/usr/bin/env python3
"""
AI Brain untuk Luna Content Studio
Menerjemahkan instruksi bahasa alami user (teks / voice note) -> Aksi Tool Editing & Clipper
"""

import os
import sys
import json
import re
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ENGINE_DIR = BASE_DIR / "engine"
JOBS_DIR = BASE_DIR / "jobs"
SUBS_VTT = JOBS_DIR / "windah_gp4" / "subs.id.vtt"
COMMENTS_JSON = JOBS_DIR / "windah_gp4" / "all_comments.info.json"

def search_stream_transcript(keywords, max_results=3):
    """Cari momen lucu di transkrip VTT berdasarkan kata kunci."""
    if not SUBS_VTT.exists():
        return []
        
    results = []
    with open(SUBS_VTT, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    for i, line in enumerate(lines):
        line_lower = line.lower()
        if any(kw.lower() in line_lower for kw in keywords):
            # Ambil timestamp dan teks sekitar
            t_line = ""
            for k in range(max(0, i-4), i+1):
                if "-->" in lines[k]:
                    t_line = lines[k].split("-->")[0].strip()
                    break
            context = "".join(lines[max(0, i-2):min(len(lines), i+4)]).replace("\n", " ").strip()
            if t_line:
                results.append({"time": t_line, "context": context[:120]})
                if len(results) >= max_results:
                    break
    return results

def search_top_comment_moments(query_terms):
    """Cari momen rekomendasi penonton di komentar YouTube."""
    if not COMMENTS_JSON.exists():
        return []
        
    with open(COMMENTS_JSON, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    comments = data.get("comments", [])
    matched = []
    pattern = re.compile(r'(\b\d{1,2}:\d{2}(?::\d{2})?\b)')
    
    for c in comments:
        text = c.get("text", "")
        times = pattern.findall(text)
        if times:
            t_lower = text.lower()
            if any(q.lower() in t_lower for q in query_terms):
                matched.append({
                    "time": times[0],
                    "author": c.get("author", "Netizen"),
                    "text": text[:100],
                    "likes": c.get("like_count", 0)
                })
    matched.sort(key=lambda x: x["likes"], reverse=True)
    return matched[:3]

def parse_user_intent(prompt_text):
    """Menganalisis prompt user untuk menentukan aksi editing yang tepat."""
    prompt_lower = prompt_text.lower()
    
    # 1. Cek intent bikin / cari klip
    if any(w in prompt_lower for w in ["potong", "buatkan klip", "bikin klip", "cari momen", "clip", "momen"]):
        # Ekstrak kata kunci topik
        keywords = []
        for kw in ["jason", "mandi", "parasut", "senjata", "maling", "nenek", "pesawat", "bagasi", "buaya", "curhat", "matematika", "kaget", "teriak"]:
            if kw in prompt_lower:
                keywords.append(kw)
        if not keywords:
            keywords = ["kocak", "ngakak", "parah"]
            
        momen_comments = search_top_comment_moments(keywords)
        momen_vtt = search_stream_transcript(keywords)
        
        return {
            "intent": "create_clip",
            "keywords": keywords,
            "comment_matches": momen_comments,
            "transcript_matches": momen_vtt,
            "detected_style": "livechat" if "chat" in prompt_lower else "clean"
        }
        
    # 2. Cek intent copywriting
    elif any(w in prompt_lower for w in ["caption", "copywriting", "judul", "hashtag"]):
        return {
            "intent": "generate_copywriting",
            "prompt": prompt_text
        }
        
    # 3. Chat umum / ide kreatif
    return {
        "intent": "chat",
        "prompt": prompt_text
    }

def format_ai_response(intent_data):
    intent = intent_data["intent"]
    
    if intent == "create_clip":
        kw_str = ", ".join(intent_data["keywords"])
        comms = intent_data["comment_matches"]
        vtt = intent_data["transcript_matches"]
        
        reply = [f"🎯 *LUNA AI MENEMUKAN MOMEN VIRAL:* (Topik: `{kw_str}`)\n"]
        
        options = []
        if comms:
            reply.append("📌 *Rekomendasi dari Komentar Penonton:*")
            for i, c in enumerate(comms, 1):
                reply.append(f"{i}. ⏱️ `{c['time']}` — @{c['author']}")
                reply.append(f"   *\"{c['text']}\"*")
                options.append(c['time'])
            reply.append("")
            
        if vtt and not comms:
            reply.append("📌 *Ditemukan dari Dialog Transkrip:*")
            for i, v in enumerate(vtt, 1):
                reply.append(f"{i}. ⏱️ `{v['time']}` — \"{v['context']}...\"")
                options.append(v['time'])
            reply.append("")
            
        best_time = options[0] if options else "00:42:15"
        reply.append(f"💡 *Saran Eksekusi Terbaik*: Momen di `{best_time}`")
        reply.append("Pilih gaya render yang kamu inginkan di bawah ini:")
        
        return "\n".join(reply), best_time
        
    elif intent == "generate_copywriting":
        return (
            "📝 *REKOMENDASI COPYWRITING SHORTS / TIKTOK*\n\n"
            "🔥 *Opsi Judul (High Click-Through Rate):*\n"
            "1. WINDAH BIKIN NETIZEN KAGET LAGI DI GTA 6?! 💀\n"
            "2. NIATNYA KEREN ENDINGNYA KENA MENTAL BRUTAL 😂🪂\n"
            "3. DETIK-DETIK MOMEN PALING KOCAK DI STREAM INI!\n\n"
            "📌 *Hashtags FYP:*\n"
            "#windahbasudara #gta6 #gtavi #lucubanget #shorts #gamingindo #fyp",
            None
        )
        
    return (
        "🤖 *Luna AI Assistant siap!* Kamu bisa kirim perintah apa saja, contohnya:\n"
        "• *\"Cariin momen pas Windah kaget\"*\n"
        "• *\"Bikinin caption TikTok yang bikin penasaran\"*\n"
        "• *\"Potong 50 detik dari menit 02:14:12\"*\n"
        "• Atau kirim *Voice Note* langsung di chat ini!",
        None
    )
