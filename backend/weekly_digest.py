import json
import os
import sys
from datetime import datetime
from pathlib import Path
from urllib import request

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app import build_weekly_report, report_markdown
from backend.db import init_db


def send_webhook(url: str, payload: dict) -> None:
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url=url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with request.urlopen(req, timeout=10) as resp:
        _ = resp.read()


def main() -> None:
    init_db()
    days = int(os.getenv("WEEKLY_DIGEST_DAYS", "7"))
    report = build_weekly_report(days=days)
    md = report_markdown(report)

    out_dir = Path(__file__).resolve().parent / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    md_path = out_dir / f"weekly-digest-{stamp}.md"
    json_path = out_dir / f"weekly-digest-{stamp}.json"
    md_path.write_text(md, encoding="utf-8")
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    webhook = os.getenv("WEEKLY_DIGEST_WEBHOOK_URL", "").strip()
    if webhook:
        send_webhook(webhook, {"text": md, "report": report})

    print(f"Digest written: {md_path}")
    print(f"Digest written: {json_path}")
    if webhook:
        print("Digest pushed to webhook.")


if __name__ == "__main__":
    main()
