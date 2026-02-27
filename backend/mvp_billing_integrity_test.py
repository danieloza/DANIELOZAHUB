import hashlib
import hmac
import json
import os
import threading
import time
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor

import psycopg
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.app import app
from backend.migrate_postgres import apply_migrations
from backend.mvp_billing import JobCreateIn, _create_job_with_credit_hold, _recover_stale_running_jobs


def _sign(payload_raw: str, secret: str) -> str:
    ts = str(int(time.time()))
    signed = f"{ts}.{payload_raw}".encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


class MVPBillingIntegrityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dsn = (os.getenv("DATABASE_URL") or "").strip()
        cls.whsec = (os.getenv("STRIPE_WEBHOOK_SECRET") or "").strip()
        if not cls.dsn:
            raise unittest.SkipTest("DATABASE_URL is required")
        if not cls.whsec:
            raise unittest.SkipTest("STRIPE_WEBHOOK_SECRET is required")
        os.environ["DATABASE_URL"] = cls.dsn
        apply_migrations()
        os.environ["ADMIN_TOKEN"] = "admin-test-token"
        os.environ["LEGACY_QUEUE_WORKER_ENABLED"] = "false"
        os.environ.pop("AUTH_ORIGIN_ALLOWLIST", None)
        cls.lock = threading.Lock()

    def _create_user(self, email: str, password_hash: str = "x") -> str:
        user_id = str(uuid.uuid4())
        with psycopg.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO users (id,email,password_hash,is_active) VALUES (%s,%s,%s,true)",
                    (user_id, email, password_hash),
                )
                conn.commit()
        return user_id

    def _seed_credits(self, user_id: str, amount: int, key: str) -> None:
        with psycopg.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO credit_ledger
                      (id,user_id,entry_type,amount,balance_after,source_type,source_id,idempotency_key,meta)
                    VALUES
                      (%s,%s,'topup',%s,%s,'admin','seed',%s,%s::jsonb)
                    ON CONFLICT (idempotency_key) DO NOTHING
                    """,
                    (str(uuid.uuid4()), user_id, amount, amount, key, json.dumps({"seed": True})),
                )
                conn.commit()

    def test_webhook_idempotency_single_ledger_entry(self) -> None:
        with TestClient(app) as client:
            user_id = self._create_user(f"idem-{int(time.time())}@example.com")
            event_id = f"evt_idem_{int(time.time())}"
            payload = {
                "id": event_id,
                "type": "checkout.session.completed",
                "data": {
                    "object": {
                        "id": f"cs_idem_{int(time.time())}",
                        "metadata": {"user_id": user_id, "credits": "13"},
                    }
                },
            }
            raw = json.dumps(payload, separators=(",", ":"))
            sig = _sign(raw, self.whsec)
            headers = {"Stripe-Signature": sig, "Content-Type": "application/json"}

            first = client.post("/api/billing/stripe/webhook", data=raw, headers=headers)
            second = client.post("/api/billing/stripe/webhook", data=raw, headers=headers)

            self.assertEqual(first.status_code, 200, first.text)
            self.assertEqual(second.status_code, 200, second.text)
            self.assertEqual(first.json().get("status"), "processed", first.text)
            self.assertEqual(second.json().get("status"), "duplicate", second.text)

            with psycopg.connect(self.dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT COUNT(*) FROM credit_ledger
                        WHERE user_id=%s AND idempotency_key=%s
                        """,
                        (user_id, f"stripe:{event_id}:topup"),
                    )
                    count = int(cur.fetchone()[0])
            self.assertEqual(count, 1)

    def test_insufficient_credits_returns_402(self) -> None:
        with TestClient(app) as client:
            email = f"insufficient-{int(time.time())}@example.com"
            reg = client.post("/api/auth/register", json={"email": email, "password": "StrongPass123"})
            self.assertEqual(reg.status_code, 200, reg.text)
            token = reg.json()["token"]
            headers = {"Authorization": f"Bearer {token}"}

            create_job = client.post(
                "/api/jobs",
                json={"provider": "mock", "operation": "image.generate", "credits_cost": 99, "input": {}},
                headers=headers,
            )
            self.assertEqual(create_job.status_code, 402, create_job.text)

    def test_credit_hold_race_allows_single_success(self) -> None:
        user_id = self._create_user(f"race-{int(time.time())}@example.com")
        self._seed_credits(user_id, 5, f"seed-race-{int(time.time())}")

        payload = JobCreateIn(provider="mock", operation="image.generate", credits_cost=4, input={"prompt": "r"})
        results = []

        def run_once() -> str:
            try:
                row = _create_job_with_credit_hold(user_id, payload)
                return f"ok:{row['id']}"
            except HTTPException as exc:
                return f"err:{exc.status_code}"

        with ThreadPoolExecutor(max_workers=2) as ex:
            futures = [ex.submit(run_once) for _ in range(2)]
            results = [f.result() for f in futures]

        ok_count = sum(1 for x in results if x.startswith("ok:"))
        err_402 = sum(1 for x in results if x == "err:402")
        self.assertEqual(ok_count, 1, results)
        self.assertEqual(err_402, 1, results)

    def test_job_create_idempotency_key_prevents_double_hold(self) -> None:
        with TestClient(app) as client:
            email = f"job-idem-{int(time.time())}@example.com"
            reg = client.post("/api/auth/register", json={"email": email, "password": "StrongPass123"})
            self.assertEqual(reg.status_code, 200, reg.text)
            reg_json = reg.json()
            user_id = str(reg_json["user"]["id"])
            token = str(reg_json["token"])
            self._seed_credits(user_id, 12, f"seed-job-idem-{int(time.time())}")

            idem = f"job-idem-{int(time.time())}"
            headers = {"Authorization": f"Bearer {token}", "Idempotency-Key": idem}
            payload = {
                "provider": "mock",
                "operation": "image.generate",
                "credits_cost": 5,
                "max_attempts": 2,
                "idempotency_key": idem,
                "input": {"prompt": "idempotent"},
            }
            first = client.post("/api/jobs", headers=headers, json=payload)
            second = client.post("/api/jobs", headers=headers, json=payload)

            self.assertEqual(first.status_code, 200, first.text)
            self.assertEqual(second.status_code, 200, second.text)
            first_job = first.json()["job"]
            second_job = second.json()["job"]
            self.assertEqual(str(first_job["id"]), str(second_job["id"]))
            self.assertEqual(bool(first_job.get("idempotent_replay")), False)
            self.assertEqual(bool(second_job.get("idempotent_replay")), True)

            balance = client.get("/api/credits/balance", headers={"Authorization": f"Bearer {token}"})
            self.assertEqual(balance.status_code, 200, balance.text)
            self.assertEqual(int(balance.json().get("balance") or 0), 7)

            with psycopg.connect(self.dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT COUNT(*) FROM credit_ledger
                        WHERE user_id=%s AND source_type='job' AND source_id=%s AND entry_type='hold'
                        """,
                        (user_id, str(first_job["id"])),
                    )
                    hold_count = int(cur.fetchone()[0])
            self.assertEqual(hold_count, 1)

    def test_failed_job_releases_credits_and_creates_dead_letter(self) -> None:
        with TestClient(app) as client:
            email = f"fail-release-{int(time.time())}@example.com"
            reg = client.post("/api/auth/register", json={"email": email, "password": "StrongPass123"})
            self.assertEqual(reg.status_code, 200, reg.text)
            reg_json = reg.json()
            token = reg_json["token"]
            user_id = reg_json["user"]["id"]
            headers = {"Authorization": f"Bearer {token}"}

            event_id = f"evt_fail_{int(time.time())}"
            payload = {
                "id": event_id,
                "type": "checkout.session.completed",
                "data": {"object": {"id": f"cs_fail_{int(time.time())}", "metadata": {"user_id": user_id, "credits": "5"}}},
            }
            raw = json.dumps(payload, separators=(",", ":"))
            sig = _sign(raw, self.whsec)
            webhook = client.post(
                "/api/billing/stripe/webhook",
                data=raw,
                headers={"Stripe-Signature": sig, "Content-Type": "application/json"},
            )
            self.assertEqual(webhook.status_code, 200, webhook.text)

            job_resp = client.post(
                "/api/jobs",
                headers=headers,
                json={
                    "provider": "replicate",
                    "operation": "image.generate",
                    "credits_cost": 5,
                    "max_attempts": 1,
                    "input": {"prompt": "x"},
                },
            )
            self.assertEqual(job_resp.status_code, 200, job_resp.text)
            job_id = job_resp.json()["job"]["id"]

            status = "queued"
            for _ in range(50):
                d = client.get(f"/api/jobs/{job_id}", headers=headers)
                self.assertEqual(d.status_code, 200, d.text)
                status = str(d.json()["job"]["status"])
                if status == "failed":
                    break
                time.sleep(0.2)
            self.assertEqual(status, "failed")

            bal = client.get("/api/credits/balance", headers=headers)
            self.assertEqual(bal.status_code, 200, bal.text)
            self.assertEqual(int(bal.json()["balance"]), 5)

            dl = client.get("/api/ops/dead-letters", headers={"x-admin-token": "admin-test-token"})
            self.assertEqual(dl.status_code, 200, dl.text)
            job_ids = {str(x.get("job_id")) for x in dl.json().get("rows", [])}
            self.assertIn(job_id, job_ids)

    def test_login_lockout_after_repeated_failures(self) -> None:
        os.environ["AUTH_LOGIN_MAX_ATTEMPTS"] = "2"
        os.environ["AUTH_LOGIN_LOCK_SECONDS"] = "300"
        os.environ["AUTH_LOGIN_WINDOW_SECONDS"] = "300"
        with TestClient(app) as client:
            email = f"lockout-{int(time.time())}@example.com"
            reg = client.post("/api/auth/register", json={"email": email, "password": "StrongPass123"})
            self.assertEqual(reg.status_code, 200, reg.text)

            bad1 = client.post("/api/auth/login", json={"email": email, "password": "WrongPass123"})
            bad2 = client.post("/api/auth/login", json={"email": email, "password": "WrongPass123"})
            bad3 = client.post("/api/auth/login", json={"email": email, "password": "WrongPass123"})
            self.assertEqual(bad1.status_code, 401, bad1.text)
            self.assertEqual(bad2.status_code, 401, bad2.text)
            self.assertEqual(bad3.status_code, 429, bad3.text)

    def test_recover_stale_running_jobs(self) -> None:
        user_retry = self._create_user(f"recover-retry-{int(time.time())}@example.com")
        user_fail = self._create_user(f"recover-fail-{int(time.time())}@example.com")

        self._seed_credits(user_retry, 8, f"seed-recover-retry-{int(time.time())}")
        self._seed_credits(user_fail, 3, f"seed-recover-fail-{int(time.time())}")

        retry_job = _create_job_with_credit_hold(
            user_retry,
            JobCreateIn(
                provider="mock",
                operation="image.generate",
                credits_cost=4,
                max_attempts=2,
                input={"prompt": "retry"},
            ),
        )
        fail_job = _create_job_with_credit_hold(
            user_fail,
            JobCreateIn(
                provider="mock",
                operation="image.generate",
                credits_cost=3,
                max_attempts=1,
                input={"prompt": "fail"},
            ),
        )
        retry_job_id = str(retry_job["id"])
        fail_job_id = str(fail_job["id"])

        with psycopg.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE jobs
                    SET status = 'running',
                        attempt_count = 1,
                        updated_at = now() - INTERVAL '10 minutes'
                    WHERE id IN (%s, %s)
                    """,
                    (retry_job_id, fail_job_id),
                )
            conn.commit()

        old_stale = os.getenv("MVP_RUNNING_STALE_SECONDS")
        os.environ["MVP_RUNNING_STALE_SECONDS"] = "60"
        try:
            summary = _recover_stale_running_jobs()
        finally:
            if old_stale is None:
                os.environ.pop("MVP_RUNNING_STALE_SECONDS", None)
            else:
                os.environ["MVP_RUNNING_STALE_SECONDS"] = old_stale

        self.assertGreaterEqual(int(summary.get("queued") or 0), 1, summary)
        self.assertGreaterEqual(int(summary.get("failed") or 0), 1, summary)

        with psycopg.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT status FROM jobs WHERE id = %s", (retry_job_id,))
                retry_status = str(cur.fetchone()[0])
                cur.execute("SELECT status FROM jobs WHERE id = %s", (fail_job_id,))
                fail_status = str(cur.fetchone()[0])
                cur.execute("SELECT COALESCE(SUM(amount), 0) FROM credit_ledger WHERE user_id = %s", (user_retry,))
                retry_balance = int(cur.fetchone()[0])
                cur.execute("SELECT COALESCE(SUM(amount), 0) FROM credit_ledger WHERE user_id = %s", (user_fail,))
                fail_balance = int(cur.fetchone()[0])
                cur.execute("SELECT COUNT(*) FROM job_dead_letters WHERE job_id = %s", (fail_job_id,))
                dead_letters = int(cur.fetchone()[0])
                cur.execute(
                    """
                    SELECT COUNT(*) FROM job_events
                    WHERE job_id = %s
                      AND event_type = 'retry_scheduled'
                      AND payload->>'recovered' = 'true'
                    """,
                    (retry_job_id,),
                )
                recovered_events = int(cur.fetchone()[0])

        self.assertEqual(retry_status, "queued")
        self.assertEqual(fail_status, "failed")
        self.assertEqual(retry_balance, 4)
        self.assertEqual(fail_balance, 3)
        self.assertEqual(dead_letters, 1)
        self.assertGreaterEqual(recovered_events, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
