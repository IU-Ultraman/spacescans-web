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
