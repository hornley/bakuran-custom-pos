# Testing

Run the current checks from the repository root:

```bash
./test.sh
```

`test.sh` runs backend pytest, the frontend Vitest suite, and the frontend production build. No virtual-environment activation or directory change is required.

The focused checks can be run directly:

```bash
(cd backend && .venv/bin/python -m pytest -q tests/test_auth_boundary.py tests/test_qr_ordering.py tests/test_delivery.py)
(cd frontend && npm test)
(cd frontend && npm run build)
```

The backend pytest fixtures create temporary SQLite databases for each test. The shared fixture sets `AUTH_LOCAL_DEV_BYPASS=true` to model an explicitly trusted local development instance; boundary tests unset it to verify the shipped default denial and separately cover local session/role/CSRF behavior. Never point tests at `backend/data/app.db`, and never run reset or mutation smoke tests against the main database.

The frontend also has a focused Vitest check for the secondary delivery board:

```bash
cd frontend && npm test
```

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

The suite uses mocked API responses and covers ready-queue selection, successful payment progression, recoverable order-line errors, Operations loading boundaries, selected partial/over-receipt payloads, the public QR route, token non-leakage, menu rendering, basket/name submission, idempotency headers, confirmation UI, safe closed-token errors, recoverable customer API errors, delivery-board rendering, delivery metadata reset, and delivery mutation headers. It does not replace a live browser/E2E check.

## Customer QR ordering checks

The QR backend tests cover session-scoped hashed tokens, invalid and closed tokens, cross-session isolation, active-menu filtering, bounded names and baskets, server-side price revalidation, one active QR order per session, transaction rollback, concurrent idempotent retries, payload conflicts, CORS preflight, and operator-auth boundaries.

## Inventory and purchasing checks

The focused inventory backend tests cover warehouse/product validation, low-stock and reorder levels, reasoned signed adjustments, partial and over-receipts, per-line completion, multi-line rollback, durable idempotency and concurrent retries, optional-auth role denial/authorization, database constraints, and audit records. The frontend tests confirm that Operations remains secondary, inventory/purchasing/audit endpoints are wired, and responsive safety-critical controls remain present.

## Delivery checks

The focused delivery suite covers delivery-channel creation, address/contact/contact-name validation, metadata isolation, payment and cash-only gates, invalid transition rollback, active-driver assignment and reassignment history, duplicate callbacks and idempotency-key conflicts, failed/cancelled outcomes, optional-auth viewer denial with audit evidence, and delivery audit records. The board is a local operational view; this phase intentionally has no external courier, webhook, driver app, GPS, or route-optimization integration.

## Current validation baseline

- Run `./test.sh` for the current integrated backend count, frontend tests, and production build.
- Run `git diff --check`.
- Backend tests use isolated temporary SQLite databases; never point tests at `backend/data/app.db`.
- No live browser/E2E or external courier integration is exercised by these tests; frontend tests use mocked fetch responses.
