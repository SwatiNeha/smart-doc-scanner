# fastapi_app.py
import os
import asyncio
from typing import List, Dict, Any
import io
import re
import json
import time
import cv2
import numpy as np
import pytesseract
from PIL import Image
from fastapi import FastAPI, File, UploadFile, HTTPException, Header, Query, Request
from pydantic import BaseModel
from fastapi.concurrency import run_in_threadpool
import httpx

# ===================== Config =====================
# Point this to your local LLM server (LM Studio default shown)
OLLAMA_BASE = os.getenv("OLLAMA_BASE", "http://localhost:11434/v1")
LLM_MODEL   = os.getenv("LLM_MODEL", "gemma3:latest")   # must match /v1/models exactly
OLLAMA_KEY  = os.getenv("OLLAMA_KEY", "")               # usually empty for LM Studio

# Simple header auth for your API (not the LLM). Leave empty to disable.
API_KEY = os.getenv("API_KEY", "")

# Tesseract path on Windows (adjust if needed)
TESSERACT_CMD = os.getenv("TESSERACT_CMD", r"C:\Program Files\Tesseract-OCR\tesseract.exe")
if os.path.exists(TESSERACT_CMD):
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

# OCR/LLM speed knobs
TESS_CONFIG   = r"--oem 1 --psm 6"
MAX_WIDTH     = 1400      # downscale big scans
UPSCALE_MIN   = 800       # gently upscale tiny receipts only
UPSCALE_FX    = 1.5
MAX_OCR_CHARS = 3000      # hard cap text sent to LLM

# ===================== App & Client =====================
app = FastAPI(title="Smart Invoice Extractor API", version="2.0.0")
client: httpx.AsyncClient | None = None

@app.on_event("startup")
async def _startup():
    """Create a pooled HTTP client and fail fast if LLM server is down."""
    global client
    client = httpx.AsyncClient(
        base_url=OLLAMA_BASE,
        http2=False,  # Windows + many local servers prefer HTTP/1.1
        timeout=httpx.Timeout(connect=5, read=180, write=30, pool=5),
        headers={"Authorization": f"Bearer {OLLAMA_KEY}"} if OLLAMA_KEY else None,
    )
    # Probe the local LLM server so we don't get mystery 502s later
    try:
        r = await client.get("/models")
        r.raise_for_status()
    except Exception as e:
        raise RuntimeError(f"LLM server not reachable at {OLLAMA_BASE}: {e!r}")

@app.on_event("shutdown")
async def _shutdown():
    global client
    if client:
        await client.aclose()

# ===================== Models =====================
class ExtractResponse(BaseModel):
    filename: str
    fields: dict
    ocr_text: str | None = None
    model: str

# ===================== Utils =====================
def require_api_key(x_api_key: str | None):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")

def _bytes_to_cv_gray(buf: bytes) -> np.ndarray:
    """Decode image bytes -> grayscale OpenCV image quickly."""
    arr = np.frombuffer(buf, dtype=np.uint8)
    gray = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
    if gray is None:
        raise ValueError("Unsupported or corrupted image.")
    h, w = gray.shape[:2]
    # Downscale big scans; gently upscale tiny receipts
    if w > MAX_WIDTH:
        fx = MAX_WIDTH / float(w)
        gray = cv2.resize(gray, (0, 0), fx=fx, fy=fx, interpolation=cv2.INTER_AREA)
    elif w < UPSCALE_MIN:
        gray = cv2.resize(gray, (0, 0), fx=UPSCALE_FX, fy=UPSCALE_FX, interpolation=cv2.INTER_LINEAR)
    # Light denoise + Otsu binarization
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    return bw

def _ocr_tesseract(img_gray: np.ndarray) -> str:
    """Run Tesseract (expects a grayscale/binarized np array)."""
    pil_img = Image.fromarray(img_gray)
    return pytesseract.image_to_string(pil_img, lang="eng", config=TESS_CONFIG)

def focus_text(ocr_text: str) -> str:
    """
    Keep only lines that likely contain target fields (drastically fewer tokens -> faster LLM).
    Also keep first/last few lines for context; cap length.
    """
    lines = [ln.strip() for ln in ocr_text.splitlines() if ln.strip()]
    if not lines:
        return ""
    needles = [
        "invoice", "inv#", "no:", "number", "date", "due",
        "subtotal", "total", "tax", "gst", "balance", "cash", "change", "amount", "paid"
    ]
    keep = []
    for ln in lines:
        low = ln.lower()
        if any(n in low for n in needles):
            keep.append(ln)
    # keep some context (first/last five lines)
    ctx = lines[:5] + keep + lines[-5:]
    # de-dup while preserving order
    uniq = list(dict.fromkeys(ctx))
    focused = "\n".join(uniq)
    # whitespace squeeze + hard cap
    focused = re.sub(r"[ \t]+", " ", focused)[:MAX_OCR_CHARS]
    return focused

json_fence = re.compile(r"```(?:json)?\s*([\s\S]+?)\s*```", re.IGNORECASE)
def extract_first_json(text: str) -> dict | None:
    blocks = json_fence.findall(text) or re.findall(r"(\{[\s\S]+?\})", text)
    for blk in blocks:
        try:
            return json.loads(blk)
        except Exception:
            continue
    return None

PROMPT_TEMPLATE = (
    "Extract the following fields from the invoice text and return ONLY a JSON object with exactly these keys:\n"
    '["invoice_number","invoice_date","due_date","subtotal","tax_rate","tax_amount","total",'
    '"balance_due","cash","change","gst_id"]\n'
    'If a field is unknown, use "NOT FOUND". If a date appears with no label, assume it is the invoice_date.\n\n'
    "Invoice Text:\n------\n{invoice_text}\n------"
)

async def call_llm_async(ocr_text: str) -> dict:
    """Call local LLM via OpenAI-compatible /chat/completions using the pooled client."""
    assert client is not None, "HTTP client not initialized"
    prompt = PROMPT_TEMPLATE.format(invoice_text=ocr_text)
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": "You are a precise invoice extraction assistant. Respond with JSON only."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.0,
        "max_tokens": 350,
        "stream": False,
        "options": {"num_predict": 320},  # many local servers honor this
    }
    try:
        r = await client.post("/chat/completions", json=payload)
        if r.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"LLM call failed: status={r.status_code} body={r.text[:500]}")
        data = r.json()
        content = data["choices"][0]["message"]["content"]
    except httpx.ReadTimeout as e:
        raise HTTPException(status_code=502, detail=f"LLM read timeout: {e!r}")
    except httpx.ConnectError as e:
        raise HTTPException(status_code=502, detail=f"LLM connect error: {e!r}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM call failed: {e!r}")

    parsed = extract_first_json(content) or {}
    keys = ["invoice_number","invoice_date","due_date","subtotal","tax_rate",
            "tax_amount","total","balance_due","cash","change","gst_id"]
    return {k: parsed.get(k, "NOT FOUND") for k in keys}


async def _process_one_upload(upload: UploadFile, include_ocr_text: bool) -> Dict[str, Any]:
    try:
        raw = await upload.read()
        img = await run_in_threadpool(_bytes_to_cv_gray, raw)
        ocr_text = (await run_in_threadpool(_ocr_tesseract, img)).strip()
        if not ocr_text:
            raise ValueError("Empty OCR result")

        focused = focus_text(ocr_text)
        fields = await call_llm_async(focused)

        return {
            "filename": upload.filename,
            "fields": fields,
            "ocr_text": ocr_text if include_ocr_text else None,
            "model": LLM_MODEL,
            "status": "ok"
        }
    except Exception as e:
        # Return an error object for this file, don’t fail the whole batch
        return {
            "filename": getattr(upload, "filename", None),
            "error": str(e),
            "status": "error"
        }

# ===================== Middleware (timings) =====================
@app.middleware("http")
async def timing_log(request: Request, call_next):
    t0 = time.perf_counter()
    resp = await call_next(request)
    dur = int((time.perf_counter() - t0) * 1000)
    print(f"[{dur}ms] {request.method} {request.url.path} -> {resp.status_code}")
    return resp

# ===================== Endpoints =====================
@app.get("/health")
def health():
    return {"status": "ok", "model": LLM_MODEL, "llm_base": OLLAMA_BASE}

@app.post("/ocr")
async def ocr_only(
    file: UploadFile = File(...),
    x_api_key: str | None = Header(default=None)
):
    require_api_key(x_api_key)
    try:
        raw = await file.read()
        img = await run_in_threadpool(_bytes_to_cv_gray, raw)
        text = (await run_in_threadpool(_ocr_tesseract, img)).strip()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"OCR error: {e}")
    return {"filename": file.filename, "ocr_text": text}

@app.post("/extract", response_model=ExtractResponse)
async def extract_fields(
    file: UploadFile = File(...),
    include_ocr_text: bool = Query(False, description="Return OCR text in response"),
    x_api_key: str | None = Header(default=None)
):
    require_api_key(x_api_key)

    # Load + preprocess (off event loop)
    try:
        raw = await file.read()
        t0 = time.perf_counter()
        img = await run_in_threadpool(_bytes_to_cv_gray, raw)
        t1 = time.perf_counter()
        ocr_text = (await run_in_threadpool(_ocr_tesseract, img)).strip()
        if not ocr_text:
            raise ValueError("Empty OCR result")
        t2 = time.perf_counter()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OCR failed: {e}")

    # Focus the text to cut tokens (big speed win)
    focused = focus_text(ocr_text)
    t3 = time.perf_counter()

    # LLM extraction
    fields = await call_llm_async(focused)
    t4 = time.perf_counter()

    # Print step timings (ms) for quick profiling
    print("timings_ms:",
          "preprocess=", int((t1 - t0) * 1000),
          "ocr=",        int((t2 - t1) * 1000),
          "focus=",      int((t3 - t2) * 1000),
          "llm=",        int((t4 - t3) * 1000),
          "total=",      int((t4 - t0) * 1000))

    return ExtractResponse(
        filename=file.filename,
        fields=fields,
        ocr_text=ocr_text if include_ocr_text else None,
        model=LLM_MODEL
    )

@app.post("/extract-batch")
async def extract_batch(
    files: List[UploadFile] = File(..., description="Upload multiple images"),
    include_ocr_text: bool = Query(False, description="Return OCR text per file"),
    x_api_key: str | None = Header(default=None),
    max_concurrency: int = Query(4, ge=1, le=16, description="Parallel files to process")
):
    """
    Concurrently extract fields for multiple receipts.
    Returns a list of per-file results (success or error).
    """
    require_api_key(x_api_key)

    # Guard: empty upload
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")

    # Limit concurrency so we don't overwhelm CPU/LLM
    sem = asyncio.Semaphore(max_concurrency)

    async def _guarded_process(f: UploadFile):
        async with sem:
            return await _process_one_upload(f, include_ocr_text)

    tasks = [asyncio.create_task(_guarded_process(f)) for f in files]
    results = await asyncio.gather(*tasks, return_exceptions=False)

    # Optional: summarize counts
    ok = sum(1 for r in results if r.get("status") == "ok")
    err = len(results) - ok
    return {"summary": {"ok": ok, "error": err, "total": len(results)}, "results": results}