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

The suite uses mocked API responses and covers ready-queue selection, successful payment progression, recoverable order-line errors, server-provided tax breakdown rendering, secondary tax configuration submission, delivery header preservation, delivery draft reset behavior, and the delivery board. It does not replace a live browser/E2E check.

## Customer QR ordering checks

The QR backend tests cover session-scoped hashed tokens, invalid and closed tokens, cross-session isolation, active-menu filtering, bounded names and baskets, server-side price revalidation, one active QR order per session, transaction rollback, concurrent idempotent retries, payload conflicts, CORS preflight, and operator-auth boundaries.

The auth boundary tests verify that `/api/health` and `/api/auth/*` remain public in the shipped disabled profile, that explicit `AUTH_LOCAL_DEV_BYPASS=true` preserves the legacy open desk, and that `AUTH_PROFILE=local` with `AUTH_ENABLED=true` preserves login, role, and CSRF enforcement.

The frontend tests cover the public route parser, token non-leakage, menu rendering, basket/name submission, idempotency headers, confirmation UI, safe closed-token errors, recoverable API errors, tax rendering/configuration, delivery request headers, and delivery draft reset behavior. The browser flow should be checked against an isolated temporary database; do not open a table or submit an order against `backend/data/app.db`.

## Phase 5 delivery workflow

The focused delivery suite uses only the temporary SQLite database supplied by pytest:

```bash
backend/.venv/bin/python -m pytest -q backend/tests/test_delivery.py
./test.sh
cd frontend && npm test && npm run build
git diff --check
```

The suite covers delivery-channel creation, address/contact/contact-name validation, metadata isolation, payment and cash-only gates, invalid transition rollback, active-driver assignment and reassignment history, duplicate callbacks and idempotency-key conflicts, failed/cancelled outcomes, optional-auth viewer denial with audit evidence, and delivery audit records. The board is a local operational view; this phase intentionally has no external courier, webhook, driver app, GPS, or route-optimization integration.

## Current validation baseline

- Backend tests: run `./test.sh` for the current count
- Focused tax pytest: run the tax-focused command below
- Focused QR/delivery pytest: run the focused command above
- Payment-gate regression: served-order payment rejection returns HTTP 409 and preserves order/payment/ticket state
- Ready/pickup regression: ready and served tickets remain visible until order close
- Frontend tests and build: run `./test.sh`
- Database: isolated temporary test databases
- Phase status: Phase 6 implementation complete; developer approval is required before merge

The backend regression suite also checks duplicate and concurrent payment/release idempotency, full lifecycle receipt/close behavior, invalid kitchen transition conflicts without mutation, tax effective-date selection, invalid/overlapping rules, Decimal half-up boundaries, historical tax snapshots, receipt lifecycle, local-auth permissions, QR token/idempotency boundaries, delivery transitions, and isolated reset/migration safety.

## Tax-focused checks

```bash
cd backend
.venv/bin/python -m pytest -q tests/test_tax_math.py tests/test_tax_configuration.py tests/test_tax_auth.py
```

The focused tax command verifies Decimal rounding, configuration authorization, snapshots, and no-mutation rejection for oversized payment and order-line values. Monetary values are bounded to `9999999999.99`; each order-line quantity is bounded to `999999999` before Decimal totals are calculated.

The default fixture uses the checked-in unauthenticated local deployment contract. The auth test explicitly opts into `AUTH_PROFILE=local`/`AUTH_ENABLED=true` with temporary bootstrap credentials and verifies manager/admin configuration access and operator denial. No credentials or operational database are used by the test.
