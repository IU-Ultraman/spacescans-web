import {
  normalizeDatasetList,
  unwrapDataset,
  type DatasetMetadata,
  type RegisteredDataset,
} from "./datasets";
import type { OutputLevel } from "./output-level";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
    /** Itemised validation problems (e.g. a dataset upload's `issues[]`). */
    public issues: string[] = [],
  ) {
    super(detail);
  }
}

export interface ErrorDescription {
  message: string;
  issues: string[];
}

function issueText(issue: unknown): string | null {
  if (typeof issue === "string") return issue.trim() || null;
  if (!issue || typeof issue !== "object") return null;
  const o = issue as Record<string, unknown>;
  const msg = [o.message, o.msg, o.detail, o.error].find(
    (v): v is string => typeof v === "string" && v.trim() !== "",
  );
  if (!msg) return null;
  let where = "";
  if (typeof o.field === "string" && o.field) where = o.field;
  else if (Array.isArray(o.loc)) where = o.loc.filter((p) => p !== "body").join(".");
  return where ? `${where}: ${msg}` : msg;
}

/**
 * A readable message (and the itemised issues, if any) from an error body.
 * FastAPI puts whatever `HTTPException(detail=...)` carried under "detail" —
 * a string, an object such as `{detail, issues[]}` or `{error, message}`, or,
 * for a 422, a list of `{loc, msg}` — and a JSONResponse may put `issues`
 * next to `detail`. The UI must never show "[object Object]".
 */
export function describeError(body: unknown, fallback: string): ErrorDescription {
  if (typeof body === "string") return { message: body.trim() || fallback, issues: [] };
  if (!body || typeof body !== "object" || Array.isArray(body)) return { message: fallback, issues: [] };
  const top = body as Record<string, unknown>;
  const inner =
    top.detail && typeof top.detail === "object" && !Array.isArray(top.detail)
      ? (top.detail as Record<string, unknown>)
      : null;
  const src = inner ?? top;
  const rawIssues = Array.isArray(src.issues)
    ? src.issues
    : Array.isArray(top.issues)
      ? top.issues
      : Array.isArray(top.detail)
        ? top.detail
        : [];
  let issues = rawIssues.map(issueText).filter((t): t is string => !!t);
  let message = [src.detail, src.message, src.error, top.error].find(
    (v): v is string => typeof v === "string" && v.trim() !== "",
  );
  if (!message) {
    if (issues.length === 1) {
      message = issues[0];
      issues = [];
    } else {
      message = issues.length ? "Please correct the following:" : fallback;
    }
  }
  return { message, issues: issues.filter((t) => t !== message) };
}

/** The body of a response as JSON; null when empty (204) or not JSON. */
async function readJson(res: Response): Promise<unknown> {
  const text = await res.text().catch(() => "");
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

function getAuthHeaders(): Record<string, string> {
  const token =
    typeof window !== "undefined" ? localStorage.getItem("token") : null;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** Clear the stored session and bounce to /login. Called from every 401 path
 * (fetch + the XHR upload) so an expired/invalid token never strands the user
 * on a half-broken authenticated page (#5). */
function handleUnauthorized(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem("token");
  localStorage.removeItem("email");
  if (window.location.pathname !== "/login") {
    window.location.href = "/login";
  }
}

/** Download an authenticated endpoint to a file.
 *
 * A plain `<a href>` / `window.open()` is a browser navigation, which cannot
 * carry the `Authorization` header (the JWT lives in localStorage, not a
 * cookie) — the API answered those with 401 {"detail":"Not authenticated"}.
 * So fetch with the header, then hand the blob to a synthetic anchor. */
async function downloadFile(path: string, filename: string): Promise<void> {
  const res = await fetch(`${API_BASE}${path}`, { headers: getAuthHeaders() });

  if (res.status === 401) {
    handleUnauthorized();
    throw new ApiError(401, "Unauthorized");
  }
  if (!res.ok) {
    const d = describeError(await readJson(res), "Download failed");
    throw new ApiError(res.status, d.message, d.issues);
  }

  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/** POST a FormData body. Content-Type is deliberately NOT set: the browser has
 *  to add it itself so the multipart boundary is correct. */
async function requestMultipart<T>(path: string, body: FormData): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: getAuthHeaders(),
    body,
  });
  if (res.status === 401) {
    handleUnauthorized();
    throw new ApiError(401, "Unauthorized");
  }
  if (!res.ok) {
    const d = describeError(await readJson(res), res.statusText || "Upload failed");
    throw new ApiError(res.status, d.message, d.issues);
  }
  return (await readJson(res)) as T;
}

/**
 * Send a FormData body with XMLHttpRequest rather than fetch, so the caller
 * can show upload progress (rasters and daily tables can be large).
 */
function xhrMultipart<T>(
  method: string,
  path: string,
  form: FormData,
  onProgress?: (pct: number) => void,
): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(method, `${API_BASE}${path}`);
    for (const [k, v] of Object.entries(getAuthHeaders())) xhr.setRequestHeader(k, v);
    xhr.upload.onprogress = (e) => {
      if (onProgress && e.lengthComputable && e.total > 0) {
        onProgress(Math.round((e.loaded / e.total) * 100));
      }
    };
    xhr.onload = () => {
      let body: unknown = null;
      try {
        body = xhr.responseText ? JSON.parse(xhr.responseText) : null;
      } catch {
        body = null;
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(body as T);
        return;
      }
      if (xhr.status === 401) handleUnauthorized();
      const d = describeError(
        body,
        xhr.status === 413 ? "The files are larger than this server accepts." : "Upload failed",
      );
      reject(new ApiError(xhr.status, d.message, d.issues));
    };
    xhr.onerror = () => reject(new ApiError(0, "Network error during upload"));
    xhr.send(form);
  });
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...getAuthHeaders(),
      ...options.headers,
    },
  });

  if (res.status === 401) {
    handleUnauthorized();
    throw new ApiError(401, "Unauthorized");
  }

  if (!res.ok) {
    // detail may be a structured object ({error, message, ...}) — FastAPI
    // allows any JSON there and our data pre-flights use that form.
    const d = describeError(await readJson(res), "Request failed");
    throw new ApiError(res.status, d.message, d.issues);
  }

  // A DELETE may answer 204 with no body.
  return (await readJson(res)) as T;
}

export interface Task {
  id: string;
  task_name: string;
  status: "not_started" | "queued" | "running" | "finished" | "error" | "cancelled";
  progress?: number;
  created_at: string;
  error_message?: string;
  /** 1-based position in the global serial queue (present only when status is "queued"). */
  queue_position?: number | null;
  /** True when a not_started task is old enough to be cleanup-eligible (#3). */
  stale?: boolean;
  variables?: string[];
  /** Spatial buffer from the saved config (radius + raster grid in meters). */
  buffer?: { size: number; raster_res_m: number } | null;
  /** Summary of the uploaded cohort (from meta.json). */
  data_summary?: {
    row_count: number;
    columns: string[];
    date_range?: { min: string; max: string };
  } | null;
  /** From the saved config, when the server reports it (phase D). */
  output_level?: OutputLevel | null;
  /** Ids of the registered datasets the task links, when reported. */
  custom_datasets?: unknown[] | null;
}

/** What the wizard saves with PUT /api/tasks/{id}/config. Catalog variables
 *  go in `variables`; the user's registered datasets go by id in
 *  `custom_datasets` (the server snapshots their definitions). */
export interface TaskConfigInput {
  buffer: { size: number; raster_res_m: number };
  variables: string[];
  output_level: OutputLevel;
  custom_datasets: string[];
}

/**
 * A single log line emitted by the backend pipeline.
 *
 * The backend writes each `logs.jsonl` row with a `source` field
 * identifying which subprocess produced the line ("runner" for the
 * top-level orchestrator, or one of the variable steps).
 */
export interface LogEntry {
  ts: string;
  level: string;
  msg: string;
  /** "runner" | "c3_bg" | "c4_ndi" | "c4_wi" */
  source?: string;
}

/**
 * Raw status payload returned by `GET /api/tasks/{id}/status`.
 *
 * The backend writes this from `_write_status` (see
 * backend/app/experiments/bg_ndi_wi.py). Fields beyond `status` /
 * `progress` / `message` are optional so payloads from older runs
 * (or non-experiment task flows) still parse.
 */
export interface TaskStatus {
  status: "not_started" | "queued" | "running" | "finished" | "error" | "cancelled";
  progress?: number;
  message?: string;
  /** 1-based position in the global serial queue (present only when status is "queued"). */
  queue_position?: number | null;
  /** Currently executing step name (e.g. "csv_to_parquet", "c3_bg", "c4_ndi", "c4_wi", "merge"). */
  current_step?: string;
  /** Total number of variable pipeline steps (excludes csv_to_parquet and merge). */
  total_steps?: number;
  /** Ordered list of variable pipeline step names, written once at run start. */
  steps?: string[];
  started_at?: string;
  pid?: number;
}

export interface VarCoverage {
  coverage_years: [number, number];
  patients_in_time_window: number;
  patients_in_region: number;
  patients_covered: number;
  coverage_pct: number;
  warnings: string[];
  boundary: 'Point' | 'BG' | 'ZCTA5' | 'Tract' | 'County';
  display_unit: string;
  /** "static" products carry one vintage and skip the time-window check. */
  temporal?: 'static' | 'yearly';
}

/** A custom exposome: a user's own area-level values, uploaded as a CSV and
 *  attached to a boundary layer the deployment already provisions. Shaped like
 *  a catalog entry so it renders next to the shipped variables, plus the fields
 *  the library UI needs. It never carries an ontology_id — custom exposomes
 *  have no ontology node, which is why they get their own block in the wizard
 *  rather than appearing in the tree. */
export interface CustomRasterFile {
  year: number | null;
  uploaded_filename: string;
  sha256: string;
  bytes: number;
}

export interface CustomRasterGrid {
  width: number;
  height: number;
  crs: string;
  resolution: [number, number];
  resolution_label: string;
  nodata: number | null;
  bounds_wgs84: [number, number, number, number];
}

export interface CustomExposome extends VariableMetadata {
  /** polygon: a CSV on a Census geography; raster: the user's own GeoTIFF grid. */
  geometry: 'polygon' | 'raster';
  dataset_id: string;
  variable_key: string;
  /** The user's own geography column in their CSV. */
  key_col: string;
  /** The weights-table column it joins to, e.g. GEOID10. */
  join_col: string;
  year_col: string | null;
  value_labels: Record<string, string>;
  /** Per value column; the dataset-level display_unit is a derived summary. */
  value_units: Record<string, string>;
  row_count: number;
  distinct_keys: number;
  uploaded_filename: string;
  created_at: string;
  /** raster only */
  rasters?: CustomRasterFile[];
  /** Parallel to value_cols: the band each result column is read from. */
  bands?: number[];
  /** First band; the only band field on datasets saved before multi-band. */
  band?: number;
  grid?: CustomRasterGrid;
}

export interface CustomRasterPreview extends CustomRasterGrid {
  cells: number;
  band_count: number;
  bands: { index: number; description: string; dtype: string; nodata: number | null }[];
  grid_hash: string;
  filename: string;
  bytes: number;
}

export interface CreateCustomRasterInput {
  /** One file with year null = time-invariant; several, each with a year. */
  files: { file: File; year: number | null }[];
  name: string;
  /** One result column per band; value_cols is parallel to bands. */
  bands: number[];
  value_cols: string[];
  description?: string;
  /** Keyed by column name. */
  value_labels?: Record<string, string>;
  value_units?: Record<string, string>;
}

export interface CustomBoundary {
  boundary: 'BG' | 'ZCTA5' | 'Tract' | 'County';
  label: string;
  join_col: string;
  key_len: number;
  /** False when this deployment has no boundary data, so a dataset on it could
   *  never run — the dialog hides those. */
  available: boolean;
}

export interface CustomPreviewColumn {
  name: string;
  numeric: boolean;
  distinct_sample: string[];
  /** [min, max] of the parsed values; present only when numeric. */
  range?: [number, number];
}

export interface CustomPreview {
  columns: CustomPreviewColumn[];
  row_count: number;
  sample_rows: Record<string, string>[];
  filename: string;
}

export interface CreateCustomExposomeInput {
  file: File;
  name: string;
  boundary: string;
  key_col: string;
  value_cols: string[];
  description?: string;
  year_col?: string | null;
  value_labels?: Record<string, string>;
  value_units?: Record<string, string>;
}

export interface VariableMetadata {
  label: string;
  description: string;
  boundary: 'Point' | 'BG' | 'ZCTA5' | 'Tract' | 'County';
  /** C3 method — drives the Buffer step. areal = buffer∩polygon (buffer +
   * grid); grid = buffer∩raster cells (buffer only); proximity = distance from
   * the point, no buffer. */
  spatial_method?: 'areal' | 'grid' | 'proximity';
  coverage_years: [number, number];
  coverage_region: 'CONUS' | 'US' | 'AK_HI';
  experiment: string;
  /** Linked SPACESCANS ontology node id (see frontend/public/ontology). */
  ontology_id?: string;
  /** Originating dataset, e.g. "US Census ACS (5-year)". */
  data_source?: string;
  /** "static" products apply to any study period (no year restriction). */
  temporal?: 'static' | 'yearly';
  variable_type: 'categorical' | 'continuous';
  display_unit: string;
  value_cols: string[];
}

export interface VariableCatalog {
  schema_version: number;
  variables: Record<string, VariableMetadata>;
}

export interface ColumnSummary {
  name: string;
  dtype: "numeric" | "categorical";
  non_null: number;
  null_count: number;
  unique: number | null;
  min: number | null;
  max: number | null;
  mean: number | null;
}

export interface ResultsPreview {
  /** What one row stands for; absent on results from before phase D. */
  level?: OutputLevel;
  columns: string[];
  rows: (string | number | null)[][];
  total_rows: number;
  has_more: boolean;
  summary: ColumnSummary[];
}

export interface HistogramData {
  name: string;
  bins: number[];
  counts: number[];
  min: number | null;
  max: number | null;
  sample_size: number;
}

export interface HistogramResponse {
  level?: OutputLevel;
  histograms: HistogramData[];
}

export interface StateGeoBucket {
  state_fips: string;
  count: number;
  mean: number | null;
}

export interface GeoResponse {
  /** Participant level: each participant counts once, in the state of their
   *  longest location episode. */
  level?: OutputLevel;
  by_state: StateGeoBucket[];
}

export interface CoverageResponse {
  row_count: number;
  variables: Record<string, VarCoverage>;
}

export const api = {
  // Auth
  signup: (data: {
    email: string;
    password: string;
    first_name: string;
    last_name: string;
  }) =>
    request<{ access_token: string }>("/api/auth/signup", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  login: (data: { email: string; password: string }) =>
    request<{ access_token: string }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  changePassword: (data: {
    email: string;
    current_password: string;
    new_password: string;
  }) =>
    request<{ access_token: string }>("/api/auth/change-password", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  // Tasks
  listTasks: () => request<Task[]>("/api/tasks"),

  createTask: (task_name: string) =>
    request<Task>("/api/tasks", {
      method: "POST",
      body: JSON.stringify({ task_name }),
    }),

  getTask: (id: string) => request<Task>(`/api/tasks/${id}`),

  deleteTask: (id: string) =>
    request<{ status: string }>(`/api/tasks/${id}`, {
      method: "DELETE",
    }),

  deleteStaleTasks: () =>
    request<{ deleted: number }>(`/api/tasks/stale`, {
      method: "DELETE",
    }),

  renameTask: (id: string, task_name: string) =>
    request<Task>(`/api/tasks/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ task_name }),
    }),

  getResultsPreview: (id: string, limit = 20) =>
    request<ResultsPreview>(`/api/tasks/${id}/results/preview?limit=${limit}`),

  // Uses XHR (not fetch) so we can report upload progress via onProgress.
  uploadFile: (
    id: string,
    file: File,
    onProgress?: (pct: number) => void,
  ): Promise<{
    row_count?: number;
    columns?: string[];
    date_range?: { min: string; max: string };
  }> =>
    new Promise((resolve, reject) => {
      const token =
        typeof window !== "undefined" ? localStorage.getItem("token") : null;
      const formData = new FormData();
      formData.append("file", file);
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `${API_BASE}/api/tasks/${id}/upload`);
      if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
      xhr.upload.onprogress = (e) => {
        if (onProgress && e.lengthComputable) {
          onProgress(Math.round((e.loaded / e.total) * 100));
        }
      };
      xhr.onload = () => {
        let body: Record<string, unknown> = {};
        try {
          body = JSON.parse(xhr.responseText);
        } catch {
          /* non-JSON response */
        }
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(body);
        } else {
          if (xhr.status === 401) handleUnauthorized();
          reject(
            new ApiError(
              xhr.status,
              (body.detail as string) ||
                (body.error as string) ||
                "Upload failed",
            ),
          );
        }
      };
      xhr.onerror = () =>
        reject(new ApiError(0, "Network error during upload"));
      xhr.send(formData);
    }),

  saveConfig: (id: string, config: TaskConfigInput) =>
    request<Task>(`/api/tasks/${id}/config`, {
      method: "PUT",
      body: JSON.stringify({ experiment: "auto", ...config }),
    }),

  startTask: (id: string) =>
    request<{ status: "running" | "queued"; task_id?: string; pid?: number }>(
      `/api/tasks/${id}/start`,
      { method: "POST" },
    ),

  stopTask: (id: string) =>
    request<{ status: string }>(`/api/tasks/${id}/stop`, {
      method: "POST",
    }),

  getCoverage: (id: string, variables: string[]) =>
    request<CoverageResponse>(
      `/api/tasks/${id}/coverage?variables=${variables.join(",")}`,
    ),

  getStatus: (id: string) => request<TaskStatus>(`/api/tasks/${id}/status`),

  getLogs: (id: string, since?: string) =>
    request<unknown[]>(
      `/api/tasks/${id}/logs${since ? `?since=${since}` : ""}`,
    ),

  /** Download the merged result.csv, or a named intermediate under output/.
   * Performs the download (authenticated fetch + blob) — it does NOT return a
   * URL, since a bare URL can't carry the auth header. */
  downloadResults: (id: string, file?: string) =>
    downloadFile(
      `/api/tasks/${id}/results${file ? `?file=${encodeURIComponent(file)}` : ""}`,
      file ?? "result.csv",
    ),

  getResultsHistogram: (id: string, bins = 20) =>
    request<HistogramResponse>(`/api/tasks/${id}/results/histogram?bins=${bins}`),

  getResultsGeo: (id: string, value_col: string) =>
    request<GeoResponse>(
      `/api/tasks/${id}/results/geo?value_col=${encodeURIComponent(value_col)}`,
    ),

  listVariables: () => request<VariableCatalog>("/api/variables"),

  // --- custom exposomes (per-user library) ---------------------------------
  // Deliberately separate from /api/variables: that endpoint is unauthenticated
  // with a pinned schema_version, so per-user rows must not appear in it. The
  // wizard fetches both and merges them.

  listCustomBoundaries: () =>
    request<{ boundaries: CustomBoundary[] }>("/api/custom-exposomes/boundaries"),

  listCustomExposomes: () =>
    request<{ variables: Record<string, CustomExposome> }>("/api/custom-exposomes"),

  previewCustomExposome: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return requestMultipart<CustomPreview>("/api/custom-exposomes/preview", form);
  },

  createCustomExposome: (input: CreateCustomExposomeInput) => {
    const form = new FormData();
    form.append("file", input.file);
    form.append("name", input.name);
    form.append("boundary", input.boundary);
    form.append("key_col", input.key_col);
    form.append("value_cols", JSON.stringify(input.value_cols));
    form.append("description", input.description ?? "");
    form.append("value_labels", JSON.stringify(input.value_labels ?? {}));
    form.append("value_units", JSON.stringify(input.value_units ?? {}));
    if (input.year_col) form.append("year_col", input.year_col);
    return requestMultipart<CustomExposome>("/api/custom-exposomes", form);
  },

  previewCustomRaster: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return requestMultipart<CustomRasterPreview>("/api/custom-exposomes/preview-raster", form);
  },

  createCustomRaster: (input: CreateCustomRasterInput) => {
    const form = new FormData();
    for (const f of input.files) form.append("files", f.file);
    form.append("years", JSON.stringify(input.files.map((f) => f.year)));
    form.append("name", input.name);
    form.append("bands", JSON.stringify(input.bands));
    form.append("value_cols", JSON.stringify(input.value_cols));
    form.append("description", input.description ?? "");
    form.append("value_labels", JSON.stringify(input.value_labels ?? {}));
    form.append("value_units", JSON.stringify(input.value_units ?? {}));
    return requestMultipart<CustomExposome>("/api/custom-exposomes/raster", form);
  },

  deleteCustomExposome: (datasetId: string) =>
    request<{ status: string }>(`/api/custom-exposomes/${datasetId}`, {
      method: "DELETE",
    }),

  // --- registered datasets ("My datasets", PHASE_D §2.2) -------------------
  // The caller's own datasets plus every dataset another user shared with the
  // whole deployment; only the owner may edit, re-share or delete one.

  listDatasets: async (): Promise<RegisteredDataset[]> =>
    normalizeDatasetList(await request<unknown>("/api/datasets")),

  getDataset: async (id: string): Promise<RegisteredDataset> =>
    unwrapDataset(await request<unknown>(`/api/datasets/${encodeURIComponent(id)}`)),

  /** Upload and register. Resolves to the new dataset, or null when the reply
   *  does not describe it (the caller then reloads the list). */
  createDataset: async (
    input: { files: File[]; metadata: DatasetMetadata },
    onProgress?: (pct: number) => void,
  ): Promise<RegisteredDataset | null> => {
    const form = new FormData();
    for (const f of input.files) form.append("files", f, f.name);
    form.append("metadata", JSON.stringify(input.metadata));
    const raw = await xhrMultipart<unknown>("POST", "/api/datasets", form, onProgress);
    try {
      return unwrapDataset(raw);
    } catch {
      return null;
    }
  },

  /** Owner only: metadata and/or visibility. Null when the reply does not
   *  describe the dataset (the caller then reloads). */
  updateDataset: async (
    id: string,
    patch: Record<string, unknown>,
  ): Promise<RegisteredDataset | null> => {
    const raw = await request<unknown>(`/api/datasets/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    });
    try {
      return unwrapDataset(raw);
    } catch {
      return null;
    }
  },

  /** Owner only; refused (409) while a running task uses the dataset. */
  deleteDataset: (id: string) =>
    request<unknown>(`/api/datasets/${encodeURIComponent(id)}`, { method: "DELETE" }),
};
