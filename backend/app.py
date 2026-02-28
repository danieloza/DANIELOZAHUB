import asyncio
import csv
import hashlib
import io
import json
import logging
import os
import re
import secrets
import smtplib
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta, date
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Dict, Optional, List, Tuple

from fastapi import FastAPI, HTTPException, UploadFile, File, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .mvp_billing import (
    router as mvp_billing_router,
    install_mvp_observability,
    init_mvp_sentry,
    start_mvp_worker,
    stop_mvp_worker,
)
from .db import (
    init_db,
    insert_job,
    get_job,
    list_jobs,
    insert_lead,
    insert_analytics_events,
    count_events_between,
    count_leads_between,
    count_form_submit_between,
    count_form_submit_by_form_between,
    count_leads_by_form_between,
    count_leads_by_status_between,
    list_leads_between,
    list_leads_for_backfill,
    list_recent_leads,
    top_events_between,
    list_recent_events,
    upsert_lead_meta,
    upsert_lead_value,
    upsert_lead_autopilot,
    upsert_lead_win_model,
    upsert_lead_enrichment,
    booking_target,
    confirm_lead_booking,
    touch_lead_action,
    get_lead_by_id,
    count_recent_leads_by_ip,
    list_analytics_events_between,
    leads_pending_touch,
    list_followup_templates,
    upsert_followup_template,
    list_followup_logs,
    list_due_followups,
    top_cta_labels_between,
    funnel_count_between,
    upsert_sequence_task,
    list_sequence_tasks_by_lead,
    list_due_sequence_tasks,
    mark_sequence_task_status,
    skip_pending_sequence_for_lead,
    sequence_progress_for_leads,
    upsert_channel_cost_daily,
    list_channel_costs_between,
    channel_costs_grouped_between,
    insert_budget_plan,
    insert_budget_plan_items,
    list_budget_plans,
    get_budget_plan,
    list_budget_plan_items,
    update_budget_plan_status,
    update_budget_plan_item_status,
    budget_plan_item,
    channel_cost_on_date,
    insert_budget_plan_cost_runs,
    list_budget_plan_cost_runs,
    unreverted_budget_plan_cost_runs,
    mark_budget_plan_runs_reverted,
    upsert_guardrail_incident,
    list_guardrail_incidents,
    update_guardrail_incident_status,
    create_incident_task,
    has_active_incident_task,
    list_incident_tasks,
    list_incident_task_audit,
    get_incident_task,
    mark_incident_task_sla_alert,
    update_incident_task_status,
    create_scenario_snapshot,
    list_scenario_snapshots,
    get_scenario_snapshot,
    delete_scenario_snapshot,
    list_execution_connectors,
    upsert_execution_connector,
    update_execution_connector_sync,
    create_approval,
    list_approvals,
    get_approval,
    update_approval_status,
    create_execution_run,
    finish_execution_run,
    list_execution_runs,
    create_experiment,
    update_experiment_status,
    list_experiments,
    get_experiment,
    upsert_experiment_arms,
    list_experiment_arms,
    insert_experiment_event,
    list_experiment_events,
    create_target_commit,
    close_other_target_commits,
    get_active_target_commit,
    upsert_target_daily_snapshot,
    list_target_daily_snapshots,
    insert_autonomous_run_log,
    list_autonomous_run_log,
)
from .worker import process_job


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _split_csv_env(name: str, fallback: str = "") -> List[str]:
    raw = (os.getenv(name) or fallback).strip()
    if not raw:
        return []
    out = []
    for part in raw.split(","):
        x = part.strip()
        if x:
            out.append(x.rstrip("/"))
    return out


def _env_bool(name: str, default: bool) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


CORS_ALLOW_ORIGINS = _split_csv_env("CORS_ALLOW_ORIGINS", "*")
PUBLIC_ORIGIN_ALLOWLIST = _split_csv_env("PUBLIC_ORIGIN_ALLOWLIST", "")
ALLOW_LOCALHOST_ORIGINS = _env_bool("ALLOW_LOCALHOST_ORIGINS", True)
ALLOW_NULL_ORIGIN = _env_bool("ALLOW_NULL_ORIGIN", True)

_origin_regex_parts: List[str] = []
if ALLOW_LOCALHOST_ORIGINS:
    _origin_regex_parts.append(r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$")
if ALLOW_NULL_ORIGIN:
    _origin_regex_parts.append(r"^null$")
CORS_ALLOW_ORIGIN_REGEX = "|".join(_origin_regex_parts) if _origin_regex_parts else None

app = FastAPI(title="DANIELOZA.AI Backend", version="0.3")
app.include_router(mvp_billing_router)
init_mvp_sentry()

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGINS or ["*"],
    allow_origin_regex=CORS_ALLOW_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
install_mvp_observability(app)

UPLOADS_DIR = Path("backend/uploads")
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")

REPO_ROOT = Path(__file__).resolve().parent.parent
SITE_ASSETS_DIR = REPO_ROOT / "assets"
SITE_APP_HTML = REPO_ROOT / "app.html"
if SITE_ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(SITE_ASSETS_DIR)), name="assets")


@app.get("/", include_in_schema=False)
def site_root() -> RedirectResponse:
    return RedirectResponse(url="/app.html", status_code=307)


@app.get("/app", include_in_schema=False)
def site_app_shortcut() -> RedirectResponse:
    return RedirectResponse(url="/app.html", status_code=307)


@app.get("/app.html", include_in_schema=False)
def site_app_panel() -> FileResponse:
    if not SITE_APP_HTML.exists():
        raise HTTPException(status_code=404, detail="app panel not found")
    return FileResponse(SITE_APP_HTML)

queue: "asyncio.Queue[Dict[str, Any]]" = asyncio.Queue()

RATE_LIMIT_MAX = 5
RATE_LIMIT_WINDOW = timedelta(hours=24)
_rate_jobs: Dict[str, List[datetime]] = {}

RATE_LIMIT_LEADS_MAX = 40
_rate_leads: Dict[str, List[datetime]] = {}

RATE_LIMIT_EVENTS_MAX = 3000
_rate_events: Dict[str, List[datetime]] = {}


def _env_flag(name: str, default: bool = True) -> bool:
    return _env_bool(name, default)


def _maybe_apply_postgres_migrations_on_startup() -> None:
    dsn = (os.getenv("DATABASE_URL") or "").strip().lower()
    if not dsn.startswith("postgres"):
        return
    if not _env_flag("MVP_STARTUP_AUTO_MIGRATE", True):
        return
    from .migrate_postgres import apply_migrations

    apply_migrations()


def client_ip(req: Request) -> str:
    xff = req.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return req.client.host if req.client else "unknown"


def rate_check(bucket: Dict[str, List[datetime]], ip: str, limit: int) -> None:
    now = datetime.now(timezone.utc)
    arr = bucket.get(ip, [])
    arr = [t for t in arr if (now - t) <= RATE_LIMIT_WINDOW]
    if len(arr) >= limit:
        raise HTTPException(status_code=429, detail=f"Rate limit: {limit}/24h dla IP {ip}")
    arr.append(now)
    bucket[ip] = arr


def parse_or_now(value: Optional[str]) -> str:
    if not value:
        return now_iso()
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value
    except Exception:
        return now_iso()


def parse_or_none(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value
    except Exception:
        return None


def normalize_lead_status(value: str) -> str:
    v = (value or "").strip().lower()
    if v not in {"new", "in_progress", "won", "lost"}:
        return "new"
    return v



def _lead_email_domain(email: str) -> str:
    x = (email or "").strip().lower()
    if "@" not in x:
        return ""
    return x.split("@", 1)[1]


def _booking_base_url() -> str:
    base = (os.getenv("BOOKING_PAGE_URL") or "").strip().rstrip("/")
    if base:
        return base
    return "http://127.0.0.1:5500/booking.html"


def _booking_link(lead_id: str, token: str) -> str:
    return f"{_booking_base_url()}?lead_id={lead_id}&token={token}"


def _detect_test_spam(data: "LeadIn", ip: str) -> Tuple[bool, bool, str]:
    payload = {"fields": data.fields or {}}
    email = _lead_email(payload).lower()
    email_domain = _lead_email_domain(email)

    test_domains = set(_split_csv_env(
        "LEAD_TEST_EMAIL_DOMAINS",
        "example.com,example.org,mailinator.com,tempmail.com,10minutemail.com,test.com",
    ))
    fake_words = [w for w in _split_csv_env("LEAD_FAKE_PATTERNS", "test,asdf,qwerty,lorem ipsum,123456") if w]

    fields_blob = " ".join(str(v or "") for v in (data.fields or {}).values()).lower()
    reasons: List[str] = []
    is_test = False
    is_spam = False

    if email_domain and email_domain in test_domains:
        is_test = True
        reasons.append(f"test_domain:{email_domain}")

    for w in fake_words:
        token = w.strip().lower()
        if token and token in fields_blob:
            is_test = True
            reasons.append(f"fake_pattern:{token}")
            break

    threshold = int((os.getenv("LEAD_IP_REPEAT_THRESHOLD") or "6").strip())
    since_24h = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    recent_ip = count_recent_leads_by_ip(ip, since_24h)
    if recent_ip >= threshold:
        is_spam = True
        reasons.append(f"repeat_ip:{recent_ip}")

    if (data.website or "").strip():
        is_spam = True
        reasons.append("honeypot")

    return is_test, is_spam, ";".join(reasons)
def _lead_email(payload: Dict[str, Any]) -> str:
    fields = payload.get("fields") if isinstance(payload, dict) else {}
    if not isinstance(fields, dict):
        return ""
    for key in ("email", "e-mail", "mail"):
        val = fields.get(key)
        if isinstance(val, str) and "@" in val:
            return val.strip()
    return ""


def _lead_score(form_type: str, payload: Dict[str, Any], lead_status: str) -> int:
    score = 0
    fields = payload.get("fields") if isinstance(payload, dict) else {}
    if not isinstance(fields, dict):
        fields = {}

    if _lead_email(payload):
        score += 30
    if isinstance(fields.get("telefon"), str) and fields.get("telefon", "").strip():
        score += 15
    if isinstance(fields.get("budzet"), str):
        b = fields.get("budzet", "").lower()
        if "2000" in b or "+" in b:
            score += 25
        elif "500-2000" in b or "500" in b:
            score += 15
    if isinstance(fields.get("cel"), str) and fields.get("cel", "").strip():
        score += 10
    if isinstance(fields.get("opis"), str) and len(fields.get("opis", "").strip()) >= 25:
        score += 10
    if form_type == "audyt":
        score += 10
    if lead_status == "in_progress":
        score += 10
    if lead_status == "won":
        score += 20
    return max(0, min(100, score))


def _lead_tier(score: int) -> str:
    if score >= 70:
        return "hot"
    if score >= 40:
        return "warm"
    return "cold"


def _autopilot_priority(score: int, lead_status: str, is_test: bool, is_spam: bool) -> str:
    if is_spam or is_test or lead_status in {"won", "lost"}:
        return "P3"
    if score >= 75:
        return "P1"
    if score >= 45:
        return "P2"
    return "P3"


def _autopilot_due_at(next_action: str) -> Optional[str]:
    now = datetime.now(timezone.utc)
    waits = {
        "call_now": timedelta(minutes=15),
        "send_intro_email": timedelta(minutes=45),
        "follow_up_today": timedelta(minutes=30),
        "enrich_contact": timedelta(hours=3),
        "await_reply": timedelta(hours=24),
    }
    wait = waits.get(next_action)
    if wait is None:
        return None
    return (now + wait).isoformat()


def _autopilot_decision(
    form_type: str,
    payload: Dict[str, Any],
    lead_status: str,
    is_test: bool,
    is_spam: bool,
    last_contact_at: Optional[str],
) -> Dict[str, Optional[str]]:
    score = _lead_score(form_type=form_type, payload=payload, lead_status=lead_status)
    priority = _autopilot_priority(score=score, lead_status=lead_status, is_test=is_test, is_spam=is_spam)
    owner_queue = "priority" if priority == "P1" else "sales"
    next_action = "review"

    fields = payload.get("fields") if isinstance(payload, dict) else {}
    if not isinstance(fields, dict):
        fields = {}
    has_email = bool(_lead_email(payload))
    has_phone = isinstance(fields.get("telefon"), str) and bool(fields.get("telefon", "").strip())
    touched = _safe_dt(str(last_contact_at or "")) is not None

    if is_spam:
        next_action = "drop_spam"
        owner_queue = "ops"
    elif is_test:
        next_action = "ignore_test"
        owner_queue = "ops"
    elif lead_status in {"won", "lost"}:
        next_action = "no_action"
    elif lead_status == "new":
        if has_phone:
            next_action = "call_now"
        elif has_email:
            next_action = "send_intro_email"
        else:
            next_action = "enrich_contact"
    elif lead_status == "in_progress":
        next_action = "await_reply" if touched else "follow_up_today"

    return {
        "priority": priority,
        "next_action": next_action,
        "next_action_due_at": _autopilot_due_at(next_action),
        "owner_queue": owner_queue,
    }


def _recompute_autopilot_for_row(row: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Optional[str]]:
    if not _autopilot_enabled():
        return {
            "priority": str(row.get("autopilot_priority") or "P3"),
            "next_action": str(row.get("autopilot_next_action") or "review"),
            "next_action_due_at": row.get("autopilot_next_action_due_at"),
            "owner_queue": str(row.get("autopilot_owner_queue") or "sales"),
        }
    decision = _autopilot_decision(
        form_type=str(row.get("form_type") or ""),
        payload=payload,
        lead_status=str(row.get("lead_status") or "new"),
        is_test=bool(int(row.get("is_test") or 0)),
        is_spam=bool(int(row.get("is_spam") or 0)),
        last_contact_at=row.get("last_contact_at"),
    )
    upsert_lead_autopilot(
        lead_id=str(row.get("id") or ""),
        priority=str(decision.get("priority") or "P3"),
        next_action=str(decision.get("next_action") or "review"),
        next_action_due_at=decision.get("next_action_due_at"),
        owner_queue=str(decision.get("owner_queue") or "sales"),
        updated_at=now_iso(),
    )
    return decision


WIN_MODEL_VERSION = "v1.0-ruleblend"


def _win_probability_to_recommendation(prob_pct: float) -> str:
    if prob_pct >= 65.0:
        return "push"
    if prob_pct >= 35.0:
        return "nurture"
    return "drop"


def _win_model_snapshot(days: int = 120, include_test: bool = False, include_spam: bool = False) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=max(7, min(365, int(days))))
    rows = list_leads_between(start.isoformat(), now.isoformat(), limit=9000, include_test=include_test, include_spam=include_spam)

    resolved = [r for r in rows if str(r.get("lead_status") or "") in {"won", "lost"}]
    total = len(resolved)
    won_total = sum(1 for r in resolved if str(r.get("lead_status") or "") == "won")
    base_rate = (won_total / total) if total > 0 else 0.24

    by_form: Dict[str, Dict[str, int]] = {}
    by_source: Dict[str, Dict[str, int]] = {}
    by_tier: Dict[str, Dict[str, int]] = {}

    for row in resolved:
        payload = {}
        try:
            payload = json.loads(row.get("payload_json") or "{}")
        except Exception:
            payload = {}
        st = str(row.get("lead_status") or "")
        won_inc = 1 if st == "won" else 0
        form_key = str(row.get("form_type") or "other").strip().lower() or "other"
        source_key = str(row.get("source_path") or payload.get("landing_path") or "(unknown)").strip().lower() or "(unknown)"
        score = _lead_score(form_key, payload, str(row.get("lead_status") or "new"))
        tier = _lead_tier(score)

        for bucket, key in ((by_form, form_key), (by_source, source_key), (by_tier, tier)):
            x = bucket.setdefault(key, {"won": 0, "total": 0})
            x["won"] += won_inc
            x["total"] += 1

    def _rates(src: Dict[str, Dict[str, int]]) -> Dict[str, Dict[str, float]]:
        out: Dict[str, Dict[str, float]] = {}
        for key, val in src.items():
            t = int(val.get("total", 0))
            w = int(val.get("won", 0))
            out[key] = {"win_rate": (w / t) if t > 0 else 0.0, "samples": float(t)}
        return out

    return {
        "model_version": WIN_MODEL_VERSION,
        "days": int(days),
        "resolved_total": total,
        "won_total": won_total,
        "base_win_rate": base_rate,
        "form_rates": _rates(by_form),
        "source_rates": _rates(by_source),
        "tier_rates": _rates(by_tier),
    }


def _blend_rate(base_rate: float, rate: float, samples: float, min_samples: float = 4.0) -> float:
    if samples <= 0:
        return base_rate
    w = max(0.0, min(1.0, samples / max(min_samples, 1.0)))
    return (base_rate * (1.0 - w)) + (rate * w)


def _predict_win_probability(
    row: Dict[str, Any],
    payload: Dict[str, Any],
    score: int,
    tier: str,
    model: Dict[str, Any],
) -> Dict[str, Any]:
    lead_status = str(row.get("lead_status") or "new")
    if lead_status == "won":
        return {"probability_pct": 100.0, "recommendation": "push", "reason": "already_won", "model_version": WIN_MODEL_VERSION}
    if lead_status == "lost":
        return {"probability_pct": 0.0, "recommendation": "drop", "reason": "already_lost", "model_version": WIN_MODEL_VERSION}

    base_rate = float(model.get("base_win_rate") or 0.24)
    p_rule = 0.08 + (float(score) / 100.0) * 0.72
    p_rule = max(0.03, min(0.95, p_rule))

    form_key = str(row.get("form_type") or "other").strip().lower() or "other"
    source_key = str(row.get("source_path") or payload.get("landing_path") or "(unknown)").strip().lower() or "(unknown)"

    form_stat = (model.get("form_rates") or {}).get(form_key, {})
    source_stat = (model.get("source_rates") or {}).get(source_key, {})
    tier_stat = (model.get("tier_rates") or {}).get(str(tier or "").lower(), {})

    p_form = _blend_rate(base_rate, float(form_stat.get("win_rate") or base_rate), float(form_stat.get("samples") or 0.0))
    p_source = _blend_rate(base_rate, float(source_stat.get("win_rate") or base_rate), float(source_stat.get("samples") or 0.0), min_samples=8.0)
    p_tier = _blend_rate(base_rate, float(tier_stat.get("win_rate") or base_rate), float(tier_stat.get("samples") or 0.0))

    probability = (0.50 * p_rule) + (0.20 * p_form) + (0.20 * p_source) + (0.10 * p_tier)

    if str(row.get("lead_status") or "") == "in_progress":
        probability += 0.06
    if row.get("booked_slot"):
        probability += 0.10

    probability = max(0.0, min(0.99, probability))
    prob_pct = round(probability * 100.0, 2)
    return {
        "probability_pct": prob_pct,
        "recommendation": _win_probability_to_recommendation(prob_pct),
        "reason": f"rule={round(p_rule*100,1)} form={round(p_form*100,1)} source={round(p_source*100,1)}",
        "model_version": str(model.get("model_version") or WIN_MODEL_VERSION),
    }


def _refresh_win_snapshot_for_row(row: Dict[str, Any], payload: Dict[str, Any], model: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if not _win_model_enabled():
        return {}
    win_model = model or _win_model_snapshot(days=120, include_test=True, include_spam=True)
    score = _lead_score(str(row.get("form_type") or ""), payload, str(row.get("lead_status") or "new"))
    tier = _lead_tier(score)
    pred = _predict_win_probability(row=row, payload=payload, score=score, tier=tier, model=win_model)
    upsert_lead_win_model(
        lead_id=str(row.get("id") or ""),
        win_probability=float(pred.get("probability_pct") or 0.0),
        win_recommendation=str(pred.get("recommendation") or "nurture"),
        win_model_version=str(pred.get("model_version") or WIN_MODEL_VERSION),
        updated_at=now_iso(),
    )
    return pred


def _lead_channel(row: Dict[str, Any], payload: Dict[str, Any]) -> str:
    utm_source = str(payload.get("utm_source") or "").strip().lower()
    if utm_source:
        return utm_source
    src = str(row.get("source_path") or payload.get("landing_path") or "").strip().lower()
    if not src:
        return "unknown"
    if "google" in src or "ads" in src:
        return "google_ads"
    if "facebook" in src or "meta" in src or "instagram" in src:
        return "meta_ads"
    if "linkedin" in src:
        return "linkedin"
    if "kontakt" in src or "audyt" in src or "oferta" in src:
        return "organic_site"
    return "unknown"


def _build_roi_report(days: int, include_test: bool, include_spam: bool) -> Dict[str, Any]:
    now_dt = datetime.now(timezone.utc)
    start_dt = now_dt - timedelta(days=days)
    s_now = now_dt.isoformat()
    s_start = start_dt.isoformat()
    start_date = start_dt.date().isoformat()
    end_date = now_dt.date().isoformat()

    leads = list_leads_between(s_start, s_now, limit=12000, include_test=include_test, include_spam=include_spam)
    costs_by_channel = {
        str(x.get("channel") or "").strip().lower(): float(x.get("total_cost") or 0.0)
        for x in channel_costs_grouped_between(start_date, end_date)
    }

    stats: Dict[str, Dict[str, Any]] = {}
    for row in leads:
        payload = {}
        try:
            payload = json.loads(row.get("payload_json") or "{}")
        except Exception:
            payload = {}
        ch = _lead_channel(row, payload)
        st = stats.setdefault(ch, {"channel": ch, "leads": 0, "won": 0, "lost": 0, "revenue": 0.0})
        st["leads"] += 1
        lead_status = str(row.get("lead_status") or "new")
        if lead_status == "won":
            st["won"] += 1
            st["revenue"] += float(row.get("deal_value") or 0.0)
        elif lead_status == "lost":
            st["lost"] += 1

    rows: List[Dict[str, Any]] = []
    for ch, st in stats.items():
        revenue = float(st.get("revenue") or 0.0)
        cost = float(costs_by_channel.get(ch, 0.0))
        won = int(st.get("won") or 0)
        cac = round(cost / won, 2) if won > 0 else None
        roi_pct = round(((revenue - cost) / cost) * 100.0, 2) if cost > 0 else None
        payback = round((revenue / cost), 2) if cost > 0 else None
        rows.append(
            {
                "channel": ch,
                "leads": int(st.get("leads") or 0),
                "won": won,
                "lost": int(st.get("lost") or 0),
                "revenue": round(revenue, 2),
                "cost": round(cost, 2),
                "cac": cac,
                "roi_pct": roi_pct,
                "payback_ratio": payback,
            }
        )

    # Include cost channels with no leads for visibility.
    for ch, cost in costs_by_channel.items():
        if any(r["channel"] == ch for r in rows):
            continue
        rows.append(
            {
                "channel": ch,
                "leads": 0,
                "won": 0,
                "lost": 0,
                "revenue": 0.0,
                "cost": round(float(cost), 2),
                "cac": None,
                "roi_pct": -100.0 if cost > 0 else None,
                "payback_ratio": 0.0 if cost > 0 else None,
            }
        )

    rows.sort(key=lambda x: (x.get("revenue", 0.0) - x.get("cost", 0.0), x.get("won", 0), x.get("leads", 0)), reverse=True)
    return {
        "generated_at": s_now,
        "days": days,
        "filters": {"include_test": include_test, "include_spam": include_spam},
        "totals": {
            "leads": sum(int(r.get("leads") or 0) for r in rows),
            "won": sum(int(r.get("won") or 0) for r in rows),
            "lost": sum(int(r.get("lost") or 0) for r in rows),
            "revenue": round(sum(float(r.get("revenue") or 0.0) for r in rows), 2),
            "cost": round(sum(float(r.get("cost") or 0.0) for r in rows), 2),
        },
        "rows": rows,
    }


def _build_budget_recommendations(
    days: int,
    include_test: bool,
    include_spam: bool,
    spend_change_pct: float = 20.0,
) -> Dict[str, Any]:
    roi_report = _build_roi_report(days=days, include_test=include_test, include_spam=include_spam)
    rows = roi_report.get("rows") or []
    change = max(1.0, min(80.0, float(spend_change_pct)))
    factor = change / 100.0

    out_rows: List[Dict[str, Any]] = []
    for row in rows:
        channel = str(row.get("channel") or "")
        leads = int(row.get("leads") or 0)
        won = int(row.get("won") or 0)
        revenue = float(row.get("revenue") or 0.0)
        cost = float(row.get("cost") or 0.0)
        payback = row.get("payback_ratio")
        roi_pct = row.get("roi_pct")
        win_rate = (won / leads) if leads > 0 else 0.0

        action = "hold"
        reason = "insufficient_data"
        if cost <= 0 and won > 0:
            action = "scale"
            reason = "wins_without_cost_tracked"
        elif cost > 0:
            if (payback is not None and float(payback) >= 2.0) or (roi_pct is not None and float(roi_pct) >= 100.0):
                action = "scale"
                reason = "high_payback"
            elif (payback is not None and float(payback) < 1.0) or (roi_pct is not None and float(roi_pct) < 0.0):
                action = "cut"
                reason = "negative_roi"
            else:
                action = "hold"
                reason = "near_break_even"

        spend_delta = 0.0
        if action == "scale":
            spend_delta = cost * factor
        elif action == "cut":
            spend_delta = -cost * factor

        # Keep estimate simple and conservative: revenue moves proportionally to spend using payback.
        payback_ratio = float(payback) if payback is not None else (revenue / cost if cost > 0 else 0.0)
        est_revenue_delta = spend_delta * payback_ratio
        est_profit_delta = est_revenue_delta - spend_delta

        out_rows.append(
            {
                "channel": channel,
                "action": action,
                "reason": reason,
                "win_rate_pct": round(win_rate * 100.0, 2),
                "payback_ratio": None if payback is None else float(payback),
                "roi_pct": None if roi_pct is None else float(roi_pct),
                "current": {
                    "leads": leads,
                    "won": won,
                    "revenue": round(revenue, 2),
                    "cost": round(cost, 2),
                },
                "simulation": {
                    "spend_change_pct": change if action != "hold" else 0.0,
                    "spend_delta": round(spend_delta, 2),
                    "estimated_revenue_delta": round(est_revenue_delta, 2),
                    "estimated_profit_delta": round(est_profit_delta, 2),
                },
            }
        )

    out_rows.sort(
        key=lambda x: (
            2 if x["action"] == "scale" else (1 if x["action"] == "hold" else 0),
            x["simulation"]["estimated_profit_delta"],
        ),
        reverse=True,
    )
    return {
        "generated_at": roi_report.get("generated_at"),
        "days": days,
        "spend_change_pct": change,
        "filters": {"include_test": include_test, "include_spam": include_spam},
        "totals": roi_report.get("totals") or {},
        "rows": out_rows,
    }


def _build_forecast_report(
    history_days: int,
    horizon_days: int,
    target_revenue: float,
    budget_change_pct: float,
    conv_uplift_pct: float,
    include_test: bool,
    include_spam: bool,
) -> Dict[str, Any]:
    history_days = max(14, min(365, int(history_days)))
    horizon_days = max(7, min(365, int(horizon_days)))
    target_revenue = max(0.0, float(target_revenue))
    budget_factor = 1.0 + (max(-80.0, min(300.0, float(budget_change_pct))) / 100.0)
    conv_uplift = max(-80.0, min(300.0, float(conv_uplift_pct))) / 100.0

    now_dt = datetime.now(timezone.utc)
    hist_start = now_dt - timedelta(days=history_days)
    s_now = now_dt.isoformat()
    s_hist = hist_start.isoformat()
    start_date = hist_start.date().isoformat()
    end_date = now_dt.date().isoformat()

    leads = list_leads_between(s_hist, s_now, limit=20000, include_test=include_test, include_spam=include_spam)
    costs = {
        str(x.get("channel") or "").strip().lower(): float(x.get("total_cost") or 0.0)
        for x in channel_costs_grouped_between(start_date, end_date)
    }

    global_won_revenue = 0.0
    global_won_count = 0
    channel_stats: Dict[str, Dict[str, Any]] = {}
    for row in leads:
        payload = {}
        try:
            payload = json.loads(row.get("payload_json") or "{}")
        except Exception:
            payload = {}
        ch = _lead_channel(row, payload)
        st = channel_stats.setdefault(ch, {"leads": 0, "won": 0, "lost": 0, "won_revenue": 0.0})
        st["leads"] += 1
        status = str(row.get("lead_status") or "new")
        if status == "won":
            st["won"] += 1
            deal = float(row.get("deal_value") or 0.0)
            st["won_revenue"] += deal
            global_won_revenue += deal
            global_won_count += 1
        elif status == "lost":
            st["lost"] += 1

    global_avg_deal = (global_won_revenue / global_won_count) if global_won_count > 0 else 5000.0
    rows: List[Dict[str, Any]] = []
    forecast_revenue_total = 0.0
    forecast_cost_total = 0.0
    forecast_wins_total = 0.0

    for channel, st in channel_stats.items():
        leads_n = int(st.get("leads") or 0)
        won_n = int(st.get("won") or 0)
        lost_n = int(st.get("lost") or 0)
        resolved = won_n + lost_n
        win_rate = (won_n + 1.0) / (resolved + 2.0) if resolved >= 0 else 0.2
        win_rate = max(0.01, min(0.95, win_rate * (1.0 + conv_uplift)))

        avg_deal = float(st.get("won_revenue") or 0.0) / won_n if won_n > 0 else global_avg_deal
        leads_per_day = leads_n / float(history_days)
        # Conservative spend elasticity: +10% spend ~= +5.5% lead volume
        leads_scale = max(0.1, 1.0 + 0.55 * (budget_factor - 1.0))
        expected_leads = leads_per_day * float(horizon_days) * leads_scale
        expected_wins = expected_leads * win_rate
        expected_revenue = expected_wins * avg_deal

        hist_cost = float(costs.get(channel, 0.0))
        cost_per_day = hist_cost / float(history_days) if history_days > 0 else 0.0
        expected_cost = cost_per_day * float(horizon_days) * budget_factor
        expected_profit = expected_revenue - expected_cost
        payback = (expected_revenue / expected_cost) if expected_cost > 0 else None

        forecast_revenue_total += expected_revenue
        forecast_cost_total += expected_cost
        forecast_wins_total += expected_wins

        rows.append(
            {
                "channel": channel,
                "history": {
                    "leads": leads_n,
                    "won": won_n,
                    "lost": lost_n,
                    "win_rate_pct": round((won_n / resolved) * 100.0, 2) if resolved > 0 else None,
                    "avg_deal": round(avg_deal, 2),
                    "cost_total": round(hist_cost, 2),
                },
                "forecast": {
                    "leads": round(expected_leads, 2),
                    "wins": round(expected_wins, 2),
                    "revenue": round(expected_revenue, 2),
                    "cost": round(expected_cost, 2),
                    "profit": round(expected_profit, 2),
                    "payback_ratio": None if payback is None else round(payback, 2),
                },
                "drivers": {
                    "budget_factor": round(budget_factor, 4),
                    "conv_uplift_pct": round(conv_uplift * 100.0, 2),
                    "smoothed_win_rate_pct": round(win_rate * 100.0, 2),
                },
            }
        )

    rows.sort(key=lambda x: (float((x.get("forecast") or {}).get("profit") or 0.0), float((x.get("forecast") or {}).get("revenue") or 0.0)), reverse=True)

    gap = max(0.0, target_revenue - forecast_revenue_total)
    target_plan: List[Dict[str, Any]] = []
    if gap > 0 and rows:
        scored = []
        for r in rows:
            f = r.get("forecast") or {}
            revenue = float(f.get("revenue") or 0.0)
            cost = float(f.get("cost") or 0.0)
            score = (revenue / cost) if cost > 0 else (revenue / 1.0)
            scored.append((score, r))
        scored.sort(key=lambda x: x[0], reverse=True)
        remaining = gap
        for score, r in scored[:6]:
            channel = str(r.get("channel") or "")
            f = r.get("forecast") or {}
            revenue = float(f.get("revenue") or 0.0)
            cost = float(f.get("cost") or 0.0)
            payback = (revenue / cost) if cost > 0 else 0.0
            if payback <= 0:
                continue
            allocate_revenue = min(remaining, gap * 0.4)
            add_cost = allocate_revenue / payback if payback > 0 else 0.0
            target_plan.append(
                {
                    "channel": channel,
                    "additional_revenue_needed": round(allocate_revenue, 2),
                    "estimated_additional_cost": round(add_cost, 2),
                    "assumed_payback": round(payback, 2),
                }
            )
            remaining -= allocate_revenue
            if remaining <= 0:
                break

    return {
        "generated_at": s_now,
        "history_days": history_days,
        "horizon_days": horizon_days,
        "scenario": {
            "target_revenue": round(target_revenue, 2),
            "budget_change_pct": round((budget_factor - 1.0) * 100.0, 2),
            "conv_uplift_pct": round(conv_uplift * 100.0, 2),
        },
        "totals": {
            "forecast_revenue": round(forecast_revenue_total, 2),
            "forecast_cost": round(forecast_cost_total, 2),
            "forecast_profit": round(forecast_revenue_total - forecast_cost_total, 2),
            "forecast_wins": round(forecast_wins_total, 2),
            "target_gap": round(gap, 2),
        },
        "target_plan": target_plan,
        "rows": rows,
    }


def _guardrail_fingerprint(incident_type: str, channel: str, title: str) -> str:
    src = f"{incident_type}|{channel}|{title}".lower().strip()
    return hashlib.sha1(src.encode("utf-8")).hexdigest()[:24]


def _build_guardrail_findings(days: int = 30, include_test: bool = False, include_spam: bool = False) -> List[Dict[str, Any]]:
    days = max(14, min(365, int(days)))
    now_dt = datetime.now(timezone.utc)
    curr_start = now_dt - timedelta(days=days)
    prev_start = curr_start - timedelta(days=days)
    s_now = now_dt.isoformat()
    s_curr = curr_start.isoformat()
    s_prev = prev_start.isoformat()

    curr_rows = list_leads_between(s_curr, s_now, limit=16000, include_test=include_test, include_spam=include_spam)
    prev_rows = list_leads_between(s_prev, s_curr, limit=16000, include_test=include_test, include_spam=include_spam)

    def _counts(rows: List[Dict[str, Any]]) -> Dict[str, float]:
        leads_n = float(len(rows))
        won_n = float(sum(1 for x in rows if str(x.get("lead_status") or "") == "won"))
        resolved_n = float(sum(1 for x in rows if str(x.get("lead_status") or "") in {"won", "lost"}))
        revenue_n = float(sum(float(x.get("deal_value") or 0.0) for x in rows if str(x.get("lead_status") or "") == "won"))
        win_rate = (won_n / resolved_n) if resolved_n > 0 else 0.0
        return {"leads": leads_n, "won": won_n, "resolved": resolved_n, "revenue": revenue_n, "win_rate": win_rate}

    c = _counts(curr_rows)
    p = _counts(prev_rows)
    findings: List[Dict[str, Any]] = []

    def _drop_pct(curr: float, prev: float) -> float:
        if prev <= 0:
            return 0.0
        return ((prev - curr) / prev) * 100.0

    leads_drop = _drop_pct(c["leads"], p["leads"])
    if p["leads"] >= 10 and leads_drop >= 30.0:
        findings.append(
            {
                "severity": "critical" if leads_drop >= 45 else "high",
                "incident_type": "lead_drop",
                "channel": "",
                "title": f"Lead volume drop {round(leads_drop,1)}% vs previous window",
                "details": {"current_leads": int(c["leads"]), "previous_leads": int(p["leads"]), "drop_pct": round(leads_drop, 2), "days": days},
            }
        )

    if p["resolved"] >= 8:
        win_drop = _drop_pct(c["win_rate"], p["win_rate"])
        if win_drop >= 20.0:
            findings.append(
                {
                    "severity": "high" if win_drop >= 35 else "medium",
                    "incident_type": "win_rate_drop",
                    "channel": "",
                    "title": f"Win-rate drop {round(win_drop,1)}% vs previous window",
                    "details": {"current_win_rate_pct": round(c["win_rate"] * 100.0, 2), "previous_win_rate_pct": round(p["win_rate"] * 100.0, 2), "drop_pct": round(win_drop, 2), "days": days},
                }
            )

    roi = _build_roi_report(days=days, include_test=include_test, include_spam=include_spam)
    for row in (roi.get("rows") or []):
        channel = str(row.get("channel") or "")
        cost = float(row.get("cost") or 0.0)
        won = int(row.get("won") or 0)
        roi_pct = row.get("roi_pct")
        if cost >= 1000.0 and won == 0:
            findings.append(
                {
                    "severity": "high",
                    "incident_type": "spend_no_wins",
                    "channel": channel,
                    "title": f"{channel}: spend without wins",
                    "details": {"cost": round(cost, 2), "won": won, "days": days},
                }
            )
        elif roi_pct is not None and float(roi_pct) < -20.0 and cost > 0:
            findings.append(
                {
                    "severity": "medium",
                    "incident_type": "negative_roi",
                    "channel": channel,
                    "title": f"{channel}: negative ROI {round(float(roi_pct),1)}%",
                    "details": {"roi_pct": round(float(roi_pct), 2), "cost": round(cost, 2), "revenue": round(float(row.get('revenue') or 0.0), 2), "days": days},
                }
            )

    return findings


def _safe_pct_delta(curr: float, prev: float) -> Optional[float]:
    if prev == 0:
        return None
    return round(((curr - prev) / prev) * 100.0, 2)


def _incident_default_tasks(incident: Dict[str, Any], now_dt: datetime) -> List[Dict[str, Any]]:
    incident_type = str(incident.get("incident_type") or "")
    severity = str(incident.get("severity") or "medium").lower()
    channel = str(incident.get("channel") or "")
    delay_h = 4 if severity in {"critical", "high"} else 12
    priority = "P1" if severity in {"critical", "high"} else "P2"
    due = (now_dt + timedelta(hours=delay_h)).isoformat()

    tasks: List[Dict[str, Any]] = []
    if incident_type == "lead_drop":
        tasks.append(
            {
                "owner": "growth",
                "priority": priority,
                "action_type": "audit_top_funnel",
                "title": "Audit top-of-funnel tracking and landing pages",
                "due_at": due,
            }
        )
        tasks.append(
            {
                "owner": "sales",
                "priority": priority,
                "action_type": "reactivate_recent_leads",
                "title": "Reactivate stalled leads from last 14 days",
                "due_at": due,
            }
        )
    elif incident_type == "win_rate_drop":
        tasks.append(
            {
                "owner": "sales",
                "priority": priority,
                "action_type": "review_lost_reasons",
                "title": "Review lost reasons and update objection playbook",
                "due_at": due,
            }
        )
    elif incident_type in {"spend_no_wins", "negative_roi"}:
        tasks.append(
            {
                "owner": "growth",
                "priority": priority,
                "action_type": "budget_reallocation",
                "title": f"Reallocate budget for {channel or 'channel'}",
                "due_at": due,
            }
        )
        tasks.append(
            {
                "owner": "sales",
                "priority": priority,
                "action_type": "quality_check_channel",
                "title": f"Quality check leads from {channel or 'channel'}",
                "due_at": due,
            }
        )
    else:
        tasks.append(
            {
                "owner": "ops",
                "priority": "P2",
                "action_type": "incident_triage",
                "title": "Triage incident and assign owner",
                "due_at": due,
            }
        )
    return tasks


def _sync_incident_tasks_from_open_incidents(limit: int = 120) -> int:
    incidents = list_guardrail_incidents(status="open", limit=limit)
    now_dt = datetime.now(timezone.utc)
    ts = now_iso()
    created = 0
    for inc in incidents:
        inc_id = int(inc.get("id") or 0)
        if inc_id <= 0:
            continue
        payload = {
            "incident_type": inc.get("incident_type"),
            "severity": inc.get("severity"),
            "channel": inc.get("channel"),
            "title": inc.get("title"),
        }
        for t in _incident_default_tasks(inc, now_dt=now_dt):
            action_type = str(t.get("action_type") or "")
            if not action_type:
                continue
            if has_active_incident_task(incident_id=inc_id, action_type=action_type):
                continue
            task_id = create_incident_task(
                incident_id=inc_id,
                due_at=str(t.get("due_at") or ts),
                owner=str(t.get("owner") or "ops"),
                priority=str(t.get("priority") or "P2"),
                title=str(t.get("title") or "incident task"),
                action_type=action_type,
                payload_json=json.dumps(payload, ensure_ascii=False),
                now_iso=ts,
            )
            if task_id > 0:
                created += 1
    return created


def _build_ops_review_report(
    days: int,
    target_revenue: float,
    include_test: bool,
    include_spam: bool,
) -> Dict[str, Any]:
    days = max(3, min(60, int(days)))
    target_revenue = max(0.0, float(target_revenue))
    now_dt = datetime.now(timezone.utc)
    curr_start = now_dt - timedelta(days=days)
    prev_start = curr_start - timedelta(days=days)
    s_now = now_dt.isoformat()
    s_curr = curr_start.isoformat()
    s_prev = prev_start.isoformat()

    kpi_curr = {
        "events": float(count_events_between(s_curr, s_now)),
        "form_submit": float(count_form_submit_between(s_curr, s_now)),
        "leads": float(count_leads_between(s_curr, s_now)),
    }
    kpi_prev = {
        "events": float(count_events_between(s_prev, s_curr)),
        "form_submit": float(count_form_submit_between(s_prev, s_curr)),
        "leads": float(count_leads_between(s_prev, s_curr)),
    }
    conv_curr = (kpi_curr["leads"] / kpi_curr["form_submit"] * 100.0) if kpi_curr["form_submit"] > 0 else 0.0
    conv_prev = (kpi_prev["leads"] / kpi_prev["form_submit"] * 100.0) if kpi_prev["form_submit"] > 0 else 0.0

    roi_curr = _build_roi_report(days=days, include_test=include_test, include_spam=include_spam)
    roi_prev = _build_roi_report(days=days * 2, include_test=include_test, include_spam=include_spam)
    # previous window proxy: take totals from 2x window minus current not available directly; keep simple with 2x signal.
    roi_tot_curr = roi_curr.get("totals") or {}
    roi_tot_prev = roi_prev.get("totals") or {}

    incidents_open = list_guardrail_incidents(status="open", limit=500)
    incidents_ack = list_guardrail_incidents(status="ack", limit=500)
    tasks_pending = list_incident_tasks(status="pending", limit=500)
    tasks_in_progress = list_incident_tasks(status="in_progress", limit=500)
    tasks_done = list_incident_tasks(status="done", limit=500)

    plans = list_budget_plans(limit=20)
    latest_plan = plans[0] if plans else None
    latest_plan_items = list_budget_plan_items(plan_id=int(latest_plan["id"])) if latest_plan else []
    latest_plan_totals = {
        "items": len(latest_plan_items),
        "applied": sum(1 for x in latest_plan_items if str(x.get("status") or "") == "applied"),
        "pending": sum(1 for x in latest_plan_items if str(x.get("status") or "") == "pending"),
        "skipped": sum(1 for x in latest_plan_items if str(x.get("status") or "") == "skipped"),
    }

    forecast = _build_forecast_report(
        history_days=max(30, days * 4),
        horizon_days=days * 2,
        target_revenue=target_revenue,
        budget_change_pct=0.0,
        conv_uplift_pct=0.0,
        include_test=include_test,
        include_spam=include_spam,
    )
    f_tot = forecast.get("totals") or {}

    priorities: List[Dict[str, Any]] = []
    if len(incidents_open) > 0:
        priorities.append({"priority": "P1", "title": f"{len(incidents_open)} open incidents require owner action"})
    if len(tasks_pending) > 0:
        priorities.append({"priority": "P1", "title": f"{len(tasks_pending)} pending incident tasks require execution"})
    gap = float(f_tot.get("target_gap") or 0.0)
    if gap > 0:
        priorities.append({"priority": "P1", "title": f"Revenue gap to target: {round(gap, 2)}"})
    if len(priorities) == 0:
        priorities.append({"priority": "P2", "title": "No critical blockers detected. Keep execution cadence."})

    return {
        "generated_at": s_now,
        "days": days,
        "window_current": {"from": s_curr, "to": s_now},
        "window_previous": {"from": s_prev, "to": s_curr},
        "kpi": {
            "current": {
                "events": int(kpi_curr["events"]),
                "form_submit": int(kpi_curr["form_submit"]),
                "leads": int(kpi_curr["leads"]),
                "conversion_pct": round(conv_curr, 2),
            },
            "previous": {
                "events": int(kpi_prev["events"]),
                "form_submit": int(kpi_prev["form_submit"]),
                "leads": int(kpi_prev["leads"]),
                "conversion_pct": round(conv_prev, 2),
            },
            "delta_pct": {
                "events": _safe_pct_delta(kpi_curr["events"], kpi_prev["events"]),
                "form_submit": _safe_pct_delta(kpi_curr["form_submit"], kpi_prev["form_submit"]),
                "leads": _safe_pct_delta(kpi_curr["leads"], kpi_prev["leads"]),
                "conversion_pct": _safe_pct_delta(conv_curr, conv_prev),
            },
        },
        "roi": {
            "current": roi_tot_curr,
            "reference": roi_tot_prev,
        },
        "incident_health": {
            "open": len(incidents_open),
            "ack": len(incidents_ack),
            "tasks_pending": len(tasks_pending),
            "tasks_in_progress": len(tasks_in_progress),
            "tasks_done": len(tasks_done),
        },
        "budget_plan": {
            "latest_plan": latest_plan,
            "latest_plan_totals": latest_plan_totals,
        },
        "forecast": {
            "target_revenue": target_revenue,
            "forecast_revenue": float(f_tot.get("forecast_revenue") or 0.0),
            "forecast_profit": float(f_tot.get("forecast_profit") or 0.0),
            "target_gap": float(f_tot.get("target_gap") or 0.0),
        },
        "top_priorities": priorities[:8],
    }


def _parse_date_ymd(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return float(numerator) / float(denominator)


def _connector_env_prefix(channel: str) -> str:
    raw = (channel or "").strip().upper()
    out = []
    for ch in raw:
        if ch.isalnum():
            out.append(ch)
        else:
            out.append("_")
    return "".join(out)


def _connector_apply_url(channel: str) -> str:
    prefix = _connector_env_prefix(channel)
    configured = (
        (os.getenv(f"AUTONOMOUS_{prefix}_APPLY_URL") or "").strip()
        or (os.getenv("AUTONOMOUS_CONNECTOR_DEFAULT_APPLY_URL") or "").strip()
    )
    if configured:
        return configured
    channel_norm = (channel or "").strip().lower() or "unknown"
    return f"http://127.0.0.1:8000/api/connectors/mock/apply/{channel_norm}"


def _connector_health_url(channel: str) -> str:
    prefix = _connector_env_prefix(channel)
    configured = (
        (os.getenv(f"AUTONOMOUS_{prefix}_HEALTH_URL") or "").strip()
        or (os.getenv("AUTONOMOUS_CONNECTOR_DEFAULT_HEALTH_URL") or "").strip()
    )
    if configured:
        return configured
    channel_norm = (channel or "").strip().lower() or "unknown"
    return f"http://127.0.0.1:8000/api/connectors/mock/health/{channel_norm}"


def _connector_token(channel: str) -> str:
    prefix = _connector_env_prefix(channel)
    return (
        (os.getenv(f"AUTONOMOUS_{prefix}_TOKEN") or "").strip()
        or (os.getenv("AUTONOMOUS_CONNECTOR_DEFAULT_TOKEN") or "").strip()
    )


def _internal_connector_token() -> str:
    return (os.getenv("AUTONOMOUS_INTERNAL_CONNECTOR_TOKEN") or "").strip()


def _internal_connector_auth_ok(req: Request) -> bool:
    expected = _internal_connector_token()
    if not expected:
        return True
    auth = (req.headers.get("authorization") or "").strip()
    if auth.lower().startswith("bearer ") and auth[7:].strip() == expected:
        return True
    token = (req.headers.get("x-connector-token") or "").strip()
    return token == expected


def _http_json_post(url: str, payload: Dict[str, Any], token: str, timeout_sec: float = 15.0) -> Dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url=url, method="POST", data=body)
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw else {}
        except Exception:
            parsed = {"raw": raw}
        return {
            "http_status": int(getattr(resp, "status", 200)),
            "body": parsed,
        }


def _http_json_get(url: str, token: str, timeout_sec: float = 8.0) -> Dict[str, Any]:
    req = urllib.request.Request(url=url, method="GET")
    req.add_header("Accept", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw else {}
        except Exception:
            parsed = {"raw": raw}
        return {
            "http_status": int(getattr(resp, "status", 200)),
            "body": parsed,
        }


def _connector_execute_budget_change(
    connector: Dict[str, Any],
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    channel = str(connector.get("channel") or "")
    mode = str(connector.get("mode") or "simulate").strip().lower()
    provider = str(connector.get("provider") or "simulator").strip().lower()
    if mode == "simulate":
        return {
            "ok": True,
            "mode": "simulate",
            "provider": provider,
            "channel": channel,
            "result": {"status": "simulated", "payload": payload},
        }

    url = _connector_apply_url(channel)
    if not url:
        return {
            "ok": False,
            "mode": "live",
            "provider": provider,
            "channel": channel,
            "error": "missing_apply_url_env",
        }
    token = _connector_token(channel)
    try:
        resp = _http_json_post(url=url, payload=payload, token=token, timeout_sec=20.0)
        return {
            "ok": True,
            "mode": "live",
            "provider": provider,
            "channel": channel,
            "result": resp,
        }
    except urllib.error.HTTPError as e:
        raw = ""
        try:
            raw = e.read().decode("utf-8", errors="replace")
        except Exception:
            raw = str(e)
        return {
            "ok": False,
            "mode": "live",
            "provider": provider,
            "channel": channel,
            "error": "http_error",
            "http_status": int(getattr(e, "code", 0)),
            "response_raw": raw[:2000],
        }
    except Exception as e:
        return {
            "ok": False,
            "mode": "live",
            "provider": provider,
            "channel": channel,
            "error": f"request_failed:{str(e)}",
        }


def _connector_health_ping(connector: Dict[str, Any]) -> Dict[str, Any]:
    channel = str(connector.get("channel") or "")
    mode = str(connector.get("mode") or "simulate").strip().lower()
    if mode == "simulate":
        return {"ok": True, "mode": mode, "note": "simulate connector"}
    url = _connector_health_url(channel)
    if not url:
        return {"ok": False, "mode": mode, "error": "missing_health_url_env"}
    token = _connector_token(channel)
    try:
        resp = _http_json_get(url=url, token=token, timeout_sec=10.0)
        return {"ok": True, "mode": mode, "result": resp}
    except urllib.error.HTTPError as e:
        raw = ""
        try:
            raw = e.read().decode("utf-8", errors="replace")
        except Exception:
            raw = str(e)
        return {"ok": False, "mode": mode, "error": "http_error", "http_status": int(getattr(e, "code", 0)), "response_raw": raw[:2000]}
    except Exception as e:
        return {"ok": False, "mode": mode, "error": f"request_failed:{str(e)}"}


def _pick_experiment_arm(experiment_id: int, session_id: str) -> Optional[Dict[str, Any]]:
    exp = get_experiment(experiment_id)
    if not exp or str(exp.get("status") or "") != "running":
        return None
    arms = list_experiment_arms(experiment_id=experiment_id)
    if not arms:
        return None

    allocation_mode = str(exp.get("allocation_mode") or "equal").lower()
    if allocation_mode == "equal":
        key_src = f"{experiment_id}:{session_id}"
        idx = int(hashlib.sha256(key_src.encode("utf-8")).hexdigest(), 16) % len(arms)
        return arms[idx]

    # Simple win-rate exploitation fallback with smoothing.
    events = list_experiment_events(experiment_id=experiment_id, limit=6000)
    by_arm: Dict[str, Dict[str, float]] = {}
    for a in arms:
        by_arm[str(a.get("arm_key") or "")] = {"exposure": 0.0, "wins": 0.0}
    for ev in events:
        arm_key = str(ev.get("arm_key") or "")
        event_type = str(ev.get("event_type") or "")
        value = float(ev.get("value") or 0.0)
        if arm_key not in by_arm:
            continue
        if event_type == "exposure":
            by_arm[arm_key]["exposure"] += value if value > 0 else 1.0
        elif event_type in {"win", "conversion"}:
            by_arm[arm_key]["wins"] += value if value > 0 else 1.0

    def _score(arm_key: str) -> float:
        st = by_arm.get(arm_key) or {"exposure": 0.0, "wins": 0.0}
        exp_n = float(st.get("exposure") or 0.0)
        win_n = float(st.get("wins") or 0.0)
        base = (win_n + 1.0) / (exp_n + 2.0)
        return base + (1.0 / (exp_n + 1.0))

    arms_sorted = sorted(arms, key=lambda x: _score(str(x.get("arm_key") or "")), reverse=True)
    if not arms_sorted:
        return arms[0]
    return arms_sorted[0]


def _target_commit_snapshot(include_test: bool, include_spam: bool) -> Optional[Dict[str, Any]]:
    commit = get_active_target_commit()
    if not commit:
        return None

    period_start = str(commit.get("period_start") or "")
    period_end = str(commit.get("period_end") or "")
    target_revenue = float(commit.get("target_revenue") or 0.0)
    if not period_start or not period_end:
        return None

    d_start = _parse_date_ymd(period_start)
    d_end = _parse_date_ymd(period_end)
    if d_end < d_start:
        return None

    today = datetime.now(timezone.utc).date()
    clipped_today = min(max(today, d_start), d_end)
    period_days = max(1, (d_end - d_start).days + 1)
    elapsed_days = max(0, (clipped_today - d_start).days + 1)
    elapsed_ratio = min(1.0, max(0.0, _safe_ratio(elapsed_days, period_days)))

    rows = list_leads_between(
        start_iso=f"{period_start}T00:00:00+00:00",
        end_iso=f"{(clipped_today + timedelta(days=1)).isoformat()}T00:00:00+00:00",
        limit=15000,
        include_test=include_test,
        include_spam=include_spam,
    )
    actual_revenue = 0.0
    won_count = 0
    for row in rows:
        if str(row.get("lead_status") or "") == "won":
            won_count += 1
            actual_revenue += float(row.get("deal_value") or 0.0)

    expected_revenue = round(target_revenue * elapsed_ratio, 2)
    gap = round(expected_revenue - actual_revenue, 2)
    gap_target_ratio = _safe_ratio(gap, target_revenue) if target_revenue > 0 else 0.0
    risk_level = "low"
    if gap_target_ratio >= 0.30:
        risk_level = "critical"
    elif gap_target_ratio >= 0.15:
        risk_level = "high"
    elif gap_target_ratio > 0:
        risk_level = "medium"

    recommendations: List[Dict[str, Any]] = []
    if gap > 0:
        alloc = _build_budget_recommendations(days=30, include_test=include_test, include_spam=include_spam, spend_change_pct=20)
        for x in (alloc.get("rows") or []):
            if str(x.get("action") or "") != "scale":
                continue
            recommendations.append(
                {
                    "type": "scale_channel",
                    "channel": x.get("channel"),
                    "estimated_profit_delta": x.get("estimated_profit_delta"),
                    "reason": x.get("reason"),
                }
            )
            if len(recommendations) >= 3:
                break
        if len(recommendations) < 3:
            backlog = leads_pending_touch(limit=120)
            p1 = sum(1 for x in backlog if str(x.get("autopilot_priority") or "") == "P1")
            recommendations.append(
                {
                    "type": "sales_push",
                    "p1_backlog": p1,
                    "action": "clear_p1_due_today",
                }
            )

    snapshot = {
        "commit": commit,
        "today": clipped_today.isoformat(),
        "period_days": period_days,
        "elapsed_days": elapsed_days,
        "elapsed_ratio": round(elapsed_ratio, 4),
        "target_revenue": round(target_revenue, 2),
        "actual_revenue": round(actual_revenue, 2),
        "expected_revenue": expected_revenue,
        "gap": gap,
        "risk_level": risk_level,
        "won_count": won_count,
        "recommendations": recommendations,
    }
    return snapshot


def _autonomous_daily_run(include_test: bool, include_spam: bool) -> Dict[str, Any]:
    now_value = now_iso()
    guardrail_findings = _build_guardrail_findings(days=30, include_test=include_test, include_spam=include_spam)
    incident_saved = 0
    for f in guardrail_findings:
        fp = _guardrail_fingerprint(
            incident_type=str(f.get("incident_type") or ""),
            channel=str(f.get("channel") or ""),
            title=str(f.get("title") or ""),
        )
        x = upsert_guardrail_incident(
            fingerprint=fp,
            severity=str(f.get("severity") or "medium"),
            incident_type=str(f.get("incident_type") or ""),
            channel=str(f.get("channel") or ""),
            title=str(f.get("title") or ""),
            details_json=json.dumps(f.get("details") or {}, ensure_ascii=False),
            now_iso=now_value,
        )
        if x > 0:
            incident_saved += 1

    task_created = _sync_incident_tasks_from_open_incidents(limit=200)
    target_snapshot = _target_commit_snapshot(include_test=include_test, include_spam=include_spam)
    if target_snapshot:
        commit_id = int((target_snapshot.get("commit") or {}).get("id") or 0)
        if commit_id > 0:
            upsert_target_daily_snapshot(
                commit_id=commit_id,
                day_iso=str(target_snapshot.get("today") or ""),
                actual_revenue=float(target_snapshot.get("actual_revenue") or 0.0),
                expected_revenue=float(target_snapshot.get("expected_revenue") or 0.0),
                gap=float(target_snapshot.get("gap") or 0.0),
                risk_level=str(target_snapshot.get("risk_level") or "low"),
                recommendations_json=json.dumps(target_snapshot.get("recommendations") or [], ensure_ascii=False),
                created_at=now_value,
            )

    summary = {
        "guardrail_findings": len(guardrail_findings),
        "incidents_upserted": incident_saved,
        "incident_tasks_created": task_created,
        "target_snapshot": target_snapshot,
    }
    insert_autonomous_run_log(run_type="daily", status="ok", summary_json=json.dumps(summary, ensure_ascii=False), created_at=now_value)
    return summary


SEQUENCE_STEPS: List[Tuple[str, int, str]] = [
    ("d0_contact", 0, "D0 telefon/mail"),
    ("d1_followup", 24, "D1 follow-up"),
    ("d3_reminder", 72, "D3 przypomnienie"),
    ("d7_close_loop", 168, "D7 zamkniecie"),
]


def _sequence_anchor_dt(created_at: Optional[str]) -> datetime:
    dt = _safe_dt(str(created_at or ""))
    if dt is None:
        return datetime.now(timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _sequence_ensure_for_lead(
    lead_id: str,
    created_at: Optional[str],
    lead_status: str,
    is_test: bool,
    is_spam: bool,
) -> None:
    if not lead_id:
        return
    now_value = now_iso()
    if is_test or is_spam:
        return
    anchor = _sequence_anchor_dt(created_at)
    for step_code, offset_h, label in SEQUENCE_STEPS:
        due_at = (anchor + timedelta(hours=offset_h)).isoformat()
        upsert_sequence_task(
            lead_id=lead_id,
            step_code=step_code,
            due_at=due_at,
            updated_at=now_value,
            status="pending",
            note=label,
        )
    if lead_status in {"won", "lost"}:
        skip_pending_sequence_for_lead(lead_id=lead_id, updated_at=now_value, note=f"lead_{lead_status}")


def _sequence_step_codes() -> set:
    return {x[0] for x in SEQUENCE_STEPS}


def _sequence_mark_action_progress(lead_id: str, action: str, timestamp_iso: str) -> None:
    mapping = {
        "call_now": "d0_contact",
        "send_intro_email": "d0_contact",
        "follow_up_today": "d1_followup",
        "await_reply": "d1_followup",
    }
    step_code = mapping.get((action or "").strip().lower())
    if not step_code:
        return
    mark_sequence_task_status(
        lead_id=lead_id,
        step_code=step_code,
        status="done",
        done_at=timestamp_iso,
        updated_at=timestamp_iso,
        note=f"action:{action}",
    )


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _feature_enabled(name: str, default: bool = True) -> bool:
    return _env_bool(name, default)


def _autopilot_enabled() -> bool:
    return _feature_enabled("AUTOPILOT_ENABLED", True)


def _win_model_enabled() -> bool:
    return _feature_enabled("WIN_MODEL_ENABLED", True)


def _roi_enabled() -> bool:
    return _feature_enabled("ROI_ENABLED", True)


def _set_feature_flags(flags: Dict[str, bool], persist: bool = True) -> None:
    for key, value in flags.items():
        os.environ[key] = "true" if bool(value) else "false"
    if not persist:
        return
    env_path = Path(__file__).resolve().parent / ".env"
    lines: List[str] = []
    if env_path.exists():
        try:
            lines = env_path.read_text(encoding="utf-8").splitlines()
        except Exception:
            lines = []
    for key, value in flags.items():
        wanted = f"{key}={'true' if bool(value) else 'false'}"
        replaced = False
        for idx, ln in enumerate(lines):
            if ln.strip().startswith(f"{key}="):
                lines[idx] = wanted
                replaced = True
                break
        if not replaced:
            lines.append(wanted)
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_DIGIT_RE = re.compile(r"\d")
_LOST_REASON_CATALOG: List[Dict[str, str]] = [
    {"code": "budget_too_low", "label": "Budzet za niski"},
    {"code": "no_response", "label": "Brak odpowiedzi"},
    {"code": "not_ready_timing", "label": "Zly timing / nie teraz"},
    {"code": "chose_competitor", "label": "Wybral konkurencje"},
    {"code": "no_decision_maker", "label": "Brak decydenta"},
    {"code": "scope_mismatch", "label": "Niedopasowany zakres"},
    {"code": "low_lead_quality", "label": "Niska jakosc leada"},
    {"code": "invalid_contact", "label": "Bledny kontakt"},
    {"code": "duplicate_lead", "label": "Duplikat"},
    {"code": "test_or_spam", "label": "Test lub spam"},
    {"code": "other", "label": "Inny powod"},
]
_LOST_REASON_ALIASES: Dict[str, str] = {
    "budget too low": "budget_too_low",
    "za drogo": "budget_too_low",
    "brak budzetu": "budget_too_low",
    "no response": "no_response",
    "brak odpowiedzi": "no_response",
    "ghosting": "no_response",
    "not now": "not_ready_timing",
    "nie teraz": "not_ready_timing",
    "timing": "not_ready_timing",
    "competitor": "chose_competitor",
    "konkurencja": "chose_competitor",
    "decydent": "no_decision_maker",
    "scope mismatch": "scope_mismatch",
    "zakres": "scope_mismatch",
    "slaby lead": "low_lead_quality",
    "low quality": "low_lead_quality",
    "invalid contact": "invalid_contact",
    "zly kontakt": "invalid_contact",
    "duplikat": "duplicate_lead",
    "duplicate": "duplicate_lead",
    "spam": "test_or_spam",
    "test": "test_or_spam",
}


def _safe_str(value: Any, max_len: int = 500) -> str:
    return str(value or "").strip()[:max_len]


def _lost_reason_norm_key(value: str) -> str:
    x = _safe_str(value, 200).lower()
    x = re.sub(r"[_\-]+", " ", x)
    x = re.sub(r"\s+", " ", x).strip()
    return x


def _normalize_lost_reason(value: str) -> str:
    raw = _safe_str(value, 200).replace("\n", " ").replace("\r", " ").strip()
    if not raw:
        return ""
    key = _lost_reason_norm_key(raw)
    allowed = {x["code"] for x in _LOST_REASON_CATALOG}
    if key in allowed:
        return key
    if key in _LOST_REASON_ALIASES:
        return _LOST_REASON_ALIASES[key]
    for alias, code in _LOST_REASON_ALIASES.items():
        if alias in key:
            return code
    return "other"


def _validate_lead_hygiene(data: "LeadIn") -> None:
    fields = data.fields or {}
    email = _safe_str(fields.get("email") or fields.get("e-mail") or fields.get("mail"), 200).lower()
    phone = _safe_str(fields.get("telefon") or fields.get("phone"), 120)
    budget = _safe_str(fields.get("budzet") or fields.get("budget"), 200)
    scope = _safe_str(fields.get("zakres") or fields.get("scope") or fields.get("cel") or fields.get("problem") or fields.get("opis"), 1000)
    form_type = _safe_str(data.form_type, 40).lower()

    errors: List[str] = []
    if not email or not _EMAIL_RE.match(email):
        errors.append("email")
    if form_type == "kontakt":
        digits = len(_PHONE_DIGIT_RE.findall(phone))
        if digits < 7:
            errors.append("telefon")
        if not budget:
            errors.append("budzet")
        if not scope:
            errors.append("zakres")
    else:
        if not scope:
            errors.append("zakres")

    if errors:
        raise HTTPException(status_code=400, detail=f"missing/invalid required fields: {', '.join(sorted(set(errors)))}")


def _origin_from_request(req: Request) -> str:
    return (req.headers.get("origin") or "").strip().rstrip("/")


def _is_origin_allowed(req: Request) -> bool:
    if not PUBLIC_ORIGIN_ALLOWLIST:
        return True
    origin = _origin_from_request(req)
    if not origin:
        return True
    if origin in PUBLIC_ORIGIN_ALLOWLIST:
        return True
    if ALLOW_LOCALHOST_ORIGINS and (origin.startswith("http://127.0.0.1") or origin.startswith("http://localhost")):
        return True
    if ALLOW_NULL_ORIGIN and origin == "null":
        return True
    return False


def _require_admin(req: Request, token: Optional[str] = None) -> None:
    expected = (os.getenv("ADMIN_TOKEN") or "").strip()
    if not expected:
        return

    auth = (req.headers.get("authorization") or "").strip()
    bearer = ""
    if auth.lower().startswith("bearer "):
        bearer = auth[7:].strip()

    header_token = (req.headers.get("x-admin-token") or "").strip()
    if token == expected or bearer == expected or header_token == expected:
        return
    raise HTTPException(status_code=403, detail="forbidden")


def _admin_actor(req: Request, actor_hint: str = "") -> str:
    actor = (actor_hint or req.headers.get("x-admin-actor") or "").strip()
    if not actor:
        raise HTTPException(status_code=400, detail="x-admin-actor (or actor field) is required")
    return actor[:120]


def _smtp_send(subject: str, body: str, to_email: str) -> None:
    host = (os.getenv("SMTP_HOST") or "").strip()
    port = int((os.getenv("SMTP_PORT") or "587").strip())
    user = (os.getenv("SMTP_USER") or "").strip()
    password = (os.getenv("SMTP_PASS") or "").strip()
    from_email = (os.getenv("SMTP_FROM") or user).strip()

    if not host or not from_email or not to_email:
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


def _slack_send(text: str) -> None:
    webhook = (os.getenv("OPS_SLACK_WEBHOOK_URL") or "").strip()
    if not webhook:
        return
    payload = json.dumps({"text": text}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        webhook,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=8):
            pass
    except Exception:
        return


def _format_fields(fields: Dict[str, Any]) -> str:
    rows = []
    for k, v in fields.items():
        if v is None:
            continue
        rows.append(f"- {k}: {v}")
    return "\n".join(rows) if rows else "- brak pĂłl"


def _send_lead_emails(lead_id: str, data: "LeadIn", ip: str, booking_link: str = "") -> None:
    notify_to = (os.getenv("LEAD_NOTIFY_TO") or "").strip()
    autoreply_enabled = _env_bool("LEAD_AUTOREPLY_ENABLED", True)

    fields_txt = _format_fields(data.fields)
    booking_line = f"Link self-booking: {booking_link}\n" if booking_link else ""
    notify_subject = f"[Lead] {data.form_type} - {lead_id}"
    notify_body = (
        f"Nowy lead: {lead_id}\n"
        f"Typ formularza: {data.form_type}\n"
        f"Source path: {data.source_path}\n"
        f"IP: {ip}\n"
        f"Session: {data.session_id or '-'}\n"
        f"Consent: {data.consent_state or '-'}\n"
        f"UTM: {data.utm_source or '-'} / {data.utm_medium or '-'} / {data.utm_campaign or '-'}\n"
        f"Referrer: {data.referrer or '-'}\n"
        f"{booking_line}\n"
        f"Pola:\n{fields_txt}\n"
    )

    if notify_to:
        _smtp_send(notify_subject, notify_body, notify_to)

    if not autoreply_enabled:
        return

    email_candidate = ""
    for key in ("email", "e-mail", "mail"):
        val = data.fields.get(key)
        if isinstance(val, str) and "@" in val:
            email_candidate = val.strip()
            break

    if not email_candidate:
        return

    auto_subject = "DANIELOZA.AI - potwierdzenie otrzymania briefu"
    auto_body = (
        "Czesc,\n\n"
        "dzieki za wiadomosc. Otrzymalem brief i wroce z odpowiedzia najszybciej, jak to mozliwe.\n"
        "Jesli chcesz, mozesz od razu wybrac termin rozmowy:\n"
        f"{booking_link}\n\n"
        "Pozdrawiam,\n"
        "DANIELOZA.AI\n"
    )
    _smtp_send(auto_subject, auto_body, email_candidate)


class CreateJobIn(BaseModel):
    model: str = Field(default="Kling 01")
    mode: str = Field(default="video")
    prompt: str = Field(min_length=1, max_length=4000)
    ar: str = Field(default="1:1")
    res: str = Field(default="1080p")
    dur: str = Field(default="10s")
    image_url: Optional[str] = None


class LeadIn(BaseModel):
    form_type: str = Field(min_length=2, max_length=40)
    fields: Dict[str, Any] = Field(default_factory=dict)
    source_path: str = Field(default="")
    session_id: Optional[str] = Field(default=None, max_length=120)
    consent_state: Optional[str] = Field(default="unknown", max_length=40)
    utm_source: Optional[str] = Field(default=None, max_length=120)
    utm_medium: Optional[str] = Field(default=None, max_length=120)
    utm_campaign: Optional[str] = Field(default=None, max_length=160)
    utm_term: Optional[str] = Field(default=None, max_length=160)
    utm_content: Optional[str] = Field(default=None, max_length=160)
    referrer: Optional[str] = Field(default=None, max_length=300)
    landing_path: Optional[str] = Field(default=None, max_length=240)
    website: Optional[str] = Field(default="", max_length=200)  # honeypot


class AnalyticsEventIn(BaseModel):
    event_name: str = Field(min_length=2, max_length=80)
    label: Optional[str] = Field(default=None, max_length=200)
    path: Optional[str] = Field(default=None, max_length=240)
    href: Optional[str] = Field(default=None, max_length=500)
    session_id: Optional[str] = Field(default=None, max_length=120)
    consent_state: Optional[str] = Field(default="unknown", max_length=40)
    created_at: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)


class AnalyticsBatchIn(BaseModel):
    events: List[AnalyticsEventIn] = Field(min_length=1, max_length=50)


class LeadMetaUpdateIn(BaseModel):
    status: str = Field(default="new", max_length=30)
    notes: str = Field(default="", max_length=8000)
    follow_up_at: Optional[str] = Field(default=None, max_length=40)
    lost_reason: str = Field(default="", max_length=200)


class FollowupTemplateIn(BaseModel):
    subject_template: str = Field(min_length=3, max_length=300)
    body_template: str = Field(min_length=3, max_length=12000)


class FollowupPostponeIn(BaseModel):
    hours: int = Field(ge=1, le=24 * 30)


class BookingConfirmIn(BaseModel):
    token: str = Field(min_length=8, max_length=200)
    booked_slot: str = Field(min_length=8, max_length=80)


class CockpitActionIn(BaseModel):
    action: str = Field(min_length=3, max_length=40)
    lost_reason: str = Field(default="", max_length=200)


class AutopilotExecuteIn(BaseModel):
    action: Optional[str] = Field(default=None, max_length=60)


class SequenceTaskDoneIn(BaseModel):
    note: str = Field(default="", max_length=300)


class SequenceTaskPostponeIn(BaseModel):
    hours: int = Field(ge=1, le=24 * 14)


class LeadValueIn(BaseModel):
    deal_value: float = Field(ge=0, le=1_000_000_000)


class ChannelCostIn(BaseModel):
    date_iso: str = Field(min_length=10, max_length=10)
    channel: str = Field(min_length=2, max_length=120)
    cost: float = Field(ge=0, le=1_000_000_000)


class ChannelCostCsvImportIn(BaseModel):
    csv_text: str = Field(min_length=10, max_length=2_000_000)


class LeadsBackfillIn(BaseModel):
    limit: int = Field(default=5000, ge=1, le=50_000)
    include_test: bool = False
    include_spam: bool = False
    refresh_autopilot: bool = True
    refresh_win: bool = True


class FeatureFlagsUpdateIn(BaseModel):
    AUTOPILOT_ENABLED: bool = True
    WIN_MODEL_ENABLED: bool = True
    ROI_ENABLED: bool = True
    persist: bool = True


class BudgetPlanCreateIn(BaseModel):
    days: int = Field(default=30, ge=7, le=365)
    spend_change_pct: float = Field(default=20, ge=1, le=80)
    note: str = Field(default="", max_length=400)


class BudgetPlanItemStatusIn(BaseModel):
    status: str = Field(min_length=4, max_length=20)


class BudgetPlanApplyIn(BaseModel):
    start_date: Optional[str] = Field(default=None, max_length=10)
    days: int = Field(default=7, ge=1, le=60)


class GuardrailIncidentStatusIn(BaseModel):
    status: str = Field(min_length=3, max_length=20)


class IncidentTaskStatusIn(BaseModel):
    status: str = Field(min_length=4, max_length=20)
    owner: str = Field(default="", max_length=80)
    priority: str = Field(default="", max_length=4)
    actor: str = Field(default="admin", max_length=120)
    reason: str = Field(default="", max_length=300)
    expected_updated_at: str = Field(default="", max_length=40)


class IncidentTaskBatchItemIn(BaseModel):
    task_id: int = Field(ge=1)
    expected_updated_at: str = Field(default="", max_length=40)


class IncidentTaskBatchIn(BaseModel):
    items: List[IncidentTaskBatchItemIn] = Field(default_factory=list)
    actor: str = Field(default="admin", max_length=120)
    reason: str = Field(default="", max_length=300)


class ScenarioSnapshotCreateIn(BaseModel):
    name: str = Field(min_length=3, max_length=140)
    days: int = Field(default=30, ge=7, le=365)
    history_days: int = Field(default=60, ge=14, le=365)
    horizon_days: int = Field(default=30, ge=7, le=365)
    target_revenue: float = Field(default=0, ge=0, le=1_000_000_000)
    budget_change_pct: float = Field(default=0, ge=-80, le=300)
    conv_uplift_pct: float = Field(default=0, ge=-80, le=300)
    spend_change_pct: float = Field(default=20, ge=1, le=80)
    include_test: bool = False
    include_spam: bool = False


class ConnectorUpsertIn(BaseModel):
    channel: str = Field(min_length=2, max_length=120)
    provider: str = Field(default="simulator", min_length=2, max_length=60)
    mode: str = Field(default="simulate", min_length=2, max_length=20)
    status: str = Field(default="enabled", min_length=2, max_length=20)
    daily_change_limit_pct: float = Field(default=20, ge=1, le=200)


class ApprovalDecisionIn(BaseModel):
    decision: str = Field(min_length=4, max_length=20)
    note: str = Field(default="", max_length=400)
    decided_by: str = Field(default="admin", max_length=80)


class PlanSubmitForApprovalIn(BaseModel):
    threshold_abs_delta_cost: float = Field(default=500, ge=0, le=1_000_000_000)
    requested_by: str = Field(default="ops", max_length=80)
    note: str = Field(default="", max_length=400)


class ExperimentArmIn(BaseModel):
    arm_key: str = Field(min_length=1, max_length=60)
    label: str = Field(min_length=1, max_length=140)
    weight: float = Field(default=1, ge=0.01, le=1000)
    config: Dict[str, Any] = Field(default_factory=dict)


class ExperimentCreateIn(BaseModel):
    name: str = Field(min_length=3, max_length=180)
    scope: str = Field(default="landing", min_length=2, max_length=80)
    metric_primary: str = Field(default="win_rate", min_length=2, max_length=80)
    allocation_mode: str = Field(default="equal", min_length=2, max_length=40)
    arms: List[ExperimentArmIn] = Field(min_length=2, max_length=12)


class ExperimentStatusIn(BaseModel):
    status: str = Field(min_length=4, max_length=20)


class ExperimentAssignIn(BaseModel):
    session_id: str = Field(min_length=2, max_length=120)


class ExperimentEventIn(BaseModel):
    arm_key: str = Field(min_length=1, max_length=60)
    event_type: str = Field(min_length=2, max_length=60)
    value: float = Field(default=1, ge=0, le=1_000_000_000)
    session_id: str = Field(default="", max_length=120)
    lead_id: str = Field(default="", max_length=120)


class TargetCommitCreateIn(BaseModel):
    period_start: str = Field(min_length=10, max_length=10)
    period_end: str = Field(min_length=10, max_length=10)
    target_revenue: float = Field(ge=0, le=1_000_000_000)
    owner: str = Field(default="ops", max_length=80)


@app.on_event("startup")
async def startup() -> None:
    init_db()
    try:
        _maybe_apply_postgres_migrations_on_startup()
    except Exception:
        logging.exception("startup postgres migrations failed")
        raise
    if _env_flag("LEGACY_QUEUE_WORKER_ENABLED", True):
        asyncio.create_task(worker_loop())
    start_mvp_worker()


@app.on_event("shutdown")
async def shutdown() -> None:
    await stop_mvp_worker()


async def worker_loop() -> None:
    while True:
        item = await queue.get()
        job_id = item["id"]
        payload = item["payload"]
        try:
            await process_job(job_id, payload)
        finally:
            queue.task_done()


@app.get("/api/health")
def health() -> Dict[str, Any]:
    return {"ok": True, "version": "0.3"}


@app.get("/api/connectors/mock/health/{channel}")
def connector_mock_health(req: Request, channel: str) -> Dict[str, Any]:
    if not _internal_connector_auth_ok(req):
        raise HTTPException(status_code=401, detail="connector unauthorized")
    return {
        "ok": True,
        "channel": (channel or "").strip().lower(),
        "provider": "mock",
        "mode": "live",
        "checked_at": now_iso(),
    }


@app.post("/api/connectors/mock/apply/{channel}")
def connector_mock_apply(req: Request, channel: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    if not _internal_connector_auth_ok(req):
        raise HTTPException(status_code=401, detail="connector unauthorized")

    channel_norm = (channel or "").strip().lower()
    current_cost = float(payload.get("current_cost") or 0.0)
    proposed_cost = float(payload.get("proposed_cost") or 0.0)
    apply_days = int(payload.get("apply_days") or 0)
    if apply_days < 1 or apply_days > 90:
        raise HTTPException(status_code=400, detail="apply_days out of range")

    delta_cost = proposed_cost - current_cost
    delta_pct = 100.0 if current_cost <= 0 and proposed_cost > 0 else (_safe_ratio(delta_cost, current_cost) * 100.0 if current_cost > 0 else 0.0)
    return {
        "ok": True,
        "channel": channel_norm,
        "provider": "mock",
        "execution_id": f"mock-{secrets.token_hex(6)}",
        "accepted": True,
        "summary": {
            "current_cost": round(current_cost, 2),
            "proposed_cost": round(proposed_cost, 2),
            "delta_cost": round(delta_cost, 2),
            "delta_pct": round(delta_pct, 2),
            "apply_days": apply_days,
        },
        "received_at": now_iso(),
    }


@app.post("/api/kling/upload")
async def upload_image(file: UploadFile = File(...)) -> Dict[str, Any]:
    from pathlib import Path

    ext = (Path(file.filename).suffix or "").lower()
    if ext not in [".png", ".jpg", ".jpeg", ".webp"]:
        raise HTTPException(status_code=400, detail="Dozwolone: png/jpg/jpeg/webp")

    name = "UPL-" + secrets.token_hex(6) + ext
    out_path = Path("backend/uploads") / name

    data = await file.read()
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Max 8MB")

    with open(out_path, "wb") as f:
        f.write(data)

    return {
        "ok": True,
        "filename": name,
        "url": f"http://127.0.0.1:8000/uploads/{name}",
    }


@app.post("/api/kling/jobs", deprecated=True)
async def create_job(req: Request, data: CreateJobIn) -> Dict[str, Any]:
    ip = client_ip(req)
    rate_check(_rate_jobs, ip, RATE_LIMIT_MAX)

    job_id = "JOB-" + secrets.token_hex(3).upper()
    payload = data.model_dump()
    payload["client_ip"] = ip
    payload_json = json.dumps(payload, ensure_ascii=False)

    insert_job(job_id, "queued", payload_json, now_iso())
    await queue.put({"id": job_id, "payload": payload})

    return {"id": job_id, "status": "queued", "payload": payload}


@app.get("/api/kling/jobs/{job_id}", deprecated=True)
def read_job(job_id: str) -> Dict[str, Any]:
    row = get_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")

    payload = json.loads(row["payload_json"])
    result = json.loads(row["result_json"]) if row["result_json"] else None

    return {
        "id": row["id"],
        "status": row["status"],
        "payload": payload,
        "result": result,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


@app.get("/api/kling/jobs", deprecated=True)
def jobs(limit: int = 30) -> List[Dict[str, Any]]:
    rows = list_jobs(limit=limit)
    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "id": r["id"],
                "status": r["status"],
                "payload": json.loads(r["payload_json"]),
                "result": json.loads(r["result_json"]) if r["result_json"] else None,
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
            }
        )
    return out


@app.post("/api/leads")
def create_lead(req: Request, data: LeadIn, bg: BackgroundTasks) -> Dict[str, Any]:
    if not _is_origin_allowed(req):
        raise HTTPException(status_code=403, detail="origin not allowed")
    ip = client_ip(req)
    rate_check(_rate_leads, ip, RATE_LIMIT_LEADS_MAX)
    _validate_lead_hygiene(data)

    lead_id = "LEAD-" + secrets.token_hex(4).upper()
    booking_token = secrets.token_urlsafe(16)
    created_at = now_iso()
    ua = req.headers.get("user-agent", "")[:300]
    payload_json = json.dumps(data.model_dump(exclude={"website"}), ensure_ascii=False)

    is_test, is_spam, spam_reason = _detect_test_spam(data, ip)

    insert_lead(
        lead_id=lead_id,
        form_type=data.form_type,
        payload_json=payload_json,
        source_path=(data.source_path or "")[:240],
        ip=ip,
        user_agent=ua,
        created_at=created_at,
    )

    upsert_lead_enrichment(
        lead_id=lead_id,
        booking_token=booking_token,
        is_test=is_test,
        is_spam=is_spam,
        spam_reason=spam_reason,
        updated_at=created_at,
    )

    if _autopilot_enabled():
        _recompute_autopilot_for_row(
            {
                "id": lead_id,
                "form_type": data.form_type,
                "lead_status": "new",
                "is_test": 1 if is_test else 0,
                "is_spam": 1 if is_spam else 0,
                "last_contact_at": None,
            },
            payload=data.model_dump(exclude={"website"}),
        )
    _refresh_win_snapshot_for_row(
        {
            "id": lead_id,
            "form_type": data.form_type,
            "lead_status": "new",
            "is_test": 1 if is_test else 0,
            "is_spam": 1 if is_spam else 0,
            "source_path": data.source_path or "",
        },
        payload=data.model_dump(exclude={"website"}),
    )
    _sequence_ensure_for_lead(
        lead_id=lead_id,
        created_at=created_at,
        lead_status="new",
        is_test=is_test,
        is_spam=is_spam,
    )

    # For honeypot submissions keep accepted=False, but store row as spam for KPI hygiene.
    if (data.website or "").strip():
        return {"ok": True, "accepted": False, "id": lead_id}

    if not is_spam:
        bg.add_task(_send_lead_emails, lead_id, data, ip, _booking_link(lead_id, booking_token))

    return {
        "ok": True,
        "accepted": True,
        "id": lead_id,
        "is_test": is_test,
        "is_spam": is_spam,
    }



@app.get("/api/public/booking/{lead_id}")
def public_booking_info(lead_id: str, token: str) -> Dict[str, Any]:
    target = booking_target(lead_id=lead_id, booking_token=(token or "").strip())
    if not target:
        raise HTTPException(status_code=404, detail="booking lead not found")

    payload = {}
    try:
        payload = json.loads(target.get("payload_json") or "{}")
    except Exception:
        payload = {}

    return {
        "ok": True,
        "lead_id": target.get("id"),
        "form_type": target.get("form_type"),
        "created_at": target.get("created_at"),
        "lead_status": target.get("lead_status") or "new",
        "booked_at": target.get("booked_at"),
        "booked_slot": target.get("booked_slot"),
        "email": _lead_email(payload),
    }


@app.post("/api/public/booking/{lead_id}/confirm")
def public_booking_confirm(lead_id: str, data: BookingConfirmIn) -> Dict[str, Any]:
    target = booking_target(lead_id=lead_id, booking_token=(data.token or "").strip())
    if not target:
        raise HTTPException(status_code=404, detail="booking lead not found")

    booked_slot = parse_or_none(data.booked_slot)
    if not booked_slot:
        raise HTTPException(status_code=400, detail="booked_slot must be ISO datetime")

    dt = datetime.fromisoformat(booked_slot.replace("Z", "+00:00"))
    if dt < datetime.now(timezone.utc) - timedelta(minutes=1):
        raise HTTPException(status_code=400, detail="booked_slot must be in the future")

    confirm_lead_booking(lead_id=lead_id, booked_slot=booked_slot, updated_at=now_iso())
    row = get_lead_by_id(lead_id)
    if row:
        payload = {}
        try:
            payload = json.loads(row.get("payload_json") or "{}")
        except Exception:
            payload = {}
        _recompute_autopilot_for_row(row, payload)
        _refresh_win_snapshot_for_row(row, payload)
        _sequence_ensure_for_lead(
            lead_id=lead_id,
            created_at=row.get("created_at"),
            lead_status=str(row.get("lead_status") or "new"),
            is_test=bool(int(row.get("is_test") or 0)),
            is_spam=bool(int(row.get("is_spam") or 0)),
        )
    return {"ok": True, "lead_id": lead_id, "booked_slot": booked_slot, "status": "in_progress"}

@app.post("/api/analytics/events")
def ingest_analytics_events(req: Request, batch: AnalyticsBatchIn) -> Dict[str, Any]:
    if not _is_origin_allowed(req):
        raise HTTPException(status_code=403, detail="origin not allowed")
    ip = client_ip(req)
    rate_check(_rate_events, ip, RATE_LIMIT_EVENTS_MAX)

    ua = req.headers.get("user-agent", "")[:300]
    rows = []
    for ev in batch.events:
        created_at = parse_or_now(ev.created_at)
        rows.append(
            (
                ev.event_name,
                ev.label or "",
                ev.path or "",
                ev.href or "",
                ev.session_id or "",
                ev.consent_state or "unknown",
                json.dumps(ev.payload, ensure_ascii=False),
                ip,
                ua,
                created_at,
            )
        )

    inserted = insert_analytics_events(rows)
    return {"ok": True, "inserted": inserted}


def _pct_delta(curr: int, prev: int) -> Optional[float]:
    if prev == 0:
        return None
    return round(((curr - prev) / prev) * 100.0, 2)


def _sum_funnel(start_iso: str, end_iso: str, paths: List[str]) -> int:
    return sum(funnel_count_between(start_iso, end_iso, p) for p in paths)


def build_weekly_report(days: int = 7) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    start_curr = now - timedelta(days=days)
    start_prev = start_curr - timedelta(days=days)

    s_curr = start_curr.isoformat()
    s_prev = start_prev.isoformat()
    s_now = now.isoformat()

    curr = {
        "events_total": count_events_between(s_curr, s_now),
        "page_view": count_events_between(s_curr, s_now, "page_view"),
        "cta_click": count_events_between(s_curr, s_now, "cta_click"),
        "form_submit": count_events_between(s_curr, s_now, "form_submit"),
        "leads": count_leads_between(s_curr, s_now),
        "funnel_index": _sum_funnel(s_curr, s_now, ["/", "/index.html"]),
        "funnel_oferta": _sum_funnel(s_curr, s_now, ["/oferta.html"]),
        "funnel_kontakt": _sum_funnel(s_curr, s_now, ["/kontakt.html"]),
    }

    prev = {
        "events_total": count_events_between(s_prev, s_curr),
        "page_view": count_events_between(s_prev, s_curr, "page_view"),
        "cta_click": count_events_between(s_prev, s_curr, "cta_click"),
        "form_submit": count_events_between(s_prev, s_curr, "form_submit"),
        "leads": count_leads_between(s_prev, s_curr),
        "funnel_index": _sum_funnel(s_prev, s_curr, ["/", "/index.html"]),
        "funnel_oferta": _sum_funnel(s_prev, s_curr, ["/oferta.html"]),
        "funnel_kontakt": _sum_funnel(s_prev, s_curr, ["/kontakt.html"]),
    }

    deltas = {k: _pct_delta(curr[k], prev[k]) for k in curr.keys()}
    top_cta = top_cta_labels_between(s_curr, s_now, limit=8)

    report = {
        "generated_at": now_iso(),
        "window_days": days,
        "window_current": {"from": s_curr, "to": s_now},
        "window_previous": {"from": s_prev, "to": s_curr},
        "current": curr,
        "previous": prev,
        "delta_percent": deltas,
        "top_cta": top_cta,
    }
    return report


def report_markdown(report: Dict[str, Any]) -> str:
    c = report["current"]
    d = report["delta_percent"]
    top = report["top_cta"]
    top_lines = "\n".join([f"- {x['label']}: {x['cnt']}" for x in top]) if top else "- brak danych"

    def fmt_delta(v: Optional[float]) -> str:
        if v is None:
            return "n/a"
        s = "+" if v >= 0 else ""
        return f"{s}{v}%"

    return (
        f"# Weekly KPI Digest\n\n"
        f"Generated: {report['generated_at']}\n"
        f"Window: {report['window_current']['from']} -> {report['window_current']['to']}\n\n"
        f"## KPI\n"
        f"- page_view: {c['page_view']} ({fmt_delta(d['page_view'])})\n"
        f"- cta_click: {c['cta_click']} ({fmt_delta(d['cta_click'])})\n"
        f"- form_submit: {c['form_submit']} ({fmt_delta(d['form_submit'])})\n"
        f"- leads: {c['leads']} ({fmt_delta(d['leads'])})\n\n"
        f"## Funnel\n"
        f"- index: {c['funnel_index']} ({fmt_delta(d['funnel_index'])})\n"
        f"- oferta: {c['funnel_oferta']} ({fmt_delta(d['funnel_oferta'])})\n"
        f"- kontakt: {c['funnel_kontakt']} ({fmt_delta(d['funnel_kontakt'])})\n\n"
        f"## Top CTA\n{top_lines}\n"
    )


@app.get("/api/admin/summary")
def admin_summary(
    req: Request,
    days: int = 7,
    include_test: bool = False,
    include_spam: bool = False,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    if days < 1 or days > 60:
        raise HTTPException(status_code=400, detail="days must be in range 1..60")
    _require_admin(req, token=token)

    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)
    s_now = now.isoformat()
    s_start = start.isoformat()

    rows_window = list_leads_between(
        s_start,
        s_now,
        limit=5000,
        include_test=include_test,
        include_spam=include_spam,
    )
    prev_start = (start - timedelta(days=days)).isoformat()
    prev_end = start.isoformat()
    rows_prev = list_leads_between(
        prev_start,
        prev_end,
        limit=5000,
        include_test=include_test,
        include_spam=include_spam,
    )
    all_rows_window = list_leads_between(s_start, s_now, limit=5000, include_test=True, include_spam=True)
    events_window = list_analytics_events_between(s_start, s_now, event_name="", limit=25000)

    form_submit_total = count_form_submit_between(s_start, s_now)
    form_submit_prev = count_form_submit_between(prev_start, prev_end)
    leads_total = len(rows_window)
    conv = round((leads_total / form_submit_total) * 100.0, 2) if form_submit_total > 0 else None

    tier_counts = {"hot": 0, "warm": 0, "cold": 0}
    email_counts: Dict[str, int] = {}
    leads_by_form: Dict[str, int] = {}
    leads_by_status: Dict[str, int] = {}
    lost_reason_counts: Dict[str, int] = {}
    first_contact_minutes: List[float] = []
    contact_24h_count = 0
    won_missing_value_count = 0
    lost_missing_reason_count = 0

    for row in rows_window:
        payload = {}
        try:
            payload = json.loads(row.get("payload_json") or "{}")
        except Exception:
            payload = {}
        em = _lead_email(payload).lower()
        if em:
            email_counts[em] = email_counts.get(em, 0) + 1
        form = str(row.get("form_type") or "other")
        leads_by_form[form] = leads_by_form.get(form, 0) + 1
        st = str(row.get("lead_status") or "new")
        leads_by_status[st] = leads_by_status.get(st, 0) + 1
        if st == "lost":
            reason_key = _normalize_lost_reason(str(row.get("lost_reason") or ""))
            if reason_key:
                lost_reason_counts[reason_key] = lost_reason_counts.get(reason_key, 0) + 1
            else:
                lost_missing_reason_count += 1
        if st == "won" and float(row.get("deal_value") or 0.0) <= 0.0:
            won_missing_value_count += 1
        created_dt = _safe_dt(str(row.get("created_at") or ""))
        first_contact_dt = _safe_dt(str(row.get("last_contact_at") or ""))
        if created_dt and first_contact_dt and first_contact_dt >= created_dt:
            mins = (first_contact_dt - created_dt).total_seconds() / 60.0
            first_contact_minutes.append(mins)
            if mins <= (24 * 60):
                contact_24h_count += 1

    duplicates_total = 0
    for row in rows_window:
        payload = {}
        try:
            payload = json.loads(row.get("payload_json") or "{}")
        except Exception:
            payload = {}
        score = _lead_score(
            form_type=str(row.get("form_type") or ""),
            payload=payload,
            lead_status=str(row.get("lead_status") or "new"),
        )
        tier_counts[_lead_tier(score)] += 1
        em = _lead_email(payload).lower()
        if em and email_counts.get(em, 0) > 1:
            duplicates_total += 1

    flagged = {
        "test": sum(1 for x in all_rows_window if int(x.get("is_test") or 0) == 1),
        "spam": sum(1 for x in all_rows_window if int(x.get("is_spam") or 0) == 1),
    }
    resolved_total = sum(1 for x in rows_window if str(x.get("lead_status") or "") in {"won", "lost"})
    resolved_with_data = sum(
        1
        for x in rows_window
        if (
            (str(x.get("lead_status") or "") == "won" and float(x.get("deal_value") or 0.0) > 0.0)
            or (str(x.get("lead_status") or "") == "lost" and bool(_normalize_lost_reason(str(x.get("lost_reason") or ""))))
        )
    )
    resolved_data_pct = round((resolved_with_data / resolved_total) * 100.0, 2) if resolved_total > 0 else None
    first_contact_avg_m = round(sum(first_contact_minutes) / len(first_contact_minutes), 2) if first_contact_minutes else None
    contact_24h_pct = round((contact_24h_count / len(first_contact_minutes)) * 100.0, 2) if first_contact_minutes else None

    def _window_stats(rows: List[Dict[str, Any]], submit_total: int) -> Dict[str, Any]:
        leads_n = len(rows)
        won_n = sum(1 for x in rows if str(x.get("lead_status") or "") == "won")
        lost_n = sum(1 for x in rows if str(x.get("lead_status") or "") == "lost")
        resolved_n = won_n + lost_n
        revenue_n = sum(float(x.get("deal_value") or 0.0) for x in rows if str(x.get("lead_status") or "") == "won")
        return {
            "leads": leads_n,
            "won": won_n,
            "lost": lost_n,
            "resolved": resolved_n,
            "win_rate_pct": round((won_n / resolved_n) * 100.0, 2) if resolved_n > 0 else None,
            "revenue": round(revenue_n, 2),
            "lead_to_submit_conversion_pct": round((leads_n / submit_total) * 100.0, 2) if submit_total > 0 else None,
        }

    current_stats = _window_stats(rows_window, form_submit_total)
    previous_stats = _window_stats(rows_prev, form_submit_prev)

    def _delta_pct(curr: Optional[float], prev: Optional[float]) -> Optional[float]:
        if curr is None or prev is None:
            return None
        if abs(prev) < 1e-9:
            return None
        return round(((curr - prev) / abs(prev)) * 100.0, 2)

    trend_delta = {
        "leads": _delta_pct(float(current_stats["leads"]), float(previous_stats["leads"])),
        "won": _delta_pct(float(current_stats["won"]), float(previous_stats["won"])),
        "resolved": _delta_pct(float(current_stats["resolved"]), float(previous_stats["resolved"])),
        "win_rate_pct": _delta_pct(current_stats["win_rate_pct"], previous_stats["win_rate_pct"]),
        "revenue": _delta_pct(float(current_stats["revenue"]), float(previous_stats["revenue"])),
        "lead_to_submit_conversion_pct": _delta_pct(
            current_stats["lead_to_submit_conversion_pct"],
            previous_stats["lead_to_submit_conversion_pct"],
        ),
    }

    return {
        "ok": True,
        "days": days,
        "from": s_start,
        "to": s_now,
        "filters": {"include_test": include_test, "include_spam": include_spam},
        "totals": {
            "leads": leads_total,
            "events": count_events_between(s_start, s_now),
            "page_view": count_events_between(s_start, s_now, "page_view"),
            "cta_click": count_events_between(s_start, s_now, "cta_click"),
            "form_submit": form_submit_total,
            "flagged_test": flagged["test"],
            "flagged_spam": flagged["spam"],
        },
        "quality": {
            "lead_to_submit_conversion_pct": conv,
            "form_submit_by_form": count_form_submit_by_form_between(s_start, s_now),
            "lead_tier_counts": tier_counts,
            "duplicates_total": duplicates_total,
            "won_missing_deal_value_count": won_missing_value_count,
            "lost_missing_reason_count": lost_missing_reason_count,
            "resolved_total": resolved_total,
            "resolved_with_required_data_pct": resolved_data_pct,
            "first_contact_avg_minutes": first_contact_avg_m,
            "first_contact_within_24h_pct": contact_24h_pct,
        },
        "leads_by_form": [{"form_type": k, "cnt": v} for k, v in sorted(leads_by_form.items(), key=lambda kv: kv[1], reverse=True)],
        "leads_by_status": [{"status": k, "cnt": v} for k, v in sorted(leads_by_status.items(), key=lambda kv: kv[1], reverse=True)],
        "lost_reason_top": [{"reason": k, "cnt": v} for k, v in sorted(lost_reason_counts.items(), key=lambda kv: kv[1], reverse=True)[:8]],
        "lost_reason_catalog": _LOST_REASON_CATALOG,
        "trend": {
            "window_days": days,
            "current": current_stats,
            "previous": previous_stats,
            "delta_pct": trend_delta,
        },
        "top_events": top_events_between(s_start, s_now, limit=12),
        "top_cta": top_cta_labels_between(s_start, s_now, limit=12),
        "analytics_segments": _analytics_segments_from_events(events_window, limit=12),
    }


@app.get("/api/admin/reports/analytics-segments")
def admin_analytics_segments_report(
    req: Request,
    days: int = 7,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    if days < 1 or days > 90:
        raise HTTPException(status_code=400, detail="days must be in range 1..90")
    _require_admin(req, token=token)

    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)
    s_now = now.isoformat()
    s_start = start.isoformat()
    events = list_analytics_events_between(s_start, s_now, event_name="", limit=30000)

    return {
        "ok": True,
        "report": {
            "generated_at": s_now,
            "days": days,
            "from": s_start,
            "to": s_now,
            "segments": _analytics_segments_from_events(events, limit=20),
        },
    }


@app.get("/api/admin/lost-reasons")
def admin_lost_reasons(req: Request, token: Optional[str] = None) -> Dict[str, Any]:
    _require_admin(req, token=token)
    return {"ok": True, "items": _LOST_REASON_CATALOG}


@app.get("/api/admin/features")
def admin_features(req: Request, token: Optional[str] = None) -> Dict[str, Any]:
    _require_admin(req, token=token)
    return {
        "ok": True,
        "features": {
            "AUTOPILOT_ENABLED": _autopilot_enabled(),
            "WIN_MODEL_ENABLED": _win_model_enabled(),
            "ROI_ENABLED": _roi_enabled(),
        },
    }


@app.post("/api/admin/features")
def admin_features_update(req: Request, data: FeatureFlagsUpdateIn, token: Optional[str] = None) -> Dict[str, Any]:
    _require_admin(req, token=token)
    flags = {
        "AUTOPILOT_ENABLED": bool(data.AUTOPILOT_ENABLED),
        "WIN_MODEL_ENABLED": bool(data.WIN_MODEL_ENABLED),
        "ROI_ENABLED": bool(data.ROI_ENABLED),
    }
    _set_feature_flags(flags, persist=bool(data.persist))
    return {"ok": True, "features": flags, "persist": bool(data.persist)}


@app.get("/api/admin/reports/win-model")
def admin_win_model_report(
    req: Request,
    days: int = 120,
    include_test: bool = False,
    include_spam: bool = False,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    if days < 7 or days > 365:
        raise HTTPException(status_code=400, detail="days must be in range 7..365")
    _require_admin(req, token=token)
    if not _win_model_enabled():
        return {"ok": True, "enabled": False, "report": {"model_version": WIN_MODEL_VERSION, "rows": []}}
    model = _win_model_snapshot(days=days, include_test=include_test, include_spam=include_spam)

    def _top_rows(name: str) -> List[Dict[str, Any]]:
        rows = []
        for label, stats in (model.get(name) or {}).items():
            rows.append(
                {
                    "label": label,
                    "win_rate_pct": round(float(stats.get("win_rate") or 0.0) * 100.0, 2),
                    "samples": int(stats.get("samples") or 0),
                }
            )
        rows.sort(key=lambda x: (x["samples"], x["win_rate_pct"]), reverse=True)
        return rows[:12]

    return {
        "ok": True,
        "report": {
            "model_version": model.get("model_version") or WIN_MODEL_VERSION,
            "days": days,
            "resolved_total": int(model.get("resolved_total") or 0),
            "won_total": int(model.get("won_total") or 0),
            "base_win_rate_pct": round(float(model.get("base_win_rate") or 0.0) * 100.0, 2),
            "top_form_rates": _top_rows("form_rates"),
            "top_source_rates": _top_rows("source_rates"),
            "top_tier_rates": _top_rows("tier_rates"),
        },
    }


@app.get("/api/admin/reports/roi")
def admin_roi_report(
    req: Request,
    days: int = 30,
    include_test: bool = False,
    include_spam: bool = False,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    if days < 7 or days > 365:
        raise HTTPException(status_code=400, detail="days must be in range 7..365")
    _require_admin(req, token=token)
    if not _roi_enabled():
        return {"ok": True, "enabled": False, "report": {"days": days, "rows": [], "totals": {"cost": 0.0, "revenue": 0.0, "profit": 0.0}}}
    report = _build_roi_report(days=days, include_test=include_test, include_spam=include_spam)
    return {"ok": True, "report": report}


@app.get("/api/admin/reports/roi/recommendations")
def admin_roi_recommendations(
    req: Request,
    days: int = 30,
    spend_change_pct: float = 20.0,
    include_test: bool = False,
    include_spam: bool = False,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    if days < 7 or days > 365:
        raise HTTPException(status_code=400, detail="days must be in range 7..365")
    if spend_change_pct < 1 or spend_change_pct > 80:
        raise HTTPException(status_code=400, detail="spend_change_pct must be in range 1..80")
    _require_admin(req, token=token)
    if not _roi_enabled():
        return {"ok": True, "enabled": False, "report": {"days": days, "rows": [], "summary": {}}}
    report = _build_budget_recommendations(
        days=days,
        include_test=include_test,
        include_spam=include_spam,
        spend_change_pct=spend_change_pct,
    )
    return {"ok": True, "report": report}


@app.post("/api/admin/budget-plans/propose")
def admin_budget_plan_propose(req: Request, data: BudgetPlanCreateIn, token: Optional[str] = None) -> Dict[str, Any]:
    _require_admin(req, token=token)
    if not _roi_enabled():
        raise HTTPException(status_code=409, detail="ROI feature disabled")
    report = _build_budget_recommendations(
        days=int(data.days),
        include_test=False,
        include_spam=False,
        spend_change_pct=float(data.spend_change_pct),
    )
    created = now_iso()
    plan_id = insert_budget_plan(
        created_at=created,
        days=int(data.days),
        spend_change_pct=float(data.spend_change_pct),
        status="proposed",
        note=(data.note or "").strip()[:400],
    )
    items_payload: List[Tuple[str, str, str, float, float, float, float, str, str]] = []
    for row in (report.get("rows") or []):
        current = row.get("current") or {}
        sim = row.get("simulation") or {}
        items_payload.append(
            (
                str(row.get("channel") or "")[:120],
                str(row.get("action") or "hold")[:20],
                str(row.get("reason") or "")[:200],
                float(current.get("cost") or 0.0),
                float((current.get("cost") or 0.0) + (sim.get("spend_delta") or 0.0)),
                float(sim.get("spend_delta") or 0.0),
                float(sim.get("estimated_profit_delta") or 0.0),
                "pending",
                created,
            )
        )
    insert_budget_plan_items(plan_id=plan_id, items=items_payload)
    return {"ok": True, "plan_id": plan_id, "items": len(items_payload), "created_at": created}


@app.get("/api/admin/budget-plans")
def admin_budget_plans(req: Request, limit: int = 20, token: Optional[str] = None) -> Dict[str, Any]:
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=400, detail="limit must be in range 1..100")
    _require_admin(req, token=token)
    plans = list_budget_plans(limit=limit)
    return {"ok": True, "plans": plans}


@app.get("/api/admin/budget-plans/{plan_id}")
def admin_budget_plan_details(req: Request, plan_id: int, token: Optional[str] = None) -> Dict[str, Any]:
    _require_admin(req, token=token)
    plan = get_budget_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="plan not found")
    items = list_budget_plan_items(plan_id=plan_id)
    totals = {
        "items": len(items),
        "pending": sum(1 for x in items if str(x.get("status") or "") == "pending"),
        "applied": sum(1 for x in items if str(x.get("status") or "") == "applied"),
        "skipped": sum(1 for x in items if str(x.get("status") or "") == "skipped"),
        "delta_cost": round(sum(float(x.get("delta_cost") or 0.0) for x in items), 2),
        "expected_profit_delta": round(sum(float(x.get("expected_profit_delta") or 0.0) for x in items), 2),
    }
    return {"ok": True, "plan": plan, "totals": totals, "items": items}


@app.post("/api/admin/budget-plans/{plan_id}/items/{item_id}/status")
def admin_budget_plan_item_status(
    req: Request,
    plan_id: int,
    item_id: int,
    data: BudgetPlanItemStatusIn,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    _require_admin(req, token=token)
    status = (data.status or "").strip().lower()
    if status not in {"pending", "applied", "skipped"}:
        raise HTTPException(status_code=400, detail="status must be pending/applied/skipped")
    plan = get_budget_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="plan not found")
    item = budget_plan_item(item_id)
    if not item or int(item.get("plan_id") or 0) != plan_id:
        raise HTTPException(status_code=404, detail="plan item not found")

    ts = now_iso()
    applied_at = ts if status == "applied" else None
    update_budget_plan_item_status(item_id=item_id, status=status, applied_at=applied_at, updated_at=ts)

    items = list_budget_plan_items(plan_id=plan_id)
    pending_left = sum(1 for x in items if str(x.get("status") or "") == "pending")
    if pending_left == 0:
        update_budget_plan_status(plan_id=plan_id, status="executed")
    elif status == "applied":
        update_budget_plan_status(plan_id=plan_id, status="in_progress")

    return {"ok": True, "plan_id": plan_id, "item_id": item_id, "status": status}


@app.post("/api/admin/budget-plans/{plan_id}/items/{item_id}/apply-costs")
def admin_budget_plan_item_apply_costs(
    req: Request,
    plan_id: int,
    item_id: int,
    data: BudgetPlanApplyIn,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    _require_admin(req, token=token)
    plan = get_budget_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="plan not found")
    item = budget_plan_item(item_id)
    if not item or int(item.get("plan_id") or 0) != plan_id:
        raise HTTPException(status_code=404, detail="plan item not found")

    start_date = (data.start_date or "").strip()
    if not start_date:
        start_date = datetime.now(timezone.utc).date().isoformat()
    try:
        start_dt = datetime.fromisoformat(start_date)
    except Exception:
        raise HTTPException(status_code=400, detail="start_date must be YYYY-MM-DD")

    apply_days = int(data.days)
    plan_days = max(1, int(plan.get("days") or 30))
    proposed_cost_total = float(item.get("proposed_cost") or 0.0)
    daily_cost = proposed_cost_total / float(plan_days)
    channel = str(item.get("channel") or "").strip().lower()
    if not channel:
        raise HTTPException(status_code=400, detail="item channel missing")

    ts = now_iso()
    run_rows: List[Tuple[int, int, str, str, float, float, str]] = []
    for i in range(apply_days):
        d = (start_dt + timedelta(days=i)).date().isoformat()
        prev_cost = channel_cost_on_date(d, channel)
        prev_value = float(prev_cost) if prev_cost is not None else 0.0
        new_value = round(daily_cost, 2)
        upsert_channel_cost_daily(date_iso=d, channel=channel, cost=new_value, updated_at=ts)
        run_rows.append((plan_id, item_id, d, channel, prev_value, new_value, ts))

    inserted = insert_budget_plan_cost_runs(run_rows)
    update_budget_plan_item_status(item_id=item_id, status="applied", applied_at=ts, updated_at=ts)
    update_budget_plan_status(plan_id=plan_id, status="in_progress")
    return {
        "ok": True,
        "plan_id": plan_id,
        "item_id": item_id,
        "channel": channel,
        "days": apply_days,
        "daily_cost": round(daily_cost, 2),
        "applied_rows": inserted,
    }


@app.post("/api/admin/budget-plans/{plan_id}/items/{item_id}/rollback-costs")
def admin_budget_plan_item_rollback_costs(
    req: Request,
    plan_id: int,
    item_id: int,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    _require_admin(req, token=token)
    plan = get_budget_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="plan not found")
    item = budget_plan_item(item_id)
    if not item or int(item.get("plan_id") or 0) != plan_id:
        raise HTTPException(status_code=404, detail="plan item not found")

    runs = unreverted_budget_plan_cost_runs(plan_id=plan_id, item_id=item_id)
    if not runs:
        return {"ok": True, "plan_id": plan_id, "item_id": item_id, "rolled_back_rows": 0}

    ts = now_iso()
    for r in runs:
        d = str(r.get("date_iso") or "")
        channel = str(r.get("channel") or "")
        prev_cost = float(r.get("prev_cost") or 0.0)
        upsert_channel_cost_daily(date_iso=d, channel=channel, cost=prev_cost, updated_at=ts)

    changed = mark_budget_plan_runs_reverted([int(r.get("id") or 0) for r in runs], reverted_at=ts)
    update_budget_plan_item_status(item_id=item_id, status="pending", applied_at=None, updated_at=ts)
    return {"ok": True, "plan_id": plan_id, "item_id": item_id, "rolled_back_rows": changed}


@app.get("/api/admin/budget-plans/{plan_id}/cost-runs")
def admin_budget_plan_cost_runs(
    req: Request,
    plan_id: int,
    item_id: Optional[int] = None,
    limit: int = 200,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    if limit < 1 or limit > 1000:
        raise HTTPException(status_code=400, detail="limit must be in range 1..1000")
    _require_admin(req, token=token)
    plan = get_budget_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="plan not found")
    rows = list_budget_plan_cost_runs(plan_id=plan_id, item_id=item_id, limit=limit)
    return {"ok": True, "plan_id": plan_id, "rows": rows}


@app.get("/api/admin/reports/forecast")
def admin_forecast_report(
    req: Request,
    history_days: int = 60,
    horizon_days: int = 30,
    target_revenue: float = 0.0,
    budget_change_pct: float = 0.0,
    conv_uplift_pct: float = 0.0,
    include_test: bool = False,
    include_spam: bool = False,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    _require_admin(req, token=token)
    report = _build_forecast_report(
        history_days=history_days,
        horizon_days=horizon_days,
        target_revenue=target_revenue,
        budget_change_pct=budget_change_pct,
        conv_uplift_pct=conv_uplift_pct,
        include_test=include_test,
        include_spam=include_spam,
    )
    return {"ok": True, "report": report}


@app.get("/api/admin/reports/ops-review")
def admin_ops_review_report(
    req: Request,
    days: int = 7,
    target_revenue: float = 0.0,
    include_test: bool = False,
    include_spam: bool = False,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    _require_admin(req, token=token)
    report = _build_ops_review_report(
        days=days,
        target_revenue=target_revenue,
        include_test=include_test,
        include_spam=include_spam,
    )
    return {"ok": True, "report": report}


@app.post("/api/admin/scenarios")
def admin_scenario_create(req: Request, data: ScenarioSnapshotCreateIn, token: Optional[str] = None) -> Dict[str, Any]:
    _require_admin(req, token=token)
    roi = _build_roi_report(days=data.days, include_test=data.include_test, include_spam=data.include_spam)
    alloc = _build_budget_recommendations(
        days=data.days,
        include_test=data.include_test,
        include_spam=data.include_spam,
        spend_change_pct=data.spend_change_pct,
    )
    forecast = _build_forecast_report(
        history_days=data.history_days,
        horizon_days=data.horizon_days,
        target_revenue=data.target_revenue,
        budget_change_pct=data.budget_change_pct,
        conv_uplift_pct=data.conv_uplift_pct,
        include_test=data.include_test,
        include_spam=data.include_spam,
    )
    summary = {
        "roi_totals": roi.get("totals") or {},
        "allocator_top": (alloc.get("rows") or [])[:5],
        "forecast_totals": forecast.get("totals") or {},
        "scenario": forecast.get("scenario") or {},
    }
    sid = create_scenario_snapshot(
        created_at=now_iso(),
        name=data.name,
        days=data.days,
        history_days=data.history_days,
        horizon_days=data.horizon_days,
        target_revenue=data.target_revenue,
        budget_change_pct=data.budget_change_pct,
        conv_uplift_pct=data.conv_uplift_pct,
        spend_change_pct=data.spend_change_pct,
        include_test=data.include_test,
        include_spam=data.include_spam,
        summary_json=json.dumps(summary, ensure_ascii=False),
    )
    return {"ok": True, "scenario_id": sid}


@app.get("/api/admin/scenarios")
def admin_scenarios_list(req: Request, limit: int = 30, token: Optional[str] = None) -> Dict[str, Any]:
    if limit < 1 or limit > 200:
        raise HTTPException(status_code=400, detail="limit must be in range 1..200")
    _require_admin(req, token=token)
    rows = list_scenario_snapshots(limit=limit)
    out: List[Dict[str, Any]] = []
    for x in rows:
        summary = {}
        try:
            summary = json.loads(x.get("summary_json") or "{}")
        except Exception:
            summary = {}
        out.append(
            {
                "id": x.get("id"),
                "created_at": x.get("created_at"),
                "name": x.get("name"),
                "days": x.get("days"),
                "history_days": x.get("history_days"),
                "horizon_days": x.get("horizon_days"),
                "target_revenue": x.get("target_revenue"),
                "budget_change_pct": x.get("budget_change_pct"),
                "conv_uplift_pct": x.get("conv_uplift_pct"),
                "spend_change_pct": x.get("spend_change_pct"),
                "include_test": bool(int(x.get("include_test") or 0)),
                "include_spam": bool(int(x.get("include_spam") or 0)),
                "summary": summary,
            }
        )
    return {"ok": True, "items": out}


@app.get("/api/admin/scenarios/{scenario_id}")
def admin_scenario_get(req: Request, scenario_id: int, token: Optional[str] = None) -> Dict[str, Any]:
    _require_admin(req, token=token)
    row = get_scenario_snapshot(scenario_id)
    if not row:
        raise HTTPException(status_code=404, detail="scenario not found")
    summary = {}
    try:
        summary = json.loads(row.get("summary_json") or "{}")
    except Exception:
        summary = {}
    return {"ok": True, "scenario": {**row, "summary": summary}}


@app.delete("/api/admin/scenarios/{scenario_id}")
def admin_scenario_delete(req: Request, scenario_id: int, token: Optional[str] = None) -> Dict[str, Any]:
    _require_admin(req, token=token)
    changed = delete_scenario_snapshot(scenario_id)
    if changed < 1:
        raise HTTPException(status_code=404, detail="scenario not found")
    return {"ok": True, "scenario_id": scenario_id}


@app.get("/api/admin/scenarios-compare")
def admin_scenarios_compare(req: Request, base_id: int, candidate_id: int, token: Optional[str] = None) -> Dict[str, Any]:
    _require_admin(req, token=token)
    a = get_scenario_snapshot(base_id)
    b = get_scenario_snapshot(candidate_id)
    if not a or not b:
        raise HTTPException(status_code=404, detail="scenario not found")

    def _sum(row: Dict[str, Any]) -> Dict[str, float]:
        s = {}
        try:
            s = json.loads(row.get("summary_json") or "{}")
        except Exception:
            s = {}
        f = (s.get("forecast_totals") or {})
        return {
            "forecast_revenue": float(f.get("forecast_revenue") or 0.0),
            "forecast_cost": float(f.get("forecast_cost") or 0.0),
            "forecast_profit": float(f.get("forecast_profit") or 0.0),
            "target_gap": float(f.get("target_gap") or 0.0),
        }

    sa = _sum(a)
    sb = _sum(b)
    delta = {k: round(sb[k] - sa[k], 2) for k in sa.keys()}
    return {
        "ok": True,
        "base": {"id": a.get("id"), "name": a.get("name"), "metrics": sa},
        "candidate": {"id": b.get("id"), "name": b.get("name"), "metrics": sb},
        "delta": delta,
    }


@app.get("/api/admin/autonomous/connectors")
def admin_autonomous_connectors(req: Request, token: Optional[str] = None) -> Dict[str, Any]:
    _require_admin(req, token=token)
    rows = []
    for x in list_execution_connectors():
        details = {}
        try:
            details = json.loads(x.get("last_result_json") or "{}")
        except Exception:
            details = {}
        rows.append({**x, "last_result": details})
    return {"ok": True, "items": rows}


@app.post("/api/admin/autonomous/connectors")
def admin_autonomous_connector_upsert(req: Request, data: ConnectorUpsertIn, token: Optional[str] = None) -> Dict[str, Any]:
    _require_admin(req, token=token)
    mode = (data.mode or "").strip().lower()
    status = (data.status or "").strip().lower()
    if mode not in {"simulate", "live"}:
        raise HTTPException(status_code=400, detail="mode must be simulate or live")
    if status not in {"enabled", "disabled"}:
        raise HTTPException(status_code=400, detail="status must be enabled or disabled")
    upsert_execution_connector(
        channel=(data.channel or "").strip().lower(),
        provider=(data.provider or "simulator").strip().lower(),
        mode=mode,
        status=status,
        daily_change_limit_pct=float(data.daily_change_limit_pct),
        updated_at=now_iso(),
    )
    return {"ok": True, "channel": (data.channel or "").strip().lower()}


@app.post("/api/admin/autonomous/connectors/{channel}/sync")
def admin_autonomous_connector_sync(req: Request, channel: str, token: Optional[str] = None) -> Dict[str, Any]:
    _require_admin(req, token=token)
    connectors = {str(x.get("channel") or ""): x for x in list_execution_connectors()}
    target = connectors.get((channel or "").strip().lower())
    if not target:
        raise HTTPException(status_code=404, detail="connector not found")
    if str(target.get("status") or "") != "enabled":
        raise HTTPException(status_code=400, detail="connector disabled")

    ts = now_iso()
    ping = _connector_health_ping(target)
    result = {
        "channel": target.get("channel"),
        "provider": target.get("provider"),
        "mode": target.get("mode"),
        "sync_status": "ok" if bool(ping.get("ok")) else "error",
        "ping": ping,
        "synced_at": ts,
    }
    update_execution_connector_sync(
        channel=str(target.get("channel") or ""),
        last_sync_at=ts,
        last_result_json=json.dumps(result, ensure_ascii=False),
        updated_at=ts,
    )
    if not bool(ping.get("ok")):
        raise HTTPException(status_code=502, detail={"sync_status": "error", "result": result})
    return {"ok": True, "result": result}


@app.get("/api/admin/autonomous/approvals")
def admin_autonomous_approvals(req: Request, status: str = "", limit: int = 120, token: Optional[str] = None) -> Dict[str, Any]:
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="limit must be in range 1..500")
    _require_admin(req, token=token)
    rows = []
    for x in list_approvals(status=status, limit=limit):
        payload = {}
        try:
            payload = json.loads(x.get("payload_json") or "{}")
        except Exception:
            payload = {}
        rows.append({**x, "payload": payload})
    return {"ok": True, "items": rows}


@app.post("/api/admin/autonomous/plans/{plan_id}/submit")
def admin_autonomous_submit_plan_for_approval(
    req: Request,
    plan_id: int,
    data: PlanSubmitForApprovalIn,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    _require_admin(req, token=token)
    plan = get_budget_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="plan not found")
    items = list_budget_plan_items(plan_id=plan_id)
    created = 0
    for item in items:
        item_id = int(item.get("id") or 0)
        if item_id <= 0:
            continue
        if str(item.get("status") or "") not in {"pending", "approved"}:
            continue
        payload = {
            "plan_id": plan_id,
            "item_id": item_id,
            "channel": str(item.get("channel") or ""),
            "delta_cost": float(item.get("delta_cost") or 0.0),
            "current_cost": float(item.get("current_cost") or 0.0),
            "proposed_cost": float(item.get("proposed_cost") or 0.0),
            "apply_days": 7,
        }
        approval_id = create_approval(
            entity_type="budget_plan_item",
            entity_id=str(item_id),
            action="apply_costs",
            payload_json=json.dumps(payload, ensure_ascii=False),
            threshold_value=float(data.threshold_abs_delta_cost),
            requested_by=(data.requested_by or "ops").strip()[:80],
            note=(data.note or "").strip()[:400],
            created_at=now_iso(),
        )
        if approval_id > 0:
            created += 1
    return {"ok": True, "plan_id": plan_id, "approvals_created": created}


@app.post("/api/admin/autonomous/approvals/{approval_id}/decision")
def admin_autonomous_approval_decision(
    req: Request,
    approval_id: int,
    data: ApprovalDecisionIn,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    _require_admin(req, token=token)
    approval = get_approval(approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail="approval not found")
    if str(approval.get("status") or "") != "pending":
        raise HTTPException(status_code=400, detail="approval is not pending")

    decision = (data.decision or "").strip().lower()
    if decision not in {"approved", "rejected"}:
        raise HTTPException(status_code=400, detail="decision must be approved or rejected")
    changed = update_approval_status(
        approval_id=approval_id,
        status=decision,
        decided_by=(data.decided_by or "admin").strip()[:80],
        note=(data.note or "").strip()[:400],
        decided_at=now_iso(),
    )
    if changed < 1:
        raise HTTPException(status_code=409, detail="approval update conflict")
    return {"ok": True, "approval_id": approval_id, "status": decision}


@app.get("/api/admin/autonomous/execution-runs")
def admin_autonomous_execution_runs(req: Request, limit: int = 120, channel: str = "", token: Optional[str] = None) -> Dict[str, Any]:
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="limit must be in range 1..500")
    _require_admin(req, token=token)
    rows = []
    for x in list_execution_runs(limit=limit, channel=(channel or "").strip().lower()):
        req_payload = {}
        res_payload = {}
        try:
            req_payload = json.loads(x.get("request_json") or "{}")
        except Exception:
            req_payload = {}
        try:
            res_payload = json.loads(x.get("response_json") or "{}")
        except Exception:
            res_payload = {}
        rows.append({**x, "request": req_payload, "response": res_payload})
    return {"ok": True, "items": rows}


@app.post("/api/admin/autonomous/plans/{plan_id}/apply-approved")
def admin_autonomous_apply_approved_plan_items(req: Request, plan_id: int, token: Optional[str] = None) -> Dict[str, Any]:
    _require_admin(req, token=token)
    plan = get_budget_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="plan not found")

    connectors = {str(x.get("channel") or ""): x for x in list_execution_connectors()}
    approvals = [x for x in list_approvals(status="approved", limit=2000) if str(x.get("entity_type") or "") == "budget_plan_item"]
    ts = now_iso()
    applied = 0
    blocked = 0

    for ap in approvals:
        payload = {}
        try:
            payload = json.loads(ap.get("payload_json") or "{}")
        except Exception:
            payload = {}
        if int(payload.get("plan_id") or 0) != plan_id:
            continue
        item_id = int(payload.get("item_id") or 0)
        item = budget_plan_item(item_id)
        if not item or int(item.get("plan_id") or 0) != plan_id:
            continue
        if str(item.get("status") or "") not in {"pending", "approved"}:
            continue

        channel = str(item.get("channel") or "").strip().lower()
        connector = connectors.get(channel)
        if not connector:
            blocked += 1
            continue
        if str(connector.get("status") or "") != "enabled":
            blocked += 1
            continue

        current_cost = float(item.get("current_cost") or 0.0)
        delta_cost = abs(float(item.get("delta_cost") or 0.0))
        delta_pct = 100.0 if current_cost <= 0 and delta_cost > 0 else (_safe_ratio(delta_cost, current_cost) * 100.0 if current_cost > 0 else 0.0)
        limit_pct = float(connector.get("daily_change_limit_pct") or 20.0)
        run_id = create_execution_run(
            connector_channel=channel,
            plan_id=plan_id,
            item_id=item_id,
            action="apply_costs",
            request_json=json.dumps(payload, ensure_ascii=False),
            created_at=ts,
        )
        if delta_pct > limit_pct:
            finish_execution_run(
                run_id=run_id,
                status="blocked_guardrail",
                response_json=json.dumps({"reason": "daily_change_limit", "delta_pct": round(delta_pct, 2), "limit_pct": limit_pct}, ensure_ascii=False),
                finished_at=ts,
            )
            blocked += 1
            continue

        apply_days = int(payload.get("apply_days") or 7)
        apply_days = max(1, min(60, apply_days))
        proposed_cost = float(item.get("proposed_cost") or 0.0)
        execution_payload = {
            "plan_id": plan_id,
            "item_id": item_id,
            "channel": channel,
            "current_cost": current_cost,
            "proposed_cost": proposed_cost,
            "delta_cost": float(item.get("delta_cost") or 0.0),
            "apply_days": apply_days,
            "requested_at": ts,
        }
        exec_result = _connector_execute_budget_change(connector=connector, payload=execution_payload)
        if not bool(exec_result.get("ok")):
            finish_execution_run(
                run_id=run_id,
                status="connector_error",
                response_json=json.dumps(exec_result, ensure_ascii=False),
                finished_at=ts,
            )
            blocked += 1
            continue

        start_date = datetime.now(timezone.utc).date()
        run_rows: List[Tuple[int, int, str, str, float, float, str]] = []
        for i in range(apply_days):
            d = (start_date + timedelta(days=i)).isoformat()
            prev_cost = channel_cost_on_date(d, channel)
            upsert_channel_cost_daily(date_iso=d, channel=channel, cost=proposed_cost, updated_at=ts)
            run_rows.append((plan_id, item_id, d, channel, float(prev_cost), proposed_cost, ts))
        insert_budget_plan_cost_runs(run_rows)
        update_budget_plan_item_status(item_id=item_id, status="applied", applied_at=ts, updated_at=ts)
        finish_execution_run(
            run_id=run_id,
            status="applied",
            response_json=json.dumps({"rows": len(run_rows), "mode": str(connector.get("mode") or "simulate"), "connector_result": exec_result}, ensure_ascii=False),
            finished_at=ts,
        )
        applied += 1

    if applied > 0:
        update_budget_plan_status(plan_id=plan_id, status="in_progress")
    return {"ok": True, "plan_id": plan_id, "applied": applied, "blocked": blocked}


@app.post("/api/admin/experiments")
def admin_experiment_create(req: Request, data: ExperimentCreateIn, token: Optional[str] = None) -> Dict[str, Any]:
    _require_admin(req, token=token)
    eid = create_experiment(
        name=data.name,
        scope=data.scope,
        metric_primary=data.metric_primary,
        allocation_mode=data.allocation_mode,
        created_at=now_iso(),
    )
    arms_payload = [
        (str(a.arm_key).strip().lower(), str(a.label), float(a.weight), json.dumps(a.config or {}, ensure_ascii=False))
        for a in data.arms
    ]
    upsert_experiment_arms(experiment_id=eid, arms=arms_payload)
    return {"ok": True, "experiment_id": eid}


@app.get("/api/admin/experiments")
def admin_experiments(req: Request, status: str = "", limit: int = 40, token: Optional[str] = None) -> Dict[str, Any]:
    if limit < 1 or limit > 200:
        raise HTTPException(status_code=400, detail="limit must be in range 1..200")
    _require_admin(req, token=token)
    out = []
    for x in list_experiments(limit=limit, status=status):
        out.append({**x, "arms": list_experiment_arms(int(x.get("id") or 0))})
    return {"ok": True, "items": out}


@app.post("/api/admin/experiments/{experiment_id}/status")
def admin_experiment_status(req: Request, experiment_id: int, data: ExperimentStatusIn, token: Optional[str] = None) -> Dict[str, Any]:
    _require_admin(req, token=token)
    st = (data.status or "").strip().lower()
    if st not in {"draft", "running", "paused", "completed"}:
        raise HTTPException(status_code=400, detail="invalid status")
    changed = update_experiment_status(experiment_id=experiment_id, status=st, updated_at=now_iso())
    if changed < 1:
        raise HTTPException(status_code=404, detail="experiment not found")
    return {"ok": True, "experiment_id": experiment_id, "status": st}


@app.post("/api/admin/experiments/{experiment_id}/assign")
def admin_experiment_assign(req: Request, experiment_id: int, data: ExperimentAssignIn, token: Optional[str] = None) -> Dict[str, Any]:
    _require_admin(req, token=token)
    arm = _pick_experiment_arm(experiment_id=experiment_id, session_id=(data.session_id or "").strip())
    if not arm:
        raise HTTPException(status_code=404, detail="experiment not running or no arms")
    insert_experiment_event(
        experiment_id=experiment_id,
        arm_key=str(arm.get("arm_key") or ""),
        event_type="exposure",
        value=1.0,
        session_id=(data.session_id or "").strip(),
        lead_id="",
        created_at=now_iso(),
    )
    cfg = {}
    try:
        cfg = json.loads(arm.get("config_json") or "{}")
    except Exception:
        cfg = {}
    return {"ok": True, "experiment_id": experiment_id, "arm_key": arm.get("arm_key"), "label": arm.get("label"), "config": cfg}


@app.post("/api/admin/experiments/{experiment_id}/event")
def admin_experiment_event(req: Request, experiment_id: int, data: ExperimentEventIn, token: Optional[str] = None) -> Dict[str, Any]:
    _require_admin(req, token=token)
    exp = get_experiment(experiment_id)
    if not exp:
        raise HTTPException(status_code=404, detail="experiment not found")
    insert_experiment_event(
        experiment_id=experiment_id,
        arm_key=(data.arm_key or "").strip().lower(),
        event_type=(data.event_type or "").strip().lower(),
        value=float(data.value),
        session_id=(data.session_id or "").strip(),
        lead_id=(data.lead_id or "").strip(),
        created_at=now_iso(),
    )
    return {"ok": True, "experiment_id": experiment_id}


@app.get("/api/admin/experiments/{experiment_id}/summary")
def admin_experiment_summary(req: Request, experiment_id: int, token: Optional[str] = None) -> Dict[str, Any]:
    _require_admin(req, token=token)
    exp = get_experiment(experiment_id)
    if not exp:
        raise HTTPException(status_code=404, detail="experiment not found")
    arms = list_experiment_arms(experiment_id=experiment_id)
    events = list_experiment_events(experiment_id=experiment_id, limit=12000)
    stats: Dict[str, Dict[str, float]] = {}
    for a in arms:
        stats[str(a.get("arm_key") or "")] = {"exposure": 0.0, "wins": 0.0, "revenue": 0.0}
    for ev in events:
        k = str(ev.get("arm_key") or "")
        if k not in stats:
            continue
        t = str(ev.get("event_type") or "")
        v = float(ev.get("value") or 0.0)
        if t == "exposure":
            stats[k]["exposure"] += v if v > 0 else 1.0
        elif t in {"win", "conversion"}:
            stats[k]["wins"] += v if v > 0 else 1.0
        elif t == "revenue":
            stats[k]["revenue"] += v
    rows = []
    for a in arms:
        k = str(a.get("arm_key") or "")
        st = stats.get(k) or {"exposure": 0.0, "wins": 0.0, "revenue": 0.0}
        exposure = float(st.get("exposure") or 0.0)
        wins = float(st.get("wins") or 0.0)
        revenue = float(st.get("revenue") or 0.0)
        conv = (wins / exposure * 100.0) if exposure > 0 else 0.0
        rows.append(
            {
                "arm_key": k,
                "label": a.get("label"),
                "weight": a.get("weight"),
                "exposure": round(exposure, 2),
                "wins": round(wins, 2),
                "conversion_pct": round(conv, 2),
                "revenue": round(revenue, 2),
            }
        )
    rows.sort(key=lambda x: (x.get("conversion_pct") or 0.0, x.get("revenue") or 0.0), reverse=True)
    return {"ok": True, "experiment": exp, "rows": rows}


@app.post("/api/admin/targets/commit")
def admin_target_commit(req: Request, data: TargetCommitCreateIn, token: Optional[str] = None) -> Dict[str, Any]:
    _require_admin(req, token=token)
    try:
        d_start = _parse_date_ymd(data.period_start)
        d_end = _parse_date_ymd(data.period_end)
    except Exception:
        raise HTTPException(status_code=400, detail="period_start/period_end must be YYYY-MM-DD")
    if d_end < d_start:
        raise HTTPException(status_code=400, detail="period_end must be >= period_start")
    ts = now_iso()
    commit_id = create_target_commit(
        period_start=data.period_start,
        period_end=data.period_end,
        target_revenue=float(data.target_revenue),
        owner=(data.owner or "ops").strip()[:80],
        status="active",
        created_at=ts,
    )
    close_other_target_commits(active_commit_id=commit_id, updated_at=ts)
    return {"ok": True, "commit_id": commit_id}


@app.get("/api/admin/targets/current")
def admin_target_current(req: Request, include_test: bool = False, include_spam: bool = False, token: Optional[str] = None) -> Dict[str, Any]:
    _require_admin(req, token=token)
    snapshot = _target_commit_snapshot(include_test=include_test, include_spam=include_spam)
    if not snapshot:
        return {"ok": True, "commit": None}
    commit = snapshot.get("commit") or {}
    rows = list_target_daily_snapshots(commit_id=int(commit.get("id") or 0), limit=60)
    out_rows = []
    for x in rows:
        rec = []
        try:
            rec = json.loads(x.get("recommendations_json") or "[]")
        except Exception:
            rec = []
        out_rows.append({**x, "recommendations": rec})
    return {"ok": True, "snapshot": snapshot, "history": out_rows}


@app.get("/api/admin/targets/trajectory")
def admin_target_trajectory(req: Request, limit: int = 30, token: Optional[str] = None) -> Dict[str, Any]:
    if limit < 1 or limit > 180:
        raise HTTPException(status_code=400, detail="limit must be in range 1..180")
    _require_admin(req, token=token)
    commit = get_active_target_commit()
    if not commit:
        return {"ok": True, "items": []}
    rows = list_target_daily_snapshots(commit_id=int(commit.get("id") or 0), limit=limit)
    items = []
    for x in rows:
        items.append(
            {
                "day_iso": x.get("day_iso"),
                "actual_revenue": float(x.get("actual_revenue") or 0.0),
                "expected_revenue": float(x.get("expected_revenue") or 0.0),
                "gap": float(x.get("gap") or 0.0),
                "risk_level": x.get("risk_level"),
            }
        )
    items.reverse()
    return {"ok": True, "commit": commit, "items": items}


@app.post("/api/admin/autonomous/run-daily")
def admin_autonomous_run_daily(
    req: Request,
    include_test: bool = False,
    include_spam: bool = False,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    _require_admin(req, token=token)
    summary = _autonomous_daily_run(include_test=include_test, include_spam=include_spam)
    return {"ok": True, "summary": summary}


@app.get("/api/admin/autonomous/run-log")
def admin_autonomous_run_log(req: Request, run_type: str = "", limit: int = 80, token: Optional[str] = None) -> Dict[str, Any]:
    if limit < 1 or limit > 300:
        raise HTTPException(status_code=400, detail="limit must be in range 1..300")
    _require_admin(req, token=token)
    rows = []
    for x in list_autonomous_run_log(run_type=run_type, limit=limit):
        summary = {}
        try:
            summary = json.loads(x.get("summary_json") or "{}")
        except Exception:
            summary = {}
        rows.append({**x, "summary": summary})
    return {"ok": True, "items": rows}


@app.post("/api/admin/guardrails/scan")
def admin_guardrails_scan(
    req: Request,
    days: int = 30,
    include_test: bool = False,
    include_spam: bool = False,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    _require_admin(req, token=token)
    findings = _build_guardrail_findings(days=days, include_test=include_test, include_spam=include_spam)
    ts = now_iso()
    saved_ids: List[int] = []
    for f in findings:
        incident_type = str(f.get("incident_type") or "")
        channel = str(f.get("channel") or "")
        title = str(f.get("title") or "")
        fp = _guardrail_fingerprint(incident_type=incident_type, channel=channel, title=title)
        incident_id = upsert_guardrail_incident(
            fingerprint=fp,
            severity=str(f.get("severity") or "medium"),
            incident_type=incident_type,
            channel=channel,
            title=title,
            details_json=json.dumps(f.get("details") or {}, ensure_ascii=False),
            now_iso=ts,
        )
        if incident_id > 0:
            saved_ids.append(incident_id)
    tasks_created = _sync_incident_tasks_from_open_incidents(limit=120)
    open_items = list_guardrail_incidents(status="open", limit=200)
    return {
        "ok": True,
        "days": days,
        "detected": len(findings),
        "saved_ids": saved_ids,
        "open_total": len(open_items),
        "tasks_created": tasks_created,
    }


@app.get("/api/admin/guardrails/incidents")
def admin_guardrails_incidents(
    req: Request,
    status: str = "",
    limit: int = 100,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="limit must be in range 1..500")
    _require_admin(req, token=token)
    status_value = (status or "").strip().lower()
    if status_value and status_value not in {"open", "ack", "resolved"}:
        raise HTTPException(status_code=400, detail="status must be open/ack/resolved")
    rows = list_guardrail_incidents(status=status_value, limit=limit)
    out: List[Dict[str, Any]] = []
    for x in rows:
        details = {}
        try:
            details = json.loads(x.get("details_json") or "{}")
        except Exception:
            details = {}
        out.append(
            {
                "id": x.get("id"),
                "created_at": x.get("created_at"),
                "updated_at": x.get("updated_at"),
                "severity": x.get("severity"),
                "incident_type": x.get("incident_type"),
                "channel": x.get("channel"),
                "title": x.get("title"),
                "status": x.get("status"),
                "acknowledged_at": x.get("acknowledged_at"),
                "resolved_at": x.get("resolved_at"),
                "details": details,
            }
        )
    return {"ok": True, "items": out}


@app.post("/api/admin/guardrails/incidents/{incident_id}/status")
def admin_guardrails_incident_status(
    req: Request,
    incident_id: int,
    data: GuardrailIncidentStatusIn,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    _require_admin(req, token=token)
    status_value = (data.status or "").strip().lower()
    if status_value not in {"open", "ack", "resolved"}:
        raise HTTPException(status_code=400, detail="status must be open/ack/resolved")
    changed = update_guardrail_incident_status(incident_id=incident_id, status=status_value, now_iso=now_iso())
    if changed < 1:
        raise HTTPException(status_code=404, detail="incident not found")
    return {"ok": True, "incident_id": incident_id, "status": status_value}


@app.post("/api/admin/guardrails/tasks/sync")
def admin_guardrails_tasks_sync(req: Request, token: Optional[str] = None) -> Dict[str, Any]:
    _require_admin(req, token=token)
    created = _sync_incident_tasks_from_open_incidents(limit=200)
    return {"ok": True, "created": created}


def _incident_task_enrich(row: Dict[str, Any], now_dt: datetime) -> Dict[str, Any]:
    due_at = str(row.get("due_at") or "")
    due_dt = _safe_dt(due_at)
    overdue_hours = 0.0
    overdue_since = row.get("overdue_since")
    if due_dt and now_dt > due_dt and str(row.get("status") or "") in {"pending", "in_progress"}:
        overdue_hours = round((now_dt - due_dt).total_seconds() / 3600.0, 2)
        if not overdue_since:
            overdue_since = due_at
    sla_bucket = "on_time"
    if overdue_hours > 24:
        sla_bucket = "24h+"
    elif overdue_hours > 4:
        sla_bucket = "4-24h"
    elif overdue_hours > 0:
        sla_bucket = "0-4h"
    out = dict(row)
    out["overdue_since"] = overdue_since
    out["overdue_hours"] = overdue_hours
    out["sla_bucket"] = sla_bucket
    return out


def _dispatch_p1_sla_alerts(rows: List[Dict[str, Any]], now_dt: datetime) -> int:
    alert_email = (os.getenv("OPS_ALERT_EMAIL") or os.getenv("LEAD_NOTIFY_TO") or "").strip()
    sent = 0
    for row in rows:
        if str(row.get("priority") or "").upper() != "P1":
            continue
        if str(row.get("status") or "") not in {"pending", "in_progress"}:
            continue
        bucket = str(row.get("sla_bucket") or "")
        if bucket not in {"0-4h", "4-24h", "24h+"}:
            continue
        if str(row.get("last_sla_alert_bucket") or "") == bucket:
            continue
        task_id = int(row.get("id") or 0)
        if task_id <= 0:
            continue
        text = (
            f"P1 SLA alert [{bucket}] task={task_id} incident={row.get('incident_id')} "
            f"owner={row.get('owner')} title={row.get('title')} due_at={row.get('due_at')}"
        )
        if alert_email:
            _smtp_send(f"[OPS] {text}", text, alert_email)
        _slack_send(text)
        mark_incident_task_sla_alert(task_id=task_id, bucket=bucket, now_iso=now_dt.isoformat())
        sent += 1
    return sent


@app.get("/api/admin/guardrails/tasks")
def admin_guardrails_tasks(req: Request, status: str = "", limit: int = 120, token: Optional[str] = None) -> Dict[str, Any]:
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="limit must be in range 1..500")
    _require_admin(req, token=token)
    status_value = (status or "").strip().lower()
    if status_value and status_value not in {"pending", "in_progress", "done", "cancelled"}:
        raise HTTPException(status_code=400, detail="status must be pending/in_progress/done/cancelled")
    rows = list_incident_tasks(status=status_value, limit=limit)
    now_dt = datetime.now(timezone.utc)
    out: List[Dict[str, Any]] = []
    for x in rows:
        payload = {}
        try:
            payload = json.loads(x.get("payload_json") or "{}")
        except Exception:
            payload = {}
        enriched = _incident_task_enrich(x, now_dt=now_dt)
        out.append(
            {
                "id": enriched.get("id"),
                "incident_id": enriched.get("incident_id"),
                "created_at": enriched.get("created_at"),
                "updated_at": enriched.get("updated_at"),
                "due_at": enriched.get("due_at"),
                "owner": enriched.get("owner"),
                "priority": enriched.get("priority") or "P2",
                "title": enriched.get("title"),
                "action_type": enriched.get("action_type"),
                "status": enriched.get("status"),
                "done_at": enriched.get("done_at"),
                "overdue_since": enriched.get("overdue_since"),
                "overdue_hours": enriched.get("overdue_hours"),
                "sla_bucket": enriched.get("sla_bucket"),
                "retry_count": int(enriched.get("retry_count") or 0),
                "reopen_count": int(enriched.get("reopen_count") or 0),
                "last_sla_alert_bucket": enriched.get("last_sla_alert_bucket"),
                "last_sla_alert_at": enriched.get("last_sla_alert_at"),
                "payload": payload,
            }
        )
    alerts_sent = _dispatch_p1_sla_alerts(out, now_dt=now_dt)
    return {"ok": True, "items": out, "sla_alerts_sent": alerts_sent}


@app.post("/api/admin/guardrails/tasks/{task_id}/status")
def admin_guardrails_task_status(
    req: Request,
    task_id: int,
    data: IncidentTaskStatusIn,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    _require_admin(req, token=token)
    status_value = (data.status or "").strip().lower()
    if status_value not in {"pending", "in_progress", "done", "cancelled"}:
        raise HTTPException(status_code=400, detail="status must be pending/in_progress/done/cancelled")
    priority_value = (data.priority or "").strip().upper()
    if priority_value and priority_value not in {"P1", "P2", "P3"}:
        raise HTTPException(status_code=400, detail="priority must be P1/P2/P3")
    actor_value = _admin_actor(req, actor_hint=(data.actor or ""))
    changed = update_incident_task_status(
        task_id=task_id,
        status=status_value,
        owner=(data.owner or "").strip()[:80],
        priority=priority_value,
        now_iso=now_iso(),
        actor=actor_value,
        reason=(data.reason or "").strip()[:300],
        expected_updated_at=(data.expected_updated_at or "").strip(),
    )
    if changed == -1:
        raise HTTPException(status_code=409, detail="task was updated by another user, refresh and retry")
    if changed < 1:
        raise HTTPException(status_code=404, detail="task not found")
    task = get_incident_task(task_id)
    return {"ok": True, "task_id": task_id, "status": status_value, "task": task}


@app.post("/api/admin/guardrails/tasks/batch/done")
def admin_guardrails_task_batch_done(req: Request, data: IncidentTaskBatchIn, token: Optional[str] = None) -> Dict[str, Any]:
    _require_admin(req, token=token)
    items = list(data.items or [])
    if not items:
        raise HTTPException(status_code=400, detail="items required")
    actor_value = _admin_actor(req, actor_hint=(data.actor or ""))
    ts = now_iso()
    changed = 0
    conflicts: List[int] = []
    ids: List[int] = []
    for item in items:
        tid = int(item.task_id)
        ids.append(tid)
        rowcount = update_incident_task_status(
            task_id=tid,
            status="done",
            now_iso=ts,
            actor=actor_value,
            reason=((data.reason or "").strip() or "batch_done")[:300],
            expected_updated_at=(item.expected_updated_at or "").strip(),
        )
        if rowcount == -1:
            conflicts.append(tid)
        elif rowcount > 0:
            changed += rowcount
    return {"ok": True, "changed": changed, "task_ids": ids, "conflicts": conflicts}


@app.post("/api/admin/guardrails/tasks/batch/postpone")
def admin_guardrails_task_batch_postpone(req: Request, data: IncidentTaskBatchIn, token: Optional[str] = None) -> Dict[str, Any]:
    _require_admin(req, token=token)
    items = list(data.items or [])
    if not items:
        raise HTTPException(status_code=400, detail="items required")
    actor_value = _admin_actor(req, actor_hint=(data.actor or ""))
    ts = now_iso()
    changed = 0
    conflicts: List[int] = []
    ids: List[int] = []
    for item in items:
        tid = int(item.task_id)
        ids.append(tid)
        task = get_incident_task(tid)
        if not task:
            continue
        due_dt = _safe_dt(str(task.get("due_at") or "")) or datetime.now(timezone.utc)
        next_due = (due_dt + timedelta(hours=24)).isoformat()
        rowcount = update_incident_task_status(
            task_id=tid,
            now_iso=ts,
            due_at=next_due,
            actor=actor_value,
            reason=((data.reason or "").strip() or "batch_postpone_24h")[:300],
            expected_updated_at=(item.expected_updated_at or "").strip(),
        )
        if rowcount == -1:
            conflicts.append(tid)
        elif rowcount > 0:
            changed += rowcount
    return {"ok": True, "changed": changed, "task_ids": ids, "conflicts": conflicts}


@app.get("/api/admin/guardrails/tasks/audit")
def admin_guardrails_task_audit(
    req: Request,
    limit: int = 200,
    task_id: int = 0,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    if limit < 1 or limit > 1000:
        raise HTTPException(status_code=400, detail="limit must be in range 1..1000")
    _require_admin(req, token=token)
    rows = list_incident_task_audit(limit=limit, task_id=max(0, int(task_id)))
    out: List[Dict[str, Any]] = []
    for x in rows:
        change = {}
        try:
            change = json.loads(x.get("change_json") or "{}")
        except Exception:
            change = {}
        out.append(
            {
                "id": x.get("id"),
                "task_id": x.get("task_id"),
                "actor": x.get("actor"),
                "action": x.get("action"),
                "change": change,
                "created_at": x.get("created_at"),
            }
        )
    return {"ok": True, "items": out}


@app.get("/api/admin/channel-costs")
def admin_channel_costs(req: Request, days: int = 30, token: Optional[str] = None) -> Dict[str, Any]:
    if days < 1 or days > 365:
        raise HTTPException(status_code=400, detail="days must be in range 1..365")
    _require_admin(req, token=token)
    now_dt = datetime.now(timezone.utc)
    start_dt = now_dt - timedelta(days=days)
    rows = list_channel_costs_between(start_dt.date().isoformat(), now_dt.date().isoformat())
    return {"ok": True, "days": days, "items": rows}


@app.post("/api/admin/channel-costs")
def admin_channel_costs_upsert(req: Request, data: ChannelCostIn, token: Optional[str] = None) -> Dict[str, Any]:
    _require_admin(req, token=token)
    try:
        datetime.fromisoformat((data.date_iso or "").strip())
    except Exception:
        raise HTTPException(status_code=400, detail="date_iso must be YYYY-MM-DD")
    channel = (data.channel or "").strip().lower()[:120]
    if not channel:
        raise HTTPException(status_code=400, detail="channel is required")
    upsert_channel_cost_daily(
        date_iso=(data.date_iso or "").strip(),
        channel=channel,
        cost=float(data.cost),
        updated_at=now_iso(),
    )
    return {"ok": True, "date_iso": data.date_iso, "channel": channel, "cost": float(data.cost)}


@app.post("/api/admin/channel-costs/import-csv")
def admin_channel_costs_import_csv(req: Request, data: ChannelCostCsvImportIn, token: Optional[str] = None) -> Dict[str, Any]:
    _require_admin(req, token=token)
    text = (data.csv_text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="csv_text is required")
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        raise HTTPException(status_code=400, detail="empty csv")

    start_idx = 0
    head = [str(x or "").strip().lower() for x in rows[0]]
    if len(head) >= 3 and ("date" in head[0] or "date_iso" in head[0]) and "channel" in head[1]:
        start_idx = 1

    imported = 0
    errors: List[str] = []
    for i, row in enumerate(rows[start_idx:], start=start_idx + 1):
        if not row or len(row) < 3:
            continue
        date_iso = str(row[0] or "").strip()
        channel = str(row[1] or "").strip().lower()
        cost_raw = str(row[2] or "").strip().replace(",", ".")
        try:
            datetime.fromisoformat(date_iso)
            if not channel:
                raise ValueError("channel")
            cost = float(cost_raw)
            if cost < 0:
                raise ValueError("cost")
            upsert_channel_cost_daily(date_iso=date_iso, channel=channel[:120], cost=cost, updated_at=now_iso())
            imported += 1
        except Exception:
            errors.append(f"line {i}: invalid row")
    return {"ok": True, "imported": imported, "errors": errors[:200]}


@app.get("/api/admin/leads")
def admin_leads(
    req: Request,
    limit: int = 50,
    form_type: str = "",
    status: str = "",
    tier: str = "",
    autopilot_priority: str = "",
    autopilot_action: str = "",
    win_recommendation: str = "",
    include_win: bool = False,
    duplicates_only: bool = False,
    include_test: bool = False,
    include_spam: bool = False,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    if limit < 1 or limit > 200:
        raise HTTPException(status_code=400, detail="limit must be in range 1..200")
    _require_admin(req, token=token)

    tier_filter = (tier or "").strip().lower()
    priority_filter = (autopilot_priority or "").strip().upper()
    action_filter = (autopilot_action or "").strip().lower()
    win_reco_filter = (win_recommendation or "").strip().lower()
    if win_reco_filter and win_reco_filter not in {"push", "nurture", "drop"}:
        raise HTTPException(status_code=400, detail="win_recommendation must be push/nurture/drop")
    include_win_effective = bool((include_win or win_reco_filter) and _win_model_enabled())
    win_model = _win_model_snapshot(days=120, include_test=include_test, include_spam=include_spam) if include_win_effective else {}
    rows = list_recent_leads(
        limit=max(limit * 4, limit),
        form_type=form_type,
        status=normalize_lead_status(status) if status else "",
        include_test=include_test,
        include_spam=include_spam,
    )
    email_counts: Dict[str, int] = {}
    parsed_payloads: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        rid = str(row.get("id") or "")
        payload = {}
        try:
            payload = json.loads(row.get("payload_json") or "{}")
        except Exception:
            payload = {}
        parsed_payloads[rid] = payload
        _sequence_ensure_for_lead(
            lead_id=rid,
            created_at=row.get("created_at"),
            lead_status=str(row.get("lead_status") or "new"),
            is_test=bool(int(row.get("is_test") or 0)),
            is_spam=bool(int(row.get("is_spam") or 0)),
        )
        em = _lead_email(payload).lower()
        if em:
            email_counts[em] = email_counts.get(em, 0) + 1
    progress_map = sequence_progress_for_leads([str(x.get("id") or "") for x in rows if str(x.get("id") or "")])

    out = []
    for row in rows:
        rid = str(row.get("id") or "")
        payload = parsed_payloads.get(rid, {})
        lead_status = str(row.get("lead_status") or "new")
        score = _lead_score(str(row.get("form_type") or ""), payload, lead_status)
        lead_tier = _lead_tier(score)
        if _autopilot_enabled():
            decision = _autopilot_decision(
                form_type=str(row.get("form_type") or ""),
                payload=payload,
                lead_status=lead_status,
                is_test=bool(int(row.get("is_test") or 0)),
                is_spam=bool(int(row.get("is_spam") or 0)),
                last_contact_at=row.get("last_contact_at"),
            )
        else:
            decision = {
                "priority": str(row.get("autopilot_priority") or "P3"),
                "next_action": str(row.get("autopilot_next_action") or "review"),
                "next_action_due_at": row.get("autopilot_next_action_due_at"),
                "owner_queue": str(row.get("autopilot_owner_queue") or "sales"),
            }
        row_priority = str(row.get("autopilot_priority") or decision.get("priority") or "P3").upper()
        row_action = str(row.get("autopilot_next_action") or decision.get("next_action") or "review").lower()
        win_pred = (
            _predict_win_probability(row=row, payload=payload, score=score, tier=lead_tier, model=win_model)
            if include_win_effective
            else {}
        )
        if not include_win_effective:
            stored_prob = row.get("win_probability")
            stored_reco = str(row.get("win_recommendation") or "")
            stored_ver = str(row.get("win_model_version") or "")
            if stored_prob is not None:
                win_pred = {
                    "probability_pct": float(stored_prob),
                    "recommendation": (stored_reco or None),
                    "model_version": (stored_ver or None),
                    "reason": "",
                }
        if tier_filter and lead_tier != tier_filter:
            continue
        if priority_filter and row_priority != priority_filter:
            continue
        if action_filter and row_action != action_filter:
            continue
        if win_reco_filter and str(win_pred.get("recommendation") or "") != win_reco_filter:
            continue
        em = _lead_email(payload).lower()
        duplicate_count = email_counts.get(em, 0) if em else 0
        is_duplicate = duplicate_count > 1
        if duplicates_only and not is_duplicate:
            continue
        seq_tasks = list_sequence_tasks_by_lead(rid)
        pending_tasks = [t for t in seq_tasks if str(t.get("status") or "") == "pending"]
        pending_tasks.sort(key=lambda t: str(t.get("due_at") or ""))
        seq_next = pending_tasks[0] if pending_tasks else None
        seq_prog = progress_map.get(rid, {"pending": 0, "done": 0, "skipped": 0, "total": 0})
        booking_token = str(row.get("booking_token") or "")
        booking_url = _booking_link(rid, booking_token) if booking_token else ""
        out.append(
            {
                "id": row.get("id"),
                "form_type": row.get("form_type"),
                "source_path": row.get("source_path"),
                "created_at": row.get("created_at"),
                "lead_status": lead_status,
                "lead_notes": row.get("lead_notes") or "",
                "lead_follow_up_at": row.get("lead_follow_up_at"),
                "lead_score": score,
                "lead_tier": lead_tier,
                "is_duplicate": is_duplicate,
                "duplicate_count": duplicate_count,
                "is_test": bool(int(row.get("is_test") or 0)),
                "is_spam": bool(int(row.get("is_spam") or 0)),
                "spam_reason": row.get("spam_reason") or "",
                "booked_at": row.get("booked_at"),
                "booked_slot": row.get("booked_slot"),
                "deal_value": float(row.get("deal_value") or 0.0),
                "last_contact_at": row.get("last_contact_at"),
                "lost_reason": row.get("lost_reason") or "",
                "autopilot_priority": row_priority,
                "autopilot_next_action": row_action,
                "autopilot_next_action_due_at": row.get("autopilot_next_action_due_at") or decision.get("next_action_due_at"),
                "autopilot_owner_queue": row.get("autopilot_owner_queue") or decision.get("owner_queue") or "sales",
                "win_probability": (float(win_pred.get("probability_pct") or 0.0) if win_pred else None),
                "win_probability_pct": (float(win_pred.get("probability_pct") or 0.0) if win_pred else None),
                "win_recommendation": (str(win_pred.get("recommendation") or "nurture") if win_pred else None),
                "win_model_version": (str(win_pred.get("model_version") or WIN_MODEL_VERSION) if win_pred else None),
                "win_reason": (str(win_pred.get("reason") or "") if win_pred else ""),
                "sequence_progress": seq_prog,
                "sequence_next_step_code": (seq_next or {}).get("step_code"),
                "sequence_next_due_at": (seq_next or {}).get("due_at"),
                "booking_url": booking_url,
                "payload": payload,
            }
        )
        if len(out) >= limit:
            break
    return {"ok": True, "leads": out}


@app.post("/api/admin/leads/backfill")
def admin_leads_backfill(req: Request, data: LeadsBackfillIn, token: Optional[str] = None) -> Dict[str, Any]:
    _require_admin(req, token=token)
    limit = int(data.limit)
    include_test = bool(data.include_test)
    include_spam = bool(data.include_spam)
    refresh_autopilot = bool(data.refresh_autopilot and _autopilot_enabled())
    refresh_win = bool(data.refresh_win and _win_model_enabled())

    win_model = _win_model_snapshot(days=120, include_test=include_test, include_spam=include_spam) if refresh_win else {}
    page = 500
    processed = 0
    autopilot_updates = 0
    win_updates = 0
    offset = 0
    while processed < limit:
        batch = list_leads_for_backfill(limit=min(page, limit - processed), offset=offset, include_test=include_test, include_spam=include_spam)
        if not batch:
            break
        for row in batch:
            payload = {}
            try:
                payload = json.loads(row.get("payload_json") or "{}")
            except Exception:
                payload = {}
            if refresh_autopilot:
                _recompute_autopilot_for_row(row, payload)
                autopilot_updates += 1
            if refresh_win:
                score = _lead_score(str(row.get("form_type") or ""), payload, str(row.get("lead_status") or "new"))
                tier = _lead_tier(score)
                pred = _predict_win_probability(row=row, payload=payload, score=score, tier=tier, model=win_model)
                upsert_lead_win_model(
                    lead_id=str(row.get("id") or ""),
                    win_probability=float(pred.get("probability_pct") or 0.0),
                    win_recommendation=str(pred.get("recommendation") or "nurture"),
                    win_model_version=str(pred.get("model_version") or WIN_MODEL_VERSION),
                    updated_at=now_iso(),
                )
                win_updates += 1
        processed += len(batch)
        offset += len(batch)

    return {
        "ok": True,
        "processed": processed,
        "autopilot_updates": autopilot_updates,
        "win_updates": win_updates,
        "autopilot_enabled": _autopilot_enabled(),
        "win_model_enabled": _win_model_enabled(),
    }


def _safe_dt(value: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat((value or "").replace("Z", "+00:00"))
    except Exception:
        return None


def _safe_json_dict(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    try:
        data = json.loads(raw or "{}")
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _analytics_segments_from_events(events: List[Dict[str, Any]], limit: int = 12) -> Dict[str, Any]:
    area_counts: Dict[str, int] = {}
    kind_counts: Dict[str, int] = {}
    page_type_counts: Dict[str, int] = {}
    form_name_counts: Dict[str, int] = {}
    cta_matrix: Dict[Tuple[str, str, str], int] = {}

    total_events = 0
    total_cta = 0
    total_submit = 0

    for ev in events:
        total_events += 1
        event_name = str(ev.get("event_name") or "")
        payload = _safe_json_dict(ev.get("payload_json"))

        page_type = str(payload.get("page_type") or "unknown")
        page_type_counts[page_type] = page_type_counts.get(page_type, 0) + 1

        if event_name == "cta_click":
            total_cta += 1
            area = str(payload.get("cta_area") or "unknown")
            kind = str(payload.get("cta_kind") or "unknown")
            label = str(ev.get("label") or "(no-label)")
            area_counts[area] = area_counts.get(area, 0) + 1
            kind_counts[kind] = kind_counts.get(kind, 0) + 1
            key = (label, area, kind)
            cta_matrix[key] = cta_matrix.get(key, 0) + 1

        if event_name == "form_submit":
            total_submit += 1
            form_name = str(payload.get("form_name") or ev.get("label") or "unknown")
            form_name_counts[form_name] = form_name_counts.get(form_name, 0) + 1

    def _top(counter: Dict[str, int], key_name: str) -> List[Dict[str, Any]]:
        rows = [{key_name: k, "cnt": int(v)} for k, v in counter.items()]
        rows.sort(key=lambda x: x["cnt"], reverse=True)
        return rows[:limit]

    matrix_rows: List[Dict[str, Any]] = []
    for (label, area, kind), cnt in cta_matrix.items():
        matrix_rows.append({"label": label, "cta_area": area, "cta_kind": kind, "cnt": int(cnt)})
    matrix_rows.sort(key=lambda x: x["cnt"], reverse=True)

    return {
        "totals": {"events": total_events, "cta_click": total_cta, "form_submit": total_submit},
        "top_cta_area": _top(area_counts, "cta_area"),
        "top_cta_kind": _top(kind_counts, "cta_kind"),
        "top_page_type": _top(page_type_counts, "page_type"),
        "top_form_name": _top(form_name_counts, "form_name"),
        "top_cta_matrix": matrix_rows[:limit],
    }


def build_pipeline_report(days: int = 1, include_test: bool = False, include_spam: bool = False) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)
    s_now = now.isoformat()
    s_start = start.isoformat()

    leads = list_leads_between(s_start, s_now, limit=8000, include_test=include_test, include_spam=include_spam)
    events = list_analytics_events_between(s_start, s_now, event_name="", limit=16000)

    cta_by_session: Dict[str, List[Dict[str, Any]]] = {}
    for ev in events:
        if str(ev.get("event_name") or "") != "cta_click":
            continue
        session = str(ev.get("session_id") or "").strip()
        if not session:
            continue
        cta_by_session.setdefault(session, []).append(ev)

    stage_rows: Dict[str, int] = {}
    page_stats: Dict[str, Dict[str, int]] = {}
    cta_stats: Dict[str, Dict[str, int]] = {}

    for lead in leads:
        status = str(lead.get("lead_status") or "new")
        form_type = str(lead.get("form_type") or "other")

        payload = {}
        try:
            payload = json.loads(lead.get("payload_json") or "{}")
        except Exception:
            payload = {}

        source = str(lead.get("source_path") or payload.get("landing_path") or "(unknown)")
        key = f"{source} -> {form_type} -> {status}"
        stage_rows[key] = stage_rows.get(key, 0) + 1

        pstat = page_stats.setdefault(source, {"leads": 0, "won": 0, "lost": 0})
        pstat["leads"] += 1
        if status == "won":
            pstat["won"] += 1
        elif status == "lost":
            pstat["lost"] += 1

        session = str(payload.get("session_id") or "").strip()
        cta_label = "(unattributed)"
        if session and session in cta_by_session:
            lead_dt = _safe_dt(str(lead.get("created_at") or ""))
            pick = None
            for ev in cta_by_session[session]:
                ev_dt = _safe_dt(str(ev.get("created_at") or ""))
                if lead_dt is not None and ev_dt is not None and ev_dt > lead_dt:
                    continue
                pick = ev
            if pick:
                cta_label = str(pick.get("label") or "(no-label)")

        cstat = cta_stats.setdefault(cta_label, {"leads": 0, "won": 0, "lost": 0})
        cstat["leads"] += 1
        if status == "won":
            cstat["won"] += 1
        elif status == "lost":
            cstat["lost"] += 1

    def rank_rows(stats: Dict[str, Dict[str, int]]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for label, st in stats.items():
            leads_n = int(st.get("leads", 0))
            won_n = int(st.get("won", 0))
            lost_n = int(st.get("lost", 0))
            win_rate = round((won_n / leads_n) * 100.0, 2) if leads_n > 0 else 0.0
            rows.append({
                "label": label,
                "leads": leads_n,
                "won": won_n,
                "lost": lost_n,
                "win_rate_pct": win_rate,
            })
        rows.sort(key=lambda x: (x["won"], x["win_rate_pct"], x["leads"]), reverse=True)
        return rows

    return {
        "generated_at": s_now,
        "days": days,
        "filters": {"include_test": include_test, "include_spam": include_spam},
        "totals": {
            "leads": len(leads),
            "won": sum(1 for x in leads if str(x.get("lead_status") or "") == "won"),
            "lost": sum(1 for x in leads if str(x.get("lead_status") or "") == "lost"),
        },
        "stage_rows": [{"stage": k, "count": v} for k, v in sorted(stage_rows.items(), key=lambda kv: kv[1], reverse=True)],
        "ranking_pages": rank_rows(page_stats),
        "ranking_cta": rank_rows(cta_stats),
        "event_segments": _analytics_segments_from_events(events, limit=10),
    }


@app.get("/api/admin/reports/pipeline")
def admin_pipeline_report(
    req: Request,
    days: int = 1,
    include_test: bool = False,
    include_spam: bool = False,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    if days < 1 or days > 90:
        raise HTTPException(status_code=400, detail="days must be in range 1..90")
    _require_admin(req, token=token)
    return {"ok": True, "report": build_pipeline_report(days=days, include_test=include_test, include_spam=include_spam)}


@app.get("/api/admin/cockpit/today")
def admin_cockpit_today(req: Request, limit: int = 120, token: Optional[str] = None) -> Dict[str, Any]:
    if limit < 1 or limit > 300:
        raise HTTPException(status_code=400, detail="limit must be in range 1..300")
    _require_admin(req, token=token)

    rows = leads_pending_touch(limit=limit)
    now_dt = datetime.now(timezone.utc)
    out = []
    for row in rows:
        anchor = _safe_dt(str(row.get("last_contact_at") or "")) or _safe_dt(str(row.get("created_at") or "")) or now_dt
        wait_hours = max(0.0, round((now_dt - anchor).total_seconds() / 3600.0, 2))
        sla_state = "ok"
        if wait_hours >= 48:
            sla_state = "late"
        elif wait_hours >= 24:
            sla_state = "risk"

        payload = {}
        try:
            payload = json.loads(row.get("payload_json") or "{}")
        except Exception:
            payload = {}

        out.append(
            {
                "id": row.get("id"),
                "form_type": row.get("form_type"),
                "created_at": row.get("created_at"),
                "last_contact_at": row.get("last_contact_at"),
                "follow_up_at": row.get("follow_up_at"),
                "lead_status": row.get("lead_status") or "new",
                "lead_notes": row.get("lead_notes") or "",
                "booked_slot": row.get("booked_slot"),
                "wait_hours": wait_hours,
                "sla_state": sla_state,
                "autopilot_priority": row.get("autopilot_priority") or "P3",
                "autopilot_next_action": row.get("autopilot_next_action") or "review",
                "autopilot_next_action_due_at": row.get("autopilot_next_action_due_at"),
                "autopilot_owner_queue": row.get("autopilot_owner_queue") or "sales",
                "email": _lead_email(payload),
                "payload": payload,
            }
        )

    out.sort(key=lambda x: x.get("wait_hours") or 0, reverse=True)
    return {"ok": True, "items": out}


@app.post("/api/admin/leads/{lead_id}/cockpit-action")
def admin_cockpit_action(
    req: Request,
    lead_id: str,
    data: CockpitActionIn,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    _require_admin(req, token=token)

    rows = list_recent_leads(limit=500, include_test=True, include_spam=True)
    target = next((r for r in rows if str(r.get("id") or "") == lead_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="lead not found")

    action = (data.action or "").strip().lower()
    notes = str(target.get("lead_notes") or "")
    follow_up_at = target.get("lead_follow_up_at")
    status = str(target.get("lead_status") or "new")
    lost_reason = str(target.get("lost_reason") or "")
    now_value = now_iso()

    if action == "call_done":
        status = "in_progress"
        notes = (notes + "\n[call_done] " + now_value).strip()
        follow_up_at = None
    elif action == "awaiting_reply":
        status = "in_progress"
        notes = (notes + "\n[awaiting_reply] " + now_value).strip()
        follow_up_at = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    elif action == "lost":
        status = "lost"
        lost_reason = _normalize_lost_reason(data.lost_reason or "")
        if not lost_reason:
            raise HTTPException(status_code=400, detail="lost_reason is required for action=lost")
        notes = (notes + f"\n[lost] {lost_reason}").strip()
        follow_up_at = None
    else:
        raise HTTPException(status_code=400, detail="action must be one of: call_done, awaiting_reply, lost")

    touch_lead_action(
        lead_id=lead_id,
        status=status,
        notes=notes[:8000],
        follow_up_at=parse_or_none(follow_up_at),
        last_contact_at=now_value,
        lost_reason=lost_reason,
        updated_at=now_value,
    )
    if action == "call_done":
        _sequence_mark_action_progress(lead_id=lead_id, action="call_now", timestamp_iso=now_value)
    elif action == "awaiting_reply":
        _sequence_mark_action_progress(lead_id=lead_id, action="follow_up_today", timestamp_iso=now_value)
    elif action == "lost":
        skip_pending_sequence_for_lead(lead_id=lead_id, updated_at=now_value, note="lead_lost")
    refreshed = get_lead_by_id(lead_id)
    if refreshed:
        payload = {}
        try:
            payload = json.loads(refreshed.get("payload_json") or "{}")
        except Exception:
            payload = {}
        _recompute_autopilot_for_row(refreshed, payload)
        _refresh_win_snapshot_for_row(refreshed, payload)
        _sequence_ensure_for_lead(
            lead_id=lead_id,
            created_at=refreshed.get("created_at"),
            lead_status=str(refreshed.get("lead_status") or "new"),
            is_test=bool(int(refreshed.get("is_test") or 0)),
            is_spam=bool(int(refreshed.get("is_spam") or 0)),
        )
    return {"ok": True, "lead_id": lead_id, "status": status, "action": action}

@app.post("/api/admin/leads/{lead_id}/meta")
def admin_update_lead_meta(
    req: Request,
    lead_id: str,
    data: LeadMetaUpdateIn,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    _require_admin(req, token=token)
    status = normalize_lead_status(data.status)
    row = get_lead_by_id(lead_id)
    if not row:
        raise HTTPException(status_code=404, detail="lead not found")
    lost_reason = _normalize_lost_reason(data.lost_reason or row.get("lost_reason") or "")
    if status == "lost" and not lost_reason:
        raise HTTPException(status_code=400, detail="lost_reason is required when status=lost")
    if status == "won" and float(row.get("deal_value") or 0.0) <= 0:
        raise HTTPException(status_code=400, detail="deal_value must be > 0 before setting status=won")
    if status != "lost":
        lost_reason = ""
    follow_up_at = parse_or_none(data.follow_up_at)
    touch_lead_action(
        lead_id=lead_id,
        status=status,
        notes=(data.notes or row.get("lead_notes") or "")[:8000],
        follow_up_at=follow_up_at,
        last_contact_at=row.get("last_contact_at"),
        lost_reason=lost_reason,
        updated_at=now_iso(),
    )
    refreshed = get_lead_by_id(lead_id)
    if refreshed:
        payload = {}
        try:
            payload = json.loads(refreshed.get("payload_json") or "{}")
        except Exception:
            payload = {}
        _recompute_autopilot_for_row(refreshed, payload)
        _refresh_win_snapshot_for_row(refreshed, payload)
        _sequence_ensure_for_lead(
            lead_id=lead_id,
            created_at=refreshed.get("created_at"),
            lead_status=str(refreshed.get("lead_status") or "new"),
            is_test=bool(int(refreshed.get("is_test") or 0)),
            is_spam=bool(int(refreshed.get("is_spam") or 0)),
        )
    return {"ok": True, "lead_id": lead_id, "status": status, "follow_up_at": follow_up_at}


@app.post("/api/admin/leads/{lead_id}/value")
def admin_update_lead_value(
    req: Request,
    lead_id: str,
    data: LeadValueIn,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    _require_admin(req, token=token)
    row = get_lead_by_id(lead_id)
    if not row:
        raise HTTPException(status_code=404, detail="lead not found")
    upsert_lead_value(lead_id=lead_id, deal_value=float(data.deal_value), updated_at=now_iso())
    return {"ok": True, "lead_id": lead_id, "deal_value": float(data.deal_value)}


@app.post("/api/admin/leads/{lead_id}/autopilot/recompute")
def admin_autopilot_recompute(req: Request, lead_id: str, token: Optional[str] = None) -> Dict[str, Any]:
    _require_admin(req, token=token)
    if not _autopilot_enabled():
        return {"ok": True, "enabled": False, "lead_id": lead_id, "autopilot": {}}
    row = get_lead_by_id(lead_id)
    if not row:
        raise HTTPException(status_code=404, detail="lead not found")
    payload = {}
    try:
        payload = json.loads(row.get("payload_json") or "{}")
    except Exception:
        payload = {}
    decision = _recompute_autopilot_for_row(row, payload)
    _refresh_win_snapshot_for_row(row, payload)
    _sequence_ensure_for_lead(
        lead_id=lead_id,
        created_at=row.get("created_at"),
        lead_status=str(row.get("lead_status") or "new"),
        is_test=bool(int(row.get("is_test") or 0)),
        is_spam=bool(int(row.get("is_spam") or 0)),
    )
    return {"ok": True, "lead_id": lead_id, "autopilot": decision}


@app.post("/api/admin/leads/{lead_id}/autopilot/execute")
def admin_autopilot_execute(
    req: Request,
    lead_id: str,
    data: AutopilotExecuteIn,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    _require_admin(req, token=token)
    if not _autopilot_enabled():
        return {"ok": True, "enabled": False, "lead_id": lead_id, "action_executed": None}
    row = get_lead_by_id(lead_id)
    if not row:
        raise HTTPException(status_code=404, detail="lead not found")

    payload = {}
    try:
        payload = json.loads(row.get("payload_json") or "{}")
    except Exception:
        payload = {}
    decision = _recompute_autopilot_for_row(row, payload)
    _refresh_win_snapshot_for_row(row, payload)
    _sequence_ensure_for_lead(
        lead_id=lead_id,
        created_at=row.get("created_at"),
        lead_status=str(row.get("lead_status") or "new"),
        is_test=bool(int(row.get("is_test") or 0)),
        is_spam=bool(int(row.get("is_spam") or 0)),
    )
    action = (data.action or "").strip().lower() or str(decision.get("next_action") or "").strip().lower()

    allowed = {
        "call_now",
        "send_intro_email",
        "follow_up_today",
        "await_reply",
        "enrich_contact",
        "drop_spam",
        "ignore_test",
        "no_action",
        "review",
    }
    if action not in allowed:
        raise HTTPException(status_code=400, detail="invalid autopilot action")

    now_value = now_iso()
    status = str(row.get("lead_status") or "new")
    notes = str(row.get("lead_notes") or "")
    follow_up_at = row.get("lead_follow_up_at")
    lost_reason = str(row.get("lost_reason") or "")
    last_contact_at: Optional[str] = None

    if action in {"call_now", "send_intro_email", "follow_up_today", "await_reply"}:
        status = "in_progress"
        notes = (notes + f"\n[autopilot:{action}] {now_value}").strip()
        follow_up_at = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
        last_contact_at = now_value
    elif action == "enrich_contact":
        notes = (notes + f"\n[autopilot:{action}] {now_value}").strip()
        follow_up_at = (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat()
    elif action == "drop_spam":
        status = "lost"
        lost_reason = "autopilot_spam"
        notes = (notes + f"\n[autopilot:{action}] {now_value}").strip()
        follow_up_at = None
    else:
        notes = (notes + f"\n[autopilot:{action}] {now_value}").strip()

    touch_lead_action(
        lead_id=lead_id,
        status=status,
        notes=notes[:8000],
        follow_up_at=parse_or_none(follow_up_at),
        last_contact_at=last_contact_at,
        lost_reason=lost_reason,
        updated_at=now_value,
    )
    _sequence_mark_action_progress(lead_id=lead_id, action=action, timestamp_iso=now_value)
    if status in {"won", "lost"}:
        skip_pending_sequence_for_lead(lead_id=lead_id, updated_at=now_value, note=f"lead_{status}")

    updated = get_lead_by_id(lead_id)
    next_decision = decision
    if updated:
        updated_payload = {}
        try:
            updated_payload = json.loads(updated.get("payload_json") or "{}")
        except Exception:
            updated_payload = {}
        next_decision = _recompute_autopilot_for_row(updated, updated_payload)
        _refresh_win_snapshot_for_row(updated, updated_payload)
        _sequence_ensure_for_lead(
            lead_id=lead_id,
            created_at=updated.get("created_at"),
            lead_status=str(updated.get("lead_status") or "new"),
            is_test=bool(int(updated.get("is_test") or 0)),
            is_spam=bool(int(updated.get("is_spam") or 0)),
        )

    return {
        "ok": True,
        "lead_id": lead_id,
        "action_executed": action,
        "status": status,
        "follow_up_at": parse_or_none(follow_up_at),
        "autopilot_next": next_decision,
    }


@app.get("/api/admin/followups/templates")
def admin_followup_templates(req: Request, token: Optional[str] = None) -> Dict[str, Any]:
    _require_admin(req, token=token)
    return {"ok": True, "templates": list_followup_templates()}


@app.post("/api/admin/followups/templates/{step_hours}")
def admin_update_followup_template(
    req: Request,
    step_hours: int,
    data: FollowupTemplateIn,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    _require_admin(req, token=token)
    if step_hours not in {24, 72}:
        raise HTTPException(status_code=400, detail="step_hours must be 24 or 72")
    upsert_followup_template(
        step_hours=step_hours,
        subject_template=data.subject_template,
        body_template=data.body_template,
        updated_at=now_iso(),
    )
    return {"ok": True, "step_hours": step_hours}


@app.get("/api/admin/followups/logs")
def admin_followup_logs(req: Request, limit: int = 80, token: Optional[str] = None) -> Dict[str, Any]:
    if limit < 1 or limit > 300:
        raise HTTPException(status_code=400, detail="limit must be in range 1..300")
    _require_admin(req, token=token)
    return {"ok": True, "logs": list_followup_logs(limit=limit)}


@app.get("/api/admin/followups/due")
def admin_followup_due(req: Request, limit: int = 80, token: Optional[str] = None) -> Dict[str, Any]:
    if limit < 1 or limit > 300:
        raise HTTPException(status_code=400, detail="limit must be in range 1..300")
    _require_admin(req, token=token)

    rows = list_due_followups(now_iso=now_iso(), limit=limit)
    out = []
    for row in rows:
        payload = {}
        try:
            payload = json.loads(row.get("payload_json") or "{}")
        except Exception:
            payload = {}
        score = _lead_score(
            form_type=str(row.get("form_type") or ""),
            payload=payload,
            lead_status=str(row.get("lead_status") or "new"),
        )
        out.append(
            {
                "id": row.get("id"),
                "form_type": row.get("form_type"),
                "created_at": row.get("created_at"),
                "follow_up_at": row.get("follow_up_at"),
                "lead_status": row.get("lead_status") or "new",
                "lead_notes": row.get("lead_notes") or "",
                "lead_score": score,
                "lead_tier": _lead_tier(score),
                "payload": payload,
            }
        )
    return {"ok": True, "due": out}


@app.get("/api/admin/sequence/due")
def admin_sequence_due(req: Request, limit: int = 100, token: Optional[str] = None) -> Dict[str, Any]:
    if limit < 1 or limit > 300:
        raise HTTPException(status_code=400, detail="limit must be in range 1..300")
    _require_admin(req, token=token)
    rows = list_due_sequence_tasks(now_iso=now_iso(), limit=limit)
    out: List[Dict[str, Any]] = []
    for row in rows:
        payload = {}
        try:
            payload = json.loads(row.get("payload_json") or "{}")
        except Exception:
            payload = {}
        score = _lead_score(
            form_type=str(row.get("form_type") or ""),
            payload=payload,
            lead_status=str(row.get("lead_status") or "new"),
        )
        due_dt = _safe_dt(str(row.get("due_at") or ""))
        now_dt = datetime.now(timezone.utc)
        overdue_hours = 0.0
        if due_dt is not None:
            overdue_hours = round(max(0.0, (now_dt - due_dt).total_seconds() / 3600.0), 2)
        out.append(
            {
                "lead_id": row.get("lead_id"),
                "step_code": row.get("step_code"),
                "due_at": row.get("due_at"),
                "status": row.get("status"),
                "note": row.get("note") or "",
                "lead_status": row.get("lead_status") or "new",
                "form_type": row.get("form_type") or "",
                "created_at": row.get("created_at"),
                "email": _lead_email(payload),
                "lead_score": score,
                "lead_tier": _lead_tier(score),
                "overdue_hours": overdue_hours,
            }
        )
    return {"ok": True, "items": out}


@app.get("/api/admin/leads/{lead_id}/sequence")
def admin_lead_sequence(req: Request, lead_id: str, token: Optional[str] = None) -> Dict[str, Any]:
    _require_admin(req, token=token)
    row = get_lead_by_id(lead_id)
    if not row:
        raise HTTPException(status_code=404, detail="lead not found")
    _sequence_ensure_for_lead(
        lead_id=lead_id,
        created_at=row.get("created_at"),
        lead_status=str(row.get("lead_status") or "new"),
        is_test=bool(int(row.get("is_test") or 0)),
        is_spam=bool(int(row.get("is_spam") or 0)),
    )
    tasks = list_sequence_tasks_by_lead(lead_id=lead_id)
    return {"ok": True, "lead_id": lead_id, "tasks": tasks}


@app.post("/api/admin/leads/{lead_id}/sequence/ensure")
def admin_lead_sequence_ensure(req: Request, lead_id: str, token: Optional[str] = None) -> Dict[str, Any]:
    _require_admin(req, token=token)
    row = get_lead_by_id(lead_id)
    if not row:
        raise HTTPException(status_code=404, detail="lead not found")
    _sequence_ensure_for_lead(
        lead_id=lead_id,
        created_at=row.get("created_at"),
        lead_status=str(row.get("lead_status") or "new"),
        is_test=bool(int(row.get("is_test") or 0)),
        is_spam=bool(int(row.get("is_spam") or 0)),
    )
    return {"ok": True, "lead_id": lead_id}


@app.post("/api/admin/leads/{lead_id}/sequence/{step_code}/done")
def admin_lead_sequence_done(
    req: Request,
    lead_id: str,
    step_code: str,
    data: SequenceTaskDoneIn,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    _require_admin(req, token=token)
    if step_code not in _sequence_step_codes():
        raise HTTPException(status_code=400, detail="invalid step_code")
    row = get_lead_by_id(lead_id)
    if not row:
        raise HTTPException(status_code=404, detail="lead not found")
    _sequence_ensure_for_lead(
        lead_id=lead_id,
        created_at=row.get("created_at"),
        lead_status=str(row.get("lead_status") or "new"),
        is_test=bool(int(row.get("is_test") or 0)),
        is_spam=bool(int(row.get("is_spam") or 0)),
    )
    ts = now_iso()
    mark_sequence_task_status(
        lead_id=lead_id,
        step_code=step_code,
        status="done",
        done_at=ts,
        updated_at=ts,
        note=(data.note or "").strip()[:300],
    )
    tasks = list_sequence_tasks_by_lead(lead_id=lead_id)
    return {"ok": True, "lead_id": lead_id, "step_code": step_code, "tasks": tasks}


@app.post("/api/admin/leads/{lead_id}/sequence/{step_code}/postpone")
def admin_lead_sequence_postpone(
    req: Request,
    lead_id: str,
    step_code: str,
    data: SequenceTaskPostponeIn,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    _require_admin(req, token=token)
    if step_code not in _sequence_step_codes():
        raise HTTPException(status_code=400, detail="invalid step_code")
    row = get_lead_by_id(lead_id)
    if not row:
        raise HTTPException(status_code=404, detail="lead not found")
    _sequence_ensure_for_lead(
        lead_id=lead_id,
        created_at=row.get("created_at"),
        lead_status=str(row.get("lead_status") or "new"),
        is_test=bool(int(row.get("is_test") or 0)),
        is_spam=bool(int(row.get("is_spam") or 0)),
    )
    ts = now_iso()
    next_due = (datetime.now(timezone.utc) + timedelta(hours=int(data.hours))).isoformat()
    mark_sequence_task_status(
        lead_id=lead_id,
        step_code=step_code,
        status="pending",
        done_at=None,
        due_at=next_due,
        updated_at=ts,
        note=f"postpone:{int(data.hours)}h",
    )
    tasks = list_sequence_tasks_by_lead(lead_id=lead_id)
    return {"ok": True, "lead_id": lead_id, "step_code": step_code, "due_at": next_due, "tasks": tasks}


@app.post("/api/admin/leads/{lead_id}/followup/postpone")
def admin_postpone_followup(
    req: Request,
    lead_id: str,
    data: FollowupPostponeIn,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    _require_admin(req, token=token)

    rows = list_recent_leads(limit=500, form_type="", status="")
    target = None
    for row in rows:
        if str(row.get("id") or "") == lead_id:
            target = row
            break
    if not target:
        raise HTTPException(status_code=404, detail="lead not found")

    next_at = (datetime.now(timezone.utc) + timedelta(hours=int(data.hours))).isoformat()
    upsert_lead_meta(
        lead_id=lead_id,
        status=str(target.get("lead_status") or "new"),
        notes=str(target.get("lead_notes") or ""),
        follow_up_at=next_at,
        updated_at=now_iso(),
    )
    refreshed = get_lead_by_id(lead_id)
    if refreshed:
        payload = {}
        try:
            payload = json.loads(refreshed.get("payload_json") or "{}")
        except Exception:
            payload = {}
        _recompute_autopilot_for_row(refreshed, payload)
        _refresh_win_snapshot_for_row(refreshed, payload)
        _sequence_ensure_for_lead(
            lead_id=lead_id,
            created_at=refreshed.get("created_at"),
            lead_status=str(refreshed.get("lead_status") or "new"),
            is_test=bool(int(refreshed.get("is_test") or 0)),
            is_spam=bool(int(refreshed.get("is_spam") or 0)),
        )
    return {"ok": True, "lead_id": lead_id, "follow_up_at": next_at}


@app.get("/api/admin/events/recent")
def admin_recent_events(req: Request, limit: int = 80, token: Optional[str] = None) -> Dict[str, Any]:
    if limit < 1 or limit > 300:
        raise HTTPException(status_code=400, detail="limit must be in range 1..300")
    _require_admin(req, token=token)
    return {"ok": True, "events": list_recent_events(limit=limit)}


def _is_report_authorized(req: Request, token: Optional[str]) -> bool:
    expected = os.getenv("WEEKLY_REPORT_TOKEN", "").strip()
    if expected:
        return token == expected or req.headers.get("x-report-token") == expected

    return True


@app.get("/api/reports/weekly")
def weekly_report(req: Request, days: int = 7, fmt: str = "json", token: Optional[str] = None) -> Any:
    if days < 1 or days > 31:
        raise HTTPException(status_code=400, detail="days must be in range 1..31")
    if not _is_report_authorized(req, token):
        raise HTTPException(status_code=403, detail="forbidden")

    report = build_weekly_report(days=days)
    if fmt == "md":
        return {"ok": True, "markdown": report_markdown(report), "report": report}
    return {"ok": True, "report": report}












