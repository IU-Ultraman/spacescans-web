const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(detail);
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
    const body = await res.json().catch(() => ({ detail: "Download failed" }));
    const raw = body.detail ?? body.error ?? "Download failed";
    throw new ApiError(
      res.status,
      typeof raw === "string" ? raw : raw?.message || JSON.stringify(raw),
    );
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
    const parsed = await res.json().catch(() => ({ detail: res.statusText }));
    const raw = parsed.detail ?? parsed.error ?? "Upload failed";
    throw new ApiError(
      res.status,
      typeof raw === "string" ? raw : raw?.message || JSON.stringify(raw),
    );
  }
  return res.json() as Promise<T>;
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
    const body = await res.json().catch(() => ({ detail: "Unknown error" }));
    // detail may be a structured object ({error, message, ...}) — FastAPI
    // allows any JSON there and our data pre-flights use that form. Pick a
    // human-readable string so the UI never shows "[object Object]".
    const raw = body.detail ?? body.error ?? "Request failed";
    const message =
      typeof raw === "string"
        ? raw
        : raw?.message || raw?.error || JSON.stringify(raw);
    throw new ApiError(res.status, message);
  }

  return res.json();
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
export interface CustomExposome extends VariableMetadata {
  dataset_id: string;
  variable_key: string;
  /** The user's own geography column in their CSV. */
  key_col: string;
  /** The weights-table column it joins to, e.g. GEOID10. */
  join_col: string;
  year_col: string | null;
  value_labels: Record<string, string>;
  row_count: number;
  distinct_keys: number;
  uploaded_filename: string;
  created_at: string;
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
  display_unit?: string;
  value_labels?: Record<string, string>;
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
  histograms: HistogramData[];
}

export interface StateGeoBucket {
  state_fips: string;
  count: number;
  mean: number | null;
}

export interface GeoResponse {
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

  saveConfig: (id: string, config: Record<string, unknown>) =>
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
    form.append("display_unit", input.display_unit ?? "");
    form.append("value_labels", JSON.stringify(input.value_labels ?? {}));
    if (input.year_col) form.append("year_col", input.year_col);
    return requestMultipart<CustomExposome>("/api/custom-exposomes", form);
  },

  deleteCustomExposome: (datasetId: string) =>
    request<{ status: string }>(`/api/custom-exposomes/${datasetId}`, {
      method: "DELETE",
    }),
};
