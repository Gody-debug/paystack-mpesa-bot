import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import config

EAT = timezone(timedelta(hours=3))  # Kenya time, no DST


@contextmanager
def _conn():
    conn = sqlite3.connect(config.DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def start_of_today_utc() -> str:
    start = datetime.now(EAT).replace(hour=0, minute=0, second=0, microsecond=0)
    return start.astimezone(timezone.utc).isoformat(timespec="seconds")


def init_db() -> None:
    with _conn() as c:
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reference TEXT UNIQUE NOT NULL,
                batch_id TEXT NOT NULL,
                phone TEXT NOT NULL,
                email TEXT NOT NULL,
                amount_kes REAL NOT NULL,
                status TEXT NOT NULL,          -- pending | success | failed
                paystack_status TEXT,
                message TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )


def insert_transaction(reference, batch_id, phone, email, amount_kes) -> None:
    now = _now()
    with _conn() as c:
        c.execute(
            """INSERT INTO transactions
               (reference, batch_id, phone, email, amount_kes, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)""",
            (reference, batch_id, phone, email, amount_kes, now, now),
        )


def update_by_reference(reference, status, paystack_status=None, message=None) -> None:
    with _conn() as c:
        c.execute(
            """UPDATE transactions
               SET status = ?, paystack_status = COALESCE(?, paystack_status),
                   message = COALESCE(?, message), updated_at = ?
               WHERE reference = ?""",
            (status, paystack_status, message, _now(), reference),
        )


def phones_prompted_today(phones: list[str]) -> set[str]:
    """
    Phones that already have a pending or successful prompt TODAY (Kenya time).
    Yesterday's payments don't block today's, since clients come back daily.
    Chunked to stay under SQLite's variable limit, so any list size works.
    """
    found: set[str] = set()
    since = start_of_today_utc()
    with _conn() as c:
        for i in range(0, len(phones), 500):
            chunk = phones[i : i + 500]
            marks = ",".join("?" * len(chunk))
            rows = c.execute(
                f"SELECT DISTINCT phone FROM transactions "
                f"WHERE status IN ('pending','success') AND created_at >= ? "
                f"AND phone IN ({marks})",
                [since, *chunk],
            ).fetchall()
            found.update(r["phone"] for r in rows)
    return found


def get_transactions(batch_id: str | None = None) -> list[dict]:
    with _conn() as c:
        if batch_id:
            rows = c.execute(
                "SELECT * FROM transactions WHERE batch_id = ? ORDER BY id DESC", (batch_id,)
            ).fetchall()
        else:
            rows = c.execute("SELECT * FROM transactions ORDER BY id DESC").fetchall()
    return [dict(r) for r in rows]


def get_batch_ids() -> list[str]:
    with _conn() as c:
        rows = c.execute(
            "SELECT batch_id, MAX(id) AS m FROM transactions GROUP BY batch_id ORDER BY m DESC"
        ).fetchall()
    return [r["batch_id"] for r in rows]


def get_pending_references() -> list[str]:
    with _conn() as c:
        rows = c.execute("SELECT reference FROM transactions WHERE status = 'pending'").fetchall()
    return [r["reference"] for r in rows]
