"use client";

import { useEffect, useState } from "react";
import { WizardLayout } from "@/components/wizard/wizard-layout";
import { UploadStep, type DataSummary } from "@/components/wizard/upload-step";
import { BufferStep, type BufferConfig } from "@/components/wizard/buffer-step";
import { VariablesStep } from "@/components/wizard/variables-step";
import { ReviewStep } from "@/components/wizard/review-step";
import type { RegisteredDataset } from "@/lib/datasets";
import { DEFAULT_OUTPUT_LEVEL, type OutputLevel } from "@/lib/output-level";

export default function NewTaskPage() {
  const [step, setStep] = useState(0);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [dataSummary, setDataSummary] = useState<DataSummary | null>(null);
  const [bufferConfig, setBufferConfig] = useState<BufferConfig | null>(null);
  const [outputLevel, setOutputLevel] = useState<OutputLevel>(DEFAULT_OUTPUT_LEVEL);
  const [selectedVariables, setSelectedVariables] = useState<string[]>([]);
  const [selectedDatasets, setSelectedDatasets] = useState<RegisteredDataset[]>([]);

  // Unsaved-progress guard: any exposure picked or moved past step 1.
  const hasProgress = step > 0 || selectedVariables.length > 0 || selectedDatasets.length > 0;
  useEffect(() => {
    if (!hasProgress) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [hasProgress]);

  // Catalog-first flow: Select Exposures → Upload → Settings → Review.
  const handleVariablesComplete = (variables: string[], datasets: RegisteredDataset[]) => {
    setSelectedVariables(variables);
    setSelectedDatasets(datasets);
    setStep(1);
  };

  const handleUploadComplete = (id: string, summary: DataSummary) => {
    setTaskId(id);
    setDataSummary(summary);
    setStep(2);
  };

  const handleSettingsComplete = (config: BufferConfig, level: OutputLevel) => {
    setBufferConfig(config);
    setOutputLevel(level);
    setStep(3);
  };

  return (
    <WizardLayout currentStep={step} confirmExit={hasProgress}>
      {step === 0 && (
        <VariablesStep
          onComplete={handleVariablesComplete}
          initialSelection={selectedVariables}
          initialDatasets={selectedDatasets}
        />
      )}

      {step === 1 && (
        <UploadStep
          onComplete={handleUploadComplete}
          onBack={() => setStep(0)}
          initialTaskId={taskId}
          initialSummary={dataSummary}
          selectedVariables={selectedVariables}
        />
      )}

      {step === 2 && (
        <BufferStep
          onComplete={handleSettingsComplete}
          onBack={() => setStep(1)}
          initialConfig={bufferConfig ?? undefined}
          initialOutputLevel={outputLevel}
          selectedVariables={selectedVariables}
          selectedDatasets={selectedDatasets}
        />
      )}

      {step === 3 && taskId && dataSummary && bufferConfig && (
        <ReviewStep
          taskId={taskId}
          dataSummary={dataSummary}
          bufferConfig={bufferConfig}
          outputLevel={outputLevel}
          selectedVariables={selectedVariables}
          selectedDatasets={selectedDatasets}
          onBack={() => setStep(2)}
        />
      )}
    </WizardLayout>
  );
}
