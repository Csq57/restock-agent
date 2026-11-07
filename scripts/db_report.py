"""Print the local session state as a table (used before the evidence audit)."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402


def main() -> None:
    c = sqlite3.connect(settings.db_path)
    c.row_factory = sqlite3.Row
    print("db:", settings.db_path)
    print("drafts:", c.execute("SELECT count(1) FROM drafts").fetchone()[0])
    print("orders:", c.execute("SELECT count(1) FROM orders").fetchone()[0])
    for r in c.execute("SELECT draft_id, status, amount, currency, paypal_order_id, capture_id "
                       "FROM orders ORDER BY created_at"):
        print(f"  draft={r['draft_id']} {r['status']:<10} {r['amount']:>8.2f} {r['currency']} "
              f"order={r['paypal_order_id']} capture={r['capture_id']}")
    print("events:", c.execute("SELECT count(1) FROM events").fetchone()[0])
    for r in c.execute("SELECT kind, count(1) n FROM events GROUP BY kind ORDER BY n DESC"):
        print(f"  {r['kind']:<28} {r['n']}")


if __name__ == "__main__":
    main()
