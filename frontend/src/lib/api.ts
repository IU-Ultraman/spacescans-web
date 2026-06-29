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
    if (typeof window !== "undefined") {
      localStorage.removeItem("token");
      window.location.href = "/login";
    }
    throw new ApiError(401, "Unauthorized");
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: "Unknown error" }));
    throw new ApiError(
      res.status,
      body.detail || body.error || "Request failed",
    );
  }

  return res.json();
}

export interface Task {
  id: string;
  task_name: string;
  status: "not_started" | "running" | "finished" | "error" | "cancelled";
  progress?: number;
  created_at: string;
  error_message?: string;
  variables?: string[];
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
  status: "not_started" | "running" | "finished" | "error" | "cancelled";
  progress?: number;
  message?: string;
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
  boundary: 'BG' | 'ZCTA5' | 'Tract' | 'County';
  display_unit: string;
  /** "static" products carry one vintage and skip the time-window check. */
  temporal?: 'static' | 'yearly';
}

export interface VariableMetadata {
  label: string;
  description: string;
  boundary: 'BG' | 'ZCTA5' | 'Tract' | 'County';
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

  getResultsPreview: (id: string, limit = 20) =>
    request<ResultsPreview>(`/api/tasks/${id}/results/preview?limit=${limit}`),

  uploadFile: async (id: string, file: File) => {
    const token = localStorage.getItem("token");
    const formData = new FormData();
    formData.append("file", file);
    const res = await fetch(`${API_BASE}/api/tasks/${id}/upload`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: formData,
    });
    if (!res.ok) throw new ApiError(res.status, (await res.json()).detail);
    return res.json();
  },

  saveConfig: (id: string, config: Record<string, unknown>) =>
    request<Task>(`/api/tasks/${id}/config`, {
      method: "PUT",
      body: JSON.stringify({ experiment: "auto", ...config }),
    }),

  startTask: (id: string) =>
    request<Task>(`/api/tasks/${id}/start`, {
      method: "POST",
    }),

  stopTask: (id: string) =>
    request<Task>(`/api/tasks/${id}/stop`, {
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

  downloadResults: (id: string) => `${API_BASE}/api/tasks/${id}/results`,

  getResultsHistogram: (id: string, bins = 20) =>
    request<HistogramResponse>(`/api/tasks/${id}/results/histogram?bins=${bins}`),

  getResultsGeo: (id: string, value_col: string) =>
    request<GeoResponse>(
      `/api/tasks/${id}/results/geo?value_col=${encodeURIComponent(value_col)}`,
    ),

  listVariables: () => request<VariableCatalog>("/api/variables"),
};
