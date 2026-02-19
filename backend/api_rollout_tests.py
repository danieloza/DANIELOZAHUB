import asyncio
import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend import app as appmod
from backend import db as dbmod
from backend.worker import process_job


def _lead_payload(email: str = "john@example.com", phone: str = "+48 500 600 700", budget: str = "500-2000 PLN") -> dict:
    return {
        "form_type": "kontakt",
        "fields": {
            "firma": "Acme",
            "email": email,
            "telefon": phone,
            "budzet": budget,
            "cel": "leady",
            "opis": "test lead",
        },
        "source_path": "/kontakt.html",
        "website": "",
    }


class RolloutApiTests(unittest.TestCase):
    def setUp(self) -> None:
        fd, temp_path = tempfile.mkstemp(prefix="dz_api_", suffix=".sqlite3")
        os.close(fd)
        dbmod.DB_PATH = Path(temp_path)
        dbmod.init_db()

        appmod._rate_jobs.clear()
        appmod._rate_leads.clear()
        appmod._rate_events.clear()

        os.environ["ADMIN_TOKEN"] = "test-token"
        os.environ["AUTOPILOT_ENABLED"] = "true"
        os.environ["WIN_MODEL_ENABLED"] = "true"
        os.environ["ROI_ENABLED"] = "true"
        os.environ["PUBLIC_ORIGIN_ALLOWLIST"] = ""

        self.client = TestClient(appmod.app)
        self.admin_headers = {"x-admin-token": "test-token"}

    def tearDown(self) -> None:
        self.client.close()

    def _create_lead(self) -> str:
        res = self.client.post("/api/leads", json=_lead_payload())
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertTrue(body.get("ok"))
        return str(body.get("id"))

    def test_lead_hygiene_invalid_email(self) -> None:
        payload = _lead_payload(email="bad-mail")
        res = self.client.post("/api/leads", json=payload)
        self.assertEqual(res.status_code, 400)

    def test_lead_hygiene_missing_phone_for_kontakt(self) -> None:
        payload = _lead_payload(phone="")
        res = self.client.post("/api/leads", json=payload)
        self.assertEqual(res.status_code, 400)

    def test_won_requires_deal_value(self) -> None:
        lead_id = self._create_lead()
        res_won_fail = self.client.post(
            f"/api/admin/leads/{lead_id}/meta",
            params={"token": "test-token"},
            headers=self.admin_headers,
            json={"status": "won", "notes": "x", "follow_up_at": None},
        )
        self.assertEqual(res_won_fail.status_code, 400)

        res_value = self.client.post(
            f"/api/admin/leads/{lead_id}/value",
            params={"token": "test-token"},
            headers=self.admin_headers,
            json={"deal_value": 1200},
        )
        self.assertEqual(res_value.status_code, 200, res_value.text)

        res_won_ok = self.client.post(
            f"/api/admin/leads/{lead_id}/meta",
            params={"token": "test-token"},
            headers=self.admin_headers,
            json={"status": "won", "notes": "x", "follow_up_at": None},
        )
        self.assertEqual(res_won_ok.status_code, 200, res_won_ok.text)

    def test_lost_requires_lost_reason(self) -> None:
        lead_id = self._create_lead()
        res_lost_fail = self.client.post(
            f"/api/admin/leads/{lead_id}/meta",
            params={"token": "test-token"},
            headers=self.admin_headers,
            json={"status": "lost", "notes": "x", "follow_up_at": None, "lost_reason": ""},
        )
        self.assertEqual(res_lost_fail.status_code, 400)

        res_lost_ok = self.client.post(
            f"/api/admin/leads/{lead_id}/meta",
            params={"token": "test-token"},
            headers=self.admin_headers,
            json={"status": "lost", "notes": "x", "follow_up_at": None, "lost_reason": "no_budget"},
        )
        self.assertEqual(res_lost_ok.status_code, 200, res_lost_ok.text)

    def test_channel_cost_csv_import(self) -> None:
        csv_text = "date_iso,channel,cost\n2026-02-18,google_ads,120.5\n2026-02-18,meta_ads,99.0\n"
        res = self.client.post(
            "/api/admin/channel-costs/import-csv",
            params={"token": "test-token"},
            headers=self.admin_headers,
            json={"csv_text": csv_text},
        )
        self.assertEqual(res.status_code, 200, res.text)
        out = res.json()
        self.assertEqual(int(out.get("imported") or 0), 2)

    def test_feature_flags_disable_reports(self) -> None:
        os.environ["ROI_ENABLED"] = "false"
        os.environ["WIN_MODEL_ENABLED"] = "false"
        res_roi = self.client.get("/api/admin/reports/roi?days=30&token=test-token", headers=self.admin_headers)
        self.assertEqual(res_roi.status_code, 200, res_roi.text)
        self.assertFalse(bool((res_roi.json() or {}).get("enabled", True)))

        res_win = self.client.get("/api/admin/reports/win-model?days=120&token=test-token", headers=self.admin_headers)
        self.assertEqual(res_win.status_code, 200, res_win.text)
        self.assertFalse(bool((res_win.json() or {}).get("enabled", True)))

    def test_feature_flags_update_endpoint(self) -> None:
        res = self.client.post(
            "/api/admin/features",
            params={"token": "test-token"},
            headers=self.admin_headers,
            json={
                "AUTOPILOT_ENABLED": False,
                "WIN_MODEL_ENABLED": True,
                "ROI_ENABLED": False,
                "persist": False,
            },
        )
        self.assertEqual(res.status_code, 200, res.text)
        out = res.json()
        self.assertTrue(out.get("ok"))
        flags = out.get("features") or {}
        self.assertFalse(bool(flags.get("AUTOPILOT_ENABLED", True)))
        self.assertFalse(bool(flags.get("ROI_ENABLED", True)))

    def test_worker_process_job_marks_done(self) -> None:
        job_id = "JOB-TEST-1"
        now = appmod.now_iso()
        dbmod.insert_job(job_id=job_id, status="queued", payload_json='{"mode":"video","model":"Kling 01"}', now_iso=now)
        asyncio.run(process_job(job_id, {"mode": "video", "model": "Kling 01"}))
        row = dbmod.get_job(job_id)
        self.assertIsNotNone(row)
        self.assertEqual(str((row or {}).get("status") or ""), "done")


if __name__ == "__main__":
    unittest.main()
