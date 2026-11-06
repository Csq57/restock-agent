"""Tool layer exposed to the LLM (OpenAI function-calling schema) and reused by the API.

Hard rule: the spending ceiling is server-side state. The model may choose *what* to buy and
*why*, but it cannot pass a budget in, and it cannot pay. Anything the model sends that looks
like a budget is logged and ignored.
"""
from __future__ import annotations

from typing import Any

from . import catalog, planner, store
from .service import capture_order, create_order

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "read_inventory",
            "description": "Read the merchant's current stock levels, sales velocity, lead times and gap quantities.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "quote_catalog",
            "description": "Get live supplier unit prices for one or more SKUs before committing to a quantity.",
            "parameters": {
                "type": "object",
                "properties": {
                    "skus": {"type": "array", "items": {"type": "string"},
                             "description": "SKU codes, e.g. ['SKU-1001']"},
                },
                "required": ["skus"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "draft_purchase_order",
            "description": ("Build or rebuild a purchase-order draft. The budget is applied by the server and "
                            "cannot be set here; every line is allocated by urgency and the total never "
                            "exceeds that server-side ceiling. Call it again to re-plan."),
            "parameters": {
                "type": "object",
                "properties": {
                    "exclude_skus": {"type": "array", "items": {"type": "string"},
                                     "description": "SKUs the buyer refuses to buy this round"},
                },
                "required": [],
            },
        },
    },
]


def dispatch(name: str, args: dict[str, Any], ctx: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute one tool call. `ctx` carries server-side truth such as the budget ceiling."""
    ctx = ctx or {}

    if name == "read_inventory":
        rows = catalog.inventory()
        return {"count": len(rows), "rows": [{
            "sku": r["sku"], "name": r["name"], "on_hand": r["on_hand"],
            "daily_sales": r["daily_sales"], "lead_time_days": r["lead_time_days"],
            "safety_days": r["safety_days"],
            "days_of_cover": round(r["on_hand"] / r["daily_sales"], 2) if r["daily_sales"] else None,
        } for r in rows]}

    if name == "quote_catalog":
        out = []
        for sku in args.get("skus", []):
            try:
                item = catalog.price_map()[sku.upper()]
                out.append({"sku": sku, "name": item["name"], "unit_price": item["unit_price"]})
            except KeyError:
                out.append({"sku": sku, "error": "not_in_catalog"})
        return {"quotes": out}

    if name == "draft_purchase_order":
        budget = float(ctx.get("budget") or 0.0)
        if budget <= 0:
            raise ValueError("server did not supply a budget ceiling for this session")
        for sneaky in ("budget_usd", "budget"):
            if sneaky in args:
                store.log("agent.budget_override_refused", "llm",
                          {"model_supplied": args[sneaky], "server_budget": budget})
                break
        previous = store.list_drafts(limit=1)
        draft = planner.build_draft(
            budget=budget,
            exclude=args.get("exclude_skus", []) or [],
            previous=previous[0] if previous else None,
        )
        assert draft["budget"] == budget and draft["total"] <= budget + 1e-9
        store.save_draft(draft)
        return {"draft_id": draft["id"], "total": draft["total"], "budget": draft["budget"],
                "lines": draft["lines"], "skipped": draft["skipped"],
                "diff": draft.get("diff", [])}

    if name == "pay_purchase_order":
        # Deliberately not exposed in TOOL_SCHEMAS: only a human approval moves money.
        raise PermissionError("payment is not callable by the agent; a human must approve the draft")

    raise ValueError(f"unknown tool {name}")

