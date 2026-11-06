"""Loaders for the two inputs the merchant controls: inventory CSV and supplier catalog."""
from __future__ import annotations

import csv
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from .config import ROOT

INVENTORY = ROOT / "data" / "inventory.csv"
CATALOG = ROOT / "data" / "catalog.json"


@lru_cache(maxsize=1)
def inventory() -> tuple[dict[str, Any], ...]:
    with INVENTORY.open(newline="", encoding="utf-8") as f:
        rows = []
        for r in csv.DictReader(f):
            rows.append({
                "sku": r["sku"].strip(),
                "name": r["name"].strip(),
                "on_hand": int(float(r["on_hand"])),
                "daily_sales": float(r["daily_sales"]),
                "lead_time_days": int(float(r["lead_time_days"])),
                "safety_days": int(float(r["safety_days"])),
                "unit_cost": float(r["unit_cost"]),
                "moq": int(float(r.get("moq") or 1)),
            })
    return tuple(rows)


@lru_cache(maxsize=1)
def catalog() -> dict[str, Any]:
    return json.loads(CATALOG.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def price_map() -> dict[str, dict[str, Any]]:
    return {i["sku"]: i for i in catalog()["items"]}


def price_of(sku: str) -> float:
    item = price_map().get(sku)
    if not item:
        raise KeyError(f"SKU {sku} is not in the supplier catalog")
    return float(item["unit_price"])


def reload() -> None:
    for fn in (inventory, catalog, price_map):
        fn.cache_clear()
