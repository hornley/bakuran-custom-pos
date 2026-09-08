# Customer QR ordering

**Status:** Implemented; awaiting developer approval
**Branch:** `feat/customer-qr-ordering`
**Base:** `main`
**Scope:** Public customer ordering for an open table session, connected to the existing cash-only front desk.

## Delivered

- Open-table mutations issue a high-entropy QR bearer token once. The database stores only its SHA-256 hash and issuance timestamp.
- Public session endpoints expose the active menu and a token-scoped order status route without operator cookies or authentication state.
- Customer names, quantities, line counts, duplicate lines, and idempotency keys are bounded and validated before writes.
- The create path runs in one `BEGIN IMMEDIATE` transaction, revalidates active menu/category state, snapshots current server prices, and creates an `awaiting_payment` QR order with no kitchen ticket.
- A table session accepts at most one active QR order. Idempotent retries return the original order; a reused key with a changed name or basket returns `409`.
- The public customer API is intentionally unauthenticated only within the session-scoped `/api/customer/tables/{token}...` prefix; it does not grant access to operator endpoints. The React entrypoint selects `/qr/<token>` before the operator `AuthGate`, while all other paths continue to render the authenticated front-desk application.
- The customer UI is responsive, supports active-menu browsing and a local basket, preserves input on API errors, and confirms the order number plus cash-payment handoff without implying kitchen release.

## Public contract

| Route | Behavior |
| --- | --- |
| `GET /api/customer/tables/{token}` | Open session context and active menu |
| `GET /api/customer/tables/{token}/menu` | Active menu only |
| `POST /api/customer/tables/{token}/orders` | Requires `Idempotency-Key`; creates one `awaiting_payment` QR order |
| `GET /api/customer/tables/{token}/orders/{order_id}` | Reads only a QR order in the same session |

Invalid, closed, and cross-session tokens return `404`. Customer order responses omit the raw idempotency key and fingerprint. Staff still uses the authenticated payment queue and cash payment endpoint; there is no customer payment gateway.

## Verification

```bash
./test.sh
(cd backend && .venv/bin/python -m pytest -q tests/test_auth_boundary.py tests/test_qr_ordering.py)
(cd frontend && npm test)
(cd frontend && npm run build)
git diff --check
```

Browser verification must use a temporary SQLite database. It should cover a mobile-sized `/qr/<token>` page, active menu browsing, basket/name submission, confirmation, an invalid/closed token state, and the unchanged front-desk root route.

## Limitations and follow-ups

- This is a single-store, single SQLite deployment. There is no cross-location synchronization, customer account, notification service, or online payment gateway.
- One open table session accepts one active order, preserving the existing table/order model and preventing ambiguous payment selection.
- Operators must securely distribute the token-backed QR URL. The raw token is intentionally available only in the open-table response needed to print or configure that QR code.
- The feature remains subject to the repository approval gate; this branch must not be merged until the developer explicitly approves it.
