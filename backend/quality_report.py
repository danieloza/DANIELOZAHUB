import os
import smtplib
import sys
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.db import (
    init_db,
    count_leads_between,
    count_form_submit_between,
    count_leads_by_form_between,
    count_form_submit_by_form_between,
)


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


def to_map(rows: List[Dict[str, int]]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for r in rows:
        out[str(r.get("form_type") or "")] = int(r.get("cnt") or 0)
    return out


def conv_pct(leads: int, submits: int) -> float:
    if submits <= 0:
        return 0.0
    return round((leads / submits) * 100.0, 2)


def window_stats(start: datetime, end: datetime) -> Dict[str, object]:
    s = start.isoformat()
    e = end.isoformat()
    leads_total = count_leads_between(s, e)
    submit_total = count_form_submit_between(s, e)
    leads_map = to_map(count_leads_by_form_between(s, e))
    submit_map = count_form_submit_by_form_between(s, e)
    return {
        "leads_total": leads_total,
        "submit_total": submit_total,
        "conv_total": conv_pct(leads_total, submit_total),
        "leads_map": leads_map,
        "submit_map": submit_map,
        "conv_audyt": conv_pct(int(leads_map.get("audyt", 0)), int(submit_map.get("audyt", 0))),
        "conv_kontakt": conv_pct(int(leads_map.get("kontakt", 0)), int(submit_map.get("kontakt", 0))),
    }


def parse_mode() -> str:
    mode = (sys.argv[1] if len(sys.argv) > 1 else "daily").strip().lower()
    if mode not in {"daily", "weekly"}:
        return "daily"
    return mode


def build_report(mode: str) -> Tuple[str, str, List[str]]:
    now = datetime.now(timezone.utc)
    issues: List[str] = []

    if mode == "daily":
        curr = window_stats(now - timedelta(days=1), now)
        title = "Daily"
    else:
        curr = window_stats(now - timedelta(days=7), now)
        prev = window_stats(now - timedelta(days=14), now - timedelta(days=7))
        title = "Weekly"

        drop_limit = float((os.getenv("ALERT_CONV_DROP_PCT") or "30").strip())
        conv_drop = curr["conv_total"] - prev["conv_total"]
        if conv_drop <= -abs(drop_limit):
            issues.append(f"conversion drop WoW: {conv_drop}% (limit -{abs(drop_limit)}%)")

    min_audyt = int((os.getenv("ALERT_MIN_LEADS_AUDYT_24H") or "0").strip())
    min_kontakt = int((os.getenv("ALERT_MIN_LEADS_KONTAKT_24H") or "0").strip())

    if mode == "daily":
        audyt_leads = int(curr["leads_map"].get("audyt", 0))
        kontakt_leads = int(curr["leads_map"].get("kontakt", 0))
        if min_audyt > 0 and audyt_leads < min_audyt:
            issues.append(f"low audyt leads 24h: {audyt_leads} < {min_audyt}")
        if min_kontakt > 0 and kontakt_leads < min_kontakt:
            issues.append(f"low kontakt leads 24h: {kontakt_leads} < {min_kontakt}")

    subject = f"[{title} Quality] leads={curr['leads_total']} conv={curr['conv_total']}%"
    lines = [
        f"mode: {mode}",
        f"generated_at: {now.isoformat()}",
        "",
        "totals:",
        f"- leads_total: {curr['leads_total']}",
        f"- form_submit_total: {curr['submit_total']}",
        f"- conversion_total: {curr['conv_total']}%",
        f"- conversion_audyt: {curr['conv_audyt']}%",
        f"- conversion_kontakt: {curr['conv_kontakt']}%",
        "",
        "leads_by_form:",
        f"- audyt: {int(curr['leads_map'].get('audyt', 0))}",
        f"- kontakt: {int(curr['leads_map'].get('kontakt', 0))}",
        f"- other: {int(curr['leads_map'].get('other', 0))}",
        "",
        "form_submit_by_form:",
        f"- audyt: {int(curr['submit_map'].get('audyt', 0))}",
        f"- kontakt: {int(curr['submit_map'].get('kontakt', 0))}",
        f"- other: {int(curr['submit_map'].get('other', 0))}",
    ]
    if issues:
        lines.extend(["", "issues:"] + [f"- {x}" for x in issues])
    else:
        lines.extend(["", "issues:", "- none"])

    return subject, "\n".join(lines), issues


def main() -> int:
    init_db()
    mode = parse_mode()
    subject, body, issues = build_report(mode)
    print(body)

    to_email = (os.getenv("ALERT_NOTIFY_TO") or "").strip()
    send_always = _env_bool("QUALITY_REPORT_SEND_ALWAYS", True)
    should_send = send_always or bool(issues)
    if should_send and to_email:
        _smtp_send(subject, body, to_email)
        print("quality report sent")
    elif should_send:
        print("ALERT_NOTIFY_TO empty; report not sent")

    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
