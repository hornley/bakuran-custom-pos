# Testing

Run the current checks from the repository root:

```bash
./test.sh
```

`test.sh` runs backend pytest with `backend/.venv/bin/python` when it exists, then runs the frontend production build. No virtual-environment activation or directory change is required.

The backend pytest fixture creates a temporary SQLite database for each test. Never point tests at `backend/data/app.db`, and never run reset or mutation smoke tests against the main database.

For a read-only service check when the app is already running:

```bash
curl -fsS http://localhost:5300/api/health
```

Expected result includes `"status":"ok"` and `"database_ready":true`.

## Phase 2 ready / pickup queue

The active kitchen queue is the default:

```bash
curl -fsS http://localhost:5300/api/kitchen
```

The ready / pickup queue includes ready and served tickets until their orders are closed:

```bash
curl -fsS 'http://localhost:5300/api/kitchen?queue=ready'
```

Supported values for `queue` are `active` and `ready`; other values return HTTP 422.

## Current phase handoff

- Backend tests: pending final run
- Frontend build: pending final run
- Database: isolated temporary test databases
- Phase status: awaiting developer approval
