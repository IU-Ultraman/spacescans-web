# Manual End-to-End Smoke Test — BG NDI + Walkability v1

This walk-through verifies the full integration from browser to result.csv.
It is not part of automated pytest; run it before publishing any release.

## Prerequisites

- Backend env (`backend/.env`) configured:
  - `SPACESCANS_DATA_DIR=/Users/xai/Desktop/spacescans-project` (project root — the dir that contains `data_full/`)
  - `SPACESCANS_PIPELINE_PYTHON=/Users/xai/miniconda3/envs/spacescans/bin/python`
  - `SPACESCANS_PIPELINE_CLI=/Users/xai/miniconda3/envs/spacescans/bin/spacescans`
  - `SPACESCANS_CONFIG_TEMPLATES_DIR=/Users/xai/Desktop/spacescans-project/configs`
- Frontend deps installed: `(cd frontend && npm install)`.
- Backend deps installed in the spacescans conda env:
  `(cd backend && /Users/xai/miniconda3/envs/spacescans/bin/pip install -r requirements.txt)`.

## Steps

1. **Start backend**

   ```bash
   cd /Users/xai/Desktop/spacescans-project/spacescans-web/backend
   /Users/xai/miniconda3/envs/spacescans/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

   Confirm `curl http://localhost:8000/api/health` returns `{"status":"ok"}`.

2. **Start frontend**

   ```bash
   cd /Users/xai/Desktop/spacescans-project/spacescans-web/frontend
   npm run dev
   ```

   Open `http://localhost:3000`.

3. **Sign up + log in** if you don't already have an account.

4. **Prepare a small CSV** — first 100 rows of the demo cohort:

   ```bash
   head -101 /Users/xai/Desktop/spacescans-project/data_full/demo_patients_conus_fast_100000.csv \
     > /tmp/smoke_100.csv
   ```

5. **Create a new task**, name it `smoke-test`.

6. **Upload step** — drop `/tmp/smoke_100.csv`. Verify the validation panel shows 100 rows and 9 columns.

7. **Buffer step** — shape locked to circle. Set size to 270 m and raster_res_m to 25. Verify the disabled square button shows the tooltip on hover.

8. **Variables step** — check both NDI and Walkability. Continue.

9. **Review & Run step**:
   - The overall progress bar should climb from 0% to 100%.
   - The step list should show:
     ```
     Step 1/3   ✅ c3_bg
     Step 2/3   ⏳ c4_ndi   — Running c4_ndi (2/3)
     Step 3/3   ⏸ c4_wi
     ```
   - Expected total wall-clock: 1–2 min on a laptop with the 220 GB tree mounted.

10. **Result download** — click "Download result.csv". Open the file:

    ```bash
    head -3 ~/Downloads/result.csv
    ```

    Confirm columns are `pid,startDate,endDate,longitude,latitude,state_fips,county_fips,tract_geoid,bg_geoid,ndi,NatWalkInd` and exactly 100 data rows.

11. **Failure modes to spot-check (optional)**:
    - Disable Walkability checkbox and rerun → result.csv only has `ndi` column.
    - Attempt to start a second task while the first is running → frontend shows 409.

## Pass criteria

- result.csv has 100 rows.
- Both `ndi` and `NatWalkInd` columns have non-null values for at least 90% of patients.
- Wall-clock under 5 minutes.
- No errors in the backend stdout.

## Sprint 1 additions (Pre-flight + Cache)

### Pre-flight coverage check

On the Variables step, after checking NDI:
- Expect a colored panel below: green if ≥95% covered, yellow 60-95%, red <60%.
- The panel reads: "X% of your cohort covered" with breakdown by time and region.
- Try a cohort with patients in 2010 (outside NDI 2012-2022) — expect a warning line.

### C3 cache speedup

After completing one task with NDI + Walkability:
1. Note the wall-clock for c3_bg step in the LogViewer (timestamp diff between
   "spawning c3_bg" and "step c3_bg exit code 0").
2. Create a NEW task, upload the same CSV, select the same variables and buffer.
3. Start the task. The c3_bg step should appear, log "cache hit", and complete
   in under a second (you'll see the step list flicker by quickly).
4. result.csv should still be produced.

To force a cache rebuild:

    rm -rf backend/data/c3_cache/

## Sprint 2 additions (Episode-dimension preservation)

### Multi-episode result rows

The pipeline now emits one result row per residential episode (a patient
who moved during the study window gets one row per residence) instead of
collapsing to one row per patient.

1. Upload `backend/tests/fixtures/patients_multi_episode.csv` (11 rows:
   5 patients with 2 episodes each + 1 single-episode control).
2. Run with NDI + Walkability, default buffer (270m circle).
3. After completion, download result.csv.
4. Expected:
   - **11 data rows** (not 6).
   - `pid` column repeats `PID0000001` twice, then `PID0000002` twice, etc.
   - At least 2 of the multi-episode patients show **different** `ndi`
     values across their two rows — proves the per-episode dispatch is
     live, not just row duplication.

### Results page hint

On the results page (`/dashboard/task/<id>/results`), the Download Results
card should display: "Result shape: one row per residential episode. A
patient with multiple residences during the study window gets one row
per residence; exposure values reflect that specific residence."

### Backward compatibility

Re-upload the original `patients_5.csv` (5 patients × 1 episode each).
Expected: 5 result rows — identical to v1 behaviour because each patient
has one episode. The episode-dimension change is invisible on
single-episode cohorts.

## Sprint 3 — Variables-driven UI + ZCTA5×CBP

Pre-flight:
- `backend/app/data/variable_metadata.json` exists with `schema_version: 1` and 3 entries (`ndi`, `walkability`, `cbp_zcta5`).
- `backend/app/data/variable_metadata.schema.json` exists.
- `pyreadr` is importable in the spacescans env (Sprint 3 Risk R1).
- The ZCTA5 buffer parquet exists at `output/python_v2/270m/ZCTA5_US/C3/buffer270mZCTA525m_demo100k.parquet` (Sprint 3 Risk R2).
- The pipeline config exists at `spacescans-pipeline/configs/c4/zcta5_cbp_demo.yaml`.
- Legacy `backend/data/variable_metadata.json` does NOT exist.

Walk-through:

1. **3-card variables-step render.** Reach the Variables step. Confirm 3 cards rendered, grouped by boundary:
   - "Block Group" section: NDI, EPA Walkability Index.
   - "ZIP Code Tabulation Area" section: Community Organization Density (ZBP).
   Each card shows: label, description, unit chip, year-range chip, boundary chip.

2. **Coverage panel mount.** Tick any single card. The coverage panel mounts inline and issues `GET /api/tasks/<id>/coverage?variables=<key>`. The response now includes the `boundary` chip.

3. **schema_version=2 mismatch banner.** Temporarily edit `backend/app/data/variable_metadata.json` and set `"schema_version": 2`. Refresh the wizard. Expected: top-of-step banner reads "Catalog out of date" with a Refresh button; the cards do NOT render. Revert the file.

4. **Multi-experiment run with `experiments` map progression.** Tick all 3 cards → Review → Run. On the task page, poll `/api/tasks/<id>/status`:
   - First snapshot: `status.experiments == {"bg_ndi_wi": "running", "zcta5_cbp": "pending"}`.
   - Mid-run snapshot: `status.experiments == {"bg_ndi_wi": "finished", "zcta5_cbp": "running"}`.
   - Final snapshot: both `"finished"`; `status.status == "finished"`.

5. **result.csv column set.** Download `result.csv`. Required columns:
   - Keys: `pid`, `episode_id`.
   - BG: `ndi`, `NatWalkInd`.
   - ZCTA5: `r_religious`, `r_civic`, `r_business`, `r_political`, `r_professional`, `r_labor`, `r_bowling`, `r_recreational`, `r_golf`, `r_sports`.
   Row count equals the BG row count from Sprint 2; ZCTA5 columns left-join cleanly.

To force a fresh run after Sprint 3 deployment (cache keys changed):

    rm -rf backend/data/c3_cache/


## Sprint 5 — TIGER Road Proximity + precomputed_areal episode dispatch

Pre-flight:
- spacescans-pipeline editable install reflects Phase A
  (`output_grouping` dispatch in `precomputed_areal_linkage.py`).
  Verify with `python -c "from spacescans.linkage import
  precomputed_areal_linkage; import inspect; print('episode' in
  inspect.getsource(precomputed_areal_linkage))"` — expect True.
- `data_full/TIGER/C4/tiger{2013,…,2019}_roads/` exists with per-county
  zip files for at least one county.
- `cache/C3/tiger_roads_filtered/` exists (first run on a fresh cache
  takes longer).
- `backend/app/data/variable_metadata.json` has 4 entries including
  `tiger_proximity`.

1. Variables-step renders 4 cards grouped by boundary:
   - "Block Group" section: NDI, EPA Walkability Index, TIGER Road
     Proximity
   - "ZCTA5" section: Community Organization Density (ZBP)
   Each card shows label, description, unit chip, year-range chip,
   boundary chip. The TIGER card's unit chip reads "meters",
   year-range "2013–2019", boundary "BG".
2. Tick the TIGER card → coverage panel mounts inline; same shape
   as Sprint 3 cards.
3. Tick all 4 variables → Review step → Run. Watch status.json:
   - `experiments` map shows bg_ndi_wi running first, zcta5_cbp
     and tiger_proximity pending; then progresses through all three
     in metadata-file order.
   - logs.jsonl carries entries from all three runners.
   - result.csv on completion carries
     ndi + NatWalkInd + all 10 r_* + dist_pri + dist_sec + dist_prisec
     columns.
4. Repeat the same task; second run should hit the
   `BG_TIGER` C3 cache (status.json shows c3_tiger_roads progresses
   to 100% in < 1s for the cached cohort + buffer).
5. Negative test: edit `configs/c4/tiger_roads_demo.yaml` to change
   `output_grouping: episode` to an unknown value (e.g.
   `output_grouping: foo`); run a fresh task. Expect a clear
   ValueError in logs.jsonl from `precomputed_areal_linkage.py`:
   `unsupported output_grouping: 'foo' (expected 'patient' or 'episode')`.
   Restore the YAML. NOTE: do NOT test by *removing* the key —
   `TimeConfig.output_grouping` defaults to `"patient"` at the
   dataclass level (`src/spacescans/models/config.py:100`), so a
   missing key silently falls back to patient-grouping instead of
   raising. Catching that regression requires the explicit-typo
   test, not an absent-field test.
