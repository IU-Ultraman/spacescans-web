"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api, type Task } from "@/lib/api";
import { StatusBadge } from "@/components/status-badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
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
          Configure
        </Link>
      );
  }
}

export function TaskList() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

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

  return (
    <div className="space-y-6">
      <Header />
      <Card className="overflow-hidden p-0">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="w-[35%] pl-6">Task Name</TableHead>
              <TableHead className="w-[20%]">Created</TableHead>
              <TableHead className="w-[25%]">Status</TableHead>
              <TableHead className="w-[20%] text-right pr-6">Action</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {tasks.map((task) => (
              <TableRow
                key={task.id}
                className="group cursor-pointer transition-colors"
              >
                <TableCell className="pl-6">
                  <span className="font-medium text-foreground">
                    {task.task_name}
                  </span>
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
                        value={task.progress}
                        className="w-32"
                      />
                    )}
                  </div>
                </TableCell>
                <TableCell className="text-right pr-6">
                  <ActionButton task={task} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
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
