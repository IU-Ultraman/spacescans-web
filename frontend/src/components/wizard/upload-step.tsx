"use client";

import { useCallback, useRef, useState } from "react";
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
  Upload,
  FileSpreadsheet,
  AlertCircle,
  CheckCircle2,
  ArrowRight,
  Loader2,
} from "lucide-react";

export interface DataSummary {
  filename: string;
  row_count: number;
  columns: string[];
  date_range?: { min: string; max: string };
}

interface UploadStepProps {
  onComplete: (taskId: string, dataSummary: DataSummary) => void;
}

export function UploadStep({ onComplete }: UploadStepProps) {
  const [taskName, setTaskName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dataSummary, setDataSummary] = useState<DataSummary | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback((f: File) => {
    setError(null);
    setDataSummary(null);
    setTaskId(null);

    if (!f.name.endsWith(".csv")) {
      setError("Please upload a CSV file.");
      return;
    }

    if (f.size > 100 * 1024 * 1024) {
      setError("File size must be under 100 MB.");
      return;
    }

    setFile(f);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      const f = e.dataTransfer.files[0];
      if (f) handleFile(f);
    },
    [handleFile]
  );

  const handleUpload = async () => {
    if (!file || !taskName.trim()) return;

    setUploading(true);
    setError(null);

    try {
      const task = await api.createTask(taskName.trim());
      const result = await api.uploadFile(task.id, file);
      const summary: DataSummary = {
        filename: file.name,
        row_count: result.row_count ?? 0,
        columns: result.columns ?? [],
        date_range: result.date_range,
      };
      setTaskId(task.id);
      setDataSummary(summary);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.detail);
      } else {
        setError("Upload failed. Please try again.");
      }
    } finally {
      setUploading(false);
    }
  };

  const handleNext = () => {
    if (taskId && dataSummary) {
      onComplete(taskId, dataSummary);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Upload Your Data</CardTitle>
        <CardDescription>
          Provide a task name and upload a CSV file to get started.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Task name */}
        <div className="space-y-2">
          <Label htmlFor="task-name">Task Name</Label>
          <Input
            id="task-name"
            placeholder="e.g., Florida Health Study 2024"
            value={taskName}
            onChange={(e) => setTaskName(e.target.value)}
            disabled={!!dataSummary}
          />
        </div>

        {/* Dropzone */}
        {!dataSummary && (
          <div className="space-y-2">
            <Label>Data File</Label>
            <div
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              className={cn(
                "flex cursor-pointer flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed px-6 py-12 transition-all",
                dragOver
                  ? "border-primary bg-primary/5"
                  : "border-muted-foreground/25 hover:border-muted-foreground/40 hover:bg-muted/30",
                file && "border-primary/50 bg-primary/5"
              )}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".csv"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) handleFile(f);
                }}
              />

              {file ? (
                <>
                  <FileSpreadsheet className="size-10 text-primary" />
                  <div className="text-center">
                    <p className="font-medium text-foreground">{file.name}</p>
                    <p className="text-xs text-muted-foreground">
                      {(file.size / 1024).toFixed(1)} KB
                    </p>
                  </div>
                </>
              ) : (
                <>
                  <Upload className="size-10 text-muted-foreground/40" />
                  <div className="text-center">
                    <p className="font-medium text-muted-foreground">
                      Drop your CSV file here, or click to browse
                    </p>
                    <p className="text-xs text-muted-foreground/60">
                      CSV files up to 100 MB
                    </p>
                  </div>
                </>
              )}
            </div>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="flex items-start gap-2.5 rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
            <AlertCircle className="mt-0.5 size-4 shrink-0" />
            <p>{error}</p>
          </div>
        )}

        {/* Upload button (before summary) */}
        {file && !dataSummary && !uploading && (
          <Button
            onClick={handleUpload}
            disabled={!taskName.trim()}
            className="w-full"
            size="lg"
          >
            <Upload className="size-4" />
            Upload & Validate
          </Button>
        )}

        {/* Loading */}
        {uploading && (
          <div className="flex items-center justify-center gap-2 py-4 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" />
            Uploading and validating your data...
          </div>
        )}

        {/* Data summary */}
        {dataSummary && (
          <div className="space-y-4">
            <div className="flex items-start gap-2.5 rounded-lg border border-green-500/30 bg-green-500/5 p-3 text-sm text-green-700 dark:text-green-400">
              <CheckCircle2 className="mt-0.5 size-4 shrink-0" />
              <p>File uploaded and validated successfully.</p>
            </div>

            <Card size="sm" className="bg-muted/30">
              <CardHeader className="border-b">
                <CardTitle className="flex items-center gap-2">
                  <FileSpreadsheet className="size-4 text-primary" />
                  {dataSummary.filename}
                </CardTitle>
              </CardHeader>
              <CardContent className="grid gap-3 sm:grid-cols-2">
                <div>
                  <p className="text-xs text-muted-foreground">Rows</p>
                  <p className="font-medium">
                    {dataSummary.row_count.toLocaleString()}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Columns</p>
                  <p className="font-medium">{dataSummary.columns.length}</p>
                </div>
                {dataSummary.date_range && (
                  <>
                    <div>
                      <p className="text-xs text-muted-foreground">
                        Date Range (Min)
                      </p>
                      <p className="font-medium">
                        {dataSummary.date_range.min}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground">
                        Date Range (Max)
                      </p>
                      <p className="font-medium">
                        {dataSummary.date_range.max}
                      </p>
                    </div>
                  </>
                )}
                <div className="sm:col-span-2">
                  <p className="mb-1.5 text-xs text-muted-foreground">
                    Column Names
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {dataSummary.columns.map((col) => (
                      <span
                        key={col}
                        className="rounded-md bg-muted px-2 py-0.5 text-xs text-muted-foreground"
                      >
                        {col}
                      </span>
                    ))}
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        )}

        {/* Next button */}
        {dataSummary && (
          <div className="flex justify-end pt-2">
            <Button onClick={handleNext} size="lg">
              Next
              <ArrowRight className="size-4" />
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
