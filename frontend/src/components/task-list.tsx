"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api, type Task } from "@/lib/api";
import { useVariableCatalog } from "@/lib/use-variable-catalog";
import { StatusBadge } from "@/components/status-badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Chip } from "@/components/ui/chip";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Plus,
  Eye,
  Settings2,
  AlertCircle,
  Activity,
  Inbox,
  Trash2,
} from "lucide-react";
import { cn } from "@/lib/utils";

function formatDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function ActionButton({ task }: { task: Task }) {
  switch (task.status) {
    case "finished":
      return (
        <Link
          href={`/dashboard/task/${task.id}/results`}
          className={cn(buttonVariants({ variant: "outline", size: "sm" }), "gap-1.5")}
        >
          <Eye className="size-3.5" />
          View Results
        </Link>
      );
    case "running":
      return (
        <Link
          href={`/dashboard/task/${task.id}`}
          className={cn(buttonVariants({ variant: "outline", size: "sm" }), "gap-1.5")}
        >
          <Activity className="size-3.5" />
          View Progress
        </Link>
      );
    case "error":
      return (
        <Link
          href={`/dashboard/task/${task.id}`}
          className={cn(buttonVariants({ variant: "destructive", size: "sm" }), "gap-1.5")}
        >
          <AlertCircle className="size-3.5" />
          View Error
        </Link>
      );
    case "not_started":
    default:
      return (
        <Link
          href={`/dashboard/task/${task.id}`}
          className={cn(buttonVariants({ variant: "outline", size: "sm" }), "gap-1.5")}
        >
          <Settings2 className="size-3.5" />
          Open
        </Link>
      );
  }
}

export function TaskList() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<Task | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | Task["status"]>("all");
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const { catalog } = useVariableCatalog();

  function variableLabel(key: string): string {
    return catalog?.variables[key]?.label ?? key;
  }

  async function handleDelete(task: Task) {
    setDeletingId(task.id);
    setDeleteError(null);
    try {
      await api.deleteTask(task.id);
      setTasks((prev) => prev.filter((t) => t.id !== task.id));
      setConfirmDelete(null);
    } catch (err) {
      setDeleteError(
        err instanceof Error ? err.message : "Failed to delete task"
      );
    } finally {
      setDeletingId(null);
    }
  }

  useEffect(() => {
    let cancelled = false;

    async function fetchTasks() {
      try {
        const data = await api.listTasks();
        if (!cancelled) {
          setTasks(data);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load tasks");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    fetchTasks();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const anyRunning = tasks.some((t) => t.status === "running");
    if (anyRunning && !intervalRef.current) {
      intervalRef.current = setInterval(async () => {
        try {
          const next = await api.listTasks();
          setTasks(next);
        } catch {
          // swallow polling errors; the next tick will retry
        }
      }, 5000);
    } else if (!anyRunning && intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [tasks]);

  if (loading) {
    return (
      <div className="space-y-6">
        <Header />
        <Card className="p-0">
          <div className="flex items-center justify-center py-20">
            <div className="flex flex-col items-center gap-3">
              <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
              <p className="text-sm text-muted-foreground">Loading tasks...</p>
            </div>
          </div>
        </Card>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        <Header />
        <Card className="p-0">
          <div className="flex items-center justify-center py-20">
            <div className="flex flex-col items-center gap-3 text-center">
              <AlertCircle className="size-10 text-destructive" />
              <p className="text-sm text-muted-foreground">{error}</p>
              <Button
                variant="outline"
                size="sm"
                onClick={() => window.location.reload()}
              >
                Retry
              </Button>
            </div>
          </div>
        </Card>
      </div>
    );
  }

  if (tasks.length === 0) {
    return (
      <div className="space-y-6">
        <Header />
        <Card className="p-0">
          <div className="flex items-center justify-center py-20">
            <div className="flex flex-col items-center gap-4 text-center">
              <div className="flex size-14 items-center justify-center rounded-full bg-muted">
                <Inbox className="size-7 text-muted-foreground" />
              </div>
              <div>
                <p className="font-medium text-foreground">No tasks yet</p>
                <p className="mt-1 text-sm text-muted-foreground">
                  Create your first task to get started.
                </p>
              </div>
              <Link
                href="/dashboard/task/new"
                className={cn(buttonVariants({ size: "sm" }), "gap-1.5")}
              >
                <Plus className="size-4" />
                New Task
              </Link>
            </div>
          </div>
        </Card>
      </div>
    );
  }

  const visibleTasks = tasks
    .filter((t) => statusFilter === "all" || t.status === statusFilter)
    .filter((t) =>
      t.task_name.toLowerCase().includes(query.trim().toLowerCase()),
    )
    .sort(
      (a, b) =>
        new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
    );

  return (
    <div className="space-y-6">
      <Header />

      {/* Search + status filter */}
      <div className="flex flex-wrap items-center gap-3">
        <Input
          placeholder="Search tasks by name…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="max-w-xs"
        />
        <select
          value={statusFilter}
          onChange={(e) =>
            setStatusFilter(e.target.value as "all" | Task["status"])
          }
          className="rounded-md border bg-background px-2 py-1.5 text-sm"
        >
          <option value="all">All statuses</option>
          <option value="running">Running</option>
          <option value="finished">Finished</option>
          <option value="error">Error</option>
          <option value="not_started">Not started</option>
          <option value="cancelled">Cancelled</option>
        </select>
        <span className="text-xs text-muted-foreground tabular-nums">
          {visibleTasks.length} of {tasks.length}
        </span>
      </div>

      <Card className="overflow-hidden p-0">
        {visibleTasks.length === 0 ? (
          <div className="py-16 text-center text-sm text-muted-foreground">
            No tasks match your search or filter.
          </div>
        ) : (
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="w-[22%] pl-6">Task Name</TableHead>
              <TableHead className="w-[25%]">Variables</TableHead>
              <TableHead className="w-[15%]">Created</TableHead>
              <TableHead className="w-[20%]">Status</TableHead>
              <TableHead className="w-[18%] text-right pr-6">Action</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {visibleTasks.map((task) => (
              <TableRow
                key={task.id}
                className="group transition-colors hover:bg-muted/40"
              >
                <TableCell className="pl-6">
                  <span className="font-medium text-foreground">
                    {task.task_name}
                  </span>
                </TableCell>
                <TableCell>
                  {task.variables && task.variables.length > 0 ? (
                    <div className="flex flex-wrap gap-1">
                      {task.variables.map((v) => (
                        <Chip key={v} className="text-[10px]">
                          {variableLabel(v)}
                        </Chip>
                      ))}
                    </div>
                  ) : (
                    <span className="text-xs text-muted-foreground italic">
                      not configured
                    </span>
                  )}
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {formatDate(task.created_at)}
                </TableCell>
                <TableCell>
                  <div className="flex flex-col gap-2">
                    <StatusBadge
                      status={task.status}
                      progress={task.progress}
                    />
                    {task.status === "running" && task.progress != null && (
                      <Progress
                        value={task.progress * 100}
                        className="w-32"
                      />
                    )}
                  </div>
                </TableCell>
                <TableCell className="text-right pr-6">
                  <div className="inline-flex items-center gap-1.5">
                    <ActionButton task={task} />
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        setDeleteError(null);
                        setConfirmDelete(task);
                      }}
                      title="Delete task"
                      className="text-muted-foreground hover:text-destructive"
                    >
                      <Trash2 className="size-3.5" />
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        )}
      </Card>

      <Dialog
        open={confirmDelete !== null}
        onOpenChange={(open) => {
          if (!open) {
            setConfirmDelete(null);
            setDeleteError(null);
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete task</DialogTitle>
            <DialogDescription>
              {confirmDelete?.status === "running" ? (
                <>
                  Task <span className="font-medium">{confirmDelete?.task_name}</span> is
                  currently running. Deleting will stop the pipeline and remove all
                  task files. This cannot be undone.
                </>
              ) : (
                <>
                  Are you sure you want to delete{" "}
                  <span className="font-medium">{confirmDelete?.task_name}</span>?
                  All task files (input, output, logs) will be permanently removed.
                  This cannot be undone.
                </>
              )}
            </DialogDescription>
          </DialogHeader>
          {deleteError && (
            <div className="rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 text-sm text-destructive">
              {deleteError}
            </div>
          )}
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setConfirmDelete(null);
                setDeleteError(null);
              }}
              disabled={deletingId !== null}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => confirmDelete && handleDelete(confirmDelete)}
              disabled={deletingId !== null}
            >
              {deletingId !== null ? "Deleting..." : "Delete"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function Header() {
  return (
    <div className="flex items-center justify-between">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground">
          Tasks
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Manage and monitor your analysis tasks.
        </p>
      </div>
      <Link
        href="/dashboard/task/new"
        className={cn(buttonVariants(), "gap-1.5")}
      >
        <Plus className="size-4" />
        New Task
      </Link>
    </div>
  );
}
