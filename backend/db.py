import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

DB_PATH = Path(__file__).resolve().parent / "jobs.sqlite3"

def conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def init_db() -> None:
    with conn() as c:
        c.execute(
            '''
            CREATE TABLE IF NOT EXISTS jobs (
              id TEXT PRIMARY KEY,
              status TEXT NOT NULL,
              payload_json TEXT NOT NULL,
              result_json TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            '''
        )
        c.commit()

def insert_job(job_id: str, status: str, payload_json: str, now_iso: str) -> None:
    with conn() as c:
        c.execute(
            "INSERT INTO jobs (id,status,payload_json,created_at,updated_at) VALUES (?,?,?,?,?)",
            (job_id, status, payload_json, now_iso, now_iso),
        )
        c.commit()

def update_job(job_id: str, status: str, result_json: Optional[str], now_iso: str) -> None:
    with conn() as c:
        c.execute(
            "UPDATE jobs SET status=?, result_json=?, updated_at=? WHERE id=?",
            (status, result_json, now_iso, job_id),
        )
        c.commit()

def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    with conn() as c:
        row = c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return dict(row) if row else None

def list_jobs(limit: int = 30) -> List[Dict[str, Any]]:
    with conn() as c:
        rows = c.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
