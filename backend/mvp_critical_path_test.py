import hashlib
import hmac
import json
import os
import time
import unittest

from fastapi.testclient import TestClient

from backend.app import app


def _sign_stripe_payload(payload_raw: str, secret: str) -> str:
    ts = str(int(time.time()))
    signed = f"{ts}.{payload_raw}".encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


class MVPCriticalPathTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not (os.getenv("DATABASE_URL") or "").strip():
            raise unittest.SkipTest("DATABASE_URL is required")
        if not (os.getenv("STRIPE_WEBHOOK_SECRET") or "").strip():
            raise unittest.SkipTest("STRIPE_WEBHOOK_SECRET is required")
        os.environ["LEGACY_QUEUE_WORKER_ENABLED"] = "false"
    def test_signup_webhook_job_result(self) -> None:
        email = f"mvp-e2e-{int(time.time())}@example.com"
        password = "StrongPass123"
        with TestClient(app) as client:
            reg = client.post("/api/auth/register", json={"email": email, "password": password})
            self.assertEqual(reg.status_code, 200, reg.text)
            reg_json = reg.json()
            token = reg_json["token"]
            user_id = reg_json["user"]["id"]
            headers = {"Authorization": f"Bearer {token}"}

            event = {
                "id": f"evt_test_{int(time.time())}",
                "type": "checkout.session.completed",
                "data": {
                    "object": {
                        "id": f"cs_test_{int(time.time())}",
                        "metadata": {
                            "user_id": user_id,
                            "credits": "20",
                        },
                    }
                },
            }
            payload_raw = json.dumps(event, separators=(",", ":"))
            signature = _sign_stripe_payload(payload_raw, os.getenv("STRIPE_WEBHOOK_SECRET", ""))
            webhook = client.post(
                "/api/billing/stripe/webhook",
                data=payload_raw,
                headers={"Stripe-Signature": signature, "Content-Type": "application/json"},
            )
            self.assertEqual(webhook.status_code, 200, webhook.text)
            self.assertEqual(webhook.json().get("status"), "processed", webhook.text)

            create_job = client.post(
                "/api/jobs",
                json={
                    "provider": "mock",
                    "operation": "image.generate",
                    "credits_cost": 5,
                    "input": {"prompt": "e2e"},
                },
                headers=headers,
            )
            self.assertEqual(create_job.status_code, 200, create_job.text)
            job_id = create_job.json()["job"]["id"]

            status = "queued"
            for _ in range(30):
                resp = client.get(f"/api/jobs/{job_id}", headers=headers)
                self.assertEqual(resp.status_code, 200, resp.text)
                status = str(resp.json()["job"]["status"])
                if status in {"succeeded", "failed"}:
                    break
                time.sleep(0.2)
            self.assertEqual(status, "succeeded")

            balance_resp = client.get("/api/credits/balance", headers=headers)
            self.assertEqual(balance_resp.status_code, 200, balance_resp.text)
            balance = int(balance_resp.json()["balance"])
            self.assertEqual(balance, 15)


if __name__ == "__main__":
    unittest.main(verbosity=2)
