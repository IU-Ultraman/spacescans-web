/**
 * Output level of a linkage task: what one row of result.csv stands for.
 *
 * "participant" (the default since phase D): one row per participant id in
 * the upload, each exposure averaged over all of that participant's location
 * episodes, weighted by the days that contribute a value. "episode": one row
 * per uploaded row (location episode), the shape every task had before.
 *
 * Kept free of React and of `@/` imports so scripts/*.test.mjs can load the
 * tsc-emitted JS directly (npm run check:lib).
 */
export type OutputLevel = "participant" | "episode";

export const OUTPUT_LEVELS: readonly OutputLevel[] = ["participant", "episode"];

export const DEFAULT_OUTPUT_LEVEL: OutputLevel = "participant";

export function isOutputLevel(value: unknown): value is OutputLevel {
  return value === "participant" || value === "episode";
}

/**
 * The level a task's results describe: the first valid candidate, in the
 * order given (results response first, then the task's saved config).
 * Results from before participant-level output existed carry no level and
 * were computed per location episode, so that is the fallback.
 */
export function resultLevel(...candidates: unknown[]): OutputLevel {
  for (const c of candidates) if (isOutputLevel(c)) return c;
  return "episode";
}

export const OUTPUT_LEVEL_INFO: Record<
  OutputLevel,
  { label: string; short: string; explain: string }
> = {
  participant: {
    label: "One row per participant",
    short: "per participant",
    explain:
      "Each exposure is averaged over all of a participant's location episodes, weighted by the days that contribute a value.",
  },
  episode: {
    label: "One row per location episode",
    short: "per location episode",
    explain:
      "One row for each row of your upload, with your own columns kept next to the exposures.",
  },
};

/** "participant(s)" or "location episode(s)". */
export function unitNoun(level: OutputLevel, count: number): string {
  const one = level === "participant" ? "participant" : "location episode";
  return count === 1 ? one : `${one}s`;
}

/** "1,234 participants" / "1 location episode". */
export function countLabel(level: OutputLevel, count: number): string {
  return `${count.toLocaleString("en-US")} ${unitNoun(level, count)}`;
}

/**
 * Whether the results map can be drawn. At episode level the server groups
 * result rows by their own state_fips column. At participant level result.csv
 * holds only pid and the exposures; the server places each participant in the
 * state of their longest location episode (ties: the most recent start), so
 * what matters is whether the uploaded cohort had a state_fips column.
 * Unknown columns (still loading, or a task without an upload summary) count
 * as present, so the map is not replaced by the explanation on every refresh.
 */
export function hasStateColumn(
  level: OutputLevel,
  resultColumns: readonly string[] | null | undefined,
  cohortColumns: readonly string[] | null | undefined,
): boolean {
  const columns = level === "participant" ? cohortColumns : resultColumns;
  return columns ? columns.includes("state_fips") : true;
}

/** Share of rows with a value (the linkage rate at the output's level), or
 *  null when there are no rows. */
export function linkageRate(summary: { non_null: number; null_count: number }): number | null {
  const total = summary.non_null + summary.null_count;
  return total > 0 ? summary.non_null / total : null;
}
