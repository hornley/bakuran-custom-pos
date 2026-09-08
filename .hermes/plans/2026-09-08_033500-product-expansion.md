# Bakuran POS Product Expansion Plan

> **For Hermes:** Use isolated worktrees and independent exact-SHA review for each feature track. Do not merge any PR without explicit developer approval.

**Goal:** Deliver the requested QR, back-office, financial, delivery, and device-integration capabilities as narrow, production-ready vertical slices while preserving the existing POS lifecycle and payment gate.

**Architecture:** Keep the FastAPI/SQLite backend and React/Vite frontend. Extend the database only with numbered migrations, use transactions and audit events for mutations, and snapshot historical monetary values on orders/receipts. Public customer QR ordering is separated from authenticated operator workflows; device integrations use a durable local job/provider boundary rather than pretending to settle external payments.

**Tech Stack:** FastAPI, Pydantic, SQLite migrations, React, TypeScript, Vite, pytest/TestClient, Vitest/jsdom.

---

## Source-of-truth findings

- `AGENTS.md` requires phase documents before implementation, isolated test databases, focused commits, independent review, and no merge before developer approval.
- `SPEC.md` currently describes the operational POS slice and explicitly defers customer-facing QR, inventory/purchasing workflow, tax, discounts, refunds, delivery, and printing. It must be updated per landed track without rewriting historical design records.
- `backend/app/main.py` currently holds the API, `backend/app/db.py` applies numbered SQL migrations, `backend/app/auth.py` provides optional local auth/roles/audit events, and `frontend/src/App.tsx` is the authenticated front-desk UI.
- `origin/main` is the latest appropriate base currently verified as `da40b9e`. The Phase 3 branch/worktrees are separate and must not be modified or duplicated.

## Dependency and parallelization plan

Create independent worktrees/branches from the exact latest appropriate base. Start QR, inventory/purchasing, and delivery from `origin/main`; do not run those writers concurrently if they need overlapping `main.py`, `db.py`, `SPEC.md`, or frontend files. The safe default is one active implementation at a time, with independent reviewer worktrees only after each exact pushed head exists.

Financial tracks are sequential:

1. Tax/configuration
2. Promotions/discounts (based on the reviewed tax branch)
3. Refunds/voids/cancellations (based on the reviewed promotions branch)
4. Printer/fiscal integrations (based on the reviewed refunds branch)

QR, inventory, and delivery can be developed before or alongside tax only if ownership is proven disjoint; otherwise serialize to avoid conflicts. Update `TASKS.md` only through the coordinator, not from feature worktrees.

## Track acceptance criteria

### Track 1: Customer-facing QR ordering

- Public table token resolves only the intended active table/session context; invalid, expired, closed, or cross-context tokens fail without disclosure.
- Customer can browse active menu, build a basket, provide a bounded calling name, and submit exactly one `awaiting_payment` QR order with an order number.
- Server revalidates menu items/prices and uses a transaction; duplicate submission/retry is idempotent via a client idempotency key.
- No customer authentication or payment gateway is introduced; operator auth remains required for front-desk mutations.
- Frontend has a mobile-responsive QR route and confirmation; front desk sees the submitted order in the existing payment queue.
- Tests cover token isolation, inactive items, empty/invalid baskets, duplicate submissions, closed sessions, and API/UI behavior.

### Track 2: Inventory and purchasing improvements

- Inventory is scoped to a warehouse and supports guarded stock movements, non-negative stock, adjustments with reason, low-stock/reorder visibility, and atomic sale/receipt behavior where the existing order lifecycle is affected.
- Purchase orders transition through draft/ordered/partially received/received/closed; receipts cannot exceed ordered quantities without an explicit authorized override.
- Mutations validate referenced products/warehouses/suppliers, are transactional/idempotent, permission protected, and audit logged.
- UI exposes inventory/purchasing operations without loading them into the compact first screen; tests cover concurrency/rollback and permission denial.

### Track 3: Tax calculation and configuration

- Admin/manager can configure active tax rates and inclusive/exclusive policy with validation and effective dates.
- Decimal arithmetic and explicit half-up rounding are used; order and receipt rows snapshot taxable subtotal, tax rate, tax amount, and total.
- Existing orders retain historical totals; retries do not create duplicate tax records; operator UI displays the breakdown.
- Tests cover rounding boundaries, configuration authorization, inactive/effective rates, and lifecycle compatibility.

### Track 4: Promotions and discounts

- Admin/manager can define bounded fixed/percentage promotions, validity windows, usage limits, and explicit non-stacking/stacking policy.
- Code application revalidates server-side, snapshots the applied rule/value on the order, never makes totals negative, and respects operator discount limits.
- Audit log records application/removal and actor; tests cover invalid codes, expiry, usage race, stacking, rounding, and retry behavior.

### Track 5: Refunds, voids, and cancellations

- Cancellations are guarded by lifecycle state; fulfillment cannot continue after cancellation.
- Voids are permission protected and distinguish pre-payment cancellation from post-payment reversal; refunds reference the original payment, never exceed refundable amount, and are idempotent by request key.
- Inventory restoration is atomic when a completed sale had a stock effect; no external payment gateway is claimed.
- UI shows reason, amount, original transaction, and irreversible confirmation; audit events capture actor/reason/state transitions.

### Track 6: Delivery workflows

- Orders may carry validated delivery address/contact and explicit delivery channel; no delivery order is dispatched without required data.
- Status transitions are guarded and idempotent (`pending -> assigned -> out_for_delivery -> delivered`, with failure/cancel paths documented); driver assignment validates active staff/driver identity.
- UI supports dispatch board, assignment, status updates, failure recovery, and customer/order lookup without exposing unrelated tenants/contexts.
- Tests cover transition conflicts, reassignment, duplicate callbacks/requests, authorization, and address validation.

### Track 7: Printer and fiscal-device integrations

- Provider interface is explicit and local; no real device or fiscal compliance is claimed without a configured adapter.
- Print/fiscal jobs are durable, linked to immutable receipt/refund snapshots, idempotent, retried with bounded backoff, and expose failed/manual retry state.
- Fiscal configuration is permission protected and secrets are not stored in source/logs; audit records cover enqueue, retry, success, and failure.
- UI shows job state and safe retry; tests use a deterministic fake provider and cover crashes/retries/duplicate enqueue.

## Delivery protocol for every track

1. Re-read `AGENTS.md`, `SPEC.md`, relevant docs, current tasks, and exact base.
2. Create a dedicated worktree and branch; record it in `TASKS.md`.
3. Write a failing test for one end-to-end behavior, run it RED, implement the minimum, run GREEN, then expand edge cases.
4. Add migration/API/UI/docs changes only for the track; preserve existing tests and payment gate.
5. Run focused tests, full `./test.sh`, type/build/lint checks available in the repository, `git diff --check`, and a safe runtime check where possible. Never mutate `backend/data/app.db`.
6. Commit focused changes, push the branch, open one GitHub PR, and record exact SHA/link in `TASKS.md`.
7. Create a detached read-only reviewer worktree at the exact pushed SHA. Reviewer inspects implementation, docs, migrations, permissions, security, tenant isolation, transactions, idempotency, rounding, and edge cases, runs checks, and posts a formal GitHub review/comment.
8. Fix valid findings in the feature worktree, rerun checks, and re-review every changed exact head. Do not merge; hand off with blockers and approval gate.

## Documentation updates

For each landed track, update `SPEC.md` public workflow/API/schema/non-goal sections and the relevant `docs/phases/phase-N.md` or new feature record. Keep prior approved design documents historical; add an implementation note when a former non-goal becomes active. Update `README.md` and `TESTING.md` only when commands or user-visible workflows change.

## Final validation and handoff

Report per track: worktree/branch, PR URL and exact head SHA, changed files, tests/build/runtime checks and actual results, reviewer verdict/comment and any fixes, documentation updates, known limitations, dependency blockers, and the explicit developer-approval/no-merge status. The final recommended unresolved limitation is that real fiscal-device certification and external delivery/payment providers require deployment-specific adapters and credentials.
