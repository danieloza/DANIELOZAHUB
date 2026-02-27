import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.request
import uuid


def _require_env(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    if not value:
        raise RuntimeError(f"Missing required env: {name}")
    return value


def _call(base_url: str, path: str, *, method: str = "GET", body=None, headers=None, retries: int = 3):
    url = base_url.rstrip("/") + path
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    last_exc = None
    for attempt in range(max(1, retries)):
        req = urllib.request.Request(url, data=data, method=method, headers=req_headers)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode("utf-8")
                payload = json.loads(raw) if raw else {}
                return resp.getcode(), payload
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8")
            try:
                payload = json.loads(raw) if raw else {}
            except Exception:
                payload = {"raw": raw}
            return exc.code, payload
        except (urllib.error.URLError, TimeoutError) as exc:
            last_exc = exc
            if attempt + 1 >= max(1, retries):
                raise
            time.sleep(1.5 * (attempt + 1))
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("unreachable")


def _post_webhook(base_url: str, payload_raw: str, signature: str, retries: int = 3):
    last_exc = None
    for attempt in range(max(1, retries)):
        req = urllib.request.Request(
            base_url + "/api/billing/stripe/webhook",
            data=payload_raw.encode("utf-8"),
            method="POST",
            headers={"Stripe-Signature": signature, "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode("utf-8")
                return resp.getcode(), json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8")
            return exc.code, json.loads(raw) if raw else {}
        except (urllib.error.URLError, TimeoutError) as exc:
            last_exc = exc
            if attempt + 1 >= max(1, retries):
                raise
            time.sleep(1.5 * (attempt + 1))
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("unreachable")


def _assert(cond: bool, msg: str):
    if not cond:
        raise RuntimeError(msg)


def _sign_stripe_payload(payload_raw: str, secret: str) -> str:
    ts = str(int(time.time()))
    signed = f"{ts}.{payload_raw}".encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


def main() -> None:
    base_url = _require_env("BACKEND_BASE_URL").rstrip("/")
    webhook_secret = _require_env("STRIPE_WEBHOOK_SECRET")
    browser_headers = {
        "Origin": base_url,
        "Referer": base_url + "/app.html",
    }

    email = f"live-smoke-{int(time.time())}-{uuid.uuid4().hex[:6]}@example.com"
    password = "StrongPass123"

    sc, reg = _call(
        base_url,
        "/api/auth/register",
        method="POST",
        body={"email": email, "password": password},
        headers=browser_headers,
    )
    _assert(sc == 200, f"register failed: {sc} {reg}")
    token = str((reg.get("token") or ""))
    user_id = str(((reg.get("user") or {}).get("id") or ""))
    _assert(token and user_id, f"register payload invalid: {reg}")
    auth_headers = {"Authorization": f"Bearer {token}", **browser_headers}

    event = {
        "id": f"evt_live_smoke_{int(time.time())}_{uuid.uuid4().hex[:6]}",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": f"cs_live_smoke_{int(time.time())}",
                "metadata": {"user_id": user_id, "credits": "20"},
            }
        },
    }
    payload_raw = json.dumps(event, separators=(",", ":"))
    signature = _sign_stripe_payload(payload_raw, webhook_secret)
    webhook_sc, webhook = _post_webhook(base_url, payload_raw, signature, retries=3)

    _assert(webhook_sc == 200, f"webhook failed: {webhook_sc} {webhook}")
    _assert(str(webhook.get("status")) == "processed", f"webhook not processed: {webhook}")

    sc, bal = _call(base_url, "/api/credits/balance", headers=auth_headers)
    _assert(sc == 200 and int(bal.get("balance", -1)) == 20, f"balance after topup invalid: {sc} {bal}")

    sc, created = _call(
        base_url,
        "/api/jobs",
        method="POST",
        headers=auth_headers,
        body={
            "provider": "mock",
            "operation": "image.generate",
            "credits_cost": 5,
            "input": {"prompt": "live smoke"},
        },
    )
    _assert(sc == 200, f"job creation failed: {sc} {created}")
    job_id = str(((created.get("job") or {}).get("id") or ""))
    _assert(job_id, f"missing job id in response: {created}")

    status = "queued"
    for _ in range(30):
        time.sleep(0.3)
        sc, job = _call(base_url, f"/api/jobs/{job_id}", headers=auth_headers)
        _assert(sc == 200, f"job fetch failed: {sc} {job}")
        status = str(((job.get("job") or {}).get("status") or ""))
        if status in {"succeeded", "failed"}:
            break
    _assert(status == "succeeded", f"job did not succeed: {status}")

    sc, bal2 = _call(base_url, "/api/credits/balance", headers=auth_headers)
    _assert(sc == 200 and int(bal2.get("balance", -1)) == 15, f"balance after job invalid: {sc} {bal2}")

    print(json.dumps({"ok": True, "email": email, "job_id": job_id, "status": status}))


if __name__ == "__main__":
    main()
