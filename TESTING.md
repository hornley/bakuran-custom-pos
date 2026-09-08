# Testing

Run the current checks from the repository root:

```bash
./test.sh
```

`test.sh` runs backend pytest with `backend/.venv/bin/python` when it exists, then runs the frontend Vitest suite and production build. No virtual-environment activation or directory change is required.

The frontend also has a focused Vitest check for the secondary delivery board:

```bash
cd frontend && npm test
```

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

The suite uses mocked API responses and covers ready-queue selection, successful payment progression, and recoverable order-line errors. It does not replace a live browser/E2E check.

## Current validation baseline

- Backend tests: `17 passed` including Phase 3 lifecycle regressions
- Payment-gate regression: served-order payment rejection returns HTTP 409 and preserves order/payment/ticket state
- Ready/pickup regression: ready and served tickets remain visible until order close
- Frontend tests: `3 passed` in 1 Vitest file
- Frontend build: passed with TypeScript and Vite
- Database: isolated temporary test databases
- Phase 3 baseline status: implementation complete; developer approval is required before merge

## Phase 5 delivery workflow

The focused delivery suite uses only the temporary SQLite database supplied by pytest:

```bash
backend/.venv/bin/python -m pytest -q backend/tests/test_delivery.py
./test.sh
cd frontend && npm test && npm run build
git diff --check
```

The suite covers delivery-channel creation, address/contact/contact-name validation, metadata isolation, payment and cash-only gates, invalid transition rollback, active-driver assignment and reassignment history, duplicate callbacks and idempotency-key conflicts, failed/cancelled outcomes, optional-auth viewer denial with audit evidence, and delivery audit records. The board is a local operational view; this phase intentionally has no external courier, webhook, driver app, GPS, or route-optimization integration.

Phase 5 validation observed on 2026-09-08:

- Focused delivery pytest: `8 passed`.
- Full `./test.sh`: `25 passed` backend, `4 passed` frontend tests in 2 files, and production build passed.
- `git diff --check`: passed.
- Known output is limited to the existing Starlette/httpx, anyio, and `app.seed` deprecation/runtime warnings.
- No live browser/E2E or external courier integration was exercised; the board contract is covered by Vitest and the application bundle by the production build.

The backend regression suite also checks duplicate and concurrent payment/release idempotency, full lifecycle receipt/close behavior, and invalid kitchen transition conflicts without mutation.
