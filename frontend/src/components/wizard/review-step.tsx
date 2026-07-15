"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Pill } from "@/components/ui/chip";
import { api, ApiError } from "@/lib/api";
import { useVariableCatalog } from "@/lib/use-variable-catalog";
import { groupByExperiment } from "@/lib/variable-grouping";
import { cn } from "@/lib/utils";
import {
  ArrowLeft,
  ChevronDown,
  Clock,
  FileSpreadsheet,
  Loader2,
  Play,
  Settings,
  Shapes,
  Tags,
  Target,
} from "lucide-react";
import type { DataSummary } from "./upload-step";
import type { BufferConfig } from "./buffer-step";
import { VariableCoveragePanel } from "./variable-coverage-panel";

// Helper — heuristic runtime estimate
function estimateRuntime(nRows: number, bufferM: number, nVariables: number): string {
  // Base C3 boundary_overlap_fast on BG (~218k boundaries): from /loop testing:
  //   100k patients × 270m × 25m raster = ~4 min
  //   scales roughly linearly with patients
  //   scales with buffer area ~ (bufferM/270)^1.5 (raster cost)
  //   C4 steps add ~30s each
  const c3MinutesBase = 4.0 * (nRows / 100000) * Math.pow(bufferM / 270, 1.5);
  const c4Minutes = 0.5 * nVariables;
  const totalMin = c3MinutesBase + c4Minutes;
  if (totalMin < 1) return "<1 min";
  if (totalMin < 5) return `~${Math.ceil(totalMin)} min`;
  return `~${Math.round(totalMin)} min`;
}

interface ReviewStepProps {
  taskId: string;
  dataSummary: DataSummary;
  bufferConfig: BufferConfig;
  selectedVariables: string[];
  onBack: () => void;
}

export function ReviewStep({
  taskId,
  dataSummary,
  bufferConfig,
  selectedVariables,
  onBack,
}: ReviewStepProps) {
  const router = useRouter();
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [cpuCores, setCpuCores] = useState("4");
  const [memoryLimit, setMemoryLimit] = useState("8");
  const { catalog } = useVariableCatalog();

  const handleStart = async () => {
    setStarting(true);
    setError(null);

    try {
      await api.saveConfig(taskId, {
        buffer: bufferConfig,
        variables: selectedVariables,
        advanced: {
          cpu_cores: parseInt(cpuCores) || 4,
          memory_limit_gb: parseInt(memoryLimit) || 8,
        },
      });
      await api.startTask(taskId);
      router.push(`/dashboard/task/${taskId}`);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.detail);
      } else {
        setError("Failed to start the task. Please try again.");
      }
      setStarting(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Review & Run</CardTitle>
        <CardDescription>
          Review your configuration before starting the task.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {/* Data summary */}
        <SummarySection
          icon={<FileSpreadsheet className="size-4" />}
          title="Uploaded Data"
        >
          <div className="grid gap-2 sm:grid-cols-2">
            <InfoItem label="File" value={dataSummary.filename} />
            <InfoItem
              label="Rows"
              value={dataSummary.row_count.toLocaleString()}
            />
            <InfoItem
              label="Columns"
              value={dataSummary.columns.length.toString()}
            />
            {dataSummary.date_range && (
              <InfoItem
                label="Date Range"
                value={`${dataSummary.date_range.min} - ${dataSummary.date_range.max}`}
              />
            )}
          </div>
        </SummarySection>

        {/* Buffer */}
        <SummarySection
          icon={<Shapes className="size-4" />}
          title="Buffer Settings"
        >
          <div className="grid gap-2 sm:grid-cols-2">
            <InfoItem
              label="Shape"
              value="Circle"
            />
            <InfoItem
              label="Radius"
              value={`${bufferConfig.size.toLocaleString()} meters`}
            />
          </div>
        </SummarySection>

        {/* Estimated Runtime */}
        <SummarySection icon={<Clock className="size-4" />} title="Estimated Runtime">
          <p className="text-sm">
            {estimateRuntime(dataSummary.row_count, bufferConfig.size, selectedVariables.length)}
          </p>
          <p className="text-xs text-muted-foreground mt-1">
            Based on {dataSummary.row_count.toLocaleString()} patients × {bufferConfig.size} m buffer × {selectedVariables.length} variable{selectedVariables.length !== 1 ? "s" : ""}. Actual runtime varies.
          </p>
        </SummarySection>

        {/* Variables */}
        <SummarySection
          icon={<Tags className="size-4" />}
          title={`Selected Variables (${selectedVariables.length})`}
        >
          {catalog ? (
            <div className="space-y-3">
              {Object.entries(
                groupByExperiment(selectedVariables, catalog),
              ).map(([expKey, varKeys]) => (
                <div key={expKey}>
                  <div className="text-xs uppercase tracking-wide text-muted-foreground mb-1.5">
                    {expKey}
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {varKeys.map((k) => (
                      <Pill key={k}>
                        {catalog.variables[k]?.label ?? k}
                      </Pill>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {selectedVariables.map((id) => (
                <Pill key={id}>{id}</Pill>
              ))}
            </div>
          )}
        </SummarySection>

        {/* Cohort coverage — pre-flight against the uploaded data */}
        {selectedVariables.length > 0 && (
          <SummarySection
            icon={<Target className="size-4" />}
            title="Cohort Coverage"
          >
            <p className="mb-3 text-xs text-muted-foreground">
              How much of your uploaded cohort each exposure can cover. If a
              value looks low, go back to step 1 and adjust your selection.
            </p>
            <div className="space-y-3">
              {selectedVariables.map((key) => (
                <div key={key}>
                  <div className="text-xs font-medium text-foreground">
                    {catalog?.variables[key]?.label ?? key}
                  </div>
                  <VariableCoveragePanel taskId={taskId} variableKey={key} />
                </div>
              ))}
            </div>
          </SummarySection>
        )}

        {/* Advanced options */}
        <div className="rounded-lg border border-border">
          <button
            type="button"
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="flex w-full items-center justify-between px-4 py-3 text-sm font-medium text-foreground transition-colors hover:bg-muted/40"
          >
            <div className="flex items-center gap-2">
              <Settings className="size-4 text-muted-foreground" />
              Advanced Options
            </div>
            <ChevronDown
              className={cn(
                "size-4 text-muted-foreground transition-transform duration-200",
                showAdvanced && "rotate-180"
              )}
            />
          </button>
          {showAdvanced && (
            <div className="animate-in fade-in slide-in-from-top-1 border-t border-border px-4 py-4 duration-200">
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="cpu-cores">CPU Cores</Label>
                  <Input
                    id="cpu-cores"
                    type="number"
                    min={1}
                    max={64}
                    value={cpuCores}
                    onChange={(e) => setCpuCores(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="memory-limit">Memory Limit (GB)</Label>
                  <Input
                    id="memory-limit"
                    type="number"
                    min={1}
                    max={256}
                    value={memoryLimit}
                    onChange={(e) => setMemoryLimit(e.target.value)}
                  />
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Error */}
        {error && (
          <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
            {error}
          </div>
        )}

        {/* Navigation */}
        <div className="flex justify-between pt-2">
          <Button
            variant="outline"
            onClick={onBack}
            disabled={starting}
            size="lg"
          >
            <ArrowLeft className="size-4" />
            Back
          </Button>
          <Button
            onClick={handleStart}
            disabled={starting}
            size="lg"
            className="min-w-[140px]"
          >
            {starting ? (
              <>
                <Loader2 className="size-4 animate-spin" />
                Starting...
              </>
            ) : (
              <>
                <Play className="size-4" />
                Start Task
              </>
            )}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function SummarySection({
  icon,
  title,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-border bg-muted/10 p-4">
      <div className="mb-3 flex items-center gap-2 text-sm font-medium text-foreground">
        <span className="text-primary">{icon}</span>
        {title}
      </div>
      {children}
    </div>
  );
}

function InfoItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-sm font-medium">{value}</p>
    </div>
  );
}
