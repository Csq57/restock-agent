"""Order lifecycle, guards, and crash reconciliation.

draft --approve(token)--> approving --create--> awaiting_capture --capture--> paid
                                     |                              |__ cancel -> cancelled
                                     |__ settled in one call ------> paid

Guards, in the order they run:
  1. approval token      - a human review of this exact draft is the only way in
  2. atomic claim        - two concurrent approves cannot both win
  3. budget ceiling      - total <= budget, re-checked after any manual edit
  4. non-empty draft
  5. catalog price drift - supplier price moved => refuse and ask for a re-plan

Reconciliation: PayPal may succeed while our write fails (crash, timeout, process kill).
Every capture attempt first re-reads the PayPal order, so a retry never double-charges and a
lost local write is repaired from the source of truth.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from typing import Any

from . import catalog, store
from .config import settings
from .paypal_client import TEST_CARD, PayPalError, get_client

EPS = 1e-9

# "card"     -> the agent holds a card on file and pays inside the create call
# "approval" -> create returns a checkoutnow link, the payer approves, then we capture
PAY_MODE = os.getenv("PAYPAL_PAYMENT_MODE", "card").strip().lower()

_SECRET = settings.approval_secret or secrets.token_hex(16)


class GuardError(RuntimeError):
    """Raised when a business rule refuses the operation. `code` is stable for the UI."""

    def __init__(self, code: str, message: str, detail: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail or {}


POLICY_KEY = "autopay_limit"


def standing_limit() -> float:
    """The merchant's standing spend limit, as stored on the server.

    The UI writes it through one endpoint; nothing about a payment request can raise it.
    Falls back to the environment value so a fresh clone still behaves predictably.
    """
    stored = store.get_policy(POLICY_KEY)
    if stored is not None:
        try:
            return float(stored)
        except ValueError:
            pass
    return float(settings.autopay_limit)


def set_standing_limit(value: float) -> float:
    if value < 0:
        raise GuardError("invalid_limit", "the standing limit cannot be negative")
    store.set_policy(POLICY_KEY, f"{float(value):.2f}")
    return standing_limit()


# ---------------------------------------------------------------- approval token
def approval_token(draft: dict[str, Any]) -> str:
    """Signs the exact reviewed state: draft id, total, and line count.

    Editing a quantity changes the total, which invalidates every token issued before the edit,
    so an approval can never be replayed against a different amount.
    """
    msg = f"{draft['id']}:{float(draft['total']):.2f}:{len(draft.get('lines', []))}".encode()
    return hmac.new(_SECRET.encode(), msg, hashlib.sha256).hexdigest()[:32]


def verify_approval(draft: dict[str, Any], token: str | None) -> None:
    expected = approval_token(draft)
    if not token or not hmac.compare_digest(str(token), expected):
        store.log("guard.approval_refused", draft.get("id", ""),
                  {"presented": bool(token), "total": draft.get("total")})
        raise GuardError(
            "approval_required",
            "approval token is missing or does not match the reviewed draft; a human must review "
            "this exact total before money moves",
            {"total": draft.get("total"), "draft_id": draft.get("id")},
        )


def _price_drift(draft: dict[str, Any]) -> list[dict[str, Any]]:
    drift = []
    for line in draft.get("lines", []):
        current = catalog.price_of(line["sku"])
        if abs(current - float(line["unit_price"])) > EPS:
            drift.append({"sku": line["sku"], "draft_price": line["unit_price"],
                          "catalog_price": current})
    return drift


def _preflight(draft: dict[str, Any]) -> None:
    if draft["total"] > draft["budget"] + EPS:
        raise GuardError("over_budget",
                         f"draft total {draft['total']:.2f} exceeds budget {draft['budget']:.2f}",
                         {"total": draft["total"], "budget": draft["budget"]})
    if not draft.get("lines"):
        raise GuardError("empty_draft", "draft has no line items")
    drift = _price_drift(draft)
    if drift:
        store.log("guard.price_drift", draft["id"], drift)
        raise GuardError("price_drift",
                         "supplier prices changed since the draft was built; re-plan to continue",
                         {"drift": drift})


# ---------------------------------------------------------------- lifecycle
def create_order(draft_id: str, token: str | None = None,
                 policy: dict[str, Any] | None = None) -> dict[str, Any]:
    """Approve and pay one draft.

    Two ways in, and only two:
      policy  - standing authorisation from the merchant ("pay up to $X automatically").
                Checked against the draft total here, server-side; the agent cannot widen it.
      token   - a one-off human review of this exact total (see approval_token).
    Anything else is refused, whichever client is calling.
    """
    current = store.get_draft(draft_id)
    if not current:
        raise GuardError("draft_not_found", f"draft {draft_id} does not exist")
    if current["status"] not in ("draft", "edited"):
        raise GuardError("illegal_transition",
                         f"draft {draft_id} is {current['status']}, expected draft",
                         {"status": current["status"]})

    authorised_by = "human_token"
    limit: float | None = None
    if policy and policy.get("autopay_limit") is not None:
        limit = float(policy["autopay_limit"])
        if current["total"] > limit + EPS:
            store.log("guard.policy_refused", draft_id,
                      {"total": current["total"], "limit": limit})
            raise GuardError(
                "over_policy_limit",
                f"draft total {current['total']:.2f} exceeds the standing limit "
                f"{limit:.2f}; a human has to approve this one",
                {"total": current["total"], "limit": limit},
            )
        authorised_by = "policy"
        store.log("policy.auto_approve", draft_id,
                  {"total": current["total"], "limit": limit})
    else:
        verify_approval(current, token)

    _preflight(current)

    draft = store.claim_for_payment(draft_id)
    if draft is None:
        raise GuardError("illegal_transition",
                         "another approval already claimed this draft",
                         {"draft_id": draft_id})

    # Re-check against the state we actually claimed: the limit has to hold for the version of
    # the draft that is about to be paid, not for the one we read a moment ago.
    if limit is not None and draft["total"] > limit + EPS:
        store.set_draft_status(draft_id, "draft")  # release the claim, nothing charged
        store.log("guard.policy_refused_after_claim", draft_id,
                  {"total": draft["total"], "limit": limit})
        raise GuardError("over_policy_limit",
                         f"draft total {draft['total']:.2f} exceeds the standing limit "
                         f"{limit:.2f} after claiming; refused",
                         {"total": draft["total"], "limit": limit})
    _preflight(draft)

    client = get_client()
    source = {"card": TEST_CARD} if PAY_MODE == "card" else None
    try:
        result = client.create_order(
            amount=draft["total"], currency=draft["currency"],
            reference=draft_id, idempotency_key=f"create-{draft_id}",
            payment_source=source,
        )
    except PayPalError as exc:
        store.set_draft_status(draft_id, "draft")  # release the claim, nothing charged
        store.log("order.create_failed", draft_id, str(exc))
        raise GuardError("create_failed", str(exc)) from exc

    # With a payment_source PayPal settles inside the create call and returns COMPLETED
    # plus a capture id; without one the order waits for payer approval.
    settled = result.get("status") == "COMPLETED"
    draft["status"] = "paid" if settled else "awaiting_capture"
    store.save_draft(draft)
    order = store.save_order({
        "draft_id": draft_id,
        "idempotency_key": f"create-{draft_id}",
        "status": "CAPTURED" if settled else "CREATED",
        "amount": draft["total"],
        "currency": draft["currency"],
        "paypal_order_id": result["id"],
        "approve_url": result.get("approve_url"),
        "capture_id": result.get("capture_id"),
    })
    store.log("order.captured" if settled else "order.created", draft_id,
              {"paypal_order_id": result["id"], "amount": draft["total"],
               "pay_mode": PAY_MODE, "capture_id": result.get("capture_id"),
               "authorised_by": authorised_by})
    return {**order, "pay_mode": PAY_MODE, "settled": settled,
            "authorised_by": authorised_by}


def reconcile(draft_id: str) -> dict[str, Any] | None:
    """Ask PayPal what actually happened and repair local state. Returns the order if settled."""
    order = store.get_order(draft_id)
    if not order or not order.get("paypal_order_id"):
        return None
    try:
        remote = get_client().get_order(order["paypal_order_id"])
    except PayPalError:
        return None
    if remote.get("status") != "COMPLETED":
        return None

    order["status"] = "CAPTURED"
    order["capture_id"] = remote.get("capture_id") or order.get("capture_id")
    store.save_order(order)
    draft = store.get_draft(draft_id) or {}
    draft["status"] = "paid"
    store.save_draft(draft)
    store.log("order.reconciled", draft_id,
              {"capture_id": order["capture_id"], "source": "paypal-get-order"})
    return {**order, "deduplicated": False, "recovered": True}


def capture_order(draft_id: str, idempotency_key: str | None = None) -> dict[str, Any]:
    key = idempotency_key or f"pay-{draft_id}"
    existing = store.get_order_by_key(key)
    if existing and existing["status"] == "CAPTURED":
        store.log("order.capture_deduplicated", draft_id, {"key": key})
        return {**existing, "deduplicated": True}

    order = store.get_order(draft_id)
    if not order:
        raise GuardError("order_not_found", f"no PayPal order for draft {draft_id}")
    if order["status"] == "CAPTURED":
        return {**order, "deduplicated": True}
    if order["status"] != "CREATED":
        raise GuardError("illegal_transition", f"order is {order['status']}")

    # Repair before acting: the previous attempt may have been charged already.
    repaired = reconcile(draft_id)
    if repaired:
        return repaired

    client = get_client()
    try:
        result = client.capture_order(order["paypal_order_id"], idempotency_key=key)
    except PayPalError as exc:
        store.log("order.capture_failed", draft_id, str(exc))
        repaired = reconcile(draft_id)
        if repaired:
            return repaired
        raise GuardError("capture_failed", str(exc)) from exc

    order["status"] = "CAPTURED"
    order["capture_id"] = result.get("capture_id")
    order["idempotency_key"] = key
    store.save_order(order)

    draft = store.get_draft(draft_id) or {}
    draft["status"] = "paid"
    store.save_draft(draft)
    store.log("order.captured", draft_id,
              {"capture_id": order["capture_id"], "amount": order["amount"]})
    return {**order, "deduplicated": False}


def cancel_order(draft_id: str) -> dict[str, Any]:
    draft = store.get_draft(draft_id)
    if not draft:
        raise GuardError("draft_not_found", f"draft {draft_id} does not exist")
    if draft["status"] in ("paid", "approving"):
        raise GuardError("illegal_transition",
                         f"a {draft['status']} order cannot be cancelled",
                         {"status": draft["status"]})
    draft["status"] = "cancelled"
    store.save_draft(draft)
    order = store.get_order(draft_id)
    if order and order["status"] == "CREATED":
        order["status"] = "CANCELLED"
        store.save_order(order)
    store.log("order.cancelled", draft_id, {})
    return {"draft_id": draft_id, "status": "cancelled"}
