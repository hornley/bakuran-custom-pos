# Bakuran POS — Agent and Development Instructions

These instructions apply to every change in this repository. Read [`DESIGN.md`](DESIGN.md)
before changing the frontend; it is the visual and interaction contract for the operator
and customer surfaces.

## Repository map

- `backend/app/`: FastAPI application, SQLite access, authentication, tax, and domain workflows.
- `backend/tests/`: pytest integration/regression tests. The `conftest.py` fixture isolates every database.
- `frontend/src/App.tsx`: authenticated operator shell, counter flow, secondary queues, and Operations workspace.
- `frontend/src/CustomerQrApp.tsx`: public `/qr/<token>` customer ordering surface.
- `frontend/src/styles.css`: shared operator/customer tokens, layout, responsive rules, and accessibility states.
- `frontend/src/*.test.tsx`: mocked-fetch/component tests for operator and customer behavior.
- `start.sh`, `stop.sh`, `restart.sh`: fixed-port local launcher lifecycle.
- `DESIGN.md`: normative visual tokens, hierarchy, accessibility, and responsive behavior.
- `TESTING.md`: runnable validation commands and known test boundaries.
- `docs/phases/`: phase scope, handoff, approval gate, and limitations.

Do not invent a parallel frontend, API client, route, or token layer. Trace existing symbols
and endpoint usage before editing them.

## Design implementation contract

- Follow `DESIGN.md` for the warm off-white canvas, white surfaces, near-black ink, restrained
  terracotta primary accent, sage success states, typography, radius, elevation, and spacing.
- The operator shell is a Monitor + Operate surface: show the next safe action, live service
  state, attention queue, and one clear primary action. Do not turn it into a marketing hero,
  analytics dashboard, or decorative card grid.
- Keep the persistent desktop rail and slim utility bar. At narrow widths use the defined
  compact/scrollable navigation behavior without page-level horizontal overflow.
- Prefer semantic buttons/links/headings/lists/labels, visible `:focus-visible` states, readable
  live status/error messages, and minimum 44px interactive targets.
- Keep the customer QR route calmer and separate: no operator rail, credentials, or bearer-token
  leakage. Preserve explicit cash-at-front-desk language.
- Preserve visible status text alongside color. Respect `prefers-reduced-motion`.
- Do not leave legacy dark/amber operator tokens, arbitrary radii, emoji, gradients, purple,
  fake metrics, charts, food photography, decorative icon fillers, or colored card rails/edge
  strips in the implemented surface. Use neutral borders and whitespace for card hierarchy.

## Database and data safety

- Never test against or mutate the main operational database at `backend/data/app.db`.
- Automated backend tests must use an isolated temporary database. The existing fixture patches
  `app.db.DATABASE_PATH` to a `tmp_path` database before initializing the schema.
- Never run reset, seed, payment, order, kitchen, inventory, purchasing, delivery, or close
  mutations against the main database as part of testing or visual verification.
- If an integration test needs data, use the existing pytest fixture or create a temporary DB.
- Do not print, commit, or expose `.env`, credential files, bootstrap passwords, tokens, or secrets.

## Scope and invariants

- This phase is presentation and interaction work unless its phase document explicitly says otherwise.
- Inventory and purchasing remain secondary and must not preload in the counter flow.
- There is no payment gateway in scope; the current payment path is cash-only.
- Manual counter orders do not require a table number.
- QR orders are selected from the connected unpaid payment queue; staff review is read-only until cash payment.
- Preserve the payment gate: unpaid orders must not enter the kitchen.
- Preserve existing API paths, server-provided prices/totals/tax snapshots/order numbers/receipts,
  authentication and CSRF boundaries, idempotency behavior, and guarded state transitions.

## Explore before editing

1. Run `git status --short --branch` and inspect the active phase document.
2. Read `DESIGN.md`, the relevant route/component, shared CSS, nearby tests, and the manifest.
3. Trace changed symbols and endpoint callers with `search_files`; do not guess object shapes.
4. Identify the narrowest acceptance behavior and add a focused test before production code when
   behavior changes. Keep visual-only token/layout edits aligned with existing behavior tests.
5. Check whether current worktree changes are user work. Touch only files required by the request.

## Phase lifecycle and approval

No phase is complete until the developer explicitly approves it.

For each phase:

1. Branch from the latest `main`.
2. Create or update `docs/phases/phase-N.md` before implementation begins.
3. Implement only the phase deliverables.
4. Add or update `TESTING.md` with short, runnable verification instructions.
5. Run local checks and have an independent agent review or run relevant checks when swarm support is available.
6. Hand off changed files, exact commands/results, browser evidence or limitations, and known issues.
7. Wait for explicit developer approval; do not merge, push, or call the phase complete before approval.

### Branch naming

```text
feat/phase-N-<topic>
fix/phase-N-<topic>
bench/phase-N-<topic>
docs/phase-N-<topic>
test/phase-N-<topic>
```

### Fix lifecycle

Create fixes from the active phase branch as `fix/phase-N-<topic>`, test them, merge them back
into the phase branch only after review, and rerun the phase checks.

### Approval and merge

After explicit developer approval only:

```bash
git checkout main
git pull --ff-only origin main
git merge --no-ff <phase-branch>
git push origin main
git branch -d <phase-branch>
git push origin --delete <phase-branch>
```

Do not merge, push, commit, or rewrite history unless explicitly requested.

## Verification expectations

- Prefer `./test.sh` from the repository root; it selects `backend/.venv/bin/python` when available.
- Also run focused frontend tests, `npm run build`, backend tests relevant to the changed workflow,
  and `git diff --check` when applicable.
- A successful build is not visual proof. For UI changes, run the app with safe fixture data and
  inspect the operator route and `/qr/<token>` at 1440px, 1280px, 1024px, 768px, and 390px when possible.
- Check shell geometry, first-viewport hierarchy, semantic controls/focus, live status/error states,
  payment-action visibility, reduced-motion behavior, and horizontal overflow.
- Separate automated/mock evidence from live browser evidence. If a browser or external integration
  is unavailable, say so plainly rather than inferring success.
- Report exact commands and observed results; do not claim completion from source inspection alone.

## Commits and generated files

- Keep each commit focused on one coherent change and keep the phase document aligned with it.
- Do not commit generated caches, dependency directories, local databases, logs, secrets, or environment files.
- Before handoff, inspect `git status --short --untracked-files=all` and account for every changed path.
