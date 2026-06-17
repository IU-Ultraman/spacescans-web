# Sprint 13 — Results Visualization (Histograms + US State Map)

**Date:** 2026-06-17
**Sprint window:** 2026-06-17 → 2026-06-19 (3 days)
**Status:** Spec + plan, ready for implementation
**Owner:** xai

---

## Background

The results page (`/Users/xai/Desktop/spacescans-project/spacescans-web/frontend/src/app/dashboard/task/[id]/results/page.tsx`) already ships:

- Completion timestamp card
- Task Summary card (name / status / id)
- **Result Preview** card — first 10 rows of `result.csv` via `GET /api/tasks/{id}/results/preview?limit=10`
- **Column Summary** card — per-exposure-column dtype / non-null / min / mean / max / nunique (filtered against a local `INPUT_COLUMNS` Set)
- Download Results card (zip + intermediates `<details>`)

User feedback: "the analytical cards are useful but flat. Add fancier viz — histograms per exposure column and a US map showing geographic spread." Two features are sized to land in one sprint:

- **Feature A — Exposure histograms.** One small bar chart per numeric exposure column. Skip input cohort columns. Skip categorical columns (e.g. `fara_tract`'s binary flags).
- **Feature B — US state choropleth.** Aggregate patient rows by `state_fips`; surface count + mean of a user-selected exposure column. State-level only (Tract / BG / ZCTA5 maps deferred for privacy + simplicity).

Both consume the same `result.csv` already produced by the pipeline — no new pipeline outputs.

---

## Scope (in)

### Backend
- `GET /api/tasks/{id}/results/histogram?bins=20` — single endpoint returning **all** numeric exposure column histograms in one shot.
- `GET /api/tasks/{id}/results/geo?value_col=<col>` — per-`state_fips` count + mean of one numeric exposure column.
- Promote `INPUT_COLS` to a shared module constant; reuse from `/preview`, `/histogram`, `/geo`.
- Fix the FIPS-int regression inherited from `/preview` by passing the same dtype map already used in `task_manager.compute_coverage` (`state_fips`, `county_fips`, `tract_geoid`, `bg_geoid` as `"string"`).
- 4–6 backend tests covering both endpoints (extend `test_tasks.py::test_results_preview` pattern).

### Frontend
- New shared module `frontend/src/lib/result-columns.ts` exporting `INPUT_COLUMNS: Set<string>` + `isInputColumn(name: string): boolean`. Refactor `results/page.tsx` Column Summary to use it.
- **Histograms card** — grid of small bar charts (`recharts` `<BarChart>`), one per numeric exposure column.
- **State Map card** — `react-simple-maps` `<ComposableMap>` with USA Albers projection + a value-column dropdown selector + count/mean toggle + hover tooltip + color legend strip.
- Install `recharts`, `react-simple-maps`, `@types/react-simple-maps`. Topojson fetched from CDN (`https://cdn.jsdelivr.net/npm/us-atlas@3/states-10m.json`) at runtime — not bundled.

### Tests
- 4–6 backend tests in `backend/tests/test_tasks.py`.
- No new frontend tests (UI-only — rely on `tsc` + visual smoke). Document the smoke checklist below.

---

## Scope (out)

- **No county / tract / BG / ZCTA5 maps.** State-only this sprint. Lower-geography maps risk surfacing small-N cells and the bug surface for FIPS leading-zero handling multiplies.
- **No per-patient pin maps.** PHI risk; would require explicit aggregation/jitter contracts.
- **No scatter / correlation / boxplot / time-series.** Deferred — single sprint, two charts.
- **No CSV-on-frontend parsing.** All aggregation server-side.
- **No shadcn chart primitive scaffold (`npx shadcn add chart`).** We write thin custom wrappers — fewer files, fewer abstractions over `recharts`.
- **No dark-mode chart palette tuning beyond using existing `--chart-N` CSS vars.** If the default Tailwind chart tokens look bad against the topojson gray, file a follow-up.

---

## Background data facts (anchored)

These are the load-bearing facts driving the design. All verified against the working tree on 2026-06-17.

### result.csv shape

Four real task outputs were inspected:

- `backend/data/tasks/task-e4af4dfd-2924-4a6e-870f-dd848dbe94cf/output/result.csv` — header: `pid,startDate,endDate,longitude,latitude,state_fips,county_fips,tract_geoid,bg_geoid,ndi`
- `backend/data/tasks/task-cf88c8a8-30cf-40a9-93e3-ff49eff3d261/output/result.csv` — adds `episode_id`: `...bg_geoid,episode_id,ndi`
- `backend/data/tasks/task-fb94a304-8f59-4bfc-8913-77cb8fdccc40/output/result.csv` — full ZCTA5 CBP variant
- `backend/data/tasks/task-79c546a3-cc74-4b66-8069-90377932245b/output/result.csv` — walkability variant

Canonical prefix (always present): `pid, startDate, endDate, longitude, latitude, state_fips, county_fips, tract_geoid, bg_geoid`. Optional `episode_id` follows the prefix. **Exposure columns** are everything after that — and are the only columns we histogram / aggregate.

### FIPS leading-zero hazard (CRITICAL)

`result.csv` is written **without** preserving FIPS leading zeros. Sample row from `task-e4af4dfd-.../output/result.csv`:

```
PID0000001,2017-08-19,2017-11-11,-93.0286350230624,45.0889762917531,27,27123,27123040504,271230405042,-1.2309778137313663
```

Bare ints. So Alabama (FIPS `01`) would serialize as `1` and Connecticut (`09`) as `9`. The existing `/results/preview` endpoint at `backend/app/routers/tasks.py:171` calls `pd.read_csv(result_path)` with **no** dtype hint, so it infers `state_fips` / `county_fips` / `tract_geoid` / `bg_geoid` as `int64`. This is a latent bug in `/preview` today (FIPS get classified as `numeric` by `is_numeric_dtype` and surfaced with min/max/mean — meaningless). The contrast: `task_manager.py:87-92` (`compute_coverage`) does it right:

```python
df = pd.read_csv(
    input_csv,
    parse_dates=["startDate", "endDate"],
    dtype={
        "state_fips": "string",
        "county_fips": "string",
        "tract_geoid": "string",
        "bg_geoid": "string",
    },
)
```

**Sprint 13 fix:** new histogram + geo endpoints MUST pass the same dtype map. The geo endpoint additionally zfill(2)s `state_fips` to be defensive against any upstream caller that re-cast to int.

### Shipped variables → exposure columns

From `backend/app/data/variable_metadata.json`. All continuous numeric except `fara_tract` (binary flag categorical):

| variable        | boundary | exposure cols                                                                                                            | type        |
| --------------- | -------- | ------------------------------------------------------------------------------------------------------------------------ | ----------- |
| ndi             | BG       | `ndi`                                                                                                                    | continuous  |
| walkability     | BG       | `NatWalkInd`                                                                                                             | continuous  |
| cbp_zcta5       | ZCTA5    | `r_religious, r_civic, r_business, r_political, r_professional, r_labor, r_bowling, r_recreational, r_golf, r_sports`    | continuous  |
| tiger_proximity | BG       | `dist_pri, dist_sec, dist_prisec`                                                                                        | continuous  |
| nhd_bluespace   | BG       | `dist_flow_m, dist_water_m, dist_area_m, dist_coast_m, dist_blue_m` (note: 99999 sentinel)                              | continuous  |
| noise           | BG       | `l50dba_exi, l50dba_imp, l50dba_nat`                                                                                     | continuous  |
| vnl             | BG       | `value`                                                                                                                  | continuous  |
| temis           | BG       | `uvddc, uvdec, uvdvc, uvief`                                                                                             | continuous  |
| fara_tract      | Tract    | `LILATracts_1And10, LATracts1, HUNVFlag, LowIncomeTracts`                                                                | categorical |

`fara_tract`'s columns are int64 but semantically binary — `pd.api.types.is_numeric_dtype` will say `True`. Our histogram endpoint accepts them today (nunique == 2 bin) but the better signal is: skip if `series.nunique(dropna=True) <= 10`. That keeps us robust against future-added flag columns without needing a per-variable allowlist. Decision: **skip if `nunique <= 2`** (binary only); allow 3–10 unique counts because they could be ordinal exposure (e.g. dose categories).

### Frontend stack

- `recharts`, `react-simple-maps`, `d3*`, `plotly` — **none installed today.** Confirmed against `frontend/package.json`.
- Existing UI primitives in `frontend/src/components/ui/`: button, badge, card, chip, dialog, dropdown-menu, input, label, progress, scroll-area, separator, sheet, table, tabs, textarea, sonner. No `chart.tsx`.
- Tailwind config (`tailwind.config.ts:4`) uses `darkMode: ['class']` and defines `chart: { '1'…'5': 'hsl(var(--chart-N))' }`. We reference these via `hsl(var(--chart-1))` etc. in chart fills so dark-mode toggling Just Works.
- Container width `mx-auto max-w-5xl` = 1024px (results page line 189). After `p-6` padding each card has ~976px interior — plenty for a 960×600 Albers projection and a 2-column histogram grid.
- `INPUT_COLUMNS` today lives inline in `results/page.tsx:140-151`, used only by Column Summary. Promote to `frontend/src/lib/result-columns.ts`.

---

## Backend design

### A.1 Histogram endpoint

```
GET /api/tasks/{task_id}/results/histogram?bins=20
```

- `bins` — int query param, default `20`, validated `5 <= bins <= 50` (FastAPI `Query(20, ge=5, le=50)`).
- Auth: same `Depends(get_current_user)` as `/preview`.
- 404 if `result_path is None or not result_path.exists()`.

**Response shape (TypeScript form for clarity):**

```ts
interface HistogramBin {
  edge_lo: number;     // left edge of this bin
  edge_hi: number;     // right edge of this bin
  count: number;       // number of non-null rows in [edge_lo, edge_hi)
}

interface ColumnHistogram {
  name: string;            // column name in result.csv
  bins: HistogramBin[];    // length == bins query param (or fewer if all-null col)
  min: number | null;      // null iff column is all-NaN
  max: number | null;
  sample_size: number;     // non-null row count
}

interface ResultsHistogramResponse {
  total_rows: number;          // len(df), matches /preview.total
  bins_requested: number;      // echoes query param
  histograms: ColumnHistogram[];  // empty iff no numeric exposure cols
}
```

**Algorithm.**

1. Read CSV with FIPS-safe dtype map.
2. Drop input columns by intersecting against `INPUT_COLS`.
3. For each remaining column, test `pd.api.types.is_numeric_dtype(series)` AND `series.nunique(dropna=True) > 2`. Skip if either fails.
4. Drop NaNs; if `len(dropped) == 0` emit an empty `bins=[]` entry with min/max=null and `sample_size=0`.
5. Compute `counts, edges = np.histogram(dropped.values, bins=bins)`. Convert edges into `bins[]` of `(edge_lo, edge_hi, count)` tuples.
6. Round all floats to 6 decimals for JSON cleanliness, sub None for non-finite values.

**Skeleton.**

```python
# backend/app/routers/tasks.py
@router.get("/{task_id}/results/histogram")
async def get_results_histogram(
    task_id: str,
    bins: int = Query(20, ge=5, le=50),
    current_user: User = Depends(get_current_user),
) -> dict:
    result_path = task_manager.get_result_path(task_id)
    if result_path is None or not result_path.exists():
        raise HTTPException(status_code=404, detail="Results not ready")

    import math
    import numpy as np
    import pandas as pd

    from app.result_columns import INPUT_COLS, FIPS_DTYPE_MAP

    df = pd.read_csv(result_path, dtype=FIPS_DTYPE_MAP)
    total_rows = len(df)
    exposure_cols = [c for c in df.columns if c not in INPUT_COLS]

    def _finite(v: float) -> float | None:
        return round(float(v), 6) if math.isfinite(v) else None

    histograms = []
    for col in exposure_cols:
        s = df[col]
        if not pd.api.types.is_numeric_dtype(s):
            continue
        if s.nunique(dropna=True) <= 2:
            continue  # binary/flag column — not a meaningful histogram
        clean = s.dropna()
        if len(clean) == 0:
            histograms.append({
                "name": col,
                "bins": [],
                "min": None,
                "max": None,
                "sample_size": 0,
            })
            continue
        counts, edges = np.histogram(clean.values, bins=bins)
        bin_objs = [
            {
                "edge_lo": _finite(edges[i]),
                "edge_hi": _finite(edges[i + 1]),
                "count": int(counts[i]),
            }
            for i in range(len(counts))
        ]
        histograms.append({
            "name": col,
            "bins": bin_objs,
            "min": _finite(float(clean.min())),
            "max": _finite(float(clean.max())),
            "sample_size": int(len(clean)),
        })

    return {
        "total_rows": int(total_rows),
        "bins_requested": int(bins),
        "histograms": histograms,
    }
```

### A.2 Geo endpoint

```
GET /api/tasks/{task_id}/results/geo?value_col=ndi
```

- `value_col` — required string query.
- Auth + 404 same as above.
- 400 if `value_col` not in result.csv columns, is in `INPUT_COLS`, or is non-numeric.

**Response shape.**

```ts
interface StateAggregate {
  state_fips: string;   // always 2-char, zero-padded
  count: number;        // count of rows in this state with non-null value_col
  mean: number;         // mean of value_col over non-null rows
}

interface ResultsGeoResponse {
  value_col: string;          // echoes query param
  total_states: number;       // length of by_state
  total_rows: number;         // len(df), pre-filter
  by_state: StateAggregate[]; // states with 0 non-null rows omitted
}
```

**Algorithm.**

1. Read CSV with FIPS-safe dtype map (`state_fips` is `"string"` from disk — but values like `27` will load as `"27"` already, no zfill needed; do defensive `.str.zfill(2)` anyway because of the latent disk-write bug).
2. Validate `value_col`: must be in columns, not in `INPUT_COLS`, and `is_numeric_dtype`.
3. Project to `[state_fips, value_col]`, drop rows where `value_col` is null.
4. `groupby("state_fips").agg(count=(value_col, "size"), mean=(value_col, "mean"))`.
5. Filter to count > 0 (already guaranteed by groupby on dropna'd frame, but explicit).
6. Round mean to 6 decimals; emit sorted by `state_fips` for deterministic order.

**Skeleton.**

```python
# backend/app/routers/tasks.py
@router.get("/{task_id}/results/geo")
async def get_results_geo(
    task_id: str,
    value_col: str = Query(..., min_length=1),
    current_user: User = Depends(get_current_user),
) -> dict:
    result_path = task_manager.get_result_path(task_id)
    if result_path is None or not result_path.exists():
        raise HTTPException(status_code=404, detail="Results not ready")

    import math
    import pandas as pd

    from app.result_columns import INPUT_COLS, FIPS_DTYPE_MAP

    df = pd.read_csv(result_path, dtype=FIPS_DTYPE_MAP)
    if value_col not in df.columns:
        raise HTTPException(status_code=400, detail=f"Unknown column: {value_col}")
    if value_col in INPUT_COLS:
        raise HTTPException(status_code=400, detail=f"Column is input, not exposure: {value_col}")
    if not pd.api.types.is_numeric_dtype(df[value_col]):
        raise HTTPException(status_code=400, detail=f"Column is not numeric: {value_col}")

    # Defensive zfill — protects against int-coerced FIPS upstream.
    sub = df[["state_fips", value_col]].copy()
    sub["state_fips"] = sub["state_fips"].astype("string").str.zfill(2)
    sub = sub.dropna(subset=[value_col])

    grouped = (
        sub.groupby("state_fips", dropna=True)[value_col]
        .agg(["size", "mean"])
        .reset_index()
        .rename(columns={"size": "count"})
        .sort_values("state_fips")
    )

    by_state = [
        {
            "state_fips": str(row.state_fips),
            "count": int(row.count),
            "mean": round(float(row.mean), 6) if math.isfinite(row.mean) else None,
        }
        for row in grouped.itertuples(index=False)
    ]

    return {
        "value_col": value_col,
        "total_states": len(by_state),
        "total_rows": int(len(df)),
        "by_state": by_state,
    }
```

### A.3 Shared input-column constant

New module `backend/app/result_columns.py`:

```python
"""Shared constants for result.csv column classification.

Used by /api/tasks/{id}/results/{preview,histogram,geo} to ensure all
three endpoints agree on what counts as an INPUT (cohort/geocode) column
vs. an EXPOSURE (variable output) column.
"""

# Columns the cohort uploads or that geocoding adds — never an exposure.
INPUT_COLS: frozenset[str] = frozenset({
    "pid",
    "episode_id",
    "startDate",
    "endDate",
    "longitude",
    "latitude",
    "state_fips",
    "county_fips",
    "tract_geoid",
    "bg_geoid",
})

# dtype hint passed to pd.read_csv to preserve FIPS leading zeros.
# Mirrors task_manager.compute_coverage at backend/app/task_manager.py:87-92.
FIPS_DTYPE_MAP: dict[str, str] = {
    "state_fips": "string",
    "county_fips": "string",
    "tract_geoid": "string",
    "bg_geoid": "string",
}
```

Refactor `routers/tasks.py::results_preview` to import `INPUT_COLS` from here and pass `FIPS_DTYPE_MAP` to its `pd.read_csv` — that fixes the latent "state_fips classified as numeric" bug in `/preview` as a freebie.

---

## Frontend design

### B.1 Dependencies

```bash
cd frontend
npm install recharts@^2.13 react-simple-maps@^3.0
npm install -D @types/react-simple-maps@^3
```

**Bundle impact:** ~150KB gzip recharts + ~30KB gzip react-simple-maps. Topojson (~30KB over wire) fetched lazily from `https://cdn.jsdelivr.net/npm/us-atlas@3/states-10m.json` — not in the bundle.

**Note on npm install in CI:** the project README documents `npm install` for the web frontend and we have observed HTTP timeouts in CI. Document this as a setup step; no behavioral change.

### B.2 Histograms card

Position: **between Column Summary and Download Results** (insert at `results/page.tsx:386`, i.e. after the Column Summary close brace at `:385` and before the Download card open at `:388`).

Layout:

- Card shell — `rounded-lg border bg-card p-6 shadow-sm` (matches surrounding cards).
- Header: "Value Distributions" + subhead `{N} numeric exposure columns • {total_rows} rows`.
- Body: `grid grid-cols-1 md:grid-cols-2 gap-4`.
- Each cell:
  - small header: column name (mono font) + sample size pill.
  - `<BarChart>` (recharts) — height 120px, no axis ticks (too small), tooltip showing `[edge_lo, edge_hi)` and count.
  - footer line: `min .. max` text in muted color.
- Skip the card entirely if `histograms.length === 0`.

**Files.**

```
frontend/src/components/results/HistogramsCard.tsx        # NEW
```

Wire into `results/page.tsx`:

```tsx
import { HistogramsCard } from "@/components/results/HistogramsCard";
// ...
<HistogramsCard taskId={taskId} totalRows={preview.total} />
```

Component fetches `/api/tasks/{taskId}/results/histogram?bins=20` on mount via the existing `api` client (extend `frontend/src/lib/api.ts` with `getResultsHistogram(taskId, bins?)`).

**Color:** bars use `fill="hsl(var(--chart-1))"` so dark-mode just works.

### B.3 State Map card

Position: **between Histograms and Download Results.**

Layout:

- Card shell same as above.
- Header: "Geographic Distribution".
- Toolbar row:
  - Value column dropdown (`<Select>` from shadcn) — options = numeric exposure cols from the histograms response (so we only fetch the list of cols once).
  - Mode toggle: `count | mean` — `<Tabs>` from shadcn or two `<Button variant="outline">` siblings.
- Map area:
  - `<ComposableMap projection="geoAlbersUsa" width={960} height={500}>`.
  - `<Geographies geography={topojsonUrl}>` then map each `geo` to `<Geography fill={colorFor(state_fips)} stroke="hsl(var(--border))" />`.
  - Hover: set state-level `<state name, count, mean>` into local state; render absolute-positioned tooltip div following the mouse.
- Color legend strip at the bottom: a horizontal `<svg>` gradient + 5 tick labels (min, p25, p50, p75, max of currently-selected metric).
- Loading skeleton: render `<Skeleton className="h-[500px] w-full" />` (use existing skeleton primitive or a `div` with `animate-pulse`) until both the topojson and the geo response have resolved.
- States with no data: fill `hsl(var(--muted))`.

**Color scale.** Hand-rolled HSL gradient — green (low) → yellow (mid) → red (high). For each state, normalize value to `t in [0, 1]` via `(value - min) / (max - min)` (clamped). Then:

```ts
function colorFor(t: number): string {
  // t in [0,1]; 0 = green (hue 120), 0.5 = yellow (hue 60), 1 = red (hue 0).
  const hue = 120 * (1 - t);
  return `hsl(${hue}, 65%, 50%)`;
}
```

No `d3-scale-chromatic` dep needed.

**Files.**

```
frontend/src/components/results/StateMapCard.tsx          # NEW
frontend/src/lib/result-columns.ts                        # NEW (also serves Histograms + Column Summary)
```

Wire into `results/page.tsx`:

```tsx
import { StateMapCard } from "@/components/results/StateMapCard";
// ...
<StateMapCard
  taskId={taskId}
  numericExposureCols={histogramCols /* hoisted from HistogramsCard or refetched */}
/>
```

To avoid two requests for the column list, hoist a `useResultsHistogram(taskId)` hook into the page and pass `numericExposureCols = data.histograms.map(h => h.name)` down to `<StateMapCard>`. Alternative: have `<StateMapCard>` issue its own `/histogram` request — simpler component boundary but extra fetch. **Decision: hoist** — keeps the page as the single fetch coordinator.

### B.4 Shared INPUT_COLUMNS module

```ts
// frontend/src/lib/result-columns.ts
/**
 * Columns produced by the cohort upload or geocoding — never an "exposure".
 * Mirrors backend/app/result_columns.py::INPUT_COLS.
 */
export const INPUT_COLUMNS: ReadonlySet<string> = new Set([
  "pid",
  "episode_id",
  "startDate",
  "endDate",
  "longitude",
  "latitude",
  "state_fips",
  "county_fips",
  "tract_geoid",
  "bg_geoid",
]);

export function isInputColumn(name: string): boolean {
  return INPUT_COLUMNS.has(name);
}
```

Refactor `results/page.tsx`:

- Delete the inline `INPUT_COLUMNS` Set at `:140-151`.
- Replace the `!INPUT_COLUMNS.has(col.name)` call site at `:300` with `!isInputColumn(col.name)`.

---

## Implementation order

Each step is a single commit unless noted.

1. **Backend — shared module.** Create `backend/app/result_columns.py`. Refactor `routers/tasks.py::results_preview` to import `INPUT_COLS` + pass `FIPS_DTYPE_MAP`. Run existing `test_results_preview` — should still pass; the FIPS column will now be classified as `categorical` not `numeric` (this is the bug fix — update the assertion if needed).
2. **Backend — histogram endpoint.** Add `/results/histogram` per A.1. Write `test_results_histogram` (see Tests below).
3. **Backend — geo endpoint.** Add `/results/geo` per A.2. Write `test_results_geo`.
4. **Frontend — shared input-cols module.** Create `frontend/src/lib/result-columns.ts`. Refactor `results/page.tsx`. Run `npx tsc --noEmit`.
5. **Frontend — install deps.** `npm install recharts react-simple-maps && npm install -D @types/react-simple-maps`. If CI is offline, document the install separately.
6. **Frontend — Histograms component.** Add `frontend/src/lib/api.ts::getResultsHistogram`. Add `HistogramsCard`. Wire into page. Run `npx tsc --noEmit` + visual smoke against a real completed task.
7. **Frontend — StateMap component.** Add `getResultsGeo`. Add `StateMapCard`. Hoist `useResultsHistogram` so the column list is shared. Visual smoke.
8. **Commit + push.** Two backend commits, one shared-frontend commit, two frontend feature commits, one push.

Estimated time: 1 day backend, 1.5 days frontend, 0.5 day smoke + polish.

---

## Tests

All four go in `backend/tests/test_tasks.py`, extending the `test_results_preview` setup pattern (lines 247–342). That pattern: monkeypatch `DATA_DIR` / `DB_PATH` / `TASKS_DIR`; reload `app.config`, `app.task_manager`, `app.main`; `create_app`; signup → token; create task; manually write `output/result.csv`.

### test_results_histogram (3 cases in one function, mirroring preview's style)

1. **404 before file exists.** Assert `GET /api/tasks/{id}/results/histogram` returns 404.
2. **Happy path.** Write a result.csv with the canonical prefix + two exposure cols (`ndi` continuous, `flag` binary). Assert response has `histograms.length == 1` (the `flag` skipped), `histograms[0].name == "ndi"`, `bins.length == 20` (default), `sum(bin.count for bin in bins) == sample_size`, `min/max` match input.
3. **Bins respected.** Re-fetch with `?bins=5` — assert `bins.length == 5` and `bins_requested == 5`.
4. **Input cols skipped.** Assert `state_fips` does not appear in `histograms` even though it's int64 with >2 unique values.

### test_results_histogram_validation

Boundary check on `bins`. `?bins=4` → 422. `?bins=51` → 422.

### test_results_geo

1. **404 before file exists.**
2. **Missing value_col.** `GET .../geo` without query → 422.
3. **Unknown col.** `?value_col=does_not_exist` → 400.
4. **Input col rejected.** `?value_col=state_fips` → 400.
5. **Happy path.** Result.csv with `state_fips` values `["12", "12", "06", "12"]` and `ndi` values `[1.0, 2.0, 3.0, NaN]`. Assert `by_state == [{state_fips: "06", count: 1, mean: 3.0}, {state_fips: "12", count: 2, mean: 1.5}]` (state `12`'s NaN row excluded; sorted by state_fips).
6. **FIPS zero-pad.** Write `state_fips` as `1` (int-style) for an Alabama row. Assert response surfaces `"01"` not `"1"` — guards the defensive `zfill(2)`.

### Frontend smoke checklist (manual, post-deploy)

- [ ] `npx tsc --noEmit` clean in `frontend/`.
- [ ] Open a completed task's results page → Histograms card renders one chart per exposure column.
- [ ] Switch to dark mode → bars still readable, map still readable.
- [ ] State Map: hover a state → tooltip shows correct count + mean.
- [ ] State Map: switch value-column dropdown → colors + legend update.
- [ ] State Map: toggle count↔mean → colors update; legend tick labels switch units.
- [ ] Open a task with `fara_tract` (all-binary cols) → Histograms card is hidden (or renders empty), no crash.
- [ ] Open a task with a single state in cohort → only that state colored, all others gray.

---

## Risks & mitigations

1. **FIPS leading-zero loss.** Pandas infers `state_fips` as int64 from disk. Mitigated by `FIPS_DTYPE_MAP` on every read AND defensive `.str.zfill(2)` in the geo endpoint. Tested by `test_results_geo` case 6.
2. **Topojson size + CDN dependency.** ~30KB gzip from `cdn.jsdelivr.net`. If CDN is blocked on a customer deployment, fall back to bundling — vendor `public/us-states-10m.json` and read from `/us-states-10m.json`. Document the fallback in a follow-up if it bites.
3. **US Albers projection clips Alaska + Hawaii.** `us-atlas/states-10m.json` ships them in standard offset positions (Albers USA composite); `react-simple-maps`'s `projection="geoAlbersUsa"` honors that. No special handling needed.
4. **Dark mode SVG fills.** Recharts: use `hsl(var(--chart-1))` strings — they'll resolve in both modes because `--chart-1` is defined per theme in `globals.css`. react-simple-maps: same trick on the no-data fill (`hsl(var(--muted))`) and the stroke (`hsl(var(--border))`).
5. **`npm install` HTTP timeout in CI.** Already documented in repo README. Sprint 13 adds 3 deps; mention in PR description so reviewers re-run if pull fails.
6. **`fara_tract` (binary flags) edge case.** Skipped via `nunique <= 2` filter in histogram endpoint. Map endpoint accepts them (still aggregatable as 0/1 mean). Acceptable — a "% flag" choropleth is meaningful.
7. **`vnl`'s generic `value` column name.** If a user ever combines `vnl` with another experiment that also outputs `value`, there's a collision. Out of scope for Sprint 13 (the multi-experiment pipeline doesn't merge by-column today — each variable lives in its own `result.csv` per task variant). File a follow-up if multi-variable result.csv ever lands.
8. **`nhd_bluespace` 99999 sentinel.** Will pull histograms' max to 99999 and distort the bins. Acceptable for Sprint 13 — the same distortion already shows up in Column Summary's `max`. A follow-up could special-case sentinels in `variable_metadata.json` but it's out of scope.
9. **Privacy at low N.** State-level aggregation rarely produces N < 5 cells (50 states, typical cohort 100s–1000s of rows). If we later add county / tract maps, we MUST add small-cell suppression. Out of scope.
10. **Reusing `/preview`'s `total_rows` for the Histograms card subhead.** If `/preview` and `/histogram` are fetched in parallel and `/histogram`'s `total_rows` differs (it won't — both read the same file — but if the file is rewritten between calls), the subhead could lag. Acceptable; client-side cache invalidation is out of scope.

---

## Open questions (to confirm during implementation)

- Should the histogram endpoint accept `?columns=ndi,NatWalkInd` to subset? **Decision: no for Sprint 13.** Single shot, all numeric exposure cols — simpler client, negligible payload (each histogram is ~bins\*3 numbers ≈ 240 bytes for default 20 bins).
- Should the map default to `count` mode or `mean` mode? **Decision: `count`.** It's the only mode that doesn't require picking a column first; the column dropdown only matters once user switches to `mean`. Actually re-decided: default `count`, but the dropdown is always visible since `mean` is what we ship the endpoint for. UI: count toggle is the left tab, mean is the right tab, default left.
- Should we cache `topojson` in localStorage across tasks? **Decision: no.** Browser HTTP cache + jsdelivr's long max-age covers it.

---

## Appendix — file inventory

### New files

- `backend/app/result_columns.py`
- `frontend/src/lib/result-columns.ts`
- `frontend/src/components/results/HistogramsCard.tsx`
- `frontend/src/components/results/StateMapCard.tsx`

### Modified files

- `backend/app/routers/tasks.py` — add `/results/histogram` + `/results/geo`; refactor `/results/preview` to import shared `INPUT_COLS` + use `FIPS_DTYPE_MAP`.
- `backend/tests/test_tasks.py` — add `test_results_histogram`, `test_results_histogram_validation`, `test_results_geo`.
- `frontend/src/app/dashboard/task/[id]/results/page.tsx` — delete inline `INPUT_COLUMNS`; import from new module; wire in two new cards; hoist `useResultsHistogram` to share column list with map.
- `frontend/src/lib/api.ts` — add `getResultsHistogram` + `getResultsGeo`.
- `frontend/package.json` + `package-lock.json` — add `recharts`, `react-simple-maps`, `@types/react-simple-maps`.

### Deleted files

None.
