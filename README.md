# spacescans-web

Web app for the SPACESCANS EHR ↔ environmental-exposure linkage pipeline:
upload a patient cohort CSV, pick exposure variables, run the pipeline, and
explore the results.

- **Backend** — FastAPI (Python), serves `/api/*`, drives the
  `spacescans-pipeline` package.
- **Frontend** — Next.js 14 (App Router, React 18, TypeScript, Tailwind).

> Install via **Docker** (one command).

The same setup runs on macOS, Windows, and Linux — the containers run Linux
regardless of host OS, so there is nothing OS-specific to configure.

---

## Prerequisites

| Requirement | Notes |
| ----------- | ----- |
| Docker | Docker Desktop (macOS/Windows) or Docker Engine (Linux) |
| Pipeline wheel | `spacescans-pipeline` is not on PyPI — supply a built wheel (step 1) |
| Exposure data | `data/` and `data_full/` (several GB) in the parent repo root — bind-mounted, not baked into the image |

---

## 1. Supply the pipeline wheel

The backend image installs the pipeline from a locally-built wheel. Copy it into
`backend/wheels/` (redo whenever the pipeline version bumps):

```bash
# from the spacescans-web/ directory
mkdir -p backend/wheels
cp ../dist/spacescans_pipeline-*.whl backend/wheels/
```

Rebuild the wheel first if the pipeline source changed:
`python -m build --wheel /path/to/spacescans-project` (writes to `dist/`).

---

## 2. Configure

```bash
cp .env.docker.example .env      # then edit SECRET_KEY
```

`docker compose` reads `.env` automatically. Without it, defaults apply (fine
for local testing; set a real secret otherwise).

| Key | Meaning |
| --- | ------- |
| `SECRET_KEY` | JWT signing key — set a real random value for anything beyond local testing |
| `NEXT_PUBLIC_API_URL` | origin the browser uses to reach the backend (default `http://localhost:8000`), inlined into the frontend at build time |

---

## 3. Run

```bash
docker compose up --build
```

- **Frontend** → `http://localhost:3000`
- **Backend** → `http://localhost:8000`

The first build pulls the conda-forge geospatial stack (~1.5 GB) and takes a few
minutes; later runs are cached and fast. Open the frontend and **sign up** to
create an account.

```bash
docker compose down        # stop + remove containers (keeps the data volume)
docker compose down -v     # also drop the SQLite DB / tasks / cache volume
docker compose logs -f backend
```

---

## What's mounted / persisted

| Path | Kind | Purpose |
| --- | --- | --- |
| `../` → `/project` | bind mount | `data/`, `data_full/`, `configs/`, `output/` — pipeline inputs (`SPACESCANS_DATA_DIR=/project`) |
| `backend-data` → `/app/data` | named volume | SQLite DB, `tasks/`, `c3_cache/` — survives restarts |

Image bases, the conda/pip channel split, and other architecture notes are in
[DOCKER.md](DOCKER.md).
