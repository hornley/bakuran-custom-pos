# Phase 5: Delivery Workflows

**Status:** Implemented; awaiting developer approval
**Branch:** `feat/delivery-workflows`
**Base:** `main`

## Purpose

Deliver a complete local delivery vertical slice without changing the compact first-screen counter flow or introducing an external courier dependency.

## Deliverables

- Add the `delivery` order channel with a one-to-one delivery record containing validated address, contact, and optional contact name metadata.
- Keep delivery metadata isolated to its owning restaurant order and reject invalid/missing metadata without partial writes.
- Add seeded active driver records and append-only assignment history with safe reassignment.
- Enforce the payment gate and cash-only boundary before assignment or dispatch.
- Guard `pending -> assigned -> out_for_delivery -> delivered` and failed/cancelled terminal paths with transaction-safe state checks.
- Make assignment retries, staff transition retries, and duplicate callback identifiers idempotent; reject conflicting idempotency reuse.
- Emit delivery and authorization audit events without putting customer address/contact values in audit detail.
- Expose a responsive secondary delivery board with address/contact, driver, history, and dispatch controls.
- Update migration, required/reset lists, seed behavior, API documentation, testing guidance, and this phase record.
- Explicitly document that there is no external courier, webhook, driver app, GPS, or route-optimization integration.

## Data and transaction notes

Migration `004_delivery.sql` creates the audit, driver, delivery, assignment-history, and idempotency tables. Delivery writes use parameterized SQL and `BEGIN IMMEDIATE`; the state update, assignment history change, audit event, and idempotency response commit together. A failed validation or conflict rolls the transaction back. The existing pytest fixture always resets an isolated temporary database.

Optional local authentication continues to be enforced by the existing middleware: viewer roles may read delivery data, while delivery mutations require an operator-capable role and CSRF validation. Authorization denials are recorded by the existing audit path.

## Verification

Run from the repository root:

```bash
backend/.venv/bin/python -m pytest -q backend/tests/test_delivery.py
./test.sh
cd frontend && npm test && npm run build
git diff --check
```

The focused tests cover missing/invalid metadata, no-mutation conflicts, order isolation, assignment/reassignment, duplicate callbacks, idempotency-key conflicts, failure/cancellation, payment and cash-only gates, audit events, and viewer denial under optional auth. Frontend tests render the delivery board contract; the production build verifies TypeScript and Vite integration.

Observed validation on 2026-09-08: focused delivery pytest `11 passed`; full `./test.sh` `28 passed` backend, `6 passed` frontend tests in 2 files, and a successful production build; `git diff --check` passed. The run emitted only the existing Starlette/httpx, anyio, and `app.seed` warnings. No live browser/E2E or external courier service was exercised. The delivery mutation header-merge regression is covered by the focused frontend test.

## Approval gate

This phase is not complete until the developer reviews and explicitly approves it. Do not merge this branch into `main` before approval. No external courier integration is included in this phase.
