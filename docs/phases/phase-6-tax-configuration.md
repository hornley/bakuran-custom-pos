# Phase 6: Tax Calculation and Configuration

**Status:** Implementation complete; developer approval is required before merge.
**Branch:** `feat/tax-configuration`
**Base:** `57fe8f3` (`origin/main`)

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

## Non-goals

- Payment gateways or external settlement.
- Fiscal-device certification or accounting integration.
- Promotions, refunds, voids, cancellations, split payments, or multi-tenant deployment.
- Inventory deduction or purchasing behavior changes.

## Dependency decision

This track starts from `origin/main` rather than the unmerged inventory or delivery branches.
Tax calculation depends only on the existing order/payment/receipt schema; it does not require
warehouse or delivery records. Promotions will depend on this track's tax snapshot contract.
The current deployment remains single-store; tenant isolation is not being claimed.

## Acceptance criteria

- Existing zero-tax behavior remains compatible when no active tax rule is configured.
- A configured effective tax rule is selected server-side, not trusted from the client.
- Exclusive and inclusive tax calculations use `Decimal` and explicit half-up cent rounding.
- Order confirmation/recalculation snapshots the selected rule, taxable subtotal, tax amount,
  and total; payment amount validation uses the tax-inclusive order total.
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

To be recorded before handoff:

- focused tax backend tests (`26 passed`);
- full `./test.sh` with isolated temporary databases (`43 passed`);
- frontend tests (`5 passed`), TypeScript/Vite production build;
- `git diff --check`;
- independent exact-SHA reviewer verdict and GitHub review URL.

## Approval gate

This phase is not complete until the developer explicitly approves it. Do not merge or push
this phase branch into `main` before approval.
