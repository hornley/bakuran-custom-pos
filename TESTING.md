# Testing

Run the current checks from the repository root:

```bash
./test.sh
```

`test.sh` runs backend pytest with `backend/.venv/bin/python` when it exists, then runs the frontend Vitest suite and production build. No virtual-environment activation or directory change is required.

For the phase-4 vertical slice, run the focused backend suite and frontend tests directly:

```bash
cd backend && .venv/bin/python -m pytest -q tests/test_inventory_purchasing.py
cd frontend && npm test
cd frontend && npm run build
git diff --check
```

The focused backend tests cover warehouse/product validation, low-stock and reorder levels, reasoned signed adjustments, partial and over-receipts, per-line completion, multi-line rollback, durable idempotency and concurrent retries, optional-auth role denial/authorization, database constraints, and audit records. The frontend tests confirm that Operations remains secondary, inventory/purchasing/audit endpoints are wired, and the responsive safety-critical controls remain present.

The backend pytest fixture creates a temporary SQLite database for each test. Never point tests at `backend/data/app.db`, and never run reset or mutation smoke tests against the main database.

For a read-only service check when the app is already running:

```bash
curl -fsS http://localhost:5300/api/health
```

Expected result includes `"status":"ok"` and `"database_ready":true`.

## Phase 2 ready / pickup queue

The active kitchen queue is the default:

```bash
curl -fsS http://localhost:5300/api/kitchen
```

The ready / pickup queue includes ready and served tickets until their orders are closed:

```bash
curl -fsS 'http://localhost:5300/api/kitchen?queue=ready'
```

Supported values for `queue` are `active` and `ready`; other values return HTTP 422.

## Frontend tests

Run the focused Vitest suite from the frontend directory:

```bash
cd frontend
npm test
```

The suite uses mocked API responses and covers ready-queue selection, successful payment progression, recoverable order-line errors, Operations loading boundaries, and selected partial/over-receipt payloads. It does not replace a live browser/E2E check.

## Current validation baseline

- Focused inventory/purchasing backend: `24 passed` with 2 existing dependency deprecation warnings (`cd backend && .venv/bin/python -m pytest -q tests/test_inventory_purchasing.py`).
- Full backend suite: `41 passed` with 3 existing warnings (`cd backend && .venv/bin/python -m pytest -q`).
- Frontend Vitest suite: `5 passed` (`cd frontend && npm test`).
- Frontend production build and TypeScript check: passed (`cd frontend && npm run build`).
- Root `./test.sh`: passed; it reruns the full backend suite, frontend tests, and build.
- `git diff --check`: passed.
- Payment-gate regression: served-order payment rejection returns HTTP 409 and preserves order/payment/ticket state
- Ready/pickup regression: ready and served tickets remain visible until order close
- Frontend tests include the Phase 3 POS flow checks and Phase 4 Operations boundary/safety controls.
- Database: isolated temporary test databases; no test mutation targets `backend/data/app.db`.
- No live browser/E2E check was run; frontend tests use mocked fetch responses.
- Phase status: Phase 4 implemented; explicit developer approval is required before merge.

The backend regression suite also checks duplicate and concurrent payment/release idempotency, full lifecycle receipt/close behavior, and invalid kitchen transition conflicts without mutation.

Inventory and purchasing are single-store in this phase. Warehouse IDs scope records within the store; multi-location synchronization, transfers, and cross-store reporting are not implemented.
