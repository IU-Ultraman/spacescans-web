"use client";

import { Button } from "@/components/ui/button";
import { Progress, ProgressLabel, ProgressValue } from "@/components/ui/progress";
import { CheckCircle2, Loader2, Pause, Square } from "lucide-react";

interface ProgressPanelProps {
  progress: number;
  message: string;
  onStop: () => void;
  /** Ordered list of variable pipeline step names (e.g. ["c3_bg","c4_ndi"]). */
  steps?: string[];
  /** Step currently executing on the backend (may be a pre/post-step like "csv_to_parquet" or "merge"). */
  currentStep?: string;
  /** Total variable steps (== steps?.length); kept for the "Step N/M" label. */
  totalSteps?: number;
}

// Canonical execution order across the whole pipeline, including pre- and
// post-steps that aren't surfaced as items in the step list. Used purely to
// decide done/running/pending state for items in `steps`.
const STEP_ORDER = ["csv_to_parquet", "c3_bg", "c4_ndi", "c4_wi", "merge"];

function stepState(
  stepName: string,
  currentStep: string | undefined,
): "done" | "running" | "pending" {
  if (!currentStep) return "pending";
  const currentIdx = STEP_ORDER.indexOf(currentStep);
  const myIdx = STEP_ORDER.indexOf(stepName);
  if (currentIdx === -1 || myIdx === -1) return "pending";
  if (myIdx < currentIdx) return "done";
  if (myIdx === currentIdx) return "running";
  return "pending";
}

export function ProgressPanel({
  progress,
  message,
  onStop,
  steps,
  currentStep,
  totalSteps,
}: ProgressPanelProps) {
  return (
    <div className="rounded-lg border bg-card p-6 shadow-sm">
      <div className="space-y-4">
        <Progress value={progress} className="w-full">
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
            className="gap-1.5"
          >
            <Square className="size-3.5" />
            Stop Task
          </Button>
        </div>

        {steps && steps.length > 0 && (
          <div className="space-y-1 border-t pt-3">
            {steps.map((stepName, i) => {
              const state = stepState(stepName, currentStep);
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
                  <span className="font-mono text-xs text-muted-foreground">
                    Step {i + 1}/{totalSteps ?? steps.length}
                  </span>
                  <span className="font-medium">{stepName}</span>
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
