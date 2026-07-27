# Running spacescans-web with Docker

One `docker compose` command brings up both services:

- **Frontend** (Next.js) → `http://localhost:3000`
- **Backend** (FastAPI + pipeline) → `http://localhost:8000`

The same image set runs on macOS, Windows, and Linux — Docker runs a Linux
container regardless of host OS. There is nothing OS-specific to configure.

---

## Prerequisites

1. **Docker** (Docker Desktop on macOS/Windows, Docker Engine on Linux).
2. **The pipeline** — `spacescans-pipeline` is not on PyPI, so the backend image
   `pip install`s it straight from its public repo (`IU-Ultraman/spacescans`),
   pinned to a release tag. Nothing to do for a normal install. Maintainers
   only: tag a new release on that repo and bump `SPACESCANS_REF` in
   `backend/Dockerfile` (default `v0.2.0`).

3. **The exposure data** — put `data_full/` + `data/` (several GB) in
   `pipeline-data/` (see [pipeline-data/README.md](pipeline-data/README.md) for
   the layout + per-dataset sources). Already have the data elsewhere? Set
   `SPACESCANS_DATA_HOST=/abs/path` in `.env` to mount it without copying.

---

## Configure

```bash
cp .env.docker.example .env      # then edit SECRET_KEY
```

`.env` is read automatically by `docker compose`. Without it, defaults apply
(fine for local testing; set a real `SECRET_KEY` otherwise).

---

## Run

```bash
docker compose up --build
```

First build pulls the conda-forge geospatial stack (~1.5 GB) and can take a few
minutes. Subsequent runs are cached and fast.

Open `http://localhost:3000` and sign up to create an account.

Stop with `Ctrl-C`; tear down with `docker compose down` (add `-v` to also drop
the SQLite DB / tasks / cache volume).

---

## What's mounted / persisted

| Path | Kind | Purpose |
| --- | --- | --- |
| `./configs` → `/configs` | bind mount (ro) | C3/C4 config templates — versioned in this repo; `SPACESCANS_CONFIG_TEMPLATES_DIR=/configs` |
| `pipeline-data/` → `/project` | bind mount (host) | exposure data (`data_full/`, `data/`); override host path with `SPACESCANS_DATA_HOST`; `SPACESCANS_DATA_DIR=/project` |
| `backend-data` → `/app/data` | named volume | SQLite DB, `tasks/`, `c3_cache/` — survives restarts |

---

## Architecture notes

- **Backend image**: `mambaorg/micromamba` base. Channel split mirrors the
  tested `spacescans` env — the GDAL/C++ layer (`libgdal`, `rasterio`,
  `exactextract`) from **conda-forge**; everything else (geopandas, shapely,
  pyproj, pandas, duckdb, pyreadr) from **pip**, via the pipeline's `[geo,rda]`
  extras (installed from GitHub) + `requirements.txt`.
- **Frontend image**: `node:20-slim`, `next build` → `next start`.
  `NEXT_PUBLIC_API_URL` is inlined at build time (default `http://localhost:8000`).
- **Two ports** (3000 / 8000). To serve everything under one URL with HTTPS,
  add a reverse proxy (e.g. Caddy) in front — not included here.
- **Serial queue** is unchanged: the backend still runs one task at a time.
