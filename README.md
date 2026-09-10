# Bakuran POS System Draft#1

Local restaurant POS for counter pickup, guided cash payment, customer-facing table QR ordering, kitchen flow, local delivery dispatch, optional table operations, and a secondary warehouse-scoped inventory/purchasing workspace. QR orders are submitted publicly from an open table session and then paid in cash by front-desk staff; delivery orders are dispatched locally by active drivers.

This is the generated Bakuran POS project. The commands below are project-local and intentionally use only these fixed ports:

- Frontend: `0.0.0.0:5200`
- Backend API: `0.0.0.0:5300`
- Tailscale URLs: `http://100.108.61.26:5200` and `http://100.108.61.26:5300`

## Project documentation

- [`SPEC.md`](SPEC.md): current POS scope, workflows, API contracts, and acceptance criteria.
- [`AGENTS.md`](AGENTS.md): database safety, phase lifecycle, branching, commits, and approval rules.

- [`DESIGN.md`](DESIGN.md): the premium warm POS design system, interaction contract, and accessibility rules.

- [`TESTING.md`](TESTING.md): short verification instructions for the current changes.
- [`docs/phases/phase-1.md`](docs/phases/phase-1.md): current phase handoff and approval checklist.
- [`docs/phases/phase-5.md`](docs/phases/phase-5.md): delivery workflow handoff and approval checklist.
- [`docs/phases/phase-2.md`](docs/phases/phase-2.md): payment gate and ready/pickup queue phase record.
- [`docs/phases/phase-3.md`](docs/phases/phase-3.md): operational hardening phase record and approval gate.
- [`docs/phases/phase-4-inventory-purchasing.md`](docs/phases/phase-4-inventory-purchasing.md): inventory/purchasing vertical slice, checks, and approval gate.
- [`docs/phases/phase-6-tax-configuration.md`](docs/phases/phase-6-tax-configuration.md): tax rules, rounding, snapshots, and validation.
- [`docs/features/customer-qr-ordering.md`](docs/features/customer-qr-ordering.md): current customer QR vertical slice, contract, checks, and limitations.

## Run the project

From the repository root:

```bash
./start.sh
```

Open the application at:

```text
http://100.108.61.26:5200
```

### Preview with mock data

To inspect the populated operator and customer surfaces without changing the SQLite database, open:

```text
http://100.108.61.26:5200/?mock=1
http://100.108.61.26:5200/qr/demo-token?mock=1
```

Mock mode is read-only from the backend's perspective and is enabled only by the `mock=1` query parameter or `VITE_MOCK_DATA=true`. It shows realistic menu items, kitchen tickets, QR payment orders, delivery assignments, inventory, purchasing, receipts, and a customer QR flow.

The API health check is:

```text
http://100.108.61.26:5300/api/health
```

`start.sh` creates `backend/.venv` and installs `backend/requirements.txt` on the first run. It installs frontend dependencies if `frontend/node_modules` is missing. It starts both services with `0.0.0.0` binding and refuses to silently use a different port.

The operator UI supports iPad portrait and landscape use. Open the frontend URL in Safari, or add it to the Home Screen for an app-like surface. The layout switches from the desktop rail to touch-friendly navigation at tablet widths and accounts for iPad safe-area insets.

Stop or restart only this project with:

```bash
./stop.sh
./restart.sh
```

Logs are written to `logs/backend.log` and `logs/frontend.log`. The launcher stores its own process IDs in `logs/backend.pid` and `logs/frontend.pid` and will not stop a process whose working directory is outside this project.

## Current network configuration

`frontend/.env.local` points the browser to:

```text
VITE_API_URL=http://100.108.61.26:5300
```

The backend allows the Tailscale frontend origin for CORS. These settings apply only to this generated project folder. They do not change the builder or any other generated project.

## Supported workflows

- Counter pickup: build an order, confirm the customer's name, issue an order number, record cash payment, move the paid order to kitchen, call the customer, and issue a receipt.
- Payment gate: orders remain in `awaiting_payment` and out of the kitchen queue until cash payment is recorded.
- Table service: view floor/table status and guarded open/close transitions. Table sessions issue QR tokens for the customer ordering route.
- Customer QR ordering: open-table tokens scope a public menu and one awaiting-payment QR order to the current table session.
- Kitchen queue: move tickets through `queued -> preparing -> ready -> served`.
- Delivery: create cash-only delivery orders, validate address/contact metadata, assign active drivers, and track dispatch through delivered, failed, or cancelled outcomes from the secondary delivery board.
- Attendance: review employee attendance status.
- Tax: configure effective inclusive/exclusive rules from the secondary Operations view and review tax breakdowns on orders.
- Promotions: managers/admins define bounded fixed or percentage codes; operators can apply, replace, or remove one promotion before payment on counter and delivery orders. Discounts are audited, idempotent, and reflected in the server-authoritative tax-inclusive total.
- Settings, search, and notifications: load settings, search resources, and review attention notifications.
- Operations: review warehouse-scoped inventory, low-stock/reorder levels, purchase lifecycle progress, receipts, and audit events.

Inventory and purchasing load only after the secondary `Operations` route is selected. They never gate POS menu entry, payment, or the unpaid-order kitchen gate.

The UI includes loading, empty, recoverable error, successful mutation, and mutation-busy states. Successful mutations reload the desk data while recoverable errors preserve the last valid view.

## Reset or seed local data

Stop the project first, then run the deterministic seed/reset command:

```bash
./stop.sh
backend/.venv/bin/python -m app.seed --reset
./start.sh
```

The SQLite database is stored at `backend/data/app.db`. Back it up before resetting. The reset replaces operational data with the deterministic sample data.

## API surface used by the frontend

Read endpoints include:

```text
GET /api/health
GET /api/menu
GET /api/kitchen
GET /api/orders
GET /api/receipts
GET /api/payment-queue
GET /api/tables
GET /api/attendance
GET /api/settings
GET /api/notifications
GET /api/search
GET /api/warehouses
GET /api/inventory
GET /api/inventory/low-stock
GET /api/inventory/reorder
PUT /api/inventory/reorder-level
POST /api/stock/adjustment
POST /api/stock/receipt
GET /api/purchases
POST /api/purchases
POST /api/purchases/{purchase_id}/lines
POST /api/purchases/{purchase_id}/order
POST /api/purchases/{purchase_id}/receive
POST /api/purchases/{purchase_id}/close
GET /api/customer/tables/{token}
GET /api/customer/tables/{token}/menu
POST /api/customer/tables/{token}/orders
GET /api/customer/tables/{token}/orders/{order_id}
GET /api/delivery
GET /api/delivery/drivers
POST /api/orders/{order_id}/delivery
POST /api/delivery/{delivery_id}/assign
POST /api/delivery/{delivery_id}/callback
GET /api/audit-events
GET /api/promotions
POST /api/promotions
POST /api/orders/{order_id}/promotions
DELETE /api/orders/{order_id}/promotions/{applied_id}
```

Important POS mutations include counter order creation, order lines, order confirmation, cash payment, kitchen transitions, order close, and sales receipt issuance. The Operations route uses explicit warehouse filters, reasoned signed adjustments, per-line purchase receipts, and durable idempotency keys for supported mutations. The frontend uses `/api/receipts` for sales receipts. The legacy no-body purchase receive endpoint remains available for older clients and records an implicit ordered transition before completion; legacy stock receipts accept an optional idempotency key.

## Promotions and discounts

Promotion codes support bounded fixed-amount and percentage discounts on counter and delivery
orders before payment. One promotion may be replaced or removed before payment. Manager/admin
definition, operator application, audit, idempotency, usage limits, and tax recalculation are
server-authoritative; public QR orders and viewers remain read-only.

## Tax configuration

The desk is zero-tax compatible when no rule is active. Tax rules are created from the secondary Operations view or `POST /api/tax/configuration`; the server validates decimal rates (`0`–`100`), inclusive/exclusive policy, and non-overlapping inclusive effective date ranges. Confirmation snapshots the effective rule and calculates tax with `Decimal` half-up cent rounding. Payment must equal the tax-inclusive total, and receipts retain the same immutable snapshot.

- Customer QR submission uses `POST /api/customer/tables/{token}/orders` with a bounded `Idempotency-Key`. It returns an `awaiting_payment` order with the server-selected tax snapshot and tax-inclusive total; only the authenticated front desk can record cash and release that order to kitchen. Payment defensively snapshots legacy QR awaiting-payment rows that lack a snapshot before validating the amount, so pre-fix rows cannot bypass configured tax.

Delivery mutations are payment-gated, use transaction-safe guarded transitions, preserve assignment history, and accept only cash. `Idempotency-Key` is supported for assignment and staff transition retries; callback identifiers make repeated local callback deliveries safe. Delivery audit events are available from `/api/audit-events`.

## Authentication

The current manifest uses `auth_profile: disabled`, but operator mutations are denied by default. Set `AUTH_LOCAL_DEV_BYPASS=true` only for a trusted local development instance that intentionally uses the legacy open desk. For protected operator access, set `AUTH_PROFILE=local` and `AUTH_ENABLED=true`, then configure `AUTH_BOOTSTRAP_USERNAME` and `AUTH_BOOTSTRAP_PASSWORD` on first startup. In local auth mode, operator reads and mutations require a session, mutations also require the CSRF token, and role checks remain active. `GET /api/health` and `/api/auth/login`, `/api/auth/logout`, and `/api/auth/session` remain public; customer bearer tokens do not grant operator access. This project is not a hosted identity service and does not include SSO, MFA, password recovery, or external identity providers.

Customer QR endpoints are intentionally public bearer-token routes. They do not grant access to operator endpoints, and the customer frontend omits operator cookies. QR tokens are session-scoped and stored only as hashes.

When local auth is enabled, authenticated operators can use normal operations mutations, viewers remain read-only, and over-receipt overrides require a manager or admin role. Audit events include the local actor when available. With auth disabled, the local deployment preserves its existing optional-auth behavior.

## Troubleshooting

Check whether the fixed ports are occupied:

```bash
ss -ltnp | grep -E ':5200|:5300'
```

If another application owns either port, stop that application before running `./start.sh`. Do not change the Bakuran ports in this project. If the page loads but cannot reach the API, confirm that the browser is using `http://100.108.61.26:5200` and that `frontend/.env.local` contains the Tailscale API URL.

## Boundaries

This is a local single-store SQLite operational slice. It does not include multi-location synchronization or transfers, reservations, external payment gateways, online card payment, refunds, recipe-level stock depletion, printer or fiscal-device integrations, payroll, biometric attendance, loyalty, email, external courier/driver integration, GPS tracking, route optimization, webhooks, background workers, hosted deployment, or third-party identity providers. Tax is limited to configured single-store rules and immutable snapshots; inventory and purchasing are available as deferred back-office capabilities; neither area is fiscal-device, accounting, or inventory-compliance software.
