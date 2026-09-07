# Phase 2: Ready / Pickup Queue

## Scope

Keep kitchen tickets in the active kitchen queue only until they are called/served, while exposing a separate ready/pickup queue that retains served tickets until the order is closed.

## Deliverables

- Add a validated kitchen queue filter with a backward-compatible active default.
- Return ready and served tickets from the ready/pickup queue.
- Update the frontend Ready view to request the ready/pickup queue.
- Add backend integration coverage for the filter and served-ticket visibility.

## Verification

- Focused backend regression tests.
- Full `./test.sh` checks.
- Frontend production build.

## Status

Implementation in progress; developer approval is required before considering this phase complete or merging it.
