import os
import smtplib
import sys
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app import build_pipeline_report
from backend.db import init_db


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _smtp_send(subject: str, body: str, to_email: str) -> None:
    host = (os.getenv("SMTP_HOST") or "").strip()
    port = int((os.getenv("SMTP_PORT") or "587").strip())
    user = (os.getenv("SMTP_USER") or "").strip()
    password = (os.getenv("SMTP_PASS") or "").strip()
    from_email = (os.getenv("SMTP_FROM") or user).strip()

    if not host or not from_email or not to_email:
        print("SMTP or recipient not configured. Report not sent.")
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_email
    msg.set_content(body)

    with smtplib.SMTP(host, port, timeout=12) as smtp:
        smtp.ehlo()
        if _env_bool("SMTP_STARTTLS", True):
            smtp.starttls()
            smtp.ehlo()
        if user and password:
            smtp.login(user, password)
        smtp.send_message(msg)


def parse_days() -> int:
    if len(sys.argv) < 2:
        return 1
    try:
        d = int(sys.argv[1])
        if d < 1:
            return 1
        if d > 90:
            return 90
        return d
    except Exception:
        return 1


def to_md(report: dict) -> str:
    lines = [
        "# Daily Pipeline Report",
        "",
        f"generated_at: {report.get('generated_at')}",
        f"days: {report.get('days')}",
        "",
        "totals:",
        f"- leads: {report.get('totals', {}).get('leads', 0)}",
        f"- won: {report.get('totals', {}).get('won', 0)}",
        f"- lost: {report.get('totals', {}).get('lost', 0)}",
        "",
        "stage_rows:",
    ]
    for x in (report.get("stage_rows") or [])[:12]:
        lines.append(f"- {x.get('stage')}: {x.get('count')}")

    lines.append("")
    lines.append("ranking_pages:")
    for x in (report.get("ranking_pages") or [])[:10]:
        lines.append(f"- {x.get('label')}: leads={x.get('leads')} won={x.get('won')} lost={x.get('lost')} win_rate={x.get('win_rate_pct')}%")

    lines.append("")
    lines.append("ranking_cta:")
    for x in (report.get("ranking_cta") or [])[:10]:
        lines.append(f"- {x.get('label')}: leads={x.get('leads')} won={x.get('won')} lost={x.get('lost')} win_rate={x.get('win_rate_pct')}%")

    return "\n".join(lines)


def main() -> int:
    init_db()
    days = parse_days()
    report = build_pipeline_report(days=days, include_test=False, include_spam=False)
    body = to_md(report)
    print(body)

    to_email = (os.getenv("ALERT_NOTIFY_TO") or "").strip()
    send_always = _env_bool("PIPELINE_REPORT_SEND_ALWAYS", True)
    should_send = send_always or int(report.get("totals", {}).get("won", 0)) == 0
    if should_send and to_email:
        subject = f"[Pipeline {days}d] leads={report.get('totals', {}).get('leads', 0)} won={report.get('totals', {}).get('won', 0)}"
        _smtp_send(subject, body, to_email)
        print("pipeline report sent")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
