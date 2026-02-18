import os, time
import httpx
import jwt
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any
from urllib.parse import urlparse
load_dotenv(override=True)

AK = os.getenv("KLING_ACCESS_KEY", "")
SK = os.getenv("KLING_SECRET_KEY", "")
BASE = os.getenv("KLING_API_BASE", "").rstrip("/")

# ===== Kling endpoints (z Twoich docs) =====
# Query Task (Single) dla image2video:
QUERY_IMAGE2VIDEO = "/v1/videos/image2video/{id}"

# Create Task (image2video) — MUSISZ podmienić na dokładny z docs, jeśli jest inny
# Najczęściej jest to ta sama ścieżka POST, co model:
CREATE_IMAGE2VIDEO = "/v1/videos/image2video"



# ===== helpers: JWT cache + rate limit =====
_JWT_CACHE = {"token": None, "exp": 0}
_LAST_CREATE: Dict[str, float] = {}  # ip -> last_ts

def _client_ip(request) -> str:
    try:
        return request.client.host
    except Exception:
        return "unknown"

def _rate_limit(ip: str, min_interval_sec: float = 5.0):
    now = time.time()
    last = _LAST_CREATE.get(ip, 0.0)
    if now - last < min_interval_sec:
        raise HTTPException(status_code=429, detail=f"Rate limit: wait {min_interval_sec:.0f}s")
    _LAST_CREATE[ip] = now
def make_jwt() -> str:
    if not AK or not SK:
        raise RuntimeError("Brak KLING_ACCESS_KEY / KLING_SECRET_KEY w .env")

    now = int(time.time())

    # cache token na ~30s żeby nie generować go co request
    if _JWT_CACHE["token"] and _JWT_CACHE["exp"] > now + 3:
        return _JWT_CACHE["token"]

    headers = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "iss": str(AK),
        "iat": now,
        "nbf": now - 5,
        "exp": now + 600,
    }
    tok = jwt.encode(payload, SK, algorithm="HS256", headers=headers)
    _JWT_CACHE["token"] = tok
    _JWT_CACHE["exp"] = now + 30
    return tok


app = FastAPI(title="DANIELOZA.AI Kling Backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # produkcyjnie ogranicz do domeny
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Image2VideoRequest(BaseModel):
    image_url: str
    prompt: str | None = ""
    style: str | None = "premium"

@app.get("/api/health")
async def health():
    return {"ok": True, "base": BASE}



from fastapi import Request, Response
from fastapi.responses import StreamingResponse

@app.get("/api/token_info")
async def token_info():
    # bez sekretów, tylko szybka diagnostyka
    return {
        "base": BASE,
        "ak_prefix": (AK[:6] + "...") if AK else None,
        "has_sk": bool(SK),
        "jwt_cached": bool(_JWT_CACHE["token"]),
        "jwt_cache_exp": _JWT_CACHE["exp"],
    }

@app.get("/api/fetch_image")
async def fetch_image(url: str):
    # UWAGA: tylko do testów lokalnych (CORS/hosting obrazka)
    if not url or not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Bad url")
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.get(url, follow_redirects=True)
        if r.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"fetch failed {r.status_code}")
        ct = r.headers.get("content-type", "application/octet-stream")
        return Response(content=r.content, media_type=ct)
@app.get("/api/debug")
async def debug():
    return {
        "base": BASE,
        "ak_prefix": (AK[:6] + "...") if AK else None,
        "has_sk": bool(SK),
        "create_url": f"{BASE}{CREATE_IMAGE2VIDEO}",
        "query_url_example": f"{BASE}{QUERY_IMAGE2VIDEO.format(id='TEST_ID')}",
    }


@app.post("/api/image2video")
async def create_image2video(payload: Image2VideoRequest, request: Request):
    if not BASE:
        raise HTTPException(status_code=500, detail="Brak KLING_API_BASE w .env")

    token = make_jwt()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    # MVP body – dopasujemy 1:1 do docs create, jeśli będzie trzeba
    body = {
        "image_url": payload.image_url,
        "prompt": payload.prompt or "",
    }

    url = f"{BASE}{CREATE_IMAGE2VIDEO}"
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(url, headers=headers, json=body)
        if r.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"Kling create error: {r.status_code} {r.text}")
        data = r.json()

    task_id = (data.get("data") or {}).get("task_id") or data.get("task_id") or data.get("id")
    if not task_id:
        raise HTTPException(status_code=502, detail=f"Brak task_id w odpowiedzi: {data}")

    return {"job_id": task_id, "raw": data}

@app.get("/api/jobs/{job_id}")
async def job_status(job_id: str):
    if not BASE:
        raise HTTPException(status_code=500, detail="Brak KLING_API_BASE w .env")

    token = make_jwt()
    headers = {"Authorization": f"Bearer {token}"}

    url = f"{BASE}{QUERY_IMAGE2VIDEO.format(id=job_id)}"

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.get(url, headers=headers)
        if r.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"Kling query error: {r.status_code} {r.text}")
        resp = r.json()

    d = resp.get("data") or {}
    status = d.get("task_status") or "unknown"

    video_url = None
    task_result = d.get("task_result") or {}
    vids = task_result.get("videos") or []
    if isinstance(vids, list) and vids:
        first = vids[0]
        if isinstance(first, dict):
            video_url = first.get("url")

    return {"status": status, "video_url": video_url, "raw": resp}

@app.get("/api/queue")
async def queue_state():
    return {"ok": True, "note": "queue endpoint is present"}
