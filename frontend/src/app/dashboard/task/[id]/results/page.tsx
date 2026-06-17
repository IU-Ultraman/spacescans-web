"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { api, type Task, type TaskStatus, type ResultsPreview } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/status-badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  ArrowLeft,
  Download,
  Calendar,
  FileText,
  CheckCircle2,
  Table as TableIcon,
  BarChart3,
} from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface IntermediateFile {
  file: string;
  label: string;
}

// All possible pipeline intermediates. We render the subset that the
// task's status.steps reports — falling back to the full list when
// status is unavailable so a stale browser still surfaces every file
// (missing ones will 404 cleanly).
const ALL_INTERMEDIATES: Record<string, IntermediateFile> = {
  c3_bg: { file: "c3_bg.parquet", label: "c3_bg.parquet (BG weights)" },
  c4_ndi: {
    file: "c4_ndi.parquet",
    label: "c4_ndi.parquet (raw NDI per patient)",
  },
  c4_wi: {
    file: "c4_wi.parquet",
    label: "c4_wi.parquet (raw Walkability per patient)",
  },
};

function intermediatesForStatus(
  status: TaskStatus | null,
): IntermediateFile[] {
  const steps = status?.steps;
  if (!steps || steps.length === 0) {
    // Unknown — show all three; missing ones will 404 cleanly.
    return Object.values(ALL_INTERMEDIATES);
  }
  const out: IntermediateFile[] = [];
  for (const step of steps) {
    const entry = ALL_INTERMEDIATES[step];
    if (entry) out.push(entry);
  }
  return out;
}

export default function TaskResultsPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = params.id;

  const [task, setTask] = useState<Task | null>(null);
  const [taskStatus, setTaskStatus] = useState<TaskStatus | null>(null);
  const [preview, setPreview] = useState<ResultsPreview | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const t = await api.getTask(id);
        if (cancelled) return;
        setTask(t);
        try {
          const s = await api.getStatus(id);
          if (!cancelled) setTaskStatus(s);
        } catch {
          // status.json may be unavailable for legacy tasks — fine.
        }
        // Load preview only if task is finished (result.csv exists)
        if (t.status === "finished") {
          try {
            const p = await api.getResultsPreview(id, 10);
            if (!cancelled) setPreview(p);
          } catch (err) {
            if (!cancelled) {
              setPreviewError(
                err instanceof Error ? err.message : "Preview unavailable"
              );
            }
          }
        }
        setLoading(false);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load task");
          setLoading(false);
        }
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [id]);

  function formatCell(value: string | number | null): string {
    if (value === null || value === undefined) return "—";
    if (typeof value === "number") {
      if (Number.isInteger(value)) return String(value);
      return value.toFixed(4);
    }
    const s = String(value);
    return s.length > 30 ? s.slice(0, 27) + "…" : s;
  }

  function formatNum(v: number | null): string {
    if (v === null) return "—";
    if (Number.isInteger(v)) return v.toLocaleString();
    if (Math.abs(v) < 0.001 || Math.abs(v) >= 1e6) {
      return v.toExponential(2);
    }
    return v.toFixed(4);
  }

  function handleDownload() {
    window.open(api.downloadResults(id), "_blank");
  }

  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
      </div>
    );
  }

  if (error || !task) {
    return (
      <div className="mx-auto max-w-5xl py-12 text-center">
        <p className="text-sm text-muted-foreground">
          {error || "Task not found"}
        </p>
        <Button
          variant="outline"
          className="mt-4"
          onClick={() => router.push("/dashboard")}
        >
          Back to Dashboard
        </Button>
      </div>
    );
  }

  const completedAt = task.created_at
    ? new Date(task.created_at).toLocaleString()
    : "Unknown";

  const intermediates = intermediatesForStatus(taskStatus);

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Link
          href={`/dashboard/task/${id}`}
          className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          <ArrowLeft className="size-5" />
        </Link>
        <div className="flex-1">
          <h1 className="text-2xl font-bold tracking-tight">{task.task_name}</h1>
          <p className="text-sm text-muted-foreground">Results</p>
        </div>
        <StatusBadge status={task.status} />
      </div>

      {/* Completion card */}
      <div className="rounded-lg border bg-card p-6 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="flex size-10 items-center justify-center rounded-full bg-emerald-500/10">
            <CheckCircle2 className="size-5 text-emerald-500" />
          </div>
          <div>
            <h2 className="font-semibold">Task Complete</h2>
            <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
              <Calendar className="size-3.5" />
              <span>{completedAt}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Summary card */}
      <div className="rounded-lg border bg-card p-6 shadow-sm">
        <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
          <FileText className="size-4" />
          Task Summary
        </div>
        <div className="mt-3 space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-muted-foreground">Task Name</span>
            <span className="font-medium">{task.task_name}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">Status</span>
            <span className="font-medium capitalize">{task.status}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">Task ID</span>
            <span className="font-mono text-xs">{task.id}</span>
          </div>
        </div>
      </div>

      {/* Preview section */}
      {preview && (
        <div className="rounded-lg border bg-card p-6 shadow-sm">
          <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
            <TableIcon className="size-4" />
            Result Preview
          </div>
          <p className="mt-2 text-xs text-muted-foreground">
            Showing first {preview.rows.length} of{" "}
            <span className="font-medium">{preview.total_rows.toLocaleString()}</span>{" "}
            rows · {preview.columns.length} columns
            {preview.has_more && (
              <span className="text-muted-foreground">
                {" "}
                · download full CSV below for the rest
              </span>
            )}
          </p>
          <div className="mt-3 overflow-x-auto rounded-md border">
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  {preview.columns.map((col) => (
                    <TableHead key={col} className="whitespace-nowrap text-xs font-medium">
                      {col}
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {preview.rows.map((row, i) => (
                  <TableRow key={i}>
                    {row.map((cell, j) => (
                      <TableCell
                        key={j}
                        className="whitespace-nowrap font-mono text-xs"
                        title={cell === null ? "null" : String(cell)}
                      >
                        {formatCell(cell)}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
      )}
      {previewError && !preview && (
        <div className="rounded-lg border border-amber-500/40 bg-amber-500/5 p-4 text-sm text-amber-700 dark:text-amber-400">
          Preview unavailable: {previewError}. The full CSV is still
          downloadable below.
        </div>
      )}

      {/* Summary stats section */}
      {preview && preview.summary && preview.summary.length > 0 && (
        <div className="rounded-lg border bg-card p-6 shadow-sm">
          <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
            <BarChart3 className="size-4" />
            Column Summary
          </div>
          <p className="mt-2 text-xs text-muted-foreground">
            Stats computed over all {preview.total_rows.toLocaleString()} rows.
            NaN coverage shown as a bar (green = non-null, gray = null).
          </p>
          <div className="mt-3 overflow-x-auto rounded-md border">
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="text-xs font-medium">Column</TableHead>
                  <TableHead className="text-xs font-medium">Type</TableHead>
                  <TableHead className="text-xs font-medium">Coverage</TableHead>
                  <TableHead className="text-xs font-medium text-right">Nulls</TableHead>
                  <TableHead className="text-xs font-medium text-right">Min</TableHead>
                  <TableHead className="text-xs font-medium text-right">Mean</TableHead>
                  <TableHead className="text-xs font-medium text-right">Max</TableHead>
                  <TableHead className="text-xs font-medium text-right">Unique</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {preview.summary.map((col) => {
                  const total = col.non_null + col.null_count;
                  const pct = total > 0 ? (col.non_null / total) * 100 : 0;
                  return (
                    <TableRow key={col.name}>
                      <TableCell className="font-mono text-xs">{col.name}</TableCell>
                      <TableCell>
                        <span
                          className={
                            "inline-flex rounded-full px-1.5 py-0.5 text-[10px] font-medium " +
                            (col.dtype === "numeric"
                              ? "bg-blue-500/10 text-blue-700 dark:text-blue-300"
                              : "bg-purple-500/10 text-purple-700 dark:text-purple-300")
                          }
                        >
                          {col.dtype}
                        </span>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <div className="relative h-1.5 w-20 overflow-hidden rounded-full bg-muted">
                            <div
                              className={
                                "absolute inset-y-0 left-0 " +
                                (pct >= 95
                                  ? "bg-emerald-500"
                                  : pct >= 60
                                  ? "bg-amber-500"
                                  : "bg-red-500")
                              }
                              style={{ width: `${pct}%` }}
                            />
                          </div>
                          <span className="text-[10px] font-mono text-muted-foreground tabular-nums">
                            {pct.toFixed(0)}%
                          </span>
                        </div>
                      </TableCell>
                      <TableCell className="text-right font-mono text-xs tabular-nums text-muted-foreground">
                        {col.null_count.toLocaleString()}
                      </TableCell>
                      <TableCell className="text-right font-mono text-xs tabular-nums">
                        {col.dtype === "numeric" ? formatNum(col.min) : "—"}
                      </TableCell>
                      <TableCell className="text-right font-mono text-xs tabular-nums">
                        {col.dtype === "numeric" ? formatNum(col.mean) : "—"}
                      </TableCell>
                      <TableCell className="text-right font-mono text-xs tabular-nums">
                        {col.dtype === "numeric" ? formatNum(col.max) : "—"}
                      </TableCell>
                      <TableCell className="text-right font-mono text-xs tabular-nums">
                        {col.dtype === "categorical" && col.unique !== null
                          ? col.unique.toLocaleString()
                          : "—"}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        </div>
      )}

      {/* Download section */}
      <div className="rounded-lg border bg-card p-6 shadow-sm">
        <h3 className="font-semibold">Download Results</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          Download the output files from your completed linkage task.
        </p>
        <p className="mt-2 text-xs text-muted-foreground">
          <span className="font-medium">Result shape:</span> one row per
          residential episode. A patient with multiple residences during the
          study window gets one row per residence; exposure values reflect
          that specific residence.
        </p>
        <Button onClick={handleDownload} className="mt-4 gap-2">
          <Download className="size-4" />
          Download result.csv
        </Button>

        {intermediates.length > 0 && (
          <details className="mt-4 text-sm">
            <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
              Advanced: pipeline intermediates
            </summary>
            <ul className="mt-2 list-disc space-y-1 pl-4">
              {intermediates.map(({ file, label }) => (
                <li key={file}>
                  <a
                    className="underline hover:text-foreground"
                    href={`${API_BASE}/api/tasks/${id}/results?file=${encodeURIComponent(file)}`}
                    download={file}
                  >
                    {label}
                  </a>
                </li>
              ))}
            </ul>
          </details>
        )}
      </div>

      {/* Navigation */}
      <div className="flex justify-between pt-2">
        <Link
          href={`/dashboard/task/${id}`}
          className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-sm font-medium transition-colors hover:bg-muted hover:text-foreground"
        >
          <ArrowLeft className="size-4" />
          Back to Task
        </Link>
        <Link
          href="/dashboard"
          className="inline-flex items-center rounded-lg border border-border bg-background px-2.5 py-1.5 text-sm font-medium transition-colors hover:bg-muted hover:text-foreground"
        >
          Back to Dashboard
        </Link>
      </div>
    </div>
  );
}
