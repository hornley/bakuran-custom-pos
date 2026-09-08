# Bakuran POS Specification

**Status:** Current implementation specification  
**Project:** Bakuran POS System Draft#1  
**Repository:** `github.com/hornley/bakuran-custom-pos`  
**Stack:** React + Vite, FastAPI, SQLite
**Current slice:** Customer-facing table QR ordering is implemented alongside the authenticated front-desk POS. The local deployment remains single-store and cash-only.

## 1. Purpose

Bakuran POS is a counter-first restaurant point-of-sale system for taking customer orders, collecting cash, sending paid orders to the kitchen, calling customers for pickup, and issuing sales receipts.

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

The system supports two connected front-desk entry paths:

1. **New order:** staff takes the customer's order manually.
2. **QR orders:** staff selects and pays an order already submitted by a customer's QR ordering flow.

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

### Kitchen staff

Kitchen staff can use the kitchen queue to advance paid orders through preparation and readiness states.

### Customer

The customer-facing QR route is available at `/qr/<token>`. A customer can browse the active menu for the open table session, choose a basket, provide a bounded calling name, and submit one unpaid QR order. The order is connected to the authenticated front-desk payment queue; customers do not log in and do not pay online.

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
| `GET /api/customer/tables/{token}` | Public session-scoped table context and active menu |
| `GET /api/customer/tables/{token}/menu` | Public active menu for a table session |
| `POST /api/customer/tables/{token}/orders` | Public QR order submission; requires `Idempotency-Key` |
| `GET /api/customer/tables/{token}/orders/{order_id}` | Public QR order status scoped to the same token/session |

### Order metadata

Orders support:

- `order_number`
- `customer_name`
- `order_channel`, including `counter` and `qr`
- Optional `table_id` and table context
- Payment state
- Kitchen eligibility and ticket state

### Customer QR contract

- `POST /api/tables/{table_id}/open` issues a high-entropy bearer token once in the operator response for the new open table session. Only its SHA-256 hash and issuance time are stored in `table_sessions`; the raw token is not returned by table listings, customer responses, or order responses.
- Customer token endpoints accept only a token for an open session. Invalid, closed, and cross-session access returns `404` without revealing another table or order.
- Customer menu responses include only active menu items whose categories are active. Order creation revalidates every submitted item and reads its current server-side price inside the write transaction.
- Customer names are trimmed, required, limited to 80 characters, and reject control characters. A basket contains 1–50 unique menu items, each with a quantity from 1–20.
- `Idempotency-Key` is required, trimmed, limited to 128 visible characters, and scoped to the table session. A retry with the same key and equivalent payload returns the original order. Reuse with a different name or basket returns `409`.
- An open table session can have at most one active QR order. New submissions after the first QR order return `409`; retries remain safe and do not create another order.
- QR orders are created as `awaiting_payment`, without a payment or kitchen ticket. Only the existing staff-recorded cash payment flow releases a paid order to the kitchen.
- The public customer API is bearer-token based and does not bypass authentication on operator routes. CORS remains limited to configured frontend origins.

## 7. Error and recovery behavior

- API failures remain on the current screen and show a dismissible error.
- Invalid or closed QR tokens show a safe unavailable state without echoing the token.
- Customer submission failures preserve the basket and name for retry.
- Failed item additions preserve the current order state.
- Failed confirmation preserves the basket and customer name.
- Failed payments leave the order unpaid and out of the kitchen.
- Back navigation is non-destructive.
- Invalid kitchen transitions return a conflict response.
- Premature kitchen release and invalid payment attempts must not mutate order state.
- Cancellation, voids, refunds, and destructive resets are outside the current POS scope.

## 8. Non-goals

The current POS does not include:

- Payment gateway integration.
- Inventory management or stock mutation.
- Purchasing or supplier workflows.
- Order cancellation, voids, or refunds.
- Staff accounts, permissions, or attendance management.
- Automatic customer notifications.
- Delivery or table-service settlement workflows.
- Multi-store or multi-location synchronization; the QR route and payment queue use the single local SQLite store.

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

### Customer QR submission

1. Staff opens a table and provides the issued QR URL to that table's QR code.
2. The customer opens `/qr/<token>` and sees only the active menu for that open table session.
3. The customer adds items, enters a calling name, and submits the basket.
4. The response shows an order number and `awaiting_payment`; it does not create a kitchen ticket.
5. A retry with the same idempotency key returns the same order, while a changed payload is rejected.
6. Staff selects the order from the unpaid QR queue and records cash before kitchen preparation begins.

### System validation

- Backend integration tests pass.
- Frontend TypeScript and production build pass.
- The health endpoint reports database readiness.
- Unpaid orders remain out of the kitchen.
- Invalid actions return a conflict and preserve state.
- Sales receipts are issued only through the close flow.

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
