import asyncio
import json
import secrets
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional, List

from fastapi import FastAPI, HTTPException, UploadFile, File, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .db import init_db, insert_job, get_job, list_jobs
from .worker import process_job

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

app = FastAPI(title="DANIELOZA.AI Backend", version="0.2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/uploads", StaticFiles(directory="backend/uploads"), name="uploads")

queue: "asyncio.Queue[Dict[str, Any]]" = asyncio.Queue()

RATE_LIMIT_MAX = 5
RATE_LIMIT_WINDOW = timedelta(hours=24)
_rate: Dict[str, List[datetime]] = {}

def client_ip(req: Request) -> str:
    xff = req.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return req.client.host if req.client else "unknown"

def rate_check(ip: str) -> None:
    now = datetime.now(timezone.utc)
    arr = _rate.get(ip, [])
    arr = [t for t in arr if (now - t) <= RATE_LIMIT_WINDOW]
    if len(arr) >= RATE_LIMIT_MAX:
        raise HTTPException(status_code=429, detail=f"Rate limit: {RATE_LIMIT_MAX}/24h dla IP {ip}")
    arr.append(now)
    _rate[ip] = arr

class CreateJobIn(BaseModel):
    model: str = Field(default="Kling 01")
    mode: str = Field(default="video")
    prompt: str = Field(min_length=1, max_length=4000)
    ar: str = Field(default="1:1")
    res: str = Field(default="1080p")
    dur: str = Field(default="10s")
    image_url: Optional[str] = None

@app.on_event("startup")
async def startup() -> None:
    init_db()
    asyncio.create_task(worker_loop())

async def worker_loop() -> None:
    while True:
        item = await queue.get()
        job_id = item["id"]
        payload = item["payload"]
        try:
            await process_job(job_id, payload)
        finally:
            queue.task_done()

@app.get("/api/health")
def health() -> Dict[str, Any]:
    return {"ok": True, "version": "0.2"}

@app.post("/api/kling/upload")
async def upload_image(file: UploadFile = File(...)) -> Dict[str, Any]:
    import os
    from pathlib import Path

    ext = (Path(file.filename).suffix or "").lower()
    if ext not in [".png", ".jpg", ".jpeg", ".webp"]:
        raise HTTPException(status_code=400, detail="Dozwolone: png/jpg/jpeg/webp")

    name = "UPL-" + secrets.token_hex(6) + ext
    out_path = Path("backend/uploads") / name

    data = await file.read()
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Max 8MB")

    with open(out_path, "wb") as f:
        f.write(data)

    return {
        "ok": True,
        "filename": name,
        "url": f"http://127.0.0.1:8000/uploads/{name}"
    }

@app.post("/api/kling/jobs")
async def create_job(req: Request, data: CreateJobIn) -> Dict[str, Any]:
    ip = client_ip(req)
    rate_check(ip)

    job_id = "JOB-" + secrets.token_hex(3).upper()
    payload = data.model_dump()
    payload["client_ip"] = ip
    payload_json = json.dumps(payload, ensure_ascii=False)

    insert_job(job_id, "queued", payload_json, now_iso())
    await queue.put({"id": job_id, "payload": payload})

    return {"id": job_id, "status": "queued", "payload": payload}

@app.get("/api/kling/jobs/{job_id}")
def read_job(job_id: str) -> Dict[str, Any]:
    row = get_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")

    payload = json.loads(row["payload_json"])
    result = json.loads(row["result_json"]) if row["result_json"] else None

    return {
        "id": row["id"],
        "status": row["status"],
        "payload": payload,
        "result": result,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }

@app.get("/api/kling/jobs")
def jobs(limit: int = 30) -> List[Dict[str, Any]]:
    rows = list_jobs(limit=limit)
    out = []
    for r in rows:
        out.append({
            "id": r["id"],
            "status": r["status"],
            "payload": json.loads(r["payload_json"]),
            "result": json.loads(r["result_json"]) if r["result_json"] else None,
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        })
    return out
