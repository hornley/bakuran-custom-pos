# Phase 3 Operational Hardening — Handoff Prompt

Copy the prompt below into the next Hermes/Coding Agent session.

```text
You are the implementation lead for Phase 3 of the Bakuran POS repository.

Repository: /home/dei/dev/bakuran-custom-pos
Remote: https://github.com/hornley/bakuran-custom-pos
Starting branch: main
Verified starting commit: da40b9ee158fee732f2a8c026c6bc3dd606ff586

## Current product state

Bakuran POS is a React/Vite frontend with a FastAPI/SQLite backend. Phase 2 is already merged into main:

- PR #1 — ready/pickup kitchen queue — merge commit 9129be07bb3fb38bc23af4d1b90b7ff3173a4a83
- PR #2 — payment gate before kitchen release — merge commit da40b9ee158fee732f2a8c026c6bc3dd606ff586

The implemented lifecycle is:

open -> awaiting_payment -> paid -> preparing -> ready -> served -> closed

The current behavior includes:

- unpaid orders cannot enter the kitchen;
- payment creates or releases exactly one kitchen ticket;
- served-order payment attempts are rejected without mutation;
- repeated valid payment/send requests are idempotent;
- GET /api/kitchen?queue=ready retains ready and served tickets until order close;
- the default GET /api/kitchen behavior remains the active kitchen queue.

At the last validation, the dependency-equipped checkout passed 12 backend tests and the frontend TypeScript/Vite production build. The main checkout previously lacked backend dependencies, so verify the current environment instead of assuming tests can run there. The root checkout also contains an untracked coordinator file TASKS.md; preserve it and do not commit or delete it unless explicitly directed.

## Phase 3 goal

Improve operational confidence and maintainability without expanding the POS product scope. Deliver tested, reproducible validation and close stale phase documentation before adding larger customer-facing features.

## Mandatory operating rules

1. Re-check git status, branch, origin/main, AGENTS.md, README.md, SPEC.md, TESTING.md, and the existing phase documents before editing.
2. Branch from the latest origin/main. Use a phase branch named `feat/phase-3-operational-hardening` or separate phase-3 branches for genuinely independent workstreams.
3. Create or update `docs/phases/phase-3.md` before implementation begins. Record scope, acceptance criteria, verification, and the developer-approval gate.
4. If work is parallelized, every implementation subagent gets its own Git worktree and branch. The coordinator owns the root worktree and TASKS.md. Each subagent must read TASKS.md and record concise progress there without adding unrelated coordination files to feature PRs.
5. Use TDD for behavior changes: write a failing regression test, verify RED, implement the smallest fix, verify GREEN, then run the full relevant suite.
6. Never remove, weaken, or rewrite existing tests merely to make them pass. Add regression coverage instead.
7. Keep each logical feature/workstream in its own focused commit and PR. Do not merge any PR until the developer explicitly approves it.
8. Use bounded Hermes CLI agents with `hermes --cli --model cx/gpt-5.6-luna-max`. Do not let reviewers recursively delegate unless explicitly required. Reviewers must use detached read-only worktrees at the exact reviewed SHA, return an explicit verdict, and stop immediately after the verdict.
9. Never test against `backend/data/app.db`. Backend integration tests must use the existing isolated temporary-database fixture.
10. Do not commit `.env` files, credentials, dependency directories, build output, local databases, logs, or caches.
11. Report unavailable browser/E2E tooling or dependencies honestly; do not fabricate a passing result.

## Required Phase 3 workstreams

### Workstream A — documentation and reproducible validation

- Update `docs/phases/phase-1.md` and `docs/phases/phase-2.md` so their status reflects that the approved work is merged and shipped; preserve their historical scope and verification details.
- Update `TESTING.md` so it describes the current 12-test backend suite, frontend build, payment-gate checks, and ready/pickup queue checks without stale “pending” or “awaiting approval” claims where no longer accurate.
- Update the README phase-document links if they are stale.
- Set up or repair only local ignored dependencies needed to run validation from the main checkout. Do not commit dependency directories.
- Run the original repository check unchanged: `./test.sh` from the root checkout.
- Add a safe read-only health check to the documented verification if appropriate. Never perform reset, seed, payment, order, kitchen, or close mutations against the operational database.

### Workstream B — backend lifecycle regression coverage

Inspect `backend/app/main.py` and existing tests before changing code. Add focused tests for behavior that is currently only partially covered:

- a ticket in `ready` remains visible in the ready/pickup queue before it is served;
- invalid or duplicate payment/release actions preserve order, payment, and ticket state;
- concurrent or repeated payment/release attempts cannot create duplicate payments or kitchen tickets, using an isolated temporary database;
- the full valid lifecycle still produces exactly one receipt and closes the table/order correctly;
- invalid kitchen transitions remain conflicts and do not mutate state.

Only change backend code if a test exposes a real defect. Preserve the payment-before-kitchen invariant and existing API compatibility.

### Workstream C — frontend test coverage

The current `frontend/package.json` has build scripts but no frontend test runner. Evaluate the smallest maintainable test setup, then add tests for the highest-value UI/API behavior:

- the Ready view requests `/api/kitchen?queue=ready`;
- the payment flow does not release an unpaid order;
- the QR payment queue selection preserves the submitted order data;
- recoverable API errors preserve the last valid view and show an error state;
- loading, mutation-busy, empty, and successful mutation states behave as intended.

Do not add a large framework or broad snapshot suite without justification. If a browser runner is added, keep the smoke test narrow and document how to run it. If browser execution is unavailable on this host, still run static/type/build checks and record the limitation.

### Workstream D — maintainability review

Review the growing `backend/app/main.py` and `frontend/src/App.tsx`, but do not perform a speculative rewrite. If the new tests identify a safe, small extraction that materially improves correctness or testability, make it as a separate focused change. Otherwise document the refactoring candidates for a later phase rather than expanding scope.

## Explicit non-goals

Do not implement these in Phase 3:

- customer-facing QR ordering;
- payment gateway integration;
- inventory or purchasing workflow changes;
- refunds, voids, cancellations, tax, promotions, delivery, or printer/fiscal integrations;
- authentication, roles, SSO, MFA, or hosted deployment;
- unrelated UI redesign or drive-by refactoring.

These remain later-phase candidates unless the developer changes scope explicitly.

## Acceptance criteria

Phase 3 is ready for handoff only when:

- the phase document exists and accurately records scope and approval status;
- stale documentation is corrected without rewriting history;
- the main checkout can run the documented validation with isolated test data;
- backend regression coverage passes without weakening existing tests;
- frontend checks pass, including the production build and any added frontend tests;
- `git diff --check` passes;
- any runtime/browser limitation is explicitly recorded;
- each logical workstream has focused commits and, if requested, its own PR;
- an independent reviewer has reviewed each final exact PR SHA and returned `APPROVE`;
- the coordinator reports changed files, exact commands, observed results, known limitations, and the developer-approval gate;
- nothing is merged without explicit developer approval.

## Required final report

Return a concise handoff containing:

- branch and PR URLs/SHA(s);
- changed files by workstream;
- exact validation commands and observed results;
- warnings or unavailable checks;
- reviewer verdicts for the exact SHAs;
- known limitations and recommended next phase: customer-facing QR ordering.
```
