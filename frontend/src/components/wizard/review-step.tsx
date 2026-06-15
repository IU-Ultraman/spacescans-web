"use client";

import { useEffect, useState } from "react";
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
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  ArrowLeft,
  ChevronDown,
  FileSpreadsheet,
  Loader2,
  Play,
  Settings,
  Shapes,
  Tags,
} from "lucide-react";
import type { DataSummary } from "./upload-step";
import type { BufferConfig } from "./buffer-step";

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
  const [metadata, setMetadata] = useState<
    Record<string, { id: string; label: string; definition: string }>
  >({});

  useEffect(() => {
    fetch("/ontology/metadata.json")
      .then((r) => r.json())
      .then(setMetadata)
      .catch(() => {});
  }, []);

  const getLabel = (id: string) => {
    const meta = metadata[id];
    return meta ? meta.label.replace(/_/g, " ") : id;
  };

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
            <InfoItem
              label="Raster resolution"
              value={`${bufferConfig.raster_res_m} m`}
            />
          </div>
        </SummarySection>

        {/* Variables */}
        <SummarySection
          icon={<Tags className="size-4" />}
          title={`Selected Variables (${selectedVariables.length})`}
        >
          <div className="flex flex-wrap gap-1.5">
            {selectedVariables.map((id) => (
              <span
                key={id}
                className="rounded-md bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary"
              >
                {getLabel(id)}
              </span>
            ))}
          </div>
        </SummarySection>

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
