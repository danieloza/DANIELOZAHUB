import json
import os
import smtplib
import sys
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.db import init_db, list_due_followup_candidates, list_followup_templates, insert_followup_log


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
        raise RuntimeError("SMTP not configured")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_email
    msg.set_content(body)

    with smtplib.SMTP(host, port, timeout=15) as smtp:
        smtp.ehlo()
        if _env_bool("SMTP_STARTTLS", True):
            smtp.starttls()
            smtp.ehlo()
        if user and password:
            smtp.login(user, password)
        smtp.send_message(msg)


def parse_steps() -> List[int]:
    raw = (os.getenv("FOLLOWUP_STEPS_HOURS") or "24,72").strip()
    out = []
    for p in raw.split(","):
        x = p.strip()
        if not x:
            continue
        try:
            n = int(x)
            if n > 0:
                out.append(n)
        except Exception:
            pass
    return sorted(set(out))


def templates_map() -> Dict[int, Dict[str, str]]:
    out: Dict[int, Dict[str, str]] = {}
    for t in list_followup_templates():
        out[int(t["step_hours"])] = {
            "subject": str(t["subject_template"]),
            "body": str(t["body_template"]),
        }
    return out


def render(template: str, data: Dict[str, str]) -> str:
    result = template
    for k, v in data.items():
        result = result.replace("{{" + k + "}}", str(v))
    return result


def extract_email(payload_json: str) -> str:
    try:
        payload = json.loads(payload_json or "{}")
    except Exception:
        payload = {}
    fields = payload.get("fields") if isinstance(payload, dict) else {}
    if not isinstance(fields, dict):
        fields = {}
    for key in ("email", "e-mail", "mail"):
        val = fields.get(key)
        if isinstance(val, str) and "@" in val:
            return val.strip()
    return ""


def main() -> int:
    init_db()
    tmap = templates_map()
    steps = parse_steps()
    now = datetime.now(timezone.utc)
    sent = 0
    errors = 0

    for step_hours in steps:
        template = tmap.get(step_hours)
        if not template:
            continue

        older_than = (now - timedelta(hours=step_hours)).isoformat()
        candidates = list_due_followup_candidates(step_hours=step_hours, older_than_iso=older_than, limit=300)
        for lead in candidates:
            lead_id = str(lead["id"])
            to_email = extract_email(str(lead.get("payload_json") or ""))
            if not to_email:
                insert_followup_log(
                    lead_id=lead_id,
                    step_hours=step_hours,
                    to_email="",
                    subject="",
                    body="",
                    status="skip_no_email",
                    sent_at=now_iso(),
                )
                continue

            data = {
                "lead_id": lead_id,
                "form_type": str(lead.get("form_type") or ""),
                "source_path": str(lead.get("source_path") or ""),
                "created_at": str(lead.get("created_at") or ""),
                "step_hours": str(step_hours),
            }
            subject = render(template["subject"], data)
            body = render(template["body"], data)
            try:
                _smtp_send(subject=subject, body=body, to_email=to_email)
                insert_followup_log(
                    lead_id=lead_id,
                    step_hours=step_hours,
                    to_email=to_email,
                    subject=subject,
                    body=body,
                    status="sent",
                    sent_at=now_iso(),
                )
                sent += 1
            except Exception as exc:
                insert_followup_log(
                    lead_id=lead_id,
                    step_hours=step_hours,
                    to_email=to_email,
                    subject=subject,
                    body=body,
                    status="error:" + str(exc)[:200],
                    sent_at=now_iso(),
                )
                errors += 1

    print(f"followup_dispatch done: sent={sent} errors={errors}")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
