# Parallel Phase 2 Tasks

## Coordination rules

- Base commit for both features: `e622d7319d4ecf94aba94fdc7a361d1abdc912fc` (`origin/main`).
- Each feature has its own Git worktree and branch. Do not edit, checkout, reset, or commit in another worktree.
- Read this file before starting and update the status/progress section after each meaningful milestone.
- This file is the shared orchestrator log at `/home/dei/dev/bakuran-custom-pos/TASKS.md`; it is coordination-only and must not be staged in feature PRs.
- Use strict TDD: add a failing regression test first, run it and record the expected failure, then implement the smallest fix and rerun focused plus full checks.
- Do not delete, weaken, or rewrite an existing test merely to make it pass. If an existing assertion contradicts the current `SPEC.md`, preserve its intent where possible, add the new contract coverage, and explain any necessary update in the progress log.
- Before a PR is created, review the diff, run the applicable checks, commit only feature files/tests, push the feature branch, and create a PR targeting `main`. Do not merge.
- Record exact branch, worktree, commit SHA, PR URL/number, checks, and blockers here when complete.

## Feature 1 — Payment gate

- Worktree: `/home/dei/dev/bakuran-custom-pos-payment-gate`
- Branch: `fix/phase-2-payment-gate`
- Owner: Hermes subagent `bakuran-payment-gate`
- Scope: unpaid orders must never be sent to the kitchen or receive a kitchen ticket; payment creates one queued ticket; valid/invalid transitions and idempotency are covered by tests.
- Required tests: rejected unpaid send, state/ticket unchanged after rejection, successful post-payment release, and relevant idempotency/invalid-action cases.
- Do not expand into unrelated UI or refactoring.

Status: PR OPEN — awaiting developer approval
Progress:
- 2026-09-08: Worktree reserved from `origin/main`.
- 2026-09-08: Hermes CLI agent completed TDD implementation in the isolated worktree.
- 2026-09-08: Commit `f1bfc4775bbcca48cf496703594746d3b8c3a015` pushed to `fix/phase-2-payment-gate`.
- 2026-09-08: PR #2 opened: https://github.com/hornley/bakuran-custom-pos/pull/2
- 2026-09-08: Coordinator independently verified the exact PR head, diff, and isolated full checks: 10 tests passed and frontend build passed (3 existing dependency/runtime warnings).
- 2026-09-08: Fixed the two trailing-whitespace findings in `docs/phases/phase-2.md` with focused commit `a418d957a202e4dc0f6ba80e847a9bd3d910b8ab`; branch and PR #2 now point to this exact SHA, and `git diff --check` is clean.
- 2026-09-08: Final focused payment-gate checks passed: 6 tests passed with 2 existing dependency deprecation warnings. Final `./test.sh` passed: 10 backend tests with 3 existing warnings and the frontend TypeScript/Vite production build. GitHub confirms PR #2 is open, unmerged, targets `main`, and has head SHA `a418d957a202e4dc0f6ba80e847a9bd3d910b8ab`; no GitHub status checks are reported.
- 2026-09-08: Fresh independent Hermes reviewer ran read-only from detached exact-SHA worktree `/home/dei/dev/bakuran-review2-payment-a418d957a202e4dc0f6ba80e847a9bd3d910b8ab` and returned `CHANGES_REQUESTED` for `backend/app/main.py:250`: `/pay` still accepts `served` orders, allowing payment after kitchen fulfillment. Reviewer also suggested explicit awaiting-payment `/send` state assertions, a valid paid-release idempotency test, and updating the stale test count in `TESTING.md`. No files or GitHub reviews were modified.
- 2026-09-08: Review-fix subagent is assigned the existing dedicated PR worktree `/home/dei/dev/bakuran-custom-pos-payment-gate` to reject payment after kitchen fulfillment, add regression coverage, rerun all checks, and update PR #2 without changing unrelated tests.
- 2026-09-08: Strict TDD RED verified with `backend/.venv/bin/python -m pytest backend/tests/test_workflow.py::test_served_order_cannot_be_paid_again_and_preserves_state -q`: the new regression reached `/pay` and failed with the pre-fix `sqlite3.IntegrityError` caused by accepting a served order.
- 2026-09-08: GREEN focused regression passed after the minimal `/pay` state guard was changed to accept only `awaiting_payment` (while retaining the already-paid idempotent return); `TESTING.md` now records the regression contract and current backend count.
- 2026-09-08: Final fix commit `77d8fcdd956163cfabe56fd3c9f53f9e6d18e00e` pushed to `fix/phase-2-payment-gate`; focused regression passed (`1 passed`, 2 existing deprecation warnings), workflow tests passed (`9 passed`, 3 existing warnings), full backend suite passed (`11 passed`, 3 existing warnings), and `./test.sh` passed with the frontend TypeScript/Vite production build.
- 2026-09-08: GitHub confirms PR #2 remains open and unmerged, targets `main`, and points to exact head SHA `77d8fcdd956163cfabe56fd3c9f53f9e6d18e00e`; no GitHub status checks/check runs are reported. Blockers remain developer approval before merge and absent GitHub CI/checks. `TASKS.md` is intentionally not staged.
- 2026-09-08: Fresh post-fix Hermes reviewer ran read-only from detached exact-SHA worktree `/home/dei/dev/bakuran-review3-payment-77d8fcdd956163cfabe56fd3c9f53f9e6d18e00e` and returned `APPROVE` with no blockers. It verified the served-order payment rejection, valid payment release, idempotency, isolated backend suite (`11 passed`), frontend production build, syntax checks, and `git diff --check`. One non-blocking suggestion remains to update the older design document that describes the obsolete lifecycle. No files or GitHub reviews were modified.
- Blockers: developer approval is required before merge; GitHub CI/checks are not reported for PR #2.

## Feature 2 — Ready/pickup queue

- Worktree: `/home/dei/dev/bakuran-custom-pos-ready-queue`
- Branch: `feat/phase-2-ready-pickup-queue`
- Owner: Hermes subagent `bakuran-ready-queue`
- Scope: after a ticket is marked served/called, it remains visible in a ready/pickup queue until order close; active kitchen behavior remains correct; use a clear compatible API filter/endpoint.
- Required tests: backend ready-filter/served-ticket visibility plus frontend coverage where the project supports it.
- Do not expand into unrelated UI or refactoring.

Status: PR OPEN — awaiting developer approval
Progress:
- 2026-09-08: Worktree reserved from `origin/main`.
- 2026-09-08: Hermes CLI agent completed TDD implementation in the isolated worktree.
- 2026-09-08: Commit `7a8c5a992f5624044bace88d4614564dfa2db0d2` pushed to `feat/phase-2-ready-pickup-queue`.
- 2026-09-08: PR #1 opened: https://github.com/hornley/bakuran-custom-pos/pull/1
- 2026-09-08: Coordinator independently verified the exact PR head, diff, and isolated full checks: 10 tests passed and frontend build passed (3 existing dependency/runtime warnings).
- 2026-09-08: Exact-head verification for `7a8c5a992f5624044bace88d4614564dfa2db0d2`: branch tip matches `origin/feat/phase-2-ready-pickup-queue`; `origin/main` is an ancestor; worktree is clean; `git diff --check origin/main...HEAD` is clean; focused regression passed (`1 passed`, 2 existing deprecation warnings); full `./test.sh` passed (backend `10 passed`, 3 existing warnings, frontend TypeScript/Vite production build passed).
- 2026-09-08: GitHub confirms PR #1 is open, unmerged, targets `main`, and points to head SHA `7a8c5a992f5624044bace88d4614564dfa2db0d2`. No GitHub status checks or check runs are reported for this branch. Static scan of added lines found no hardcoded secrets, shell injection, eval/exec, unsafe pickle, or SQL-formatting findings. The existing frontend package has no test runner; frontend production build is the applicable check.
- 2026-09-08: Coordinator fixed the new ready-queue regression setup for payment-gate compatibility only: it now confirms and pays before kitchen transitions, preserving the existing tests and assertions. Commit `453382ddd3e02ba6782b4c1697d63dd2bc496ba0` is pushed; focused test passed (`1 passed`, 2 existing deprecation warnings) and final `./test.sh` passed (`10 passed`, 3 existing warnings, frontend TypeScript/Vite production build passed).
- 2026-09-08: Final remote verification confirms `origin/feat/phase-2-ready-pickup-queue` and PR #1 both point to `453382ddd3e02ba6782b4c1697d63dd2bc496ba0`; PR #1 targets `main` and remains open/unmerged. No GitHub status checks or check runs are reported.
- 2026-09-08: Fresh independent Hermes reviewer ran read-only from detached exact-SHA worktree `/home/dei/dev/bakuran-review2-ready-453382ddd3e02ba6782b4c1697d63dd2bc496ba0` and returned `APPROVE` with no blockers. Reviewer suggested coverage for a pre-served `ready` ticket, frontend request-level coverage if a test harness is added, and updating pending verification text in `TESTING.md`. No files or GitHub reviews were modified.
- Blockers: developer approval is required before merge; GitHub CI/checks are not reported for PR #1.

## Orchestrator checklist

- [x] Create isolated worktrees from latest `origin/main`.
- [x] Create this shared task log.
- [x] Start both Hermes CLI agents in parallel with model `cx/gpt-5.6-luna-max`.
- [x] Monitor each agent's TDD milestones and worktree status.
- [x] Verify each exact feature SHA independently before accepting its PR handoff.
- [x] Confirm both PRs target `main` and remain unmerged.
- [x] Report PRs, checks, and remaining limitations to the developer.
- [x] Merge PR #1 after exact-head and clean-worktree verification.
- [x] Resolve PR #2's post-PR #1 documentation conflict without changing feature behavior, then push exact updated head.
- [x] Merge PR #2 after exact-head and clean-merge verification.
- [x] Pull merged `main` and validate the composed tree using the dependency-equipped payment worktree (`12 passed`, frontend production build passed, compile/diff checks passed).
- [x] Remove clean implementation and detached review worktrees; delete merged local feature branches.

## Product roadmap tracks — customer and operations expansion

This section is coordinated from the root checkout. `TASKS.md` is not part of feature PRs.
The current Phase 3 work remains owned by its existing agent; these tracks start from
`origin/main` and do not edit or merge the Phase 3 worktree.

### Scope and dependency decisions

The requested product work is split into seven independently reviewable vertical slices:

1. **Customer-facing QR ordering** — public table-token route, menu/basket, customer name,
   `awaiting_payment` submission, confirmation, and handoff to the existing front-desk queue.
2. **Inventory and purchasing improvements** — warehouse-aware stock, guarded purchase
   ordering/receiving, partial receipts, adjustments, low-stock visibility, permissions,
   and audit events.
3. **Tax calculation and configuration** — configurable tax rates, deterministic money
   rounding, tax snapshots on orders/receipts, manager/admin configuration, and UI display.
4. **Promotions and discounts** — validated discount codes/rules, stacking policy, order
   snapshots, permission limits, audit events, and UI application/review.
5. **Refunds, voids, and cancellations** — guarded lifecycle transitions, cash refund
   records tied to original payments, inventory restoration where applicable, permissions,
   idempotency, auditability, and operational UI.
6. **Delivery workflows** — delivery order metadata, address/driver assignment, guarded
   dispatch/status transitions, failure recovery, permissions, audit events, and UI.
7. **Printer and fiscal-device integrations** — provider boundary, durable print/fiscal job
   queue, retry/idempotency behavior, fiscal configuration, permissions, audit events, and UI.

Dependency order:

```text
QR ───────────────┐
Inventory ────────┼──> Tax ──> Promotions ──> Refunds/voids/cancellations ──> Printer/fiscal
Delivery ─────────┘
```

QR, inventory, and delivery do not depend on the financial tracks and may be implemented
from `origin/main` in isolated worktrees. They still touch shared application/docs files,
so implementation is serialized unless the agents can prove disjoint ownership. Tax must
precede promotions; promotions must precede refunds; printer/fiscal consumes finalized tax,
refund, and receipt state. No feature branch is merged automatically.

### Acceptance and non-negotiable constraints

- Every track has its own worktree, branch, focused commit(s), pushed branch, and GitHub PR.
- Each PR gets a separate detached read-only reviewer at its exact head; the reviewer must
  inspect the diff, SPEC/docs, migrations, permissions, security, edge cases, and tests,
  then post a GitHub review comment. A stale or partial review is not approval.
- No payment gateway integration is assumed. Payment-provider boundaries remain explicit;
  cash refunds and local print/fiscal adapters must not claim external settlement.
- Tenant isolation is represented by the current single-store schema; any new records must
  be scoped to the store/warehouse/table/order context and must not accept arbitrary foreign
  identifiers without validation. If true multi-tenant isolation is not available in the
  current schema, document it as a blocker rather than pretending it is implemented.
- All mutations are transactional, validated, idempotent where retried, and audit logged.
- Monetary calculations use deterministic decimal rounding and preserve historical snapshots.
- Existing payment-gate and lifecycle behavior must remain green; tests never use
  `backend/data/app.db`.

### Track status

| Track | Branch | Base | Status | PR | Reviewer |
|---|---|---|---|---|---|
| Customer-facing QR ordering | `feat/customer-qr-ordering` | `origin/main` | Review-clean; awaiting developer approval | #5 https://github.com/hornley/bakuran-custom-pos/pull/5 | Exact-SHA COMMENTED approval at `1b4e5b8` |
| Inventory/purchasing improvements | `feat/inventory-purchasing-workflow` | `origin/main` | Quantity-bound fix pushed; re-review pending | #6 https://github.com/hornley/bakuran-custom-pos/pull/6 | Fresh exact-SHA review required at `8d2b857` |
| Tax calculation/configuration | `feat/tax-configuration` | `origin/main` (`57fe8f3`) | Review-clean; awaiting developer approval | #7 https://github.com/hornley/bakuran-custom-pos/pull/7 | Exact-SHA COMMENTED approval at `c1df91b` |
| Promotions/discounts | `feat/promotions-discounts` | tax branch | Planned | — | — |
| Refunds/voids/cancellations | `feat/refunds-voids-cancellations` | promotions branch | Planned | — | — |
| Delivery workflows | `feat/delivery-workflows` | `origin/main` | Review-clean; awaiting developer approval | #4 https://github.com/hornley/bakuran-custom-pos/pull/4 | Exact-SHA COMMENTED approval at `b1160ee` |
| Printer/fiscal integrations | `feat/printer-fiscal-integrations` | refunds branch | Planned | — | — |

### Implementation log

- 2026-09-08: Inspected `AGENTS.md`, all `docs/`, `SPEC.md`, manifests, migrations,
  backend/frontend architecture, current tests, branch/worktree state, and GitHub auth.
- 2026-09-08: Confirmed `origin/main` is `da40b9e`; the Phase 3 coordinator branch is
  separate and has no active child process visible in this session. Preserving it and
  starting product tracks from the latest appropriate base rather than duplicating Phase 3.
- 2026-09-08: Phase 3 is merged into `origin/main` at `57fe8f3`. QR ordering PR #5 is
  pushed at `7af13d6a9e2c027b87824dbc7b2822831124c676`; delivery PR #4 is pushed at
  `99d4edee251b2431acb2f3b24eb2e516b6971dc4`. Both are open, unmerged, and awaiting
  independent exact-SHA reviews. Inventory work continues in its isolated worktree.
- 2026-09-08: Inventory/purchasing PR #6 is pushed at
  `617465c59925b54ef69ef4ec0dd4f21e36fcbce8`; it is open, unmerged, and awaiting an
  independent exact-SHA review.
- 2026-09-08: Exact-SHA inventory review posted at
  `https://github.com/hornley/bakuran-custom-pos/pull/6#pullrequestreview-5137279425`.
  It found a populated-reset foreign-key failure in `backend/app/db.py` and a frontend
  retry-key reuse gap in `frontend/src/App.tsx`; both fixes are assigned in the existing
  inventory worktree. GitHub cannot accept REQUEST_CHANGES from the PR author account, so
  the review is recorded as COMMENTED and is not approval.
- 2026-09-08: Exact-SHA delivery review posted at
  `https://github.com/hornley/bakuran-custom-pos/pull/4#pullrequestreview-5137291275`.
  It found a delivery payment-gate/status conflict after kitchen service, sensitive
  failure/cancellation reasons copied into audit details, and stale delivery draft fields
  leaking into a new order. Fixes are assigned in the existing delivery worktree. GitHub
  cannot accept REQUEST_CHANGES from the PR author account, so the review is COMMENTED and
  is not approval.
- 2026-09-08: Delivery fixes pushed at `79c462af53efc3f9000c3c1218efe208b6091555`.
  Coordinator independently verified PR #4 remains open/clean and reran `./test.sh`: 28
  backend tests, 5 frontend tests, and the production build passed; `git diff --check`
  passed. A fresh detached exact-SHA re-review is required for this new head.
- 2026-09-08: Delivery re-review found a blocking frontend header merge bug: delivery
  mutations replaced default JSON/CSRF headers when adding `Idempotency-Key`, causing browser
  requests to fail validation. A focused header/test/docs fix is assigned before re-review.
- 2026-09-08: Delivery header fix pushed at `ab4d060a3e0757210b65c3e3ac12ece35571cdbf`.
  The fix agent reported focused delivery tests (11), full backend tests (28), frontend tests
  (5), build, and `git diff --check` passing; stale phase/testing counts were updated. A fresh
  exact-SHA review is assigned.
- 2026-09-08: Delivery re-review found only stale validation counts in checked-in docs and the
  PR description (`5` versus the observed `6` frontend tests). A documentation-only correction
  is assigned before final re-review.
- 2026-09-08: Delivery count correction pushed at `b1160eef99e76adfd285e8843492437621f15bb3`.
  TESTING.md, phase-5.md, and the PR description now report focused 11, backend 28, frontend 6
  in 2 files, build, and diff-check results. A final exact-SHA review is assigned.
- 2026-09-08: Delivery PR #4 final exact-head review completed at
  `b1160eef99e76adfd285e8843492437621f15bb3` with Verdict: APPROVE and no findings. GitHub
  recorded the self-review as COMMENTED; review URL:
  `https://github.com/hornley/bakuran-custom-pos/pull/4#pullrequestreview-5138187922`.
- 2026-09-08: Exact-SHA QR review posted at
  `https://github.com/hornley/bakuran-custom-pos/pull/5#pullrequestreview-5137317626`.
  It found that the default disabled-auth deployment leaves operator mutations unauthenticated,
  violating the documented public-customer/operator boundary. The review is COMMENTED because
  GitHub rejects REQUEST_CHANGES from the PR author account; a fix and exact-head re-review are
  required before the PR can be considered ready.
- 2026-09-08: QR PR #5 auth-boundary fix assigned in the existing QR worktree after the
  exact-SHA reviewer found default operator mutations unauthenticated. A new exact-head
  review will be required after the fix is pushed.
- 2026-09-08: QR auth-boundary fix pushed at `1b4e5b87422059be993234c60be86e6cfb2aa62f`.
  It denies operator mutations by default, preserves token-scoped public customer routes,
  documents explicit `AUTH_LOCAL_DEV_BYPASS`, and adds auth-boundary tests. A fresh exact-SHA
  review is assigned after an earlier reviewer process hit the workspace spend cap.
- 2026-09-08: Two bounded QR review attempts were interrupted before posting. A short,
  read-only exact-SHA review was re-dispatched for PR #5; no source changes are pending.
- 2026-09-08: QR PR #5 exact-head review completed at `1b4e5b87422059be993234c60be86e6cfb2aa62f`.
  The reviewer posted a formal COMMENT review with `Verdict: APPROVE` because GitHub rejects
  self-approval; no blocking findings remained. Review URL:
  `https://github.com/hornley/bakuran-custom-pos/pull/5#pullrequestreview-5137769200`.
- 2026-09-08: Tax takeover assigned in `/tmp/bakuran-tax` because the first implementation
  stopped with uncommitted backend-only changes and no PR; frontend/UI, current docs, final
  validation, push, and PR creation remain outstanding.
- 2026-09-08: Tax PR #7 opened at `b0ebc9da7bb9a7c6c0a95bf533e627ef41b60ff9`.
  The completed vertical slice reports focused tax tests (26), full backend tests (43),
  frontend tests (5), production build, isolated-database smoke validation, and
  `git diff --check` passing. An independent exact-SHA review is required before approval.
- 2026-09-08: Tax exact-SHA review found two blocking magnitude-validation gaps: huge payment
  decimals can raise `InvalidOperation` as HTTP 500, and huge order-line quantities can do the
  same during Decimal quantization. A focused 422/no-mutation fix with regression tests is
  assigned for PR #7.
- 2026-09-08: Tax magnitude fix pushed at `c1df91b84a15a41785e452a592e3cf2d0986e487`.
  It bounds monetary values to `9999999999.99`, order-line quantities to `999999999`, catches
  Decimal quantization failures as 422, and adds no-mutation regressions. Final validation:
  28 focused tax tests, 45 backend tests, 5 frontend tests, build, diff check, and isolated
  DB safety passed. A fresh exact-SHA review is assigned.
- 2026-09-08: Tax PR #7 exact-head re-review completed at
  `c1df91b84a15a41785e452a592e3cf2d0986e487` with Verdict: APPROVE and no findings. GitHub
  recorded the self-review as COMMENTED; review URL:
  `https://github.com/hornley/bakuran-custom-pos/pull/7#pullrequestreview-5138607053`.
- 2026-09-08: Inventory review fixes pushed at `97247c29d4b29f78998694d3ba509afa8433df9d`.
  Coordinator verified PR #6 remains open/clean; the fix agent reported `./test.sh` passed
  with 42 backend tests, 6 frontend tests, build, focused reset/retry regressions, and
  `git diff --check`. A fresh detached exact-SHA re-review is required for this new head.
- 2026-09-08: The fresh inventory review found a further blocking validation gap: purchase
  line unit costs accepted non-finite JSON values such as `1e309`; a focused fix and re-review
  are assigned before PR #6 can be considered review-clean.
- 2026-09-08: Inventory non-finite unit-cost fix pushed at
  `70cc65fc636b7900dc2b0f31ac9e35636de7fd8a`. The fix agent reported focused inventory tests
  (26), full backend tests (44), frontend tests (6), build, and `git diff --check` passing.
  A fresh exact-SHA review is assigned for this head.
- 2026-09-08: The fresh inventory review found a second numeric-integrity gap: finite
  `unit_cost=1e308` multiplied by quantity can overflow to Infinity after validation and
  commit state before response serialization. A focused computed-total overflow fix and
  re-review are assigned.
- 2026-09-08: Inventory computed-total overflow fix pushed at
  `e8b93cfab090e741810ed685685198130746c20a`. The fix agent reported focused inventory tests
  (28), full backend tests (46), frontend tests (6), build, and `git diff --check` passing;
  a fresh exact-SHA review is assigned.
- 2026-09-08: The fresh inventory review found unbounded quantity overflow: an extreme stock
  adjustment can exceed SQLite INTEGER range and silently store REAL stock. Purchase receipt
  and legacy receipt quantities share the same risk. A consistent bounded-quantity fix,
  regression tests, and documentation-count update are assigned.
- 2026-09-08: The first quantity-bound remediation agent exited without a terminal result;
  its worktree contains only uncommitted quantity regression-test edits and no production fix.
  A takeover agent was assigned to repair the tests, implement the bound consistently, and
  finish validation/push for PR #6.
- 2026-09-08: Inventory quantity-bound remediation committed and pushed at
  `8d2b857ee2aeccc6c5e014096697a6f259023fd9`. It bounds stock adjustments, purchase lines,
  receipt lines, legacy stock receipts, reorder levels, and checked arithmetic before mutation;
  docs were updated. Final validation: 32 focused inventory tests, 50 backend tests, 6 frontend
  tests, production build, diff check, and isolated DB safety passed. A fresh exact-SHA review
  is required for this new head.
- 2026-09-08: Created `/tmp/bakuran-tax` on `feat/tax-configuration` from `origin/main`
  `57fe8f3` and recorded the Phase 6 tax scope before implementation. Tax is serialized
  after the independent review gates for the existing PRs; promotions will depend on its
  finalized tax snapshot contract.
