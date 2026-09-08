# Testing

Run the current checks from the repository root:

```bash
./test.sh
```

`test.sh` runs backend pytest, the frontend Vitest suite, and the frontend production build. No virtual-environment activation or directory change is required.

The focused checks can be run directly:

```bash
(cd backend && .venv/bin/python -m pytest -q tests/test_auth_boundary.py tests/test_qr_ordering.py)
(cd frontend && npm test)
(cd frontend && npm run build)
```

The backend pytest fixtures create temporary SQLite databases for each test. The shared fixture sets `AUTH_LOCAL_DEV_BYPASS=true` to model an explicitly trusted local development instance; boundary tests unset it to verify the shipped default denial and separately cover local session/role/CSRF behavior. Never point tests at `backend/data/app.db`, and never run reset or mutation smoke tests against the main database.

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

The suite uses mocked API responses and covers ready-queue selection, successful payment progression, recoverable order-line errors, the public QR route, token non-leakage, menu rendering, basket/name submission, idempotency headers, confirmation UI, safe closed-token errors, and recoverable customer API errors. It does not replace a live browser/E2E check.

## Customer QR ordering checks

The QR backend tests cover session-scoped hashed tokens, invalid and closed tokens, cross-session isolation, active-menu filtering, bounded names and baskets, server-side price revalidation, one active QR order per session, transaction rollback, concurrent idempotent retries, payload conflicts, CORS preflight, and operator-auth boundaries.

The auth boundary tests also verify that `/api/health` and `/api/auth/*` remain public in the shipped disabled profile, that explicit `AUTH_LOCAL_DEV_BYPASS=true` preserves the legacy open desk, and that `AUTH_PROFILE=local` with `AUTH_ENABLED=true` preserves login, role, and CSRF enforcement.

The frontend tests cover the public route parser, token non-leakage, menu rendering, basket/name submission, idempotency headers, confirmation UI, safe closed-token errors, and recoverable API errors. The browser flow should be checked against an isolated temporary database; do not open a table or submit an order against `backend/data/app.db`.

## Current phase handoff

- Backend tests: run `./test.sh` for the current count
- Payment-gate regression: served-order payment rejection returns HTTP 409 and preserves order/payment/ticket state
- Frontend tests and build: run `./test.sh`
- Database: isolated temporary test databases
- Feature status: awaiting developer approval
