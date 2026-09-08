# Phase 3 — Operational Hardening

## Status

Implementation complete; developer approval is required before merge.

## Scope

- Reproducible documentation and validation.
- Backend lifecycle regression coverage.
- Focused frontend test coverage where maintainable.

## Acceptance criteria

- Historical phase documents accurately describe merged work.
- `TESTING.md` documents the current backend suite, frontend build, payment gate, ready/pickup queue, and safe health check.
- Backend regression tests cover ready/pickup visibility, invalid and duplicate payment/release state preservation, repeated/concurrent idempotency, full lifecycle receipt/close behavior, and invalid kitchen transitions.
- Frontend tests cover the highest-value UI/API behavior without expanding product scope.
- `./test.sh` and relevant focused checks pass using isolated test data.

## Verification

- Backend regression file: `5 passed`.
- Full backend suite: `17 passed` with 3 existing warnings.
- Frontend tests: `3 passed` in 1 Vitest file.
- Frontend production build: passed with TypeScript and Vite.
- Root `./test.sh`: passed using `backend/.venv` and the frontend dependencies.
- `git diff --check`: passed.
- Backend tests use the existing isolated temporary SQLite fixture; no operational database mutations were run.
- Frontend tests use mocked fetch responses; no live browser/E2E check was run.

## Approval gate

This phase is not complete until the developer explicitly approves it. Do not merge or push the phase branch before approval.
