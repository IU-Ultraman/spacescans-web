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
  { name: "pid", type: "string", desc: "Patient identifier — unique per row" },
  { name: "startDate", type: "YYYY-MM-DD", desc: "Episode start (ISO date)" },
  { name: "endDate", type: "YYYY-MM-DD", desc: "Episode end (ISO date)" },
  { name: "longitude", type: "float", desc: "WGS84 (EPSG:4326), e.g. -82.35" },
  { name: "latitude", type: "float", desc: "WGS84 (EPSG:4326), e.g. 29.65" },
];

const OPTIONAL_COLUMNS: { name: string; type: string; desc: string }[] = [
  { name: "state_fips", type: "string (2)", desc: "Census state FIPS, e.g. '06' — leading zeros required" },
  { name: "county_fips", type: "string (5)", desc: "state+county FIPS, e.g. '06037'" },
  { name: "tract_geoid", type: "string (11)", desc: "state+county+tract GEOID" },
  { name: "bg_geoid", type: "string (12)", desc: "state+county+tract+block-group GEOID" },
];

export interface DataSummary {
  filename: string;
  row_count: number;
  columns: string[];
  date_range?: { min: string; max: string };
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
    setError(null);

    try {
      const task = await api.createTask(taskName.trim());
      const result = await api.uploadFile(task.id, file);
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
    setError(null);
    try {
      const res = await fetch("/demo_cohort.csv");
      if (!res.ok) throw new Error("demo fetch failed");
      const text = await res.text();
      const demoFile = new File([text], "demo_cohort.csv", { type: "text/csv" });
      const name = taskName.trim() || "Demo cohort";
      const id = taskId ?? (await api.createTask(name)).id;
      const result = await api.uploadFile(id, demoFile);
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
          <Label htmlFor="task-name">Task Name</Label>
          <Input
            id="task-name"
            placeholder="e.g., Florida Health Study 2024"
            value={taskName}
            onChange={(e) => setTaskName(e.target.value)}
            disabled={!!dataSummary}
          />
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
              case-sensitive). Geographic identifiers (state_fips, county_fips,
              tract_geoid, bg_geoid) are optional — they are computed downstream
              if absent.
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

            <details className="group">
              <summary className="cursor-pointer text-xs font-medium text-muted-foreground hover:text-foreground">
                Optional GEOID columns (4) — if you have pre-computed them
              </summary>
              <div className="mt-2 overflow-x-auto rounded-md border bg-background">
                <table className="w-full text-xs">
                  <thead className="bg-muted/50">
                    <tr className="border-b">
                      <th className="px-3 py-2 text-left font-medium">Column</th>
                      <th className="px-3 py-2 text-left font-medium">Type</th>
                      <th className="px-3 py-2 text-left font-medium">Description</th>
                    </tr>
                  </thead>
                  <tbody>
                    {OPTIONAL_COLUMNS.map((c) => (
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
              <p className="mt-2 text-xs text-muted-foreground/80">
                FIPS columns are <strong>strings</strong>, not integers. Leading
                zeros (e.g. <code className="font-mono">&quot;06&quot;</code> for
                California) must be preserved — open the file in a text editor or
                set the type to text in your spreadsheet tool to avoid losing
                them.
              </p>
            </details>
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
              Try with a demo cohort (500 patients)
            </Button>
            <p className="text-center text-[11px] text-muted-foreground/70">
              A 500-patient sample spread across the US — no file needed.
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

        {/* Upload button (before summary) */}
        {file && !dataSummary && !uploading && (
          <Button
            onClick={handleUpload}
            disabled={!taskName.trim()}
            className="w-full"
            size="lg"
          >
            <Upload className="size-4" />
            Upload & Validate
          </Button>
        )}

        {/* Loading */}
        {uploading && (
          <div className="flex items-center justify-center gap-2 py-4 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" />
            Uploading and validating your data...
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
