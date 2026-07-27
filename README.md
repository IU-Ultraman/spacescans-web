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
| Pipeline | installed from GitHub at build time (`IU-Ultraman/spacescans`, pinned tag) — nothing to do |
| Exposure data | put `data_full/` + `data/` (several GB) in `pipeline-data/` — see [pipeline-data/README.md](pipeline-data/README.md), or reuse an existing tree via `SPACESCANS_DATA_HOST` |

---

## 1. Pipeline (installed from GitHub)

`spacescans-pipeline` is not on PyPI, so the backend image `pip install`s it
straight from its public repo (`IU-Ultraman/spacescans`), pinned to a release
tag — nothing to do here.

**Maintainers only** — to ship a newer pipeline release, tag it on
`IU-Ultraman/spacescans` and bump `SPACESCANS_REF` in `backend/Dockerfile`
(default `v0.2.0`).

---

## 2. Data

Put the exposure data (`data_full/` + `data/`, several GB) in **`pipeline-data/`**
— see [pipeline-data/README.md](pipeline-data/README.md) for the exact layout
and per-dataset sources. Already have the data elsewhere? Skip copying and set
`SPACESCANS_DATA_HOST=/abs/path` in `.env`.

---

## 3. Configure

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

## 4. Run

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
| `./configs` → `/configs` | bind mount (ro) | C3/C4 config templates — **versioned in this repo** (`SPACESCANS_CONFIG_TEMPLATES_DIR=/configs`) |
| `pipeline-data/` → `/project` | bind mount | exposure data (`data_full/`, `data/`) — override host path with `SPACESCANS_DATA_HOST` (`SPACESCANS_DATA_DIR=/project`) |
| `backend-data` → `/app/data` | named volume | SQLite DB, `tasks/`, `c3_cache/` — survives restarts |

Image bases, the conda/pip channel split, and other architecture notes are in
[DOCKER.md](DOCKER.md).
