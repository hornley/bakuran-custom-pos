# Bakuran Counter UI Simplification

Date: 2026-09-07
Status: Approved by user and implemented
Scope: Simplify the existing front-desk POS ordering workspace. This change is frontend-focused and does not alter the backend order, payment, kitchen, or receipt contracts.

## 1. Goal

Make the front-desk POS easy to operate in one sequential pass:

```text
New order
  -> Build basket
  -> Confirm customer
  -> Collect cash
  -> Kitchen
  -> Ready for pickup
```

The interface should remove promotional copy and unrelated context from the primary workspace. Staff should not need to enter a table number for a manual counter order. Customer QR orders remain available through the connected unpaid-order queue.

## 2. Primary entry screen

Replace the large hero treatment with a compact counter header:

- Heading: `Counter`
- Supporting text: `Start a new order or open a QR order awaiting payment.`
- Primary entry: `New order`
- Secondary entry: `QR orders`

Remove these current hero elements:

- `Counter pickup / guided order`
- `Take the order. Keep it moving.`
- The long explanatory hero paragraph
- Any manual table-number prompt or requirement

The primary screen must not preload the menu, basket, table grid, receipt history, metrics, or kitchen history. Operations remain available through secondary navigation.

When a manual order is active, a visible `Back to order type` action remains above the stepper. It returns to the two entry choices without clearing the current basket or customer name. Choosing `New order` again resumes that manual draft.

## 3. Manual counter flow

Manual ordering uses one dominant task per screen:

1. **Basket**
   - Show menu categories, item details, price, quantity, and add controls.
   - Keep the basket and running total visible.
   - Primary action: `Review order`.
   - No table number field.

2. **Customer**
   - Show a read-only basket summary and total.
   - Require a calling name.
   - Primary action: `Continue to payment`.
   - Back action: `Back to basket`.

3. **Payment**
   - Show customer name, basket, and total due.
   - Primary action: `Record cash payment`.
   - Do not expose the generated order number before payment.
   - Back action: `Back to customer`.

4. **Kitchen and pickup**
   - After payment, show the generated order number, customer name, payment status, and kitchen status.
   - Reuse the existing preparing, ready, served, and close actions.
   - Back action: `Back to kitchen` returns to the kitchen queue without undoing payment or kitchen state.

After closing, show the receipt and a `Start another order` action.

## 4. Back navigation

Every reversible screen has an explicit back action:

| Current state | Back action | Result |
|---|---|---|
| Manual flow | `Back to order type` | Returns to the two entry choices while preserving the draft |
| Entry screen | No order-specific back action | Remains at counter entry choices |
| Basket | `Back to counter` | Returns to the entry screen and clears only an uncommitted empty draft |
| Customer | `Back to basket` | Keeps all basket items and quantities |
| Payment | `Back to customer` | Keeps basket and customer name; order remains unpaid |
| Kitchen / pickup | `Back to kitchen` | Returns to the kitchen queue; never reverses payment or kitchen state |
| QR payment review | `Back to QR orders` | Returns to the queue; does not edit or recreate the QR order |

Back navigation is non-destructive. It must not cancel, void, refund, or change server state. Existing server state is reloaded when returning to a persisted order context.

## 5. QR order path

The QR path remains separate from manual ordering:

1. Staff chooses `QR orders`.
2. The connected queue lists submitted unpaid QR orders.
3. Staff selects an order from the list. No scanning or manual order-number input is required.
4. The review screen is read-only and shows customer name, existing order number, total, and table context when available.
5. Staff records cash payment.
6. The existing order number is preserved and the paid order enters the kitchen.
7. Back action: `Back to QR orders`.

The manual flow must not show QR-specific table context. QR table context may be shown as read-only information when supplied by the order.

## 6. Navigation and secondary operations

Keep secondary routes available but visually subordinate:

- New order
- QR orders / awaiting payment
- Kitchen
- Ready pickup
- Operations

The ordering route should emphasize the current step rather than render multiple operational dashboards at once. Do not add inventory or purchasing content.

## 7. Error and recovery behavior

- If starting an order fails, remain at the entry screen and show a dismissible error.
- If adding an item fails, preserve the current basket state and show the error.
- If customer confirmation fails, remain on the customer screen with the name and basket intact.
- If payment fails, remain on the payment screen and keep the order unpaid and out of the kitchen.
- If a back action returns to a persisted order, refresh that order from the server before rendering status-sensitive actions.
- Avoid destructive cancel or reset actions in the primary flow. Starting another order is available only after completion or an explicit fresh-start action.

## 8. Visual direction

Retain the existing dark operational visual language while reducing hierarchy and copy density:

- Compact header instead of a hero slogan.
- One dominant action per step.
- Back actions are secondary text buttons, visually clear but subordinate.
- Menu items use a responsive two-column product-card grid on larger screens and one column on small screens.
- High contrast for total, customer name, order number, and payment state.
- No large dashboard metric strip on the first screen.
- No default floor/table grid, receipt history, or kitchen history on the first screen.
- Preserve responsive behavior for front-desk monitors and smaller screens.

## 9. Acceptance scenarios

### Manual counter order

1. Open the app and see a compact `Counter` entry screen.
2. Confirm the removed slogan and long hero copy are not shown.
3. Choose `New order`.
4. Confirm products display as cards in a grid and the basket remains visible.
5. Add items and confirm the basket updates.
6. Use `Back to order type`, then choose `New order` again and confirm the draft remains.
7. Continue to customer confirmation and enter a calling name.
8. Use `Back to basket` and confirm items remain.
9. Continue to payment and use `Back to customer`; confirm the name remains and the order is still unpaid.
10. Record cash payment and confirm the order number appears only after payment.
11. Advance the order through kitchen and pickup states.
12. Use `Back to kitchen` without changing payment or kitchen state.
13. Close the order and confirm a receipt is issued.

### QR order payment

1. Choose `QR orders` from the counter screen.
2. Select an unpaid submitted QR order from the connected queue.
3. Confirm the review is read-only and no scan or order-number field is required.
4. Use `Back to QR orders` and confirm the queue remains available.
5. Reopen the order, record cash payment, and confirm the existing order number is preserved.
6. Confirm the paid order enters the kitchen with its QR table context.

### Minimal first screen

The initial counter workspace must not render:

- A floor or table grid.
- The menu or basket before `New order` is chosen.
- QR payment orders before `QR orders` is chosen.
- Historical receipts.
- Dashboard metrics.
- Kitchen history.
- Inventory or purchasing data.

## 10. Non-goals

- No payment gateway.
- No inventory management.
- No customer-facing QR ordering page in this pass.
- No order cancellation, voids, refunds, or staff administration.
- No backend schema or endpoint changes unless implementation discovers a necessary compatibility fix.
