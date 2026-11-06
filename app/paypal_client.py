"""PayPal Orders v2 client (sandbox) + a deterministic mock for offline tests.

Real path:  POST /v1/oauth2/token -> POST /v2/checkout/orders -> POST /v2/checkout/orders/{id}/capture
Mock path:  used when PAYPAL_CLIENT_ID/SECRET are absent, so the demo and the
            boundary tests run without credentials.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import requests

from .config import settings


class PayPalError(RuntimeError):
    pass


# Sandbox test card. PayPal's documented test numbers all work in the sandbox only.
TEST_CARD = {
    "name": "Restock Agent",
    "number": "4111111111111111",
    "expiry": "2030-12",
    "security_code": "123",
    "billing_address": {
        "address_line_1": "2211 North First Street",
        "admin_area_2": "San Jose",
        "admin_area_1": "CA",
        "postal_code": "95131",
        "country_code": "US",
    },
}


@dataclass
class _Token:
    value: str = ""
    expires_at: float = 0.0
    _cache: dict[str, _Token] = field(default_factory=dict, repr=False)


class PayPalClient:
    """Thin Orders v2 wrapper with token refresh (sandbox tokens live 3-8h)."""

    def __init__(self, client_id: str | None = None, client_secret: str | None = None,
                 base_url: str | None = None, timeout: int = 30) -> None:
        self.client_id = client_id if client_id is not None else settings.client_id
        self.client_secret = client_secret if client_secret is not None else settings.client_secret
        self.base_url = (base_url or settings.base_url).rstrip("/")
        self.timeout = timeout
        self._token = _Token()

    # ---- auth -------------------------------------------------------
    def token(self) -> str:
        if self._token.value and time.time() < self._token.expires_at - 60:
            return self._token.value
        if not (self.client_id and self.client_secret):
            raise PayPalError("missing sandbox credentials (PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET)")
        r = requests.post(
            f"{self.base_url}/v1/oauth2/token",
            auth=(self.client_id, self.client_secret),
            data={"grant_type": "client_credentials"},
            headers={"Accept": "application/json", "Accept-Language": "en_US"},
            timeout=self.timeout,
        )
        if r.status_code != 200:
            raise PayPalError(f"token failed {r.status_code}: {r.text[:300]}")
        body = r.json()
        self._token = _Token(body["access_token"], time.time() + float(body.get("expires_in", 3600)))
        return self._token.value

    def _h(self, idempotency_key: str | None = None) -> dict[str, str]:
        h = {"Authorization": f"Bearer {self.token()}", "Content-Type": "application/json"}
        if idempotency_key:
            h["PayPal-Request-Id"] = idempotency_key
        return h

    # ---- orders -----------------------------------------------------
    def create_order(self, amount: float, currency: str, reference: str,
                     idempotency_key: str | None = None,
                     payment_source: dict[str, Any] | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {
            "intent": "CAPTURE",
            "purchase_units": [{
                "reference_id": reference,
                "description": f"Restock purchase order {reference}",
                "amount": {"currency_code": currency, "value": f"{amount:.2f}"},
            }],
            "application_context": {
                "brand_name": "Restock Agent",
                "user_action": "PAY_NOW",
                "shipping_preference": "NO_SHIPPING",
            },
        }
        if payment_source:
            body["payment_source"] = payment_source
        r = requests.post(f"{self.base_url}/v2/checkout/orders", json=body,
                          headers=self._h(idempotency_key), timeout=self.timeout)
        if r.status_code not in (200, 201):
            raise PayPalError(f"create_order failed {r.status_code}: {r.text[:300]}")
        data = r.json()
        approve = next((l["href"] for l in data.get("links", []) if l["rel"] in ("approve", "payer-action")), None)
        capture_id = None
        try:
            capture_id = data["purchase_units"][0]["payments"]["captures"][0]["id"]
        except (KeyError, IndexError):
            pass
        return {"id": data["id"], "status": data["status"], "approve_url": approve,
                "capture_id": capture_id, "raw": data}

    def capture_order(self, order_id: str, idempotency_key: str | None = None) -> dict[str, Any]:
        r = requests.post(f"{self.base_url}/v2/checkout/orders/{order_id}/capture",
                          json={}, headers=self._h(idempotency_key), timeout=self.timeout)
        if r.status_code not in (200, 201):
            raise PayPalError(f"capture failed {r.status_code}: {r.text[:300]}")
        data = r.json()
        return {"status": data.get("status"), "capture_id": _capture_id(data), "raw": data}

    def get_order(self, order_id: str) -> dict[str, Any]:
        """Source of truth for reconciliation: did this order actually get paid?"""
        r = requests.get(f"{self.base_url}/v2/checkout/orders/{order_id}",
                         headers=self._h(), timeout=self.timeout)
        if r.status_code != 200:
            raise PayPalError(f"get_order failed {r.status_code}: {r.text[:300]}")
        data = r.json()
        return {"id": data.get("id"), "status": data.get("status"),
                "capture_id": _capture_id(data), "raw": data}


def _capture_id(data: dict[str, Any]) -> str | None:
    try:
        return data["purchase_units"][0]["payments"]["captures"][0]["id"]
    except (KeyError, IndexError, TypeError):
        return None


class MockPayPal:
    """Offline stand-in: same interface, deterministic ids, records what it was asked to do."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.settled: dict[str, str] = {}

    def create_order(self, amount: float, currency: str, reference: str,
                     idempotency_key: str | None = None,
                     payment_source: dict[str, Any] | None = None) -> dict[str, Any]:
        oid = "MOCK-" + uuid.uuid4().hex[:12].upper()
        self.calls.append({"op": "create", "amount": amount, "currency": currency,
                           "reference": reference, "idempotency_key": idempotency_key,
                           "card": bool(payment_source)})
        completed = bool(payment_source)
        if completed:
            self.settled[oid] = "CAP-MOCK-" + uuid.uuid4().hex[:8].upper()
        return {"id": oid,
                "status": "COMPLETED" if completed else "CREATED",
                "approve_url": None if completed else f"https://www.sandbox.paypal.com/checkoutnow?token={oid}",
                "capture_id": self.settled.get(oid),
                "raw": {}}

    def capture_order(self, order_id: str, idempotency_key: str | None = None) -> dict[str, Any]:
        self.calls.append({"op": "capture", "order_id": order_id, "idempotency_key": idempotency_key})
        cap = self.settled.setdefault(order_id, "CAP-" + uuid.uuid4().hex[:10].upper())
        return {"status": "COMPLETED", "capture_id": cap, "raw": {}}

    def get_order(self, order_id: str) -> dict[str, Any]:
        return {"id": order_id,
                "status": "COMPLETED" if order_id in self.settled else "CREATED",
                "capture_id": self.settled.get(order_id), "raw": {}}

    def force_settle(self, order_id: str, capture_id: str = "CAP-FORCED") -> None:
        """Simulates 'PayPal charged it but our process died before writing the row'."""
        self.settled[order_id] = capture_id


def get_client() -> PayPalClient | MockPayPal:
    return PayPalClient() if settings.has_paypal_creds else MockPayPal()
