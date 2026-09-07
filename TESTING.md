# Testing

Run the current checks from the repository root:

```bash
./test.sh
```

`test.sh` runs backend pytest with `backend/.venv/bin/python` when it exists, then runs the frontend production build. No virtual-environment activation or directory change is required.

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
- Frontend build: `npm run build`
- Database: isolated temporary test databases
- Phase status: Phase 3 implementation in progress; developer approval is required before merge

The backend regression suite also checks duplicate and concurrent payment/release idempotency, full lifecycle receipt/close behavior, and invalid kitchen transition conflicts without mutation.
