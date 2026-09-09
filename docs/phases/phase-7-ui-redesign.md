# Phase 7: Bakuran POS v4 UI Redesign

**Status:** Implementation in progress; awaiting developer approval
**Branch:** `feat/phase-7-v4-ui`
**Base:** `main` at `23db34f`

## Purpose

Implement the approved v4 design contract in `DESIGN.md` across the operator POS and public customer QR ordering surface without changing backend contracts or payment-gate behavior.

## Deliverables

- Replace the legacy operator visual language with the shared v4 tokens, restrained shell, persistent desktop rail, and responsive small-screen navigation.
- Add an operational Overview surface with the live dashboard feed, service strip, attention queue, and quick actions; do not fabricate metrics.
- Keep New order as a visible four-step Basket → Customer → Payment → Kitchen & pickup flow with server-provided totals and tax breakdowns.
- Make QR payments, Kitchen, Ready, Delivery, and Operations secondary workspaces with clear next actions and explicit status text.
- Preserve delivery, inventory/purchasing, tax, authentication, CSRF, idempotency, and public `/qr/<token>` contracts.
- Make interactive controls semantic, keyboard-accessible, focus-visible, live-region aware, and safe under reduced motion.
- Validate the required desktop/tablet/mobile viewport matrix with fresh screenshots and record browser limitations honestly.
- Keep `TESTING.md` and this phase handoff aligned with runnable checks and known limitations.

## Current implementation note

The operator shell is being aligned to `DESIGN.md` and the generated warm premium reference:
desktop rail + utility bar, live service strip, attention queue, shortcut actions, restrained
terracotta accent, sage success states, and responsive rail-to-scroll navigation. Existing API
contracts and the customer QR route remain in scope and are not replaced by mock data.

## Scope boundaries

- Presentation and interaction work only; no new backend workflow, payment gateway, inventory deduction, external courier, or hosted identity behavior.
- Inventory and purchasing remain secondary and must not preload in the counter flow.
- Tests and runtime checks must use isolated databases; never mutate `backend/data/app.db`.
- Do not merge or push this phase before explicit developer approval.

## Verification plan

Run from the repository root:

```bash
./test.sh
cd frontend && npm test
cd frontend && npm run build
git diff --check
```

Also run an isolated read-only/runtime health check and fresh browser inspection at 1440px, 1280px, 1024px, 768px, and 390px. Inspect the operator route and `/qr/<token>` separately, including keyboard focus, semantic controls, live status/error messaging, reduced-motion CSS, payment-action visibility, and horizontal overflow. Do not claim visual verification when the browser environment cannot provide it.

## Known limitations

- The repository's automated frontend tests use mocked fetch responses and do not replace live browser/E2E verification.
- External courier services, driver applications, GPS, and payment gateways are intentionally out of scope.
- The default local deployment may be unauthenticated; protected-auth behavior remains covered by the existing backend/auth tests.

## Approval gate

This phase is not complete until the developer explicitly reviews and approves the implementation. The coordinator must provide changed files, exact checks and observed results, fresh screenshot/browser evidence or its limitation, independent QA findings for the exact implementation head, and remaining limitations before requesting approval.
