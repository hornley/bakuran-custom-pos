# Phase 4: Inventory and Purchasing Workflow

**Status:** Implemented; awaiting explicit developer approval
**Branch:** `feat/inventory-purchasing-workflow`
**Base:** `da40b9e` (`origin/main`)

## Purpose

Add a warehouse-aware back-office slice without changing the compact counter flow or its payment gate.

## Deliverables

- Warehouse-scoped inventory validates active product and warehouse references and enforces database foreign keys plus `on_hand >= reserved >= 0`.
- Reorder levels, available stock, low-stock flags, and reorder quantities are exposed per warehouse.
- Signed stock adjustments require a reason and are atomic, non-negative, and reservation-safe.
- Purchases follow `draft -> ordered -> partially_received -> received -> closed`, with `received_quantity` tracked independently on every line.
- Receipts validate all lines before mutation, support partial delivery, reject over-receipt by default, and require a reason plus manager/admin authorization for overrides when auth is enabled.
- Supported mutations persist idempotency request fingerprints and replay their stored responses without double mutation; payload/key conflicts return HTTP 409.
- Inventory and purchasing mutations write transactional audit events, including optional-auth actor IDs.
- The secondary Operations UI loads warehouse stock, low-stock/reorder controls, purchase lifecycle controls, receipts, tables, and audit history only after navigation; the compact counter screen remains focused on POS/payment/kitchen flow.
- Legacy no-body purchase receiving and `/api/stock/receipt` remain compatible where safe, and the existing payment gate is unchanged.

## Scope limitation

This is a single-store implementation. Warehouses scope stock inside one store; multi-location synchronization, cross-store transfers, and cross-store reporting are intentionally out of scope.

## Verification

- Focused inventory/purchasing backend tests cover rollback, concurrency, partial receipts, per-line completion, over-receipt, idempotency, invalid references, database constraints, optional-auth denial/authorization, and audit records.
- Frontend contract tests cover secondary loading boundaries and responsive inventory/purchasing controls.
- Full `./test.sh`.
- Frontend production build and type-check.
- `git diff --check`.

The final handoff records the exact commands and observed results in `TESTING.md` and the pull request description. Tests use temporary databases and do not reset, seed, or mutate `backend/data/app.db`.

## Approval gate

This phase is not complete until the developer reviews and explicitly approves it. Do not merge this branch into `main`.
