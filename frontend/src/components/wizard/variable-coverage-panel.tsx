"use client";

import { useEffect, useState } from "react";
import { api, type VarCoverage } from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  CheckCircle2,
  AlertTriangle,
  AlertCircle,
  MapPin,
  Calendar,
} from "lucide-react";

interface VariableCoveragePanelProps {
  taskId: string;
  variableKey: string;
}

export function VariableCoveragePanel({
  taskId,
  variableKey,
}: VariableCoveragePanelProps) {
  const [data, setData] = useState<VarCoverage | null>(null);
  const [rowCount, setRowCount] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .getCoverage(taskId, [variableKey])
      .then((resp) => {
        if (cancelled) return;
        setRowCount(resp.row_count);
        setData(resp.variables[variableKey] ?? null);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [taskId, variableKey]);

  if (error) return null; // fail silently — don't obstruct Run
  if (!data || rowCount === null) {
    return (
      <div className="mt-2 text-xs text-muted-foreground">
        Checking coverage...
      </div>
    );
  }

  const tone =
    data.coverage_pct >= 95
      ? "ok"
      : data.coverage_pct >= 60
        ? "warn"
        : "bad";
  const Icon =
    tone === "ok" ? CheckCircle2 : tone === "warn" ? AlertTriangle : AlertCircle;

  return (
    <div
      className={cn(
        "mt-2 rounded-md border p-2 text-xs",
        tone === "ok" &&
          "border-emerald-500/30 bg-emerald-500/5 text-emerald-700 dark:text-emerald-400",
        tone === "warn" &&
          "border-amber-500/30 bg-amber-500/5 text-amber-700 dark:text-amber-400",
        tone === "bad" &&
          "border-red-500/30 bg-red-500/5 text-red-700 dark:text-red-400",
      )}
    >
      <div className="flex items-center gap-1.5 font-medium">
        <Icon className="size-3.5" />
        {data.coverage_pct}% of your cohort covered
      </div>

      {/* Geographic and temporal coverage shown as two separate dimensions —
          static layers have no year restriction, so their Time row says so. */}
      <div className="mt-1.5 space-y-1 text-muted-foreground">
        <div className="flex items-start gap-1.5">
          <MapPin className="mt-0.5 size-3 shrink-0" />
          <span>
            <span className="font-medium">Location:</span>{" "}
            {data.patients_in_region.toLocaleString()} /{" "}
            {rowCount.toLocaleString()} in the contiguous US ({data.boundary})
          </span>
        </div>
        <div className="flex items-start gap-1.5">
          <Calendar className="mt-0.5 size-3 shrink-0" />
          <span>
            <span className="font-medium">Time:</span>{" "}
            {data.temporal === "static" ? (
              <>any study period — static layer (no year restriction)</>
            ) : (
              <>
                {data.patients_in_time_window.toLocaleString()} /{" "}
                {rowCount.toLocaleString()} within {data.coverage_years[0]}–
                {data.coverage_years[1]}
              </>
            )}
          </span>
        </div>
      </div>
      {data.warnings.map((w, i) => (
        <div key={i} className="mt-1">
          {w}
        </div>
      ))}
    </div>
  );
}
