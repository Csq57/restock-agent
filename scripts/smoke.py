"""Smoke run: plan -> approve -> capture against whatever PayPal mode is configured.

  python -m scripts.smoke                 # uses mock unless .env has sandbox creds
  python -m scripts.smoke --budget 300
  python -m scripts.smoke --token-check   # only verifies sandbox OAuth
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import agent, service, store  # noqa: E402
from app.config import settings  # noqa: E402
from app.paypal_client import PayPalClient  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=float, default=500.0)
    ap.add_argument("--token-check", action="store_true")
    ap.add_argument("--capture", metavar="DRAFT_ID", default=None,
                    help="capture an already-created order (after the payer approved it)")
    args = ap.parse_args()

    print(f"paypal_mode={'sandbox-live' if settings.has_paypal_creds else 'mock'}  "
          f"llm={'on' if settings.has_llm else 'deterministic'}  pay_mode={service.PAY_MODE}")

    if args.capture:
        paid = service.capture_order(args.capture, f"manual-{args.capture}")
        print(f"capture: {paid['status']} id={paid['capture_id']} dedup={paid['deduplicated']}")
        return 0

    if args.token_check:
        if not settings.has_paypal_creds:
            print("no sandbox credentials in .env - nothing to check")
            return 2
        tok = PayPalClient().token()
        print(f"token ok: {tok[:12]}... (len {len(tok)})")
        return 0

    result = agent.plan(args.budget)
    draft = result["draft"]
    print(f"\n[{result['engine']}] {result['reply']}\n")
    for line in draft["lines"]:
        print(f"  {line['sku']:<9} {line['name']:<26} x{line['qty']:<3} "
              f"@{line['unit_price']:>6.2f} = {line['line_total']:>8.2f}  ({line['reason']})")
    print(f"  {'TOTAL':<38} {draft['total']:>8.2f} / budget {draft['budget']:.2f}")
    if draft["skipped"]:
        print("  left out: " + ", ".join(f"{s['sku']}({s['reason']})" for s in draft["skipped"]))

    order = service.create_order(draft["id"])
    print(f"\norder created: {order['paypal_order_id']}  (pay_mode={order.get('pay_mode')})")
    print(f"approve url  : {order['approve_url']}")

    try:
        paid = service.capture_order(draft["id"], f"smoke-{draft['id']}")
        print(f"capture      : {paid['status']} id={paid['capture_id']} "
              f"dedup={paid['deduplicated']}")
    except service.GuardError as exc:
        print(f"capture      : REFUSED {exc.code} -> {exc.message[:160]}")
        if "ORDER_NOT_APPROVED" in exc.message:
            print("               payer approval is required; open the approve url above, then:")
            print(f"               python -m scripts.smoke --capture {draft['id']}")
        return 1

    print("\naudit trail:")
    for ev in reversed(store.events(limit=8)):
        print(f"  {ev['kind']:<28} {ev['ref']:<14} {ev['detail'][:90]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
