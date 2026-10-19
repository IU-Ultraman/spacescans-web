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
