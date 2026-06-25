"use client";

import { useState } from "react";
import { WizardLayout } from "@/components/wizard/wizard-layout";
import { UploadStep, type DataSummary } from "@/components/wizard/upload-step";
import { BufferStep, type BufferConfig } from "@/components/wizard/buffer-step";
import { VariablesStep } from "@/components/wizard/variables-step";
import { ReviewStep } from "@/components/wizard/review-step";

export default function NewTaskPage() {
  const [step, setStep] = useState(0);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [dataSummary, setDataSummary] = useState<DataSummary | null>(null);
  const [bufferConfig, setBufferConfig] = useState<BufferConfig | null>(null);
  const [selectedVariables, setSelectedVariables] = useState<string[]>([]);

  // Catalog-first flow: Select Exposures → Upload → Buffer → Review.
  const handleVariablesComplete = (variables: string[]) => {
    setSelectedVariables(variables);
    setStep(1);
  };

  const handleUploadComplete = (id: string, summary: DataSummary) => {
    setTaskId(id);
    setDataSummary(summary);
    setStep(2);
  };

  const handleBufferComplete = (config: BufferConfig) => {
    setBufferConfig(config);
    setStep(3);
  };

  return (
    <WizardLayout currentStep={step}>
      {step === 0 && (
        <VariablesStep
          onComplete={handleVariablesComplete}
          initialSelection={selectedVariables}
        />
      )}

      {step === 1 && (
        <UploadStep
          onComplete={handleUploadComplete}
          onBack={() => setStep(0)}
          initialTaskId={taskId}
          initialSummary={dataSummary}
        />
      )}

      {step === 2 && (
        <BufferStep
          onComplete={handleBufferComplete}
          onBack={() => setStep(1)}
          initialConfig={bufferConfig ?? undefined}
        />
      )}

      {step === 3 && taskId && dataSummary && bufferConfig && (
        <ReviewStep
          taskId={taskId}
          dataSummary={dataSummary}
          bufferConfig={bufferConfig}
          selectedVariables={selectedVariables}
          onBack={() => setStep(2)}
        />
      )}
    </WizardLayout>
  );
}
