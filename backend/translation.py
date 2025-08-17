# translation.py
from fastapi import APIRouter, File, UploadFile, Form
from fastapi.responses import FileResponse, JSONResponse
import os, shutil, tempfile, re, json
from dotenv import load_dotenv

# ================== Google AI (Gemini) Setup ==================
load_dotenv()
GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY")

GOOGLE_AI_AVAILABLE = False
model = None
try:
    import google.generativeai as genai
    if GEMINI_API_KEY:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-2.0-flash")
        GOOGLE_AI_AVAILABLE = True
    else:
        print("⚠️ GOOGLE_API_KEY not set — translation will use fallback (echo).")
except Exception as e:
    print(f"⚠️ google generative ai not available — fallback (echo). Details: {e}")

# ================== FastAPI Router ==================
router = APIRouter()

# ================== Helpers (ported & trimmed) ==================

def parse_script_file(script_path: str):
    """Parse a scene script: 'Speaker: text' → [{'speaker','text'}, ...]"""
    dialogue = []
    with open(script_path, 'r', encoding='utf-8') as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            if ':' in line:
                speaker, text = line.split(':', 1)
                dialogue.append({'speaker': speaker.strip(), 'text': text.strip()})
            else:
                dialogue.append({'speaker': 'Unknown', 'text': line})
    return dialogue

def parse_srt_file(srt_path: str):
    """Parse .srt to [{'index','start','end','text'}]"""
    subs = []
    with open(srt_path, 'r', encoding='utf-8') as f:
        content = f.read()
    blocks = re.split(r'\n\s*\n', content.strip())
    for block in blocks:
        lines = block.split('\n')
        if len(lines) >= 3:
            idx = lines[0].strip()
            times = lines[1].strip()
            text = ' '.join(lines[2:]).strip()
            if ' --> ' in times:
                start, end = times.split(' --> ')
                try:
                    subs.append({
                        'index': int(idx),
                        'start': start,
                        'end': end,
                        'text': text
                    })
                except:
                    # Skip malformed block
                    pass
    return subs

def generate_translation_prompt(dialogue, target_lang: str):
    dialogue_text = "\n".join([f"{d['speaker']}: {d['text']}" for d in dialogue])
    return f"""
You are a professional subtitler like Netflix's best localization experts.
Translate the following scene dialogue into {target_lang}, preserving emotional tone, idioms, slang, and natural fluency.
Return lines ONLY in the format: SpeakerName: Translated text
Do NOT add numbering, timestamps, or extra commentary.

{dialogue_text}
"""

def translate_scene(dialogue, target_lang: str):
    """Translate the whole scene using context. Fallback = echo source."""
    if not GOOGLE_AI_AVAILABLE or not model:
        return "\n".join([f"{d['speaker']}: {d['text']}" for d in dialogue])

    try:
        prompt = generate_translation_prompt(dialogue, target_lang)
        resp = model.generate_content(prompt)
        return (resp.text or "").strip()
    except Exception as e:
        print(f"⚠️ Scene translation failed: {e} — falling back to echo.")
        return "\n".join([f"{d['speaker']}: {d['text']}" for d in dialogue])

def parse_translated_dialogue(translated_text: str):
    """Parse 'Speaker: text' lines to [{'speaker','text'}]"""
    out = []
    for raw in translated_text.split('\n'):
        line = raw.strip()
        if not line:
            continue
        if ':' in line:
            speaker, text = line.split(':', 1)
            out.append({'speaker': speaker.strip(), 'text': text.strip()})
        else:
            out.append({'speaker': 'Unknown', 'text': line})
    return out

# --- Japanese cleanup for better MT quality ---
_jp = re.compile(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]')
def clean_japanese_text(text: str) -> str:
    if _jp.search(text):
        cleaned = re.sub(r'([\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF])\s+([\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF])', r'\1\2', text)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        return cleaned
    return text

def translate_line(text: str, target_lang: str, max_retries: int = 3) -> str:
    """Per-line translation with retries + JP cleanup. Fallback = echo."""
    if not GOOGLE_AI_AVAILABLE or not model:
        return text

    cleaned = clean_japanese_text(text)
    prompt = (
        f"You are a professional subtitle translator. Translate into {target_lang}.\n"
        f'Original: "{cleaned}"\n'
        "Output ONLY the translation, no quotes, no extra text."
    )

    for attempt in range(max_retries):
        try:
            resp = model.generate_content(prompt)
            translated = (resp.text or "").strip()
            if translated and translated != cleaned:
                return translated
            else:
                print(f"[warn] empty/identical translation attempt {attempt+1} for: {cleaned[:50]}...")
        except Exception as e:
            print(f"[warn] line translation attempt {attempt+1} failed: {e}")

    return f"[TRANSLATION FAILED] {text}"

def choose_best_variant(original_text: str, variants_text: str, target_lang: str) -> str:
    """
    If a source line has variants separated by '/', ask the model to pick the best.
    Not strictly needed if your data has no variants, but included for parity.
    """
    variants = [v.strip() for v in variants_text.split('/') if v.strip()]
    if len(variants) <= 1:
        return variants[0] if variants else original_text

    if not GOOGLE_AI_AVAILABLE or not model:
        return variants[0]

    prompt = (
        f'Choose the best {target_lang} subtitle for the original:\n'
        f'Original: "{original_text}"\n'
        "Options:\n" + "\n".join(f"- {v}" for v in variants) + "\n"
        "Reply with ONLY the chosen option text."
    )
    try:
        resp = model.generate_content(prompt)
        return (resp.text or "").strip() or variants[0]
    except Exception as e:
        print(f"[warn] variant choice failed: {e}")
        return variants[0]

def align_translations_to_srt(srt_subtitles, translated_dialogue, target_lang: str):
    """
    Align scene-level translated lines to SRT lines. If we run out,
    fallback to per-line translation. Also retry failures.
    """
    aligned = []
    td_i = 0
    print(f"[debug] SRT lines={len(srt_subtitles)}, scene lines={len(translated_dialogue)}")

    for i, sub in enumerate(srt_subtitles):
        # If the source subtitle has slash-variants, optionally pick one first
        source_text = sub['text']
        if '/' in source_text:
            chosen = choose_best_variant(source_text, source_text, target_lang)
        else:
            chosen = source_text

        if td_i < len(translated_dialogue):
            translated_text = translated_dialogue[td_i]['text']
            td_i += 1
        else:
            translated_text = translate_line(chosen, target_lang)

        if translated_text.startswith("[TRANSLATION FAILED]"):
            retry = translate_line(chosen, target_lang, max_retries=1)
            if not retry.startswith("[TRANSLATION FAILED]"):
                translated_text = retry

        aligned.append({
            'index': sub['index'],
            'start': sub['start'],
            'end': sub['end'],
            'translated_text': translated_text
        })

    if len(translated_dialogue) > len(srt_subtitles):
        print(f"[warn] Unused scene lines: {len(translated_dialogue) - len(srt_subtitles)}")

    return aligned

def translation_stats(aligned, target_language: str):
    total = len(aligned)
    failed = [s for s in aligned if s['translated_text'].startswith("[TRANSLATION FAILED]")]
    ok = total - len(failed)
    rate = (ok / total * 100.0) if total else 0.0
    return {
        "language": target_language,
        "total_lines": total,
        "translated": ok,
        "failed": len(failed),
        "success_rate_pct": round(rate, 1),
        "failed_indices": [s['index'] for s in failed]
    }

def write_srt_file(aligned, output_path: str):
    with open(output_path, 'w', encoding='utf-8') as f:
        for sub in aligned:
            f.write(f"{sub['index']}\n")
            f.write(f"{sub['start']} --> {sub['end']}\n")
            f.write(f"{sub['translated_text']}\n\n")

# ================== Endpoint ==================

@router.post("/translate")
async def translate_endpoint(
    srt: UploadFile = File(...),
    target_lang: str = Form(...),
    script: UploadFile | None = File(None),     # optional: better context if provided
    return_json_stats: bool = Form(False)       # optional: include stats JSON with file
):
    """
    Inputs:
      - srt: original subtitles (.srt)
      - target_lang: e.g., "Japanese", "Spanish", "fr", etc.
      - script (optional): scene/script text file with lines like 'Speaker: text'
      - return_json_stats (optional): if True returns JSON + SRT path; else returns the .srt file directly
    Output:
      - translated_{target_lang}.srt (FileResponse) OR JSON with stats + temp path
    """
    tmpdir = tempfile.mkdtemp()
    try:
        # Save inputs
        srt_path = os.path.join(tmpdir, srt.filename or "input.srt")
        with open(srt_path, "wb") as f:
            shutil.copyfileobj(srt.file, f)

        script_path = None
        if script is not None:
            script_path = os.path.join(tmpdir, script.filename or "script.txt")
            with open(script_path, "wb") as f:
                shutil.copyfileobj(script.file, f)

        # Parse
        srt_subs = parse_srt_file(srt_path)

        translated_dialogue = []
        if script_path:  # Context-aware scene translation
            dialogue = parse_script_file(script_path)
            scene_text = translate_scene(dialogue, target_lang)
            translated_dialogue = parse_translated_dialogue(scene_text)

        # Align (with fallback per-line translation)
        aligned = align_translations_to_srt(srt_subs, translated_dialogue, target_lang)

        # Write output
        out_path = os.path.join(tmpdir, f"translated_{target_lang}.srt")
        write_srt_file(aligned, out_path)

        # Build stats (optional)
        stats = translation_stats(aligned, target_lang)

        if return_json_stats:
            # Return JSON (path is temp; orchestrator can fetch file immediately)
            return JSONResponse({
                "ok": True,
                "output_srt_path": out_path,
                "stats": stats
            })

        # Default: return the SRT file directly
        return FileResponse(out_path,
                            filename=f"translated_{target_lang}.srt",
                            media_type="text/plain")

    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
