"""SQLite persistence: drafts, orders, and an append-only audit log."""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS drafts (
    id          TEXT PRIMARY KEY,
    created_at  REAL NOT NULL,
    status      TEXT NOT NULL,
    budget      REAL NOT NULL,
    total       REAL NOT NULL,
    payload     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS orders (
    draft_id        TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    status          TEXT NOT NULL,
    amount          REAL NOT NULL,
    currency        TEXT NOT NULL,
    paypal_order_id TEXT,
    approve_url     TEXT,
    capture_id      TEXT,
    created_at      REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    ts     REAL NOT NULL,
    kind   TEXT NOT NULL,
    ref    TEXT,
    detail TEXT
);
"""


@contextmanager
def conn(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    db = path or settings.db_path
    db.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(db)
    c.row_factory = sqlite3.Row
    try:
        c.executescript(SCHEMA)
        yield c
        c.commit()
    finally:
        c.close()


def log(kind: str, ref: str = "", detail: Any = "") -> None:
    if not isinstance(detail, str):
        detail = json.dumps(detail, ensure_ascii=False)
    with conn() as c:
        c.execute("INSERT INTO events(ts, kind, ref, detail) VALUES(?,?,?,?)",
                  (time.time(), kind, ref, detail))


def save_draft(draft: dict[str, Any]) -> dict[str, Any]:
    draft_id = draft.get("id") or uuid.uuid4().hex[:12]
    draft["id"] = draft_id
    with conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO drafts(id, created_at, status, budget, total, payload) "
            "VALUES(?,?,?,?,?,?)",
            (draft_id, time.time(), draft["status"], draft["budget"],
             draft["total"], json.dumps(draft, ensure_ascii=False)),
        )
    log("draft.saved", draft_id, {"total": draft["total"], "budget": draft["budget"],
                                  "lines": len(draft["lines"])})
    return draft


def get_draft(draft_id: str) -> dict[str, Any] | None:
    with conn() as c:
        row = c.execute("SELECT payload FROM drafts WHERE id=?", (draft_id,)).fetchone()
    return json.loads(row["payload"]) if row else None


def set_draft_status(draft_id: str, status: str) -> dict[str, Any] | None:
    draft = get_draft(draft_id)
    if not draft:
        return None
    draft["status"] = status
    return save_draft(draft)


def list_drafts(limit: int = 20) -> list[dict[str, Any]]:
    with conn() as c:
        rows = c.execute("SELECT payload FROM drafts ORDER BY created_at DESC LIMIT ?",
                         (limit,)).fetchall()
    return [json.loads(r["payload"]) for r in rows]


def get_order(draft_id: str) -> dict[str, Any] | None:
    with conn() as c:
        row = c.execute("SELECT * FROM orders WHERE draft_id=?", (draft_id,)).fetchone()
    return dict(row) if row else None


def get_order_by_key(key: str) -> dict[str, Any] | None:
    with conn() as c:
        row = c.execute("SELECT * FROM orders WHERE idempotency_key=?", (key,)).fetchone()
    return dict(row) if row else None


CLAIMABLE = ("draft", "edited", "approving")


def claim_for_payment(draft_id: str) -> dict[str, Any] | None:
    """Atomically move a draft into `approving`. Returns None if another caller already claimed it.

    The status check and the write happen inside one transaction, so two concurrent approves
    cannot both win - the second sees status `approving` and is refused.
    """
    with conn() as c:
        c.execute("BEGIN IMMEDIATE")
        row = c.execute("SELECT payload, status FROM drafts WHERE id=?", (draft_id,)).fetchone()
        if not row or row["status"] not in ("draft", "edited"):
            return None
        draft = json.loads(row["payload"])
        draft["status"] = "approving"
        cur = c.execute(
            "UPDATE drafts SET status='approving', payload=? WHERE id=? AND status IN ('draft','edited')",
            (json.dumps(draft, ensure_ascii=False), draft_id),
        )
        if cur.rowcount != 1:
            return None
        return draft


def save_order(order: dict[str, Any]) -> dict[str, Any]:
    with conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO orders(draft_id, idempotency_key, status, amount, currency,"
            " paypal_order_id, approve_url, capture_id, created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (order["draft_id"], order["idempotency_key"], order["status"], order["amount"],
             order["currency"], order.get("paypal_order_id"), order.get("approve_url"),
             order.get("capture_id"), time.time()),
        )
    return order


def events(limit: int = 200) -> list[dict[str, Any]]:
    with conn() as c:
        rows = c.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


def reset() -> None:
    with conn() as c:
        for t in ("drafts", "orders", "events"):
            c.execute(f"DELETE FROM {t}")
