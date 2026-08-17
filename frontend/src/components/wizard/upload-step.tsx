"use client";

import { useCallback, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useVariableCatalog } from "@/lib/use-variable-catalog";
import { VariableCoveragePanel } from "./variable-coverage-panel";
import {
  Upload,
  FileSpreadsheet,
  AlertCircle,
  CheckCircle2,
  ArrowLeft,
  ArrowRight,
  Loader2,
  Info,
} from "lucide-react";

const REQUIRED_COLUMNS: { name: string; type: string; desc: string }[] = [
  { name: "pid", type: "string", desc: "Patient identifier — or PATID; unique per row" },
  { name: "startDate", type: "YYYY-MM-DD", desc: "Episode start — or M/D/YYYY, see below" },
  { name: "endDate", type: "YYYY-MM-DD", desc: "Episode end — or M/D/YYYY, see below" },
  { name: "longitude", type: "float", desc: "WGS84 (EPSG:4326), e.g. -82.35" },
  { name: "latitude", type: "float", desc: "WGS84 (EPSG:4326), e.g. 29.65" },
];

// Only state_fips is worth asking for: it is the sole input to the results
// map. No exposure calculation reads any cohort geography — every variable
// derives its own spatial unit (block group, tract, ZCTA5, county) from the
// coordinates, verified by re-running a cohort with deliberately wrong GEOIDs
// and getting bit-identical values. county_fips/tract_geoid/bg_geoid still
// pass through to the output untouched if supplied; they just aren't worth
// asking a user to produce.

export interface DataSummary {
  filename: string;
  row_count: number;
  columns: string[];
  date_range?: { min: string; max: string };
}

/** Pick a default task name that isn't taken yet.
 *
 * Task names are unique per user (the API answers 409 "A task named 'X'
 * already exists", trimmed + case-insensitive), so any auto-filled default has
 * to dodge the existing ones — otherwise running the demo a second time, or
 * re-uploading the same file, dead-ends on an error the user didn't cause.
 * Falls back to the bare name if the lookup fails; the backend still guards. */
async function suggestFreeName(base: string): Promise<string> {
  const clean = base.trim() || "Cohort";
  let taken: Set<string>;
  try {
    const tasks = await api.listTasks();
    taken = new Set(tasks.map((t) => t.task_name.trim().toLowerCase()));
  } catch {
    return clean;
  }
  if (!taken.has(clean.toLowerCase())) return clean;
  for (let i = 2; i <= 99; i++) {
    const candidate = `${clean} ${i}`;
    if (!taken.has(candidate.toLowerCase())) return candidate;
  }
  return `${clean} ${Date.now()}`;
}

interface UploadStepProps {
  onComplete: (taskId: string, dataSummary: DataSummary) => void;
  /** Optional — present once the wizard has a step before this one. */
  onBack?: () => void;
  /** Restore prior upload when revisiting via Back, so we don't create a
   *  second task. When both are set, the summary view is shown immediately. */
  initialTaskId?: string | null;
  initialSummary?: DataSummary | null;
  /** Exposures chosen in the previous step — used to show coverage right
   *  after upload instead of waiting until Review. */
  selectedVariables?: string[];
}

export function UploadStep({
  onComplete, onBack, initialTaskId = null, initialSummary = null,
  selectedVariables = [],
}: UploadStepProps) {
  const { catalog } = useVariableCatalog();
  const [taskName, setTaskName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [dataSummary, setDataSummary] = useState<DataSummary | null>(initialSummary);
  const [taskId, setTaskId] = useState<string | null>(initialTaskId);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback((f: File) => {
    setError(null);
    setDataSummary(null);
    setTaskId(null);

    if (!f.name.endsWith(".csv")) {
      setError("Please upload a CSV file.");
      return;
    }

    if (f.size > 100 * 1024 * 1024) {
      setError("File size must be under 100 MB.");
      return;
    }

    setFile(f);

    // Prefill the (required) task name from the filename so picking a file
    // never dead-ends on a greyed-out upload button. The functional update
    // never clobbers a name the user typed — including one typed while the
    // suggestion was still resolving.
    void (async () => {
      const suggestion = await suggestFreeName(f.name.replace(/\.csv$/i, ""));
      setTaskName((prev) => (prev.trim() ? prev : suggestion));
    })();
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      const f = e.dataTransfer.files[0];
      if (f) handleFile(f);
    },
    [handleFile]
  );

  const handleUpload = async () => {
    if (!file || !taskName.trim()) return;

    setUploading(true);
    setProgress(0);
    setError(null);

    try {
      const task = await api.createTask(taskName.trim());
      const result = await api.uploadFile(task.id, file, setProgress);
      const summary: DataSummary = {
        filename: file.name,
        row_count: result.row_count ?? 0,
        columns: result.columns ?? [],
        date_range: result.date_range,
      };
      setTaskId(task.id);
      setDataSummary(summary);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.detail);
      } else {
        setError("Upload failed. Please try again.");
      }
    } finally {
      setUploading(false);
    }
  };

  // One-click: load the bundled demo cohort so a user without their own CSV
  // can experience the full flow. Uploads to the existing task on revisit.
  const handleUseDemo = async () => {
    setUploading(true);
    setProgress(0);
    setError(null);
    try {
      const res = await fetch("/demo_cohort.csv");
      if (!res.ok) throw new Error("demo fetch failed");
      const text = await res.text();
      const demoFile = new File([text], "demo_cohort.csv", { type: "text/csv" });
      // "Demo cohort" collides on the second demo run (names are unique per
      // user), so fall back to the first free variant and show it in the field.
      const name = taskName.trim() || (await suggestFreeName("Demo cohort"));
      if (!taskName.trim()) setTaskName(name);
      const id = taskId ?? (await api.createTask(name)).id;
      const result = await api.uploadFile(id, demoFile, setProgress);
      setFile(demoFile);
      setTaskId(id);
      setDataSummary({
        filename: "demo_cohort.csv",
        row_count: result.row_count ?? 0,
        columns: result.columns ?? [],
        date_range: result.date_range,
      });
    } catch (err) {
      setError(
        err instanceof ApiError ? err.detail : "Failed to load the demo cohort.",
      );
    } finally {
      setUploading(false);
    }
  };

  const handleNext = () => {
    if (taskId && dataSummary) {
      onComplete(taskId, dataSummary);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Upload Your Data</CardTitle>
        <CardDescription>
          Provide a task name and upload a CSV cohort file. See the required
          column schema below before uploading.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Coverage scope notice — set expectations before uploading */}
        <div className="flex items-start gap-2.5 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-xs text-amber-700 dark:text-amber-400">
          <Info className="mt-0.5 size-4 shrink-0" />
          <p>
            Exposures cover the <strong>contiguous US (CONUS)</strong> only, each
            for specific years. Residences outside CONUS (or outside an
            exposure&apos;s years) won&apos;t be linked — you&apos;ll see a
            coverage check after uploading.
          </p>
        </div>

        {/* Task name */}
        <div className="space-y-2">
          <Label htmlFor="task-name">
            Task Name <span className="text-destructive">*</span>
          </Label>
          <Input
            id="task-name"
            placeholder="e.g., Florida Health Study 2024"
            value={taskName}
            onChange={(e) => setTaskName(e.target.value)}
            disabled={!!dataSummary}
            required
            aria-required="true"
          />
          {!dataSummary && (
            <p className="text-xs text-muted-foreground">
              You can name your task before uploading the file; otherwise, the
              task will be automatically named after the uploaded file.
            </p>
          )}
        </div>

        {/* CSV format spec */}
        {!dataSummary && (
          <div className="space-y-3 rounded-lg border bg-muted/30 p-4">
            <div className="flex items-center gap-2">
              <Info className="size-4 text-primary" />
              <h3 className="text-sm font-semibold text-foreground">
                Required CSV format
              </h3>
            </div>
            <p className="text-xs text-muted-foreground">
              Your CSV must include these 5 columns (header names are
              case-sensitive, except that the identifier may be{" "}
              <code className="font-mono">pid</code> or{" "}
              <code className="font-mono">PATID</code>). Add{" "}
              <code className="font-mono">state_fips</code> only if you want the
              Geographic Distribution map on the results page. Any other columns
              you include are passed through to your results unchanged.
            </p>

            <div className="overflow-x-auto rounded-md border bg-background">
              <table className="w-full text-xs">
                <thead className="bg-muted/50">
                  <tr className="border-b">
                    <th className="px-3 py-2 text-left font-medium">Column</th>
                    <th className="px-3 py-2 text-left font-medium">Type</th>
                    <th className="px-3 py-2 text-left font-medium">Description</th>
                  </tr>
                </thead>
                <tbody>
                  {REQUIRED_COLUMNS.map((c) => (
                    <tr key={c.name} className="border-b last:border-b-0">
                      <td className="px-3 py-2 font-mono font-medium text-foreground">
                        {c.name}
                      </td>
                      <td className="px-3 py-2 font-mono text-muted-foreground">
                        {c.type}
                      </td>
                      <td className="px-3 py-2 text-muted-foreground">{c.desc}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="rounded-md border bg-background px-3 py-2.5">
              <p className="text-xs font-medium text-foreground">
                Accepted date formats
              </p>
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                <code className="font-mono">2017-08-19</code> (ISO, preferred)
                or <code className="font-mono">8/19/2017</code>.
              </p>
              <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground/80">
                Use <strong>one format throughout the file</strong> — startDate
                and endDate must match. Slash dates are read{" "}
                <strong>month first</strong>, so{" "}
                <code className="font-mono">3/4/2017</code> is 4 March.
              </p>
            </div>

            <div className="rounded-md border bg-background px-3 py-2.5">
              <p className="text-xs font-medium text-foreground">
                Optional: <code className="font-mono">state_fips</code>
              </p>
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                2-digit Census state FIPS — only draws the results map. Keep it
                a string: <code className="font-mono">&quot;06&quot;</code>, not{" "}
                <code className="font-mono">6</code>.
              </p>
            </div>
          </div>
        )}

        {/* Dropzone */}
        {!dataSummary && (
          <div className="space-y-2">
            <Label>Data File</Label>
            <div
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              className={cn(
                "flex cursor-pointer flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed px-6 py-12 transition-all",
                dragOver
                  ? "border-primary bg-primary/5"
                  : "border-muted-foreground/25 hover:border-muted-foreground/40 hover:bg-muted/30",
                file && "border-primary/50 bg-primary/5"
              )}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".csv"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) handleFile(f);
                }}
              />

              {file ? (
                <>
                  <FileSpreadsheet className="size-10 text-primary" />
                  <div className="text-center">
                    <p className="font-medium text-foreground">{file.name}</p>
                    <p className="text-xs text-muted-foreground">
                      {(file.size / 1024).toFixed(1)} KB
                    </p>
                  </div>
                </>
              ) : (
                <>
                  <Upload className="size-10 text-muted-foreground/40" />
                  <div className="text-center">
                    <p className="font-medium text-muted-foreground">
                      Drop your CSV file here, or click to browse
                    </p>
                    <p className="text-xs text-muted-foreground/60">
                      CSV files up to 100 MB
                    </p>
                  </div>
                </>
              )}
            </div>
          </div>
        )}

        {/* Demo cohort shortcut — try the flow without your own CSV */}
        {!dataSummary && !uploading && (
          <div className="space-y-2">
            <div className="flex items-center gap-3">
              <div className="h-px flex-1 bg-border" />
              <span className="text-xs text-muted-foreground">or</span>
              <div className="h-px flex-1 bg-border" />
            </div>
            <Button
              type="button"
              variant="outline"
              onClick={handleUseDemo}
              className="w-full"
              size="lg"
            >
              <FileSpreadsheet className="size-4" />
              Try with a demo cohort (100 patients)
            </Button>
            <p className="text-center text-[11px] text-muted-foreground/70">
              Real coordinates across 30 states — no file needed.
            </p>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="flex items-start gap-2.5 rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
            <AlertCircle className="mt-0.5 size-4 shrink-0" />
            <p>{error}</p>
          </div>
        )}

        {/* Upload button (before summary). The button is disabled until a task
            name exists — say so, otherwise a picked file plus a greyed-out
            button reads as "the upload is broken". */}
        {file && !dataSummary && !uploading && (
          <div className="space-y-2">
            <Button
              onClick={handleUpload}
              disabled={!taskName.trim()}
              className="w-full"
              size="lg"
            >
              <Upload className="size-4" />
              Upload &amp; Validate
            </Button>
            {!taskName.trim() && (
              <p className="flex items-center justify-center gap-1.5 text-xs text-muted-foreground">
                <AlertCircle className="size-3.5 shrink-0 text-destructive" />
                Your file is ready — enter a{" "}
                <span className="font-medium text-foreground">Task Name</span>{" "}
                above to upload.
              </p>
            )}
          </div>
        )}

        {/* Loading */}
        {uploading && (
          <div className="space-y-2 py-2">
            <div className="flex items-center justify-between text-sm text-muted-foreground">
              <span className="flex items-center gap-2">
                <Loader2 className="size-4 animate-spin" />
                {progress < 100
                  ? "Uploading your data…"
                  : "Validating your data…"}
              </span>
              <span className="font-mono tabular-nums">{progress}%</span>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-primary transition-all duration-200"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>
        )}

        {/* Data summary */}
        {dataSummary && (
          <div className="space-y-4">
            <div className="flex items-start gap-2.5 rounded-lg border border-green-500/30 bg-green-500/5 p-3 text-sm text-green-700 dark:text-green-400">
              <CheckCircle2 className="mt-0.5 size-4 shrink-0" />
              <p>File uploaded and validated successfully.</p>
            </div>

            <Card size="sm" className="bg-muted/30">
              <CardHeader className="border-b">
                <CardTitle className="flex items-center gap-2">
                  <FileSpreadsheet className="size-4 text-primary" />
                  {dataSummary.filename}
                </CardTitle>
              </CardHeader>
              <CardContent className="grid gap-3 sm:grid-cols-2">
                <div>
                  <p className="text-xs text-muted-foreground">Rows</p>
                  <p className="font-medium">
                    {dataSummary.row_count.toLocaleString()}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Columns</p>
                  <p className="font-medium">{dataSummary.columns.length}</p>
                </div>
                {dataSummary.date_range && (
                  <>
                    <div>
                      <p className="text-xs text-muted-foreground">
                        Date Range (Min)
                      </p>
                      <p className="font-medium">
                        {dataSummary.date_range.min}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground">
                        Date Range (Max)
                      </p>
                      <p className="font-medium">
                        {dataSummary.date_range.max}
                      </p>
                    </div>
                  </>
                )}
                <div className="sm:col-span-2">
                  <p className="mb-1.5 text-xs text-muted-foreground">
                    Column Names
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {dataSummary.columns.map((col) => (
                      <span
                        key={col}
                        className="rounded-md bg-muted px-2 py-0.5 text-xs text-muted-foreground"
                      >
                        {col}
                      </span>
                    ))}
                  </div>
                </div>
              </CardContent>
            </Card>

            {taskId && selectedVariables.length > 0 && (
              <div className="rounded-lg border bg-muted/10 p-4">
                <p className="text-sm font-medium text-foreground">
                  Cohort coverage
                </p>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  How much of this cohort each selected exposure can cover. If a
                  value is low, go back a step to adjust your exposures.
                </p>
                <div className="mt-3 space-y-2.5">
                  {selectedVariables.map((key) => (
                    <div key={key}>
                      <div className="text-xs font-medium">
                        {catalog?.variables[key]?.label ?? key}
                      </div>
                      <VariableCoveragePanel taskId={taskId} variableKey={key} />
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Next button (with Back once a previous step exists) */}
        {dataSummary && (
          <div className="flex justify-between pt-2">
            {onBack ? (
              <Button variant="outline" onClick={onBack} size="lg">
                <ArrowLeft className="size-4" />
                Back
              </Button>
            ) : (
              <span />
            )}
            <Button onClick={handleNext} size="lg">
              Next
              <ArrowRight className="size-4" />
            </Button>
          </div>
        )}

        {/* Back button before an upload exists (so exposures can be revised) */}
        {onBack && !dataSummary && !uploading && (
          <div className="flex pt-2">
            <Button variant="outline" onClick={onBack} size="lg">
              <ArrowLeft className="size-4" />
              Back
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
