"""HTTP surface for the single-screen review app."""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import agent, catalog, planner, service, store, tools
from .config import ROOT, settings

app = FastAPI(title="Restock Agent", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")


class PlanIn(BaseModel):
    budget_usd: float = Field(gt=0, le=100_000)
    message: str = ""


class ReplanIn(BaseModel):
    draft_id: str | None = None
    budget_usd: float = Field(gt=0, le=100_000)
    exclude_skus: list[str] = []


class EditIn(BaseModel):
    draft_id: str
    quantities: dict[str, int]


class ApprovalIn(BaseModel):
    approval_token: str | None = None


def _reviewable(draft: dict[str, Any]) -> dict[str, Any]:
    """Attach the token that a human review of this exact state produces.

    The token is derived from (draft id, total, line count), so it is invalidated the moment a
    quantity changes. It is only ever returned to the review surface - never to the model.
    """
    return {**draft, "approval_token": service.approval_token(draft)}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "paypal_mode": "sandbox-live" if settings.has_paypal_creds else "mock",
        "llm_mode": "llm" if settings.has_llm else "deterministic",
        "llm_chain": [settings.llm_model] + ([settings.llm2_model] if settings.has_llm2 else []),
        "currency": settings.currency,
        "llm_model": settings.llm_model if settings.has_llm else None,
        "tools": [t["function"]["name"] for t in agent.tools.TOOL_SCHEMAS]
        if hasattr(agent, "tools") else [],
    }


@app.get("/api/inventory")
def inventory() -> dict[str, Any]:
    rows = catalog.inventory()
    return {"count": len(rows), "rows": [dict(r) for r in rows]}


@app.post("/api/plan")
def plan(body: PlanIn) -> dict[str, Any]:
    try:
        out = agent.plan(body.budget_usd, body.message)
        out["draft"] = _reviewable(out["draft"])
        return out
    except service.GuardError as exc:
        raise HTTPException(status_code=409, detail={"code": exc.code, "message": exc.message,
                                                    **exc.detail}) from exc


@app.post("/api/replan")
def replan(body: ReplanIn) -> dict[str, Any]:
    previous = store.get_draft(body.draft_id) if body.draft_id else None
    draft = planner.build_draft(budget=body.budget_usd, exclude=body.exclude_skus, previous=previous)
    store.save_draft(draft)
    store.log("draft.replanned", draft["id"],
              {"budget": draft["budget"], "total": draft["total"], "diff": draft.get("diff", [])})
    return {"draft": _reviewable(draft)}


@app.post("/api/edit")
def edit(body: EditIn) -> dict[str, Any]:
    draft = store.get_draft(body.draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail={"code": "draft_not_found"})
    updated = planner.apply_overrides(draft, body.quantities)
    store.save_draft(updated)
    store.log("draft.edited", updated["id"], {"total": updated["total"]})
    return {"draft": _reviewable(updated)}


@app.post("/api/approve/{draft_id}")
def approve(draft_id: str, body: ApprovalIn | None = None) -> dict[str, Any]:
    try:
        order = service.create_order(draft_id, body.approval_token if body else None)
        return {"draft": _reviewable(store.get_draft(draft_id) or {}), "order": order,
                "mode": "sandbox-live" if settings.has_paypal_creds else "mock"}
    except service.GuardError as exc:
        raise HTTPException(status_code=409, detail={"code": exc.code, "message": exc.message,
                                                    **exc.detail}) from exc


@app.post("/api/capture/{draft_id}")
def capture(draft_id: str, idempotency_key: str | None = None) -> dict[str, Any]:
    try:
        order = service.capture_order(draft_id, idempotency_key)
        return {"draft": store.get_draft(draft_id), "order": order}
    except service.GuardError as exc:
        raise HTTPException(status_code=409, detail={"code": exc.code, "message": exc.message,
                                                    **exc.detail}) from exc


@app.post("/api/cancel/{draft_id}")
def cancel(draft_id: str) -> dict[str, Any]:
    try:
        return service.cancel_order(draft_id)
    except service.GuardError as exc:
        raise HTTPException(status_code=409, detail={"code": exc.code, "message": exc.message,
                                                    **exc.detail}) from exc


@app.get("/api/events")
def events(limit: int = 100) -> dict[str, Any]:
    return {"events": store.events(limit)}


@app.get("/api/state")
def state() -> dict[str, Any]:
    return {"drafts": store.list_drafts(limit=10), "events": store.events(limit=50)}
