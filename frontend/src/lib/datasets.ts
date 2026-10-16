/**
 * Registered datasets ("My datasets"): the shapes /api/datasets returns
 * (PHASE_D §2.2) and the pure logic behind the upload form — dataset kinds and
 * their time structures, period dates read from file names, a CSV header
 * reader, the metadata JSON the form sends, and readers that accept either a
 * bare dataset or an envelope.
 *
 * `buildDatasetMetadata` is the ONE place the frontend decides the shape of
 * the kind-specific fields (`key`, `periods`, `variables[].band`); if the
 * backend settles on other names, change them here.
 *
 * Kept free of React and of `@/` imports so scripts/*.test.mjs can load the
 * tsc-emitted JS directly (npm run check:lib).
 */

export type DatasetKind = "polygon_table" | "raster" | "features";
export type DatasetTemporal = "static" | "yearly" | "biweekly" | "daily";
export type DatasetVisibility = "private" | "deployment";
export type BoundaryLayer = "Tract" | "BG" | "ZCTA5" | "County";
export type LinkMethod = "areal" | "grid" | "proximity";

export interface DatasetVariable {
  name: string;
  unit?: string | null;
  description?: string | null;
  /** Raster datasets: the 1-based band this variable is read from. */
  band?: number | null;
}

/** How a record is located: the area code column and its geography (area
 *  tables), and the column holding the year or date (time-varying tables, or
 *  features with a year attribute). */
export interface DatasetKey {
  geography?: string;
  column?: string;
  time_column?: string;
}

export interface RegisteredDataset {
  id: string;
  name: string;
  kind: DatasetKind;
  temporal: DatasetTemporal;
  variables: DatasetVariable[];
  visibility: DatasetVisibility;
  owned_by_me: boolean;
  owner_display?: string | null;
  created_at?: string | null;
  /** Absent or e.g. "ready" = usable; see isPending / isFailed. */
  status?: string | null;
  // Detail fields (GET /api/datasets/{id}); optional in the list.
  key?: DatasetKey | string | null;
  source?: string | null;
  version?: string | null;
  description?: string | null;
  license_note?: string | null;
  files?: string[] | null;
  checksum?: string | null;
  spacescans_version?: string | null;
  created_utc?: string | null;
}

// ------------------------------------------------------------- vocabulary ---

export const DATASET_KINDS: readonly DatasetKind[] = ["polygon_table", "raster", "features"];

export const KIND_INFO: Record<
  DatasetKind,
  { label: string; short: string; blurb: string; accept: string; method: LinkMethod; linkedAs: string }
> = {
  polygon_table: {
    label: "Area table (CSV)",
    short: "Area table",
    blurb: "Values per census tract, block group, ZCTA or county.",
    accept: ".csv,.txt",
    method: "areal",
    linkedAs: "Area-weighted mean of the census areas the buffer overlaps",
  },
  raster: {
    label: "Raster (GeoTIFF)",
    short: "Raster",
    blurb: "A grid of values: one GeoTIFF, or one per period on a common grid.",
    accept: ".tif,.tiff",
    method: "grid",
    linkedAs: "Coverage-weighted mean of the raster cells under the buffer",
  },
  features: {
    label: "Features (points, lines or polygons)",
    short: "Features",
    blurb: "Your own map features, linked as the distance to the nearest one.",
    accept: ".gpkg,.geojson,.json,.zip",
    method: "proximity",
    linkedAs: "Distance in metres from the location to the nearest feature (no buffer)",
  },
};

export const TEMPORAL_BY_KIND: Record<DatasetKind, readonly DatasetTemporal[]> = {
  polygon_table: ["static", "yearly", "daily"],
  raster: ["static", "yearly", "biweekly", "daily"],
  features: ["static", "yearly"],
};

export const TEMPORAL_LABEL: Record<DatasetTemporal, string> = {
  static: "Time-invariant",
  yearly: "Yearly",
  biweekly: "Biweekly",
  daily: "Daily",
};

/** What one upload of this kind and time structure consists of. */
export function temporalHint(kind: DatasetKind, temporal: DatasetTemporal): string {
  if (kind === "polygon_table") {
    if (temporal === "yearly") return "one row per area and year (a year column)";
    if (temporal === "daily") return "one row per area and day (a date column)";
    return "one value per area";
  }
  if (kind === "raster") {
    if (temporal === "yearly") return "one GeoTIFF per year";
    if (temporal === "biweekly") return "one GeoTIFF per two-week period";
    if (temporal === "daily") return "one GeoTIFF per day";
    return "one GeoTIFF";
  }
  if (temporal === "yearly") return "one file per year, or one file with a year column";
  return "one file";
}

/** How a location episode meets the data's time structure. */
export function matchingNote(temporal: DatasetTemporal): string {
  if (temporal === "static") {
    return "The same values apply to every location episode, whatever its dates.";
  }
  const unit = temporal === "yearly" ? "years" : temporal === "biweekly" ? "two-week periods" : "days";
  return `Each location episode is matched to the ${unit} it overlaps and averaged by the days in each.`;
}

export const BOUNDARY_LAYERS: readonly { value: BoundaryLayer; label: string; keyLen: number }[] = [
  { value: "Tract", label: "Census tract", keyLen: 11 },
  { value: "BG", label: "Block group", keyLen: 12 },
  { value: "ZCTA5", label: "ZCTA (ZIP code area)", keyLen: 5 },
  { value: "County", label: "County", keyLen: 5 },
];

export function boundaryLabel(value: string | undefined | null): string {
  return BOUNDARY_LAYERS.find((b) => b.value === value)?.label ?? String(value ?? "");
}

// ---------------------------------------------------------------- limits ---

export const MAX_NAME = 80;
export const MAX_DESCRIPTION = 400;
export const MAX_SHORT_FIELD = 200;
export const MAX_VARIABLES = 40;
export const MAX_VARIABLE_NAME = 40;
export const VARIABLE_NAME = /^[A-Za-z][A-Za-z0-9_]*$/;

/** Columns result.csv or the runner already uses (compared ignoring case). */
export const RESERVED_COLUMNS: ReadonlySet<string> = new Set(
  [
    "pid", "patid", "episode_id", "startDate", "endDate", "longitude", "latitude",
    "state_fips", "county_fips", "tract_geoid", "bg_geoid", "geoid", "grid_id", "year",
  ].map((c) => c.toLowerCase()),
);

/** Why a dataset name would be refused, or null. */
export function nameProblem(name: string): string | null {
  const n = name.trim();
  if (!n) return "Give the dataset a name.";
  if (n.length > MAX_NAME) return `Use at most ${MAX_NAME} characters.`;
  return null;
}

/**
 * Why a result-column name would be refused, or null. `strict` (rasters and
 * features, whose names the user types) also requires an identifier; area
 * tables keep their CSV headers as they are, as before.
 */
export function variableNameProblem(name: string, others: readonly string[], strict: boolean): string | null {
  const n = name.trim();
  if (!n) return "Give the column a name.";
  if (strict && !VARIABLE_NAME.test(n)) return "Start with a letter; use only letters, digits and underscores.";
  if (strict && n.length > MAX_VARIABLE_NAME) return `Use at most ${MAX_VARIABLE_NAME} characters.`;
  if (RESERVED_COLUMNS.has(n.toLowerCase())) return `"${n}" is already a column of the results.`;
  if (others.some((o) => o.trim().toLowerCase() === n.toLowerCase())) {
    return "Another column has this name (names are compared ignoring case).";
  }
  return null;
}

/** `<name>_dist_m`, the default result column of a features dataset. */
export function defaultDistanceName(datasetName: string): string {
  let s = datasetName
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, MAX_VARIABLE_NAME - "_dist_m".length);
  s = s.replace(/_+$/g, "");
  if (!s) return "feature_dist_m";
  if (!/^[a-z]/.test(s)) s = `f_${s}`.slice(0, MAX_VARIABLE_NAME - "_dist_m".length).replace(/_+$/g, "");
  return `${s}_dist_m`;
}

// --------------------------------------------------- dates in file names ---

function isoDate(y: number, m: number, d: number): string | null {
  if (y < 1900 || y > 2100 || m < 1 || m > 12 || d < 1) return null;
  const dt = new Date(Date.UTC(y, m - 1, d));
  if (dt.getUTCFullYear() !== y || dt.getUTCMonth() !== m - 1 || dt.getUTCDate() !== d) return null;
  return dt.toISOString().slice(0, 10);
}

function dayOfYear(y: number, doy: number): string | null {
  if (y < 1900 || y > 2100 || doy < 1) return null;
  const dt = new Date(Date.UTC(y, 0, doy));
  if (dt.getUTCFullYear() !== y) return null;
  return dt.toISOString().slice(0, 10);
}

/** The stem of a file name: no directory, no extension. */
function stem(filename: string): string {
  const base = filename.split(/[\\/]/).pop() ?? filename;
  return base.replace(/\.[A-Za-z0-9]+$/, "");
}

/** The first four-digit year (1900-2099) in a file name, preferring one not
 *  embedded in a longer number. */
export function yearFromFilename(filename: string): number | null {
  const s = stem(filename);
  const m = s.match(/(?<!\d)(?:19|20)\d{2}(?!\d)/) ?? s.match(/(?:19|20)\d{2}/);
  return m ? Number(m[0]) : null;
}

/**
 * Every date in a file name, left to right: 2014-01-31 (also with _ or . as
 * separator), 20140131, or a year plus day of year, 2014031 (the ACAG style
 * "2014001-2014014"). Tokens that are not real dates are skipped.
 */
export function datesFromFilename(filename: string): string[] {
  const s = stem(filename);
  const re = /(?<!\d)(?:(\d{4})([-_.])(\d{2})\2(\d{2})|(\d{4})(\d{2})(\d{2})|(\d{4})(\d{3}))(?!\d)/g;
  const out: string[] = [];
  let m: RegExpExecArray | null;
  while ((m = re.exec(s)) !== null) {
    let iso: string | null = null;
    if (m[1]) iso = isoDate(Number(m[1]), Number(m[3]), Number(m[4]));
    else if (m[5]) iso = isoDate(Number(m[5]), Number(m[6]), Number(m[7]));
    else if (m[8]) iso = dayOfYear(Number(m[8]), Number(m[9]));
    if (iso) out.push(iso);
  }
  return out;
}

/** A date shifted by whole days (UTC, ISO in and out). */
export function addDays(iso: string, days: number): string {
  const dt = new Date(`${iso}T00:00:00Z`);
  dt.setUTCDate(dt.getUTCDate() + days);
  return dt.toISOString().slice(0, 10);
}

/** True for a real calendar date written YYYY-MM-DD. */
export function isIsoDate(value: string): boolean {
  const m = value.trim().match(/^(\d{4})-(\d{2})-(\d{2})$/);
  return !!m && isoDate(Number(m[1]), Number(m[2]), Number(m[3])) !== null;
}

/**
 * First guess at a file's period, from its name. Yearly: the year. Daily:
 * the first date (the period is that day). Biweekly: the first date as the
 * start and a second, later date as the end, else 13 days after the start
 * (a 14-day period); the form shows both so the user can correct them.
 */
export function guessPeriod(
  filename: string,
  temporal: DatasetTemporal,
): { year: string; start: string; end: string } {
  if (temporal === "yearly") {
    const y = yearFromFilename(filename);
    return { year: y === null ? "" : String(y), start: "", end: "" };
  }
  if (temporal === "static") return { year: "", start: "", end: "" };
  const dates = datesFromFilename(filename);
  const start = dates[0] ?? "";
  if (temporal === "daily") return { year: "", start, end: start };
  const later = dates.slice(1).find((d) => d > start);
  return { year: "", start, end: later ?? (start ? addDays(start, 13) : "") };
}

// ------------------------------------------------------------ CSV header ---

export interface CsvHead {
  columns: string[];
  /** Up to maxRows data rows, each padded/truncated to the header width. */
  rows: string[][];
}

/**
 * Header and first rows of a CSV, read in the browser (no upload needed to
 * offer the column choices). RFC 4180 quoting; a BOM and CRLF are fine.
 * `complete` says whether `text` is the whole file; if not, the last record
 * may be cut off and is dropped.
 */
export function parseCsvHead(text: string, maxRows = 50, complete = true): CsvHead {
  const src = text.charCodeAt(0) === 0xfeff ? text.slice(1) : text;
  const records: string[][] = [];
  let field = "";
  let record: string[] = [];
  let inQuotes = false;
  let ended = true; // the text so far ends on a record boundary
  for (let i = 0; i < src.length && records.length <= maxRows; i++) {
    const ch = src[i];
    ended = false;
    if (inQuotes) {
      if (ch === '"') {
        if (src[i + 1] === '"') {
          field += '"';
          i++;
        } else {
          inQuotes = false;
        }
      } else {
        field += ch;
      }
      continue;
    }
    if (ch === '"') {
      inQuotes = true;
    } else if (ch === ",") {
      record.push(field);
      field = "";
    } else if (ch === "\n" || ch === "\r") {
      if (ch === "\r" && src[i + 1] === "\n") i++;
      record.push(field);
      records.push(record);
      record = [];
      field = "";
      ended = true;
    } else {
      field += ch;
    }
  }
  if (!ended && records.length <= maxRows) {
    // A trailing record without a final newline: whole only if the file is.
    if (complete && !inQuotes) {
      record.push(field);
      records.push(record);
    }
  }
  const nonEmpty = records.filter((r) => !(r.length === 1 && r[0].trim() === ""));
  if (nonEmpty.length === 0) return { columns: [], rows: [] };
  const columns = nonEmpty[0].map((c) => c.trim());
  const rows = nonEmpty
    .slice(1, maxRows + 1)
    .map((r) => columns.map((_, j) => (r[j] ?? "").trim()));
  return { columns, rows };
}

const BLANK = new Set(["", "na", "n/a", "nan", "null", "none", "."]);
const NUMBER = /^[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?$/;

export interface ColumnProfile {
  name: string;
  /** Share of non-blank sample values that parse as numbers (0 if all blank). */
  numericShare: number;
  allYears: boolean;
  allDates: boolean;
}

export function profileColumns(head: CsvHead): ColumnProfile[] {
  return head.columns.map((name, j) => {
    const values = head.rows.map((r) => r[j] ?? "").filter((v) => !BLANK.has(v.toLowerCase()));
    const n = values.length;
    const numeric = values.filter((v) => NUMBER.test(v)).length;
    return {
      name,
      numericShare: n ? numeric / n : 0,
      allYears: n > 0 && values.every((v) => /^(?:19|20)\d{2}$/.test(v)),
      allDates: n > 0 && values.every((v) => isIsoDate(v)),
    };
  });
}

/** First guesses the user can correct: the area-code column, and the year or
 *  date column of a time-varying table. */
export function guessColumns(
  profiles: readonly ColumnProfile[],
  temporal: DatasetTemporal,
): { key: string; time: string } {
  const key =
    profiles.find((p) => /^(geoid|fips|tract|bg|zcta|zip|county|geo)/i.test(p.name))?.name ?? "";
  let time = "";
  if (temporal === "yearly") {
    time = profiles.find((p) => /^year$/i.test(p.name))?.name ?? profiles.find((p) => p.allYears)?.name ?? "";
  } else if (temporal === "daily") {
    time = profiles.find((p) => /^(date|day)$/i.test(p.name))?.name ?? profiles.find((p) => p.allDates)?.name ?? "";
  }
  return { key: key === time ? "" : key, time };
}

// -------------------------------------------------------------- metadata ---

export interface DatasetDescription {
  name: string;
  temporal: DatasetTemporal;
  source?: string;
  version?: string;
  description?: string;
  license_note?: string;
  visibility: DatasetVisibility;
}

export interface TableSpec {
  kind: "polygon_table";
  geography: BoundaryLayer;
  keyColumn: string;
  /** Year (yearly) or date (daily) column; ignored when static. */
  timeColumn?: string | null;
  variables: { name: string; unit?: string; description?: string }[];
}

export interface RasterFileSpec {
  file: string;
  /** Yearly. */
  year?: string;
  /** Biweekly and daily, YYYY-MM-DD. */
  start?: string;
  end?: string;
}

export interface RasterSpec {
  kind: "raster";
  files: RasterFileSpec[];
  variables: { name: string; band: number; unit?: string; description?: string }[];
}

export interface FeaturesSpec {
  kind: "features";
  /** Yearly only: one file per year, or one file with a year attribute. */
  yearly?: { mode: "files"; files: { file: string; year: string }[] } | { mode: "column"; column: string };
  variable: { name: string; description?: string };
}

export type DatasetSpec = TableSpec | RasterSpec | FeaturesSpec;

export interface DatasetPeriod {
  file: string;
  year?: number;
  start?: string;
  end?: string;
}

/** The `metadata` part of POST /api/datasets. */
export interface DatasetMetadata {
  name: string;
  kind: DatasetKind;
  temporal: DatasetTemporal;
  key?: DatasetKey;
  variables: DatasetVariable[];
  periods?: DatasetPeriod[];
  source?: string;
  version?: string;
  description?: string;
  license_note?: string;
  visibility: DatasetVisibility;
}

function trimmed(value: string | undefined | null): string | undefined {
  const t = (value ?? "").trim();
  return t ? t : undefined;
}

function variable(name: string, unit?: string | null, description?: string | null): DatasetVariable {
  const v: DatasetVariable = { name: name.trim() };
  const u = trimmed(unit);
  const d = trimmed(description);
  if (u) v.unit = u;
  if (d) v.description = d;
  return v;
}

/** The metadata JSON for a new dataset. Optional text fields are trimmed and
 *  left out when empty. */
export function buildDatasetMetadata(desc: DatasetDescription, spec: DatasetSpec): DatasetMetadata {
  const meta: DatasetMetadata = {
    name: desc.name.trim(),
    kind: spec.kind,
    temporal: desc.temporal,
    variables: [],
    visibility: desc.visibility,
  };
  for (const field of ["source", "version", "description", "license_note"] as const) {
    const v = trimmed(desc[field]);
    if (v) meta[field] = v;
  }

  if (spec.kind === "polygon_table") {
    const key: DatasetKey = { geography: spec.geography, column: spec.keyColumn };
    if (desc.temporal !== "static" && trimmed(spec.timeColumn)) key.time_column = spec.timeColumn!.trim();
    meta.key = key;
    meta.variables = spec.variables.map((v) => variable(v.name, v.unit, v.description));
  } else if (spec.kind === "raster") {
    meta.variables = spec.variables.map((v) => ({ ...variable(v.name, v.unit, v.description), band: v.band }));
    if (desc.temporal === "yearly") {
      meta.periods = spec.files.map((f) => ({ file: f.file, year: Number((f.year ?? "").trim()) }));
    } else if (desc.temporal === "biweekly" || desc.temporal === "daily") {
      meta.periods = spec.files.map((f) => {
        const start = (f.start ?? "").trim();
        const end = desc.temporal === "daily" ? start : (f.end ?? "").trim();
        return { file: f.file, start, end };
      });
    }
  } else {
    meta.variables = [variable(spec.variable.name, "m", spec.variable.description)];
    if (desc.temporal === "yearly" && spec.yearly) {
      if (spec.yearly.mode === "files") {
        meta.periods = spec.yearly.files.map((f) => ({ file: f.file, year: Number(f.year.trim()) }));
      } else {
        meta.key = { time_column: spec.yearly.column.trim() };
      }
    }
  }
  return meta;
}

/** Problems with a raster's per-file periods, or [] when they are usable. */
export function periodProblems(files: readonly RasterFileSpec[], temporal: DatasetTemporal): string[] {
  const problems: string[] = [];
  if (files.length === 0) return ["Choose at least one file."];
  if (temporal === "static") {
    if (files.length > 1) problems.push("A time-invariant raster is one file.");
    return problems;
  }
  if (temporal === "yearly") {
    if (!files.every((f) => /^(?:19|20)\d{2}$/.test((f.year ?? "").trim()))) {
      problems.push("Give every file a four-digit year.");
    } else if (new Set(files.map((f) => f.year!.trim())).size !== files.length) {
      problems.push("Two files have the same year.");
    }
    return problems;
  }
  if (!files.every((f) => isIsoDate(f.start ?? ""))) {
    problems.push("Give every file a start date (YYYY-MM-DD).");
    return problems;
  }
  if (new Set(files.map((f) => f.start!.trim())).size !== files.length) {
    problems.push("Two files have the same start date.");
  }
  if (temporal === "biweekly") {
    if (!files.every((f) => isIsoDate(f.end ?? ""))) {
      problems.push("Give every file an end date (YYYY-MM-DD).");
    } else if (files.some((f) => f.end!.trim() < f.start!.trim())) {
      problems.push("An end date is before its start date.");
    } else {
      const sorted = [...files].sort((a, b) => a.start!.localeCompare(b.start!));
      for (let i = 1; i < sorted.length; i++) {
        if (sorted[i].start!.trim() <= sorted[i - 1].end!.trim()) {
          problems.push("Two periods overlap.");
          break;
        }
      }
    }
  }
  return problems;
}

// ---------------------------------------------------- reading the API ---

const PENDING = new Set(["preparing", "pending", "processing", "queued", "registering", "validating"]);
const FAILED = new Set(["failed", "error", "invalid"]);

export function isPending(d: Pick<RegisteredDataset, "status">): boolean {
  return !!d.status && PENDING.has(d.status.toLowerCase());
}

export function isFailed(d: Pick<RegisteredDataset, "status">): boolean {
  return !!d.status && FAILED.has(d.status.toLowerCase());
}

/** Whether a task can use it now. */
export function isSelectable(d: Pick<RegisteredDataset, "status">): boolean {
  return !isPending(d) && !isFailed(d);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function asVariables(value: unknown): DatasetVariable[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((v) => {
    if (typeof v === "string") return [{ name: v }];
    if (isRecord(v) && typeof v.name === "string") return [v as unknown as DatasetVariable];
    return [];
  });
}

/** One dataset from a response that is either the dataset or `{dataset}`. */
export function unwrapDataset(raw: unknown): RegisteredDataset {
  const obj = isRecord(raw) && isRecord(raw.dataset) ? raw.dataset : raw;
  if (!isRecord(obj) || typeof obj.id !== "string") {
    throw new Error("The server's reply did not describe a dataset.");
  }
  return {
    ...(obj as unknown as RegisteredDataset),
    name: typeof obj.name === "string" ? obj.name : obj.id,
    variables: asVariables(obj.variables),
    visibility: obj.visibility === "deployment" ? "deployment" : "private",
    owned_by_me: obj.owned_by_me === true,
    created_at:
      (typeof obj.created_at === "string" && obj.created_at) ||
      (typeof obj.created_utc === "string" && obj.created_utc) ||
      null,
  };
}

/** The list from GET /api/datasets: a bare array or `{datasets: [...]}`. */
export function normalizeDatasetList(raw: unknown): RegisteredDataset[] {
  const items = Array.isArray(raw) ? raw : isRecord(raw) && Array.isArray(raw.datasets) ? raw.datasets : null;
  if (!items) throw new Error("The server's reply did not list datasets.");
  return items.flatMap((item) => {
    try {
      return [unwrapDataset(item)];
    } catch {
      return [];
    }
  });
}

/** Own datasets first, then shared ones; each group newest first, then by name. */
export function sortDatasets(list: readonly RegisteredDataset[]): RegisteredDataset[] {
  return [...list].sort((a, b) => {
    if (a.owned_by_me !== b.owned_by_me) return a.owned_by_me ? -1 : 1;
    const t = (b.created_at ?? "").localeCompare(a.created_at ?? "");
    return t !== 0 ? t : a.name.localeCompare(b.name);
  });
}

/** The fields of an edit that differ from the dataset (PATCH body). */
export function metadataPatch(
  before: RegisteredDataset,
  after: {
    name: string;
    description: string;
    source: string;
    version: string;
    license_note: string;
    variables: DatasetVariable[];
  },
): Record<string, unknown> {
  const patch: Record<string, unknown> = {};
  const norm = (v: string | null | undefined) => (v ?? "").trim();
  if (norm(after.name) !== norm(before.name)) patch.name = after.name.trim();
  for (const field of ["description", "source", "version", "license_note"] as const) {
    if (norm(after[field]) !== norm(before[field])) patch[field] = after[field].trim();
  }
  const vars = after.variables.map((v) => {
    const out: DatasetVariable = { name: v.name };
    out.unit = norm(v.unit) || null;
    out.description = norm(v.description) || null;
    if (v.band != null) out.band = v.band;
    return out;
  });
  const changed = vars.some((v, i) => {
    const b = before.variables[i];
    return !b || norm(b.unit) !== norm(v.unit) || norm(b.description) !== norm(v.description);
  });
  if (changed || vars.length !== before.variables.length) patch.variables = vars;
  return patch;
}
