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
  start it again. Queued tasks are kept and start once the backend is back. Step 4 checks
  that nothing is running.
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

  The 0.2.7 upgrade had to delete 520 cache files because the weights themselves changed.
  Nothing like that happens here. The cache also stays valid if you roll back.
- **`configs/` is checked at startup.** With `SPACESCANS_CONFIG_TEMPLATES_DIR=/configs` (as in
  `docker-compose.yml`), the backend refuses to start unless every template packaged in
  `spacescans` has a byte-identical file in `./configs`. The repo's `configs/` matches; a local
  edit there would stop the backend.
- **The build needs network access** to GitHub (pip installs the package from
  `IU-Ultraman/spacescans` at `SPACESCANS_REF`). It takes about a minute while the conda layer
  is in Docker's build cache.
  - If that cache was pruned, conda-forge is resolved again and GDAL or rasterio may move.
    Newly computed C3 weights can then differ by about 1e-8, which phase-C decision 1
    accepts.
  - The keys do not change, so existing cache entries keep being used.

## 1. Tag the paper's web commit

The paper's runs used web 3991c3b with pipeline v0.2.7. A tag keeps that state reproducible:
building from the tag pins `SPACESCANS_REF=v0.2.7` again.

```bash
cd spacescans-web
git tag -a paper-jamia-2026 3991c3b -m "Web state of the JAMIA paper's runs (pipeline v0.2.7)"
git push origin paper-jamia-2026
# Note the image the backend runs now; it is the fast way back (see Rollback).
docker inspect spacescans-web-backend-1 --format '{{.Image}}'
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

## 4. Check that no task is running

```bash
docker compose exec -T backend /opt/conda/bin/python -c "import json, pathlib; print([p.parent.name for p in pathlib.Path('/app/data/tasks').glob('*/status.json') if json.loads(p.read_text()).get('status') in ('running', 'queued')])"
```

`[]` means nothing would be interrupted. Otherwise wait, or accept that the listed tasks must
be started again.

## 5. Build the backend image

```bash
docker compose build backend
```

## 6. Start it

```bash
docker compose up -d backend
```

This recreates only the backend container: new image, now with `init: true`. The frontend and
RStudio containers keep running.

## 7. Smoke checks

```bash
docker compose ps backend                    # running
docker compose logs --tail 40 backend        # "Application startup complete"; no traceback, no "refusing to start"
curl -s http://localhost:8000/api/health     # {"status":"ok"}
docker compose exec -T backend cat /proc/1/comm    # docker-init (the init process is PID 1)
docker compose exec -T backend /opt/conda/bin/python -c "import json, pathlib, pandas, pyarrow, spacescans; d = next(pathlib.Path('/opt/conda/lib/python3.12/site-packages').glob('spacescans_pipeline-*.dist-info')); print(json.loads((d / 'direct_url.json').read_text())['vcs_info']['commit_id'], pandas.__version__, pyarrow.__version__, spacescans.capabilities()['flags']['episode_grouping'])"
# expected: <PKG_SHA> 3.0.5 26.0.0 True
```

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

The C3 cache is valid for both versions, so a rollback needs no cache clearing either.
Restarting the backend interrupts running tasks, as in step 4.

**Fast: the previous image.** It stays in Docker's image store until you prune it. Use the ID
noted in step 1 (`sha256:8b219bc1b067…` at the time of writing):

```bash
docker tag <old image id> spacescans-web-backend:latest
docker compose up -d backend
```

This runs 3991c3b + v0.2.7 again within seconds. With the new `docker-compose.yml` it also
gets the init process, which does no harm. Then also revert the code (next block), so that the
next `docker compose build` does not bring the new version back. After the fast path, the
build and `up` lines in that block are optional: they rebuild the same old code.

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

How the two reverts work:

- `056cb73` is the merge that brought the phase-C web changes in.
- The commits after it are undone first, newest first: the step-3 pin, this document and
  the integration track's fixes. None of them is a merge.
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
  integrated package cannot be installed from GitHub before step 2, so step 5 is the first
  build with it, and step 7 checks that build.
  - Its test suite passes.
  - It starts the way compose starts it: PID 1 is `docker-init`, and `/api/health` and
    `/api/variables` answer.
  - It reproduces the goldens and hits a cache written by 0.2.7.
  - `python -m app.dispatcher run` completes a mixed task.
  - The paper's CLI forms work: `runtime.py`'s wrapper cold and warm, the
    `independent_impl_chain.sh` form, and the run-lock message.
  - The commands of steps 4 and 7 were run in it as written.
- **synth_10k in the frozen image:** bg_ndi_wi and noise through the shims equal the 0.2.7
  runner within 3.6e-15.
