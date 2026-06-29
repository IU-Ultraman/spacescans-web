"use client";

import { Button } from "@/components/ui/button";
import { Progress, ProgressLabel, ProgressValue } from "@/components/ui/progress";
import { CheckCircle2, Loader2, Pause, Square } from "lucide-react";

interface ProgressPanelProps {
  progress: number;
  message: string;
  onStop: () => void;
  /** True once a stop has been requested but the task hasn't halted yet. */
  stopping?: boolean;
  /** Ordered list of variable pipeline step names (e.g. ["c3_bg","c4_ndi"]). */
  steps?: string[];
  /** Step currently executing on the backend (may be a pre/post-step like "csv_to_parquet" or "merge"). */
  currentStep?: string;
  /** Total variable steps (== steps?.length); kept for the "Step N/M" label. */
  totalSteps?: number;
}

// Friendly names for the raw pipeline step ids. C3 builds spatial weights;
// C4 links an exposure to the cohort. The suffix after c3_/c4_ is a boundary
// (bg/zcta5/tract_us…) or a variable key (ndi/wi/zcta5_cbp…).
const STEP_SUFFIX_LABEL: Record<string, string> = {
  bg: "Block Group",
  zcta5: "ZCTA5",
  tract_us: "Census Tract",
  county_us: "County",
  cache: "cache",
  ndi: "Neighborhood Deprivation",
  wi: "Walkability",
  zcta5_cbp: "Community Organizations",
  tiger_roads: "Road Proximity",
  nhd_bluespace: "Bluespace",
  noise: "Noise",
  temis: "UV Exposure",
  vnl: "Night-time Lights",
  tract_fara: "Food Access",
};

function prettify(s: string): string {
  return s.replace(/_/g, " ");
}

function friendlyStep(raw: string): string {
  if (raw === "csv_to_parquet") return "Preparing your data";
  if (raw === "merge") return "Merging results";
  if (raw.startsWith("c3_")) {
    const s = raw.slice(3);
    return `Computing spatial weights — ${STEP_SUFFIX_LABEL[s] ?? prettify(s)}`;
  }
  if (raw.startsWith("c4_")) {
    const s = raw.slice(3);
    return `Linking ${STEP_SUFFIX_LABEL[s] ?? prettify(s)}`;
  }
  return prettify(raw);
}

function stepState(
  stepName: string,
  currentStep: string | undefined,
  steps: string[],
): "done" | "running" | "pending" {
  if (!currentStep) return "pending";
  // Real execution order = csv_to_parquet, then this task's variable steps in
  // order, then merge. Derived from the actual step list so it is correct for
  // every experiment (not just a hardcoded bg_ndi_wi order).
  const order = ["csv_to_parquet", ...steps, "merge"];
  const currentIdx = order.indexOf(currentStep);
  const myIdx = order.indexOf(stepName);
  if (currentIdx === -1 || myIdx === -1) return "pending";
  if (myIdx < currentIdx) return "done";
  if (myIdx === currentIdx) return "running";
  return "pending";
}

export function ProgressPanel({
  progress,
  message,
  onStop,
  stopping = false,
  steps,
  currentStep,
  totalSteps,
}: ProgressPanelProps) {
  return (
    <div className="rounded-lg border bg-card p-6 shadow-sm">
      <div className="space-y-4">
        <Progress value={progress * 100} className="w-full">
          <ProgressLabel>Progress</ProgressLabel>
          <ProgressValue />
        </Progress>

        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">
            {message || "Processing..."}
          </p>

          <Button
            variant="destructive"
            size="sm"
            onClick={onStop}
            disabled={stopping}
            className="gap-1.5"
          >
            {stopping ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <Square className="size-3.5" />
            )}
            {stopping ? "Stopping…" : "Stop Task"}
          </Button>
        </div>

        {steps && steps.length > 0 && (
          <div className="space-y-1 border-t pt-3">
            {steps.map((stepName, i) => {
              const state = stepState(stepName, currentStep, steps);
              const Icon =
                state === "done"
                  ? CheckCircle2
                  : state === "running"
                    ? Loader2
                    : Pause;
              const iconClass =
                state === "running"
                  ? "size-4 animate-spin text-primary"
                  : state === "done"
                    ? "size-4 text-green-600"
                    : "size-4 text-muted-foreground";
              return (
                <div
                  key={stepName}
                  className="flex items-center gap-2 text-sm"
                >
                  <Icon className={iconClass} aria-hidden />
                  <span className="font-mono text-[10px] text-muted-foreground tabular-nums">
                    {i + 1}/{totalSteps ?? steps.length}
                  </span>
                  <span className="font-medium">{friendlyStep(stepName)}</span>
                  <span className="font-mono text-[10px] text-muted-foreground">
                    {stepName}
                  </span>
                  {state === "running" && message && (
                    <span className="text-muted-foreground">— {message}</span>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
