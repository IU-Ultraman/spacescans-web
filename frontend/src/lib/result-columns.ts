/**
 * Columns produced by the cohort upload or by geocoding — never an "exposure"
 * computed by the pipeline. Mirrors `backend/app/task_manager.py::INPUT_COLS`
 * so the frontend agrees with the backend on what to skip in histograms /
 * choropleths / column-summary stats.
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
