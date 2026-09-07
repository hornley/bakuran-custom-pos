# Bakuran Guided Ordering Flow UI Redesign

Date: 2026-09-07
Status: Approved for future implementation
Scope: Future redesign of the Bakuran ordering experience. This document records the approved flow only. No application UI is changed by this design pass.

## 1. Purpose

Replace the current table-first operations dashboard as the primary ordering experience with a focused, sequential order flow for counter staff and future QR table ordering.

The front desk has two explicit entry paths:

### Manual order

```text
Start a manual order
  -> Build the basket
  -> Confirm customer details
  -> Record payment
  -> Reveal the system-generated order number
  -> Send paid order to kitchen
  -> Call customer by name or order number
```

### QR order payment

```text
Open submitted QR orders
  -> Choose the matching customer order
  -> Review it read-only
  -> Record payment
  -> Preserve the existing order number
  -> Send paid order to kitchen
  -> Call customer by name or order number
```

The design should make the next action obvious and keep unrelated operational data out of the first screen.

## 2. Approved product model

Bakuran will support two order-entry channels that share one fulfillment lifecycle:

### 2.1 Counter order

A staff member takes the customer's order at the front desk.

1. Staff starts a new manual order.
2. Staff adds menu items.
3. Staff confirms the basket and customer name.
4. Staff records cash payment.
5. The system reveals the generated order number.
6. The paid order enters the kitchen queue.
7. Staff calls the customer by name or displays the order number when ready.

### 2.2 QR table order

A customer scans a QR code attached to a table.

1. The QR code opens the customer ordering route.
2. The table is attached automatically from the QR token. A manual table-number fallback may be provided.
3. The customer selects menu items.
4. The customer confirms the order and provides a calling name.
5. The system creates the order and displays an order number.
6. The customer presents the number or name at the front desk. Staff chooses the matching unpaid order from the connected list.
7. Staff records payment.
8. The paid order enters the kitchen queue.
9. Staff calls the customer by name or order number when ready.

The customer-facing QR route is a future channel. The current front-desk UI must still provide the connected unpaid-order list so QR orders can be selected without scanning or manually typing an order number.

## 3. Core rule: payment gates preparation

An order can receive an order number before payment, but it must not enter the kitchen queue until payment is recorded.

This avoids preparing unpaid orders and gives front-desk staff an explicit payment queue.

```text
Draft
  -> Awaiting payment
  -> Paid
  -> Preparing
  -> Ready
  -> Completed
```

The current backend uses the existing order lifecycle and cash-payment path. The future implementation must either map `awaiting_payment` onto the existing state model or add an explicit state if the current API cannot represent this distinction safely. It must not silently treat an unpaid order as kitchen-ready.

## 4. Primary UI architecture

### 4.1 Default landing state

The default staff route should open to a blank `Choose a flow` screen rather than a dashboard containing floor tables, historical receipts, metrics, and all menu data.

The first screen contains only:

- Bakuran identity.
- A `Take a new order` entry for manual customer ordering.
- A `Pay an existing QR order` entry for submitted customer orders.
- A compact route to secondary operations such as kitchen, ready orders, tables, and reports.

The menu and basket are loaded only after the staff chooses the manual path. The unpaid QR order list is loaded only after the staff chooses the QR path.

No historical receipts, table occupancy grid, dashboard metrics, or kitchen records should be rendered in the primary order workspace before the user asks for them.

### 4.2 Sequential stepper

The selected layout is a guided stepper with one dominant task per step:

Manual orders use:

1. `Build order`
2. `Confirm details`
3. `Payment`
4. `Kitchen and pickup`

QR orders use a connected payment review followed by the same kitchen and pickup states.

The stepper should preserve enough context to avoid disorientation, including the order number, basket total, and current status. It should not expose every operation as an equal-weight panel.

### 4.3 Secondary operations

Secondary operational views remain available, but they should be behind explicit navigation rather than competing with order entry:

- Awaiting payment queue.
- Kitchen queue.
- Ready for pickup.
- Tables and QR management.
- Sales receipts.
- Staff and settings.

A staff member may leave an order and resume it from the relevant queue. The default action remains starting a new order.

## 5. Detailed screen behavior

### Step 1: Build order

Purpose: quickly add items while the customer is ordering.

Required elements:

- Menu categories.
- Menu item name, short description, price, and add control.
- Quantity adjustment after adding.
- Basket with item lines, quantities, and running total.
- `Review order` primary action.
- Empty-basket guidance before the action becomes available.

Counter context should be selected by default for staff orders. A QR order may supply a table context automatically.

### Step 2: Confirm details

Purpose: verify what will be created before assigning a number.

Required elements:

- Basket summary.
- Total due.
- Calling name field.
- Order channel indicator: `Counter pickup` or `Table QR`.
- Optional table context. QR orders should show the resolved table as read-only or clearly identified as QR-provided.
- `Create order and get number` primary action.
- Back action to return to the menu without losing the basket.

Calling name is required for the initial implementation because it is the primary human pickup mechanism. The order number remains the fallback identifier.

### Step 3A: Manual payment

Purpose: collect payment before revealing the pickup number.

Required elements:

- Customer name.
- Basket summary.
- Total due.
- `Record cash payment` primary action.
- Clear copy that the order number appears after payment.

The manual payment screen must not display the order number as a customer-facing handoff before payment.

### Step 3B: QR order payment

Purpose: select and pay an order already submitted by the customer.

Required elements:

- Large order number.
- Customer name.
- Total due.
- Order channel and table context when present.
- Existing order number and customer name.
- Read-only basket and total.
- Optional QR table context.
- Staff action: `Record cash payment`.
- Status label: `Awaiting payment`.

The screen must not allow front-desk staff to re-create or edit the QR basket in this pass. It must not state or imply that the kitchen has started preparation.

The payment queue should support lookup by:

- Order number.
- Customer name.
- Table number when the order came from QR.

### Step 4: Kitchen and pickup

Purpose: communicate the post-payment fulfillment state.

After cash payment is recorded:

- The order becomes eligible for the kitchen queue.
- The interface shows `Paid` and `Sent to kitchen` feedback.
- Kitchen staff can advance the order through preparing, ready, and served states using the existing operational transitions.
- The pickup view emphasizes both the calling name and order number.
- A ready order can be marked completed after handoff.

## 6. Data and API implications

The redesign should reuse the existing menu, order, payment, kitchen, and receipt contracts where possible.

The future implementation must provide these stable concepts:

- `order_number` generated when the order is created.
- `customer_name` stored with the order or an associated customer-facing order record.
- `source` or `order_channel` with at least `counter` and `qr` values.
- Optional `table_id` or table token for QR orders.
- Payment status that distinguishes unpaid from paid.
- Kitchen eligibility that requires paid status.
- Receipt creation after the existing close flow.

If the current schema does not contain customer name or channel fields, add a focused migration rather than encoding this information in free-form notes.

No payment gateway is included. The initial payment method remains staff-recorded cash payment.

No inventory check or inventory mutation should be introduced as part of this redesign.

## 7. Error and recovery behavior

- If the API is unavailable while starting an order, keep the user on the current step and show a recoverable error.
- If order creation fails, preserve the basket so the staff member does not have to rebuild it.
- If payment recording fails, keep the order in `Awaiting payment` and do not send it to kitchen.
- If a QR table token is invalid, allow the customer to enter a table number or continue as a counter pickup order only if staff explicitly permits it.
- If an order number lookup returns multiple matches, require an exact confirmation using name, total, or table context.
- If the browser is refreshed on the payment or pickup screen, recover the order by its order number and reload the current server status.
- Avoid destructive actions in the primary flow. Cancellation, voids, and refunds remain separate future work.

## 8. Visual and interaction direction

The existing dark operational visual language can remain as the base, but the hierarchy must become calmer and more focused:

- One dominant action per step.
- Minimal navigation on the ordering route.
- High contrast for order number, total, payment state, and pickup state.
- No large dashboard metric strip on the first screen.
- No default receipt history on the first screen.
- No default table grid on the first screen.
- Responsive layout suitable for a front-desk monitor and future customer phone use.
- Clear empty, loading, error, and success states.

The approved visual direction is the `Guided order flow` shown in the brainstorming companion. The companion mockup is a design reference, not production code.

## 9. Acceptance scenarios

### Counter order

1. Open the application and see the two front-desk choices.
2. Choose `Take a new order`.
3. Add menu items and see the basket update.
4. Continue to confirmation and enter a calling name.
5. Record cash payment without showing the order number beforehand.
6. Confirm the system then reveals an order number and the order becomes eligible for kitchen.
7. Advance the order to ready.
8. Confirm the pickup view shows both customer name and order number.
9. Close the order and confirm a sales receipt is issued.

### QR table order

1. A customer submits a QR order containing a valid table identity.
2. Confirm the order appears in the front-desk QR payment list without scanning or manual order-number typing.
3. Choose the matching order from the list.
4. Confirm the basket and total are read-only.
5. Record cash payment and preserve the existing order number.
6. Confirm the order enters the kitchen queue with its table context.
7. Mark the order ready and confirm the customer can be called by name or number.

### Minimal first screen

The default front-desk route must not render:

- A preloaded floor table grid.
- The menu and basket before a manual order is chosen.
- QR payment orders before the QR path is chosen.
- Historical sales receipts.
- Dashboard metrics.
- Kitchen history.
- Inventory or purchasing data.

Those views may exist as secondary operational routes.

## 10. Non-goals for this redesign

- Online payment or payment gateway integration.
- Customer accounts or login.
- Automatic customer notifications by SMS or push.
- Inventory availability or stock deduction.
- Tax, discounts, refunds, split payments, and loyalty.
- Full table-service ordering with waiter assignment.
- Receipt printing hardware integration.
- Rebuilding the UI in this pass.

## 11. Future implementation sequence

When UI rebuilding begins, implement in this order:

1. Add or confirm the order fields needed for customer name, source, table context, and payment state.
2. Add backend transitions and lookup endpoints for awaiting-payment orders.
3. Replace the current default desk view with the guided `Build order` step.
4. Implement confirmation and order-number handoff.
5. Implement the payment queue and cash payment action.
6. Connect paid orders to the existing kitchen lifecycle.
7. Add ready and pickup views.
8. Move tables, receipts, metrics, staff, and settings to secondary routes.
9. Add QR table tokens and the customer-facing order route.
10. Validate the counter and QR acceptance scenarios with real HTTP and browser workflows.

The current application remains unchanged until this implementation sequence is explicitly started.
