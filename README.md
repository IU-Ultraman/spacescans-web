# spacescans-web

Web app for the SPACESCANS EHR ↔ environmental-exposure linkage pipeline.
Upload a patient cohort CSV, pick exposure variables, run the linkage
pipeline, and explore the results (preview table, per-column summary,
exposure histograms, and a US state choropleth).

- **Backend** — FastAPI (Python), serves `/api/*`, drives the
  `spacescans-pipeline` package via an editable install.
- **Frontend** — Next.js 14 (App Router, React 18, TypeScript, Tailwind).
- **Data** — SQLite for users/tasks; per-task working dirs on disk;
  the heavy exposure data lives in the `spacescans-pipeline` data tree.

---

## Architecture

```
spacescans-web/
├── backend/          FastAPI app (app.main:app)
│   ├── app/          routers, task_manager, dispatcher, experiments/, variable_registry
│   ├── data/         spacescans.db + tasks/<id>/ working dirs   (gitignored)
│   ├── .env          local config (gitignored — see below)
│   └── requirements.txt
└── frontend/         Next.js app
    └── src/app/dashboard/...   wizard + results pages
```

The backend shells out to the **`spacescans-pipeline`** package (a sibling
checkout, installed editable). The web layer never computes exposures
itself — it renders pipeline YAML configs, spawns the pipeline runner per
experiment, and merges the per-experiment outputs into `result.csv`.

---

## Prerequisites

| Tool | Version used | Notes |
|------|--------------|-------|
| Python | 3.12 (conda env `spacescans`) | same env that runs the pipeline |
| Node.js | 20.x (e.g. v20.20.2) | `nvm use 20` |
| spacescans-pipeline | ≥ 0.2 | editable-installed into the Python env |

The Python env must already have `spacescans-pipeline` importable
(`python -c "import spacescans"`). It is normally installed editable from
the sibling pipeline checkout:

```bash
pip install -e /path/to/spacescans-project   # the pipeline repo root
```

---

## Backend — setup & run

```bash
cd backend

# 1. install Python deps into the spacescans conda env
/path/to/conda/envs/spacescans/bin/python -m pip install -r requirements.txt

# 2. create backend/.env  (gitignored — copy the template below and edit)
cat > .env <<'EOF'
SPACESCANS_DATA_DIR=/path/to/spacescans-project
SPACESCANS_PIPELINE_PYTHON=/path/to/conda/envs/spacescans/bin/python
SPACESCANS_PIPELINE_CLI=/path/to/conda/envs/spacescans/bin/spacescans
SPACESCANS_CONFIG_TEMPLATES_DIR=/path/to/spacescans-project/configs
SECRET_KEY=change-me
EOF

# 3. run the API on :8000
/path/to/conda/envs/spacescans/bin/python -m uvicorn app.main:app --reload --port 8000
```

- The SQLite DB (`backend/data/spacescans.db`), `tasks/`, and `c3_cache/`
  dirs are created automatically on first startup.
- On startup the app also reconciles any task left in a `running` state by
  a previous process (orphan recovery).

### Config keys (`backend/.env`)

| Key | Meaning |
|-----|---------|
| `SPACESCANS_DATA_DIR` | pipeline project root; exposure data lives under `<dir>/data_full/` |
| `SPACESCANS_PIPELINE_PYTHON` | python interpreter the runner subprocess uses |
| `SPACESCANS_PIPELINE_CLI` | `spacescans` CLI entrypoint |
| `SPACESCANS_CONFIG_TEMPLATES_DIR` | pipeline `configs/` (C3/C4 YAML templates) |
| `SECRET_KEY` | JWT signing key — **set a real secret in production** |

Defaults for `DATA_DIR`, `DB_PATH`, `CORS_ORIGINS`, etc. live in
`backend/app/config.py`.

---

## Frontend — setup & run

```bash
cd frontend
nvm use 20            # or ensure node 20.x is on PATH
npm install
npm run dev           # serves http://localhost:3000
```

The frontend talks to the backend at `http://localhost:8000` by default.
Override with `NEXT_PUBLIC_API_URL` if the API runs elsewhere.

---

## First use

1. Backend on `:8000`, frontend on `:3000`, both running.
2. Open http://localhost:3000 → **Sign up** to create an account
   (first/last name, email, password).
3. **New Task** → upload a cohort CSV with columns
   `pid,startDate,endDate,longitude,latitude` (plus optional FIPS columns).
4. Pick variables → Review → Run.
5. When the task finishes, open **Results** for the preview table,
   column summary, exposure histograms, and the US state map.

---

## Tests

```bash
# backend (264 tests; integration tests are marker-gated + skipped without the data tree)
cd backend && /path/to/conda/envs/spacescans/bin/python -m pytest -q

# backend incl. end-to-end pipeline tests (needs SPACESCANS_DATA_DIR populated)
/path/to/conda/envs/spacescans/bin/python -m pytest -q -m integration

# frontend type-check
cd frontend && npx tsc --noEmit
```

---

## Troubleshooting

**“Cannot sign in” right after restarting the frontend.**
If a stale `npm run dev` is still holding port 3000, the new one binds 3001
(or 3002) and the browser origin no longer matches. CORS allows
`localhost:3000-3002` (see `backend/app/config.py`), but the cleanest fix is
to kill the stale dev server so the new one reclaims 3000:

```bash
lsof -nP -iTCP -sTCP:LISTEN | grep node   # find stray next-server PIDs
kill -9 <pid> ...                          # then re-run `npm run dev`
```

**`Cannot find module './vendor-chunks/....js'` (or other `.next` errors).**
The `.next` build cache is stale/corrupted — usually from running
`npm run build` while `npm run dev` is also running (they share `.next`).
Fix:

```bash
rm -rf frontend/.next && (cd frontend && npm run dev)
```

Don't run `npm run build` against the same checkout while a dev server is
live; use `npx tsc --noEmit` to type-check instead.

**`Module not found: Can't resolve 'recharts'` (or another dep).**
`node_modules` is out of sync with `package.json` (e.g. after pulling new
deps). Run `npm install` in `frontend/` and restart the dev server.

**Forgot your password.**
There is no password-reset UI yet. Reset directly in the dev DB:

```python
# from backend/ with the spacescans env
import sqlite3; from app.auth import hash_password
con = sqlite3.connect("data/spacescans.db")
con.execute("UPDATE users SET hashed_password=? WHERE email=?",
            (hash_password("new-password"), "you@example.com"))
con.commit()
```

**A task is stuck `running`.**
Deleting the task stops its runner subprocess and releases the run lock.
On the next backend startup, orphaned `running` tasks with dead PIDs are
auto-marked `error`.
