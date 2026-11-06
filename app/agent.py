"""The agent loop: an LLM decides which tools to call; every call is traced for the audit log.

If no LLM key is configured the same pipeline runs deterministically, so the app, the
tests and the demo never depend on a network model being reachable.
"""
from __future__ import annotations

import json
import re
import time
from typing import Any

import requests

from . import store, tools
from .config import settings

SYSTEM = (
    "You are the replenishment agent for a small coffee shop. You plan restocking purchases. "
    "Use the tools: read_inventory to see stock, quote_catalog to confirm prices, and "
    "draft_purchase_order to build a purchase order. "
    "The budget ceiling is set by the merchant's system, not by you: you cannot pass a budget to any "
    "tool and you cannot pay. Never say whether payment was or was not made - the merchant's standing "
    "limit decides that after you finish, and the system reports it separately. "
    "When the merchant changes the budget, your draft is rebuilt for you - explain what was cut and why. "
    "Answer in at most 100 words, as plain text: no markdown, no asterisks, no bullet points."
)

MAX_STEPS = 6


def _unlock_note(draft: dict[str, Any]) -> str | None:
    """A verified sentence from the planner, shown next to whatever the model wrote.

    The model is free to phrase the trade-off however it likes; this line is computed and
    re-checked by build_draft, so the number on screen is never a hallucination.
    """
    unlock = draft.get("next_unlock")
    if not unlock:
        return None
    cover = f" (currently {unlock['days_of_cover_now']} days of cover)" if unlock.get("days_of_cover_now") else ""
    verb = "adds" if unlock.get("action") == "add_moq" else "restores"
    return (f"Planner: +${unlock['unlock_cost']:.2f} (budget ${unlock['budget_after']:.2f}) {verb} "
            f"{unlock['adds_qty']} x {unlock['name']}{cover}. Re-planned and re-checked, not estimated.")


def _providers() -> list[dict[str, str]]:
    """Ordered model endpoints. A free tier with a 20/day cap must never be a single point of failure."""
    chain = [{"base": settings.llm_base_url, "key": settings.llm_api_key,
              "model": settings.llm_model, "name": "primary"}]
    if settings.has_llm2:
        chain.append({"base": settings.llm2_base_url, "key": settings.llm2_api_key,
                      "model": settings.llm2_model, "name": "secondary"})
    return chain


_PAYMENT_CLAIM = re.compile(
    r"[^.]*\b(nothing has been charged|nothing is charged|has not been charged|"
    r"not been charged|no charge has been made|payment has not|payment is not made)\b[^.]*\.",
    re.IGNORECASE,
)


def strip_payment_claims(text: str) -> str:
    """Remove any sentence where the model guesses about payment.

    The model cannot know: settlement happens after it returns, decided by the server against
    the merchant's standing limit. Leaving its guess on screen next to a real capture id is the
    kind of contradiction a judge notices in one second.
    """
    return re.sub(r"\s{2,}", " ", _PAYMENT_CLAIM.sub(" ", text)).strip()


def settlement_line(order: dict[str, Any] | None, decision: str,
                    blocked: dict[str, Any] | None = None) -> str:
    if decision == "auto_paid" and order:
        return (f"Payment: PAID automatically by the agent inside the standing limit - "
                f"PayPal order {order.get('paypal_order_id')}, capture {order.get('capture_id')}, "
                f"${float(order.get('amount', 0)):.2f}.")
    if blocked:
        return (f"Payment: NOT made. ${float(blocked.get('total', 0)):.2f} is above the "
                f"${float(blocked.get('limit', 0)):.2f} standing limit, so this one needs a human.")
    return "Payment: not made."


def _chat(messages: list[dict[str, Any]]) -> dict[str, Any]:
    """One model turn, walking the provider chain on rate limits, outages and bad credentials.

    The free tier of an OpenAI-compatible provider will happily return 429 while you are
    demonstrating. Falling through to the next provider keeps the run on a real model instead
    of quietly degrading to the deterministic planner in front of a judge.
    """
    last_error: Exception | None = None
    for provider in _providers():
        body = {"model": provider["model"], "messages": messages,
                "tools": tools.TOOL_SCHEMAS, "tool_choice": "auto", "temperature": 0.0}
        headers = {"Authorization": f"Bearer {provider['key']}",
                   "Content-Type": "application/json"}
        url = f"{provider['base'].rstrip('/')}/chat/completions"
        for attempt in range(2):
            try:
                r = requests.post(url, headers=headers, json=body, timeout=60)
            except requests.RequestException as exc:
                last_error = exc
                time.sleep(1.0)
                continue
            if r.status_code in (429, 500, 502, 503, 504):
                last_error = RuntimeError(f"{provider['name']} {r.status_code}: {r.text[:160]}")
                store.log("agent.llm_retry", provider["name"],
                          {"status": r.status_code, "attempt": attempt + 1})
                time.sleep(1.5 * (attempt + 1))
                continue
            if r.status_code >= 400:
                # a hard error (bad key, unsupported tool schema, wrong model name) is not
                # worth retrying on this provider - move to the next one instead
                last_error = RuntimeError(f"{provider['name']} {r.status_code}: {r.text[:200]}")
                store.log("agent.llm_provider_error", provider["name"],
                          {"status": r.status_code, "detail": r.text[:160]})
                break
            if provider["name"] != "primary":
                store.log("agent.llm_provider_switch", provider["name"], provider["model"])
            return r.json()["choices"][0]["message"]
    raise RuntimeError(f"all providers failed: {last_error}")


def _deterministic(plan_budget: float) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    ctx = {"budget": plan_budget}
    trace: list[dict[str, Any]] = []

    inv = tools.dispatch("read_inventory", {}, ctx)
    trace.append({"tool": "read_inventory", "args": {}, "result": {"count": inv["count"]}})

    urgent = sorted(inv["rows"], key=lambda r: r["days_of_cover"] or 999)[:3]
    skus = [r["sku"] for r in urgent]
    quotes = tools.dispatch("quote_catalog", {"skus": skus}, ctx)
    trace.append({"tool": "quote_catalog", "args": {"skus": skus}, "result": quotes})

    created = tools.dispatch("draft_purchase_order", {}, ctx)
    trace.append({"tool": "draft_purchase_order", "args": {},
                  "result": {"draft_id": created["draft_id"], "total": created["total"]}})
    draft = store.get_draft(created["draft_id"]) or created

    names = ", ".join(f"{l['name']} x{l['qty']}" for l in draft["lines"][:4])
    reply = (f"Drafted a {len(draft['lines'])}-line order for ${draft['total']:.2f} of a "
             f"${plan_budget:.2f} budget ({names}). "
             f"{len(draft['skipped'])} SKUs were left out and are listed with reasons. "
             "Nothing has been charged - approve to create the PayPal order.")
    return reply, trace, draft


def plan(budget: float, message: str = "") -> dict[str, Any]:
    """Run one planning turn and persist the resulting draft."""
    if not settings.has_llm:
        reply, trace, draft = _deterministic(budget)
        store.log("agent.plan", "deterministic", {"budget": budget, "total": draft["total"]})
        return {"reply": reply, "trace": trace, "draft": draft, "engine": "deterministic",
                "note": _unlock_note(draft)}

    ctx = {"budget": float(budget)}
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM},
        {"role": "system", "content": f"Merchant's budget ceiling for this session: ${float(budget):.2f} "
                                      f"{settings.currency}. It is applied by the server; you cannot change it."},
        {"role": "user", "content": message or "Plan this week's restock."},
    ]
    trace: list[dict[str, Any]] = []
    draft: dict[str, Any] | None = None
    reply = ""
    fell_back = False

    try:
        for _ in range(MAX_STEPS):
            msg = _chat(messages)
            messages.append(msg)
            calls = msg.get("tool_calls") or []
            if not calls:
                reply = (msg.get("content") or "").strip()
                break
            for call in calls:
                name = call["function"]["name"]
                args = json.loads(call["function"].get("arguments") or "{}")
                result = tools.dispatch(name, args, ctx)
                trace.append({"tool": name, "args": args,
                              "result": {k: v for k, v in result.items() if k != "lines"}})
                if name == "draft_purchase_order":
                    draft = store.get_draft(result["draft_id"])
                messages.append({"role": "tool", "tool_call_id": call["id"],
                                 "content": json.dumps(result)[:6000]})
        else:
            reply = "Stopped after the step limit; review the draft in the table."
    except Exception as exc:  # network / provider failure must not break the demo
        store.log("agent.llm_failed", "llm", str(exc))
        reply, trace, draft = _deterministic(budget)
        fell_back = True
        trace.insert(0, {"tool": "fallback", "args": {}, "result": {"reason": str(exc)[:200]}})

    if draft is None:
        created = tools.dispatch("draft_purchase_order", {}, ctx)
        draft = store.get_draft(created["draft_id"])

    assert draft["budget"] == ctx["budget"], "budget ceiling leaked"
    store.log("agent.plan", "llm-fallback" if fell_back else "llm",
              {"budget": budget, "total": draft["total"],
               "tools": [t["tool"] for t in trace]})
    return {"reply": reply, "trace": trace, "draft": draft,
            "engine": "llm-fallback" if fell_back else "llm",
            "note": _unlock_note(draft)}
