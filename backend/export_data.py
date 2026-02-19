import csv
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.db import DB_PATH, init_db


def fetch_all(con: sqlite3.Connection, sql: str):
    cur = con.execute(sql)
    return [dict(zip([d[0] for d in cur.description], row)) for row in cur.fetchall()]


def write_csv(path: Path, rows):
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    init_db()
    out_dir = Path(__file__).resolve().parent / "exports"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    with sqlite3.connect(DB_PATH) as con:
        leads = fetch_all(con, "SELECT * FROM leads ORDER BY created_at DESC")
        lead_meta = fetch_all(con, "SELECT * FROM lead_meta ORDER BY updated_at DESC")
        events = fetch_all(con, "SELECT * FROM analytics_events ORDER BY created_at DESC")
        followups = fetch_all(con, "SELECT * FROM followup_log ORDER BY sent_at DESC")

    bundle = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "leads": leads,
        "lead_meta": lead_meta,
        "analytics_events": events,
        "followup_log": followups,
    }

    json_path = out_dir / f"full-export-{stamp}.json"
    json_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")

    write_csv(out_dir / f"leads-{stamp}.csv", leads)
    write_csv(out_dir / f"lead-meta-{stamp}.csv", lead_meta)
    write_csv(out_dir / f"events-{stamp}.csv", events)
    write_csv(out_dir / f"followups-{stamp}.csv", followups)

    print(f"Export written: {json_path}")


if __name__ == "__main__":
    main()
