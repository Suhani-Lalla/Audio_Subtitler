# orchestrator.py
import os
import json
import asyncio
import tempfile
import uuid
from typing import Optional, List, Dict
from contextlib import asynccontextmanager
import multipart, io
import httpx
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
import zipfile
# =======================
# Config & Environment
# =======================
load_dotenv()

EXTRACTOR_URL = os.getenv("EXTRACTOR_URL", "https://9b57ef0fb8a7.ngrok-free.app/transcribe")
TRANSLATOR_URL = os.getenv("TRANSLATOR_URL", "https://your-render-translate.onrender.com/translate")
OVERLAY_URL    = os.getenv("OVERLAY_URL",    "https://your-render-overlay.onrender.com/overlay")

CONNECT_TIMEOUT = float(os.getenv("CONNECT_TIMEOUT", "15"))
READ_TIMEOUT    = float(os.getenv("READ_TIMEOUT", "300"))
TOTAL_TIMEOUT   = float(os.getenv("TOTAL_TIMEOUT", "600"))

MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
INITIAL_BACKOFF = float(os.getenv("INITIAL_BACKOFF", "0.8"))
BACKOFF_FACTOR = float(os.getenv("BACKOFF_FACTOR", "1.8"))

# In-memory job store (could later be replaced by Redis, DB, etc.)
JOB_STORE: Dict[str, Dict[str, str]] = {}

# =======================
# Utilities
# =======================
def _headers() -> Dict[str, str]:
    return {"Accept": "*/*"}


async def _sleep_backoff(attempt: int) -> None:
    delay = INITIAL_BACKOFF * (BACKOFF_FACTOR ** attempt)
    await asyncio.sleep(delay)

@asynccontextmanager
async def get_httpx_client():
    timeout = httpx.Timeout(
        connect=CONNECT_TIMEOUT,
        read=READ_TIMEOUT,
        write=READ_TIMEOUT,
        pool=TOTAL_TIMEOUT
    )
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        yield client

def _save_temp_bytes(data: bytes, suffix: str) -> str:
    path = tempfile.mkstemp(suffix=suffix)[1]
    with open(path, "wb") as f:
        f.write(data)
    return path

# =======================
# Orchestration Steps
# =======================
async def call_extractor(video_path: str) -> (str, str):
    """Extractor now returns a ZIP containing .srt and .txt files."""
    for attempt in range(MAX_RETRIES):
        try:
            async with get_httpx_client() as client:
                with open(video_path, "rb") as f:
                    files = {"file": (os.path.basename(video_path), f, "video/mp4")}
                    r = await client.post(EXTRACTOR_URL, files=files, headers=_headers())

                if r.is_error:
                    raise HTTPException(status_code=502, detail=f"Extractor error: {r.status_code} {r.text}")

                # Handle zip file in memory
                srt_path = txt_path = None
                try:
                    zip_bytes = io.BytesIO(r.content)
                    with zipfile.ZipFile(zip_bytes) as zf:
                        for name in zf.namelist():
                            if name.endswith(".srt"):
                                srt_path = _save_temp_bytes(zf.read(name), ".srt")
                            elif name.endswith(".txt"):
                                txt_path = _save_temp_bytes(zf.read(name), ".txt")
                except Exception as e:
                    raise HTTPException(status_code=502, detail=f"Invalid extractor ZIP: {e}")

                if not (srt_path and txt_path):
                    raise HTTPException(status_code=502, detail="Extractor ZIP missing .srt or .txt")

                return srt_path, txt_path

        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                await _sleep_backoff(attempt)
                continue
            raise HTTPException(status_code=502, detail=f"Extractor call failed: {e}")

async def call_translator(srt_path: str, txt_path: str, target_lang: str) -> str:
    """Translator returns translated .srt."""
    for attempt in range(MAX_RETRIES):
        try:
            async with get_httpx_client() as client:
                with open(srt_path, "rb") as sf, open(txt_path, "rb") as tf:
                    files = {
                        "srt": (os.path.basename(srt_path), sf, "text/plain"),
                        "script": (os.path.basename(txt_path), tf, "text/plain"),
                    }
                    data = {"target_lang": target_lang}
                    r = await client.post(TRANSLATOR_URL, files=files, data=data, headers=_headers())

                if r.is_error:
                    raise HTTPException(status_code=502, detail=f"Translator error: {r.status_code} {r.text}")

                return _save_temp_bytes(r.content, ".srt")

        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                await _sleep_backoff(attempt)
                continue
            raise HTTPException(status_code=502, detail=f"Translator call failed: {e}")

async def call_overlay(video_path: str, translated_srt_path: str, style_json: str) -> str:
    """Overlay requires video + translated SRT + style JSON."""
    try:
        json.loads(style_json)
    except Exception:
        raise HTTPException(status_code=422, detail="style_json must be valid JSON string")

    for attempt in range(MAX_RETRIES):
        try:
            async with get_httpx_client() as client:
                with open(video_path, "rb") as vf, open(translated_srt_path, "rb") as sf:
                    files = {
                        "video": (os.path.basename(video_path), vf, "video/mp4"),
                        "srt": (os.path.basename(translated_srt_path), sf, "text/plain"),
                    }
                    data = {"style_json": style_json}
                    r = await client.post(OVERLAY_URL, files=files, data=data, headers=_headers())
                if r.is_error:
                    raise HTTPException(status_code=502, detail=f"Overlay error: {r.status_code} {r.text}")

                return _save_temp_bytes(r.content, ".mp4")

        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                await _sleep_backoff(attempt)
                continue
            raise HTTPException(status_code=502, detail=f"Overlay call failed: {e}")


# =======================
# FastAPI App
# =======================
app = FastAPI(title="Subtitle Pipeline", version="1.0.0")

# Enable CORS so frontend can call this service directly
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # for now allow all, later restrict to your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/process_initial")
async def process_initial(
    file: UploadFile = File(..., description="Source video file (mp4/mov/etc.)"),
    target_lang: str = Form(..., description="Target language code (e.g., 'ja', 'Japanese')")
):
    """
    Step 1: Extractor + Translator.
    Stores video + translated SRT in JOB_STORE and returns job_id.
    """
    try:
        # Save incoming video
        video_suffix = os.path.splitext(file.filename or "")[1] or ".mp4"
        video_path = tempfile.mkstemp(suffix=video_suffix)[1]
        content = await file.read()
        with open(video_path, "wb") as vf:
            vf.write(content)

        # Extractor
        base_srt_path, base_txt_path = await call_extractor(video_path)

        # Translator
        translated_srt_path = await call_translator(base_srt_path, base_txt_path, target_lang)

        # Register job
        job_id = uuid.uuid4().hex
        JOB_STORE[job_id] = {
            "video": video_path,
            "srt": translated_srt_path
        }

        return {"job_id": job_id, "message": "Translation ready. Use this job_id for overlay."}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"process_initial failed: {e}")


@app.post("/overlay")
async def overlay_endpoint(
    job_id: str = Form(..., description="Job ID from /process_initial"),
    style_json: str = Form(..., description="Overlay style JSON as string (required)")
):
    """
    Step 2: Overlay.
    Uses stored video + translated SRT from JOB_STORE.
    Returns final MP4 with burned-in subtitles.
    """
    try:
        if job_id not in JOB_STORE:
            raise HTTPException(status_code=404, detail="Invalid job_id or expired job")

        video_path = JOB_STORE[job_id]["video"]
        srt_path = JOB_STORE[job_id]["srt"]

        # Overlay
        final_video_path = await call_overlay(video_path, srt_path, style_json)

        # Stream final video
        def iterfile():
            with open(final_video_path, "rb") as f:
                for chunk in iter(lambda: f.read(1024 * 1024), b""):
                    yield chunk

        filename = f"final_{uuid.uuid4().hex}.mp4"
        return StreamingResponse(
            iterfile(),
            media_type="video/mp4",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            background=BackgroundTask(lambda: os.remove(final_video_path))
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"overlay failed: {e}")


@app.get("/healthz")
async def healthz():
    return {"ok": True, "jobs_active": len(JOB_STORE)}
