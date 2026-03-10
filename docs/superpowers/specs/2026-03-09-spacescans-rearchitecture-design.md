# SPACESCANS Web App Rearchitecture — Design Spec

## Goal

Simplify the SPACESCANS web app by decoupling it from the Python linkage pipeline. The web app generates JSON configuration files; a separate CLI pipeline consumes them. Reduce infrastructure from 7 services to 2, drop PostgreSQL/Neo4j/Redis/Celery, and modernize the frontend.

## Architecture Overview

### Stack

- **Frontend:** Next.js 14 + TypeScript + Tailwind CSS + shadcn/ui
- **Backend:** FastAPI (Python) + SQLite (auth only)
- **Ontology:** Pre-processed static JSON files from OWL source
- **Task execution:** Backend spawns mock CLI as subprocess, file-based contract
- **Infrastructure:** No Docker required for dev. Just `npm run dev` + `uvicorn`

### Services: 7 → 2

**Removed:** PostgreSQL, Neo4j, Redis, Celery, Flower, NGINX, Docs server

**Kept (simplified):** Next.js frontend, FastAPI backend

### New Repository

The rearchitected app lives in a fresh GitHub repository, built from scratch with the new stack.

## Authentication

- SQLite (WAL mode for concurrent read/write) stores users: `id`, `email`, `hashed_password`, `first_name`, `last_name`, `is_active`, `created_at`
- JWT-based auth: tokens expire after 24 hours, no refresh tokens — user re-logs on expiry
- Tokens stored in localStorage, frontend redirects to `/login` on 401
- Password hashing with bcrypt
- No admin/superuser system
- No password reset or email verification in v1 (out of scope)
- Small team target (< 50 users)

### Task Access Control

Every `/api/tasks/{id}/*` endpoint verifies that `request.user_id == meta.json.user_id`. Returns 403 if the task belongs to a different user. Task UUIDs are random (uuid4), not sequential.

## Ontology & Data Catalog

### Build-time Processing

A Python script parses `SPACEO_20251203.owl` and outputs:

- `ontology/index.json` — top-level classes
- `ontology/nodes/{ClassName}.json` — children for each node (lazy loading)
- `ontology/search-index.json` — pre-built client-side search index
- `ontology/metadata.json` — variable metadata (description, data source, coverage, resolution)

### Frontend Catalog Features

- **Tree browser** (left panel) — lazy-loads children on expand via split JSON files
- **Search bar** (top) — client-side keyword search using pre-built index
- **Detail panel** (right) — shows metadata when a variable is selected
- **Breadcrumbs** — shows path in hierarchy

### Scalability

Split JSON per node means each file is tiny regardless of total ontology size. Only loads what the user browses. Can scale to 100k+ classes with no performance degradation.

## Task Lifecycle & File-Based Contract

### Task Directory Structure

```
backend/data/tasks/task-{uuid}/
├── meta.json        # backend-owned: task name, user_id, created_at, data summary
├── config.json      # backend-owned: CLI input (buffer, variables, execution options)
├── input.csv        # uploaded patient data
├── status.json      # CLI-owned: status, progress, message, pid (backend reads only)
├── logs.jsonl       # CLI-owned: append-only log lines (backend reads only)
└── output/
    └── result.csv   # CLI-owned: linkage results
```

**File ownership:** `meta.json` and `config.json` are written by the backend. `status.json`, `logs.jsonl`, and `output/` are written by the CLI. The backend reads but never writes CLI-owned files.

### config.json (Contract Between Web App and CLI)

```json
{
  "version": 1,
  "input_file": "input.csv",
  "buffer": {
    "shape": "circle",
    "size": 1000,
    "unit": "meters"
  },
  "variables": ["p_assault", "p_burglary", "walkability_index"],
  "execution": {
    "cpu_cores": 4,
    "memory_limit_gb": 8
  }
}
```

### status.json (Written by CLI)

```json
{
  "status": "running",
  "progress": 0.45,
  "message": "Linking patient 450/1000 to UCR data...",
  "started_at": "2026-03-09T10:30:00Z",
  "pid": 12345
}
```

### logs.jsonl (Appended by CLI)

```jsonl
{"ts": "2026-03-09T10:30:01Z", "level": "info", "msg": "Started linkage task"}
{"ts": "2026-03-09T10:30:05Z", "level": "info", "msg": "Processing batch 1/10..."}
{"ts": "2026-03-09T10:30:12Z", "level": "warn", "msg": "3 addresses failed geocoding"}
```

### Lifecycle

| Step | Action | Files |
|------|--------|-------|
| Create | Backend creates directory + `meta.json` | `meta.json` |
| Upload | Backend saves CSV, parses summary (row count, date range, columns) | `input.csv`, `meta.json` |
| Configure | User picks buffer + variables, backend writes config | `config.json` |
| Start | Backend spawns CLI subprocess | `status.json` (CLI writes PID) |
| Running | CLI writes progress to `status.json`, appends to `logs.jsonl` | `status.json`, `logs.jsonl` |
| Poll | Frontend polls status endpoint, backend reads `status.json` | read only |
| Stop | Backend sends SIGTERM to PID | `status.json` |
| Finish | CLI writes final status + result | `status.json`, `output/result.csv` |
| Error | CLI writes error to status | `status.json` |
| Download | Backend serves `output/result.csv` | read only |

### Input CSV Format

Patient data with columns:
- `patient_id`
- `longitude` / `latitude`
- `start_date` / `end_date` (time period for that address)

After upload, the web app parses and shows a data summary (row count, date range, columns). It checks variable data coverage: if the input CSV date range falls outside a selected variable's available date range (from `ontology/metadata.json`), a warning is shown (non-blocking — user can proceed but is informed).

### File Upload Validation

- Max upload size: 100MB
- Allowed types: `.csv` only (validated by extension and content sniffing)
- Required columns: `patient_id`, `longitude`, `latitude`, `start_date`, `end_date`
- Encoding: UTF-8
- Malformed CSVs return a 400 with a descriptive error message
- On upload, old `input.csv` in the task directory is replaced

### Task Configuration Fields

1. **Buffer shape** — circle or square (extensible to other shapes)
2. **Buffer size** — numeric value in meters
3. **Variable selection** — from ontology catalog
4. **Advanced options** (behind toggle) — CPU cores, memory limit

## Frontend Pages

### Public

- `/` — Landing page
- `/login` — Sign in
- `/signup` — Create account
- `/catalog` — Browse ontology (public)

### Protected (auth required)

- `/dashboard` — Task list with status badges, inline progress bars
- `/dashboard/task/new` — 4-step wizard: Upload Data → Buffer Settings → Variables → Review & Run
- `/dashboard/task/[id]` — Task detail with progress bar + live log panel + stop button
- `/dashboard/task/[id]/results` — View summary + download result CSV

### UI Patterns

- shadcn/ui components for consistent modern look
- Step-by-step task configuration wizard
- Data summary shown after upload
- Buffer shape visual preview
- Variable selection via ontology tree with search
- Dark terminal-style log panel for task progress
- Status badges: Not Started (gray), Running (blue + progress), Finished (green), Error (red), Cancelled (yellow)

## API Endpoints

### Auth

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/signup` | Create account |
| POST | `/api/auth/login` | Returns JWT token |

### Tasks

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/tasks` | List current user's tasks |
| POST | `/api/tasks` | Create new task |
| GET | `/api/tasks/{id}` | Get task metadata |
| DELETE | `/api/tasks/{id}` | Delete task and directory |
| POST | `/api/tasks/{id}/upload` | Upload input CSV, returns data summary |
| PUT | `/api/tasks/{id}/config` | Save config |
| POST | `/api/tasks/{id}/start` | Spawn CLI subprocess |
| POST | `/api/tasks/{id}/stop` | Send SIGTERM to process |
| GET | `/api/tasks/{id}/status` | Read status.json |
| GET | `/api/tasks/{id}/logs` | Read logs.jsonl (supports `?since=` for incremental) |
| GET | `/api/tasks/{id}/results` | Download result CSV |

### Ontology

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/ontology/roots` | Top-level classes |
| GET | `/api/ontology/children/{name}` | Children of a node |
| GET | `/api/ontology/search?q=` | Search pre-built index |
| GET | `/api/ontology/metadata/{name}` | Variable detail info |

## Mock CLI Pipeline

A Python script at `backend/mock_cli/cli.py` that:

- Accepts: `python -m mock_cli.cli run ./task-{uuid}/`
- Reads `config.json` and `input.csv`
- Simulates processing with sleep increments
- Writes progress to `status.json`, appends to `logs.jsonl`
- Generates fake `output/result.csv` (input columns + random values for selected variables)
- Supports SIGTERM for graceful cancellation
- Validates `config.json` schema (writes error to status if malformed)

## Multi-User & Concurrent Tasks

- Each task directory includes `user_id` in `meta.json`
- Users only see their own tasks (enforced by access control check on every endpoint)
- Each task runs as a separate subprocess — no shared state
- No concurrency limits for now (can be added later)

## Process Recovery

On backend startup, scan all task directories for `status.json` with `"status": "running"`:
- Check if PID is still alive (`os.kill(pid, 0)`)
- If PID is dead, update `status.json` to `{"status": "error", "message": "Process terminated unexpectedly"}`
- If PID is alive, leave it running (subprocess survived restart)

For stop requests: send SIGTERM, wait 10 seconds, then send SIGKILL if process is still alive.

On graceful CLI shutdown (SIGTERM received), CLI writes `{"status": "cancelled"}` to `status.json` before exiting. On crash, `status.json` retains `"running"` and the recovery scan handles it.

## Error Response Format

All API errors return:
```json
{
  "error": "Short error code",
  "detail": "Human-readable explanation"
}
```

HTTP status codes: 400 (bad request), 401 (not authenticated), 403 (forbidden), 404 (not found), 413 (file too large), 500 (server error).

## Operational Notes

- **CORS:** FastAPI CORSMiddleware configured to allow the Next.js dev server origin in development
- **Data durability:** Task data lives on the host filesystem. No backup strategy in v1 — acceptable for research prototype
- **Ontology delivery:** Frontend fetches static JSON files directly from Next.js `/public` directory (no backend proxy needed). The build script outputs to the frontend's public folder
- **SQLite WAL mode:** Enabled for concurrent read/write support at small scale

## Decisions Log

| Decision | Choice | Rationale |
|----------|--------|-----------|
| CLI communication | File-based contract | Zero runtime coupling, CLI testable standalone |
| CLI invocation | Subprocess on same machine | Simple, can scale to remote later |
| Database | SQLite for auth only | Small team, tasks are file-based |
| Ontology storage | Pre-processed static JSON | Drop Neo4j, lazy-load per node, client-side search |
| Frontend framework | Next.js + shadcn/ui + Tailwind | Modern, clean, single UI library |
| Task progress | Detailed log streaming | CLI writes status.json + logs.jsonl, frontend polls |
| Frontend approach | Keep pages & layout, modernize components | Familiar navigation, clean component layer |
| Concurrency limits | None for now | YAGNI, add later if needed |
