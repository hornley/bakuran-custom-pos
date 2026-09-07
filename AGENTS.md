# Agent and Development Instructions

These instructions apply to all work in this repository.

## 1. Database safety

- Never test against the main operational database at `backend/data/app.db`.
- Automated tests must use an isolated temporary database.
- The existing backend test fixture overrides `app.db.DATABASE_PATH` with a `tmp_path` database before initializing the schema.
- Do not run reset, seed, payment, order, kitchen, or close mutations against the main database as part of testing.
- If a new integration test needs a database, create it under a temporary directory or use the existing pytest fixture.

## 2. Phase lifecycle

No phase is complete until the developer explicitly approves it.

For each phase:

1. Branch from the latest `main`.
2. Create or update `docs/phases/phase-N.md` before implementation begins.
3. Implement only the phase deliverables.
4. Add or update `TESTING.md` with short, runnable verification instructions.
5. Run the tests locally and have independent agents review or run the relevant checks when the swarm is available.
6. Hand the phase to the developer with the changed files, checks run, results, and known limitations.
7. Wait for explicit developer approval. Do not merge or call the phase complete before approval.

### Branch naming

Use the phase number and a short topic:

```text
feat/phase-N-<topic>
fix/phase-N-<topic>
bench/phase-N-<topic>
docs/phase-N-<topic>
test/phase-N-<topic>
```

### Fix lifecycle

- Create fixes from the active phase branch as `fix/phase-N-<topic>`.
- Test the fix and merge it back into the phase branch.
- Re-run the phase checks after the fix.

### Approval and merge

After the developer approves the phase:

```bash
git checkout main
git pull --ff-only origin main
git merge --no-ff <phase-branch>
git push origin main
git branch -d <phase-branch>
git push origin --delete <phase-branch>
```

Do not perform the merge before approval.

## 3. Commits

- Make each commit concise and focused.
- A commit should describe one coherent change, for example `docs: add phase testing instructions`.
- Keep the relevant phase document aligned with the commit. Do not create a separate phase document for every small edit, but ensure the phase record is created or updated as part of the phase's commits.
- Do not commit generated caches, dependency directories, local databases, logs, secrets, or environment files.

## 4. Testing expectations

- The coordinator must run the relevant checks.
- When swarm support is available, at least one independent agent must run or review the relevant checks too.
- Report exact commands and observed results in the handoff.
- Prefer `./test.sh` from the repository root. It selects `backend/.venv/bin/python` automatically when available and does not require manually activating a virtual environment.
- Do not describe source inspection as a substitute for an end-user check. If a browser or external integration is unavailable, record that limitation explicitly.

## 5. Scope discipline

- Inventory and purchasing are deferred from the focused POS workflow.
- There is no payment gateway in the current scope.
- Manual counter orders do not require a table number.
- QR orders are selected from the connected unpaid payment queue.
- Preserve the payment gate: unpaid orders must not enter the kitchen.
