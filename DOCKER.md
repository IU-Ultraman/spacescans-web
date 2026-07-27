# Running spacescans-web with Docker

One `docker compose` command brings up both services:

- **Frontend** (Next.js) → `http://localhost:3000`
- **Backend** (FastAPI + pipeline) → `http://localhost:8000`

The same image set runs on macOS, Windows, and Linux — Docker runs a Linux
container regardless of host OS. There is nothing OS-specific to configure.

---

## Prerequisites

1. **Docker** (Docker Desktop on macOS/Windows, Docker Engine on Linux).
2. **The pipeline wheel** — `spacescans-pipeline` is not on PyPI, so the backend
   image installs it from a wheel **committed to this repo** at
   `backend/wheels/*.whl`. Nothing to do for a normal install. Maintainers only,
   after changing the pipeline, rebuild + replace + commit the wheel:

   ```bash
   # in the pipeline repo (spacescans-project)
   python -m build --wheel                       # -> dist/spacescans_pipeline-*.whl
   cp dist/spacescans_pipeline-*.whl <spacescans-web>/backend/wheels/
   ```

3. **The exposure data** — `data/` and `data_full/` (several GB) must exist in
   the parent repo root. They are bind-mounted into the container, not baked
   into the image.

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
| `../` → `/project` | bind mount (host) | `data/`, `data_full/`, `output/` — exposure data from the parent repo; `SPACESCANS_DATA_DIR=/project` |
| `backend-data` → `/app/data` | named volume | SQLite DB, `tasks/`, `c3_cache/` — survives restarts |

---

## Architecture notes

- **Backend image**: `mambaorg/micromamba` base. Channel split mirrors the
  tested `spacescans` env — the GDAL/C++ layer (`libgdal`, `rasterio`,
  `exactextract`) from **conda-forge**; everything else (geopandas, shapely,
  pyproj, pandas, duckdb, pyreadr) from **pip**, via the pipeline wheel's
  `[geo,rda]` extras + `requirements.txt`.
- **Frontend image**: `node:20-slim`, `next build` → `next start`.
  `NEXT_PUBLIC_API_URL` is inlined at build time (default `http://localhost:8000`).
- **Two ports** (3000 / 8000). To serve everything under one URL with HTTPS,
  add a reverse proxy (e.g. Caddy) in front — not included here.
- **Serial queue** is unchanged: the backend still runs one task at a time.
