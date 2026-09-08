# Testing

Run the current checks from the repository root:

```bash
./test.sh
```

`test.sh` runs backend pytest with `backend/.venv/bin/python` when it exists, then runs the frontend Vitest suite and production build. No virtual-environment activation or directory change is required.

The backend pytest fixture creates a temporary SQLite database for each test. Never point tests at `backend/data/app.db`, and never run reset or mutation smoke tests against the main database. Tax and authentication tests also use isolated temporary databases.

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

The suite uses mocked API responses and covers ready-queue selection, successful payment progression, recoverable order-line errors, server-provided tax breakdown rendering, and secondary tax configuration submission. It does not replace a live browser/E2E check.

## Current validation baseline

- Backend tests: `45 passed` including tax rounding/configuration, snapshots, auth, reset compatibility, Phase 3 lifecycle regressions, and bounded-magnitude no-mutation regressions
- Payment-gate regression: served-order payment rejection returns HTTP 409 and preserves order/payment/ticket state
- Ready/pickup regression: ready and served tickets remain visible until order close
- Frontend tests: `5 passed` in 1 Vitest file
- Frontend build: passed with TypeScript and Vite
- Database: isolated temporary test databases
- Phase status: Phase 6 implementation complete; developer approval is required before merge

The backend regression suite also checks duplicate and concurrent payment/release idempotency, full lifecycle receipt/close behavior, invalid kitchen transition conflicts without mutation, tax effective-date selection, invalid/overlapping rules, Decimal half-up boundaries, historical tax snapshots, receipt lifecycle, local-auth permissions, and isolated reset/migration safety.

## Tax-focused checks

```bash
cd backend
.venv/bin/python -m pytest -q tests/test_tax_math.py tests/test_tax_configuration.py tests/test_tax_auth.py
```

The focused tax command currently reports `28 passed`. It also verifies that
`1e1000` payment amounts and `10**100` line quantities return HTTP 422 without
changing order, payment, kitchen-ticket, or order-line state. Monetary values
are bounded to `9999999999.99`; each order-line quantity is bounded to
`999999999` before Decimal totals are calculated.

The default fixture uses the checked-in unauthenticated local deployment contract.
The auth test explicitly opts into `AUTH_PROFILE=local`/`AUTH_ENABLED=true` with
temporary bootstrap credentials and verifies manager/admin configuration access
and operator denial. No credentials or operational database are used by the test.
