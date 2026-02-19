import sqlite3
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DB_PATH = Path(__file__).resolve().parent / "jobs.sqlite3"


def conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def _table_columns(c: sqlite3.Connection, table_name: str) -> set:
    rows = c.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(r["name"]) for r in rows}


def _ensure_column(c: sqlite3.Connection, table_name: str, column_name: str, ddl_tail: str) -> None:
    cols = _table_columns(c, table_name)
    if column_name in cols:
        return
    c.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl_tail}")

def init_db() -> None:
    with conn() as c:
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
              id TEXT PRIMARY KEY,
              status TEXT NOT NULL,
              payload_json TEXT NOT NULL,
              result_json TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS leads (
              id TEXT PRIMARY KEY,
              form_type TEXT NOT NULL,
              payload_json TEXT NOT NULL,
              source_path TEXT,
              ip TEXT,
              user_agent TEXT,
              created_at TEXT NOT NULL
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS analytics_events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              event_name TEXT NOT NULL,
              label TEXT,
              path TEXT,
              href TEXT,
              session_id TEXT,
              consent_state TEXT,
              payload_json TEXT,
              source_ip TEXT,
              user_agent TEXT,
              created_at TEXT NOT NULL
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS lead_meta (
              lead_id TEXT PRIMARY KEY,
              status TEXT NOT NULL DEFAULT 'new',
              notes TEXT NOT NULL DEFAULT '',
              follow_up_at TEXT,
              updated_at TEXT NOT NULL,
              booking_token TEXT,
              booked_at TEXT,
              booked_slot TEXT,
              is_test INTEGER NOT NULL DEFAULT 0,
              is_spam INTEGER NOT NULL DEFAULT 0,
              spam_reason TEXT NOT NULL DEFAULT '',
              last_contact_at TEXT,
              lost_reason TEXT NOT NULL DEFAULT ''
            )
            """
        )
        _ensure_column(c, "lead_meta", "booking_token", "TEXT")
        _ensure_column(c, "lead_meta", "booked_at", "TEXT")
        _ensure_column(c, "lead_meta", "booked_slot", "TEXT")
        _ensure_column(c, "lead_meta", "is_test", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(c, "lead_meta", "is_spam", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(c, "lead_meta", "spam_reason", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(c, "lead_meta", "last_contact_at", "TEXT")
        _ensure_column(c, "lead_meta", "lost_reason", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(c, "lead_meta", "autopilot_priority", "TEXT NOT NULL DEFAULT 'P3'")
        _ensure_column(c, "lead_meta", "autopilot_next_action", "TEXT NOT NULL DEFAULT 'review'")
        _ensure_column(c, "lead_meta", "autopilot_next_action_due_at", "TEXT")
        _ensure_column(c, "lead_meta", "autopilot_owner_queue", "TEXT NOT NULL DEFAULT 'sales'")
        _ensure_column(c, "lead_meta", "autopilot_updated_at", "TEXT")
        _ensure_column(c, "lead_meta", "deal_value", "REAL NOT NULL DEFAULT 0")
        _ensure_column(c, "lead_meta", "win_probability", "REAL")
        _ensure_column(c, "lead_meta", "win_recommendation", "TEXT")
        _ensure_column(c, "lead_meta", "win_model_version", "TEXT")
        _ensure_column(c, "lead_meta", "win_updated_at", "TEXT")
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS followup_templates (
              step_hours INTEGER PRIMARY KEY,
              subject_template TEXT NOT NULL,
              body_template TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS followup_log (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              lead_id TEXT NOT NULL,
              step_hours INTEGER NOT NULL,
              to_email TEXT NOT NULL,
              subject TEXT NOT NULL,
              body TEXT NOT NULL,
              status TEXT NOT NULL,
              sent_at TEXT NOT NULL
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS lead_sequence_tasks (
              lead_id TEXT NOT NULL,
              step_code TEXT NOT NULL,
              due_at TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'pending',
              done_at TEXT,
              note TEXT NOT NULL DEFAULT '',
              updated_at TEXT NOT NULL,
              PRIMARY KEY (lead_id, step_code)
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS channel_cost_daily (
              date_iso TEXT NOT NULL,
              channel TEXT NOT NULL,
              cost REAL NOT NULL DEFAULT 0,
              updated_at TEXT NOT NULL,
              PRIMARY KEY (date_iso, channel)
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS budget_plans (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              created_at TEXT NOT NULL,
              days INTEGER NOT NULL,
              spend_change_pct REAL NOT NULL,
              status TEXT NOT NULL DEFAULT 'proposed',
              note TEXT NOT NULL DEFAULT ''
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS budget_plan_items (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              plan_id INTEGER NOT NULL,
              channel TEXT NOT NULL,
              action TEXT NOT NULL,
              reason TEXT NOT NULL DEFAULT '',
              current_cost REAL NOT NULL DEFAULT 0,
              proposed_cost REAL NOT NULL DEFAULT 0,
              delta_cost REAL NOT NULL DEFAULT 0,
              expected_profit_delta REAL NOT NULL DEFAULT 0,
              status TEXT NOT NULL DEFAULT 'pending',
              applied_at TEXT,
              updated_at TEXT NOT NULL
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS budget_plan_cost_runs (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              plan_id INTEGER NOT NULL,
              item_id INTEGER NOT NULL,
              date_iso TEXT NOT NULL,
              channel TEXT NOT NULL,
              prev_cost REAL NOT NULL DEFAULT 0,
              new_cost REAL NOT NULL DEFAULT 0,
              applied_at TEXT NOT NULL,
              reverted_at TEXT
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS guardrail_incidents (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              fingerprint TEXT NOT NULL UNIQUE,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              severity TEXT NOT NULL,
              incident_type TEXT NOT NULL,
              channel TEXT NOT NULL DEFAULT '',
              title TEXT NOT NULL,
              details_json TEXT NOT NULL DEFAULT '{}',
              status TEXT NOT NULL DEFAULT 'open',
              acknowledged_at TEXT,
              resolved_at TEXT
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS incident_tasks (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              incident_id INTEGER NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              due_at TEXT NOT NULL,
              owner TEXT NOT NULL DEFAULT 'sales',
              priority TEXT NOT NULL DEFAULT 'P2',
              title TEXT NOT NULL,
              action_type TEXT NOT NULL,
              payload_json TEXT NOT NULL DEFAULT '{}',
              status TEXT NOT NULL DEFAULT 'pending',
              done_at TEXT,
              overdue_since TEXT,
              retry_count INTEGER NOT NULL DEFAULT 0,
              reopen_count INTEGER NOT NULL DEFAULT 0,
              last_sla_alert_bucket TEXT,
              last_sla_alert_at TEXT
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS incident_task_audit (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              task_id INTEGER NOT NULL,
              actor TEXT NOT NULL DEFAULT 'system',
              action TEXT NOT NULL DEFAULT 'update',
              change_json TEXT NOT NULL DEFAULT '{}',
              created_at TEXT NOT NULL
            )
            """
        )
        _ensure_column(c, "incident_tasks", "priority", "TEXT NOT NULL DEFAULT 'P2'")
        _ensure_column(c, "incident_tasks", "overdue_since", "TEXT")
        _ensure_column(c, "incident_tasks", "retry_count", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(c, "incident_tasks", "reopen_count", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(c, "incident_tasks", "last_sla_alert_bucket", "TEXT")
        _ensure_column(c, "incident_tasks", "last_sla_alert_at", "TEXT")
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS scenario_snapshots (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              created_at TEXT NOT NULL,
              name TEXT NOT NULL,
              days INTEGER NOT NULL,
              history_days INTEGER NOT NULL,
              horizon_days INTEGER NOT NULL,
              target_revenue REAL NOT NULL DEFAULT 0,
              budget_change_pct REAL NOT NULL DEFAULT 0,
              conv_uplift_pct REAL NOT NULL DEFAULT 0,
              spend_change_pct REAL NOT NULL DEFAULT 0,
              include_test INTEGER NOT NULL DEFAULT 0,
              include_spam INTEGER NOT NULL DEFAULT 0,
              summary_json TEXT NOT NULL DEFAULT '{}'
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS execution_connectors (
              channel TEXT PRIMARY KEY,
              provider TEXT NOT NULL DEFAULT 'simulator',
              mode TEXT NOT NULL DEFAULT 'simulate',
              status TEXT NOT NULL DEFAULT 'enabled',
              daily_change_limit_pct REAL NOT NULL DEFAULT 20,
              last_sync_at TEXT,
              last_result_json TEXT NOT NULL DEFAULT '{}',
              updated_at TEXT NOT NULL
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS approvals (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              entity_type TEXT NOT NULL,
              entity_id TEXT NOT NULL,
              action TEXT NOT NULL,
              payload_json TEXT NOT NULL DEFAULT '{}',
              threshold_value REAL NOT NULL DEFAULT 0,
              status TEXT NOT NULL DEFAULT 'pending',
              requested_by TEXT NOT NULL DEFAULT 'system',
              decided_by TEXT,
              note TEXT NOT NULL DEFAULT '',
              created_at TEXT NOT NULL,
              decided_at TEXT
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS execution_runs (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              connector_channel TEXT NOT NULL,
              plan_id INTEGER,
              item_id INTEGER,
              action TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'pending',
              request_json TEXT NOT NULL DEFAULT '{}',
              response_json TEXT NOT NULL DEFAULT '{}',
              created_at TEXT NOT NULL,
              finished_at TEXT
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS experiments (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT NOT NULL,
              scope TEXT NOT NULL DEFAULT 'landing',
              status TEXT NOT NULL DEFAULT 'draft',
              metric_primary TEXT NOT NULL DEFAULT 'win_rate',
              allocation_mode TEXT NOT NULL DEFAULT 'equal',
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS experiment_arms (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              experiment_id INTEGER NOT NULL,
              arm_key TEXT NOT NULL,
              label TEXT NOT NULL,
              weight REAL NOT NULL DEFAULT 1,
              config_json TEXT NOT NULL DEFAULT '{}',
              UNIQUE(experiment_id, arm_key)
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS experiment_events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              experiment_id INTEGER NOT NULL,
              arm_key TEXT NOT NULL,
              event_type TEXT NOT NULL,
              value REAL NOT NULL DEFAULT 1,
              session_id TEXT,
              lead_id TEXT,
              created_at TEXT NOT NULL
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS target_commits (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              period_start TEXT NOT NULL,
              period_end TEXT NOT NULL,
              target_revenue REAL NOT NULL,
              owner TEXT NOT NULL DEFAULT 'ops',
              status TEXT NOT NULL DEFAULT 'active',
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS target_daily_snapshots (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              commit_id INTEGER NOT NULL,
              day_iso TEXT NOT NULL,
              actual_revenue REAL NOT NULL DEFAULT 0,
              expected_revenue REAL NOT NULL DEFAULT 0,
              gap REAL NOT NULL DEFAULT 0,
              risk_level TEXT NOT NULL DEFAULT 'low',
              recommendations_json TEXT NOT NULL DEFAULT '[]',
              created_at TEXT NOT NULL,
              UNIQUE(commit_id, day_iso)
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS autonomous_run_log (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              run_type TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'ok',
              summary_json TEXT NOT NULL DEFAULT '{}',
              created_at TEXT NOT NULL
            )
            """
        )
        c.execute("CREATE INDEX IF NOT EXISTS idx_events_created_at ON analytics_events(created_at)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_events_name_created_at ON analytics_events(event_name, created_at)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_leads_created_at ON leads(created_at)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_followup_log_lead_step ON followup_log(lead_id, step_hours)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_followup_log_sent_at ON followup_log(sent_at)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_lead_meta_status ON lead_meta(status)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_lead_meta_flags ON lead_meta(is_test, is_spam)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_lead_meta_booking_token ON lead_meta(booking_token)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_lead_meta_autopilot_due ON lead_meta(autopilot_next_action_due_at)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_lead_meta_autopilot_priority ON lead_meta(autopilot_priority)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_lead_meta_win_recommendation ON lead_meta(win_recommendation)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_sequence_due_status ON lead_sequence_tasks(due_at, status)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_channel_cost_daily_date ON channel_cost_daily(date_iso)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_channel_cost_daily_channel ON channel_cost_daily(channel)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_budget_plans_created ON budget_plans(created_at)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_budget_plans_status ON budget_plans(status)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_budget_plan_items_plan ON budget_plan_items(plan_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_budget_plan_items_status ON budget_plan_items(status)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_budget_plan_runs_item ON budget_plan_cost_runs(item_id, reverted_at)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_budget_plan_runs_plan ON budget_plan_cost_runs(plan_id, applied_at)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_guardrail_status_updated ON guardrail_incidents(status, updated_at)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_guardrail_severity ON guardrail_incidents(severity)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_incident_tasks_status_due ON incident_tasks(status, due_at)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_incident_tasks_incident ON incident_tasks(incident_id, status)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_incident_tasks_priority_status ON incident_tasks(priority, status)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_incident_tasks_overdue_since ON incident_tasks(overdue_since)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_incident_task_audit_task_created ON incident_task_audit(task_id, created_at)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_scenario_snapshots_created ON scenario_snapshots(created_at)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_approvals_status_created ON approvals(status, created_at)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_execution_runs_channel_created ON execution_runs(connector_channel, created_at)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_experiment_events_exp_arm ON experiment_events(experiment_id, arm_key, event_type)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_target_commits_status ON target_commits(status, period_start)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_target_snapshots_commit_day ON target_daily_snapshots(commit_id, day_iso)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_autonomous_run_log_type_created ON autonomous_run_log(run_type, created_at)")

        # Default follow-up templates (editable from admin panel)
        c.execute(
            """
            INSERT OR IGNORE INTO followup_templates (step_hours, subject_template, body_template, updated_at)
            VALUES
              (24, 'Follow-up po 24h - {{form_type}}', 'Czesc, wracam po 24h w sprawie Twojego formularza {{form_type}}. Daj znac, czy dzialamy dalej.', datetime('now')),
              (72, 'Follow-up po 72h - {{form_type}}', 'Hej, to drugie przypomnienie po 72h. Jesli temat jest aktualny, odpisz i jedziemy dalej.', datetime('now'))
            """
        )
        c.execute(
            """
            INSERT OR IGNORE INTO execution_connectors
            (channel, provider, mode, status, daily_change_limit_pct, last_sync_at, last_result_json, updated_at)
            VALUES
              ('google_ads', 'simulator', 'simulate', 'enabled', 20, NULL, '{}', datetime('now')),
              ('meta_ads', 'simulator', 'simulate', 'enabled', 20, NULL, '{}', datetime('now')),
              ('linkedin', 'simulator', 'simulate', 'enabled', 15, NULL, '{}', datetime('now'))
            """
        )
        c.commit()


def insert_job(job_id: str, status: str, payload_json: str, now_iso: str) -> None:
    with conn() as c:
        c.execute(
            "INSERT INTO jobs (id,status,payload_json,created_at,updated_at) VALUES (?,?,?,?,?)",
            (job_id, status, payload_json, now_iso, now_iso),
        )
        c.commit()


def update_job(job_id: str, status: str, result_json: Optional[str], now_iso: str) -> None:
    with conn() as c:
        c.execute(
            "UPDATE jobs SET status=?, result_json=?, updated_at=? WHERE id=?",
            (status, result_json, now_iso, job_id),
        )
        c.commit()


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    with conn() as c:
        row = c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return dict(row) if row else None


def list_jobs(limit: int = 30) -> List[Dict[str, Any]]:
    with conn() as c:
        rows = c.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def insert_lead(
    lead_id: str,
    form_type: str,
    payload_json: str,
    source_path: str,
    ip: str,
    user_agent: str,
    created_at: str,
) -> None:
    with conn() as c:
        c.execute(
            """
            INSERT INTO leads (id, form_type, payload_json, source_path, ip, user_agent, created_at)
            VALUES (?,?,?,?,?,?,?)
            """,
            (lead_id, form_type, payload_json, source_path, ip, user_agent, created_at),
        )
        c.execute(
            """
            INSERT OR IGNORE INTO lead_meta (lead_id, status, notes, follow_up_at, updated_at)
            VALUES (?, 'new', '', NULL, ?)
            """,
            (lead_id, created_at),
        )
        c.commit()


def upsert_lead_meta(lead_id: str, status: str, notes: str, follow_up_at: Optional[str], updated_at: str) -> None:
    with conn() as c:
        c.execute(
            """
            INSERT INTO lead_meta (lead_id, status, notes, follow_up_at, updated_at)
            VALUES (?,?,?,?,?)
            ON CONFLICT(lead_id) DO UPDATE SET
              status=excluded.status,
              notes=excluded.notes,
              follow_up_at=excluded.follow_up_at,
              updated_at=excluded.updated_at
            """,
            (lead_id, status, notes, follow_up_at, updated_at),
        )
        c.commit()


def upsert_lead_value(lead_id: str, deal_value: float, updated_at: str) -> None:
    safe_value = float(deal_value if deal_value is not None else 0.0)
    with conn() as c:
        c.execute(
            """
            INSERT INTO lead_meta (lead_id, status, notes, follow_up_at, updated_at, deal_value)
            VALUES (?, 'new', '', NULL, ?, ?)
            ON CONFLICT(lead_id) DO UPDATE SET
              deal_value=excluded.deal_value,
              updated_at=excluded.updated_at
            """,
            (lead_id, updated_at, safe_value),
        )
        c.commit()


def upsert_lead_autopilot(
    lead_id: str,
    priority: str,
    next_action: str,
    next_action_due_at: Optional[str],
    owner_queue: str,
    updated_at: str,
) -> None:
    with conn() as c:
        c.execute(
            """
            INSERT INTO lead_meta
            (lead_id, status, notes, follow_up_at, updated_at, autopilot_priority, autopilot_next_action, autopilot_next_action_due_at, autopilot_owner_queue, autopilot_updated_at)
            VALUES (?, 'new', '', NULL, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(lead_id) DO UPDATE SET
              autopilot_priority=excluded.autopilot_priority,
              autopilot_next_action=excluded.autopilot_next_action,
              autopilot_next_action_due_at=excluded.autopilot_next_action_due_at,
              autopilot_owner_queue=excluded.autopilot_owner_queue,
              autopilot_updated_at=excluded.autopilot_updated_at,
              updated_at=excluded.updated_at
            """,
            (lead_id, updated_at, priority, next_action, next_action_due_at, owner_queue, updated_at),
        )
        c.commit()


def upsert_lead_win_model(
    lead_id: str,
    win_probability: Optional[float],
    win_recommendation: Optional[str],
    win_model_version: Optional[str],
    updated_at: str,
) -> None:
    with conn() as c:
        c.execute(
            """
            INSERT INTO lead_meta
            (lead_id, status, notes, follow_up_at, updated_at, win_probability, win_recommendation, win_model_version, win_updated_at)
            VALUES (?, 'new', '', NULL, ?, ?, ?, ?, ?)
            ON CONFLICT(lead_id) DO UPDATE SET
              win_probability=excluded.win_probability,
              win_recommendation=excluded.win_recommendation,
              win_model_version=excluded.win_model_version,
              win_updated_at=excluded.win_updated_at,
              updated_at=excluded.updated_at
            """,
            (lead_id, updated_at, win_probability, win_recommendation, win_model_version, updated_at),
        )
        c.commit()


def upsert_lead_enrichment(
    lead_id: str,
    booking_token: Optional[str],
    is_test: bool,
    is_spam: bool,
    spam_reason: str,
    updated_at: str,
) -> None:
    with conn() as c:
        c.execute(
            """
            INSERT INTO lead_meta (lead_id, status, notes, follow_up_at, updated_at, booking_token, is_test, is_spam, spam_reason)
            VALUES (?, 'new', '', NULL, ?, ?, ?, ?, ?)
            ON CONFLICT(lead_id) DO UPDATE SET
              updated_at=excluded.updated_at,
              booking_token=COALESCE(excluded.booking_token, lead_meta.booking_token),
              is_test=excluded.is_test,
              is_spam=excluded.is_spam,
              spam_reason=excluded.spam_reason
            """,
            (lead_id, updated_at, booking_token, 1 if is_test else 0, 1 if is_spam else 0, spam_reason),
        )
        c.commit()


def booking_target(lead_id: str, booking_token: str) -> Optional[Dict[str, Any]]:
    with conn() as c:
        row = c.execute(
            """
            SELECT
              l.id, l.form_type, l.payload_json, l.source_path, l.created_at,
              COALESCE(m.status, 'new') AS lead_status,
              m.booking_token,
              m.booked_at,
              m.booked_slot,
              COALESCE(m.is_test, 0) AS is_test,
              COALESCE(m.is_spam, 0) AS is_spam
            FROM leads l
            JOIN lead_meta m ON m.lead_id = l.id
            WHERE l.id = ? AND COALESCE(m.booking_token, '') = ?
            """,
            (lead_id, booking_token),
        ).fetchone()
        return dict(row) if row else None


def confirm_lead_booking(lead_id: str, booked_slot: str, updated_at: str) -> None:
    with conn() as c:
        c.execute(
            """
            UPDATE lead_meta
            SET status='in_progress',
                booked_at=?,
                booked_slot=?,
                follow_up_at=NULL,
                updated_at=?
            WHERE lead_id=?
            """,
            (updated_at, booked_slot, updated_at, lead_id),
        )
        c.commit()


def touch_lead_action(
    lead_id: str,
    status: str,
    notes: str,
    follow_up_at: Optional[str],
    last_contact_at: Optional[str],
    lost_reason: str,
    updated_at: str,
) -> None:
    with conn() as c:
        c.execute(
            """
            INSERT INTO lead_meta
            (lead_id, status, notes, follow_up_at, updated_at, last_contact_at, lost_reason)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(lead_id) DO UPDATE SET
              status=excluded.status,
              notes=excluded.notes,
              follow_up_at=excluded.follow_up_at,
              updated_at=excluded.updated_at,
              last_contact_at=excluded.last_contact_at,
              lost_reason=excluded.lost_reason
            """,
            (lead_id, status, notes, follow_up_at, updated_at, last_contact_at, lost_reason),
        )
        c.commit()


def count_recent_leads_by_ip(ip: str, since_iso: str) -> int:
    with conn() as c:
        row = c.execute(
            "SELECT COUNT(*) AS cnt FROM leads WHERE ip = ? AND created_at >= ?",
            (ip, since_iso),
        ).fetchone()
        return int(row["cnt"] if row else 0)


def insert_analytics_events(rows: List[Tuple[str, str, str, str, str, str, str, str, str, str]]) -> int:
    if not rows:
        return 0
    with conn() as c:
        c.executemany(
            """
            INSERT INTO analytics_events
            (event_name, label, path, href, session_id, consent_state, payload_json, source_ip, user_agent, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            rows,
        )
        c.commit()
    return len(rows)


def count_events_between(start_iso: str, end_iso: str, event_name: Optional[str] = None) -> int:
    with conn() as c:
        if event_name:
            row = c.execute(
                "SELECT COUNT(*) AS cnt FROM analytics_events WHERE created_at >= ? AND created_at < ? AND event_name = ?",
                (start_iso, end_iso, event_name),
            ).fetchone()
        else:
            row = c.execute(
                "SELECT COUNT(*) AS cnt FROM analytics_events WHERE created_at >= ? AND created_at < ?",
                (start_iso, end_iso),
            ).fetchone()
        return int(row["cnt"] if row else 0)


def count_leads_between(start_iso: str, end_iso: str) -> int:
    with conn() as c:
        row = c.execute(
            "SELECT COUNT(*) AS cnt FROM leads WHERE created_at >= ? AND created_at < ?",
            (start_iso, end_iso),
        ).fetchone()
        return int(row["cnt"] if row else 0)


def count_form_submit_between(start_iso: str, end_iso: str) -> int:
    with conn() as c:
        row = c.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM analytics_events
            WHERE created_at >= ? AND created_at < ?
              AND event_name = 'form_submit'
            """,
            (start_iso, end_iso),
        ).fetchone()
        return int(row["cnt"] if row else 0)


def count_form_submit_by_form_between(start_iso: str, end_iso: str) -> Dict[str, int]:
    with conn() as c:
        rows = c.execute(
            """
            SELECT
              CASE
                WHEN LOWER(label) LIKE '%audyt%' THEN 'audyt'
                WHEN LOWER(label) LIKE '%kontakt%' THEN 'kontakt'
                ELSE 'other'
              END AS form_type,
              COUNT(*) AS cnt
            FROM analytics_events
            WHERE created_at >= ? AND created_at < ?
              AND event_name = 'form_submit'
            GROUP BY form_type
            """,
            (start_iso, end_iso),
        ).fetchall()
        out: Dict[str, int] = {"audyt": 0, "kontakt": 0, "other": 0}
        for r in rows:
            out[str(r["form_type"])] = int(r["cnt"])
        return out


def top_cta_labels_between(start_iso: str, end_iso: str, limit: int = 8) -> List[Dict[str, Any]]:
    with conn() as c:
        rows = c.execute(
            """
            SELECT COALESCE(label, '(no-label)') AS label, COUNT(*) AS cnt
            FROM analytics_events
            WHERE created_at >= ? AND created_at < ? AND event_name = 'cta_click'
            GROUP BY COALESCE(label, '(no-label)')
            ORDER BY cnt DESC
            LIMIT ?
            """,
            (start_iso, end_iso, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def funnel_count_between(start_iso: str, end_iso: str, path: str) -> int:
    with conn() as c:
        row = c.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM analytics_events
            WHERE created_at >= ? AND created_at < ?
              AND event_name = 'page_view'
              AND path = ?
            """,
            (start_iso, end_iso, path),
        ).fetchone()
        return int(row["cnt"] if row else 0)


def list_recent_leads(
    limit: int = 50,
    form_type: str = "",
    status: str = "",
    include_test: bool = True,
    include_spam: bool = True,
) -> List[Dict[str, Any]]:
    sql = """
        SELECT
          l.id, l.form_type, l.payload_json, l.source_path, l.ip, l.user_agent, l.created_at,
          COALESCE(m.status, 'new') AS lead_status,
          COALESCE(m.notes, '') AS lead_notes,
          m.follow_up_at AS lead_follow_up_at,
          m.updated_at AS lead_updated_at,
          COALESCE(m.booking_token, '') AS booking_token,
          m.booked_at AS booked_at,
          m.booked_slot AS booked_slot,
          COALESCE(m.is_test, 0) AS is_test,
          COALESCE(m.is_spam, 0) AS is_spam,
          COALESCE(m.spam_reason, '') AS spam_reason,
          m.last_contact_at AS last_contact_at,
          COALESCE(m.lost_reason, '') AS lost_reason,
          COALESCE(m.autopilot_priority, 'P3') AS autopilot_priority,
          COALESCE(m.autopilot_next_action, 'review') AS autopilot_next_action,
          m.autopilot_next_action_due_at AS autopilot_next_action_due_at,
          COALESCE(m.autopilot_owner_queue, 'sales') AS autopilot_owner_queue,
          m.autopilot_updated_at AS autopilot_updated_at,
          m.win_probability AS win_probability,
          COALESCE(m.win_recommendation, '') AS win_recommendation,
          COALESCE(m.win_model_version, '') AS win_model_version,
          m.win_updated_at AS win_updated_at,
          COALESCE(m.deal_value, 0) AS deal_value
        FROM leads l
        LEFT JOIN lead_meta m ON m.lead_id = l.id
        WHERE 1=1
    """
    args: List[Any] = []
    if form_type:
        sql += " AND l.form_type = ?"
        args.append(form_type)
    if status:
        sql += " AND COALESCE(m.status, 'new') = ?"
        args.append(status)
    if not include_test:
        sql += " AND COALESCE(m.is_test, 0) = 0"
    if not include_spam:
        sql += " AND COALESCE(m.is_spam, 0) = 0"
    sql += " ORDER BY l.created_at DESC LIMIT ?"
    args.append(limit)

    with conn() as c:
        rows = c.execute(sql, tuple(args)).fetchall()
        return [dict(r) for r in rows]


def list_leads_for_backfill(
    limit: int = 1000,
    offset: int = 0,
    include_test: bool = True,
    include_spam: bool = True,
) -> List[Dict[str, Any]]:
    sql = """
        SELECT
          l.id, l.form_type, l.payload_json, l.source_path, l.ip, l.user_agent, l.created_at,
          COALESCE(m.status, 'new') AS lead_status,
          COALESCE(m.notes, '') AS lead_notes,
          m.follow_up_at AS lead_follow_up_at,
          m.updated_at AS lead_updated_at,
          COALESCE(m.booking_token, '') AS booking_token,
          m.booked_at AS booked_at,
          m.booked_slot AS booked_slot,
          COALESCE(m.is_test, 0) AS is_test,
          COALESCE(m.is_spam, 0) AS is_spam,
          COALESCE(m.spam_reason, '') AS spam_reason,
          m.last_contact_at AS last_contact_at,
          COALESCE(m.lost_reason, '') AS lost_reason,
          COALESCE(m.autopilot_priority, 'P3') AS autopilot_priority,
          COALESCE(m.autopilot_next_action, 'review') AS autopilot_next_action,
          m.autopilot_next_action_due_at AS autopilot_next_action_due_at,
          COALESCE(m.autopilot_owner_queue, 'sales') AS autopilot_owner_queue,
          m.autopilot_updated_at AS autopilot_updated_at,
          m.win_probability AS win_probability,
          COALESCE(m.win_recommendation, '') AS win_recommendation,
          COALESCE(m.win_model_version, '') AS win_model_version,
          m.win_updated_at AS win_updated_at,
          COALESCE(m.deal_value, 0) AS deal_value
        FROM leads l
        LEFT JOIN lead_meta m ON m.lead_id = l.id
        WHERE 1=1
    """
    args: List[Any] = []
    if not include_test:
        sql += " AND COALESCE(m.is_test, 0) = 0"
    if not include_spam:
        sql += " AND COALESCE(m.is_spam, 0) = 0"
    sql += " ORDER BY l.created_at ASC LIMIT ? OFFSET ?"
    args.extend([int(limit), int(offset)])
    with conn() as c:
        rows = c.execute(sql, tuple(args)).fetchall()
        return [dict(r) for r in rows]


def count_leads_by_form_between(start_iso: str, end_iso: str) -> List[Dict[str, Any]]:
    with conn() as c:
        rows = c.execute(
            """
            SELECT form_type, COUNT(*) AS cnt
            FROM leads
            WHERE created_at >= ? AND created_at < ?
            GROUP BY form_type
            ORDER BY cnt DESC
            """,
            (start_iso, end_iso),
        ).fetchall()
        return [dict(r) for r in rows]


def count_leads_by_status_between(start_iso: str, end_iso: str, include_test: bool = True, include_spam: bool = True) -> List[Dict[str, Any]]:
    sql = """
        SELECT COALESCE(m.status, 'new') AS status, COUNT(*) AS cnt
        FROM leads l
        LEFT JOIN lead_meta m ON m.lead_id = l.id
        WHERE l.created_at >= ? AND l.created_at < ?
    """
    args: List[Any] = [start_iso, end_iso]
    if not include_test:
        sql += " AND COALESCE(m.is_test, 0) = 0"
    if not include_spam:
        sql += " AND COALESCE(m.is_spam, 0) = 0"
    sql += " GROUP BY COALESCE(m.status, 'new') ORDER BY cnt DESC"

    with conn() as c:
        rows = c.execute(sql, tuple(args)).fetchall()
        return [dict(r) for r in rows]


def list_leads_between(start_iso: str, end_iso: str, limit: int = 5000, include_test: bool = True, include_spam: bool = True) -> List[Dict[str, Any]]:
    sql = """
        SELECT
          l.id, l.form_type, l.payload_json, l.source_path, l.ip, l.created_at,
          COALESCE(m.status, 'new') AS lead_status,
          COALESCE(m.notes, '') AS lead_notes,
          m.follow_up_at AS lead_follow_up_at,
          COALESCE(m.is_test, 0) AS is_test,
          COALESCE(m.is_spam, 0) AS is_spam,
          COALESCE(m.spam_reason, '') AS spam_reason,
          m.booked_at,
          m.booked_slot,
          m.last_contact_at,
          COALESCE(m.lost_reason, '') AS lost_reason,
          COALESCE(m.autopilot_priority, 'P3') AS autopilot_priority,
          COALESCE(m.autopilot_next_action, 'review') AS autopilot_next_action,
          m.autopilot_next_action_due_at AS autopilot_next_action_due_at,
          COALESCE(m.autopilot_owner_queue, 'sales') AS autopilot_owner_queue,
          m.autopilot_updated_at AS autopilot_updated_at,
          m.win_probability AS win_probability,
          COALESCE(m.win_recommendation, '') AS win_recommendation,
          COALESCE(m.win_model_version, '') AS win_model_version,
          m.win_updated_at AS win_updated_at,
          COALESCE(m.deal_value, 0) AS deal_value
        FROM leads l
        LEFT JOIN lead_meta m ON m.lead_id = l.id
        WHERE l.created_at >= ? AND l.created_at < ?
    """
    args: List[Any] = [start_iso, end_iso]
    if not include_test:
        sql += " AND COALESCE(m.is_test, 0) = 0"
    if not include_spam:
        sql += " AND COALESCE(m.is_spam, 0) = 0"
    sql += " ORDER BY l.created_at DESC LIMIT ?"
    args.append(limit)

    with conn() as c:
        rows = c.execute(sql, tuple(args)).fetchall()
        return [dict(r) for r in rows]


def top_events_between(start_iso: str, end_iso: str, limit: int = 20) -> List[Dict[str, Any]]:
    with conn() as c:
        rows = c.execute(
            """
            SELECT event_name, COUNT(*) AS cnt
            FROM analytics_events
            WHERE created_at >= ? AND created_at < ?
            GROUP BY event_name
            ORDER BY cnt DESC
            LIMIT ?
            """,
            (start_iso, end_iso, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def list_recent_events(limit: int = 60) -> List[Dict[str, Any]]:
    with conn() as c:
        rows = c.execute(
            """
            SELECT event_name, label, path, href, session_id, consent_state, created_at
            FROM analytics_events
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def list_followup_templates() -> List[Dict[str, Any]]:
    with conn() as c:
        rows = c.execute(
            """
            SELECT step_hours, subject_template, body_template, updated_at
            FROM followup_templates
            ORDER BY step_hours ASC
            """
        ).fetchall()
        return [dict(r) for r in rows]


def upsert_followup_template(step_hours: int, subject_template: str, body_template: str, updated_at: str) -> None:
    with conn() as c:
        c.execute(
            """
            INSERT INTO followup_templates (step_hours, subject_template, body_template, updated_at)
            VALUES (?,?,?,?)
            ON CONFLICT(step_hours) DO UPDATE SET
              subject_template=excluded.subject_template,
              body_template=excluded.body_template,
              updated_at=excluded.updated_at
            """,
            (step_hours, subject_template, body_template, updated_at),
        )
        c.commit()


def list_due_followup_candidates(step_hours: int, older_than_iso: str, limit: int = 200) -> List[Dict[str, Any]]:
    with conn() as c:
        rows = c.execute(
            """
            SELECT
              l.id, l.form_type, l.payload_json, l.source_path, l.created_at,
              COALESCE(m.status, 'new') AS lead_status,
              COALESCE(m.notes, '') AS lead_notes,
              m.follow_up_at
            FROM leads l
            LEFT JOIN lead_meta m ON m.lead_id = l.id
            WHERE l.created_at <= ?
              AND COALESCE(m.status, 'new') NOT IN ('won', 'lost')
              AND COALESCE(m.is_test, 0) = 0
              AND COALESCE(m.is_spam, 0) = 0
              AND NOT EXISTS (
                SELECT 1
                FROM followup_log fl
                WHERE fl.lead_id = l.id AND fl.step_hours = ?
              )
            ORDER BY l.created_at ASC
            LIMIT ?
            """,
            (older_than_iso, step_hours, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def insert_followup_log(
    lead_id: str,
    step_hours: int,
    to_email: str,
    subject: str,
    body: str,
    status: str,
    sent_at: str,
) -> None:
    with conn() as c:
        c.execute(
            """
            INSERT INTO followup_log (lead_id, step_hours, to_email, subject, body, status, sent_at)
            VALUES (?,?,?,?,?,?,?)
            """,
            (lead_id, step_hours, to_email, subject, body, status, sent_at),
        )
        c.commit()


def list_followup_logs(limit: int = 100) -> List[Dict[str, Any]]:
    with conn() as c:
        rows = c.execute(
            """
            SELECT id, lead_id, step_hours, to_email, subject, status, sent_at
            FROM followup_log
            ORDER BY sent_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def list_due_followups(now_iso: str, limit: int = 200) -> List[Dict[str, Any]]:
    with conn() as c:
        rows = c.execute(
            """
            SELECT
              l.id, l.form_type, l.payload_json, l.source_path, l.created_at,
              COALESCE(m.status, 'new') AS lead_status,
              COALESCE(m.notes, '') AS lead_notes,
              m.follow_up_at
            FROM leads l
            JOIN lead_meta m ON m.lead_id = l.id
            WHERE m.follow_up_at IS NOT NULL
              AND m.follow_up_at <= ?
              AND COALESCE(m.status, 'new') NOT IN ('won', 'lost')
              AND COALESCE(m.is_test, 0) = 0
              AND COALESCE(m.is_spam, 0) = 0
            ORDER BY m.follow_up_at ASC
            LIMIT ?
            """,
            (now_iso, limit),
        ).fetchall()
        return [dict(r) for r in rows]



def list_analytics_events_between(start_iso: str, end_iso: str, event_name: str = "", limit: int = 12000) -> List[Dict[str, Any]]:
    sql = """
        SELECT event_name, label, path, href, session_id, consent_state, payload_json, source_ip, user_agent, created_at
        FROM analytics_events
        WHERE created_at >= ? AND created_at < ?
    """
    args: List[Any] = [start_iso, end_iso]
    if event_name:
        sql += " AND event_name = ?"
        args.append(event_name)
    sql += " ORDER BY created_at ASC LIMIT ?"
    args.append(limit)

    with conn() as c:
        rows = c.execute(sql, tuple(args)).fetchall()
        return [dict(r) for r in rows]


def get_lead_by_id(lead_id: str) -> Optional[Dict[str, Any]]:
    with conn() as c:
        row = c.execute(
            """
            SELECT
              l.id, l.form_type, l.payload_json, l.source_path, l.ip, l.user_agent, l.created_at,
              COALESCE(m.status, 'new') AS lead_status,
              COALESCE(m.notes, '') AS lead_notes,
              m.follow_up_at AS lead_follow_up_at,
              m.updated_at AS lead_updated_at,
              COALESCE(m.booking_token, '') AS booking_token,
              m.booked_at AS booked_at,
              m.booked_slot AS booked_slot,
              COALESCE(m.is_test, 0) AS is_test,
              COALESCE(m.is_spam, 0) AS is_spam,
              COALESCE(m.spam_reason, '') AS spam_reason,
              m.last_contact_at AS last_contact_at,
              COALESCE(m.lost_reason, '') AS lost_reason,
              COALESCE(m.autopilot_priority, 'P3') AS autopilot_priority,
              COALESCE(m.autopilot_next_action, 'review') AS autopilot_next_action,
              m.autopilot_next_action_due_at AS autopilot_next_action_due_at,
              COALESCE(m.autopilot_owner_queue, 'sales') AS autopilot_owner_queue,
              m.autopilot_updated_at AS autopilot_updated_at,
              m.win_probability AS win_probability,
              COALESCE(m.win_recommendation, '') AS win_recommendation,
              COALESCE(m.win_model_version, '') AS win_model_version,
              m.win_updated_at AS win_updated_at,
              COALESCE(m.deal_value, 0) AS deal_value
            FROM leads l
            LEFT JOIN lead_meta m ON m.lead_id = l.id
            WHERE l.id = ?
            """,
            (lead_id,),
        ).fetchone()
        return dict(row) if row else None


def upsert_sequence_task(
    lead_id: str,
    step_code: str,
    due_at: str,
    updated_at: str,
    status: str = "pending",
    note: str = "",
) -> None:
    with conn() as c:
        c.execute(
            """
            INSERT INTO lead_sequence_tasks (lead_id, step_code, due_at, status, done_at, note, updated_at)
            VALUES (?, ?, ?, ?, NULL, ?, ?)
            ON CONFLICT(lead_id, step_code) DO UPDATE SET
              due_at=excluded.due_at,
              status=CASE
                WHEN lead_sequence_tasks.status IN ('done', 'skipped') THEN lead_sequence_tasks.status
                ELSE excluded.status
              END,
              note=CASE
                WHEN excluded.note != '' THEN excluded.note
                ELSE lead_sequence_tasks.note
              END,
              updated_at=excluded.updated_at
            """,
            (lead_id, step_code, due_at, status, note, updated_at),
        )
        c.commit()


def list_sequence_tasks_by_lead(lead_id: str) -> List[Dict[str, Any]]:
    with conn() as c:
        rows = c.execute(
            """
            SELECT lead_id, step_code, due_at, status, done_at, note, updated_at
            FROM lead_sequence_tasks
            WHERE lead_id = ?
            ORDER BY due_at ASC
            """,
            (lead_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def mark_sequence_task_status(
    lead_id: str,
    step_code: str,
    status: str,
    updated_at: str,
    done_at: Optional[str] = None,
    note: str = "",
    due_at: Optional[str] = None,
) -> None:
    with conn() as c:
        if due_at is None:
            c.execute(
                """
                UPDATE lead_sequence_tasks
                SET status = ?,
                    done_at = ?,
                    note = CASE WHEN ? != '' THEN ? ELSE note END,
                    updated_at = ?
                WHERE lead_id = ? AND step_code = ?
                """,
                (status, done_at, note, note, updated_at, lead_id, step_code),
            )
        else:
            c.execute(
                """
                UPDATE lead_sequence_tasks
                SET status = ?,
                    done_at = ?,
                    due_at = ?,
                    note = CASE WHEN ? != '' THEN ? ELSE note END,
                    updated_at = ?
                WHERE lead_id = ? AND step_code = ?
                """,
                (status, done_at, due_at, note, note, updated_at, lead_id, step_code),
            )
        c.commit()


def skip_pending_sequence_for_lead(lead_id: str, updated_at: str, note: str = "") -> None:
    with conn() as c:
        c.execute(
            """
            UPDATE lead_sequence_tasks
            SET status = 'skipped',
                done_at = ?,
                note = CASE WHEN ? != '' THEN ? ELSE note END,
                updated_at = ?
            WHERE lead_id = ? AND status = 'pending'
            """,
            (updated_at, note, note, updated_at, lead_id),
        )
        c.commit()


def list_due_sequence_tasks(now_iso: str, limit: int = 120) -> List[Dict[str, Any]]:
    with conn() as c:
        rows = c.execute(
            """
            SELECT
              t.lead_id, t.step_code, t.due_at, t.status, t.done_at, t.note, t.updated_at,
              l.form_type, l.payload_json, l.source_path, l.created_at,
              COALESCE(m.status, 'new') AS lead_status
            FROM lead_sequence_tasks t
            JOIN leads l ON l.id = t.lead_id
            LEFT JOIN lead_meta m ON m.lead_id = t.lead_id
            WHERE t.status = 'pending'
              AND t.due_at <= ?
              AND COALESCE(m.status, 'new') NOT IN ('won', 'lost')
              AND COALESCE(m.is_test, 0) = 0
              AND COALESCE(m.is_spam, 0) = 0
            ORDER BY t.due_at ASC
            LIMIT ?
            """,
            (now_iso, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def sequence_progress_for_leads(lead_ids: List[str]) -> Dict[str, Dict[str, int]]:
    if not lead_ids:
        return {}
    placeholders = ",".join(["?"] * len(lead_ids))
    sql = f"""
        SELECT lead_id,
               SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending_cnt,
               SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END) AS done_cnt,
               SUM(CASE WHEN status = 'skipped' THEN 1 ELSE 0 END) AS skipped_cnt,
               COUNT(*) AS total_cnt
        FROM lead_sequence_tasks
        WHERE lead_id IN ({placeholders})
        GROUP BY lead_id
    """
    with conn() as c:
        rows = c.execute(sql, tuple(lead_ids)).fetchall()
        out: Dict[str, Dict[str, int]] = {}
        for r in rows:
            out[str(r["lead_id"])] = {
                "pending": int(r["pending_cnt"] or 0),
                "done": int(r["done_cnt"] or 0),
                "skipped": int(r["skipped_cnt"] or 0),
                "total": int(r["total_cnt"] or 0),
            }
        return out


def upsert_channel_cost_daily(date_iso: str, channel: str, cost: float, updated_at: str) -> None:
    with conn() as c:
        c.execute(
            """
            INSERT INTO channel_cost_daily (date_iso, channel, cost, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(date_iso, channel) DO UPDATE SET
              cost=excluded.cost,
              updated_at=excluded.updated_at
            """,
            (date_iso, channel, float(cost), updated_at),
        )
        c.commit()


def list_channel_costs_between(start_date_iso: str, end_date_iso: str) -> List[Dict[str, Any]]:
    with conn() as c:
        rows = c.execute(
            """
            SELECT date_iso, channel, cost, updated_at
            FROM channel_cost_daily
            WHERE date_iso >= ? AND date_iso <= ?
            ORDER BY date_iso DESC, channel ASC
            """,
            (start_date_iso, end_date_iso),
        ).fetchall()
        return [dict(r) for r in rows]


def channel_costs_grouped_between(start_date_iso: str, end_date_iso: str) -> List[Dict[str, Any]]:
    with conn() as c:
        rows = c.execute(
            """
            SELECT channel, SUM(cost) AS total_cost, COUNT(*) AS days_count
            FROM channel_cost_daily
            WHERE date_iso >= ? AND date_iso <= ?
            GROUP BY channel
            ORDER BY total_cost DESC
            """,
            (start_date_iso, end_date_iso),
        ).fetchall()
        return [dict(r) for r in rows]


def channel_cost_on_date(date_iso: str, channel: str) -> Optional[float]:
    with conn() as c:
        row = c.execute(
            "SELECT cost FROM channel_cost_daily WHERE date_iso = ? AND channel = ?",
            (date_iso, channel),
        ).fetchone()
        if not row:
            return None
        return float(row["cost"] or 0.0)


def insert_budget_plan(created_at: str, days: int, spend_change_pct: float, status: str, note: str) -> int:
    with conn() as c:
        cur = c.execute(
            """
            INSERT INTO budget_plans (created_at, days, spend_change_pct, status, note)
            VALUES (?, ?, ?, ?, ?)
            """,
            (created_at, int(days), float(spend_change_pct), status, note[:400]),
        )
        c.commit()
        return int(cur.lastrowid or 0)


def insert_budget_plan_items(plan_id: int, items: List[Tuple[str, str, str, float, float, float, float, str, str]]) -> int:
    if not items:
        return 0
    with conn() as c:
        c.executemany(
            """
            INSERT INTO budget_plan_items
            (plan_id, channel, action, reason, current_cost, proposed_cost, delta_cost, expected_profit_delta, status, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [(plan_id, *x) for x in items],
        )
        c.commit()
        return len(items)


def list_budget_plans(limit: int = 20) -> List[Dict[str, Any]]:
    with conn() as c:
        rows = c.execute(
            """
            SELECT id, created_at, days, spend_change_pct, status, note
            FROM budget_plans
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_budget_plan(plan_id: int) -> Optional[Dict[str, Any]]:
    with conn() as c:
        row = c.execute(
            """
            SELECT id, created_at, days, spend_change_pct, status, note
            FROM budget_plans
            WHERE id = ?
            """,
            (plan_id,),
        ).fetchone()
        return dict(row) if row else None


def list_budget_plan_items(plan_id: int) -> List[Dict[str, Any]]:
    with conn() as c:
        rows = c.execute(
            """
            SELECT id, plan_id, channel, action, reason, current_cost, proposed_cost, delta_cost, expected_profit_delta, status, applied_at, updated_at
            FROM budget_plan_items
            WHERE plan_id = ?
            ORDER BY ABS(delta_cost) DESC, id ASC
            """,
            (plan_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def update_budget_plan_status(plan_id: int, status: str) -> None:
    with conn() as c:
        c.execute("UPDATE budget_plans SET status=? WHERE id=?", (status, plan_id))
        c.commit()


def update_budget_plan_item_status(item_id: int, status: str, applied_at: Optional[str], updated_at: str) -> None:
    with conn() as c:
        c.execute(
            """
            UPDATE budget_plan_items
            SET status=?,
                applied_at=?,
                updated_at=?
            WHERE id=?
            """,
            (status, applied_at, updated_at, item_id),
        )
        c.commit()


def budget_plan_item(item_id: int) -> Optional[Dict[str, Any]]:
    with conn() as c:
        row = c.execute(
            """
            SELECT id, plan_id, channel, action, reason, current_cost, proposed_cost, delta_cost, expected_profit_delta, status, applied_at, updated_at
            FROM budget_plan_items
            WHERE id = ?
            """,
            (item_id,),
        ).fetchone()
        return dict(row) if row else None


def insert_budget_plan_cost_runs(rows: List[Tuple[int, int, str, str, float, float, str]]) -> int:
    if not rows:
        return 0
    with conn() as c:
        c.executemany(
            """
            INSERT INTO budget_plan_cost_runs
            (plan_id, item_id, date_iso, channel, prev_cost, new_cost, applied_at, reverted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            rows,
        )
        c.commit()
        return len(rows)


def list_budget_plan_cost_runs(plan_id: int, item_id: Optional[int] = None, limit: int = 200) -> List[Dict[str, Any]]:
    sql = """
        SELECT id, plan_id, item_id, date_iso, channel, prev_cost, new_cost, applied_at, reverted_at
        FROM budget_plan_cost_runs
        WHERE plan_id = ?
    """
    args: List[Any] = [plan_id]
    if item_id is not None:
        sql += " AND item_id = ?"
        args.append(int(item_id))
    sql += " ORDER BY applied_at DESC, id DESC LIMIT ?"
    args.append(int(limit))
    with conn() as c:
        rows = c.execute(sql, tuple(args)).fetchall()
        return [dict(r) for r in rows]


def unreverted_budget_plan_cost_runs(plan_id: int, item_id: int) -> List[Dict[str, Any]]:
    with conn() as c:
        rows = c.execute(
            """
            SELECT id, plan_id, item_id, date_iso, channel, prev_cost, new_cost, applied_at, reverted_at
            FROM budget_plan_cost_runs
            WHERE plan_id = ? AND item_id = ? AND reverted_at IS NULL
            ORDER BY id ASC
            """,
            (plan_id, item_id),
        ).fetchall()
        return [dict(r) for r in rows]


def mark_budget_plan_runs_reverted(run_ids: List[int], reverted_at: str) -> int:
    if not run_ids:
        return 0
    placeholders = ",".join(["?"] * len(run_ids))
    sql = f"UPDATE budget_plan_cost_runs SET reverted_at=? WHERE id IN ({placeholders})"
    args: List[Any] = [reverted_at] + [int(x) for x in run_ids]
    with conn() as c:
        cur = c.execute(sql, tuple(args))
        c.commit()
        return int(cur.rowcount or 0)


def upsert_guardrail_incident(
    fingerprint: str,
    severity: str,
    incident_type: str,
    channel: str,
    title: str,
    details_json: str,
    now_iso: str,
) -> int:
    with conn() as c:
        row = c.execute(
            "SELECT id, status FROM guardrail_incidents WHERE fingerprint = ?",
            (fingerprint,),
        ).fetchone()
        if row:
            incident_id = int(row["id"])
            prior_status = str(row["status"] or "open")
            if prior_status == "resolved":
                c.execute(
                    """
                    UPDATE guardrail_incidents
                    SET updated_at=?,
                        severity=?,
                        incident_type=?,
                        channel=?,
                        title=?,
                        details_json=?,
                        status='open',
                        acknowledged_at=NULL,
                        resolved_at=NULL
                    WHERE id=?
                    """,
                    (now_iso, severity, incident_type, channel, title, details_json, incident_id),
                )
            else:
                c.execute(
                    """
                    UPDATE guardrail_incidents
                    SET updated_at=?,
                        severity=?,
                        incident_type=?,
                        channel=?,
                        title=?,
                        details_json=?
                    WHERE id=?
                    """,
                    (now_iso, severity, incident_type, channel, title, details_json, incident_id),
                )
            c.commit()
            return incident_id

        cur = c.execute(
            """
            INSERT INTO guardrail_incidents
            (fingerprint, created_at, updated_at, severity, incident_type, channel, title, details_json, status, acknowledged_at, resolved_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', NULL, NULL)
            """,
            (fingerprint, now_iso, now_iso, severity, incident_type, channel, title, details_json),
        )
        c.commit()
        return int(cur.lastrowid or 0)


def list_guardrail_incidents(status: str = "", limit: int = 100) -> List[Dict[str, Any]]:
    sql = """
        SELECT id, fingerprint, created_at, updated_at, severity, incident_type, channel, title, details_json, status, acknowledged_at, resolved_at
        FROM guardrail_incidents
        WHERE 1=1
    """
    args: List[Any] = []
    if status:
        sql += " AND status = ?"
        args.append(status)
    sql += " ORDER BY updated_at DESC LIMIT ?"
    args.append(limit)
    with conn() as c:
        rows = c.execute(sql, tuple(args)).fetchall()
        return [dict(r) for r in rows]


def update_guardrail_incident_status(incident_id: int, status: str, now_iso: str) -> int:
    with conn() as c:
        if status == "ack":
            cur = c.execute(
                """
                UPDATE guardrail_incidents
                SET status='ack',
                    acknowledged_at=?,
                    updated_at=?
                WHERE id=?
                """,
                (now_iso, now_iso, incident_id),
            )
        elif status == "resolved":
            cur = c.execute(
                """
                UPDATE guardrail_incidents
                SET status='resolved',
                    resolved_at=?,
                    updated_at=?
                WHERE id=?
                """,
                (now_iso, now_iso, incident_id),
            )
        else:
            cur = c.execute(
                """
                UPDATE guardrail_incidents
                SET status='open',
                    updated_at=?,
                    resolved_at=NULL
                WHERE id=?
                """,
                (now_iso, incident_id),
            )
        c.commit()
        return int(cur.rowcount or 0)


def create_incident_task(
    incident_id: int,
    due_at: str,
    owner: str,
    priority: str,
    title: str,
    action_type: str,
    payload_json: str,
    now_iso: str,
) -> int:
    with conn() as c:
        cur = c.execute(
            """
            INSERT INTO incident_tasks
            (incident_id, created_at, updated_at, due_at, owner, priority, title, action_type, payload_json, status, done_at, overdue_since, retry_count, reopen_count, last_sla_alert_bucket, last_sla_alert_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', NULL, NULL, 0, 0, NULL, NULL)
            """,
            (incident_id, now_iso, now_iso, due_at, owner, priority, title, action_type, payload_json),
        )
        audit = {"created": True, "status": "pending", "owner": owner, "priority": priority, "due_at": due_at}
        c.execute(
            """
            INSERT INTO incident_task_audit (task_id, actor, action, change_json, created_at)
            VALUES (?, 'system', 'create', ?, ?)
            """,
            (int(cur.lastrowid or 0), json.dumps(audit, ensure_ascii=False), now_iso),
        )
        c.commit()
        return int(cur.lastrowid or 0)


def has_active_incident_task(incident_id: int, action_type: str) -> bool:
    with conn() as c:
        row = c.execute(
            """
            SELECT 1
            FROM incident_tasks
            WHERE incident_id = ?
              AND action_type = ?
              AND status IN ('pending', 'in_progress')
            LIMIT 1
            """,
            (incident_id, action_type),
        ).fetchone()
        return row is not None


def list_incident_tasks(status: str = "", limit: int = 120) -> List[Dict[str, Any]]:
    sql = """
        SELECT
          id, incident_id, created_at, updated_at, due_at, owner, priority, title, action_type,
          payload_json, status, done_at, overdue_since, retry_count, reopen_count, last_sla_alert_bucket, last_sla_alert_at
        FROM incident_tasks
        WHERE 1=1
    """
    args: List[Any] = []
    if status:
        sql += " AND status = ?"
        args.append(status)
    sql += " ORDER BY due_at ASC, updated_at DESC LIMIT ?"
    args.append(limit)
    with conn() as c:
        rows = c.execute(sql, tuple(args)).fetchall()
        return [dict(r) for r in rows]


def get_incident_task(task_id: int) -> Optional[Dict[str, Any]]:
    with conn() as c:
        row = c.execute(
            """
            SELECT
              id, incident_id, created_at, updated_at, due_at, owner, priority, title, action_type,
              payload_json, status, done_at, overdue_since, retry_count, reopen_count, last_sla_alert_bucket, last_sla_alert_at
            FROM incident_tasks
            WHERE id = ?
            """,
            (task_id,),
        )
        return dict(row) if row else None


def update_incident_task_status(
    task_id: int,
    now_iso: str,
    status: str = "",
    owner: str = "",
    priority: str = "",
    due_at: Optional[str] = None,
    actor: str = "admin",
    reason: str = "",
    expected_updated_at: str = "",
) -> int:
    with conn() as c:
        row = c.execute("SELECT * FROM incident_tasks WHERE id = ?", (task_id,)).fetchone()
        if not row:
            return 0
        prev = dict(row)
        if expected_updated_at and str(prev.get("updated_at") or "") != expected_updated_at:
            return -1
        next_status = status or str(prev.get("status") or "pending")
        next_owner = owner or str(prev.get("owner") or "ops")
        next_priority = (priority or str(prev.get("priority") or "P2")).upper()
        if next_priority not in {"P1", "P2", "P3"}:
            next_priority = "P2"
        next_due_at = due_at if due_at is not None else str(prev.get("due_at") or now_iso)
        next_retry = int(prev.get("retry_count") or 0)
        next_reopen = int(prev.get("reopen_count") or 0)
        was_terminal = str(prev.get("status") or "") in {"done", "cancelled"}
        is_reopen = was_terminal and next_status == "in_progress"
        if is_reopen:
            next_retry += 1
            next_reopen += 1

        done_at = str(prev.get("done_at") or "") or None
        if next_status == "done":
            if str(prev.get("status") or "") != "done":
                done_at = now_iso
        elif status:
            done_at = None

        overdue_since = str(prev.get("overdue_since") or "") or None
        last_sla_alert_bucket = str(prev.get("last_sla_alert_bucket") or "") or None
        last_sla_alert_at = str(prev.get("last_sla_alert_at") or "") or None
        if next_status in {"done", "cancelled"}:
            overdue_since = None
            last_sla_alert_bucket = None
            last_sla_alert_at = None
        elif due_at is not None:
            overdue_since = None
            last_sla_alert_bucket = None
            last_sla_alert_at = None
        if next_status in {"pending", "in_progress"} and next_due_at and next_due_at < now_iso and not overdue_since:
            overdue_since = now_iso

        cur = c.execute(
            """
            UPDATE incident_tasks
            SET status = ?,
                owner = ?,
                priority = ?,
                due_at = ?,
                updated_at = ?,
                done_at = ?,
                overdue_since = ?,
                retry_count = ?,
                reopen_count = ?,
                last_sla_alert_bucket = ?,
                last_sla_alert_at = ?
            WHERE id = ?
            """,
            (
                next_status,
                next_owner,
                next_priority,
                next_due_at,
                now_iso,
                done_at,
                overdue_since,
                next_retry,
                next_reopen,
                last_sla_alert_bucket,
                last_sla_alert_at,
                task_id,
            ),
        )

        change: Dict[str, Any] = {}
        for key, new_value in (
            ("status", next_status),
            ("owner", next_owner),
            ("priority", next_priority),
            ("due_at", next_due_at),
            ("done_at", done_at),
            ("overdue_since", overdue_since),
            ("retry_count", next_retry),
            ("reopen_count", next_reopen),
            ("last_sla_alert_bucket", last_sla_alert_bucket),
            ("last_sla_alert_at", last_sla_alert_at),
        ):
            old_value = prev.get(key)
            if old_value != new_value:
                change[key] = {"from": old_value, "to": new_value}
        if reason.strip():
            change["reason"] = reason.strip()[:300]
        if is_reopen:
            change["reopen_rule"] = "done_or_cancelled_to_in_progress"
        if change:
            c.execute(
                """
                INSERT INTO incident_task_audit (task_id, actor, action, change_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (task_id, (actor or "admin")[:120], "update", json.dumps(change, ensure_ascii=False), now_iso),
            )
        c.commit()
        return int(cur.rowcount or 0)


def list_incident_task_audit(limit: int = 200, task_id: int = 0) -> List[Dict[str, Any]]:
    sql = """
        SELECT id, task_id, actor, action, change_json, created_at
        FROM incident_task_audit
        WHERE 1=1
    """
    args: List[Any] = []
    if task_id > 0:
        sql += " AND task_id = ?"
        args.append(task_id)
    sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
    args.append(limit)
    with conn() as c:
        rows = c.execute(sql, tuple(args)).fetchall()
        return [dict(r) for r in rows]


def mark_incident_task_sla_alert(task_id: int, bucket: str, now_iso: str) -> int:
    with conn() as c:
        cur = c.execute(
            """
            UPDATE incident_tasks
            SET last_sla_alert_bucket = ?,
                last_sla_alert_at = ?,
                updated_at = updated_at
            WHERE id = ?
            """,
            (bucket, now_iso, int(task_id)),
        )
        if int(cur.rowcount or 0) > 0:
            c.execute(
                """
                INSERT INTO incident_task_audit (task_id, actor, action, change_json, created_at)
                VALUES (?, 'system', 'sla_alert', ?, ?)
                """,
                (int(task_id), json.dumps({"bucket": bucket}, ensure_ascii=False), now_iso),
            )
        c.commit()
        return int(cur.rowcount or 0)


def create_scenario_snapshot(
    created_at: str,
    name: str,
    days: int,
    history_days: int,
    horizon_days: int,
    target_revenue: float,
    budget_change_pct: float,
    conv_uplift_pct: float,
    spend_change_pct: float,
    include_test: bool,
    include_spam: bool,
    summary_json: str,
) -> int:
    with conn() as c:
        cur = c.execute(
            """
            INSERT INTO scenario_snapshots
            (created_at, name, days, history_days, horizon_days, target_revenue, budget_change_pct, conv_uplift_pct, spend_change_pct, include_test, include_spam, summary_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                created_at,
                name[:140],
                int(days),
                int(history_days),
                int(horizon_days),
                float(target_revenue),
                float(budget_change_pct),
                float(conv_uplift_pct),
                float(spend_change_pct),
                1 if include_test else 0,
                1 if include_spam else 0,
                summary_json,
            ),
        )
        c.commit()
        return int(cur.lastrowid or 0)


def list_scenario_snapshots(limit: int = 30) -> List[Dict[str, Any]]:
    with conn() as c:
        rows = c.execute(
            """
            SELECT id, created_at, name, days, history_days, horizon_days, target_revenue, budget_change_pct, conv_uplift_pct, spend_change_pct, include_test, include_spam, summary_json
            FROM scenario_snapshots
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_scenario_snapshot(snapshot_id: int) -> Optional[Dict[str, Any]]:
    with conn() as c:
        row = c.execute(
            """
            SELECT id, created_at, name, days, history_days, horizon_days, target_revenue, budget_change_pct, conv_uplift_pct, spend_change_pct, include_test, include_spam, summary_json
            FROM scenario_snapshots
            WHERE id = ?
            """,
            (snapshot_id,),
        ).fetchone()
        return dict(row) if row else None


def delete_scenario_snapshot(snapshot_id: int) -> int:
    with conn() as c:
        cur = c.execute("DELETE FROM scenario_snapshots WHERE id = ?", (snapshot_id,))
        c.commit()
        return int(cur.rowcount or 0)


def leads_pending_touch(limit: int = 120) -> List[Dict[str, Any]]:
    with conn() as c:
        rows = c.execute(
            """
            SELECT
              l.id, l.form_type, l.payload_json, l.source_path, l.created_at,
              COALESCE(m.status, 'new') AS lead_status,
              COALESCE(m.notes, '') AS lead_notes,
              m.follow_up_at,
              m.last_contact_at,
              COALESCE(m.is_test, 0) AS is_test,
              COALESCE(m.is_spam, 0) AS is_spam,
              COALESCE(m.lost_reason, '') AS lost_reason,
              m.booked_slot,
              COALESCE(m.autopilot_priority, 'P3') AS autopilot_priority,
              COALESCE(m.autopilot_next_action, 'review') AS autopilot_next_action,
              m.autopilot_next_action_due_at AS autopilot_next_action_due_at,
              COALESCE(m.autopilot_owner_queue, 'sales') AS autopilot_owner_queue,
              m.autopilot_updated_at AS autopilot_updated_at,
              m.win_probability AS win_probability,
              COALESCE(m.win_recommendation, '') AS win_recommendation,
              COALESCE(m.win_model_version, '') AS win_model_version,
              m.win_updated_at AS win_updated_at,
              COALESCE(m.deal_value, 0) AS deal_value
            FROM leads l
            LEFT JOIN lead_meta m ON m.lead_id = l.id
            WHERE COALESCE(m.status, 'new') IN ('new', 'in_progress')
              AND COALESCE(m.is_test, 0) = 0
              AND COALESCE(m.is_spam, 0) = 0
            ORDER BY l.created_at ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def list_execution_connectors() -> List[Dict[str, Any]]:
    with conn() as c:
        rows = c.execute(
            """
            SELECT channel, provider, mode, status, daily_change_limit_pct, last_sync_at, last_result_json, updated_at
            FROM execution_connectors
            ORDER BY channel ASC
            """
        ).fetchall()
        return [dict(r) for r in rows]


def upsert_execution_connector(
    channel: str,
    provider: str,
    mode: str,
    status: str,
    daily_change_limit_pct: float,
    updated_at: str,
) -> None:
    with conn() as c:
        c.execute(
            """
            INSERT INTO execution_connectors
            (channel, provider, mode, status, daily_change_limit_pct, last_sync_at, last_result_json, updated_at)
            VALUES (?, ?, ?, ?, ?, NULL, '{}', ?)
            ON CONFLICT(channel) DO UPDATE SET
              provider=excluded.provider,
              mode=excluded.mode,
              status=excluded.status,
              daily_change_limit_pct=excluded.daily_change_limit_pct,
              updated_at=excluded.updated_at
            """,
            (channel, provider, mode, status, float(daily_change_limit_pct), updated_at),
        )
        c.commit()


def update_execution_connector_sync(channel: str, last_sync_at: str, last_result_json: str, updated_at: str) -> int:
    with conn() as c:
        cur = c.execute(
            """
            UPDATE execution_connectors
            SET last_sync_at = ?,
                last_result_json = ?,
                updated_at = ?
            WHERE channel = ?
            """,
            (last_sync_at, last_result_json, updated_at, channel),
        )
        c.commit()
        return int(cur.rowcount or 0)


def create_approval(
    entity_type: str,
    entity_id: str,
    action: str,
    payload_json: str,
    threshold_value: float,
    requested_by: str,
    note: str,
    created_at: str,
) -> int:
    with conn() as c:
        cur = c.execute(
            """
            INSERT INTO approvals
            (entity_type, entity_id, action, payload_json, threshold_value, status, requested_by, decided_by, note, created_at, decided_at)
            VALUES (?, ?, ?, ?, ?, 'pending', ?, NULL, ?, ?, NULL)
            """,
            (entity_type, entity_id, action, payload_json, float(threshold_value), requested_by, note[:400], created_at),
        )
        c.commit()
        return int(cur.lastrowid or 0)


def list_approvals(status: str = "", limit: int = 120) -> List[Dict[str, Any]]:
    sql = """
        SELECT id, entity_type, entity_id, action, payload_json, threshold_value, status, requested_by, decided_by, note, created_at, decided_at
        FROM approvals
        WHERE 1=1
    """
    args: List[Any] = []
    if status:
        sql += " AND status = ?"
        args.append(status)
    sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
    args.append(int(limit))
    with conn() as c:
        rows = c.execute(sql, tuple(args)).fetchall()
        return [dict(r) for r in rows]


def get_approval(approval_id: int) -> Optional[Dict[str, Any]]:
    with conn() as c:
        row = c.execute(
            """
            SELECT id, entity_type, entity_id, action, payload_json, threshold_value, status, requested_by, decided_by, note, created_at, decided_at
            FROM approvals
            WHERE id = ?
            """,
            (approval_id,),
        ).fetchone()
        return dict(row) if row else None


def update_approval_status(approval_id: int, status: str, decided_by: str, note: str, decided_at: str) -> int:
    with conn() as c:
        cur = c.execute(
            """
            UPDATE approvals
            SET status = ?,
                decided_by = ?,
                note = CASE WHEN ? != '' THEN ? ELSE note END,
                decided_at = ?
            WHERE id = ?
            """,
            (status, decided_by, note, note, decided_at, int(approval_id)),
        )
        c.commit()
        return int(cur.rowcount or 0)


def create_execution_run(
    connector_channel: str,
    action: str,
    request_json: str,
    created_at: str,
    plan_id: Optional[int] = None,
    item_id: Optional[int] = None,
) -> int:
    with conn() as c:
        cur = c.execute(
            """
            INSERT INTO execution_runs
            (connector_channel, plan_id, item_id, action, status, request_json, response_json, created_at, finished_at)
            VALUES (?, ?, ?, ?, 'pending', ?, '{}', ?, NULL)
            """,
            (connector_channel, plan_id, item_id, action, request_json, created_at),
        )
        c.commit()
        return int(cur.lastrowid or 0)


def finish_execution_run(run_id: int, status: str, response_json: str, finished_at: str) -> int:
    with conn() as c:
        cur = c.execute(
            """
            UPDATE execution_runs
            SET status = ?,
                response_json = ?,
                finished_at = ?
            WHERE id = ?
            """,
            (status, response_json, finished_at, int(run_id)),
        )
        c.commit()
        return int(cur.rowcount or 0)


def list_execution_runs(limit: int = 120, channel: str = "") -> List[Dict[str, Any]]:
    sql = """
        SELECT id, connector_channel, plan_id, item_id, action, status, request_json, response_json, created_at, finished_at
        FROM execution_runs
        WHERE 1=1
    """
    args: List[Any] = []
    if channel:
        sql += " AND connector_channel = ?"
        args.append(channel)
    sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
    args.append(int(limit))
    with conn() as c:
        rows = c.execute(sql, tuple(args)).fetchall()
        return [dict(r) for r in rows]


def create_experiment(
    name: str,
    scope: str,
    metric_primary: str,
    allocation_mode: str,
    created_at: str,
) -> int:
    with conn() as c:
        cur = c.execute(
            """
            INSERT INTO experiments
            (name, scope, status, metric_primary, allocation_mode, created_at, updated_at)
            VALUES (?, ?, 'draft', ?, ?, ?, ?)
            """,
            (name[:180], scope[:80], metric_primary[:80], allocation_mode[:40], created_at, created_at),
        )
        c.commit()
        return int(cur.lastrowid or 0)


def update_experiment_status(experiment_id: int, status: str, updated_at: str) -> int:
    with conn() as c:
        cur = c.execute(
            """
            UPDATE experiments
            SET status = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (status, updated_at, int(experiment_id)),
        )
        c.commit()
        return int(cur.rowcount or 0)


def list_experiments(limit: int = 40, status: str = "") -> List[Dict[str, Any]]:
    sql = """
        SELECT id, name, scope, status, metric_primary, allocation_mode, created_at, updated_at
        FROM experiments
        WHERE 1=1
    """
    args: List[Any] = []
    if status:
        sql += " AND status = ?"
        args.append(status)
    sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
    args.append(int(limit))
    with conn() as c:
        rows = c.execute(sql, tuple(args)).fetchall()
        return [dict(r) for r in rows]


def get_experiment(experiment_id: int) -> Optional[Dict[str, Any]]:
    with conn() as c:
        row = c.execute(
            """
            SELECT id, name, scope, status, metric_primary, allocation_mode, created_at, updated_at
            FROM experiments
            WHERE id = ?
            """,
            (int(experiment_id),),
        ).fetchone()
        return dict(row) if row else None


def upsert_experiment_arms(experiment_id: int, arms: List[Tuple[str, str, float, str]]) -> int:
    if not arms:
        return 0
    with conn() as c:
        for arm_key, label, weight, config_json in arms:
            c.execute(
                """
                INSERT INTO experiment_arms (experiment_id, arm_key, label, weight, config_json)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(experiment_id, arm_key) DO UPDATE SET
                  label=excluded.label,
                  weight=excluded.weight,
                  config_json=excluded.config_json
                """,
                (int(experiment_id), arm_key[:60], label[:140], float(weight), config_json),
            )
        c.commit()
        return len(arms)


def list_experiment_arms(experiment_id: int) -> List[Dict[str, Any]]:
    with conn() as c:
        rows = c.execute(
            """
            SELECT id, experiment_id, arm_key, label, weight, config_json
            FROM experiment_arms
            WHERE experiment_id = ?
            ORDER BY id ASC
            """,
            (int(experiment_id),),
        ).fetchall()
        return [dict(r) for r in rows]


def insert_experiment_event(
    experiment_id: int,
    arm_key: str,
    event_type: str,
    value: float,
    session_id: str,
    lead_id: str,
    created_at: str,
) -> int:
    with conn() as c:
        cur = c.execute(
            """
            INSERT INTO experiment_events
            (experiment_id, arm_key, event_type, value, session_id, lead_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (int(experiment_id), arm_key[:60], event_type[:60], float(value), session_id[:120], lead_id[:120], created_at),
        )
        c.commit()
        return int(cur.lastrowid or 0)


def list_experiment_events(experiment_id: int, limit: int = 5000) -> List[Dict[str, Any]]:
    with conn() as c:
        rows = c.execute(
            """
            SELECT id, experiment_id, arm_key, event_type, value, session_id, lead_id, created_at
            FROM experiment_events
            WHERE experiment_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (int(experiment_id), int(limit)),
        ).fetchall()
        return [dict(r) for r in rows]


def create_target_commit(
    period_start: str,
    period_end: str,
    target_revenue: float,
    owner: str,
    status: str,
    created_at: str,
) -> int:
    with conn() as c:
        cur = c.execute(
            """
            INSERT INTO target_commits
            (period_start, period_end, target_revenue, owner, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (period_start, period_end, float(target_revenue), owner[:80], status[:40], created_at, created_at),
        )
        c.commit()
        return int(cur.lastrowid or 0)


def close_other_target_commits(active_commit_id: int, updated_at: str) -> int:
    with conn() as c:
        cur = c.execute(
            """
            UPDATE target_commits
            SET status='closed',
                updated_at=?
            WHERE id != ?
              AND status = 'active'
            """,
            (updated_at, int(active_commit_id)),
        )
        c.commit()
        return int(cur.rowcount or 0)


def get_active_target_commit() -> Optional[Dict[str, Any]]:
    with conn() as c:
        row = c.execute(
            """
            SELECT id, period_start, period_end, target_revenue, owner, status, created_at, updated_at
            FROM target_commits
            WHERE status = 'active'
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """
        ).fetchone()
        return dict(row) if row else None


def upsert_target_daily_snapshot(
    commit_id: int,
    day_iso: str,
    actual_revenue: float,
    expected_revenue: float,
    gap: float,
    risk_level: str,
    recommendations_json: str,
    created_at: str,
) -> None:
    with conn() as c:
        c.execute(
            """
            INSERT INTO target_daily_snapshots
            (commit_id, day_iso, actual_revenue, expected_revenue, gap, risk_level, recommendations_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(commit_id, day_iso) DO UPDATE SET
              actual_revenue=excluded.actual_revenue,
              expected_revenue=excluded.expected_revenue,
              gap=excluded.gap,
              risk_level=excluded.risk_level,
              recommendations_json=excluded.recommendations_json,
              created_at=excluded.created_at
            """,
            (
                int(commit_id),
                day_iso,
                float(actual_revenue),
                float(expected_revenue),
                float(gap),
                risk_level[:20],
                recommendations_json,
                created_at,
            ),
        )
        c.commit()


def list_target_daily_snapshots(commit_id: int, limit: int = 60) -> List[Dict[str, Any]]:
    with conn() as c:
        rows = c.execute(
            """
            SELECT id, commit_id, day_iso, actual_revenue, expected_revenue, gap, risk_level, recommendations_json, created_at
            FROM target_daily_snapshots
            WHERE commit_id = ?
            ORDER BY day_iso DESC
            LIMIT ?
            """,
            (int(commit_id), int(limit)),
        ).fetchall()
        return [dict(r) for r in rows]


def insert_autonomous_run_log(run_type: str, status: str, summary_json: str, created_at: str) -> int:
    with conn() as c:
        cur = c.execute(
            """
            INSERT INTO autonomous_run_log (run_type, status, summary_json, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (run_type[:60], status[:20], summary_json, created_at),
        )
        c.commit()
        return int(cur.lastrowid or 0)


def list_autonomous_run_log(run_type: str = "", limit: int = 80) -> List[Dict[str, Any]]:
    sql = """
        SELECT id, run_type, status, summary_json, created_at
        FROM autonomous_run_log
        WHERE 1=1
    """
    args: List[Any] = []
    if run_type:
        sql += " AND run_type = ?"
        args.append(run_type)
    sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
    args.append(int(limit))
    with conn() as c:
        rows = c.execute(sql, tuple(args)).fetchall()
        return [dict(r) for r in rows]
