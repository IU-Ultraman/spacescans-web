# Phase D cutover (2026-10-19): participant-level output, registered datasets

Done on 2026-10-19 by the project lead on the author's go-ahead ("推送、发布和切换 … 开始吧").
It moved the live app from web bcebc8f + spacescans d92f7a3 to web 4d2a636 + spacescans
fff65b7 (0.3.0): participant-level output by default, registered and shared datasets with
feature uploads, and the review fixes (uploads refused when their content is a GDAL VRT,
upload size capped during receipt, custom-raster weights independent of the first file's
nodata).

What changes on the volume: at startup the backend writes a `dataset.json` record next to
every earlier upload (private, owned by its user); nothing is moved or deleted, and the old
image ignores the extra file. New tasks default to participant level; earlier tasks keep
their episode-level results. Catalog C3 cache keys are unchanged; custom-raster weights get a
new tag (`CUSTOMGRIDND_`), so earlier custom-raster entries are recomputed once.

Order used: the package `main` pushed (fff65b7, CI green: test, test extras, R CMD check);
the candidate images built from a `git archive` of the web commit (the same context as
`docker compose build`); a rehearsal on a COPY of the live volume (port 8200, data root
read-only); then the live switch: running images tagged for rollback, no task running or
queued, the web `main` fast-forwarded (so `configs/` matches the new package before the
backend starts), the candidates tagged `latest`, `docker compose up -d backend` and then
`frontend`, the smoke checks, and `git push origin main`.

## Rollback

Both previous images are tagged: `spacescans-web-backend:pre-phaseD-d92f7a3` (image 4722a449b631)
and `spacescans-web-frontend:pre-phaseD-bcebc8f` (image 7c2a62a7da26).

```bash
cd spacescans-web
git checkout bcebc8f -- configs          # the templates the old package checks at startup
docker tag spacescans-web-backend:pre-phaseD-d92f7a3 spacescans-web-backend:latest
docker tag spacescans-web-frontend:pre-phaseD-bcebc8f spacescans-web-frontend:latest
docker compose up -d backend frontend
```

then revert the web commits after bcebc8f (or reset a local branch) so that the next
`docker compose build` does not bring phase D back. Tasks and datasets created after the
cutover stay on the volume; the old app does not list registered datasets created through
`/api/datasets` (32-hex folders) and cannot open participant-level results.

## What was checked

Images now running: backend `bbd1a4339849` (spacescans fff65b7, 0.3.0; pandas 3.0.5, pyarrow
26.0.0; every pin of `backend/constraints.txt` matched; PID 1 `docker-init`), frontend
`245b36eac960` (`NEXT_PUBLIC_API_URL` from `.env`). Backend recreated 15:19:25 EDT and frontend
15:20:39 EDT on 2026-10-19, with no task running or queued.

Rehearsal on a copy of the live volume (1.1 GB, 174 task folders, 7 users), the candidate
backend on port 8200 with the data root read-only; the copy was deleted afterwards:

- all 26 finished tasks readable, all at episode level; the results, preview and map
  endpoints answer for the earlier tasks of the throwaway account `paper-figures`;
- 5 earlier uploads got their `dataset.json` at startup; the 2 under `user-999` and
  `user-9998` belong to no user in the database and stay invisible; `paper-figures` sees
  its upload, private and ready;
- noise + walkability on the 10k cohort of an earlier smoke task, at episode level: both C3
  steps hit the existing cache entries (`3b628c95__BG__b270m__r25m`,
  `3b628c95__BG_NOISE__b270m`) and every value equals the earlier task's (max |diff| 0,
  10,002 rows);
- the same cohort at participant level with the earlier upload: 5,055 rows for 5,055
  participants, cache hits as above, noise equal to the day-weighted mean of the episode
  values (2.1e-14);
- an upload whose content is a GDAL VRT named `.tif`: 400.

Live smoke (as `paper-figures`): the earlier upload listed; the 5 earlier finished tasks'
results, preview and map endpoints answer; noise on the 300-episode cohort of
`cutover-smoke-new-182742` at participant level finished in 9 s with 154 rows for 154
participants. The task stays in that account. The frontend answers on `/` and `/login`.

## Release upgrade (2026-10-23): spacescans 0.3.0 from the release tag

On the author's go-ahead ("升级到正式发布版") the live app moved from spacescans fff65b7 to the
released 0.3.0 (tag v0.3.0, commit 374d7c6, also on PyPI as `spacescans`). Between the two
the package gained the duckdb < 2 cap and the pandas 3.1 FileNotFoundError fix, the 7
remaining mirror files became `available` in its data manifest, and the distribution was
renamed from `spacescans-pipeline` to `spacescans`; its config templates did not change.
Web commit 1dd8e77 follows the rename (Dockerfile install spec and requirements filter,
requirements.txt, tests, messages).

Checked before the switch: the web backend suite with the PyPI wheel installed (623 passed,
the known health-probe failure that needs real paths, 2 skips); the candidate image
`spacescans-web-backend:rel-1dd8e77` (8cc6a96c3c37) reports dist-info
`spacescans-0.3.0.dist-info` at commit 374d7c6, no `spacescans_pipeline` dist-info, and every
`constraints.txt` pin; in an isolated container (empty volume, data read-only) a
participant-level noise task on the committed synth_1k cohort finished in 9 s with 510 rows
for 510 participants.

Switched at 15:21 EDT with no task running or queued: backend 8cc6a96c3c37, frontend
`spacescans-web-frontend:rel-1dd8e77` (f7f4e64ac662). Live smoke as `paper-figures`: the
earlier upload listed, the 6 earlier finished tasks' results, preview and map endpoints
answer, noise on the 300-episode cohort at participant level finished in 6 s with 154 rows
for 154 participants.

The image check of step 7 now looks for `spacescans-*.dist-info` (not
`spacescans_pipeline-*`). Rollback to the phase-D images (spacescans fff65b7):

```bash
docker tag spacescans-web-backend:phaseD-4d2a636 spacescans-web-backend:latest
docker tag spacescans-web-frontend:phaseD-4d2a636 spacescans-web-frontend:latest
docker compose up -d backend frontend
```

then revert 1dd8e77 so that the next build does not bring 0.3.0 back.

## Release upgrade (2026-10-25): spacescans 0.3.1 with worker processes

On the author's go-ahead ("线上 web 升级到 0.3.1，默认 4 个 worker") the live app moved from
spacescans 0.3.0 (374d7c6) to 0.3.1 (tag v0.3.1, commit 3010689, on PyPI). 0.3.1 adds
`engine.workers`: the polygon-overlap weights (block groups, tracts, ZCTAs, counties) and the
ACAG NetCDF files are computed by that many worker processes, with the same Step 1 output as
one process. Web commit b5f527b passes `SPACESCANS_PIPELINE_WORKERS` (compose default 4) into
the run context when the package has the `workers` flag. Commit 5021bd0 moves
`SPACESCANS_REF` to 3010689.

Checked before the switch:
- The web backend suite: 630 passed, plus the known health-probe failure. This was run once
  with PyPI 0.3.0 and once with the 0.3.1 branch installed. A runner test asserts that every
  rendered config carries `engine.workers` 4 with 0.3.1 and none with 0.3.0.
- The candidate image `spacescans-web-backend:rel-5021bd0` (743a041205a2) reports
  `spacescans-0.3.1.dist-info` at commit 3010689, the `workers` flag, and all 49
  `constraints.txt` pins.
- Isolated containers: an empty volume, the data mounted read-only, `--oom-score-adj 500`,
  `SPACESCANS_PIPELINE_WORKERS=4`.
  - Walkability on synth_1k at participant level finished in 18 s with 510 rows for 510
    participants. Both configs carried `workers: 4`, and Step 1 logged "569 tiles with work
    in 32 chunks on 4 worker processes".
  - ACAG on synth_100k at episode level finished in 1,232 s. The paper's single-process run
    in this environment took 2,229 s. The ACAG run peaked at 19.3 GiB summed over processes
    (21.9 GiB cgroup `memory.peak`, page cache included) of 23.4 GiB, with no OOM kill. It
    wrote 99,549 result rows, the same count as the paper's 100k run
    (`paper-RT-100k-acag-r1`): episodes without any ACAG cell have no row in either.

Switched at 19:39 EDT, with no task running or queued: backend 743a041205a2; the frontend is
unchanged (f7f4e64ac662, also tagged `rel-5021bd0`). After the switch:
- `/api/health` answers ok; the container has `SPACESCANS_PIPELINE_WORKERS=4` and spacescans
  0.3.1.
- A walkability task on synth_1k in the live container (participant level, task
  `paper-relcheck-wi-1k`, removed afterwards) finished in 16.9 s with 510 rows, `workers: 4`
  in both configs, and four workers in Step 1.

Fewer workers without a rollback: set `SPACESCANS_PIPELINE_WORKERS=1` (or 2) in `.env`, then
`docker compose up -d backend`. Rollback to 0.3.0 (the env variable is then ignored):

```bash
docker tag spacescans-web-backend:rel-1dd8e77 spacescans-web-backend:latest
docker compose up -d backend
```

then revert 5021bd0 so that the next build does not bring 0.3.1 back.

## Release upgrade (2026-10-26): spacescans 0.3.2, workers for every Step 1

On the author's go-ahead (2026-10-26, to "upgrade the live web to 0.3.2") the live app moved
from spacescans 0.3.1 (3010689) to 0.3.2 (tag v0.3.2, commit 7827bdc, on PyPI). 0.3.2 runs the
spatial computation (Step 1) of every catalog source in `SPACESCANS_PIPELINE_WORKERS` worker
processes (4 here): the grid weights of noise, VIIRS, TEMIS, ACAG and custom grids, the NHD
and TIGER searches, and, as in 0.3.1, the polygon overlap. ACAG's NetCDF files are decoded in
workers as before, and TEMIS's daily HDF4 files when no converted copy covers the request. The
Step 1 output is the same as with one process. Web commit f80404d moves `SPACESCANS_REF` to
7827bdc and updates the comments and DOCKER.md; the runner code is unchanged.

Checked before the switch:
- The web backend suite with the 0.3.2 wheel: 630 passed, plus the known health-probe failure.
- The candidate image `spacescans-web-backend:rel-f80404d` (27c927f68e6b) reports spacescans
  0.3.2 installed from commit 7827bdc, the `workers` flag, and all 49 `constraints.txt` pins.
- An isolated container: an empty volume, the data mounted read-only, `--init`,
  `--oom-score-adj 500`, `SPACESCANS_PIPELINE_WORKERS=4`. Every run ended with exit code 0 and
  no OOM kill, every config carried `workers: 4`, and each Step 1 logged its worker processes.
  The paper's single-process runs in this environment are the comparison (Table 2, and
  Supplementary Table S1 for 10k):

  | Run | Time (s) | Paper, one process (s) | Rows | Peak, summed over processes (GiB) |
  |---|---|---|---|---|
  | Walkability, synth_1k, participant level | 18.8 | — | 510 | 6.4 |
  | Noise, synth_100k, episode level | 32.4 | 84.9 | 100,000 | 4.2 |
  | VIIRS, synth_100k, episode level | 42.1 | 96.6 | 100,000 | 8.1 |
  | NHD, synth_100k, episode level | 161.3 | 387.2 | 100,000 | 3.4 |
  | TIGER, synth_100k, episode level | 164.5 | 406.5 | 100,000 | 6.9 |
  | TEMIS, synth_10k, episode level | 36.6 | 34.6 | 10,002 | 9.5 |

  Walkability took 18 s in the same check of 0.3.1. The row counts equal those of the paper's
  runs (`paper-RT-100k-<key>-r1`, `paper-RT-10k-temis-r3`). TEMIS took about as long as with one
  process: 27.4 of its 34.6 s are Step 2, which reads the converted parquet in one process. The
  cgroup's `memory.peak` reached 21.4 GiB of 23.4 GiB over the six runs, page cache included.

Switched at 07:53 EDT, with no task running or queued: backend 27c927f68e6b; the frontend is
unchanged (f7f4e64ac662, also tagged `rel-f80404d`). After the switch:
- `/api/health` answers ok; the container has `SPACESCANS_PIPELINE_WORKERS=4` and spacescans
  0.3.2.
- Tasks in the live container, with four workers, exit code 0 and no OOM kill:
  - walkability on synth_1k at participant level (task `paper-relcheck-wi-1k`): 510 rows in
    2.1 s, its Step 1 weights served from the cache;
  - noise on a copy of synth_10k whose participant ids carry a new prefix, so the cache could
    not serve it (task `paper-relcheck-noise-10k`): 10,002 rows in 14.8 s, `workers: 4` in both
    configs, and Step 1 logged "3 chunks on 4 worker processes".

  The two task folders, three files under `/tmp` and the cache entry
  `3709a9e4__BG_NOISE__b270m` (parquet and meta.json) from these checks are still in the live
  container; they hold synthetic data only.

Fewer workers without a rollback: set `SPACESCANS_PIPELINE_WORKERS=1` (or 2) in `.env`, then
`docker compose up -d backend`. Rollback to 0.3.1:

```bash
docker tag spacescans-web-backend:rel-5021bd0 spacescans-web-backend:latest
docker compose up -d backend
```

then revert f80404d so that the next build does not bring 0.3.2 back.

## Release upgrade (2026-10-27): spacescans 0.3.3, the bridge interrupt fix

On the author's go-ahead ("把 web 升到 0.3.3") the live app moved from spacescans 0.3.2
(7827bdc) to 0.3.3 (tag v0.3.3, commit e8f99b6, on PyPI). 0.3.3 only changes how the Python
bridge, which the R package talks to, handles SIGINT/SIGTERM on Python 3.13 and later; the web
does not use the bridge, so the runners and every config are unchanged. Web commit 9bd76aa
moves `SPACESCANS_REF` to e8f99b6 and DOCKER.md's example.

Checked before the switch:
- The candidate image `spacescans-web-backend:rel-9bd76aa` (39c559abbda7) reports spacescans
  0.3.3 installed from commit e8f99b6, the `workers` flag, and all 49 `constraints.txt` pins.
- The web backend suite, run inside the candidate image with the compose mounts (`/configs`,
  the data read-only at `/project`): 617 passed in the image's own `/app`, and the five
  repository-layout tests (`test_data_sources_generated`, `test_install_posture`,
  `test_variable_registry`) pass with the repository mounted; 7 skipped. The health-probe test
  passes with the mounts.
- An isolated container (empty volume, data read-only, `--init`, `--oom-score-adj 500`, no
  network, `SPACESCANS_PIPELINE_WORKERS=4`), driven by the paper's `runtime.py`: noise on
  synth_1k, cold 8.0 s and cached 5.0 s, and walkability on synth_1k, cold 20.5 s (Step 1
  18.5 s on four workers) and cached 1.8 s; every run exit code 0, 1,001 rows, `workers: 4`
  in every config, the cached runs served from the cache.

Switched at 10:25 EDT, with no task running or queued (the task folders' `status.json`:
28 finished, 2 partial, 1 cancelled, none running): backend 39c559abbda7; the frontend is
unchanged (f7f4e64ac662, also tagged `rel-9bd76aa`). After the switch:
- `/api/health` answers ok; PID 1 is `docker-init`; the container has
  `SPACESCANS_PIPELINE_WORKERS=4` and spacescans 0.3.3 with the `workers` flag.
- Noise on synth_1k in the live container (task `paper-RT-1k-noise-r1-w4`, four workers):
  cold 8.5 s, cached 5.0 s, exit code 0, 1,001 rows.

Residue of the checks, synthetic data only, which the lead's tooling may not delete (its
`rm` in the live container is blocked): the task folders `paper-RT-1k-noise-r1-w4`,
`paper-relcheck-wi-1k` and `paper-relcheck-noise-10k` under `/app/data/tasks`, the cache entries
`33eebe32__BG_NOISE__b270m` and `3709a9e4__BG_NOISE__b270m` (parquet and meta.json) under
`/app/data/c3_cache`, and `/tmp/ss_relcheck*` from 2026-10-26. One command removes them:

```bash
docker exec spacescans-web-backend-1 rm -rf /app/data/tasks/paper-RT-1k-noise-r1-w4 \
  /app/data/tasks/paper-relcheck-wi-1k /app/data/tasks/paper-relcheck-noise-10k \
  /app/data/c3_cache/33eebe32__BG_NOISE__b270m.parquet /app/data/c3_cache/33eebe32__BG_NOISE__b270m.meta.json \
  /app/data/c3_cache/3709a9e4__BG_NOISE__b270m.parquet /app/data/c3_cache/3709a9e4__BG_NOISE__b270m.meta.json \
  /tmp/ss_relcheck.py /tmp/ss_relcheck_synth_1k.csv /tmp/ss_relcheck_synth_10k.csv
```

Rollback to 0.3.2:

```bash
docker tag spacescans-web-backend:rel-f80404d spacescans-web-backend:latest
docker compose up -d backend
```

then revert 9bd76aa so that the next build does not bring 0.3.3 back.
