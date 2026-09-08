# Phase 6: Tax Calculation and Configuration

**Status:** Implementation complete; developer approval is required before merge.
**Branch:** `feat/tax-configuration`
**Reconciled base:** `f46bdab3e09551eff23753fbdde82c7868ca2635` (`origin/main` after inventory)

## Purpose

Add deterministic tax configuration and tax snapshots to the existing cash POS without
changing the payment gate or claiming external accounting/fiscal compliance.

## Scope

- Manager/admin-configurable tax rates with inclusive/exclusive policy and inclusive
  effective date ranges. Ranges may be adjacent but may not overlap.
- Decimal-only monetary calculation with explicit half-up rounding at cent precision;
  rates are validated as decimal text with at most four fractional digits.
- Tax breakdowns on open orders, payments, and receipts.
- Historical order/receipt tax snapshots that do not change when configuration changes.
- Optional-auth permission checks, audit events, validation, and transactional updates.
- Secondary front-desk UI for tax configuration and order/receipt tax visibility,
  while preserving the compact initial screen.
- QR orders snapshot the effective server-side rule and tax-inclusive total when the
  public order is created. Payment defensively snapshots a legacy QR `awaiting_payment`
  row that has no snapshot before validating the amount, so pre-fix rows cannot bypass tax.

## Non-goals

- Payment gateways or external settlement.
- Fiscal-device certification or accounting integration.
- Promotions, refunds, voids, cancellations, split payments, or multi-tenant deployment.
- Inventory deduction or purchasing behavior changes.

## Data and transaction notes

The reconciled branch is based on `f46bdab3e09551eff23753fbdde82c7868ca2635` and applies
migrations `001` through `007` in order, including `006_inventory_purchasing.sql` and
`007_tax_configuration.sql`. QR order creation and the legacy payment fallback use the
existing `BEGIN IMMEDIATE` transaction boundary and select the effective rule on the server;
client-provided tax or totals are never trusted. Existing non-QR historical completed rows
remain immutable zero-tax history when a later rule is configured. New orders with no active
rule preserve the zero-tax total.

## Acceptance criteria

- Existing zero-tax behavior remains compatible when no active tax rule is configured.
- A configured effective tax rule is selected server-side, not trusted from the client.
- Exclusive and inclusive tax calculations use `Decimal` and explicit half-up cent rounding.
- Manual/delivery confirmation and QR order creation snapshot the selected rule, taxable
  subtotal, tax amount, and total; payment amount validation uses the tax-inclusive order total.
- Payment defensively snapshots a QR `awaiting_payment` order with no snapshot before amount
  validation, covering rows created before the QR tax integration.
- Closing an order issues exactly one receipt with the immutable tax snapshot.
- Configuration mutations require manager/admin when local auth is enabled, are audited, and
  reject invalid rates/date ranges and conflicting active effective rules.
- Repeated configuration/order actions are safe and do not create duplicate tax snapshots.
- The default checked-in `auth_profile: disabled` deployment intentionally allows
  local tax configuration without login. Explicit `AUTH_PROFILE=local` plus
  `AUTH_ENABLED=true` enables the existing local session/CSRF middleware, where
  only manager/admin roles may configure tax.
- Frontend displays the breakdown and offers a secondary configuration view without changing
  the compact initial screen.

## Verification

- Full `./test.sh`: `121 passed` backend, `16 passed` frontend tests in 3 files, and production build passed.
- Focused tax/QR/delivery/inventory/auth backend suites: `103 passed`.
- Fresh isolated migration/reset and endpoint smoke passed with migration versions `1, 2, 3, 4, 5, 6, 7`; health, tax configuration, QR order creation/payment, and delivery routes returned expected responses.
- `git diff --check` passed.
- No live browser/E2E or external courier integration was exercised.

## Approval gate

This phase is not complete until the developer explicitly approves it. Do not merge or push
this phase branch into `main` before approval.
