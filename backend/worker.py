import asyncio
import json
from datetime import datetime, timezone
from typing import Dict, Any

from .db import update_job

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

async def process_job(job_id: str, payload: Dict[str, Any]) -> None:
    update_job(job_id, "running", None, now_iso())
    await asyncio.sleep(1.2)

    mode = payload.get("mode")
    img = payload.get("image_url")

    await asyncio.sleep(1.2)

    result = {
        "jobId": job_id,
        "provider": "mock",
        "mode": mode,
        "model": payload.get("model"),
        "imageUrl": img,
        "message": "Gotowe (mock). Następny krok: podpiąć prawdziwe Kling API i zwracać videoUrl.",
        "videoUrl": None,
    }
    update_job(job_id, "done", json.dumps(result, ensure_ascii=False), now_iso())
