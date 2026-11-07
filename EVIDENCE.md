# Evidence

Generated 2026-11-07 06:31 UTC from `scripts/audit_evidence.py`. Every row below was asked for directly from `GET /v2/checkout/orders/{id}` on the PayPal **sandbox**; nothing here relies on this app's own database.

| draft | app says | PayPal says | capture (app) | capture (PayPal) | amount | result |
|---|---|---|---|---|---|---|
| 9ef2952cf222 | CAPTURED | COMPLETED | `6G4474502P272802R` | `6G4474502P272802R` | 589.40 USD | match |
| 2a335eaa9b64 | CAPTURED | COMPLETED | `14A20069V5594282Y` | `14A20069V5594282Y` | 659.00 USD | match |

## Authorisation trail

- [x] a payment happened with no human involved
- [x] a payment was refused for being over the standing limit
- [x] the model chain fell back to a second provider

## What this does not prove

- It does not prove the money is real: this is the PayPal **sandbox**, so no funds moved. The point of the sandbox is that the API path is identical.
- It does not prove the model chose well; only that the model, not the UI, decided which tools to call (see `agent.plan` events and the tool trace in the video).
