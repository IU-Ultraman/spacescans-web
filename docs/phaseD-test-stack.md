# Phase-D test stack (`tier2-d-test`)

A TEST copy of the web app, built from the same `backend/Dockerfile` and `frontend/` as production
(spacescans installed from GitHub at the Dockerfile's `SPACESCANS_REF`). It is **not** the live
app: the live compose project is `spacescans-web` on ports 3000/8000, and nothing here
touches it, its images or its volume.

| | Test stack |
|---|---|
| Compose file | `docs/phaseD-test-stack.yml` (standalone; never combine it with `docker-compose.yml`) |
| Project | `tier2-d-test` (containers `tier2-d-test-backend-1`, `tier2-d-test-frontend-1`) |
| Images | `tier2-d-backend:integration` (from `backend/Dockerfile`), `tier2-d-frontend:integration` |
| URLs | frontend <http://localhost:3100>, backend <http://localhost:8100> (bound to this machine only) |
| App state | volume `tier2-d-test_backend-data` (SQLite users, tasks, registered datasets, C3 cache) |
| Exposure data | `/Users/xai/Desktop/spacescans-all/spacescans-web/pipeline-data`, mounted **read-only** |
| Pipeline | spacescans-pipeline from GitHub at `backend/Dockerfile`'s `SPACESCANS_REF` |

Run every command below from the repository root (`spacescans-web-wt/d-integration`). Builds
and runs are heavy work: take the host lock
`/Users/xai/Desktop/spacescans-all/tier2-artifacts/.heavy.lock` (rule H4), for example by
prefixing a command with this helper:

```bash
heavy() { python3 -c 'import fcntl,subprocess,sys
with open("/Users/xai/Desktop/spacescans-all/tier2-artifacts/.heavy.lock","a+") as f:
    fcntl.flock(f, fcntl.LOCK_EX); sys.exit(subprocess.call(sys.argv[1:]))' "$@"; }
```

## Start it again

The images and the volume were kept, so a start needs no build:

```bash
heavy docker compose -p tier2-d-test -f docs/phaseD-test-stack.yml up -d --no-build
curl -s http://127.0.0.1:8100/api/health        # {"status":"ok"} once the backend is up
```

Open <http://localhost:3100>. The volume still holds the state the integration gate left:

- user **Ada Tester** (`ada.tester@example.com`) owns three datasets shared with the
  deployment (a daily tract table, a biweekly raster series of six GeoTIFFs and point
  features) and three private ones uploaded through the browser;
- user **Ben Tester** (`ben.tester@example.com`) has two finished tasks on a synthetic
  cohort (6 participants, 11 location episodes) that link NPS noise plus Ada's three shared
  datasets: "e2e participant level" (one row per participant) and "e2e episode level";
- user **Cy Tester** (`cy.tester@example.com`) has the two queue-probe tasks; the second
  shows as failed: the gate's probe of the serial queue caught the pre-existing race in
  which a queued task starts in the gap between another task's experiments.

All three use the password `Synthetic-Pass-1` (synthetic test accounts on this local
volume only). To re-capture Figure 3, sign in as Ben, or sign up a new user and upload your
own synthetic cohort; catalog variables whose data is in `pipeline-data` run as in the live
app.

Every start signs logins with a fresh random key, so a backend restart logs everyone out. To
keep logins across restarts, export a key of your own first (it is never written to a file):

```bash
export TIER2_TEST_SECRET_KEY=$(openssl rand -hex 32)
```

## Stop it

```bash
docker compose -p tier2-d-test -f docs/phaseD-test-stack.yml down       # keeps the volume
docker compose -p tier2-d-test -f docs/phaseD-test-stack.yml down -v    # also deletes the volume
```

Keep the images (`tier2-d-backend:integration`, `tier2-d-frontend:integration`) until the
lead no longer needs the stack; then `docker image rm` them.

## Rebuild

Only needed after a change on this branch, for example a new `SPACESCANS_REF`:

```bash
heavy docker compose -p tier2-d-test -f docs/phaseD-test-stack.yml build
```


The frontend bakes `NEXT_PUBLIC_API_URL=http://localhost:8100` in at build time; the backend
allows CORS from `http://localhost:3100` and `http://127.0.0.1:3100` only.

## What differs from production

- No `restart: unless-stopped`, ports bound to 127.0.0.1, the data root read-only, no
  RStudio service, a random per-start `SECRET_KEY`, CORS for port 3100.

## The integration gate (PHASE_D section 6)

`docs/phaseD-gate/` holds the gate that was run on this stack. It **resets the stack** (it
deletes the test volume first), so run it only when the current state is not needed:

```bash
heavy docs/phaseD-gate/run_gate.sh /path/to/a/work/dir
```

- `make_data.py` writes the synthetic inputs (generated once into `<work_dir>/data`, never
  committed): a cohort of 6 participants and 11 location episodes in Indiana and Illinois
  (zero-padded numeric ids, overlapping episodes, gaps, one episode before every dated
  period), a daily tract table with a missing-value window, a biweekly raster series of six
  GeoTIFFs with one nodata cell, point features and a private static table. It reads the
  2010 tract boundaries (read-only) to put each location where a 400 m circle stays inside
  one tract and one raster cell, so the reference is exact.
- `ref.py` recomputes every episode and participant value from those files with the
  PHASE_D 2.2 formula, independently of the app.
- `gate.py` drives the API with two users (Ada registers the shared daily table, raster
  series and features plus a private table; Ben links them with NPS noise at
  `output_level` participant and episode) and checks result.csv shapes and values against
  the reference, a hand computation for one participant, linkage rates, the results
  endpoints' `level`, access control, the delete and un-share rules, the frontend pages and
  bundle; a third user records how the serial queue behaves (an observation, not a check).
- `browse.mjs` walks the frontend in headless Chrome as both users, including uploads
  through the dataset dialog, and fails on any console error.
- `proj_network_probe.py` reproduces, inside the backend image, the PROJ network failure
  the gate found (see below).

Outputs land in `<work_dir>/out`: `checks.json`, the result CSVs, screenshots, container
logs and `facts.txt`. The results of the integration run are in
`tier2-artifacts/docs/phaseD/progress-I2.md`.

## Found by the gate: PROJ network grids

The image's conda-forge PROJ activation exports `PROJ_NETWORK=ON` (the grids package
`proj-data` is not installed), so coordinate transformations tried to download NOAA grids
from cdn.proj.org: an outbound request that depends on where the cohort's locations are.
In the API's worker threads the download failed and features were stored with infinite
coordinates. `backend/app/__init__.py` now sets `PROJ_NETWORK=OFF` for every web process
(production image too). The live app, built the same way, still has the network on until
this branch is deployed.
