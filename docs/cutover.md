# Cutover: the backend on the shared spacescans implementation (tier 2, W4)

This switches the running backend from web 3991c3b + pipeline v0.2.7 to the branch
`tier2/web-integration`: the 11 runners become thin shims over `spacescans.orchestrate`, the
variable catalog, merge, custom-exposome checks, data downloads and config templates come from
the `spacescans` package, and the backend runs under an init process (`init: true`). The R
package uses the same Python code, so after this there is one implementation.

Nothing here has been done for you: no agent pushed, tagged, built the live image or restarted
a container. Run the steps in order from `/Users/xai/Desktop/spacescans-all`. They take about
15 minutes, most of it waiting for the package's GitHub CI.

## Before you start

- **Restarting the backend interrupts any running task.** At startup the backend marks a task
  still recorded as `running` as `error` ("Process terminated unexpectedly"). Its user has to
  start it again. Queued tasks are kept and start once the backend is back. Step 5 checks
  that nothing is running, right before the restart.
- **No cache clearing is needed.** The new code reads and writes the C3 weight cache
  (`/app/data/c3_cache` in the `spacescans-web_backend-data` volume) under the same keys,
  with the same `.meta.json` files, as 0.2.7:
  - Every key and meta equals the 0.2.7 one: the 14 golden keys, and every run of the
    13 golden configurations in the frozen image.
  - Given a cache seeded with entries 0.2.7 wrote, the new code served every C3 step from
    it and rewrote nothing.
  - The weights come from the same computation code: the C3 tables of all 13 runs are
    byte-identical in the same image.
  - `pandas==3.0.5` and `pyarrow==26.0.0` are pinned. The key includes a hash of
    `input.parquet`, and pandas writes its own version into that file.
  - One deliberate difference: an entry is used only if its `.meta.json` records the full
    hash of the task's `input.parquet` (`sha_full`). The key holds only its first 8 hex
    digits, so two cohorts can share a key; 0.2.7 then served one cohort's weights to the
    other. An entry whose meta is missing, unreadable or has no `sha_full` is recomputed
    once and rewritten. Every entry 0.2.7 writes has one, and so did all six entries of the
    live cache when checked on 2026-10-14.

  The 0.2.7 upgrade had to delete 520 cache files because the weights themselves changed.
  Nothing like that happens here. The cache also stays valid if you roll back to the old
  image; a rebuild of the old code may not keep it (see Rollback).
- **`configs/` is checked at startup.** With `SPACESCANS_CONFIG_TEMPLATES_DIR=/configs` (as in
  `docker-compose.yml`), the backend refuses to start unless every template packaged in
  `spacescans` has a byte-identical file in `./configs`. The repo's `configs/` matches; a local
  edit there would stop the backend.
- **The build needs network access** to GitHub (pip installs the package from
  `IU-Ultraman/spacescans` at `SPACESCANS_REF`) and to PyPI. It takes a few minutes while the
  conda layer is in Docker's build cache.
  - Changing `SPACESCANS_REF` makes Docker run both pip steps again. They install the
    versions in `backend/constraints.txt`, which are those of the image the gates tested
    (the computation libraries equal the frozen 0.2.7 image's). Step 7 checks them.
  - Only the conda layer is not pinned. If that cache was pruned, conda-forge is resolved
    again and GDAL or rasterio may move. Newly computed C3 weights can then differ by about
    1e-8, which phase-C decision 1 accepts.
  - The keys do not change, so existing cache entries keep being used.

## 1. Tag the paper's web commit and the running image

The paper's runs used web 3991c3b with pipeline v0.2.7. The git tag keeps that code: building
from it installs pipeline v0.2.7 again. It does not keep the library versions: 3991c3b's
`requirements.txt` asks for `pandas>=2.0` and pins only the web framework, so a rebuild takes
that day's PyPI releases of pandas, pyarrow and every library the pipeline computes with. The
exact environment of the paper's runs is the image the backend runs now. Its only tag is `latest`, which step 4 moves to the new image;
without a tag of its own, any `docker image prune` or Docker Desktop clean-up deletes it.

```bash
cd spacescans-web
git tag -a paper-jamia-2026 3991c3b -m "Web state of the JAMIA paper's runs (pipeline v0.2.7)"
git push origin paper-jamia-2026
# Keep the image the backend runs now: it is the fast way back (see Rollback).
docker inspect spacescans-web-backend-1 --format '{{.Image}}'      # sha256:8b219bc1b067... at the time of writing
docker tag "$(docker inspect spacescans-web-backend-1 --format '{{.Image}}')" spacescans-web-backend:pre-tier2-0.2.7
docker image ls spacescans-web-backend                              # latest and pre-tier2-0.2.7: the same ID
```

## 2. Push the package

```bash
cd ../spacescans
git checkout main
git merge --ff-only tier2/c-integration
git push origin main
PKG_SHA=$(git rev-parse main); echo "$PKG_SHA"
```

Wait until the GitHub Actions run of that commit is green. If `main` has moved since
7e2aa88, `--ff-only` refuses. In that case merge normally, rerun the package suite and use the
new head.

## 3. Merge the web branch and pin the package

```bash
cd ../spacescans-web
PKG_SHA=$(git -C ../spacescans rev-parse main)          # the commit pushed in step 2
git checkout main
git merge --ff-only tier2/web-integration
sed -i '' "s/^ARG SPACESCANS_REF=.*/ARG SPACESCANS_REF=$PKG_SHA/" backend/Dockerfile
grep '^ARG SPACESCANS_REF' backend/Dockerfile          # the full 40-character SHA
git commit -am "Build the backend against spacescans ${PKG_SHA:0:7}"
```

Use the full SHA. A short one makes pip warn "Did not find branch or tag" before it checks the
commit out. Do not push yet (step 9).

## 4. Build the backend image

```bash
docker compose build backend
```

The old backend keeps serving while this runs, and users can still start tasks.

## 5. Check that no task is running

Run this right before step 6, not before the build: during the build the old backend starts
a queued task within seconds of the run lock coming free.

```bash
docker compose exec -T backend /opt/conda/bin/python -c "import json, pathlib; print([p.parent.name for p in pathlib.Path('/app/data/tasks').glob('*/status.json') if json.loads(p.read_text()).get('status') in ('running', 'queued')])"
```

`[]` means nothing would be interrupted. Otherwise wait and run it again, or accept that the
listed tasks must be started again. If some time passes before step 6, run it again.

## 6. Start it

```bash
docker compose up -d backend
```

This recreates only the backend container: new image, now with `init: true`. The frontend and
RStudio containers keep running.

## 7. Smoke checks

```bash
docker compose ps backend                    # running ("Restarting": a startup check failed, see below)
docker compose logs --tail 40 backend        # "Application startup complete"; no traceback
curl -s http://localhost:8000/api/health     # {"status":"ok"}
docker compose exec -T backend cat /proc/1/comm    # docker-init (the init process is PID 1)
docker compose exec -T backend /opt/conda/bin/python -c "import json, pathlib, pandas, pyarrow, spacescans; d = next(pathlib.Path('/opt/conda/lib/python3.12/site-packages').glob('spacescans_pipeline-*.dist-info')); print(json.loads((d / 'direct_url.json').read_text())['vcs_info']['commit_id'], pandas.__version__, pyarrow.__version__, spacescans.capabilities()['flags']['episode_grouping'])"
# expected: <PKG_SHA> 3.0.5 26.0.0 True
docker compose exec -T backend /opt/conda/bin/python -c "import importlib.metadata as m; pins = [l.strip().split('==') for l in open('/app/constraints.txt') if l.strip() and not l.startswith('#')]; print([(n, v, m.version(n)) for n, v in pins if m.version(n) != v])"
# expected: []   (every pip-installed package at the version the gates tested)
```

A failed startup check does not print a message of its own: the log shows a traceback
ending in `RuntimeError: SPACESCANS_CONFIG_TEMPLATES_DIR=/configs does not match the templates
packaged in spacescans …` or `RuntimeError: Pipeline integration disabled. Missing paths: …`,
then uvicorn's `Application startup failed. Exiting.` With `restart: unless-stopped` the
container then restarts in a loop, and `docker compose ps` shows `Restarting`.

Then in the browser (`http://localhost:3000`):

1. Run a small task, for example noise on a few hundred episodes. It should end "Completed".
2. Run a cohort and variable you ran before the cutover again. The task log should show
   `cache hit: <key> — skipping pipeline run` for its C3 steps, which shows the old cache
   entries are still used.

The paper's scripts call
`docker exec spacescans-web-backend-1 /opt/conda/bin/python -m app.experiments.<x> run <task_dir> --variables …`.
The shims keep that command, its output file names and the run-lock message.

## 8. Rebuild the frontend

`frontend/src/lib/data-sources.json` is now generated from the package's data manifest. The
licence lines, sizes and file notes changed. The old frontend works with the new backend, so
this step can wait.

```bash
docker compose build frontend && docker compose up -d frontend
```

## 9. Push the web branch

```bash
git push origin main
```

## Rollback

The C3 cache is valid for both versions, so a rollback needs no cache clearing either; with
a rebuild of the old code that holds only while it gets pandas 3.0.5 (see below).
Restarting the backend interrupts running tasks, as in step 5.

**Fast: the previous image.** Step 1 tagged it `spacescans-web-backend:pre-tier2-0.2.7`:

```bash
docker tag spacescans-web-backend:pre-tier2-0.2.7 spacescans-web-backend:latest
docker compose up -d backend
```

This runs 3991c3b + v0.2.7 again within seconds, in exactly the old environment. With the new
`docker-compose.yml` it also gets the init process, which does no harm. Then also revert the
code (next block), so that the next `docker compose build` does not bring the new version
back. After the fast path, the build and `up` lines in that block are optional, and better
left out: the rebuild is not version-pinned (below).

Once the cutover is accepted, remove the rollback tag, so that Docker can reclaim the old
image: `docker image rm spacescans-web-backend:pre-tier2-0.2.7`.

**Complete: revert the web commits.** This restores web 31c5dc3: the old runners, the old
compose file and `SPACESCANS_REF=v0.2.7`.

```bash
cd spacescans-web
git status --short                                     # nothing: start from a clean checkout
git revert --no-edit 056cb73572be08207338830f79ee4e48c76a89c1..HEAD   # every commit after the merge, newest first
git revert --no-edit -m 1 056cb73572be08207338830f79ee4e48c76a89c1    # the merge of tier2/web-container
git diff --stat 31c5dc3                                # nothing: the tree is 31c5dc3's again
docker compose build backend && docker compose up -d backend
docker compose build frontend && docker compose up -d frontend   # if step 8 was done
git push origin main
```

The rebuild of 31c5dc3 is not version-pinned: its `requirements.txt` asks for `pandas>=2.0`
and nothing pins pyarrow or the other libraries. A build without the old build cache can
therefore install newer releases. The cache is then not wrong, only cold: a newer pandas
changes every legacy cache key (the key hashes `input.parquet`, which records the pandas
version), so every C3 step misses the cache and recomputes. After such a rebuild, check the
versions:

```bash
docker compose exec -T backend /opt/conda/bin/python -c "import pandas, pyarrow; print(pandas.__version__, pyarrow.__version__)"
# 3.0.5 26.0.0: the cache stays valid
```

How the two reverts work:

- `056cb73` is the merge that brought the phase-C web changes in.
- The commits after it are undone first, newest first: the step-3 pin, this document and
  the fixes made after the merge. None of them is a merge.
- The merge's first parent is 31c5dc3, so `-m 1` then undoes all of its changes at once.
- This file goes too; it stays in the history.

The package push needs no rollback. The web image pins its own `SPACESCANS_REF`, and v0.2.7
is still tagged.

## What was verified before this document was written

These checks ran on 2026-10-14, on branches, with ephemeral containers and read-only data.
The live compose project was never touched. "The integrated package" is `tier2/c-integration`,
the commit step 2 pushes.

- **Backend test suite** with the integrated package: 509 passed. The only failure is the
  known health-probe test, which needs `SPACESCANS_*` paths.
- **Frozen 0.2.7 image** (`spacescans-web-backend:frozen-2026-10-12`), with this backend
  mounted at `/app`:
  - **With package 7e2aa88 mounted:** all 13 golden configurations (every catalog variable
    and both upload paths) and the full fan-in match the 0.2.7 runs.
    - Byte-identical: `input.parquet`, the C3 tables, cache keys and metas, the YAML and
      the runner log lines.
    - Equal: the whole `status.json` write sequence.
    - Values within 1.4e-14, which is the 0.2.7 runner's own pass-to-pass difference.
  - **With the integrated package mounted:** bg_ndi_wi, noise and both uploads give the same
    result. A cache seeded with 0.2.7's entries is hit by every C3 step.
- **Deployable image:** built from this Dockerfile with `SPACESCANS_REF=7e2aa88`. The
  integrated package cannot be installed from GitHub before step 2, so step 4 is the first
  build with it, and step 7 checks that build.
  - Its test suite passes.
  - It starts the way compose starts it: PID 1 is `docker-init`, and `/api/health` and
    `/api/variables` answer.
  - It reproduces the goldens and hits a cache written by 0.2.7.
  - `python -m app.dispatcher run` completes a mixed task.
  - The paper's CLI forms work: `runtime.py`'s wrapper cold and warm, the
    `independent_impl_chain.sh` form, and the run-lock message.
  - The commands of steps 5 and 7 were run in it as written.
- **synth_10k in the frozen image:** bg_ndi_wi and noise through the shims equal the 0.2.7
  runner within 3.6e-15.
