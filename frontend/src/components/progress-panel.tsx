"use client";

import { Button } from "@/components/ui/button";
import { Progress, ProgressLabel, ProgressValue } from "@/components/ui/progress";
import { Square } from "lucide-react";

interface ProgressPanelProps {
  progress: number;
  message: string;
  onStop: () => void;
}

export function ProgressPanel({ progress, message, onStop }: ProgressPanelProps) {
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
      </div>
    </div>
  );
}
