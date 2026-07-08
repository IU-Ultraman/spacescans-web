# spacescans-web

Web app for the SPACESCANS EHR ↔ environmental-exposure linkage pipeline:
upload a patient cohort CSV, pick exposure variables, run the pipeline, and
explore the results.

- **Backend** — FastAPI (Python), serves `/api/*`, drives the
  `spacescans-pipeline` package via an editable install.
- **Frontend** — Next.js 14 (App Router, React 18, TypeScript, Tailwind).

> This README covers **installation only**.

---

## Prerequisites

| Tool | Version | Notes |
| ---- | ------- | ----- |
| Python | 3.12 | the same interpreter that runs the pipeline; a conda env named `spacescans` is the tested setup |
| Node.js | 20.x (e.g. 20.20.2) | `nvm use 20` |
| spacescans-pipeline | ≥ 0.2 | a local checkout of the pipeline repo (this repo's parent), installed editable — see step 1 |

Paths below are placeholders — substitute your own:

- `/path/to/spacescans-project` — the pipeline repo root (contains `pyproject.toml`, `configs/`, `data_full/`).
- `/path/to/conda/envs/spacescans/bin/python` — the Python interpreter for the `spacescans` env.

---

## 1. Install the pipeline package (editable)

The backend imports `spacescans`, so the Python env must have the pipeline
installed:

```bash
/path/to/conda/envs/spacescans/bin/python -m pip install -e /path/to/spacescans-project
/path/to/conda/envs/spacescans/bin/python -c "import spacescans; print('pipeline OK')"
```

---

## 2. Backend

```bash
cd backend

# install the API dependencies into the same env
/path/to/conda/envs/spacescans/bin/python -m pip install -r requirements.txt

# create backend/.env (gitignored)
cat > .env <<'EOF'
SPACESCANS_DATA_DIR=/path/to/spacescans-project
SPACESCANS_PIPELINE_PYTHON=/path/to/conda/envs/spacescans/bin/python
SPACESCANS_PIPELINE_CLI=/path/to/conda/envs/spacescans/bin/spacescans
SPACESCANS_CONFIG_TEMPLATES_DIR=/path/to/spacescans-project/configs
SECRET_KEY=change-me
EOF
```

`.env` keys:

| Key | Meaning |
| --- | ------- |
| `SPACESCANS_DATA_DIR` | pipeline project root; exposure data lives under `<dir>/data_full/` |
| `SPACESCANS_PIPELINE_PYTHON` | interpreter the runner subprocess uses |
| `SPACESCANS_PIPELINE_CLI` | the `spacescans` CLI entrypoint |
| `SPACESCANS_CONFIG_TEMPLATES_DIR` | pipeline `configs/` (C3/C4 YAML templates) |
| `SECRET_KEY` | JWT signing key — **set a real secret in production** |

The SQLite DB (`backend/data/spacescans.db`), `tasks/`, and `c3_cache/`
directories are created automatically on first startup. Other defaults
(`DB_PATH`, `CORS_ORIGINS`, …) live in `backend/app/config.py`.

---

## 3. Frontend

```bash
cd frontend
nvm use 20        # or ensure Node 20.x is on PATH
npm install
```

---

## Run

Start the two processes (separate terminals):

```bash
# backend → http://localhost:8000
cd backend
/path/to/conda/envs/spacescans/bin/python -m uvicorn app.main:app --reload --port 8000

# frontend → http://localhost:3000
cd frontend
npm run dev
```

Open <http://localhost:3000> and sign up to create an account. The frontend
talks to the API at `http://localhost:8000` by default — override with
`NEXT_PUBLIC_API_URL` if the backend runs elsewhere.
