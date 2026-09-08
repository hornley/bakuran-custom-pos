# Bakuran POS Specification

**Status:** Current implementation specification  
**Project:** Bakuran POS System Draft#1  
**Repository:** `github.com/hornley/bakuran-custom-pos`  
**Stack:** React + Vite, FastAPI, SQLite
**Current slice:** Customer-facing table QR ordering is implemented alongside the authenticated front-desk POS. The local deployment remains single-store and cash-only.

## 1. Purpose

Bakuran POS is a counter-first restaurant point-of-sale system for taking customer orders, collecting cash, sending paid orders to the kitchen, calling customers for pickup, and issuing sales receipts.

The current delivery slice extends the counter workflow with validated delivery metadata, staffed driver assignment, and local dispatch tracking. Delivery orders remain cash-only and do not call an external courier service.

The primary operating model is:

```text
Choose order type
  -> Build basket
  -> Confirm customer
  -> Collect cash
  -> Kitchen
  -> Ready for pickup
  -> Close order and issue receipt
```

The system supports three connected front-desk entry paths:

1. **New order:** staff takes the customer's order manually.
2. **QR orders:** staff selects and pays an order already submitted by a customer's QR ordering flow.
3. **Delivery order:** staff takes a counter order, records its address and contact details, then dispatches it from the secondary delivery board.

There is no payment gateway. Payments are recorded by front-desk staff as cash transactions.

## 2. Product principles

- Keep the counter flow sequential and easy to scan.
- Show one dominant action at each step.
- Do not require a table number for manual counter orders.
- Never send an unpaid order to the kitchen.
- Let staff identify pickup orders by customer name and order number.
- Keep QR orders connected to the front desk without requiring scanning or manual order-number typing.
- Keep operational reference views secondary to order entry.
- Keep inventory and purchasing work in the secondary Operations workspace; it must not block POS ordering, payment, or kitchen release.
- Do not introduce inventory or purchasing work into the sequential POS order flow.
- Require delivery address and contact metadata before confirmation or payment.
- Keep delivery status changes transaction-safe and replay-safe when callbacks or staff retries repeat.

## 3. User roles

### Front-desk staff

Front-desk staff can:

- Start manual orders.
- Add menu items and quantities.
- Record customer calling names.
- Record cash payments.
- Select submitted QR orders from the payment queue.
- Send paid orders into kitchen fulfillment.
- Advance kitchen and pickup status.
- Close completed orders and issue receipts.
- Create delivery-channel counter orders and record a validated address, contact number, and optional contact name.
- Assign and reassign active delivery drivers from the secondary delivery board.
- Advance paid deliveries through dispatch, delivery, failure, or cancellation paths.

### Delivery driver

Drivers are represented as active/inactive operational records with a code, display name, and contact number. This slice does not provide driver login, a driver-facing application, GPS tracking, or external courier integration.

### Kitchen staff

Kitchen staff can use the kitchen queue to advance paid orders through preparation and readiness states.

### Customer

The customer-facing QR route is available at `/qr/<token>`. A customer can browse the active menu for the open table session, choose a basket, provide a bounded calling name, and submit one unpaid QR order. The order is connected to the authenticated front-desk payment queue; customers do not log in and do not pay online.

### Operations staff and local authentication

Inventory and purchasing are optional back-office capabilities. With local authentication disabled, the local deployment keeps the existing unauthenticated workflow. When local authentication is enabled, authenticated operators can perform normal operational mutations, viewers are read-only, and over-receipt overrides require a `manager` or `admin` role. Audit events record the authenticated actor when one exists.

## 4. Front-desk UI

### 4.1 Initial screen

The initial screen is intentionally compact. It shows:

- Bakuran POS identity.
- `Counter` heading.
- `New order` entry.
- `QR orders` entry.
- Secondary routes for kitchen, ready pickup, and operations.

It must not preload:

- A floor or table grid.
- The menu or basket.
- Historical receipts.
- Dashboard metrics.
- Kitchen history.
- Inventory or purchasing data. Those resources load only after `Operations` is selected.

Delivery is opened through a secondary `Delivery` route and is not preloaded on the compact first screen.

### 4.2 Manual order flow

```text
New order
  -> Basket
  -> Customer
  -> Payment
  -> Kitchen & pickup
```

#### Basket

- Products are displayed as clickable POS-style cards.
- Product cards use a responsive two-column grid on larger screens and one column on small screens.
- Clicking a card adds the selected quantity.
- The separate `Add` button is not used.
- Quantity input remains available on each card.
- Product name, description, price, category, and quantity controls use readable counter-facing typography.
- The basket remains visible beside the product grid.
- No table number field is shown.

#### Customer

- Staff enters a required calling name.
- The basket and total remain visible in a summary.
- `Back to basket` preserves selected items.
- `Continue to payment` moves forward only when a basket and name exist.

#### Payment

- Staff sees the customer name, basket, and amount due.
- Staff records a cash payment.
- The manual order number is not presented as a customer-facing handoff before payment.
- `Back to customer` preserves the name and leaves the order unpaid.

#### Kitchen and pickup

After payment:

- The system displays the generated order number.
- The order becomes eligible for kitchen preparation.
- Staff can start preparation, mark the order ready, call the customer, and complete pickup.
- The pickup view emphasizes both customer name and order number.
- `Back to kitchen` returns to the kitchen queue without reversing payment or kitchen state.

### 4.3 Order-type navigation

When a manual order is active, `Back to order type` is visible above the stepper.

- It returns to the `New order` and `QR orders` choices.
- It preserves the current manual draft, basket, and customer name.
- Choosing `New order` again resumes the draft.
- It does not cancel, void, refund, or delete server state.

### 4.4 QR order flow

```text
QR orders
  -> Select submitted unpaid order
  -> Review read-only order
  -> Record cash payment
  -> Kitchen & pickup
```

The QR payment queue:

- Lists submitted QR orders awaiting payment.
- Supports lookup by order number, customer name, or table context.
- Does not require scanning an order number.
- Does not require manually typing an order number to select an order.
- Shows the existing customer name, order number, total, and table context when present.
- Does not allow front-desk staff to edit or recreate the customer's basket.
- Preserves the original order number after payment.
- Uses `Back to QR orders` to return to the queue.

### 4.5 Delivery order flow

```text
Delivery order
  -> Build basket
  -> Save address/contact metadata
  -> Confirm customer
  -> Collect cash
  -> Pending dispatch
  -> Assign or reassign driver
  -> Out for delivery
  -> Delivered
```

Delivery metadata is stored against exactly one restaurant order and is never inferred from another order. Address and contact are required; contact name is optional but length-validated. Invalid metadata is rejected before a delivery record is created or changed.

The secondary delivery board shows pending, assigned, out-for-delivery, delivered, failed, and cancelled records. It shows each order's own address/contact, active driver, and assignment history. Staff may fail or cancel a paid delivery with a reason. A failed or cancelled delivery cannot be assigned or delivered afterward.

Callbacks may report `out_for_delivery`, `delivered`, `failed`, or `cancelled` with a required callback identifier. Repeated callback identifiers replay the original response; reusing one for a different payload is rejected.

## 5. Order lifecycle

The payment gate controls kitchen eligibility:

```text
open
  -> awaiting_payment
  -> paid
  -> preparing
  -> ready
  -> served
  -> closed
```

Rules:

- Manual orders enter `awaiting_payment` after customer confirmation.
- QR orders enter the payment queue in `awaiting_payment`.
- An unpaid order must not have a kitchen ticket.
- A paid order receives or activates a queued kitchen ticket.
- Kitchen transitions must follow the valid sequence.
- Closing an eligible completed order issues a sales receipt.

For delivery orders, payment is a hard boundary for dispatch as well:

```text
open
  -> awaiting_payment
  -> paid + delivery pending
  -> assigned
  -> out_for_delivery
  -> delivered | failed | cancelled
```

Delivery orders accept cash only. Assignment and all dispatch transitions require a paid order and its payment record. The delivery status is independent from the restaurant kitchen ticket so the existing payment gate and kitchen workflow remain intact.

## 6. Public API contracts

The backend uses FastAPI and SQLite. The current POS relies on these public interfaces:

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Service and database readiness |
| `GET /api/menu` | Active menu items for manual ordering |
| `POST /api/counter/orders` | Create a manual counter order |
| `POST /api/sessions/{session_id}/orders` | Create an order with channel metadata, including QR orders |
| `GET /api/orders/{order_id}` | Load order, lines, payment, kitchen ticket, and receipt state |
| `POST /api/orders/{order_id}/lines` | Add menu items to an order |
| `POST /api/orders/{order_id}/confirm` | Save customer name and move a manual order to payment pending |
| `POST /api/orders/{order_id}/pay` | Record staff cash payment and release the order to kitchen |
| `POST /api/kitchen/{ticket_id}/start` | Start preparation |
| `POST /api/kitchen/{ticket_id}/ready` | Mark an order ready |
| `POST /api/kitchen/{ticket_id}/serve` | Call or hand off the customer order |
| `POST /api/orders/{order_id}/close` | Complete pickup and issue a receipt |
| `GET /api/payment-queue` | List unpaid submitted orders for front-desk selection |
| `GET /api/kitchen` | List kitchen tickets |
| `GET /api/receipts` | List sales receipts with immutable tax snapshots |
| `GET /api/tables` | Secondary operations reference |
|| `GET /api/warehouses` | List active warehouse scopes |
|| `POST /api/warehouses` | Create an active warehouse scope |
|| `GET /api/inventory` | List warehouse-scoped stock and movements |
|| `GET /api/inventory/low-stock` | List stock at or below reorder level |
|| `GET /api/inventory/reorder` | Compatibility alias for low-stock visibility |
|| `PUT /api/inventory/reorder-level` | Set a product/warehouse reorder level |
|| `POST /api/stock/adjustment` | Apply a reasoned signed stock adjustment |
|| `GET /api/purchases` | List purchases with receipt progress per line |
|| `POST /api/purchases` | Create a draft purchase |
|| `POST /api/purchases/{purchase_id}/lines` | Add a validated product/warehouse line to a draft |
|| `POST /api/purchases/{purchase_id}/order` | Move a draft purchase to ordered |
|| `POST /api/purchases/{purchase_id}/receive` | Receive selected quantities, including partial receipts |
|| `POST /api/purchases/{purchase_id}/close` | Close a fully received purchase |
|| `GET /api/customer/tables/{token}` | Public session-scoped table context and active menu |
|| `GET /api/customer/tables/{token}/menu` | Public active menu for a table session |
|| `POST /api/customer/tables/{token}/orders` | Public QR order submission; requires `Idempotency-Key` |
|| `GET /api/customer/tables/{token}/orders/{order_id}` | Public QR order status scoped to the same token/session |
|| `POST /api/orders/{order_id}/delivery` | Validate and save delivery address/contact metadata |
|| `GET /api/delivery` | List delivery board records, optionally filtered by status |
|| `GET /api/delivery/drivers` | List active delivery drivers |
|| `GET /api/delivery/{delivery_id}` | Load one delivery with driver and assignment history |
|| `POST /api/delivery/{delivery_id}/assign` | Assign or reassign an active driver |
|| `POST /api/delivery/{delivery_id}/out-for-delivery` | Guarded dispatch transition |
|| `POST /api/delivery/{delivery_id}/delivered` | Guarded delivery completion transition |
|| `POST /api/delivery/{delivery_id}/failed` | Record a failed delivery with a reason |
|| `POST /api/delivery/{delivery_id}/cancel` | Record a cancelled delivery with a reason |
|| `POST /api/delivery/{delivery_id}/callback` | Apply an idempotent local callback event |
|| `GET /api/audit-events` | Review audit events for inventory, purchasing, delivery, and auth actions |
|| `GET /api/tax/configuration` | List tax rules and the rule effective today |
|| `POST /api/tax/configuration` | Add a validated, audited manager/admin tax rule |

The legacy `POST /api/purchases/{purchase_id}/receive` call without a body remains supported where safe: it records a draft as ordered, receives all outstanding lines, and returns the historical purchase-row response. The legacy `POST /api/stock/receipt` endpoint remains available and supports an optional idempotency key for safe retries.

### Order metadata

Orders support:

- `order_number`
- `customer_name`
- `order_channel`, including `counter`, `qr`, and `delivery`
- Optional `table_id` and table context
- Payment state
- Kitchen eligibility and ticket state
- For `order_channel=delivery`: delivery address, contact, optional contact name, dispatch status, driver, and assignment history

### Customer QR contract

- `POST /api/tables/{table_id}/open` issues a high-entropy bearer token once in the operator response for the new open table session. Only its SHA-256 hash and issuance time are stored in `table_sessions`; the raw token is not returned by table listings, customer responses, or order responses.
- Customer token endpoints accept only a token for an open session. Invalid, closed, and cross-session access returns `404` without revealing another table or order.
- Customer menu responses include only active menu items whose categories are active. Order creation revalidates every submitted item and reads its current server-side price inside the write transaction.
- Customer names are trimmed, required, limited to 80 characters, and reject control characters. A basket contains 1–50 unique menu items, each with a quantity from 1–20.
- `Idempotency-Key` is required, trimmed, limited to 128 visible characters, and scoped to the table session. A retry with the same key and equivalent payload returns the original order. Reuse with a different name or basket returns `409`.
- An open table session can have at most one active QR order. New submissions after the first QR order return `409`; retries remain safe and do not create another order.
- QR orders are created as `awaiting_payment`, with the server-selected tax snapshot and tax-inclusive total, without a payment or kitchen ticket. Only the existing staff-recorded cash payment flow releases a paid order to the kitchen. Legacy QR awaiting-payment rows without a snapshot are snapshotted transactionally before payment validation.
- The public customer API is bearer-token based and does not bypass authentication on operator routes. With shipped `AUTH_PROFILE=disabled`, operator mutations require `401` unless `AUTH_LOCAL_DEV_BYPASS=true` is explicitly set for a trusted local development instance. For protected operation, set `AUTH_PROFILE=local` and `AUTH_ENABLED=true`; operator sessions, roles, and CSRF checks then apply. CORS remains limited to configured frontend origins.

### Tax calculation and snapshots

- Tax rules contain a name, a decimal percentage rate from `0` through `100`, an
  `exclusive` or `inclusive` policy, and an ISO effective date range. Rates are
  stored as text and support at most four decimal places.
- The server selects the rule effective on the confirmation date for manual and delivery orders, and at QR order creation for customer-submitted QR orders. Effective
  ranges are inclusive; overlapping ranges are rejected, while adjacent date
  ranges are allowed.
- All tax and payment amounts use `Decimal`, with explicit half-up rounding to
  cents. Exclusive tax is calculated from the pre-tax subtotal; inclusive tax extracts the tax from the tax-inclusive total.
- Confirmation copies the selected rule and calculated taxable subtotal, tax,
  and total to the order. QR creation performs the same server-side snapshot before
  returning the awaiting-payment order. Payment must equal that tax-inclusive total
  to the cent, and payment still gates kitchen release. A legacy QR awaiting-payment
  row with no snapshot is snapshotted before payment amount validation.
- Closing copies the order tax snapshot into exactly one immutable receipt.
  Later rule changes cannot alter historical orders or receipts.
- Customer QR order creation and payment use the same transactional server-side tax
  snapshot contract as the front-desk flow; client-provided tax values are ignored.
- If no rule is effective, the existing zero-tax total is preserved. Records
  created before this migration remain zero-tax and are not retroactively recalculated.
- With the checked-in `auth_profile: disabled` deployment, local API access is intentionally unauthenticated so the existing local desk still opens directly. Setting `AUTH_PROFILE=local` and `AUTH_ENABLED=true` enables the existing local-session middleware; tax configuration then requires a manager or administrator and uses CSRF protection. This is local authentication, not hosted identity, SSO, MFA, or a compliance certification.

### Inventory and purchasing contract

- Every stock row is scoped by an active product and active warehouse. The database also enforces product/warehouse foreign keys and `on_hand >= reserved >= 0`.
- Inventory responses expose `on_hand`, `reserved`, `available`, `reorder_level`, `low_stock`, and `reorder_quantity`. Low stock is `available <= reorder_level`.
- A stock adjustment requires a non-zero signed quantity and a non-blank reason. It is atomic and cannot make on-hand stock negative or lower than reserved stock.
- Purchase status follows `draft -> ordered -> partially_received -> received -> closed`. Draft lines require active product and warehouse references and have positive quantity and non-negative unit cost.
- Each purchase line tracks `received_quantity`. A receipt validates every line before mutating any inventory, so a multi-line failure rolls back all lines.
- A receipt cannot exceed a line's ordered quantity unless `allow_over_receipt=true`, a non-blank `override_reason` is supplied, and local auth (when enabled) identifies a `manager` or `admin` actor.
- Explicit idempotency keys are persisted with a request fingerprint and response. Repeating the same operation replays the stored response; reusing a key with a different operation or payload returns a conflict.
- Inventory and purchasing mutations write audit events in the same transaction. Optional-auth requests record a null actor; authenticated requests record the local user id.
- The POS does not automatically reserve, deplete, or gate menu sales on inventory in this phase. The payment gate remains authoritative: unpaid orders cannot enter the kitchen.

## 7. Error and recovery behavior

- API failures remain on the current screen and show a dismissible error.
- Invalid or closed QR tokens show a safe unavailable state without echoing the token.
- Customer submission failures preserve the basket and name for retry.
- Failed item additions preserve the current order state.
- Failed confirmation preserves the basket and customer name.
- Failed payments leave the order unpaid and out of the kitchen.
- Back navigation is non-destructive.
- Invalid kitchen transitions return a conflict response.
- Invalid tax configuration returns validation/conflict responses without a
  partial write, and each successful configuration is recorded in `audit_events`.
- Premature kitchen release and invalid payment attempts must not mutate order state.
- Delivery metadata, assignment, transition, and callback validation failures do not mutate delivery state.
- Repeated idempotent delivery requests replay the original response; conflicting reuse of an idempotency key returns a conflict.
- Delivery mutations are logged as audit events without writing address or contact data into the event detail.
- Cancellation, voids, refunds, and destructive resets are outside the current POS scope.

## 8. Non-goals

The current POS does not include:

- Payment gateway integration.
- Order cancellation, voids, or refunds.
- Hosted identity and staff administration beyond the optional local-auth module.
- Automatic customer notifications.
- External courier, driver, GPS, route-optimization, webhook, or online-delivery integration.
- Delivery refunds, cash-on-delivery collection, or settlement workflows.
- Multi-store or multi-location synchronization; the QR route, delivery board, and payment queue use the single local SQLite store.
- Recipe-level stock depletion, automatic sale reservations, discounts, or purchase invoicing.

## 9. Acceptance criteria

### Manual order

1. Staff opens the app and sees the compact counter entry screen.
2. Staff chooses `New order`.
3. Products appear as larger clickable cards in a grid.
4. Clicking a product card adds the selected quantity without a separate Add button.
5. Staff can return to `Back to order type` and resume the draft.
6. Staff confirms a customer name.
7. Staff can move back to the basket or customer step without losing work.
8. Staff records cash payment.
9. The order number becomes visible after payment.
10. The paid order progresses through kitchen and pickup.
11. Staff closes the order and receives a sales receipt.

### QR order

1. Staff opens `QR orders`.
2. A submitted unpaid QR order appears in the connected queue.
3. Staff selects the order without scanning or typing its order number.
4. The order basket is read-only.
5. Staff records cash payment.
6. The existing order number is preserved.
7. The paid order enters the kitchen with its table context when available.

### Inventory and purchasing

1. Staff opens `Operations` as a secondary route; the compact counter entry screen does not load inventory or purchasing data.
2. Stock is filtered by an active warehouse and exposes low-stock rows using available quantity versus reorder level.
3. A signed stock adjustment requires a reason and preserves non-negative, non-reserved stock.
4. A purchase moves through draft, ordered, partially received, received, and closed states.
5. Each receipt updates only the selected purchase-line quantities and supports a later partial receipt.
6. Over-receipt is rejected unless the request includes a reason and, when auth is enabled, a manager/admin actor.
7. A failed multi-line receipt leaves every inventory row, purchase line, movement, and audit event unchanged.
8. Repeated idempotent requests replay once without double-mutating inventory; payload conflicts return a conflict.

### Customer QR submission

1. Staff opens a table and provides the issued QR URL to that table's QR code.
2. The customer opens `/qr/<token>` and sees only the active menu for that open table session.
3. The customer adds items, enters a calling name, and submits the basket.
4. The response shows an order number and `awaiting_payment`; it does not create a kitchen ticket.
5. A retry with the same idempotency key returns the same order, while a changed payload is rejected.
6. Staff selects the order from the unpaid QR queue and records cash before kitchen preparation begins.

### Delivery

1. Staff creates a `delivery` counter order and adds menu lines.
2. Missing or invalid address/contact metadata is rejected without creating or changing a delivery record.
3. Confirmation and payment are blocked until metadata exists; non-cash delivery payment is rejected.
4. A paid delivery appears as `pending` on the secondary delivery board.
5. Staff assigns and can reassign only active drivers; assignment history keeps the previous driver.
6. Invalid transitions preserve the exact delivery and assignment state.
7. Delivery callbacks and staff retries are idempotent and do not duplicate assignment or audit records.
8. The board supports delivered, failed, and cancelled terminal outcomes and displays the order's own metadata only.

### System validation

- Backend integration tests pass.
- Frontend TypeScript and production build pass.
- The health endpoint reports database readiness.
- Unpaid orders remain out of the kitchen.
- Invalid actions return a conflict and preserve state.
- Sales receipts are issued only through the close flow.
- Delivery status changes require payment, follow the guarded state graph, and emit audit events.
- No external courier service is called by this implementation.

## 10. Local development

Start the services from the project root:

```bash
./start.sh
```

Default endpoints:

- Frontend: `http://localhost:5200`
- Backend: `http://localhost:5300`
- Health: `http://localhost:5300/api/health`

Run validation:

```bash
cd backend && .venv/bin/python -m pytest -q
cd frontend && npm test && npm run build
```

The application can be hosted on `0.0.0.0` for access from another device using the host machine's LAN or tailnet address.

Inventory and purchasing are intentionally single-store in this phase. Warehouse IDs scope stock within the store, but there is no multi-location synchronization, transfer workflow, or cross-store reporting.
