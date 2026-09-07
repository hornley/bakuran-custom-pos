# Phase 2: Payment Gate and Ready / Pickup Queue

**Status:** Approved, merged, and shipped on `main`
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

- Focused backend payment-gate tests rejected unpaid and served-order release attempts without mutation.
- Full `./test.sh` checks passed, including backend pytest and frontend production build.
- Ready/pickup queue filtering and served-ticket visibility were verified.
- Final diff and branch status review completed.

## Approval gate

The developer reviewed and explicitly approved this phase. It was merged into `main`; no further phase-2 merge is pending.
