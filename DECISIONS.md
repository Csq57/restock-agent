# Engineering decision log

Why the system is shaped the way it is. Each entry: the situation, the choice, and what it rules out.
These are the decisions a reviewer would otherwise have to reverse-engineer from the code.

---

## The agent may propose a purchase order, never pay for one

**Situation.** The obvious design is to give the model a `pay_purchase_order` tool and let it decide
when to spend.

**Choice.** The payment tool is not in the model's schema at all. `app/tools.py` exposes only
`read_inventory`, `quote_catalog` and `draft_purchase_order`. `pay_purchase_order` exists in the
dispatcher so a direct call raises `PermissionError` rather than silently doing nothing.

**Rules out.** A prompt injection, a hallucinated tool call, or a model having a bad day can never
move money. The blast radius of the model is "produce a wrong draft", which a human or the policy
layer catches.

---

## The budget lives on the server, not in the tool signature

**Situation.** The first real run against a live model produced a **$5,684.50** order against a
$1,200 budget: `draft_purchase_order` accepted `budget_usd` as a model-supplied parameter, and the
model filled in `1,000,000` for it.

**Choice.** Three layers, because one is not enough:

1. `budget_usd` was removed from the tool schema — the model cannot express it.
2. If a call still carries it, the dispatcher logs `agent.budget_override_refused` and ignores it.
3. `service.py` asserts `draft["budget"] == ctx["budget"]` before anything is created.

**Rules out.** The spending limit being a suggestion. The ceiling is server state; the model's
opinion of it is not an input.

---

## An approval is a signature over a specific draft, not a boolean

**Situation.** "Approved" as a flag on a draft can be replayed: approve a $50 draft, edit it to
$5,000, and the flag still reads true.

**Choice.** `approval_token(draft)` is an HMAC over the draft's identity and its reviewed economics.
Editing a quantity changes the total, which invalidates every token issued before the edit. The
service refuses a create whose token does not match the draft it is looking at.

**Rules out.** Approve-then-edit. The token is bound to the numbers the reviewer actually saw.

---

## Claiming a draft for payment is atomic

**Situation.** Two concurrent approvals of the same draft would otherwise both pass the state check
and create two orders — the classic double-spend race.

**Choice.** `store.claim_for_payment()` takes the write lock with `BEGIN IMMEDIATE` and moves the
draft out of `reviewed` in the same transaction. The loser gets `None` and a
`GuardError("illegal_transition")`.

**Rules out.** "It passed the check a millisecond ago" as an excuse to charge twice.

---

## Create and capture are idempotent, and reconciliation is a read

**Situation.** PayPal's Orders v2 has two payment shapes, and retrying either one can double-charge.

**Choice.** In `card` mode the order is created with `payment_source.card` and PayPal settles inside
the create call, returning `COMPLETED` plus a capture id; a further capture would fail with
`ORDER_ALREADY_CAPTURED`, so it is not attempted. In `approval` mode the payer approves first and the
capture follows. Either way the final state is established by `GET /v2/checkout/orders/{id}` — a
read, not a write.

**Rules out.** Trusting the local record over the payment provider's own view of the order.

---

## Degrading is honest, not silent

**Situation.** Free-tier model quotas run out mid-demo, and a demo that dies on a 429 is worse than
one that keeps working.

**Choice.** `app/agent.py` runs a two-provider chain and retries 429/5xx, then falls through to the
other provider, then to the deterministic planner. The response reports which one answered:
`engine` is `llm`, `llm-fallback` or `deterministic`, and the trace names the fallback.

**Rules out.** A fallback that pretends to be the model. If the planner did the work, the UI says so.

---

## Verification is a script, not a claim

**Situation.** "It works" is not evidence, and a reviewer should not have to trust the README.

**Choice.** `scripts/audit_evidence.py` walks the local store and writes `EVIDENCE.md` from the actual
rows: drafts, guard refusals, approvals, orders and their reconciled status. The boundary tests run
entirely offline — PayPal is swapped for an in-process mock — so every guard can be exercised without
credentials: `python -m unittest discover -s tests -v`.

**Rules out.** Evidence that exists only in the demo video.

---

## Design decisions were pressure-tested before implementation

Non-trivial choices — the guard set, the token binding, the fallback chain — were reviewed by an
independent reviewer (an LLM used as a second opinion on the design, not as an author of it) before
being built. Two of the guards above exist because that review asked "what happens if the model does
this", and the answer at the time was "nothing stops it".
