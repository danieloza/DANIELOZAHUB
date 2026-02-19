import os
import sqlite3
import sys
import tempfile
import threading
import time
from pathlib import Path
from socketserver import StreamRequestHandler, ThreadingTCPServer

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import backend.db as db
from backend.app import app


class TinySMTPServer(ThreadingTCPServer):
    allow_reuse_address = True

    def __init__(self, server_address, handler_class):
        super().__init__(server_address, handler_class)
        self.messages = []


class TinySMTPHandler(StreamRequestHandler):
    def _send(self, line):
        self.wfile.write((line + "\r\n").encode("utf-8"))

    def handle(self):
        self._send("220 localhost ESMTP TinySMTP")

        mail_from = ""
        rcpt_tos = []
        data_lines = []
        in_data = False

        while True:
            raw = self.rfile.readline()
            if not raw:
                break
            line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            upper = line.upper()

            if in_data:
                if line == ".":
                    self.server.messages.append(
                        {
                            "mailfrom": mail_from,
                            "rcpttos": list(rcpt_tos),
                            "data": "\n".join(data_lines),
                        }
                    )
                    data_lines = []
                    in_data = False
                    self._send("250 2.0.0 queued")
                else:
                    if line.startswith(".."):
                        line = line[1:]
                    data_lines.append(line)
                continue

            if upper.startswith("EHLO") or upper.startswith("HELO"):
                self._send("250-localhost")
                self._send("250 OK")
            elif upper.startswith("MAIL FROM:"):
                mail_from = line[10:].strip().strip("<>").strip()
                rcpt_tos = []
                self._send("250 2.1.0 OK")
            elif upper.startswith("RCPT TO:"):
                rcpt = line[8:].strip().strip("<>").strip()
                rcpt_tos.append(rcpt)
                self._send("250 2.1.5 OK")
            elif upper == "DATA":
                in_data = True
                self._send("354 End data with <CR><LF>.<CR><LF>")
            elif upper == "RSET":
                mail_from = ""
                rcpt_tos = []
                data_lines = []
                in_data = False
                self._send("250 2.0.0 OK")
            elif upper == "NOOP":
                self._send("250 2.0.0 OK")
            elif upper == "QUIT":
                self._send("221 2.0.0 Bye")
                break
            else:
                self._send("250 2.0.0 OK")


def wait_for(predicate, timeout_sec=5.0, interval_sec=0.1):
    started = time.time()
    while time.time() - started < timeout_sec:
        if predicate():
            return True
        time.sleep(interval_sec)
    return False


def _set_env(k, v):
    if v is None:
        os.environ.pop(k, None)
    else:
        os.environ[k] = v


def run_e2e():
    temp_dir = Path(tempfile.mkdtemp(prefix="dz-forms-e2e-"))
    db.DB_PATH = temp_dir / "jobs.e2e.sqlite3"
    db.init_db()

    smtp = TinySMTPServer(("127.0.0.1", 0), TinySMTPHandler)
    smtp_port = smtp.server_address[1]
    smtp_thread = threading.Thread(target=smtp.serve_forever, daemon=True)
    smtp_thread.start()

    env_keys = [
        "SMTP_HOST",
        "SMTP_PORT",
        "SMTP_USER",
        "SMTP_PASS",
        "SMTP_FROM",
        "SMTP_STARTTLS",
        "LEAD_NOTIFY_TO",
        "LEAD_AUTOREPLY_ENABLED",
    ]
    old_env = {k: os.environ.get(k) for k in env_keys}

    try:
        _set_env("SMTP_HOST", "127.0.0.1")
        _set_env("SMTP_PORT", str(smtp_port))
        _set_env("SMTP_USER", "")
        _set_env("SMTP_PASS", "")
        _set_env("SMTP_FROM", "noreply@danieloza.ai")
        _set_env("SMTP_STARTTLS", "false")
        _set_env("LEAD_NOTIFY_TO", "owner@danieloza.ai")
        _set_env("LEAD_AUTOREPLY_ENABLED", "true")

        with TestClient(app) as client:
            payloads = [
                {
                    "form_type": "audyt",
                    "fields": {
                        "profil_link": "https://instagram.com/example_audyt",
                        "email": "audyt-client@example.com",
                        "platforma": "Instagram",
                        "cel": "Leady / sprzedaz",
                    },
                    "source_path": "/audyt.html",
                    "session_id": "s_e2e_audyt",
                    "consent_state": "granted",
                },
                {
                    "form_type": "kontakt",
                    "fields": {
                        "firma": "Danex",
                        "email": "kontakt-client@example.com",
                        "cel": "wzrost leadow",
                        "budzet": "500-2000 zl / miesiac",
                    },
                    "source_path": "/kontakt.html",
                    "session_id": "s_e2e_kontakt",
                    "consent_state": "granted",
                },
            ]

            lead_ids = []
            for payload in payloads:
                res = client.post(
                    "/api/leads",
                    json=payload,
                    headers={"user-agent": "dz-e2e-forms-test"},
                )
                assert res.status_code == 200, res.text
                data = res.json()
                assert data.get("ok") is True
                assert data.get("accepted") is True
                assert str(data.get("id", "")).startswith("LEAD-")
                lead_ids.append(data["id"])

            assert wait_for(
                lambda: len(smtp.messages) >= 4
            ), f"Expected >=4 SMTP messages, got {len(smtp.messages)}"

        with sqlite3.connect(db.DB_PATH) as con:
            con.row_factory = sqlite3.Row
            rows = con.execute(
                "SELECT id, form_type, source_path FROM leads ORDER BY created_at ASC"
            ).fetchall()

        assert len(rows) == 2, f"Expected 2 leads in DB, got {len(rows)}"
        saved_ids = {r["id"] for r in rows}
        assert set(lead_ids) == saved_ids, f"Lead IDs mismatch. API={lead_ids}, DB={saved_ids}"
        assert {r["form_type"] for r in rows} == {"audyt", "kontakt"}
        assert {r["source_path"] for r in rows} == {"/audyt.html", "/kontakt.html"}

        all_rcpts = [rcpt for msg in smtp.messages for rcpt in msg["rcpttos"]]
        assert "owner@danieloza.ai" in all_rcpts
        assert "audyt-client@example.com" in all_rcpts
        assert "kontakt-client@example.com" in all_rcpts

        print("E2E OK: leads saved=2, smtp messages=", len(smtp.messages))
        print("DB path:", db.DB_PATH)
        print("SMTP port:", smtp_port)
    finally:
        smtp.shutdown()
        smtp.server_close()
        for k, v in old_env.items():
            _set_env(k, v)


if __name__ == "__main__":
    run_e2e()
