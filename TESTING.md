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

The backend pytest fixture creates a temporary SQLite database for each test. Never point tests at `backend/data/app.db`, and never run reset or mutation smoke tests against the main database. Tax, authentication, and inventory tests also use isolated temporary databases.

For the phase-4 vertical slice, run the focused backend suite and frontend tests directly:

```bash
cd backend && .venv/bin/python -m pytest -q tests/test_inventory_purchasing.py
cd frontend && npm test
cd frontend && npm run build
git diff --check
```

The focused backend tests cover warehouse/product validation, low-stock and reorder levels, reasoned signed adjustments, partial and over-receipts, per-line completion, multi-line rollback, durable idempotency and concurrent retries, optional-auth role denial/authorization, database constraints, and audit records. The frontend tests confirm that Operations remains secondary, inventory/purchasing/audit endpoints are wired, and the responsive safety-critical controls remain present.

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

The suite uses mocked API responses and covers ready-queue selection, successful payment progression, recoverable order-line errors, Operations loading boundaries, server-provided tax breakdown rendering, secondary tax configuration submission, selected partial/over-receipt payloads, the public QR route, token non-leakage, menu rendering, basket/name submission, idempotency headers, confirmation UI, safe closed-token errors, recoverable customer API errors, delivery-board rendering, delivery metadata reset, and delivery mutation headers. It does not replace a live browser/E2E check.

## Customer QR ordering checks

The QR backend tests cover session-scoped hashed tokens, invalid and closed tokens, cross-session isolation, active-menu filtering, bounded names and baskets, server-side price revalidation, one active QR order per session, transaction rollback, concurrent idempotent retries, payload conflicts, CORS preflight, operator-auth boundaries, tax snapshots at QR creation, and defensive tax snapshots for legacy awaiting-payment QR rows.

The auth boundary tests verify that `/api/health` and `/api/auth/*` remain public in the shipped disabled profile, that explicit `AUTH_LOCAL_DEV_BYPASS=true` preserves the legacy open desk, and that `AUTH_PROFILE=local` with `AUTH_ENABLED=true` preserves login, role, and CSRF enforcement.

The frontend tests cover the public route parser, token non-leakage, menu rendering, basket/name submission, idempotency headers, confirmation UI, safe closed-token errors, recoverable API errors, tax rendering/configuration, Operations loading boundaries, selected partial/over-receipt payloads, delivery request headers, and delivery draft reset behavior. The browser flow should be checked against an isolated temporary database; do not open a table or submit an order against `backend/data/app.db`.

## Phase 5 delivery workflow

The focused delivery suite uses only the temporary SQLite database supplied by pytest:

```bash
backend/.venv/bin/python -m pytest -q backend/tests/test_delivery.py
./test.sh
cd frontend && npm test && npm run build
git diff --check
```

The suite covers delivery-channel creation, address/contact/contact-name validation, metadata isolation, payment and cash-only gates, invalid transition rollback, active-driver assignment and reassignment history, duplicate callbacks and idempotency-key conflicts, failed/cancelled outcomes, optional-auth viewer denial with audit evidence, and delivery audit records. The board is a local operational view; this phase intentionally has no external courier, webhook, driver app, GPS, or route-optimization integration.

## Inventory and purchasing checks

The focused inventory backend tests cover warehouse/product validation, low-stock and reorder levels, reasoned signed adjustments, partial and over-receipts, per-line completion, multi-line rollback, durable idempotency and concurrent retries, optional-auth role denial/authorization, database constraints, and audit records. The frontend tests confirm that Operations remains secondary, inventory/purchasing/audit endpoints are wired, and the responsive safety-critical controls remain present.

## Current validation baseline

- Run `./test.sh` for the current integrated backend count, frontend tests, and production build.
- Run `git diff --check`.
- Backend tests use isolated temporary SQLite databases; never point tests at `backend/data/app.db`.
- No live browser/E2E or external courier integration is exercised by these tests; frontend tests use mocked fetch responses.

## Tax-focused checks

```bash
cd backend
.venv/bin/python -m pytest -q tests/test_tax_math.py tests/test_tax_configuration.py tests/test_tax_auth.py
```

The focused tax command verifies Decimal rounding, configuration authorization, manual and QR snapshots, defensive legacy QR payment snapshotting, and no-mutation rejection for oversized payment and order-line values. Monetary values are bounded to `9999999999.99`; each order-line quantity is bounded to `999999999` before Decimal totals are calculated.

The default fixture uses the checked-in unauthenticated local deployment contract. The auth test explicitly opts into `AUTH_PROFILE=local`/`AUTH_ENABLED=true` with temporary bootstrap credentials and verifies manager/admin configuration access and operator denial. No credentials or operational database are used by the test.

## Promotions and discounts

Run the focused promotion suite and complete gates:

```bash
backend/.venv/bin/python -m pytest -q backend/tests/test_promotions.py
./test.sh
cd frontend && npm test && npm run build
git diff --check
```

Promotion tests use isolated temporary SQLite databases and cover normalization, fixed/percentage
rounding and bounds, manager/operator/viewer authorization, validity and usage limits, replacement
and removal, concurrent transactional application, idempotency conflicts, lifecycle/payment gates,
discounted-subtotal tax snapshots, receipts, delivery compatibility, and public QR isolation.
Frontend tests cover apply/retry/remove controls, server-returned pricing, permission and error
states, mock lifecycle parity, usage tracking, and unknown mutation failures. These are mocked or
TestClient checks; they do not replace served-host browser validation at 1440, 1280, 1024, 768,
and 390 pixel widths. Never use `backend/data/app.db` for promotion checks.
