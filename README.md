# Bakuran POS System Draft#1

Local restaurant POS for counter pickup, guided cash payment, kitchen flow, and optional table operations. QR table ordering is represented in the order contract for a future customer-facing route.

This is the generated Bakuran POS project. The commands below are project-local and intentionally use only these fixed ports:

- Frontend: `0.0.0.0:5200`
- Backend API: `0.0.0.0:5300`
- Tailscale URLs: `http://100.108.61.26:5200` and `http://100.108.61.26:5300`

## Run the project

From the repository root:

```bash
./start.sh
```

Open the application at:

```text
http://100.108.61.26:5200
```

The API health check is:

```text
http://100.108.61.26:5300/api/health
```

`start.sh` creates `backend/.venv` and installs `backend/requirements.txt` on the first run. It installs frontend dependencies if `frontend/node_modules` is missing. It starts both services with `0.0.0.0` binding and refuses to silently use a different port.

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
- Table service: view floor/table status and guarded open/close transitions. Table orders can carry `customer_name` and `order_channel=qr` for the future QR route.
- Kitchen queue: move tickets through `queued -> preparing -> ready -> served`.
- Attendance: review employee attendance status.
- Settings, search, and notifications: load settings, search resources, and review attention notifications.

Purchasing and inventory APIs remain available as deferred back-office capabilities, but they are not loaded or used by the focused POS desk.

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
```

Important POS mutations include counter order creation, order lines, order confirmation, cash payment, kitchen transitions, order close, and sales receipt issuance. Inventory and purchasing endpoints remain available as deferred back-office APIs, but the POS frontend does not load or use them. The frontend uses `/api/receipts` for sales receipts.

## Authentication

The current manifest uses `auth_profile: disabled`, so the desk opens directly. The generated backend retains the local authentication and CSRF modules for an opt-in local-auth variant. This project is not a hosted identity service and does not include SSO, MFA, password recovery, or external identity providers.

## Troubleshooting

Check whether the fixed ports are occupied:

```bash
ss -ltnp | grep -E ':5200|:5300'
```

If another application owns either port, stop that application before running `./start.sh`. Do not change the Bakuran ports in this project. If the page loads but cannot reach the API, confirm that the browser is using `http://100.108.61.26:5200` and that `frontend/.env.local` contains the Tailscale API URL.

## Boundaries

This is a local SQLite operational slice. It does not include multi-location synchronization, reservations, delivery, online ordering, external payment gateways, refunds, tax calculation, promotions, recipe-level stock depletion, printer or fiscal-device integrations, payroll, biometric attendance, loyalty, email, webhooks, background workers, hosted deployment, or third-party identity providers.
