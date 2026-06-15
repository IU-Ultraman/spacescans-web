"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { api, type Task } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/status-badge";
import {
  ArrowLeft,
  Download,
  Calendar,
  FileText,
  CheckCircle2,
} from "lucide-react";

export default function TaskResultsPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = params.id;

  const [task, setTask] = useState<Task | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const t = await api.getTask(id);
        if (cancelled) return;
        setTask(t);
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
      <div className="mx-auto max-w-2xl py-12 text-center">
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

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Link
          href={`/dashboard/task/${id}`}
          className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          <ArrowLeft className="size-5" />
        </Link>
        <div className="flex-1">
          <h1 className="text-2xl font-bold tracking-tight">{task.name}</h1>
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
            <span className="font-medium">{task.name}</span>
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

      {/* Download section */}
      <div className="rounded-lg border bg-card p-6 shadow-sm">
        <h3 className="font-semibold">Download Results</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          Download the output files from your completed linkage task.
        </p>
        <Button onClick={handleDownload} className="mt-4 gap-2">
          <Download className="size-4" />
          Download result.csv
        </Button>

        {/* Intermediate parquet downloads disabled until backend /results endpoint supports ?file= queries. */}
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
