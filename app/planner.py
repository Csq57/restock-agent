"""The planning brain: gap math, budget-constrained allocation, and re-planning.

Deliberately deterministic and side-effect free so every number the UI shows can be
re-derived and audited. The LLM layer calls into this module through tools.
"""
from __future__ import annotations

import math
import time
from typing import Any, Iterable, Mapping

from . import catalog

EPS = 1e-9


def _money(x: float) -> float:
    return round(float(x) + EPS, 2)


def _gap(row: Mapping[str, Any]) -> int:
    """Units needed to cover lead time + safety stock."""
    target = row["daily_sales"] * (row["lead_time_days"] + row["safety_days"])
    return max(0, math.ceil(target - row["on_hand"]))


def _round_up_to(value: int, step: int) -> int:
    step = max(1, int(step or 1))
    return int(math.ceil(value / step) * step)


def _row_preview(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        cover = r["on_hand"] / r["daily_sales"] if r["daily_sales"] else 999.0
        out.append({
            "sku": r["sku"],
            "name": r["name"],
            "on_hand": r["on_hand"],
            "daily_sales": r["daily_sales"],
            "days_of_cover": round(cover, 2),
            "gap_qty": _gap(r),
            "catalog_price": catalog.price_of(r["sku"]),
        })
    return out


def build_draft(budget: float, exclude: Iterable[str] = (), overrides: Mapping[str, int] | None = None,
                previous: dict[str, Any] | None = None, _probe: bool = False) -> dict[str, Any]:
    """Allocate a purchase order under a hard budget.

    Order of allocation is urgency (days_of_cover ascending) so the money goes to
    whatever runs out first. Anything that does not fit is reported, never silently
    dropped - and each dropped line is priced, so a buyer can see what one more SKU costs.
    """
    budget = _money(max(0.0, float(budget)))
    exclude = {s.strip().upper() for s in exclude}
    overrides = {k.strip().upper(): int(v) for k, v in (overrides or {}).items()}

    candidates: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    partials: list[dict[str, Any]] = []

    for row in catalog.inventory():
        sku = row["sku"].upper()
        if sku in exclude:
            skipped.append({"sku": row["sku"], "name": row["name"], "reason": "excluded_by_user"})
            continue
        gap = _gap(row)
        if gap <= 0 and sku not in overrides:
            skipped.append({"sku": row["sku"], "name": row["name"], "reason": "sufficient_stock"})
            continue
        cover = row["on_hand"] / row["daily_sales"] if row["daily_sales"] else 999.0
        candidates.append({**row, "_gap": gap, "_cover": cover,
                           "_price": catalog.price_of(row["sku"])})

    candidates.sort(key=lambda r: (r["_cover"], -r["_gap"]))

    lines: list[dict[str, Any]] = []
    spent = 0.0

    for row in candidates:
        sku = row["sku"].upper()
        price = row["_price"]
        if sku in overrides:
            qty = max(0, overrides[sku])
        else:
            qty = _round_up_to(row["_gap"], row["moq"])

        if qty <= 0:
            skipped.append({"sku": row["sku"], "name": row["name"], "reason": "quantity_forced_to_zero"})
            continue

        cost = _money(qty * price)
        room = _money(budget - spent)

        if cost > room + EPS:
            wanted_qty = qty
            affordable = int(math.floor((room / price) + EPS))
            affordable = (affordable // row["moq"]) * row["moq"]
            if sku in overrides:
                affordable = 0  # explicit quantities are never silently trimmed
            if affordable <= 0:
                skipped.append({"sku": row["sku"], "name": row["name"],
                                "reason": "over_budget",
                                "wanted_qty": qty, "wanted_cost": cost,
                                "room_left": room,
                                "min_qty": row["moq"],
                                "min_cost": _money(row["moq"] * price),
                                "days_of_cover_now": round(row["_cover"], 2)})
                continue
            qty = affordable
            cost = _money(qty * price)
            partials.append({"sku": row["sku"], "name": row["name"],
                             "have_qty": qty,
                             "moq": row["moq"],
                             "moq_cost": _money(row["moq"] * price),
                             "days_of_cover": round(row["_cover"], 2)})

        spent = _money(spent + cost)
        lines.append({
            "sku": row["sku"],
            "name": row["name"],
            "qty": qty,
            "unit_price": price,
            "line_total": cost,
            "days_of_cover": round(row["_cover"], 2),
            "gap_qty": row["_gap"],
            "moq": row["moq"],
            "reason": "urgent_restock" if row["_cover"] <= row["lead_time_days"] else "top_up",
        })

    draft = {
        "id": None,
        "status": "draft",
        "budget": budget,
        "total": _money(spent),
        "currency": catalog.catalog().get("currency", "USD"),
        "supplier": catalog.catalog().get("supplier", ""),
        "lines": lines,
        "skipped": skipped,
        "generated_at": time.time(),
        "planner": "deterministic",
    }
    if previous:
        draft["diff"] = diff(previous, draft)
        draft["replanned_from"] = previous.get("id")
    if not _probe:
        draft["next_unlock"] = next_unlock(budget, _money(budget - spent), skipped, partials, exclude)
    return draft


def next_unlock(budget: float, headroom: float, skipped: list[dict[str, Any]],
                partials: list[dict[str, Any]], exclude: Iterable[str]) -> dict[str, Any] | None:
    """The single most useful "one more step" for the buyer, and what it costs.

    Two shapes, in order of usefulness:
      1. add_moq - a line already in the order was trimmed by the budget. One more minimum
         order quantity of that line is the natural next purchase.
      2. add_sku - nothing was trimmed, so quote the cheapest budget increase that actually
         brings a skipped SKU back.

    Every candidate is re-planned and re-checked, so the number cannot be decorative.
    """
    excluded = {s.strip().upper() for s in exclude}
    best: dict[str, Any] | None = None

    for p in partials:
        trial = build_draft(budget=_money(budget + p["moq_cost"]), exclude=excluded, _probe=True)
        got = next((l["qty"] for l in trial["lines"] if l["sku"] == p["sku"]), 0)
        if got <= p["have_qty"]:
            continue
        candidate = {
            "action": "add_moq",
            "sku": p["sku"],
            "name": p["name"],
            "unlock_cost": p["moq_cost"],
            "adds_qty": got - p["have_qty"],
            "budget_after": _money(budget + p["moq_cost"]),
            "days_of_cover_now": p["days_of_cover"],
        }
        if best is None or (candidate["days_of_cover_now"], candidate["unlock_cost"]) < \
                (best["days_of_cover_now"], best["unlock_cost"]):
            best = candidate
    if best:
        return best

    verified: list[dict[str, Any]] = []
    for item in skipped:
        if item["reason"] != "over_budget":
            continue
        delta = _money(item["min_cost"] - headroom)
        if delta <= 0:
            continue
        trial = build_draft(budget=_money(budget + delta), exclude=excluded, _probe=True)
        if item["sku"] not in [l["sku"] for l in trial["lines"]]:
            continue  # the extra money went to an earlier partial fill instead
        verified.append({
            "action": "add_sku",
            "sku": item["sku"],
            "name": item["name"],
            "unlock_cost": delta,
            "adds_qty": item["min_qty"],
            "budget_after": _money(budget + delta),
            "days_of_cover_now": item.get("days_of_cover_now"),
        })
    if not verified:
        return None
    affordable = [v for v in verified if v["unlock_cost"] <= budget * 0.25] or verified
    return min(affordable, key=lambda v: (v["days_of_cover_now"] or 99, v["unlock_cost"]))


def diff(old: Mapping[str, Any], new: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Human-readable change list, used by the UI and by the demo narration."""
    old_map = {l["sku"]: l["qty"] for l in old.get("lines", [])}
    new_map = {l["sku"]: l["qty"] for l in new.get("lines", [])}
    changes: list[dict[str, Any]] = []
    for sku in sorted(set(old_map) | set(new_map)):
        before, after = old_map.get(sku, 0), new_map.get(sku, 0)
        if before == after:
            continue
        where = "dropped" if after == 0 else ("added" if before == 0 else "changed")
        changes.append({"sku": sku, "from": before, "to": after, "change": where})
    return changes


def apply_overrides(draft: dict[str, Any], overrides: Mapping[str, int]) -> dict[str, Any]:
    """Re-price an existing draft after the reviewer edits quantities in the grid."""
    price_map = {l["sku"]: l["unit_price"] for l in draft["lines"]}
    new_lines = []
    total = 0.0
    for line in draft["lines"]:
        qty = int(overrides.get(line["sku"].upper(), overrides.get(line["sku"], line["qty"])))
        qty = max(0, qty)
        if qty == 0:
            continue
        line = {**line, "qty": qty, "line_total": _money(qty * price_map[line["sku"]])}
        total = _money(total + line["line_total"])
        new_lines.append(line)
    return {**draft, "lines": new_lines, "total": total,
            "status": "draft", "edited": True}
