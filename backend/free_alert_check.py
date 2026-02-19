import os
import smtplib
import sys
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from urllib import request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from backend.db import init_db, count_leads_between


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
        print("SMTP not configured. Skipping email alert.")
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


def check_health(url: str) -> str:
    req = request.Request(url, method="GET")
    with request.urlopen(req, timeout=8) as resp:
        payload = resp.read(200).decode("utf-8", errors="replace")
        return f"{resp.status} {payload}"


def main() -> int:
    alert_to = (os.getenv("ALERT_NOTIFY_TO") or "").strip()
    health_url = (os.getenv("ALERT_HEALTH_URL") or "http://127.0.0.1:8000/api/health").strip()
    min_leads_24h = int((os.getenv("ALERT_MIN_LEADS_24H") or "0").strip())

    problems = []
    health_info = ""
    try:
        health_info = check_health(health_url)
    except Exception as exc:
        problems.append(f"health check failed: {exc}")

    init_db()
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=24)
    leads_24h = count_leads_between(start.isoformat(), now.isoformat())
    if min_leads_24h > 0 and leads_24h < min_leads_24h:
        problems.append(f"low leads: {leads_24h} < {min_leads_24h} in last 24h")

    if not problems:
        print("Alert check OK")
        print(f"Health: {health_info}")
        print(f"Leads 24h: {leads_24h}")
        return 0

    print("ALERT:")
    for p in problems:
        print("-", p)

    if alert_to:
        subject = "[ALERT] DANIELOZA backend check failed"
        body = (
            "Detected issues:\n"
            + "\n".join(f"- {p}" for p in problems)
            + f"\n\nhealth_url: {health_url}\n"
            + f"health_info: {health_info or '-'}\n"
            + f"leads_24h: {leads_24h}\n"
            + f"checked_at: {now.isoformat()}\n"
        )
        _smtp_send(subject, body, alert_to)
        print("Alert email sent.")
    else:
        print("ALERT_NOTIFY_TO empty, email skipped.")

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
