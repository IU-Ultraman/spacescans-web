import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

type TaskStatus = "not_started" | "running" | "finished" | "error" | "cancelled";

const statusConfig: Record<
  TaskStatus,
  { label: string; className: string }
> = {
  not_started: {
    label: "Not Started",
    className:
      "bg-muted text-muted-foreground border-muted-foreground/20",
  },
  running: {
    label: "Running",
    className:
      "bg-blue-500/10 text-blue-600 border-blue-500/20 dark:text-blue-400",
  },
  finished: {
    label: "Finished",
    className:
      "bg-emerald-500/10 text-emerald-600 border-emerald-500/20 dark:text-emerald-400",
  },
  error: {
    label: "Error",
    className:
      "bg-red-500/10 text-red-600 border-red-500/20 dark:text-red-400",
  },
  cancelled: {
    label: "Cancelled",
    className:
      "bg-amber-500/10 text-amber-600 border-amber-500/20 dark:text-amber-400",
  },
};

interface StatusBadgeProps {
  status: TaskStatus;
  progress?: number;
  className?: string;
}

export function StatusBadge({ status, progress, className }: StatusBadgeProps) {
  const config = statusConfig[status] ?? statusConfig.not_started;

  return (
    <Badge
      variant="outline"
      className={cn(
        "border font-medium",
        config.className,
        className
      )}
    >
      {status === "running" && (
        <span className="relative mr-1 flex size-2">
          <span className="absolute inline-flex size-full animate-ping rounded-full bg-blue-500 opacity-75" />
          <span className="relative inline-flex size-2 rounded-full bg-blue-500" />
        </span>
      )}
      {config.label}
      {status === "running" && progress != null && (
        <span className="ml-1 tabular-nums opacity-70">{progress}%</span>
      )}
    </Badge>
  );
}
