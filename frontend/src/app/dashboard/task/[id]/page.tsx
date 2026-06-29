"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { api, type Task, type TaskStatus } from "@/lib/api";
import { StatusBadge } from "@/components/status-badge";
import { LogViewer, type LogEntry } from "@/components/log-viewer";
import { ProgressPanel } from "@/components/progress-panel";
import { Button } from "@/components/ui/button";
import {
  ArrowLeft,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Settings,
  ExternalLink,
} from "lucide-react";

export default function TaskDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = params.id;

  const [task, setTask] = useState<Task | null>(null);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState("Processing...");
  // Full status payload from `/api/tasks/{id}/status` — kept separately from
  // `task` so the multi-step fields (current_step, total_steps, steps) survive
  // polling updates and remain available after the run finishes.
  const [taskStatus, setTaskStatus] = useState<TaskStatus | null>(null);
  const [stopping, setStopping] = useState(false);

  const lastTimestampRef = useRef<string | undefined>(undefined);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const logPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const wasRunningRef = useRef(false);
  const notifiedRef = useRef(false);

  // Notify when a task we watched running reaches a terminal state — so a user
  // who navigated away (backgrounded tab) finds out. document.title always
  // updates; a browser Notification fires too if the user granted permission.
  useEffect(() => {
    if (!task) return;
    if (task.status === "running") {
      wasRunningRef.current = true;
      notifiedRef.current = false;
      try {
        if (typeof Notification !== "undefined" && Notification.permission === "default") {
          Notification.requestPermission().catch(() => {});
        }
      } catch {
        /* requestPermission may be unavailable/blocked — fine */
      }
      return;
    }
    if (
      (task.status === "finished" || task.status === "error") &&
      wasRunningRef.current &&
      !notifiedRef.current
    ) {
      notifiedRef.current = true;
      const ok = task.status === "finished";
      document.title = `${ok ? "✓ Done" : "⚠ Failed"} — ${task.task_name}`;
      try {
        if (typeof Notification !== "undefined" && Notification.permission === "granted") {
          new Notification(`SPACESCANS — task ${ok ? "finished" : "failed"}`, {
            body: task.task_name,
          });
        }
      } catch {
        /* Notification construction can throw on some platforms — ignore */
      }
    }
  }, [task?.status, task?.task_name]); // eslint-disable-line react-hooks/exhaustive-deps

  // Fetch the task on mount. We also pull status.json so that already-running
  // or already-finished tasks render their step-list immediately (the polling
  // effect below only fires while status === "running").
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
          // status.json may not exist yet for not_started tasks — fine.
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

  // Fetch initial logs (for non-running states that still have logs)
  useEffect(() => {
    if (!task) return;
    if (task.status === "not_started") return;

    async function fetchLogs() {
      try {
        const rawLogs = await api.getLogs(id);
        const parsed = rawLogs as LogEntry[];
        setLogs(parsed);
        if (parsed.length > 0) {
          lastTimestampRef.current = parsed[parsed.length - 1].ts;
        }
      } catch {
        // Logs may not be available yet
      }
    }
    fetchLogs();
  }, [id, task?.status]); // eslint-disable-line react-hooks/exhaustive-deps

  // Poll status and logs when running
  useEffect(() => {
    if (!task || task.status !== "running") return;

    pollRef.current = setInterval(async () => {
      try {
        const status = await api.getStatus(id);
        setTaskStatus(status);
        setTask((prev) =>
          prev
            ? { ...prev, status: status.status, progress: status.progress }
            : prev,
        );
        if (status.progress !== undefined) {
          setStatusMessage(
            `Progress: ${Math.round((status.progress ?? 0) * 100)}%`,
          );
        }
      } catch {
        // Ignore transient errors
      }
    }, 2000);

    logPollRef.current = setInterval(async () => {
      try {
        const newLogs = (await api.getLogs(
          id,
          lastTimestampRef.current,
        )) as LogEntry[];
        if (newLogs.length > 0) {
          setLogs((prev) => [...prev, ...newLogs]);
          lastTimestampRef.current = newLogs[newLogs.length - 1].ts;
          // Use the last log message as status message
          const lastMsg = newLogs[newLogs.length - 1].msg;
          if (lastMsg) setStatusMessage(lastMsg);
        }
      } catch {
        // Ignore transient errors
      }
    }, 2000);

    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
      if (logPollRef.current) clearInterval(logPollRef.current);
    };
  }, [id, task?.status]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleStop = useCallback(async () => {
    setStopping(true);
    setStatusMessage("Stopping — waiting for the pipeline to halt…");
    try {
      await api.stopTask(id);
      // Do NOT overwrite `task` with the stop response: keep status
      // "running" so the poller stays alive and flips the view to
      // "cancelled" once the backend actually halts the runner.
    } catch (err) {
      setStopping(false);
      setError(err instanceof Error ? err.message : "Failed to stop task");
    }
  }, [id]);

  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
      </div>
    );
  }

  if (error && !task) {
    return (
      <div className="mx-auto max-w-2xl py-12">
        <div className="rounded-lg border border-red-500/20 bg-red-500/5 p-6 text-center">
          <XCircle className="mx-auto mb-3 size-10 text-red-500" />
          <h2 className="text-lg font-semibold text-red-600">
            Failed to Load Task
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">{error}</p>
          <Button
            variant="outline"
            className="mt-4"
            onClick={() => router.push("/dashboard")}
          >
            Back to Dashboard
          </Button>
        </div>
      </div>
    );
  }

  if (!task) return null;

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Link
          href="/dashboard"
          className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          <ArrowLeft className="size-5" />
        </Link>
        <div className="flex-1">
          <h1 className="text-2xl font-bold tracking-tight">{task.task_name}</h1>
          <p className="text-sm text-muted-foreground">Task ID: {task.id}</p>
        </div>
        <StatusBadge status={task.status} progress={task.progress} />
      </div>

      {/* Status-specific content */}
      {task.status === "running" && (
        <>
          <ProgressPanel
            progress={task.progress ?? 0}
            message={statusMessage}
            onStop={handleStop}
            stopping={stopping}
            steps={taskStatus?.steps}
            currentStep={taskStatus?.current_step}
            totalSteps={taskStatus?.total_steps}
          />
          <LogViewer logs={logs} />
        </>
      )}

      {task.status === "finished" && (
        <>
          <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-6">
            <div className="flex items-start gap-4">
              <CheckCircle2 className="mt-0.5 size-6 shrink-0 text-emerald-500" />
              <div className="flex-1">
                <h2 className="text-lg font-semibold text-emerald-600 dark:text-emerald-400">
                  Task Completed Successfully
                </h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  Your linkage task has finished processing. Results are ready
                  for download.
                </p>
                <div className="mt-4 flex gap-3">
                  <Link
                    href={`/dashboard/task/${id}/results`}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-2.5 py-1.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/80"
                  >
                    <ExternalLink className="size-4" />
                    View Results
                  </Link>
                </div>
              </div>
            </div>
          </div>
          <LogViewer logs={logs} />
        </>
      )}

      {task.status === "error" && (
        <>
          <div className="rounded-lg border border-red-500/20 bg-red-500/5 p-6">
            <div className="flex items-start gap-4">
              <XCircle className="mt-0.5 size-6 shrink-0 text-red-500" />
              <div className="flex-1">
                <h2 className="text-lg font-semibold text-red-600 dark:text-red-400">
                  Task Failed
                </h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  {task.error_message ||
                    "An error occurred during processing. Check the logs below for details."}
                </p>
                <Button
                  variant="outline"
                  size="sm"
                  className="mt-3"
                  onClick={() => router.push("/dashboard")}
                >
                  Back to Dashboard
                </Button>
              </div>
            </div>
          </div>
          <LogViewer logs={logs} />
        </>
      )}

      {task.status === "not_started" && (
        <div className="rounded-lg border border-dashed p-8 text-center">
          <Settings className="mx-auto mb-3 size-10 text-muted-foreground/50" />
          <h2 className="text-lg font-semibold">Setup not completed</h2>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
            This task was created but its setup was never finished, so there is
            nothing to run yet. Task setup happens in the New Task flow — start
            a new task there, or delete this one from the dashboard.
          </p>
          <div className="mt-4 flex items-center justify-center gap-2">
            <Link
              href="/dashboard/task/new"
              className="inline-flex items-center rounded-lg bg-primary px-2.5 py-1.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
            >
              Start a new task
            </Link>
            <Link
              href="/dashboard"
              className="inline-flex items-center rounded-lg border border-border bg-background px-2.5 py-1.5 text-sm font-medium transition-colors hover:bg-muted hover:text-foreground"
            >
              Back to Dashboard
            </Link>
          </div>
        </div>
      )}

      {task.status === "cancelled" && (
        <>
          <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-6">
            <div className="flex items-start gap-4">
              <AlertTriangle className="mt-0.5 size-6 shrink-0 text-amber-500" />
              <div className="flex-1">
                <h2 className="text-lg font-semibold text-amber-600 dark:text-amber-400">
                  Task Cancelled
                </h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  This task was stopped before completion.
                </p>
                <Button
                  variant="outline"
                  size="sm"
                  className="mt-3"
                  onClick={() => router.push("/dashboard")}
                >
                  Back to Dashboard
                </Button>
              </div>
            </div>
          </div>
          <LogViewer logs={logs} />
        </>
      )}
    </div>
  );
}
