import os
import sys
from pathlib import Path


def _require_database_url() -> str:
    dsn = (os.getenv("DATABASE_URL") or "").strip()
    if not dsn:
        raise RuntimeError("DATABASE_URL is required")
    return dsn


def _connect(dsn: str):
    try:
        import psycopg
    except Exception as exc:
        raise RuntimeError("psycopg is not installed. Add 'psycopg[binary]' to requirements.") from exc
    return psycopg.connect(dsn)


def apply_migrations() -> int:
    dsn = _require_database_url()
    root = Path(__file__).resolve().parent
    migrations_dir = root / "migrations"
    files = sorted(migrations_dir.glob("*.sql"))
    if not files:
        print("No migrations found.")
        return 0

    applied = 0
    with _connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                  version TEXT PRIMARY KEY,
                  applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
        conn.commit()

        for path in files:
            version = path.name
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM schema_migrations WHERE version = %s", (version,))
                if cur.fetchone():
                    print(f"skip  {version}")
                    continue

            sql = path.read_text(encoding="utf-8")
            with conn:
                with conn.cursor() as cur:
                    cur.execute(sql)
                    cur.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (version,))
            applied += 1
            print(f"apply {version}")

    print(f"done  {applied} migration(s) applied")
    return applied


if __name__ == "__main__":
    try:
        apply_migrations()
    except Exception as exc:
        print(f"migration failed: {exc}", file=sys.stderr)
        sys.exit(1)
