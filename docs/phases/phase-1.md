# Phase 1: POS P0 and Development Governance

**Status:** Approved and merged into `main`
**Branch:** `docs/phase-1-governance`  
**Base:** latest `main`

## Purpose

Document the current Bakuran POS contract and establish the development rules for future phases.

## Deliverables

- `SPEC.md`: current POS behavior, workflows, API contracts, non-goals, and acceptance criteria.
- `AGENTS.md`: database safety, phase lifecycle, branching, commit, approval, and testing rules.
- `TESTING.md`: short commands for the current checks without manually activating a virtual environment.
- `test.sh`: root-level test/build entrypoint that uses an isolated pytest database fixture.

## Scope boundaries

- Counter-first POS workflow.
- Manual cash orders.
- Connected QR payment queue.
- Kitchen and pickup lifecycle.
- Sales receipt issuance.
- Inventory and purchasing remain deferred.
- No payment gateway.

## Verification

Coordinator checks:

```bash
./test.sh
```

Observed coordinator result: backend pytest passed `9 passed`, the frontend TypeScript/Vite production build passed, and the command exited successfully.

Independent agent checks:

- Backend isolation validator ran `./test.sh`, confirmed `backend/tests/conftest.py` uses `tmp_path / "app.db"`, and confirmed `backend/data/app.db` was untouched.
- Frontend/docs validator inspected `AGENTS.md`, `SPEC.md`, `TESTING.md`, this phase record, `frontend/src/App.tsx`, and `frontend/package.json`; `cd frontend && npm run build` passed and the docs aligned with the implemented flows.
- The agents reported only existing Starlette/httpx, anyio, and `app.seed` warnings.

The independent checks were run by separate swarm agents. Recursive spawning was unavailable in the light swarm, but no additional recursive reviewer was required for this phase.

## Historical approval record

The developer reviewed and explicitly approved this phase. It was merged into `main`; no phase-1 merge is pending.

## Handoff checklist

- [x] Developer reviewed `SPEC.md`.
- [x] Developer reviewed `AGENTS.md`.
- [x] Developer ran or reviewed `./test.sh`.
- [x] Developer approved the phase.
- [x] Approved branch merged into `main` with `--no-ff`.
