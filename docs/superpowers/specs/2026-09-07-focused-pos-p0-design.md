# Focused POS P0 Design

Date: 2026-09-07
Status: Approved by user
Scope: Make the local restaurant POS usable for the basic table-service workflow while deferring inventory management.

## 1. Goal

Deliver a working POS path:

```text
Open table
  -> Create order
  -> Add menu items
  -> Send to kitchen
  -> Start / ready / serve
  -> Accept payment
  -> Close order
  -> Issue and display sales receipt
```

The POS must not depend on inventory availability or stock movements in this slice.

## 2. Scope

### Included

- Repair startup/runtime checks so the current project launches the current backend, frontend, and database.
- Initialize and validate the SQLite schema during backend startup.
- Connect the frontend to the existing create-order endpoint.
- Connect the frontend to the existing close-order endpoint.
- Add a dedicated sales receipt listing endpoint.
- Make menu/order entry independent of inventory.
- Add or update automated tests for the complete POS lifecycle.
- Use real UTC timestamps for new business records.

### Explicitly deferred

- Inventory availability checks during order entry.
- Inventory decrement on payment.
- Stock movements and reservations.
- Purchasing and receiving UI.
- Warehouse logic and reorder levels.
- Tax, discounts, refunds, split payments, register shifts, and external payment gateways.

Existing inventory tables and endpoints remain in the codebase but are not used by the POS interface.

## 3. Backend design

### 3.1 Menu and order entry

`GET /api/menu` will return active menu items and category information without joining inventory or calculating an `available` value.

`POST /api/orders/{oid}/lines` will validate:

- The order exists and is open.
- The menu item exists and is active.
- The quantity is positive.

It will not query inventory or reject a line based on stock.

The existing line snapshot behavior remains: item name, unit price, quantity, and line total are stored on the order line.

### 3.2 Order listing contract

`GET /api/orders` will include `table_id` in every row, in addition to the existing order and table information. This gives the frontend a stable way to associate an order with a selected table.

### 3.3 Sales receipts

Add:

```text
GET /api/receipts
```

The endpoint will return sales receipts joined to their originating order and table:

```json
{
  "id": 1,
  "receipt_number": "REC-0001",
  "order_id": 1,
  "order_number": "ORD-0001",
  "table_code": "T01",
  "total": 23,
  "issued_at": "2026-09-07T09:30:00Z"
}
```

Receipt creation remains part of `POST /api/orders/{oid}/close`, preserving the existing order-to-receipt transaction.

### 3.4 Timestamps

Replace the fixed `NOW` value in the business API with a UTC timestamp helper that generates an ISO-8601 timestamp for each mutation.

### 3.5 Database readiness

Backend startup will continue to initialize migrations and seed data, but readiness will be observable:

- `/api/health` will verify that the expected schema is available.
- A missing or unusable database schema will produce a failed startup/readiness state instead of a false healthy response.

## 4. Frontend design

### 4.1 Initial data load

The POS desk will load only the data needed for the focused experience:

- Dashboard
- Tables
- Menu
- Kitchen queue
- Orders
- Sales receipts
- Attendance
- Settings
- Notifications
- Search

Inventory and purchasing requests will be removed from the initial load.

### 4.2 Navigation

Remove the `Purchasing & stock` tab from the POS interface. Keep:

- Register desk
- Kitchen queue
- Attendance
- Settings and search

### 4.3 Register flow

When an available table is opened:

1. POST `/api/tables/{tid}/open`.
2. Read the returned session ID.
3. POST `/api/sessions/{sid}/orders`.
4. Reload the desk data.
5. Select the new active order.

Menu Add buttons become enabled only when the selected table has an open order.

### 4.4 Order actions

The current order panel will expose actions based on order status:

- `open`: Send to kitchen.
- `served`: Pay exact order total using the current cash payment path.
- `paid`: Close order and issue receipt.

After close, the desk reloads tables, orders, and sales receipts. The table becomes available again and the new receipt appears in the receipt panel.

### 4.5 Receipt panel

Change the frontend receipt request from `/api/stock/receipts` to `/api/receipts`. The panel will render `receipt_number`, `order_number`, `table_code`, and `total` from the sales receipt contract.

## 5. Runtime and launcher design

- Replace hard-coded documentation paths with paths derived from the project root.
- Strengthen virtual-environment validation. A present executable is not sufficient if required imports cannot run.
- Ensure the launcher uses the current backend and frontend paths for the tracked process.
- Make readiness check both backend health/database readiness and frontend root availability.
- Prefer a database-aware readiness request such as `/api/dashboard` so missing schema errors cannot be reported as a healthy service.
- Keep ports unchanged at frontend `5200` and backend `5300`.

## 6. Error handling

- Preserve the existing recoverable frontend error behavior.
- Opening a table and creating its order are one user action, but failures are reported clearly. If table opening succeeds and order creation fails, reload the desk and show the error without silently retrying.
- Backend state transitions remain guarded and transactional.
- Closing an already closed order remains idempotent.
- No inventory errors should block POS order entry or payment in this scope.

## 7. Testing strategy

### Backend tests

Add or update tests for:

- Complete HTTP lifecycle through receipt creation and `/api/receipts` listing.
- `/api/orders` includes `table_id`.
- Menu/order line creation succeeds without inventory availability checks.
- Receipt fields include the originating order and table.
- New records receive current UTC timestamps.
- Database readiness fails clearly when the expected schema is unavailable.

Existing workflow transition and rollback tests remain valid, except the old inventory-limit assertion must be replaced with a test proving inventory is not consulted by POS.

### Frontend checks

- TypeScript/Vite production build passes.
- Static route contract check confirms frontend calls create order, close order, and `/api/receipts`.
- The frontend initial request list contains no inventory or purchasing endpoints.

### Acceptance scenario

Using a clean local database and running services:

1. Open the desk.
2. Select an available table.
3. Open the table.
4. Add a menu item.
5. Send the order to the kitchen.
6. Advance the ticket through preparation and serving.
7. Pay the exact total.
8. Close the order.
9. Confirm the table is available.
10. Confirm the sales receipt appears in the receipt panel.
11. Confirm no inventory endpoint or stock movement is required for success.

## 8. Non-goals

This change does not introduce:

- Inventory accounting.
- Register sessions or cash reconciliation.
- Refunds or voids.
- Customer selection.
- Discounts or tax calculation.
- Multi-location behavior.
- Receipt printing.
- Authentication policy changes.

## 9. Completion criteria

The design is complete when:

- The current project launcher starts the current project and refuses false readiness.
- The frontend can execute the full table-service POS flow without manual API calls.
- Sales receipts are available through a dedicated endpoint and visible in the UI.
- Inventory is not loaded, consulted, or required by the POS flow.
- Backend tests and frontend build pass.
- The acceptance scenario passes using the public HTTP interfaces.
