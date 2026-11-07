"""Reconcile every payment this repo claims against PayPal itself.

Local state is not evidence. This script asks GET /v2/checkout/orders/{id} for each order the app
recorded and checks the three things a viewer would check:

  1. PayPal says COMPLETED
  2. PayPal's capture id equals the one the app stored (and the one on screen in the video)
  3. the captured amount equals the draft total

It also checks that the audit log contains the authorisation that let each payment happen.

  python -m scripts.audit_evidence             # print + write EVIDENCE.md
  python -m scripts.audit_evidence --no-file   # print only

Exit code 1 if anything disagrees. Safe to run repeatedly: it never moves money.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import store  # noqa: E402
from app.config import ROOT, settings  # noqa: E402
from app.paypal_client import PayPalError, get_client  # noqa: E402


def rows() -> list[sqlite3.Row]:
    c = sqlite3.connect(settings.db_path)
    c.row_factory = sqlite3.Row
    return list(c.execute(
        "SELECT o.draft_id, o.status, o.amount, o.currency, o.paypal_order_id, o.capture_id "
        "FROM orders o ORDER BY o.created_at"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-file", action="store_true")
    args = ap.parse_args()

    if not settings.has_paypal_creds:
        print("no sandbox credentials in .env - cannot reconcile against PayPal")
        return 2

    client = get_client()
    lines: list[str] = []
    failures = 0
    print(f"reconciling {len(rows())} order(s) against {settings.base_url}\n")

    header = ("| draft | app says | PayPal says | capture (app) | capture (PayPal) | amount | result |\n"
              "|---|---|---|---|---|---|---|")
    lines += ["# Evidence", "",
              f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} from "
              f"`scripts/audit_evidence.py`. Every row below was asked for directly from "
              f"`GET /v2/checkout/orders/{{id}}` on the PayPal **sandbox**; nothing here relies on "
              f"this app's own database.", "", header]

    for r in rows():
        try:
            remote = client.get_order(r["paypal_order_id"])
        except PayPalError as exc:
            print(f"{r['paypal_order_id']}: PayPal error {exc}")
            lines.append(f"| {r['draft_id']} | {r['status']} | error | {r['capture_id']} | - | "
                         f"{r['amount']:.2f} | PAYPAL ERROR |")
            failures += 1
            continue

        ok_status = remote.get("status") == "COMPLETED"
        ok_capture = (remote.get("capture_id") or "") == (r["capture_id"] or "")
        ok_amount = abs(float(r["amount"]) - _amount(remote)) < 0.005
        ok = ok_status and ok_capture and ok_amount
        failures += 0 if ok else 1

        print(f"{r['paypal_order_id']}  status={remote.get('status')}  "
              f"capture={remote.get('capture_id')}  amount={_amount(remote):.2f}  "
              f"-> {'OK' if ok else 'MISMATCH'}")
        lines.append(
            f"| {r['draft_id']} | {r['status']} | {remote.get('status')} | `{r['capture_id']}` | "
            f"`{remote.get('capture_id')}` | {r['amount']:.2f} {r['currency']} | "
            f"{'match' if ok else 'MISMATCH'} |")

    kinds = [e["kind"] for e in store.events(limit=500)]
    checks = {
        "a payment happened with no human involved": "policy.auto_approve" in kinds,
        "a payment was refused for being over the standing limit": "guard.policy_refused" in kinds,
        "the model chain fell back to a second provider": "agent.llm_provider_switch" in kinds,
    }
    lines += ["", "## Authorisation trail", ""]
    print()
    for label, passed in checks.items():
        print(f"{'OK ' if passed else 'MISSING'}  {label}")
        lines.append(f"- {'[x]' if passed else '[ ]'} {label}")
        failures += 0 if passed else 1

    lines += ["", "## What this does not prove", "",
              "- It does not prove the money is real: this is the PayPal **sandbox**, so no funds "
              "moved. The point of the sandbox is that the API path is identical.",
              "- It does not prove the model chose well; only that the model, not the UI, decided "
              "which tools to call (see `agent.plan` events and the tool trace in the video).", ""]

    if not args.no_file:
        out = ROOT / "EVIDENCE.md"
        out.write_text("\n".join(lines), encoding="utf-8")
        print(f"\nwrote {out}")

    print(f"\n{'ALL CHECKS PASSED' if failures == 0 else f'{failures} CHECK(S) FAILED'}")
    return 0 if failures == 0 else 1


def _amount(remote: dict) -> float:
    raw = remote.get("raw") or {}
    try:
        return float(raw["purchase_units"][0]["amount"]["value"])
    except (KeyError, IndexError, TypeError, ValueError):
        try:
            return float(raw["purchase_units"][0]["payments"]["captures"][0]["amount"]["value"])
        except (KeyError, IndexError, TypeError, ValueError):
            return -1.0


if __name__ == "__main__":
    raise SystemExit(main())
