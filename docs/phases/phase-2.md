# Phase 2: Payment Gate and Ready / Pickup Queue

**Status:** Implemented; awaiting developer approval
**Branch:** `fix/phase-2-payment-gate`
**Base:** `main`

## Purpose

Enforce the payment gate so unpaid orders never enter kitchen fulfillment.

## Deliverables

- Reject kitchen-send attempts for `open` and `awaiting_payment` orders.
- Preserve order and kitchen-ticket state after rejected or otherwise invalid attempts.
- Release a paid order to exactly one queued kitchen ticket.
- Preserve idempotent behavior for repeated valid release/send requests.
- Add backend integration coverage for rejection, no mutation, post-payment release, and idempotency.
- Add a validated ready/pickup kitchen queue containing ready and served tickets until order close.
- Update the frontend Ready view to request the ready/pickup queue.
- Add backend coverage for ready/pickup filtering and served-ticket visibility.

## Contract correction

The earlier workflow test allowed an order to be sent while `open`, then paid after kitchen service. That contradicts the current `SPEC.md` and `AGENTS.md`: manual and QR orders remain `awaiting_payment` until payment, and unpaid orders must not have a kitchen ticket. The test is updated to assert payment before kitchen release instead of preserving the obsolete path.

## Verification

- Focused backend payment-gate tests.
- Full `./test.sh` checks, including backend pytest and frontend production build.
- Final diff and branch status review.

## Approval gate

This phase is not complete until the developer reviews and explicitly approves it. Do not merge this branch into `main`.
