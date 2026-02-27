import asyncio
import hashlib
import json
import logging
import os
import secrets
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(tags=["mvp"])

logger = logging.getLogger("mvp")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

_WORKER_TASK: Optional[asyncio.Task] = None
_WORKER_STATE: Dict[str, Any] = {
    "running": False,
    "last_heartbeat": None,
    "processed_total": 0,
    "failures_total": 0,
}
_AUTH_LOCK = threading.Lock()
_LOGIN_ATTEMPTS: Dict[str, List[datetime]] = {}
_LOGIN_LOCKED_UNTIL: Dict[str, datetime] = {}


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now_utc().isoformat()


def _env_bool(name: str, default: bool) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _worker_enabled() -> bool:
    if not (os.getenv("DATABASE_URL") or "").strip():
        return False
    return _env_bool("MVP_WORKER_ENABLED", True)


def _require_env(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    if not value:
        raise HTTPException(status_code=503, detail=f"Missing required env var: {name}")
    return value


def _connect_postgres():
    dsn = _require_env("DATABASE_URL")
    try:
        import psycopg
        from psycopg.rows import dict_row
    except Exception as exc:
        raise HTTPException(status_code=500, detail="psycopg is not installed") from exc
    try:
        conn = psycopg.connect(dsn)
        conn.row_factory = dict_row
        return conn
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Cannot connect to Postgres: {exc}") from exc


def _hash_password(password: str, *, iterations: int = 390000) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations).hex()
    return f"pbkdf2_sha256${iterations}${salt}${digest}"


def _verify_password(password: str, password_hash: str) -> bool:
    try:
        algo, iter_raw, salt, digest = password_hash.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        iterations = int(iter_raw)
    except Exception:
        return False
    check = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations).hex()
    return secrets.compare_digest(check, digest)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _password_policy_ok(password: str) -> bool:
    if len(password) < 8:
        return False
    has_alpha = any(c.isalpha() for c in password)
    has_digit = any(c.isdigit() for c in password)
    return has_alpha and has_digit


def _client_ip(req: Request) -> str:
    xff = (req.headers.get("x-forwarded-for") or "").strip()
    if xff:
        return xff.split(",", 1)[0].strip()
    return req.client.host if req.client else "unknown"


def _auth_origin_check(req: Request) -> None:
    raw_allow = (os.getenv("AUTH_ORIGIN_ALLOWLIST") or "").strip()
    if not raw_allow:
        return
    allow = {x.strip().rstrip("/") for x in raw_allow.split(",") if x.strip()}
    origin = (req.headers.get("origin") or "").strip().rstrip("/")
    referer = (req.headers.get("referer") or "").strip().rstrip("/")
    if origin and origin in allow:
        return
    if referer:
        for allowed in allow:
            if referer.startswith(allowed + "/") or referer == allowed:
                return
    raise HTTPException(status_code=403, detail="auth origin blocked")


def _login_key(email: str, ip: str) -> str:
    return f"{email.lower()}|{ip}"


def _login_limits() -> Tuple[int, int, int]:
    window_s = int((os.getenv("AUTH_LOGIN_WINDOW_SECONDS") or "900").strip())
    max_attempts = int((os.getenv("AUTH_LOGIN_MAX_ATTEMPTS") or "8").strip())
    lock_s = int((os.getenv("AUTH_LOGIN_LOCK_SECONDS") or "900").strip())
    return max(60, window_s), max(1, max_attempts), max(60, lock_s)


def _prune_login_state(now: datetime, window_s: int) -> None:
    threshold = now - timedelta(seconds=window_s)
    for key in list(_LOGIN_ATTEMPTS.keys()):
        arr = [t for t in _LOGIN_ATTEMPTS.get(key, []) if t >= threshold]
        if arr:
            _LOGIN_ATTEMPTS[key] = arr
        else:
            _LOGIN_ATTEMPTS.pop(key, None)
    for key in list(_LOGIN_LOCKED_UNTIL.keys()):
        if _LOGIN_LOCKED_UNTIL[key] <= now:
            _LOGIN_LOCKED_UNTIL.pop(key, None)


def _assert_login_allowed(email: str, ip: str) -> None:
    now = _now_utc()
    window_s, _, _ = _login_limits()
    key = _login_key(email, ip)
    with _AUTH_LOCK:
        _prune_login_state(now, window_s)
        until = _LOGIN_LOCKED_UNTIL.get(key)
        if until and until > now:
            wait_s = int((until - now).total_seconds())
            raise HTTPException(status_code=429, detail=f"too many login attempts, retry in {wait_s}s")


def _register_login_failure(email: str, ip: str) -> None:
    now = _now_utc()
    window_s, max_attempts, lock_s = _login_limits()
    key = _login_key(email, ip)
    with _AUTH_LOCK:
        _prune_login_state(now, window_s)
        arr = _LOGIN_ATTEMPTS.get(key, [])
        arr.append(now)
        _LOGIN_ATTEMPTS[key] = arr
        if len(arr) >= max_attempts:
            _LOGIN_LOCKED_UNTIL[key] = now + timedelta(seconds=lock_s)


def _register_login_success(email: str, ip: str) -> None:
    key = _login_key(email, ip)
    with _AUTH_LOCK:
        _LOGIN_ATTEMPTS.pop(key, None)
        _LOGIN_LOCKED_UNTIL.pop(key, None)


def _parse_bearer_token(req: Request) -> str:
    auth = (req.headers.get("authorization") or "").strip()
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = auth.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Empty bearer token")
    return token


def _current_balance(cur: Any, user_id: str) -> int:
    cur.execute("SELECT COALESCE(SUM(amount), 0) AS balance FROM credit_ledger WHERE user_id = %s", (user_id,))
    row = cur.fetchone()
    return int((row or {}).get("balance") or 0)


def _admin_token_ok(req: Request) -> bool:
    expected = (os.getenv("ADMIN_TOKEN") or "").strip()
    if not expected:
        return False
    supplied = (req.headers.get("x-admin-token") or req.query_params.get("token") or "").strip()
    return bool(supplied) and secrets.compare_digest(supplied, expected)


def _auth_user_from_token(req: Request) -> Dict[str, Any]:
    token = _parse_bearer_token(req)
    token_hash = _hash_token(token)
    with _connect_postgres() as conn:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                      s.id AS session_id,
                      s.user_id,
                      s.expires_at,
                      u.email,
                      u.is_active
                    FROM auth_sessions s
                    JOIN users u ON u.id = s.user_id
                    WHERE s.token_hash = %s
                      AND s.revoked_at IS NULL
                    LIMIT 1
                    """,
                    (token_hash,),
                )
                row = cur.fetchone()
                if not row:
                    raise HTTPException(status_code=401, detail="Invalid auth token")
                expires_at = row.get("expires_at")
                if not expires_at or expires_at <= _now_utc():
                    raise HTTPException(status_code=401, detail="Session expired")
                if not bool(row.get("is_active")):
                    raise HTTPException(status_code=403, detail="User is disabled")
                cur.execute("UPDATE auth_sessions SET last_used_at = now() WHERE id = %s", (row["session_id"],))

                req.state.user_id = str(row["user_id"])
                req.state.session_id = str(row["session_id"])
                return {
                    "id": str(row["user_id"]),
                    "email": str(row["email"]),
                    "session_id": str(row["session_id"]),
                    "expires_at": row["expires_at"].isoformat() if row.get("expires_at") else None,
                }


def _issue_session(cur: Any, user_id: str) -> Tuple[str, str]:
    token = secrets.token_urlsafe(48)
    token_hash = _hash_token(token)
    days = int((os.getenv("AUTH_SESSION_DAYS") or "30").strip())
    expires_at = _now_utc() + timedelta(days=max(1, days))
    cur.execute(
        """
        INSERT INTO auth_sessions
          (id, user_id, token_hash, created_at, expires_at, last_used_at)
        VALUES
          (%s, %s, %s, now(), %s, now())
        """,
        (str(uuid.uuid4()), user_id, token_hash, expires_at),
    )
    return token, expires_at.isoformat()


class RegisterIn(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=8, max_length=128)


class CheckoutSessionIn(BaseModel):
    credits: int = Field(ge=1, le=1_000_000)
    success_url: str = Field(min_length=8, max_length=512)
    cancel_url: str = Field(min_length=8, max_length=512)
    currency: str = Field(default="usd", min_length=3, max_length=8)


class JobCreateIn(BaseModel):
    provider: str = Field(min_length=2, max_length=80)
    operation: str = Field(min_length=2, max_length=120)
    input: Dict[str, Any] = Field(default_factory=dict)
    credits_cost: int = Field(default=1, ge=1, le=1_000_000)
    max_attempts: int = Field(default=5, ge=1, le=20)


class CreditAdjustmentIn(BaseModel):
    user_id: str = Field(min_length=36, max_length=36)
    amount: int = Field(ge=-1_000_000, le=1_000_000)
    reason: str = Field(min_length=3, max_length=240)
    idempotency_key: str = Field(default="", max_length=200)


def _parse_stripe_event(payload: bytes, signature_header: str) -> Dict[str, Any]:
    webhook_secret = _require_env("STRIPE_WEBHOOK_SECRET")
    try:
        import stripe
    except Exception as exc:
        raise HTTPException(status_code=500, detail="stripe package is not installed") from exc

    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=signature_header,
            secret=webhook_secret,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid Stripe signature: {exc}") from exc
    return dict(event)


def _resolve_checkout_credits(session: Dict[str, Any]) -> int:
    metadata = session.get("metadata") or {}
    raw = metadata.get("credits")
    if raw is None:
        return 0
    try:
        credits = int(str(raw).strip())
    except Exception:
        return 0
    return credits if credits > 0 else 0


def _resolve_checkout_user_id(session: Dict[str, Any]) -> str:
    metadata = session.get("metadata") or {}
    user_id = str(metadata.get("user_id") or "").strip()
    if user_id:
        return user_id
    return str(session.get("client_reference_id") or "").strip()


def _apply_checkout_completed(cur: Any, event: Dict[str, Any]) -> Tuple[str, Optional[str]]:
    data = event.get("data") or {}
    session = data.get("object") or {}
    event_id = str(event.get("id") or "").strip()
    if not event_id:
        return "failed", "missing event id"

    user_id = _resolve_checkout_user_id(session)
    if not user_id:
        return "failed", "missing user_id (expected metadata.user_id or client_reference_id)"

    credits = _resolve_checkout_credits(session)
    if credits <= 0:
        return "failed", "missing positive credits value in metadata.credits"

    cur.execute("SELECT id FROM users WHERE id = %s FOR UPDATE", (user_id,))
    if not cur.fetchone():
        return "failed", f"user not found: {user_id}"

    balance_before = _current_balance(cur, user_id)
    balance_after = balance_before + credits

    ledger_id = str(uuid.uuid4())
    source_id = str(session.get("id") or event_id)
    idem_key = f"stripe:{event_id}:topup"
    meta = {
        "stripe_event_id": event_id,
        "stripe_session_id": source_id,
        "type": "checkout.session.completed",
    }
    cur.execute(
        """
        INSERT INTO credit_ledger
          (id, user_id, entry_type, amount, balance_after, source_type, source_id, idempotency_key, meta, created_at)
        VALUES
          (%s, %s, 'topup', %s, %s, 'stripe_event', %s, %s, %s::jsonb, now())
        ON CONFLICT (idempotency_key) DO NOTHING
        RETURNING id
        """,
        (ledger_id, user_id, credits, balance_after, source_id, idem_key, json.dumps(meta)),
    )
    cur.fetchone()
    return "processed", None


def _process_event_in_tx(event: Dict[str, Any]) -> Dict[str, Any]:
    event_id = str(event.get("id") or "").strip()
    event_type = str(event.get("type") or "").strip()
    if not event_id or not event_type:
        raise HTTPException(status_code=400, detail="Stripe event missing id/type")

    with _connect_postgres() as conn:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO webhook_events
                      (provider, event_id, event_type, payload, received_at, status)
                    VALUES
                      ('stripe', %s, %s, %s::jsonb, now(), 'received')
                    ON CONFLICT (provider, event_id) DO NOTHING
                    RETURNING id
                    """,
                    (event_id, event_type, json.dumps(event)),
                )
                inserted = cur.fetchone()
                if not inserted:
                    return {"status": "duplicate", "event_id": event_id, "event_type": event_type}

                status = "ignored"
                error_text = None
                if event_type == "checkout.session.completed":
                    status, error_text = _apply_checkout_completed(cur, event)

                cur.execute(
                    """
                    UPDATE webhook_events
                    SET status = %s, error_text = %s, processed_at = now()
                    WHERE provider = 'stripe' AND event_id = %s
                    """,
                    (status, error_text, event_id),
                )
                return {"status": status, "event_id": event_id, "event_type": event_type}


def _create_job_with_credit_hold(user_id: str, data: JobCreateIn) -> Dict[str, Any]:
    job_id = str(uuid.uuid4())
    hold_entry_id = str(uuid.uuid4())

    with _connect_postgres() as conn:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM users WHERE id = %s FOR UPDATE", (user_id,))
                if not cur.fetchone():
                    raise HTTPException(status_code=404, detail="user not found")

                balance_before = _current_balance(cur, user_id)
                if balance_before < data.credits_cost:
                    raise HTTPException(
                        status_code=402,
                        detail=f"insufficient credits: required={data.credits_cost}, available={balance_before}",
                    )

                balance_after = balance_before - data.credits_cost
                hold_idem_key = f"job:{job_id}:hold"
                hold_meta = {
                    "job_id": job_id,
                    "provider": data.provider,
                    "operation": data.operation,
                    "kind": "reservation",
                }
                cur.execute(
                    """
                    INSERT INTO credit_ledger
                      (id, user_id, entry_type, amount, balance_after, source_type, source_id, idempotency_key, meta, created_at)
                    VALUES
                      (%s, %s, 'hold', %s, %s, 'job', %s, %s, %s::jsonb, now())
                    """,
                    (
                        hold_entry_id,
                        user_id,
                        -data.credits_cost,
                        balance_after,
                        job_id,
                        hold_idem_key,
                        json.dumps(hold_meta),
                    ),
                )

                cur.execute(
                    """
                    INSERT INTO jobs
                      (id, user_id, provider, operation, status, attempt_count, max_attempts, credits_cost, available_at, input_json, created_at, updated_at)
                    VALUES
                      (%s, %s, %s, %s, 'queued', 0, %s, %s, now(), %s::jsonb, now(), now())
                    """,
                    (
                        job_id,
                        user_id,
                        data.provider,
                        data.operation,
                        data.max_attempts,
                        data.credits_cost,
                        json.dumps(data.input or {}),
                    ),
                )
                cur.execute(
                    """
                    INSERT INTO job_events (job_id, event_type, payload, created_at)
                    VALUES (%s, 'queued', %s::jsonb, now())
                    """,
                    (
                        job_id,
                        json.dumps(
                            {
                                "credits_cost": data.credits_cost,
                                "balance_before": balance_before,
                                "balance_after": balance_after,
                            }
                        ),
                    ),
                )

                return {
                    "id": job_id,
                    "status": "queued",
                    "user_id": user_id,
                    "provider": data.provider,
                    "operation": data.operation,
                    "credits_cost": data.credits_cost,
                    "balance_after": balance_after,
                }


def _apply_credit_adjustment(data: CreditAdjustmentIn) -> Dict[str, Any]:
    if data.amount == 0:
        raise HTTPException(status_code=400, detail="adjustment amount cannot be zero")
    idem_key = (data.idempotency_key or "").strip() or f"admin:adjust:{data.user_id}:{hashlib.sha1((data.reason + str(data.amount)).encode('utf-8')).hexdigest()}"
    with _connect_postgres() as conn:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM users WHERE id = %s FOR UPDATE", (data.user_id,))
                if not cur.fetchone():
                    raise HTTPException(status_code=404, detail="user not found")
                balance_before = _current_balance(cur, data.user_id)
                balance_after = balance_before + int(data.amount)
                cur.execute(
                    """
                    INSERT INTO credit_ledger
                      (id, user_id, entry_type, amount, balance_after, source_type, source_id, idempotency_key, meta, created_at)
                    VALUES
                      (%s, %s, 'adjustment', %s, %s, 'admin', %s, %s, %s::jsonb, now())
                    ON CONFLICT (idempotency_key) DO NOTHING
                    RETURNING id
                    """,
                    (
                        str(uuid.uuid4()),
                        data.user_id,
                        int(data.amount),
                        balance_after,
                        "manual_adjustment",
                        idem_key,
                        json.dumps({"reason": data.reason}),
                    ),
                )
                row = cur.fetchone()
                applied = row is not None
                if not applied:
                    cur.execute(
                        """
                        SELECT amount, balance_after, created_at
                        FROM credit_ledger
                        WHERE idempotency_key = %s
                        LIMIT 1
                        """,
                        (idem_key,),
                    )
                    existing = cur.fetchone() or {}
                    return {
                        "applied": False,
                        "idempotency_key": idem_key,
                        "amount": int(existing.get("amount") or 0),
                        "balance_after": int(existing.get("balance_after") or balance_before),
                        "created_at": existing.get("created_at").isoformat() if existing.get("created_at") else None,
                    }
                return {
                    "applied": True,
                    "idempotency_key": idem_key,
                    "amount": int(data.amount),
                    "balance_before": balance_before,
                    "balance_after": balance_after,
                }


def _backoff_seconds(attempt_count: int) -> int:
    exp = max(0, attempt_count - 1)
    seconds = 10 * (3 ** exp)
    return int(min(900, seconds))


def _insert_ledger_release(cur: Any, user_id: str, job_id: str, credits_cost: int, reason: str) -> None:
    if credits_cost <= 0:
        return
    cur.execute("SELECT id FROM users WHERE id = %s FOR UPDATE", (user_id,))
    if not cur.fetchone():
        return
    balance_before = _current_balance(cur, user_id)
    balance_after = balance_before + credits_cost
    idem_key = f"job:{job_id}:{reason}"
    cur.execute(
        """
        INSERT INTO credit_ledger
          (id, user_id, entry_type, amount, balance_after, source_type, source_id, idempotency_key, meta, created_at)
        VALUES
          (%s, %s, 'release', %s, %s, 'job', %s, %s, %s::jsonb, now())
        ON CONFLICT (idempotency_key) DO NOTHING
        """,
        (
            str(uuid.uuid4()),
            user_id,
            credits_cost,
            balance_after,
            job_id,
            idem_key,
            json.dumps({"job_id": job_id, "reason": reason}),
        ),
    )


def _insert_ledger_consume(cur: Any, user_id: str, job_id: str, credits_cost: int) -> None:
    if credits_cost <= 0:
        return
    cur.execute("SELECT id FROM users WHERE id = %s FOR UPDATE", (user_id,))
    if not cur.fetchone():
        return
    balance_before = _current_balance(cur, user_id)
    balance_after = balance_before - credits_cost
    idem_key = f"job:{job_id}:consume"
    cur.execute(
        """
        INSERT INTO credit_ledger
          (id, user_id, entry_type, amount, balance_after, source_type, source_id, idempotency_key, meta, created_at)
        VALUES
          (%s, %s, 'consume', %s, %s, 'job', %s, %s, %s::jsonb, now())
        ON CONFLICT (idempotency_key) DO NOTHING
        """,
        (
            str(uuid.uuid4()),
            user_id,
            -credits_cost,
            balance_after,
            job_id,
            idem_key,
            json.dumps({"job_id": job_id, "reason": "job_succeeded"}),
        ),
    )


def _replicate_run_prediction(input_json: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    try:
        import requests
    except Exception as exc:
        raise RuntimeError("requests package missing for replicate provider") from exc

    token = (os.getenv("REPLICATE_API_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("REPLICATE_API_TOKEN missing for provider=replicate")

    model = str(input_json.get("model") or "").strip()
    version = str(input_json.get("version") or "").strip()
    replicate_input = input_json.get("input")
    if replicate_input is None:
        replicate_input = {k: v for k, v in input_json.items() if k not in {"model", "version"}}
    if not isinstance(replicate_input, dict):
        raise RuntimeError("replicate input must be an object")
    if not version and not model:
        raise RuntimeError("replicate requires input.version or input.model")

    payload: Dict[str, Any] = {"input": replicate_input}
    if version:
        payload["version"] = version
    else:
        payload["model"] = model

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    create_resp = requests.post(
        "https://api.replicate.com/v1/predictions",
        headers=headers,
        json=payload,
        timeout=30,
    )
    if create_resp.status_code >= 300:
        raise RuntimeError(f"replicate create failed: {create_resp.status_code} {create_resp.text[:200]}")
    prediction = create_resp.json() or {}
    prediction_id = str(prediction.get("id") or "").strip()
    if not prediction_id:
        raise RuntimeError("replicate response missing prediction id")

    timeout_s = int((os.getenv("REPLICATE_POLL_TIMEOUT_SECONDS") or "180").strip())
    timeout_s = max(30, timeout_s)
    deadline = time.time() + timeout_s
    status = str(prediction.get("status") or "")
    while status in {"starting", "processing"} and time.time() < deadline:
        time.sleep(2.0)
        get_resp = requests.get(
            f"https://api.replicate.com/v1/predictions/{prediction_id}",
            headers=headers,
            timeout=30,
        )
        if get_resp.status_code >= 300:
            raise RuntimeError(f"replicate poll failed: {get_resp.status_code} {get_resp.text[:200]}")
        prediction = get_resp.json() or {}
        status = str(prediction.get("status") or "")

    if status != "succeeded":
        err = str(prediction.get("error") or "replicate prediction did not succeed")
        raise RuntimeError(err)

    return prediction_id, {
        "ok": True,
        "provider": "replicate",
        "prediction_id": prediction_id,
        "status": status,
        "output": prediction.get("output"),
        "logs": prediction.get("logs"),
        "metrics": prediction.get("metrics"),
        "finished_at": _now_iso(),
    }


def _run_provider(job: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    provider = str(job.get("provider") or "").strip().lower()
    operation = str(job.get("operation") or "").strip().lower()
    input_json = job.get("input_json") or {}
    if not isinstance(input_json, dict):
        input_json = {}

    if bool(input_json.get("force_fail")):
        raise RuntimeError("forced failure via input.force_fail")
    if str(input_json.get("simulate") or "").strip().lower() == "fail":
        raise RuntimeError("simulated provider failure")

    if provider == "replicate":
        return _replicate_run_prediction(input_json)

    time.sleep(0.2)
    return "", {
        "ok": True,
        "provider": provider or "mock",
        "operation": operation,
        "mock_result": True,
        "input_echo": input_json,
        "finished_at": _now_iso(),
    }


def _claim_next_job() -> Optional[Dict[str, Any]]:
    with _connect_postgres() as conn:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                      id, user_id, provider, operation, input_json, status,
                      attempt_count, max_attempts, credits_cost
                    FROM jobs
                    WHERE status = 'queued' AND available_at <= now()
                    ORDER BY available_at ASC, created_at ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                    """
                )
                row = cur.fetchone()
                if not row:
                    return None

                attempt = int(row.get("attempt_count") or 0) + 1
                cur.execute(
                    """
                    UPDATE jobs
                    SET status = 'running',
                        attempt_count = %s,
                        started_at = COALESCE(started_at, now()),
                        updated_at = now()
                    WHERE id = %s
                    """,
                    (attempt, row["id"]),
                )
                cur.execute(
                    """
                    INSERT INTO job_events (job_id, event_type, payload, created_at)
                    VALUES (%s, 'started', %s::jsonb, now())
                    """,
                    (row["id"], json.dumps({"attempt": attempt})),
                )
                row["attempt_count"] = attempt
                return row


def _mark_job_succeeded(job: Dict[str, Any], provider_job_id: str, result_json: Dict[str, Any]) -> None:
    job_id = str(job["id"])
    user_id = str(job["user_id"])
    credits_cost = int(job.get("credits_cost") or 0)
    with _connect_postgres() as conn:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT status FROM jobs WHERE id = %s FOR UPDATE", (job_id,))
                existing = cur.fetchone()
                if not existing or str(existing.get("status") or "") != "running":
                    return

                # Convert hold -> consume without net balance change (release + consume).
                _insert_ledger_release(cur, user_id, job_id, credits_cost, "release_on_success")
                _insert_ledger_consume(cur, user_id, job_id, credits_cost)

                cur.execute(
                    """
                    UPDATE jobs
                    SET status = 'succeeded',
                        provider_job_id = COALESCE(%s, provider_job_id),
                        result_json = %s::jsonb,
                        last_error = NULL,
                        finished_at = now(),
                        updated_at = now()
                    WHERE id = %s
                    """,
                    (provider_job_id or None, json.dumps(result_json), job_id),
                )
                cur.execute(
                    """
                    INSERT INTO job_events (job_id, event_type, payload, created_at)
                    VALUES (%s, 'succeeded', %s::jsonb, now())
                    """,
                    (job_id, json.dumps({"attempt": int(job.get("attempt_count") or 0)})),
                )


def _mark_job_failed_or_retry(job: Dict[str, Any], error_text: str) -> None:
    job_id = str(job["id"])
    user_id = str(job["user_id"])
    attempt_count = int(job.get("attempt_count") or 0)
    max_attempts = int(job.get("max_attempts") or 1)
    credits_cost = int(job.get("credits_cost") or 0)

    with _connect_postgres() as conn:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT status FROM jobs WHERE id = %s FOR UPDATE", (job_id,))
                existing = cur.fetchone()
                if not existing or str(existing.get("status") or "") != "running":
                    return

                if attempt_count < max_attempts:
                    delay_seconds = _backoff_seconds(attempt_count)
                    cur.execute(
                        """
                        UPDATE jobs
                        SET status = 'queued',
                            available_at = now() + make_interval(secs => %s),
                            last_error = %s,
                            updated_at = now()
                        WHERE id = %s
                        """,
                        (delay_seconds, error_text, job_id),
                    )
                    cur.execute(
                        """
                        INSERT INTO job_events (job_id, event_type, payload, created_at)
                        VALUES (%s, 'retry_scheduled', %s::jsonb, now())
                        """,
                        (
                            job_id,
                            json.dumps(
                                {
                                    "attempt": attempt_count,
                                    "next_retry_seconds": delay_seconds,
                                    "error": error_text,
                                }
                            ),
                        ),
                    )
                    return

                _insert_ledger_release(cur, user_id, job_id, credits_cost, "release_on_fail")
                cur.execute(
                    """
                    UPDATE jobs
                    SET status = 'failed',
                        last_error = %s,
                        finished_at = now(),
                        updated_at = now()
                    WHERE id = %s
                    """,
                    (error_text, job_id),
                )
                cur.execute(
                    """
                    INSERT INTO job_events (job_id, event_type, payload, created_at)
                    VALUES (%s, 'failed', %s::jsonb, now())
                    """,
                    (
                        job_id,
                        json.dumps({"attempt": attempt_count, "error": error_text}),
                    ),
                )
                cur.execute(
                    """
                    INSERT INTO job_dead_letters
                      (id, job_id, user_id, reason, payload, created_at)
                    VALUES
                      (%s, %s, %s, %s, %s::jsonb, now())
                    ON CONFLICT (job_id) DO NOTHING
                    """,
                    (
                        str(uuid.uuid4()),
                        job_id,
                        user_id,
                        "max_attempts_exhausted",
                        json.dumps(
                            {
                                "attempt_count": attempt_count,
                                "max_attempts": max_attempts,
                                "error": error_text,
                            }
                        ),
                    ),
                )


def _process_one_job() -> bool:
    job = _claim_next_job()
    if not job:
        return False
    try:
        provider_job_id, result = _run_provider(job)
        _mark_job_succeeded(job, provider_job_id, result)
    except Exception as exc:
        _mark_job_failed_or_retry(job, str(exc))
    return True


async def _mvp_worker_loop() -> None:
    logger.info("mvp worker started")
    while True:
        _WORKER_STATE["last_heartbeat"] = _now_iso()
        try:
            processed = await asyncio.to_thread(_process_one_job)
            if processed:
                _WORKER_STATE["processed_total"] = int(_WORKER_STATE.get("processed_total") or 0) + 1
                continue
            await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            logger.info("mvp worker cancelled")
            raise
        except Exception as exc:
            _WORKER_STATE["failures_total"] = int(_WORKER_STATE.get("failures_total") or 0) + 1
            logger.exception("mvp worker loop error: %s", exc)
            await asyncio.sleep(1.0)


def start_mvp_worker() -> Optional[asyncio.Task]:
    global _WORKER_TASK
    if not _worker_enabled():
        logger.info("mvp worker disabled")
        _WORKER_STATE["running"] = False
        return None
    if _WORKER_TASK and not _WORKER_TASK.done():
        return _WORKER_TASK
    loop = asyncio.get_running_loop()
    _WORKER_TASK = loop.create_task(_mvp_worker_loop(), name="mvp-worker")
    _WORKER_STATE["running"] = True
    return _WORKER_TASK


async def stop_mvp_worker() -> None:
    global _WORKER_TASK
    if not _WORKER_TASK:
        return
    if _WORKER_TASK.done():
        _WORKER_TASK = None
        return
    _WORKER_TASK.cancel()
    try:
        await _WORKER_TASK
    except asyncio.CancelledError:
        pass
    _WORKER_TASK = None
    _WORKER_STATE["running"] = False


def install_mvp_observability(app: FastAPI) -> None:
    if bool(getattr(app.state, "mvp_observability_installed", False)):
        return

    @app.middleware("http")
    async def _request_logger(request: Request, call_next):
        if not request.url.path.startswith("/api/"):
            return await call_next(request)

        started = time.perf_counter()
        request_id = (request.headers.get("x-request-id") or "").strip() or uuid.uuid4().hex
        request.state.request_id = request_id

        status_code = 500
        try:
            response = await call_next(request)
            status_code = int(response.status_code)
            response.headers["x-request-id"] = request_id
            return response
        finally:
            elapsed_ms = int((time.perf_counter() - started) * 1000.0)
            payload = {
                "event": "api_request",
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": status_code,
                "latency_ms": elapsed_ms,
                "user_id": str(getattr(request.state, "user_id", "") or ""),
                "job_id": str(getattr(request.state, "job_id", "") or ""),
                "stripe_event_id": str(getattr(request.state, "stripe_event_id", "") or ""),
            }
            logger.info(json.dumps(payload, ensure_ascii=True))

    app.state.mvp_observability_installed = True


def init_mvp_sentry() -> None:
    dsn = (os.getenv("SENTRY_DSN") or "").strip()
    if not dsn:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
    except Exception as exc:
        logger.warning("Sentry DSN provided but sentry-sdk not available: %s", exc)
        return

    traces_sample_rate = float((os.getenv("SENTRY_TRACES_SAMPLE_RATE") or "0.0").strip())
    sentry_sdk.init(
        dsn=dsn,
        traces_sample_rate=max(0.0, min(1.0, traces_sample_rate)),
        integrations=[FastApiIntegration()],
    )
    logger.info("sentry initialized")


@router.post("/api/auth/register")
def register(req: Request, data: RegisterIn) -> Dict[str, Any]:
    _auth_origin_check(req)
    email = (data.email or "").strip().lower()
    if "@" not in email:
        raise HTTPException(status_code=400, detail="invalid email")
    if not _password_policy_ok(data.password):
        raise HTTPException(status_code=400, detail="password must be at least 8 chars with letters and digits")

    user_id = str(uuid.uuid4())
    password_hash = _hash_password(data.password)

    with _connect_postgres() as conn:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO users (id, email, password_hash, created_at, is_active)
                    VALUES (%s, %s, %s, now(), true)
                    ON CONFLICT DO NOTHING
                    RETURNING id, email, created_at
                    """,
                    (user_id, email, password_hash),
                )
                row = cur.fetchone()
                if not row:
                    raise HTTPException(status_code=409, detail="email already exists")
                token, expires_at = _issue_session(cur, user_id)
                return {
                    "ok": True,
                    "user": {
                        "id": str(row["id"]),
                        "email": str(row["email"]),
                        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
                    },
                    "token": token,
                    "expires_at": expires_at,
                }


@router.post("/api/auth/login")
def login(req: Request, data: LoginIn) -> Dict[str, Any]:
    _auth_origin_check(req)
    email = (data.email or "").strip().lower()
    ip = _client_ip(req)
    _assert_login_allowed(email, ip)
    with _connect_postgres() as conn:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, email, password_hash, is_active
                    FROM users
                    WHERE lower(email) = lower(%s)
                    LIMIT 1
                    """,
                    (email,),
                )
                row = cur.fetchone()
                if not row or not _verify_password(data.password, str(row.get("password_hash") or "")):
                    _register_login_failure(email, ip)
                    raise HTTPException(status_code=401, detail="invalid credentials")
                if not bool(row.get("is_active")):
                    raise HTTPException(status_code=403, detail="user is disabled")
                _register_login_success(email, ip)
                token, expires_at = _issue_session(cur, str(row["id"]))
                return {
                    "ok": True,
                    "user": {"id": str(row["id"]), "email": str(row["email"])},
                    "token": token,
                    "expires_at": expires_at,
                }


@router.post("/api/auth/logout")
def logout(req: Request) -> Dict[str, Any]:
    _auth_origin_check(req)
    token = _parse_bearer_token(req)
    token_hash = _hash_token(token)
    with _connect_postgres() as conn:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE auth_sessions
                    SET revoked_at = now()
                    WHERE token_hash = %s AND revoked_at IS NULL
                    """,
                    (token_hash,),
                )
                changed = int(cur.rowcount or 0)
                return {"ok": True, "revoked": changed}


@router.get("/api/auth/me")
def auth_me(req: Request) -> Dict[str, Any]:
    user = _auth_user_from_token(req)
    return {"ok": True, "user": user}


@router.get("/api/credits/balance")
def credits_balance(req: Request) -> Dict[str, Any]:
    user = _auth_user_from_token(req)
    with _connect_postgres() as conn:
        with conn.cursor() as cur:
            balance = _current_balance(cur, user["id"])
            return {"ok": True, "user_id": user["id"], "balance": balance}


@router.get("/api/credits/ledger")
def credits_ledger(req: Request, limit: int = 50) -> Dict[str, Any]:
    user = _auth_user_from_token(req)
    limit = max(1, min(500, int(limit)))
    with _connect_postgres() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  id, entry_type, amount, balance_after, source_type, source_id,
                  idempotency_key, meta, created_at
                FROM credit_ledger
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (user["id"], limit),
            )
            rows = cur.fetchall() or []
            for row in rows:
                if row.get("created_at"):
                    row["created_at"] = row["created_at"].isoformat()
            return {"ok": True, "user_id": user["id"], "rows": rows}


@router.post("/api/billing/checkout-session")
def billing_checkout_session(req: Request, data: CheckoutSessionIn) -> Dict[str, Any]:
    user = _auth_user_from_token(req)
    if not (data.success_url.startswith("http://") or data.success_url.startswith("https://")):
        raise HTTPException(status_code=400, detail="success_url must be absolute")
    if not (data.cancel_url.startswith("http://") or data.cancel_url.startswith("https://")):
        raise HTTPException(status_code=400, detail="cancel_url must be absolute")

    try:
        import stripe
    except Exception as exc:
        raise HTTPException(status_code=500, detail="stripe package is not installed") from exc

    stripe.api_key = _require_env("STRIPE_SECRET_KEY")
    per_credit_cents = int((os.getenv("STRIPE_CREDIT_PRICE_CENTS") or "100").strip())
    if per_credit_cents < 1:
        raise HTTPException(status_code=500, detail="STRIPE_CREDIT_PRICE_CENTS must be >= 1")

    currency = (data.currency or "usd").strip().lower()
    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            success_url=data.success_url,
            cancel_url=data.cancel_url,
            client_reference_id=user["id"],
            metadata={"user_id": user["id"], "credits": str(data.credits)},
            line_items=[
                {
                    "price_data": {
                        "currency": currency,
                        "unit_amount": per_credit_cents,
                        "product_data": {"name": "DANIELOZA AI Credits"},
                    },
                    "quantity": data.credits,
                }
            ],
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"stripe checkout session failed: {exc}") from exc

    return {
        "ok": True,
        "checkout_session_id": str(session.get("id")),
        "url": str(session.get("url") or ""),
        "credits": data.credits,
        "amount_cents": per_credit_cents * data.credits,
        "currency": currency,
    }


@router.post("/api/billing/stripe/webhook")
async def stripe_webhook(req: Request) -> Dict[str, Any]:
    signature = (req.headers.get("stripe-signature") or "").strip()
    if not signature:
        raise HTTPException(status_code=400, detail="Missing Stripe-Signature header")

    payload = await req.body()
    event = _parse_stripe_event(payload, signature)
    req.state.stripe_event_id = str(event.get("id") or "")
    outcome = _process_event_in_tx(event)
    return {"ok": True, **outcome}


@router.post("/api/jobs")
def create_job_with_hold(req: Request, data: JobCreateIn) -> Dict[str, Any]:
    user = _auth_user_from_token(req)
    row = _create_job_with_credit_hold(user["id"], data)
    req.state.user_id = user["id"]
    req.state.job_id = str(row["id"])
    return {"ok": True, "job": row}


@router.get("/api/jobs")
def jobs_list(req: Request, limit: int = 50) -> Dict[str, Any]:
    user = _auth_user_from_token(req)
    limit = max(1, min(200, int(limit)))
    with _connect_postgres() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  id, status, provider, operation, attempt_count, max_attempts,
                  credits_cost, created_at, updated_at, started_at, finished_at,
                  last_error, result_json
                FROM jobs
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (user["id"], limit),
            )
            rows = cur.fetchall() or []
            for row in rows:
                for key in ("created_at", "updated_at", "started_at", "finished_at"):
                    if row.get(key):
                        row[key] = row[key].isoformat()
            return {"ok": True, "jobs": rows}


@router.get("/api/jobs/{job_id}")
def job_details(req: Request, job_id: str) -> Dict[str, Any]:
    user = _auth_user_from_token(req)
    with _connect_postgres() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  id, user_id, status, provider, operation, attempt_count, max_attempts,
                  credits_cost, input_json, result_json, last_error,
                  created_at, updated_at, started_at, finished_at
                FROM jobs
                WHERE id = %s AND user_id = %s
                LIMIT 1
                """,
                (job_id, user["id"]),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="job not found")
            cur.execute(
                """
                SELECT event_type, payload, created_at
                FROM job_events
                WHERE job_id = %s
                ORDER BY created_at ASC
                """,
                (job_id,),
            )
            events = cur.fetchall() or []
            for event in events:
                if event.get("created_at"):
                    event["created_at"] = event["created_at"].isoformat()
            for key in ("created_at", "updated_at", "started_at", "finished_at"):
                if row.get(key):
                    row[key] = row[key].isoformat()
            return {"ok": True, "job": row, "events": events}


@router.get("/api/ready")
def ready() -> Dict[str, Any]:
    db_ok = False
    db_error = None
    try:
        with _connect_postgres() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 AS ok")
                db_ok = bool(cur.fetchone())
    except Exception as exc:
        db_error = str(exc)
        db_ok = False

    last_heartbeat_raw = _WORKER_STATE.get("last_heartbeat")
    heartbeat_age_s = None
    if isinstance(last_heartbeat_raw, str):
        try:
            heartbeat_at = datetime.fromisoformat(last_heartbeat_raw.replace("Z", "+00:00"))
            heartbeat_age_s = max(0.0, (_now_utc() - heartbeat_at).total_seconds())
        except Exception:
            heartbeat_age_s = None
    worker_required = _worker_enabled()
    worker_ok = True
    if worker_required:
        worker_ok = heartbeat_age_s is not None and heartbeat_age_s <= 30.0

    return {
        "ok": bool(db_ok and worker_ok),
        "db_ok": db_ok,
        "db_error": db_error,
        "worker_required": worker_required,
        "worker_running": bool(_WORKER_STATE.get("running")),
        "worker_last_heartbeat": last_heartbeat_raw,
        "worker_heartbeat_age_s": heartbeat_age_s,
    }


@router.post("/api/ops/credits/adjust")
def ops_credit_adjust(req: Request, data: CreditAdjustmentIn) -> Dict[str, Any]:
    if not _admin_token_ok(req):
        raise HTTPException(status_code=401, detail="admin unauthorized")
    result = _apply_credit_adjustment(data)
    return {"ok": True, "result": result}


@router.get("/api/ops/metrics")
def ops_metrics(req: Request) -> Dict[str, Any]:
    if not _admin_token_ok(req):
        raise HTTPException(status_code=401, detail="admin unauthorized")

    with _connect_postgres() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT status, COUNT(*)::int AS n
                FROM jobs
                GROUP BY status
                """
            )
            by_status = {str(row["status"]): int(row["n"]) for row in (cur.fetchall() or [])}
            cur.execute(
                """
                SELECT COUNT(*)::int AS n
                FROM webhook_events
                WHERE status = 'failed' AND received_at >= (now() - INTERVAL '1 hour')
                """
            )
            webhook_failed_last_hour = int((cur.fetchone() or {}).get("n") or 0)
            cur.execute(
                """
                SELECT COUNT(*)::int AS n
                FROM jobs
                WHERE status = 'failed' AND finished_at >= (now() - INTERVAL '1 hour')
                """
            )
            jobs_failed_last_hour = int((cur.fetchone() or {}).get("n") or 0)
            cur.execute(
                """
                SELECT COUNT(*)::int AS n
                FROM job_dead_letters
                WHERE created_at >= (now() - INTERVAL '24 hours')
                """
            )
            dead_letters_last_24h = int((cur.fetchone() or {}).get("n") or 0)
            cur.execute(
                """
                SELECT percentile_cont(0.95)
                  WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (finished_at - started_at)))
                AS p95_seconds
                FROM jobs
                WHERE status IN ('succeeded', 'failed')
                  AND started_at IS NOT NULL
                  AND finished_at IS NOT NULL
                  AND finished_at >= (now() - INTERVAL '24 hours')
                """
            )
            p95_seconds = (cur.fetchone() or {}).get("p95_seconds")
            return {
                "ok": True,
                "queue_depth": {
                    "queued": int(by_status.get("queued", 0)),
                    "running": int(by_status.get("running", 0)),
                    "succeeded": int(by_status.get("succeeded", 0)),
                    "failed": int(by_status.get("failed", 0)),
                },
                "webhook_failed_last_hour": webhook_failed_last_hour,
                "jobs_failed_last_hour": jobs_failed_last_hour,
                "dead_letters_last_24h": dead_letters_last_24h,
                "job_duration_p95_seconds_24h": float(p95_seconds) if p95_seconds is not None else None,
                "worker": {
                    "running": bool(_WORKER_STATE.get("running")),
                    "last_heartbeat": _WORKER_STATE.get("last_heartbeat"),
                    "processed_total": int(_WORKER_STATE.get("processed_total") or 0),
                    "failures_total": int(_WORKER_STATE.get("failures_total") or 0),
                },
            }


@router.get("/api/ops/dead-letters")
def ops_dead_letters(req: Request, limit: int = 100) -> Dict[str, Any]:
    if not _admin_token_ok(req):
        raise HTTPException(status_code=401, detail="admin unauthorized")
    limit = max(1, min(1000, int(limit)))
    with _connect_postgres() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, job_id, user_id, reason, payload, created_at
                FROM job_dead_letters
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall() or []
            for row in rows:
                if row.get("created_at"):
                    row["created_at"] = row["created_at"].isoformat()
            return {"ok": True, "rows": rows}
