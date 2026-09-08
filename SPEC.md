# Bakuran POS Specification

**Status:** Current implementation specification  
**Project:** Bakuran POS System Draft#1  
**Repository:** `github.com/hornley/bakuran-custom-pos`  
**Stack:** React + Vite, FastAPI, SQLite

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
- Do not introduce inventory or purchasing work into the POS flow.
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

The future customer-facing QR route will allow a customer to select menu items from their table, provide a calling name, and submit an unpaid order. That customer-facing route is not part of the current frontend implementation. The current POS supports the connected front-desk payment queue required after submission.

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
- Inventory or purchasing data.

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
| `GET /api/receipts` | List sales receipts |
| `GET /api/tables` | Secondary operations reference |
| `POST /api/orders/{order_id}/delivery` | Validate and save delivery address/contact metadata |
| `GET /api/delivery` | List delivery board records, optionally filtered by status |
| `GET /api/delivery/drivers` | List active delivery drivers |
| `GET /api/delivery/{delivery_id}` | Load one delivery with driver and assignment history |
| `POST /api/delivery/{delivery_id}/assign` | Assign or reassign an active driver |
| `POST /api/delivery/{delivery_id}/out-for-delivery` | Guarded dispatch transition |
| `POST /api/delivery/{delivery_id}/delivered` | Guarded delivery completion transition |
| `POST /api/delivery/{delivery_id}/failed` | Record a failed delivery with a reason |
| `POST /api/delivery/{delivery_id}/cancel` | Record a cancelled delivery with a reason |
| `POST /api/delivery/{delivery_id}/callback` | Apply an idempotent local callback event |
| `GET /api/audit-events` | Review audit events for delivery and auth actions |

### Order metadata

Orders support:

- `order_number`
- `customer_name`
- `order_channel`, including `counter`, `qr`, and `delivery`
- Optional `table_id` and table context
- Payment state
- Kitchen eligibility and ticket state
- For `order_channel=delivery`: delivery address, contact, optional contact name, dispatch status, driver, and assignment history

## 7. Error and recovery behavior

- API failures remain on the current screen and show a dismissible error.
- Failed item additions preserve the current order state.
- Failed confirmation preserves the basket and customer name.
- Failed payments leave the order unpaid and out of the kitchen.
- Back navigation is non-destructive.
- Invalid kitchen transitions return a conflict response.
- Premature kitchen release and invalid payment attempts must not mutate order state.
- Delivery metadata, assignment, transition, and callback validation failures do not mutate delivery state.
- Repeated idempotent delivery requests replay the original response; conflicting reuse of an idempotency key returns a conflict.
- Delivery mutations are logged as audit events without writing address or contact data into the event detail.
- Cancellation, voids, refunds, and destructive resets are outside the current POS scope.

## 8. Non-goals

The current POS does not include:

- Payment gateway integration.
- Inventory management or stock mutation.
- Purchasing or supplier workflows.
- A customer-facing QR ordering page.
- Order cancellation, voids, or refunds.
- Staff accounts, permissions, or attendance management beyond the existing optional local-auth boundary.
- Automatic customer notifications.
- External courier, driver, GPS, route-optimization, webhook, or online-delivery integration.
- Delivery refunds, cash-on-delivery collection, or settlement workflows.

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
cd frontend && npm run build
```

The application can be hosted on `0.0.0.0` for access from another device using the host machine's LAN or tailnet address.
