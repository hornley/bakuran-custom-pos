# Phase 8 — Promotions and discounts

**Status:** Implementation complete; independent review approved at exact head `89ee42fb2f6c73fa6a4fb30781847b50ff4aa03f`. Developer approval is required before merge.
**Branch:** `feat/promotions-discounts`
**Base:** `0daaa8ffc7b9ee10cf4301b42a07b1b3df90b8f6`

## Scope

Deliver a server-authoritative promotions vertical slice for operator-created manual and delivery orders. Promotions support fixed-amount and percentage discounts, one replaceable promotion before payment, tax recalculation from the discounted taxable subtotal, durable snapshots on orders and receipts, audit events, usage limits, and idempotent apply/remove mutations. The operator UI exposes apply, replacement/removal, and the resulting pricing breakdown. Customer QR remains read-only and does not receive a customer-facing discount flow.

## Contract decisions

- Codes are trimmed, case-insensitive, stored in normalized uppercase form, and unique. Names are trimmed and bounded.
- Fixed amounts and percentages are non-negative, cent/rate bounded, and cannot produce a negative discounted subtotal or total. Percentage values are at most 100; fixed discounts clamp to the subtotal.
- Validity windows are inclusive and evaluated against UTC dates. Inactive, not-yet-valid, and expired rules are rejected.
- V1 is explicitly non-stacking: applying a new code replaces the one existing applied promotion before payment. Apply and remove are audited.
- Usage is one atomic use per applied order. There is no cancellation/refund reversal lifecycle in v1.
- Managers/admins create definitions; operators may apply eligible definitions; viewers are read-only. Public QR endpoints cannot mutate promotions.
- Promotions apply to manual and operator-created delivery orders. Orders after payment, kitchen release, closure, or cancellation cannot be changed.
- Existing tax rule identity/effective dates remain snapshotted; tax amounts and total are recalculated against the discounted subtotal. Historical promotion fields are never inferred from a current definition.

## Non-goals

Refunds, voids, cancellation usage reversal, stacking, customer-facing QR discounts, payment gateways, fiscal/printer integration, and unrelated delivery/inventory/auth refactors.

## Migration and API

Use migration `008_promotions.sql` unless a newer migration exists. Add promotion definitions, applied snapshots, usage accounting, and order pricing fields, while preserving existing migration reset behavior.

- `GET /api/promotions` lists permitted promotion definitions/status.
- `POST /api/promotions` creates a manager/admin definition.
- `POST /api/orders/{id}/promotions` applies/replaces a code with a bounded `Idempotency-Key`.
- `DELETE /api/orders/{id}/promotions/{applied_id}` removes an applied promotion before payment.

Mutation responses return the complete order view, including promotion snapshot, original/discounted pricing, tax breakdown, and final total.

## Validation

Run focused backend promotion tests, the repository test wrapper, frontend tests/build, `git diff --check`, and isolated temporary-database API/browser checks. Never mutate `backend/data/app.db`. Independent review must inspect the exact pushed SHA before any merge; this phase is not complete until developer approval.
