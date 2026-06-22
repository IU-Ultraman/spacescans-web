"use client";

import { useEffect, useState } from "react";
import { api, type VarCoverage } from "@/lib/api";
import { cn } from "@/lib/utils";
import { CheckCircle2, AlertTriangle, AlertCircle } from "lucide-react";

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
        {data.temporal === "static"
          ? `${data.coverage_pct}% in CONUS coverage area`
          : `${data.coverage_pct}% of your cohort covered`}
      </div>
      <div className="mt-0.5 text-muted-foreground">
        {data.temporal === "static" ? (
          <>
            {data.patients_covered.toLocaleString()} /{" "}
            {rowCount.toLocaleString()} in CONUS ({data.boundary}) — static
            layer, applies to any study period
          </>
        ) : (
          <>
            {data.patients_covered.toLocaleString()} /{" "}
            {rowCount.toLocaleString()} within {data.coverage_years[0]}-
            {data.coverage_years[1]} + {data.boundary} on CONUS
          </>
        )}
      </div>
      {data.warnings.map((w, i) => (
        <div key={i} className="mt-1">
          {w}
        </div>
      ))}
    </div>
  );
}
